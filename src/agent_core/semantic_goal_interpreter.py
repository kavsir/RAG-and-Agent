"""
Semantic Goal Interpreter (Round P2.1):
Triển khai toàn diện đường ống UNDERSTAND ngữ nghĩa lai (Hybrid Semantic Structured Understanding):
Normalize
→ Resolve discourse context
→ Resolve academic entities
→ Extract deterministic safety/tool signals
→ Semantic intent interpretation (BGE-M3)
→ Structured slot extraction (fields, constraints, aggregation, comparison)
→ Confidence / ambiguity policy
→ GoalFrame
"""
import re
import json
import logging
from typing import Dict, Any, List, Optional

from src.agent_core.schemas import (
    EntityType,
    AcademicEntity,
    AcademicOperation,
    GoalIntent,
    GoalScope,
    AggregationType,
    ReferentType,
    ComparisonType,
    GoalFrame,
    validate_goal_frame,
)
from src.memory.student_memory import StudentMemory
from src.agent_core.academic_store import normalize_cohort, normalize_major
from src.agent_core.semantic_intent_registry import get_semantic_intent_matcher, SemanticIntentMatcher
from src.agent_core.entity_catalog import get_entity_catalog, EntityCatalog
from src.agent_core.course_resolver import get_course_resolver, CourseEntityResolver, ResolutionStatus, strip_accents
from src.semantics import analyze_utterance

logger = logging.getLogger(__name__)


# Supported auto fields for Course Overview
OVERVIEW_FIELDS = [
    "credits", "lecturer", "prerequisites", "assessment", "clo", "hours", "course_plan"
]
FULL_DETAILS_FIELDS = [
    "credits", "lecturer", "prerequisites", "assessment", "clo", "hours",
    "course_plan", "department", "english_name"
]


