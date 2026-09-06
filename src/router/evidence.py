"""
Evidence Extractor: Bóc tách chứng cớ có cấu trúc và gán mức độ tin cậy (STRONG / WEAK / NONE)
phục vụ định tuyến ý định cục bộ, ngăn chặn ô nhiễm mục tiêu từ các từ ngữ thông dụng.
"""
import re
from typing import Dict, Any, Optional
from src.router.schemas import RouterEvidence


def extract_evidence(text: str, lower_text: str, analyzed_query: Optional[Dict[str, Any]] = None) -> RouterEvidence:
    """
    Trích xuất toàn bộ bằng chứng ngữ nghĩa và cấu trúc từ câu hỏi.
    """
    evidence = RouterEvidence()

    # 1. Bóc tách Mã môn học (Course Code)
    code_match = re.search(r"\b([A-Z]{2,4}\d{4})\b", text, re.IGNORECASE)
    if code_match:
        evidence.course_code = code_match.group(1).upper()
        evidence.course_code_strength = "STRONG"
    elif analyzed_query and analyzed_query.get("course_code"):
        evidence.course_code = analyzed_query["course_code"].upper()
        evidence.course_code_strength = "WEAK"

    if analyzed_query and analyzed_query.get("course_name"):
        evidence.course_name_signal = analyzed_query["course_name"]

    # 2. Bóc tách Tín hiệu Phạm vi Học vụ / Đại Nam (Academic Scope)
    scope_keywords = [
        "đại học đại nam", "đại nam", "khoa cntt", "ngành cntt", "k19", "k18", "k17", "k20",
        "quy chế đào tạo", "chương trình đào tạo", "khung chương trình",
        "chuẩn đầu ra clo", "đề cương chi tiết", "học phần", "môn học của trường",
        "đồ án tốt nghiệp", "xét tốt nghiệp"
    ]
    if any(sk in lower_text for sk in scope_keywords):
        evidence.academic_scope = True

    if any(ck in lower_text for ck in ["chương trình đào tạo", "khung chương trình", "môn học theo kỳ"]):
        evidence.curriculum_scope = True

    if any(rk in lower_text for rk in ["quy chế", "quy định", "buộc thôi học", "cảnh báo học vụ", "điều kiện tốt nghiệp", "tốt nghiệp", "đồ án tốt nghiệp"]):
        evidence.regulation_scope = True

    # 3. Bóc tách và Khử nhiễu Mục tiêu Học vụ (Academic Target)
    # Khử nhiễu từ "điểm":
    has_false_diem = bool(re.search(
        r"\b(điểm khác biệt|ưu điểm|nhược điểm|điểm mạnh|điểm yếu|đặc điểm|quan điểm|thời điểm)\b",
        lower_text
    ))
    has_academic_diem = bool(re.search(
        r"\b(điểm\s*(a1|a2|a3|chuyên cần|giữa kỳ|cuối kỳ|rèn luyện|thi|học phần|thang)|tính điểm|trọng số điểm)\b",
        lower_text
    ))

    # Khử nhiễu từ "mục tiêu":
    has_false_objective = bool(re.search(
        r"\b(mục tiêu của thuật toán|mục tiêu của giao thức|mục tiêu của rest|mục tiêu của oop)\b",
        lower_text
    ))
    has_academic_objective = bool(re.search(
        r"\b(mục tiêu môn|mục tiêu học phần|mục tiêu đào tạo|mục tiêu bài học)\b",
        lower_text
    ))

    # 4. Bóc tách Ý định Công cụ (Tool Intent Proximity Matching) & An toàn Ngữ nghĩa (Safety Gate)
    from src.semantics import analyze_utterance, Polarity, Modality
    sem = analyze_utterance(text)

    # A. Email tool
    is_email_unsafe = (
        sem.polarity == Polarity.NEGATED
        or sem.prohibition_detected
        or sem.modality in [Modality.EXPLANATORY, Modality.HYPOTHETICAL]
        or sem.is_contradictory
        or (sem.polarity == Polarity.MIXED and any(w in lower_text for w in ["đừng gửi", "không gửi", "chớ gửi", "thôi đừng"]))
        or any(nk in lower_text for nk in [
            "email là gì", "giao thức email", "khái niệm email", "smtp là gì",
            "địa chỉ email là gì", "email của thầy", "email giảng viên", "email liên hệ",
            "làm thế nào để gửi email", "hướng dẫn gửi email"
        ])
    )
    email_action_match = re.search(
        r"\b(soạn|gửi|viết|draft|compose|send)\b.{0,35}\b(email|mail|thư)\b",
        lower_text
    )
    if email_action_match and not is_email_unsafe:
        evidence.tool_action = email_action_match.group(1)
        evidence.tool_object = email_action_match.group(2)
        evidence.tool_intent = "SEND_EMAIL"
        evidence.tool_strength = "STRONG"

    # B. Reminder tool
    is_reminder_unsafe = (
        sem.polarity == Polarity.NEGATED
        or sem.prohibition_detected
        or sem.modality in [Modality.EXPLANATORY, Modality.HYPOTHETICAL]
        or sem.is_contradictory
        or any(nk in lower_text for nk in [
            "nhắc lại khái niệm", "nhắc lại kiến thức", "nhắc lại định nghĩa",
            "nhắc lại bài cũ", "nhắc nhở là gì", "làm thế nào để nhắc",
            "hướng dẫn nhắc"
        ])
    )
    reminder_action_match = re.search(
        r"\b(nhắc|đặt lịch|lên lịch|hẹn|hẹn giờ|báo|remind|schedule|nhắc nhở)\b.{0,35}\b(tôi|lịch|ôn thi|nộp|deadline|hạn|giờ|ngày|buổi|mai|họp|chiều|sáng|tối)\b",
        lower_text
    )
    if reminder_action_match and not is_reminder_unsafe:
        evidence.tool_action = reminder_action_match.group(1)
        evidence.tool_object = reminder_action_match.group(2)
        evidence.tool_intent = "SET_REMINDER"
        evidence.tool_strength = "STRONG"

    # Đánh giá Academic Targets chính thức
    has_email_contact_inquiry = (
        bool(re.search(r"\b(email|mail)\b", lower_text))
        and not email_action_match
        and not any(nk in lower_text for nk in ["email là gì", "giao thức email", "khái niệm email", "smtp là gì"])
    )

    if any(kw in lower_text for kw in ["tín chỉ", "mấy tín", "bao nhiêu tín", "số tín"]):
        evidence.academic_target = "credits"
        evidence.target_strength = "STRONG"
    elif has_email_contact_inquiry or any(kw in lower_text for kw in ["giảng viên", "ai dạy", "ai là người dạy", "thầy nào", "cô nào", "phụ trách môn", "phụ trách", "học vị"]):
        evidence.academic_target = "lecturer"
        evidence.target_strength = "STRONG"
    elif "chuẩn đầu ra" in lower_text or bool(re.search(r"\bclo\b", lower_text)):
        evidence.academic_target = "clo"
        evidence.target_strength = "STRONG"
    elif any(kw in lower_text for kw in ["kế hoạch giảng dạy", "lịch trình", "buổi học theo tuần"]):
        evidence.academic_target = "course_plan"
        evidence.target_strength = "STRONG"
    elif any(kw in lower_text for kw in ["tiên quyết", "học trước", "điều kiện học"]):
        evidence.academic_target = "prerequisites"
        evidence.target_strength = "STRONG"
    elif any(kw in lower_text for kw in ["đánh giá chuyên cần", "hình thức thi", "kiểm tra giữa kỳ"]) or has_academic_diem:
        evidence.academic_target = "assessment"
        evidence.target_strength = "STRONG"
    elif has_academic_objective:
        evidence.academic_target = "course_objective"
        evidence.target_strength = "STRONG"
    elif has_false_diem or has_false_objective:
        # Nhận diện rõ ràng đây là từ ngữ giao thoa không phải học vụ
        evidence.target_strength = "NONE"

    # 5. Bóc tách Tín hiệu Câu hỏi Khái niệm / Kỹ thuật chung (Conceptual Question Signal)
    conceptual_patterns = [
        r"\blà gì\b", r"\bnhư thế nào\b", r"\bnguyên lý hoạt động\b",
        r"\bkhác biệt giữa\b", r"\bso sánh\b", r"\bkhác nhau như thế nào\b",
        r"\bcách thức hoạt động\b", r"\bgiải thích\b", r"\btìm hiểu về\b",
        r"\bthuật toán\b", r"\bgiao thức\b", r"\bcú pháp\b", r"\bđặc điểm của\b",
        r"\btính chất\b", r"\bưu điểm và nhược điểm\b", r"\bkhái niệm\b",
        r"\bthường dùng\b", r"\bphổ biến\b", r"\bứng dụng\b", r"\btrong thực tế\b"
    ]
    if any(re.search(cp, lower_text) for cp in conceptual_patterns):
        evidence.conceptual_question_signal = True

    return evidence
