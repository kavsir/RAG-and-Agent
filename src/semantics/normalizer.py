"""
Text Normalizer for Semantics Layer.
Standardizes Unicode, whitespace, and clause delimiters for accurate linguistic analysis.
"""
import re
import unicodedata
from typing import List


def normalize_whitespace(text: str) -> str:
    """Loại bỏ khoảng trắng thừa và chuẩn hóa dòng mới."""
    if not text:
        return ""
    # Chuẩn hóa Unicode NFKC
    text = unicodedata.normalize("NFKC", text)
    # Thay thế các ký tự điều khiển/khoảng trắng lạ
    text = re.sub(r"[\r\n\t\f\v]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_for_semantics(text: str) -> str:
    """Chuẩn hóa văn bản phục vụ phân tích ngữ nghĩa: chữ thường, đệm dấu câu."""
    cleaned = normalize_whitespace(text).lower()
    # Thêm khoảng trắng quanh các dấu câu phân tách mệnh đề
    cleaned = re.sub(r"([,;:!?\.])", r" \1 ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def split_clauses(text: str) -> List[str]:
    """
    Tách câu thành các mệnh đề con dựa trên dấu câu và các liên từ tương phản.
    Hữu ích để phát hiện mâu thuẫn nội tại hoặc câu lai ghép (mixed clauses).
    """
    raw_norm = normalize_whitespace(text)
    if not raw_norm:
        return []

    # Tách theo dấu câu ngắt câu / mệnh đề: phẩy, chấm phẩy, chấm lửng, gạch nối
    delimiters = r"[,;\.\?!]|\b(?:nhưng|mà|tuy nhiên|tuy thế|song|thế nhưng|nhưng mà|à không|khoan|thôi|đổi ý)\b"
    tokens = re.split(delimiters, raw_norm, flags=re.IGNORECASE)
    clauses = [t.strip() for t in tokens if t.strip()]
    return clauses or [raw_norm]
