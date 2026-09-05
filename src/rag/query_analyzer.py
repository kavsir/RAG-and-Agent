"""
Query Analyzer: Phân tích cấu trúc câu hỏi người dùng, giải quyết entity và liên kết ngữ cảnh hội thoại.
"""
import re
import logging
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


logger = logging.getLogger(__name__)

# Danh mục các targets cần bóc tách
TARGET_KEYWORDS = {
    "credits": ["tín chỉ", "mấy tín", "bao nhiêu tín", "số tín", "credit"],
    "lecturer": ["giảng viên", "ai dạy", "ai là người dạy", "người dạy", "thầy", "cô", "phụ trách", "email", "học vị", "liên hệ"],
    "clo": ["clo", "chuẩn đầu ra", "đề cương", "đề cương chi tiết", "course learning outcome", "chuẩn đầu"],
    "course_objective": ["mục tiêu", "objective", "học xong được gì"],
    "course_plan": ["kế hoạch", "tuần", "lịch học", "lịch trình", "buổi học", "schedule"],
    "assessment": ["đánh giá", "điểm", "thi", "kiểm tra", "trọng số", "giữa kỳ", "chuyên cần", "cuối kỳ"],
    "prerequisites": ["tiên quyết", "học trước", "điều kiện học"],
    "curriculum": ["chương trình", "đào tạo", "danh sách môn", "môn học theo kỳ", "khung chương trình"],
    "semester": ["học kỳ", "kỳ nào", "học kỳ nào", "vào kỳ", "kỳ 1", "kỳ 2", "kỳ 3", "kỳ 4", "kỳ 5", "kỳ 6", "kỳ 7", "kỳ 8"],
    "regulation": ["quy chế", "quy định", "tốt nghiệp", "học vụ", "cảnh báo", "buộc thôi học", "điều kiện"],
    "graduation_requirement": ["tốt nghiệp", "xét tốt nghiệp", "chuẩn tốt nghiệp", "điều kiện ra trường"],
}


class AnalyzedQuery(BaseModel):
    raw_query: str
    rewritten_query: str
    domain: str = "course_detail"  # "course_detail" | "curriculum" | "regulation" | "general"
    course_code: Optional[str] = None
    explicit_course_code: Optional[str] = None
    resolved_course_code: Optional[str] = None
    resolution_source: str = "NONE"  # "EXPLICIT" | "SESSION" | "UNRESOLVED" | "NONE"
    unresolved_reference: bool = False
    course_name: Optional[str] = None
    major: Optional[str] = None
    cohort: Optional[str] = None
    targets: List[str] = Field(default_factory=list)

    def to_filter_dict(self) -> Dict[str, Any]:
        """Tạo metadata filter an toàn cho ChromaDB."""
        filters = {}
        if self.course_code:
            filters["course_code"] = self.course_code
        return filters


def extract_regex_entities(text: str) -> Dict[str, Any]:
    """Trích xuất nhanh các thực thể qua regex."""
    res: Dict[str, Any] = {
        "course_code": None,
        "cohort": None,
        "major": None,
        "targets": []
    }

    # Bắt mã môn học: FIT4201, FIT4104, AI9990, SE2024, v.v.
    code_match = re.search(r"\b([A-Z]{2,4}\d{4})\b", text, re.IGNORECASE)
    if code_match:
        res["course_code"] = code_match.group(1).upper()

    # Bắt khóa học: K19, K18, K17, v.v.
    cohort_match = re.search(r"\b(K\d{1,2})\b", text, re.IGNORECASE)
    if cohort_match:
        res["cohort"] = cohort_match.group(1).upper()

    # Bắt ngành học
    text_lower = text.lower()
    if "khoa học máy tính" in text_lower or "khmt" in text_lower:
        res["major"] = "Khoa học máy tính"
    elif "hệ thống thông tin" in text_lower or "httt" in text_lower:
        res["major"] = "Hệ thống thông tin"
    elif "công nghệ thông tin" in text_lower or "cntt" in text_lower or "it" in text_lower:
        res["major"] = "Công nghệ thông tin"

    # Nhận diện targets an toàn với word boundary cho các từ ngắn
    for target, kws in TARGET_KEYWORDS.items():
        for kw in kws:
            if len(kw.split()) == 1 and len(kw) <= 4:
                if re.search(r"\b" + re.escape(kw) + r"\b", text_lower):
                    res["targets"].append(target)
                    break
            else:
                if kw in text_lower:
                    res["targets"].append(target)
                    break

    return res


