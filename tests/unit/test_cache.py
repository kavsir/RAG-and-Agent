from src.cache.exact_cache import ExactCache, get_exact_cache
from src.agent.nodes import cache_node, save_chat_node


def test_exact_cache_operations():
    cache = ExactCache()
    assert cache.size() == 0

    sources = [{"source_file": "FIT4201.docx", "section": "I"}]
    cache.set(
        key="Môn FIT4201 có mấy tín chỉ?",
        answer="Môn có 2 tín chỉ.",
        category="DOMAIN_DATA",
        sources=sources,
        tool_intent=None,
    )
    assert cache.size() == 1

    # Case-insensitive / whitespace-stripped retrieval
    val = cache.get("  môn fit4201 có mấy tín chỉ?  ")
    assert val is not None
    assert val["answer"] == "Môn có 2 tín chỉ."
    assert val["category"] == "DOMAIN_DATA"
    assert val["sources"] == sources
    assert val["tool_intent"] is None

    cache.clear()
    assert cache.size() == 0
    assert cache.get("Môn FIT4201 có mấy tín chỉ?") is None


def test_cache_node_domain_restoration():
    cache = get_exact_cache()
    cache.clear()

    # Lưu 1 câu hỏi DOMAIN_DATA
    sources = [{"source_file": "FIT4201- Hệ thống nhúng.docx", "chunk_id": "c1"}]
    save_chat_node({
        "question": "Môn FIT4201 có bao nhiêu tín chỉ?",
        "answer": "Môn FIT4201 có 2 tín chỉ.",
        "category": "DOMAIN_DATA",
        "sources": sources,
        "tool_intent": None,
        "cache_hit": False,
    })

    # Truy vấn lại qua cache_node
    res = cache_node({"question": "  môn FIT4201 có bao nhiêu tín chỉ? "})
    assert res["cache_hit"] is True
    assert res["answer"] == "Môn FIT4201 có 2 tín chỉ."
    assert res["category"] == "DOMAIN_DATA"
    assert len(res["sources"]) == 1
    assert res["sources"][0]["source_file"] == "FIT4201- Hệ thống nhúng.docx"


def test_cache_node_general_llm_preservation():
    cache = get_exact_cache()
    cache.clear()

    save_chat_node({
        "question": "Dijkstra là gì?",
        "answer": "Dijkstra là thuật toán tìm đường đi ngắn nhất.",
        "category": "GENERAL_LLM",
        "sources": [],
        "tool_intent": None,
        "cache_hit": False,
    })

    res = cache_node({"question": "Dijkstra là gì?"})
    assert res["cache_hit"] is True
    assert res["category"] == "GENERAL_LLM"
    assert res["sources"] == []


def test_cache_node_tool_action_preservation():
    cache = get_exact_cache()
    cache.clear()

    save_chat_node({
        "question": "Nhắc tôi ôn thi ngày mai",
        "answer": "Đã lên lịch nhắc nhở.",
        "category": "TOOL_ACTION",
        "sources": [],
        "tool_intent": "SET_REMINDER",
        "cache_hit": False,
    })

    res = cache_node({"question": "Nhắc tôi ôn thi ngày mai"})
    assert res["cache_hit"] is True
    assert res["category"] == "TOOL_ACTION"
    assert res["tool_intent"] == "SET_REMINDER"
