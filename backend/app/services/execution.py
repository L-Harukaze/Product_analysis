"""事务 C/D/E 执行引擎（ARCHITECTURE 6.2 / 10 / 11 / 12 章）。

- 事务 C：分轮协议（轮次表来自方法包第 5 节声明）+ 配方五层 + 四项静态校验 + P-2 超时两分支
- 事务 D：分域 7 次同构装配（`services/assembly.py`）+ 图表纯代码装配（`services/charts.py`）
- 质检 L3：per-method 批量、异模型异上下文（`services/qc_context.py`，与执行引擎无公共 import）
- L2 不变式：execute 触发时五类检查（`services/invariants.py`）
- 方法池并发（P-1 信号量 8）+ 失败停顿（failed 未处置 → 不推进质检/装配）
- 进度落库 progress_json（10.2 轮询消费）：phase = pending | running(Rn[/N]) | done | failed
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

import yaml

from .. import db
from ..llm_provider import LLMCallError

logger = logging.getLogger("execution")

QC_METHOD_ID = "QC"
_MAX_ROWS_PER_TABLE = 20  # 注入 prompt 的每表行数上限（防 prompt 爆炸；V1 经验值）


def _load_progress(raw: str | None) -> dict[str, Any]:
    return json.loads(raw) if raw else {"methods": [], "done_n": 0, "total_n": 0}


def _load_json(raw: str | None, default: Any) -> Any:
    """JSON 列读取（防腐：库内历史脏值退化为默认值，不抛异常打断管道）。"""
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def init_progress(matrix: list[dict[str, Any]]) -> dict[str, Any]:
    """激活矩阵 → 进度初始化：激活方法 + QC 质检条目（前端管道条消费）。"""
    methods = [{"method": e["method"], "phase": "pending"} for e in matrix if e.get("method")]
    methods.append({"method": QC_METHOD_ID, "phase": "pending"})
    return {"methods": methods, "done_n": 0, "total_n": len(methods)}


def _save_progress(conn: Any, diagnosis_id: str, progress: dict[str, Any]) -> None:
    progress["done_n"] = sum(1 for m in progress["methods"] if m["phase"] == "done")
    conn.execute(
        "UPDATE diagnoses SET progress_json=?, updated_at=datetime('now') WHERE id=?",
        (json.dumps(progress, ensure_ascii=False), diagnosis_id),
    )


def _read_archive(conn: Any, product_id: str) -> dict[str, list[dict[str, Any]]]:
    rows: dict[str, list[dict[str, Any]]] = {}
    for r in conn.execute(
        "SELECT table_id, row_json FROM archive_records WHERE product_id=? ORDER BY table_id, id",
        (product_id,),
    ):
        rows.setdefault(r["table_id"], []).append(json.loads(r["row_json"]))
    return rows


def _result_entry(progress: dict[str, Any], method: str) -> dict[str, Any]:
    return next(m for m in progress["methods"] if m["method"] == method)


# ———— 事务 C：方法执行（6.2 配方五层 + 分轮协议 + P-2 超时两分支） ————

EXECUTOR_PROMPT_VERSION = "executor-v1.0-recipe5"  # T7 措辞触发制：配方 v1.0 基线


def _archive_slice(
    archive: dict[str, list[dict[str, Any]]], table_ids: list[str]
) -> dict[str, list[dict[str, Any]]]:
    """数据层切片（protocol.md 第 4 节第 3 条：每轮只携带该轮消费的表切片）。"""
    ids = {str(t) for t in table_ids}
    if not ids:
        ids = set(archive)  # 包未声明 → 全量（单轮直出形态）
    return {t: rows[:_MAX_ROWS_PER_TABLE] for t, rows in archive.items() if t in ids}


def _round_output_schema(pkg: Any, r: Any, is_final: bool) -> str:
    """该轮 output.schema 对应部分（S17：每轮 prompt 自携 schema，禁悬空引用）。"""
    out = pkg.output_schema.get("output", {}) or {}
    parts: dict[str, Any] = {}
    mids = out.get("intermediate_tables", {}) or {}
    sel = {k: v for k, v in mids.items() if k in (r.outputs or ())}
    if sel:
        parts["intermediate_tables"] = sel
    if is_final:
        for k in ("diagnostic_items", "conflict_resolutions", "data_gap_reports",
                  "method_xref", "limitations_statement"):
            if k in out:
                parts[k] = out[k]
    if not parts:
        parts = {"run": out.get("run", {})}
    return yaml.safe_dump(parts, allow_unicode=True, sort_keys=False)


def _round_messages(
    pkg: Any, r: Any, *, idx: int, total: int, is_final: bool, product_name: str, category: str,
    archive_slice: dict[str, list[dict[str, Any]]], prev_tables: dict[str, Any],
    shared: dict[str, str], last_error: str | None = None,
) -> list[dict[str, str]]:
    """配方五层（6.2）：纪律层 + 资产层 + 指令层 + 数据层 + 中间表层。"""
    system = (
        "你是经济学分析方法执行器。严格按给定的执行形态（轮次 / STEP 范围 / 产出）完成【本轮】分析，"
        "只输出约定的 JSON 对象（不要任何额外文本、不要 markdown 围栏）。所有量化表述必须能追溯到"
        "给定档案数据，或显式标注为估算。\n\n"
        "===== 系统纪律层 · 全局表述纪律 v1.0（每轮固定，_shared/discipline.md 全文）=====\n"
        + shared.get("discipline.md", "")
        + "\n\n===== 系统纪律层 · 全局数据契约 v1.0（每轮固定，_shared/contract.md 全文）=====\n"
        + shared.get("contract.md", "")
    )
    outputs_txt = "、".join(r.outputs) if r.outputs else "（本轮无中间表产出）"
    contract: dict[str, Any] = {
        "tables": {t: "行数组（字段按下述 output.schema）" for t in (r.outputs or [])},
        "notes": "本轮执行注记：本轮 STEP 的结论与判断（文本）",
        "flags": "本轮触发的降级 flag（只允许 output.schema 枚举值；无则空数组）",
    }
    if is_final:
        contract.update({
            "diagnostic_items": [{
                "L1_fact": "事实依据（数字+口径+来源+置信；官方类带原文引句）",
                "L2_mechanism": "机制解释（只许援引本方法理论支柱）",
                "L3_quantification": "量化结论（承重数字给来源口径；缺数据标未量化+原因）",
                "L4_prescription": "行动建议",
                "confounder_check": "已知混杂逐条检查结论",
                "evidence_strength": "官方|第三方|估算",
            }],
            "conflict_resolutions": "冲突检查留痕数组（可空）",
            "data_gap_reports": "数据缺口数组（可空）",
            "method_xref": "跨界方法线索数组（可空）",
            "limitations_statement": "已知局限声明（不得删除）",
        })
    blocks = [
        "===== 方法资产层（skill.md 全文，禁删减）=====\n"
        f"# 方法 {pkg.method_id} v{pkg.version}\n{pkg.skill_md}",
        "===== 任务指令层（编排器按第 5 节轮次表生成）=====\n"
        f"当前第 {idx}/{total} 轮：{r.label}（负载画像：{r.note or '未声明'}）\n"
        f"本轮执行范围：{r.step_label}\n"
        f"本轮输入表：{'、'.join('表' + t for t in r.input_tables) if r.input_tables else '（按方法定义取用）'}\n"
        f"本轮产出写入中间表：{outputs_txt}（只输出本轮声明的产出，禁自由扩展表名）\n"
        "停止条件：完成本轮声明范围即停止，禁止连跑后续轮次〔S20〕；轮内线性执行，"
        "禁反复重算、禁反复改写输出〔S14〕\n"
        "本轮输出 schema（自携，S17 禁悬空引用）：\n" + _round_output_schema(pkg, r, is_final) + "\n"
        "输出契约（严格按此 JSON 结构，缺字段不可）：\n" + json.dumps(contract, ensure_ascii=False, indent=1),
        "===== 数据层（本轮消费的档案切片，带来源/置信/口径三件套）=====\n"
        f"产品：{product_name}｜品类：{category}\n" + json.dumps(archive_slice, ensure_ascii=False),
    ]
    if prev_tables:
        blocks.append(
            "===== 中间表层（前轮中间表全文，已固化，直接消费禁重算）=====\n"
            + json.dumps(prev_tables, ensure_ascii=False)
        )
    if last_error:
        blocks.append("===== 上轮失败经验（必须规避）=====\n" + str(last_error))
    return [{"role": "system", "content": system}, {"role": "user", "content": "\n\n".join(blocks)}]


def _persist_method_result(
    conn: Any, diagnosis_id: str, method: str, round_no: int, data: dict[str, Any]
) -> None:
    for tname, rows in (data.get("tables") or {}).items():
        if not isinstance(rows, list):
            continue
        conn.execute(
            "INSERT OR REPLACE INTO intermediate_tables(diagnosis_id, method, round, table_name, row_json) "
            "VALUES (?,?,?,?,?)",
            (diagnosis_id, method, round_no, str(tname), json.dumps(rows, ensure_ascii=False)),
        )


async def run_method(
    state: dict[str, Any], diagnosis_id: str, method: str, last_error: str | None = None
) -> None:
    """执行单个方法（retry 复用）：逐轮配方 → LLM → 四项静态校验 → 中间表落库 → done/failed。

    - 分轮协议（6.2）：轮次来自方法包第 5 节声明，引擎无方法分支（T2）
    - P-2 预算级处置：单轮超时 → 按包声明的 STEP 边界拆小轮重跑【一次】；不可拆/仍超 → failed
    """
    registry = state["registry"]
    provider = state["llm_provider"]
    pkg = registry.get(method)
    shared = getattr(registry, "shared", {}) or {}
    rounds = list(pkg.rounds) or []

    def _read(conn):
        d = conn.execute(
            "SELECT d.product_id, p.name AS product_name, c.name AS category FROM diagnoses d "
            "JOIN products p ON p.id=d.product_id LEFT JOIN categories c ON c.id=p.category_id "
            "WHERE d.id=?",
            (diagnosis_id,),
        ).fetchone()
        return d, _read_archive(conn, d["product_id"])
    d, archive = await db.run(_read)
    category = d["category"] or "未分类"

    async def _set_phase(phase: str, error: dict[str, Any] | None = None, result: dict[str, Any] | None = None) -> None:
        def _write(conn) -> None:
            progress = _load_progress(conn.execute(
                "SELECT progress_json FROM diagnoses WHERE id=?", (diagnosis_id,)).fetchone()["progress_json"])
            entry = _result_entry(progress, method)
            entry["phase"] = phase
            if error:
                entry["error"] = error
            else:
                entry.pop("error", None)
            if result:
                entry["result"] = result
            _save_progress(conn, diagnosis_id, progress)
        await db.run(_write)

    async def _call_round(
        r: Any, idx: int, total: int, is_final: bool, prev: dict[str, Any], require_outputs: bool = True
    ) -> dict[str, Any]:
        """单轮 LLM 调用（配方组装 + 四项静态校验，5.2 三道防线内的代码校验）。"""
        return await provider.call_json(
            "executor",
            _round_messages(
                pkg, r, idx=idx, total=total, is_final=is_final,
                product_name=d["product_name"], category=category,
                archive_slice=_archive_slice(archive, r.input_tables), prev_tables=prev,
                shared=shared, last_error=last_error,
            ),
            diagnosis_id=diagnosis_id, method=method, round_no=r.round,
            timeout_s=pkg.time_limit_s, skill_version=pkg.version,
            prompt_template_version=EXECUTOR_PROMPT_VERSION,
            validate=lambda x: _validate_round(
                x, outputs=(r.outputs if require_outputs else []), is_final=is_final,
                flags_enum=pkg.downgrade_flags, known_tables=set(prev) | set(r.outputs),
            ),
        )

    # 方法级清桶：重跑（retry）= 该方法产物作废重写（8.3 清桶语义的方法级延伸）
    await db.run(lambda c: c.execute(
        "DELETE FROM intermediate_tables WHERE diagnosis_id=? AND method=?", (diagnosis_id, method)))

    total = len(rounds)
    produced: dict[str, list[dict[str, Any]]] = {}
    notes: list[str] = []
    flags: list[str] = []
    items: list[dict[str, Any]] = []
    extras: dict[str, Any] = {}
    split_record = f"按包声明轮次表执行（{total} 轮，未拆轮）"

    try:
        for idx, r in enumerate(rounds, start=1):
            is_final = idx == total
            phase = f"running({idx}/{total})" if total > 1 else "running(1)"
            await _set_phase(phase)
            try:
                data = await _call_round(r, idx, total, is_final, dict(produced))
            except LLMCallError as e:
                # P-2 预算级（a 分支）：超时且包声明了可拆的 STEP 边界 → 按声明切法拆小轮重跑【一次】
                subs = r.split_by_steps() if _is_timeout(e) else None
                if subs is None:
                    raise
                split_record = (
                    f"R{r.round} 超时 → 按包声明 STEP 边界拆为 "
                    f"{subs[0].step_label} / {subs[1].step_label} 重跑 1 次"
                )
                merged: dict[str, Any] = {"tables": {}, "notes": "", "flags": []}
                for i, sub in enumerate(subs):
                    await _set_phase(f"running({idx}/{total}·拆轮{i + 1}/{len(subs)})")
                    sd = await _call_round(sub, idx, total, is_final and i == len(subs) - 1,
                                           dict(produced), require_outputs=False)
                    for tname, rows in (sd.get("tables") or {}).items():
                        if isinstance(rows, list):
                            merged["tables"].setdefault(str(tname), []).extend(rows)
                    merged["notes"] = (merged["notes"] + "\n" + str(sd.get("notes") or "")).strip()
                    for f in (sd.get("flags") or []):
                        if f not in merged["flags"]:
                            merged["flags"].append(f)
                    for k in ("diagnostic_items", "conflict_resolutions", "data_gap_reports",
                              "method_xref", "limitations_statement"):
                        if sd.get(k):
                            merged[k] = sd[k]
                data = merged

            tables = {str(k): v for k, v in (data.get("tables") or {}).items() if isinstance(v, list)}
            produced.update(tables)
            if data.get("notes"):
                notes.append(f"R{r.round}：{data['notes']}")
            for f in (data.get("flags") or []):
                if f not in flags:
                    flags.append(f)
            if is_final:
                items = [it for it in (data.get("diagnostic_items") or []) if isinstance(it, dict)]
                extras = {
                    k: data.get(k) for k in ("conflict_resolutions", "data_gap_reports",
                                             "method_xref", "limitations_statement") if data.get(k)
                }
            await db.run(lambda c: _persist_method_result(c, diagnosis_id, method, r.round,
                                                          {"tables": tables}))

        if not items:
            raise ValueError("末轮未产出 diagnostic_items（四层结论），装配无法归位")
        head = items[0]
        result = {
            "conclusion": {
                k: str(head.get(k) or "")
                for k in ("L1_fact", "L2_mechanism", "L3_quantification",
                          "L4_prescription", "confounder_check")
            },
            "evidence_strength": head.get("evidence_strength") or "第三方",
            "flags": flags, "notes": notes, "diagnostic_items": items,
            "rounds": total, "split_record": split_record, **extras,
        }
        await _set_phase("done", result=result)
    except LLMCallError as e:
        await _set_phase("failed", error={
            "timeout": f"{pkg.time_limit_s:.0f}s", "retries": 2,
            "split_record": split_record, "raw": str(e)[:500],
        })
    except Exception as e:  # 后台任务兜底（T6：错误可见不静默）
        logger.exception("[execution] 方法 %s 异常", method)
        await _set_phase("failed", error={
            "timeout": f"{pkg.time_limit_s:.0f}s", "retries": 0,
            "split_record": split_record, "raw": f"{type(e).__name__}: {e}"[:500],
        })


def _is_timeout(err: Exception) -> bool:
    """P-2 预算级判定：time_limit 到点（区别于网络级失败）。"""
    return "超时" in str(err) or "timeout" in str(err).lower()


def _validate_round(
    data: Any, *, outputs: list[str], is_final: bool, flags_enum: list[str], known_tables: set[str]
) -> None:
    """四项静态校验（6.2）：产出齐全性 / 中间表引用完整性 / flag 枚举 / 末轮四层完整性。"""
    if not isinstance(data, dict):
        raise ValueError("输出不是 JSON 对象")
    tables = data.get("tables")
    if not isinstance(tables, dict):
        raise ValueError("缺少 tables 对象")

    # ① 产出齐全性：轮次表声明的产出中间表全部出现
    missing = [t for t in outputs if not isinstance(tables.get(t), list)]
    if missing:
        raise ValueError(f"轮次表声明的产出中间表缺失或非数组：{'/'.join(missing)}")

    # ② 中间表引用完整性（S17 代码化）：引用 `表名[行号]` 必须存在於前轮/本轮产出
    refs = set(re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*\[\s*\d+\s*\]",
                          json.dumps(tables, ensure_ascii=False)))
    dangling = sorted(x for x in refs if x not in known_tables)
    if dangling:
        raise ValueError(f"中间表引用悬空（S17）：{'/'.join(dangling)} 不在前轮/本轮产出中")

    # ③ flag 枚举校验（S4）：只允许 skill 第 4 节 / output.schema 声明的枚举值
    raw_flags = data.get("flags") or []
    flags = [raw_flags] if isinstance(raw_flags, str) else list(raw_flags)
    bad = [f for f in flags if f not in flags_enum]
    if bad:
        raise ValueError(f"flag {bad} 不在枚举内（S4 允许：{'/'.join(flags_enum) or '空'}）")

    # ④ 末轮：诊断项四层完整性
    if is_final:
        got = data.get("diagnostic_items")
        if not isinstance(got, list) or not got:
            raise ValueError("末轮缺 diagnostic_items（需 1-4 条四层诊断项）")
        for it in got:
            for k in ("L1_fact", "L2_mechanism", "L3_quantification",
                      "L4_prescription", "confounder_check"):
                if not str((it or {}).get(k) or "").strip():
                    raise ValueError(f"诊断项缺 {k}")


# ———— 质检（11.3 L3 / 6.3：per-method 批量，异模型异上下文，不拦截） ————

async def run_qc(state: dict[str, Any], diagnosis_id: str) -> list[dict[str, Any]]:
    """per-method 批量质检（6.3 调用粒度）：方法末轮完成后一次调用携带该方法全部承重数字。

    - 与装配解耦并发（qc 角色 max_concurrency=4，5.1）
    - 不拦截：结果落库 + 报告徽标，人裁决（11.3）
    - 逐条全量：缺条按该数字 fail 处置（6.3，禁空数组偷懒通道）
    """
    from . import qc_context  # 5.5 隔离：QC 上下文独立模块（与执行引擎无公共构建路径）

    provider = state["llm_provider"]
    registry = state.get("registry")

    def _read(conn):
        d = conn.execute(
            "SELECT progress_json, product_id FROM diagnoses WHERE id=?", (diagnosis_id,)
        ).fetchone()
        return _load_progress(d["progress_json"]), _read_archive(conn, d["product_id"])
    progress, archive = await db.run(_read)

    batches = qc_context.build_batches(progress, archive, registry)
    if not batches:
        return []
    timeout_s = getattr(provider.roles.get("qc"), "timeout_s", None)

    async def _one(batch: dict[str, Any]) -> list[dict[str, Any]]:
        data = await provider.call_json(
            "qc", qc_context.messages(batch),
            diagnosis_id=diagnosis_id, method=QC_METHOD_ID, round_no=1,
            timeout_s=timeout_s, prompt_template_version=qc_context.QC_PROMPT_VERSION,
            validate=lambda x: qc_context.validate(x, batch),
        )
        return qc_context.to_items(data, batch)

    results = await asyncio.gather(*(_one(b) for b in batches), return_exceptions=True)
    items: list[dict[str, Any]] = []
    for batch, res in zip(batches, results):
        if isinstance(res, BaseException):
            # T6：质检失败必须可见——按 fail 登记，不静默放行
            logger.warning("[execution] %s 质检失败（6.3 缺条按 fail 处置）：%s", batch["method"], res)
            items.extend(qc_context.failed_items(batch, f"{type(res).__name__}: {res}"))
        else:
            items.extend(res)
    # 全局唯一 id（跨方法不撞号）
    for i, it in enumerate(items, start=1):
        it["id"] = f"QC-{i:02d}"
    return items


# ———— 事务 D：装配（V1=纯代码组装） ————

# ———— 编排：失败停顿 + 质检 + 装配 + done ————

def _method_entries(progress: dict[str, Any]) -> list[dict[str, Any]]:
    return [m for m in progress["methods"] if m["method"] != QC_METHOD_ID]


def _all_settled(progress: dict[str, Any]) -> bool:
    return all(
        m["phase"] == "done" or (m["phase"] == "failed" and m.get("handled"))
        for m in _method_entries(progress)
    )


async def _finalize(state: dict[str, Any], diagnosis_id: str) -> None:
    """全部方法终态 → QC 与装配**解耦并发**（6.3）→ done（失败停顿：未处置的 failed 阻断在此）。"""
    def _read(conn):
        return conn.execute(
            "SELECT progress_json, activation_matrix_json, qc_json, qc_verdicts_json, conflicts_json "
            "FROM diagnoses WHERE id=?",
            (diagnosis_id,),
        ).fetchone()
    d = await db.run(_read)
    progress = _load_progress(d["progress_json"])
    if not _all_settled(progress):
        return  # 有 failed 未处置 → 停顿（前端展示人肉断点）

    # D1 根治：QC 条目一律从库读（reassemble 重放时 QC 已 done，不重跑也不询问）
    qc_items = _load_json(d["qc_json"], [])

    async def _qc_job() -> list[dict[str, Any]]:
        await db.run(lambda c: _set_method_phase_sync(c, diagnosis_id, QC_METHOD_ID, "running(1)"))
        items = await run_qc(state, diagnosis_id)
        await db.run(lambda c: _persist_qc_sync(c, diagnosis_id, items))
        await db.run(lambda c: _set_method_phase_sync(c, diagnosis_id, QC_METHOD_ID, "done"))
        return items

    qc_task = (asyncio.create_task(_qc_job())
               if _result_entry(progress, QC_METHOD_ID)["phase"] == "pending" else None)

    matrix = json.loads(d["activation_matrix_json"])
    await db.run(lambda c: c.execute(
        "UPDATE diagnoses SET status='assembling', updated_at=datetime('now') WHERE id=?", (diagnosis_id,)))
    progress = _load_progress((await db.run(_read))["progress_json"])
    # 12.2 分域装配（7 次同构调用 + 代码仲裁 + 图表装配）；装配失败 → failed_at(assembling)，T6 可见
    from .assembly import assemble

    try:
        report = await assemble(
            state, diagnosis_id, matrix=matrix, progress=progress, qc_items=qc_items,
            qc_verdicts=_load_json(d["qc_verdicts_json"], {}),
            conflicts=_load_json(d["conflicts_json"], []),
        )
        if qc_task is not None:
            qc_items = await qc_task
            verdicts = _load_json(d["qc_verdicts_json"], {})
            report["qc"] = [
                {**it, **({"owner_verdict": verdicts[str(it["id"])]["verdict"]}
                          if str(it.get("id")) in verdicts else {})}
                for it in qc_items
            ]
    except Exception as e:
        if qc_task is not None:
            qc_task.cancel()
        logger.exception("[execution] %s 装配失败", diagnosis_id)
        await db.run(lambda c: c.execute(
            "UPDATE diagnoses SET status=?, error_json=?, updated_at=datetime('now') WHERE id=?",
            ("failed_at(assembling)", json.dumps({"raw": str(e)[:500]}, ensure_ascii=False), diagnosis_id),
        ))
        return

    def _write(conn) -> None:
        conn.execute(
            "UPDATE diagnoses SET status='done', report_json=?, updated_at=datetime('now') WHERE id=?",
            (json.dumps(report, ensure_ascii=False), diagnosis_id),
        )
    await db.run(_write)
    logger.info("[execution] %s 装配完成 → done", diagnosis_id)


def _persist_qc_sync(conn: Any, diagnosis_id: str, qc_items: list[dict[str, Any]]) -> None:
    """11.4：QC 条目独立落库（report_json 会被 reassemble 整包重写，裁决/条目必须独立存活）。"""
    conn.execute(
        "UPDATE diagnoses SET qc_json=?, updated_at=datetime('now') WHERE id=?",
        (json.dumps(qc_items, ensure_ascii=False), diagnosis_id),
    )


def _set_method_phase_sync(conn: Any, diagnosis_id: str, method: str, phase: str) -> None:
    progress = _load_progress(conn.execute(
        "SELECT progress_json FROM diagnoses WHERE id=?", (diagnosis_id,)).fetchone()["progress_json"])
    _result_entry(progress, method)["phase"] = phase
    _save_progress(conn, diagnosis_id, progress)


async def run_pipeline(state: dict[str, Any], diagnosis_id: str) -> None:
    """事务 C 主流程：方法池并发 → 失败停顿/质检/装配（后台任务，异常落 failed_at(executing)，T6）。"""
    try:
        def _read(conn):
            return conn.execute(
                "SELECT progress_json, product_id FROM diagnoses WHERE id=?", (diagnosis_id,)
            ).fetchone()
        d = await db.run(_read)
        progress = _load_progress(d["progress_json"])
        targets = [m["method"] for m in _method_entries(progress) if m["phase"] == "pending"]
        await asyncio.gather(*(run_method(state, diagnosis_id, m) for m in targets))
        await _finalize(state, diagnosis_id)
    except Exception as e:
        logger.exception("[execution] 管道异常")
        await db.run(lambda c: c.execute(
            "UPDATE diagnoses SET status=?, error_json=?, updated_at=datetime('now') WHERE id=?",
            ("failed_at(executing)", json.dumps({"raw": str(e)[:500]}, ensure_ascii=False), diagnosis_id),
        ))


async def start_execution(state: dict[str, Any], diagnosis_id: str) -> None:
    """POST /execute 入口：进度初始化 + status=executing + 后台任务启动（202 同步返回）。"""
    def _init(conn) -> None:
        d = conn.execute(
            "SELECT activation_matrix_json, product_id FROM diagnoses WHERE id=?", (diagnosis_id,)
        ).fetchone()
        matrix = json.loads(d["activation_matrix_json"])
        # 8.3 清桶规则：重放 = 执行产物作废重写（否则 R1 新数据撞旧轮唯一键）。
        # llm_call_logs 不清——审计追加语义；qc_verdicts_json 不清——11.4 裁决一次性持久化。
        conn.execute("DELETE FROM intermediate_tables WHERE diagnosis_id=?", (diagnosis_id,))
        conn.execute(
            "UPDATE diagnoses SET status='executing', progress_json=?, qc_json=NULL, report_json=NULL, "
            "error_json=NULL, updated_at=datetime('now') WHERE id=?",
            (json.dumps(init_progress(matrix), ensure_ascii=False), diagnosis_id),
        )
    await db.run(_init)
    asyncio.create_task(run_pipeline(state, diagnosis_id))
