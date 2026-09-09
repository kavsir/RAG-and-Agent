"""
Requirement Builder for Goal-Driven Agent Core V1.1 (Round A1 Type-Aware).
Enforces the fundamental architectural invariant:
NO DOMAIN ANSWER WITHOUT EVIDENCE REQUIREMENTS.
Constructs distinct EvidenceRequirement instances for typed academic objects:
- CURRICULUM, COHORT, MAJOR, SEMESTER -> STRUCTURED_CURRICULUM
- COURSE -> STRUCTURED_COURSE_CATALOG / COURSE_DETAIL_RAG
- REGULATION -> REGULATION_RAG

Eliminates the invalid universal assumption: filters={"course_code": entity}.
"""
from typing import List, Optional
from src.agent_core.schemas import (
    GoalSpec,
    EvidenceRequirement,
    EvidenceStatus,
    GoalIntent,
    GoalScope,
    EntityType,
    AcademicOperation,
)
from src.agent_core.environment_catalog import get_knowledge_environment_catalog
from src.agent_core.capability_registry import get_capability_registry


class RequirementBuilder:
    """Xây dựng danh sách yêu cầu bằng chứng (EvidenceRequirement) có kiểu từ GoalSpec."""

    def __init__(self):
        self.env_catalog = get_knowledge_environment_catalog()
        self.capability_registry = get_capability_registry()

    def build_requirements(self, goal_spec: GoalSpec) -> List[EvidenceRequirement]:
        # 0. Nếu đã có AcademicQueryPlan sẵn với evidence_requirements đã tạo
        if goal_spec.query_plan and goal_spec.query_plan.evidence_requirements:
            typed_reqs = []
            for r in goal_spec.query_plan.evidence_requirements:
                if isinstance(r, EvidenceRequirement):
                    typed_reqs.append(r)
                elif isinstance(r, dict):
                    typed_reqs.append(EvidenceRequirement(**r))
            if typed_reqs:
                return typed_reqs

        requirements: List[EvidenceRequirement] = []
        fields = list(goal_spec.requested_fields)
        if not fields:
            if goal_spec.intent == GoalIntent.COURSE_FULL_DETAILS or goal_spec.scope == GoalScope.ALL_AVAILABLE:
                fields = ["credits", "lecturer", "prerequisites", "assessment", "clo", "hours", "course_plan", "department", "english_name"]
            elif goal_spec.intent == GoalIntent.COURSE_OVERVIEW or goal_spec.scope == GoalScope.SUMMARY:
                fields = ["credits", "lecturer", "prerequisites", "assessment", "clo", "hours", "course_plan"]

        subject_type = goal_spec.subject_type or (
            EntityType.CURRICULUM if goal_spec.intent == GoalIntent.CURRICULUM_OVERVIEW
            else (EntityType.REGULATION if goal_spec.intent == GoalIntent.REGULATION_LOOKUP else EntityType.COURSE)
        )

        # 1. CTĐT / Khóa / Ngành / Học kỳ (STRUCTURED_CURRICULUM)
        if subject_type in (EntityType.CURRICULUM, EntityType.COHORT, EntityType.MAJOR, EntityType.SEMESTER) or goal_spec.intent == GoalIntent.CURRICULUM_OVERVIEW:
            cohort_entity = next((s.value for s in goal_spec.subjects if s.type == EntityType.COHORT), "K19")
            major_entity = next((s.value for s in goal_spec.subjects if s.type == EntityType.MAJOR), "Khoa học máy tính")
            semester_entity = next((s.value for s in goal_spec.subjects if s.type == EntityType.SEMESTER), None)
            course_entity = next((s.value for s in goal_spec.subjects if s.type == EntityType.COURSE), None)

            filters = {"cohort": cohort_entity, "major": major_entity}
            if semester_entity:
                try:
                    import re
                    filters["semester"] = int(re.sub(r"\D", "", str(semester_entity)))
                except Exception:
                    pass
            if course_entity and goal_spec.operation == AcademicOperation.FIND_COURSE_SEMESTER.value:
                filters["course_code"] = course_entity.upper()

            req = EvidenceRequirement(
                entity=f"{cohort_entity}_{major_entity}",
                subject_type=subject_type,
                subject_id=f"{cohort_entity}_{major_entity}",
                field=goal_spec.operation or "LIST_COURSES",
                accepted_document_types=["curriculum"],
                data_capability="STRUCTURED_CURRICULUM",
                filters=filters,
                status=EvidenceStatus.PENDING,
                attempt_count=0,
            )
            requirements.append(req)
            return requirements

        # 2. Quy chế chung toàn trường (REGULATION_RAG)
        if subject_type == EntityType.REGULATION or goal_spec.intent == GoalIntent.REGULATION_LOOKUP:
            target_field = fields[0] if fields else "regulation"
            req = EvidenceRequirement(
                entity="DNTU",
                subject_type=EntityType.REGULATION,
                subject_id="DNTU_REGULATION",
                field=target_field,
                accepted_document_types=["regulation"],
                data_capability="REGULATION_RAG",
                filters={"document_type": "regulation"},
                status=EvidenceStatus.PENDING,
                attempt_count=0,
            )
            requirements.append(req)
            return requirements

        # 3. Trường hợp Môn học cụ thể (Course-scoped requirements)
        if goal_spec.entities:
            for entity in goal_spec.entities:
                # Đảm bảo bảo vệ COHORT_AS_COURSE_CODE
                e_val = str(entity).strip().upper()
                if e_val.startswith("K") and len(e_val) in (3, 4) and e_val[1:].isdigit():
                    continue

                for field in fields:
                    doc_types = self.env_catalog.get_source_doc_types(field)
                    is_unavail = self.env_catalog.is_field_unavailable(field)
                    cap = self.capability_registry.resolve_capability(EntityType.COURSE, field=field)

                    status = EvidenceStatus.NOT_AVAILABLE if is_unavail else EvidenceStatus.PENDING
                    req = EvidenceRequirement(
                        entity=entity,
                        subject_type=EntityType.COURSE,
                        subject_id=entity,
                        field=field,
                        accepted_document_types=doc_types or ["course_detail"],
                        data_capability=cap,
                        filters={"course_code": entity},
                        status=status,
                        attempt_count=0,
                    )
                    requirements.append(req)

        # 4. Fallback nếu không có thực thể cụ thể và không phải các loại trên
        if not requirements:
            for field in fields or ["general"]:
                doc_types = self.env_catalog.get_source_doc_types(field)
                is_unavail = self.env_catalog.is_field_unavailable(field)
                status = EvidenceStatus.NOT_AVAILABLE if is_unavail else EvidenceStatus.PENDING
                req = EvidenceRequirement(
                    entity="DNTU",
                    subject_type=EntityType.GENERAL_TOPIC,
                    subject_id="DNTU",
                    field=field,
                    accepted_document_types=doc_types or ["regulation"],
                    filters={"document_type": "regulation"},
                    status=status,
                    attempt_count=0,
                )
                requirements.append(req)

        return requirements


# Singleton Instance
_req_builder_instance: Optional[RequirementBuilder] = None


def get_requirement_builder() -> RequirementBuilder:
    global _req_builder_instance
    if _req_builder_instance is None:
        _req_builder_instance = RequirementBuilder()
    return _req_builder_instance
