from pathlib import Path
from unittest.mock import MagicMock, patch
from frugal import token_counter


def test_count_text_tokens_empty():
    assert token_counter.count_text_tokens("") == 0
    assert token_counter.count_text_tokens(None) == 0


def test_count_text_tokens_offline_fallback(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    text = "A" * 100  # 100 characters
    count = token_counter.count_text_tokens(text)
    # With tiktoken cl100k_base, repeated 'A'*100 encodes to 13 tokens (vs 25 with len//4)
    assert count in (13, 25)


def test_count_text_tokens_cached(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    text = "Unique test text for caching verification."
    c1 = token_counter.count_text_tokens(text)
    c2 = token_counter.count_text_tokens(text)
    assert c1 == c2

    # Check that lru_cache recorded a hit
    info = token_counter._cached_text_count.cache_info()
    assert info.hits >= 1


@patch("google.generativeai.GenerativeModel")
def test_count_text_tokens_with_mock_api(mock_model_class, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    mock_instance = MagicMock()
    mock_model_class.return_value = mock_instance
    mock_resp = MagicMock()
    mock_resp.total_tokens = 42
    mock_instance.count_tokens.return_value = mock_resp

    # Bypass previous cache entries with fresh text
    unique_text = "Some very specific text for API test 12345"
    tokens = token_counter.count_text_tokens(unique_text)
    assert tokens == 42


def test_count_image_tokens_missing_file():
    assert token_counter.count_image_tokens("non_existent_image.png") == 0


def test_count_image_tokens_offline_fallback(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    from PIL import Image
    img_file = tmp_path / "test.png"
    # Create a 1000x500 image: ceil(1000/768)=2 tiles across, ceil(500/768)=1 tile down = 2 tiles * 258 = 516 tokens
    Image.new("RGB", (1000, 500), color="white").save(img_file)

    count = token_counter.count_image_tokens(str(img_file))
    assert count == 516

