"""
Personal Memory Policy & Candidate Extractor:
Trích xuất ứng viên sự thật cá nhân tất định và thực thi chính sách ghi nhớ an toàn.
Tuyệt đối 0 cuộc gọi LLM bên ngoài (Zero paid API calls).
"""
import re
import logging
from typing import List, Any, Optional, Tuple

from src.memory.personal_models import (
    SUPPORTED_FACT_KEYS,
    KNOWN_PLACEHOLDER_DEFAULTS,
    SOURCE_EXPLICIT_USER,
    SOURCE_MIGRATED_LEGACY,
)

logger = logging.getLogger(__name__)


def is_academic_claim(text: str) -> bool:
    """
    Kiểm tra xem câu nói có chứa phát ngôn học vụ / sự thật trường lớp hay không.
    Mọi tuyên bố học vụ phải được kiểm chứng qua RAG, KHÔNG ĐƯỢC lưu vào Personal Memory.
    """
    lower = text.lower()
    # Có mã môn học (FIT4201, FIT4104, ...)
    if re.search(r"\b[A-Z]{2,4}\d{4}\b", text, re.IGNORECASE):
        return True

    # Chứa từ khóa học vụ nhà trường
    academic_keywords = [
        "tín chỉ", "mấy tín", "bao nhiêu tín", "chuẩn đầu ra", "clo",
        "giảng viên phụ trách", "ai dạy môn", "thầy nào dạy", "cô nào dạy",
        "tiên quyết", "học trước", "quy chế đào tạo", "điều kiện tốt nghiệp",
        "cảnh báo học vụ", "buộc thôi học", "điểm thi", "trọng số điểm",
        "đề cương chi tiết", "đề cương môn", "học phí"
    ]
    return any(kw in lower for kw in academic_keywords)


def is_transient_or_emotional(text: str) -> bool:
    """
    Kiểm tra xem câu nói có phải là cảm xúc nhất thời, than phiền hoặc trạng thái tạm thời hay không.
    """
    lower = text.lower()
    transient_cues = [
        "hôm nay môn này khó", "môn này khó thật", "khó hiểu quá", "tôi thấy mệt",
        "mệt mỏi", "buồn ngủ", "bài tập nhiều", "áp lực quá", "stress quá",
        "không hiểu gì cả", "chán quá", "hôm nay trời đẹp", "tôi đói bụng"
    ]
    return any(cue in lower for cue in transient_cues)


def is_sensitive_topic(text: str) -> bool:
    """
    Kiểm tra chủ đề nhạy cảm không phục vụ mục đích cố vấn học tập (Privacy Rules).
    """
    lower = text.lower()
    sensitive_cues = [
        "bệnh án", "sức khỏe", "tôn giáo", "đảng phái", "chính trị",
        "giới tính", "tình dục", "tiền án", "tiền sự", "tài khoản ngân hàng",
        "mật khẩu", "số cccd", "cmnd", "số dư", "vay nợ", "sổ đỏ", "bệnh tật"
    ]
    return any(cue in lower for cue in sensitive_cues)


def normalize_fact_value(fact_key: str, raw_val: Any) -> Any:
    """Chuẩn hóa giá trị của sự thật cá nhân."""
    if not isinstance(raw_val, str):
        return raw_val

    val = raw_val.strip()
    if fact_key == "cohort":
        # Chuẩn hóa K19, k19 -> K19
        m = re.search(r"K?\s*(1[7-9]|2[0-5])", val, re.IGNORECASE)
        if m:
            return f"K{m.group(1)}"
    elif fact_key == "major":
        val_lower = val.lower()
        if "khoa học máy tính" in val_lower or "khmt" in val_lower:
            return "Khoa học máy tính"
        elif "hệ thống thông tin" in val_lower or "httt" in val_lower:
            return "Hệ thống thông tin"
        elif "công nghệ thông tin" in val_lower or "cntt" in val_lower or "it" in val_lower:
            return "Công nghệ thông tin"
        elif "kỹ thuật phần mềm" in val_lower or "ktpm" in val_lower:
            return "Kỹ thuật phần mềm"
    elif fact_key == "response_style":
        val_lower = val.lower()
        if any(w in val_lower for w in ["ngắn", "ngắn gọn", "súc tích", "concise"]):
            return "concise"
        elif any(w in val_lower for w in ["chi tiết", "đầy đủ", "detailed"]):
            return "detailed"
        elif any(w in val_lower for w in ["thực hành", "code", "practical"]):
            return "practical"
    elif fact_key == "preferred_language":
        val_lower = val.lower()
        if "tiếng anh" in val_lower or "english" in val_lower or val_lower in ["en", "eng"]:
            return "tiếng anh"
        elif "tiếng việt" in val_lower or "vietnamese" in val_lower or val_lower in ["vi", "vie"]:
            return "tiếng việt"
    elif fact_key == "current_semester":
        m = re.search(r"\d+", val)
        if m:
            return int(m.group(0))

    return val


