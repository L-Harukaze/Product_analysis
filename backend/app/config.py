"""配置加载：llm.yaml 三角色 + 环境变量 key（ARCHITECTURE 5.1）。

加载时三条校验（违反即启动失败，T6 显式报错不静默）：
1. qc.model != executor.model（异模型，G1.2）
2. 三角色 api_key 环境变量非空
3. max_concurrency > 0、timeout 配置合法
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = BACKEND_DIR.parent

load_dotenv(BACKEND_DIR / ".env")


class ConfigError(RuntimeError):
    """启动失败类错误（T6：不静默，启动即拦截）。"""


class RoleConfig:
    def __init__(self, role: str, raw: dict[str, Any]):
        self.role = role
        self.base_url: str = raw["base_url"]
        self.model: str = raw["model"]
        api_key_env: str = raw["api_key_env"]
        self.max_concurrency: int = int(raw["max_concurrency"])
        self.timeout_s: float | None = raw.get("timeout_s")
        self.api_key = os.environ.get(api_key_env, "").strip()
        if not self.api_key:
            raise ConfigError(f"[llm.yaml] 角色 {role} 的 api_key 环境变量 {api_key_env} 为空（5.1 校验 2）")
        if self.max_concurrency <= 0:
            raise ConfigError(f"[llm.yaml] 角色 {role} 的 max_concurrency 必须 > 0（5.1 校验 3）")
        if self.timeout_s is not None and self.timeout_s <= 0:
            raise ConfigError(f"[llm.yaml] 角色 {role} 的 timeout_s 必须为 null 或正数（5.1 校验 3）")


def load_llm_config() -> dict[str, RoleConfig]:
    path = BACKEND_DIR / "config" / "llm.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    roles = {name: RoleConfig(name, body) for name, body in raw["roles"].items()}
    for required in ("executor", "arbiter", "qc"):
        if required not in roles:
            raise ConfigError(f"[llm.yaml] 缺少角色 {required}（5.1 三角色配置矩阵）")
    if roles["qc"].model == roles["executor"].model:
        raise ConfigError("[llm.yaml] qc.model 不得等于 executor.model（异模型，5.1 校验 1 / G1.2）")
    return roles
