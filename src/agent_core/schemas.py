"""
Schemas & Data Models for Goal-Driven Agent Core V1.1.
Implements typed structures for goals, observations, plans, evidence,
progress snapshots, and anti-loop tracking.
Enforces zero chain-of-thought text fields and complete evidence provenance.
"""
from enum import Enum
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from src.agent_core.cardinality import FieldCardinality, get_field_cardinality, FIELD_CARDINALITY_POLICY

__all__ = [
    "FieldCardinality",
    "get_field_cardinality",
    "FIELD_CARDINALITY_POLICY",
    "EntityType",
    "AcademicEntity",
    "AcademicOperation",
    "AcademicQueryPlan",
    "GoalIntent",
    "GoalScope",
    "AggregationType",
    "ReferentType",
    "ComparisonType",
    "GoalFrame",
    "validate_goal_frame",
]


class EntityType(str, Enum):
    COURSE = "COURSE"
    COHORT = "COHORT"
    MAJOR = "MAJOR"
    SEMESTER = "SEMESTER"
    CURRICULUM = "CURRICULUM"
    REGULATION = "REGULATION"
    PERSON = "PERSON"
    GENERAL_TOPIC = "GENERAL_TOPIC"


class AcademicEntity(BaseModel):
    """Thực thể học vụ có kiểu (Round A1)."""
    type: EntityType
    value: str
    canonical_id: Optional[str] = None
    confidence: float = 1.0
    resolution_source: str = "explicit"


class AcademicOperation(str, Enum):
    LIST_COURSES = "LIST_COURSES"
    GET_SEMESTER_COURSES = "GET_SEMESTER_COURSES"
    FIND_COURSE_SEMESTER = "FIND_COURSE_SEMESTER"
    GET_TOTAL_CREDITS = "GET_TOTAL_CREDITS"
    LOOKUP_FIELD = "LOOKUP_FIELD"
    REGULATION_LOOKUP = "REGULATION_LOOKUP"
    COMPARE_COURSES = "COMPARE_COURSES"
    TOOL_EXECUTION = "TOOL_EXECUTION"


class ResultScope(str, Enum):
    """Phạm vi số lượng kết quả người dùng yêu cầu (Round A1.2)."""
    SUMMARY = "SUMMARY"
    PAGE = "PAGE"
    TOP_K = "TOP_K"
    ALL = "ALL"


class AcademicCollectionResult(BaseModel):
    """
    Hợp đồng kết quả tập hợp tri thức học vụ (Round A1.2 Result Cardinality Contract).
    Bảo đảm tính minh bạch về số lượng bản ghi và cấm cắt ngắn ngầm định (SILENT_RESULT_TRUNCATION = 0).
    """
    items: List[Dict[str, Any]] = Field(default_factory=list)
    total_count: int = 0
    returned_count: int = 0
    is_complete: bool = True
    truncation_reason: Optional[str] = None
    result_scope: ResultScope = ResultScope.ALL
    page: Optional[int] = None
    limit: Optional[int] = None

    def model_post_init(self, __context: Any) -> None:
        if self.result_scope == ResultScope.ALL:
            if self.total_count > 0 and self.returned_count != self.total_count:
                raise ValueError(
                    f"ALL_SCOPE_INCOMPLETE_RESULT: ResultScope.ALL requires returned_count ({self.returned_count}) == total_count ({self.total_count})"
                )
            self.is_complete = True
            self.truncation_reason = None
        elif self.returned_count < self.total_count:
            self.is_complete = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "items": self.items,
            "total_count": self.total_count,
            "returned_count": self.returned_count,
            "is_complete": self.is_complete,
            "truncation_reason": self.truncation_reason,
            "result_scope": self.result_scope.value,
            "page": self.page,
            "limit": self.limit,
        }


class AcademicQueryPlan(BaseModel):
    """Kế hoạch truy vấn tri thức học vụ có kiểu (Round A1 & A1.2)."""
    plan_id: str
    subject_type: EntityType
    operation: str
    filters: Dict[str, Any] = Field(default_factory=dict)
    projection: List[str] = Field(default_factory=list)
    data_capability: str
    accepted_sources: List[str] = Field(default_factory=list)
    evidence_requirements: List[Any] = Field(default_factory=list)
    result_scope: ResultScope = ResultScope.ALL
    limit: Optional[int] = None
    page: Optional[int] = None


class GoalIntent(str, Enum):
    COURSE_OVERVIEW = "COURSE_OVERVIEW"
    COURSE_FULL_DETAILS = "COURSE_FULL_DETAILS"
    COURSE_FIELD_LOOKUP = "COURSE_FIELD_LOOKUP"
    COURSE_COMPARISON = "COURSE_COMPARISON"
    CURRICULUM_OVERVIEW = "CURRICULUM_OVERVIEW"
    REGULATION_LOOKUP = "REGULATION_LOOKUP"
    GENERAL_TOPIC_EXPLANATION = "GENERAL_TOPIC_EXPLANATION"
    TOOL_ACTION = "TOOL_ACTION"
    UNKNOWN = "UNKNOWN"


