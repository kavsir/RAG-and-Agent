"""
Schemas & Data Models for Goal-Driven Agent Core V1.1.
Implements typed structures for goals, observations, plans, evidence,
progress snapshots, and anti-loop tracking.
Enforces zero chain-of-thought text fields and complete evidence provenance.
"""
from enum import Enum
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class GoalType(str, Enum):
    LOOKUP_CREDITS = "LOOKUP_CREDITS"
    LOOKUP_LECTURER = "LOOKUP_LECTURER"
    LOOKUP_LECTURER_EMAIL = "LOOKUP_LECTURER_EMAIL"
    LOOKUP_PREREQUISITES = "LOOKUP_PREREQUISITES"
    LOOKUP_ASSESSMENT = "LOOKUP_ASSESSMENT"
    LOOKUP_CLO = "LOOKUP_CLO"
    LOOKUP_SCHEDULE = "LOOKUP_SCHEDULE"
    LOOKUP_COURSE_PLAN = "LOOKUP_COURSE_PLAN"
    LOOKUP_REGULATION = "LOOKUP_REGULATION"
    COMPARE_COURSES = "COMPARE_COURSES"
    SET_REMINDER = "SET_REMINDER"
    SEND_EMAIL = "SEND_EMAIL"
    GENERAL_KNOWLEDGE = "GENERAL_KNOWLEDGE"
    UNDEFINED = "UNDEFINED"


class AgentStatus(str, Enum):
    NEW = "NEW"
    UNDERSTANDING = "UNDERSTANDING"
    NEEDS_USER_INPUT = "NEEDS_USER_INPUT"
    PLANNING = "PLANNING"
    ACTING = "ACTING"
    VERIFYING = "VERIFYING"
    REPLANNING = "REPLANNING"
    PARTIAL = "PARTIAL"
    COMPLETED = "COMPLETED"
    ABSTAINED = "ABSTAINED"
    FAILED_SAFE = "FAILED_SAFE"


class StopReason(str, Enum):
    GOAL_COMPLETED = "GOAL_COMPLETED"
    USER_INPUT_REQUIRED = "USER_INPUT_REQUIRED"
    UNKNOWN_ENTITY = "UNKNOWN_ENTITY"
    ENTITY_CONFLICT = "ENTITY_CONFLICT"
    DATA_NOT_AVAILABLE = "DATA_NOT_AVAILABLE"
    PARTIAL_EVIDENCE = "PARTIAL_EVIDENCE"
    NO_PROGRESS = "NO_PROGRESS"
    DUPLICATE_ACTION = "DUPLICATE_ACTION"
    MAX_ITERATIONS = "MAX_ITERATIONS"
    SAFETY_BLOCK = "SAFETY_BLOCK"
    UNSUPPORTED_CAPABILITY = "UNSUPPORTED_CAPABILITY"
    FAILED = "FAILED"


class EvidenceStatus(str, Enum):
    PENDING = "PENDING"
    SATISFIED = "SATISFIED"
    VERIFIED_VALUE = "VERIFIED_VALUE"
    VERIFIED_NONE = "VERIFIED_NONE"
    MISSING = "MISSING"
    CONFLICTING = "CONFLICTING"
    INSUFFICIENT = "INSUFFICIENT"
    NOT_AVAILABLE = "NOT_AVAILABLE"
    AMBIGUOUS = "AMBIGUOUS"


class ActionType(str, Enum):
    CATALOG_LOOKUP = "CATALOG_LOOKUP"
    RETRIEVE_EXACT = "RETRIEVE_EXACT"
    RETRIEVE_EXPANDED = "RETRIEVE_EXPANDED"
    COMPARE_EVIDENCE = "COMPARE_EVIDENCE"
    ASK_USER = "ASK_USER"
    PARTIAL_ANSWER = "PARTIAL_ANSWER"
    ABSTAIN = "ABSTAIN"
    FINISH = "FINISH"
    PENDING_CAPABILITY = "PENDING_CAPABILITY"


class QuestionType(str, Enum):
    MISSING_INTENT = "MISSING_INTENT"
    MISSING_ENTITY = "MISSING_ENTITY"
    ENTITY_CONFLICT = "ENTITY_CONFLICT"
    MISSING_DATA_ALTERNATIVE = "MISSING_DATA_ALTERNATIVE"
    CONFIRM_ACTION = "CONFIRM_ACTION"


class EvidenceRequirement(BaseModel):
    """Đặc tả bằng chứng cần thu thập cho một thực thể học vụ cụ thể."""
    entity: str
    field: str
    accepted_document_types: List[str] = Field(default_factory=list)
    filters: Dict[str, Any] = Field(default_factory=dict)
    status: EvidenceStatus = EvidenceStatus.PENDING
    extracted_value: Optional[Any] = None
    source_doc_id: Optional[str] = None
    source_title: Optional[str] = None
    confidence: float = 0.0
    attempt_count: int = 0

    @property
    def requirement_key(self) -> str:
        return f"{self.entity}.{self.field}"


class EvidenceItem(BaseModel):
    """Một mẩu dữ liệu bằng chứng đã được thẩm định từ môi trường tri thức kèm xuất xứ đầy đủ."""
    entity: str
    field: str
    document_type: str
    content: str
    source: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    is_authoritative: bool = True
    relevance_score: float = 1.0
    status: EvidenceStatus = EvidenceStatus.VERIFIED_VALUE
    source_file: Optional[str] = None
    chunk_id: Optional[str] = None
    section: Optional[str] = None
    extracted_at: Optional[str] = None
    retrieval_strategy: Optional[str] = None


