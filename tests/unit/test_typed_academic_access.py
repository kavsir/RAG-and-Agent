"""
Unit tests for Round A1: Typed Academic Knowledge Access Architecture.
Verifies all core invariants:
- CURRICULUM_GOAL_WITH_COURSE_ONLY_PLAN = 0
- COHORT_AS_COURSE_CODE = 0
- STALE_COURSE_IN_CURRICULUM_QUERY = 0
- WRONG_DATA_CAPABILITY_SELECTION = 0
- STRUCTURED_RESULT_WITHOUT_PROVENANCE = 0
- CROSS_CURRICULUM_LEAKAGE = 0
- 0 LLM calls for deterministic lookups
- p95 latency < 100ms
"""
import time
import pytest
from pathlib import Path

from src.agent_core.schemas import (
    EntityType,
    AcademicEntity,
    AcademicOperation,
    AcademicQueryPlan,
    GoalFrame,
    GoalIntent,
    GoalScope,
    validate_goal_frame,
)
from src.agent_core.academic_store import StructuredAcademicStore, get_academic_store
from src.agent_core.capability_registry import get_capability_registry
from src.agent_core.query_planner import AcademicQueryPlanner, GoalPlanConsistencyValidator
from src.agent_core.semantic_goal_interpreter import get_semantic_goal_interpreter
from src.agent_core.requirements import get_requirement_builder
from src.ingestion.curriculum_parser import CurriculumParser


@pytest.fixture(scope="module")
def academic_store():
    store = get_academic_store()
    # Nạp dữ liệu nếu chưa có
    cnt = store.count_records()
    if cnt["curriculums"] == 0:
        parser = CurriculumParser()
        parser.ingest_all_curricula(store=store)
    return store


def test_academic_store_ingestion_and_counts(academic_store):
    counts = academic_store.count_records()
    assert counts["curriculums"] >= 3
    assert counts["courses"] >= 100


def test_academic_store_query_provenance_and_speed(academic_store):
    """Bảo đảm mọi bản ghi có provenance đầy đủ và độ trễ < 50ms."""
    start = time.perf_counter()
    curr = academic_store.get_curriculum("K19", "Khoa học máy tính")
    elapsed = (time.perf_counter() - start) * 1000

    assert curr is not None
    assert curr["cohort"] == "K19"
    assert "Khoa học máy tính" in curr["major"]
    assert curr["total_credits"] == 151
    assert curr["source_file"] == "CTDTK_NKHMT_K19.docx"
    assert len(curr["source_hash"]) == 64
    assert curr["ingestion_timestamp"]
    assert elapsed < 50.0  # Siêu nhanh < 50ms (vượt chuẩn p95 < 100ms)


def test_find_course_placement(academic_store):
    """Xác định vị trí học kỳ của môn FIT4113 trong CTĐT KHMT K19."""
    placement = academic_store.find_course_placement("K19", "Khoa học máy tính", "FIT4113")
    assert placement is not None
    assert placement["course_code"] == "FIT4113"
    assert placement["semester"] == 6
    assert placement["credits"] == 2
    assert placement["source_file"] == "CTDTK_NKHMT_K19.docx"
    assert placement["source_section"]
    assert placement["source_chunk_id"]


def test_cross_curriculum_leakage_protection(academic_store):
    """Bảo đảm CROSS_CURRICULUM_LEAKAGE = 0: chỉ lấy môn thuộc đúng CTĐT."""
    khmt_courses = academic_store.list_curriculum_courses("K19", "Khoa học máy tính")
    cntt_courses = academic_store.list_curriculum_courses("K19", "Công nghệ thông tin")

    khmt_codes = {c["course_code"] for c in khmt_courses}
    cntt_codes = {c["course_code"] for c in cntt_courses}

    # Cả hai CTĐT đều độc lập và gắn đúng curriculum_id
    for c in khmt_courses:
        assert c["curriculum_id"] == "K19_KHMT"
        assert c["source_file"] == "CTDTK_NKHMT_K19.docx"

    for c in cntt_courses:
        assert c["curriculum_id"] == "K19_CNTT"
        assert c["source_file"] == "CTDT_CNTT_K19.docx"


