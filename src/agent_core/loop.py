"""
Agent Loop Engine for Goal-Driven Agent Core V1.
Implements the bounded execution cycle:
UNDERSTAND -> OBSERVE -> PLAN -> ACT -> VERIFY -> PROGRESS -> ASK_USER / FINISH.

Enforces:
- USER GOAL > AGENT ASSUMPTION
- Zero infinite loops via 3 independent mechanisms:
  1. MAX ITERATIONS (max 2 attempts per requirement)
  2. NO-PROGRESS DETECTION (ProgressSnapshot comparison)
  3. DUPLICATE ACTION PREVENTION (ActionFingerprint registry)
- First-class Human-in-the-loop with resume_with_user_response()
- Strict zero external API calls policy.
"""
import uuid
from typing import Dict, Any, Optional

from src.agent_core.schemas import (
    AgentGoalState,
    AgentStatus,
    StopReason,
    EvidenceStatus,
    EvidenceRequirement,
    ActionType,
    QuestionType,
    GoalType,
)
from src.agent_core.goal_analyzer import get_goal_analyzer
from src.agent_core.requirements import get_requirement_builder
from src.agent_core.observer import get_agent_observer
from src.agent_core.planner import get_agent_planner
from src.agent_core.actions import get_action_executor
from src.agent_core.progress import get_progress_tracker
from src.agent_core.environment_catalog import get_knowledge_environment_catalog
from src.agent_core.entity_catalog import get_entity_catalog