class GoalScope(str, Enum):
    SINGLE_FIELD = "SINGLE_FIELD"
    SUMMARY = "SUMMARY"
    ALL_AVAILABLE = "ALL_AVAILABLE"
    FILTERED_SET = "FILTERED_SET"


class AggregationType(str, Enum):
    NONE = "NONE"
    COUNT = "COUNT"
    LIST = "LIST"
    MAX = "MAX"
    MIN = "MIN"
    COMPARE = "COMPARE"


class ReferentType(str, Enum):
    EXPLICIT = "EXPLICIT"
    PREVIOUS_ENTITY = "PREVIOUS_ENTITY"
    PREVIOUS_INTENT = "PREVIOUS_INTENT"
    PRONOUN = "PRONOUN"
    NONE = "NONE"


class ComparisonType(str, Enum):
    NONE = "NONE"
    GREATER_THAN = "GREATER_THAN"
    LESS_THAN = "LESS_THAN"
    EQUAL = "EQUAL"
    COMPARE = "COMPARE"


class GoalFrame(BaseModel):
    """
    Typed Semantic Goal Frame biểu diễn ý định và cấu trúc mục tiêu của người dùng (Round P2.1 & A1).
    TUYỆT ĐỐI KHÔNG lưu chain_of_thought hay reasoning_text tự do.
    """
    intent: GoalIntent = GoalIntent.UNKNOWN
    subjects: List[AcademicEntity] = Field(default_factory=list)
    subject_type: Optional[EntityType] = None
    operation: Optional[str] = None
    entities: List[str] = Field(default_factory=list)
    referents: List[ReferentType] = Field(default_factory=list)
    requested_fields: List[str] = Field(default_factory=list)
    scope: GoalScope = GoalScope.SINGLE_FIELD
    constraints: List[str] = Field(default_factory=list)
    aggregation: AggregationType = AggregationType.NONE
    comparison: ComparisonType = ComparisonType.NONE
    tool_action: Optional[str] = None
    confidence: float = 1.0
    confidence_margin: float = 1.0
    missing_slots: List[str] = Field(default_factory=list)
    resolution_sources: Dict[str, str] = Field(default_factory=dict)
    unsupported_reason: Optional[str] = None
    suggested_alternative: Optional[str] = None
    result_scope: ResultScope = ResultScope.ALL
    limit: Optional[int] = None
    page: Optional[int] = None


