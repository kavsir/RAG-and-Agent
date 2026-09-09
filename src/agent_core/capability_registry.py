"""
Knowledge Capability Registry: Đăng ký và phân giải năng lực dữ liệu học vụ (Round A1).
Phân giải chính xác năng lực lưu trữ và truy vấn tương ứng với từng đối tượng học vụ có kiểu:
- STRUCTURED_CURRICULUM: CTĐT, kế hoạch học kỳ, số tín chỉ, vị trí môn học (SQLite)
- STRUCTURED_COURSE_CATALOG: Danh mục môn học, mã môn, số tín chỉ cơ bản
- COURSE_DETAIL_RAG: Đề cương chi tiết, CLO, giảng viên, hình thức đánh giá (Chroma + BM25)
- REGULATION_RAG: Quy chế đào tạo, điều kiện tốt nghiệp, bảo lưu, học lại (Chroma + BM25)

Đảm bảo WRONG_DATA_CAPABILITY_SELECTION = 0.
"""
import logging
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

from src.agent_core.schemas import EntityType, AcademicOperation

logger = logging.getLogger(__name__)


class KnowledgeCapability(BaseModel):
    """Mô tả một năng lực truy xuất tri thức học vụ."""
    name: str
    description: str
    supported_entity_types: List[EntityType]
    supported_operations: List[str]
    storage_type: str  # "sqlite", "vector_bm25", "in_memory"
    accepted_document_types: List[str]
    p95_latency_ms: float = 100.0
    requires_llm: bool = False


# Danh mục các trường thuộc về đề cương chi tiết môn học (COURSE_DETAIL_RAG)
COURSE_DETAIL_FIELDS = {
    "lecturer", "giang_vien", "email", "lecturer_email", "clo", "chuan_dau_ra",
    "assessment", "danh_gia", "schedule", "ke_hoach_giang_day", "syllabus",
    "de_cuong", "noi_dung", "tai_lieu", "muc_tieu", "noi_dung_chi_tiet"
}

# Danh mục các trường tra cứu danh mục hoặc CTĐT
CATALOG_CURRICULUM_FIELDS = {
    "prerequisites", "tien_quyet", "song_hanh", "hoc_truoc", "credits", "tin_chi",
    "semester", "hoc_ky", "course_type", "loai_mon"
}


