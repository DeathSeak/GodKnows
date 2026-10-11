"""Gemini API token counting with SHA-256 LRU caching, high-precision tiktoken fallback, and dimension-based vision tiling."""

from __future__ import annotations

import functools
import hashlib
import math
import os
from pathlib import Path
from typing import Any

from frugal import config


def compute_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


@functools.lru_cache(maxsize=1000)
def _cached_text_count(text_hash: str, text: str, model_name: str) -> int:
    """
    Internal cached worker that calls Gemini countTokens API.
    Keyed by (text_hash, text, model_name).
    Falls back to high-precision offline BPE tokenization (tiktoken) or len(text) // 4.
    """
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        try:
            import tiktoken
            encoding = tiktoken.get_encoding("cl100k_base")
            return max(1, len(encoding.encode(text)))
        except Exception:
            return max(1, len(text) // 4)

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)
        response = model.count_tokens(text)
        if response and hasattr(response, "total_tokens") and response.total_tokens > 0:
            return int(response.total_tokens)
    except Exception:
        pass

    # Fallback to tiktoken if Gemini API encounters network or authentication issues
    try:
        import tiktoken
        encoding = tiktoken.get_encoding("cl100k_base")
        return max(1, len(encoding.encode(text)))
    except Exception:
        return max(1, len(text) // 4)


def count_text_tokens(text: str | None, model: str | None = None) -> int:
    """
    Counts tokens for text using Gemini countTokens API with LRU cache.
    Falls back to high-precision tiktoken BPE encoding when offline.
    """
    if not text:
        return 0

    cfg = config.get_config()
    target_model = model or cfg.intelligence.model
    text_hash = compute_sha256(text)
    return _cached_text_count(text_hash, text, target_model)


def count_image_tokens(image_path: str | Path, model: str | None = None) -> int:
    """
    Counts tokens for an image using Gemini countTokens API.
    When offline, uses Pillow to calculate image dimensions and applies
    Google's published Gemini vision tiling specification:
    - 258 tokens per 768x768 tile.
    """
    img_p = Path(image_path)
    if not img_p.exists():
        return 0

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if api_key:
        try:
            import google.generativeai as genai
            from PIL import Image

            cfg = config.get_config()
            target_model = model or cfg.intelligence.model
            genai.configure(api_key=api_key)
            model_inst = genai.GenerativeModel(target_model)

            img = Image.open(img_p)
            response = model_inst.count_tokens([img])
            if response and hasattr(response, "total_tokens") and response.total_tokens > 0:
                return int(response.total_tokens)
        except Exception:
            pass

    # Exact dimension-based tiling calculation (Gemini vision specification)
    try:
        from PIL import Image
        with Image.open(img_p) as img:
            width, height = img.size
            tiles_x = max(1, math.ceil(width / 768))
            tiles_y = max(1, math.ceil(height / 768))
            return tiles_x * tiles_y * 258
    except Exception:
        return 258


def count_payload_tokens(payload: str | None) -> int:
    """
    Counts tokens for a complete tool response payload (text + summary + escape hatch).
    """
    return count_text_tokens(payload)
