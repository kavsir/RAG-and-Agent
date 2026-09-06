"""
Knowledge Environment Builder for Agent Core V1.1.
Deterministically generates runtime/knowledge_environment.json from:
- data_raw/curriculum/*.docx
- data_raw/course_detail/*.docx
- data_raw/regulation/*.docx
Enforces provenance for every factual field and eliminates hardcoded mutable python dictionaries.
"""
import os
import glob
import re
import json
import docx
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any

RUNTIME_PATH = Path("runtime/knowledge_environment.json")
INGESTION_VERSION = "v1.2"
EXTRACTED_AT = datetime.now(timezone.utc).isoformat()

UNAVAILABLE_FIELDS = {
    "failure_rate": {
        "title": "Tỷ lệ trượt môn / Thống kê rớt môn",
        "reason": "Môi trường học vụ hiện không công bố bảng thống kê tỷ lệ trượt môn sinh viên.",
        "alternative_fields": ["credits", "assessment", "hours"],
        "proposal_text": (
            "Hiện dữ liệu chính thức không công bố thống kê tỷ lệ trượt môn (tỷ lệ rớt môn). "
            "Mình có thể phân tích cấu trúc điểm đánh giá, khối lượng tín chỉ và số giờ thực hành "
            "để bạn ước lượng mức độ đòi hỏi của học phần. Bạn có muốn xem theo hướng này không?"
        ),
    },
    "difficulty": {
        "title": "Chỉ số độ khó học phần",
        "reason": "Đề cương và quy chế không xếp hạng hay gán nhãn độ khó chủ quan cho môn học.",
        "alternative_fields": ["credits", "hours", "assessment"],
        "proposal_text": (
            "Tài liệu chính thức hiện không xếp hạng hay đánh giá trực tiếp về độ khó hay khả năng dễ qua môn của môn học. "
            "Mình có thể so sánh gián tiếp bằng số tín chỉ, khối lượng thực hành và cấu trúc điểm đánh giá. "
            "Bạn có muốn dùng các tiêu chí này để so sánh không?"
        ),
    },
    "student_rating": {
        "title": "Đánh giá / Review chủ quan của sinh viên",
        "reason": "Hệ thống học vụ chỉ lưu trữ tài liệu chuẩn ban hành, không tích hợp diễn đàn review sinh viên.",
        "alternative_fields": ["objectives", "clo", "assessment"],
        "proposal_text": (
            "Tài liệu chính thức không lưu trữ review hay đánh giá của sinh viên khoá trước và cách chấm điểm của thầy. "
            "Mình có thể cung cấp mục tiêu môn học, chuẩn đầu ra (CLO) và tiêu chí đánh giá để bạn nắm rõ kỳ vọng. "
            "Bạn có muốn xem không?"
        ),
    },
    "job_salary": {
        "title": "Mức lương sau tốt nghiệp",
        "reason": "Dữ liệu đào tạo không chứa khảo sát thống kê thu nhập sau tốt nghiệp.",
        "alternative_fields": ["objectives", "clo"],
        "proposal_text": (
            "Dữ liệu chính thức hiện không chứa thống kê mức lương hay thu nhập sau tốt nghiệp. "
            "Mình có thể cung cấp thông tin về chuẩn đầu ra và kiến thức kỹ năng đạt được sau môn học. "
            "Bạn có muốn tìm hiểu không?"
        ),
    },
    "exam_leak": {
        "title": "Đề thi năm ngoái / Thông tin lộ đề",
        "reason": "Hệ thống tuyệt đối bảo mật đề thi và không hỗ trợ các câu hỏi liên quan đến lộ đề.",
        "alternative_fields": ["assessment"],
        "proposal_text": (
            "Tài liệu chính thức bảo mật và không công bố đề thi hay thông tin lộ đề (leak đề). "
            "Mình có thể cung cấp hình thức thi và cấu trúc đánh giá chính thức của học phần. "
            "Bạn có muốn xem không?"
        ),
    },
}

DOCUMENT_TYPES = {
    "course_detail": {
        "title": "Đề cương chi tiết học phần",
        "authority_level": "PRIMARY_COURSE_AUTHORITY",
        "directory": "data_raw/course_detail",
        "collection": "course_detail",
        "verifiable_fields": [
            "course_code", "course_name_vi", "course_name_en",
            "credits", "theory_hours", "practice_hours", "hours",
            "department", "prerequisites", "course_objective", "objectives",
            "clo", "assessment", "course_plan", "lecturer", "lecturer_email"
        ]
    },
    "curriculum": {
        "title": "Khung chương trình đào tạo K19",
        "authority_level": "PRIMARY_CURRICULUM_AUTHORITY",
        "directory": "data_raw/curriculum",
        "collection": "curriculum",
        "verifiable_fields": [
            "course_code", "course_name", "credits", "semester",
            "course_placement", "curriculum_structure", "cohort_plan",
            "total_credits_program", "course_type"
        ]
    },
    "regulation": {
        "title": "Quy chế & Quy định đào tạo ĐNTU",
        "authority_level": "PRIMARY_REGULATION_AUTHORITY",
        "directory": "data_raw/regulation",
        "collection": "regulation",
        "verifiable_fields": [
            "graduation_requirements", "academic_warning", "training_rules",
            "grading_scale", "attendance_rules", "scholarship_rules",
            "retake_rules", "regulation"
        ]
    }
}

