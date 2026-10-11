import sqlite3
import pytest
from pathlib import Path
from frugal import state


def test_session_id_caching():
    state.reset_session_id()
    s1 = state.get_session_id()
    s2 = state.get_session_id()
    assert s1 == s2
    assert len(s1) == 36  # standard UUID string length


def test_initialize_db(tmp_path: Path):
    db_file = tmp_path / "test_state.db"
    state.initialize_db(db_path=db_file)

    assert db_file.exists()

    with state.get_connection(db_path=db_file) as conn:
        # Verify WAL mode
        cur = conn.execute("PRAGMA journal_mode;")
        row = cur.fetchone()
        assert row[0].lower() == "wal"

        # Verify tables exist
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
        )
        tables = {r["name"] for r in cur.fetchall()}
        expected_tables = {"sessions", "file_reads", "command_runs", "artifacts", "metrics"}
        assert expected_tables.issubset(tables)

        # Verify session was registered
        cur = conn.execute("SELECT session_id FROM sessions;")
        sess_rows = cur.fetchall()
        assert len(sess_rows) >= 1
        assert sess_rows[0]["session_id"] == state.get_session_id()

        # Verify indexes exist
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' ORDER BY name;"
        )
        indexes = {r["name"] for r in cur.fetchall()}
        expected_indexes = {
            "idx_file_reads_path",
            "idx_file_reads_session",
            "idx_command_runs_hash",
            "idx_command_runs_session",
            "idx_metrics_session",
        }
        assert expected_indexes.issubset(indexes)


def test_artifacts_type_constraint(tmp_path: Path):
    db_file = tmp_path / "test_state.db"
    state.initialize_db(db_path=db_file)

    with state.get_connection(db_path=db_file) as conn:
        # Valid type
        conn.execute(
            "INSERT INTO artifacts (artifact_id, artifact_type, path) VALUES (?, ?, ?);",
            ("art_1", "log", "/path/to/log"),
        )
        # Invalid type should violate CHECK constraint
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO artifacts (artifact_id, artifact_type, path) VALUES (?, ?, ?);",
                ("art_2", "invalid_type", "/path/to/something"),
            )
