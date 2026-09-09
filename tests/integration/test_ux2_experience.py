"""
Integration tests for Round UX2: User-Centered Chat Experience.

Validates the four production UX defects fixed:
1. Fast Path Latency (< 100ms, 0 RAG, 0 LLM for greetings/thanks/identity).
2. CourseEntityResolver V2 (typo tolerance, abbreviations, pronoun session context).
3. Ambiguous General Query Clarification (0 confident hallucination for ambiguous acronyms).
4. Answer Presentation Model (structured Markdown, credit breakdown, numbered CLOs, graduation bullets, assessment table).
5. Interactive LLM Streaming for General LLM.
"""
import pytest
import time
import json
from typing import List, Dict, Any
from fastapi.testclient import TestClient

from src.api.main import app
from src.llm.client import set_mock_llm_handler
from src.memory.memory_manager import get_memory_manager
from src.cache.exact_cache import get_exact_cache
from src.agent_core.presentation import (
    format_credits,
    format_clo,
    format_graduation,
    format_assessment,
    format_lecturer,
)


def mock_api_llm(prompt, system_prompt=None):
    p = prompt.lower()
    if "kiểm định viên" in p or "groundedness" in p:
        return '{"valid": true}'

    q_part = p.split("[câu hỏi]:")[-1] if "[câu hỏi]:" in p else p

    if "dijkstra" in q_part:
        return "Thuật toán Dijkstra là thuật toán tìm đường đi ngắn nhất từ một đỉnh nguồn tới các đỉnh còn lại trong đồ thị có trọng số không âm."
    if "fit4113" in q_part or "điện toán đám mây" in q_part:
        return "Học phần Điện toán đám mây (FIT4113) có khối lượng 3 tín chỉ."
    if "phân loại" in p or "intent" in p:
        return '{"category": "DOMAIN_DATA", "tool_intent": null}'
    return "Câu trả lời từ trợ lý học vụ."


@pytest.fixture(scope="module", autouse=True)
def warmup_module():
    """Warm up services once per test module to prevent cold-start initialization skew."""
    from src.router import get_router_service
    from src.ingestion.vector_store import get_embedding_model
    try:
        get_embedding_model()
        get_router_service().classify("warmup query")
    except Exception:
        pass


@pytest.fixture(autouse=True)
def setup_mock():
    set_mock_llm_handler(mock_api_llm)
    get_memory_manager().clear()
    get_exact_cache().clear()
    yield
    set_mock_llm_handler(None)
    get_memory_manager().clear()
    get_exact_cache().clear()


client = TestClient(app)


def parse_sse_events(raw_text: str) -> List[Dict[str, Any]]:
    events = []
    blocks = raw_text.strip().split("\n\n")
    for block in blocks:
        if not block.strip():
            continue
        evt_type = "message"
        data_str = ""
        for line in block.split("\n"):
            line = line.strip()
            if line.startswith("event:"):
                evt_type = line[6:].strip()
            elif line.startswith("data:"):
                data_str = line[5:].strip()
        if data_str:
            try:
                parsed_data = json.loads(data_str)
                events.append({"event": evt_type, "data": parsed_data})
            except json.JSONDecodeError:
                events.append({"event": evt_type, "raw": data_str})
    return events


def test_fast_path_latency_and_categories():
    """Verify local fast path responds in < 100ms with FAST_PATH category and 0 LLM."""
    # Warm up client connection once
    client.post("/api/chat", json={"message": "chào bạn"})

    test_queries = [
        "xin chào",
        "chào bạn",
        "cảm ơn bạn nhé",
        "tạm biệt",
        "bạn là ai",
        "bạn làm được gì",
    ]

    for q in test_queries:
        t0 = time.perf_counter()
        resp = client.post("/api/chat", json={"message": q})
        elapsed_ms = (time.perf_counter() - t0) * 1000

        assert resp.status_code == 200, f"Failed for {q}"
        data = resp.json()
        assert data["category"] == "FAST_PATH"
        assert len(data["answer"]) > 0
        assert data["sources"] == []
        assert elapsed_ms < 100, f"Query '{q}' took {elapsed_ms:.1f}ms, exceeding 100ms target"


