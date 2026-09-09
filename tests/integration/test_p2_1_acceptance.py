"""
Integration Acceptance tests for Round P2.1 — SEMANTIC GOAL UNDERSTANDING.
Validates:
1. End-to-end multi-turn Scenario A (Entity switch + field inheritance).
2. End-to-end multi-turn Scenario B (Overview -> Full details -> Constrained workload).
3. End-to-end multi-turn Scenario C (Concept constraint -> Aggregation).
4. Section 30 canonical student benchmark queries.
5. GoalAnalyzer integration populating GoalSpec with typed GoalFrame.
"""
import pytest
from src.agent_core.semantic_goal_interpreter import get_semantic_goal_interpreter
from src.agent_core.goal_analyzer import get_goal_analyzer
from src.agent_core.schemas import (
    GoalIntent,
    GoalScope,
    AggregationType,
    ReferentType,
    ComparisonType,
)


@pytest.fixture
def interpreter():
    return get_semantic_goal_interpreter()


@pytest.fixture
def analyzer():
    return get_goal_analyzer()


def test_scenario_a_cross_turn_entity_switch_and_field_inheritance(interpreter):
    """
    Scenario A:
    Turn 1: "kể mình nghe về môn nhúng" -> COURSE_OVERVIEW, entity=FIT4201
    Turn 2: "ai dạy vậy?" -> COURSE_FIELD_LOOKUP, entity=FIT4201, field=lecturer
    Turn 3: "còn cloud?" -> COURSE_FIELD_LOOKUP, entity=FIT4113, field=lecturer (inherited)
    Turn 4: "đầu ra nữa" -> COURSE_FIELD_LOOKUP, entity=FIT4113, field=clo
    """
    context = {}

    # Turn 1
    f1 = interpreter.interpret("kể mình nghe về môn nhúng", session_context=context)
    assert f1.intent == GoalIntent.COURSE_OVERVIEW
    assert "FIT4201" in f1.entities
    context["last_academic_entity"] = f1.entities[0]
    context["last_intent"] = f1.intent.value
    context["last_scope"] = f1.scope.value
    context["last_requested_fields"] = list(f1.requested_fields)
    context["last_constraints"] = list(f1.constraints)

    # Turn 2
    f2 = interpreter.interpret("ai dạy vậy?", session_context=context)
    assert f2.intent == GoalIntent.COURSE_FIELD_LOOKUP
    assert "FIT4201" in f2.entities
    assert "lecturer" in f2.requested_fields
    context["last_academic_entity"] = f2.entities[0]
    context["last_intent"] = f2.intent.value
    context["last_scope"] = f2.scope.value
    context["last_requested_fields"] = list(f2.requested_fields)
    context["last_constraints"] = list(f2.constraints)

    # Turn 3
    f3 = interpreter.interpret("còn cloud?", session_context=context)
    assert f3.intent == GoalIntent.COURSE_FIELD_LOOKUP
    assert "FIT4113" in f3.entities
    assert "lecturer" in f3.requested_fields, "Expected field 'lecturer' inherited from previous turn"
    context["last_academic_entity"] = f3.entities[0]
    context["last_intent"] = f3.intent.value
    context["last_scope"] = f3.scope.value
    context["last_requested_fields"] = list(f3.requested_fields)
    context["last_constraints"] = list(f3.constraints)

    # Turn 4
    f4 = interpreter.interpret("đầu ra nữa", session_context=context)
    assert f4.intent == GoalIntent.COURSE_FIELD_LOOKUP
    assert "FIT4113" in f4.entities
    assert "clo" in f4.requested_fields


def test_scenario_b_overview_to_full_details_to_constrained_workload(interpreter):
    """
    Scenario B:
    Turn 1: "cho mình xem FIT4113" -> COURSE_OVERVIEW, scope=SUMMARY
    Turn 2: "nói kỹ hết đi" -> COURSE_FULL_DETAILS, scope=ALL_AVAILABLE
    Turn 3: "môn này có nặng thực hành không?" -> COURSE_FIELD_LOOKUP, field=hours, constraint=PRACTICAL_WORKLOAD
    """
    context = {}

    # Turn 1
    f1 = interpreter.interpret("cho mình xem FIT4113", session_context=context)
    assert f1.intent == GoalIntent.COURSE_OVERVIEW
    assert "FIT4113" in f1.entities
    assert f1.scope == GoalScope.SUMMARY
    context["last_academic_entity"] = f1.entities[0]
    context["last_intent"] = f1.intent.value
    context["last_scope"] = f1.scope.value
    context["last_requested_fields"] = list(f1.requested_fields)
    context["last_constraints"] = list(f1.constraints)

    # Turn 2
    f2 = interpreter.interpret("nói kỹ hết đi", session_context=context)
    assert f2.intent == GoalIntent.COURSE_FULL_DETAILS
    assert "FIT4113" in f2.entities
    assert f2.scope == GoalScope.ALL_AVAILABLE
    context["last_academic_entity"] = f2.entities[0]
    context["last_intent"] = f2.intent.value
    context["last_scope"] = f2.scope.value
    context["last_requested_fields"] = list(f2.requested_fields)
    context["last_constraints"] = list(f2.constraints)

    # Turn 3
    f3 = interpreter.interpret("môn này có nặng thực hành không?", session_context=context)
    assert f3.intent == GoalIntent.COURSE_FIELD_LOOKUP
    assert "FIT4113" in f3.entities
    assert "hours" in f3.requested_fields
    assert "PRACTICAL_WORKLOAD" in f3.constraints


