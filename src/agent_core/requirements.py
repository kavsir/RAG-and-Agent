"""
Requirement Builder for Goal-Driven Agent Core V1.
Enforces the fundamental architectural invariant:
NO DOMAIN ANSWER WITHOUT EVIDENCE REQUIREMENTS.
Constructs distinct EvidenceRequirement instances for each entity-field pair.
"""
from typing import List
from src.agent_core.schemas import GoalSpec, EvidenceRequirement, EvidenceStatus
from src.agent_core.environment_catalog import get_knowledge_environment_catalog


class RequirementBuilder:
    """Xây dựng danh sách yêu cầu bằng chứng (EvidenceRequirement) từ GoalSpec."""

    def __init__(self):
        self.env_catalog = get_knowledge_environment_catalog()

    def build_requirements(self, goal_spec: GoalSpec) -> List[EvidenceRequirement]:
        requirements: List[EvidenceRequirement] = []

        # 1. Trường hợp có thực thể cụ thể (Course-scoped requirements)
        if goal_spec.entities:
            for entity in goal_spec.entities:
                for field in goal_spec.requested_fields:
                    doc_types = self.env_catalog.get_source_doc_types(field)
                    is_unavail = self.env_catalog.is_field_unavailable(field)

                    status = EvidenceStatus.NOT_AVAILABLE if is_unavail else EvidenceStatus.PENDING
                    req = EvidenceRequirement(
                        entity=entity,
                        field=field,
                        accepted_document_types=doc_types or ["course_outline"],
                        filters={"course_code": entity},
                        status=status,
                        attempt_count=0,
                    )
                    requirements.append(req)

        # 2. Trường hợp quy chế chung toàn trường hoặc không có thực thể cụ thể
        else:
            for field in goal_spec.requested_fields:
                doc_types = self.env_catalog.get_source_doc_types(field)
                is_unavail = self.env_catalog.is_field_unavailable(field)

                status = EvidenceStatus.NOT_AVAILABLE if is_unavail else EvidenceStatus.PENDING
                req = EvidenceRequirement(
                    entity="DNTU",
                    field=field,
                    accepted_document_types=doc_types or ["regulation"],
                    filters={"document_type": "regulation"},
                    status=status,
                    attempt_count=0,
                )
                requirements.append(req)

        return requirements


# Singleton Instance
_req_builder_instance: RequirementBuilder = None


def get_requirement_builder() -> RequirementBuilder:
    global _req_builder_instance
    if _req_builder_instance is None:
        _req_builder_instance = RequirementBuilder()
    return _req_builder_instance
