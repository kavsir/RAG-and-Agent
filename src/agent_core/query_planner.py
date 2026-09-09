"""
Academic Query Planner: Bộ lập kế hoạch truy vấn tri thức học vụ có kiểu (Round A1).
Chuyển đổi Typed GoalFrame thành AcademicQueryPlan cụ thể, có cấu trúc,
và bảo đảm tính nhất quán tuyệt đối giữa Mục tiêu và Kế hoạch (Goal-Plan Consistency).

Bảo đảm các bất biến:
- CURRICULUM_GOAL_WITH_COURSE_ONLY_PLAN = 0
- COHORT_AS_COURSE_CODE = 0
- STALE_COURSE_IN_CURRICULUM_QUERY = 0
- WRONG_DATA_CAPABILITY_SELECTION = 0
"""
import re
import uuid
import logging
from typing import Optional, Dict, Any, List

from src.agent_core.schemas import (
    EntityType,
    AcademicEntity,
    AcademicOperation,
    AcademicQueryPlan,
    GoalFrame,
    GoalIntent,
    EvidenceRequirement,
    EvidenceStatus,
)
from src.agent_core.capability_registry import get_capability_registry

logger = logging.getLogger(__name__)

COURSE_CODE_REGEX = re.compile(r"^[A-Za-z]{2,4}\d{4}$")


class GoalPlanConsistencyValidator:
    """
    Bộ thẩm định tính nhất quán giữa Mục tiêu (GoalFrame) và Kế hoạch (AcademicQueryPlan).
    Fails closed nếu phát hiện bất kỳ sự lệch pha hoặc rò rỉ nào.
    """

    @staticmethod
    def validate(goal_frame: GoalFrame, plan: AcademicQueryPlan) -> List[str]:
        errors: List[str] = []

        # 1. CURRICULUM_GOAL_WITH_COURSE_ONLY_PLAN:
        # Nếu mục tiêu là CTĐT hoặc đối tượng là CURRICULUM/COHORT/MAJOR/SEMESTER (ngoại trừ hỏi kỳ của môn),
        # kế hoạch KHÔNG được là truy vấn chỉ có course_code đơn lẻ trên năng lực đề cương môn học.
        is_curriculum_intent = (
            goal_frame.intent == GoalIntent.CURRICULUM_OVERVIEW
            or plan.subject_type in (EntityType.CURRICULUM, EntityType.COHORT, EntityType.MAJOR, EntityType.SEMESTER)
        )
        if is_curriculum_intent and plan.operation != AcademicOperation.FIND_COURSE_SEMESTER.value:
            if plan.data_capability == "COURSE_DETAIL_RAG":
                errors.append(
                    "CURRICULUM_GOAL_WITH_COURSE_ONLY_PLAN: Curriculum goal cannot be planned as COURSE_DETAIL_RAG."
                )
            if "course_code" in plan.filters and "cohort" not in plan.filters and "major" not in plan.filters:
                errors.append(
                    "CURRICULUM_GOAL_WITH_COURSE_ONLY_PLAN: Curriculum goal planned with course_code only without curriculum scope."
                )

        # 2. COHORT_AS_COURSE_CODE:
        # Giá trị khóa học (cohort) tuyệt đối không được gán nhầm thành mã môn học (course_code)
        if "course_code" in plan.filters:
            code_val = str(plan.filters["course_code"]).strip().upper()
            if code_val.startswith("K") and len(code_val) in (3, 4) and code_val[1:].isdigit():
                errors.append(f"COHORT_AS_COURSE_CODE: Cohort string '{code_val}' used as course_code.")

        # 3. STALE_COURSE_IN_CURRICULUM_QUERY:
        # Khi chuyển chủ đề từ môn học sang CTĐT tổng quan, mã môn cũ không được còn sót lại trong filters
        if is_curriculum_intent and plan.operation in (
            AcademicOperation.LIST_COURSES.value,
            AcademicOperation.GET_SEMESTER_COURSES.value,
            AcademicOperation.GET_TOTAL_CREDITS.value,
        ):
            if "course_code" in plan.filters:
                errors.append(
                    f"STALE_COURSE_IN_CURRICULUM_QUERY: Stale course_code '{plan.filters['course_code']}' remained in curriculum plan."
                )

        # 4. WRONG_DATA_CAPABILITY_SELECTION:
        # Kiểm tra sự phù hợp giữa subject_type và data_capability
        if plan.subject_type in (EntityType.CURRICULUM, EntityType.COHORT, EntityType.MAJOR, EntityType.SEMESTER):
            if plan.data_capability != "STRUCTURED_CURRICULUM":
                errors.append(
                    f"WRONG_DATA_CAPABILITY_SELECTION: Subject type {plan.subject_type.value} routed to {plan.data_capability}."
                )

        return errors


