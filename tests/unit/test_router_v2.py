"""
Unit Tests cho Router V2 (Local Intent Classification Agent).
Kiểm thử toàn diện 5 tầng phân loại, chống ô nhiễm từ khóa,
khử nhiễu tool query, tái sử dụng singleton embedding, và kiểm chứng 0 external API calls.
"""
import pytest
from src.router import get_router_service, IntentDecision
from src.router.normalizer import normalize_query
from src.router.evidence import extract_evidence
from src.router.policy import evaluate_policy
from src.ingestion.vector_store import get_embedding_model
import src.llm.client


@pytest.fixture(scope="module")
def router_service():
    """Khởi tạo RouterService singleton cho toàn bộ suite test."""
    return get_router_service()


def test_zero_external_api_calls(monkeypatch, router_service):
    """Router V2 tuyệt đối không gọi LLM bên ngoài."""
    def mock_invoke(*args, **kwargs):
        raise AssertionError("VIOLATION: Router V2 called external LLM!")

    monkeypatch.setattr(src.llm.client, "invoke_llm", mock_invoke)

    queries = [
        "Môn FIT4201 có bao nhiêu tín chỉ?",
        "Điểm khác biệt cơ bản giữa giao thức TCP và UDP là gì?",
        "Soạn giúp tôi email gửi thầy xin hoãn nộp bài",
        "Nhắc tôi ôn thi lúc 8h tối mai",
        "Quy chế đào tạo của trường Đại Nam",
    ]
    for q in queries:
        decision = router_service.classify(q)
        assert isinstance(decision, IntentDecision)


def test_embedding_model_singleton_reuse():
    """Kiểm tra Router V2 dùng chung Singleton embedding model với vector store, 0 extra RAM."""
    model1 = get_embedding_model()
    router = get_router_service()
    assert router.semantic_classifier is not None
    assert router.semantic_classifier.embedding_model is model1


def test_normalizer():
    """Kiểm tra normalizer chuẩn hóa unicode và khoảng cách mã môn."""
    raw = "  Môn  FIT  4201   có   mấy tín?  "
    clean, lower = normalize_query(raw)
    assert clean == "Môn FIT 4201 có mấy tín?"
    assert "fit4201" in lower


def test_strong_domain_routing(router_service):
    """Kiểm tra các câu hỏi domain học vụ rõ ràng đi qua Fast-Path."""
    # Có mã môn học trực tiếp
    d1 = router_service.classify("Môn FIT4201 có bao nhiêu tín chỉ?")
    assert d1.category == "DOMAIN_DATA"
    assert d1.decision_path == "STRONG_DOMAIN_FAST_PATH"
    assert "FIT4201" in d1.reason_code

    # Quy chế đào tạo
    d2 = router_service.classify("Quy chế đào tạo về cảnh báo học vụ của trường Đại Nam")
    assert d2.category == "DOMAIN_DATA"
    assert d2.decision_path == "STRONG_DOMAIN_FAST_PATH"

    # Môn không có mã nhưng có target và cue
    d3 = router_service.classify("Môn Hệ thống nhúng có bao nhiêu tín chỉ?")
    assert d3.category == "DOMAIN_DATA"
    assert d3.decision_path == "STRONG_DOMAIN_FAST_PATH"


def test_target_disambiguation(router_service):
    """Kiểm tra khử ô nhiễm từ 'điểm' và 'mục tiêu'."""
    # 'Điểm khác biệt' KHÔNG ĐƯỢC kích hoạt assessment target
    clean, lower = normalize_query("Điểm khác biệt giữa TCP và UDP")
    ev = extract_evidence(clean, lower)
    assert ev.target_strength == "NONE"

    d = router_service.classify("Điểm khác biệt cơ bản giữa giao thức TCP và UDP trong mạng máy tính là gì?")
    assert d.category == "GENERAL_LLM"

    # 'Điểm chuyên cần' PHẢI kích hoạt assessment target
    clean_ac, lower_ac = normalize_query("Điểm chuyên cần môn này chiếm bao nhiêu phần trăm?")
    ev_ac = extract_evidence(clean_ac, lower_ac)
    assert ev_ac.academic_target == "assessment"
    assert ev_ac.target_strength == "STRONG"


def test_strong_tool_routing(router_service):
    """Kiểm tra nhận diện TOOL_ACTION thông qua proximity matching."""
    # Email tool
    d1 = router_service.classify("Soạn giúp tôi email gửi thầy giáo đến tieppv@dainam.edu.vn")
    assert d1.category == "TOOL_ACTION"
    assert d1.tool_intent == "SEND_EMAIL"
    assert d1.decision_path == "STRONG_TOOL_FAST_PATH"

    # Reminder tool
    d2 = router_service.classify("Đặt lịch nhắc ôn thi cuối kỳ lúc 8 giờ ngày 25/12/2026")
    assert d2.category == "TOOL_ACTION"
    assert d2.tool_intent == "SET_REMINDER"
    assert d2.decision_path == "STRONG_TOOL_FAST_PATH"


def test_negative_tool_queries(router_service):
    """Kiểm tra các câu hỏi có chứa từ email hoặc nhắc nhưng bản chất là khái niệm."""
    # 'Email là gì' không được vào TOOL_ACTION
    d1 = router_service.classify("Email là gì và các giao thức gửi nhận thư điện tử phổ biến gồm những gì?")
    assert d1.category == "GENERAL_LLM"
    assert d1.tool_intent is None

    # 'Nhắc lại định nghĩa' không được vào TOOL_ACTION
    d2 = router_service.classify("Nhắc lại định nghĩa về tính đa hình trong lập trình hướng đối tượng")
    assert d2.category == "GENERAL_LLM"
    assert d2.tool_intent is None


def test_multi_turn_disambiguation(router_service):
    """Kiểm tra xử lý ngữ cảnh nhiều lượt (multi-turn)."""
    # Lượt 1 đã thiết lập FIT4201 trong session
    session_ctx = {"course_code": "FIT4201"}

    # Lượt 2 hỏi học vụ: 'Môn đó có bao nhiêu tín chỉ?' -> DOMAIN_DATA
    d1 = router_service.classify("Môn đó có bao nhiêu tín chỉ?", analyzed_query=session_ctx)
    assert d1.category == "DOMAIN_DATA"

    # Lượt 2 hỏi kỹ thuật thực tế: 'Vậy hệ thống nhúng trong thực tế thường dùng vi điều khiển nào?' -> GENERAL_LLM
    d2 = router_service.classify("Vậy hệ thống nhúng trong thực tế thường dùng vi điều khiển nào?", analyzed_query=session_ctx)
    assert d2.category == "GENERAL_LLM"


def test_low_confidence_fallback():
    """Kiểm tra tầng chính sách fallback khi không có semantic classifier hoặc điểm số thấp."""
    clean, lower = normalize_query("Một câu hỏi lạ chưa từng thấy về môn học")
    ev = extract_evidence(clean, lower)
    decision = evaluate_policy(clean, lower, ev, semantic_classifier=None)
    # Vì có từ 'môn học', fallback an toàn ưu tiên DOMAIN_DATA
    assert decision.category == "DOMAIN_DATA"
    assert decision.decision_path == "LOW_CONFIDENCE_FALLBACK"
