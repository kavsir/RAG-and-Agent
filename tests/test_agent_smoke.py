"""
Smoke test cho LangGraph Agent với 3 nhánh: DOMAIN_DATA, GENERAL_LLM, TOOL_ACTION.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.llm.client import set_mock_llm_handler
from src.agent.graph import graph


def mock_llm_handler(prompt, system_prompt=None):
    prompt_lower = prompt.lower()
    if "kiểm định" in prompt_lower or "tiêu chí" in prompt_lower or "groundedness" in prompt_lower:
        return '{"valid": true}'
    if "xyz9999" in prompt_lower:
        return "Chưa tìm thấy đủ dữ liệu trong tài liệu hiện có để trả lời chính xác."
    if "fit4201" in prompt_lower:
        return "Môn FIT4201 - Hệ thống nhúng có 3 tín chỉ theo đề cương chi tiết."
    if "dijkstra" in prompt_lower:
        return "Dijkstra là thuật toán tìm đường đi ngắn nhất giữa các đỉnh trong đồ thị có trọng số không âm."
    if "phân loại" in prompt_lower:
        return '{"category": "DOMAIN_DATA", "tool_intent": null}'
    return "Câu trả lời mẫu."


def test_agent_graph_routes():
    set_mock_llm_handler(mock_llm_handler)

    # 1. Test DOMAIN_DATA
    res1 = graph.invoke({
        "question": "FIT4201 có bao nhiêu tín chỉ?",
        "conversation_id": "test-1",
        "chat_history": "",
        "student_profile": {}
    })
    print("DOMAIN_DATA Category:", res1.get("category"))
    print("DOMAIN_DATA Answer:", res1.get("answer"))
    print("DOMAIN_DATA Sources count:", len(res1.get("sources", [])))
    assert res1.get("category") == "DOMAIN_DATA"
    assert len(res1.get("sources", [])) > 0
    assert "FIT4201" in res1.get("answer")

    # 2. Test GENERAL_LLM
    res2 = graph.invoke({
        "question": "Dijkstra là gì?",
        "conversation_id": "test-2",
        "chat_history": "",
        "student_profile": {}
    })
    print("GENERAL_LLM Category:", res2.get("category"))
    assert res2.get("category") == "GENERAL_LLM"
    assert "Dijkstra" in res2.get("answer")

    # 3. Test TOOL_ACTION (Reminder)
    res3 = graph.invoke({
        "question": "Nhắc tôi ôn thi ngày 20/12 lúc 8h",
        "conversation_id": "test-3",
        "chat_history": "",
        "student_profile": {}
    })
    print("TOOL_ACTION Category:", res3.get("category"))
    assert res3.get("category") == "TOOL_ACTION"
    assert any(p in res3.get("answer", "") for p in ["Đã lên lịch nhắc nhở", "Đã ghi nhận lịch nhắc"])

    # 4. Test TOOL_ACTION (Email disabled fallback)
    res4 = graph.invoke({
        "question": "Gửi email cho bạn test@gmail.com",
        "conversation_id": "test-4",
        "chat_history": "",
        "student_profile": {}
    })
    print("Email fallback Answer:", res4.get("answer"))
    assert "Chức năng email hiện chưa được cấu hình." in res4.get("answer")

    # 5. Test Insufficient Evidence Abstention
    res5 = graph.invoke({
        "question": "Học phần XYZ9999 có bao nhiêu tín chỉ?",
        "conversation_id": "test-5",
        "chat_history": "",
        "student_profile": {}
    })
    print("Abstention Answer:", res5.get("answer"))
    assert "Chưa tìm thấy đủ dữ liệu" in res5.get("answer")

    print("\nALL 5 SCENARIOS PASSED PERFECTLY!")


if __name__ == "__main__":
    test_agent_graph_routes()
