"""
Goal Analyzer (UNDERSTAND Phase) for Goal-Driven Agent Core V1.1 / Round P2.1.
Tích hợp trực tiếp với SemanticGoalInterpreter để hiện thực hóa
Hybrid Semantic Structured Understanding:
- Tự động hiểu phát ngôn tự nhiên của sinh viên qua BGE-M3 intent matching
- Nhận diện thực thể, phân giải đại từ và kế thừa ngữ cảnh phiên (Discourse State)
- Trích xuất ràng buộc ngữ nghĩa (PRACTICAL_WORKLOAD, CONTAINS_CONCEPT,...)
- Hỗ trợ Aggregation (COUNT, LIST, COMPARE) và Comparison (GREATER_THAN, LESS_THAN)
- Đảm bảo 100% tuân thủ các quy tắc an toàn và kiểm soát mâu thuẫn nội tại
"""
import logging
from typing import Dict, Any, List, Optional

from src.agent_core.schemas import (
    GoalSpec,
    GoalType,
    GoalIntent,
    GoalFrame,
)
from src.agent_core.entity_catalog import get_entity_catalog, EntityCatalog
from src.agent_core.environment_catalog import get_knowledge_environment_catalog, KnowledgeEnvironmentCatalog
from src.agent_core.semantic_goal_interpreter import get_semantic_goal_interpreter, SemanticGoalInterpreter

logger = logging.getLogger(__name__)


