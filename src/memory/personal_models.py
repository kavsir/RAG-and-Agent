"""
Personal Memory Models: Định nghĩa cấu trúc dữ liệu, danh sách khóa cho phép (whitelist),
nguồn gốc (provenance), sự kiện vòng đời (audit events), và kết quả ghi nhận bộ nhớ cá nhân.
"""
import uuid
import datetime
from typing import Optional, Any, Set, Dict
from pydantic import BaseModel, Field

# Danh sách các khóa thông tin cá nhân được phép ghi nhận (Whitelist)
SUPPORTED_FACT_KEYS: Set[str] = {
    "preferred_name",
    "major",
    "cohort",
    "current_semester",
    "preferred_language",
    "response_style",
    "learning_goal",
    "own_email",
    "specialization",
}

# Các giá trị mặc định giao diện giả định cần LOẠI BỎ, không bao giờ được coi là sự thật người dùng
KNOWN_PLACEHOLDER_DEFAULTS: Dict[str, Any] = {
    "name": "Sinh viên CNTT",
    "preferred_name": "Sinh viên CNTT",
    "major": "Công nghệ thông tin",
    "cohort": "K19",
    "style": "Thực hành",
    "response_style": "Thực hành",
    "email": "student@dainam.edu.vn",
    "own_email": "student@dainam.edu.vn",
}

# Các nguồn gốc dữ liệu hợp lệ (Provenance)
SOURCE_EXPLICIT_USER = "EXPLICIT_USER"
SOURCE_PROFILE_API = "PROFILE_API"
SOURCE_SYSTEM_DEFAULT = "SYSTEM_DEFAULT"
SOURCE_MIGRATED_LEGACY = "MIGRATED_LEGACY"


class PersonalFact(BaseModel):
    """
    Một sự thật cá nhân hoặc sở thích bền vững của người dùng.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    fact_key: str
    value: Any
    source_type: str = SOURCE_EXPLICIT_USER
    confidence: float = 1.0
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))
    updated_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))
    expires_at: Optional[datetime.datetime] = None
    status: str = "ACTIVE"  # "ACTIVE" | "DELETED" | "INACTIVE"


class MemoryEvent(BaseModel):
    """
    Bản ghi kiểm toán vòng đời của sự thật cá nhân (Audit Event).
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    event_type: str  # "CREATE" | "UPDATE" | "DELETE" | "DELETE_ALL" | "MIGRATE" | "REJECT"
    fact_key: str
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    source_type: str
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))


class MemoryWriteResult(BaseModel):
    """
    Kết quả có cấu trúc sau khi xử lý ứng viên bộ nhớ qua chính sách.
    """
    action: str  # "CREATED" | "UPDATED" | "UNCHANGED" | "REJECTED" | "DELETED"
    fact_key: str
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    source_type: str
    reason: Optional[str] = None
