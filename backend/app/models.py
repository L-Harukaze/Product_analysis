"""API 契约模型（ARCHITECTURE 13 章 + 2026-09-16 契约增量）。

权威 TS 投影 = frontend/src/api/types.ts——本文件与其逐字对齐，禁止发明字段/枚举。
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# ———— 状态机（3.2）：DxBaseStatus | `failed_at(${DxStage})` ————

STAGES = ("routing", "data", "executing", "assembling")
BASE_STATUSES = ("created", "routed", "ready", "executing", "assembling", "done")


def failed_at(stage: str) -> str:
    assert stage in STAGES
    return f"failed_at({stage})"


def parse_failed(status: str) -> str | None:
    return status[len("failed_at("):-1] if status.startswith("failed_at(") else None


# ———— 请求 ————

class KnownFacts(BaseModel):
    price: float | None = None


class CreateDiagnosisRequest(BaseModel):
    """POST /diagnoses 请求（13.2 + 契约增量 1：background）"""
    product_name: str
    category_hint: str | None = None
    known_facts: KnownFacts | None = None
    background: str | None = Field(
        default=None,
        description="产品背景信息（Owner 微调 2026-09-16）：注入事务 A 路由 prompt，并随采集 prompt 下发",
    )


# ———— 事务 A 响应 ————

class FingerprintDetail(BaseModel):
    reason: str
    precedents: list[str] = []
    confidence: float


class FingerprintItem(BaseModel):
    dimension: Literal["F1", "F2", "F3", "F4", "F5", "F6"]
    label: str
    value: str
    source: Literal["L1 规则", "L2 定量·查表", "L3 仲裁"]
    detail: FingerprintDetail | None = None


class ActivationEntry(BaseModel):
    domain: str            # D1..D7（含名称）
    method: str | None     # null = 不适用（显式登记）
    form: str
    reason: str


class MissingItem(BaseModel):
    table: str             # 表 ID（A-G）
    name: str
    status: Literal["archived", "missing"]
    rows: int | None = None


class CreateDiagnosisResponse(BaseModel):
    """POST /diagnoses 响应 201（事务 A 同步返回）"""
    diagnosis_id: str
    status: str
    fingerprint: list[FingerprintItem]
    activation_matrix: list[ActivationEntry]
    missing_data: list[MissingItem]
    collection_prompt: str


# ———— 列表 / 详情 ————

class DiagnosisSummary(BaseModel):
    diagnosis_id: str
    product_name: str
    category: str
    status: str
    stage_hint: str        # 后端组装，前端不推算
    pending_conflicts_n: int
    updated_at: str


class DataSubmitRequest(BaseModel):
    """POST /data 请求（13.2）：豆包返回的原始 JSON 文本，原样入 data_submissions 快照"""
    payload: str


class DataError(BaseModel):
    """POST /data 打回结构（11.2，事务 B 实现消费）"""
    table: str
    row_index: int
    field: str
    error: str


class MethodError(BaseModel):
    timeout: str
    retries: int
    split_record: str
    raw: str


class SubmissionRecord(BaseModel):
    n: int
    at: str
    accepted: bool
    table: str
    rows: int | None = None
    errors: list[DataError] | None = None


class DiagnosisDetail(BaseModel):
    """GET /{id} —— 诊断全档案快照（按 mock 返回丰富度，联调对齐项 1）"""
    diagnosis_id: str
    product_name: str
    category: str
    status: str
    stage_hint: str
    pending_conflicts_n: int
    updated_at: str
    fingerprint: list[FingerprintItem] | None = None
    activation_matrix: list[ActivationEntry] | None = None
    missing_data: list[MissingItem] | None = None
    archive_summary: list[dict[str, Any]] | None = None
    archive_rows: dict[str, list[dict[str, Any]]] | None = None  # 契约增量 4
    pending_conflicts: list[dict[str, Any]] | None = None
    blocking_errors: list[dict[str, Any]] | None = None  # 契约增量（2026-09-17 S28）：error 档检出
    submissions: list[SubmissionRecord] | None = None
    progress: dict[str, Any] | None = None
    error_detail: dict[str, Any] | None = None


# ———— 错误体（13.3） ————

class ApiErrorBody(BaseModel):
    reason: str | None = None
    expected_states: list[str] | None = None
    current: str | None = None
    error_id: str | None = None
