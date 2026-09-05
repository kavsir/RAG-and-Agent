"""
API Router: Định nghĩa các endpoints cho dịch vụ AI Academic Advisor.
"""
import uuid
import logging
from fastapi import APIRouter, HTTPException

from src.config.settings import settings
from src.agent.graph import graph
from src.identity import resolve_principal
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
    principal = resolve_principal()
    user_id = principal.user_id
    conv_id = request.conversation_id or str(uuid.uuid4())
    memory_mgr = get_memory_manager()

    # 1. Trích xuất sự thật cá nhân tiềm năng từ tin nhắn người dùng (0 external calls)
    memory_mgr.process_personal_memory(user_id=user_id, message=request.message)

    # 2. Lấy ngữ cảnh cá nhân hóa tối thiểu (không tiêm thừa thãi)
    relevant_profile = memory_mgr.get_relevant_profile_context(
        query=request.message,
        category="DOMAIN_DATA",
        user_id=user_id,
    )

    # 3. Lấy lịch sử phiên và trạng thái thực thể của đúng phiên
    history_text = memory_mgr.get_conversation_history(conversation_id=conv_id, k=5)
    session_state = memory_mgr.get_session_state(conv_id)

    initial_state = {
        "question": request.message,
        "conversation_id": conv_id,
        "chat_history": history_text,
        "student_profile": relevant_profile,
        "rewritten_question": "",
        "category": "DOMAIN_DATA",
        "tool_intent": None,
        "analyzed_query": {},
        "session_context": session_state.to_context_dict(),
        "resolved_entities": {},
        "resolution_source": "NONE",
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
