"""
API Router: Định nghĩa các endpoints cho dịch vụ AI Academic Advisor.
"""
import uuid
import logging
from fastapi import APIRouter, HTTPException

from src.config.settings import settings
from src.agent.graph import graph
from src.memory.memory_manager import get_memory_manager
from src.cache.exact_cache import get_exact_cache
from src.api.schemas import (
    ChatRequest,
    ChatResponse,
    ChatMetadata,
    SourceItem,
    ProfileData,
    HealthResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health_check():
    """Kiểm tra tình trạng hoạt động của toàn bộ hệ thống."""
    # 1. Kiểm tra Vector Store
    vector_status = "ok" if settings.CHROMA_PATH.exists() else "not_found"

    # 2. Kiểm tra BM25
    bm25_files = list(settings.CHROMA_PATH.glob("bm25_*.pkl"))
    bm25_status = "ok" if len(bm25_files) >= 3 else "partial_or_missing"

    # 3. Kiểm tra LLM Configuration
    llm_status = "configured" if settings.LLM_API_KEY and settings.LLM_API_KEY not in ("", "#", "your_api_key_here") else "mock_or_unconfigured"

    # 4. Kiểm tra Email
    email_status = "enabled" if settings.EMAIL_ENABLED else "disabled"

    components = {
        "vector_store": vector_status,
        "bm25": bm25_status,
        "llm": llm_status,
        "email": email_status,
        "reranker": "enabled" if settings.ENABLE_RERANKER else "disabled",
    }
    overall_status = "ok" if vector_status == "ok" else "warning"

    return HealthResponse(status=overall_status, components=components)


@router.post("/api/chat", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest):
    """Xử lý câu hỏi của người dùng thông qua LangGraph Agent."""
    conv_id = request.conversation_id or str(uuid.uuid4())
    memory_mgr = get_memory_manager()

    history_text = memory_mgr.get_conversation_history(k=5)
    profile = memory_mgr.profile.get_profile()

    initial_state = {
        "question": request.message,
        "conversation_id": conv_id,
        "chat_history": history_text,
        "student_profile": profile,
        "rewritten_question": "",
        "category": "DOMAIN_DATA",
        "tool_intent": None,
        "analyzed_query": {},
        "retrieved_docs": [],
        "context": "",
        "sources": [],
        "answer": "",
        "validation_result": {},
        "retry_count": 0,
        "reminder_request": None,
        "email_request": None,
        "cache_hit": False,
    }

    try:
        final_state = graph.invoke(initial_state)

        answer = final_state.get("answer", "Xin lỗi, không có phản hồi.")
        category = final_state.get("category", "DOMAIN_DATA")
        sources_raw = final_state.get("sources", [])
        cache_hit = final_state.get("cache_hit", False)
        tool_intent = final_state.get("tool_intent")

        # Nếu câu trả lời là từ chối do thiếu dữ liệu, đảm bảo danh sách nguồn rỗng
        if "chưa tìm thấy đủ dữ liệu" in answer.lower():
            sources_raw = []

        # Chuẩn hóa danh sách sources sang schema SourceItem
        sources_list = []
        for s in sources_raw:
            sources_list.append(
                SourceItem(
                    source_file=s.get("source_file", ""),
                    document_type=s.get("document_type", ""),
                    course_code=s.get("course_code", ""),
                    course_name=s.get("course_name", ""),
                    section=s.get("section", ""),
                    subsection=s.get("subsection", ""),
                    chunk_id=s.get("chunk_id", ""),
                )
            )

        return ChatResponse(
            answer=answer,
            category=category,
            sources=sources_list,
            conversation_id=conv_id,
            metadata=ChatMetadata(
                cache_hit=cache_hit,
                category=category,
                tool_intent=tool_intent,
            ),
        )
    except Exception as e:
        logger.error(f"Lỗi khi thực thi chat agent: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Lỗi xử lý yêu cầu: {str(e)}")


@router.post("/api/conversations/clear")
def clear_conversation():
    """Xóa toàn bộ lịch sử trò chuyện và bộ nhớ đệm."""
    memory_mgr = get_memory_manager()
    memory_mgr.clear()

    cache = get_exact_cache()
    cache.clear()

    return {"status": "ok", "message": "Đã làm mới hội thoại và xóa cache thành công."}


@router.get("/api/profile", response_model=ProfileData)
def get_profile():
    """Lấy thông tin hồ sơ sinh viên hiện tại."""
    memory_mgr = get_memory_manager()
    data = memory_mgr.profile.get_profile()
    return ProfileData(**data)


@router.put("/api/profile", response_model=ProfileData)
def update_profile(data: ProfileData):
    """Cập nhật thông tin hồ sơ sinh viên."""
    memory_mgr = get_memory_manager()
    memory_mgr.profile.update_profile(data.model_dump())
    updated = memory_mgr.profile.get_profile()
    return ProfileData(**updated)
