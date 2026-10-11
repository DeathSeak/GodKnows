"""File read deduplication to prevent context waste from repetitive reads."""

from __future__ import annotations

import hashlib
from pathlib import Path

from frugal import config, security, state


def is_ignored_file(path_str: str) -> bool:
    """Checks if the file name matches the dedupe ignore list (e.g. lockfiles)."""
    cfg = config.get_config()
    ignore_list = cfg.dedupe.ignore
    filename = Path(path_str).name
    return filename in ignore_list


def compute_sha256(content_bytes: bytes) -> str:
    """Computes SHA-256 hex digest of file bytes."""
    return hashlib.sha256(content_bytes).hexdigest()


def check_and_read(
    path: str,
    force: bool = False,
    session_id: str | None = None,
    db_path: Path | None = None,
    project_root: Path | None = None,
) -> tuple[str, bool]:
    """
    Checks if a file has been read before with identical content in the current session.
    Returns (content_or_sentinel, was_deduplicated).
    """
    # 1. Path validation (prevent traversal outside project root)
    try:
        resolved_path = security.validate_path(path, project_root=project_root)
    except security.SecurityError as e:
        return f"[FRUGAL ERROR] {e}", False

    # 2. File existence check
    if not resolved_path.exists():
        return f"[FRUGAL ERROR] File not found: '{path}'", False

    if not resolved_path.is_file():
        return f"[FRUGAL ERROR] Path is not a regular file: '{path}'", False

    # 3. Read raw bytes
    try:
        raw_bytes = resolved_path.read_bytes()
    except OSError as e:
        return f"[FRUGAL ERROR] Failed to read file '{path}': {e}", False

    # 4. Check for binary file
    if security.is_binary_content(raw_bytes):
        return "[FRUGAL] Binary file detected. Content suppressed.", False

    # 5. Check for empty file
    if len(raw_bytes) == 0:
        return "[FRUGAL] File is empty.", False

    # 6. Decode text (utf-8 with latin-1 fallback) and normalize newlines
    try:
        text_content = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text_content = raw_bytes.decode("latin-1")
        except Exception as e:
            return f"[FRUGAL ERROR] Encoding error reading '{path}': {e}", False

    text_content = text_content.replace("\r\n", "\n").replace("\r", "\n")

    # 7. Check if file is larger than 1MB (1,048,576 bytes)
    lines = text_content.splitlines()
    is_large_file = len(raw_bytes) > 1024 * 1024
    if is_large_file:
        displayed_content = (
            "\n".join(lines[:1000])
            + f"\n\n[FRUGAL WARNING] File exceeds 1MB ({len(raw_bytes)} bytes). "
            + f"Displaying first 1000 lines of {len(lines)} lines."
        )
    else:
        displayed_content = text_content

    # If deduplication is globally disabled or file is in ignore list, skip deduping
    cfg = config.get_config()
    if not cfg.dedupe.enabled or is_ignored_file(path):
        return displayed_content, False

    # 8. Compute content hash
    content_sha256 = compute_sha256(raw_bytes)
    current_session = session_id or state.get_session_id()
    normalized_path_str = str(resolved_path)

    # 9. Query SQLite file_reads table
    try:
        with state.get_connection(db_path=db_path) as conn:
            # Ensure session exists
            conn.execute(
                "INSERT OR IGNORE INTO sessions (session_id) VALUES (?);",
                (current_session,),
            )

            # Determine next turn number
            cur_turn = conn.execute(
                "SELECT COALESCE(MAX(turn), 0) + 1 AS next_turn FROM file_reads WHERE session_id = ?;",
                (current_session,),
            )
            next_turn = cur_turn.fetchone()["next_turn"]

            # Check if previously read with same hash
            cur = conn.execute(
                """
                SELECT turn FROM file_reads
                WHERE session_id = ? AND path = ? AND sha256 = ?
                ORDER BY id DESC
                LIMIT 1;
                """,
                (current_session, normalized_path_str, content_sha256),
            )
            match = cur.fetchone()

            if match is not None and not force:
                previous_turn = match["turn"]
                line_count = len(lines)
                hash_short = content_sha256[:8]
                sentinel = (
                    f"[FRUGAL DEDUPE]\n"
                    f"File: {path}\n"
                    f"Status: unchanged since previous read\n"
                    f"Previous turn: {previous_turn}\n"
                    f"Lines skipped: {line_count}\n"
                    f"Hash: sha256:{hash_short}...\n"
                    f"Use force=True to reload."
                )
                return sentinel, True

            # If no match or force=True: record read
            conn.execute(
                """
                INSERT INTO file_reads (session_id, path, sha256, turn)
                VALUES (?, ?, ?, ?);
                """,
                (current_session, normalized_path_str, content_sha256, next_turn),
            )

    except Exception:
        # On database failure, return full content without crashing
        return displayed_content, False

    return displayed_content, False
