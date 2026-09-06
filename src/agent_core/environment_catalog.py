"""
Knowledge Environment Catalog for Goal-Driven Agent Core V1.
Defines the authoritative scope of what is verifiable vs. unavailable:
- Real document types (course_outline, curriculum, regulation)
- Verifiable fields mapping
- Explicit unavailable fields catalog with standard proposal templates
Strictly enforces: USER GOAL > AGENT ASSUMPTION (never guess unavailable data).
"""
from typing import Dict, Any, List, Optional


class KnowledgeEnvironmentCatalog:
    """Catalog quản lý không gian tri thức thực tế của hệ thống học vụ."""

    DOCUMENT_TYPES = {
        "course_outline": {
            "title": "Đề cương chi tiết học phần",
            "authority_level": "PRIMARY_COURSE_AUTHORITY",
            "directory": "data_raw/course_detail",
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
            "verifiable_fields": [
                "graduation_requirements", "academic_warning", "training_rules",
                "grading_scale", "attendance_rules", "scholarship_rules",
                "retake_rules", "regulation"
            ]
        }
    }

    # Bản đồ ánh xạ từng trường thông tin sang loại tài liệu lưu trữ chính thức
    FIELD_TO_DOC_TYPES = {
        "credits": ["course_outline", "curriculum"],
        "course_name": ["course_outline", "curriculum"],
        "lecturer": ["course_outline"],
        "lecturer_email": ["course_outline"],
        "prerequisites": ["course_outline"],
        "assessment": ["course_outline"],
        "course_plan": ["course_outline"],
        "course_objective": ["course_outline"],
        "objectives": ["course_outline"],
        "clo": ["course_outline"],
        "hours": ["course_outline"],
        "department": ["course_outline"],
        "english_name": ["course_outline"],
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

    # Các trường hoàn toàn KHÔNG CÓ trong cơ sở dữ liệu học vụ
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

    def get_source_doc_types(self, field: str) -> List[str]:
        """Trả về danh sách loại tài liệu lưu trữ trường thông tin."""
        return self.FIELD_TO_DOC_TYPES.get(field, [])

    def is_field_unavailable(self, field: str) -> bool:
        """Kiểm tra trường thông tin có thuộc danh mục không công bố chính thức hay không."""
        return field in self.UNAVAILABLE_FIELDS

    def get_unavailable_field_info(self, field: str) -> Optional[Dict[str, Any]]:
        """Lấy thông tin giải thích vì sao trường không tồn tại."""
        return self.UNAVAILABLE_FIELDS.get(field)

    def propose_alternative_for_field(self, field: str) -> Dict[str, Any]:
        """Tạo đề xuất giải pháp thay thế có cấu trúc cho trường không có sẵn."""
        info = self.UNAVAILABLE_FIELDS.get(field)
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
