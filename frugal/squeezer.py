"""Tier 1: Deterministic compression using regex and heuristics."""

from __future__ import annotations

import re
from typing import List

from frugal import config

# Regex matching ANSI escape sequences
ANSI_REGEX = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")

# Verbose package manager and build commands that produce repetitive logs on success
VERBOSE_COMMAND_PATTERNS = [
    "npm install",
    "npm i",
    "pnpm install",
    "pnpm i",
    "pip install",
    "poetry install",
    "cargo build",
    "yarn install",
    "yarn add",
]


def strip_ansi(text: str) -> str:
    """Removes ANSI escape codes, terminal formatting, and carriage returns."""
    if not text:
        return ""
    cleaned = ANSI_REGEX.sub("", text)
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    return cleaned


def is_verbose_command(command: str) -> bool:
    """Returns True if the command is a known verbose runner."""
    normalized = " ".join(command.strip().lower().split())
    for pattern in VERBOSE_COMMAND_PATTERNS:
        if normalized.startswith(pattern):
            return True
    return False


def has_nested_traceback(text: str) -> bool:
    """
    Returns True if text contains multiple 'Traceback' occurrences or
    chained exceptions (e.g., 'During handling of the above exception').
    """
    traceback_count = text.count("Traceback (most recent call last):")
    if traceback_count > 1:
        return True
    if "During handling of the above exception" in text:
        return True
    if "The above exception was the direct cause" in text:
        return True
    return False


def has_multiple_errors(text: str) -> bool:
    """Returns True if text contains 3+ distinct error markers."""
    error_markers = re.findall(
        r"(?i)(?:error|exception|failed|failure):[^\n]+", text
    )
    # Deduplicate similar markers to check for distinct errors
    unique_errors = set(m.strip().lower() for m in error_markers)
    return len(unique_errors) >= 3


def is_unclear_failure(text: str) -> bool:
    """Returns True if text is a failure but contains no obvious error keywords."""
    keywords = ["error", "fatal", "exception", "traceback", "failed", "failure"]
    text_lower = text.lower()
    return not any(kw in text_lower for kw in keywords)


def extract_failure_block(
    text: str,
    head_lines: int = 10,
    tail_lines: int = 20,
    grep_patterns: List[str] | None = None,
) -> tuple[str, int, int]:
    """
    For failing commands, extracts the high-signal failure block:
    - Retains the first head_lines.
    - Retains the last tail_lines.
    - Scans the middle lines for keywords (error, fatal, exception, etc.).
    - Filters out noisy framework/virtualenv stack frames (e.g., site-packages/, node_modules/).
    
    Returns (extracted_text, retained_line_count, total_line_count).
    """
    lines = text.split("\n")
    # 1. Strip test runner startup noise (pytest/jest/vitest session startup headers)
    if "test session starts" in text and ("FAILURES" in text or "FAILED" in text):
        failures_idx = next((i for i, l in enumerate(lines) if "FAILURES" in l or "FAILED" in l), 0)
        if failures_idx > 0:
            lines = lines[failures_idx:]

    total_count = len(lines)

    # 2. Collapse intermediate boilerplate in chained multi-tier tracebacks
    if has_nested_traceback(text):
        blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
        if len(blocks) >= 3:
            first_block = blocks[0]
            last_block = blocks[-1]
            omitted_count = len(blocks) - 2
            collapsed = f"{first_block}\n\n... [{omitted_count} intermediate chained exceptions omitted] ...\n\n{last_block}"
            collapsed_lines = collapsed.split("\n")
            return collapsed, len(collapsed_lines), total_count

    if total_count <= (head_lines + tail_lines):
        return "\n".join(lines), total_count, total_count

    patterns = grep_patterns or ["error", "fatal", "exception", "traceback", "failed"]
    pattern_regex = re.compile(r"(?i)(" + "|".join(patterns) + ")")

    head = lines[:head_lines]
    tail = lines[-tail_lines:]
    middle = lines[head_lines:-tail_lines]


    matched_middle: List[str] = []
    noise_count = 0

    for line in middle:
        # Filter noisy stack frames if line doesn't have explicit error keyword
        if ("site-packages/" in line or "node_modules/" in line or ".cache/" in line) and not pattern_regex.search(line):
            noise_count += 1
            continue

        if pattern_regex.search(line):
            matched_middle.append(line)

    retained: List[str] = []
    retained.extend(head)

    if middle:
        retained.append(f"... [{len(middle)} lines omitted | {len(matched_middle)} high-signal lines extracted] ...")
        retained.extend(matched_middle)

    retained.extend(tail)
    retained_text = "\n".join(retained)
    return retained_text, len(retained), total_count


