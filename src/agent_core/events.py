"""
Stream Event and Observational Event Emitter for Agent Execution.
Enforces strict safe-thinking policy:
- No raw chain-of-thought or reasoning text
- Structured progress phases only
- Observational instrumentation with zero side-effects on decision semantics
"""
import time
import json
from typing import Optional, Dict, Any, Callable
from pydantic import BaseModel, Field, model_validator


class AgentPhase:
    UNDERSTAND = "UNDERSTAND"
    OBSERVE = "OBSERVE"
    PLAN = "PLAN"
    ACT = "ACT"
    VERIFY = "VERIFY"
    PREPARE_ANSWER = "PREPARE_ANSWER"

    ALL_PHASES = {UNDERSTAND, OBSERVE, PLAN, ACT, VERIFY, PREPARE_ANSWER}


class StreamEventType:
    META = "meta"
    PHASE = "phase"
    ANSWER_START = "answer_start"
    ANSWER_DELTA = "answer_delta"
    SOURCES = "sources"
    CLARIFICATION = "clarification"
    TOOL_STATUS = "tool_status"
    DONE = "done"
    ERROR = "error"
    PING = "ping"


class StreamEvent(BaseModel):
    """
    Structured streaming event for HTTP SSE transport.
    Strictly forbids raw chain-of-thought or reasoning text fields.
    """
    type: str = Field(..., description="Event type: meta, phase, answer_start, answer_delta, sources, clarification, tool_status, done, error, ping")
    timestamp: float = Field(default_factory=time.time, description="Unix timestamp of event")
    conversation_id: Optional[str] = Field(None, description="Conversation ID")
    goal_id: Optional[str] = Field(None, description="Active goal ID")
    phase: Optional[str] = Field(None, description="Structured visible phase name")
    label: Optional[str] = Field(None, description="User-friendly progress label in Vietnamese")
    data: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Structured safe payload")

    @model_validator(mode="before")
    @classmethod
    def validate_no_reasoning_leakage(cls, values: Any) -> Any:
        if isinstance(values, dict):
            # Enforce zero raw chain-of-thought / reasoning leakage
            prohibited_keys = {"reasoning_text", "chain_of_thought", "raw_reasoning", "internal_prompt"}
            found = prohibited_keys.intersection(values.keys())
            if found:
                raise ValueError(f"Prohibited reasoning fields detected in StreamEvent: {found}")
            data_dict = values.get("data")
            if isinstance(data_dict, dict):
                found_data = prohibited_keys.intersection(data_dict.keys())
                if found_data:
                    raise ValueError(f"Prohibited reasoning fields detected in StreamEvent data: {found_data}")
        return values

    def to_sse(self) -> str:
        """Serialize event to standard SSE wire format."""
        dumped = self.model_dump(exclude_none=True)
        json_str = json.dumps(dumped, ensure_ascii=False)
        return f"event: {self.type}\ndata: {json_str}\n\n"


class AgentEventEmitter:
    """
    Observational event sink for Agent Core and chat execution.
    Pushes structured phase and tool status events to an external consumer.
    Strictly observational: exceptions are trapped to never break core execution.
    """

    def __init__(
        self,
        callback: Optional[Callable[[StreamEvent], None]] = None,
        conversation_id: Optional[str] = None,
        goal_id: Optional[str] = None,
    ):
        self.callback = callback
        self.conversation_id = conversation_id
        self.goal_id = goal_id

    def set_goal_id(self, goal_id: str) -> None:
        self.goal_id = goal_id

    def set_conversation_id(self, conversation_id: str) -> None:
        self.conversation_id = conversation_id

    def emit(
        self,
        type: str,
        phase: Optional[str] = None,
        label: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emit a structured event safely."""
        if not self.callback:
            return
        try:
            event = StreamEvent(
                type=type,
                timestamp=time.time(),
                conversation_id=self.conversation_id,
                goal_id=self.goal_id,
                phase=phase,
                label=label,
                data=data or {},
            )
            self.callback(event)
        except Exception:
            # Observational only: must never interrupt core logic
            pass

    def emit_phase(
        self,
        phase: str,
        label: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emit a safe visible phase transition."""
        self.emit(type=StreamEventType.PHASE, phase=phase, label=label, data=data)

    def emit_tool_status(
        self,
        label: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emit an authorized tool progress status."""
        self.emit(
            type=StreamEventType.TOOL_STATUS,
            phase=AgentPhase.ACT,
            label=label,
            data=data,
        )
