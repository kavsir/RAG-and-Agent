import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.llm.client import set_mock_llm_handler


from src.memory.memory_manager import get_memory_manager
from src.cache.exact_cache import get_exact_cache


def mock_api_llm(prompt, system_prompt=None):
    p = prompt.lower()
    if "kiểm định" in p or "tiêu chí" in p or "groundedness" in p:
        return '{"valid": true}'

    # Ưu tiên kiểm tra phần [câu hỏi]: nếu có để tránh ảnh hưởng bởi chat_history
    q_part = p.split("[câu hỏi]:")[-1] if "[câu hỏi]:" in p else p

    if "dijkstra" in q_part:
        return "Thuật toán Dijkstra dùng để tìm đường đi ngắn nhất."
    if "xyz9999" in q_part:
        return "Chưa tìm thấy đủ dữ liệu trong tài liệu hiện có để trả lời chính xác."
    if "fit4201" in q_part:
        return "Môn FIT4201 - Hệ thống nhúng có 3 tín chỉ theo đề cương chi tiết."
    if "phân loại" in p or "intent" in p:
        return '{"category": "DOMAIN_DATA", "tool_intent": null}'
    return "Câu trả lời mẫu từ trợ lý."


@pytest.fixture(autouse=True)
def setup_mock():
    set_mock_llm_handler(mock_api_llm)
    get_memory_manager().clear()
    get_exact_cache().clear()
    yield
    set_mock_llm_handler(None)
    get_memory_manager().clear()
    get_exact_cache().clear()


client = TestClient(app)


def test_health_endpoint():
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ("ok", "warning")
    assert "components" in data
    assert "vector_store" in data["components"]


def test_chat_domain_data():
    res = client.post("/api/chat", json={"message": "Môn FIT4201 có bao nhiêu tín chỉ?"})
    assert res.status_code == 200
    data = res.json()
    assert data["category"] == "DOMAIN_DATA"
    assert "FIT4201" in data["answer"]
    assert len(data["sources"]) > 0
    assert "conversation_id" in data


def test_chat_general_llm():
    res = client.post("/api/chat", json={"message": "Giải thích thuật toán Dijkstra"})
    assert res.status_code == 200
    data = res.json()
    assert data["category"] == "GENERAL_LLM"
    assert "Dijkstra" in data["answer"]
    assert len(data["sources"]) == 0


def test_chat_tool_reminder():
    res = client.post("/api/chat", json={"message": "Nhắc tôi ôn thi môn AI ngày 15/12"})
    assert res.status_code == 200
    data = res.json()
    assert data["category"] == "TOOL_ACTION"
    assert any(p in data["answer"] for p in ["Đã lên lịch nhắc nhở", "Đã ghi nhận lịch nhắc"])


def test_chat_insufficient_evidence():
    res = client.post("/api/chat", json={"message": "Học phần XYZ9999 có mấy tín chỉ?"})
    assert res.status_code == 200
    data = res.json()
    assert "Chưa tìm thấy đủ dữ liệu" in data["answer"]
    assert data["sources"] == []


def test_chat_invalid_request():
    # Empty message should trigger 422 Unprocessable Entity
    res = client.post("/api/chat", json={"message": ""})
    assert res.status_code == 422


def test_profile_lifecycle():
    # GET profile
    res1 = client.get("/api/profile")
    assert res1.status_code == 200

    # PUT profile
    payload = {
        "name": "Nguyễn Văn Test",
        "major": "Khoa học máy tính",
        "cohort": "K19",
        "email": "test@dainam.edu.vn",
        "style": "Lý thuyết"
    }
    res2 = client.put("/api/profile", json=payload)
    assert res2.status_code == 200
    assert res2.json()["name"] == "Nguyễn Văn Test"


def test_clear_conversations():
    res = client.post("/api/conversations/clear")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
