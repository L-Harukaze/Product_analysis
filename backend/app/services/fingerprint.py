"""指纹判定三级漏斗（ARCHITECTURE 7.1 / 7.2 / 5.4 / 3.4）。

确定性策略四级递进：规则直查 → 定量规则 → 带证据仲裁 → 落库固化。
- L1 规则直查（F2/F5/F6）：品类映射表直判，零 LLM
- L2 定量规则（F1）：产品价格 × 品类基线表，查表+比边界，零 LLM（档位边界值是数据）
- L3 带证据仲裁（F3/F4 及残余）：一次调用判全部待判维度（5.4 批量粒度），
  S1 维度定义 + S3 先例 + S6 基线锚点 + S4 输出契约 + 维度级解析校验
- 落库固化（7.2）：product 已有固化指纹直接复用（幂等）；仲裁输出即冻结
- 仲裁超时/维度级残缺 ≠ 路由失败（3.4）：保守档位 + 待补裁决清单，显式登记不静默
"""
from __future__ import annotations

import json
import logging
from typing import Any

from ..llm_provider import LLMProvider, LLMCallError

logger = logging.getLogger("fingerprint")

DIMENSIONS = ("F1", "F2", "F3", "F4", "F5", "F6")
L1_DIMS = ("F2", "F5", "F6")
SOURCE_L1 = "L1 规则"
SOURCE_L2 = "L2 定量·查表"
SOURCE_L3 = "L3 仲裁"

_PROMPT_TEMPLATE_VERSION = "arbiter-skeleton-5.4-v0"  # T7：骨架版戳，K80 实跑后固化 v1.0


