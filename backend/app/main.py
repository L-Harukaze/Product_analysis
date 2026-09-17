"""FastAPI 入口（ARCHITECTURE 施工顺序 P1/P2：注册表骨架 + 事务 A/B）。

启动序列（T6 显式失败，任一失败 → 启动失败）：
1. DB schema 初始化（8.1）
2. 静态资产加载（路由表/L1 映射/维度定义/基线表）
3. 方法包注册表加载 + 十条校验（9.2，路由表引用闭包传入）
4. llm.yaml 三角色加载 + 三条校验（5.1）

路由裸挂 /diagnoses（vite proxy 剥 /api 前缀）。
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import db
from .assets import load_assets
from .config import load_llm_config
from .llm_provider import LLMProvider
from .registry import Registry
from .routers import diagnoses

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_schema()
    assets = load_assets()
    route_method_ids = {r["method"] for r in assets["route_table"]["rules"]}

    registry = Registry()
    registry.load(referenced_method_ids=route_method_ids)

    roles = load_llm_config()
    provider = LLMProvider(roles)

    from .services.fingerprint import FingerprintService
    app.state.registry = registry
    app.state.assets = assets
    app.state.fingerprint_service = FingerprintService(provider, assets)
    app.state.llm_provider = provider
    yield
    await provider.aclose()


app = FastAPI(title="产品经济学诊断 Agent", version="0.4", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"], allow_headers=["*"],
)
app.include_router(diagnoses.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"ok": "true"}
