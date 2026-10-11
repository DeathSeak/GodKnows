import base64
import json
from pathlib import Path
import pytest
from frugal import state, storage


@pytest.fixture
def test_env(tmp_path: Path):
    db_file = tmp_path / ".frugal" / "state.db"
    state.initialize_db(db_path=db_file)
    storage.ensure_directories(base_dir=tmp_path)
    return tmp_path


def test_ensure_directories(tmp_path: Path):
    storage.ensure_directories(base_dir=tmp_path)
    base = tmp_path / ".frugal"
    assert (base / "logs").is_dir()
    assert (base / "visual").is_dir()
    assert (base / "files").is_dir()


def test_save_and_get_log_slice(test_env: Path):
    raw_lines = [f"Line {i}: test output" for i in range(1, 51)]
    raw_text = "\n".join(raw_lines)

    log_id, pointer = storage.save_log(raw_text, base_dir=test_env)
    assert log_id
    assert f"run_{log_id}.log" in pointer
    assert f"frugal_get_log(log_id=\"{log_id}\")" in pointer

    # Verify database registration
    db_path = test_env / ".frugal" / "state.db"
    with state.get_connection(db_path=db_path) as conn:
        cur = conn.execute("SELECT * FROM artifacts WHERE artifact_id = ?;", (log_id,))
        row = cur.fetchone()
        assert row is not None
        assert row["artifact_type"] == "log"

    # Slice lines 5 to 10
    slice_output = storage.get_log_slice(log_id, start_line=5, end_line=10, base_dir=test_env)
    assert "Line 5: test output" in slice_output
    assert "Line 10: test output" in slice_output
    assert "Line 4: test output" not in slice_output
    assert "Line 11: test output" not in slice_output


def test_get_log_slice_edge_cases(test_env: Path):
    # Invalid log_id (path traversal attempt)
    bad_id = "../evil"
    res = storage.get_log_slice(bad_id, base_dir=test_env)
    assert "[FRUGAL ERROR] Invalid log_id format" in res

    # Missing log_id
    missing_id = "00000000-0000-0000-0000-000000000000"
    res = storage.get_log_slice(missing_id, base_dir=test_env)
    assert "[FRUGAL ERROR] Log artifact not found" in res


def test_save_and_get_visual(test_env: Path):
    sample_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    sample_analysis = {
        "summary": "Sample UI Analysis",
        "issues": [],
        "confidence": "high",
    }

    visual_id, img_path, json_path = storage.save_visual(
        sample_png, sample_analysis, base_dir=test_env
    )
    assert visual_id
    assert img_path.endswith(".png")
    assert json_path.endswith(".json")

    # Get JSON analysis (raw=False)
    json_result = storage.get_visual(visual_id, raw=False, base_dir=test_env)
    parsed = json.loads(json_result)
    assert parsed["summary"] == "Sample UI Analysis"

    # Get raw base64 (raw=True)
    raw_b64 = storage.get_visual(visual_id, raw=True, base_dir=test_env)
    decoded = base64.b64decode(raw_b64)
    assert decoded == sample_png


def test_save_file_snapshot(test_env: Path):
    code_content = "def hello():\n    return 'world'\n"
    snap_id, pointer = storage.save_file_snapshot(
        "src/main.py", code_content, base_dir=test_env
    )
    assert snap_id
    assert "Snapshot saved:" in pointer
    assert "Original: src/main.py" in pointer

    snap_file = test_env / ".frugal" / "files" / f"snap_{snap_id}.txt"
    assert snap_file.exists()
    assert snap_file.read_text(encoding="utf-8") == code_content
