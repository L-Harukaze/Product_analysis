"""L2 不变式检查器（ARCHITECTURE 11.3，五类通用不变式 · 三档处置）。

| 不变式 | 检查内容 | 处置档 |
|---|---|---|
| 算术闭合 | 份额类字段同组求和≈1 | **error**：阻断 execute |
| 口径混算 | 同组同指标不同值且置信档/口径不同 | **error**：阻断 execute |
| 跨源碰撞 | 同组同指标不同值（置信档与口径一致） | **conflict**：409 触发被拒 |
| 时窗错位 | 同表 period 多值且时间窗不重叠 | **warn**：放行，报告注记 |
| 值越界 | 数值超合理域（负价格、份额>100%） | **warn**：放行，报告注记 |

纪律：
- **零方法知识（T2）**：规则是通用代码——读档案行 + `_shared/contract.md` 的置信三档/口径契约，
  字段名语义按通用词根识别（share/percent/price…），无任何 per-方法分支
- **宁可少检不可误报**（需求 R2.1 首版裁量）：只在形态明确可判时出检，形态不明的组直接跳过
- 行引用格式 `"表B 行 2"`（1-based，与 L1 打回定位 11.2 同构，前端据此标红定位）
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

# ———— 字段名语义词根（通用约定，非方法知识）————
_SHARE_HINT = ("share", "percent", "ratio", "proportion", "penetration", "份额", "占比", "率", "渗透")
_VALUE_HINT = ("price", "cost", "amount", "volume", "sales", "qty", "quantity", "revenue", "value",
               "价", "量", "额", "成本", "销量", "收入")
_PERIOD_HINT = ("period", "date", "month", "quarter", "year", "window", "时间", "期", "月", "年", "日")
_META_FIELDS = ("source_url", "confidence", "caliber")

_SHARE_SUM_TOLERANCE = 0.05   # 份额和≈1 的容差
_VALUE_DIFF_RATIO = 0.05      # 同指标不一致的相对差阈值（低于此视为同一值的精度噪声）

TIER_ERROR = "error"
TIER_CONFLICT = "conflict"
TIER_WARN = "warn"

INVARIANT_LABELS = {
    "算术闭合": TIER_ERROR,
    "口径混算": TIER_ERROR,
    "跨源碰撞": TIER_CONFLICT,
    "时窗错位": TIER_WARN,
    "值越界": TIER_WARN,
}


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _hinted(field: str, hints: tuple[str, ...]) -> bool:
    low = str(field).lower()
    return any(h in low for h in hints)


def _numbers(row: dict[str, Any]) -> dict[str, float]:
    return {k: float(v) for k, v in row.items() if _is_number(v)}


def _period_of(row: dict[str, Any]) -> str:
    """行的时间窗取值（与 _check_share_closure 同源）。无 period 字段 → ""（整表同期）。"""
    return next((str(row[k]) for k in sorted(row) if _hinted(k, _PERIOD_HINT)), "")


def _dimension_key(row: dict[str, Any]) -> str:
    """行的维度键：非数值、非时间、非三件套的字段值组合（player/version/band/tier…）。

    无此类字段时退化为整表一组（key=""）——少检不误报。
    """
    parts: list[str] = []
    for k in sorted(row):
        if k in _META_FIELDS or _hinted(k, _PERIOD_HINT):
            continue
        v = row[k]
        if _is_number(v) or isinstance(v, (dict, list)):
            continue
        parts.append(f"{k}={v}")
    return "|".join(parts)


def _parse_period_window(value: str) -> tuple[float, float] | None:
    """period 文本 → (起, 止) 数值序（年/月归一为小数年）。无法解析 → None（跳过该检查）。"""
    s = str(value).strip()
    # ⚠️ 必须非捕获组：`(19|20)\d{2}` 的 findall 只返回捕获组（"20"），年份会变成 20.0 而非 2020.0
    years = [float(y) for y in re.findall(r"(?:19|20)\d{2}", s)]
    months: list[int] = []
    m = re.search(r"(\d{1,2})\s*月", s)
    if m:
        months.append(int(m.group(1)))
    if not years:
        return None
    y0 = years[0]
    y1 = years[-1] if len(years) > 1 else years[0]
    m0 = months[0] if months else 1
    m1 = months[-1] if len(months) > 1 else 12
    # "Qn" 季度记号：映射到该季度的起止月
    q = re.search(r"[Qq]([1-4])", s)
    if q:
        n = int(q.group(1))
        m0, m1 = (n - 1) * 3 + 1, n * 3
    return (y0 + (m0 - 1) / 12.0, y1 + (m1 - 1) / 12.0)


def _finding(invariant: str, detail: str, rows: list[str],
             fixes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """冲突条目（types.ts L2Conflict 逐字：{id, invariant, detail, rows}）+ 内部 tier。

    fixes（可选，契约增量 2026-09-17 S28 迭代）：逐行替换建议——前端档案库在标红行下方
    渲染"建议 X 替换为 Y"（比通用指引具体一个层级）。
    """
    seed = f"{invariant}|{','.join(sorted(rows))}|{detail[:80]}"
    cid = "C-" + hashlib.md5(seed.encode("utf-8")).hexdigest()[:6]
    item = {
        "id": cid,
        "invariant": invariant,
        "tier": INVARIANT_LABELS[invariant],
        "detail": detail,
        "rows": rows,
        "handled": None,
    }
    if fixes:
        item["fixes"] = fixes
    return item


def _row_ref(tid: str, idx: int) -> str:
    return f"表{tid} 行 {idx}"


# ———— 修复建议（S28 迭代）：以最高置信档为基准的逐行替换建议 ————

_SOURCE_RANK = {"官方": 0, "第三方": 1, "估算": 2}  # 官方>第三方>估算>未标（同 _arbitrate 的仲裁序）

_EQUAL_EPS = 1e-9


def _build_fixes(tid: str, field: str, items: list[tuple[int, dict[str, Any]]]) -> list[dict[str, Any]] | None:
    """组内同字段取值不一致 → 逐行修复建议（前端行下卡片"建议 X 替换为 Y"的数据源）。

    规则（**宁可少给不可误导**——与误报裁量同一纪律）：
    - 基准 = 最高置信档（官方>第三方>估算>未标）且**该档内取值唯一**的行；
    - 最高档内部就取值不一致（无法仲裁）、或无从定基准 → 返回 None（前端回退通用指引，交人工核对）；
    - 基准行给 action="keep"（保留说明），值已一致的行给 keep，其余行给 action="replace"
      （{row, field, action, from, to, note}，row 为 `表X 行 N` 引用）。
    """
    ranked = sorted(items, key=lambda it: (_SOURCE_RANK.get(str(it[1].get("confidence", "")), 3), it[0]))
    top_rank = _SOURCE_RANK.get(str(ranked[0][1].get("confidence", "")), 3)
    top = [it for it in ranked if _SOURCE_RANK.get(str(it[1].get("confidence", "")), 3) == top_rank]
    top_vals = {round(float(row[field]), 6) for _, row in top}
    if len(top_vals) != 1:
        return None  # 最高档内部不一致 → 无唯一基准，不猜
    best_i, best_row = top[0]
    best_v = float(best_row[field])
    best_conf = str(best_row.get("confidence", "")) or "未标"
    best_ref = _row_ref(tid, best_i)
    fixes: list[dict[str, Any]] = [{
        "row": best_ref, "field": field, "action": "keep",
        "from": best_v, "to": best_v,
        "note": f"本行是同组最高置信档（{best_conf}）——建议保留，其余行应对齐到本值",
    }]
    for i, row in items:
        if i == best_i:
            continue
        v = float(row[field])
        if abs(v - best_v) <= _EQUAL_EPS:
            fixes.append({
                "row": _row_ref(tid, i), "field": field, "action": "keep",
                "from": v, "to": best_v,
                "note": f"本行取值与同组基准一致（{best_ref}）——保留即可",
            })
        else:
            fixes.append({
                "row": _row_ref(tid, i), "field": field, "action": "replace",
                "from": v, "to": best_v,
                "note": f"与同组最高置信档保持一致（对齐 {best_ref} · {best_conf}）",
            })
    return fixes


def check(rows_by_table: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """档案行 → L2 发现清单（每项含 tier：error / conflict / warn）。"""
    findings: list[dict[str, Any]] = []

    for tid, rows in sorted(rows_by_table.items()):
        if not rows:
            continue
        _check_value_range(findings, tid, rows)
        _check_share_closure(findings, tid, rows)
        _check_source_collision(findings, tid, rows)
        _check_time_window(findings, tid, rows)

    order = {TIER_ERROR: 0, TIER_CONFLICT: 1, TIER_WARN: 2}
    findings.sort(key=lambda f: (order.get(f["tier"], 3), f["invariant"], f["id"]))
    return findings


# ———— 值越界（warn）————

def _check_value_range(findings: list[dict[str, Any]], tid: str, rows: list[dict[str, Any]]) -> None:
    for i, row in enumerate(rows, start=1):
        for f, v in _numbers(row).items():
            if _hinted(f, _SHARE_HINT):
                # 比例（0-1）或百分比（0-100）两种写法都合法；越界=负或>100
                if v < 0 or v > 100:
                    findings.append(_finding(
                        "值越界", f"{f}={v} 超出份额类合理域（允许 0-1 比例或 0-100 百分比）",
                        [_row_ref(tid, i)]))
            elif _hinted(f, _VALUE_HINT) and v < 0:
                findings.append(_finding("值越界", f"{f}={v} 为负（价格/量/额类字段不应为负）",
                                         [_row_ref(tid, i)]))


# ———— 算术闭合（error）：份额类字段同组求和≈1 ————

def _check_share_closure(findings: list[dict[str, Any]], tid: str, rows: list[dict[str, Any]]) -> None:
    groups: dict[tuple[str, str], list[tuple[int, float]]] = {}
    for i, row in enumerate(rows, start=1):
        period = next((str(row[k]) for k in sorted(row) if _hinted(k, _PERIOD_HINT)), "")
        for f, v in _numbers(row).items():
            if _hinted(f, _SHARE_HINT):
                groups.setdefault((f, period), []).append((i, v))
    for (field, period), items in sorted(groups.items()):
        if len(items) < 2:
            continue  # 单行无法判断闭合
        values = [v for _, v in items]
        if not all(0 <= v <= 1 for v in values):
            continue  # 百分比写法或含异常值 → 交由值越界/口径检查处理，此处不误报
        total = sum(values)
        if abs(total - 1.0) > _SHARE_SUM_TOLERANCE:
            ref = f"（{period}）" if period else ""
            findings.append(_finding(
                "算术闭合",
                f"字段 {field} 同组{ref}合计 {total:.3f} ≠ 1（份额类字段应闭合到 1）",
                [_row_ref(tid, i) for i, _ in items]))


# ———— 跨源碰撞（conflict）/ 口径混算（error）————

def _check_source_collision(findings: list[dict[str, Any]], tid: str, rows: list[dict[str, Any]]) -> None:
    # ⚠️ 分组键必须含 period（S26）：时序表（出货量/价格序列）同一维度**不同期**的数值本就不同，
    # 若按"同维度"分组会把跨期差异误判成"同指标值不一致" → 误报 error/conflict 永久阻断演示主线。
    # 真正的跨源碰撞 = 同维度 **且同期** 的两个来源取值不同。跨期不可比由"时窗错位"（warn）单独表达。
    groups: dict[tuple[str, str], list[tuple[int, dict[str, Any]]]] = {}
    for i, row in enumerate(rows, start=1):
        groups.setdefault((_dimension_key(row), _period_of(row)), []).append((i, row))
    for (key, period), items in sorted(groups.items()):
        if len(items) < 2:
            continue
        fields = set.intersection(*({f for f in _numbers(row)} for _, row in items)) if items else set()
        for f in sorted(fields):
            values = [(i, float(row[f])) for i, row in items]
            uniq = {round(v, 6) for _, v in values}
            if len(uniq) < 2:
                continue  # 完全一致 → 无碰撞
            base = max(abs(v) for _, v in values)
            if base <= 0 or (max(uniq) - min(uniq)) / base <= _VALUE_DIFF_RATIO:
                continue  # 差异在精度噪声内
            confs = {str(row.get("confidence", "")) for _, row in items}
            calibers = {str(row.get("caliber", "")) for _, row in items}
            mixed = len(confs) > 1 or len(calibers) > 1
            where = f"（{key}｜{period}）" if (key or period) else ""
            # 具体替换建议（S28 迭代）：混档场景以最高置信档为基准；同档不一致 → None（人工核对）
            fixes = _build_fixes(tid, f, items)
            if mixed:
                findings.append(_finding(
                    "口径混算",
                    f"字段 {f} 同组{where}取值不一致且口径/置信档混用："
                    f"置信={'/'.join(sorted(c for c in confs if c)) or '-'}、"
                    f"口径={'/'.join(sorted(c for c in calibers if c)) or '-'}（官方与第三方不可混算）",
                    [_row_ref(tid, i) for i, _ in values], fixes))
            else:
                findings.append(_finding(
                    "跨源碰撞",
                    f"字段 {f} 同组{where}双路径取值不一致："
                    + "、".join(f"{v:g}" for _, v in values) + f"（口径={'/'.join(sorted(c for c in calibers if c)) or '-'}）",
                    [_row_ref(tid, i) for i, _ in values], fixes))


# ———— 时窗错位（warn）————

def _check_time_window(findings: list[dict[str, Any]], tid: str, rows: list[dict[str, Any]]) -> None:
    """时窗错位（warn）—— S26 收窄：只检"单行时间窗倒挂（起 > 止）"这一形态明确可判的异常。

    原判据"同表各行区间无共同交集 → 跨期不可比"对**时序表必然误报**：出货量/价格/事件序列
    每行本就是不同时点，天然没有共同交集（K80 实测误报 9 条，全表命中）。
    按"宁可少检不可误报"（R2.1 裁量）收窄；跨期可比性交由方法执行时的混杂检查
    （confounder_check）与方法局限声明表达，不在 L2 层假装能判。
    """
    period_fields = [k for k in sorted(rows[0]) if _hinted(k, _PERIOD_HINT)]
    if not period_fields:
        return
    pf = period_fields[0]
    for i, row in enumerate(rows, start=1):
        if pf not in row:
            continue
        w = _parse_period_window(str(row[pf]))
        if w is None:
            return  # 无法解析 → 整体跳过（少检不误报）
        if w[0] > w[1]:
            findings.append(_finding(
                "时窗错位",
                f"字段 {pf} 时间窗起止倒挂（起 {w[0]:.2f} > 止 {w[1]:.2f}）",
                [_row_ref(tid, i)]))


# ———— 落库与裁决合并（11.3：裁决一次性持久化）————

def merge_with_verdicts(
    stored: list[dict[str, Any]], fresh: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """新检出项 × 库内已有裁决 → 合并（同 id 的裁决跨重放生效）。

    幂等语义（11.3）：Owner 维持过的冲突在重放/重跑时不再询问。

    ⚠️ 只保留"已裁决但本次未复现"的旧条目（审计：裁决过的事实不因数据变化凭空消失）；
    **未裁决且本次不再复现的条目必须丢弃**——数据已被修数修正、冲突不复存在，
    若继续保留会让 stale 未裁决冲突永久阻断 execute（S25：修数路径形同关闭）。
    """
    handled = {str(s.get("id")): s.get("handled") for s in stored if s.get("handled")}
    merged: list[dict[str, Any]] = []
    for f in fresh:
        item = dict(f)
        item["handled"] = handled.get(str(f["id"]))
        merged.append(item)
    # 已裁决但本次未复现的冲突保留（审计）；未裁决且未复现的 = 数据已修正，丢弃
    fresh_ids = {str(f["id"]) for f in fresh}
    merged.extend([s for s in stored
                   if str(s.get("id")) not in fresh_ids and s.get("handled")])
    return merged


def pending_conflicts(stored: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """未裁决的 conflict 档条目（前端 409 面板 / 详情 pending_conflicts）。"""
    return [
        {"id": s["id"], "invariant": s["invariant"], "detail": s["detail"], "rows": s.get("rows", [])}
        for s in stored if s.get("tier") == TIER_CONFLICT and not s.get("handled")
    ]


def blocking_errors(stored: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """error 档条目（详情 blocking_errors / 前端阻断卡片与修数入口的数据源）。

    error 档 = 必须修数的硬伤（算术闭合/口径混算），**没有"维持"语义**——不参与裁决，
    所以也不过滤 handled。入口在详情而不是 409 体：409 通用守卫体（13.3）保持三字段不变
    （冒烟步骤 12 有严格断言），且详情是持久的——刷新后卡片与修数入口不丢。
    下一次 execute 重跑 L2 时，已修正的条目按 merge_with_verdicts 规则（未裁决且未复现）丢弃。
    """
    return [
        {"id": s["id"], "invariant": s["invariant"], "detail": s["detail"], "rows": s.get("rows", [])}
        for s in stored if s.get("tier") == TIER_ERROR
    ]
