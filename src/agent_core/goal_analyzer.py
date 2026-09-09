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

from src.agent_core.schemas import GoalSpec, GoalType, GoalIntent, GoalScope
from src.agent_core.entity_catalog import get_entity_catalog, EntityCatalog
from src.agent_core.environment_catalog import get_knowledge_environment_catalog, KnowledgeEnvironmentCatalog


class GoalAnalyzer:
    """Bộ phân tích mục tiêu thực sự của người dùng (Goal Understanding V2)."""

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

        # 0. Trích xuất Discourse State từ session_context
        session_last_entity = None
        session_last_intent = None
        session_last_scope = None
        session_last_fields: List[str] = []
        if session_context:
            session_last_entity = (
                session_context.get("last_academic_entity")
                or session_context.get("active_course_code")
                or session_context.get("active_course")
                or session_context.get("active_entity")
            )
            session_last_intent = session_context.get("last_intent")
            session_last_scope = session_context.get("last_scope")
            session_last_fields = session_context.get("last_requested_fields") or []

        # Tự động phân tích ngữ nghĩa phát ngôn nếu chưa được cung cấp
        if utterance_semantics is None:
            try:
                from src.semantics import analyze_utterance
                sem = analyze_utterance(raw_query)
                utterance_semantics = {
                    "polarity": sem.polarity.value,
                    "modality": sem.modality.value,
                    "is_contradictory": sem.is_contradictory,
                }
            except Exception:
                utterance_semantics = None

        # 1. Kiểm tra THỰC THỂ KHÔNG XÁC ĐỊNH (UNKNOWN ENTITY)
        unknown_entities = self.entity_catalog.find_unknown_entities(raw_query)
        if unknown_entities:
            return GoalSpec(
                objectives=[GoalType.UNDEFINED],
                entities=unknown_entities,
                requested_fields=self._extract_fields(lower_query),
                goal_clarity="UNDERSPECIFIED",
                missing_slot="unknown_entity",
                intent=GoalIntent.UNKNOWN,
                scope=GoalScope.SINGLE_FIELD,
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
                intent=GoalIntent.UNKNOWN,
                scope=GoalScope.SINGLE_FIELD,
            )

        # 3. Đại từ / Chỉ định từ trong câu hỏi
        pronoun_patterns = [
            r"\bm[oô]n\s+n[aà]y\b",
            r"\bh[oọ]c\s+ph[aầ]n\s+n[aà]y\b",
            r"\bn[oó]\b",
            r"\bm[oô]n\s+[đd][oó]\b",
            r"\bh[oọ]c\s+ph[aầ]n\s+[đd][oó]\b",
            r"\bm[oô]n\s+tr[eê]n\b",
            r"\bh[oọ]c\s+ph[aầ]n\s+tr[eê]n\b",
            r"\bm[oô]n\s+v[uừ]a\s+r[oồ]i\b",
            r"\bm[oô]n\s+h[oọ]c\s+[đd][oó]\b",
            r"\bm[oô]n\s+h[oọ]c\s+n[aà]y\b",
            r"\bm[oô]n\s+[aấ]y\b",
        ]
        has_pronoun = any(re.search(p, lower_query) for p in pronoun_patterns)

        # 4. Trích xuất Thực thể đã biết trong câu
        known_entities = self.entity_catalog.extract_known_entities(raw_query)

        # 4.1 Nếu không có mã hoặc alias chuẩn, dùng CourseEntityResolver V2
        if not known_entities and not has_pronoun:
            from src.agent_core.course_resolver import get_course_resolver, ResolutionStatus
            res = get_course_resolver().resolve(raw_query, session_context=session_context)
            if res.status == ResolutionStatus.RESOLVED and res.course_code:
                known_entities.append(res.course_code)
            elif res.status == ResolutionStatus.NEEDS_USER_CONFIRMATION:
                return GoalSpec(
                    objectives=[GoalType.UNDEFINED],
                    entities=[res.course_code] if res.course_code else [],
                    requested_fields=self._extract_fields(lower_query),
                    goal_clarity="AMBIGUOUS",
                    missing_slot="entity_confirmation",
                    intent=GoalIntent.UNKNOWN,
                    scope=GoalScope.SINGLE_FIELD,
                )
            elif res.status == ResolutionStatus.UNKNOWN_CODE:
                return GoalSpec(
                    objectives=[GoalType.UNDEFINED],
                    entities=[res.course_code] if res.course_code else [],
                    requested_fields=self._extract_fields(lower_query),
                    goal_clarity="UNDERSPECIFIED",
                    missing_slot="unknown_entity",
                    intent=GoalIntent.UNKNOWN,
                    scope=GoalScope.SINGLE_FIELD,
                )

        # 4.2 Phân giải đại từ (Referent Resolution)
        if has_pronoun and not known_entities:
            if session_last_entity and self.entity_catalog.is_known_code(session_last_entity):
                known_entities.append(session_last_entity)
            else:
                # Có đại từ nhưng không có thực thể trong phiên -> MISSING_ENTITY
                return GoalSpec(
                    objectives=[GoalType.UNDEFINED],
                    entities=[],
                    requested_fields=self._extract_fields(lower_query),
                    goal_clarity="UNDERSPECIFIED",
                    missing_slot="entity",
                    intent=GoalIntent.UNKNOWN,
                    scope=GoalScope.SINGLE_FIELD,
                )

        # 4.3 Khử mơ hồ Khái niệm vs Môn học (Concept vs Course Title Disambiguation)
        conceptual_triggers = [r"\blà gì\b", r"\bnhư thế nào\b", r"\bnguyên lý\b", r"\bkhái niệm\b", r"\bgiải thích\b"]
        has_concept_cue = any(re.search(pat, lower_query) for pat in conceptual_triggers)
        academic_cues = ["mã", "môn", "học phần", "tín chỉ", "tiên quyết", "giảng viên", "thi", "đề cương", "clo", "kỳ"]
        has_academic_cue = any(cue in lower_query for cue in academic_cues)
        has_explicit_code = bool(re.search(r"\b[A-Za-z]{2,4}\d{4}\b", raw_query))

        if known_entities and len(known_entities) == 1 and has_concept_cue and not has_academic_cue and not has_explicit_code:
            code = known_entities[0]
            return GoalSpec(
                objectives=[GoalType.UNDEFINED],
                entities=[code],
                requested_fields=[],
                goal_clarity="AMBIGUOUS",
                missing_slot="concept_course_ambiguity",
                intent=GoalIntent.UNKNOWN,
                scope=GoalScope.SINGLE_FIELD,
            )

        # 5. Trích xuất các trường thông tin được yêu cầu (Requested Fields)
        requested_fields = self._extract_fields(lower_query)

        # 5.1 Kế thừa thực thể cho câu hỏi tiếp nối trường (Follow-up Field Inheritance)
        if not known_entities and requested_fields and session_last_entity:
            if self.entity_catalog.is_known_code(session_last_entity):
                known_entities.append(session_last_entity)

        # 5.2 Chuyển đổi thực thể và kế thừa ý định (Entity Switch with Intent/Field Inheritance)
        is_entity_switch = bool(
            re.search(r"\b(còn|thế\s+còn|môn\s+khác)\b", lower_query)
            or (len(known_entities) == 1 and len(requested_fields) == 0 and session_last_entity and known_entities[0] != session_last_entity)
        )
        if is_entity_switch and len(known_entities) == 1 and not requested_fields:
            if session_last_fields:
                requested_fields = list(session_last_fields)
            elif session_last_intent == GoalIntent.COURSE_OVERVIEW.value or session_last_scope == GoalScope.SUMMARY.value:
                has_overview_cue = True
            elif session_last_intent == GoalIntent.COURSE_FULL_DETAILS.value or session_last_scope == GoalScope.ALL_AVAILABLE.value:
                is_full_details = True

        # 5.3 Fallback thực thể từ Session nếu chưa có
        if not known_entities and session_last_entity and self.entity_catalog.is_known_code(session_last_entity):
            known_entities.append(session_last_entity)

        # 6. Kiểm tra các ý định công cụ (Tool Intents)
        tool_objectives = self._extract_tool_intents(lower_query, utterance_semantics)

        # 7. Phân biệt so sánh đa thực thể
        is_comparison = (len(known_entities) >= 2) or bool(
            re.search(r"\b(so\s+sánh|khác\s+nhau|giống\s+nhau|môn\s+nào\s+.*hơn)\b", lower_query)
        )

        # 8. Xác định Intent và Scope (Goal Intent & Scope Classification)
        full_detail_cues = [
            "tất cả", "toàn bộ", "tất cả thông tin", "chi tiết tổng thể",
            "tổng thể", "chi tiết tất cả", "tất cả về", "mọi thông tin",
            "full thông tin", "đầy đủ thông tin"
        ]
        is_full_details = any(cue in lower_query for cue in full_detail_cues)

        overview_cues = [
            "chi tiết", "cho tôi biết về", "giới thiệu", "thông tin môn",
            "tổng quan", "môn này thế nào", "môn này có gì", "tìm hiểu về",
            "thông tin học phần", "nội dung môn"
        ]
        has_overview_cue = any(cue in lower_query for cue in overview_cues)

        intent = GoalIntent.UNKNOWN
        scope = GoalScope.SINGLE_FIELD

        if tool_objectives:
            intent = GoalIntent.TOOL_ACTION
            scope = GoalScope.SINGLE_FIELD
        elif is_comparison:
            intent = GoalIntent.COURSE_COMPARISON
            scope = GoalScope.SUMMARY
            if not requested_fields:
                requested_fields = ["credits", "lecturer", "prerequisites", "assessment"]
        elif any(f in ("graduation_requirements", "academic_warning", "training_rules", "regulation") for f in requested_fields):
            intent = GoalIntent.REGULATION_LOOKUP
            scope = GoalScope.SINGLE_FIELD
        elif known_entities:
            if is_full_details:
                intent = GoalIntent.COURSE_FULL_DETAILS
                scope = GoalScope.ALL_AVAILABLE
                requested_fields = [
                    "credits", "lecturer", "prerequisites", "assessment", "clo", "hours",
                    "course_plan", "department", "english_name"
                ]
            elif not requested_fields or has_overview_cue:
                # Broad Academic Intent: COURSE_OVERVIEW
                intent = GoalIntent.COURSE_OVERVIEW
                scope = GoalScope.SUMMARY
                requested_fields = [
                    "credits", "lecturer", "prerequisites", "assessment", "clo", "hours", "course_plan"
                ]
            else:
                intent = GoalIntent.COURSE_FIELD_LOOKUP
                scope = GoalScope.SINGLE_FIELD

        # 9. Xây dựng danh sách mục tiêu chính (Objectives)
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

        # 10. Đánh giá tính rõ ràng của mục tiêu (Goal Clarity & Missing Slots)
        # TH 10.1: Dữ liệu KHÔNG TỒN TẠI trong tài liệu chính thức (MISSING_DATA)
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
                intent=intent,
                scope=scope,
            )

        # TH 10.2: Thiếu thực thể (MISSING_ENTITY)
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
                intent=GoalIntent.UNKNOWN,
                scope=GoalScope.SINGLE_FIELD,
            )

        # TH 10.3: Thiếu ý định thực sự (MISSING_INTENT)
        # Chỉ khi có >=2 môn không có từ khóa so sánh và không có trường cụ thể
        # Hoặc câu hỏi hoàn toàn vô định không có thực thể (e.g. "học kỳ này học môn gì")
        is_truly_missing_intent = (
            (len(known_entities) >= 2 and not is_comparison and len(self._extract_fields(lower_query)) == 0)
            or ("học kỳ này học môn gì" in lower_query and not known_entities)
            or ("đăng ký môn học thì thế nào" in lower_query and not known_entities)
        )
        if is_truly_missing_intent:
            return GoalSpec(
                objectives=[GoalType.UNDEFINED],
                entities=known_entities,
                requested_fields=[],
                is_multi_entity=len(known_entities) >= 2,
                is_multi_intent=False,
                goal_clarity="UNDERSPECIFIED",
                missing_slot="intent",
                intent=GoalIntent.UNKNOWN,
                scope=GoalScope.SINGLE_FIELD,
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
            intent=intent,
            scope=scope,
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
        if any(w in lower_text for w in ["khó hơn", "độ khó", "khó nhất", "dễ hơn", "khó hay dễ", "môn nào khó", "có khó không", "dễ qua môn", "dễ qua", "dễ đạt", "điểm a", "nhàn hơn", "học nhàn", "nhàn nhất", "học nhàn hơn", "nhàn"]):
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
        if utterance_semantics:
            if (
                utterance_semantics.get("polarity") == "NEGATED"
                or utterance_semantics.get("modality") in ("HYPOTHETICAL", "CONDITIONAL", "EXPLANATORY")
                or utterance_semantics.get("is_contradictory")
            ):
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
