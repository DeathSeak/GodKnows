"""Circuit breaker for detecting agent death loops and blind retries."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from frugal import config, state


def compute_command_hash(command: str) -> str:
    """Computes SHA-256 hash of normalized command string."""
    normalized = " ".join(command.strip().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def check_command(
    command: str,
    session_id: str | None = None,
    db_path: Path | None = None,
) -> str | None:
    """
    Checks if this command triggers the circuit breaker.
    Queries the last N runs in command_runs for this command_hash.
    If all N exist and all have exit_code != 0, triggers an alert.
    Returns alert string if triggered, None otherwise.
    """
    cmd_str = command.strip()
    if not cmd_str:
        return None

    cmd_hash = compute_command_hash(cmd_str)
    current_session = session_id or state.get_session_id()
    cfg = config.get_config()
    max_repeats = cfg.breaker.max_repeats

    try:
        with state.get_connection(db_path=db_path) as conn:
            cur = conn.execute(
                """
                SELECT exit_code FROM command_runs
                WHERE session_id = ? AND command_hash = ?
                ORDER BY id DESC
                LIMIT ?;
                """,
                (current_session, cmd_hash, max_repeats),
            )
            rows = cur.fetchall()
    except sqlite3.OperationalError:
        # If database is locked, skip breaker check without blocking execution
        return None

    if len(rows) >= max_repeats and all(r["exit_code"] != 0 for r in rows):
        alert = (
            "[FRUGAL CIRCUIT BREAKER TRIGGERED]\n"
            f"Command: {cmd_str}\n"
            f"Repeated failures: {len(rows)}\n"
            "Last error signature: Command repeatedly exited with failure status\n\n"
            "Likely causes:\n"
            "- Unresolved syntax error or missing package dependency\n"
            "- Unmodified failing test expectation or broken environment\n\n"
            "Recommended actions:\n"
            "- Inspect the failing test or code file before re-executing\n"
            "- Inspect configuration and runtime logs\n"
            "- Do NOT rerun the exact same command without changing code"
        )
        return alert

    return None


def record_command_run(
    command: str,
    exit_code: int,
    session_id: str | None = None,
    db_path: Path | None = None,
) -> None:
    """
    Records a command execution into the command_runs table in state.db.
    """
    cmd_str = command.strip()
    if not cmd_str:
        return

    cmd_hash = compute_command_hash(cmd_str)
    current_session = session_id or state.get_session_id()

    try:
        with state.get_connection(db_path=db_path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO sessions (session_id) VALUES (?);",
                (current_session,),
            )
            conn.execute(
                """
                INSERT INTO command_runs (session_id, command, command_hash, exit_code)
                VALUES (?, ?, ?, ?);
                """,
                (current_session, cmd_str, cmd_hash, exit_code),
            )
    except sqlite3.OperationalError:
        pass
