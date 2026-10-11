from pathlib import Path
from frugal import deduper, state


def test_deduper_normal_read_and_dedupe(tmp_path: Path):
    db_file = tmp_path / "test_dedupe.db"
    state.initialize_db(db_path=db_file)
    sess_id = "test-sess-dedupe"

    test_file = tmp_path / "source.py"
    test_content = "def add(a, b):\n    return a + b\n"
    test_file.write_text(test_content)

    # 1. First read
    content1, was_dedup1 = deduper.check_and_read(
        str(test_file), session_id=sess_id, db_path=db_file, project_root=tmp_path
    )
    assert was_dedup1 is False
    assert content1 == test_content

    # 2. Second read (unchanged content) -> should dedupe
    content2, was_dedup2 = deduper.check_and_read(
        str(test_file), session_id=sess_id, db_path=db_file, project_root=tmp_path
    )
    assert was_dedup2 is True
    assert "[FRUGAL DEDUPE]" in content2
    assert "Status: unchanged since previous read" in content2
    assert "Use force=True to reload." in content2

    # 3. Third read with force=True -> should return full content
    content3, was_dedup3 = deduper.check_and_read(
        str(test_file), force=True, session_id=sess_id, db_path=db_file, project_root=tmp_path
    )
    assert was_dedup3 is False
    assert content3 == test_content


def test_deduper_file_modified(tmp_path: Path):
    db_file = tmp_path / "test_dedupe.db"
    state.initialize_db(db_path=db_file)
    sess_id = "test-sess-mod"

    test_file = tmp_path / "app.py"
    test_file.write_text("v1")

    # Read v1
    c1, d1 = deduper.check_and_read(
        str(test_file), session_id=sess_id, db_path=db_file, project_root=tmp_path
    )
    assert d1 is False
    assert c1 == "v1"

    # Modify file to v2
    test_file.write_text("v2")

    # Read v2 -> should NOT dedupe because hash changed
    c2, d2 = deduper.check_and_read(
        str(test_file), session_id=sess_id, db_path=db_file, project_root=tmp_path
    )
    assert d2 is False
    assert c2 == "v2"


def test_deduper_ignored_lockfile(tmp_path: Path):
    db_file = tmp_path / "test_dedupe.db"
    state.initialize_db(db_path=db_file)
    sess_id = "test-sess-ignore"

    lockfile = tmp_path / "package-lock.json"
    lockfile.write_text('{"name": "test", "lockfileVersion": 3}')

    # Read 1
    c1, d1 = deduper.check_and_read(
        str(lockfile), session_id=sess_id, db_path=db_file, project_root=tmp_path
    )
    assert d1 is False

    # Read 2 -> should still not dedupe because package-lock.json is in ignore list
    c2, d2 = deduper.check_and_read(
        str(lockfile), session_id=sess_id, db_path=db_file, project_root=tmp_path
    )
    assert d2 is False
    assert c2 == c1


def test_deduper_edge_cases(tmp_path: Path):
    db_file = tmp_path / "test_dedupe.db"
    state.initialize_db(db_path=db_file)
    sess_id = "test-sess-edge"

    # Missing file
    c_missing, d_missing = deduper.check_and_read(
        str(tmp_path / "missing.txt"), session_id=sess_id, db_path=db_file, project_root=tmp_path
    )
    assert "File not found" in c_missing
    assert d_missing is False

    # Binary file
    bin_file = tmp_path / "binary.bin"
    bin_file.write_bytes(b"hello\x00world")
    c_bin, d_bin = deduper.check_and_read(
        str(bin_file), session_id=sess_id, db_path=db_file, project_root=tmp_path
    )
    assert "Binary file detected" in c_bin
    assert d_bin is False

    # Empty file
    empty_file = tmp_path / "empty.txt"
    empty_file.write_text("")
    c_empty, d_empty = deduper.check_and_read(
        str(empty_file), session_id=sess_id, db_path=db_file, project_root=tmp_path
    )
    assert "File is empty" in c_empty
    assert d_empty is False
