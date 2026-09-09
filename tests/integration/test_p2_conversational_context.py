"""
Integration tests for Round P2 — Goal Understanding V2 + Conversational Discourse State.
Covers:
- Scenario A: Entity -> Broad Details -> Follow-up Field ("chi tiết học phần hệ thống nhúng" -> "giảng viên thì sao?" -> "CLO nữa")
- Scenario B: Pronoun with context vs Pronoun without context ("Môn đó bao nhiêu tín chỉ?")
- Scenario C: Entity Switch with Field Inheritance ("CLO FIT4201" -> "còn FIT4113?")
- Scenario D: Course vs General Concept Disambiguation ("chi tiết hệ thống nhúng" vs "hệ thống nhúng là gì")
- Adversarial Context: Cross-session & Cross-user Isolation (0 entity leakage)
"""
import uuid
import pytest
from src.api.chat_service import get_chat_execution_service
from src.api.schemas import ChatRequest


@pytest.fixture
def chat_service():
    return get_chat_execution_service()


def test_scenario_a_entity_overview_and_followup_fields(chat_service):
    """
    Scenario A:
    Turn 1: "chi tiết học phần hệ thống nhúng" -> Course Overview (COMPLETED, no clarification loop).
    Turn 2: "giảng viên thì sao?" -> inherits FIT4201, returns lecturer.
    Turn 3: "CLO nữa" -> inherits FIT4201, returns CLO.
    """
    conv_id = f"test-p2-scenario-a-{uuid.uuid4().hex[:8]}"

    # Turn 1: Broad academic intent (Course Overview)
    req1 = ChatRequest(message="chi tiết học phần hệ thống nhúng", conversation_id=conv_id)
    resp1 = chat_service.handle_chat(req1, user_id="student-a")

    assert resp1.status == "COMPLETED", f"Turn 1 should complete without clarification: {resp1.answer}"
    assert resp1.category == "DOMAIN_DATA"
    assert "FIT4201" in resp1.answer or "Hệ thống nhúng" in resp1.answer
    assert "tín chỉ" in resp1.answer.lower()
    assert len(resp1.sources) > 0, "Turn 1 must cite authoritative sources"

    # Turn 2: Follow-up field without entity: "giảng viên thì sao?"
    req2 = ChatRequest(message="giảng viên thì sao?", conversation_id=conv_id)
    resp2 = chat_service.handle_chat(req2, user_id="student-a")

    assert resp2.status == "COMPLETED", f"Turn 2 should inherit entity: {resp2.answer}"
    assert resp2.category == "DOMAIN_DATA"
    assert "Giảng viên" in resp2.answer or "giảng viên" in resp2.answer.lower() or "Cán bộ phụ trách" in resp2.answer

    # Turn 3: Follow-up field without entity: "CLO nữa"
    req3 = ChatRequest(message="CLO nữa", conversation_id=conv_id)
    resp3 = chat_service.handle_chat(req3, user_id="student-a")

    assert resp3.status == "COMPLETED", f"Turn 3 should inherit entity: {resp3.answer}"
    assert resp3.category == "DOMAIN_DATA"
    assert "CLO" in resp3.answer or "Chuẩn đầu ra" in resp3.answer


def test_scenario_b_pronoun_with_and_without_context(chat_service):
    """
    Scenario B:
    Case 1: Pronoun in empty session -> NEEDS_USER_INPUT (targeted missing entity).
    Case 2: Pronoun after course established -> Resolves to active entity, answers query.
    """
    # Case 1: Empty session with pronoun
    empty_conv = f"test-p2-empty-{uuid.uuid4().hex[:8]}"
    req_empty = ChatRequest(message="Môn đó bao nhiêu tín chỉ?", conversation_id=empty_conv)
    resp_empty = chat_service.handle_chat(req_empty, user_id="student-b1")

    assert resp_empty.status == "NEEDS_USER_INPUT", "Empty session must ask for clarification"
    assert "môn học" in resp_empty.answer.lower()

    # Case 2: Session with course established
    active_conv = f"test-p2-active-{uuid.uuid4().hex[:8]}"
    req1 = ChatRequest(message="FIT4113 mấy tín chỉ?", conversation_id=active_conv)
    resp1 = chat_service.handle_chat(req1, user_id="student-b2")
    assert resp1.status == "COMPLETED"
    assert "3" in resp1.answer

    # Turn 2: Pronoun referent with all details
    req2 = ChatRequest(message="cho tôi biết tất cả thông tin môn đó", conversation_id=active_conv)
    resp2 = chat_service.handle_chat(req2, user_id="student-b2")

    assert resp2.status in ("COMPLETED", "PARTIAL")
    assert "FIT4113" in resp2.answer or "Điện toán đám mây" in resp2.answer
    assert "tín chỉ" in resp2.answer.lower()
    assert len(resp2.sources) > 0


