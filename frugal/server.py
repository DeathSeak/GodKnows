"""FastMCP Server for Frugal — Orchestrating the 3-Tier Token Firewall."""

from __future__ import annotations

import json
import time
from pathlib import Path

from fastmcp import FastMCP

from frugal import (
    breaker,
    config,
    deduper,
    intelligence,
    metrics,
    redactor,
    security,
    squeezer,
    state,
    storage,
    token_counter,
)

mcp = FastMCP("Frugal")


def initialize() -> None:
    """Called to initialize runtime environment: state DB, storage directories, and config."""
    try:
        config.get_config()
        state.initialize_db()
        storage.ensure_directories()
    except Exception:
        pass


# Ensure initialized on module load
initialize()


@mcp.tool()
def frugal_bash(command: str) -> str:
    """Executes a shell command with Frugal tiered compression, secret masking, and lossless disk preservation."""
    try:
        t0 = time.perf_counter()

        # 1. Security Check
        sec = security.check_command(command)
        if not sec.allowed:
            return f"[FRUGAL SECURITY BLOCKED] {sec.reason}"

        # 2. Circuit Breaker Check
        breaker_alert = breaker.check_command(command)

        # 3. Safe Execution (shell=False)
        cmd_res = security.run_command(command)
        latency_ms = int((time.perf_counter() - t0) * 1000)

        # 4. Secret Redaction (applied to stdout, stderr, AND command string)
        clean_command = redactor.redact(command)
        clean_stdout = redactor.redact(cmd_res.stdout)
        clean_stderr = redactor.redact(cmd_res.stderr)
        raw_output = clean_stdout
        if clean_stderr:
            raw_output = f"{clean_stdout}\n{clean_stderr}".strip() if clean_stdout else clean_stderr

        # 5. Lossless Disk Persistence (Save raw output BEFORE compression)
        log_id, pointer = storage.save_log(raw_output)

        # 6. Record run in circuit breaker
        breaker.record_command_run(command, cmd_res.returncode)

        # 7. Tier 1 Deterministic Compression
        tier1_text, needs_intel = squeezer.squeeze_output(
            clean_command, cmd_res.returncode, raw_output, log_id=log_id
        )

        final_content = tier1_text
        tier_used = 1
        p_toks = 0
        c_toks = 0

        # 8. Tier 2 Intelligent Escalation (Gemma 4 text)
        if needs_intel:
            final_content, p_toks, c_toks, tier_used = (
                intelligence.intelligent_squeeze_with_meta(
                    raw_output, clean_command, cmd_res.returncode, log_id=log_id
                )
            )

        # 9. Radical Transparency Telemetry Recording
        session_id = state.get_session_id()
        metrics.record_bash_event(
            session_id=session_id,
            command=clean_command,
            exit_code=cmd_res.returncode,
            raw_output=raw_output,
            compressed_output=final_content,
            tier_used=tier_used,
            gemma_prompt_tokens=p_toks,
            gemma_completion_tokens=c_toks,
            latency_ms=latency_ms,
        )

        # 10. Format and return response
        if breaker_alert:
            return f"{breaker_alert}\n\n{final_content}"
        return final_content

    except Exception as e:
        return f"[FRUGAL ERROR] Execution failed in frugal_bash: {e}"


@mcp.tool()
def frugal_read_file(path: str, force: bool = False) -> str:
    """Reads a file with hash deduplication to eliminate context waste."""
    try:
        t0 = time.perf_counter()
        session_id = state.get_session_id()

        content, was_deduplicated = deduper.check_and_read(
            path, force=force, session_id=session_id
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)

        # Accurate baseline calculation:
        raw_text = content
        if was_deduplicated:
            try:
                resolved = security.validate_path(path)
                if resolved.exists():
                    raw_text = resolved.read_text(encoding="utf-8", errors="replace")
            except Exception:
                pass

        metrics.record_read_event(
            session_id=session_id,
            path=path,
            was_deduplicated=was_deduplicated,
            raw_content=raw_text,
            compressed_content=content,
            latency_ms=latency_ms,
        )
        return content

    except Exception as e:
        return f"[FRUGAL ERROR] Failed to read file: {e}"


@mcp.tool()
def frugal_get_log(log_id: str, start_line: int = 1, end_line: int = 200) -> str:
    """Escape hatch: retrieves a 1-indexed slice of raw logs from disk."""
    try:
        return storage.get_log_slice(log_id, start_line=start_line, end_line=end_line)
    except Exception as e:
        return f"[FRUGAL ERROR] Failed to retrieve log slice: {e}"


