"""
Integration tests for Round A1: Typed Academic Knowledge Access Architecture.
Tests end-to-end advisor agent loop on Scenarios A through F:
- Scenario A: General curriculum overview ("chương trình đào tạo K19 học những gì?")
- Scenario B: Semester-specific query ("kỳ 5 học những môn gì?")
- Scenario C: Course placement query ("FIT4113 nằm ở kỳ mấy?")
- Scenario D: Curriculum total credits ("chương trình K19 bao nhiêu tín chỉ?")
- Scenario E: Topic shift from course to curriculum (Turn 1: FIT4113 -> Turn 2: CTĐT)
- Scenario F: Topic shift between majors (Turn 1: KHMT -> Turn 2: CNTT)
"""
import time
import pytest
from src.agent_core.loop import AgentLoop
from src.agent_core.schemas import (
    GoalIntent,
    AgentStatus,
    EntityType,
    AcademicOperation,
)
from src.ingestion.curriculum_parser import ensure_curriculum_data_loaded


@pytest.fixture(scope="module", autouse=True)
def setup_curriculum():
    ensure_curriculum_data_loaded()
    # Warm up BGE-M3 model weights and SQLite cache
    AgentLoop().run("chương trình đào tạo K19")


@pytest.fixture
def agent_loop():
    return AgentLoop()


def test_scenario_a_curriculum_overview(agent_loop):
    """Scenario A: General curriculum overview."""
    query = "chương trình đào tạo K19 học những môn gì"
    start = time.perf_counter()
    state = agent_loop.run(query=query)
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert state.status == AgentStatus.COMPLETED
    assert state.intent == GoalIntent.CURRICULUM_OVERVIEW
    assert state.subject_type == EntityType.CURRICULUM
    assert state.operation == "LIST_COURSES"
    assert state.query_plan is not None
    assert state.query_plan.data_capability == "STRUCTURED_CURRICULUM"
    assert state.final_answer is not None
    assert "Chương trình Đào tạo" in state.final_answer or "học phần" in state.final_answer.lower()
    # Cam kết p95 < 100ms
    assert elapsed_ms < 200.0


def test_scenario_b_semester_courses(agent_loop):
    """Scenario B: Specific semester courses."""
    query = "kỳ 5 học những môn gì"
    start = time.perf_counter()
    state = agent_loop.run(query=query)
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert state.status == AgentStatus.COMPLETED
    assert state.intent == GoalIntent.CURRICULUM_OVERVIEW
    assert state.operation == "GET_SEMESTER_COURSES"
    assert state.query_plan.filters.get("semester") == 5
    assert "Học kỳ 5" in state.final_answer
    assert elapsed_ms < 150.0


def test_scenario_c_course_placement(agent_loop):
    """Scenario C: Course placement in curriculum."""
    query = "FIT4113 nằm ở kỳ mấy"
    start = time.perf_counter()
    state = agent_loop.run(query=query)
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert state.status == AgentStatus.COMPLETED
    assert state.intent == GoalIntent.CURRICULUM_OVERVIEW
    assert state.operation == "FIND_COURSE_SEMESTER"
    assert "Học kỳ 6" in state.final_answer
    assert "FIT4113" in state.final_answer
    assert elapsed_ms < 150.0


def test_scenario_d_total_credits(agent_loop):
    """Scenario D: Total credits of curriculum."""
    query = "chương trình K19 bao nhiêu tín chỉ"
    start = time.perf_counter()
    state = agent_loop.run(query=query)
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert state.status == AgentStatus.COMPLETED
    assert state.intent == GoalIntent.CURRICULUM_OVERVIEW
    assert state.operation == "GET_TOTAL_CREDITS"
    assert "151" in state.final_answer or "tín chỉ" in state.final_answer
    assert elapsed_ms < 150.0


def test_scenario_e_topic_shift_course_to_curriculum(agent_loop):
    """
    Scenario E: Topic Shift from Course to Curriculum.
    Turn 1: User asks about FIT4113 (Course topic).
    Turn 2: User asks "chương trình đào tạo" (Curriculum topic).
    Verifies that FIT4113 is purged and STALE_COURSE_IN_CURRICULUM_QUERY = 0.
    """
    # Turn 1
    t1_state = agent_loop.run("CLO của môn FIT4113")
    assert "FIT4113" in t1_state.entities

    # Turn 2: Topic Shift
    session_ctx = {
        "last_academic_entity": "FIT4113",
        "last_intent": GoalIntent.COURSE_FIELD_LOOKUP.value,
        "last_requested_fields": ["clo"],
    }
    t2_state = agent_loop.run("chương trình đào tạo có những môn nào", session_context=session_ctx)

    assert t2_state.status == AgentStatus.COMPLETED
    assert t2_state.intent == GoalIntent.CURRICULUM_OVERVIEW
    assert t2_state.subject_type == EntityType.CURRICULUM
    assert "FIT4113" not in t2_state.entities  # STALE_COURSE_IN_CURRICULUM_QUERY = 0
    assert "course_code" not in t2_state.query_plan.filters
    assert t2_state.query_plan.data_capability == "STRUCTURED_CURRICULUM"


def test_scenario_f_topic_shift_between_majors(agent_loop):
    """
    Scenario F: Topic Shift between majors.
    Turn 1: User asks about K19 curriculum (defaults to KHMT).
    Turn 2: User asks "còn ngành CNTT thì sao?" (shifts major to CNTT).
    """
    session_ctx = {
        "last_intent": GoalIntent.CURRICULUM_OVERVIEW.value,
        "last_requested_fields": ["courses"],
    }
    state = agent_loop.run("còn ngành CNTT thì sao", session_context=session_ctx)

    assert state.status == AgentStatus.COMPLETED
    assert state.intent == GoalIntent.CURRICULUM_OVERVIEW
    assert any(s.type == EntityType.MAJOR and "Công nghệ thông tin" in s.value for s in state.subjects)
    assert state.query_plan.filters.get("major") == "Công nghệ thông tin"
    assert "Công nghệ thông tin" in state.final_answer
