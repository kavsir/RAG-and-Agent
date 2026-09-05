"""
Unit & Integration Tests cho Structured SQLite Session Memory (Round B).
Kiểm thử toàn diện:
1. Tạo phiên và ghi tin nhắn
2. Cô lập lịch sử theo conversation_id (Cross-session Isolation)
3. Kế thừa thực thể qua đại từ (Follow-up Entity Resolution)
4. Chuyển đổi thực thể (Entity Switching)
5. Kế thừa mục tiêu (Target Carry-over)
6. Xử lý câu hỏi mơ hồ (Ambiguous Reference Safety)
7. Tồn tại bền vững qua khởi động lại tiến trình (Restart Persistence)
8. Xóa riêng một phiên (Single Session Deletion)
9. Tương thích với Router V2 (Weak entity contract, không ép general sang domain)
"""
import pytest
from pathlib import Path
from src.memory.sqlite_store import SQLiteSessionStore
from src.memory.session_memory import SessionMemoryService
from src.rag.query_analyzer import analyze_query
from src.router import get_router_service


@pytest.fixture
def temp_session_service(tmp_path: Path):
    """Tạo SessionMemoryService cô lập với CSDL tạm thời cho mỗi test."""
    db_file = tmp_path / "test_memory.db"
    store = SQLiteSessionStore(db_path=db_file)
    return SessionMemoryService(store=store)


def test_session_creation_and_append_message(temp_session_service):
    """Kiểm tra tạo phiên và ghi nhận tin nhắn chính xác."""
    conv_id = "test-session-001"
    msg1 = temp_session_service.store.append_message(conv_id, "user", "Xin chào")
    msg2 = temp_session_service.store.append_message(conv_id, "assistant", "Chào bạn, tôi là Cố vấn học tập.")

    assert msg1.id is not None
    assert msg1.conversation_id == conv_id
    assert msg1.role == "user"
    assert msg2.id is not None
    assert msg2.role == "assistant"

    messages = temp_session_service.get_recent_messages(conv_id, k=5)
    assert len(messages) == 2
    assert messages[0].content == "Xin chào"
    assert messages[1].content == "Chào bạn, tôi là Cố vấn học tập."


def test_cross_session_isolation(temp_session_service):
    """BẢO ĐẢM CỔNG: Hai phiên A và B hoàn toàn độc lập, không ô nhiễm chéo."""
    conv_a = "session-student-A"
    conv_b = "session-student-B"

    # Phiên A hỏi về FIT4201
    temp_session_service.update_turn(conv_a, "FIT4201 là môn gì?", "Là Hệ thống nhúng.")

    # Phiên B hỏi về FIT4104
    temp_session_service.update_turn(conv_b, "FIT4104 là môn gì?", "Là Full-Stack Design.")

    # Kiểm tra trạng thái thực thể của từng phiên
    state_a = temp_session_service.get_session_state(conv_a)
    state_b = temp_session_service.get_session_state(conv_b)

    assert state_a.active_course_code == "FIT4201"
    assert state_b.active_course_code == "FIT4104"

    # Phiên A hỏi tiếp: "Ai dạy môn đó?" -> phải giải quyết thành FIT4201
    code_a, _, src_a, _ = temp_session_service.resolve_context(conv_a, "Ai dạy môn đó?")
    assert code_a == "FIT4201"
    assert src_a == "SESSION"

    # Phiên B hỏi tiếp: "Ai dạy môn đó?" -> phải giải quyết thành FIT4104
    code_b, _, src_b, _ = temp_session_service.resolve_context(conv_b, "Ai dạy môn đó?")
    assert code_b == "FIT4104"
    assert src_b == "SESSION"


def test_entity_switching(temp_session_service):
    """BẢO ĐẢM CỔNG: Thực thể tường minh mới nhất phải ghi đè thực thể cũ."""
    conv_id = "test-switch-session"

    # Lượt 1: Hỏi về FIT4201
    temp_session_service.update_turn(conv_id, "FIT4201 có bao nhiêu tín chỉ?", "Có 2 tín chỉ.")
    state1 = temp_session_service.get_session_state(conv_id)
    assert state1.active_course_code == "FIT4201"

    # Lượt 2: Chuyển sang hỏi môn FIT4104
    temp_session_service.update_turn(conv_id, "Còn môn FIT4104 thì sao?", "FIT4104 có 3 tín chỉ.")
    state2 = temp_session_service.get_session_state(conv_id)
    assert state2.active_course_code == "FIT4104"

    # Lượt 3: Hỏi bằng đại từ "Ai dạy môn đó?" -> phải gắn với FIT4104, KHÔNG ĐƯỢC là FIT4201
    code, _, src, _ = temp_session_service.resolve_context(conv_id, "Ai dạy môn đó?")
    assert code == "FIT4104"
    assert src == "SESSION"