@mcp.tool()
def frugal_analyze_ui(screenshot_path: str, task_hint: str = "") -> str:
    """Analyzes a UI screenshot using Gemma 4 multimodal vision, saving raw image to disk first."""
    try:
        t0 = time.perf_counter()

        # 1. Path validation
        valid_path = security.validate_path(screenshot_path)
        if not valid_path.exists():
            return f"[FRUGAL ERROR] Screenshot file not found: {screenshot_path}"

        img_bytes = valid_path.read_bytes()

        # 2. Tier 3 Multimodal Analysis via Gemma 4
        analysis_json_str, p_toks, c_toks, tier_used = (
            intelligence.analyze_screenshot_with_meta(
                str(valid_path), task_hint=task_hint
            )
        )

        try:
            analysis_dict = json.loads(analysis_json_str)
        except Exception:
            analysis_dict = {"summary": analysis_json_str}

        # 3. Lossless Persistence (Save screenshot and analysis JSON to disk)
        import uuid
        visual_id = str(uuid.uuid4())
        analysis_dict["visual_id"] = visual_id
        analysis_dict["escape_hatch"] = (
            f'frugal_get_visual(visual_id="{visual_id}", raw=True)'
        )

        visual_id, img_rel_path, json_rel_path = storage.save_visual(
            img_bytes, analysis_dict, visual_id=visual_id
        )

        final_payload = json.dumps(analysis_dict, indent=2)

        # 4. Measure tokens & record telemetry
        raw_tokens = token_counter.count_image_tokens(str(valid_path))
        comp_tokens = token_counter.count_payload_tokens(final_payload)
        latency_ms = int((time.perf_counter() - t0) * 1000)

        session_id = state.get_session_id()
        metrics.record_visual_event(
            session_id=session_id,
            visual_id=visual_id,
            raw_tokens=raw_tokens,
            compressed_tokens=comp_tokens,
            gemma_prompt_tokens=p_toks,
            gemma_completion_tokens=c_toks,
            latency_ms=latency_ms,
        )

        return final_payload

    except Exception as e:
        return f"[FRUGAL ERROR] UI analysis failed: {e}"


@mcp.tool()
def frugal_get_visual(visual_id: str, raw: bool = False) -> str:
    """Escape hatch: retrieves visual analysis JSON (raw=False) or base64 PNG (raw=True)."""
    try:
        return storage.get_visual(visual_id, raw=raw)
    except Exception as e:
        return f"[FRUGAL ERROR] Failed to retrieve visual artifact: {e}"


@mcp.tool()
def frugal_stats(session_id: str | None = None) -> str:
    """Returns two-ledger token savings telemetry for the current or specified session."""
    try:
        active_session = session_id or state.get_session_id()
        stats = metrics.get_session_stats(session_id=active_session)

        report = (
            "======================= FRUGAL SESSION STATS =======================\n"
            f"Session ID:                  {session_id}\n\n"
            "[LEDGER A: AGENT CONTEXT SAVINGS]\n"
            f"- Bash Invocations:          {stats['bash_calls']}\n"
            f"- File Reads:                {stats['file_reads']} ({stats['duplicate_reads_blocked']} deduplicated)\n"
            f"- Visual UI Analyses:        {stats['visual_analyses']}\n"
            f"- Baseline Context Tokens:   {stats['baseline_tokens']:,}\n"
            f"- Compressed Context Tokens: {stats['frugal_tokens']:,}\n"
            f"- Gross Context Saved:       {stats['saved_tokens']:,} ({stats['reduction_percent']}% reduction)\n\n"
            "[LEDGER B: ENGINE PROCESSING OVERHEAD (RADICAL TRANSPARENCY)]\n"
            f"- Tier 1 Deterministic:      {stats['tier1_zero_cost_calls']} calls (0 tokens — 100% FREE)\n"
            f"- Tier 2/3 AI Calls:         {stats['tier2_tier3_calls']} calls\n"
            f"- Gemma 4 Prompt Tokens:     {stats['gemma_prompt_tokens']:,}\n"
            f"- Gemma 4 Completion Tokens: {stats['gemma_completion_tokens']:,}\n"
            f"- Total Gemma 4 Overhead:    {stats['gemma_overhead_tokens']:,} tokens\n\n"
            "[NET SYSTEM ROI]\n"
            f"- Net Saved (Single Turn):   {stats['net_tokens_saved']:,} tokens\n"
            f"- Token Counter Engine:      {stats['token_counter']}\n"
            "===================================================================="
        )
        return report

    except Exception as e:
        return f"[FRUGAL ERROR] Failed to generate session stats: {e}"


if __name__ == "__main__":
    mcp.run()