class FingerprintService:
    def __init__(self, provider: LLMProvider, assets: dict[str, Any]):
        self.provider = provider
        self.category_map: dict[str, dict[str, str]] = assets["category_map"]
        self.dims: dict[str, dict[str, Any]] = assets["fingerprint_dims"]
        self.baselines: dict[str, dict[str, Any]] = assets["baselines"]

    # ———— 对外主入口 ————

    async def compute(
        self,
        *,
        product_name: str,
        category: str,
        known_price: float | None,
        frozen: list[dict[str, Any]] | None,
        precedent_rows: list[dict[str, Any]],
        diagnosis_id: str | None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """返回 (fingerprint_items, pending_arbitrations)。

        frozen 非空 → 直接复用（7.2 幂等，同产品重复路由结果必定一致）。
        """
        if frozen:
            return frozen, []

        items: dict[str, dict[str, Any]] = {}
        baseline = self.baselines.get(category)

        # L1 规则直查（F2/F5/F6）
        for dim in L1_DIMS:
            val = (self.category_map.get(category) or {}).get(dim)
            if val is not None:
                items[dim] = {
                    "dimension": dim, "label": self.dims[dim]["label"],
                    "value": val, "source": SOURCE_L1,
                }

        # L2 定量规则（F1）：查表+比边界，零 LLM；缺价格 → 退化 L3（7.1 fallback 链条）
        f1_value = None
        if baseline and known_price is not None:
            f1_value = self._lookup_f1(baseline, known_price)
        if f1_value is not None:
            items["F1"] = {
                "dimension": "F1", "label": self.dims["F1"]["label"],
                "value": f1_value, "source": SOURCE_L2,
            }

        # L3 带证据仲裁（F3/F4 及全部残余）
        pending_dims = [d for d in DIMENSIONS if d not in items]
        pending_records: list[dict[str, Any]] = []
        if pending_dims:
            arbitrated, failures = await self._arbitrate(
                product_name=product_name, category=category,
                pending_dims=pending_dims, baseline=baseline,
                precedent_rows=precedent_rows, diagnosis_id=diagnosis_id,
            )
            items.update(arbitrated)
            pending_records = failures

        ordered = [items[d] for d in DIMENSIONS if d in items]
        return ordered, pending_records

    # ———— L2：查表+比边界（通用函数，边界值全部来自基线表，T2 禁魔法数字） ————

    def _lookup_f1(self, baseline: dict[str, Any], price: float) -> str:
        """查表+比边界（7.1）：价格档=价格落分位区间；频率档=更换周期落月数区间。
        档位边界值全部来自基线表数据，代码零魔法数字（T2）；缺失=数据缺陷，显式报错（T6）。"""
        dist = baseline["price_distribution"]

        def p(key: Any) -> float | None:
            return dist[f"p{int(key):02d}"] if key is not None else None

        price_tier = next(
            (
                tier
                for tier, rng in (baseline.get("price_tiers") or {}).items()
                if (p(rng.get("pct_min")) is None or price >= p(rng.get("pct_min")))
                and (p(rng.get("pct_max")) is None or price < p(rng.get("pct_max")))
            ),
            None,
        )
        cycle = baseline["replacement_cycle_months"]
        freq_tier = next(
            (
                tier
                for tier, rng in (baseline.get("frequency_tiers") or {}).items()
                if cycle >= rng.get("min_months", 0) and cycle < rng.get("max_months", float("inf"))
            ),
            None,
        )
        if price_tier is None or freq_tier is None:
            raise ValueError(f"基线表 {baseline.get('category')} 的价格/频率档边界数据不完整，无法完成 L2 判定")
        return f"{freq_tier}{price_tier}"

    # ———— L3：带证据仲裁（5.4 槽位骨架，一次调用判全部待判维度） ————

    async def _arbitrate(
        self, *, product_name: str, category: str, pending_dims: list[str],
        baseline: dict[str, Any] | None, precedent_rows: list[dict[str, Any]],
        diagnosis_id: str | None,
    ) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
        # S1 维度定义 + S6 品类基线锚点（按维度分别检索、分区注入）
        s1_lines = [f"- {d} {self.dims[d]['label']}：档位 {self.dims[d]['tiers']}。判据：{self.dims[d]['doc']}" for d in pending_dims]
        s6_lines: list[str] = []
        if baseline:
            if "F3" in pending_dims and baseline.get("differentiation_anchor"):
                s6_lines.append(f"F3 差异化光谱锚点：{json.dumps(baseline['differentiation_anchor'], ensure_ascii=False)}")
            if "F4" in pending_dims and baseline.get("ecosystem_anchor"):
                s6_lines.append(f"F4 生态锚点：{json.dumps(baseline['ecosystem_anchor'], ensure_ascii=False)}")

        # S3 先例区（按维度检索；跨产品同品类历史仲裁）
        s3_lines = [
            f"先例：{r['product_name']}（{r['category']}）曾判定 {r['dimension']}={r['verdict']}，理由：{r['reason']}"
            for r in precedent_rows
        ]
        s5 = "若你的判定与上述先例不同，必须解释为何不同。" if s3_lines else ""

        system = (
            "你是产品经济学诊断系统的路由仲裁器。你的任务是基于产品常识判断（产品名/品类/维度判据），"
            "对给定的指纹维度做边界判定。这不是数据采集任务——只做产品固有属性判断。\n"
            "严格输出 JSON：{\"verdicts\": [{\"dimension\": \"F3\", \"value\": \"档位值\", "
            "\"reason\": \"判定理由（须引用你依据的锚点或先例）\", \"confidence\": 0.0}]}\n"
            "value 必须取自该维度声明的档位枚举，禁止自拟。confidence ∈ [0,1]。"
        )
        user = (
            f"## S1 待判维度定义\n" + "\n".join(s1_lines) + "\n\n"
            f"## S2 产品标识\n产品名：{product_name}\n品类：{category}\n\n"
            + (f"## S3 历史仲裁先例\n" + "\n".join(s3_lines) + f"\n{s5}\n\n" if s3_lines else "")
            + (f"## S6 品类基线锚点\n" + "\n".join(s6_lines) + "\n\n" if s6_lines else "")
            + f"## 输出要求\n对全部 {len(pending_dims)} 个待判维度（{'、'.join(pending_dims)}）各输出一条判定，"
            "不得遗漏任何维度。"
        )

        def _validate(data: Any) -> None:
            verdicts = data.get("verdicts") if isinstance(data, dict) else None
            if not isinstance(verdicts, list) or not verdicts:
                raise ValueError("缺少 verdicts 数组")
            got = {v.get("dimension") for v in verdicts}
            missing = set(pending_dims) - got
            if missing:
                raise ValueError(f"维度级残缺：缺少 {sorted(missing)}（5.4 维度级解析校验）")
            for v in verdicts:
                if v.get("dimension") in pending_dims:
                    if not v.get("value") or not v.get("reason") or v.get("confidence") is None:
                        raise ValueError(f"维度 {v.get('dimension')} 缺 reason/confidence 字段")

        try:
            data = await self.provider.call_json(
                "arbiter",
                [{"role": "system", "content": system}, {"role": "user", "content": user}],
                diagnosis_id=diagnosis_id,
                method="routing_arbitration",
                timeout_s=self.provider.roles["arbiter"].timeout_s,
                prompt_template_version=_PROMPT_TEMPLATE_VERSION,
                validate=_validate,
            )
        except LLMCallError as e:
            logger.warning("[fingerprint] L3 仲裁失败，走保守档位（3.4）：", exc_info=True)
            return self._conservative(pending_dims, baseline, str(e))

        # 档位合法性再校验（value ∈ tiers 枚举）
        out: dict[str, dict[str, Any]] = {}
        failures: list[dict[str, Any]] = []
        for v in data["verdicts"]:
            dim = v["dimension"]
            if dim not in pending_dims:
                continue
            declared = str(self.dims[dim]["tiers"]).split("/")
            if v["value"] not in declared:
                failures.append({
                    "dimension": dim, "value": self._conservative_value(dim, baseline),
                    "reason": f"仲裁输出档位 {v['value']} 不在声明枚举内，按保守档位处置（T6）",
                })
                continue
            out[dim] = {
                "dimension": dim, "label": self.dims[dim]["label"], "value": v["value"],
                "source": SOURCE_L3,
                "detail": {
                    "reason": v["reason"],
                    "precedents": [s for s in s3_lines[:3]] or
                                  [s.split("锚点：")[-1] for s in s6_lines[:1]],
                    "confidence": float(v["confidence"]),
                },
            }
        for f in failures:
            out.pop(f["dimension"], None)
        return out, failures

    def _conservative(self, pending_dims: list[str], baseline: dict[str, Any] | None,
                      error: str) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
        """3.4：仲裁超时 → 保守档位（宁可少激活、显式登记），生成待补裁决清单。"""
        items: dict[str, dict[str, Any]] = {}
        failures: list[dict[str, Any]] = []
        for dim in pending_dims:
            val = self._conservative_value(dim, baseline)
            failures.append({
                "dimension": dim, "value": val,
                "reason": f"L3 仲裁失败（{error[:200]}），按保守档位「{val}」处置；补裁决后 reroute 可得完整矩阵",
            })
            items[dim] = {
                "dimension": dim, "label": self.dims[dim]["label"], "value": val,
                "source": SOURCE_L3,
                "detail": {"reason": "仲裁失败，保守档位（待补裁决）", "precedents": [], "confidence": 0.0},
            }
        return items, failures

    def _conservative_value(self, dim: str, baseline: dict[str, Any] | None) -> str:
        if baseline and (baseline.get("conservative") or {}).get(dim):
            return baseline["conservative"][dim]
        declared = str(self.dims[dim]["tiers"]).split("/")
        return declared[len(declared) // 2]  # 枚举中位=最保守中性档
