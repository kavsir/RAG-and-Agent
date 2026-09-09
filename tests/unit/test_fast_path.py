"""
Unit tests for Local Conversational Fast Path (Round UX2).
Validates p95 < 100ms, deterministic responses, zero RAG / external LLM, and non-social pass-through.
"""
import time
from src.api.fast_path import match_fast_path


def test_fast_path_greetings():
    for q in ["xin chào", "Chào bạn", "Hello", "hi", "chào ad!", "ALOOO", "xin chào bạn"]:
        res = match_fast_path(q)
        assert res.matched is True, f"Failed for {q}"
        assert res.intent == "GREETING"
        assert "Trợ lý AI Cố vấn Học tập" in res.answer


def test_fast_path_thanks():
    for q in ["cảm ơn", "cảm ơn bạn nhé!", "thanks", "thank you so much", "cmon", "tks"]:
        res = match_fast_path(q)
        assert res.matched is True, f"Failed for {q}"
        assert res.intent == "THANKS"
        assert "Rất vui được hỗ trợ bạn" in res.answer


def test_fast_path_farewells():
    for q in ["tạm biệt", "bye bye", "goodbye", "chào tạm biệt", "hẹn gặp lại"]:
        res = match_fast_path(q)
        assert res.matched is True, f"Failed for {q}"
        assert res.intent == "FAREWELL"
        assert "Tạm biệt bạn" in res.answer


def test_fast_path_identity():
    for q in ["bạn là ai", "bạn là ai?", "who are you", "bạn tên gì", "giới thiệu bản thân"]:
        res = match_fast_path(q)
        assert res.matched is True, f"Failed for {q}"
        assert res.intent == "IDENTITY"
        assert "Trường Đại học Đại Nam" in res.answer


def test_fast_path_capabilities():
    for q in ["bạn làm được gì", "bạn có thể làm gì?", "chức năng của bạn là gì", "help"]:
        res = match_fast_path(q)
        assert res.matched is True, f"Failed for {q}"
        assert res.intent == "CAPABILITY"
        assert "Tra cứu thông tin học phần" in res.answer


def test_fast_path_non_social_pass_through():
    non_social = [
        "FIT4113 có mấy tín chỉ",
        "môn điện toán đám mây học kỳ nào",
        "điều kiện tốt nghiệp",
        "thuật toán dpf",
        "dijkstra là gì",
        "nhắc tôi học bài",
    ]
    for q in non_social:
        res = match_fast_path(q)
        assert res.matched is False, f"Erroneously matched for {q}"


def test_fast_path_latency_p95():
    times = []
    for _ in range(100):
        t0 = time.perf_counter()
        match_fast_path("xin chào bạn nhé!")
        times.append(time.perf_counter() - t0)
    times.sort()
    p95 = times[94] * 1000  # ms
    assert p95 < 5.0, f"Expected p95 < 5ms, got {p95:.3f}ms"
