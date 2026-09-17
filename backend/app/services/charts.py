"""图表数据装配（ARCHITECTURE 12.3：纯代码零 LLM）。

- chart.yaml 绑定（方法资产）+ 中间表 → ECharts option JSON
- 模板层锁死类型（_shared/chart_templates.yaml 的 kind/stack），实例层只填值写注记——
  **模型无选型权**（PRD 9.3 三层治理）
- 变体选择 = 代码规则（数据形态判定：观测数 / 断链），不解析自然语言 variant_rule
- option **零视觉属性**（颜色主题由前端注入，FRONTEND.md §9.3 边界约定）
- 未批准模板（v0.2 候选）与非 T- 声明（表格占位）不渲染图形
"""
from __future__ import annotations

import re
from typing import Any

import yaml

from ..config import WORKSPACE_ROOT

_TEMPLATES_PATH = WORKSPACE_ROOT / "methods" / "_shared" / "chart_templates.yaml"
_META_FIELDS = ("source_url", "confidence", "caliber")
_X_HINT = ("date", "period", "month", "year", "version", "pair", "band", "object",
           "tier", "param", "item", "player", "时间", "期", "月", "年", "档", "版本")


def _load_templates() -> dict[str, Any]:
    raw = yaml.safe_load(_TEMPLATES_PATH.read_text(encoding="utf-8")) or {}
    return raw.get("templates", {}) or {}


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _pick_fields(rows: list[dict[str, Any]]) -> tuple[str | None, str | None, str | None]:
    """(x 类目字段, y 数值字段, 分组字段)——通用数据形态判定，零方法知识。"""
    keys = [k for k in rows[0] if k not in _META_FIELDS]
    num_keys = [k for k in keys if any(_is_number(r.get(k)) for r in rows)]
    cat_keys = [k for k in keys if k not in num_keys]
    x_field = next((k for k in cat_keys if any(h in str(k).lower() for h in _X_HINT)),
                   cat_keys[0] if cat_keys else None)
    rest_cat = [k for k in cat_keys if k != x_field]
    return x_field, (num_keys[0] if num_keys else None), (rest_cat[0] if rest_cat else None)


def _has_gap(rows: list[dict[str, Any]], y_field: str) -> bool:
    """断链判定：序列中间存在缺失值（禁插值，断点留 None）。"""
    miss = [i for i, r in enumerate(rows) if r.get(y_field) is None]
    return bool(miss) and miss[0] > 0 and miss[-1] < len(rows) - 1


def _option(kind: str, rows: list[dict[str, Any]], *, stack: bool = False) -> dict[str, Any] | None:
    x_field, y_field, group = _pick_fields(rows)
    if x_field is None or y_field is None:
        return None
    if kind == "scatter":
        return {
            "xAxis": {"type": "value"},
            "yAxis": {"type": "value"},
            "series": [{
                "type": "scatter",
                "name": y_field,
                "data": [[r.get(x_field), r.get(y_field)]
                         for r in rows if _is_number(r.get(y_field))],
            }],
        }
    xs = [r.get(x_field) for r in rows]
    series: list[dict[str, Any]] = []
    if group:
        groups: list[str] = []
        for r in rows:
            g = str(r.get(group) or "")
            if g not in groups:
                groups.append(g)
        for g in groups:
            series.append({
                "type": kind, "name": g, "stack": "total" if stack else None,
                "data": [(r.get(y_field) if _is_number(r.get(y_field)) else None)
                         for r in rows if str(r.get(group) or "") == g],
            })
    else:
        series.append({
            "type": kind, "name": y_field, "stack": "total" if stack else None,
            "data": [(r.get(y_field) if _is_number(r.get(y_field)) else None) for r in rows],
        })
    for s in series:
        if s.get("stack") is None:
            s.pop("stack", None)
    return {
        "xAxis": {"type": "category", "data": xs},
        "yAxis": {"type": "value"},
        "series": series,
    }


def build_charts(
    registry: Any, method: str, mid_rows: dict[str, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    """方法包 chart.yaml 绑定 × 中间表 → ChartSpec 列表（types.ts 逐字：{chart_id, type, option, note}）。"""
    pkg = registry.get(method)
    templates = _load_templates()
    charts: list[dict[str, Any]] = []
    for binding in (pkg.chart.get("bindings") or []):
        srcs = binding.get("source_table")
        srcs = srcs if isinstance(srcs, list) else ([srcs] if srcs else [])
        tpls = binding.get("template")
        tpls = tpls if isinstance(tpls, list) else ([tpls] if tpls else [])
        rows: list[dict[str, Any]] = []
        for s in srcs:
            rows.extend(r for r in (mid_rows.get(str(s)) or []) if isinstance(r, dict))
        for tpl in tpls:
            tpl = str(tpl)
            if not tpl.startswith("T-"):
                continue  # 表格占位声明（v0.1）不渲染图形
            tpl_def = templates.get(tpl) or {}
            if "候选" in str(tpl_def.get("status", "")):
                continue  # 未批准模板：一律表格输出
            if not rows:
                continue
            kind = str(tpl_def.get("kind") or "bar")
            stack = bool(tpl_def.get("stack"))
            option = _option(kind, rows, stack=stack)
            if option is None:
                continue
            y_field = _pick_fields(rows)[1] or "-"
            note = (
                f"{tpl} {tpl_def.get('name', '')}｜观测 {len(rows)} 行，y={y_field}；"
                f"变体按数据形态规则选定（{'断链：断点留空·禁插值' if _has_gap(rows, y_field) else '连续序列'}）"
            )
            charts.append({
                "chart_id": f"{method}-{tpl}", "type": kind, "option": option, "note": note,
            })
    return charts


def chart_refs_of(charts: list[dict[str, Any]]) -> list[str]:
    return [str(c.get("chart_id")) for c in charts]
