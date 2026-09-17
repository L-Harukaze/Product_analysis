"""L1 数据校验器（ARCHITECTURE 11.2）：input.schema.yaml（资产）→ 通用校验引擎（代码）。

- schema 是数据不是校验代码（T2）：字段存在/类型/枚举/URL 格式/必填全部由资产声明驱动，
  引擎零方法知识（不含任何 if method == "M03" 式分支）
- 行级三件套非空（PRD 8.2）：source_url + confidence(官方/第三方/估算) + caliber——
  库层 archive_records NOT NULL 约束是第二道闸（8.3），校验器先拦可读错误
- 错误消息结构化 {table, row_index, field, error}——6.1 采集 prompt 打回条款的数据源
- 缺数清单/需求并集构建也在此（事务 A/B 共享，消除重复）
"""
from __future__ import annotations

import json
from typing import Any

CONFIDENCE_TIERS = ("官方", "第三方", "估算")  # PRD 8.2 置信档枚举（采集 prompt 硬规则 1 同源）
META_FIELDS = ("source_url", "confidence", "caliber")  # 行级三件套
_NUMBER_TYPES = ("number", "int", "integer", "float")


def build_needed_tables(registry: Any, matrix: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """激活方法 input.tables 按表 ID 归并 fields 并集（2.2 数据需求汇总）。

    同字母多表 fields 并集合并是 V1 近似（Owner 已登记的决策点）。
    """
    needed: dict[str, dict[str, Any]] = {}
    for entry in matrix:
        if entry.get("method") is None:
            continue
        pkg = registry.get(entry["method"])
        for tkey, tdef in pkg.input_tables.items():
            tid = pkg.table_id(tkey)
            slot = needed.setdefault(
                tid, {"name": tdef.get("desc", tkey), "fields": {}, "row_example": tdef.get("row_example")}
            )
            for f, spec in (tdef.get("fields") or {}).items():
                slot["fields"].setdefault(f, spec)
    return needed


def summarize_missing(
    needed: dict[str, dict[str, Any]], counts: dict[str, int]
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """needed × 已有档案计数 = 缺数清单。返回 (missing_data 列表, 仅缺失表的 slot 字典)。"""
    missing_data: list[dict[str, Any]] = []
    missing_only: dict[str, dict[str, Any]] = {}
    for tid, slot in sorted(needed.items()):
        n = counts.get(tid, 0)
        missing_data.append({
            "table": tid, "name": slot["name"],
            "status": "archived" if n > 0 else "missing",
            "rows": n if n > 0 else None,
        })
        if n == 0:
            missing_only[tid] = slot
    return missing_data, missing_only


def parse_payload(payload: str) -> dict[str, list[dict[str, Any]]]:
    """解析豆包返回 JSON（{"tables": {表ID: [行...]}}）。失败抛 ValueError（可读消息进 errors）。"""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON 解析失败：{e.msg}（请粘贴豆包返回的原文）") from e
    tables = data.get("tables") if isinstance(data, dict) else None
    if not isinstance(tables, dict) or not tables:
        raise ValueError('payload 顶层缺少 "tables" 对象（按采集 prompt 第三节的输出格式返回）')
    # 表键归一：容忍 "A_config" 全键形态 → 表 ID "A"
    return {str(k).split("_", 1)[0]: v for k, v in tables.items()}


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def validate_tables(
    needed: dict[str, dict[str, Any]], tables: dict[str, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    """L1 校验（11.2）：返回结构化错误列表，空列表 = 全部合格。

    只校验缺数清单中的表（needed）；payload 多出的表忽略（6.1 采集 prompt 仅要求缺失部分）。
    """
    errors: list[dict[str, Any]] = []

    def add(tid: str, i: int, field: str, msg: str) -> None:
        errors.append({"table": tid, "row_index": i, "field": field, "error": msg})

    for tid, rows in tables.items():
        slot = needed.get(tid)
        if slot is None:
            continue  # 非本次缺数清单内的表：忽略
        if not isinstance(rows, list) or not rows:
            add(tid, 0, "-", "表数据为空或格式不对（应为行数组）")
            continue
        fields: dict[str, Any] = slot.get("fields") or {}
        for i, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                add(tid, i, "-", f"行格式错误：应为对象，实际 {type(row).__name__}")
                continue
            # 1) schema 驱动：必填 / 类型 / 枚举
            for fname, spec in fields.items():
                spec = spec or {}
                val = row.get(fname)
                if val is None or (isinstance(val, str) and not val.strip()):
                    if spec.get("required"):
                        add(tid, i, fname, "必填缺失")
                    continue
                t = str(spec.get("type", "")).lower()
                if t in _NUMBER_TYPES and not _is_number(val):
                    add(tid, i, fname,
                        f"类型错误：期望 {spec.get('type')}，实际是 {val!r}（请传数值，不要带单位/百分号的文本——硬规则 2）")
                enum = spec.get("enum")
                if enum and val not in enum:
                    add(tid, i, fname, f"枚举外取值 {val!r}（允许：{'/'.join(map(str, enum))}——硬规则 3）")
            # 2) 行级三件套（PRD 8.2 通用约束，schema 外）：非空 + URL 格式 + 置信档枚举
            for mf in META_FIELDS:
                val = row.get(mf)
                if val is None or (isinstance(val, str) and not val.strip()):
                    add(tid, i, mf, "必填缺失（硬规则 1：无来源不入档——每行须带 来源URL+置信档+口径）")
            su = row.get("source_url")
            if isinstance(su, str) and su.strip() and not (su.startswith("http://") or su.startswith("https://")):
                add(tid, i, "source_url", "URL 格式：须以 http(s):// 开头")
            conf = row.get("confidence")
            if conf is not None and (isinstance(conf, str) and conf.strip()) and conf not in CONFIDENCE_TIERS:
                add(tid, i, "confidence", f"置信档 {conf!r} 不合法（允许：{'/'.join(CONFIDENCE_TIERS)}）")

    # 同一行同一字段的重复错误只保留一条（如 G 表 caliber 既是 schema 必填又是三件套）
    seen: set[tuple[str, int, str]] = set()
    deduped: list[dict[str, Any]] = []
    for e in errors:
        key = (e["table"], e["row_index"], e["field"])
        if key not in seen:
            seen.add(key)
            deduped.append(e)
    return deduped


def format_rejection(errors: list[dict[str, Any]]) -> tuple[str, str]:
    """错误列表 → (rejection_history, rejected_items) 文本（6.1 打回条款注入采集 prompt）。"""
    history = (
        f"上次提交的拒绝原因（共 {len(errors)} 处错误）——请修正后重新提交：\n"
        + "\n".join(f"  · 第 {e['row_index']} 行 字段 {e['field']}：{e['error']}" for e in errors)
    )
    items = "；".join(f"表 {e['table']} 第 {e['row_index']} 行 字段 {e['field']}" for e in errors)
    return history, items