def test_target_carry_over(temp_session_service):
    """BẢO ĐẢM CỔNG: Kế thừa mục tiêu logic (lecturer -> email)."""
    conv_id = "test-target-session"

    # Lượt 1: Hỏi giảng viên môn FIT4201
    temp_session_service.update_turn(
        conv_id,
        "Ai dạy môn FIT4201?",
        "Thầy Nguyễn Văn Nhẫn phụ trách.",
        analyzed_query={"targets": ["lecturer"]},
    )
    state = temp_session_service.get_session_state(conv_id)
    assert state.active_course_code == "FIT4201"
    assert state.active_target == "lecturer"

    # Lượt 2: Hỏi ngắn gọn "Email thì sao?"
    code, target, src, _ = temp_session_service.resolve_context(conv_id, "Email thì sao?")
    assert code == "FIT4201"
    assert target == "lecturer_email"
    assert src == "SESSION"


def test_ambiguous_reference_safety(temp_session_service):
    """BẢO ĐẢM CỔNG: Đại từ khi chưa có thực thể trong phiên phải đánh dấu UNRESOLVED."""
    conv_id = "test-empty-session"

    # Phiên hoàn toàn mới, người dùng hỏi ngay đại từ
    code, target, src, unresolved = temp_session_service.resolve_context(conv_id, "Môn đó có bao nhiêu tín chỉ?")
    assert code is None
    assert unresolved is True
    assert src == "UNRESOLVED"

    # Query Analyzer cũng phải ghi nhận unresolved_reference
    aq = analyze_query("Môn đó có bao nhiêu tín chỉ?", session_context={"course_code": None})
    assert aq.unresolved_reference is True
    assert aq.resolution_source == "UNRESOLVED"
    assert aq.course_code is None


def test_restart_persistence(tmp_path: Path):
    """BẢO ĐẢM CỔNG: Dữ liệu phiên tồn tại bền vững qua khởi động lại tiến trình."""
    db_file = tmp_path / "persistent_advisor.db"

    # Tiến trình 1: Khởi tạo và ghi dữ liệu
    service_1 = SessionMemoryService(store=SQLiteSessionStore(db_path=db_file))
    service_1.update_turn(
        conversation_id="conv-persistent-123",
        user_message="Môn FIT4201 có mấy tín chỉ?",
        ai_message="Môn có 2 tín chỉ.",
        analyzed_query={"targets": ["credits"], "course_name": "Hệ thống nhúng"},
        sources=[{"source": "FIT4201- Hệ thống nhúng.docx"}],
    )
    service_1.store.close()

    # Tiến trình 2: Khởi tạo instance mới hoàn toàn từ file CSDL SQLite trên đĩa
    service_2 = SessionMemoryService(store=SQLiteSessionStore(db_path=db_file))
    state = service_2.get_session_state("conv-persistent-123")

    assert state.conversation_id == "conv-persistent-123"
    assert state.active_course_code == "FIT4201"
    assert state.active_course_name == "Hệ thống nhúng"
    assert state.active_target == "credits"
    assert "FIT4201- Hệ thống nhúng.docx" in state.last_source_ids

    messages = service_2.get_recent_messages("conv-persistent-123", k=5)
    assert len(messages) == 2
    assert messages[0].content == "Môn FIT4201 có mấy tín chỉ?"


def test_clear_single_session(temp_session_service):
    """Xóa một phiên không ảnh hưởng đến phiên khác."""
    conv_1 = "session-to-clear"
    conv_2 = "session-to-keep"

    temp_session_service.update_turn(conv_1, "FIT4201 là gì?", "Nhúng.")
    temp_session_service.update_turn(conv_2, "FIT4104 là gì?", "Web.")

    # Xóa riêng phiên 1
    temp_session_service.clear_session(conv_1)

    # Phiên 1 bị reset
    state_1 = temp_session_service.get_session_state(conv_1)
    assert state_1.active_course_code is None
    assert len(temp_session_service.get_recent_messages(conv_1)) == 0

    # Phiên 2 vẫn nguyên vẹn
    state_2 = temp_session_service.get_session_state(conv_2)
    assert state_2.active_course_code == "FIT4104"
    assert len(temp_session_service.get_recent_messages(conv_2)) == 2


def test_router_v2_compatibility_weak_contract(temp_session_service):
    """
    BẢO ĐẢM CỔNG: Thực thể kế thừa từ Session chỉ có mức WEAK đối với Router V2,
    không được ép câu hỏi kỹ thuật/khái niệm chung vào DOMAIN_DATA.
    """
    router = get_router_service()
    conv_id = "session-router-compat"

    # Lượt 1: Hỏi học vụ về FIT4201
    temp_session_service.update_turn(conv_id, "FIT4201 có mấy tín chỉ?", "2 tín chỉ.")
    session_ctx = temp_session_service.get_session_state(conv_id).to_context_dict()

    # Lượt 2: Hỏi câu hỏi kỹ thuật thực tế: "Vậy hệ thống nhúng trong thực tế thường dùng vi điều khiển nào?"
    # Router V2 phải nhận diện đây là GENERAL_LLM
    decision = router.classify(
        query="Vậy hệ thống nhúng trong thực tế thường dùng vi điều khiển nào?",
        analyzed_query=session_ctx,
    )
    assert decision.category == "GENERAL_LLM"
    assert decision.tool_intent is None