def test_scenario_c_filtered_concept_constraints_to_aggregation(interpreter):
    """
    Scenario C:
    Turn 1: "CLO cloud" -> field=clo
    Turn 2: "cái nào liên quan AWS?" -> field=clo, constraint=CONTAINS_CONCEPT("AWS"), aggregation=LIST, scope=FILTERED_SET
    Turn 3: "có mấy cái?" -> field=clo, constraint=CONTAINS_CONCEPT("AWS"), aggregation=COUNT
    """
    context = {}

    # Turn 1
    f1 = interpreter.interpret("CLO cloud", session_context=context)
    assert f1.intent == GoalIntent.COURSE_FIELD_LOOKUP
    assert "FIT4113" in f1.entities
    assert "clo" in f1.requested_fields
    context["last_academic_entity"] = f1.entities[0]
    context["last_intent"] = f1.intent.value
    context["last_scope"] = f1.scope.value
    context["last_requested_fields"] = list(f1.requested_fields)
    context["last_constraints"] = list(f1.constraints)

    # Turn 2
    f2 = interpreter.interpret("cái nào liên quan AWS?", session_context=context)
    assert f2.intent == GoalIntent.COURSE_FIELD_LOOKUP
    assert "FIT4113" in f2.entities
    assert "clo" in f2.requested_fields
    assert 'CONTAINS_CONCEPT("AWS")' in f2.constraints
    assert f2.aggregation == AggregationType.LIST
    assert f2.scope == GoalScope.FILTERED_SET
    context["last_academic_entity"] = f2.entities[0]
    context["last_intent"] = f2.intent.value
    context["last_scope"] = f2.scope.value
    context["last_requested_fields"] = list(f2.requested_fields)
    context["last_constraints"] = list(f2.constraints)

    # Turn 3
    f3 = interpreter.interpret("có mấy cái?", session_context=context)
    assert f3.intent == GoalIntent.COURSE_FIELD_LOOKUP
    assert "FIT4113" in f3.entities
    assert "clo" in f3.requested_fields
    assert 'CONTAINS_CONCEPT("AWS")' in f3.constraints
    assert f3.aggregation == AggregationType.COUNT


def test_section_30_canonical_queries(interpreter):
    """Verify Section 30 core mission queries."""
    # 1. "môn nhúng học những gì vậy?"
    f1 = interpreter.interpret("môn nhúng học những gì vậy?")
    assert f1.intent == GoalIntent.COURSE_OVERVIEW
    assert "FIT4201" in f1.entities

    # 2. "kể mình nghe về môn cloud"
    f2 = interpreter.interpret("kể mình nghe về môn cloud")
    assert f2.intent == GoalIntent.COURSE_OVERVIEW
    assert "FIT4113" in f2.entities

    # 3. "môn vừa rồi ai đứng lớp?"
    f3 = interpreter.interpret("môn vừa rồi ai đứng lớp?", session_context={"last_academic_entity": "FIT4201"})
    assert f3.intent == GoalIntent.COURSE_FIELD_LOOKUP
    assert "FIT4201" in f3.entities
    assert "lecturer" in f3.requested_fields
    assert ReferentType.PREVIOUS_ENTITY in f3.referents

    # 4. "nó có nặng thực hành không?"
    f4 = interpreter.interpret("nó có nặng thực hành không?", session_context={"last_academic_entity": "FIT4201"})
    assert f4.intent == GoalIntent.COURSE_FIELD_LOOKUP
    assert "FIT4201" in f4.entities
    assert "hours" in f4.requested_fields
    assert "PRACTICAL_WORKLOAD" in f4.constraints
    assert ReferentType.PRONOUN in f4.referents

    # 5. "còn môn kia thì sao?" (inherits last_intent and last_fields from previous context)
    f5 = interpreter.interpret(
        "còn FIT4113 thì sao?",
        session_context={"last_academic_entity": "FIT4201", "last_intent": "COURSE_FIELD_LOOKUP", "last_requested_fields": ["lecturer"]},
    )
    assert "FIT4113" in f5.entities
    assert "lecturer" in f5.requested_fields

    # 6. "CLO nào liên quan AWS?"
    f6 = interpreter.interpret("CLO nào liên quan AWS?", session_context={"last_academic_entity": "FIT4113"})
    assert "FIT4113" in f6.entities
    assert "clo" in f6.requested_fields
    assert 'CONTAINS_CONCEPT("AWS")' in f6.constraints

    # 7. "so 2 môn này xem môn nào thực hành nhiều hơn"
    f7 = interpreter.interpret("so cloud với nhúng xem môn nào thực hành nhiều hơn")
    assert f7.intent == GoalIntent.COURSE_COMPARISON
    assert "FIT4113" in f7.entities
    assert "FIT4201" in f7.entities
    assert "hours" in f7.requested_fields
    assert "PRACTICAL_COMPONENT" in f7.constraints
    assert f7.comparison == ComparisonType.GREATER_THAN


def test_goal_analyzer_spec_generation(analyzer):
    """Verify GoalAnalyzer integrates with SemanticGoalInterpreter to produce complete GoalSpec."""
    spec = analyzer.analyze("môn FIT4113 có bao nhiêu CLO liên quan AWS?")
    assert spec.goal_clarity == "CLEAR"
    assert spec.intent == GoalIntent.COURSE_FIELD_LOOKUP
    assert "FIT4113" in spec.entities
    assert "clo" in spec.requested_fields
    assert 'CONTAINS_CONCEPT("AWS")' in spec.constraints
    assert spec.aggregation == AggregationType.COUNT
    assert spec.goal_frame is not None
    assert spec.goal_frame.confidence >= 0.50
