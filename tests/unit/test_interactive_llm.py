"""
Unit tests for Interactive LLM Client (Round UX2):
- Connect / read / overall timeouts
- 0 retries on 4xx (fail fast)
- Max 1 retry on 5xx or network errors
- Provider streaming generator (stream_invoke)
"""
from unittest.mock import patch, MagicMock
import httpx
from src.llm.client import LLMClient, set_mock_llm_handler


def test_llm_zero_retries_on_4xx():
    """Client error (401/404/429) must fail fast with 0 retries."""
    client = LLMClient(api_key="test-key")
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized: Invalid API key"

    with patch("httpx.Client.post", return_value=mock_resp) as mock_post:
        result = client.invoke("Test prompt", max_retries=1)
        assert mock_post.call_count == 1, f"Expected 1 call (0 retries), got {mock_post.call_count}"
        assert "Lỗi yêu cầu AI (401)" in result


def test_llm_max_one_retry_on_5xx():
    """Server error (500) must retry at most 1 time (2 attempts total)."""
    client = LLMClient(api_key="test-key")
    mock_resp = MagicMock()
    mock_resp.status_code = 503
    mock_resp.text = "Service Unavailable"

    with patch("httpx.Client.post", return_value=mock_resp) as mock_post:
        result = client.invoke("Test prompt", max_retries=1)
        assert mock_post.call_count == 2, f"Expected 2 calls (1 retry), got {mock_post.call_count}"
        assert "không thể kết nối" in result


def test_llm_max_one_retry_on_timeout():
    """Timeout error must retry at most 1 time."""
    client = LLMClient(api_key="test-key")

    with patch("httpx.Client.post", side_effect=httpx.TimeoutException("Read timed out")) as mock_post:
        result = client.invoke("Test prompt", max_retries=1)
        assert mock_post.call_count == 2, f"Expected 2 calls (1 retry), got {mock_post.call_count}"
        assert "không thể kết nối" in result


def test_llm_stream_invoke_mock():
    """Streaming with mock handler yields chunks properly."""
    set_mock_llm_handler(lambda p, **kw: "Đây là câu trả lời thử nghiệm.")
    client = LLMClient(api_key="test-key")
    chunks = list(client.stream_invoke("Test prompt"))
    assert len(chunks) > 0
    reconstructed = "".join(chunks)
    assert "Đây là câu trả lời thử nghiệm." in reconstructed
    set_mock_llm_handler(None)
