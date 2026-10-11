from pathlib import Path
from frugal import breaker, state


def test_breaker_triggers_on_three_failures(tmp_path: Path):
    db_file = tmp_path / "test_breaker.db"
    state.initialize_db(db_path=db_file)
    sess_id = "test-session-breaker"
    cmd = "pytest tests/test_failing.py"

    # Run 1: first failure
    breaker.record_command_run(cmd, exit_code=1, session_id=sess_id, db_path=db_file)
    alert = breaker.check_command(cmd, session_id=sess_id, db_path=db_file)
    assert alert is None

    # Run 2: second failure
    breaker.record_command_run(cmd, exit_code=1, session_id=sess_id, db_path=db_file)
    alert = breaker.check_command(cmd, session_id=sess_id, db_path=db_file)
    assert alert is None

    # Run 3: third failure
    breaker.record_command_run(cmd, exit_code=1, session_id=sess_id, db_path=db_file)
    alert = breaker.check_command(cmd, session_id=sess_id, db_path=db_file)

    # Must trigger circuit breaker
    assert alert is not None
    assert "[FRUGAL CIRCUIT BREAKER TRIGGERED]" in alert
    assert "Repeated failures: 3" in alert
    assert "Do NOT rerun the exact same command without changing code" in alert


def test_breaker_resets_on_success(tmp_path: Path):
    db_file = tmp_path / "test_breaker.db"
    state.initialize_db(db_path=db_file)
    sess_id = "test-session-reset"
    cmd = "npm run test"

    # Record 3 failures
    for _ in range(3):
        breaker.record_command_run(cmd, exit_code=1, session_id=sess_id, db_path=db_file)

    assert breaker.check_command(cmd, session_id=sess_id, db_path=db_file) is not None

    # Now record 1 success
    breaker.record_command_run(cmd, exit_code=0, session_id=sess_id, db_path=db_file)

    # Next check should NOT trigger because the most recent run was exit_code == 0
    assert breaker.check_command(cmd, session_id=sess_id, db_path=db_file) is None


def test_breaker_different_commands_isolated(tmp_path: Path):
    db_file = tmp_path / "test_breaker.db"
    state.initialize_db(db_path=db_file)
    sess_id = "test-session-isolated"

    cmd1 = "python test_a.py"
    cmd2 = "python test_b.py"

    # cmd1 fails 3 times
    for _ in range(3):
        breaker.record_command_run(cmd1, exit_code=1, session_id=sess_id, db_path=db_file)

    assert breaker.check_command(cmd1, session_id=sess_id, db_path=db_file) is not None
    assert breaker.check_command(cmd2, session_id=sess_id, db_path=db_file) is None