class AgentLoop:
    """Động cơ điều phối vòng lặp tác tử có giới hạn và an toàn."""

    MAX_TOTAL_ITERATIONS = 15  # Giới hạn cứng số vòng lặp tối đa cho 1 mục tiêu (Round P2)

    def __init__(self):
        self.goal_analyzer = get_goal_analyzer()
        self.req_builder = get_requirement_builder()
        self.observer = get_agent_observer()
        self.planner = get_agent_planner()
        self.executor = get_action_executor()
        self.tracker = get_progress_tracker()
        self.env_catalog = get_knowledge_environment_catalog()
        self.entity_catalog = get_entity_catalog()

    def run(
        self,
        query: str,
        session_context: Optional[Dict[str, Any]] = None,
        personal_context: Optional[Dict[str, Any]] = None,
        router_hint: Optional[Dict[str, Any]] = None,
        goal_id: Optional[str] = None,
        event_sink: Optional[Any] = None,
    ) -> AgentGoalState:
        """Thực thi một chu trình hoàn chỉnh từ câu hỏi ban đầu của người dùng."""
        gid = goal_id or f"goal-{uuid.uuid4().hex[:8]}"

        # =====================================================================
        # 1. UNDERSTAND: Phân tích mục tiêu thực sự của người dùng
        # =====================================================================
        if event_sink:
            event_sink.emit_phase("UNDERSTAND", "Đang hiểu yêu cầu của bạn...")

        goal_spec = self.goal_analyzer.analyze(
            query=query,
            session_context=session_context,
        )

        # Xây dựng danh sách yêu cầu bằng chứng (EvidenceRequirements)
        requirements = self.req_builder.build_requirements(goal_spec)

        missing_info = []
        if goal_spec.missing_slot:
            missing_info.append(goal_spec.missing_slot)

        # Khởi tạo trạng thái AgentGoalState có cấu trúc
        state = AgentGoalState(
            goal_id=gid,
            original_query=query,
            current_user_input=query,
            objectives=goal_spec.objectives,
            entities=goal_spec.entities,
            subjects=goal_spec.subjects,
            subject_type=goal_spec.subject_type,
            operation=goal_spec.operation,
            query_plan=goal_spec.query_plan,
            requirements=requirements,
            missing_information=missing_info,
            status=AgentStatus.UNDERSTANDING,
            intent=goal_spec.intent,
            scope=goal_spec.scope,
            goal_frame=goal_spec.goal_frame,
            result_scope=getattr(goal_spec, "result_scope", None) or (goal_spec.query_plan.result_scope if goal_spec.query_plan else None),
            limit=getattr(goal_spec, "limit", None) or (goal_spec.query_plan.limit if goal_spec.query_plan else None),
            page=getattr(goal_spec, "page", None) or (goal_spec.query_plan.page if goal_spec.query_plan else None),
        )

        # =====================================================================
        # 2. BOUNDED EXECUTION LOOP
        # =====================================================================
        return self._execute_loop(
            state=state,
            session_context=session_context,
            personal_context=personal_context,
            router_hint=router_hint,
            event_sink=event_sink,
        )

    def _execute_loop(
        self,
        state: AgentGoalState,
        session_context: Optional[Dict[str, Any]] = None,
        personal_context: Optional[Dict[str, Any]] = None,
        router_hint: Optional[Dict[str, Any]] = None,
        event_sink: Optional[Any] = None,
    ) -> AgentGoalState:
        """Vòng lặp có chặn (Bounded Loop) tuân thủ 3 cơ chế chống lặp."""
        while state.iteration < self.MAX_TOTAL_ITERATIONS:
            state.iteration += 1

            # 2.1 OBSERVE: Quan sát môi trường
            if event_sink:
                event_sink.emit_phase("OBSERVE", "Đang kiểm tra ngữ cảnh và dữ liệu...")
            self.observer.observe(
                current_input=state.current_user_input,
                state=state,
                session_context=session_context,
                personal_context=personal_context,
                router_hint=router_hint,
            )

            # 2.2 PLAN: Lập kế hoạch hành động tiếp theo
            if event_sink:
                event_sink.emit_phase("PLAN", "Đang xác định cách xử lý phù hợp...")
            plan = self.planner.plan_next_action(state)
            state.planned_action = plan

            # 2.3 CHỐNG LẶP HÀNH ĐỘNG (DUPLICATE ACTION PREVENTION)
            if plan.action_type not in (ActionType.FINISH, ActionType.ASK_USER, ActionType.PARTIAL_ANSWER, ActionType.ABSTAIN):
                if self.tracker.is_duplicate_action(state, plan.fingerprint):
                    satisfied = [
                        r for r in state.requirements
                        if r.status in (EvidenceStatus.SATISFIED, EvidenceStatus.VERIFIED_VALUE, EvidenceStatus.VERIFIED_NONE)
                    ]
                    if satisfied:
                        state.status = AgentStatus.PARTIAL
                        state.stop_reason = StopReason.DUPLICATE_ACTION
                        state.final_answer = "Hành động tra cứu đã bị trùng lặp và bị chặn lại bởi cơ chế an toàn."
                    else:
                        state.status = AgentStatus.ABSTAINED
                        state.stop_reason = StopReason.DUPLICATE_ACTION
                        state.final_answer = "Hành động tra cứu đã bị trùng lặp và bị chặn lại bởi cơ chế an toàn."
                    break

            # 2.3.1 PHÒNG VỆ THỰC THI GIẢI PHÁP THAY THẾ CHƯA ĐƯỢC CẤP PHÉP (UNAUTHORIZED GOAL EXECUTION GUARD)
            if state.alternative_proposed and not state.alternative_authorized:
                if plan.action_type not in (ActionType.ASK_USER, ActionType.ABSTAIN, ActionType.FINISH):
                    state.alternative_execution_attempts_before_authorization += 1
                    state.status = AgentStatus.NEEDS_USER_INPUT
                    state.stop_reason = StopReason.USER_INPUT_REQUIRED
                    break

            state.attempted_actions.append(plan.fingerprint)

            # 2.4 ACT: Thực thi hành động
            if event_sink:
                act_label = "Đang tìm thông tin học vụ..."
                if plan.entity and plan.entity not in ("DNTU", "general"):
                    act_label = f"Đang tra cứu {plan.entity}..."
                elif plan.requested_field:
                    from src.agent_core.actions import FIELD_NAMES_VN
                    f_vn = FIELD_NAMES_VN.get(plan.requested_field, plan.requested_field)
                    act_label = f"Đang tra cứu thông tin {f_vn}..."
                event_sink.emit_phase("ACT", act_label)

            obs_action = self.executor.execute(plan, state, event_sink=event_sink)
            state.action_history.append(obs_action)

            # 2.5 KIỂM TRA TIẾN TRÌNH (NO-PROGRESS DETECTION)
            snapshot = self.tracker.create_snapshot(state, last_fingerprint=plan.fingerprint)
            has_progress, prog_reason = self.tracker.evaluate_progress(state, snapshot)

            # 2.6 KIỂM TRA ĐIỀU KIỆN DỪNG VÒNG LẶP
            # A. Người dùng cần cung cấp thêm thông tin (ASK_USER)
            if state.status == AgentStatus.NEEDS_USER_INPUT or plan.action_type == ActionType.ASK_USER:
                state.status = AgentStatus.NEEDS_USER_INPUT
                state.stop_reason = StopReason.USER_INPUT_REQUIRED
                break

            # B. Đã hoàn thành (FINISH / COMPARE_EVIDENCE)
            if state.status == AgentStatus.COMPLETED or plan.action_type in (ActionType.FINISH, ActionType.COMPARE_EVIDENCE):
                state.status = AgentStatus.COMPLETED
                state.stop_reason = StopReason.GOAL_COMPLETED
                break

            # C. Câu trả lời từng phần (PARTIAL)
            if state.status == AgentStatus.PARTIAL or plan.action_type == ActionType.PARTIAL_ANSWER:
                state.status = AgentStatus.PARTIAL
                if not state.stop_reason:
                    state.stop_reason = StopReason.PARTIAL_EVIDENCE
                break

            # D. Từ chối an toàn (ABSTAIN)
            if state.status == AgentStatus.ABSTAINED or plan.action_type == ActionType.ABSTAIN:
                state.status = AgentStatus.ABSTAINED
                if not state.stop_reason:
                    state.stop_reason = StopReason.DATA_NOT_AVAILABLE
                break

            # E. Không có tiến triển sau hành động (NO-PROGRESS STOP)
            if state.no_progress_count >= 1 and plan.reason_code.startswith("NO_PROGRESS"):
                if not state.final_answer:
                    state.final_answer = "Dừng tra cứu do không có dữ liệu tiến triển mới từ hệ thống."
                break

        # Nếu đạt số vòng tối đa mà chưa dừng
        if state.iteration >= self.MAX_TOTAL_ITERATIONS and state.status not in (
            AgentStatus.COMPLETED, AgentStatus.NEEDS_USER_INPUT, AgentStatus.PARTIAL, AgentStatus.ABSTAINED
        ):
            state.status = AgentStatus.FAILED_SAFE
            state.stop_reason = StopReason.MAX_ITERATIONS
            state.final_answer = "Đã đạt giới hạn số vòng lặp tối đa mà không thể thu thập đủ bằng chứng."

        if event_sink and state.status not in (AgentStatus.NEEDS_USER_INPUT, AgentStatus.ABSTAINED):
            event_sink.emit_phase("PREPARE_ANSWER", "Đang chuẩn bị câu trả lời...")

        return state

    def resume_with_user_response(
        self,
        state: AgentGoalState,
        user_response: str,
        session_context: Optional[Dict[str, Any]] = None,
        event_sink: Optional[Any] = None,
    ) -> AgentGoalState:
        """
        Khôi phục vòng lặp tác tử khi nhận được câu trả lời từ người dùng (Human-in-the-loop).
        Không tạo goal hoàn toàn mới mà kế thừa và cập nhật trạng thái mục tiêu hiện tại.
        """
        raw_resp = (user_response or "").strip()
        lower_resp = raw_resp.lower()
        state.current_user_input = raw_resp
        state.status = AgentStatus.REPLANNING
        state.clarification_required = False

        if event_sink:
            event_sink.emit_phase("UNDERSTAND", "Đang hiểu phản hồi làm rõ của bạn...")

        # TH1: Xử lý phản hồi đề xuất giải pháp thay thế (USER-APPROVED ALTERNATIVE)
        if state.clarification_type == QuestionType.MISSING_DATA_ALTERNATIVE:
            is_negative = any(neg in lower_resp for neg in ["không", "từ chối", "thôi", "bỏ qua", "chỉ cần"])
            is_agree = not is_negative and any(w in lower_resp for w in ["đồng ý", "được", "ok", "yes", "ừ", "hãy so sánh", "tiêu chí trên", "có", "phân tích"])
            if is_agree:
                state.alternative_authorized = True
                unavail_fields = [r.field for r in state.requirements if r.field in self.env_catalog.UNAVAILABLE_FIELDS]
                state.requirements = [r for r in state.requirements if r.field not in unavail_fields]

                alt_fields = ["credits", "assessment"]
                for ent in state.entities:
                    for f in alt_fields:
                        if not any(r.entity == ent and r.field == f for r in state.requirements):
                            doc_types = self.env_catalog.get_source_doc_types(f)
                            req = EvidenceRequirement(
                                entity=ent,
                                field=f,
                                accepted_document_types=doc_types or ["course_outline"],
                                filters={"course_code": ent},
                                status=EvidenceStatus.PENDING,
                                attempt_count=0,
                            )
                            state.requirements.append(req)

                state.missing_information = []
                if GoalType.COMPARE_COURSES not in state.objectives:
                    state.objectives.append(GoalType.COMPARE_COURSES)
                return self._execute_loop(state, session_context=session_context, event_sink=event_sink)
            else:
                state.alternative_authorized = False
                state.status = AgentStatus.ABSTAINED
                state.stop_reason = StopReason.DATA_NOT_AVAILABLE
                state.final_answer = (
                    "Đã ghi nhận phản hồi của bạn. Vì tài liệu chính thức không có chỉ số bạn yêu cầu "
                    "và bạn không muốn dùng phương án thay thế, hệ thống sẽ dừng tra cứu tại đây."
                )
                return state

        # TH2: Xử lý giải quyết mâu thuẫn thực thể (ENTITY CONFLICT)
        if state.clarification_type == QuestionType.ENTITY_CONFLICT:
            chosen_code = None
            for code in state.entities:
                if code.lower() in lower_resp:
                    chosen_code = code
                    break

            if not chosen_code:
                for code in state.entities:
                    info = self.entity_catalog.get_course_info(code)
                    if info and any(alias in lower_resp for alias in info.get("aliases", [])):
                        chosen_code = code
                        break

            if not chosen_code and state.entities:
                chosen_code = state.entities[0]

            state.entities = [chosen_code]
            doc_types = self.env_catalog.get_source_doc_types("credits")
            state.requirements = [
                EvidenceRequirement(
                    entity=chosen_code,
                    field="credits",
                    accepted_document_types=doc_types or ["course_outline"],
                    filters={"course_code": chosen_code},
                    status=EvidenceStatus.PENDING,
                    attempt_count=0,
                )
            ]
            state.missing_information = []
            return self._execute_loop(state, session_context=session_context, event_sink=event_sink)

        # TH3: Xử lý bổ sung thực thể bị thiếu (MISSING ENTITY)
        if state.clarification_type == QuestionType.MISSING_ENTITY:
            extracted_ents = self.entity_catalog.extract_known_entities(raw_resp)
            if extracted_ents:
                state.entities = extracted_ents
                original_fields = [r.field for r in state.requirements] or self.goal_analyzer._extract_fields(state.original_query.lower()) or ["credits"]
                state.requirements = []
                for ent in state.entities:
                    for f in original_fields:
                        doc_types = self.env_catalog.get_source_doc_types(f)
                        state.requirements.append(
                            EvidenceRequirement(
                                entity=ent,
                                field=f,
                                accepted_document_types=doc_types or ["course_outline"],
                                filters={"course_code": ent},
                                status=EvidenceStatus.PENDING,
                                attempt_count=0,
                            )
                        )
                state.missing_information = []
                return self._execute_loop(state, session_context=session_context, event_sink=event_sink)
            else:
                state.final_answer = "Không nhận diện được mã môn học trong phản hồi của bạn. Vui lòng thử lại."
                state.status = AgentStatus.NEEDS_USER_INPUT
                return state

        # TH4: Xử lý bổ sung ý định bị thiếu (MISSING INTENT)
        if state.clarification_type == QuestionType.MISSING_INTENT:
            # Nếu trong câu trả lời người dùng có bổ sung mã môn học
            new_ents = self.entity_catalog.extract_known_entities(raw_resp)
            if new_ents:
                state.entities = new_ents

            fields = self.goal_analyzer._extract_fields(lower_resp)
            if not fields:
                if "tín chỉ" in lower_resp or "tín" in lower_resp:
                    fields = ["credits"]
                elif "giảng viên" in lower_resp or "thầy" in lower_resp or "cô" in lower_resp:
                    fields = ["lecturer"]
                elif "chuẩn đầu ra" in lower_resp or "clo" in lower_resp:
                    fields = ["clo"]
                elif "đánh giá" in lower_resp or "thi" in lower_resp:
                    fields = ["assessment"]
                else:
                    fields = ["credits"]

            for ent in state.entities:
                for f in fields:
                    if not any(r.entity == ent and r.field == f for r in state.requirements):
                        doc_types = self.env_catalog.get_source_doc_types(f)
                        req = EvidenceRequirement(
                            entity=ent,
                            field=f,
                            accepted_document_types=doc_types or ["course_outline"],
                            filters={"course_code": ent},
                            status=EvidenceStatus.PENDING,
                            attempt_count=0,
                        )
                        state.requirements.append(req)
            state.missing_information = []
            return self._execute_loop(state, session_context=session_context, event_sink=event_sink)

        # Mặc định tiếp tục vòng lặp
        return self._execute_loop(state, session_context=session_context, event_sink=event_sink)


# Singleton Instance
_agent_loop_instance: AgentLoop = None


def get_agent_loop() -> AgentLoop:
    global _agent_loop_instance
    if _agent_loop_instance is None:
        _agent_loop_instance = AgentLoop()
    return _agent_loop_instance