class KnowledgeCapabilityRegistry:
    """
    Bộ quản lý đăng ký và phân giải năng lực dữ liệu học vụ.
    """

    CAPABILITY_STRUCTURED_CURRICULUM = "STRUCTURED_CURRICULUM"
    CAPABILITY_STRUCTURED_COURSE_CATALOG = "STRUCTURED_COURSE_CATALOG"
    CAPABILITY_COURSE_DETAIL_RAG = "COURSE_DETAIL_RAG"
    CAPABILITY_REGULATION_RAG = "REGULATION_RAG"

    def __init__(self):
        self._capabilities: Dict[str, KnowledgeCapability] = {}
        self._register_default_capabilities()

    def _register_default_capabilities(self) -> None:
        self._capabilities[self.CAPABILITY_STRUCTURED_CURRICULUM] = KnowledgeCapability(
            name=self.CAPABILITY_STRUCTURED_CURRICULUM,
            description="Truy vấn dữ liệu quan hệ bảng biểu CTĐT, danh sách môn theo kỳ, vị trí kỳ của môn, tổng số tín chỉ",
            supported_entity_types=[EntityType.CURRICULUM, EntityType.COHORT, EntityType.MAJOR, EntityType.SEMESTER, EntityType.COURSE],
            supported_operations=[
                AcademicOperation.LIST_COURSES.value,
                AcademicOperation.GET_SEMESTER_COURSES.value,
                AcademicOperation.FIND_COURSE_SEMESTER.value,
                AcademicOperation.GET_TOTAL_CREDITS.value,
            ],
            storage_type="sqlite",
            accepted_document_types=["curriculum"],
            p95_latency_ms=10.0,
            requires_llm=False,
        )

        self._capabilities[self.CAPABILITY_STRUCTURED_COURSE_CATALOG] = KnowledgeCapability(
            name=self.CAPABILITY_STRUCTURED_COURSE_CATALOG,
            description="Tra cứu danh mục môn học, mã môn chuẩn hóa, số tín chỉ cơ bản",
            supported_entity_types=[EntityType.COURSE],
            supported_operations=[AcademicOperation.LOOKUP_FIELD.value],
            storage_type="in_memory",
            accepted_document_types=["catalog"],
            p95_latency_ms=5.0,
            requires_llm=False,
        )

        self._capabilities[self.CAPABILITY_COURSE_DETAIL_RAG] = KnowledgeCapability(
            name=self.CAPABILITY_COURSE_DETAIL_RAG,
            description="Tìm kiếm ngữ nghĩa đề cương môn học (CLO, giảng viên, đánh giá, kế hoạch chi tiết)",
            supported_entity_types=[EntityType.COURSE],
            supported_operations=[AcademicOperation.LOOKUP_FIELD.value, AcademicOperation.COMPARE_COURSES.value],
            storage_type="vector_bm25",
            accepted_document_types=["course_detail", "syllabus"],
            p95_latency_ms=800.0,
            requires_llm=True,
        )

        self._capabilities[self.CAPABILITY_REGULATION_RAG] = KnowledgeCapability(
            name=self.CAPABILITY_REGULATION_RAG,
            description="Tìm kiếm quy chế đào tạo, điều kiện tốt nghiệp, khen thưởng, kỷ luật",
            supported_entity_types=[EntityType.REGULATION],
            supported_operations=[AcademicOperation.REGULATION_LOOKUP.value],
            storage_type="vector_bm25",
            accepted_document_types=["regulation"],
            p95_latency_ms=800.0,
            requires_llm=True,
        )

    def resolve_capability(
        self,
        subject_type: EntityType,
        operation: Optional[str] = None,
        field: Optional[str] = None,
    ) -> str:
        """
        Phân giải năng lực dữ liệu học vụ phù hợp nhất dựa trên loại thực thể, phép toán và trường thông tin.
        Bảo đảm quy tắc:
        1. CURRICULUM, COHORT, MAJOR, SEMESTER -> STRUCTURED_CURRICULUM
        2. COURSE với operation FIND_COURSE_SEMESTER hoặc GET_SEMESTER_COURSES -> STRUCTURED_CURRICULUM
        3. REGULATION -> REGULATION_RAG
        4. COURSE với field liên quan đến đề cương chi tiết (CLO, lecturer, assessment) -> COURSE_DETAIL_RAG
        5. COURSE với field liên quan đến catalog/tín chỉ/tiên quyết -> STRUCTURED_COURSE_CATALOG
        """
        norm_op = operation.value if isinstance(operation, AcademicOperation) else (operation or "")

        # 1. Thực thể CTĐT / Khóa / Học kỳ / Ngành học
        if subject_type in (EntityType.CURRICULUM, EntityType.COHORT, EntityType.MAJOR, EntityType.SEMESTER):
            return self.CAPABILITY_STRUCTURED_CURRICULUM

        # 2. Phép toán tìm vị trí học kỳ của môn học
        if norm_op == AcademicOperation.FIND_COURSE_SEMESTER.value or norm_op == "FIND_COURSE_SEMESTER":
            return self.CAPABILITY_STRUCTURED_CURRICULUM

        if norm_op in (AcademicOperation.GET_SEMESTER_COURSES.value, AcademicOperation.GET_TOTAL_CREDITS.value):
            return self.CAPABILITY_STRUCTURED_CURRICULUM

        # 3. Quy chế học vụ
        if subject_type == EntityType.REGULATION or norm_op == AcademicOperation.REGULATION_LOOKUP.value:
            return self.CAPABILITY_REGULATION_RAG

        # 4. Môn học và trường thông tin
        if subject_type == EntityType.COURSE:
            field_lower = (field or "").strip().lower()
            if field_lower in COURSE_DETAIL_FIELDS:
                return self.CAPABILITY_COURSE_DETAIL_RAG
            if field_lower in ("semester", "hoc_ky", "ky_hoc"):
                return self.CAPABILITY_STRUCTURED_CURRICULUM
            if field_lower in CATALOG_CURRICULUM_FIELDS:
                return self.CAPABILITY_STRUCTURED_COURSE_CATALOG
            return self.CAPABILITY_COURSE_DETAIL_RAG

        # Fallback an toàn
        return self.CAPABILITY_STRUCTURED_CURRICULUM if subject_type != EntityType.REGULATION else self.CAPABILITY_REGULATION_RAG

    def get_capability(self, name: str) -> Optional[KnowledgeCapability]:
        return self._capabilities.get(name)


# Singleton
_registry_instance: Optional[KnowledgeCapabilityRegistry] = None


def get_capability_registry() -> KnowledgeCapabilityRegistry:
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = KnowledgeCapabilityRegistry()
    return _registry_instance
