"""Security guardrails, command validation, and path containment."""

from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List

from frugal import config


class SecurityError(Exception):
    """Raised when a security boundary violation is detected."""
    pass


@dataclass(frozen=True)
class SecurityResult:
    allowed: bool
    reason: str = ""


@dataclass(frozen=True)
class CommandResult:
    stdout: str
    stderr: str
    returncode: int


def get_allowed_commands() -> list[str]:
    cfg = config.get_config()
    return list(cfg.security.allowed_commands)


def get_denied_patterns() -> list[str]:
    cfg = config.get_config()
    return list(cfg.security.denied_patterns)


def normalize_binary_name(executable_token: str) -> str:
    """
    Normalizes executable name by stripping directory paths and Windows extensions.
    e.g. 'C:\\Python\\python.exe' -> 'python', './node' -> 'node'
    """
    token = executable_token.strip().strip("\"'")
    name = Path(token).name.lower()
    for ext in (".exe", ".bat", ".cmd", ".sh"):
        if name.endswith(ext):
            name = name[: -len(ext)]
            break
    return name


def parse_command(command: str) -> list[str]:
    """
    Splits a command string into tokens, stripping enclosing quotes while
    preserving Windows backslashes in paths.
    """
    cmd = command.strip()
    if os.name == "nt":
        # On Windows, backslashes are path separators, not escape characters (except before quotes)
        import re
        cmd = re.sub(r'\\(?!["\'])', r'\\\\', cmd)
    return shlex.split(cmd, posix=True)


def check_command(command: str) -> SecurityResult:
    """
    Validates a command against allowlist and denylist.
    Returns SecurityResult(allowed: bool, reason: str).
    """
    if not command or not command.strip():
        return SecurityResult(allowed=False, reason="Empty command")

    cmd_str = command.strip()

    # 1. Check against denied patterns
    denied_patterns = get_denied_patterns()
    for pattern in denied_patterns:
        if pattern.lower() in cmd_str.lower():
            return SecurityResult(
                allowed=False,
                reason=f"Command matches denied pattern: '{pattern}'",
            )

    # 2. Parse command with shlex
    try:
        tokens = parse_command(cmd_str)
    except ValueError as e:
        return SecurityResult(allowed=False, reason=f"Malformed command quoting: {e}")

    if not tokens:
        return SecurityResult(allowed=False, reason="Empty command tokens")

    # 3. Check executable against allowlist
    executable = normalize_binary_name(tokens[0])
    allowed_commands = [c.lower() for c in get_allowed_commands()]

    if executable not in allowed_commands:
        return SecurityResult(
            allowed=False,
            reason=f"Command '{executable}' is not in allowlist: {allowed_commands}",
        )

    return SecurityResult(allowed=True, reason="")


def run_command(
    command: str,
    timeout: int = 120,
    cwd: Path | None = None,
) -> CommandResult:
    """
    Executes a validated command safely using shell=False.
    """
    sec = check_command(command)
    if not sec.allowed:
        return CommandResult(
            stdout="",
            stderr=f"[FRUGAL SECURITY BLOCKED] {sec.reason}",
            returncode=-3,
        )

    try:
        cmd_tokens = parse_command(command.strip())
    except ValueError as e:
        return CommandResult(
            stdout="",
            stderr=f"[FRUGAL SECURITY BLOCKED] Malformed command quoting: {e}",
            returncode=-3,
        )

    exec_cwd = str(cwd) if cwd else None

    try:
        proc = subprocess.run(
            cmd_tokens,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=exec_cwd,
        )
        return CommandResult(
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
            returncode=proc.returncode,
        )
    except subprocess.TimeoutExpired:
        return CommandResult(
            stdout="",
            stderr=f"[FRUGAL TIMEOUT] Command timed out after {timeout} seconds",
            returncode=-1,
        )
    except FileNotFoundError:
        return CommandResult(
            stdout="",
            stderr=f"[FRUGAL NOT FOUND] Executable not found: '{cmd_tokens[0]}'",
            returncode=-2,
        )
    except Exception as e:
        return CommandResult(
            stdout="",
            stderr=f"[FRUGAL ERROR] Execution failed: {e}",
            returncode=-4,
        )


def validate_path(path: str | Path, project_root: Path | None = None) -> Path:
    """
    Validates and resolves a file path against the project root.
    Returns resolved absolute Path.
    Raises SecurityError if path traversal is detected.
    """
    root = (project_root or Path.cwd()).resolve()
    target = Path(path)

    if not target.is_absolute():
        target = root / target

    resolved = target.resolve()

    try:
        if not resolved.is_relative_to(root):
            raise SecurityError(
                f"Path traversal detected: '{path}' resolves outside root '{root}'"
            )
    except AttributeError:
        # Python < 3.9 compatibility check (fallback)
        try:
            resolved.relative_to(root)
        except ValueError:
            raise SecurityError(
                f"Path traversal detected: '{path}' resolves outside root '{root}'"
            )

    return resolved


def is_binary_content(content: bytes) -> bool:
    """Detects whether bytes contain null characters indicating binary data."""
    return b"\x00" in content
