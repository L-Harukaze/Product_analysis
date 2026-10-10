"""A/B 实验（flash改动方案.md §4）：K80 × M03 单轮直出配方，思考模式开/关对照。

用法（backend 目录下运行）：
    python -u -m scripts.ab_thinking_test --group B   # B 组：enable_thinking=false，3 次
    python -u -m scripts.ab_thinking_test --group A   # A 组：现状默认（思考模式），3 次

设计要点：
- 复用生产代码保真：app.registry 加载方法包、execution._round_messages 组装配方五层
- 模拟 flash 终态：刀3（skill.md 第 5 节移除 → 单轮直出）+ 刀4（每表 5 行切片）
- 组内 3 路并发 = flash「并发 3」的实战口径（非理想串行延迟）
- 产物：backend/data/ab_test/{A,B}1-3.json（全文，盲评用）+ summary_{A,B}.json
- 判据（§4）：B 组延迟中位数 < 40s 且四层输出质量可接受 → 关思考模式
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import statistics
import sys
import time
from pathlib import Path

import httpx
import yaml

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import app.services.execution as execution  # noqa: E402
from app.llm_provider import _extract_json  # noqa: E402
from app.registry import Registry, MethodRound, _SECTION5_PATTERN  # noqa: E402

DB_PATH = BACKEND / "data" / "app.db"
ENV_PATH = BACKEND / ".env"
OUT_DIR = BACKEND / "data" / "ab_test"
LLM_YAML = BACKEND / "config" / "llm.yaml"
N_RUNS = 3
FOUR_LAYERS = ("L1_fact", "L2_mechanism", "L3_quantification", "L4_prescription", "confounder_check")


def _load_key() -> str:
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("LLM_EXECUTOR_KEY="):
            v = s.split("=", 1)[1].strip()
            if v and not v.startswith("sk-xxx"):
                return v
    raise SystemExit("[abort] backend/.env 未找到有效的 LLM_EXECUTOR_KEY")


def _load_k80() -> tuple[dict, dict[str, list[dict]]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT p.id, p.name, c.name AS category FROM products p "
        "LEFT JOIN categories c ON c.id=p.category_id WHERE p.name LIKE ? ORDER BY p.created_at",
        ("%K80%",),
    ).fetchall()
    if not rows:
        names = [r["name"] for r in conn.execute("SELECT name FROM products")]
        raise SystemExit(f"[abort] 库中无 K80 产品。现有产品：{names}")
    for r in rows:
        print(f"[k80] 候选：{r['name']}（id={r['id']}，品类={r['category'] or '未分类'}）")
    p = rows[0]
    archive: dict[str, list[dict]] = {}
    for r in conn.execute(
        "SELECT table_id, row_json FROM archive_records WHERE product_id=? ORDER BY table_id, id",
        (p["id"],),
    ):
        archive.setdefault(r["table_id"], []).append(json.loads(r["row_json"]))
    conn.close()
    counts = {t: len(v) for t, v in sorted(archive.items())}
    print(f"[k80] 使用：{p['name']}｜档案行数：{counts}")
    return {"name": p["name"], "category": p["category"] or "未分类"}, archive


def _build_messages(product: dict, archive: dict[str, list[dict]]) -> list[dict[str, str]]:
    reg = Registry()
    reg.load({"M01", "M02", "M03", "M04", "M05", "M06", "M07", "M08", "M09", "S4"})
    pkg = reg.get("M03")

    # 刀3 模拟：第 5 节轮次表移除 → registry 单轮直出兜底形态（registry.py:301 同构）
    pkg.skill_md = _SECTION5_PATTERN.sub("", pkg.skill_md)
    # 刀4 模拟：每表 5 行
    execution._MAX_ROWS_PER_TABLE = 5

    declared_table_ids = sorted({pkg.table_id(k) for k in pkg.input_tables})
    out_mids = list(((pkg.output_schema.get("output") or {}).get("intermediate_tables") or {}).keys())
    r = MethodRound(1, "单轮直出", None, None, declared_table_ids, out_mids,
                    "第 5 节已移除：单轮直出（flash 刀3 形态）")
    msgs = execution._round_messages(
        pkg, r, idx=1, total=1, is_final=True,
        product_name=product["name"], category=product["category"],
        archive_slice=execution._archive_slice(archive, r.input_tables),
        prev_tables={}, shared=reg.shared, last_error=None,
    )
    size = len(json.dumps(msgs, ensure_ascii=False))
    print(f"[m03] 单轮直出配方组装完成：prompt 约 {size / 1000:.1f}K 字符｜输入表：{'/'.join(declared_table_ids)}｜产出：{'/'.join(out_mids) or '（仅终局产出）'}")
    return msgs


async def _call_once(i: int, group: str, key: str, msgs: list[dict[str, str]],
                     model: str, base_url: str) -> dict:
    payload: dict = {"model": model, "messages": msgs,
                     "response_format": {"type": "json_object"}}
    if group == "B":
        payload["enable_thinking"] = False  # 百炼兼容模式：同模型关思考链
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(
            base_url=base_url, headers={"Authorization": f"Bearer {key}"},
            timeout=httpx.Timeout(600.0, connect=15.0),
        ) as client:
            resp = await client.post("/chat/completions", json=payload)
        rec: dict = {"group": group, "run": i, "latency_s": round(time.monotonic() - t0, 1)}
        if resp.status_code != 200:
            rec.update(ok=False, error=f"HTTP {resp.status_code}: {resp.text[:300]}")
            return rec
        body = resp.json()
        msg = body["choices"][0]["message"]
        content = msg.get("content") or ""
        reasoning = msg.get("reasoning_content") or ""
        usage = body.get("usage") or {}
        rec.update(
            ok=True,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            reasoning_chars=len(reasoning), content_chars=len(content),
            content=content, reasoning_head=reasoning[:300],
        )
        try:
            data = _extract_json(content)
            items = data.get("diagnostic_items") or []
            rec.update(json_ok=True, items_n=len(items), four_layers_ok=bool(items) and all(
                str((it or {}).get(k) or "").strip() for it in items for k in FOUR_LAYERS))
        except Exception as e:  # JSON 解析/结构问题：记录不中断
            rec.update(json_ok=False, json_err=f"{type(e).__name__}: {e}"[:200])
        return rec
    except Exception as e:
        return {"group": group, "run": i, "ok": False,
                "error": f"{type(e).__name__}: {e}"[:300],
                "latency_s": round(time.monotonic() - t0, 1)}


async def main(group: str) -> None:
    key = _load_key()
    llm = yaml.safe_load(LLM_YAML.read_text(encoding="utf-8"))
    role = llm["roles"]["executor"]
    model, base_url = role["model"], role["base_url"]
    product, archive = _load_k80()
    msgs = _build_messages(product, archive)

    print(f"\n[exp] {group} 组开始：{N_RUNS} 路并发，model={model}，"
          f"enable_thinking={'false' if group == 'B' else '默认(思考)'}\n")
    results = await asyncio.gather(*(_call_once(i, group, key, msgs, model, base_url)
                                    for i in range(1, N_RUNS + 1)))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for rec in results:
        (OUT_DIR / f"{group}{rec['run']}.json").write_text(
            json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")

    ok = [r for r in results if r.get("ok")]
    lat = [r["latency_s"] for r in ok]
    print(f"\n===== {group} 组结果 =====")
    for r in results:
        if r.get("ok"):
            print(f"  #{r['run']}  延迟={r['latency_s']}s  tokens={r.get('prompt_tokens')}-"
                  f">{r.get('completion_tokens')}  思考链={r['reasoning_chars']}字  "
                  f"JSON={'OK' if r.get('json_ok') else 'FAIL'}  四层={'齐' if r.get('four_layers_ok') else '缺/无'}")
        else:
            print(f"  #{r['run']}  失败：{r.get('error')}")
    if lat:
        med = statistics.median(lat)
        print(f"  中位延迟 {med}s｜成功率 {len(ok)}/{N_RUNS}｜"
              f"四层完整 {(sum(1 for r in ok if r.get('four_layers_ok')))}/{len(ok)}")
        if group == "B":
            print(f"  [判据] 延迟中位数 {'<' if med < 40 else '≥'} 40s "
                  f"{'→ 达标（思考模式可关，待四层盲评确认质量）' if med < 40 else '→ 不达标（保思考模式，目标放宽 5 分钟版）'}")
    summary = {"group": group, "model": model, "enable_thinking": group == "B",
               "runs": [{k: v for k, v in r.items() if k not in ("content", "reasoning_head")}
                        for r in results],
               "median_latency_s": statistics.median(lat) if lat else None}
    (OUT_DIR / f"summary_{group}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  全文已存：{OUT_DIR / f'{group}1-3.json'}（供四层盲评）")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", choices=["A", "B"], required=True,
                    help="A=现状思考模式，B=enable_thinking=false")
    asyncio.run(main(ap.parse_args().group))
