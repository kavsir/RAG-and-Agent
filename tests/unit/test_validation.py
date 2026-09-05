from src.agent.nodes import validation_node
from src.agent.graph import route_after_validation
from src.llm.client import set_mock_llm_handler


def test_validation_valid():
    set_mock_llm_handler(lambda p, **kwargs: '{"valid": true}')
    try:
        state = {
            "answer": "Môn FIT4201 có 2 tín chỉ.",
            "context": "Môn FIT4201 - Hệ thống nhúng có 2 tín chỉ.",
            "question": "Môn FIT4201 có bao nhiêu tín chỉ?",
            "retry_count": 0,
            "sources": [{"source_file": "FIT4201.docx"}],
        }
        res = validation_node(state)
        assert res["validation_result"]["valid"] is True
        assert route_after_validation(res) == "save_chat"
    finally:
        set_mock_llm_handler(None)


def test_validation_invalid_retry_under_limit():
    set_mock_llm_handler(lambda p, **kwargs: '{"valid": false, "reason": "Thừa thông tin bịa đặt", "missing_keywords": ["tín chỉ"]}')
    try:
        state = {
            "answer": "Môn FIT4201 có 10 tín chỉ và do GS. X dạy.",
            "context": "Môn FIT4201 có 2 tín chỉ.",
            "question": "Môn FIT4201 có bao nhiêu tín chỉ?",
            "retry_count": 0,
            "sources": [{"source_file": "FIT4201.docx"}],
        }
        res = validation_node(state)
        assert res["validation_result"]["valid"] is False
        assert res["retry_count"] == 1
        assert route_after_validation(res) == "retrieve"
    finally:
        set_mock_llm_handler(None)


def test_validation_invalid_retry_limit_reached_abstains():
    set_mock_llm_handler(lambda p, **kwargs: '{"valid": false, "reason": "Thừa thông tin bịa đặt"}')
    try:
        state = {
            "answer": "Môn FIT4201 có 10 tín chỉ.",
            "context": "Môn FIT4201 có 2 tín chỉ.",
            "question": "Môn FIT4201 có bao nhiêu tín chỉ?",
            "retry_count": 2,  # Đã retry đủ 2 lần
            "sources": [{"source_file": "FIT4201.docx"}],
        }
        res = validation_node(state)
        # Bắt buộc chuyển thành Abstain
        assert "chưa tìm thấy đủ dữ liệu" in res["answer"].lower()
        assert res["sources"] == []
        assert res["validation_result"]["valid"] is True
        # Phải kết thúc sang save_chat, không được loop vô tận
        assert route_after_validation(res) == "save_chat"
    finally:
        set_mock_llm_handler(None)


def test_validation_malformed_json_fails_safe():
    # LLM trả về text không phải JSON
    set_mock_llm_handler(lambda p, **kwargs: "Đây là câu trả lời không phải JSON hợp lệ.")
    try:
        # Lần retry 0: Coi là fail, retry tiếp
        state0 = {
            "answer": "Câu trả lời A.",
            "context": "Context A.",
            "question": "Hỏi A?",
            "retry_count": 0,
        }
        res0 = validation_node(state0)
        assert res0["validation_result"]["valid"] is False
        assert res0["retry_count"] == 1
        assert route_after_validation(res0) == "retrieve"

        # Lần retry 2: Hết lượt, cưỡng chế abstain
        state2 = {
            "answer": "Câu trả lời A.",
            "context": "Context A.",
            "question": "Hỏi A?",
            "retry_count": 2,
        }
        res2 = validation_node(state2)
        assert "chưa tìm thấy đủ dữ liệu" in res2["answer"].lower()
        assert res2["sources"] == []
        assert res2["validation_result"]["valid"] is True
        assert route_after_validation(res2) == "save_chat"
    finally:
        set_mock_llm_handler(None)


def test_validation_exception_fails_safe():
    # LLM raise exception (network error)
    def raise_err(prompt, **kwargs):
        raise ConnectionError("Network timeout")

    set_mock_llm_handler(raise_err)
    try:
        state = {
            "answer": "Câu trả lời lỗi.",
            "context": "Context lỗi.",
            "question": "Hỏi lỗi?",
            "retry_count": 2,
        }
        res = validation_node(state)
        assert "chưa tìm thấy đủ dữ liệu" in res["answer"].lower()
        assert res["sources"] == []
        assert res["validation_result"]["valid"] is True
        assert route_after_validation(res) == "save_chat"
    finally:
        set_mock_llm_handler(None)
