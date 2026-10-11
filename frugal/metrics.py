"""Event telemetry logging and two-ledger token accounting."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from frugal import state, token_counter


def record_bash_event(
    session_id: str,
    command: str,
    exit_code: int,
    raw_output: str,
    compressed_output: str,
    tier_used: int,
    gemma_prompt_tokens: int = 0,
    gemma_completion_tokens: int = 0,
    latency_ms: int = 0,
    db_path: Path | None = None,
) -> None:
    """
    Records a frugal_bash event with exact token counts and Gemma overhead.
    """
    raw_tokens = token_counter.count_payload_tokens(raw_output)
    compressed_tokens = token_counter.count_payload_tokens(compressed_output)
    saved_tokens = max(0, raw_tokens - compressed_tokens)
    current_session = session_id or state.get_session_id()

    try:
        with state.get_connection(db_path=db_path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO sessions (session_id) VALUES (?);",
                (current_session,),
            )
            conn.execute(
                """
                INSERT INTO metrics (
                    session_id, tool, raw_tokens, compressed_tokens,
                    saved_tokens, tier_used, gemma_prompt_tokens,
                    gemma_completion_tokens, latency_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    current_session,
                    "frugal_bash",
                    raw_tokens,
                    compressed_tokens,
                    saved_tokens,
                    tier_used,
                    gemma_prompt_tokens,
                    gemma_completion_tokens,
                    latency_ms,
                ),
            )
    except sqlite3.OperationalError:
        pass


def record_read_event(
    session_id: str,
    path: str,
    was_deduplicated: bool,
    raw_content: str,
    compressed_content: str,
    latency_ms: int = 0,
    db_path: Path | None = None,
) -> None:
    """
    Records a frugal_read_file event into metrics table.
    """
    raw_tokens = token_counter.count_payload_tokens(raw_content)
    if was_deduplicated:
        compressed_tokens = token_counter.count_payload_tokens(compressed_content)
        saved_tokens = max(0, raw_tokens - compressed_tokens)
    else:
        compressed_tokens = raw_tokens
        saved_tokens = 0

    current_session = session_id or state.get_session_id()

    try:
        with state.get_connection(db_path=db_path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO sessions (session_id) VALUES (?);",
                (current_session,),
            )
            conn.execute(
                """
                INSERT INTO metrics (
                    session_id, tool, raw_tokens, compressed_tokens,
                    saved_tokens, tier_used, gemma_prompt_tokens,
                    gemma_completion_tokens, latency_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    current_session,
                    "frugal_read_file",
                    raw_tokens,
                    compressed_tokens,
                    saved_tokens,
                    1,
                    0,
                    0,
                    latency_ms,
                ),
            )
    except sqlite3.OperationalError:
        pass


def record_visual_event(
    session_id: str,
    visual_id: str,
    raw_tokens: int,
    compressed_tokens: int,
    gemma_prompt_tokens: int = 0,
    gemma_completion_tokens: int = 0,
    latency_ms: int = 0,
    db_path: Path | None = None,
) -> None:
    """
    Records a frugal_analyze_ui event into metrics table.
    """
    saved_tokens = max(0, raw_tokens - compressed_tokens)
    current_session = session_id or state.get_session_id()

    try:
        with state.get_connection(db_path=db_path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO sessions (session_id) VALUES (?);",
                (current_session,),
            )
            conn.execute(
                """
                INSERT INTO metrics (
                    session_id, tool, raw_tokens, compressed_tokens,
                    saved_tokens, tier_used, gemma_prompt_tokens,
                    gemma_completion_tokens, latency_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    current_session,
                    "frugal_analyze_ui",
                    raw_tokens,
                    compressed_tokens,
                    saved_tokens,
                    3,
                    gemma_prompt_tokens,
                    gemma_completion_tokens,
                    latency_ms,
                ),
            )
    except sqlite3.OperationalError:
        pass


def get_session_stats(
    session_id: str | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """
    Returns aggregate stats for the session with two-ledger transparency.
    """
    current_session = session_id or state.get_session_id()

    default_stats: dict[str, Any] = {
        "bash_calls": 0,
        "file_reads": 0,
        "visual_analyses": 0,
        "duplicate_reads_blocked": 0,
        "death_loops_interrupted": 0,
        "baseline_tokens": 0,
        "frugal_tokens": 0,
        "saved_tokens": 0,
        "reduction_percent": 0.0,
        "token_counter": "gemini-countTokens",
        "gemma_overhead_tokens": 0,
        "gemma_prompt_tokens": 0,
        "gemma_completion_tokens": 0,
        "net_tokens_saved": 0,
        "tier1_zero_cost_calls": 0,
        "tier2_tier3_calls": 0,
    }

    try:
        with state.get_connection(db_path=db_path) as conn:
            cur = conn.execute(
                """
                SELECT
                    COUNT(CASE WHEN tool = 'frugal_bash' THEN 1 END) as bash_calls,
                    COUNT(CASE WHEN tool = 'frugal_read_file' THEN 1 END) as file_reads,
                    COUNT(CASE WHEN tool = 'frugal_analyze_ui' THEN 1 END) as visual_analyses,
                    COUNT(CASE WHEN tool = 'frugal_read_file' AND saved_tokens > 0 THEN 1 END) as duplicate_reads_blocked,
                    COALESCE(SUM(raw_tokens), 0) as baseline_tokens,
                    COALESCE(SUM(compressed_tokens), 0) as frugal_tokens,
                    COALESCE(SUM(saved_tokens), 0) as saved_tokens,
                    COALESCE(SUM(gemma_prompt_tokens), 0) as gemma_prompt_tokens,
                    COALESCE(SUM(gemma_completion_tokens), 0) as gemma_completion_tokens,
                    COUNT(CASE WHEN tier_used = 1 THEN 1 END) as tier1_zero_cost_calls,
                    COUNT(CASE WHEN tier_used IN (2, 3) THEN 1 END) as tier2_tier3_calls
                FROM metrics
                WHERE session_id = ?;
                """,
                (current_session,),
            )
            row = cur.fetchone()

            if row:
                baseline = row["baseline_tokens"]
                saved = row["saved_tokens"]
                p_toks = row["gemma_prompt_tokens"]
                c_toks = row["gemma_completion_tokens"]
                overhead = p_toks + c_toks
                net_saved = saved - overhead
                red_pct = round((saved / baseline * 100), 2) if baseline > 0 else 0.0

                stats = {
                    "bash_calls": row["bash_calls"],
                    "file_reads": row["file_reads"],
                    "visual_analyses": row["visual_analyses"],
                    "duplicate_reads_blocked": row["duplicate_reads_blocked"],
                    "death_loops_interrupted": 0,
                    "baseline_tokens": baseline,
                    "frugal_tokens": row["frugal_tokens"],
                    "saved_tokens": saved,
                    "reduction_percent": red_pct,
                    "token_counter": "gemini-countTokens",
                    "gemma_overhead_tokens": overhead,
                    "gemma_prompt_tokens": p_toks,
                    "gemma_completion_tokens": c_toks,
                    "net_tokens_saved": net_saved,
                    "tier1_zero_cost_calls": row["tier1_zero_cost_calls"],
                    "tier2_tier3_calls": row["tier2_tier3_calls"],
                }
                return stats
    except sqlite3.OperationalError:
        pass

    return default_stats
