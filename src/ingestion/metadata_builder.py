"""
Xây dựng metadata chuẩn hóa và an toàn (chỉ chứa primitive types) cho các chunk trong Vector DB.
"""
import os
import re
from typing import Dict, Any, Optional


def detect_doc_type(file_path: str) -> str:
    norm = file_path.replace("\\", "/").lower()
    if "course_detail" in norm:
        return "course_detail"
    elif "curriculum" in norm:
        return "curriculum"
    elif "regulation" in norm:
        return "regulation"
    return "others"


def extract_course_code_from_filename(filename: str) -> str:
    match = re.search(r"([A-Z]{3,4}\d{4})", filename)
    return match.group(1) if match else ""


def build_base_metadata(file_path: str, doc_type: str, chunk_id: str) -> Dict[str, Any]:
    filename = os.path.basename(file_path)
    return {
        "source_file": filename,
        "filename": filename,
        "document_type": doc_type,
        "chunk_id": chunk_id,
        "course_code": "",
        "course_name": "",
        "major": "CNTT",
        "cohort": "",
        "section": "",
        "subsection": "",
    }


def build_course_detail_metadata(file_path: str, text: str, chunk_id: str, **kwargs) -> Dict[str, Any]:
    meta = build_base_metadata(file_path, "course_detail", chunk_id)
    filename = os.path.basename(file_path)

    # Trích xuất mã môn học
    course_code = extract_course_code_from_filename(filename)
    if not course_code:
        code_match = re.search(r"Mã học phần[:\s]+([A-Z0-9]+)", text)
        if code_match:
            course_code = code_match.group(1).strip()
    meta["course_code"] = course_code

    # Trích xuất tên môn học
    if "-" in filename:
        name_part = filename.split("-", 1)[-1].replace(".docx", "").strip()
        meta["course_name"] = name_part
    elif "_" in filename:
        name_part = filename.split("_", 1)[-1].replace(".docx", "").strip()
        meta["course_name"] = name_part

    # Section info
    if "section" in kwargs:
        meta["section"] = str(kwargs["section"])
    if "section_title" in kwargs:
        meta["subsection"] = str(kwargs["section_title"])
    if "week" in kwargs and kwargs["week"]:
        meta["subsection"] = f"Tuần {kwargs['week']}"

    # Trích xuất số tín chỉ nếu có
    credit_match = re.search(r"(\d+)\s*tín chỉ", text, re.IGNORECASE)
    if credit_match:
        meta["credits"] = int(credit_match.group(1))

    return meta


def build_curriculum_metadata(file_path: str, text: str, chunk_id: str, **kwargs) -> Dict[str, Any]:
    meta = build_base_metadata(file_path, "curriculum", chunk_id)
    filename = os.path.basename(file_path)

    cohort_match = re.search(r"K(\d+)", filename, re.IGNORECASE)
    if cohort_match:
        meta["cohort"] = f"K{cohort_match.group(1)}"

    # Chuyên ngành
    if "KHMT" in filename:
        meta["major"] = "Khoa học máy tính"
    elif "HTTT" in filename:
        meta["major"] = "Hệ thống thông tin"
    else:
        meta["major"] = "Công nghệ thông tin"

    if "semester" in kwargs and kwargs["semester"]:
        meta["section"] = f"Học kỳ {kwargs['semester']}"
    if "section" in kwargs:
        meta["section"] = str(kwargs["section"])

    return meta


def build_regulation_metadata(file_path: str, text: str, chunk_id: str, **kwargs) -> Dict[str, Any]:
    meta = build_base_metadata(file_path, "regulation", chunk_id)

    # Trích xuất Điều hoặc Chương
    article_match = re.search(r"(Điều\s+\d+[^:\n]*)", text)
    if article_match:
        meta["section"] = article_match.group(1).strip()
    chapter_match = re.search(r"(CHƯƠNG\s+[IVX]+[^:\n]*)", text, re.IGNORECASE)
    if chapter_match:
        meta["subsection"] = chapter_match.group(1).strip()

    return meta


def build_metadata(file_path: str, text: str, chunk_id: str, doc_type: Optional[str] = None, **kwargs) -> Dict[str, Any]:
    if not doc_type or doc_type == "unknown":
        doc_type = detect_doc_type(file_path)

    if doc_type in ("course_detail", "syllabus"):
        return build_course_detail_metadata(file_path, text, chunk_id, **kwargs)
    elif doc_type == "curriculum":
        return build_curriculum_metadata(file_path, text, chunk_id, **kwargs)
    elif doc_type == "regulation":
        return build_regulation_metadata(file_path, text, chunk_id, **kwargs)
    else:
        return build_base_metadata(file_path, doc_type, chunk_id)
