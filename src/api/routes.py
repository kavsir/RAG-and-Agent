"""
API Router: Định nghĩa các endpoints cho dịch vụ AI Academic Advisor.
Tích hợp trực tiếp AgentCoreService vào đường dẫn chính POST /api/chat.
"""
import logging
from fastapi import APIRouter, HTTPException, Request

from src.config.settings import settings
from src.identity import resolve_principal
from src.memory.memory_manager import get_memory_manager
from src.cache.exact_cache import get_exact_cache
from src.api.chat_service import get_chat_execution_service
from src.api.streaming import create_chat_stream_response
from src.api.schemas import (
    ChatRequest,
    ChatResponse,
    ProfileData,
    HealthResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health_check():
    """Kiểm tra tình trạng hoạt động của toàn bộ hệ thống."""
    vector_status = "ok" if settings.CHROMA_PATH.exists() else "not_found"
    bm25_files = list(settings.CHROMA_PATH.glob("bm25_*.pkl"))
    bm25_status = "ok" if len(bm25_files) >= 3 else "partial_or_missing"
    llm_status = "configured" if settings.LLM_API_KEY and settings.LLM_API_KEY not in ("", "#", "your_api_key_here") else "mock_or_unconfigured"
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
    """
    Xử lý câu hỏi người dùng thông qua Goal-Driven Agent Core V1.1 (Blocking Endpoint).
    Hỗ trợ Human-in-the-loop multi-turn resumption cô lập theo (user_id, conv_id).
    Giữ nguyên 100% tương thích ngược với API client và các bài kiểm thử hiện có.
    """
    try:
        service = get_chat_execution_service()
        return service.process(request)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi thực thi chat agent: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Lỗi xử lý yêu cầu: {str(e)}")


@router.post("/api/chat/stream")
async def chat_stream_endpoint(request: ChatRequest, raw_request: Request):
    """
    Xử lý câu hỏi người dùng qua HTTP Streaming (text/event-stream).
    Cung cấp phản hồi tiến trình có cấu trúc (Structured Progress) theo thời gian thực.
    Đảm bảo 0 rò rỉ chain-of-thought và 0 stream unverified answer tokens.
    """
    try:
        return await create_chat_stream_response(request, raw_request)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi khởi tạo chat stream: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Lỗi khởi tạo stream: {str(e)}")


@router.delete("/api/conversations/{conversation_id}")
def delete_conversation_session(conversation_id: str):
    """Xóa riêng một phiên hội thoại cụ thể và giải phóng trạng thái thực thể của phiên đó."""
    memory_mgr = get_memory_manager()
    memory_mgr.clear_session(conversation_id)
    return {
        "status": "ok",
        "conversation_id": conversation_id,
        "message": f"Đã xóa thành công phiên hội thoại {conversation_id}."
    }


@router.post("/api/profile/reset")
def reset_student_profile():
    """Khởi tạo lại profile sinh viên về giá trị mặc định."""
    principal = resolve_principal()
    memory_mgr = get_memory_manager()
    memory_mgr.clear_personal_profile(principal.user_id)
    return {
        "status": "ok",
        "message": f"Đã reset toàn bộ sự thật cá nhân của user '{principal.user_id}'."
    }


@router.get("/api/conversations/{conversation_id}")
def get_conversation_session(conversation_id: str):
    """Lấy danh sách tin nhắn và trạng thái thực thể của đúng phiên hội thoại."""
    memory_mgr = get_memory_manager()
    messages = memory_mgr.get_recent_messages(conversation_id, k=50)
    state = memory_mgr.get_session_state(conversation_id)
    return {
        "conversation_id": conversation_id,
        "state": state.model_dump(),
        "messages": [m.model_dump() for m in messages],
    }


@router.post("/api/conversations/clear")
def clear_conversation():
    """Xóa toàn bộ lịch sử trò chuyện legacy và bộ nhớ đệm (giữ tương thích frontend)."""
    memory_mgr = get_memory_manager()
    memory_mgr.clear()

    cache = get_exact_cache()
    cache.clear()

    return {"status": "ok", "message": "Đã làm mới hội thoại và xóa cache thành công."}


@router.get("/api/profile", response_model=ProfileData)
def get_profile():
    """Lấy thông tin hồ sơ sinh viên hiện tại (ưu tiên Personal Memory đã xác thực)."""
    principal = resolve_principal()
    memory_mgr = get_memory_manager()
    facts = memory_mgr.get_personal_profile(user_id=principal.user_id)

    # Hiển thị dữ liệu thực tế đã lưu hoặc giá trị mặc định chỉ phục vụ trình bày (presentation default)
    return ProfileData(
        name=facts.get("preferred_name") or "Sinh viên",
        major=facts.get("major") or "Chưa khai báo",
        cohort=facts.get("cohort") or "Chưa khai báo",
        style=facts.get("response_style") or "Tiêu chuẩn",
        email=facts.get("own_email") or "Chưa khai báo",
    )


@router.put("/api/profile", response_model=ProfileData)
def update_profile(data: ProfileData):
    """Cập nhật thông tin hồ sơ sinh viên qua Personal Memory Service."""
    principal = resolve_principal()
    memory_mgr = get_memory_manager()
    user_id = principal.user_id

    # Đồng bộ sang Personal Memory có cấu trúc với nguồn gốc PROFILE_API
    field_map = {
        "name": "preferred_name",
        "major": "major",
        "cohort": "cohort",
        "style": "response_style",
        "email": "own_email",
    }
    for k, v in data.model_dump().items():
        if v is not None and str(v).strip() and str(v) != "Chưa khai báo":
            fact_key = field_map.get(k, k)
            memory_mgr.set_personal_fact(
                user_id=user_id,
                fact_key=fact_key,
                value=v,
                source_type="PROFILE_API",
            )

    # Đồng bộ legacy profile để đảm bảo tương thích ngược
    memory_mgr.legacy_profile.update_profile(data.model_dump())

    return get_profile()


@router.get("/api/memory/profile")
def get_personal_memory_facts():
    """Lấy danh sách chi tiết các sự thật cá nhân đang lưu trữ của người dùng (kèm Provenance)."""
    principal = resolve_principal()
    memory_mgr = get_memory_manager()
    facts = memory_mgr.personal.store.get_all_personal_facts(user_id=principal.user_id, status="ACTIVE")
    return [
        {
            "fact_key": f.fact_key,
            "value": f.value,
            "source_type": f.source_type,
            "confidence": f.confidence,
            "updated_at": f.updated_at.isoformat(),
        }
        for f in facts
    ]


@router.delete("/api/memory/profile/{fact_key}")
def delete_personal_fact(fact_key: str):
    """Xóa một sự thật cá nhân cụ thể của người dùng (Forget one fact)."""
    principal = resolve_principal()
    memory_mgr = get_memory_manager()
    deleted = memory_mgr.delete_personal_fact(user_id=principal.user_id, fact_key=fact_key)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy sự thật cá nhân với khóa '{fact_key}'")
    return {
        "status": "ok",
        "fact_key": fact_key,
        "message": f"Đã xóa thành công sự thật '{fact_key}'.",
    }


@router.delete("/api/memory/profile")
def clear_personal_memory():
    """Xóa toàn bộ sự thật cá nhân của người dùng (Clear all personal memory)."""
    principal = resolve_principal()
    memory_mgr = get_memory_manager()
    count = memory_mgr.clear_personal_memory(user_id=principal.user_id)
    return {
        "status": "ok",
        "cleared_count": count,
        "message": "Đã xóa sạch toàn bộ sự thật cá nhân thành công.",
    }


@router.get("/api/memory/events")
def get_memory_events():
    """Lấy nhật ký kiểm toán biến động sự thật cá nhân (Memory Audit Events)."""
    principal = resolve_principal()
    memory_mgr = get_memory_manager()
    events = memory_mgr.personal.store.get_memory_events(user_id=principal.user_id, limit=50)
    return [e.model_dump() for e in events]
