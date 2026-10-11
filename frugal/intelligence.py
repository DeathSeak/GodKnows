"""Tier 2 & 3: Intelligent compression and visual analysis via Gemma 4 with metadata tracking."""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from frugal import config, squeezer, token_counter


class GemmaAPIError(Exception):
    """Raised when Gemma 4 API call fails or times out."""
    pass


import warnings
warnings.filterwarnings("ignore", category=FutureWarning, module="google.generativeai")


def clean_json_response(raw_text: str) -> dict[str, Any]:
    """
    Extracts and parses JSON from model output, stripping thoughts, markdown code fences,
    or trailing commentary.
    """
    cleaned = raw_text.strip()

    # 1. Direct parse attempt
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # 2. Extract code blocks and balanced { ... } candidates
    candidates: list[str] = []

    # Markdown code blocks
    for match in re.finditer(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", cleaned):
        candidates.append(match.group(1).strip())

    # Scan for top-level balanced { ... } blocks
    stack: list[str] = []
    start_idx = -1
    in_string = False
    escape = False

    for i, char in enumerate(cleaned):
        if char == '"' and not escape:
            in_string = not in_string
        elif char == '\\' and in_string:
            escape = not escape
            continue
        elif not in_string:
            if char == '{':
                if not stack:
                    start_idx = i
                stack.append(char)
            elif char == '}':
                if stack:
                    stack.pop()
                    if not stack and start_idx != -1:
                        candidates.append(cleaned[start_idx : i + 1])
                        start_idx = -1
        escape = False

    # Prefer parsed dictionary candidates containing domain keys ('summary' or 'issues')
    for cand in reversed(candidates):
        try:
            parsed = json.loads(cand)
            if isinstance(parsed, dict) and ("summary" in parsed or "issues" in parsed):
                return parsed
        except json.JSONDecodeError:
            continue

    # Fallback to any valid dict candidate
    for cand in reversed(candidates):
        try:
            parsed = json.loads(cand)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue

    # If all parsing fails, return safe structured fallback
    return {
        "summary": "Output analyzed (unstructured response wrapped)",
        "raw_response": cleaned,
        "root_cause": "Unspecified",
        "error_signature": "",
        "affected_files": [],
        "suggested_actions": ["Review raw log via escape hatch"],
        "confidence": "low",
    }


def call_gemma4_with_usage(
    prompt: str,
    image_path: str | Path | None = None,
    timeout: float = 45.0,
) -> tuple[str, int, int]:
    """
    Invokes Gemma 4 and extracts (response_text, prompt_tokens, completion_tokens).
    """
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise GemmaAPIError(
            "GEMINI_API_KEY or GOOGLE_API_KEY is not set in environment"
        )

    try:
        import google.generativeai as genai
    except ImportError as e:
        raise GemmaAPIError(f"google.generativeai package not installed: {e}") from e

    cfg = config.get_config()
    if image_path:
        model_name = cfg.visual.model
        if model_name in ("gemma-4", "gemma4", "gemini", "gemini-3.8-flash"):
            model_name = "gemma-4-26b-a4b-it"
    else:
        model_name = cfg.intelligence.model
        if model_name in ("gemma-4", "gemma4"):
            model_name = "gemma-4-26b-a4b-it"

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)


    content_parts: list[Any] = []

    if image_path:
        img_p = Path(image_path)
        if not img_p.exists():
            raise GemmaAPIError(f"Screenshot image file not found: {image_path}")

        try:
            from PIL import Image
            img = Image.open(img_p)
            content_parts.append(img)
        except Exception as e:
            raise GemmaAPIError(f"Failed to load image for visual analysis: {e}") from e

    content_parts.append(prompt)

    last_err: Exception | None = None
    for attempt in range(2):
        try:
            response = model.generate_content(
                content_parts,
                request_options={"timeout": timeout},
            )
            if not response or not response.text:
                raise GemmaAPIError("Gemma 4 returned empty response")

            prompt_toks = 0
            comp_toks = 0
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                prompt_toks = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
                comp_toks = getattr(response.usage_metadata, "candidates_token_count", 0) or 0

            # If usage_metadata is missing or 0, fallback to token_counter
            if prompt_toks == 0:
                prompt_toks = token_counter.count_text_tokens(prompt)
                if image_path:
                    prompt_toks += token_counter.count_image_tokens(image_path)
            if comp_toks == 0:
                comp_toks = token_counter.count_text_tokens(response.text)

            return response.text, prompt_toks, comp_toks
        except Exception as e:
            last_err = e
            if attempt == 0:
                time.sleep(2.0)
                continue
            break

    raise GemmaAPIError(f"Gemma 4 API invocation failed: {last_err}") from last_err


