"""
Unit tests for Goal Understanding V2 + Conversational Discourse State (Round P2).
Validates:
1. Broad academic intents: COURSE_OVERVIEW & COURSE_FULL_DETAILS (0 false MISSING_INTENT).
2. Referent resolution: "môn này", "môn đó", "nó", "môn vừa rồi" with & without session context.
3. Follow-up field inheritance: "giảng viên thì sao?", "CLO nữa" inherits last_academic_entity.
4. Entity switch with field inheritance: "còn FIT4113?" inherits last_requested_fields.
5. Concept vs Course Title disambiguation: "hệ thống nhúng là gì" vs "chi tiết hệ thống nhúng".
"""
import pytest
from src.agent_core.goal_analyzer import get_goal_analyzer
from src.agent_core.schemas import GoalIntent, GoalScope


@pytest.fixture
def analyzer():
    return get_goal_analyzer()


def test_course_overview_natural_queries(analyzer):
    """Test queries asking for general course info resolve to COURSE_OVERVIEW without missing intent."""
    queries = [
        ("chi tiết học phần hệ thống nhúng", "FIT4201"),
        ("cho tôi biết về FIT4113", "FIT4113"),
        ("giới thiệu môn mạng máy tính", "FIT4006"),
        ("thông tin học phần FIT4201", "FIT4201"),
        ("FIT4201 thế nào", "FIT4201"),
        ("môn FIT4113", "FIT4113"),
    ]
    for q, expected_code in queries:
        spec = analyzer.analyze(q)
        assert spec.goal_clarity == "CLEAR", f"Failed clarity for query: {q}"
        assert spec.missing_slot is None, f"Failed missing_slot for query: {q}"
        assert spec.intent == GoalIntent.COURSE_OVERVIEW, f"Failed intent for query: {q}"
        assert spec.scope == GoalScope.SUMMARY, f"Failed scope for query: {q}"
        assert expected_code in spec.entities, f"Expected {expected_code} in entities for query: {q}"
        assert "credits" in spec.requested_fields
        assert "lecturer" in spec.requested_fields
        assert "prerequisites" in spec.requested_fields


def test_course_full_details_queries(analyzer):
    """Test queries asking for all / full course info resolve to COURSE_FULL_DETAILS."""
    queries = [
        ("chi tiết tổng thể môn FIT4201", "FIT4201"),
        ("cho tôi biết tất cả thông tin môn FIT4113", "FIT4113"),
        ("toàn bộ thông tin học phần hệ thống nhúng", "FIT4201"),
        ("tất cả về FIT4201", "FIT4201"),
    ]
    for q, expected_code in queries:
        spec = analyzer.analyze(q)
        assert spec.goal_clarity == "CLEAR", f"Failed clarity for query: {q}"
        assert spec.missing_slot is None, f"Failed missing_slot for query: {q}"
        assert spec.intent == GoalIntent.COURSE_FULL_DETAILS, f"Failed intent for query: {q}"
        assert spec.scope == GoalScope.ALL_AVAILABLE, f"Failed scope for query: {q}"
        assert expected_code in spec.entities
        assert "credits" in spec.requested_fields
        assert "department" in spec.requested_fields
        assert "english_name" in spec.requested_fields


def test_referent_resolution_with_session(analyzer):
    """Test resolving pronouns against session discourse state."""
    session_ctx = {
        "last_academic_entity": "FIT4201",
        "active_course_code": "FIT4201",
    }
    pronoun_queries = [
        "môn đó bao nhiêu tín chỉ?",
        "cho tôi biết tất cả thông tin môn đó",
        "môn này học kỳ mấy?",
        "nó có những chuẩn đầu ra nào?",
        "môn vừa rồi ai dạy?",
    ]
    for q in pronoun_queries:
        spec = analyzer.analyze(q, session_context=session_ctx)
        assert "FIT4201" in spec.entities, f"Failed resolving pronoun for: {q}"
        assert spec.missing_slot is None, f"Failed missing_slot for: {q}"


def test_referent_resolution_without_session_targeted_clarification(analyzer):
    """Pronoun with empty session must return targeted MISSING_ENTITY clarification."""
    spec = analyzer.analyze("môn đó bao nhiêu tín chỉ?", session_context={})
    assert spec.goal_clarity == "UNDERSPECIFIED"
    assert spec.missing_slot == "entity"
    assert spec.entities == []


def test_followup_field_inheritance(analyzer):
    """Follow-up questions specifying only fields must inherit last_academic_entity."""
    session_ctx = {
        "last_academic_entity": "FIT4201",
        "active_course_code": "FIT4201",
    }
    # Turn 2: "giảng viên thì sao?"
    spec2 = analyzer.analyze("giảng viên thì sao?", session_context=session_ctx)
    assert spec2.entities == ["FIT4201"]
    assert spec2.intent == GoalIntent.COURSE_FIELD_LOOKUP
    assert "lecturer" in spec2.requested_fields
    assert spec2.missing_slot is None

    # Turn 3: "CLO nữa"
    spec3 = analyzer.analyze("CLO nữa", session_context=session_ctx)
    assert spec3.entities == ["FIT4201"]
    assert spec3.intent == GoalIntent.COURSE_FIELD_LOOKUP
    assert "clo" in spec3.requested_fields
    assert spec3.missing_slot is None


def test_entity_switch_with_field_inheritance(analyzer):
    """Switching entity without fields inherits last_requested_fields from previous turn."""
    session_ctx = {
        "last_academic_entity": "FIT4201",
        "last_intent": "COURSE_FIELD_LOOKUP",
        "last_scope": "SINGLE_FIELD",
        "last_requested_fields": ["clo"],
    }
    spec = analyzer.analyze("còn FIT4113?", session_context=session_ctx)
    assert spec.entities == ["FIT4113"]
    assert spec.intent == GoalIntent.COURSE_FIELD_LOOKUP
    assert "clo" in spec.requested_fields
    assert spec.missing_slot is None


def test_concept_vs_course_title_disambiguation(analyzer):
    """Test disambiguation between course info and general technical definition."""
    # Conceptual question without academic cues -> targeted clarification
    spec_concept = analyzer.analyze("hệ thống nhúng là gì")
    assert spec_concept.goal_clarity == "AMBIGUOUS"
    assert spec_concept.missing_slot == "concept_course_ambiguity"
    assert "FIT4201" in spec_concept.entities

    # Academic question with the same course name -> COURSE_OVERVIEW
    spec_course = analyzer.analyze("chi tiết học phần hệ thống nhúng")
    assert spec_course.goal_clarity == "CLEAR"
    assert spec_course.missing_slot is None
    assert spec_course.intent == GoalIntent.COURSE_OVERVIEW
    assert "FIT4201" in spec_course.entities


def test_unavailable_field_abstain(analyzer):
    """Asking for unavailable data returns missing_slot='data'."""
    spec = analyzer.analyze("FIT4201 tỷ lệ trượt bao nhiêu?")
    assert spec.goal_clarity == "UNDERSPECIFIED"
    assert spec.missing_slot == "data"
