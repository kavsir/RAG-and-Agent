from src.agent.nodes import router_node


def test_router_domain_data_with_code():
    state = {
        "question": "Môn FIT4201 có mấy tín chỉ?",
        "rewritten_question": "Môn FIT4201 có mấy tín chỉ?",
        "analyzed_query": {"course_code": "FIT4201", "targets": ["credits"]}
    }
    res = router_node(state)
    assert res["category"] == "DOMAIN_DATA"


def test_router_domain_data_with_keywords():
    state = {
        "question": "Quy chế đào tạo tín chỉ và điều kiện tốt nghiệp",
        "rewritten_question": "Quy chế đào tạo tín chỉ và điều kiện tốt nghiệp",
        "analyzed_query": {"course_code": None, "targets": ["regulation"]}
    }
    res = router_node(state)
    assert res["category"] == "DOMAIN_DATA"


def test_router_general_llm():
    state = {
        "question": "Giải thích thuật toán Dijkstra",
        "rewritten_question": "Giải thích thuật toán Dijkstra",
        "analyzed_query": {"course_code": None, "targets": []}
    }
    res = router_node(state)
    assert res["category"] == "GENERAL_LLM"


def test_router_tool_reminder():
    state = {
        "question": "Nhắc tôi ôn thi ngày mai lúc 8h",
        "rewritten_question": "Nhắc tôi ôn thi ngày mai lúc 8h",
        "analyzed_query": {"course_code": None, "targets": []}
    }
    res = router_node(state)
    assert res["category"] == "TOOL_ACTION"
    assert res["tool_intent"] == "SET_REMINDER"


def test_router_tool_email():
    state = {
        "question": "Gửi email thông báo cho thầy giáo test@dainam.edu.vn",
        "rewritten_question": "Gửi email thông báo cho thầy giáo test@dainam.edu.vn",
        "analyzed_query": {"course_code": None, "targets": []}
    }
    res = router_node(state)
    assert res["category"] == "TOOL_ACTION"
    assert res["tool_intent"] == "SEND_EMAIL"
