"""
Module chứa các hàm đọc file từ định dạng .docx và .txt với bảo toàn thứ tự bảng biểu và tiêu đề.
"""
import os
import logging
from typing import Optional
from docx import Document
from docx.text.paragraph import Paragraph
from docx.table import Table

logger = logging.getLogger(__name__)


def load_docx(file_path: str) -> Optional[str]:
    """
    Đọc file .docx và trả về text theo đúng thứ tự xuất hiện của đoạn văn và bảng biểu.
    """
    try:
        doc = Document(file_path)
        full_lines = []

        for child in doc.element.body:
            if child.tag.endswith("p"):
                para = Paragraph(child, doc)
                text = para.text.strip()
                if text:
                    full_lines.append(text)
            elif child.tag.endswith("tbl"):
                table = Table(child, doc)
                for row in table.rows:
                    row_cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                    # Loại bỏ các cell trùng lặp do merge cell
                    unique_cells = []
                    for c in row_cells:
                        if not unique_cells or c != unique_cells[-1]:
                            unique_cells.append(c)
                    if unique_cells:
                        full_lines.append(" | ".join(unique_cells))

        return "\n".join(full_lines)
    except Exception as e:
        logger.error(f"Lỗi đọc file DOCX {file_path}: {e}")
        return None


def load_text(file_path: str) -> Optional[str]:
    """Đọc file .txt thông thường."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error(f"Lỗi đọc file TXT {file_path}: {e}")
        return None


def load_file(file_path: str) -> Optional[str]:
    """Tự động phát hiện định dạng và gọi loader tương ứng."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".docx":
        return load_docx(file_path)
    elif ext == ".txt":
        return load_text(file_path)
    else:
        logger.warning(f"Định dạng không hỗ trợ: {file_path}")
        return None