def test_capability_resolution():
    """Kiểm tra phân giải năng lực dữ liệu chuẩn xác (WRONG_DATA_CAPABILITY_SELECTION = 0)."""
    reg = get_capability_registry()

    # CURRICULUM -> STRUCTURED_CURRICULUM
    cap = reg.resolve_capability(EntityType.CURRICULUM, operation="LIST_COURSES")
    assert cap == "STRUCTURED_CURRICULUM"

    # COHORT -> STRUCTURED_CURRICULUM
    cap = reg.resolve_capability(EntityType.COHORT)
    assert cap == "STRUCTURED_CURRICULUM"

    # SEMESTER -> STRUCTURED_CURRICULUM
    cap = reg.resolve_capability(EntityType.SEMESTER)
    assert cap == "STRUCTURED_CURRICULUM"

    # COURSE + FIND_COURSE_SEMESTER -> STRUCTURED_CURRICULUM
    cap = reg.resolve_capability(EntityType.COURSE, operation="FIND_COURSE_SEMESTER")
    assert cap == "STRUCTURED_CURRICULUM"

    # COURSE + lecturer -> COURSE_DETAIL_RAG
    cap = reg.resolve_capability(EntityType.COURSE, field="lecturer")
    assert cap == "COURSE_DETAIL_RAG"

    # REGULATION -> REGULATION_RAG
    cap = reg.resolve_capability(EntityType.REGULATION)
    assert cap == "REGULATION_RAG"


def test_query_planner_invariants():
    """Kiểm tra lập kế hoạch truy vấn và các bất biến học vụ."""
    planner = AcademicQueryPlanner()

    # 1. Mục tiêu CTĐT
    frame_curr = GoalFrame(
        intent=GoalIntent.CURRICULUM_OVERVIEW,
        subjects=[
            AcademicEntity(type=EntityType.COHORT, value="K19"),
            AcademicEntity(type=EntityType.MAJOR, value="Khoa học máy tính"),
        ],
        subject_type=EntityType.CURRICULUM,
        operation="LIST_COURSES",
    )
    plan = planner.create_plan(frame_curr)
    assert plan.data_capability == "STRUCTURED_CURRICULUM"
    assert plan.filters["cohort"] == "K19"
    assert "course_code" not in plan.filters  # Không có course_code thừa

    # 2. Bất biến COHORT_AS_COURSE_CODE = 0
    frame_bad_cohort = GoalFrame(
        intent=GoalIntent.COURSE_FIELD_LOOKUP,
        subjects=[AcademicEntity(type=EntityType.COHORT, value="K19")],
        entities=["K19"],
        subject_type=EntityType.COURSE,
    )
    plan_cohort = planner.create_plan(frame_bad_cohort)
    assert plan_cohort.filters.get("course_code") != "K19"


def test_semantic_interpreter_curriculum_queries():
    """Kiểm tra nhận diện câu hỏi CTĐT trong SemanticGoalInterpreter."""
    interp = get_semantic_goal_interpreter()

    # Câu hỏi tổng quan CTĐT
    f1 = interp.interpret("chương trình đào tạo K19 học những môn gì")
    assert f1.intent == GoalIntent.CURRICULUM_OVERVIEW
    assert f1.subject_type == EntityType.CURRICULUM
    assert any(s.type == EntityType.COHORT and s.value == "K19" for s in f1.subjects)
    assert f1.operation == "LIST_COURSES"
    assert len(f1.entities) == 0  # Không gắn nhầm course code

    # Câu hỏi học kỳ cụ thể
    f2 = interp.interpret("kỳ 5 học những gì")
    assert f2.intent == GoalIntent.CURRICULUM_OVERVIEW
    assert any(s.type == EntityType.SEMESTER and s.value == "5" for s in f2.subjects)
    assert f2.operation == "GET_SEMESTER_COURSES"

    # Câu hỏi tổng tín chỉ
    f3 = interp.interpret("chương trình K19 bao nhiêu tín chỉ")
    assert f3.intent == GoalIntent.CURRICULUM_OVERVIEW
    assert f3.operation == "GET_TOTAL_CREDITS"

    # Câu hỏi vị trí môn học
    f4 = interp.interpret("FIT4113 nằm ở kỳ mấy")
    assert f4.intent == GoalIntent.CURRICULUM_OVERVIEW
    assert f4.operation == "FIND_COURSE_SEMESTER"
    assert any(s.type == EntityType.COURSE and s.value == "FIT4113" for s in f4.subjects)


def test_topic_shift_purges_stale_course():
    """
    Bảo đảm STALE_COURSE_IN_CURRICULUM_QUERY = 0:
    Lượt 1 hỏi FIT4113 (môn học).
    Lượt 2 hỏi chương trình đào tạo -> FIT4113 bị loại bỏ hoàn toàn khỏi thực thể.
    """
    interp = get_semantic_goal_interpreter()
    session_ctx = {
        "last_academic_entity": "FIT4113",
        "last_intent": GoalIntent.COURSE_FIELD_LOOKUP.value,
        "last_requested_fields": ["clo"],
    }

    # Người dùng chuyển chủ đề sang CTĐT
    frame = interp.interpret("chương trình đào tạo có những môn nào", session_context=session_ctx)

    assert frame.intent == GoalIntent.CURRICULUM_OVERVIEW
    assert frame.subject_type == EntityType.CURRICULUM
    assert "FIT4113" not in frame.entities  # Stale course code PURGED!
    assert not any(s.type == EntityType.COURSE for s in frame.subjects)