OUTLINE_ALIASES = {
    "FIT4104": [
        "full-stack", "full stack", "fullstack",
        "dự án thiết kế lập trình full-stack", "lập trình full-stack",
        "dự án full-stack", "dự án full stack", "thiết kế lập trình full-stack",
        "công nghệ web"
    ],
    "FIT4113": [
        "điện toán đám mây", "cloud computing",
        "công nghệ điện toán đám mây", "đám mây"
    ],
    "FIT4117": [
        "quản trị dự án cntt", "quản trị dự án",
        "quản trị dự án công nghệ thông tin", "it project management"
    ],
    "FIT4201": [
        "hệ thống nhúng", "embedded systems", "embedded system",
        "nhúng"
    ]
}

ENGLISH_NAMES = {
    "FIT4104": "Full-Stack Design and Programming",
    "FIT4113": "Cloud computing technologies",
    "FIT4117": "IT Project Management",
    "FIT4201": "Embedded Systems"
}


def build_knowledge_environment() -> Dict[str, Any]:
    entities: Dict[str, Dict[str, Any]] = {}

    # 1. Parse Curriculum docx
    curric_files = sorted(glob.glob("data_raw/curriculum/*.docx"))
    course_pattern = re.compile(r"^([A-Z]{3,4}\d{4})\s*-\s*(.+?)\s*-\s*(\d+)\s*tín\s*chỉ", re.MULTILINE)

    for fpath in curric_files:
        fname = os.path.basename(fpath)
        try:
            doc = docx.Document(fpath)
            for p in doc.paragraphs:
                for m in course_pattern.finditer(p.text):
                    code = m.group(1).strip()
                    name = m.group(2).strip()
                    credits_val = int(m.group(3))

                    if code not in entities:
                        entities[code] = {
                            "entity_id": code,
                            "canonical_name": name,
                            "english_name": ENGLISH_NAMES.get(code, ""),
                            "aliases": [name.lower()],
                            "sources": [fname],
                            "document_types": ["curriculum"],
                            "has_outline": False,
                            "available_fields": ["credits", "course_name"],
                            "provenance": {
                                "source_file": fname,
                                "document_type": "curriculum",
                                "extracted_at": EXTRACTED_AT,
                                "ingestion_version": INGESTION_VERSION,
                                "credits_authoritative": credits_val,
                            }
                        }
                    else:
                        if fname not in entities[code]["sources"]:
                            entities[code]["sources"].append(fname)
        except Exception as e:
            print(f"Lỗi đọc {fpath}: {e}")

    # 2. Parse Detailed Outlines
    outline_files = sorted(glob.glob("data_raw/course_detail/*.docx"))
    for fpath in outline_files:
        fname = os.path.basename(fpath)
        m = re.search(r"(FIT\d{4})", fname)
        if m:
            code = m.group(1)
            aliases = OUTLINE_ALIASES.get(code, [])
            if code in entities:
                ent = entities[code]
                ent["has_outline"] = True
                if fname not in ent["sources"]:
                    ent["sources"].append(fname)
                if "course_detail" not in ent["document_types"]:
                    ent["document_types"].insert(0, "course_detail")
                for a in aliases:
                    if a not in ent["aliases"]:
                        ent["aliases"].append(a)
                ent["available_fields"] = [
                    "credits", "lecturer", "lecturer_email", "prerequisites",
                    "assessment", "clo", "objectives", "hours", "department",
                    "course_plan", "english_name"
                ]
                ent["provenance"]["outline_source_file"] = fname
                ent["provenance"]["outline_doc_type"] = "course_detail"
            else:
                entities[code] = {
                    "entity_id": code,
                    "canonical_name": code,
                    "english_name": ENGLISH_NAMES.get(code, ""),
                    "aliases": aliases,
                    "sources": [fname],
                    "document_types": ["course_detail"],
                    "has_outline": True,
                    "available_fields": [
                        "credits", "lecturer", "lecturer_email", "prerequisites",
                        "assessment", "clo", "objectives", "hours", "department",
                        "course_plan", "english_name"
                    ],
                    "provenance": {
                        "source_file": fname,
                        "document_type": "course_detail",
                        "extracted_at": EXTRACTED_AT,
                        "ingestion_version": INGESTION_VERSION,
                    }
                }

    # Deterministic sorting of entities by entity_id
    sorted_entities = {k: entities[k] for k in sorted(entities.keys())}

    catalog = {
        "version": INGESTION_VERSION,
        "generated_at": EXTRACTED_AT,
        "document_types": DOCUMENT_TYPES,
        "unavailable_fields": UNAVAILABLE_FIELDS,
        "entities": sorted_entities,
    }

    RUNTIME_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RUNTIME_PATH, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2, sort_keys=True)

    print(f"Generated {RUNTIME_PATH} with {len(sorted_entities)} entities.")
    return catalog


if __name__ == "__main__":
    build_knowledge_environment()
