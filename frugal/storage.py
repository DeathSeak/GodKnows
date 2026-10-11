"""Disk persistence and escape hatch retrieval for Frugal."""

from __future__ import annotations

import base64
import json
import re
import uuid
from pathlib import Path
from typing import Any

from frugal import state

# UUID regex to strictly prevent path traversal on artifact IDs
UUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def get_base_dir(base_dir: Path | None = None) -> Path:
    return (base_dir or Path.cwd()) / ".frugal"


def ensure_directories(base_dir: Path | None = None) -> None:
    """Ensures .frugal/logs, .frugal/visual, .frugal/files directories exist."""
    root = get_base_dir(base_dir)
    (root / "logs").mkdir(parents=True, exist_ok=True)
    (root / "visual").mkdir(parents=True, exist_ok=True)
    (root / "files").mkdir(parents=True, exist_ok=True)


def is_valid_artifact_id(artifact_id: str) -> bool:
    """Validates that artifact_id matches UUID format and cannot traverse directories."""
    return bool(UUID_PATTERN.match(artifact_id.strip()))


def save_log(raw_output: str, base_dir: Path | None = None) -> tuple[str, str]:
    """
    Saves raw command output to .frugal/logs/run_<uuid>.log.
    Registers entry in state.db artifacts table.
    Returns (log_id, pointer_string).
    """
    ensure_directories(base_dir)
    root = get_base_dir(base_dir)
    log_id = str(uuid.uuid4())
    filename = f"run_{log_id}.log"
    file_path = root / "logs" / filename

    try:
        file_path.write_text(raw_output, encoding="utf-8", errors="replace")
    except OSError as e:
        return "", f"[FRUGAL ERROR] Failed to save log to disk: {e}"

    rel_path = f".frugal/logs/{filename}"

    # Register artifact in database
    db_path = root / "state.db"
    try:
        with state.get_connection(db_path=db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO artifacts (artifact_id, artifact_type, path, meta) VALUES (?, ?, ?, ?);",
                (log_id, "log", rel_path, None),
            )
    except Exception:
        # Lossless on disk is primary; DB failure should not crash
        pass

    pointer = (
        f"[Raw output saved: {rel_path} |\n"
        f" Inspect with: frugal_get_log(log_id=\"{log_id}\")]"
    )
    return log_id, pointer


def save_visual(
    image_bytes: bytes,
    analysis_json: dict[str, Any],
    base_dir: Path | None = None,
    visual_id: str | None = None,
) -> tuple[str, str, str]:
    """
    Saves screenshot to .frugal/visual/ui_<uuid>.png
    Saves analysis JSON to .frugal/visual/ui_<uuid>.json
    Returns (visual_id, image_path, analysis_path)
    """
    ensure_directories(base_dir)
    root = get_base_dir(base_dir)
    vid = visual_id or str(uuid.uuid4())
    analysis_json["visual_id"] = vid

    img_filename = f"ui_{vid}.png"
    json_filename = f"ui_{vid}.json"

    img_path = root / "visual" / img_filename
    json_path = root / "visual" / json_filename

    try:
        img_path.write_bytes(image_bytes)
        json_path.write_text(
            json.dumps(analysis_json, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError as e:
        raise OSError(f"Failed to persist visual artifact: {e}") from e

    rel_img_path = f".frugal/visual/{img_filename}"
    rel_json_path = f".frugal/visual/{json_filename}"

    # Register in artifacts table
    db_path = root / "state.db"
    try:
        with state.get_connection(db_path=db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO artifacts (artifact_id, artifact_type, path, meta) VALUES (?, ?, ?, ?);",
                (vid, "visual", rel_img_path, rel_json_path),
            )
    except Exception:
        pass

    return vid, rel_img_path, rel_json_path


def save_file_snapshot(
    path: str,
    content: str,
    base_dir: Path | None = None,
) -> tuple[str, str]:
    """
    Saves file content to .frugal/files/snap_<uuid>.txt
    Returns (snapshot_id, pointer_string)
    """
    ensure_directories(base_dir)
    root = get_base_dir(base_dir)
    snap_id = str(uuid.uuid4())
    filename = f"snap_{snap_id}.txt"
    snap_path = root / "files" / filename

    try:
        snap_path.write_text(content, encoding="utf-8", errors="replace")
    except OSError as e:
        return "", f"[FRUGAL ERROR] Failed to save snapshot to disk: {e}"

    rel_snap_path = f".frugal/files/{filename}"

    # Register in artifacts table
    db_path = root / "state.db"
    try:
        with state.get_connection(db_path=db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO artifacts (artifact_id, artifact_type, path, meta) VALUES (?, ?, ?, ?);",
                (snap_id, "file", rel_snap_path, path),
            )
    except Exception:
        pass

    pointer = (
        f"[Snapshot saved: {rel_snap_path} | "
        f"Original: {path}]"
    )
    return snap_id, pointer


def get_log_slice(
    log_id: str,
    start_line: int = 1,
    end_line: int = 200,
    base_dir: Path | None = None,
) -> str:
    """
    Reads a slice of raw log from disk (1-indexed inclusive).
    Returns the requested lines.
    """
    if not is_valid_artifact_id(log_id):
        return f"[FRUGAL ERROR] Invalid log_id format: '{log_id}'"

    root = get_base_dir(base_dir)
    log_file = root / "logs" / f"run_{log_id}.log"

    if not log_file.exists():
        return f"[FRUGAL ERROR] Log artifact not found: run_{log_id}.log"

    try:
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as e:
        return f"[FRUGAL ERROR] Failed to read log file: {e}"

    total_lines = len(lines)
    if total_lines == 0:
        return "[FRUGAL] Log file is empty."

    start = max(1, start_line)
    end = min(total_lines, max(start, end_line))

    # Convert 1-indexed to 0-indexed slice
    selected_lines = lines[start - 1 : end]
    content = "\n".join(selected_lines)

    header = f"[LOG SLICE: lines {start}-{end} of {total_lines} for {log_id}]\n"
    return header + content


def get_visual(
    visual_id: str,
    raw: bool = False,
    base_dir: Path | None = None,
) -> str:
    """
    Retrieves visual analysis or raw screenshot.
    If raw=False: return the JSON analysis.
    If raw=True: return base64-encoded original image.
    """
    if not is_valid_artifact_id(visual_id):
        return f"[FRUGAL ERROR] Invalid visual_id format: '{visual_id}'"

    root = get_base_dir(base_dir)

    if raw:
        img_file = root / "visual" / f"ui_{visual_id}.png"
        if not img_file.exists():
            return f"[FRUGAL ERROR] Screenshot image not found for visual_id: {visual_id}"
        try:
            raw_bytes = img_file.read_bytes()
            b64_str = base64.b64encode(raw_bytes).decode("ascii")
            return b64_str
        except OSError as e:
            return f"[FRUGAL ERROR] Failed to read screenshot: {e}"
    else:
        json_file = root / "visual" / f"ui_{visual_id}.json"
        if not json_file.exists():
            return f"[FRUGAL ERROR] Visual analysis JSON not found for visual_id: {visual_id}"
        try:
            return json_file.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            return f"[FRUGAL ERROR] Failed to read analysis JSON: {e}"