class SemanticGoalInterpreter:
    """
    Bộ thông dịch mục tiêu ngữ nghĩa lai cấu trúc hóa (Round P2.1).
    Tuân thủ thứ bậc thẩm quyền:
    explicit current user entity > explicit current user intent > strong semantic interpretation > previous-turn inherited context > weak heuristic.
    """

    def __init__(
        self,
        intent_matcher: Optional[SemanticIntentMatcher] = None,
        entity_catalog: Optional[EntityCatalog] = None,
        course_resolver: Optional[CourseEntityResolver] = None,
    ):
        self.intent_matcher = intent_matcher or get_semantic_intent_matcher()
        self.entity_catalog = entity_catalog or get_entity_catalog()
        self.course_resolver = course_resolver or get_course_resolver()
        self.llm_fallback_count = 0
        self.schema_failure_count = 0
        self.total_interpret_count = 0

    def interpret(
        self,
        query: str,
        session_context: Optional[Dict[str, Any]] = None,
        utterance_semantics: Optional[Dict[str, Any]] = None,
        profile_context: Optional[Dict[str, Any]] = None,
    ) -> GoalFrame:
        """
        Thực thi toàn bộ 8 bước của pipeline UNDERSTAND để sinh ra GoalFrame có kiểu.
        """
        self.total_interpret_count += 1
        raw_query = (query or "").strip()

        # =====================================================================
        # BƯỚC 1: NORMALIZE
        # =====================================================================
        clean_query = re.sub(r"\s+", " ", raw_query).strip()
        clean_lower = clean_query.lower()

        # =====================================================================
        # BƯỚC 2: RESOLVE DISCOURSE CONTEXT
        # =====================================================================
        session_last_entity = None
        session_last_intent = None
        session_last_fields: List[str] = []
        session_last_constraints: List[str] = []

        if session_context:
            session_last_entity = (
                session_context.get("last_academic_entity")
                or session_context.get("active_course_code")
                or session_context.get("active_course")
                or session_context.get("active_entity")
            )
            session_last_intent = session_context.get("last_intent")
            session_last_fields = session_context.get("last_requested_fields") or []
            session_last_constraints = session_context.get("last_constraints") or []

        pronoun_patterns = [
            r"\b(nó|cái\s+này|môn\s+này|học\s+phần\s+này)\b",
        ]
        has_pronoun = any(re.search(pat, clean_lower) for pat in pronoun_patterns)

        previous_entity_cues = [
            r"\b(môn\s+(đó|kia|ấy|vừa\s+nói|vừa\s+hỏi|trên))\b",
            r"\bcái\s+(đó|kia)\b",
        ]
        has_previous_entity_cue = any(re.search(pat, clean_lower) for pat in previous_entity_cues)
        has_entity_switch_cue = bool(re.search(r"\b(còn|thế\s+còn|môn\s+khác)\b", clean_lower))

        # =====================================================================
        # BƯỚC 3: RESOLVE ACADEMIC ENTITIES
        # =====================================================================
        entities: List[str] = []
        referents: List[ReferentType] = []
        resolution_sources: Dict[str, str] = {}

        # 3.0 Nhận diện tín hiệu đối tượng học vụ có kiểu (Round A1: Curriculum, Cohort, Major, Semester, Regulation)
        clean_unaccented = strip_accents(clean_lower)
        profile_data = profile_context or (session_context.get("personal_context") if session_context else None) or StudentMemory().get_profile()

        is_curriculum_phrase = bool(
            re.search(r"\b(chương trình đào tạo|ctđt|ctdt|khung chương trình|chương trình học|lộ trình học)\b", clean_lower)
            or re.search(r"\b(chuong trinh dao tao|khung chuong trinh|chuong trinh hoc|lo trinh hoc)\b", clean_unaccented)
        )
        cohort_match = re.search(r"\b(?:khóa|khoa|k)\s*(\d{2})\b", clean_lower)
        has_cohort_in_query = bool(cohort_match)

        sem_match = (
            re.search(r"\b(?:học\s+kỳ|kỳ|hk)\s*(\d{1,2})\b", clean_lower)
            or re.search(r"\b(?:hoc\s+ky|ky|hk)\s*(\d{1,2})\b", clean_unaccented)
        )
        has_semester_in_query = bool(sem_match)

        has_course_placement_cue = bool(
            re.search(r"\b(kỳ mấy|ở kỳ nào|thuộc kỳ nào|kỳ nào học|học kỳ mấy|nằm ở kỳ|nằm kỳ nào|học vào kỳ nào)\b", clean_lower)
            or re.search(r"\b(ky may|o ky nao|thuoc ky nao|ky nao hoc|hoc ky may|nam o ky|nam ky nao|hoc vao ky nao)\b", clean_unaccented)
        )
        has_total_credits_cue = bool(
            re.search(r"\b(tổng\s+tín\s+chỉ|tổng\s+số\s+tín\s+chỉ|bao\s+nhiêu\s+tín\s+chỉ|bao\s+nhiêu\s+tín)\b", clean_lower)
            or re.search(r"\b(tong\s+tin\s+chi|tong\s+so\s+tin\s+chi|bao\s+nhieu\s+tin\s+chi|bao\s+nhieu\s+tin)\b", clean_unaccented)
        )
        cohort_cues = ["học những gì", "học gì", "môn gì", "tín chỉ", "chương trình", "môn nào", "kế hoạch", "những môn gì", "những môn nào"]
        semester_cues = ["học những gì", "học gì", "môn gì", "những môn gì", "môn nào", "những môn nào", "có môn nào", "có những môn nào", "gồm những môn", "gồm môn nào", "kế hoạch", "những gì", "danh sách"]

        major_patterns = [
            ("Khoa học máy tính", [r"\bkhoa\s+học\s+máy\s+tính\b", r"\bkhmt\b", r"\bcomputer\s+science\b"]),
            ("Công nghệ thông tin", [r"\bcông\s+nghệ\s+thông\s+tin\b", r"\bcntt\b", r"\binformation\s+technology\b"]),
            ("Hệ thống thông tin", [r"\bhệ\s+thống\s+thông\s+tin\b", r"\bhttt\b", r"\binformation\s+systems\b"]),
        ]
        curr_major = None
        for m_name, pats in major_patterns:
            if any(re.search(p, clean_lower) for p in pats) or any(re.search(p, clean_unaccented) for p in pats):
                curr_major = m_name
                major_source = "explicit_query"
                break
        has_explicit_major = curr_major is not None
        if not curr_major:
            curr_major = normalize_major(profile_data.get("major", "Khoa học máy tính"))
            major_source = "profile_context"

        has_major_cues = bool(re.search(r"\b(ngành|chuyên\s+ngành|nganh|chuyen\s+nganh)\b", clean_lower))

        is_curriculum_query = (
            is_curriculum_phrase
            or (has_cohort_in_query and (any(w in clean_lower for w in cohort_cues) or any(w in clean_unaccented for w in cohort_cues)))
            or (has_semester_in_query and (session_last_intent == GoalIntent.CURRICULUM_OVERVIEW.value or any(w in clean_lower for w in ["thì sao", "còn", "học"]) or any(w in clean_lower for w in semester_cues) or any(w in clean_unaccented for w in semester_cues)))
            or has_course_placement_cue
            or (has_total_credits_cue and (is_curriculum_phrase or has_cohort_in_query or "chương trình" in clean_lower or "ngành" in clean_lower or session_last_intent == GoalIntent.CURRICULUM_OVERVIEW.value))
            or (has_explicit_major and (has_major_cues or session_last_intent == GoalIntent.CURRICULUM_OVERVIEW.value or is_curriculum_phrase or any(w in clean_lower for w in ["học", "chương trình", "môn", "kế hoạch", "tín chỉ", "những gì", "thì sao"])))
            or (session_last_intent == GoalIntent.CURRICULUM_OVERVIEW.value and has_entity_switch_cue and not entities)
        )
        is_regulation_query = bool(
            re.search(r"\b(tốt nghiệp|xét tốt nghiệp|điều kiện tốt nghiệp|cảnh báo học vụ|buộc thôi học|quy chế đào tạo|quy chế học vụ|điều kiện học lại|bảo lưu)\b", clean_lower)
            or re.search(r"\b(tot nghiep|xet tot nghiep|dieu kien tot nghiep|canh bao hoc vu|buoc thoi hoc|quy che dao tao|quy che hoc vu|dieu kien hoc lai|bao luu)\b", clean_unaccented)
        )

        curriculum_operation: Optional[str] = None
        curr_cohort = normalize_cohort(f"K{cohort_match.group(1)}") if cohort_match else normalize_cohort(profile_data.get("cohort", "K19"))
        cohort_source = "explicit_query" if cohort_match else "profile_context"

        curr_semester = int(sem_match.group(1)) if sem_match else None

        if is_curriculum_query:
            if has_course_placement_cue:
                explicit_codes = self.entity_catalog.extract_codes(clean_query)
                placement_course = explicit_codes[0] if explicit_codes else None
                if not placement_course:
                    cr = self.course_resolver.resolve(clean_query, session_context=session_context)
                    if cr.status == ResolutionStatus.RESOLVED and cr.course_code:
                        placement_course = cr.course_code
                    elif session_last_entity and self.entity_catalog.is_known_code(session_last_entity):
                        placement_course = session_last_entity
                if placement_course:
                    entities = [placement_course]
                    ref_t = ReferentType.EXPLICIT if placement_course in clean_query.upper() else ReferentType.PREVIOUS_ENTITY
                    referents = [ref_t]
                    resolution_sources[f"entity_{placement_course}"] = "course_placement"
                curriculum_operation = AcademicOperation.FIND_COURSE_SEMESTER.value
            else:
                # Chuyển chủ đề: xóa bỏ mã môn cũ để triệt tiêu STALE_COURSE_IN_CURRICULUM_QUERY
                entities = []
                referents = []
                if has_total_credits_cue or ("tín chỉ" in clean_lower and not has_semester_in_query):
                    curriculum_operation = AcademicOperation.GET_TOTAL_CREDITS.value
                elif has_semester_in_query:
                    curriculum_operation = AcademicOperation.GET_SEMESTER_COURSES.value
                else:
                    curriculum_operation = AcademicOperation.LIST_COURSES.value
        else:
            # 3.1 Nhận diện thực thể không xác định (Unknown entity)
            unknown_entities = self.entity_catalog.find_unknown_entities(clean_query)
            if unknown_entities:
                frame = GoalFrame(
                    intent=GoalIntent.UNKNOWN,
                    entities=unknown_entities,
                    referents=[ReferentType.EXPLICIT],
                    missing_slots=["unknown_entity"],
                    confidence=1.0,
                    resolution_sources={"entity": "catalog_unknown"},
                )
                self._log_trace(clean_query, frame, "catalog_unknown")
                return frame

            # 3.2 Nhận diện mâu thuẫn thực thể (Conflict: Mã A + Tên môn B)
            conflict = self.entity_catalog.check_entity_conflict(clean_query)
            if conflict:
                frame = GoalFrame(
                    intent=GoalIntent.UNKNOWN,
                    entities=[conflict["code"], conflict["conflicting_code"]],
                    referents=[ReferentType.EXPLICIT],
                    missing_slots=["entity_conflict"],
                    confidence=1.0,
                    resolution_sources={"entity": "entity_conflict"},
                )
                self._log_trace(clean_query, frame, "entity_conflict")
                return frame

            # 3.3 Trích xuất tất cả các mã môn rõ ràng trong câu hỏi (Explicit Codes)
            explicit_codes = self.entity_catalog.extract_codes(clean_query)
            for code in explicit_codes:
                if self.entity_catalog.is_known_code(code) and code not in entities:
                    entities.append(code)
                    referents.append(ReferentType.EXPLICIT)
                    resolution_sources[f"entity_{code}"] = "explicit_code"

            # 3.4 Nhận diện thực thể bằng CourseEntityResolver (hỗ trợ so sánh nhiều môn)
            comp_parts = self._split_comparison_entities(clean_query)
            if comp_parts:
                for part in comp_parts:
                    p_res = self.course_resolver.resolve(part, session_context=session_context)
                    if p_res.status == ResolutionStatus.RESOLVED and p_res.course_code:
                        if p_res.course_code not in entities:
                            entities.append(p_res.course_code)
                            referents.append(ReferentType.EXPLICIT)
                            resolution_sources[f"entity_{p_res.course_code}"] = f"resolver_{p_res.stage}"

            # Nếu chưa tìm thấy thực thể hoặc chỉ mới có 1 thực thể, thử resolve toàn bộ query
            if not entities:
                c_res = self.course_resolver.resolve(clean_query, session_context=session_context)
                if c_res.status == ResolutionStatus.RESOLVED and c_res.course_code:
                    entities.append(c_res.course_code)
                    if c_res.stage == "stage3_session_context":
                        if has_pronoun:
                            referents.append(ReferentType.PRONOUN)
                        else:
                            referents.append(ReferentType.PREVIOUS_ENTITY)
                        resolution_sources[f"entity_{c_res.course_code}"] = "session_context"
                    else:
                        referents.append(ReferentType.EXPLICIT)
                        resolution_sources[f"entity_{c_res.course_code}"] = f"resolver_{c_res.stage}"
                elif c_res.status == ResolutionStatus.UNKNOWN_CODE:
                    frame = GoalFrame(
                        intent=GoalIntent.UNKNOWN,
                        entities=[c_res.course_code] if c_res.course_code else [],
                        referents=[ReferentType.EXPLICIT],
                        missing_slots=["unknown_entity"],
                        confidence=1.0,
                        resolution_sources={"entity": "resolver_unknown_code"},
                    )
                    self._log_trace(clean_query, frame, "resolver_unknown_code")
                    return frame

            # 3.5 Phân giải đại từ và liên hệ thực thể trước (Referent Resolution)
            if (has_pronoun or has_previous_entity_cue) and not entities:
                if session_last_entity and self.entity_catalog.is_known_code(session_last_entity):
                    entities.append(session_last_entity)
                    if has_pronoun:
                        referents.append(ReferentType.PRONOUN)
                    else:
                        referents.append(ReferentType.PREVIOUS_ENTITY)
                    resolution_sources[f"entity_{session_last_entity}"] = "previous_entity_referent"
                else:
                    ref_type = ReferentType.PRONOUN if has_pronoun else ReferentType.PREVIOUS_ENTITY
                    frame = GoalFrame(
                        intent=GoalIntent.UNKNOWN,
                        entities=[],
                        referents=[ref_type],
                        missing_slots=["entity"],
                        confidence=1.0,
                        resolution_sources={"entity": "unresolved_referent"},
                    )
                    self._log_trace(clean_query, frame, "unresolved_referent")
                    return frame

            # 3.6 Kế thừa thực thể trước đó khi hỏi tiếp nối không nhắc lại chủ ngữ
            if not is_curriculum_query and not is_regulation_query and not entities and session_last_entity and self.entity_catalog.is_known_code(session_last_entity):
                entities.append(session_last_entity)
                referents.append(ReferentType.PREVIOUS_ENTITY)
                resolution_sources[f"entity_{session_last_entity}"] = "inherited_previous_entity"

        # =====================================================================
        # BƯỚC 4: EXTRACT DETERMINISTIC SAFETY / TOOL SIGNALS
        # =====================================================================
        if utterance_semantics is None:
            try:
                sem = analyze_utterance(clean_query)
                utterance_semantics = {
                    "polarity": sem.polarity.value,
                    "modality": sem.modality.value,
                    "is_contradictory": sem.is_contradictory,
                    "prohibition_detected": sem.prohibition_detected,
                }
            except Exception:
                utterance_semantics = None

        is_negated = bool(
            re.search(r"\b(đừng|không\s+được|chớ|không\s+cần|hủy|thôi|không\s+muốn)\b", clean_lower)
        )
        is_hypothetical = bool(
            re.search(r"\b(nếu|giả\s+sử|liệu|trong\s+trường\s+hợp|thử\s+xem)\b", clean_lower)
        )
        if utterance_semantics:
            if (
                utterance_semantics.get("polarity") == "NEGATED"
                or utterance_semantics.get("modality") in ("HYPOTHETICAL", "CONDITIONAL", "EXPLANATORY")
                or utterance_semantics.get("prohibition_detected")
                or utterance_semantics.get("is_contradictory")
            ):
                is_negated = True

        tool_action = None
        if not is_negated and not is_hypothetical:
            email_match = re.search(r"\b(soạn|gửi|viết|draft|compose|send)\b.{0,30}\b(email|mail|thư)\b", clean_lower)
            reminder_match = re.search(r"\b(đặt\s+lịch|nhắc|hẹn\s+giờ|tạo\s+lịch|remind)\b", clean_lower)
            if email_match and not any(nk in clean_lower for nk in ["email là gì", "khái niệm email", "email của thầy"]):
                tool_action = "SEND_EMAIL"
            elif reminder_match and not any(nk in clean_lower for nk in ["nhắc lại định nghĩa", "nhắc lại khái niệm", "nhắc nhở là gì"]):
                tool_action = "SET_REMINDER"

        # =====================================================================
        # BƯỚC 5: SEMANTIC INTENT INTERPRETATION (BGE-M3)
        # =====================================================================
        top1_intent, top1_score, top2_intent, top2_score, margin, all_scores = (
            self.intent_matcher.match_intent(clean_query)
        )

        # =====================================================================
        # BƯỚC 6: STRUCTURED SLOT EXTRACTION
        # =====================================================================
        requested_fields: List[str] = self._extract_fields(clean_lower)
        constraints: List[str] = []
        aggregation = AggregationType.NONE
        comparison = ComparisonType.NONE

        is_comparison_query = bool(
            len(entities) >= 2
            or re.search(r"\b(so\s+sánh|so\s+.*với|môn\s+nào\s+.*hơn|khác\s+nhau|đối\s+chiếu)\b", clean_lower)
        )

        # 6.1 Trích xuất ràng buộc tải thực hành (PRACTICAL_WORKLOAD / PRACTICAL_COMPONENT)
        # "nó có nặng thực hành không?", "nhiều thực hành không?", "lab nhiều không?"
        # QUY TẮC BẤT DI BẤT DỊCH: TUYỆT ĐỐI KHÔNG coi "nặng" là credits!
        clean_unaccented = strip_accents(clean_lower)
        has_practical_query = bool(
            re.search(r"\b(nặng\s+thực\s+hành|nhiều\s+thực\s+hành|thực\s+hành\s+nhiều|làm\s+lab\s+nhiều|nặng\s+lab|lab\s+nhiều|nhiều\s+giờ\s+thực\s+hành)\b", clean_lower)
            or (re.search(r"\bthực\s+hành\b", clean_lower) and any(w in clean_lower for w in ["nặng", "nhiều", "nặng không", "nhiều không"]))
            or re.search(r"\b(nang\s+thuc\s+hanh|nhieu\s+thuc\s+hanh|thuc\s+hanh\s+nhieu|lam\s+lab\s+nhieu|nang\s+lab|lab\s+nhieu|nhieu\s+gio\s+thuc\s+hanh)\b", clean_unaccented)
            or (re.search(r"\bthuc\s+hanh\b", clean_unaccented) and any(w in clean_unaccented for w in ["nang", "nhieu", "nang khong", "nhieu khong"]))
        )
        if has_practical_query:
            if "hours" not in requested_fields:
                requested_fields.append("hours")
            if is_comparison_query:
                constraints.append("PRACTICAL_COMPONENT")
            else:
                constraints.append("PRACTICAL_WORKLOAD")

        # 6.2 Trích xuất ràng buộc khái niệm (CONTAINS_CONCEPT("AWS"))
        # "CLO nào của cloud liên quan AWS?", "có bao nhiêu CLO liên quan AWS?", "trong CLO cái nào có AWS"
        concept_match = re.search(
            r"(?:liên\s+quan(?:\s+đến|\s+tới)?|nói\s+về|chứa)\s+([A-Za-z0-9_\-\+\.]{2,})",
            clean_query,
            re.IGNORECASE,
        )
        if not concept_match:
            # Chỉ bắt "có" hoặc "về" khi đi liền với từ viết hoa viết tắt kỹ thuật (như AWS, GCP, Azure, Docker, K8s, AI, IoT)
            concept_match = re.search(
                r"\b(?:có|về)\s+([A-Z0-9_\-\+]{2,})\b",
                clean_query,
            )
        if concept_match:
            candidate_concept = concept_match.group(1).strip()
            stop_concepts = {
                "đến", "tới", "môn", "học phần", "gì", "nào", "đó", "này",
                "thực hành", "lý thuyết", "bao nhiêu", "mấy", "thì", "sao",
                "không", "full", "fit", "clo", "cho", "mình"
            }
            if len(candidate_concept) >= 2 and candidate_concept.lower() not in stop_concepts and not candidate_concept.lower().startswith("fit"):
                constraints.append(f'CONTAINS_CONCEPT("{candidate_concept}")')
                if ("clo" in clean_lower or "chuẩn đầu ra" in clean_lower) and "clo" not in requested_fields:
                    requested_fields.append("clo")

        # 6.3 Trích xuất Aggregation (COUNT / LIST / COMPARE)
        count_cues = [
            r"\bbao\s+nhiêu\s+(clo|chuẩn\s+đầu\s+ra|tín|tiết|buổi)\b",
            r"\bcó\s+bao\s+nhiêu\b",
            r"\bcó\s+mấy\s+(cái|clo|mục)\b",
            r"\bđếm\s+(giúp|cho)\b",
            r"\bmấy\s+cái\b",
            r"\bco\s+may\s+cai\b",
            r"\bbao\s+nhieu\b",
        ]
        if any(re.search(pat, clean_lower) for pat in count_cues) or any(re.search(pat, clean_unaccented) for pat in count_cues):
            aggregation = AggregationType.COUNT
        elif any(re.search(pat, clean_lower) for pat in [r"\b(cái\s+nào|clo\s+nào|những\s+clo\s+nào|danh\s+sách|kể\s+ra|liệt\s+kê)\b"]) or any(re.search(pat, clean_unaccented) for pat in [r"\b(cai\s+nao|clo\s+nao|nhung\s+clo\s+nao|danh\s+sach|ke\s+ra|liet\s+ke)\b"]):
            aggregation = AggregationType.LIST

        # 6.4 Trích xuất Comparison (GREATER_THAN / LESS_THAN / COMPARE)
        if is_comparison_query:
            if re.search(r"\b(nhiều\s+hơn|nặng\s+hơn|lớn\s+hơn|cao\s+hơn|nhieu\s+hon|nang\s+hon|lon\s+hon|cao\s+hon)\b", clean_lower):
                comparison = ComparisonType.GREATER_THAN
            elif re.search(r"\b(ít\s+hơn|nhẹ\s+hơn|thấp\s+hơn|bé\s+hơn|it\s+hon|nhe\s+hon|thap\s+hon|be\s+hon)\b", clean_lower):
                comparison = ComparisonType.LESS_THAN
            else:
                comparison = ComparisonType.COMPARE
            aggregation = AggregationType.COMPARE

        # 6.5 Kế thừa trường tiếp nối từ lượt trước (Follow-up Field Inheritance)
        # Turn 1: "CLO FIT4113" -> Turn 2: "còn hệ thống nhúng?" -> inherit 'clo'
        # Turn 1: "giảng viên FIT4201" -> Turn 2: "còn cloud?" -> inherit 'lecturer'
        # Turn 1: "CLO cloud" -> Turn 2: "cái nào liên quan AWS?" -> inherit 'clo'
        if not requested_fields and session_last_fields:
            if has_entity_switch_cue or constraints or aggregation in (AggregationType.COUNT, AggregationType.LIST):
                requested_fields = list(session_last_fields)
                referents.append(ReferentType.PREVIOUS_INTENT)

        # 6.6 Kế thừa bộ lọc/ràng buộc tiếp nối
        # Turn 1: "CLO cloud" -> Turn 2: "cái nào liên quan AWS?" (constraint=AWS) -> Turn 3: "có mấy cái?" (COUNT on filtered set)
        if not constraints and session_last_constraints:
            if aggregation in (AggregationType.COUNT, AggregationType.LIST) or any(w in clean_lower for w in ["mấy cái", "cái nào"]) or any(w in clean_unaccented for w in ["may cai", "cai nao"]):
                constraints = list(session_last_constraints)

        # =====================================================================
        # BƯỚC 7: CONFIDENCE & AMBIGUITY POLICY
        # =====================================================================
        final_intent = GoalIntent.UNKNOWN
        final_scope = GoalScope.SINGLE_FIELD
        missing_slots: List[str] = []
        unsupported_reason = None
        suggested_alternative = None

        # 7.1 Xử lý các trường không khả dụng trong Knowledge Environment (Missing Data)
        from src.agent_core.environment_catalog import get_knowledge_environment_catalog
        env_cat = get_knowledge_environment_catalog()
        unavailable_fields = [f for f in requested_fields if env_cat.is_field_unavailable(f)]
        is_subjective_difficulty = bool(
            re.search(r"\b(dễ\s+hơn|khó\s+hơn|nhẹ\s+hơn|nhàn\s+hơn|môn\s+nào\s+dễ|môn\s+nào\s+khó|môn\s+nào\s+nhẹ|môn\s+nào\s+nhàn|có\s+khó|có\s+dễ|có\s+nhẹ|có\s+nhàn)\b", clean_lower)
            or re.search(r"\b(de\s+hon|kho\s+hon|nhe\s+hon|nhan\s+hon|mon\s+nao\s+de|mon\s+nao\s+kho|mon\s+nao\s+nhe|mon\s+nao\s+nhan|co\s+kho|co\s+de|co\s+nhe|co\s+nhan)\b", clean_unaccented)
        ) or ("difficulty" in unavailable_fields)

        if unavailable_fields or is_subjective_difficulty:
            missing_slots.append("data")
            if is_subjective_difficulty:
                unsupported_reason = "missing_direct_difficulty_evidence"
                suggested_alternative = (
                    "Mình không có chỉ số độ khó trực tiếp từ đề cương chính thức. "
                    "Nếu bạn muốn, mình có thể so sánh dựa trên khối lượng thực hành (số giờ lab), "
                    "hình thức đánh giá (tỷ lệ thi) và số tín chỉ nhé."
                )
            else:
                first_unavail = unavailable_fields[0]
                unsupported_reason = f"unavailable_field_{first_unavail}"
                prop_info = env_cat.propose_alternative_for_field(first_unavail)
                suggested_alternative = prop_info.get("proposal_text")

            final_intent = GoalIntent.COURSE_COMPARISON if len(entities) >= 2 else GoalIntent.COURSE_FIELD_LOOKUP
            frame = GoalFrame(
                intent=final_intent,
                entities=entities,
                referents=referents,
                requested_fields=requested_fields,
                scope=final_scope,
                constraints=constraints,
                aggregation=aggregation,
                comparison=comparison,
                confidence=1.0,
                confidence_margin=1.0,
                missing_slots=missing_slots,
                resolution_sources=resolution_sources,
                unsupported_reason=unsupported_reason,
                suggested_alternative=suggested_alternative,
            )
            self._log_trace(clean_query, frame, "unavailable_field_abstain")
            return frame

        # 7.0 Các chỉ dấu ngữ cảnh ngữ nghĩa tự nhiên
        has_brief_cue = bool(
            re.search(r"\b(sơ\s+qua|sơ\s+lược|kể\s+sơ|nói\s+sơ|sơ|ngắn\s+gọn|tóm\s+tắt|khái\s+quát|đại\s+khái)\b", clean_lower)
            or re.search(r"\b(so\s+qua|so\s+luoc|ke\s+so|noi\s+so|so|ngan\s+gon|tom\s+tat|khai\s+quat|dai\s+khai)\b", clean_unaccented)
        )
        full_detail_cues = [
            "tất cả", "toàn bộ", "tất cả thông tin", "chi tiết tổng thể",
            "tổng thể", "chi tiết tất cả", "tất cả về", "mọi thông tin",
            "full thông tin", "đầy đủ thông tin", "biết hết", "nói kỹ hết",
            "xem hết", "tất cả luôn", "toàn bộ chi tiết", "đầy đủ môn này"
        ]
        has_full_details_cue = any(w in clean_lower for w in full_detail_cues)
        is_complex_compositional = any(
            phrase in clean_lower
            for phrase in [
                "thích thực hành nhưng", "muốn nhẹ", "nếu phải chọn",
                "theo các tiêu chí có trong", "tổng hợp giúp mình nếu"
            ]
        )
        is_ambiguous_score = (margin < 0.05 and top1_score < 0.65 and not requested_fields and not has_full_details_cue)

        # 7.1b Curriculum Intent (Round A1: Typed Academic Knowledge Access)
        if is_curriculum_query:
            final_intent = GoalIntent.CURRICULUM_OVERVIEW
            if curriculum_operation == AcademicOperation.GET_TOTAL_CREDITS.value:
                final_scope = GoalScope.SINGLE_FIELD
                requested_fields = ["total_credits"]
            elif curriculum_operation == AcademicOperation.FIND_COURSE_SEMESTER.value:
                final_scope = GoalScope.SINGLE_FIELD
                requested_fields = ["semester"]
            elif curriculum_operation == AcademicOperation.GET_SEMESTER_COURSES.value:
                final_scope = GoalScope.FILTERED_SET
                requested_fields = ["courses"]
            else:
                final_scope = GoalScope.ALL_AVAILABLE
                requested_fields = ["courses"]
            resolution_sources["intent"] = "typed_curriculum_analyzer"
        # 7.2 Tool Action (Quyền ưu tiên an toàn cao nhất)
        elif tool_action:
            final_intent = GoalIntent.TOOL_ACTION
            final_scope = GoalScope.SINGLE_FIELD
            resolution_sources["intent"] = "safety_tool_extractor"
        # 7.3 So sánh nhiều môn
        elif is_comparison_query and len(entities) >= 2:
            final_intent = GoalIntent.COURSE_COMPARISON
            final_scope = GoalScope.FILTERED_SET if constraints else GoalScope.SUMMARY
            resolution_sources["intent"] = "comparison_rule_and_semantics"
            if not requested_fields:
                requested_fields = ["hours", "credits", "assessment"] if has_practical_query else ["credits", "assessment"]
        # 7.4 Khử mơ hồ Khái niệm vs Tên môn học (Concept vs Course Title)
        # Ví dụ: "hệ thống nhúng là gì?", "cloud là gì?"
        elif self._is_concept_ambiguous(clean_lower, entities, clean_query):
            final_intent = GoalIntent.UNKNOWN
            missing_slots.append("concept_course_ambiguity")
            resolution_sources["intent"] = "concept_course_ambiguity_policy"
        # 7.5 Full Details
        elif not has_brief_cue and (
            top1_intent == GoalIntent.COURSE_FULL_DETAILS
            or has_full_details_cue
            or (session_last_intent == GoalIntent.COURSE_FULL_DETAILS.value and has_entity_switch_cue and not requested_fields)
        ):
            final_intent = GoalIntent.COURSE_FULL_DETAILS
            final_scope = GoalScope.ALL_AVAILABLE
            requested_fields = list(FULL_DETAILS_FIELDS)
            resolution_sources["intent"] = "semantic_full_details"
        # 7.6 Course Overview (chỉ áp dụng khi không yêu cầu trường cụ thể hay ràng buộc cụ thể)
        elif not requested_fields and not constraints and (
            has_brief_cue
            or top1_intent == GoalIntent.COURSE_OVERVIEW
            or any(w in clean_lower for w in ["học những gì", "có gì hay", "kể mình nghe", "cho mình biết về", "giới thiệu", "tổng quan", "chi tiết học phần", "chi tiết môn", "thông tin học phần", "thế nào", "học gì", "có gì"])
            or (entities and not has_entity_switch_cue)
            or (session_last_intent == GoalIntent.COURSE_OVERVIEW.value and has_entity_switch_cue)
        ):
            final_intent = GoalIntent.COURSE_OVERVIEW
            final_scope = GoalScope.SUMMARY
            requested_fields = list(OVERVIEW_FIELDS)
            resolution_sources["intent"] = "semantic_course_overview"
        # 7.7 Regulation Lookup
        elif top1_intent == GoalIntent.REGULATION_LOOKUP or any(
            f in ("graduation_requirements", "academic_warning", "training_rules", "regulation") for f in requested_fields
        ):
            final_intent = GoalIntent.REGULATION_LOOKUP
            final_scope = GoalScope.SINGLE_FIELD
            resolution_sources["intent"] = "semantic_regulation"
        # 7.8 Field Lookup
        elif requested_fields or constraints:
            final_intent = GoalIntent.COURSE_FIELD_LOOKUP
            final_scope = GoalScope.FILTERED_SET if constraints else GoalScope.SINGLE_FIELD
            resolution_sources["intent"] = "semantic_field_lookup"
        # 7.8b Complex Compositional LLM Fallback (Sections 14, 15, 16)
        elif is_complex_compositional or is_ambiguous_score:
            llm_frame = self._llm_fallback_interpret(clean_query, session_context)
            if llm_frame:
                self._log_trace(clean_query, llm_frame, "structured_llm_fallback")
                return llm_frame
            final_intent = top1_intent
            final_scope = GoalScope.SINGLE_FIELD
            resolution_sources["intent"] = "bge_m3_top1"
        # 7.9 Fallback theo BGE-M3 Top1 Intent
        else:
            final_intent = top1_intent
            final_scope = GoalScope.SINGLE_FIELD
            resolution_sources["intent"] = "bge_m3_top1"

        # Điều chỉnh scope nếu có constraints trên tập hợp (ví dụ CLO lọc theo AWS)
        if constraints and "clo" in requested_fields:
            final_scope = GoalScope.FILTERED_SET

        # Xây dựng Typed Subjects và AcademicOperation (Round A1)
        subjects: List[AcademicEntity] = []
        subject_type: Optional[EntityType] = None
        operation: Optional[str] = None

        if is_curriculum_query or final_intent == GoalIntent.CURRICULUM_OVERVIEW:
            subject_type = EntityType.CURRICULUM
            operation = curriculum_operation or AcademicOperation.LIST_COURSES.value
            subjects.append(AcademicEntity(
                type=EntityType.COHORT,
                value=curr_cohort,
                canonical_id=curr_cohort,
                confidence=1.0,
                resolution_source=cohort_source,
            ))
            subjects.append(AcademicEntity(
                type=EntityType.MAJOR,
                value=curr_major,
                canonical_id=curr_major,
                confidence=1.0,
                resolution_source=major_source,
            ))
            if curr_semester is not None:
                subjects.append(AcademicEntity(
                    type=EntityType.SEMESTER,
                    value=str(curr_semester),
                    canonical_id=str(curr_semester),
                    confidence=1.0,
                    resolution_source="explicit_query",
                ))
            if operation == AcademicOperation.FIND_COURSE_SEMESTER.value and entities:
                subjects.append(AcademicEntity(
                    type=EntityType.COURSE,
                    value=entities[0],
                    canonical_id=entities[0],
                    confidence=1.0,
                    resolution_source=resolution_sources.get(f"entity_{entities[0]}", "explicit_code"),
                ))
            subjects.append(AcademicEntity(
                type=EntityType.CURRICULUM,
                value=f"{curr_cohort}_{curr_major}",
                canonical_id=f"{curr_cohort}_{curr_major}",
                confidence=1.0,
                resolution_source="synthesized",
            ))

        elif is_regulation_query or final_intent == GoalIntent.REGULATION_LOOKUP:
            subject_type = EntityType.REGULATION
            operation = AcademicOperation.REGULATION_LOOKUP.value
            subjects.append(AcademicEntity(
                type=EntityType.REGULATION,
                value="quy chế đào tạo",
                canonical_id="quy_che",
                confidence=1.0,
                resolution_source="explicit_query",
            ))

        elif entities:
            subject_type = EntityType.COURSE
            operation = AcademicOperation.COMPARE_COURSES.value if is_comparison_query else AcademicOperation.LOOKUP_FIELD.value
            for code in entities:
                if re.match(r"^K\d{2}$", code, re.IGNORECASE):
                    continue
                subjects.append(AcademicEntity(
                    type=EntityType.COURSE,
                    value=code,
                    canonical_id=code,
                    confidence=1.0,
                    resolution_source=resolution_sources.get(f"entity_{code}", "resolver"),
                ))

        else:
            subject_type = EntityType.GENERAL_TOPIC
            operation = AcademicOperation.LOOKUP_FIELD.value

        # =====================================================================
        # BƯỚC 8: CONSTRUCT & VALIDATE GOALFRAME
        # =====================================================================
        frame = GoalFrame(
            intent=final_intent,
            entities=entities,
            subjects=subjects,
            subject_type=subject_type,
            operation=operation,
            referents=referents,
            requested_fields=requested_fields,
            scope=final_scope,
            constraints=constraints,
            aggregation=aggregation,
            comparison=comparison,
            tool_action=tool_action,
            confidence=top1_score,
            confidence_margin=margin,
            missing_slots=missing_slots,
            resolution_sources=resolution_sources,
            unsupported_reason=unsupported_reason,
            suggested_alternative=suggested_alternative,
        )

        validation_errors = validate_goal_frame(frame)
        if validation_errors:
            logger.warning(f"SemanticGoalInterpreter: GoalFrame validation warnings: {validation_errors}")

        self._log_trace(clean_query, frame, resolution_sources.get("intent", "unknown"))
        return frame

    def _split_comparison_entities(self, query: str) -> List[str]:
        """Tách các vế thực thể trong câu hỏi so sánh (ví dụ: 'so cloud với nhúng', 'cloud với nhúng')."""
        match = re.search(r"so\s+(.+?)\s+với\s+(.+?)(?:\s+xem|\s+môn|\s*$|\?|,)", query, re.IGNORECASE)
        if match:
            return [match.group(1).strip(), match.group(2).strip()]
        match_between = re.search(r"giữa\s+(.+?)\s+và\s+(.+?)(?:\s+xem|\s+môn|\s*$|\?|,)", query, re.IGNORECASE)
        if match_between:
            return [match_between.group(1).strip(), match_between.group(2).strip()]
        match_simple = re.search(r"([a-zA-Z0-9_\u00C0-\u024F\s]+?)\s+với\s+([a-zA-Z0-9_\u00C0-\u024F\s]+?)(?:\s+xem|\s+môn|\s+cái|\s+thì|\s+học\s+phần|\s*$|\?|,)", query, re.IGNORECASE)
        if match_simple:
            return [match_simple.group(1).strip(), match_simple.group(2).strip()]
        return []

    def _is_concept_ambiguous(self, lower_query: str, entities: List[str], raw_query: str) -> bool:
        """
        Kiểm tra câu hỏi có mơ hồ giữa tên môn học và khái niệm công nghệ nói chung.
        Ví dụ: 'hệ thống nhúng là gì', 'cloud là gì'.
        """
        if not entities or len(entities) > 1:
            return False

        conceptual_triggers = [r"\blà gì\b", r"\blĩnh vực gì\b", r"\bnhư thế nào\b", r"\bnguyên lý\b", r"\bkhái niệm\b"]
        has_concept_cue = any(re.search(pat, lower_query) for pat in conceptual_triggers)
        if not has_concept_cue:
            return False

        academic_cues = ["môn", "học phần", "mã", "tín chỉ", "tiên quyết", "giảng viên", "thi", "đề cương", "clo", "kỳ", "chi tiết"]
        has_academic_cue = any(re.search(rf"\b{re.escape(cue)}\b", lower_query) for cue in academic_cues)
        has_explicit_code = bool(re.search(r"\b[A-Za-z]{2,4}\d{4}\b", raw_query))

        return not has_academic_cue and not has_explicit_code

    def _extract_fields(self, lower_query: str) -> List[str]:
        """Trích xuất danh sách trường thông tin học vụ từ câu hỏi."""
        fields: List[str] = []
        lower_unaccented = strip_accents(lower_query)

        field_keywords = {
            "credits": [
                "tín chỉ", "số tín", "mấy tín", "bao nhiêu tín",
                "tin chi", "so tin", "may tin", "bao nhieu tin",
            ],
            "lecturer": [
                "giảng viên", "ai dạy", "thầy nào", "cô nào", "ai đứng lớp", "cán bộ phụ trách",
                "giang vien", "ai day", "thay nao", "co nao", "ai dung lop", "can bo phu trach",
            ],
            "lecturer_email": ["email", "mail", "hòm thư", "hom thu"],
            "prerequisites": [
                "tiên quyết", "học trước", "điều kiện tiên quyết",
                "tien quyet", "hoc truoc", "dieu kien tien quyet",
            ],
            "assessment": [
                "đánh giá", "tính điểm", "trọng số", "hình thức thi", "thi cử", "chuyên cần", "giữa kỳ", "cuối kỳ",
                "thi trắc nghiệm", "tự luận", "thi kiểu nào", "thi thế nào", "thi ra sao",
                "danh gia", "tinh diem", "trong so", "hinh thuc thi", "thi cu", "chuyen can", "giua ky", "cuoi ky",
                "thi trac nghiem", "tu luan", "thi kieu nao", "thi the nao", "thi ra sao",
            ],
            "clo": [
                "clo", "chuẩn đầu ra", "mục tiêu học phần", "đầu ra",
                "chuan dau ra", "muc tieu hoc phan", "dau ra",
            ],
            "hours": [
                "thời lượng", "số giờ", "số tiết", "lý thuyết", "thực hành", "thực tập", "lab",
                "thoi luong", "so gio", "so tiet", "ly thuyet", "thuc hanh", "thuc tap",
            ],
            "course_plan": [
                "kế hoạch giảng dạy", "lịch trình", "nội dung từng tuần", "tiến độ",
                "ke hoach giang day", "lich trinh", "noi dung tung tuan", "tien do",
            ],
            "department": [
                "bộ môn phụ trách", "thuộc bộ môn", "khoa phụ trách",
                "bo mon phu trach", "thuoc bo mon", "khoa phu trach",
            ],
            "english_name": ["tên tiếng anh", "tên quốc tế", "ten tieng anh", "ten quoc te"],
            "graduation_requirements": ["tốt nghiệp", "xét tốt nghiệp", "điều kiện tốt nghiệp", "tot nghiep", "xet tot nghiep", "dieu kien tot nghiep"],
            "academic_warning": ["cảnh báo học vụ", "buộc thôi học", "hạ điểm rèn luyện", "canh bao hoc vu", "buoc thoi hoc", "ha diem ren luyen"],
            "training_rules": ["quy chế đào tạo", "quy chế học vụ", "điều kiện học lại", "quy che dao tao", "quy che hoc vu", "dieu kien hoc lai"],
            "total_credits": ["tổng số tín chỉ", "tổng tín chỉ", "tổng số tín", "tong so tin chi", "tong tin chi", "tong so tin"],
            "semester": ["học kỳ", "kỳ mấy", "ở kỳ nào", "kỳ học", "thuộc kỳ", "kỳ nào", "hoc ky", "ky may", "o ky nao", "ky hoc", "thuoc ky", "ky nao"],
        }

        # Dữ liệu KHÔNG TỒN TẠI trong môi trường học vụ (đánh dấu tường minh)
        has_so_qua = bool(
            re.search(r"\b(sơ\s+qua|sơ\s+lược|kể\s+sơ|nói\s+sơ|sơ|so\s+qua|so\s+luoc|ke\s+so|noi\s+so)\b", lower_query)
            or re.search(r"\b(so\s+qua|so\s+luoc|ke\s+so|noi\s+so)\b", lower_unaccented)
        )
        fail_patterns = [
            r"\b(tỷ\s+lệ\s+trượt|rớt\s+môn|trượt\s+môn|bao\s+nhiêu\s+đứa\s+trượt|tỷ\s+lệ\s+đỗ|tỷ\s+lệ\s+rớt|tỷ\s+lệ\s+qua\s+môn|khả\s+năng\s+qua\s+môn|dễ\s+qua\s+môn|khó\s+qua\s+môn)\b",
            r"\b(ty\s+le\s+truot|rot\s+mon|truot\s+mon|ty\s+le\s+do|ty\s+le\s+rot|ty\s+le\s+qua\s+mon|kha\s+nang\s+qua\s+mon|de\s+qua\s+mon|kho\s+qua\s+mon)\b",
        ]
        if not has_so_qua and (
            any(re.search(pat, lower_query) for pat in fail_patterns)
            or any(re.search(pat, lower_unaccented) for pat in fail_patterns)
        ):
            fields.append("failure_rate")

        diff_patterns = [
            r"\b(khó\s+hơn|độ\s+khó|khó\s+nhất|dễ\s+hơn|khó\s+hay\s+dễ|môn\s+nào\s+khó|có\s+khó\s+không|dễ\s+qua\s+môn|dễ\s+qua|dễ\s+đạt|điểm\s+a|nhàn\s+hơn|học\s+nhàn|nhàn\s+nhất|học\s+nhàn\s+hơn|khó\s+quá\s+không|khó\s+không)\b",
            r"\b(kho\s+hon|do\s+kho|kho\s+nhat|de\s+hon|kho\s+hay\s+de|mon\s+nao\s+kho|co\s+kho\s+khong|de\s+qua\s+mon|de\s+qua|de\s+dat|diem\s+a|nhan\s+hon|hoc\s+nhan|nhan\s+nhat|hoc\s+nhan\s+hon|kho\s+qua\s+khong|kho\s+khong)\b",
        ]
        if any(re.search(pat, lower_query) for pat in diff_patterns) or any(re.search(pat, lower_unaccented) for pat in diff_patterns):
            fields.append("difficulty")

        rating_patterns = [
            r"\b(review|đánh\s+giá\s+của\s+sinh\s+viên|sinh\s+viên\s+nói\s+gì|chấm\s+điểm\s+thầy|sinh\s+viên\s+review|chấm\s+gắt|chấm\s+điểm\s+có\s+gắt\s+không|chấm\s+có\s+gắt\s+không|chấm\s+gắt\s+không)\b",
            r"\b(danh\s+gia\s+cua\s+sinh\s+vien|sinh\s+vien\s+noi\s+gi|cham\s+diem\s+thay|sinh\s+vien\s+review|cham\s+gat|cham\s+diem\s+co\s+gat\s+khong|cham\s+co\s+gat\s+khong|cham\s+gat\s+khong)\b",
        ]
        if any(re.search(pat, lower_query) for pat in rating_patterns) or any(re.search(pat, lower_unaccented) for pat in rating_patterns):
            fields.append("student_rating")

        salary_patterns = [
            r"\b(lương|mức\s+lương|thu\s+nhập|mấy\s+chục\s+triệu)\b",
            r"\b(luong|muc\s+luong|thu\s+nhap|may\s+chuc\s+trieu)\b",
        ]
        if any(re.search(pat, lower_query) for pat in salary_patterns) or any(re.search(pat, lower_unaccented) for pat in salary_patterns):
            fields.append("job_salary")

        leak_patterns = [
            r"\b(lộ\s+đề|đề\s+bị\s+lộ|đề\s+thi\s+có\s+bị\s+lộ|đề\s+thi\s+năm\s+ngoái|bị\s+lộ|leak\s+đề|đề\s+leak)\b",
            r"\b(lo\s+de|de\s+bi\s+lo|de\s+thi\s+co\s+bi\s+lo|de\s+thi\s+nam\s+ngoai|bi\s+lo|leak\s+de|de\s+leak)\b",
            r"\b(lộ|leak)\b",
        ]
        if any(re.search(pat, lower_query) for pat in leak_patterns) or any(re.search(pat, lower_unaccented) for pat in leak_patterns[:2]):
            fields.append("exam_leak")

        # Kiểm tra regex bổ sung cho prerequisites và assessment
        if re.search(r"\b(học|cần\s+học)\b.*\b(trước)\b", lower_query) or re.search(r"\b(hoc|can\s+hoc)\b.*\b(truoc)\b", lower_unaccented):
            fields.append("prerequisites")

        if (
            re.search(r"\bthi\s+(?:trắc\s+nghiệm|tự\s+luận|vấn\s+đáp|thế\s+nào|kiểu\s+nào|ra\s+sao)\b", lower_query)
            or re.search(r"\bthi\s+(?:trac\s+nghiem|tu\s+luan|van\s+dap|the\s+nao|kieu\s+nao|ra\s+sao)\b", lower_unaccented)
            or re.search(r"\b(trắc\s+nghiệm|tự\s+luận)\b", lower_query)
            or re.search(r"\b(trac\s+nghiem|tu\s+luan)\b", lower_unaccented)
        ):
            fields.append("assessment")

        for field, kws in field_keywords.items():
            for kw in kws:
                pat = rf"\b{re.escape(kw)}\b"
                if re.search(pat, lower_query) or re.search(pat, lower_unaccented):
                    fields.append(field)
                    break

        return list(dict.fromkeys(fields))

    def _log_trace(self, raw_query: str, frame: GoalFrame, source: str) -> None:
        """Ghi nhận structured trace cho môi trường phát triển (Development Only)."""
        logger.info(
            f"[UNDERSTAND] normalized_query='{raw_query}' | "
            f"intent={frame.intent.value} | "
            f"entities={frame.entities} | "
            f"fields={frame.requested_fields} | "
            f"scope={frame.scope.value} | "
            f"constraints={frame.constraints} | "
            f"aggregation={frame.aggregation.value} | "
            f"comparison={frame.comparison.value} | "
            f"confidence={frame.confidence:.4f} | "
            f"margin={frame.confidence_margin:.4f} | "
            f"missing_slots={frame.missing_slots} | "
            f"resolution_source={source}"
        )

    def _llm_fallback_interpret(
        self,
        query: str,
        session_context: Optional[Dict[str, Any]] = None,
    ) -> Optional[GoalFrame]:
        """
        Fallback có cấu trúc qua LLM cho các câu hỏi đa tiêu chí / phức tạp (Sections 14, 15, 16).
        LLM chỉ phân tích truy vấn và trả về JSON thuần túy theo schema GoalFrame.
        Tuyệt đối không sinh câu trả lời học vụ hoặc tự sáng tác kiến thức.
        """
        try:
            from src.llm.client import invoke_llm, is_live_llm_ready
            if not is_live_llm_ready():
                return None

            prompt = (
                "Bạn là bộ phân tích mục tiêu (Goal Parser) cho Hệ thống Cố vấn Học tập.\n"
                "Nhiệm vụ DUY NHẤT của bạn là phân tích câu hỏi của sinh viên và trả về JSON đúng định dạng.\n"
                "TUYỆT ĐỐI KHÔNG trả lời câu hỏi, không tư vấn, không sáng tác thông tin học phần.\n"
                "Chỉ xuất JSON thuần túy (không kèm markdown ```json):\n"
                "{\n"
                '  "intent": "COURSE_OVERVIEW" | "COURSE_FULL_DETAILS" | "COURSE_FIELD_LOOKUP" | "COURSE_COMPARISON" | "REGULATION_LOOKUP" | "GENERAL_TOPIC_EXPLANATION" | "TOOL_ACTION" | "UNKNOWN",\n'
                '  "entities": ["MÃ_MÔN", ...],\n'
                '  "requested_fields": ["hours", "assessment", "credits", "clo", "lecturer", ...],\n'
                '  "constraints": ["..."],\n'
                '  "aggregation": "NONE" | "COUNT" | "LIST" | "COMPARE",\n'
                '  "missing_slots": []\n'
                "}\n"
                f"Câu hỏi: {query}\n"
            )

            raw_res = invoke_llm(prompt, temperature=0.0).strip()
            raw_res = re.sub(r"^```(?:json)?\s*", "", raw_res)
            raw_res = re.sub(r"```$", "", raw_res).strip()
            data = json.loads(raw_res)

            # Schema Validation (Section 16)
            intent_str = data.get("intent", "UNKNOWN")
            if intent_str not in GoalIntent._value2member_map_:
                self.schema_failure_count += 1
                return None
            intent = GoalIntent(intent_str)

            aggr_str = data.get("aggregation", "NONE")
            if aggr_str not in AggregationType._value2member_map_:
                self.schema_failure_count += 1
                return None
            aggr = AggregationType(aggr_str)

            # Kiểm tra và chuẩn hóa thực thể
            ents: List[str] = []
            for e in data.get("entities", []):
                extracted = self.entity_catalog.extract_codes(e)
                if extracted:
                    ents.extend(extracted)
                else:
                    c_info = self.entity_catalog.get_course_info(e)
                    if c_info:
                        ents.append(c_info.get("code", e))

            fields = [f for f in data.get("requested_fields", []) if isinstance(f, str)]
            constraints = [c for c in data.get("constraints", []) if isinstance(c, str)]
            missing = [m for m in data.get("missing_slots", []) if isinstance(m, str)]

            self.llm_fallback_count += 1
            frame = GoalFrame(
                intent=intent,
                entities=list(dict.fromkeys(ents)),
                referents=[ReferentType.EXPLICIT] if ents else [ReferentType.NONE],
                requested_fields=fields,
                scope=GoalScope.FILTERED_SET if constraints else (GoalScope.SUMMARY if intent == GoalIntent.COURSE_OVERVIEW else GoalScope.SINGLE_FIELD),
                constraints=constraints,
                aggregation=aggr,
                comparison=ComparisonType.COMPARE if aggr == AggregationType.COMPARE else ComparisonType.NONE,
                confidence=0.90,
                confidence_margin=0.30,
                missing_slots=missing,
                resolution_sources={"intent": "structured_llm_fallback"},
            )
            val_errs = validate_goal_frame(frame)
            if val_errs:
                self.schema_failure_count += 1
                return None
            return frame
        except Exception as ex:
            logger.warning(f"SemanticGoalInterpreter: LLM fallback error: {ex}")
            self.schema_failure_count += 1
            return None

    def get_metrics(self) -> Dict[str, Any]:
        """Trả về các số liệu thống kê vận hành của Semantic Goal Interpreter."""
        fallback_rate = (self.llm_fallback_count / self.total_interpret_count) if self.total_interpret_count > 0 else 0.0
        schema_fail_rate = (self.schema_failure_count / self.llm_fallback_count) if self.llm_fallback_count > 0 else 0.0
        return {
            "total_queries": self.total_interpret_count,
            "fallback_count": self.llm_fallback_count,
            "schema_failure_count": self.schema_failure_count,
            "goal_parser_llm_fallback_rate": fallback_rate,
            "llm_parser_schema_failure_rate": schema_fail_rate,
        }


# Global Singleton Instance
_interpreter_singleton: Optional[SemanticGoalInterpreter] = None


def get_semantic_goal_interpreter() -> SemanticGoalInterpreter:
    """Lấy Singleton SemanticGoalInterpreter."""
    global _interpreter_singleton
    if _interpreter_singleton is None:
        _interpreter_singleton = SemanticGoalInterpreter()
    return _interpreter_singleton
