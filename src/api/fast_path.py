"""
Local Conversational Fast Path for AI Academic Advisor.
Handles deterministic social interactions locally:
- Greetings: xin chào, hello, hi, chào bạn, chào ad, alo...
- Gratitude: cảm ơn, thanks, thank you, cảm ơn bạn...
- Farewells: tạm biệt, bye, goodbye, hẹn gặp lại...
- Identity: bạn là ai, bạn tên gì, who are you...
- Capabilities: bạn làm được gì, bạn giúp được gì, chức năng của bạn...

Performance: p95 < 10ms (zero RAG, zero embeddings, zero external LLM).
"""
import re
import unicodedata
from dataclasses import dataclass
from typing import Optional


@dataclass
class FastPathResult:
    matched: bool
    answer: str
    intent: Optional[str] = None
    category: str = "FAST_PATH"


def normalize_fast_path_text(text: str) -> str:
    """Normalize input text: lowercase, remove accents, remove punctuation, collapse whitespace."""
    if not text:
        return ""
    s = text.strip().lower()
    # Normalize unicode to NFD and strip combining accents to match accented & unaccented seamlessly
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    # Replace đ / Đ with d
    s = s.replace("đ", "d").replace("Đ", "d")
    # Remove surrounding punctuation
    s = re.sub(r"[^\w\s]", " ", s)
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s

GREETING_ANSWER = (
    "Xin chào bạn! Tôi là Trợ lý AI Cố vấn Học tập của Khoa Công nghệ Thông tin - Trường Đại học Đại Nam (DNTU).\n\n"
    "Tôi có thể hỗ trợ bạn tra cứu thông tin học phần, chuẩn đầu ra (CLO), kế hoạch học tập, "
    "phương thức đánh giá, cũng như giải đáp các quy chế đào tạo tín chỉ. Bạn cần hỗ trợ thông tin gì hôm nay?"
)

THANKS_ANSWER = (
    "Rất vui được hỗ trợ bạn! Chúc bạn học tập thật tốt và đạt kết quả cao tại DNTU. "
    "Nếu có bất kỳ thắc mắc nào về môn học hay quy chế, bạn cứ thoải mái đặt câu hỏi nhé!"
)

FAREWELL_ANSWER = (
    "Tạm biệt bạn! Chúc bạn một ngày học tập và làm việc thật hiệu quả. "
    "Hẹn gặp lại bạn bất cứ khi nào bạn cần hỗ trợ thông tin học vụ!"
)

IDENTITY_ANSWER = (
    "Tôi là **Trợ lý AI Cố vấn Học tập** của Khoa Công nghệ Thông tin - Trường Đại học Đại Nam (DNTU).\n\n"
    "Hệ thống của tôi được tích hợp trực tiếp với cơ sở dữ liệu đề cương chi tiết học phần, "
    "chương trình đào tạo K19 và quy chế đào tạo chính thống của nhà trường để cung cấp thông tin "
    "chính xác, minh bạch và có trích dẫn minh chứng rõ ràng."
)

CAPABILITY_ANSWER = (
    "Tôi có thể hỗ trợ bạn các công việc học vụ sau:\n"
    "1. 📚 **Tra cứu thông tin học phần**: Số tín chỉ, số tiết lý thuyết/thực hành, giảng viên phụ trách, email liên hệ.\n"
    "2. 🎯 **Chuẩn đầu ra (CLO)**: Mục tiêu và năng lực đạt được sau khi hoàn thành môn học.\n"
    "3. 📝 **Điều kiện & Đánh giá**: Môn học tiên quyết, thang điểm và phương thức đánh giá điểm học phần.\n"
    "4. 📜 **Quy chế & Quy định đào tạo**: Điều kiện xét tốt nghiệp, cảnh báo học vụ, quy định điểm danh, học bổng.\n"
    "5. 💻 **Hỗ trợ chuyên môn**: Giải thích các thuật toán, công nghệ và khái niệm kỹ thuật trong chương trình CNTT.\n\n"
    "Bạn có thể gõ câu hỏi tự nhiên như: *'Môn FIT4113 có mấy tín chỉ?'*, *'Giảng viên dạy môn Hệ thống nhúng là ai?'*, hoặc *'Điều kiện tốt nghiệp là gì?'*."
)


GREETING_PATTERNS = [
    r"^(xin\s+)?ch[aà]o(\s+b[aạ]n)?(\s+nh[eé])?(\s+[aạ])?$",
    r"^ch[aà]o\s+(ad|bot|th[aà]y|c[oô]|em|m[iì]nh|c[aả]\s+nh[aà])$",
    r"^(hi|hello|hey|alo+)(\s+(ad|bot|b[aạ]n))?(\s+nh[eé])?$",
    r"^(good\s+morning|good\s+afternoon|good\s+evening)$",
]

