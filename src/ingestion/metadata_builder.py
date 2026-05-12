# metadata_builder.py
import os
import re
from typing import Dict, Any, List

def detect_doc_type(file_path: str) -> str:
    if 'course_detail' in file_path:
        return 'syllabus'
    elif 'curriculum' in file_path:
        return 'curriculum'
    elif 'regulation' in file_path:
        return 'regulation'
    else:
        return 'unknown'

def extract_course_code_from_filename(filename: str) -> str:
    match = re.match(r'([A-Z0-9]+)', filename)
    return match.group(1) if match else ''

def build_base_metadata(file_path: str, doc_type: str, chunk_id: str) -> Dict[str, Any]:
    filename = os.path.basename(file_path)
    return {
        "source_file": file_path,
        "filename": filename,
        "doc_type": doc_type,
        "chunk_id": chunk_id,
        "language": "vi",
    }

def build_syllabus_metadata(file_path: str, text: str, chunk_id: str, **kwargs) -> Dict[str, Any]:
    meta = build_base_metadata(file_path, 'syllabus', chunk_id)
    filename = os.path.basename(file_path)
    meta['course_code'] = extract_course_code_from_filename(filename)
    if '-' in filename:
        name_part = filename.split('-', 1)[-1].replace('.docx', '').strip()
        meta['course_name'] = name_part

    # Metadata từ chunker
    if 'section' in kwargs:
        meta['section'] = kwargs['section']
    if 'section_num' in kwargs:
        meta['section_num'] = kwargs['section_num']
    if 'section_title' in kwargs:
        meta['section_title'] = kwargs['section_title']
    if 'type' in kwargs:
        meta['chunk_type'] = kwargs['type']
    if 'clos' in kwargs:
        meta['clos'] = kwargs['clos']
    if 'week' in kwargs:
        meta['week'] = kwargs['week']
    if 'sub_section' in kwargs:
        meta['sub_section'] = kwargs['sub_section']
    if 'sub_section_title' in kwargs:
        meta['sub_section_title'] = kwargs['sub_section_title']

    # Trích xuất thông tin dựa trên section_num
    section_num = kwargs.get('section_num', '')
    if section_num == 'I':
        # Thông tin tổng quát
        credit_match = re.search(r'(\d+)\s*tín chỉ', text)
        if credit_match:
            meta['credits'] = int(credit_match.group(1))
        prereq_match = re.search(r'Học phần học trước[:\s]+([A-Z0-9]+)', text)
        if prereq_match:
            meta['prerequisite'] = prereq_match.group(1)
        # Có thể trích xuất thêm: ngày ban hành, khoa phụ trách...
        date_match = re.search(r'Ngày ban hành[:\s]+(.+)', text)
        if date_match:
            meta['issued_date'] = date_match.group(1).strip()
    elif section_num == 'II':
        # Thông tin giảng viên
        lecturers = []
        # Tìm các dòng có "Giảng viên phụ trách" hoặc "Giảng viên giảng dạy"
        for line in text.split('\n'):
            line = line.strip()
            if 'Giảng viên' in line and ':' in line:
                lecturers.append(line)
            # Cũng có thể bắt email, học vị
            email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', line)
            if email_match and 'Giảng viên' not in line:
                # Dòng chứa email nhưng không có "Giảng viên" -> có thể là email giảng viên
                lecturers.append(line)
        if lecturers:
            meta['lecturers'] = lecturers
    elif section_num == 'V':
        # Chuẩn đầu ra (CLO) đã có trong kwargs['clos']
        # Có thể thêm danh sách chi tiết
        clos_list = kwargs.get('clos', [])
        if clos_list:
            meta['clos'] = clos_list
    elif section_num == 'VIII':
        # Đánh giá: trích xuất các phương pháp đánh giá (A1, A2.1, A2.2, A3)
        assessments = re.findall(r'([A-Z]\d+(?:\.\d+)?)', text)
        if assessments:
            meta['assessment_methods'] = list(set(assessments))  # loại trùng

    return meta

def build_curriculum_metadata(file_path: str, text: str, chunk_id: str, **kwargs) -> Dict[str, Any]:
    meta = build_base_metadata(file_path, 'curriculum', chunk_id)
    filename = os.path.basename(file_path)
    match = re.search(r'K(\d+)', filename)
    if match:
        meta['cohort'] = f"K{match.group(1)}"
    meta['program'] = 'CNTT'

    # Metadata từ chunker
    if 'type' in kwargs:
        meta['chunk_type'] = kwargs['type']
    if 'semester' in kwargs:
        meta['semester'] = kwargs['semester']
    if 'specialization' in kwargs:
        meta['specialization'] = kwargs['specialization']

    # Trích xuất danh sách mã môn học nếu có
    course_codes = re.findall(r'([A-Z]{3}\d{4})', text)
    if course_codes:
        meta['course_codes'] = list(set(course_codes))

    return meta

def build_regulation_metadata(file_path: str, text: str, chunk_id: str, **kwargs) -> Dict[str, Any]:
    meta = build_base_metadata(file_path, 'regulation', chunk_id)

    # Trích xuất chương nếu có
    chapter_match = re.search(r'(CHƯƠNG\s+[IVX]+)', text, re.IGNORECASE)
    if chapter_match:
        meta['chapter'] = chapter_match.group(1)

    # Trích xuất điều
    if 'article' in kwargs:
        meta['article'] = kwargs['article']
    else:
        article_match = re.search(r'(Điều\s+\d+)', text)
        if article_match:
            meta['article'] = article_match.group(1)

    # Trích xuất tiêu đề (dòng đầu)
    first_line = text.split('\n')[0].strip()
    if first_line:
        meta['title'] = first_line

    # Trích xuất từ khóa chính
    topics = []
    keywords = ['tín chỉ', 'thời gian', 'khối lượng', 'đánh giá', 'thi', 'điểm', 'tốt nghiệp',
                'học tập', 'quy chế', 'sinh viên', 'giảng viên', 'chương trình']
    for kw in keywords:
        if kw in text.lower():
            topics.append(kw)
    if topics:
        meta['topics'] = topics

    return meta

def build_metadata(file_path: str, text: str, chunk_id: str, doc_type: str = None, **kwargs) -> Dict[str, Any]:
    if doc_type is None:
        doc_type = detect_doc_type(file_path)

    if doc_type == 'syllabus':
        return build_syllabus_metadata(file_path, text, chunk_id, **kwargs)
    elif doc_type == 'curriculum':
        return build_curriculum_metadata(file_path, text, chunk_id, **kwargs)
    elif doc_type == 'regulation':
        return build_regulation_metadata(file_path, text, chunk_id, **kwargs)
    else:
        return build_base_metadata(file_path, 'unknown', chunk_id)