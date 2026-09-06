"""
Knowledge Environment Catalog for Goal-Driven Agent Core V1.1.
Data-derived from runtime/knowledge_environment.json.
Defines authoritative scope of verifiable vs. unavailable fields:
- Real document types (course_detail, curriculum, regulation)
- Verifiable fields mapping
- Explicit unavailable fields catalog with standard proposal templates
Strictly enforces: USER GOAL > AGENT ASSUMPTION (never guess unavailable data).
"""
import json
from pathlib import Path
from typing import Dict, Any, List, Optional

RUNTIME_PATH = Path("runtime/knowledge_environment.json")


class KnowledgeEnvironmentCatalog:
    """Catalog quản lý không gian tri thức thực tế được sinh từ dữ liệu thật."""

    def __init__(self, json_path: Optional[Path] = None):
        self.json_path = json_path or RUNTIME_PATH
        self.document_types: Dict[str, Dict[str, Any]] = {}
        self.unavailable_fields: Dict[str, Dict[str, Any]] = {}
        self._load_from_json()

    def _load_from_json(self):
        """Nạp cấu hình môi trường tri thức từ JSON sinh tất định."""
        if not self.json_path.exists():
            from src.agent_core.build_knowledge_env import build_knowledge_environment
            data = build_knowledge_environment()
        else:
            try:
                with open(self.json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                from src.agent_core.build_knowledge_env import build_knowledge_environment
                data = build_knowledge_environment()

        self.document_types = data.get("document_types", {})
        self.unavailable_fields = data.get("unavailable_fields", {})

    @property
    def DOCUMENT_TYPES(self) -> Dict[str, Dict[str, Any]]:
        return self.document_types

    @property
    def UNAVAILABLE_FIELDS(self) -> Dict[str, Dict[str, Any]]:
        return self.unavailable_fields

    FIELD_TO_DOC_TYPES = {
        "credits": ["course_detail", "curriculum"],
        "course_name": ["course_detail", "curriculum"],
        "lecturer": ["course_detail"],
        "lecturer_email": ["course_detail"],
        "prerequisites": ["course_detail", "curriculum"],
        "assessment": ["course_detail"],
        "course_plan": ["course_detail"],
        "course_objective": ["course_detail"],
        "objectives": ["course_detail"],
        "clo": ["course_detail"],
        "hours": ["course_detail"],
        "department": ["course_detail"],
        "english_name": ["course_detail"],
        "semester": ["curriculum"],
        "course_placement": ["curriculum"],
        "curriculum_structure": ["curriculum"],
        "cohort_plan": ["curriculum"],
        "total_credits_program": ["curriculum"],
        "course_type": ["curriculum"],
        "graduation_requirements": ["regulation"],
        "academic_warning": ["regulation"],
        "training_rules": ["regulation"],
        "grading_scale": ["regulation"],
        "attendance_rules": ["regulation"],
        "scholarship_rules": ["regulation"],
        "retake_rules": ["regulation"],
        "regulation": ["regulation"],
    }

    def get_source_doc_types(self, field: str) -> List[str]:
        """Trả về danh sách loại tài liệu lưu trữ trường thông tin."""
        return self.FIELD_TO_DOC_TYPES.get(field, [])

    def is_field_unavailable(self, field: str) -> bool:
        """Kiểm tra trường thông tin có thuộc danh mục không công bố chính thức hay không."""
        return field in self.unavailable_fields

    def get_unavailable_field_info(self, field: str) -> Optional[Dict[str, Any]]:
        """Lấy thông tin giải thích vì sao trường không tồn tại."""
        return self.unavailable_fields.get(field)

    def propose_alternative_for_field(self, field: str) -> Dict[str, Any]:
        """Tạo đề xuất giải pháp thay thế có cấu trúc cho trường không có sẵn."""
        info = self.unavailable_fields.get(field)
        if not info:
            return {
                "field": field,
                "has_proposal": False,
                "proposal_text": "Trường dữ liệu này hiện không có trong hệ thống.",
                "alternative_fields": [],
            }

        return {
            "field": field,
            "has_proposal": True,
            "reason": info["reason"],
            "alternative_fields": info["alternative_fields"],
            "proposal_text": info["proposal_text"],
        }


# Global Singleton
_env_catalog_instance: Optional[KnowledgeEnvironmentCatalog] = None


def get_knowledge_environment_catalog() -> KnowledgeEnvironmentCatalog:
    global _env_catalog_instance
    if _env_catalog_instance is None:
        _env_catalog_instance = KnowledgeEnvironmentCatalog()
    return _env_catalog_instance
