"""D1-D7 问题域扫描（ARCHITECTURE 7.2）。

指纹 × 路由表查表，无 LLM——指纹一定，激活矩阵必定（确定性）。
域内方法选择按规则求值；域无命中 → 显式登记"不适用"行（K07 不静默缺席）。
"""
from __future__ import annotations

from typing import Any

F1_PRICE_TIERS = ("低价", "中价", "高价")


def scan(fingerprint: list[dict[str, Any]], route_table: dict[str, Any]) -> list[dict[str, Any]]:
    fp: dict[str, str] = {item["dimension"]: item["value"] for item in fingerprint}
    f1_price_tier = next((t for t in F1_PRICE_TIERS if t in fp.get("F1", "")), None)

    domains: dict[str, str] = route_table["domains"]
    not_applied: dict[str, str] = route_table.get("not_applied_reasons", {})
    entries: list[dict[str, Any]] = []

    for domain_id in domains:
        domain_label = f"{domain_id} {domains[domain_id]}"
        domain_entries: list[dict[str, Any]] = []
        for rule in route_table["rules"]:
            if rule["domain"] != domain_id:
                continue
            if not _match(rule["when"], fp, f1_price_tier):
                continue
            reason = rule.get("reason")
            if not reason and "reason_by_f1_price_tier" in rule:
                reason = rule["reason_by_f1_price_tier"].get(f1_price_tier or "", "")
            domain_entries.append({
                "domain": domain_label,
                "method": rule["method"],
                "form": rule["form"],
                "reason": reason or "",
            })
        if domain_entries:
            entries.extend(domain_entries)
        else:
            # 显式登记（K07：不静默缺席）
            entries.append({
                "domain": domain_label,
                "method": None,
                "form": "不适用",
                "reason": not_applied.get(domain_id, not_applied.get("default", "")),
            })
    return entries


def _match(when: dict[str, Any], fp: dict[str, str], f1_price_tier: str | None) -> bool:
    if when.get("always"):
        return True
    for cond, allowed in when.items():
        if cond == "always":
            continue
        if cond == "f1_price_tier":
            if f1_price_tier not in (allowed or []):
                return False
            continue
        dim = cond.upper()
        if not (dim.startswith("F") and len(dim) == 2 and dim[1].isdigit()):
            return False  # 未知条件键 → 规则不命中（显式保守，不误激活）
        if fp.get(dim) not in (allowed or []):
            return False
    return True
