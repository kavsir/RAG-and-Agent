"""
Unit tests for HTTP streaming, StreamEvent schema, and AgentEventEmitter.
Verifies safe-thinking policy, zero raw chain-of-thought exposure, and chunk reconstruction.
"""
import pytest
import json
from src.agent_core.events import (
    StreamEvent,
    StreamEventType,
    AgentPhase,
    AgentEventEmitter,
)
from src.api.streaming import chunk_answer_text


def test_stream_event_serialization():
    event = StreamEvent(
        type=StreamEventType.PHASE,
        conversation_id="conv-123",
        goal_id="goal-456",
        phase=AgentPhase.UNDERSTAND,
        label="Đang hiểu yêu cầu của bạn...",
        data={"step": 1},
    )
    sse_text = event.to_sse()
    assert sse_text.startswith("event: phase\n")
    assert "data: " in sse_text
    assert sse_text.endswith("\n\n")

    # Verify JSON content
    data_line = [line for line in sse_text.splitlines() if line.startswith("data: ")][0]
    payload = json.loads(data_line[6:])
    assert payload["type"] == "phase"
    assert payload["conversation_id"] == "conv-123"
    assert payload["goal_id"] == "goal-456"
    assert payload["phase"] == "UNDERSTAND"
    assert payload["label"] == "Đang hiểu yêu cầu của bạn..."
    assert payload["data"] == {"step": 1}


def test_stream_event_forbids_raw_chain_of_thought():
    # Attempt to inject reasoning_text directly
    with pytest.raises(ValueError, match="Prohibited reasoning fields"):
        StreamEvent.model_validate({
            "type": "phase",
            "phase": "UNDERSTAND",
            "reasoning_text": "secret model reasoning",
        })

    # Attempt to inject chain_of_thought
    with pytest.raises(ValueError, match="Prohibited reasoning fields"):
        StreamEvent.model_validate({
            "type": "phase",
            "chain_of_thought": "step 1 think step 2 think",
        })

    # Attempt to inject into data dictionary
    with pytest.raises(ValueError, match="Prohibited reasoning fields"):
        StreamEvent.model_validate({
            "type": "phase",
            "data": {"reasoning_text": "internal thought trace"},
        })

    with pytest.raises(ValueError, match="Prohibited reasoning fields"):
        StreamEvent.model_validate({
            "type": "phase",
            "data": {"raw_reasoning": "unfiltered thought"},
        })


def test_chunk_answer_text_exact_reconstruction():
    text = (
        "Môn FIT4201 - Hệ thống nhúng có 3 tín chỉ theo đề cương chi tiết.\n"
        "Giảng viên phụ trách: Thầy Tuấn.\n"
        "Được giảng dạy tại Khoa Công nghệ Thông tin."
    )
    chunks = chunk_answer_text(text, target_chunk_len=25)
    assert len(chunks) > 1
    # Strict invariant: concatenating chunks must equal the original text character-by-character
    assert "".join(chunks) == text


def test_chunk_answer_text_edge_cases():
    assert chunk_answer_text("") == []
    assert chunk_answer_text("SingleWord") == ["SingleWord"]
    assert "".join(chunk_answer_text("Word1 Word2 Word3", target_chunk_len=10)) == "Word1 Word2 Word3"


def test_agent_event_emitter():
    emitted = []

    def sink(event: StreamEvent):
        emitted.append(event)

    emitter = AgentEventEmitter(callback=sink, conversation_id="conv-abc")
    emitter.set_goal_id("goal-xyz")

    emitter.emit_phase(AgentPhase.UNDERSTAND, "Đang hiểu yêu cầu...")
    emitter.emit_phase(AgentPhase.ACT, "Đang tra cứu FIT4201...")
    emitter.emit_tool_status("Đang kiểm tra gửi email...")

    assert len(emitted) == 3
    assert emitted[0].type == "phase"
    assert emitted[0].phase == "UNDERSTAND"
    assert emitted[0].conversation_id == "conv-abc"
    assert emitted[0].goal_id == "goal-xyz"

    assert emitted[1].type == "phase"
    assert emitted[1].phase == "ACT"

    assert emitted[2].type == "tool_status"
    assert emitted[2].phase == "ACT"


def test_agent_event_emitter_traps_exceptions():
    def bad_sink(event: StreamEvent):
        raise RuntimeError("Sink failed unexpectedly")

    emitter = AgentEventEmitter(callback=bad_sink)
    # Must not raise exception
    emitter.emit_phase(AgentPhase.OBSERVE, "Đang kiểm tra...")
