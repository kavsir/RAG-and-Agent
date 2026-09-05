"""
Schemas cho Router V2: Định nghĩa các kiểu dữ liệu cho phân loại ý định cục bộ.
"""
from typing import Optional, Dict, Any, Literal
from pydantic import BaseModel, Field

IntentCategory = Literal["DOMAIN_DATA", "GENERAL_LLM", "TOOL_ACTION"]
ToolIntent = Optional[Literal["SET_REMINDER", "SEND_EMAIL"]]
EvidenceStrength = Literal["STRONG", "WEAK", "NONE"]
DecisionPath = Literal[
    "STRONG_TOOL_FAST_PATH",
    "STRONG_DOMAIN_FAST_PATH",
    "STRONG_GENERAL_FAST_PATH",
    "SEMANTIC_CLASSIFIER",
    "LOW_CONFIDENCE_FALLBACK",
]


class RouterEvidence(BaseModel):
    """Thông tin bằng chứng có cấu trúc bóc tách từ câu hỏi."""
    course_code: Optional[str] = None
    course_code_strength: EvidenceStrength = "NONE"
    course_name_signal: Optional[str] = None
    academic_scope: bool = False
    curriculum_scope: bool = False
    regulation_scope: bool = False
    academic_target: Optional[str] = None
    target_strength: EvidenceStrength = "NONE"
    tool_action: Optional[str] = None
    tool_object: Optional[str] = None
    tool_intent: ToolIntent = None
    tool_strength: EvidenceStrength = "NONE"
    conceptual_question_signal: bool = False


class IntentDecision(BaseModel):
    """Kết quả phân loại ý định chuẩn hóa từ Router V2."""
    category: IntentCategory
    tool_intent: ToolIntent = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    reason_code: str
    decision_path: DecisionPath
    evidence: Dict[str, Any] = Field(default_factory=dict)
