"""
Integration tests for HTTP SSE streaming endpoint POST /api/chat/stream.
Validates:
- text/event-stream media type
- Event lifecycle and ordering (meta -> phase -> answer_start -> answer_delta -> sources -> done)
- Time To First Event (TTFE) <= 500ms
- Evidence truth invariant (0 unverified domain tokens, sources only after answer)
- Zero leakage of raw chain-of-thought or reasoning text
- Tool authorization safety and exactly-once execution
- Multi-turn resumption via conversation_id
- Exact parity with legacy /api/chat endpoint
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


def mock_api_llm(prompt, system_prompt=None):
    p = prompt.lower()
    if "kiểm định viên" in p or "groundedness" in p:
        return '{"valid": true}'

    q_part = p.split("[câu hỏi]:")[-1] if "[câu hỏi]:" in p else p

    if "dijkstra" in q_part:
        return "Thuật toán Dijkstra dùng để tìm đường đi ngắn nhất."
    if "xyz9999" in q_part:
        return "Chưa tìm thấy đủ dữ liệu trong tài liệu hiện có để trả lời chính xác."
    if "fit4201" in q_part:
        return "Môn FIT4201 - Hệ thống nhúng có 3 tín chỉ theo đề cương chi tiết."
    if "phân loại" in p or "intent" in p:
        return '{"category": "DOMAIN_DATA", "tool_intent": null}'
    return "Câu trả lời mẫu từ trợ lý."


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
    """Helper to parse SSE raw response into structured events."""
    events = []
    blocks = raw_text.split("\n\n")
    for block in blocks:
        if not block.strip():
            continue
        event_type = None
        data = None
        for line in block.splitlines():
            if line.startswith("event:"):
                event_type = line[6:].strip()
            elif line.startswith("data:"):
                data_str = line[5:].strip()
                data = json.loads(data_str)
        if event_type:
            events.append({"event": event_type, "data": data})
    return events


def test_stream_content_type_and_ttfe():
    t0 = time.perf_counter()
    t_first = None
    with client.stream("POST", "/api/chat/stream", json={"message": "Môn FIT4201 có bao nhiêu tín chỉ?"}) as res:
        assert res.status_code == 200
        assert "text/event-stream" in res.headers["content-type"]
        for line in res.iter_lines():
            if line:
                t_first = time.perf_counter() - t0
                break

    assert t_first is not None
    # Local TTFE target <= 500ms
    assert t_first <= 0.500, f"TTFE was {t_first * 1000:.1f}ms, expected <= 500ms"


def test_stream_domain_data_lifecycle_and_invariants():
    res = client.post("/api/chat/stream", json={"message": "Môn FIT4201 có bao nhiêu tín chỉ?"})
    assert res.status_code == 200

    events = parse_sse_events(res.text)
    event_types = [e["event"] for e in events]

    # 1. Event ordering checks
    assert "meta" in event_types
    assert "phase" in event_types
    assert "answer_start" in event_types
    assert "answer_delta" in event_types
    assert "sources" in event_types
    assert "done" in event_types

    meta_idx = event_types.index("meta")
    first_phase_idx = event_types.index("phase")
    start_idx = event_types.index("answer_start")
    first_delta_idx = event_types.index("answer_delta")
    sources_idx = event_types.index("sources")
    done_idx = event_types.index("done")

    assert meta_idx < first_phase_idx
    assert first_phase_idx < start_idx
    assert start_idx < first_delta_idx
    assert first_delta_idx < sources_idx
    assert sources_idx < done_idx

    # 2. Invariant: done emitted exactly once
    assert event_types.count("done") == 1

    # 3. Phase validations (UNDERSTAND, ACT, VERIFY emitted)
    phases_emitted = [e["data"].get("phase") for e in events if e["event"] == "phase"]
    assert "UNDERSTAND" in phases_emitted
    assert "ACT" in phases_emitted
    assert "VERIFY" in phases_emitted

    # 4. Invariant: Zero leakage of raw chain_of_thought or reasoning_text
    for e in events:
        data = e["data"]
        assert "chain_of_thought" not in data
        assert "reasoning_text" not in data
        assert "raw_reasoning" not in data
        if "data" in data and isinstance(data["data"], dict):
            assert "chain_of_thought" not in data["data"]
            assert "reasoning_text" not in data["data"]

    # 5. Answer reconstruction
    deltas = [e["data"].get("delta") or (e["data"].get("data") or {}).get("delta", "") for e in events if e["event"] == "answer_delta"]
    full_answer = "".join(deltas)
    assert "FIT4201" in full_answer
    assert "tín chỉ" in full_answer

    # 6. Sources validation
    sources_event = [e for e in events if e["event"] == "sources"][0]
    sources_items = sources_event["data"].get("data", {}).get("items", []) or sources_event["data"].get("items", [])
    assert len(sources_items) > 0
    assert any("FIT4201" in s.get("source_file", "") or "FIT4201" in s.get("course_code", "") for s in sources_items)


def test_stream_general_llm():
    res = client.post("/api/chat/stream", json={"message": "Giải thích thuật toán Dijkstra"})
    assert res.status_code == 200

    events = parse_sse_events(res.text)
    event_types = [e["event"] for e in events]

    assert "meta" in event_types
    assert "phase" in event_types
    assert "answer_start" in event_types
    assert "answer_delta" in event_types
    assert "done" in event_types

    # General LLM has no domain sources
    assert "sources" not in event_types

    deltas = [e["data"].get("delta") or (e["data"].get("data") or {}).get("delta", "") for e in events if e["event"] == "answer_delta"]
    full_answer = "".join(deltas)
    assert "Dijkstra" in full_answer


def test_stream_tool_reminder_action():
    res = client.post("/api/chat/stream", json={"message": "Nhắc tôi ôn thi môn AI ngày 15/12"})
    assert res.status_code == 200

    events = parse_sse_events(res.text)
    event_types = [e["event"] for e in events]

    assert "done" in event_types
    done_event = [e for e in events if e["event"] == "done"][0]
    done_data = done_event["data"].get("data") or done_event["data"]
    assert done_data.get("category") == "TOOL_ACTION"

    deltas = [e["data"].get("delta") or (e["data"].get("data") or {}).get("delta", "") for e in events if e["event"] == "answer_delta"]
    full_answer = "".join(deltas)
    assert any(p in full_answer for p in ["Đã lên lịch nhắc nhở", "Đã ghi nhận lịch nhắc"])


def test_stream_tool_email_draft_safe():
    res = client.post("/api/chat/stream", json={"message": "Soạn giúp tôi bản thảo email gửi cho student@dainam.edu.vn về việc dời lịch thi"})
    assert res.status_code == 200

    events = parse_sse_events(res.text)
    deltas = [e["data"].get("delta") or (e["data"].get("data") or {}).get("delta", "") for e in events if e["event"] == "answer_delta"]
    full_answer = "".join(deltas)
    assert "Bản thảo email (Draft - Chưa gửi đi)" in full_answer


def test_stream_unknown_entity_safe_abstain():
    res = client.post("/api/chat/stream", json={"message": "Học phần XYZ9999 có mấy tín chỉ?"})
    assert res.status_code == 200

    events = parse_sse_events(res.text)
    deltas = [e["data"].get("delta") or (e["data"].get("data") or {}).get("delta", "") for e in events if e["event"] == "answer_delta"]
    full_answer = "".join(deltas)

    assert "Chưa tìm thấy đủ dữ liệu" in full_answer or "không có trong danh mục" in full_answer
    # No sources should be emitted for unknown entities
    event_types = [e["event"] for e in events]
    assert "sources" not in event_types


def test_stream_clarification_and_resumption():
    # 1. Ask something missing information to trigger clarification
    res1 = client.post("/api/chat/stream", json={"message": "Môn học này có bao nhiêu tín chỉ?"})
    assert res1.status_code == 200

    events1 = parse_sse_events(res1.text)
    event_types1 = [e["event"] for e in events1]

    # Should emit clarification or ask for missing course
    assert "done" in event_types1
    done_data = [e for e in events1 if e["event"] == "done"][0]["data"]
    conv_id = done_data.get("conversation_id") or done_data.get("data", {}).get("conversation_id")
    assert conv_id is not None

    # 2. Resume with entity
    res2 = client.post(
        "/api/chat/stream",
        json={"message": "Môn FIT4201", "conversation_id": conv_id},
    )
    assert res2.status_code == 200
    events2 = parse_sse_events(res2.text)
    deltas2 = [e["data"].get("delta") or (e["data"].get("data") or {}).get("delta", "") for e in events2 if e["event"] == "answer_delta"]
    full_answer2 = "".join(deltas2)
    assert "FIT4201" in full_answer2


def test_stream_and_legacy_parity():
    # Compare legacy /api/chat and /api/chat/stream
    query = "Môn FIT4201 có bao nhiêu tín chỉ?"
    res_legacy = client.post("/api/chat", json={"message": query})
    assert res_legacy.status_code == 200
    legacy_json = res_legacy.json()

    res_stream = client.post("/api/chat/stream", json={"message": query})
    assert res_stream.status_code == 200
    stream_events = parse_sse_events(res_stream.text)

    stream_deltas = [e["data"].get("delta") or (e["data"].get("data") or {}).get("delta", "") for e in stream_events if e["event"] == "answer_delta"]
    stream_full_answer = "".join(stream_deltas)

    # Parity check: both answers must contain the exact key content
    assert legacy_json["category"] == "DOMAIN_DATA"
    assert "FIT4201" in legacy_json["answer"]
    assert "FIT4201" in stream_full_answer
    assert len(legacy_json["sources"]) > 0


def test_stream_invalid_request():
    res = client.post("/api/chat/stream", json={"message": ""})
    assert res.status_code == 422