THANKS_PATTERNS = [
    r"^(c[aả]m\s+[oơ]n|thanks|thank\s+you(\s+so\s+much)?|cmon|tks|thx)(\s+(b[aạ]n|ad|bot|nhi[eề]u|nha|nh[eé]))*(\s+[aạ])?$",
    r"^(em|m[iì]nh|da|d[aạ])\s+c[aả]m\s+[oơ]n(\s+(th[aà]y|c[oô]|ad|bot|b[aạ]n|anh|ch[iị]))*(\s+[aạ])?$",
]

FAREWELL_PATTERNS = [
    r"^(t[aạ]m\s+bi[eệ]t|bye(\s+bye)?|goodbye|good\s+bye|h[eẹ]n\s+g[aặ]p\s+l[aạ]i)(\s+(b[aạ]n|ad|bot|th[aà]y|c[oô]))*(\s+nh[eé])?$",
    r"^ch[aà]o\s+t[aạ]m\s+bi[eệ]t$",
    r"^(ch[uú]c\s+)?ng[uủ]\s+ngon$",
]

IDENTITY_PATTERNS = [
    r"^(b[aạ]n|m[aà]y|bot|em|c[aậu])\s+l[aà]\s+(ai|g[iì])(\s+v[aậ]y)?\??$",
    r"^who\s+are\s+you\??$",
    r"^(t[eê]n|name)\s+(c[uủ]a\s+)?(b[aạ]n|bot)\s+l[aà]\s+g[iì]\??$",
    r"^(b[aạ]n|bot)\s+t[eê]n\s+(l[aà]\s+)?g[iì]\??$",
    r"^gi[oớ]i\s+thi[eệ]u\s+(v[eề]\s+)?(b[aả]n\s+th[aâ]n|b[aạ]n|m[iì]nh)\??$",
]

CAPABILITY_PATTERNS = [
    r"^(b[aạ]n|bot)\s+(l[aà]m|gi[uú]p)\s+(d[uư][oơ]c|\u0111\u01b0\u1ee3c)\s+g[iì]\??$",
    r"^(b[aạ]n|bot)\s+c[oó]\s+th[eể]\s+(l[aà]m|gi[uú]p)\s+g[iì]\??$",
    r"^ch[uứ]c\s+n[aă]ng(\s+c[uủ]a\s+(b[aạ]n|bot))?(\s+l[aà]\s+g[iì])?\??$",
    r"^(h[uư][oớ]ng\s+d[aã]n\s+s[uử]\s+d[uụ]ng|help|tr[oợ]\s+gi[uú]p|h[oỗ]\s+tr[oợ]\s+nh[uữ]ng\s+g[iì])\??$",
]


def match_fast_path(query: str) -> FastPathResult:
    """
    Match query against deterministic fast-path patterns.
    Returns FastPathResult with matched=True if query is a purely social interaction.
    """
    if not query:
        return FastPathResult(matched=False, answer="")

    raw = query.strip().lower()
    norm = normalize_fast_path_text(query)
    if not norm:
        return FastPathResult(matched=False, answer="")

    # Fast reject if query has domain markers or is too long
    domain_markers = ["fit", "csc", "bba", "dnu", "eng", "tin chi", "giang vien", "clo", "de cuong", "quy che", "tot nghiep", "thuat toan", "nhac"]
    if any(m in norm for m in domain_markers):
        return FastPathResult(matched=False, answer="")

    if len(norm.split()) > 7:
        return FastPathResult(matched=False, answer="")

    # 1. Capability (check before identity to avoid "chức năng của bạn là gì" matching "bạn là gì")
    for pat in CAPABILITY_PATTERNS:
        if re.search(pat, raw, re.IGNORECASE) or re.search(pat, norm, re.IGNORECASE):
            return FastPathResult(matched=True, answer=CAPABILITY_ANSWER, intent="CAPABILITY")

    # 2. Identity
    for pat in IDENTITY_PATTERNS:
        if re.search(pat, raw, re.IGNORECASE) or re.search(pat, norm, re.IGNORECASE):
            return FastPathResult(matched=True, answer=IDENTITY_ANSWER, intent="IDENTITY")

    # 3. Thanks
    for pat in THANKS_PATTERNS:
        if re.search(pat, raw, re.IGNORECASE) or re.search(pat, norm, re.IGNORECASE):
            return FastPathResult(matched=True, answer=THANKS_ANSWER, intent="THANKS")

    # 4. Farewell
    for pat in FAREWELL_PATTERNS:
        if re.search(pat, raw, re.IGNORECASE) or re.search(pat, norm, re.IGNORECASE):
            return FastPathResult(matched=True, answer=FAREWELL_ANSWER, intent="FAREWELL")

    # 5. Greeting
    for pat in GREETING_PATTERNS:
        if re.search(pat, raw, re.IGNORECASE) or re.search(pat, norm, re.IGNORECASE):
            return FastPathResult(matched=True, answer=GREETING_ANSWER, intent="GREETING")

    return FastPathResult(matched=False, answer="")

