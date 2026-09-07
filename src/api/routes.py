"""
API Router: Định nghĩa các endpoints cho dịch vụ AI Academic Advisor.
Tích hợp trực tiếp AgentCoreService vào đường dẫn chính POST /api/chat.
"""
import uuid
import re
import logging
from typing import List
from fastapi import APIRouter, HTTPException

from src.config.settings import settings
from src.identity import resolve_principal
from src.memory.memory_manager import get_memory_manager
from src.cache.cache_policy import decide_cache_policy, CacheScope
from src.cache.exact_cache import get_exact_cache
from src.agent_core.service import get_agent_core_service
from src.agent_core.schemas import AgentStatus, GoalType, EvidenceStatus
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
    Xử lý câu hỏi người dùng thông qua Goal-Driven Agent Core V1.1.
    Hỗ trợ Human-in-the-loop multi-turn resumption cô lập theo (user_id, conv_id).
    """
    principal = resolve_principal()
    user_id = principal.user_id
    conv_id = request.conversation_id or str(uuid.uuid4())
    memory_mgr = get_memory_manager()
    agent_service = get_agent_core_service()

    # 1. Trích xuất sự thật cá nhân tiềm năng từ tin nhắn người dùng
    try:
        memory_mgr.process_personal_memory(user_id=user_id, message=request.message)
    except Exception as e:
        logger.warning(f"Lỗi xử lý personal memory: {e}")

    # 2. Lấy trạng thái phiên và hồ sơ cá nhân
    session_state = memory_mgr.get_session_state(conv_id)
    session_ctx = session_state.to_context_dict() if session_state else {}
    personal_ctx = memory_mgr.get_personal_profile(user_id) if hasattr(memory_mgr, "get_personal_profile") else {}

    # 2. Kiểm tra xem phiên này có Goal đang chờ phản hồi làm rõ hay không
    active_goal = agent_service.get_active_goal(user_id=user_id, conversation_id=conv_id)
    if active_goal and active_goal.status == AgentStatus.NEEDS_USER_INPUT:
        logger.info(f"Phát hiện Goal {active_goal.goal_id} đang chờ làm rõ. Tiến hành resume_goal...")
        goal_state = agent_service.resume_goal(
            user_id=user_id,
            conversation_id=conv_id,
            user_response=request.message,
            goal_id=active_goal.goal_id,
            session_context=session_ctx,
        )
        r_dec = None
    else:
        from src.router import get_router_service
        r_dec = get_router_service().classify(query=request.message, analyzed_query=session_ctx)

        if r_dec.category == "GENERAL_LLM":
            from src.agent.nodes import general_answer_node
            state_dict = {
                "question": request.message,
                "student_profile": personal_ctx,
                "chat_history": memory_mgr.get_conversation_history(conv_id, k=5),
            }
            gen_res = general_answer_node(state_dict)
            answer = gen_res.get("answer", "")
            return ChatResponse(
                answer=answer,
                category="GENERAL_LLM",
                sources=[],
                conversation_id=conv_id,
                goal_id=None,
                status="COMPLETED",
                metadata=ChatMetadata(
                    cache_hit=False,
                    category="GENERAL_LLM",
                    tool_intent=None,
                    cache_scope="CACHEABLE",
                ),
            )

        logger.info(f"Khởi tạo chu trình xử lý mục tiêu mới cho conv_id={conv_id}...")
        goal_state = agent_service.process_query(
            query=request.message,
            user_id=user_id,
            conversation_id=conv_id,
            session_context=session_ctx,
            personal_context=personal_ctx,
        )

    try:
        # 4. Xác định danh mục phản hồi
        category = "TOOL_ACTION" if r_dec and r_dec.category == "TOOL_ACTION" else "DOMAIN_DATA"
        tool_intent = r_dec.tool_intent if r_dec and category == "TOOL_ACTION" else None
        if any(o in (GoalType.SEND_EMAIL, GoalType.SET_REMINDER) for o in goal_state.objectives):
            category = "TOOL_ACTION"
            tool_intent = "SEND_EMAIL" if GoalType.SEND_EMAIL in goal_state.objectives else "SET_REMINDER"

        # 4.1. Thực thi an toàn công cụ qua Action Authorization Gate
        if category == "TOOL_ACTION" and tool_intent:
            from src.semantics import analyze_utterance, authorize_tool_action, ActionOperation
            sem = analyze_utterance(request.message)

            # Thu thập email người nhận chính thống từ bằng chứng đã được thẩm định
            context_recipients = []
            target_entity = goal_state.entities[0] if goal_state.entities else None
            for ev in goal_state.evidence:
                if (
                    ev.status == EvidenceStatus.VERIFIED_VALUE
                    and ev.field == "lecturer_email"
                    and ev.is_authoritative is True
                    and (not target_entity or ev.entity == target_entity)
                ):
                    found_emails = re.findall(r"[\w\.-]+@[\w\.-]+\.\w+", ev.content)
                    context_recipients.extend(found_emails)
            context_recipients = list(dict.fromkeys(context_recipients))

            action_context = {"available_recipients": context_recipients}
            decision = authorize_tool_action(sem, requested_tool=tool_intent, context=action_context)

            if decision.requires_clarification:
                answer = decision.clarification_message or "Yêu cầu có thông tin chưa rõ ràng hoặc mâu thuẫn. Bạn có muốn thực hiện không?"
                goal_state.status = AgentStatus.NEEDS_USER_INPUT
                goal_state.clarification_question = answer
                goal_state.final_answer = answer
            elif not decision.authorized:
                answer = decision.safe_response or "Yêu cầu thực thi công cụ không được cấp phép."
                goal_state.status = AgentStatus.ABSTAINED
                goal_state.final_answer = answer
            elif tool_intent == "SEND_EMAIL":
                if decision.operation == ActionOperation.COMPOSE_EMAIL or not decision.side_effect:
                    email_matches = re.findall(r"[\w\.-]+@[\w\.-]+\.\w+", request.message)
                    recipient = email_matches[0] if email_matches else "(Chưa chỉ định người nhận)"
                    answer = (
                        f"📝 **Bản thảo email (Draft - Chưa gửi đi)**:\n"
                        f"- **Người nhận**: {recipient}\n"
                        f"- **Tiêu đề**: Thông báo từ sinh viên ĐNTU\n"
                        f"- **Nội dung dự thảo**: Kính gửi Thầy/Cô,\n\nEm gửi thông tin về: {request.message}.\n\nTrân trọng,\nSinh viên\n\n"
                        f"*(Lưu ý: Hệ thống chỉ tạo bản thảo theo yêu cầu và tuyệt đối không tự ý gửi thư đi.)*"
                    )
                    goal_state.status = AgentStatus.COMPLETED
                    goal_state.final_answer = answer
                else:
                    recipient = decision.metadata.get("recipient") if decision.metadata else None
                    if not recipient:
                        answer = "Bạn muốn gửi email tới địa chỉ nào? Vui lòng cung cấp địa chỉ email người nhận hợp lệ."
                        goal_state.status = AgentStatus.NEEDS_USER_INPUT
                        goal_state.clarification_question = answer
                        goal_state.final_answer = answer
                    else:
                        from src.tools.email_sender import send_email_direct
                        send_email_direct(
                            to=recipient,
                            subject="Thông báo từ sinh viên ĐNTU",
                            body=f"Nội dung: {request.message}",
                        )
                        answer = f"✅ Đã gửi email thành công tới: {recipient}."
                        goal_state.status = AgentStatus.COMPLETED
                        goal_state.final_answer = answer
            elif tool_intent == "SET_REMINDER":
                from src.agent.nodes import parse_reminder_datetime
                from src.scheduler.reminder_scheduler import schedule_reminder
                scheduled_dt = parse_reminder_datetime(request.message)
                if not scheduled_dt:
                    answer = "Vui lòng cung cấp ngày hoặc giờ cụ thể bạn muốn đặt lịch nhắc (Ví dụ: 'Nhắc tôi nộp bài lúc 17h ngày 20/12')."
                    goal_state.status = AgentStatus.NEEDS_USER_INPUT
                    goal_state.clarification_question = answer
                else:
                    from src.agent.nodes import _reminder_job_callback
                    job_id = f"remind_{uuid.uuid4().hex[:8]}"
                    schedule_reminder(
                        run_date=scheduled_dt,
                        func=_reminder_job_callback,
                        args=[request.message, job_id],
                    )
                    answer = f"✅ Đã lên lịch nhắc nhở thành công vào lúc {scheduled_dt.strftime('%H:%M ngày %d/%m/%Y')}."
                    goal_state.status = AgentStatus.COMPLETED
                    goal_state.final_answer = answer

        # 5. Xác định câu trả lời hiển thị
        answer = goal_state.final_answer or goal_state.clarification_question or "Đã hoàn tất xử lý yêu cầu."
        if goal_state.status == AgentStatus.NEEDS_USER_INPUT and goal_state.clarification_question:
            answer = goal_state.clarification_question
        elif goal_state.status == AgentStatus.ABSTAINED and "chưa tìm thấy đủ dữ liệu" not in answer.lower():
            answer = f"{answer} Chưa tìm thấy đủ dữ liệu trong tài liệu hiện có để trả lời chính xác."

        # 6. Chuẩn hóa danh sách nguồn minh chứng chính thống (100% provenance, 0 fabricated)
        sources_list: List[SourceItem] = []
        if goal_state.status not in (AgentStatus.ABSTAINED, AgentStatus.NEEDS_USER_INPUT):
            for ev in goal_state.evidence:
                if ev.is_authoritative:
                    sources_list.append(
                        SourceItem(
                            source_file=ev.source_file or ev.source,
                            document_type=ev.document_type,
                            course_code=ev.entity if ev.entity not in ("DNTU", "general") else "",
                            course_name="",
                            section=ev.section or "",
                            subsection="",
                            chunk_id=ev.chunk_id or ev.source,
                        )
                    )

        # 7. Chính sách Cache: Các trạng thái tương tác hoặc thiếu dữ liệu bắt buộc KHÔNG được cache mù quáng
        cache_hit = False
        cache_scope = CacheScope.NON_CACHEABLE
        if goal_state.status in (AgentStatus.NEEDS_USER_INPUT, AgentStatus.PARTIAL, AgentStatus.ABSTAINED) or category == "TOOL_ACTION":
            cache_scope = CacheScope.NON_CACHEABLE
        else:
            cache_dec = decide_cache_policy(
                query=request.message,
                category=category,
                tool_intent=tool_intent,
                session_context=session_ctx,
                relevant_profile=personal_ctx,
            )
            cache_scope = cache_dec.scope

        # 8. Cập nhật lịch sử hội thoại phiên
        try:
            memory_mgr.update(
                user_message=request.message,
                ai_message=answer,
                conversation_id=conv_id,
                sources=sources_list,
            )
        except Exception as e:
            logger.warning(f"Lỗi ghi nhận lịch sử phiên: {e}")

        return ChatResponse(
            answer=answer,
            category=category,
            sources=sources_list,
            conversation_id=conv_id,
            goal_id=goal_state.goal_id,
            status=goal_state.status.value,
            clarification_question=goal_state.clarification_question,
            clarification_options=goal_state.clarification_options,
            metadata=ChatMetadata(
                cache_hit=cache_hit,
                category=category,
                tool_intent=tool_intent,
                cache_scope=cache_scope,
                goal_id=goal_state.goal_id,
                status=goal_state.status.value,
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
