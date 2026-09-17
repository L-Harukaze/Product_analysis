"""L3 QC 调用上下文（ARCHITECTURE 6.3 / 5.5）——**独立模块，与执行引擎无公共 import**。

5.5 异上下文（代码结构约束）：QC 的 prompt 组装与执行引擎不共享构建路径，
目的是防"执行引擎的自我辩护"污染质检——QC 看到执行过程就可能被锚定
（这本身就是 M04 讲的锚定效应：工具链设计遵守自己方法论的诊断结论）。

输入白名单（5.5 红线）：{承重数字, 来源声明, 档案原始记录（含 URL）, 方法名, 口径/置信元数据}；
**推理过程禁入**（中间表 / 引擎 prompt/响应 / skill 推理内容）。
"""
from __future__ import annotations

import re
from typing import Any

QC_PROMPT_VERSION = "qc-v1.0-whitelist"
ISSUE_TYPES = ("溯源不符", "来源可疑", "量级存疑", "口径混用", "与常识冲突")
VERDICTS = ("pass", "warn", "fail")

# 承重数字：L1_fact 中的数值（含单位/量级记号）
_NUMBER_PATTERN = re.compile(r"-?\d[\d,]*(?:\.\d+)?\s*(?:%|万|亿|元|辆|台|次|月|年|个|倍|pct)?")


def _numbers(text: str) -> list[str]:
    seen: list[str] = []
    for m in _NUMBER_PATTERN.findall(str(text)):
        v = m.strip()
        if v and v not in seen:
            seen.append(v)
    return seen


def _table_ids_of(registry: Any, method: str) -> list[str]:
    """方法消费的档案表 ID（用于取档案原始记录；读注册表，非执行引擎路径）。"""
    try:
        pkg = registry.get(method)
    except (KeyError, AttributeError):
        return []
    return sorted({str(k).split("_", 1)[0] for k in (pkg.input_tables or {})})


def build_batches(
    progress: dict[str, Any], archive: dict[str, list[dict[str, Any]]], registry: Any
) -> list[dict[str, Any]]:
    """per-method 批量（6.3 调用粒度）：每方法一批，携带该方法全部承重数字。

    承重数字定义（6.3 V1）= 各方法 `diagnostic_items.L1_fact` 的全部数字（事实层全部必检）。
    """
    batches: list[dict[str, Any]] = []
    for m in progress.get("methods", []):
        method = m.get("method")
        if not method or m.get("phase") != "done":
            continue
        result = m.get("result") or {}
        items = result.get("diagnostic_items") or [result.get("conclusion") or {}]
        numbers: list[dict[str, Any]] = []
        for i, it in enumerate(items):
            if not isinstance(it, dict):
                continue
            nums = _numbers(it.get("L1_fact", ""))
            if not nums:
                continue
            numbers.append({
                "id": f"{method}#{i + 1}",
                "method": method,
                "claim_text": str(it.get("L1_fact") or ""),
                "numbers": nums,
                "confidence": it.get("evidence_strength") or "第三方",
            })
        if not numbers:
            continue
        archive_rows: list[dict[str, Any]] = []
        for tid in _table_ids_of(registry, method):
            for r in (archive.get(tid) or [])[:20]:  # 档案原始记录（含来源 URL），限量防 prompt 爆炸
                archive_rows.append({"表": tid, **{k: v for k, v in r.items()}})
        batches.append({
            "method": method,
            "caliber": "见档案行 caliber 字段（口径声明）",
            "numbers": numbers,
            "archive_rows": archive_rows,
        })
    return batches


def messages(batch: dict[str, Any]) -> list[dict[str, str]]:
    system = (
        "[任务] 溯源核验 / 来源独立性 / 量级合理性（PRD 8.3 三查）。\n"
        "[输入] 承重数字清单（数字 | 方法名 | 口径声明 | 置信档 | 来源声明）+ 档案原始记录（含来源 URL）。\n"
        "[纪律] 只依据给定档案记录核验，不引入外部知识；无法核验的标 fail + 原因（不可验）。\n"
        "[输出] 严格 JSON："
        '{"items": [{"number": "承重数字标识（原样回填）", "verdict": "pass|warn|fail", '
        f'"issue_type": "{"|".join(ISSUE_TYPES)}|null", "reason": "理由", "basis": "依据（引用输入中的档案记录）"}}]\n'
        "逐条全量输出（含 pass 条目），输出条数必须等于输入承重数字条数——空数组不是通过。"
    )
    user = (
        f"## 承载方法\n{batch['method']}（口径声明：{batch['caliber']}）\n\n"
        f"## 承重数字清单（{len(batch['numbers'])} 条，逐条核验）\n"
        + "\n".join(
            f"- {n['id']}｜{n['method']}｜数字：{'、'.join(n['numbers'])}｜置信档：{n['confidence']}\n"
            f"  声称原文：{n['claim_text']}"
            for n in batch["numbers"]
        )
        + "\n\n## 档案原始记录（含来源 URL，核验唯一依据）\n"
        + (("\n".join(f"- 表{r.get('表')}：{r}" for r in batch["archive_rows"]))
           if batch["archive_rows"] else "（该方法未提供档案行）")
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def validate(data: Any, batch: dict[str, Any]) -> None:
    """6.3 防空数组偷懒通道：条数必须等于输入承重数字条数；枚举封闭。"""
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list) or len(items) != len(batch["numbers"]):
        raise ValueError(f"QC 输出条数应等于承重数字条数 {len(batch['numbers'])}，实际 {len(items or [])}")
    for it in items:
        if it.get("verdict") not in VERDICTS:
            raise ValueError(f"verdict 非法：{it.get('verdict')}（允许 {VERDICTS}）")
        t = it.get("issue_type")
        if t not in (None, "", "null") and t not in ISSUE_TYPES:
            raise ValueError(f"issue_type 非法：{t}（五类枚举封闭）")


def to_items(data: dict[str, Any], batch: dict[str, Any]) -> list[dict[str, Any]]:
    """LLM 输出 → QCItem（types.ts 逐字字段）。"""
    out: list[dict[str, Any]] = []
    for i, (src, it) in enumerate(zip(batch["numbers"], data.get("items") or []), start=1):
        it = it if isinstance(it, dict) else {}
        t = it.get("issue_type")
        out.append({
            "id": f"QC-{i:02d}",
            "number": f"{src['method']}｜{'、'.join(src['numbers'])}",
            "verdict": it.get("verdict") or "warn",
            "issue_type": t if t not in (None, "", "null") else None,
            "reason": str(it.get("reason") or ""),
            "basis": str(it.get("basis") or ""),
        })
    return out


def failed_items(batch: dict[str, Any], reason: str) -> list[dict[str, Any]]:
    """调用终态失败 → 缺条按该数字 fail 处置（6.3 显式，禁止静默通过）。"""
    return [
        {"id": f"QC-{i:02d}", "number": f"{n['method']}｜{'、'.join(n['numbers'])}",
         "verdict": "fail", "issue_type": "来源可疑",
         "reason": f"质检调用失败，按 fail 登记（6.3 缺条处置）：{reason[:200]}",
         "basis": "无（质检未执行）"}
        for i, n in enumerate(batch["numbers"], start=1)
    ]
