"""事务 A-E 全链路冒烟（真实 LLM；TestClient 起进程内 app，无需另起服务）。

用法：
    cd backend && python -u -m scripts.smoke            # 全量 12 步（实测 45-60 分钟）
    cd backend && python -u -m scripts.smoke --fast     # 快速回归：跳过步骤 11（真实管道），~2 分钟
    cd backend && python -u -m scripts.smoke --steps 1-10,12   # 同上（不含 11 即视为快速模式）

⚠️ 必须 `-u`：不加则 stdout 重定向到文件时块缓冲，日志滞后 20 分钟（缺陷日志 S24）。
覆盖：启动校验链 / 事务 A 路由 / 事务 B 打回与入档（含 L2 冲突、修数、error 档）/ 事务 C-E 真实管道 / 报告 / 裁决 / 评测。
"""
from __future__ import annotations

import json
import re
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def _fast_mode() -> tuple[bool, str]:
    """分层冒烟：只提供"跳过步骤 11（真实管道）"这一档。

    步骤 1-10 + 12 全是纯代码/秒级（事务 A/B + L1/L2 + 端点对照），占全量时长 <10%；
    步骤 11 跑真实管道（6 方法分轮 + QC + 7 域装配 + 重放），实测 26.6 / 35.0 分钟 + 重放 ~12 分钟。
    其余步骤有数据依赖（11 依赖 10 的 rb_id），逐步跳过意义不大且易误判，故不提供逐步开关。

    用法：`python -u -m scripts.smoke --fast` 或 `--steps 1-10,12`（不含 11 即视为快速模式）。
    """
    argv = sys.argv[1:]
    if "--fast" in argv:
        return True, "--fast"
    if "--steps" in argv:
        i = argv.index("--steps")
        spec = argv[i + 1] if i + 1 < len(argv) else ""
        nums: set[int] = set()
        for part in spec.replace(" ", "").split(","):
            if not part:
                continue
            if "-" in part:
                a, b = part.split("-", 1)
                nums |= set(range(int(a), int(b) + 1))
            else:
                nums.add(int(part))
        if nums and 11 not in nums:
            return True, f"--steps {spec}（不含 11）"
    return False, ""


def _cleanup_own(client, *dx_ids: str | None) -> None:
    """只删冒烟**自己创建**的诊断（不碰 Owner 的演示数据），避免列表页越跑越脏。

    每跑一次冒烟都会为「小米SU7」「冒烟测试新品X1」各新建一条诊断；不清的话
    `--fast` 反复回归会把列表堆满（T3-T6 会跑很多次）。产品档案/固化指纹挂在 product 上，不受影响。
    """
    removed = []
    for dx in dict.fromkeys(d for d in dx_ids if d):
        if client.get(f"/diagnoses/{dx}").status_code == 404:
            continue  # 已被前面的步骤删掉
        if client.delete(f"/diagnoses/{dx}").status_code == 200:
            removed.append(dx)
    if removed:
        print(f"13 冒烟自建诊断已清理（{len(removed)} 条，列表页不留痕）：{'、'.join(removed)}")