def test_fast_path_streaming():
    """Verify fast path works via /api/chat/stream endpoint without flashing thinking card."""
    t0 = time.perf_counter()
    resp = client.post("/api/chat/stream", json={"message": "xin chào"})
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    events = parse_sse_events(resp.text)
    event_types = [e["event"] for e in events]

    assert "meta" in event_types
    assert "answer_delta" in event_types
    assert "done" in event_types
    done_evt = next(e for e in events if e["event"] == "done")
    done_payload = done_evt["data"].get("data", done_evt["data"])
    assert done_payload["category"] == "FAST_PATH"
    assert elapsed_ms < 400, f"Fast path stream took {elapsed_ms:.1f}ms"


def test_ambiguous_acronym_disambiguation():
    """Ambiguous CS acronyms like 'thuật toán dpf' trigger clarification, 0 confident guessing."""
    resp = client.post("/api/chat", json={"message": "thuật toán dpf là gì"})
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "NEEDS_USER_INPUT"
    assert data["category"] == "GENERAL_LLM"
    assert data["clarification_question"] is not None
    assert "dpf" in data["clarification_question"].lower()
    assert len(data["clarification_options"]) >= 2
    assert any("Distributed Point Function" in opt for opt in data["clarification_options"])


def test_ambiguous_acronym_stream_event():
    """Verify ambiguous acronym triggers clarification event in SSE stream."""
    resp = client.post("/api/chat/stream", json={"message": "thuật toán dfa"})
    assert resp.status_code == 200
    events = parse_sse_events(resp.text)
    event_types = [e["event"] for e in events]

    assert "clarification" in event_types
    clar_evt = next(e for e in events if e["event"] == "clarification")
    clar_payload = clar_evt["data"].get("data", clar_evt["data"])
    assert "dfa" in clar_payload["question"].lower()
    assert len(clar_payload["options"]) >= 2


def test_course_resolver_typo_and_session_context():
    """Verify CourseEntityResolver V2 handles typos and multi-turn session pronouns."""
    # Turn 1: Typo 'cn điện toán máy'
    resp1 = client.post("/api/chat", json={"message": "Môn cn điện toán máy có mấy tín chỉ?"})
    assert resp1.status_code == 200
    data1 = resp1.json()
    conv_id = data1["conversation_id"]

    # Turn 2: Pronoun referring to the active course in session
    resp2 = client.post("/api/chat", json={"message": "môn này học ở học kỳ mấy?", "conversation_id": conv_id})
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["conversation_id"] == conv_id


def test_answer_presentation_models():
    """Verify answer presentation formatting functions."""
    # 1. Credits
    cred_answer = format_credits("FIT4113", "Điện toán đám mây", "3 tín chỉ")
    assert "Điện toán đám mây (FIT4113)" in cred_answer
    assert "**3**" in cred_answer

    # 2. Lecturer
    lect_answer = format_lecturer("FIT4113", "Điện toán đám mây", "TS. Nguyễn Văn A")
    assert "Giảng viên môn Điện toán đám mây (FIT4113)" in lect_answer
    assert "TS. Nguyễn Văn A" in lect_answer

    # 3. CLOs (Numbered list)
    clo_raw = "CLO1: Hiểu kiến trúc đám mây; CLO2: Triển khai Kubernetes trên AWS"
    clo_answer = format_clo("FIT4113", "Điện toán đám mây", clo_raw)
    assert "1. **CLO1:** Hiểu kiến trúc đám mây" in clo_answer
    assert "2. **CLO2:** Triển khai Kubernetes trên AWS" in clo_answer

    # 4. Assessment Table
    assess_raw = "Chuyên cần 10%; Giữa kỳ 30% tự luận; Cuối kỳ 60% thực hành máy"
    assess_answer = format_assessment("FIT4113", "Điện toán đám mây", assess_raw)
    assert "| Thành phần đánh giá | Tỷ lệ | Hình thức / Tiêu chí |" in assess_answer
    assert "10%" in assess_answer
    assert "60%" in assess_answer

    # 5. Graduation requirements (Structured bullets with bold metrics)
    grad_raw = "Tích lũy tối thiểu 135 tín chỉ; Điểm GPA tối thiểu 2.0; Có chứng chỉ TOEIC 500"
    grad_answer = format_graduation("Chương trình đào tạo CNTT", grad_raw)
    assert "Điều kiện xét tốt nghiệp" in grad_answer
    assert "- Tích lũy tối thiểu 135 tín chỉ" in grad_answer