def call_gemma4(
    prompt: str,
    image_path: str | Path | None = None,
    timeout: float = 30.0,
) -> str:
    """Wrapper returning response text directly."""
    text, _, _ = call_gemma4_with_usage(prompt, image_path=image_path, timeout=timeout)
    return text


def intelligent_squeeze_with_meta(
    raw_output: str,
    command: str,
    exit_code: int,
    log_id: str = "",
) -> tuple[str, int, int, int]:
    """
    Tier 2: Returns (compressed_json, prompt_tokens, completion_tokens, tier_used).
    Falls back to Tier 1 on failure with (tier1_text, 0, 0, 1).
    """
    lines = raw_output.splitlines()
    if len(lines) > 300:
        capped_output = "\n".join(lines[:100] + [f"... [{len(lines) - 200} lines omitted] ..."] + lines[-100:])
    else:
        capped_output = raw_output

    prompt = (
        "You are a senior DevOps engineer analyzing terminal output for an AI coding agent.\n"
        f"Command: {command}\n"
        f"Exit Code: {exit_code}\n\n"
        "Return a JSON object with:\n"
        "- summary: Concise one-line description\n"
        "- root_cause: Likely root cause\n"
        "- error_signature: Exact error signature\n"
        "- affected_files: List of files involved\n"
        "- suggested_actions: 1-2 concrete next steps\n"
        "- confidence: high/medium/low\n\n"
        "Raw output:\n"
        f"{capped_output}\n\n"
        "Return valid JSON."
    )

    try:
        raw_response, p_toks, c_toks = call_gemma4_with_usage(prompt)
        parsed = clean_json_response(raw_response)
        if log_id:
            parsed["log_id"] = log_id
        return json.dumps(parsed, indent=2), p_toks, c_toks, 2
    except (GemmaAPIError, Exception):
        tier1_result, _ = squeezer.squeeze_output(
            command, exit_code, raw_output, log_id=log_id
        )
        return (
            tier1_result + "\n\n[FRUGAL NOTE] Gemma 4 unavailable. Tier 1 compression used.",
            0,
            0,
            1,
        )


def intelligent_squeeze(
    raw_output: str,
    command: str,
    exit_code: int,
    log_id: str = "",
) -> str:
    """Tier 2 backward-compatible signature returning string."""
    result, _, _, _ = intelligent_squeeze_with_meta(
        raw_output, command, exit_code, log_id=log_id
    )
    return result


def analyze_screenshot_with_meta(
    screenshot_path: str,
    task_hint: str = "",
    visual_id: str = "",
) -> tuple[str, int, int, int]:
    """
    Tier 3: Returns (json_analysis, prompt_tokens, completion_tokens, tier_used).
    """
    prompt = (
        "You are a UI QA engineer analyzing a screenshot for an AI coding agent.\n"
        "Return a JSON object with:\n"
        "- summary: One-line description of the screen and any error\n"
        "- error_text: Exact error text visible on screen\n"
        "- suggested_fix: Concrete action to resolve the issue\n\n"
        f"Task hint: {task_hint}\n\n"
        "Return valid JSON."
    )

    try:
        raw_response, p_toks, c_toks = call_gemma4_with_usage(
            prompt, image_path=screenshot_path
        )
        parsed = clean_json_response(raw_response)
        if visual_id:
            parsed["visual_id"] = visual_id
        return json.dumps(parsed, indent=2), p_toks, c_toks, 3
    except Exception as e:
        fallback_data = {
            "summary": "[FRUGAL NOTE] Visual analysis unavailable (Gemma 4 fallback).",
            "error": str(e),
            "issues": [],
            "visible_text": [],
            "layout_notes": "Unable to process screenshot via Gemma 4.",
            "suggested_next_steps": [
                f'Inspect original screenshot with frugal_get_visual(visual_id="{visual_id}", raw=True)'
                if visual_id
                else "Inspect original screenshot with frugal_get_visual(visual_id, raw=True)"
            ],
            "visual_id": visual_id,
        }
        return json.dumps(fallback_data, indent=2), 0, 0, 1


def analyze_screenshot(
    screenshot_path: str,
    task_hint: str = "",
    visual_id: str = "",
) -> str:
    """Tier 3 backward-compatible signature returning string."""
    result, _, _, _ = analyze_screenshot_with_meta(
        screenshot_path, task_hint=task_hint, visual_id=visual_id
    )
    return result
