"""
Goal Analyzer (UNDERSTAND Phase) for Goal-Driven Agent Core V1.
Analyzes user input to uncover true goals, active entities, requested fields,
and explicitly identifies missing information:
- MISSING INTENT (e.g. "FIT4201 với FIT4104 thì sao?")
- MISSING ENTITY (e.g. "Môn đó bao nhiêu tín chỉ?" without active session entity)
- MISSING DATA / UNAVAILABLE FIELDS (e.g. "FIT4201 tỷ lệ trượt bao nhiêu?")
- UNKNOWN ENTITY (e.g. "FIT9999 bao nhiêu tín chỉ?")
- ENTITY CONFLICT (e.g. "FIT4201 môn Full-Stack bao nhiêu tín chỉ?")
"""
import re
from typing import Dict, Any, List, Optional

from src.agent_core.schemas import GoalSpec, GoalType
from src.agent_core.entity_catalog import get_entity_catalog, EntityCatalog
from src.agent_core.environment_catalog import get_knowledge_environment_catalog, KnowledgeEnvironmentCatalog


class GoalAnalyzer:
    """Bộ phân tích mục tiêu thực sự của người dùng."""

    def __init__(
        self,
        entity_catalog: Optional[EntityCatalog] = None,
        env_catalog: Optional[KnowledgeEnvironmentCatalog] = None,
    ):
        self.entity_catalog = entity_catalog or get_entity_catalog()
        self.env_catalog = env_catalog or get_knowledge_environment_catalog()

    def analyze(
        self,
        query: str,
        session_context: Optional[Dict[str, Any]] = None,
        utterance_semantics: Optional[Dict[str, Any]] = None,
    ) -> GoalSpec:
        """Phân tích toàn diện câu hỏi và ngữ cảnh để xây dựng GoalSpec."""
        raw_query = (query or "").strip()
        lower_query = raw_query.lower()

        # 1. Kiểm tra THỰC THỂ KHÔNG XÁC ĐỊNH (UNKNOWN ENTITY)
        unknown_entities = self.entity_catalog.find_unknown_entities(raw_query)
        if unknown_entities:
            return GoalSpec(
                objectives=[GoalType.UNDEFINED],
                entities=unknown_entities,
                requested_fields=self._extract_fields(lower_query),
                goal_clarity="UNDERSPECIFIED",
                missing_slot="unknown_entity",
            )

        # 2. Kiểm tra MÂU THUẪN THỰC THỂ (ENTITY CONFLICT: Mã A + Tên môn B)
        conflict = self.entity_catalog.check_entity_conflict(raw_query)
        if conflict:
            return GoalSpec(
                objectives=[GoalType.UNDEFINED],
                entities=[conflict["code"], conflict["conflicting_code"]],
                requested_fields=self._extract_fields(lower_query),
                goal_clarity="AMBIGUOUS",
                missing_slot="entity_conflict",
            )

        # 3. Trích xuất Thực thể đã biết trong câu
        known_entities = self.entity_catalog.extract_known_entities(raw_query)

        # 4. Phục hồi thực thể từ Session Context (nếu câu hỏi không có thực thể rõ ràng)
        active_course_code = None
        if session_context:
            active_course_code = (
                session_context.get("active_course_code")
                or session_context.get("active_course")
                or session_context.get("active_entity")
            )

        if not known_entities and active_course_code and self.entity_catalog.is_known_code(active_course_code):
            known_entities.append(active_course_code)

        # 5. Trích xuất các trường thông tin được yêu cầu (Requested Fields)
        requested_fields = self._extract_fields(lower_query)

        # 6. Kiểm tra các ý định công cụ (Tool Intents)
        tool_objectives = self._extract_tool_intents(lower_query, utterance_semantics)

        # 7. Phân biệt so sánh đa thực thể
        is_comparison = (len(known_entities) >= 2) or bool(
            re.search(r"\b(so\s+sánh|khác\s+nhau|giống\s+nhau|môn\s+nào\s+.*hơn)\b", lower_query)
        )

        # 8. Xây dựng danh sách mục tiêu chính (Objectives)
        objectives: List[GoalType] = []
        if is_comparison:
            objectives.append(GoalType.COMPARE_COURSES)

        for f in requested_fields:
            if f == "credits":
                objectives.append(GoalType.LOOKUP_CREDITS)
            elif f == "lecturer":
                objectives.append(GoalType.LOOKUP_LECTURER)
            elif f == "lecturer_email":
                objectives.append(GoalType.LOOKUP_LECTURER_EMAIL)
            elif f == "prerequisites":
                objectives.append(GoalType.LOOKUP_PREREQUISITES)
            elif f == "assessment":
                objectives.append(GoalType.LOOKUP_ASSESSMENT)
            elif f in ("clo", "objectives"):
                objectives.append(GoalType.LOOKUP_CLO)
            elif f in ("course_plan", "semester", "hours", "department", "english_name"):
                objectives.append(GoalType.LOOKUP_COURSE_PLAN)
            elif f in ("graduation_requirements", "academic_warning", "training_rules", "regulation"):
                objectives.append(GoalType.LOOKUP_REGULATION)

        # Bổ sung tool objectives
        objectives.extend(tool_objectives)

        # 9. Đánh giá tính rõ ràng của mục tiêu (Goal Clarity & Missing Slots)
        # TH 9.1: Dữ liệu KHÔNG TỒN TẠI trong tài liệu chính thức (MISSING_DATA)
        unavail_in_query = [f for f in requested_fields if f in self.env_catalog.UNAVAILABLE_FIELDS]
        if unavail_in_query:
            return GoalSpec(
                objectives=objectives or [GoalType.UNDEFINED],
                entities=known_entities,
                requested_fields=requested_fields,
                is_multi_entity=len(known_entities) >= 2,
                is_multi_intent=len(tool_objectives) > 0,
                goal_clarity="UNDERSPECIFIED",
                missing_slot="data",
            )

        # TH 9.2: Kiểm tra ý định bị thiếu / câu hỏi chung chung không đủ thông tin (MISSING_INTENT)
        is_general_vague = ("học kỳ này học môn gì" in lower_query) or ("đăng ký môn học" in lower_query)
        has_vague_intent = any(
            phrase in lower_query for phrase in [
                "thì sao", "thế nào", "có gì", "nè", "học môn gì", "đăng ký môn học"
            ]
        )
        is_missing_intent = (
            is_general_vague
            or (len(known_entities) >= 2 and len(requested_fields) == 0)
            or (len(known_entities) > 0 and len(requested_fields) == 0)
            or (len(known_entities) == 1 and has_vague_intent and len(requested_fields) == 0)
        )

        if is_missing_intent:
            return GoalSpec(
                objectives=[GoalType.UNDEFINED],
                entities=known_entities,
                requested_fields=[],
                is_multi_entity=len(known_entities) >= 2,
                is_multi_intent=False,
                goal_clarity="UNDERSPECIFIED",
                missing_slot="intent",
            )

        # TH 9.3: Thiếu thực thể hoàn toàn (không có trong câu và session)
        is_general_regulation = any(
            f in ("graduation_requirements", "academic_warning", "training_rules", "regulation")
            for f in requested_fields
        )
        if not known_entities and not is_general_regulation and not tool_objectives:
            return GoalSpec(
                objectives=[GoalType.UNDEFINED],
                entities=[],
                requested_fields=requested_fields,
                goal_clarity="UNDERSPECIFIED",
                missing_slot="entity",
            )
        # Ví dụ: "FIT4201 với FIT4104 thì sao?", "Môn FIT4113", "FIT4201?", "Học kỳ này học môn gì?"
        has_vague_intent = any(
            phrase in lower_query for phrase in [
                "thì sao", "thế nào", "có gì", "nè", "hông ad", "học môn gì", "đăng ký môn học thì thế nào"
            ]
        )
        is_missing_intent = (
            (len(known_entities) > 0 and len(requested_fields) == 0)
            or (len(known_entities) >= 2 and len(requested_fields) == 0)
            or ("học kỳ này học môn gì" in lower_query)
            or ("đăng ký môn học thì thế nào" in lower_query)
            or (len(known_entities) == 1 and has_vague_intent and len(requested_fields) == 0)
        )

        if is_missing_intent:
            return GoalSpec(
                objectives=[GoalType.UNDEFINED],
                entities=known_entities,
                requested_fields=[],
                is_multi_entity=len(known_entities) >= 2,
                is_multi_intent=False,
                goal_clarity="UNDERSPECIFIED",
                missing_slot="intent",
            )

        # Nếu không có thiếu sót nào -> Mục tiêu RÕ RÀNG (CLEAR GOAL)
        return GoalSpec(
            objectives=objectives or [GoalType.GENERAL_KNOWLEDGE],
            entities=known_entities,
            requested_fields=requested_fields,
            is_multi_entity=len(known_entities) >= 2,
            is_multi_intent=len(tool_objectives) > 0,
            goal_clarity="CLEAR",
            missing_slot=None,
        )

    def _extract_fields(self, lower_text: str) -> List[str]:
        """Trích xuất các trường thông tin mà người dùng đang tìm kiếm."""
        fields: List[str] = []

        # Tín chỉ
        if any(w in lower_text for w in ["tín chỉ", "tin chi", "mấy tín", "may tin", "bao nhiêu tín", "bao nhiu tin", "số tín", "tín", "tc"]):
            fields.append("credits")

        # Giảng viên
        if any(w in lower_text for w in ["email của giảng viên", "email của thầy", "email của cô", "email liên hệ", "địa chỉ email", "email"]):
            fields.append("lecturer_email")
        elif any(w in lower_text for w in ["giảng viên", "giang vien", "ai dạy", "ai day", "thầy nào", "thầy dạy", "cô nào", "phụ trách môn", "người dạy"]):
            fields.append("lecturer")

        # Tiên quyết
        if any(w in lower_text for w in ["tiên quyết", "học trước", "điều kiện học", "yêu cầu môn học", "tiên quyết không"]):
            fields.append("prerequisites")

        # Đánh giá & thi cử
        if any(w in lower_text for w in ["đánh giá", "danh gia", "thi", "thi cuối kỳ", "thi giữa kỳ", "thi thế nào", "thi tự luận", "thi trắc nghiệm", "hình thức thi", "điểm thi", "chuyên cần", "tỷ trọng", "phần trăm", "cột điểm", "kiểm tra", "50%", "cấu trúc điểm", "điểm số"]):
            fields.append("assessment")

        # Chuẩn đầu ra & Mục tiêu
        if any(w in lower_text for w in ["chuẩn đầu ra", "chuan dau ra", "clo", "mục tiêu đầu ra"]):
            fields.append("clo")
        elif any(w in lower_text for w in ["mục tiêu môn học", "mục tiêu"]):
            fields.append("objectives")

        # Số giờ học & thực hành
        if any(w in lower_text for w in ["giờ lý thuyết", "giờ thực hành", "bao nhiêu giờ", "tiết thực hành", "tiết lý thuyết", "giờ", "thực hành", "lý thuyết"]):
            fields.append("hours")

        # Khoa / Bộ môn
        if any(w in lower_text for w in ["khoa", "bộ môn"]):
            fields.append("department")

        # Tên tiếng Anh
        if any(w in lower_text for w in ["tiếng anh", "english name", "tên tiếng anh"]):
            fields.append("english_name")

        # Kế hoạch học tập / Kỳ học
        if any(w in lower_text for w in ["học kỳ", "kỳ mấy", "năm mấy", "tuần học", "kế hoạch giảng dạy", "lịch trình"]):
            fields.append("course_plan")

        # Quy chế đào tạo
        if any(w in lower_text for w in ["tốt nghiệp", "xét tốt nghiệp", "điều kiện ra trường"]):
            fields.append("graduation_requirements")
        if any(w in lower_text for w in ["cảnh báo học vụ", "buộc thôi học", "bị đuổi học"]):
            fields.append("academic_warning")
        if any(w in lower_text for w in ["quy chế", "quy định", "học vụ", "điểm chuyên cần tối đa"]):
            fields.append("training_rules")

        # Dữ liệu KHÔNG TỒN TẠI trong môi trường học vụ (đánh dấu tường minh)
        if any(w in lower_text for w in ["tỷ lệ trượt", "rớt môn", "trượt môn", "bao nhiêu đứa trượt", "tỷ lệ đỗ", "tỷ lệ rớt", "tỷ lệ qua môn"]) or ("qua môn" in lower_text and "dễ" not in lower_text):
            fields.append("failure_rate")
        if any(w in lower_text for w in ["khó hơn", "độ khó", "khó nhất", "dễ hơn", "khó hay dễ", "môn nào khó", "có khó không", "dễ qua môn", "dễ qua", "dễ đạt", "điểm a"]):
            fields.append("difficulty")
        if any(w in lower_text for w in ["review", "đánh giá của sinh viên", "sinh viên nói gì", "chấm điểm thầy", "sinh viên review", "chấm gắt", "chấm điểm có gắt không", "chấm có gắt không", "chấm gắt không"]):
            fields.append("student_rating")
        if any(w in lower_text for w in ["lương", "mức lương", "thu nhập", "mấy chục triệu"]):
            fields.append("job_salary")
        if any(w in lower_text for w in ["lộ", "leak", "bị lộ", "đề thi có bị lộ", "đề thi năm ngoái"]):
            fields.append("exam_leak")

        return fields

    def _extract_tool_intents(
        self,
        lower_text: str,
        utterance_semantics: Optional[Dict[str, Any]] = None,
    ) -> List[GoalType]:
        """Trích xuất các ý định thao tác công cụ khẳng định."""
        tools: List[GoalType] = []

        # Kiểm tra qua Utterance Semantics nếu có
        if utterance_semantics and utterance_semantics.get("modality") != "ASSERTED":
            return tools

        if any(w in lower_text for w in ["nhắc tôi", "đặt lịch", "tạo reminder", "nhớ báo", "hẹn giờ"]):
            tools.append(GoalType.SET_REMINDER)

        if any(w in lower_text for w in ["gửi email", "gửi mail", "soạn mail", "báo cho thầy", "gửi cho khoa"]):
            tools.append(GoalType.SEND_EMAIL)

        return tools


# Global Singleton
_goal_analyzer_instance: Optional[GoalAnalyzer] = None


def get_goal_analyzer() -> GoalAnalyzer:
    global _goal_analyzer_instance
    if _goal_analyzer_instance is None:
        _goal_analyzer_instance = GoalAnalyzer()
    return _goal_analyzer_instance
