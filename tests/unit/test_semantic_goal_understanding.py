"""
Unit tests for Round P2.1 — SEMANTIC GOAL UNDERSTANDING.
Validates:
1. GoalFrame schema validation & invariants (no reasoning_text, strictly typed fields).
2. Semantic intent interpretation using singleton BGE-M3.
3. Referent & pronoun resolution (EXPLICIT, PRONOUN, PREVIOUS_ENTITY).
4. Practical workload constraint extraction (NEVER reinterpreted as credits).
5. Concept constraint extraction (CONTAINS_CONCEPT("AWS"), stop-word safety).
6. Multi-course comparison splitting & comparison types.
7. Unaccented, mobile slang, and typo robustness.
8. Unsupported goal handling (missing syllabus data, objective alternatives).
"""
import pytest
from src.agent_core.semantic_goal_interpreter import get_semantic_goal_interpreter
from src.agent_core.schemas import (
    GoalIntent,
    GoalScope,
    AggregationType,
    ReferentType,
    ComparisonType,
    GoalFrame,
    validate_goal_frame,
)


@pytest.fixture
def interpreter():
    return get_semantic_goal_interpreter()


def test_goal_frame_invariants_and_schema():
    """Verify GoalFrame strictly complies with architecture invariants."""
    frame = GoalFrame(
        intent=GoalIntent.COURSE_OVERVIEW,
        entities=["FIT4201"],
        referents=[ReferentType.EXPLICIT],
        requested_fields=["credits", "lecturer"],
        scope=GoalScope.SUMMARY,
        confidence=0.95,
        confidence_margin=0.40,
    )
    # Check that forbidden fields do not exist on the schema
    assert not hasattr(frame, "reasoning_text"), "GoalFrame must NOT have reasoning_text"
    assert not hasattr(frame, "chain_of_thought"), "GoalFrame must NOT have chain_of_thought"
    assert not hasattr(frame, "hidden_thought"), "GoalFrame must NOT have hidden_thought"

    errs = validate_goal_frame(frame)
    assert len(errs) == 0, f"Valid GoalFrame failed validation: {errs}"


def test_goal_frame_validation_guards():
    """Verify validate_goal_frame detects invalid confidence and missing slots."""
    invalid_frame = GoalFrame(
        intent=GoalIntent.COURSE_OVERVIEW,
        entities=[],
        confidence=1.5,  # Out of range
        confidence_margin=-0.2,  # Negative
    )
    errs = validate_goal_frame(invalid_frame)
    assert any("Confidence must be between 0.0 and 1.0" in e for e in errs)
    assert any("Confidence margin cannot be negative" in e for e in errs)


def test_referent_and_pronoun_resolution(interpreter):
    """Test resolution of pronouns and deictic references with session context."""
    # Context has FIT4201
    ctx = {"last_academic_entity": "FIT4201"}

    # Pronoun: 'nó'
    frame_pronoun = interpreter.interpret("nó có bao nhiêu tín chỉ?", session_context=ctx)
    assert frame_pronoun.intent == GoalIntent.COURSE_FIELD_LOOKUP
    assert "FIT4201" in frame_pronoun.entities
    assert ReferentType.PRONOUN in frame_pronoun.referents
    assert "credits" in frame_pronoun.requested_fields

    # Previous entity: 'môn đó'
    frame_prev = interpreter.interpret("môn đó học những gì?", session_context=ctx)
    assert frame_prev.intent == GoalIntent.COURSE_OVERVIEW
    assert "FIT4201" in frame_prev.entities
    assert ReferentType.PREVIOUS_ENTITY in frame_prev.referents

    # Unresolved pronoun without context -> missing slot 'entity'
    frame_unresolved = interpreter.interpret("nó có bao nhiêu tín chỉ?", session_context={})
    assert frame_unresolved.intent == GoalIntent.UNKNOWN
    assert "entity" in frame_unresolved.missing_slots


def test_practical_workload_never_reinterpreted_as_credits(interpreter):
    """
    CRITICAL RULE: 'nó có nặng thực hành không?'
    Must extract field='hours' and constraint='PRACTICAL_WORKLOAD'.
    Must NEVER be reinterpreted as credits.
    """
    ctx = {"last_academic_entity": "FIT4201"}
    queries = [
        "nó có nặng thực hành không?",
        "môn này nhiều thực hành không?",
        "nó có lab nhiều không?",
        "nhiều giờ thực hành không?",
    ]
    for q in queries:
        frame = interpreter.interpret(q, session_context=ctx)
        assert frame.intent == GoalIntent.COURSE_FIELD_LOOKUP, f"Failed intent for: {q}"
        assert "FIT4201" in frame.entities, f"Failed entity for: {q}"
        assert "hours" in frame.requested_fields, f"Expected 'hours' in fields for: {q}"
        assert "credits" not in frame.requested_fields, f"CRITICAL: 'credits' falsely inferred for: {q}"
        assert "PRACTICAL_WORKLOAD" in frame.constraints, f"Expected PRACTICAL_WORKLOAD for: {q}"


