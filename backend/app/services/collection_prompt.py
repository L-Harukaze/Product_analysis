"""采集 prompt 生成器（ARCHITECTURE 6.1）：纯代码模板填充，零 LLM。

固定骨架跨产品不变；变量点仅三处：表内容（方法需求决定）、时间窗（路由决定）、产品标识。
格式统一的根本保证是确定性组装——可复用、可统一校验（L1 按同一 schema 打回）。
打回条款：第 n 次生成自动携带第 n-1 次拒绝原因与定位（契约增量：background 注入「已知产品背景」节）。
"""
from __future__ import annotations

from typing import Any

from .data_validation import CONFIDENCE_TIERS

MISSING_FMT = "（缺）"


def _field_md(name: str, spec: dict[str, Any]) -> str:
    ftype = spec.get("type", MISSING_FMT)
    unit = f"（{spec['unit']}）" if spec.get("unit") else ""
    note = spec.get("note", "")
    if spec.get("enum"):
        note = (note + "；" if note else "") + f"枚举：{'/'.join(spec['enum'])}"
    required = "必填" if spec.get("required") else "可选"
    return f"| {name} | {ftype}{unit} | {required} | {note} |"


def generate(
    *,
    product_name: str,
    diagnosis_id: str,
    category: str,
    missing_tables: dict[str, dict[str, Any]],   # table_id → {name, fields, row_example}
    time_window: str,
    background: str | None,
    rejection_history: str | None = None,
    rejected_items: str | None = None,
) -> str:
    lines: list[str] = []
    lines.append(f"# 数据采集任务：{product_name}")
    lines.append(f"（诊断任务 {diagnosis_id}，品类：{category}）")
    lines.append("")
    lines.append(f"## 一、需要的表（共 {len(missing_tables)} 张，仅缺失部分）")
    for tid in sorted(missing_tables):
        t = missing_tables[tid]
        lines.append(f"### 表 {tid}：{t['name']}")
        lines.append("| 字段 | 类型 | 必填 | 说明 |")
        lines.append("|---|---|---|---|")
        for fname, spec in (t.get("fields") or {}).items():
            lines.append(_field_md(fname, spec or {}))
        example = t.get("row_example")
        if example:
            import json
            lines.append(f"行示例：`{json.dumps(example, ensure_ascii=False)}`")
        lines.append("")
    lines.append("## 二、硬规则")
    lines.append("1. 每条数据必须带 来源URL(source_url) + 置信档(confidence) + 口径(caliber)，无来源不入档：")
    lines.append(
        f"   - source_url 以 http(s):// 开头；confidence 只能取 {'/'.join(CONFIDENCE_TIERS)}；"
        "caliber 写明统计口径（如 中国大陆/全球、交付/锁单）"
    )
    lines.append("2. 数值字段只传数字本身：不带单位、不带 %、不带千分位文本；单位以表头声明为准（如单位万元的字段，21.59 就传 21.59）")
    lines.append("3. 枚举字段只能取表内声明的枚举值之一，禁止自拟或组合")
    lines.append("4. 总量数字以官方值为档案基准，第三方口径单独标注，不可混用")
    lines.append("5. 断链序列禁止插值；跨产品对比必须同期取样")
    lines.append("6. 估算值必须显式标注\"估算\"")
    lines.append(f"7. 时间范围：{time_window}")
    if background:
        lines.append("")
        lines.append("## 已知产品背景")
        lines.append(background.strip())
    lines.append("")
    lines.append("## 三、输出格式")
    lines.append("严格按以下 JSON 结构返回（与上表字段一致，格式示例）：")
    skeleton = {tid: [{"<字段>": "<按表声明类型>"}] for tid in sorted(missing_tables)}
    import json
    lines.append(f"{{\"tables\": {json.dumps(skeleton, ensure_ascii=False)}}}")
    lines.append("")
    lines.append("## 四、打回条款")
    lines.append(f"上次提交的拒绝原因（如有）：{rejection_history or '无'}")
    lines.append(f"请针对以下行/字段修正后重新提交：{rejected_items or '无'}")
    return "\n".join(lines)
