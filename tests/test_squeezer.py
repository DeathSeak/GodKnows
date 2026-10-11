import pytest
from frugal import squeezer


def test_strip_ansi():
    ansi_text = "\x1b[31mError:\x1b[0m test failed\r\nNext line\rAnother line"
    cleaned = squeezer.strip_ansi(ansi_text)
    assert "\x1b[" not in cleaned
    assert "\r" not in cleaned
    assert "Error: test failed" in cleaned
    assert "Next line" in cleaned


def test_is_verbose_command():
    assert squeezer.is_verbose_command("npm install") is True
    assert squeezer.is_verbose_command("pnpm install --frozen-lockfile") is True
    assert squeezer.is_verbose_command("pip install -r requirements.txt") is True
    assert squeezer.is_verbose_command("cargo build --release") is True
    assert squeezer.is_verbose_command("pytest tests/") is False
    assert squeezer.is_verbose_command("python script.py") is False


def test_nested_traceback_detection():
    single_tb = """
Traceback (most recent call last):
  File "test.py", line 1, in <module>
    raise ValueError("bad")
ValueError: bad
"""
    assert squeezer.has_nested_traceback(single_tb) is False

    nested_tb = """
Traceback (most recent call last):
  File "test.py", line 2, in <module>
    raise KeyError("missing")
KeyError: missing

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "test.py", line 4, in <module>
    raise RuntimeError("crashed")
RuntimeError: crashed
"""
    assert squeezer.has_nested_traceback(nested_tb) is True


def test_multiple_errors_detection():
    one_error = "Error: database connection refused"
    assert squeezer.has_multiple_errors(one_error) is False

    multi_errors = """
Error: failed to connect to db
Exception: timeout exceeded on socket
FAILED: test_auth_login
"""
    assert squeezer.has_multiple_errors(multi_errors) is True


def test_squeeze_verbose_success():
    verbose_log = "\n".join([f"Downloading package-{i}..." for i in range(100)])
    result, needs_intel = squeezer.squeeze_output(
        command="pnpm install", exit_code=0, raw_output=verbose_log, log_id="test-log-1"
    )
    assert needs_intel is False
    assert "[FRUGAL SUMMARY]" in result
    assert "Status: SUCCESS" in result
    assert "frugal_get_log(log_id=\"test-log-1\")" in result
    assert "Downloading package-0..." in result
    assert "Downloading package-99..." in result


def test_squeeze_simple_failure():
    failing_log = (
        "pytest running...\n"
        + "\n".join([f"collecting test {i}..." for i in range(50)])
        + "\nFAILED tests/test_foo.py::test_bar - AssertionError: expected True but got False\n"
        + "1 failed, 49 passed in 0.5s\n"
    )
    result, needs_intel = squeezer.squeeze_output(
        command="pytest tests/", exit_code=1, raw_output=failing_log, log_id="fail-log-1"
    )
    assert "[FRUGAL SUMMARY]" in result
    assert "Status: FAILED" in result
    assert "AssertionError" in result
    assert "frugal_get_log(log_id=\"fail-log-1\")" in result


def test_squeeze_needs_intelligence_on_complex_failure():
    complex_failure = (
        "Traceback (most recent call last):\n"
        "  File 'a.py', line 1\n"
        "ValueError: root error\n"
        "During handling of the above exception, another exception occurred:\n"
        "Traceback (most recent call last):\n"
        "  File 'b.py', line 2\n"
        "RuntimeError: secondary error\n"
    )
    _, needs_intel = squeezer.squeeze_output(
        command="python run.py", exit_code=1, raw_output=complex_failure
    )
    assert needs_intel is True


def test_squeeze_edge_cases():
    # Binary output
    res, needs_intel = squeezer.squeeze_output("cat bin", 0, "some\x00binary\x00data")
    assert "[FRUGAL] Binary output suppressed." in res
    assert needs_intel is False

    # Empty output
    res_empty, needs_intel_empty = squeezer.squeeze_output("ls", 0, "   \n\r  ")
    assert "[FRUGAL] Command produced no output." in res_empty
    assert needs_intel_empty is False

    # Single line output
    res_single, needs_intel_single = squeezer.squeeze_output("echo hi", 0, "hi")
    assert res_single == "hi"
    assert needs_intel_single is False
