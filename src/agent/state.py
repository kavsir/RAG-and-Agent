from typing import TypedDict, List, Dict, Any, Optional


class AgentState(TypedDict):
    """Trạng thái làm việc của LangGraph Agent qua từng node."""
    # Thông tin đầu vào
    question: str
    conversation_id: str
    chat_history: str
    user_id: Optional[str]
    student_profile: Dict[str, Any]

    # Phân tích & Định tuyến
    rewritten_question: str
    category: str  # "DOMAIN_DATA" | "GENERAL_LLM" | "TOOL_ACTION"
    tool_intent: Optional[str]  # "SET_REMINDER" | "SEND_EMAIL" | None
    analyzed_query: Dict[str, Any]
    session_context: Optional[Dict[str, Any]]
    resolved_entities: Dict[str, Any]
    resolution_source: str

    # Cache Policy (Context-Safe)
    cache_policy: Optional[Dict[str, Any]]

    # RAG Retrieval & Context
    retrieved_docs: List[Dict[str, Any]]
    context: str
    sources: List[Dict[str, Any]]

    # Sinh câu trả lời & Kiểm định
    answer: str
    validation_result: Dict[str, Any]
    retry_count: int

    # Tool Action payloads
    reminder_request: Optional[Dict[str, Any]]
    email_request: Optional[Dict[str, Any]]

    # Performance
    cache_hit: bool
