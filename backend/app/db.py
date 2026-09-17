"""SQLite 访问层（ARCHITECTURE 8 章 / P-3）。

- 单库单文件，WAL + busy_timeout
- 12 张表 + schema_version，启动时 CREATE TABLE IF NOT EXISTS（8.1 迁移策略）
- 外键 ON DELETE CASCADE 全声明；V1 API 不暴露删除端点（8.1）
- 全 async（P-3/T5）：阻塞调用经 asyncio.to_thread 包装
- T4 纪律：写事务必须纯写（毫秒级），禁止在 DB 事务内做 LLM 调用
"""
from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from typing import Any, Callable, TypeVar

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "app.db"

SCHEMA_VERSION = 1

# 统一 JSON 行模式（8.1）：业务载荷列 = 行级元数据列 + JSON 载荷列
DDL = [
    "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)",
    """CREATE TABLE IF NOT EXISTS categories (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        parent_id TEXT REFERENCES categories(id) ON DELETE CASCADE
    )""",
    """CREATE TABLE IF NOT EXISTS category_baselines (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category_id TEXT NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
        baseline_json TEXT NOT NULL,
        source_url TEXT NOT NULL,
        confidence TEXT NOT NULL,
        caliber TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE IF NOT EXISTS products (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        category_id TEXT REFERENCES categories(id),
        fingerprint_json TEXT,
        fingerprint_source TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE IF NOT EXISTS archive_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id TEXT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
        table_id TEXT NOT NULL,
        row_json TEXT NOT NULL,
        source_url TEXT NOT NULL,
        confidence TEXT NOT NULL,
        caliber TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_archive_product_table ON archive_records(product_id, table_id)",
    "CREATE INDEX IF NOT EXISTS idx_archive_source_url ON archive_records(source_url)",
    """CREATE TABLE IF NOT EXISTS diagnoses (
        id TEXT PRIMARY KEY,
        product_id TEXT NOT NULL REFERENCES products(id),
        status TEXT NOT NULL,
        activation_matrix_json TEXT,
        routing_reason_json TEXT,
        missing_data_json TEXT,
        pending_arbitrations_json TEXT,
        collection_prompt TEXT,
        background_note TEXT,
        progress_json TEXT,
        report_json TEXT,
        error_json TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_diagnoses_status ON diagnoses(status)",
    "CREATE INDEX IF NOT EXISTS idx_diagnoses_product ON diagnoses(product_id)",
    """CREATE TABLE IF NOT EXISTS data_submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        diagnosis_id TEXT NOT NULL REFERENCES diagnoses(id) ON DELETE CASCADE,
        seq_n INTEGER NOT NULL,
        payload_snapshot TEXT NOT NULL,
        accepted INTEGER NOT NULL,
        reject_errors_json TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE IF NOT EXISTS intermediate_tables (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        diagnosis_id TEXT NOT NULL REFERENCES diagnoses(id) ON DELETE CASCADE,
        method TEXT NOT NULL,
        round INTEGER NOT NULL,
        table_name TEXT NOT NULL,
        row_json TEXT NOT NULL,
        UNIQUE(diagnosis_id, method, round, table_name)
    )""",
    """CREATE TABLE IF NOT EXISTS llm_call_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        diagnosis_id TEXT,
        role TEXT NOT NULL,
        method TEXT,
        round INTEGER,
        prompt_text TEXT NOT NULL,
        response_text TEXT NOT NULL,
        token_in INTEGER,
        token_out INTEGER,
        latency_ms INTEGER,
        timeout_s REAL,
        retry_count INTEGER,
        skill_version TEXT,
        prompt_template_version TEXT,
        terminal_status TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_llm_logs_diag ON llm_call_logs(diagnosis_id)",
    """CREATE TABLE IF NOT EXISTS arbitration_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id TEXT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
        dimension TEXT NOT NULL,
        verdict TEXT NOT NULL,
        reason TEXT NOT NULL,
        confidence REAL,
        model TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE IF NOT EXISTS claims (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        diagnosis_id TEXT NOT NULL REFERENCES diagnoses(id) ON DELETE CASCADE,
        claim_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE IF NOT EXISTS claim_evaluations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        claim_id INTEGER NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
        verdict_tier TEXT NOT NULL,
        result_json TEXT,
        owner_verdict TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE IF NOT EXISTS method_registry (
        method_id TEXT PRIMARY KEY,
        version TEXT NOT NULL,
        path TEXT NOT NULL,
        time_limit_s REAL,
        loaded_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
]

_conn: sqlite3.Connection | None = None
_lock = asyncio.Lock()

T = TypeVar("T")


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA busy_timeout=5000")
        _conn.execute("PRAGMA foreign_keys=ON")
    return _conn


def _run_sync(fn: Callable[[sqlite3.Connection], T]) -> T:
    conn = _get_conn()
    try:
        result = fn(conn)
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise


async def run(fn: Callable[[sqlite3.Connection], T]) -> T:
    """串行化执行 DB 操作（P-3：单写者，避免 SQLITE_BUSY）。"""
    async with _lock:
        return await asyncio.to_thread(_run_sync, fn)


def init_schema() -> None:
    conn = _get_conn()
    for stmt in DDL:
        conn.execute(stmt)
    # 轻迁移（8.1 向后兼容）：增量列——旧库 ALTER 补列，不破坏既有数据
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(diagnoses)")}
    for col in ("background_note", "progress_json", "report_json",
                # 11.4：QC 条目与 Owner 裁决独立存活（reassemble 整包重写 report_json 会吞掉裁决）
                "qc_json", "qc_verdicts_json",
                # 11.3：L2 冲突清单挂 diagnosis（裁决一次性持久化，重放不再询问）
                "conflicts_json"):
        if col not in cols:
            conn.execute(f"ALTER TABLE diagnoses ADD COLUMN {col} TEXT")
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    if row is None:
        conn.execute("INSERT INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION,))
    elif row["version"] != SCHEMA_VERSION:
        raise RuntimeError(f"schema_version={row['version']} 与代码 {SCHEMA_VERSION} 不一致（8.1）")
    conn.commit()
