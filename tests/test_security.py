import sys
from pathlib import Path
import pytest
from frugal import security


def test_allowed_commands():
    res = security.check_command("python -c \"print('hello')\"")
    assert res.allowed is True
    assert res.reason == ""

    res_git = security.check_command("git status")
    assert res_git.allowed is True


def test_blocked_commands():
    # Executable not in allowlist
    res = security.check_command("powershell Get-Process")
    assert res.allowed is False
    assert "not in allowlist" in res.reason


def test_denied_patterns():
    # Matches rm -rf
    res = security.check_command("python -c 'print()' rm -rf /")
    assert res.allowed is False
    assert "denied pattern" in res.reason

    # Matches sudo
    res_sudo = security.check_command("sudo git status")
    assert res_sudo.allowed is False


def test_empty_and_malformed_commands():
    res_empty = security.check_command("   ")
    assert res_empty.allowed is False

    res_malformed = security.check_command('python -c "unclosed string')
    assert res_malformed.allowed is False
    assert "Malformed" in res_malformed.reason


def test_run_command_safe_execution():
    cmd = f'python -c "import sys; sys.stdout.write(\'frugal_ok\'); sys.exit(0)"'
    result = security.run_command(cmd)
    assert result.returncode == 0
    assert result.stdout == "frugal_ok"


def test_run_command_blocked():
    result = security.run_command("curl https://example.com")
    assert result.returncode == -3
    assert "FRUGAL SECURITY BLOCKED" in result.stderr


def test_run_command_timeout():
    # Run a short timeout command
    cmd = 'python -c "import time; time.sleep(2)"'
    result = security.run_command(cmd, timeout=1)
    assert result.returncode == -1
    assert "TIMED OUT" in result.stderr.upper()


def test_validate_path_within_root(tmp_path: Path):
    safe_file = tmp_path / "subdir" / "file.txt"
    safe_file.parent.mkdir(parents=True)
    safe_file.write_text("ok")

    validated = security.validate_path(safe_file, project_root=tmp_path)
    assert validated.resolve() == safe_file.resolve()


def test_validate_path_traversal(tmp_path: Path):
    sub = tmp_path / "workspace"
    sub.mkdir()
    traversal_path = "../outside.txt"

    with pytest.raises(security.SecurityError):
        security.validate_path(traversal_path, project_root=sub)


def test_is_binary_content():
    assert security.is_binary_content(b"hello world") is False
    assert security.is_binary_content(b"hello\x00world") is True