def test_concept_constraint_extraction(interpreter):
    """
    Test extraction of technical concepts like AWS, GCP in CLO queries.
    CLO nào của cloud liên quan AWS? -> CONTAINS_CONCEPT("AWS"), aggregation=LIST
    FIT4113 có bao nhiêu CLO liên quan AWS? -> CONTAINS_CONCEPT("AWS"), aggregation=COUNT
    """
    # Query 1: LIST CLO with concept AWS
    q1 = "CLO nào của cloud liên quan AWS?"
    f1 = interpreter.interpret(q1)
    assert "FIT4113" in f1.entities
    assert "clo" in f1.requested_fields
    assert 'CONTAINS_CONCEPT("AWS")' in f1.constraints
    assert f1.aggregation == AggregationType.LIST
    assert f1.scope == GoalScope.FILTERED_SET

    # Query 2: COUNT CLO with concept AWS
    q2 = "FIT4113 có bao nhiêu CLO liên quan AWS?"
    f2 = interpreter.interpret(q2)
    assert "FIT4113" in f2.entities
    assert "clo" in f2.requested_fields
    assert 'CONTAINS_CONCEPT("AWS")' in f2.constraints
    assert f2.aggregation == AggregationType.COUNT

    # Query 3: Ordinary words like 'gì' or 'này' must NOT produce CONTAINS_CONCEPT
    q3 = "môn nhúng có gì hay?"
    f3 = interpreter.interpret(q3)
    assert not any("CONTAINS_CONCEPT" in c for c in f3.constraints), f"Spurious concept extracted: {f3.constraints}"


def test_multi_course_comparison_workload(interpreter):
    """
    Test: 'so cloud với nhúng xem môn nào thực hành nhiều hơn'
    intent=COURSE_COMPARISON, entities=[FIT4113, FIT4201], field=hours, constraint=PRACTICAL_COMPONENT, comparison=GREATER_THAN
    """
    q = "so cloud với nhúng xem môn nào thực hành nhiều hơn"
    frame = interpreter.interpret(q)
    assert frame.intent == GoalIntent.COURSE_COMPARISON
    assert "FIT4113" in frame.entities
    assert "FIT4201" in frame.entities
    assert "hours" in frame.requested_fields
    assert "PRACTICAL_COMPONENT" in frame.constraints
    assert frame.comparison == ComparisonType.GREATER_THAN
    assert frame.aggregation == AggregationType.COMPARE


def test_unaccented_and_mutation_robustness(interpreter):
    """Test queries with missing accents and casual student phrasing."""
    # 1. Unaccented lecturer
    f1 = interpreter.interpret("ai dung lop FIT4201")
    assert f1.intent == GoalIntent.COURSE_FIELD_LOOKUP
    assert "FIT4201" in f1.entities
    assert "lecturer" in f1.requested_fields

    # 2. Unaccented credits
    f2 = interpreter.interpret("FIT4113 may tin chi")
    assert f2.intent == GoalIntent.COURSE_FIELD_LOOKUP
    assert "FIT4113" in f2.entities
    assert "credits" in f2.requested_fields

    # 3. Unaccented practical workload
    f3 = interpreter.interpret("hoc phan cloud co nhieu gio thuc hanh khong")
    assert f3.intent == GoalIntent.COURSE_FIELD_LOOKUP
    assert "FIT4113" in f3.entities
    assert "hours" in f3.requested_fields
    assert "PRACTICAL_WORKLOAD" in f3.constraints


def test_unsupported_difficulty_honest_alternative(interpreter):
    """
    Test unsupported subjective difficulty query:
    Must return missing_slots=['data'] and suggest syllabus-grounded alternative (hours, assessment, credits).
    Must NEVER hallucinate difficulty or guess.
    """
    ctx = {"last_academic_entity": "FIT4201"}
    frame = interpreter.interpret("mon nay co kho qua khong?", session_context=ctx)
    assert "data" in frame.missing_slots
    assert frame.unsupported_reason == "missing_direct_difficulty_evidence"
    assert frame.suggested_alternative is not None
    assert "khối lượng thực hành" in frame.suggested_alternative
    assert "FIT4201" in frame.entities


def test_safety_deterministic_tool_action(interpreter):
    """Deterministic tool action extraction with safety negation checks."""
    # Active send email
    f1 = interpreter.interpret("soạn email gửi thầy về việc đăng ký môn FIT4201")
    assert f1.intent == GoalIntent.TOOL_ACTION
    assert f1.tool_action == "SEND_EMAIL"

    # Negated / hypothetical tool action -> suppressed
    f2 = interpreter.interpret("đừng gửi email cho thầy nhé")
    assert f2.tool_action is None

    f3 = interpreter.interpret("nếu gửi email thì gửi cho ai?")
    assert f3.tool_action is None
