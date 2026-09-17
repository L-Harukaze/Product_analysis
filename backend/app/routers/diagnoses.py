"""诊断端点——事务 A（ARCHITECTURE 3.3 / 13.1 / 13.2）。

裸挂 /diagnoses（vite proxy 剥 /api 前缀，交接文档既定）。
守卫语义：状态机 = DB 字段 + 端点守卫（3.3），非法迁移 409 {reason, expected_states, current}。
T4：LLM 调用在写事务外完成；落库 = 单个纯写事务（毫秒级）。
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from .. import db
from ..models import (
    BASE_STATUSES,
    STAGES,
    ActivationEntry,
    CreateDiagnosisRequest,
    CreateDiagnosisResponse,
    DataError,
    DataSubmitRequest,
    DiagnosisDetail,
    DiagnosisSummary,
    FingerprintItem,
    MissingItem,
    SubmissionRecord,
    failed_at,
    parse_failed,
)
from ..services import collection_prompt, invariants, routing
from ..services.data_validation import (
    build_needed_tables,
    format_rejection,
    parse_payload,
    summarize_missing,
    validate_tables,
)
from ..services.execution import (
    _finalize,
    run_method,
    start_execution,
)


def _load_progress_pub(raw: str | None) -> dict[str, Any]:
    return json.loads(raw) if raw else {"methods": [], "done_n": 0, "total_n": 0}

router = APIRouter()

STAGE_HINTS = {
    "created": "事务 A 路由中",
    "routed": "路由完成，等待数据采集",
    "ready": "档案齐备，等待核对与触发执行",
    "executing": "方法池执行中",
    "assembling": "报告装配中",
    "done": "报告已产出",
}


def _stage_hint(status: str, pending_n: int = 0) -> str:
    if parse_failed(status):
        return f"{parse_failed(status)} 阶段失败，等待重放"
    # 11.3：ready 且有未裁决冲突——文案对齐 mock（stateStore.ts stageHint）
    if status == "ready" and pending_n:
        return f"{pending_n} 处数据冲突待处理"
    return STAGE_HINTS.get(status, status)


def _pending_conflicts(raw: str | None) -> list[dict[str, Any]]:
    """conflicts_json → 未裁决 conflict 档（详情 pending_conflicts / 列表计数同源）。"""
    try:
        return invariants.pending_conflicts(json.loads(raw or "[]"))
    except json.JSONDecodeError:
        return []


def _blocking_errors(raw: str | None) -> list[dict[str, Any]]:
    """conflicts_json → error 档条目（详情 blocking_errors：前端阻断卡片 + 修数入口的数据源）。"""
    try:
        return invariants.blocking_errors(json.loads(raw or "[]"))
    except json.JSONDecodeError:
        return []


def _submission_table(s: Any) -> str:
    """payload 快照 → 首个提交表 ID（展示用；解析失败/整体格式问题 → '-'）。"""
    try:
        tables = json.loads(s["payload_snapshot"]).get("tables", {})
        return next(iter(tables), "-") or "-"
    except (json.JSONDecodeError, AttributeError):
        return "-"


def _submission_rows(s: Any) -> int | None:
    """payload 快照 → 提交总行数（仅合格入档展示；打回由 errors 定位）。"""
    if not s["accepted"]:
        return None
    try:
        tables = json.loads(s["payload_snapshot"]).get("tables", {})
        return sum(len(v) for v in tables.values() if isinstance(v, list))
    except (json.JSONDecodeError, AttributeError):
        return None


def _get_state(request: Request) -> dict[str, Any]:
    """执行态（事务 C/D/E 消费）：llm_provider 必须在此注入——缺它 methods 会整体 failed。"""
    return {
        "registry": request.app.state.registry,
        "assets": request.app.state.assets,
        "fp_service": request.app.state.fingerprint_service,
        "llm_provider": request.app.state.llm_provider,
    }


async def _http_409(reason: str, expected: list[str], current: str) -> HTTPException:
    return HTTPException(status_code=409, detail={
        "reason": reason, "expected_states": expected, "current": current,
    })


# ———— 事务 A：创建 + 路由 ————

async def _run_transaction_a(
    *,
    state: dict[str, Any],
    product_row: Any,
    category: str,
    known_price: float | None,
    background: str | None,
    existing_diagnosis_id: str | None = None,
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], str, str]:
    """事务 A 主体（2.2）。返回 (status, fingerprint, matrix, missing, prompt, diagnosis_id)。

    已存在 diagnosis（reroute）→ 复用该 id 并重算；否则新建。
    """
    registry = state["registry"]
    assets = state["assets"]
    fp_service = state["fp_service"]
    product_id = product_row["id"]

    # 读库：固化指纹（7.2 幂等复用）
    frozen = json.loads(product_row["fingerprint_json"]) if product_row["fingerprint_json"] else None

    # 读库：S3 先例检索（同品类跨产品历史仲裁）
    def _read_precedents(conn):
        return [
            dict(r) for r in conn.execute(
                "SELECT ar.dimension, ar.verdict, ar.reason, p.name AS product_name, c.name AS category "
                "FROM arbitration_records ar "
                "JOIN products p ON p.id = ar.product_id "
                "LEFT JOIN categories c ON c.id = p.category_id "
                "WHERE p.category_id = ? AND p.id != ? "
                "ORDER BY ar.created_at DESC LIMIT 5",
                (product_row["category_id"], product_id),
            )
        ]
    precedents = await db.run(_read_precedents)

    # LLM 阶段（写事务外，T4）：指纹三级漏斗
    fingerprint, pending_arbitrations = await fp_service.compute(
        product_name=product_row["name"], category=category,
        known_price=known_price, frozen=frozen,
        precedent_rows=precedents, diagnosis_id=existing_diagnosis_id,
    )

    # 路由扫描（纯查表，无 LLM）：指纹一定，激活矩阵必定（7.2）
    matrix = routing.scan(fingerprint, assets["route_table"])

    # 数据需求汇总（各方法 input.schema 并集）× 已有档案 = 缺数清单（2.2；构建逻辑与事务 B 共享）
    needed = build_needed_tables(registry, matrix)

    def _read_archive_counts(conn):
        return {
            r["table_id"]: r["n"]
            for r in conn.execute(
                "SELECT table_id, COUNT(*) AS n FROM archive_records WHERE product_id=? GROUP BY table_id",
                (product_id,),
            )
        }
    counts = await db.run(_read_archive_counts)
    missing_data, missing_only = summarize_missing(needed, counts)

    # 采集 prompt（6.1：纯代码模板填充，零 LLM；仅针对缺失部分）
    diagnosis_id = existing_diagnosis_id or f"dx_{uuid.uuid4().hex[:12]}"
    prompt = collection_prompt.generate(
        product_name=product_row["name"], diagnosis_id=diagnosis_id,
        category=category, missing_tables=missing_only,
        time_window=assets["route_table"].get("default_time_window", "近 24 个月"),
        background=background,
    )

    # 状态迁移：缺数为空 → 直接 ready 跳过断点 1（2.2）
    status = "ready" if not missing_only else "routed"

    def _write(conn) -> None:
        # 指纹固化条件（7.2 + 3.4）：仲裁全部成功（无 pending）才冻结到 product
        if frozen is None and not pending_arbitrations:
            conn.execute(
                "UPDATE products SET fingerprint_json=?, fingerprint_source='computed' WHERE id=?",
                (json.dumps(fingerprint, ensure_ascii=False), product_id),
            )
        if frozen is None:
            for item in fingerprint:
                if item["source"] == "L3 仲裁" and item.get("detail"):
                    conn.execute(
                        "INSERT INTO arbitration_records(product_id, dimension, verdict, reason, confidence, model) "
                        "VALUES (?,?,?,?,?,?)",
                        (product_id, item["dimension"], item["value"], item["detail"]["reason"],
                         item["detail"]["confidence"], "arbiter"),
                    )

        if existing_diagnosis_id:
            conn.execute(
                "UPDATE diagnoses SET status=?, activation_matrix_json=?, missing_data_json=?, "
                "pending_arbitrations_json=?, collection_prompt=?, updated_at=datetime('now') WHERE id=?",
                (status, json.dumps(matrix, ensure_ascii=False), json.dumps(missing_data, ensure_ascii=False),
                 json.dumps(pending_arbitrations, ensure_ascii=False), prompt, diagnosis_id),
            )
        else:
            conn.execute(
                "INSERT INTO diagnoses(id, product_id, status, activation_matrix_json, missing_data_json, "
                "pending_arbitrations_json, collection_prompt, background_note) VALUES (?,?,?,?,?,?,?,?)",
                (diagnosis_id, product_id, status, json.dumps(matrix, ensure_ascii=False),
                 json.dumps(missing_data, ensure_ascii=False),
                 json.dumps(pending_arbitrations, ensure_ascii=False), prompt, background),
            )
    await db.run(_write)
    return status, fingerprint, matrix, missing_data, prompt, diagnosis_id


@router.post("/diagnoses", response_model=CreateDiagnosisResponse, status_code=201)
async def create_diagnosis(req: CreateDiagnosisRequest, request: Request):
    state = _get_state(request)
    name = req.product_name.strip()
    if not name:
        raise HTTPException(status_code=422, detail={"errors": ["product_name 不能为空"]})

    # category 确定：hint 匹配预置品类；未匹配 → 未分类（L1 无映射，全维度走 L3）
    category = req.category_hint.strip() if req.category_hint else None
    known = category in state["assets"]["category_map"] or category in state["assets"]["baselines"]
    if not category or not known:
        category = _match_category(state, category) or "未分类"

    # product 匹配/新建（2.2：同产品复用固化指纹）
    def _upsert_product(conn):
        row = conn.execute("SELECT * FROM products WHERE name=?", (name,)).fetchone()
        if row is None:
            cat_id = conn.execute("SELECT id FROM categories WHERE name=?", (category,)).fetchone()
            pid = f"p_{uuid.uuid4().hex[:12]}"
            conn.execute(
                "INSERT INTO products(id, name, category_id) VALUES (?,?,?)",
                (pid, name, cat_id["id"] if cat_id else None),
            )
            row = conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
        return row
    product = await db.run(_upsert_product)
    if product["category_id"]:
        cat_row = await db.run(lambda c: c.execute(
            "SELECT name FROM categories WHERE id=?", (product["category_id"],)).fetchone())
        if cat_row:
            category = cat_row["name"]

    status, fingerprint, matrix, missing, prompt, dx_id = await _run_transaction_a(
        state=state, product_row=product, category=category,
        known_price=req.known_facts.price if req.known_facts else None,
        background=req.background,
    )
    return CreateDiagnosisResponse(
        diagnosis_id=dx_id, status=status,
        fingerprint=[FingerprintItem(**f) for f in fingerprint],
        activation_matrix=[ActivationEntry(**e) for e in matrix],
        missing_data=[MissingItem(**m) for m in missing],
        collection_prompt=prompt,
    )


def _match_category(state: dict[str, Any], hint: str | None) -> str | None:
    if not hint:
        return None
    if hint in state["assets"]["baselines"]:
        return hint
    for name in state["assets"]["category_map"]:
        if hint in name or name in hint:
            return name
    return None


# ———— reroute：重放事务 A（守卫 failed_at(routing)，3.3） ————

@router.post("/diagnoses/{diagnosis_id}/reroute", response_model=CreateDiagnosisResponse, status_code=201)
async def reroute(diagnosis_id: str, request: Request):
    state = _get_state(request)

    def _read(conn):
        d = conn.execute("SELECT * FROM diagnoses WHERE id=?", (diagnosis_id,)).fetchone()
        if d is None:
            return None, None
        p = conn.execute("SELECT * FROM products WHERE id=?", (d["product_id"],)).fetchone()
        return d, p
    dx, product = await db.run(_read)
    if dx is None:
        raise HTTPException(status_code=404, detail={"reason": "diagnosis 不存在"})
    if dx["status"] != failed_at("routing"):
        raise await _http_409(
            f"reroute 仅允许 failed_at(routing) 状态重放（当前 {dx['status']}）",
            [failed_at("routing")], dx["status"],
        )
    category = "未分类"
    if product["category_id"]:
        cat_row = await db.run(lambda c: c.execute(
            "SELECT name FROM categories WHERE id=?", (product["category_id"],)).fetchone())
        if cat_row:
            category = cat_row["name"]

    status, fingerprint, matrix, missing, prompt, _ = await _run_transaction_a(
        state=state, product_row=product, category=category, known_price=None,
        background=None, existing_diagnosis_id=diagnosis_id,
    )
    return CreateDiagnosisResponse(
        diagnosis_id=diagnosis_id, status=status,
        fingerprint=[FingerprintItem(**f) for f in fingerprint],
        activation_matrix=[ActivationEntry(**e) for e in matrix],
        missing_data=[MissingItem(**m) for m in missing],
        collection_prompt=prompt,
    )


# ———— 采集 prompt（6.1：最新版；打回后自动携带拒绝原因。守卫对齐 mock：routed 才可取） ————

@router.get("/diagnoses/{diagnosis_id}/collection-prompt")
async def get_collection_prompt(diagnosis_id: str, request: Request):
    def _read(conn):
        return conn.execute(
            "SELECT status, collection_prompt FROM diagnoses WHERE id=?", (diagnosis_id,)
        ).fetchone()
    row = await db.run(_read)
    if row is None:
        raise HTTPException(status_code=404, detail={"reason": "diagnosis 不存在"})
    if row["status"] != "routed":
        raise await _http_409(
            f"采集 prompt 仅 routed 状态可取（当前 {row['status']}）", ["routed"], row["status"],
        )
    if not row["collection_prompt"]:
        raise HTTPException(status_code=404, detail={"reason": "采集 prompt 未生成"})
    return {"prompt": row["collection_prompt"]}


# ———— 删除（Owner 契约增量 2026-09-16：列表管理） ————

@router.delete("/diagnoses/{diagnosis_id}")
async def delete_diagnosis(diagnosis_id: str, request: Request):
    """删除诊断（列表管理）。

    - 仅删诊断级数据（diagnoses + 子表 CASCADE：提交记录/中间表/claims）；
      products / archive_records / arbitration_records 保留——产品档案与固化指纹是跨诊断复用资产（7.2）
    - llm_call_logs 无外键，调用留痕保留（5.3 审计）
    - 守卫（3.3 纪律）：executing/assembling 不可删——后台任务运行中，删除即资源泄漏，显式 409 不静默
    """
    def _read(conn):
        return conn.execute(
            "SELECT status FROM diagnoses WHERE id=?", (diagnosis_id,)
        ).fetchone()
    row = await db.run(_read)
    if row is None:
        raise HTTPException(status_code=404, detail={"reason": "diagnosis 不存在"})
    if row["status"] in ("executing", "assembling"):
        deletable = [
            s for s in (*BASE_STATUSES, *(f"failed_at({s})" for s in STAGES))
            if s not in ("executing", "assembling")
        ]
        raise await _http_409(
            f"执行中/装配中的诊断不可删除（后台任务运行中）", deletable, row["status"],
        )
    await db.run(lambda c: c.execute("DELETE FROM diagnoses WHERE id=?", (diagnosis_id,)))
    return {"accepted": True}


# ———— 事务 B：数据提交 + L1 校验循环（ARCHITECTURE 3.3 / 11.2 / 13.2） ————

@router.post("/diagnoses/{diagnosis_id}/data")
async def submit_data(diagnosis_id: str, req: DataSubmitRequest, request: Request):
    """事务 B（11.2 L1 校验循环）：打回 → errors + prompt 注入拒绝原因；合格 → 入档 + 清单刷新。

    入档语义（8.3 按表覆盖）：提交体里出现的表 = 该表最新快照，先作废该产品该表的旧行再写入，
    以此兑现 11.3 的"修数走事务 B 再提交"路径；历史提交快照仍全量留在 data_submissions。

    T4/T5：校验是纯代码毫秒级，单写事务落库；payload 原文快照进 data_submissions（8.3）。
    打回是 200 + {accepted: false}（契约 13.2）——"提交了但不合格"不是 HTTP 错误。
    """
    state = _get_state(request)

    def _read(conn):
        d = conn.execute(
            "SELECT d.status, d.product_id, d.background_note, p.name AS product_name "
            "FROM diagnoses d JOIN products p ON p.id=d.product_id WHERE d.id=?",
            (diagnosis_id,),
        ).fetchone()
        return d
    dx = await db.run(_read)
    if dx is None:
        raise HTTPException(status_code=404, detail={"reason": "diagnosis 不存在"})
    # 11.3：ready 状态档案更新路径必须通（冲突裁决后 Owner 可选修数再执行）
    if dx["status"] not in ("routed", "ready"):
        raise await _http_409(
            f"数据提交仅 routed / ready 状态可用（当前 {dx['status']}）", ["routed", "ready"], dx["status"],
        )

    # L1 解析 + 校验（11.2：schema 驱动，零方法知识）
    try:
        tables = parse_payload(req.payload)
    except ValueError as e:
        tables, errors = {}, [{"table": "-", "row_index": 0, "field": "payload", "error": str(e)}]
    else:
        def _matrix(conn):
            row = conn.execute(
                "SELECT activation_matrix_json FROM diagnoses WHERE id=?", (diagnosis_id,)
            ).fetchone()
            return json.loads(row["activation_matrix_json"]) if row["activation_matrix_json"] else []
        needed = build_needed_tables(state["registry"], await db.run(_matrix))
        errors = validate_tables(needed, tables)

    # ———— 打回分支：留痕 + 采集 prompt 注入拒绝原因（6.1 打回条款） ————
    if errors:
        history, items = format_rejection(errors)

        def _write_reject(conn) -> None:
            seq = conn.execute(
                "SELECT COALESCE(MAX(seq_n), 0) + 1 AS n FROM data_submissions WHERE diagnosis_id=?",
                (diagnosis_id,),
            ).fetchone()["n"]
            conn.execute(
                "INSERT INTO data_submissions(diagnosis_id, seq_n, payload_snapshot, accepted, reject_errors_json) "
                "VALUES (?,?,?,0,?)",
                (diagnosis_id, seq, req.payload, json.dumps(errors, ensure_ascii=False)),
            )
            prompt, missing_data, _ = _reload_prompt_sync(
                conn, state, dx=dx, diagnosis_id=diagnosis_id,
                rejection_history=history, rejected_items=items,
            )
            conn.execute(
                "UPDATE diagnoses SET collection_prompt=?, missing_data_json=?, updated_at=datetime('now') WHERE id=?",
                (prompt, json.dumps(missing_data, ensure_ascii=False), diagnosis_id),
            )
        await db.run(_write_reject)
        return {"accepted": False, "errors": [DataError(**e) for e in errors]}

    # ———— 合格分支：入档（8.3 JSON 行）+ 留痕 + 清单刷新 + 缺数清空迁移 ready（2.2 断点 1 关闭） ————
    def _write_accept(conn) -> None:
        # 8.3 按表覆盖（upsert by table）：提交体里出现的表 = 该表最新快照，先作废旧行再写入。
        # 兑现 11.3 / ARCH 2.2 承诺的"修数走事务 B 再提交"路径——纯 append 会让已入档的
        # 错误行永远无法清除（一旦产生跨源碰撞，重新提交只会越堆越冲突，S25）。
        # 未提交的表不受影响（表=最小入档单元，与缺数清单按表判定同构）；
        # 历史留痕由 data_submissions 全量保留（2.2"历史全留痕"），覆盖不丢审计。
        for tid in tables:
            conn.execute(
                "DELETE FROM archive_records WHERE product_id=? AND table_id=?",
                (dx["product_id"], tid),
            )
        for tid, rows in tables.items():
            for r in rows:
                conn.execute(
                    "INSERT INTO archive_records(product_id, table_id, row_json, source_url, confidence, caliber) "
                    "VALUES (?,?,?,?,?,?)",
                    (dx["product_id"], tid, json.dumps(r, ensure_ascii=False),
                     str(r.get("source_url", "")),
                     str(r.get("confidence", "") or "第三方"),
                     str(r.get("caliber", ""))),
                )
        seq = conn.execute(
            "SELECT COALESCE(MAX(seq_n), 0) + 1 AS n FROM data_submissions WHERE diagnosis_id=?",
            (diagnosis_id,),
        ).fetchone()["n"]
        conn.execute(
            "INSERT INTO data_submissions(diagnosis_id, seq_n, payload_snapshot, accepted) VALUES (?,?,?,1)",
            (diagnosis_id, seq, req.payload),
        )
        prompt, missing_data, missing_only = _reload_prompt_sync(
            conn, state, dx=dx, diagnosis_id=diagnosis_id,
        )
        # ready 入档后维持 ready（11.3 修数路径：重算缺数清单，状态不回退 routed）
        new_status = "ready" if (not missing_only or dx["status"] == "ready") else "routed"
        conn.execute(
            "UPDATE diagnoses SET status=?, missing_data_json=?, collection_prompt=?, updated_at=datetime('now') "
            "WHERE id=?",
            (new_status, json.dumps(missing_data, ensure_ascii=False), prompt, diagnosis_id),
        )
    await db.run(_write_accept)

    d = await db.run(lambda c: c.execute(
        "SELECT missing_data_json FROM diagnoses WHERE id=?", (diagnosis_id,)).fetchone())
    missing = json.loads(d["missing_data_json"]) if d["missing_data_json"] else []
    return {
        "accepted": True,
        "archive_summary": [
            {"table": m["table"], "name": m["name"], "rows": m["rows"]}
            for m in missing if m["status"] == "archived"
        ],
        "missing_data": [MissingItem(**m) for m in missing],
    }


def _category_of(conn: Any, product_id: str) -> str:
    row = conn.execute(
        "SELECT c.name AS name FROM products p LEFT JOIN categories c ON c.id=p.category_id WHERE p.id=?",
        (product_id,),
    ).fetchone()
    return (row["name"] if row and row["name"] else "未分类")


def _reload_prompt_sync(
    conn: Any, state: dict[str, Any], *, dx: Any, diagnosis_id: str,
    rejection_history: str | None = None, rejected_items: str | None = None,
) -> tuple[str, list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """同步版（已在写事务内）：重算缺数 + 重生成 prompt（可携带打回条款）。"""
    matrix = json.loads(conn.execute(
        "SELECT activation_matrix_json FROM diagnoses WHERE id=?", (diagnosis_id,)
    ).fetchone()["activation_matrix_json"] or "[]")
    needed = build_needed_tables(state["registry"], matrix)
    counts = {
        r["table_id"]: r["n"]
        for r in conn.execute(
            "SELECT table_id, COUNT(*) AS n FROM archive_records WHERE product_id=? GROUP BY table_id",
            (dx["product_id"],),
        )
    }
    missing_data, missing_only = summarize_missing(needed, counts)
    prompt = collection_prompt.generate(
        product_name=dx["product_name"], diagnosis_id=diagnosis_id,
        category=_category_of(conn, dx["product_id"]),
        missing_tables=missing_only,
        time_window=state["assets"]["route_table"].get("default_time_window", "近 24 个月"),
        background=dx["background_note"],
        rejection_history=rejection_history,
        rejected_items=rejected_items,
    )
    return prompt, missing_data, missing_only


# ———— 事务 C：触发执行 + 方法池进度（ARCHITECTURE 10 章 / 3.3） ————

@router.post("/diagnoses/{diagnosis_id}/execute", status_code=202)
async def execute_diagnosis(diagnosis_id: str, request: Request):
    """事务 C 触发（10.1）：守卫 → L2 不变式检查（三档）→ 清桶+后台执行。

    L2 处置档（11.3）：
    - error（算术闭合/口径混算）→ 409 通用守卫体，阻断（修数走事务 B）
    - conflict（跨源碰撞）未裁决 → 409 {reason, conflicts}，status **不迁移**（触发被拒≠失败）
    - warn（时窗错位/值越界）→ 放行，落库供装配生成 l2_conflict_notes
    """
    state = _get_state(request)

    def _read(conn):
        d = conn.execute(
            "SELECT status, product_id, activation_matrix_json, conflicts_json FROM diagnoses WHERE id=?",
            (diagnosis_id,),
        ).fetchone()
        if d is None:
            return None, {}
        rows: dict[str, list[dict[str, Any]]] = {}
        for r in conn.execute(
            "SELECT table_id, row_json FROM archive_records WHERE product_id=? ORDER BY table_id, id",
            (d["product_id"],),
        ):
            rows.setdefault(r["table_id"], []).append(json.loads(r["row_json"]))
        return d, rows
    row, archive = await db.run(_read)
    if row is None:
        raise HTTPException(status_code=404, detail={"reason": "diagnosis 不存在"})
    if row["status"] not in ("ready", "failed_at(executing)"):
        raise await _http_409(
            f"触发执行仅 ready（或 failed_at(executing) 重放）可用（当前 {row['status']}）",
            ["ready", "failed_at(executing)"], row["status"],
        )

    # L2 不变式检查（11.3）：只查本次激活方法所需的表（needed 并集），范围可控
    matrix = json.loads(row["activation_matrix_json"] or "[]")
    needed = build_needed_tables(state["registry"], matrix)
    findings = invariants.check({t: r for t, r in archive.items() if t in needed})
    stored = json.loads(row["conflicts_json"] or "[]")
    merged = invariants.merge_with_verdicts(stored, findings)

    async def _persist_conflicts() -> None:
        await db.run(lambda c: c.execute(
            "UPDATE diagnoses SET conflicts_json=?, updated_at=datetime('now') WHERE id=?",
            (json.dumps(merged, ensure_ascii=False), diagnosis_id),
        ))

    errors = [f for f in merged if f["tier"] == invariants.TIER_ERROR]
    if errors:
        await _persist_conflicts()
        raise await _http_409(
            "L2 不变式检查阻断（error 档）："
            + "；".join(f"{e['invariant']}：{e['detail']}" for e in errors[:3]),
            ["ready"], row["status"],
        )
    pending = invariants.pending_conflicts(merged)
    if pending:
        await _persist_conflicts()
        raise HTTPException(status_code=409, detail={
            "reason": f"存在 {len(pending)} 处未裁决的数据冲突，需 Owner 裁决后重试（11.3）",
            "conflicts": pending,
        })

    await _persist_conflicts()
    await start_execution(state, diagnosis_id)
    return {"task_started": True}


@router.post("/diagnoses/{diagnosis_id}/conflicts/{cid}/verdict")
async def conflict_verdict(diagnosis_id: str, cid: str, request: Request):
    """L2 conflict 的 Owner 裁决（11.3）：维持→落库幂等生效，修数走事务 B。

    守卫（13.1）：ready 且存在该未裁决冲突。裁决一次性持久化——重放/重跑不再询问。
    """
    body = await request.json()
    verdict = str(body.get("verdict") or "维持")
    note = body.get("note")
    row = await db.run(lambda c: c.execute(
        "SELECT status, conflicts_json FROM diagnoses WHERE id=?", (diagnosis_id,)).fetchone())
    if row is None:
        raise HTTPException(status_code=404, detail={"reason": "diagnosis 不存在"})
    if row["status"] != "ready":
        raise await _http_409(f"冲突裁决仅 ready 状态可用（当前 {row['status']}）", ["ready"], row["status"])
    stored = json.loads(row["conflicts_json"] or "[]")
    target = next((s for s in stored if str(s.get("id")) == cid), None)
    if target is None:
        raise HTTPException(status_code=404, detail={"reason": f"冲突 {cid} 不存在"})

    def _write(conn) -> None:
        fresh = json.loads(conn.execute(
            "SELECT conflicts_json FROM diagnoses WHERE id=?", (diagnosis_id,)
        ).fetchone()["conflicts_json"] or "[]")
        for s in fresh:
            if str(s.get("id")) != cid:
                continue
            s["handled"] = {
                "verdict": verdict, "note": note,
                "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        conn.execute(
            "UPDATE diagnoses SET conflicts_json=?, updated_at=datetime('now') WHERE id=?",
            (json.dumps(fresh, ensure_ascii=False), diagnosis_id),
        )
    await db.run(_write)
    return {"accepted": True}


@router.post("/diagnoses/{diagnosis_id}/progress/{method}/retry")
async def retry_method_endpoint(diagnosis_id: str, method: str, request: Request):
    """重试失败方法：注入上轮错误经验重跑（round 递增），完成后自动续 finalize。"""
    state = _get_state(request)

    def _read(conn):
        dx = conn.execute("SELECT status FROM diagnoses WHERE id=?", (diagnosis_id,)).fetchone()
        raw = conn.execute(
            "SELECT progress_json FROM diagnoses WHERE id=?", (diagnosis_id,)
        ).fetchone()["progress_json"]
        return dx, raw
    dx, raw = await db.run(_read)
    if dx is None:
        raise HTTPException(status_code=404, detail={"reason": "diagnosis 不存在"})
    if dx["status"] != "executing":
        raise await _http_409("重试仅执行中可用", ["executing"], dx["status"])
    progress = _load_progress_pub(raw)
    entry = next((m for m in progress["methods"] if m["method"] == method), None)
    if entry is None or entry["phase"] != "failed":
        raise await _http_409("仅失败方法可重试", ["failed"], str(entry["phase"]) if entry else "unknown")
    last_error = (entry.get("error") or {}).get("raw")

    def _mark(conn) -> None:
        entry["handled"] = "retried"
        entry["phase"] = "running(1)"  # 重跑整方法（分轮包从 R1 起，中间表覆盖写）
        conn.execute(
            "UPDATE diagnoses SET progress_json=?, updated_at=datetime('now') WHERE id=?",
            (json.dumps(progress, ensure_ascii=False), diagnosis_id),
        )
    await db.run(_mark)

    async def _task() -> None:
        await run_method(state, diagnosis_id, method, last_error)
        await _finalize(state, diagnosis_id)
    asyncio.create_task(_task())
    return {"accepted": True}


@router.post("/diagnoses/{diagnosis_id}/progress/{method}/skip")
async def skip_method_endpoint(diagnosis_id: str, method: str, request: Request):
    """跳过失败方法：登记降级（报告如实呈现），其余收尾后自动进入质检/装配。"""
    state = _get_state(request)

    def _read(conn):
        dx = conn.execute("SELECT status FROM diagnoses WHERE id=?", (diagnosis_id,)).fetchone()
        raw = conn.execute("SELECT progress_json FROM diagnoses WHERE id=?", (diagnosis_id,)).fetchone()["progress_json"]
        return dx, raw
    dx, raw = await db.run(_read)
    if dx is None:
        raise HTTPException(status_code=404, detail={"reason": "diagnosis 不存在"})
    if dx["status"] != "executing":
        raise await _http_409("跳过仅执行中可用", ["executing"], dx["status"])
    progress = _load_progress_pub(raw)
    entry = next((m for m in progress["methods"] if m["method"] == method), None)
    if entry is None or entry["phase"] != "failed":
        raise await _http_409("仅失败方法可跳过", ["failed"], str(entry["phase"]) if entry else "unknown")

    def _mark(conn) -> None:
        entry["handled"] = "skipped"
        conn.execute(
            "UPDATE diagnoses SET progress_json=?, updated_at=datetime('now') WHERE id=?",
            (json.dumps(progress, ensure_ascii=False), diagnosis_id),
        )
    await db.run(_mark)
    asyncio.create_task(_finalize(state, diagnosis_id))
    return {"accepted": True}


# ———— 事务 D：装配重放 + 报告（ARCHITECTURE 12 章 / 13.2 聚合式） ————

@router.post("/diagnoses/{diagnosis_id}/reassemble")
async def reassemble_diagnosis(diagnosis_id: str, request: Request):
    state = _get_state(request)
    row = await db.run(lambda c: c.execute(
        "SELECT status FROM diagnoses WHERE id=?", (diagnosis_id,)).fetchone())
    if row is None:
        raise HTTPException(status_code=404, detail={"reason": "diagnosis 不存在"})
    if row["status"] not in ("failed_at(assembling)", "done"):
        raise await _http_409(
            f"重放装配仅 failed_at(assembling)/done 可用（当前 {row['status']}）",
            ["failed_at(assembling)", "done"], row["status"],
        )
    await db.run(lambda c: c.execute(
        "UPDATE diagnoses SET status='assembling', updated_at=datetime('now') WHERE id=?", (diagnosis_id,)))
    asyncio.create_task(_finalize(state, diagnosis_id))
    return {"accepted": True}


@router.get("/diagnoses/{diagnosis_id}/report")
async def get_report(diagnosis_id: str, request: Request):
    row = await db.run(lambda c: c.execute(
        "SELECT status, report_json, qc_verdicts_json FROM diagnoses WHERE id=?", (diagnosis_id,)
    ).fetchone())
    if row is None:
        raise HTTPException(status_code=404, detail={"reason": "diagnosis 不存在"})
    if row["status"] != "done":
        raise await _http_409("报告仅 done 状态可取", ["done"], row["status"])
    if not row["report_json"]:
        raise HTTPException(status_code=404, detail={"reason": "报告未生成"})
    report = json.loads(row["report_json"])
    # 11.4 兜底：裁决在报告装配后才落库时（旧报告/新增裁决），回显 owner_verdict
    verdicts = json.loads(row["qc_verdicts_json"] or "{}")
    for it in report.get("qc", []):
        if it.get("owner_verdict"):
            continue
        v = verdicts.get(str(it.get("id")))
        if v:
            it["owner_verdict"] = v.get("verdict")
    return report


# ———— L4：QC 条目 Owner 裁决（ARCHITECTURE 11.4 / 13.1） ————

_QC_VERDICTS = ("维持", "修正")


@router.post("/diagnoses/{diagnosis_id}/qc/{qid}/verdict")
async def qc_verdict_endpoint(diagnosis_id: str, qid: str, request: Request):
    """报告页 QC 徽标裁决（11.4）：维持=质疑不成立；修正=认可质疑（数据修正走 2.4 人肉回路）。

    - 守卫（13.1）：status=done 且该 QC 条目存在
    - 幂等：重复裁决同值返回成功；reassemble 重放读已有 verdict 不再询问（裁决一次性持久化）
    """
    body = await request.json()
    verdict = str(body.get("verdict") or "维持")
    if verdict not in _QC_VERDICTS:
        raise HTTPException(status_code=422, detail={"errors": [f"verdict 须为 {_QC_VERDICTS} 之一"]})
    note = body.get("note")

    row = await db.run(lambda c: c.execute(
        "SELECT status, qc_json FROM diagnoses WHERE id=?", (diagnosis_id,)).fetchone())
    if row is None:
        raise HTTPException(status_code=404, detail={"reason": "diagnosis 不存在"})
    if row["status"] != "done":
        raise await _http_409(f"QC 裁决仅 done 状态可用（当前 {row['status']}）", ["done"], row["status"])
    items = json.loads(row["qc_json"] or "[]")
    if not any(str(it.get("id")) == qid for it in items):
        raise HTTPException(status_code=404, detail={"reason": f"QC 条目 {qid} 不存在"})

    def _write(conn) -> None:
        raw = conn.execute(
            "SELECT qc_verdicts_json FROM diagnoses WHERE id=?", (diagnosis_id,)
        ).fetchone()["qc_verdicts_json"]
        verdicts = json.loads(raw or "{}")
        verdicts[qid] = {
            "verdict": verdict, "note": note,
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        conn.execute(
            "UPDATE diagnoses SET qc_verdicts_json=?, updated_at=datetime('now') WHERE id=?",
            (json.dumps(verdicts, ensure_ascii=False), diagnosis_id),
        )
    await db.run(_write)
    return {"accepted": True}


# ———— 事务 E：外部论断三层对照（covered/conflict/increment） ————

_CLAIM_PROMPT = (
    "你是评测对照员。把每条外部论断与我方报告结论对照，分三档："
    "covered（我方已覆盖并有对应结论）、conflict（与我方结论方向相反，需给出双方立场）、"
    "increment（我方未覆盖的增量信息）。"
    '严格输出 JSON：{"items": [{"index": 0, "tier": "covered|conflict|increment", '
    '"detail": "对照理由", "mine": "我方相关结论原文摘要（conflict 档必填）"}]}'
)


@router.post("/diagnoses/{diagnosis_id}/claims")
async def submit_claims(diagnosis_id: str, request: Request):
    state = _get_state(request)
    body = await request.json()
    claims = body.get("claims") or []
    if not isinstance(claims, list) or not claims:
        raise HTTPException(status_code=422, detail={"reason": "claims 不能为空"})
    row = await db.run(lambda c: c.execute(
        "SELECT status, report_json FROM diagnoses WHERE id=?", (diagnosis_id,)).fetchone())
    if row is None:
        raise HTTPException(status_code=404, detail={"reason": "diagnosis 不存在"})
    if row["status"] != "done":
        raise await _http_409("论断对照仅 done 状态可用", ["done"], row["status"])

    report = json.loads(row["report_json"] or "{}")
    mine = [
        {"domain": d["title"], "quant": (d.get("items") or [{}])[0].get("L3_quantification", ""),
         "action": (d.get("items") or [{}])[0].get("L4_prescription", "")}
        for d in report.get("domains", []) if d.get("status") == "active"
    ]

    def _validate(data: Any) -> None:
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list) or len(items) != len(claims):
            raise ValueError("items 数量与论断数不一致")

    data = await state["llm_provider"].call_json(
        "qc",
        [{"role": "system", "content": _CLAIM_PROMPT},
         {"role": "user", "content": json.dumps(
             {"我方结论": mine, "外部论断": claims}, ensure_ascii=False)}],
        diagnosis_id=diagnosis_id, method="claims_eval", round_no=1,
        timeout_s=60, prompt_template_version="claims-eval-v1", validate=_validate,
    )

    def _persist(conn) -> list[dict[str, Any]]:
        pending: list[dict[str, Any]] = []
        for i, claim in enumerate(claims):
            cur = conn.execute(
                "INSERT INTO claims(diagnosis_id, claim_json) VALUES (?,?)",
                (diagnosis_id, json.dumps(claim, ensure_ascii=False)),
            )
            cid = cur.lastrowid
            it = data["items"][i]
            tier = it.get("tier", "covered")
            result = {"detail": it.get("detail", "")}
            if tier == "conflict":
                result.update({"mine": str(it.get("mine", "")), "theirs": str(claim.get("论断", ""))})
            conn.execute(
                "INSERT INTO claim_evaluations(claim_id, verdict_tier, result_json) VALUES (?,?,?)",
                (cid, tier, json.dumps(result, ensure_ascii=False)),
            )
            if tier == "conflict":
                pending.append({
                    "cid": str(cid), "mine": result["mine"],
                    "theirs": result["theirs"], "detail": result["detail"],
                })
        return pending
    pending = await db.run(_persist)
    return {"evaluation": [
        {"claim_id": f"CLM-{i + 1:02d}", "对照档": it.get("tier", "covered"), "detail": it.get("detail", "")}
        for i, it in enumerate(data["items"])
    ], "pending_verdicts": pending}


@router.post("/diagnoses/{diagnosis_id}/claims/{claim_id}/verdict")
async def claim_verdict(diagnosis_id: str, claim_id: str, request: Request):
    body = await request.json()
    verdict = str(body.get("verdict") or "我方正确")
    row = await db.run(lambda c: c.execute(
        "SELECT c.id FROM claims c JOIN diagnoses d ON d.id=c.diagnosis_id "
        "WHERE d.id=? AND c.id=?", (diagnosis_id, int(claim_id) if claim_id.isdigit() else -1),
    ).fetchone())
    if row is None:
        raise HTTPException(status_code=404, detail={"reason": "claim 不存在"})
    await db.run(lambda c: c.execute(
        "UPDATE claim_evaluations SET owner_verdict=? WHERE claim_id=?", (verdict, int(claim_id))))
    return {"accepted": True}


@router.get("/diagnoses/{diagnosis_id}/evaluation")
async def get_evaluation(diagnosis_id: str, request: Request):
    def _read(conn):
        rows = conn.execute(
            "SELECT ce.claim_id, ce.verdict_tier, ce.result_json, ce.owner_verdict, ce.created_at "
            "FROM claim_evaluations ce JOIN claims c ON c.id=ce.claim_id "
            "WHERE c.diagnosis_id=? ORDER BY ce.id", (diagnosis_id,),
        ).fetchall()
        return rows
    rows = await db.run(_read)
    evaluation = [
        {"claim_id": f"CLM-{r['claim_id']:02d}", "对照档": r["verdict_tier"],
         "detail": json.loads(r["result_json"]).get("detail", "") if r["result_json"] else ""}
        for r in rows
    ]
    pendings = []
    for r in rows:
        if r["verdict_tier"] == "conflict" and not r["owner_verdict"]:
            result = json.loads(r["result_json"]) if r["result_json"] else {}
            pendings.append({
                "cid": str(r["claim_id"]), "mine": str(result.get("mine", "")),
                "theirs": str(result.get("theirs", "")), "detail": str(result.get("detail", "")),
            })
    return {
        "evaluation": evaluation,
        "pending_verdicts": pendings,
        "verdicts": [
            {"cid": str(r["claim_id"]), "verdict": r["owner_verdict"], "at": r["created_at"]}
            for r in rows if r["owner_verdict"]
        ],
    }


# ———— 列表 / 详情快照 ————

@router.get("/diagnoses", response_model=list[DiagnosisSummary])
async def list_diagnoses(request: Request):
    def _read(conn):
        rows = conn.execute(
            "SELECT d.id, d.status, d.updated_at, d.conflicts_json, p.name AS product_name, c.name AS category "
            "FROM diagnoses d JOIN products p ON p.id=d.product_id "
            "LEFT JOIN categories c ON c.id=p.category_id "
            "ORDER BY d.updated_at DESC"
        ).fetchall()
        return [
            {
                "diagnosis_id": r["id"], "product_name": r["product_name"],
                "category": r["category"] or "未分类", "status": r["status"],
                "stage_hint": _stage_hint(r["status"], len(_pending_conflicts(r["conflicts_json"]))),
                "pending_conflicts_n": len(_pending_conflicts(r["conflicts_json"])),
                "updated_at": r["updated_at"],
            }
            for r in rows
        ]
    return await db.run(_read)


@router.get("/diagnoses/{diagnosis_id}", response_model=DiagnosisDetail)
async def get_diagnosis(diagnosis_id: str, request: Request):
    def _read(conn):
        d = conn.execute(
            "SELECT d.*, p.name AS product_name, p.fingerprint_json AS product_fingerprint, "
            "c.name AS category "
            "FROM diagnoses d JOIN products p ON p.id=d.product_id "
            "LEFT JOIN categories c ON c.id=p.category_id WHERE d.id=?",
            (diagnosis_id,),
        ).fetchone()
        if d is None:
            return None, None, None, None
        err = json.loads(d["error_json"]) if d["error_json"] else None
        archive_rows: dict[str, list[dict[str, Any]]] = {}
        for r in conn.execute(
            "SELECT table_id, row_json FROM archive_records WHERE product_id=? ORDER BY table_id, id",
            (d["product_id"],),
        ):
            archive_rows.setdefault(r["table_id"], []).append(json.loads(r["row_json"]))
        submissions = conn.execute(
            "SELECT * FROM data_submissions WHERE diagnosis_id=? ORDER BY seq_n", (diagnosis_id,)
        ).fetchall()
        return d, archive_rows, submissions, err
    d, archive_rows, submissions, err = await db.run(_read)
    if d is None:
        raise HTTPException(status_code=404, detail={"reason": "diagnosis 不存在"})

    missing = json.loads(d["missing_data_json"]) if d["missing_data_json"] else []
    fp_raw = json.loads(d["product_fingerprint"]) if d["product_fingerprint"] else []
    stage = parse_failed(d["status"])
    error_detail = None
    if stage:
        error_detail = {
            "stage": stage,
            "timeout": str((err or {}).get("timeout", "-")),
            "retries": int((err or {}).get("retries", 0)),
            "split_record": str((err or {}).get("split_record", "-")),
            "raw": str((err or {}).get("raw", "-")),
        }
    conflicts = _pending_conflicts(d["conflicts_json"])
    blocking = _blocking_errors(d["conflicts_json"])
    return DiagnosisDetail(
        diagnosis_id=d["id"], product_name=d["product_name"],
        category=d["category"] or "未分类", status=d["status"],
        stage_hint=_stage_hint(d["status"], len(conflicts)), pending_conflicts_n=len(conflicts),
        updated_at=d["updated_at"],
        fingerprint=[FingerprintItem(**f) for f in fp_raw] or None,
        activation_matrix=[ActivationEntry(**e) for e in (json.loads(d["activation_matrix_json"]) if d["activation_matrix_json"] else [])] or None,
        missing_data=[MissingItem(**m) for m in missing] or None,
        archive_summary=[m for m in missing if m.get("status") == "archived"] or None,
        archive_rows=archive_rows or None,
        pending_conflicts=conflicts or None,
        blocking_errors=blocking or None,
        submissions=[
            SubmissionRecord(
                n=s["seq_n"], at=s["created_at"], accepted=bool(s["accepted"]),
                table=_submission_table(s), rows=_submission_rows(s),
                errors=json.loads(s["reject_errors_json"]) if s["reject_errors_json"] else None,
            )
            for s in submissions
        ] or None,
        progress=json.loads(d["progress_json"]) if d["progress_json"] else None,
        error_detail=error_detail,
    )
