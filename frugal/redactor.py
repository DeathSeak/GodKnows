"""Secret masking for terminal outputs and file contents."""

from __future__ import annotations

import re
from typing import List, Tuple

from frugal import config

SECRET_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (
        re.compile(r"(?i)(api[_-]?key|apikey)\s*[=:]\s*\S+", re.MULTILINE),
        r"\1=[REDACTED]",
    ),
    (
        re.compile(r"(?i)(secret|token|password|passwd)\s*[=:]\s*\S+", re.MULTILINE),
        r"\1=[REDACTED]",
    ),
    (
        re.compile(r"(?i)(database_url|db_url|connection_string)\s*[=:]\s*\S+", re.MULTILINE),
        r"\1=[REDACTED]",
    ),
    (
        re.compile(r"(?i)(aws_access_key_id|aws_secret_access_key)\s*[=:]\s*\S+", re.MULTILINE),
        r"\1=[REDACTED]",
    ),
    (
        re.compile(r"sk-[a-zA-Z0-9]{20,}", re.MULTILINE),
        "[REDACTED_OPENAI_KEY]",
    ),
    (
        re.compile(r"ghp_[a-zA-Z0-9]{36}", re.MULTILINE),
        "[REDACTED_GITHUB_TOKEN]",
    ),
    (
        re.compile(r"gho_[a-zA-Z0-9]{36}", re.MULTILINE),
        "[REDACTED_GITHUB_TOKEN]",
    ),
    (
        re.compile(r"xoxb-[a-zA-Z0-9\-]+", re.MULTILINE),
        "[REDACTED_SLACK_TOKEN]",
    ),
    (
        re.compile(r"(?i)bearer\s+[a-zA-Z0-9\-._~+/]+=*", re.MULTILINE),
        "Bearer [REDACTED]",
    ),
]


def redact(text: str | None) -> str:
    """
    Applies all SECRET_PATTERNS to the input text.
    Returns redacted text.
    Must be called BEFORE storage.save_log() and BEFORE any compression.
    """
    if text is None:
        return ""

    if not text:
        return ""

    # Check configuration
    try:
        cfg = config.get_config()
        if not cfg.privacy.redact_secrets:
            return text
    except Exception:
        pass

    redacted = text
    for pattern, replacement in SECRET_PATTERNS:
        redacted = pattern.sub(replacement, redacted)

    return redacted
