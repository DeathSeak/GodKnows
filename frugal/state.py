"""SQLite persistent state management for Frugal."""

from __future__ import annotations

import contextlib
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Generator

_CURRENT_SESSION_ID: str | None = None


def get_default_db_path(root_dir: Path | None = None) -> Path:
    base = root_dir or Path.cwd()
    return base / ".frugal" / "state.db"


def get_session_id() -> str:
    """
    Returns current session ID (UUID4), cached in memory.
    """
    global _CURRENT_SESSION_ID
    if _CURRENT_SESSION_ID is None:
        _CURRENT_SESSION_ID = str(uuid.uuid4())
    return _CURRENT_SESSION_ID


def set_session_id(session_id: str) -> None:
    """Sets the current session ID explicitly (useful for benchmarks/testing)."""
    global _CURRENT_SESSION_ID
    _CURRENT_SESSION_ID = session_id


def reset_session_id() -> str:
    """Resets and regenerates a new session ID."""
    global _CURRENT_SESSION_ID
    _CURRENT_SESSION_ID = str(uuid.uuid4())
    return _CURRENT_SESSION_ID


@contextlib.contextmanager
def get_connection(
    db_path: Path | None = None,
    timeout: float = 5.0,
    max_retries: int = 3,
    retry_delay: float = 0.1,
) -> Generator[sqlite3.Connection, None, None]:
    """
    Provides a sqlite3 connection context manager with row_factory=sqlite3.Row.
    Retries up to max_retries if the database is locked.
    """
    target = db_path or get_default_db_path()
    target.parent.mkdir(parents=True, exist_ok=True)

    conn: sqlite3.Connection | None = None
    last_err: Exception | None = None

    for attempt in range(max_retries):
        try:
            conn = sqlite3.connect(str(target), timeout=timeout)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA journal_mode = WAL;")
            break
        except sqlite3.OperationalError as e:
            last_err = e
            if "locked" in str(e).lower() and attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            raise

    if conn is None:
        if last_err:
            raise last_err
        raise RuntimeError("Failed to establish SQLite connection")

    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS file_reads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    turn INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE TABLE IF NOT EXISTS command_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    command TEXT NOT NULL,
    command_hash TEXT NOT NULL,
    exit_code INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id TEXT PRIMARY KEY,
    artifact_type TEXT NOT NULL CHECK(artifact_type IN ('log','visual','file')),
    path TEXT NOT NULL,
    meta TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    tool TEXT NOT NULL,
    raw_tokens INTEGER NOT NULL DEFAULT 0,
    compressed_tokens INTEGER NOT NULL DEFAULT 0,
    saved_tokens INTEGER NOT NULL DEFAULT 0,
    tier_used INTEGER NOT NULL DEFAULT 1,
    gemma_prompt_tokens INTEGER NOT NULL DEFAULT 0,
    gemma_completion_tokens INTEGER NOT NULL DEFAULT 0,
    latency_ms INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE INDEX IF NOT EXISTS idx_file_reads_path ON file_reads(path);
CREATE INDEX IF NOT EXISTS idx_file_reads_session ON file_reads(session_id);
CREATE INDEX IF NOT EXISTS idx_command_runs_hash ON command_runs(command_hash);
CREATE INDEX IF NOT EXISTS idx_command_runs_session ON command_runs(session_id);
CREATE INDEX IF NOT EXISTS idx_metrics_session ON metrics(session_id);
"""


def initialize_db(db_path: Path | None = None) -> None:
    """
    Initializes the SQLite database schema and ensures current session is recorded.
    Applies idempotent column migrations if necessary.
    """
    with get_connection(db_path=db_path) as conn:
        conn.executescript(SCHEMA_DDL)

        # Idempotent migration for radical transparency metrics columns
        cur = conn.execute("PRAGMA table_info(metrics);")
        existing_cols = {row["name"] for row in cur.fetchall()}
        if "gemma_prompt_tokens" not in existing_cols:
            conn.execute(
                "ALTER TABLE metrics ADD COLUMN gemma_prompt_tokens INTEGER NOT NULL DEFAULT 0;"
            )
        if "gemma_completion_tokens" not in existing_cols:
            conn.execute(
                "ALTER TABLE metrics ADD COLUMN gemma_completion_tokens INTEGER NOT NULL DEFAULT 0;"
            )

        sess_id = get_session_id()
        conn.execute(
            "INSERT OR IGNORE INTO sessions (session_id) VALUES (?);",
            (sess_id,),
        )
