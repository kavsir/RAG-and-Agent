from typing import TypedDict, List, Dict, Any

class AgentState(TypedDict):
    question: str
    rewritten_question: str
    intent: str
    category: str  # DOMAIN_DATA hoặc GENERAL_LLM
    plan: str
    retrieved_docs: List[Any]
    context: str
    answer: str
    reflection: str
    student_profile: Dict[str, Any]
    chat_history: str
    messages: List[Dict[str, str]]
    validation_result: Dict[str, Any]
    regenerate_count: int
    retry_count: int  # Track retries to prevent infinite loops
    skip_pipeline: bool
    reminder_requests: List[Dict[str, Any]]
    reminder_results: List[Dict[str, Any]]
    email_requests: List[Dict[str, Any]]
    email_results: List[Dict[str, Any]]
    intents_list: List[str]   