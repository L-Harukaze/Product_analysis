"""M03 回归基准（ARCHITECTURE 6.2 回归基准锚点）。

配方五层定稿后的第一条实测任务 = **系统内复跑 M03 R1-R3，中间表与《M03 v1.0 冻结签发版》
逐字段对齐**；数值级差异 = 配方缺陷，走《缺陷日志.md》登记（S21 接续编号）。
6.2 的对错由这个基准裁决，不凭感觉。

用法：cd backend && python -m scripts.m03_regression
前置：小米SU7 的产品档案（表 A/B/C/D/E/F/G）已入档（豆包采集 → 事务 B 入档）。
      档案不全时脚本打印指引并退出（不臆造数据——回归基准的前提是同一份输入）。
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services.execution import run_method  # noqa: E402

TARGET_PRODUCT = "小米SU7"
METHOD = "M03"
REQUIRED_TABLES = ["A", "B", "C", "D", "E", "F", "G"]

# 冻结签发版"验证数据锚"（历史文档/M03 v1.0冻结签发版.md 第二部分）——数值级比对基准
FROZEN_ANCHORS: dict[str, list[str]] = {
    "ladder 三档官方价（万）": ["21.59", "24.59", "29.99"],
    "2024 全年交付（辆）": ["136854"],
    "2024 智能EV ASP（元）": ["234479", "23.45"],
    "锁单结构（%）": ["28.57", "28.27", "43.16"],
    "锁单总量": ["70000", "88063"],
    "CONF-01 锁单加权价（万）": ["26.06", "26.07"],
    "碳酸锂锚定时点价（元/吨）": ["109700", "75050"],
}


def _norm(text: str) -> str:
    """数字归一：去千分位逗号与空白，便于 136,854 ≡ 136854 的等价判定。"""
    return re.sub(r"[,\s]", "", text)


def main() -> None:
    with TestClient(app, raise_server_exceptions=False) as client:
        state = {"registry": app.state.registry, "llm_provider": app.state.llm_provider}
        from app import db

        def _find(conn):
            d = conn.execute(
                "SELECT d.id, d.status, p.id AS product_id FROM diagnoses d "
                "JOIN products p ON p.id=d.product_id WHERE p.name=? ORDER BY d.created_at",
                (TARGET_PRODUCT,),
            ).fetchall()
            tables: dict[str, int] = {}
            if d:
                tables = {
                    r["table_id"]: r["n"] for r in conn.execute(
                        "SELECT table_id, COUNT(*) AS n FROM archive_records WHERE product_id=? GROUP BY table_id",
                        (d[0]["product_id"],),
                    )
                }
            return [dict(x) for x in d], tables

        diagnoses, tables = db._run_sync(_find)
        missing = [t for t in REQUIRED_TABLES if tables.get(t, 0) == 0]
        if not diagnoses or missing:
            print(f"[SKIP] 回归前置未满足：{'档案缺表 ' + '/'.join(missing) if missing else '无 SU7 诊断'}")
            print("       请先用豆包采集 SU7 七表数据 → 事务 B 入档，再跑本基准（回归要求同一份输入）")
            return

        dx_id = diagnoses[0]["id"]
        print(f"== M03 回归基准：诊断 {dx_id}（档案表 {sorted(tables)}）==")
        asyncio.run(run_method(state, dx_id, METHOD))

        def _read(conn):
            d = conn.execute(
                "SELECT progress_json FROM diagnoses WHERE id=?", (dx_id,)).fetchone()
            rows = conn.execute(
                "SELECT round, table_name, row_json FROM intermediate_tables "
                "WHERE diagnosis_id=? AND method=? ORDER BY round, table_name", (dx_id, METHOD),
            ).fetchall()
            return d["progress_json"], [dict(r) for r in rows]

        raw_progress, mid_rows = db._run_sync(_read)
        entry = next(m for m in json.loads(raw_progress)["methods"] if m["method"] == METHOD)
        print(f"执行结果：phase={entry.get('phase')} rounds={ (entry.get('result') or {}).get('rounds') } "
              f"split={ (entry.get('result') or {}).get('split_record') }")
        if entry["phase"] != "done":
            print(f"[FAIL] M03 未跑通：{json.dumps(entry.get('error'), ensure_ascii=False)[:300]}")
            return
        for r in mid_rows:
            print(f"  R{r['round']} {r['table_name']}：{len(json.loads(r['row_json']))} 行")

        blob = _norm(" ".join(r["row_json"] for r in mid_rows))
        blob += _norm(json.dumps((entry.get("result") or {}).get("notes", []), ensure_ascii=False))
        ok, gaps = 0, []
        for label, values in FROZEN_ANCHORS.items():
            hit = [v for v in values if _norm(v) in blob]
            if hit:
                ok += 1
                print(f"  [OK]   {label}：命中 {hit}")
            else:
                gaps.append(label)
                print(f"  [MISS] {label}：冻结锚点 {values} 未出现在中间表（配方缺陷候选，需人工判别）")
        print(f"\n回归结论：{ok}/{len(FROZEN_ANCHORS)} 组冻结锚点命中")
        if gaps:
            print("未命中组需人工判别：数值级差异 = 配方缺陷 → 登记《缺陷日志.md》S21 接续编号；"
                  "表述级差异（同值不同写法）不构成配方缺陷。")


if __name__ == "__main__":
    main()
