"""静态资产加载（Owner 预建数据资产，ARCHITECTURE 7.1/7.2）。

- route_table.yaml：路由表（指纹 × 路由表查表）
- category_map.yaml：L1 规则直查映射（F2/F5/F6）
- fingerprint_dims.yaml：指纹维度定义（S1 槽位 + label）
- baselines/*.yaml：品类基线表（表H：L2 定量 + S6 锚点 + 保守档位）
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"


def _load(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_assets() -> dict[str, Any]:
    baselines: dict[str, Any] = {}
    for p in (ASSETS_DIR / "baselines").glob("*.yaml"):
        body = _load(p)
        # 键 = 品类中文名（yaml 内声明），供指纹 L2/仲裁 S6 按品类检索
        baselines[body.get("category", p.stem)] = body
    return {
        "route_table": _load(ASSETS_DIR / "route_table.yaml"),
        "category_map": _load(ASSETS_DIR / "category_map.yaml"),
        "fingerprint_dims": _load(ASSETS_DIR / "fingerprint_dims.yaml"),
        "baselines": baselines,
    }
