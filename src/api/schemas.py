"""
Pydantic Schemas cho FastAPI API endpoints.
"""
from typing import List, Optional, Dict
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="Câu hỏi hoặc yêu cầu của người dùng")
    conversation_id: Optional[str] = Field(None, description="ID phiên trò chuyện")


class SourceItem(BaseModel):
    source_file: str
    document_type: str
    course_code: Optional[str] = ""
    course_name: Optional[str] = ""
    section: Optional[str] = ""
    subsection: Optional[str] = ""
    chunk_id: Optional[str] = ""


class ChatMetadata(BaseModel):
    cache_hit: bool = False
    category: str = "DOMAIN_DATA"
    tool_intent: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    category: str
    sources: List[SourceItem] = Field(default_factory=list)
    conversation_id: str
    metadata: ChatMetadata


class ProfileData(BaseModel):
    name: Optional[str] = "Sinh viên CNTT"
    major: Optional[str] = "Công nghệ thông tin"
    cohort: Optional[str] = "K19"
    style: Optional[str] = "Thực hành"
    email: Optional[str] = "student@dainam.edu.vn"


class HealthResponse(BaseModel):
    status: str
    components: Dict[str, str]


class APIErrorDetails(BaseModel):
    code: str
    message: str


class APIErrorResponse(BaseModel):
    error: APIErrorDetails
