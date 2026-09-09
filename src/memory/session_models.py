"""
Session Memory Models: Định nghĩa các Pydantic schema có kiểu cho phiên làm việc,
tin nhắn hội thoại và trạng thái thực thể có cấu trúc (SessionState).
"""
import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class SessionRecord(BaseModel):
    """Bản ghi phiên hội thoại trong cơ sở dữ liệu."""
    conversation_id: str
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))
    updated_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))
    last_activity_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))
    status: str = "active"
    metadata_json: Optional[str] = None


class SessionMessage(BaseModel):
    """Tin nhắn đơn lẻ thuộc về một phiên hội thoại xác định."""
    id: Optional[int] = None
    conversation_id: str
    role: str  # "user" | "assistant" | "system"
    content: str
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))


class SessionState(BaseModel):
    """
    Trạng thái thực thể và ngữ cảnh hội thoại có cấu trúc của một phiên (SessionState).
    Phục vụ giải quyết đại từ thay thế, chuyển đổi thực thể (entity switching)
    và kế thừa mục tiêu (target carry-over) một cách tất định.
    """
    conversation_id: str
    active_course_code: Optional[str] = None
    active_course_name: Optional[str] = None
    active_entity_type: Optional[str] = None  # "course" | "lecturer" | "regulation" | "curriculum"
    active_entities: Dict[str, Any] = Field(default_factory=dict)
    active_target: Optional[str] = None  # "credits" | "lecturer" | "clo" | "assessment" | ...
    last_source_ids: List[str] = Field(default_factory=list)
    unresolved_reference: bool = False

    # ROUND P2: Conversational Subject State (Discourse State)
    last_academic_entity: Optional[str] = None
    last_entity_type: Optional[str] = None
    last_intent: Optional[str] = None
    last_scope: Optional[str] = None
    last_requested_fields: List[str] = Field(default_factory=list)
    last_completed_goal_id: Optional[str] = None

    updated_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))

    def to_context_dict(self) -> Dict[str, Any]:
        """Chuyển đổi sang dict ngữ cảnh truyền cho Query Analyzer, Goal Analyzer và Router."""
        entity = self.last_academic_entity or self.active_course_code
        return {
            "conversation_id": self.conversation_id,
            "course_code": entity,
            "active_course_code": entity,
            "active_course": entity,
            "active_entity": entity,
            "course_name": self.active_course_name,
            "entity_type": self.last_entity_type or self.active_entity_type or "course",
            "active_target": self.active_target,
            "last_academic_entity": entity,
            "last_entity_type": self.last_entity_type or self.active_entity_type or "course",
            "last_intent": self.last_intent,
            "last_scope": self.last_scope,
            "last_requested_fields": self.last_requested_fields,
            "last_completed_goal_id": self.last_completed_goal_id,
            "unresolved_reference": self.unresolved_reference,
            "last_source_ids": self.last_source_ids,
        }