def extract_candidate_facts(text: str) -> List[Tuple[str, Any]]:
    """
    Trích xuất các cặp (fact_key, value) tiềm năng từ câu người dùng bằng biểu thức chính quy tất định.
    """
    candidates: List[Tuple[str, Any]] = []

    # 1. Tên ưa thích (preferred_name)
    m_name = re.search(
        r"(?:từ giờ\s+)?(?:gọi\s+(?:tôi|mình|em)\s+là|tên\s+(?:của\s+)?(?:tôi|mình|em)\s+là|(?:tôi|mình|em)\s+tên\s+là)\s+([A-ZÀ-Ỹa-zà-ỹ\s]{2,30})",
        text,
        re.IGNORECASE,
    )
    if m_name:
        candidate_name = m_name.group(1).strip()
        candidate_name = re.sub(
            r"(?i)\s+(?:nhé|nha|ạ|ơi|nghe|nhe|đi|được\s+không|giúp\s+tôi|nhá|thôi)$",
            "",
            candidate_name,
        ).strip(".,!? ")
        # Loại trừ các từ chung chung
        if candidate_name.lower() not in ["sinh viên", "người dùng", "ai", "bot", "gì", "bạn", "sinh viên cntt"]:
            candidates.append(("preferred_name", candidate_name))

    # 2. Khóa học (cohort)
    m_cohort = re.search(
        r"(?:tôi|mình|em)\s+(?:học|chuyển\s+sang\s+học|là\s+sinh\s+viên)?\s*(?:khóa|k)\s*(1[7-9]|2[0-5])\b",
        text,
        re.IGNORECASE,
    )
    if m_cohort:
        candidates.append(("cohort", f"K{m_cohort.group(1)}"))
    else:
        m_cohort_simple = re.search(r"\b(?:khóa|k)\s*(1[7-9]|2[0-5])\b", text, re.IGNORECASE)
        if m_cohort_simple and any(w in text.lower() for w in ["tôi", "mình", "em", "học", "sinh viên", "chuyển"]):
            candidates.append(("cohort", f"K{m_cohort_simple.group(1)}"))

    # 3. Ngành học (major)
    m_major = re.search(
        r"(?:tôi|mình|em)\s+(?:học|là\s+sinh\s+viên)?\s*(?:ngành\s+)?(công nghệ thông tin|cntt|khoa học máy tính|khmt|hệ thống thông tin|httt|kỹ thuật phần mềm|ktpm)\b",
        text,
        re.IGNORECASE,
    )
    if m_major:
        candidates.append(("major", m_major.group(1).strip()))

    # 4. Học kỳ hiện tại (current_semester)
    m_sem = re.search(
        r"(?:tôi|mình|em)\s+(?:đang\s+)?học\s+(?:học\s+)?kỳ\s+([1-8])\b",
        text,
        re.IGNORECASE,
    )
    if m_sem:
        candidates.append(("current_semester", int(m_sem.group(1))))

    # 5. Phong cách phản hồi (response_style)
    m_style = re.search(
        r"(?:hãy|thích|muốn|yêu cầu)\s+(?:trả lời|phản hồi)\s+(ngắn gọn|chi tiết|súc tích|thực hành)",
        text,
        re.IGNORECASE,
    )
    if m_style:
        candidates.append(("response_style", m_style.group(1).strip()))
    elif any(w in text.lower() for w in ["thích câu trả lời ngắn", "trả lời ngắn thôi", "trả lời ngắn"]):
        candidates.append(("response_style", "concise"))
    elif any(w in text.lower() for w in ["trả lời chi tiết hơn", "phản hồi chi tiết hơn", "trả lời chi tiết"]):
        candidates.append(("response_style", "detailed"))

    # 6. Ngôn ngữ ưa thích (preferred_language)
    m_lang = re.search(
        r"(?:trả lời|dùng|ưu tiên)\s+(?:bằng\s+)?(tiếng việt|tiếng anh|vietnamese|english)",
        text,
        re.IGNORECASE,
    )
    if m_lang:
        candidates.append(("preferred_language", m_lang.group(1).strip().lower()))

    # 7. Mục tiêu học tập (learning_goal)
    m_goal = re.search(
        r"(?:mục tiêu\s+(?:học tập\s+)?của\s+(?:tôi|mình)|(?:tôi|mình)\s+muốn\s+trở\s+thành)\s+(?:là\s+)?([^.!?\n]{3,50})",
        text,
        re.IGNORECASE,
    )
    if m_goal:
        candidate_goal = m_goal.group(1).strip()
        candidate_goal = re.sub(
            r"(?i)\s+(?:nhé|nha|ạ|ơi|nghe|nhe|đi|được\s+không|giúp\s+tôi|nhá|thôi)$",
            "",
            candidate_goal,
        ).strip(".,!? ")
        candidates.append(("learning_goal", candidate_goal))

    # 8. Email cá nhân (own_email)
    m_email = re.search(
        r"(?:email|mail)\s+(?:của\s+)?(?:tôi|mình|em)\s+là\s+([\w\.-]+@[\w\.-]+\.\w+)",
        text,
        re.IGNORECASE,
    )
    if m_email:
        candidates.append(("own_email", m_email.group(1).strip()))

    return candidates


