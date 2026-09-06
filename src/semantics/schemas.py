"""
Schemas and Data Models for Utterance Semantics and Action Authorization.
Part of Round S1: Utterance Semantics + Tool Action Safety Gate.
Strictly local, typed, and side-effect safe.
"""
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class Polarity(str, Enum):
    """Tính phân cực ngữ nghĩa của phát ngôn."""
    AFFIRMATIVE = "AFFIRMATIVE"      # Khẳng định: "Gửi email cho thầy", "Tôi học K19"
    NEGATED = "NEGATED"              # Phủ định: "Đừng gửi email", "Tôi không học K19"
    MIXED = "MIXED"                  # Lai ghép: "Soạn email nhưng đừng gửi"
    UNKNOWN = "UNKNOWN"              # Chưa xác định


class Modality(str, Enum):
    """Phương thức / Giọng điệu của phát ngôn."""
    DIRECT = "DIRECT"                # Mệnh lệnh / Khẳng định trực tiếp
    QUESTION = "QUESTION"            # Câu hỏi thông tin chung: "Môn này mấy tín chỉ?"
    HYPOTHETICAL = "HYPOTHETICAL"    # Giả định / Phản thực tế: "Nếu tôi gửi email...", "Giả sử tôi học K19..."
    CONDITIONAL = "CONDITIONAL"      # Điều kiện chưa thỏa mãn: "Khi nào thi xong thì nhắc tôi"
    EXPLANATORY = "EXPLANATORY"      # Yêu cầu giải thích khái niệm: "Email là gì?", "Cách đặt lịch nhắc thế nào?"
    UNKNOWN = "UNKNOWN"              # Chưa xác định


class SubjectScope(str, Enum):
    """Đối tượng chủ thể của thông tin / hành động."""
    SELF = "SELF"                    # Bản thân người dùng: "Tôi", "mình", "em"
    THIRD_PARTY = "THIRD_PARTY"      # Bên thứ ba: "Bạn tôi", "Anh tôi", "Người khác"
    UNKNOWN = "UNKNOWN"              # Không rõ chủ thể


class ActionOperation(str, Enum):
    """Các thao tác công cụ được phân tách rõ ràng theo mức độ tác động."""
    COMPOSE_EMAIL = "COMPOSE_EMAIL"  # Soạn thảo bản nháp email (AN TOÀN - KHÔNG PHẢI SIDE EFFECT)
    SEND_EMAIL = "SEND_EMAIL"        # Gửi email thực tế qua SMTP (SIDE EFFECT NGUY HIỂM)
    SET_REMINDER = "SET_REMINDER"    # Đặt lịch hẹn qua Scheduler (SIDE EFFECT)
    NO_ACTION = "NO_ACTION"          # Không thực hiện hành động nào
    CLARIFY = "CLARIFY"              # Yêu cầu người dùng làm rõ do mâu thuẫn/mơ hồ


class UtteranceSemantics(BaseModel):
    """Tín hiệu ngữ nghĩa có cấu trúc trích xuất từ phát ngôn của người dùng."""
    raw_text: str
    normalized_text: str
    polarity: Polarity = Polarity.UNKNOWN
    modality: Modality = Modality.UNKNOWN
    subject_scope: SubjectScope = SubjectScope.UNKNOWN
    is_contradictory: bool = False
    prohibition_detected: bool = False
    action_requests: List[ActionOperation] = Field(default_factory=list)
    action_prohibitions: List[ActionOperation] = Field(default_factory=list)
    target_operation: ActionOperation = ActionOperation.NO_ACTION
    details: Dict[str, Any] = Field(default_factory=dict)


class ActionAuthorizationDecision(BaseModel):
    """Quyết định cấp phép hành động công cụ (Action Authorization Gate)."""
    operation: Optional[ActionOperation] = None
    authorized: bool = False
    side_effect: bool = False
    reason_code: str = "DEFAULT_DENY"
    requires_clarification: bool = False
    clarification_message: Optional[str] = None
    safe_response: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