def test_scenario_c_entity_switch_with_field_inheritance(chat_service):
    """
    Scenario C:
    Turn 1: "CLO của FIT4201 là gì?" -> answers CLO for FIT4201.
    Turn 2: "còn FIT4113?" -> inherits field CLO, answers CLO for FIT4113 without asking.
    """
    conv_id = f"test-p2-switch-{uuid.uuid4().hex[:8]}"

    # Turn 1: Lookup CLO for FIT4201
    req1 = ChatRequest(message="CLO của FIT4201 là gì?", conversation_id=conv_id)
    resp1 = chat_service.handle_chat(req1, user_id="student-c")
    assert resp1.status == "COMPLETED"
    assert "CLO" in resp1.answer

    # Turn 2: Switch entity: "còn FIT4113?"
    req2 = ChatRequest(message="còn FIT4113?", conversation_id=conv_id)
    resp2 = chat_service.handle_chat(req2, user_id="student-c")

    assert resp2.status == "COMPLETED", f"Should inherit CLO field without asking: {resp2.answer}"
    assert "FIT4113" in resp2.answer or "Điện toán đám mây" in resp2.answer
    assert "CLO" in resp2.answer or "Chuẩn đầu ra" in resp2.answer


def test_scenario_d_course_title_vs_concept_disambiguation(chat_service):
    """
    Scenario D:
    1. "chi tiết hệ thống nhúng" -> resolves to FIT4201 Course Overview (DOMAIN_DATA, not GENERAL_LLM).
    2. "hệ thống nhúng là gì" -> asks targeted clarification between course info and general concept.
    """
    conv_id = f"test-p2-concept-{uuid.uuid4().hex[:8]}"

    # 1. Course overview by course title
    req_course = ChatRequest(message="chi tiết hệ thống nhúng", conversation_id=conv_id)
    resp_course = chat_service.handle_chat(req_course, user_id="student-d")

    assert resp_course.status == "COMPLETED"
    assert resp_course.category == "DOMAIN_DATA"
    assert "FIT4201" in resp_course.answer or "Hệ thống nhúng" in resp_course.answer

    # 2. Concept question with course name
    conv_id_2 = f"test-p2-concept-2-{uuid.uuid4().hex[:8]}"
    req_concept = ChatRequest(message="hệ thống nhúng là gì", conversation_id=conv_id_2)
    resp_concept = chat_service.handle_chat(req_concept, user_id="student-d")

    assert resp_concept.status == "NEEDS_USER_INPUT"
    assert "Hệ thống nhúng" in resp_concept.answer
    assert "FIT4201" in resp_concept.answer


def test_adversarial_cross_session_isolation(chat_service):
    """
    Adversarial Test:
    Session 1 discusses FIT4201.
    Session 2 from a different conversation asks "môn này bao nhiêu tín chỉ?".
    Session 2 MUST NOT leak Session 1's entity.
    """
    conv_1 = f"test-isolation-1-{uuid.uuid4().hex[:8]}"
    conv_2 = f"test-isolation-2-{uuid.uuid4().hex[:8]}"

    # Session 1 establishes FIT4201
    req1 = ChatRequest(message="FIT4201 có mấy tín chỉ?", conversation_id=conv_1)
    resp1 = chat_service.handle_chat(req1, user_id="user-1")
    assert resp1.status == "COMPLETED"

    # Session 2 asks with pronoun
    req2 = ChatRequest(message="môn này bao nhiêu tín chỉ?", conversation_id=conv_2)
    resp2 = chat_service.handle_chat(req2, user_id="user-2")

    # Must ask for clarification because Session 2 has 0 entities
    assert resp2.status == "NEEDS_USER_INPUT"
    assert "FIT4201" not in resp2.answer