class GoalAnalyzer:
    """Bộ phân tích mục tiêu thực sự của người dùng (Goal Understanding V2.1)."""

    def __init__(
        self,
        entity_catalog: Optional[EntityCatalog] = None,
        env_catalog: Optional[KnowledgeEnvironmentCatalog] = None,
        interpreter: Optional[SemanticGoalInterpreter] = None,
    ):
        self.entity_catalog = entity_catalog or get_entity_catalog()
        self.env_catalog = env_catalog or get_knowledge_environment_catalog()
        self.interpreter = interpreter or get_semantic_goal_interpreter()

    def analyze(
        self,
        query: str,
        session_context: Optional[Dict[str, Any]] = None,
        utterance_semantics: Optional[Dict[str, Any]] = None,
    ) -> GoalSpec:
        """
        Phân tích toàn diện câu hỏi và ngữ cảnh bằng SemanticGoalInterpreter
        và trả về đối tượng GoalSpec hoàn chỉnh chứa GoalFrame.
        """
        frame: GoalFrame = self.interpreter.interpret(
            query=query,
            session_context=session_context,
            utterance_semantics=utterance_semantics,
        )

        # Xây dựng danh sách mục tiêu chính (Objectives)
        objectives: List[GoalType] = []
        if frame.tool_action == "SEND_EMAIL":
            objectives.append(GoalType.SEND_EMAIL)
        elif frame.tool_action == "SET_REMINDER":
            objectives.append(GoalType.SET_REMINDER)
        elif frame.intent == GoalIntent.COURSE_COMPARISON:
            objectives.append(GoalType.COMPARE_COURSES)
        elif frame.intent == GoalIntent.REGULATION_LOOKUP:
            objectives.append(GoalType.LOOKUP_REGULATION)
        elif frame.intent == GoalIntent.GENERAL_TOPIC_EXPLANATION:
            objectives.append(GoalType.GENERAL_KNOWLEDGE)

        field_to_goal_type = {
            "credits": GoalType.LOOKUP_CREDITS,
            "lecturer": GoalType.LOOKUP_LECTURER,
            "lecturer_email": GoalType.LOOKUP_LECTURER_EMAIL,
            "prerequisites": GoalType.LOOKUP_PREREQUISITES,
            "assessment": GoalType.LOOKUP_ASSESSMENT,
            "clo": GoalType.LOOKUP_CLO,
            "hours": GoalType.LOOKUP_SCHEDULE,
            "course_plan": GoalType.LOOKUP_COURSE_PLAN,
            "regulation": GoalType.LOOKUP_REGULATION,
        }

        for f in frame.requested_fields:
            gt = field_to_goal_type.get(f)
            if gt and gt not in objectives:
                objectives.append(gt)

        if not objectives:
            objectives.append(GoalType.UNDEFINED)

        # Xác định missing_slot chính
        missing_slot = frame.missing_slots[0] if frame.missing_slots else None

        # Xác định unsupported_intents
        unsupported_intents = [f for f in frame.requested_fields if self.env_catalog.is_field_unavailable(f)]

        # Xác định goal_clarity
        if missing_slot in ("unknown_entity", "entity", "intent", "data_alternative", "data"):
            goal_clarity = "UNDERSPECIFIED"
        elif missing_slot in ("entity_conflict", "concept_course_ambiguity"):
            goal_clarity = "AMBIGUOUS"
        else:
            goal_clarity = "CLEAR"

        # Thiết lập câu hỏi làm rõ có định hướng (Targeted Clarification Prompt & Options)
        clarification_prompt = None
        clarification_options: List[str] = []

        if missing_slot == "unknown_entity":
            code_str = ", ".join(frame.entities) if frame.entities else "này"
            clarification_prompt = f"Mã học phần {code_str} không tồn tại trong danh mục chương trình đào tạo của trường."
        elif missing_slot == "entity_conflict":
            clarification_prompt = "Phát hiện mâu thuẫn giữa mã môn học và tên môn học trong câu hỏi của bạn."
        elif missing_slot == "entity":
            clarification_prompt = (
                "Bạn đang hỏi về môn học / học phần nào? Vui lòng cung cấp tên môn học "
                "hoặc mã học phần để mình tra cứu chính xác nhé."
            )
            clarification_options = []
        elif missing_slot == "concept_course_ambiguity":
            code = frame.entities[0] if frame.entities else ""
            c_info = self.entity_catalog.get_course_info(code)
            c_name = c_info.get("canonical_name", code) if c_info else code
            clarification_prompt = (
                f"Bạn đang muốn xem thông tin học phần **{c_name}** ({code}), "
                f"hay muốn tìm hiểu khái niệm **{c_name}** trong thực tế?"
            )
            clarification_options = [
                f"Xem thông tin học phần {code} - {c_name}",
                f"Giải thích khái niệm công nghệ '{c_name}'",
            ]
        elif missing_slot in ("data", "data_alternative"):
            clarification_prompt = frame.suggested_alternative or frame.unsupported_reason
            if frame.suggested_alternative:
                clarification_options = [
                    "Đồng ý so sánh theo tiêu chí có trong đề cương",
                    "Không, hủy yêu cầu",
                ]
        elif missing_slot == "intent":
            clarification_prompt = "Bạn muốn biết thông tin cụ thể gì về học phần này?"
            clarification_options = [
                "Số tín chỉ",
                "Giảng viên phụ trách",
                "Chuẩn đầu ra (CLO)",
                "Hình thức đánh giá / thi",
            ]

        from src.agent_core.query_planner import AcademicQueryPlanner
        planner = AcademicQueryPlanner()
        profile_data = (session_context.get("personal_context") if session_context else None) or {}
        query_plan = planner.create_plan(frame, student_profile=profile_data)

        return GoalSpec(
            intent=frame.intent,
            scope=frame.scope,
            objectives=objectives,
            entities=list(frame.entities),
            subjects=list(frame.subjects),
            subject_type=frame.subject_type,
            operation=frame.operation,
            query_plan=query_plan,
            referents=list(frame.referents),
            requested_fields=list(frame.requested_fields),
            constraints=list(frame.constraints),
            aggregation=frame.aggregation,
            comparison=frame.comparison,
            goal_frame=frame,
            is_multi_entity=len(frame.entities) >= 2,
            is_multi_intent=len(objectives) > 1,
            unsupported_intents=unsupported_intents,
            goal_clarity=goal_clarity,
            missing_slot=missing_slot,
            clarification_prompt=clarification_prompt,
            clarification_options=clarification_options,
            unsupported_reason=frame.unsupported_reason,
            suggested_alternative=frame.suggested_alternative,
            result_scope=getattr(frame, "result_scope", None) or (query_plan.result_scope if query_plan else None),
            limit=getattr(frame, "limit", None) or (query_plan.limit if query_plan else None),
            page=getattr(frame, "page", None) or (query_plan.page if query_plan else None),
        )


# Global Singleton
_goal_analyzer_instance: Optional[GoalAnalyzer] = None


def get_goal_analyzer() -> GoalAnalyzer:
    global _goal_analyzer_instance
    if _goal_analyzer_instance is None:
        _goal_analyzer_instance = GoalAnalyzer()
    return _goal_analyzer_instance