class ActionFingerprint(BaseModel):
    """Định danh duy nhất một hành động để chống lặp hành động mù quáng."""
    action_type: ActionType
    entity: Optional[str] = None
    requested_field: Optional[str] = None
    document_type: Optional[str] = None
    metadata_filter: Optional[str] = None
    strategy: str = "exact"

    def to_string(self) -> str:
        return (
            f"{self.action_type.value}|{self.entity or '*'}|"
            f"{self.requested_field or '*'}|{self.document_type or '*'}|"
            f"{self.metadata_filter or '*'}|{self.strategy}"
        )


class ActionPlan(BaseModel):
    """Kế hoạch thực hiện một bước hành động tiếp theo của Agent."""
    action_id: str
    action_type: ActionType
    entity: Optional[str] = None
    requested_field: Optional[str] = None
    strategy: str = "exact"
    fingerprint: str
    reason_code: str
    ask_user_payload: Optional[Dict[str, Any]] = None


class ActionObservation(BaseModel):
    """Kết quả quan sát được sau khi thực thi một hành động cụ thể."""
    action_id: str
    action_type: ActionType
    success: bool
    documents_found: int = 0
    new_evidence_count: int = 0
    requirements_satisfied: List[str] = Field(default_factory=list)
    evidence_items: List[EvidenceItem] = Field(default_factory=list)
    raw_output: Optional[str] = None
    message: str = ""


class ProgressSnapshot(BaseModel):
    """Ảnh chụp tiến độ thực thi để phát hiện bế tắc (No-Progress Detection)."""
    iteration: int
    satisfied_requirements: List[str] = Field(default_factory=list)
    missing_requirements: List[str] = Field(default_factory=list)
    evidence_count: int = 0
    conflicting_requirements: List[str] = Field(default_factory=list)
    last_action_fingerprint: Optional[str] = None


class GoalSpec(BaseModel):
    """Đặc tả mục tiêu thực sự của người dùng sau giai đoạn UNDERSTAND."""
    objectives: List[GoalType] = Field(default_factory=list)
    entities: List[str] = Field(default_factory=list)
    requested_fields: List[str] = Field(default_factory=list)
    is_multi_entity: bool = False
    is_multi_intent: bool = False
    unsupported_intents: List[str] = Field(default_factory=list)
    goal_clarity: str = "CLEAR"  # CLEAR | UNDERSPECIFIED | AMBIGUOUS
    missing_slot: Optional[str] = None  # "intent" | "entity" | "data" | "entity_conflict"


class AgentObservation(BaseModel):
    """Tổng hợp quan sát có cấu trúc từ môi trường và các hệ thống con."""
    current_query: str
    semantics: Optional[Dict[str, Any]] = None
    session_context: Optional[Dict[str, Any]] = None
    active_entities: List[str] = Field(default_factory=list)
    personal_context: Optional[Dict[str, Any]] = None
    router_hint: Optional[Dict[str, Any]] = None
    catalog_known_entities: List[str] = Field(default_factory=list)
    catalog_unknown_entities: List[str] = Field(default_factory=list)
    entity_conflicts: List[Dict[str, Any]] = Field(default_factory=list)
    data_available_fields: List[str] = Field(default_factory=list)
    data_unavailable_fields: List[str] = Field(default_factory=list)


class AgentGoalState(BaseModel):
    """
    Trạng thái toàn diện của Agent theo dõi mục tiêu người dùng.
    TUYỆT ĐỐI KHÔNG LƯU chain_of_thought hay reasoning_text tự do.
    Mọi quyết định được biểu diễn thông qua cấu trúc dữ liệu tường minh.
    """
    goal_id: str
    original_query: str
    current_user_input: str
    user_id: Optional[str] = None
    conversation_id: Optional[str] = None
    objectives: List[GoalType] = Field(default_factory=list)
    entities: List[str] = Field(default_factory=list)
    requirements: List[EvidenceRequirement] = Field(default_factory=list)
    evidence: List[EvidenceItem] = Field(default_factory=list)
    missing_information: List[str] = Field(default_factory=list)

    # Quyết định hành động có cấu trúc (Structured Decision)
    planned_action: Optional[ActionPlan] = None
    attempted_actions: List[str] = Field(default_factory=list)  # Lưu các fingerprint đã chạy
    action_history: List[ActionObservation] = Field(default_factory=list)
    progress_history: List[ProgressSnapshot] = Field(default_factory=list)

    # Giới hạn & Phòng vệ vòng lặp (Anti-loop Invariants)
    iteration: int = 0
    no_progress_count: int = 0
    status: AgentStatus = AgentStatus.NEW
    stop_reason: Optional[StopReason] = None

    # Tương tác con người (Human-in-the-loop)
    clarification_required: bool = False
    clarification_question: Optional[str] = None
    clarification_options: List[str] = Field(default_factory=list)
    clarification_type: Optional[QuestionType] = None

    # Đề xuất giải pháp thay thế có sự chấp thuận của người dùng
    alternative_proposed: bool = False
    alternative_authorized: bool = False
    alternative_proposal_text: Optional[str] = None

    # Đầu ra cuối cùng
    final_answer: Optional[str] = None