def main() -> None:
    FAST, fast_reason = _fast_mode()
    with TestClient(app, raise_server_exceptions=False) as client:
        if FAST:
            print(f"[快速模式] {fast_reason} —— 本次跳过步骤 11（真实管道）")
        print("== 1. health ==")
        r = client.get("/health")
        print(r.status_code, r.json())

        print("\n== 2. POST /diagnoses（SU7 固化指纹复用，7.2 幂等快路径）==")
        r = client.post("/diagnoses", json={"product_name": "小米SU7"})
        print(r.status_code)
        body = r.json()
        print(json.dumps(body, ensure_ascii=False, indent=1)[:1500])
        assert r.status_code == 201, f"期望 201，得到 {r.status_code}"
        for k in ("diagnosis_id", "status", "fingerprint", "activation_matrix", "missing_data", "collection_prompt"):
            assert k in body, f"响应缺字段 {k}（对照 types.ts）"
        dx_id = body["diagnosis_id"]
        dims = [f["dimension"] for f in body["fingerprint"]]
        assert dims == ["F1", "F2", "F3", "F4", "F5", "F6"], f"指纹维度残缺：{dims}"
        assert all("source" in f for f in body["fingerprint"]), "指纹缺 source 标注"
        for e in body["activation_matrix"]:
            assert set(e) == {"domain", "method", "form", "reason"}, f"激活矩阵字段漂移：{set(e)}"
        for m in body["missing_data"]:
            assert set(m) <= {"table", "name", "status", "rows"}, f"缺数清单字段漂移：{set(m)}"

        print("\n== 3. POST /diagnoses（新品：无固化 → L3 仲裁失败 → 保守档位降级，3.4）==")
        dx2_id: str | None = None
        r = client.post("/diagnoses", json={
            "product_name": "冒烟测试新品X1",
            "category_hint": "手机",
            "known_facts": {"price": 1999},
            "background": "冒烟测试背景信息",
        })
        print(r.status_code)
        if r.status_code == 201:
            b2 = r.json()
            dx2_id = b2["diagnosis_id"]  # 新品保持 routed（不被步骤 10 入档污染，跨轮稳定）
            print("status:", b2["status"], "| L1/L2 判定:", [
                (f["dimension"], f["value"], f["source"]) for f in b2["fingerprint"] if f["source"] != "L3 仲裁"])
            print("missing tables:", [(m["table"], m["status"]) for m in b2["missing_data"]])
            assert "## 已知产品背景" in b2["collection_prompt"], "background 未注入采集 prompt（契约增量 1）"
        else:
            print(r.json())

        print("\n== 4. GET /diagnoses 列表 ==")
        r = client.get("/diagnoses")
        print(r.status_code, json.dumps(r.json()[:2], ensure_ascii=False))
        for item in r.json():
            assert set(item) == {"diagnosis_id", "product_name", "category", "status",
                                 "stage_hint", "pending_conflicts_n", "updated_at"}, "列表字段漂移（对照 types.ts）"

        print("\n== 5. GET /diagnoses/{id} 详情（mock 丰富度对照）==")
        r = client.get(f"/diagnoses/{dx_id}")
        print(r.status_code)
        d = r.json()
        print("keys:", sorted(d.keys()))
        assert d["fingerprint"] and d["activation_matrix"] and d["missing_data"], "详情缺路由产物"

        print("\n== 6. POST reroute 守卫（routed 状态 → 期待 409）==")
        r = client.post(f"/diagnoses/{dx_id}/reroute")
        print(r.status_code, r.json())
        assert r.status_code == 409, "reroute 守卫失效"
        detail = r.json()["detail"]
        assert set(detail) == {"reason", "expected_states", "current"}, "409 体字段漂移（13.3）"

        print("\n== 7. GET /diagnoses/{id}/collection-prompt（契约 13.1：打回后最新版）==")
        r = client.get(f"/diagnoses/{dx2_id or dx_id}/collection-prompt")
        print(r.status_code)
        assert r.status_code == 200, f"采集 prompt 端点缺失/异常：{r.status_code}（2026-09-16 联调 404 事故回归位）"
        assert "prompt" in r.json() and r.json()["prompt"], "采集 prompt 空响应"
        print(f"prompt 前 80 字：{r.json()['prompt'][:80]}…")

        print("\n== 8. 前端 src/api 端点 <-> 后端 OpenAPI 对照（防两端各说各话）==")
        ts = (Path(__file__).resolve().parent.parent.parent / "frontend" / "src" / "api" / "diagnoses.ts")
        declared: set[str] = set(re.findall(
            r"request<[^>]*>\(\s*'(?:GET|POST|DELETE|PUT|PATCH)'\s*,\s*['`]([^'`]+)['`]", ts.read_text(encoding="utf-8")))

        def _shape(p: str) -> str:
            # TS 模板参数 ${id} 与 FastAPI 参数 {diagnosis_id} 归一为 {}，只比形状
            return re.sub(r"\{[^}]*\}", "{}", re.sub(r"\$\{[^}]*\}", "{p}", p))

        fe_shapes = {_shape(p) for p in declared}
        be_shapes = {_shape(p) for p in app.openapi()["paths"]} - {"/health"}  # health 非契约端点
        extra = be_shapes - fe_shapes
        pending = fe_shapes - be_shapes
        assert not extra, f"后端实现了前端未声明的端点（契约外）：{sorted(extra)}"
        print(f"对照通过：后端 {len(be_shapes)} 个端点全部在前端契约声明内")
        if pending:
            print("[PENDING] 前端已声明、后端后续里程碑实现（事务 B/C/D/E）：", sorted(pending))

        print("\n== 9. DELETE /diagnoses/{id}（列表管理：删除后详情应 404）==")
        r = client.post("/diagnoses", json={"product_name": "删除回归专用Z9"})
        assert r.status_code == 201, "删除回归前置创建失败"
        zid = r.json()["diagnosis_id"]
        r = client.delete(f"/diagnoses/{zid}")
        print(r.status_code, r.json())
        assert r.status_code == 200 and r.json().get("accepted") is True, "删除端点异常"
        r = client.get(f"/diagnoses/{zid}")
        assert r.status_code == 404, "删除后 GET 详情应 404"
        print("删除回归通过：诊断已删、产品档案保留")

        print("\n== 10. 事务 B：POST /data L1 校验循环（打回 + 入档 + ready 迁移）==")
        # 事务 B 会写产品档案（跨诊断复用）——用唯一名一次性产品承载副作用，测完即删，
        # 避免污染 SU7/新品X1 的演示语义（否则下轮 SU7 缺数清空直接 ready）
        rb = client.post("/diagnoses", json={
            "product_name": f"事务B回归专用{uuid.uuid4().hex[:6]}",
            "category_hint": "手机", "known_facts": {"price": 2999},
        })
        assert rb.status_code == 201, "事务B回归前置创建失败"
        rb_id = rb.json()["diagnosis_id"]
        rb_body = rb.json()

        # 10a 打回：类型错误 + 行级三件套缺失 → 200 accepted=false + 行/字段定位
        bad = {"tables": {"A": [{"version": "标准版", "price_official": "21.59万"}]}}
        r = client.post(f"/diagnoses/{rb_id}/data", json={"payload": json.dumps(bad, ensure_ascii=False)})
        assert r.status_code == 200 and r.json()["accepted"] is False, f"打回响应异常：{r.status_code}"
        errs = r.json()["errors"]
        print(f"10a 打回：{len(errs)} 处错误，字段定位：{sorted({e['field'] for e in errs})}")
        assert any(e["field"] == "price_official" and "类型" in e["error"] for e in errs), "类型错误未定位"
        assert any(e["field"] == "source_url" for e in errs), "三件套缺失未定位"
        r = client.get(f"/diagnoses/{dx_id}/collection-prompt")
        assert "拒绝原因" in r.json()["prompt"], "打回条款未注入采集 prompt（6.1）"
        print("10a 打回条款已注入采集 prompt")

        # 10b 合格：按注册表 schema 动态构造全部缺数表的最小合格行 → missing 清空 → ready
        registry = client.app.state.registry
        from app.services.data_validation import build_needed_tables  # noqa: E402

        needed = build_needed_tables(registry, rb_body["activation_matrix"])

        def _is_share_field(f: str) -> bool:
            low = str(f).lower()
            return any(h in low for h in ("share", "percent", "ratio", "率", "份额", "占比"))

        def _min_row(fields: dict) -> dict:
            row: dict = {}
            for f, spec in (fields or {}).items():
                spec = spec or {}
                if not spec.get("required"):
                    continue
                if spec.get("enum"):
                    row[f] = spec["enum"][0]
                elif str(spec.get("type", "")).lower() in ("number", "int", "integer", "float"):
                    # 份额类给 0.5：同组两行闭合到 1，避免构造数据被 L2 算术闭合误判
                    row[f] = 0.5 if _is_share_field(f) else 1
                else:
                    row[f] = "测试值"
            row.update({"source_url": "https://example.com/t", "confidence": "官方", "caliber": "测试口径"})
            return row

        good = {"tables": {tid: [_min_row(slot["fields"]) for _ in range(2)] for tid, slot in needed.items()}}
        r = client.post(f"/diagnoses/{rb_id}/data", json={"payload": json.dumps(good, ensure_ascii=False)})
        assert r.status_code == 200 and r.json()["accepted"] is True, f"合格提交异常：{r.status_code} {r.text[:300]}"
        acc = r.json()
        assert all(m["status"] == "archived" for m in acc["missing_data"]), "入档后清单未刷新"
        assert acc["archive_summary"] and set(acc["archive_summary"][0]) == {"table", "name", "rows"}, "archive_summary 字段漂移"
        r = client.get(f"/diagnoses/{rb_id}")
        assert r.json()["status"] == "ready", f"缺数清空应迁移 ready，实际 {r.json()['status']}"
        assert r.json()["submissions"] and len(r.json()["submissions"]) == 2, "提交历史应有 2 条（1 打回 + 1 入档）"
        print(f"10b 入档 {len(acc['archive_summary'])} 表 → status=ready，提交历史 2 条")

        # 回归诊断保留给步骤 11（事务 C/D/E 复用），步骤 11 末尾清理
        print("10c 回归诊断保留（步骤 11 续用）")

        # 10d L2 冲突闭环（11.3）：跨源碰撞 → 409 触发被拒 → 维持裁决 → 放行
        # 构造：同批提交内同表两行"同维度不同值"（8.3 入档=按表覆盖，旧写法靠"追加一行"造碰撞
        # 在覆盖语义下会变成"整表被替换、反而没碰撞"，必须改成同批构造——这也更真实：
        # 碰撞本就是同批数据里的双路径矛盾）
        collide: tuple[str, list[str]] | None = None
        for tid, slot in sorted(needed.items()):
            nums = [
                f for f, spec in (slot["fields"] or {}).items()
                if str((spec or {}).get("type", "")).lower() in ("number", "int", "integer", "float")
                and not _is_share_field(f)
            ]
            if nums:
                collide = (tid, nums)
                break
        if collide:
            tid, nums = collide
            c_rows = [_min_row(needed[tid]["fields"]) for _ in range(2)]
            for f in nums:
                c_rows[1][f] = 3  # 同批两行同维度不同值 → 双路径同指标值不同
            r = client.post(f"/diagnoses/{rb_id}/data",
                            json={"payload": json.dumps({"tables": {tid: c_rows}}, ensure_ascii=False)})
            assert r.status_code == 200 and r.json()["accepted"] is True, f"碰撞数据提交失败：{r.text[:200]}"

            r = client.post(f"/diagnoses/{rb_id}/execute")
            assert r.status_code == 409, f"跨源碰撞应触发 409：{r.status_code} {r.text[:200]}"
            detail409 = r.json()["detail"]
            assert detail409.get("conflicts"), f"409 体缺 conflicts：{detail409}"
            cid = detail409["conflicts"][0]["id"]
            d = client.get(f"/diagnoses/{rb_id}").json()
            assert d["status"] == "ready", f"触发被拒不应迁移状态（11.3）：{d['status']}"
            assert d["pending_conflicts_n"] >= 1, "详情未回显未裁决冲突"
            assert d["stage_hint"] == f"{d['pending_conflicts_n']} 处数据冲突待处理", \
                f"stage_hint 未对齐 mock：{d['stage_hint']}"
            r = client.post(f"/diagnoses/{rb_id}/conflicts/{cid}/verdict",
                            json={"verdict": "维持", "note": "冒烟：维持原值"})
            assert r.status_code == 200 and r.json().get("accepted") is True, f"冲突裁决失败：{r.text[:200]}"
            r = client.post(f"/diagnoses/{rb_id}/conflicts/{cid}/verdict", json={"verdict": "维持"})
            assert r.status_code == 200, "冲突裁决幂等失效（重复同值应成功）"
            d = client.get(f"/diagnoses/{rb_id}").json()
            assert d["pending_conflicts_n"] == 0 and d["pending_conflicts"] is None, "裁决后仍有未裁决冲突"
            print(f"10d L2 冲突闭环：{cid} 碰撞 → 409（status 不迁移）→ 维持裁决幂等 → 放行")
        else:
            print("10d 无含非份额数值字段的表，跳过 L2 冲突用例")

        # 10e 修数闭环（11.3 / ARCH 2.2「Owner 选修数 → 走事务 B 再提交 → 天然重跑 L2」）
        # 与 10d 的分工：10d=拒绝变更（裁决维持后放行），10e=手动更改（改数后靠数据本身变一致而放行）
        if collide:
            tid, nums = collide
            c2 = [_min_row(needed[tid]["fields"]) for _ in range(2)]
            for f in nums:
                c2[1][f] = 7  # 换个值 → 新的冲突 id（不与 10d 已裁决那条撞号）
            r = client.post(f"/diagnoses/{rb_id}/data",
                            json={"payload": json.dumps({"tables": {tid: c2}}, ensure_ascii=False)})
            assert r.status_code == 200 and r.json()["accepted"] is True, f"冲突数据提交失败：{r.text[:200]}"
            r = client.post(f"/diagnoses/{rb_id}/execute")
            assert r.status_code == 409, f"新冲突应触发 409：{r.status_code} {r.text[:200]}"
            cid2 = r.json()["detail"]["conflicts"][0]["id"]
            # 修数：重新提交该表（两行同值）→ 8.3 按表覆盖 → 旧冲突行作废 → L2 重算不再检出
            fixed = [_min_row(needed[tid]["fields"]) for _ in range(2)]
            r = client.post(f"/diagnoses/{rb_id}/data",
                            json={"payload": json.dumps({"tables": {tid: fixed}}, ensure_ascii=False)})
            assert r.status_code == 200 and r.json()["accepted"] is True, f"修数提交失败：{r.text[:200]}"
            print(f"10e 修数闭环：{cid2} 冲突已检出 → 重新提交表{tid}（8.3 按表覆盖）→ 修数稿已入档。"
                  "【断言边界】本步只证明到「冲突被检出 + 修数稿被接受」，"
                  "「放行」由步骤 11 的 execute=202 证明——若步骤 11 报 409，"
                  "先查是不是修数没把冲突清干净（S25）")
        else:
            print("10e 无含非份额数值字段的表，跳过修数用例")

        # —— 步骤 12 提前到 11 之前：它是纯代码路径（秒级）且不依赖步骤 11，
        #    这样 --fast 跳过慢步骤 11 时，L2 error 档回归位仍会被跑到 ——
        print("\n== 12. L2 error 档：份额不闭合 → 阻断 execute（11.3，13.3 通用守卫体）==")
        share_tid = next((t for t, slot in sorted(needed.items())
                          if any(_is_share_field(f) for f in (slot["fields"] or {}))), None)
        if not share_tid:
            print("12 激活矩阵无份额类字段表，跳过 error 档用例")
        else:
            # 独立一次性产品承载（error 档会永久阻断该诊断，不污染步骤 11 的回归档案）
            r = client.post("/diagnoses", json={
                "product_name": f"L2error回归专用{uuid.uuid4().hex[:6]}",
                "category_hint": "手机", "known_facts": {"price": 2999},
            })
            assert r.status_code == 201, "error 档前置创建失败"
            er_id = r.json()["diagnosis_id"]
            payload = {t: [_min_row(slot["fields"]) for _ in range(2)] for t, slot in needed.items()}
            for row in payload[share_tid]:
                for f in (needed[share_tid]["fields"] or {}):
                    if _is_share_field(f):
                        row[f] = 0.9  # 同组两行求和 1.8 ≠ 1 → 算术闭合 error
            r = client.post(f"/diagnoses/{er_id}/data",
                            json={"payload": json.dumps({"tables": payload}, ensure_ascii=False)})
            assert r.status_code == 200 and r.json()["accepted"] is True, \
                f"error 档数据提交失败：{r.status_code} {r.text[:200]}"
            assert client.get(f"/diagnoses/{er_id}").json()["status"] == "ready", "error 档前置应为 ready"
            r = client.post(f"/diagnoses/{er_id}/execute")
            assert r.status_code == 409, f"份额不闭合应阻断 execute：{r.status_code} {r.text[:200]}"
            body = r.json()["detail"]
            assert set(body) == {"reason", "expected_states", "current"}, \
                f"error 档 409 体应为 13.3 通用守卫体：{body}"
            assert "算术闭合" in body["reason"] or "口径混算" in body["reason"], \
                f"阻断原因非 L2 error 档：{body['reason']}"
            # S28 回归位：error 档条目必须能从详情读到（前端阻断卡片 + 修数入口的数据源；
            # 409 体保持 13.3 通用守卫体三字段不变，可见性由详情承担）
            errs = client.get(f"/diagnoses/{er_id}").json().get("blocking_errors") or []
            assert len(errs) > 0 and all(e.get("rows") for e in errs), \
                f"error 档详情应暴露 blocking_errors（含行引用）：{errs}"
            print(f"12 error 档阻断通过：{body['reason'][:70]}…（详情 blocking_errors={len(errs)} 条）")
            assert client.delete(f"/diagnoses/{er_id}").status_code == 200, "error 档诊断清理失败"

        print("\n== 11. 事务 C/D/E：execute → 管道执行（真实 LLM）→ done → report → claims 评测 ==")
        import time as _time
        from app import db as _db

        if FAST:  # 快速回归：跳过真实管道（占全量 ~90% 时长），保留全部秒级回归位
            print(f"[跳过步骤 11：{fast_reason}] 需要验管道/装配/QC 请跑全量（不带参数）")
            r = client.delete(f"/diagnoses/{rb_id}")
            assert r.status_code == 200, "回归诊断清理失败"
            print("11f 回归诊断已清理（快速模式）")
            _cleanup_own(client, dx_id, dx2_id)
            print(f"\n全部冒烟断言通过 [OK]（快速模式：{fast_reason}，未跑步骤 11）")
            return

        # 11a- D2 清桶回归（8.3）：重放 = 执行产物作废重写。
        # 预先塞入哨兵中间表，execute 触发后必须被清空（否则旧轮数据撞新轮唯一键 / 残留污染装配）
        _db._run_sync(lambda c: c.execute(
            "INSERT OR REPLACE INTO intermediate_tables(diagnosis_id, method, round, table_name, row_json) "
            "VALUES (?,?,?,?,?)", (rb_id, "__SENTINEL__", 99, "__stale__", "[1]")))
        t0 = _time.time()
        r = client.post(f"/diagnoses/{rb_id}/execute")
        assert r.status_code == 202, (
            f"execute 应 202：{r.status_code} {r.text[:300]}"
            f"（若 409：先查 10e 修数是否真清除了冲突，再查 L2 error 档）")
        stale_n = _db._run_sync(lambda c: c.execute(
            "SELECT COUNT(*) AS n FROM intermediate_tables WHERE diagnosis_id=? AND method='__SENTINEL__'",
            (rb_id,)).fetchone()["n"])
        assert stale_n == 0, "D2 清桶失效：execute 未清空旧中间表（8.3 重放产物作废）"
        pg0 = client.get(f"/diagnoses/{rb_id}").json()["progress"]
        assert pg0["done_n"] == 0 and all(m["phase"] == "pending" for m in pg0["methods"]), \
            f"D2 进度未重置：{pg0}"
        print("11a- D2 清桶：旧中间表已清空 + 进度重置为 pending（8.3）")
        print("11a 已触发执行（202），轮询等待管道完成（真实 LLM，分轮 + 重跑可能十几分钟）…")
        final = None
        policy: dict[str, str] = {}
        for i in range(1000):  # 最长 ~50 分钟（实测两次：26.6min / 35.0min；LLM 方差 >30%，余量必须给足）
            _time.sleep(3)
            d = client.get(f"/diagnoses/{rb_id}").json()
            if d["status"] in ("done", "failed_at(executing)", "failed_at(assembling)"):
                final = d
                break
            if i and i % 20 == 0:  # 心跳：每分钟报一次，防止"慢"被误判成"坏"（S24 教训）
                pgp = d.get("progress") or {}
                print(f"  …已等待 {i * 3 / 60:.0f} 分钟，status={d['status']} "
                      f"进度 {pgp.get('done_n', '-')}/{pgp.get('total_n', '-')}")
            if d["status"] == "executing":
                # 失败停顿（Owner 微调 P2）：failed 方法未处置 → 不推进质检/装配，此处演示人肉断点闭环
                for mth in [m["method"] for m in (d["progress"] or {}).get("methods", [])
                            if m["phase"] == "failed" and not m.get("handled")]:
                    if policy.get(mth) == "retried":
                        r = client.post(f"/diagnoses/{rb_id}/progress/{mth}/skip")
                        assert r.status_code == 200, f"skip 端点异常：{r.status_code} {r.text[:200]}"
                        policy[mth] = "skipped"
                        print(f"  11b- {mth} 重试后仍失败 → skip（报告登记为降级域）")
                    else:
                        r = client.post(f"/diagnoses/{rb_id}/progress/{mth}/retry")
                        assert r.status_code == 200, f"retry 端点异常：{r.status_code} {r.text[:200]}"
                        policy[mth] = "retried"
                        print(f"  11b- {mth} 失败停顿 → retry（携带上轮错误经验重跑）")
        assert final is not None, "执行轮询超时（>30 分钟）"
        if policy:
            print(f"11b 失败处置闭环：{policy}")
        assert final["status"] == "done", f"执行未到 done：{final['status']} {json.dumps(final.get('progress'), ensure_ascii=False)[:400]}"
        pg = final["progress"]
        print(f"11b 管道完成：{pg['done_n']}/{pg['total_n']} 方法 done（用时 {(_time.time() - t0) / 60:.1f} 分钟）")

        r = client.get(f"/diagnoses/{rb_id}/report")
        assert r.status_code == 200, f"报告异常：{r.status_code} {r.text[:200]}"
        rep = r.json()
        active_items = [i for d in rep["domains"] for i in (d.get("items") or [])]
        assert active_items, "报告无 active 域四层结论"
        assert all(i["L1_fact"] and i["L3_quantification"] for i in active_items), "四层结论缺层"
        assert set(rep) == {"domains", "qc", "charts", "conflict_log", "l2_conflict_notes",
                            "downgraded_methods", "limitations"}, f"报告字段漂移（13.2）：{sorted(rep)}"
        assert len(rep["domains"]) == len(rb_body["activation_matrix"]), \
            "域数量应等于激活矩阵（占位域不静默缺席，12.2）"
        print(f"11c 报告：{len(rep['domains'])} 域 · {len(active_items)} 张四层卡 · QC {len(rep['qc'])} 条 "
              f"· 图表 {len(rep['charts'])} 张 · 降级 {len(rep['downgraded_methods'])}")
        if rep["downgraded_methods"]:
            weak = [d for d in rep["domains"] if d["status"] == "weak"]
            assert weak, "降级方法未登记为 weak 域（不静默缺席）"
            print(f"11c- 降级闭环：{len(weak)} 个 weak 域 + downgraded_methods {len(rep['downgraded_methods'])} 条")
        if rep["charts"]:
            c0 = rep["charts"][0]
            assert set(c0) == {"chart_id", "type", "option", "note"}, "图表字段漂移（13.2）"
            print(f"11c- 图表样例：{c0['chart_id']} type={c0['type']}（12.3 纯代码装配）")

        # 11c2 L4 QC 裁决（11.4）：落库幂等 + 报告回显 owner_verdict
        qid = rep["qc"][0]["id"] if rep["qc"] else None
        if qid:
            r = client.post(f"/diagnoses/{rb_id}/qc/{qid}/verdict",
                            json={"verdict": "维持", "note": "冒烟裁决"})
            assert r.status_code == 200 and r.json().get("accepted") is True, \
                f"QC 裁决端点异常：{r.status_code} {r.text[:200]}"
            qc0 = next(i for i in client.get(f"/diagnoses/{rb_id}/report").json()["qc"] if i["id"] == qid)
            assert qc0.get("owner_verdict") == "维持", "报告未回显 owner_verdict（11.4）"
            r = client.post(f"/diagnoses/{rb_id}/qc/{qid}/verdict", json={"verdict": "维持"})
            assert r.status_code == 200, "QC 裁决幂等失效（重复同值应成功）"
            print(f"11c2 QC 裁决 {qid}：落库 + 报告回显 + 幂等通过")
        else:
            print("11c2 QC 为空（质检未产出），跳过裁决验证")

        claims = [
            {"论断": "该产品一年后保值率约 78%", "依据": "二手平台抽样", "来源": "https://example.com/used", "立场": "外部"},
            {"论断": "该品类明年将出现原料涨价潮", "依据": "行业通讯", "来源": "https://example.com/news", "立场": "外部"},
        ]
        r = client.post(f"/diagnoses/{rb_id}/claims", json={"claims": claims})
        assert r.status_code == 200, f"claims 异常：{r.status_code} {r.text[:300]}"
        ev = r.json()
        assert len(ev["evaluation"]) == len(claims) and all(e["对照档"] in ("covered", "conflict", "increment") for e in ev["evaluation"]), "三层对照结构漂移"
        r = client.get(f"/diagnoses/{rb_id}/evaluation")
        assert r.status_code == 200 and r.json()["evaluation"], "evaluation 查询异常"
        print(f"11d 评测：{len(ev['evaluation'])} 条对照（covered/conflict/increment），pending {len(ev['pending_verdicts'])}")

        # 11e 重放装配（D1 回归位：_finalize 的 reassemble 路径曾因 qc_items 未初始化静默崩）
        # 预算：分域 7 次同构调用是真实 LLM 调用，实测约 8 分钟（非秒级）——轮询须给足，否则断言误判
        t1 = _time.time()
        r = client.post(f"/diagnoses/{rb_id}/reassemble")
        assert r.status_code == 200 and r.json().get("accepted") is True, f"reassemble 异常：{r.status_code}"
        for i in range(600):  # 最长 ~20 分钟（实测 8.5-12min；LLM 耗时方差大，余量给足防 S24 重演）
            _time.sleep(2)
            d = client.get(f"/diagnoses/{rb_id}").json()
            if d["status"] != "assembling":
                break
            if i and i % 30 == 0:  # 心跳：慢≠坏，别再把预算不足误判成产品缺陷
                print(f"  …重放装配已等待 {i * 2 / 60:.0f} 分钟（7 域真实调用，实测 8.5-12 分钟）")
        st = client.get(f"/diagnoses/{rb_id}").json()["status"]
        assert st == "done", f"重放装配未回到 done（D1 回归：曾卡死 assembling），实际 {st}"
        print(f"11e 重放装配回到 done（D1 回归通过，用时 {(_time.time() - t1) / 60:.1f} 分钟）")
        if qid:
            qc_after = next(i for i in client.get(f"/diagnoses/{rb_id}/report").json()["qc"]
                            if i["id"] == qid)
            assert qc_after.get("owner_verdict") == "维持", \
                "reassemble 重放后 QC 裁决丢失（11.4 裁决一次性持久化）"
            print(f"11e- QC 裁决 {qid} 在重放装配后仍在（11.4 一次性持久化）")

        r = client.delete(f"/diagnoses/{rb_id}")
        assert r.status_code == 200, "回归诊断清理失败"
        print("11f 回归诊断已清理")

        _cleanup_own(client, dx_id, dx2_id)

        print("\n全部冒烟断言通过 [OK]")


if __name__ == "__main__":
    main()
