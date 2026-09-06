"""
Agent Planner (PLAN Phase) for Goal-Driven Agent Core V1.
Plans the single best NEXT action based on current state and observations.
Strictly adheres to:
- USER GOAL > AGENT ASSUMPTION (never assume or reinterpret user intent)
- ASK_USER as a first-class citizen for clarifying ambiguities or proposing alternatives
- Anti-loop invariant checks (NO_PROGRESS, DUPLICATE_ACTION, MAX_ATTEMPTS)
- Strict local execution with 0 external API calls
"""
from typing import Optional

from src.agent_core.schemas import (
    AgentGoalState,
    ActionPlan,
    ActionType,
    QuestionType,
    EvidenceStatus,
    AgentStatus,
    ActionFingerprint,
)
from src.agent_core.environment_catalog import get_knowledge_environment_catalog, KnowledgeEnvironmentCatalog
from src.agent_core.entity_catalog import get_entity_catalog, EntityCatalog
from src.agent_core.progress import get_progress_tracker, ProgressTracker


class AgentPlanner:
    """Bộ lập kế hoạch hành động từng bước có cấu trúc."""

    MAX_ATTEMPTS_PER_REQUIREMENT = 2

    def __init__(
        self,
        env_catalog: Optional[KnowledgeEnvironmentCatalog] = None,
        entity_catalog: Optional[EntityCatalog] = None,
        tracker: Optional[ProgressTracker] = None,
    ):
        self.env_catalog = env_catalog or get_knowledge_environment_catalog()
        self.entity_catalog = entity_catalog or get_entity_catalog()
        self.tracker = tracker or get_progress_tracker()

    def plan_next_action(self, state: AgentGoalState) -> ActionPlan:
        """Quyết định hành động tối ưu tiếp theo cho Agent."""
        action_idx = len(state.action_history) + 1
        action_id = f"ACT-{action_idx:02d}"

        # 1. Trạng thái đã hoàn tất hoặc dừng an toàn
        if state.status in (AgentStatus.COMPLETED, AgentStatus.ABSTAINED, AgentStatus.FAILED_SAFE):
            fp = ActionFingerprint(action_type=ActionType.FINISH, strategy="terminal").to_string()
            return ActionPlan(
                action_id=action_id,
                action_type=ActionType.FINISH,
                fingerprint=fp,
                reason_code="GOAL_ALREADY_TERMINAL",
            )

        # 2. Xử lý các khoảng trống đầu vào (Missing Information & Clarification Gates)
        # 2.1 THỰC THỂ KHÔNG TỒN TẠI (UNKNOWN ENTITY)
        if "unknown_entity" in state.missing_information:
            unknown_code = state.entities[0] if state.entities else "này"
            fp = ActionFingerprint(action_type=ActionType.ABSTAIN, entity=unknown_code, strategy="unknown_entity").to_string()
            return ActionPlan(
                action_id=action_id,
                action_type=ActionType.ABSTAIN,
                entity=unknown_code,
                fingerprint=fp,
                reason_code="UNKNOWN_ENTITY",
                ask_user_payload={
                    "question_type": QuestionType.MISSING_ENTITY.value,
                    "clarification_question": (
                        f"Mã môn học '{unknown_code}' hiện không có trong chương trình đào tạo của Nhà trường. "
                        f"Bạn vui lòng kiểm tra lại mã môn học nhé."
                    ),
                    "options": ["Kiểm tra lại mã môn", "Xem danh sách môn học"],
                }
            )

        # 2.2 MÂU THUẪN THỰC THỂ (ENTITY CONFLICT: Mã A + Tên B)
        if "entity_conflict" in state.missing_information:
            conflict = self.entity_catalog.check_entity_conflict(state.original_query)
            fp = ActionFingerprint(action_type=ActionType.ASK_USER, strategy="entity_conflict").to_string()
            question = conflict.get("clarification_question") if conflict else "Có mâu thuẫn giữa mã môn và tên môn trong câu hỏi của bạn."
            options = conflict.get("options", []) if conflict else []
            return ActionPlan(
                action_id=action_id,
                action_type=ActionType.ASK_USER,
                fingerprint=fp,
                reason_code="ENTITY_CONFLICT",
                ask_user_payload={
                    "question_type": QuestionType.ENTITY_CONFLICT.value,
                    "clarification_question": question,
                    "options": options,
                }
            )

        # 2.3 THIẾU THỰC THỂ (MISSING ENTITY)
        if "entity" in state.missing_information:
            fp = ActionFingerprint(action_type=ActionType.ASK_USER, strategy="missing_entity").to_string()
            return ActionPlan(
                action_id=action_id,
                action_type=ActionType.ASK_USER,
                fingerprint=fp,
                reason_code="MISSING_ENTITY",
                ask_user_payload={
                    "question_type": QuestionType.MISSING_ENTITY.value,
                    "clarification_question": (
                        "Bạn đang hỏi về môn học / học phần nào? Bạn có thể cung cấp mã môn học "
                        "hoặc mã học phần (ví dụ FIT4201) để mình tra cứu chính xác nhé."
                    ),
                    "options": ["FIT4201 - Hệ thống nhúng", "FIT4104 - Dự án Full-Stack", "FIT4117 - Quản trị dự án"],
                }
            )

        # 2.4 THIẾU Ý ĐỊNH RÕ RÀNG (MISSING INTENT)
        if "intent" in state.missing_information:
            ents_str = " và ".join(state.entities) if state.entities else "học phần này"
            fp = ActionFingerprint(action_type=ActionType.ASK_USER, strategy="missing_intent").to_string()
            return ActionPlan(
                action_id=action_id,
                action_type=ActionType.ASK_USER,
                fingerprint=fp,
                reason_code="GOAL_UNDERSPECIFIED",
                ask_user_payload={
                    "question_type": QuestionType.MISSING_INTENT.value,
                    "clarification_question": (
                        f"Bạn muốn mình so sánh {ents_str} theo tiêu chí nào (các thông tin như số tín chỉ, giảng viên, chuẩn đầu ra (CLO), hình thức đánh giá hay thứ tự nên học)?"
                        if len(state.entities) >= 2 else
                        ("Bạn muốn tìm hiểu thông tin học phần của học kỳ nào và ngành học nào?"
                         if not state.entities else
                         f"Bạn muốn biết thông tin cụ thể gì về học phần {ents_str} (số tín chỉ, giảng viên, đề cương, hay điều kiện tiên quyết)?")
                    ),
                    "options": [
                        "Số tín chỉ",
                        "Giảng viên phụ trách",
                        "Chuẩn đầu ra (CLO)",
                        "Hình thức đánh giá / thi",
                        "Thứ tự nên học",
                    ],
                }
            )

        # 2.5 DỮ LIỆU KHÔNG TỒN TẠI (MISSING DATA: e.g. difficulty, failure_rate)
        if "data" in state.missing_information:
            if not state.alternative_authorized:
                # Tìm trường unavailable từ requirements hoặc query
                unavail_field = None
                for req in state.requirements:
                    if req.field in self.env_catalog.UNAVAILABLE_FIELDS:
                        unavail_field = req.field
                        break
                if not unavail_field:
                    query_l = state.original_query.lower()
                    for f in self.env_catalog.UNAVAILABLE_FIELDS:
                        if f in query_l:
                            unavail_field = f
                            break
                    if not unavail_field:
                        if "trượt" in query_l or "rớt" in query_l:
                            unavail_field = "failure_rate"
                        elif "review" in query_l or "đánh giá của sinh viên" in query_l or "chấm" in query_l:
                            unavail_field = "student_rating"
                        elif "lương" in query_l or "thu nhập" in query_l:
                            unavail_field = "job_salary"
                        elif "lộ" in query_l or "leak" in query_l:
                            unavail_field = "exam_leak"
                        else:
                            unavail_field = "difficulty"

                prop = self.env_catalog.propose_alternative_for_field(unavail_field)
                fp = ActionFingerprint(
                    action_type=ActionType.ASK_USER,
                    requested_field=unavail_field,
                    strategy="propose_alternative"
                ).to_string()
                return ActionPlan(
                    action_id=action_id,
                    action_type=ActionType.ASK_USER,
                    requested_field=unavail_field,
                    fingerprint=fp,
                    reason_code="PROPOSE_ALTERNATIVE",
                    ask_user_payload={
                        "question_type": QuestionType.MISSING_DATA_ALTERNATIVE.value,
                        "clarification_question": prop["proposal_text"],
                        "options": [
                            "Đồng ý, hãy so sánh theo các tiêu chí trên",
                            "Không, chỉ cần tìm đúng tiêu chí ban đầu",
                        ],
                        "alternative_fields": prop["alternative_fields"],
                    }
                )

        # 3. Kiểm tra cơ chế chống lặp NO-PROGRESS
        if state.no_progress_count >= 1:
            satisfied = [r for r in state.requirements if r.status == EvidenceStatus.SATISFIED]
            if satisfied:
                fp = ActionFingerprint(action_type=ActionType.PARTIAL_ANSWER, strategy="no_progress_fallback").to_string()
                return ActionPlan(
                    action_id=action_id,
                    action_type=ActionType.PARTIAL_ANSWER,
                    fingerprint=fp,
                    reason_code="NO_PROGRESS_PARTIAL",
                )
            else:
                fp = ActionFingerprint(action_type=ActionType.ABSTAIN, strategy="no_progress_abort").to_string()
                return ActionPlan(
                    action_id=action_id,
                    action_type=ActionType.ABSTAIN,
                    fingerprint=fp,
                    reason_code="NO_PROGRESS_ABSTAIN",
                )

        # 4. Tìm kiếm bằng chứng cho các yêu cầu chưa thỏa mãn (Unsatisfied Requirements)
        pending_reqs = [
            r for r in state.requirements
            if r.status in (EvidenceStatus.PENDING, EvidenceStatus.INSUFFICIENT, EvidenceStatus.MISSING)
        ]

        if pending_reqs:
            req = pending_reqs[0]

            # Kiểm tra xem yêu cầu này đã vượt quá số lần thử tối đa chưa
            if req.attempt_count >= self.MAX_ATTEMPTS_PER_REQUIREMENT:
                satisfied = [r for r in state.requirements if r.status == EvidenceStatus.SATISFIED]
                if satisfied:
                    fp = ActionFingerprint(action_type=ActionType.PARTIAL_ANSWER, strategy="exhausted_partial").to_string()
                    return ActionPlan(
                        action_id=action_id,
                        action_type=ActionType.PARTIAL_ANSWER,
                        fingerprint=fp,
                        reason_code="REQUIREMENT_EXHAUSTED_PARTIAL",
                    )
                else:
                    fp = ActionFingerprint(action_type=ActionType.ABSTAIN, strategy="exhausted_abstain").to_string()
                    return ActionPlan(
                        action_id=action_id,
                        action_type=ActionType.ABSTAIN,
                        fingerprint=fp,
                        reason_code="REQUIREMENT_EXHAUSTED_ABSTAIN",
                    )

            # Chọn chiến lược truy xuất phù hợp
            if req.field in ("credits", "course_name") and self.entity_catalog.is_known_code(req.entity):
                fp = ActionFingerprint(
                    action_type=ActionType.CATALOG_LOOKUP,
                    entity=req.entity,
                    requested_field=req.field,
                    target_doc_type="curriculum",
                    strategy="catalog_first",
                ).to_string()
                return ActionPlan(
                    action_id=action_id,
                    action_type=ActionType.CATALOG_LOOKUP,
                    entity=req.entity,
                    requested_field=req.field,
                    target_requirement_key=req.requirement_key,
                    fingerprint=fp,
                    reason_code="FAST_CATALOG_LOOKUP",
                )

            # Tra cứu chính xác từ tài liệu docx
            fp = ActionFingerprint(
                action_type=ActionType.RETRIEVE_EXACT,
                entity=req.entity,
                requested_field=req.field,
                target_doc_type=req.accepted_document_types[0] if req.accepted_document_types else "course_outline",
                strategy="exact_match",
            ).to_string()
            return ActionPlan(
                action_id=action_id,
                action_type=ActionType.RETRIEVE_EXACT,
                entity=req.entity,
                requested_field=req.field,
                target_requirement_key=req.requirement_key,
                fingerprint=fp,
                reason_code="EXACT_EVIDENCE_RETRIEVAL",
            )

        # 5. Tất cả các yêu cầu đã được đáp ứng (ALL REQUIREMENTS SATISFIED)
        if len(state.entities) >= 2 or any(obj == "COMPARE_COURSES" for obj in state.objectives):
            fp = ActionFingerprint(action_type=ActionType.COMPARE_EVIDENCE, strategy="synthesize").to_string()
            return ActionPlan(
                action_id=action_id,
                action_type=ActionType.COMPARE_EVIDENCE,
                fingerprint=fp,
                reason_code="COMPARE_MULTI_ENTITY_EVIDENCE",
            )

        fp = ActionFingerprint(action_type=ActionType.FINISH, strategy="complete").to_string()
        return ActionPlan(
            action_id=action_id,
            action_type=ActionType.FINISH,
            fingerprint=fp,
            reason_code="ALL_REQUIREMENTS_SATISFIED",
        )


# Global Singleton
_planner_instance: Optional[AgentPlanner] = None


def get_agent_planner() -> AgentPlanner:
    global _planner_instance
    if _planner_instance is None:
        _planner_instance = AgentPlanner()
    return _planner_instance