def evaluate_candidate(
    fact_key: str,
    raw_val: Any,
    full_text: str,
    source_type: str = SOURCE_EXPLICIT_USER,
) -> Tuple[bool, Optional[str], Any]:
    """
    Đánh giá ứng viên theo chính sách an toàn và bảo mật bộ nhớ.
    Returns:
        (is_allowed: bool, rejection_reason: Optional[str], normalized_value: Any)
    """
    # 1. Kiểm tra Whitelist
    if fact_key not in SUPPORTED_FACT_KEYS:
        return False, f"KEY_NOT_IN_WHITELIST: '{fact_key}' is not a supported personal fact", None

    # 2. Kiểm tra tuyên bố học vụ (Academic Claim)
    if is_academic_claim(full_text):
        return False, "ACADEMIC_CLAIM_REJECTED: Statement contains academic assertions that belong to RAG truth", None

    # 3. Kiểm tra cảm xúc / phát ngôn nhất thời (Transient/Emotional)
    if is_transient_or_emotional(full_text):
        return False, "TRANSIENT_OR_EMOTIONAL_REJECTED: Sentence contains transient/emotional state", None

    # 4. Kiểm tra dữ liệu nhạy cảm (Sensitive info)
    if is_sensitive_topic(full_text):
        return False, "SENSITIVE_INFO_REJECTED: Statement involves sensitive privacy domains", None

    # 5. Chuẩn hóa giá trị
    norm_val = normalize_fact_value(fact_key, raw_val)

    # 6. Kiểm tra giá trị rỗng hoặc placeholder default
    if norm_val is None or (isinstance(norm_val, str) and not norm_val.strip()):
        return False, "EMPTY_VALUE_REJECTED: Value is empty", None

    # Tên hoặc email mặc định giả lập không bao giờ được chấp nhận dù từ nguồn nào
    if fact_key in ["preferred_name", "name"] and norm_val == "Sinh viên CNTT":
        return False, f"PLACEHOLDER_DEFAULT_REJECTED: '{norm_val}' matches known system placeholder", None
    if fact_key in ["own_email", "email"] and norm_val == "student@dainam.edu.vn":
        return False, f"PLACEHOLDER_DEFAULT_REJECTED: '{norm_val}' matches known system placeholder", None

    # Với dữ liệu di chuyển từ tệp legacy cũ, toàn bộ template mặc định bị loại bỏ
    if source_type == SOURCE_MIGRATED_LEGACY:
        if fact_key in KNOWN_PLACEHOLDER_DEFAULTS and norm_val == KNOWN_PLACEHOLDER_DEFAULTS[fact_key]:
            return False, f"PLACEHOLDER_DEFAULT_REJECTED: '{norm_val}' matches known system placeholder", None

    return True, None, norm_val