def squeeze_output(
    command: str,
    exit_code: int,
    raw_output: str,
    log_id: str = "",
) -> tuple[str, bool]:
    """
    Tier 1 deterministic compression.
    Returns (compressed_text, needs_intelligence).
    """
    # Edge case 1: Binary output
    if "\x00" in raw_output:
        return "[FRUGAL] Binary output suppressed.", False

    # Edge case 2: Empty output
    cleaned = strip_ansi(raw_output).strip()
    if not cleaned:
        return "[FRUGAL] Command produced no output.", False

    lines = cleaned.split("\n")
    total_lines = len(lines)

    # Edge case 3: Single line output
    if total_lines == 1:
        return cleaned, False

    cfg = config.get_config()
    tier2_threshold = cfg.compression.tier2_threshold_lines

    escape_hatch = (
        f"[ESCAPE HATCH]\nfrugal_get_log(log_id=\"{log_id}\")"
        if log_id
        else "[ESCAPE HATCH]\nInspect raw log via frugal_get_log(log_id)"
    )

    # Case A: Success (exit_code == 0)
    if exit_code == 0:
        if is_verbose_command(command) or total_lines > 50:
            # Compress successful verbose output
            summary_header = (
                f"[FRUGAL SUMMARY]\n"
                f"Command: {command}\n"
                f"Exit code: 0\n"
                f"Status: SUCCESS\n"
                f"Compressed output: 3 lines retained from {total_lines} lines.\n\n"
                f"[OUTPUT]\n"
                f"{lines[0]}\n"
                f"... [{total_lines - 2} lines omitted] ...\n"
                f"{lines[-1]}\n\n"
                f"{escape_hatch}"
            )
            return summary_header, False
        else:
            # Short successful commands remain concise as-is
            return cleaned, False

    # Case B: Failure (exit_code != 0)
    failure_block, retained_lines, total_lines = extract_failure_block(
        cleaned,
        head_lines=cfg.compression.head_lines,
        tail_lines=cfg.compression.tail_lines,
        grep_patterns=list(cfg.compression.grep_patterns),
    )

    # Decision logic for needs_intelligence
    needs_intel = (
        retained_lines > tier2_threshold
        or has_nested_traceback(cleaned)
        or has_multiple_errors(cleaned)
        or is_unclear_failure(cleaned)
    )

    # Threshold Check: If no lines were omitted/compressed (retained_lines == total_lines),
    # use a slim inline summary rather than an expansive 9-line template to eliminate negative token ROI:
    if retained_lines == total_lines:
        hatch_str = f"\n\n[ESCAPE HATCH] frugal_get_log(log_id=\"{log_id}\")" if log_id else ""
        summary_text = (
            f"[FRUGAL SUMMARY] Status: FAILED | Exit {exit_code} ({total_lines} lines retained)\n"
            f"{failure_block}"
            f"{hatch_str}"
        )
    else:
        summary_text = (
            f"[FRUGAL SUMMARY]\n"
            f"Command: {command}\n"
            f"Exit code: {exit_code}\n"
            f"Status: FAILED\n"
            f"Compressed output: {retained_lines} lines retained from {total_lines} lines.\n\n"
            f"[FAILURE SIGNATURE]\n"
            f"{failure_block}\n\n"
            f"{escape_hatch}"
        )

    return summary_text, needs_intel

