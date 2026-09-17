"""Owner 预建数据 seed（幂等，可重复执行）。

预置内容（ARCHITECTURE 7.1 V1 范围）：
- categories：手机 / 零食 / 新能源车
- category_baselines：基线表 JSON 载荷（表H，与 assets/baselines/*.yaml 同源）
- products：SU7 指纹预置固化（已验证案例直接落固化结果，不依赖基线表，7.1）

用法：cd backend && python -m scripts.seed
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402
from app.assets import load_assets  # noqa: E402

CATEGORIES = [("mobile", "手机"), ("snack", "零食"), ("ev", "新能源车")]

# SU7 = M03 验证载体（2024-03-28 上市，21.59/24.59/29.99 万三档），指纹预置固化（7.1）
SU7_FINGERPRINT = [
    {"dimension": "F1", "label": "价格 × 频率", "value": "低频高价", "source": "L2 定量·查表"},
    {"dimension": "F2", "label": "信息属性", "value": "搜索品", "source": "L1 规则"},
    {
        "dimension": "F3", "label": "差异化", "value": "强", "source": "L3 仲裁",
        "detail": {
            "reason": "与同档竞品差异化显著：智能驾驶自研叙事 + 品牌势能，配置光谱独占一档",
            "precedents": ["参照锚点：特斯拉 Model 3（强差异化代表）"],
            "confidence": 0.86,
        },
    },
    {
        "dimension": "F4", "label": "生态", "value": "中", "source": "L3 仲裁",
        "detail": {
            "reason": "米家生态协同存在但车机互联对换机迁移成本的锁定弱于手机主线",
            "precedents": ["参照锚点：小米 15（生态绑定强代表）"],
            "confidence": 0.72,
        },
    },
    {"dimension": "F5", "label": "政策敏感", "value": "高", "source": "L1 规则"},
    {"dimension": "F6", "label": "供给形态", "value": "实体", "source": "L1 规则"},
]


async def main() -> None:
    db.init_schema()
    assets = load_assets()

    def _seed(conn) -> None:
        for cid, name in CATEGORIES:
            conn.execute(
                "INSERT INTO categories(id, name) VALUES (?,?) "
                "ON CONFLICT(id) DO NOTHING",
                (cid, name),
            )
        baseline_by_category = {"手机": "手机", "零食": "零食"}  # assets 键 = yaml 内 category 中文名
        for cname, key in baseline_by_category.items():
            b = assets["baselines"][key]
            cat = conn.execute("SELECT id FROM categories WHERE name=?", (cname,)).fetchone()
            if cat is None:
                continue
            existing = conn.execute(
                "SELECT id FROM category_baselines WHERE category_id=?", (cat["id"],)
            ).fetchone()
            payload = json.dumps(b, ensure_ascii=False)
            if existing is None:
                conn.execute(
                    "INSERT INTO category_baselines(category_id, baseline_json, source_url, confidence, caliber) "
                    "VALUES (?,?,?,?,?)",
                    (cat["id"], payload, b.get("source_url", ""), b.get("confidence", "第三方"), b.get("caliber", "")),
                )
        # SU7 指纹预置固化（7.1：不依赖基线表，跳过全部判定）
        conn.execute(
            "INSERT INTO products(id, name, category_id, fingerprint_json, fingerprint_source) "
            "VALUES ('p_su7_demo', '小米SU7', 'ev', ?, 'frozen') "
            "ON CONFLICT(id) DO NOTHING",
            (json.dumps(SU7_FINGERPRINT, ensure_ascii=False),),
        )

    await db.run(_seed)
    print("seed 完成：3 品类 + 2 基线表 + SU7 固化指纹")


if __name__ == "__main__":
    asyncio.run(main())