def analyze_query(
    query: str,
    chat_history: str = "",
    session_context: Optional[Dict[str, Any]] = None,
) -> AnalyzedQuery:
    """
    Phân tích toàn diện câu hỏi để chuẩn bị cho quá trình retrieval và định tuyến.
    Tích hợp bộ nhớ phiên có cấu trúc (SessionContext) để phân giải đại từ thay thế
    và kế thừa mục tiêu một cách tất định mà không gây ô nhiễm chéo.
    """
    query_lower = query.lower()

    # 1. Bóc tách mã môn trực tiếp trong câu hiện tại
    code_match = re.search(r"\b([A-Z]{2,4}\d{4})\b", query, re.IGNORECASE)
    explicit_code: Optional[str] = code_match.group(1).upper() if code_match else None
    resolved_code: Optional[str] = explicit_code
    resolution_source = "EXPLICIT" if explicit_code else "NONE"
    unresolved_reference = False
    resolved_query = query

    # 2. Nếu không có mã môn trực tiếp, phân giải qua session_context hoặc chat_history
    if not explicit_code:
        pronoun_patterns = [
            r"\bmôn đó\b", r"\bmôn này\b", r"\bmôn đấy\b", r"\bhọc phần đó\b",
            r"\bhọc phần này\b", r"\bmôn trên\b", r"\bhọc phần trên\b",
            r"\bnó\b", r"\bkỳ đó\b"
        ]
        has_pronoun = any(re.search(p, query_lower) for p in pronoun_patterns)
        implicit_followup_cues = [
            "ai dạy", "ai phụ trách", "thầy nào", "cô nào", "email",
            "mấy tín", "bao nhiêu tín", "số tín", "chuẩn đầu ra",
            "kế hoạch", "học phí", "chuyên cần", "thi kết thúc",
            "tiên quyết", "học trước", "điều kiện tiên quyết", "đề cương"
        ]
        has_implicit_cue = any(cue in query_lower for cue in implicit_followup_cues)

        session_course = session_context.get("course_code") if session_context else None

        if session_course and (has_pronoun or has_implicit_cue):
            resolved_code = session_course.upper()
            resolution_source = "SESSION"
            if has_pronoun:
                resolved_query = re.sub(
                    r"(môn đó|môn này|học phần đó|môn đấy|môn trên)",
                    f"môn {resolved_code}",
                    query,
                    flags=re.IGNORECASE,
                )
            else:
                resolved_query = f"{query} môn {resolved_code}"
            logger.info(f"Session resolution: '{query}' -> '{resolved_query}' (source=SESSION)")
        elif has_pronoun and not session_course:
            # Có đại từ nhưng không có mã môn trong session_context -> thử tìm trong chat_history fallback
            recent_codes = re.findall(r"\b([A-Z]{2,4}\d{4})\b", chat_history)
            if recent_codes:
                resolved_code = recent_codes[-1].upper()
                resolution_source = "SESSION"
                resolved_query = re.sub(
                    r"(môn đó|môn này|học phần đó|môn đấy|môn trên)",
                    f"môn {resolved_code}",
                    query,
                    flags=re.IGNORECASE,
                )
            else:
                unresolved_reference = True
                resolution_source = "UNRESOLVED"
                logger.warning(f"Ambiguous reference: '{query}' has pronoun but no active course in session.")

    # 3. Bóc tách thực thể và mục tiêu qua regex
    extracted = extract_regex_entities(resolved_query)

    # 4. Kế thừa target từ session nếu có liên quan (target carry-over)
    if session_context and session_context.get("active_target"):
        prev_target = session_context["active_target"]
        if "email" in query_lower and prev_target in ["lecturer", "lecturer_email"]:
            if "lecturer" not in extracted["targets"]:
                extracted["targets"].append("lecturer")

    # 5. Xác định domain
    domain = "course_detail"
    curriculum_keywords = [
        "chương trình đào tạo", "chương trình", "khung chương trình", "khung",
        "môn học theo kỳ", "kỳ 1", "kỳ 2", "kỳ 3", "kỳ 4", "kỳ 5", "kỳ 6", "kỳ 7", "kỳ 8",
        "ctdt", "chuyên ngành", "cơ sở ngành", "đại cương", "bắt buộc", "tự chọn", "học phần chuyên ngành"
    ]
    regulation_keywords = [
        "quy chế", "quy định", "tốt nghiệp", "cảnh báo học vụ", "cảnh báo học tập",
        "điểm rèn luyện", "thôi học", "buộc thôi học", "hoãn thi", "thi bổ sung", "điểm f"
    ]

    q_eval_lower = resolved_query.lower()
    if any(kw in q_eval_lower for kw in regulation_keywords):
        domain = "regulation"
    elif any(kw in q_eval_lower for kw in curriculum_keywords):
        domain = "curriculum"
    elif resolved_code or any(t in extracted["targets"] for t in ["credits", "lecturer", "clo", "course_plan"]):
        domain = "course_detail"

    rewritten = resolved_query.strip()
    final_course_code = resolved_code or extracted["course_code"]

    return AnalyzedQuery(
        raw_query=query,
        rewritten_query=rewritten,
        domain=domain,
        course_code=final_course_code,
        explicit_course_code=explicit_code,
        resolved_course_code=resolved_code if resolution_source == "SESSION" else None,
        resolution_source=resolution_source,
        unresolved_reference=unresolved_reference,
        major=extracted["major"],
        cohort=extracted["cohort"],
        targets=extracted["targets"],
    )


def resolve_conversational_query(query: str, chat_history: str = "") -> str:
    """Hàm tương thích ngược (deprecated) phục vụ các unit tests cũ."""
    aq = analyze_query(query, chat_history=chat_history)
    return aq.rewritten_query
