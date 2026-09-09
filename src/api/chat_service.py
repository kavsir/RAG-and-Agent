"""
Chat Execution Service: Shared execution engine for blocking /api/chat and streaming /api/chat/stream.
Preserves 100% backward compatibility, exact Agent Core V1.1 decisions, and evidence verification.
"""
import uuid
import re
import logging
from typing import List, Optional

from src.identity import resolve_principal
from src.memory.memory_manager import get_memory_manager
from src.cache.cache_policy import decide_cache_policy, CacheScope
from src.agent_core.service import get_agent_core_service
from src.agent_core.schemas import AgentStatus, GoalType, EvidenceStatus
from src.agent_core.events import AgentEventEmitter
from src.api.schemas import (
    ChatRequest,
    ChatResponse,
    ChatMetadata,
    SourceItem,
)

logger = logging.getLogger(__name__)


class ChatExecutionService:
    """
    Unified chat execution service.
    Accepts optional AgentEventEmitter to stream real-time progress events.
    When event_sink is None, runs identically to legacy execution.
    """

    def process(
        self,
        request: ChatRequest,
        event_sink: Optional[AgentEventEmitter] = None,
        user_id: Optional[str] = None,
    ) -> ChatResponse:
        principal = resolve_principal()
        user_id = user_id or principal.user_id
        conv_id = request.conversation_id or getattr(request, "session_id", None) or str(uuid.uuid4())
        memory_mgr = get_memory_manager()
        agent_service = get_agent_core_service()

        if event_sink:
            event_sink.set_conversation_id(conv_id)
            event_sink.emit(
                type="meta",
                data={"conversation_id": conv_id, "user_id": user_id},
            )
            event_sink.emit_phase("UNDERSTAND", "Đang hiểu yêu cầu của bạn...")

        # 1. Trích xuất sự thật cá nhân tiềm năng từ tin nhắn người dùng
        try:
            memory_mgr.process_personal_memory(user_id=user_id, message=request.message)
        except Exception as e:
            logger.warning(f"Lỗi xử lý personal memory: {e}")

        # 2. Lấy trạng thái phiên và hồ sơ cá nhân
        session_state = memory_mgr.get_session_state(conv_id)
        session_ctx = session_state.to_context_dict() if session_state else {}
        personal_ctx = memory_mgr.get_personal_profile(user_id) if hasattr(memory_mgr, "get_personal_profile") else {}

        # 3. Kiểm tra xem phiên này có Goal đang chờ phản hồi làm rõ hay không
        active_goal = agent_service.get_active_goal(user_id=user_id, conversation_id=conv_id)
        if active_goal and active_goal.status == AgentStatus.NEEDS_USER_INPUT:
            logger.info(f"Phát hiện Goal {active_goal.goal_id} đang chờ làm rõ. Tiến hành resume_goal...")
            if event_sink:
                event_sink.set_goal_id(active_goal.goal_id)
                event_sink.emit_phase("OBSERVE", "Đang kiểm tra ngữ cảnh và dữ liệu...")
            goal_state = agent_service.resume_goal(
                user_id=user_id,
                conversation_id=conv_id,
                user_response=request.message,
                goal_id=active_goal.goal_id,
                session_context=session_ctx,
                personal_context=personal_ctx,
                event_sink=event_sink,
            )
            r_dec = None
        else:
            # 3.0. Fast Path: Xử lý tức thì các tương tác hội thoại thông thường (p95 < 100ms, 0 RAG, 0 LLM)
            from src.api.fast_path import match_fast_path
            fast_res = match_fast_path(request.message)
            if fast_res.matched:
                try:
                    memory_mgr.update(
                        user_message=request.message,
                        ai_message=fast_res.answer,
                        conversation_id=conv_id,
                        sources=[],
                    )
                except Exception as e:
                    logger.warning(f"Lỗi ghi nhận lịch sử fast path: {e}")

                return ChatResponse(
                    answer=fast_res.answer,
                    category="FAST_PATH",
                    sources=[],
                    conversation_id=conv_id,
                    goal_id=None,
                    status="COMPLETED",
                    metadata=ChatMetadata(
                        cache_hit=True,
                        category="FAST_PATH",
                        tool_intent=None,
                        cache_scope="CACHEABLE",
                    ),
                )

            from src.router import get_router_service
            if event_sink:
                event_sink.emit_phase("OBSERVE", "Đang kiểm tra ngữ cảnh và dữ liệu...")
            r_dec = get_router_service().classify(query=request.message, analyzed_query=session_ctx)

            if r_dec.category == "GENERAL_LLM":
                # 3.1 Kiểm tra từ viết tắt kỹ thuật mơ hồ: Yêu cầu làm rõ thay vì đoán mò (0 confident guessing)
                from src.router.acronym_disambiguator import check_ambiguous_acronym
                acronym_res = check_ambiguous_acronym(request.message)
                if acronym_res.is_ambiguous:
                    try:
                        memory_mgr.update(
                            user_message=request.message,
                            ai_message=acronym_res.clarification_question,
                            conversation_id=conv_id,
                            sources=[],
                        )
                    except Exception as e:
                        logger.warning(f"Lỗi ghi nhận lịch sử acronym disambiguation: {e}")

                    return ChatResponse(
                        answer=acronym_res.clarification_question,
                        category="GENERAL_LLM",
                        sources=[],
                        conversation_id=conv_id,
                        goal_id=None,
                        status="NEEDS_USER_INPUT",
                        clarification_question=acronym_res.clarification_question,
                        clarification_options=acronym_res.clarification_options,
                        metadata=ChatMetadata(
                            cache_hit=False,
                            category="GENERAL_LLM",
                            tool_intent=None,
                            cache_scope="NON_CACHEABLE",
                            status="NEEDS_USER_INPUT",
                        ),
                    )

                state_dict = {
                    "question": request.message,
                    "student_profile": personal_ctx,
                    "chat_history": memory_mgr.get_conversation_history(conv_id, k=5),
                }
                if event_sink:
                    event_sink.emit_phase("PLAN", "Đang xác định cách xử lý phù hợp...")
                    event_sink.emit_phase("PREPARE_ANSWER", "Đang chuẩn bị câu trả lời...")
                    event_sink.emit(type="answer_start")
                    from src.agent.nodes import stream_general_answer_node
                    accumulated = []
                    for delta in stream_general_answer_node(state_dict):
                        accumulated.append(delta)
                        event_sink.emit(type="answer_delta", data={"delta": delta})
                    answer = "".join(accumulated).strip()
                else:
                    from src.agent.nodes import general_answer_node
                    gen_res = general_answer_node(state_dict)
                    answer = gen_res.get("answer", "")

                try:
                    memory_mgr.update(
                        user_message=request.message,
                        ai_message=answer,
                        conversation_id=conv_id,
                        sources=[],
                    )
                except Exception as e:
                    logger.warning(f"Lỗi ghi nhận lịch sử GENERAL_LLM: {e}")

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
                event_sink=event_sink,
            )

        # 4. Xác định danh mục phản hồi
        category = "TOOL_ACTION" if r_dec and r_dec.category == "TOOL_ACTION" else "DOMAIN_DATA"
        tool_intent = r_dec.tool_intent if r_dec and category == "TOOL_ACTION" else None
        if any(o in (GoalType.SEND_EMAIL, GoalType.SET_REMINDER) for o in goal_state.objectives):
            category = "TOOL_ACTION"
            tool_intent = "SEND_EMAIL" if GoalType.SEND_EMAIL in goal_state.objectives else "SET_REMINDER"

        # 4.1. Thực thi an toàn công cụ qua Action Authorization Gate
        if category == "TOOL_ACTION" and tool_intent:
            if event_sink:
                event_sink.emit_phase("PLAN", "Đang xác định cách xử lý phù hợp...")
                event_sink.emit_tool_status("Đang kiểm tra yêu cầu thực hiện tác vụ...")
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
                    if event_sink:
                        event_sink.emit_tool_status("Đang tạo bản thảo email...")
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
                    if event_sink:
                        event_sink.emit_tool_status("Đã tạo bản thảo email.")
                else:
                    recipient = decision.metadata.get("recipient") if decision.metadata else None
                    if not recipient:
                        answer = "Bạn muốn gửi email tới địa chỉ nào? Vui lòng cung cấp địa chỉ email người nhận hợp lệ."
                        goal_state.status = AgentStatus.NEEDS_USER_INPUT
                        goal_state.clarification_question = answer
                        goal_state.final_answer = answer
                    else:
                        if event_sink:
                            event_sink.emit_tool_status("Đã xác định người nhận...")
                            event_sink.emit_tool_status("Đang thực hiện yêu cầu đã được cấp phép...")
                        from src.tools.email_sender import send_email_direct
                        send_email_direct(
                            to=recipient,
                            subject="Thông báo từ sinh viên ĐNTU",
                            body=f"Nội dung: {request.message}",
                        )
                        answer = f"✅ Đã gửi email thành công tới: {recipient}."
                        goal_state.status = AgentStatus.COMPLETED
                        goal_state.final_answer = answer
                        if event_sink:
                            event_sink.emit_tool_status("Đã hoàn thành.")
            elif tool_intent == "SET_REMINDER":
                from src.agent.nodes import parse_reminder_datetime
                from src.scheduler.reminder_scheduler import schedule_reminder
                if event_sink:
                    event_sink.emit_tool_status("Đang kiểm tra thông tin đặt lịch nhắc nhở...")
                scheduled_dt = parse_reminder_datetime(request.message)
                if not scheduled_dt:
                    answer = "Vui lòng cung cấp ngày hoặc giờ cụ thể bạn muốn đặt lịch nhắc (Ví dụ: 'Nhắc tôi nộp bài lúc 17h ngày 20/12')."
                    goal_state.status = AgentStatus.NEEDS_USER_INPUT
                    goal_state.clarification_question = answer
                else:
                    if event_sink:
                        event_sink.emit_tool_status("Đang thực hiện yêu cầu đã được cấp phép...")
                    from src.agent.nodes import _reminder_job_callback
                    job_id = f"remind_{uuid.uuid4().hex[:8]}"
                    schedule_reminder(
                        run_date=scheduled_dt,
                        func=_reminder_job_callback,
                        args=[request.message, job_id],
                    )
                    answer = f"✅ Đã lên lịch nhắc nhở thành công vào lúc {scheduled_dt.strftime('%H:%M ngày %d/%m/%Y')}.\n- Mã lịch nhắc: {job_id}"
                    goal_state.status = AgentStatus.COMPLETED
                    goal_state.final_answer = answer
                    if event_sink:
                        event_sink.emit_tool_status("Đã hoàn thành.")

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

        # 8. Cập nhật lịch sử hội thoại phiên và Discourse State
        try:
            last_academic_entity = goal_state.entities[0] if goal_state.entities else None
            last_intent_val = (
                goal_state.intent.value if hasattr(goal_state.intent, "value") else (str(goal_state.intent) if goal_state.intent else None)
            )
            last_scope_val = (
                goal_state.scope.value if hasattr(goal_state.scope, "value") else (str(goal_state.scope) if goal_state.scope else None)
            )
            last_req_fields = [
                r.field for r in goal_state.requirements
                if r.status in (EvidenceStatus.SATISFIED, EvidenceStatus.VERIFIED_VALUE, EvidenceStatus.VERIFIED_NONE)
            ] or [r.field for r in goal_state.requirements]
            last_goal_id = goal_state.goal_id if goal_state.status in (AgentStatus.COMPLETED, AgentStatus.PARTIAL) else None

            memory_mgr.update(
                user_message=request.message,
                ai_message=answer,
                conversation_id=conv_id,
                sources=sources_list,
                last_academic_entity=last_academic_entity,
                last_entity_type="course" if last_academic_entity else None,
                last_intent=last_intent_val,
                last_scope=last_scope_val,
                last_requested_fields=last_req_fields,
                last_completed_goal_id=last_goal_id,
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

    handle_chat = process


_chat_execution_service: Optional[ChatExecutionService] = None


def get_chat_execution_service() -> ChatExecutionService:
    global _chat_execution_service
    if _chat_execution_service is None:
        _chat_execution_service = ChatExecutionService()
    return _chat_execution_service
