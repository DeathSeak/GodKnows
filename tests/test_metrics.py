from pathlib import Path
from frugal import metrics, state


def test_metrics_empty_session(tmp_path: Path):
    db_file = tmp_path / "test_metrics.db"
    state.initialize_db(db_path=db_file)

    stats = metrics.get_session_stats(session_id="empty-sess", db_path=db_file)
    assert stats["bash_calls"] == 0
    assert stats["file_reads"] == 0
    assert stats["baseline_tokens"] == 0
    assert stats["saved_tokens"] == 0
    assert stats["reduction_percent"] == 0.0
    assert stats["gemma_overhead_tokens"] == 0
    assert stats["net_tokens_saved"] == 0


def test_record_bash_and_read_events(tmp_path: Path):
    db_file = tmp_path / "test_metrics.db"
    state.initialize_db(db_path=db_file)
    sess_id = "test-session-telemetry"

    # Event 1: Tier 1 bash event (0 Gemma overhead)
    raw_log = "A" * 4000  # ~1000 tokens
    comp_log = "A" * 400  # ~100 tokens
    metrics.record_bash_event(
        session_id=sess_id,
        command="pytest",
        exit_code=0,
        raw_output=raw_log,
        compressed_output=comp_log,
        tier_used=1,
        gemma_prompt_tokens=0,
        gemma_completion_tokens=0,
        db_path=db_file,
    )

    # Event 2: Tier 2 bash event (Gemma overhead)
    raw_fail = "B" * 2000  # ~500 tokens
    comp_fail = "B" * 200  # ~50 tokens
    metrics.record_bash_event(
        session_id=sess_id,
        command="python app.py",
        exit_code=1,
        raw_output=raw_fail,
        compressed_output=comp_fail,
        tier_used=2,
        gemma_prompt_tokens=250,
        gemma_completion_tokens=40,
        db_path=db_file,
    )

    # Event 3: Deduplicated file read event
    raw_file = "C" * 1200  # ~300 tokens
    sentinel = "C" * 80    # ~20 tokens
    metrics.record_read_event(
        session_id=sess_id,
        path="src/main.py",
        was_deduplicated=True,
        raw_content=raw_file,
        compressed_content=sentinel,
        db_path=db_file,
    )

    stats = metrics.get_session_stats(session_id=sess_id, db_path=db_file)

    assert stats["bash_calls"] == 2
    assert stats["file_reads"] == 1
    assert stats["duplicate_reads_blocked"] == 1
    assert stats["tier1_zero_cost_calls"] == 2  # event 1 and event 3 are tier 1
    assert stats["tier2_tier3_calls"] == 1      # event 2 is tier 2

    # Verify gross savings
    assert stats["baseline_tokens"] > stats["frugal_tokens"]
    assert stats["saved_tokens"] > 0
    assert stats["reduction_percent"] > 80.0

    # Verify radical transparency overhead
    assert stats["gemma_prompt_tokens"] == 250
    assert stats["gemma_completion_tokens"] == 40
    assert stats["gemma_overhead_tokens"] == 290
    assert stats["net_tokens_saved"] == (stats["saved_tokens"] - 290)
    assert stats["net_tokens_saved"] > 0


def test_record_visual_event(tmp_path: Path):
    db_file = tmp_path / "test_metrics.db"
    state.initialize_db(db_path=db_file)
    sess_id = "test-session-visual"

    metrics.record_visual_event(
        session_id=sess_id,
        visual_id="test-vis-1",
        raw_tokens=5000,
        compressed_tokens=300,
        gemma_prompt_tokens=1500,
        gemma_completion_tokens=200,
        db_path=db_file,
    )

    stats = metrics.get_session_stats(session_id=sess_id, db_path=db_file)
    assert stats["visual_analyses"] == 1
    assert stats["baseline_tokens"] == 5000
    assert stats["frugal_tokens"] == 300
    assert stats["saved_tokens"] == 4700
    assert stats["gemma_overhead_tokens"] == 1700
    assert stats["net_tokens_saved"] == (4700 - 1700)
