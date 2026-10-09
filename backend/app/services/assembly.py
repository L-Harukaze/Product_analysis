"""事务 D 报告装配器（ARCHITECTURE 12 章：分域 7 次同构装配 + 代码仲裁 + 图表装配）。

代码与 LLM 分工（12.1）：
| 环节 | 执行者 |
|---|---|
| 域归簇 + 弱适用/不适用域占位 | **代码**（激活矩阵查表，不静默缺席） |
| 跨方法冲突**检测** | LLM（输出槽 conflict_candidates） |
| 冲突**仲裁** | **代码**（证据强度规则；平局不仲裁，回交 Owner） |
| 分类学归位 + 章节组织 + 措辞 | LLM（优点四类/缺陷四类，PRD 9.2） |
| 四层完整性 / 货币化边界 / 图表引用 | **代码**后校验（阻断项） |
| 图表数据装配 | **代码**（12.3，零 LLM） |

纪律：分域调用失败**不传染**——单域回退到执行引擎原始四层并显式登记（T6 + 3.4）。
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from .. import db
from ..llm_provider import LLMCallError
from . import charts

logger = logging.getLogger("assembly")

ASSEMBLER_PROMPT_VERSION = "assembler-v1.0-domain7"
ASSEMBLER_METHOD_TAG = "assembler"  # 12.1：留痕 method=assembler（复用 executor 角色配置）
STRENGTH_ORDER = {"官方": 3, "第三方": 2, "估算": 1}  # 12.1 仲裁规则：官方 > 第三方 > 估算
TAXONOMY_TEXT = (
    "优点四类（规模学习 / 生态锁定 / 定价能力 / 信任资产）；"
    "缺陷四类（效率损失 / 信息不对称折价 / 结构脆弱 / 激励设计失败）——PRD 9.2 分类学"
)
FOUR_LAYERS = ("L1_fact", "L2_mechanism", "L3_quantification", "L4_prescription", "confounder_check")


def _cluster(
    matrix: list[dict[str, Any]], progress: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """代码预处理（12.2）：域归簇 + 占位（占位不占 LLM 调用）。"""
    clusters: list[dict[str, Any]] = []
    placeholders: list[dict[str, Any]] = []
    downgraded: list[dict[str, Any]] = []
    for e in matrix:
        domain = str(e.get("domain") or "-")
        domain_id = domain.split()[0]
        method = e.get("method")
        if method is None:
            placeholders.append({"domain_id": domain_id, "title": domain,
                                 "status": "not_applied", "note": str(e.get("reason") or "")})
            continue
        entry = next((m for m in progress.get("methods", []) if m["method"] == method), None)
        result = (entry or {}).get("result") or {}
        if not entry or entry.get("phase") != "done" or not result:
            note = ("该方法未完成（用户选择跳过，错误经验已沉淀到缺陷清单）"
                    if (entry or {}).get("handled") == "skipped"
                    else "该方法未完成（重试后仍失败，已如实登记）")
            placeholders.append({"domain_id": domain_id, "title": domain,
                                 "status": "weak", "note": note})
            downgraded.append({"method": method, "reason": note})
            continue
        items = result.get("diagnostic_items") or [result.get("conclusion") or {}]
        clusters.append({
            "domain_id": domain_id, "title": domain, "method": method,
            "items": [it for it in items if isinstance(it, dict)],
            "flags": list(result.get("flags") or []),
            "limitations": str(result.get("limitations_statement") or ""),
        })
    return clusters, placeholders, downgraded


def _domain_messages(
    c: dict[str, Any], *, idx: int, total: int, product_name: str, category: str,
    shared: dict[str, str], chart_ids: list[str],
) -> list[dict[str, str]]:
    system = (
        "你是产品经济学报告装配器。只做三件事：①按分类学给本域诊断项归位并组织章节；"
        "②在不新增数字的前提下优化表述（禁编造、禁跨方法汇总）；③指出域内/跨方法的语义冲突候选。"
        "严格输出 JSON（不要任何额外文本、不要 markdown 围栏）。\n\n"
        "===== 系统纪律层 · _shared/discipline.md =====\n" + shared.get("discipline.md", "")
    )
    src = [
        {"i": i, "method": c["method"],
         **{k: str(it.get(k) or "") for k in FOUR_LAYERS},
         "evidence_strength": it.get("evidence_strength") or "第三方"}
        for i, it in enumerate(c["items"])
    ]
    contract = {
        "items": [{
            "method": c["method"],
            "L1_fact": "事实依据（数字+口径+来源+置信；只可压缩表述，禁改数字禁新增）",
            "L2_mechanism": "机制解释", "L3_quantification": "量化结论",
            "L4_prescription": "行动建议", "confounder_check": "混杂检查",
            "evidence_strength": "官方|第三方|估算",
            "chart_refs": f"本域可用图表 ID（可空数组；允许：{'/'.join(chart_ids) or '无'}）",
        }],
        "conflict_candidates": [{"item_a": "索引 i", "item_b": "索引 j", "detail": "语义矛盾点"}],
        "note": "本域章节注记（分类学归位说明 / 局限；无则空字符串）",
    }
    user = "\n\n".join([
        f"===== 域骨架（第 {idx}/{total} 域，分域装配 12.2）=====\n"
        f"域：{c['title']}（{c['domain_id']}）｜承载方法：{c['method']}\n"
        f"产品：{product_name}｜品类：{category}\n"
        f"降级 flag：{'/'.join(c['flags']) if c['flags'] else '无'}\n"
        f"方法局限声明（必须保留）：{c['limitations'] or '（方法未给出）'}",
        f"===== 分类学定义（PRD 9.2，归位与排序依据）=====\n{TAXONOMY_TEXT}",
        "===== 本域预分组诊断项（来自方法执行，条数不得增减）=====\n"
        + json.dumps(src, ensure_ascii=False, indent=1),
        "===== 输出契约（严格按此 JSON 结构，items 条数必须等于输入条数）=====\n"
        + json.dumps(contract, ensure_ascii=False, indent=1),
        "===== 数据契约 · _shared/contract.md（口径/置信纪律）=====\n" + shared.get("contract.md", ""),
    ])
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _normalize_items(data: dict[str, Any], c: dict[str, Any], chart_ids: set[str]) -> list[dict[str, Any]]:
    """LLM 输出 → DiagnosticItem（types.ts 逐字字段，不发明新字段）。"""
    raw = data.get("items") if isinstance(data, dict) else None
    if not isinstance(raw, list) or len(raw) != len(c["items"]):
        raise ValueError(f"装配输出 items 条数应等于输入（{len(c['items'])}），实际 {len(raw or [])}")
    out: list[dict[str, Any]] = []
    for src, it in zip(c["items"], raw):
        it = it if isinstance(it, dict) else {}
        item = {k: str(it.get(k) or src.get(k) or "") for k in FOUR_LAYERS}
        strength = it.get("evidence_strength") or src.get("evidence_strength") or "第三方"
        if strength not in STRENGTH_ORDER:
            raise ValueError(f"evidence_strength 非法：{strength}")
        refs = [r for r in (it.get("chart_refs") or []) if str(r) in chart_ids]
        out.append({**item, "evidence_strength": strength, "chart_refs": refs,
                    "method": c["method"]})
    return out


def _arbitrate(
    clusters_out: list[dict[str, Any]], candidates: list[dict[str, Any]]
) -> tuple[str, list[str]]:
    """冲突仲裁（12.1：**代码**规则，非模型）：官方 > 第三方 > 估算；平局不仲裁。"""
    flat = [it for d in clusters_out for it in (d.get("items") or [])]
    log: list[str] = []
    unresolved: list[str] = []
    for c in candidates:
        try:
            a, b = flat[int(c.get("item_a", -1))], flat[int(c.get("item_b", -1))]
        except (ValueError, TypeError, IndexError):
            continue
        sa, sb = STRENGTH_ORDER.get(a.get("evidence_strength"), 0), STRENGTH_ORDER.get(b.get("evidence_strength"), 0)
        detail = str(c.get("detail") or "").strip()
        if sa == sb:
            unresolved.append(
                f"[{a.get('method')} vs {b.get('method')}] {detail}｜同强度对撞（{a.get('evidence_strength')}），"
                f"规则裁不了不假装能裁 → 整体降 conflict 档回交 Owner（12.1 平局条款）")
        else:
            loser, winner = (a, b) if sa < sb else (b, a)
            log.append(
                f"[{winner.get('method')} 胜 {loser.get('method')}] {detail}｜"
                f"按证据强度裁决（{winner.get('evidence_strength')} > {loser.get('evidence_strength')}），"
                f"败方保留留痕并降级")
    return "；".join(log) or "无", unresolved


async def assemble(
    state: dict[str, Any], diagnosis_id: str, *, matrix: list[dict[str, Any]],
    progress: dict[str, Any], qc_items: list[dict[str, Any]],
    qc_verdicts: dict[str, Any] | None = None, conflicts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """分域 7 次同构装配（12.2）→ 代码仲裁 + 后校验 → 报告 JSON。"""
    registry = state["registry"]
    provider = state["llm_provider"]
    shared = getattr(registry, "shared", {}) or {}
    clusters, placeholders, downgraded = _cluster(matrix, progress)

    def _read_ctx(conn):
        d = conn.execute(
            "SELECT p.name AS product_name, c.name AS category FROM diagnoses d "
            "JOIN products p ON p.id=d.product_id LEFT JOIN categories c ON c.id=p.category_id "
            "WHERE d.id=?", (diagnosis_id,)).fetchone()
        mids: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for r in conn.execute(
            "SELECT method, table_name, row_json FROM intermediate_tables WHERE diagnosis_id=?",
                (diagnosis_id,)):
            try:
                rows = json.loads(r["row_json"])
            except json.JSONDecodeError:
                continue
            if isinstance(rows, list):
                mids.setdefault(r["method"], {}).setdefault(r["table_name"], []).extend(rows)
        return d, mids
    ctx, mids = await db.run(_read_ctx)
    product_name = (ctx["product_name"] if ctx else "") or "-"
    category = (ctx["category"] if ctx else "") or "未分类"

    # 图表装配（12.3 纯代码，先于装配调用——chart_refs 需要可引用清单）
    all_charts: list[dict[str, Any]] = []
    for method in sorted(mids):
        try:
            all_charts.extend(charts.build_charts(registry, method, mids.get(method) or {}))
        except Exception:  # 单方法图表失败不阻断报告（T6：可见但可用）
            logger.exception("[assembly] 方法 %s 图表装配失败", method)
    chart_ids = [str(c["chart_id"]) for c in all_charts]
    id_set = set(chart_ids)

    # 分域同构装配 · 并发化（flash 刀6：原 for 串行 → asyncio.gather）
    # 依据：各域调用相互独立（单域失败回退机制即证明无依赖），并发受 executor 信号量约束；
    # 共享可变列表（candidates/downgraded）在 asyncio 单线程模型下无竞态。
    candidates: list[dict[str, Any]] = []
    total = len(clusters)

    async def _assemble_one(idx: int, c: dict[str, Any]) -> dict[str, Any]:
        budget = registry.get(c["method"]).time_limit_s
        try:
            data = await provider.call_json(
                "executor",
                _domain_messages(c, idx=idx, total=total, product_name=product_name,
                                 category=category, shared=shared, chart_ids=chart_ids),
                diagnosis_id=diagnosis_id, method=ASSEMBLER_METHOD_TAG, round_no=idx,
                timeout_s=budget, skill_version="assembly",
                prompt_template_version=ASSEMBLER_PROMPT_VERSION,
                validate=lambda x, _c=c: _normalize_items(x, _c, id_set),
            )
            items = _normalize_items(data, c, id_set)
            cands = [cand for cand in (data.get("conflict_candidates") or []) if isinstance(cand, dict)]
            note = str(data.get("note") or "")
        except LLMCallError as e:
            logger.warning("[assembly] 域 %s 装配失败，回退执行引擎原始四层（12.2 不传染）：%s",
                           c["domain_id"], e)
            items = [{
                **{k: str(it.get(k) or "") for k in FOUR_LAYERS},
                "evidence_strength": it.get("evidence_strength") or "第三方",
                "chart_refs": [], "method": c["method"],
            } for it in c["items"]]
            note = f"本域装配调用失败，已回退为方法执行原始四层结论（{str(e)[:120]}）"
            downgraded.append({"method": c["method"], "reason": note})
            cands = []
        return {"domain_id": c["domain_id"], "title": c["title"], "status": "active",
                "items": items, "cands": cands, "note": note}

    results = await asyncio.gather(*(_assemble_one(i, c) for i, c in enumerate(clusters, start=1)))
    domains_out: list[dict[str, Any]] = []
    for r in results:
        candidates.extend(r["cands"])
        domains_out.append({"domain_id": r["domain_id"], "title": r["title"],
                            "status": "active", "items": r["items"],
                            **({"note": r["note"]} if r["note"] else {})})

    # 代码后校验（12.2 阻断项）：四层完整性 + 货币化边界 + 图表引用完整性
    for d in domains_out:
        for it in d.get("items") or []:
            missing = [k for k in FOUR_LAYERS if not str(it.get(k) or "").strip()]
            if missing:
                raise ValueError(f"域 {d['domain_id']} 诊断项四层缺 {missing}（12.2 阻断项）")
            if it.get("method") != d.get("items", [{}])[0].get("method"):
                raise ValueError(f"域 {d['domain_id']} 出现跨方法汇总（货币化边界 G3.3 阻断项）")
            bad = [r for r in (it.get("chart_refs") or []) if r not in id_set]
            if bad:
                raise ValueError(f"图表引用不存在：{bad}（12.2 图表引用完整性）")

    conflict_log, unresolved = _arbitrate(domains_out, candidates)
    if unresolved:
        conflict_log = (conflict_log + "；" if conflict_log != "无" else "") + "；".join(unresolved)

    qc_out = []
    for it in qc_items:
        item = dict(it)
        v = (qc_verdicts or {}).get(str(it.get("id")))
        if v:
            item["owner_verdict"] = v.get("verdict")
        qc_out.append(item)

    log_parts, notes = [], []
    for c in conflicts or []:
        ref = "、".join(c.get("rows", []))
        if c.get("tier") == "conflict" and c.get("handled"):
            h = c["handled"]
            n = f"（{h.get('note')}）" if h.get("note") else ""
            log_parts.append(f"{c['invariant']}[{c['id']}]：Owner 裁决「{h.get('verdict')}」{n}——按原值继续，差异留痕")
            notes.append(f"{c['invariant']}：{c['detail']}（裁决「{h.get('verdict')}」，涉及 {ref}）")
        elif c.get("tier") == "conflict":
            log_parts.append(f"{c['invariant']}[{c['id']}]：未裁决（本报告按原值继续）")
        elif c.get("tier") == "warn":
            notes.append(f"{c['invariant']}（放行·注记）：{c['detail']}（涉及 {ref}）")
    if conflict_log != "无":
        log_parts.append(conflict_log)

    limitations = "\n\n".join([
        "分域装配（12.2）：每域一次同构调用，单域失败回退原始四层并显式登记。",
        "货币化边界（G3.3）：仅单方法内货币化，跨方法缺陷账单汇总不输出。",
        *([f"L2 放行注记：{x}" for x in notes]),
    ])
    return {
        "domains": domains_out + placeholders,
        "qc": qc_out,
        "charts": all_charts,
        "conflict_log": "；".join(log_parts) or "无",
        "l2_conflict_notes": "\n".join(notes) or "无",
        "downgraded_methods": downgraded,
        "limitations": limitations,
    }