def validate_goal_frame(frame: GoalFrame) -> List[str]:
    """
    Kiểm tra tính nhất quán nội tại của GoalFrame trước khi chuyển sang Planner.
    Đảm bảo Planner không bao giờ nhận một GoalFrame mâu thuẫn nội tại.
    Trả về danh sách các lỗi không nhất quán nếu có.
    """
    errors: List[str] = []

    # 0. Kiểm tra ngưỡng tin cậy (Confidence bounds)
    if not (0.0 <= frame.confidence <= 1.0):
        errors.append("Confidence must be between 0.0 and 1.0.")
    if frame.confidence_margin < 0.0:
        errors.append("Confidence margin cannot be negative.")

    # 1. Kiểm tra mâu thuẫn đối với so sánh
    if frame.intent == GoalIntent.COURSE_COMPARISON:
        if len(frame.entities) < 2 and not frame.missing_slots:
            errors.append("COURSE_COMPARISON requires at least 2 entities or an unresolved missing entity slot.")
        if frame.aggregation == AggregationType.NONE:
            frame.aggregation = AggregationType.COMPARE

    # 2. Kiểm tra Tool Action
    if frame.intent == GoalIntent.TOOL_ACTION:
        if not frame.tool_action:
            errors.append("TOOL_ACTION intent requires a defined tool_action.")

    # 3. Kiểm tra Filtered Set
    if frame.scope == GoalScope.FILTERED_SET:
        if not frame.constraints and not frame.requested_fields:
            errors.append("FILTERED_SET requires either explicit constraints or requested fields.")

    # 4. Kiểm tra Aggregation COUNT/LIST
    if frame.aggregation in (AggregationType.COUNT, AggregationType.LIST):
        if not frame.requested_fields and not frame.constraints:
            errors.append(f"Aggregation {frame.aggregation.value} requires target field or constraint.")

    # 5. Kiểm tra tính nhất quán kiểu mục tiêu học vụ (Round A1 Invariants)
    import re
    # CURRICULUM_GOAL_WITH_COURSE_ONLY_PLAN: mục tiêu curriculum không được chứa course entity làm đối tượng chính duy nhất
    if frame.intent == GoalIntent.CURRICULUM_OVERVIEW or frame.subject_type in (EntityType.CURRICULUM, EntityType.COHORT):
        if frame.operation != "FIND_COURSE_SEMESTER":
            has_course_subject = any(s.type == EntityType.COURSE for s in frame.subjects)
            has_curriculum_or_cohort = any(s.type in (EntityType.CURRICULUM, EntityType.COHORT, EntityType.MAJOR, EntityType.SEMESTER) for s in frame.subjects)
            if has_course_subject and not has_curriculum_or_cohort:
                errors.append("CURRICULUM_GOAL_WITH_COURSE_ONLY_PLAN: Curriculum goal cannot contain only course entity.")

    # COHORT_AS_COURSE_CODE: giá trị khóa học/khóa tuyển sinh không được là mã môn học
    for s in frame.subjects:
        if s.type == EntityType.COHORT and re.match(r"^[A-Za-z]{2,4}\d{4}$", s.value):
            errors.append(f"COHORT_AS_COURSE_CODE: Cohort value '{s.value}' cannot be a course code.")

    return errors


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
    EXECUTE_STRUCTURED_QUERY = "EXECUTE_STRUCTURED_QUERY"
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
    """Đặc tả bằng chứng cần thu thập cho một thực thể học vụ cụ thể (Round A1 Type-Aware)."""
    entity: str = ""
    subject_type: EntityType = EntityType.COURSE
    subject_id: str = ""
    field: str = ""
    accepted_document_types: List[str] = Field(default_factory=list)
    data_capability: Optional[str] = None
    filters: Dict[str, Any] = Field(default_factory=dict)
    status: EvidenceStatus = EvidenceStatus.PENDING
    extracted_value: Optional[Any] = None
    source_doc_id: Optional[str] = None
    source_title: Optional[str] = None
    confidence: float = 0.0
    attempt_count: int = 0

    def __init__(self, **data):
        super().__init__(**data)
        if not self.entity and self.subject_id:
            self.entity = self.subject_id
        elif not self.subject_id and self.entity:
            self.subject_id = self.entity

    @property
    def requirement_key(self) -> str:
        s_id = self.subject_id or self.entity
        return f"{self.subject_type.value}:{s_id}.{self.field}"


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
    target_requirement_key: Optional[str] = None


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
    intent: GoalIntent = GoalIntent.UNKNOWN
    scope: GoalScope = GoalScope.SINGLE_FIELD
    objectives: List[GoalType] = Field(default_factory=list)
    entities: List[str] = Field(default_factory=list)
    referents: List[ReferentType] = Field(default_factory=list)
    requested_fields: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    aggregation: AggregationType = AggregationType.NONE
    comparison: ComparisonType = ComparisonType.NONE
    goal_frame: Optional[GoalFrame] = None
    subjects: List[AcademicEntity] = Field(default_factory=list)
    subject_type: Optional[EntityType] = None
    operation: Optional[str] = None
    query_plan: Optional[AcademicQueryPlan] = None
    is_multi_entity: bool = False
    is_multi_intent: bool = False
    unsupported_intents: List[str] = Field(default_factory=list)
    goal_clarity: str = "CLEAR"  # CLEAR | UNDERSPECIFIED | AMBIGUOUS
    missing_slot: Optional[str] = None  # "intent" | "entity" | "data" | "entity_conflict"
    clarification_prompt: Optional[str] = None
    clarification_options: List[str] = Field(default_factory=list)
    unsupported_reason: Optional[str] = None
    suggested_alternative: Optional[str] = None
    result_scope: ResultScope = ResultScope.ALL
    limit: Optional[int] = None
    page: Optional[int] = None


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
    intent: GoalIntent = GoalIntent.UNKNOWN
    scope: GoalScope = GoalScope.SINGLE_FIELD
    objectives: List[GoalType] = Field(default_factory=list)
    entities: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    aggregation: AggregationType = AggregationType.NONE
    comparison: ComparisonType = ComparisonType.NONE
    goal_frame: Optional[GoalFrame] = None
    subjects: List[AcademicEntity] = Field(default_factory=list)
    subject_type: Optional[EntityType] = None
    operation: Optional[str] = None
    query_plan: Optional[AcademicQueryPlan] = None
    requirements: List[EvidenceRequirement] = Field(default_factory=list)
    evidence: List[EvidenceItem] = Field(default_factory=list)
    missing_information: List[str] = Field(default_factory=list)
    result_scope: ResultScope = ResultScope.ALL
    limit: Optional[int] = None
    page: Optional[int] = None

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
    alternative_execution_attempts_before_authorization: int = 0

    # Đầu ra cuối cùng
    final_answer: Optional[str] = None
