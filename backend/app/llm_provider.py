"""LLM Provider 抽象与调用接口（ARCHITECTURE 5.2 / 5.3）。

- 统一 OpenAI 兼容 client：httpx.AsyncClient，每角色独立实例
- 结构化输出三道防线：prompt 约定 JSON → response_format=json_object → 代码解析+校验；
  解析/校验失败带错误反馈重试（P-2 网络级 2 次），仍失败 → 调用方按 T6 处置
- 调用留痕（5.3）：调用层统一写入 llm_call_logs，业务代码不自写
- 全 async（P-3）：禁止一切同步网络 IO
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any

import httpx

from .config import RoleConfig
from . import db

logger = logging.getLogger("llm")

MAX_RETRIES = 2  # P-2：网络级/解析级重试上限


class LLMCallError(RuntimeError):
    """调用终态失败（T6：由调用方结构化落库处置，不静默）。"""


def _extract_json(text: str) -> Any:
    """从响应文本提取 JSON（剥离 markdown 围栏等包装）。"""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    return json.loads(text)


class LLMProvider:
    def __init__(self, roles: dict[str, RoleConfig]):
        self.roles = roles
        self._clients: dict[str, httpx.AsyncClient] = {}
        self._semaphores = {
            name: asyncio.Semaphore(cfg.max_concurrency) for name, cfg in roles.items()
        }

    async def aclose(self) -> None:
        for c in self._clients.values():
            await c.aclose()

    def _client(self, role: str) -> httpx.AsyncClient:
        if role not in self._clients:
            cfg = self.roles[role]
            self._clients[role] = httpx.AsyncClient(
                base_url=cfg.base_url,
                headers={"Authorization": f"Bearer {cfg.api_key}"},
                timeout=httpx.Timeout(
                    (cfg.timeout_s or 600.0) + 30.0,
                    connect=10.0,
                ),
            )
        return self._clients[role]

    async def call_json(
        self,
        role: str,
        messages: list[dict[str, str]],
        *,
        diagnosis_id: str | None,
        method: str | None = None,
        round_no: int | None = None,
        timeout_s: float | None = None,
        skill_version: str | None = None,
        prompt_template_version: str | None = None,
        validate: Any = None,
    ) -> Any:
        """调用并解析 JSON（三道防线）。validate(data) 抛异常视为校验失败参与重试。"""
        cfg = self.roles[role]
        effective_timeout = timeout_s if timeout_s is not None else cfg.timeout_s
        msgs = list(messages)
        attempts = 0
        last_err: Exception | None = None
        start = time.monotonic()
        prompt_text = json.dumps(messages, ensure_ascii=False)
        response_text = ""
        usage_in = usage_out = 0
        retry_count = 0
        terminal = "failed"

        while attempts <= MAX_RETRIES:
            attempts += 1
            try:
                async with self._semaphores[role]:
                    payload: dict[str, Any] = {
                        "model": cfg.model,
                        "messages": msgs,
                        "response_format": {"type": "json_object"},
                    }
                    if cfg.enable_thinking is not None:
                        # flash 刀1：百炼思考模式开关（A/B 实测 2026-10-09：开思考 600s 超时 0/3，关思考 76s 四层全齐）
                        payload["enable_thinking"] = cfg.enable_thinking
                    resp = await self._client(role).post(
                        "/chat/completions", json=payload, timeout=effective_timeout,
                    )
                if resp.status_code != 200:
                    raise LLMCallError(f"HTTP {resp.status_code}: {resp.text[:500]}")
                body = resp.json()
                response_text = body["choices"][0]["message"]["content"]
                usage = body.get("usage") or {}
                usage_in, usage_out = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
                data = _extract_json(response_text)
                if validate is not None:
                    validate(data)
                terminal = "success" if retry_count == 0 else "retried_and_ok"
                self._log(
                    diagnosis_id=diagnosis_id, role=role, method=method, round_no=round_no,
                    prompt_text=prompt_text, response_text=response_text,
                    token_in=usage_in, token_out=usage_out,
                    latency_ms=int((time.monotonic() - start) * 1000),
                    timeout_s=effective_timeout, retry_count=retry_count,
                    skill_version=skill_version, prompt_template_version=prompt_template_version,
                    terminal_status=terminal,
                )
                return data
            except (httpx.TimeoutException, asyncio.TimeoutError):
                last_err = LLMCallError(f"调用超时（timeout_s={effective_timeout}）")
                terminal = "timeout"
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                last_err = e
                terminal = "failed"
            except Exception as e:  # 网络/HTTP 等
                last_err = e
                terminal = "failed"

            retry_count = attempts - 1
            if attempts <= MAX_RETRIES:
                # 带错误反馈重试（5.2 三道防线）
                msgs = list(messages) + [
                    {"role": "assistant", "content": response_text or ""},
                    {"role": "user", "content": f"上次输出不合法：{last_err}。请严格按约定的 JSON 结构重新输出，不要任何额外文本。"},
                ]

        self._log(
            diagnosis_id=diagnosis_id, role=role, method=method, round_no=round_no,
            prompt_text=prompt_text, response_text=response_text,
            token_in=usage_in, token_out=usage_out,
            latency_ms=int((time.monotonic() - start) * 1000),
            timeout_s=effective_timeout, retry_count=retry_count,
            skill_version=skill_version, prompt_template_version=prompt_template_version,
            terminal_status=terminal,
        )
        raise LLMCallError(f"[{role}] LLM 调用终态失败：{last_err}") from last_err

    @staticmethod
    def _log(**kw: Any) -> None:
        """5.3：调用层统一写入，业务代码不自写。"""

        def _insert(conn) -> None:
            conn.execute(
                "INSERT INTO llm_call_logs(diagnosis_id, role, method, round, prompt_text, response_text, "
                "token_in, token_out, latency_ms, timeout_s, retry_count, skill_version, "
                "prompt_template_version, terminal_status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    kw.get("diagnosis_id"), kw["role"], kw.get("method"), kw.get("round_no"),
                    kw["prompt_text"], kw["response_text"], kw["token_in"], kw["token_out"],
                    kw["latency_ms"], kw["timeout_s"], kw["retry_count"], kw["skill_version"],
                    kw["prompt_template_version"], kw["terminal_status"],
                ),
            )
        try:
            db._run_sync(_insert)
        except Exception:  # 留痕失败不阻断主流程，但必须可见（T6）
            logger.exception("[llm] 留痕落库失败")