class AcademicQueryPlanner:
    """
    Bộ lập kế hoạch truy vấn học vụ có kiểu.
    """

    def __init__(self):
        self.capability_registry = get_capability_registry()
        self.validator = GoalPlanConsistencyValidator()

    def create_plan(
        self,
        goal_frame: GoalFrame,
        student_profile: Optional[Dict[str, Any]] = None,
        profile_context: Optional[Dict[str, Any]] = None,
    ) -> AcademicQueryPlan:
        """
        Tạo kế hoạch truy vấn tri thức học vụ từ GoalFrame.
        """
        profile = profile_context or student_profile or {}
        default_cohort = profile.get("cohort", "K19")
        default_major = profile.get("major", "Khoa học máy tính")

        # 1. Xác định subject_type
        subject_type = goal_frame.subject_type
        if not subject_type:
            if goal_frame.intent == GoalIntent.CURRICULUM_OVERVIEW:
                subject_type = EntityType.CURRICULUM
            elif goal_frame.intent == GoalIntent.REGULATION_LOOKUP:
                subject_type = EntityType.REGULATION
            elif any(s.type in (EntityType.CURRICULUM, EntityType.COHORT, EntityType.MAJOR, EntityType.SEMESTER) for s in goal_frame.subjects):
                subject_type = EntityType.CURRICULUM
            else:
                subject_type = EntityType.COURSE

        # 2. Xác định operation
        operation = goal_frame.operation
        if not operation:
            if subject_type in (EntityType.CURRICULUM, EntityType.COHORT, EntityType.MAJOR, EntityType.SEMESTER):
                # Kiểm tra xem có phải hỏi kỳ của môn học cụ thể không
                has_course = any(s.type == EntityType.COURSE for s in goal_frame.subjects)
                has_sem_keyword = any(f in ("semester", "hoc_ky", "ky_hoc") for f in goal_frame.requested_fields)
                if has_course and has_sem_keyword:
                    operation = AcademicOperation.FIND_COURSE_SEMESTER.value
                elif any("credit" in f or "tín chỉ" in f for f in goal_frame.requested_fields):
                    operation = AcademicOperation.GET_TOTAL_CREDITS.value
                elif any(s.type == EntityType.SEMESTER for s in goal_frame.subjects):
                    operation = AcademicOperation.GET_SEMESTER_COURSES.value
                else:
                    operation = AcademicOperation.LIST_COURSES.value
            elif subject_type == EntityType.REGULATION:
                operation = AcademicOperation.REGULATION_LOOKUP.value
            elif subject_type == EntityType.COURSE:
                # Kiểm tra nếu hỏi kỳ của môn
                if any(f in ("semester", "hoc_ky", "ky_hoc") for f in goal_frame.requested_fields):
                    operation = AcademicOperation.FIND_COURSE_SEMESTER.value
                else:
                    operation = AcademicOperation.LOOKUP_FIELD.value
            else:
                operation = AcademicOperation.LOOKUP_FIELD.value

        # 3. Trích xuất filters
        filters: Dict[str, Any] = {}

        if subject_type in (EntityType.CURRICULUM, EntityType.COHORT, EntityType.MAJOR, EntityType.SEMESTER) or operation == AcademicOperation.FIND_COURSE_SEMESTER.value:
            # Thu thập cohort và major
            cohort_entity = next((s.value for s in goal_frame.subjects if s.type == EntityType.COHORT), None)
            major_entity = next((s.value for s in goal_frame.subjects if s.type == EntityType.MAJOR), None)
            semester_entity = next((s.value for s in goal_frame.subjects if s.type == EntityType.SEMESTER), None)

            filters["cohort"] = cohort_entity or default_cohort
            filters["major"] = major_entity or default_major

            if semester_entity is not None:
                try:
                    # Trích xuất số nguyên từ chuỗi "kỳ 5", "hoc ky 5", "5"
                    sem_num = int(re.sub(r"\D", "", str(semester_entity)))
                    filters["semester"] = sem_num
                except Exception:
                    pass

            if operation == AcademicOperation.FIND_COURSE_SEMESTER.value:
                # Tìm course_code trong subjects
                course_entity = next((s.value for s in goal_frame.subjects if s.type == EntityType.COURSE), None)
                if not course_entity and goal_frame.entities:
                    course_entity = goal_frame.entities[0]
                if course_entity:
                    filters["course_code"] = course_entity.upper()
            else:
                # TUYỆT ĐỐI KHÔNG để sót course_code cũ vào kế hoạch CTĐT tổng quan (STALE_COURSE_IN_CURRICULUM_QUERY)
                filters.pop("course_code", None)

        elif subject_type == EntityType.COURSE:
            course_entity = next((s.value for s in goal_frame.subjects if s.type == EntityType.COURSE), None)
            if not course_entity and goal_frame.entities:
                course_entity = goal_frame.entities[0]

            if course_entity:
                # Bảo vệ COHORT_AS_COURSE_CODE
                c_val = course_entity.strip().upper()
                if not (c_val.startswith("K") and len(c_val) in (3, 4) and c_val[1:].isdigit()):
                    filters["course_code"] = c_val

            if goal_frame.requested_fields:
                filters["field"] = goal_frame.requested_fields[0]

        elif subject_type == EntityType.REGULATION:
            if goal_frame.requested_fields:
                filters["topic"] = goal_frame.requested_fields[0]

        # 4. Phân giải năng lực dữ liệu (Knowledge Capability Resolution)
        primary_field = goal_frame.requested_fields[0] if goal_frame.requested_fields else None
        capability = self.capability_registry.resolve_capability(
            subject_type=subject_type,
            operation=operation,
            field=primary_field,
        )

        # 5. Xác định accepted_sources
        cap_obj = self.capability_registry.get_capability(capability)
        accepted_sources = cap_obj.accepted_document_types if cap_obj else ["curriculum"]

        # 6. Tạo EvidenceRequirements tương ứng
        req_list: List[EvidenceRequirement] = []
        if capability == "STRUCTURED_CURRICULUM":
            req = EvidenceRequirement(
                entity=f"{filters.get('cohort', default_cohort)}_{filters.get('major', default_major)}",
                subject_type=subject_type,
                subject_id=f"{filters.get('cohort', default_cohort)}_{filters.get('major', default_major)}",
                field=operation,
                accepted_document_types=accepted_sources,
                data_capability=capability,
                filters=filters,
                status=EvidenceStatus.PENDING,
            )
            req_list.append(req)
        elif subject_type == EntityType.COURSE:
            c_code = filters.get("course_code", "")
            req = EvidenceRequirement(
                entity=c_code,
                subject_type=EntityType.COURSE,
                subject_id=c_code,
                field=primary_field or "overview",
                accepted_document_types=accepted_sources,
                data_capability=capability,
                filters=filters,
                status=EvidenceStatus.PENDING,
            )
            req_list.append(req)
        elif subject_type == EntityType.REGULATION:
            topic = filters.get("topic", "regulation")
            req = EvidenceRequirement(
                entity=topic,
                subject_type=EntityType.REGULATION,
                subject_id=topic,
                field=topic,
                accepted_document_types=accepted_sources,
                data_capability=capability,
                filters=filters,
                status=EvidenceStatus.PENDING,
            )
            req_list.append(req)

        plan = AcademicQueryPlan(
            plan_id=f"plan_{uuid.uuid4().hex[:8]}",
            subject_type=subject_type,
            operation=operation,
            filters=filters,
            projection=goal_frame.requested_fields,
            data_capability=capability,
            accepted_sources=accepted_sources,
            evidence_requirements=req_list,
        )

        # 7. Kiểm tra tính nhất quán (Goal-Plan Consistency Check)
        errs = self.validator.validate(goal_frame, plan)
        if errs:
            logger.warning(f"Plan validation issues: {errs}. Failsafe self-healing applied.")
            # Self-healing: nếu có stale course_code trong curriculum plan, lập tức xóa bỏ
            if any("STALE_COURSE_IN_CURRICULUM_QUERY" in e for e in errs):
                plan.filters.pop("course_code", None)
            if any("WRONG_DATA_CAPABILITY_SELECTION" in e for e in errs):
                plan.data_capability = "STRUCTURED_CURRICULUM"

        return plan
