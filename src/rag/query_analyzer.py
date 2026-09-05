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
    "lecturer": ["giảng viên", "ai dạy", "thầy", "cô", "phụ trách", "email", "học vị", "liên hệ"],
    "clo": ["clo", "chuẩn đầu ra", "course learning outcome", "chuẩn đầu"],
    "course_objective": ["mục tiêu", "objective", "học xong được gì"],
    "course_plan": ["kế hoạch", "tuần", "lịch học", "lịch trình", "buổi học", "schedule"],
    "assessment": ["đánh giá", "điểm", "thi", "kiểm tra", "trọng số", "giữa kỳ", "chuyên cần", "cuối kỳ"],
    "prerequisites": ["tiên quyết", "học trước", "điều kiện học"],
    "curriculum": ["chương trình", "đào tạo", "danh sách môn", "môn học theo kỳ", "khung chương trình"],
    "semester": ["học kỳ", "kỳ 1", "kỳ 2", "kỳ 3", "kỳ 4", "kỳ 5", "kỳ 6", "kỳ 7", "kỳ 8"],
    "regulation": ["quy chế", "quy định", "tốt nghiệp", "học vụ", "cảnh báo", "buộc thôi học", "điều kiện"],
    "graduation_requirement": ["tốt nghiệp", "xét tốt nghiệp", "chuẩn tốt nghiệp", "điều kiện ra trường"],
}


class AnalyzedQuery(BaseModel):
    raw_query: str
    rewritten_query: str
    domain: str = "course_detail"  # "course_detail" | "curriculum" | "regulation" | "general"
    course_code: Optional[str] = None
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

    # Bắt mã môn học: FIT4201, FIT4104, v.v.
    code_match = re.search(r"\b([A-Z]{3,4}\d{4})\b", text, re.IGNORECASE)
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


def resolve_conversational_query(query: str, chat_history: str = "") -> str:
    """
    Giải quyết các đại từ thay thế ('môn đó', 'môn này', 'thầy ấy') dựa vào lịch sử hội thoại gần nhất.
    Không bao giờ loại bỏ thực thể quan trọng (mã môn, tên môn, CLO, tuần).
    """
    query_lower = query.lower()
    needs_resolution = any(kw in query_lower for kw in ["môn đó", "môn này", "học phần đó", "nó", "môn đấy", "kỳ đó"])

    if not needs_resolution or not chat_history:
        return query

    # Trích xuất mã môn gần nhất từ lịch sử chat
    recent_codes = re.findall(r"\b([A-Z]{3,4}\d{4})\b", chat_history)
    if recent_codes:
        last_code = recent_codes[-1].upper()
        # Thay thế "môn đó", "môn này" bằng mã môn
        resolved = re.sub(r"(môn đó|môn này|học phần đó|môn đấy)", f"môn {last_code}", query, flags=re.IGNORECASE)
        logger.info(f"Conversational resolution: '{query}' -> '{resolved}'")
        return resolved

    return query


def analyze_query(query: str, chat_history: str = "") -> AnalyzedQuery:
    """Phân tích toàn diện câu hỏi để chuẩn bị cho quá trình retrieval và định tuyến."""
    # 1. Giải quyết follow-up query
    resolved_query = resolve_conversational_query(query, chat_history)

    # 2. Bóc tách nhanh qua regex
    extracted = extract_regex_entities(resolved_query)

    # 3. Xác định domain mục tiêu
    query_lower = resolved_query.lower()
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

    if any(kw in query_lower for kw in regulation_keywords):
        domain = "regulation"
    elif any(kw in query_lower for kw in curriculum_keywords):
        domain = "curriculum"
    elif extracted["course_code"] or any(t in extracted["targets"] for t in ["credits", "lecturer", "clo", "course_plan"]):
        domain = "course_detail"

    # 4. Tạo rewritten query tối ưu cho retrieval
    rewritten = resolved_query.strip()

    return AnalyzedQuery(
        raw_query=query,
        rewritten_query=rewritten,
        domain=domain,
        course_code=extracted["course_code"],
        major=extracted["major"],
        cohort=extracted["cohort"],
        targets=extracted["targets"],
    )
