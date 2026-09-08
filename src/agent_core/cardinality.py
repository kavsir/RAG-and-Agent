"""
Field Cardinality Policy for Goal-Driven Agent Core V1.1.
Defines explicit cardinality categories for academic and regulation fields:
- SINGLE_VALUE: One authoritative fact expected (credits, department, semester, english_name).
- MULTI_VALUE: Multiple distinct values expected (lecturer, lecturer_email, clo, prerequisites).
- MULTI_COMPONENT: Multiple composite components expected (assessment, hours).
- MULTI_CLAUSE: Multiple regulatory clauses expected (graduation_requirements, academic_warning, attendance_rules, grading_scale, training_rules, regulation).
"""
from enum import Enum
from typing import Dict


class FieldCardinality(str, Enum):
    SINGLE_VALUE = "SINGLE_VALUE"
    MULTI_VALUE = "MULTI_VALUE"
    MULTI_COMPONENT = "MULTI_COMPONENT"
    MULTI_CLAUSE = "MULTI_CLAUSE"


FIELD_CARDINALITY_POLICY: Dict[str, FieldCardinality] = {
    # SINGLE_VALUE
    "credits": FieldCardinality.SINGLE_VALUE,
    "department": FieldCardinality.SINGLE_VALUE,
    "english_name": FieldCardinality.SINGLE_VALUE,
    "semester": FieldCardinality.SINGLE_VALUE,
    "course_plan": FieldCardinality.SINGLE_VALUE,
    "course_name": FieldCardinality.SINGLE_VALUE,

    # MULTI_VALUE
    "lecturer": FieldCardinality.MULTI_VALUE,
    "lecturer_email": FieldCardinality.MULTI_VALUE,
    "clo": FieldCardinality.MULTI_VALUE,
    "objectives": FieldCardinality.MULTI_VALUE,
    "prerequisites": FieldCardinality.MULTI_VALUE,

    # MULTI_COMPONENT
    "assessment": FieldCardinality.MULTI_COMPONENT,
    "hours": FieldCardinality.MULTI_COMPONENT,

    # MULTI_CLAUSE
    "graduation_requirements": FieldCardinality.MULTI_CLAUSE,
    "academic_warning": FieldCardinality.MULTI_CLAUSE,
    "attendance_rules": FieldCardinality.MULTI_CLAUSE,
    "grading_scale": FieldCardinality.MULTI_CLAUSE,
    "training_rules": FieldCardinality.MULTI_CLAUSE,
    "regulation": FieldCardinality.MULTI_CLAUSE,
}


def get_field_cardinality(field: str) -> FieldCardinality:
    """Trả về chính sách lực lượng cho trường dữ liệu chỉ định."""
    return FIELD_CARDINALITY_POLICY.get(field, FieldCardinality.SINGLE_VALUE)
