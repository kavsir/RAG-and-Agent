"""
Query Normalizer: Chuẩn hóa câu hỏi an toàn phục vụ phân tích ý định mà không làm mất văn bản gốc.
"""
import re
import unicodedata
from typing import Tuple


def normalize_query(raw_query: str) -> Tuple[str, str]:
    """
    Chuẩn hóa câu hỏi an toàn.
    Returns:
        (clean_text, normalized_lower)
        - clean_text: Giữ nguyên hoa/thường ban đầu, chuẩn hóa Unicode NFC và khoảng trắng.
        - normalized_lower: Chuỗi viết thường, chuẩn hóa khoảng cách mã môn (ví dụ 'fit 4201' -> 'fit4201').
    """
    if not raw_query:
        return "", ""

    # 1. Unicode NFKC normalization
    text = unicodedata.normalize("NFKC", raw_query)

    # 2. Xóa khoảng trắng thừa
    text = re.sub(r"\s+", " ", text).strip()

    # 3. Tạo bản copy viết thường phục vụ so khớp
    lower_text = text.lower()

    # 4. Chuẩn hóa mã môn học viết cách (ví dụ 'fit 4201' -> 'fit4201', 'ai 9990' -> 'ai9990')
    lower_text = re.sub(r"\b([a-z]{2,4})\s+(\d{4})\b", r"\1\2", lower_text)

    return text, lower_text
