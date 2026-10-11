import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from frugal import intelligence


def test_clean_json_response_plain():
    raw = '{"summary": "Test summary", "confidence": "high"}'
    parsed = intelligence.clean_json_response(raw)
    assert parsed["summary"] == "Test summary"
    assert parsed["confidence"] == "high"


def test_clean_json_response_markdown_fence():
    raw = '```json\n{"summary": "From markdown fence", "affected_files": ["foo.py"]}\n```'
    parsed = intelligence.clean_json_response(raw)
    assert parsed["summary"] == "From markdown fence"
    assert parsed["affected_files"] == ["foo.py"]


def test_clean_json_response_surrounding_text():
    raw = 'Here is the analysis:\n{"summary": "Embedded JSON", "root_cause": "Crash"}\nHope this helps!'
    parsed = intelligence.clean_json_response(raw)
    assert parsed["summary"] == "Embedded JSON"
    assert parsed["root_cause"] == "Crash"


def test_clean_json_response_unparseable():
    raw = "This is not json at all."
    parsed = intelligence.clean_json_response(raw)
    assert "Output analyzed" in parsed["summary"]
    assert parsed["raw_response"] == "This is not json at all."
    assert parsed["confidence"] == "low"


def test_call_gemma4_missing_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    with pytest.raises(intelligence.GemmaAPIError) as exc_info:
        intelligence.call_gemma4("Hello")
    assert "not set in environment" in str(exc_info.value)


@patch("google.generativeai.GenerativeModel")
def test_intelligent_squeeze_success(mock_model_class, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-test-key")

    mock_instance = MagicMock()
    mock_model_class.return_value = mock_instance
    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "summary": "Database connection refused",
        "root_cause": "PostgreSQL service is down",
        "error_signature": "ConnectionRefusedError: [Errno 111]",
        "affected_files": ["src/db.py"],
        "suggested_actions": ["Start postgres service", "Check connection URL"],
        "confidence": "high",
    })
    mock_instance.generate_content.return_value = mock_response

    output = intelligence.intelligent_squeeze(
        raw_output="ConnectionRefusedError: [Errno 111] Connection refused",
        command="python app.py",
        exit_code=1,
        log_id="test-log-uuid",
    )

    data = json.loads(output)
    assert data["summary"] == "Database connection refused"
    assert data["root_cause"] == "PostgreSQL service is down"
    assert data["log_id"] == "test-log-uuid"


def test_intelligent_squeeze_fallback_on_api_error(monkeypatch):
    # Ensure no API key triggers fallback to Tier 1
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    raw_output = "Traceback (most recent call last):\n  File 'a.py'\nZeroDivisionError: division by zero"
    output = intelligence.intelligent_squeeze(
        raw_output=raw_output,
        command="python a.py",
        exit_code=1,
        log_id="log-fallback-1",
    )

    # Should contain Tier 1 summary and the fallback note
    assert "[FRUGAL SUMMARY]" in output
    assert "ZeroDivisionError" in output
    assert "[FRUGAL NOTE] Gemma 4 unavailable. Tier 1 compression used." in output
    assert "frugal_get_log(log_id=\"log-fallback-1\")" in output


def test_analyze_screenshot_fallback_on_missing_file(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-test-key")

    result = intelligence.analyze_screenshot(
        screenshot_path="non_existent_screenshot.png",
        task_hint="Find the broken button",
        visual_id="vis-fallback-1",
    )

    data = json.loads(result)
    assert "[FRUGAL NOTE] Visual analysis unavailable" in data["summary"]
    assert data["visual_id"] == "vis-fallback-1"
    assert "frugal_get_visual" in data["suggested_next_steps"][0]
