from src.cache.exact_cache import ExactCache, get_exact_cache
from src.cache.cache_policy import (
    CacheScope,
    decide_cache_policy,
)
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

    # Delete operation
    assert cache.delete("Môn FIT4201 có mấy tín chỉ?") is True
    assert cache.size() == 0
    assert cache.get("Môn FIT4201 có mấy tín chỉ?") is None

    cache.clear()
    assert cache.size() == 0


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
    res = cache_node({
        "question": "  môn FIT4201 có bao nhiêu tín chỉ? ",
        "category": "DOMAIN_DATA",
    })
    assert res["cache_hit"] is True
    assert res["answer"] == "Môn FIT4201 có 2 tín chỉ."
    assert res["category"] == "DOMAIN_DATA"
    assert len(res["sources"]) == 1
    assert res["sources"][0]["source_file"] == "FIT4201- Hệ thống nhúng.docx"
    assert res["cache_policy"]["scope"] == CacheScope.GLOBAL_SAFE


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

    res = cache_node({
        "question": "Dijkstra là gì?",
        "category": "GENERAL_LLM",
    })
    assert res["cache_hit"] is True
    assert res["category"] == "GENERAL_LLM"
    assert res["sources"] == []
    assert res["cache_policy"]["scope"] == CacheScope.GLOBAL_SAFE


def test_cache_node_tool_action_non_cacheable():
    """RÀNG BUỘC C.1: Hành động tool tuyệt đối không được cache."""
    cache = get_exact_cache()
    cache.clear()

    # 1. Thử lưu một tool action SET_REMINDER
    save_chat_node({
        "question": "Nhắc tôi ôn thi ngày mai",
        "answer": "Đã lên lịch nhắc nhở lúc 08:00 ngày mai.",
        "category": "TOOL_ACTION",
        "sources": [],
        "tool_intent": "SET_REMINDER",
        "cache_hit": False,
    })

    # Bắt buộc cache size == 0 (không lưu tool response)
    assert cache.size() == 0

    # 2. Truy vấn lại qua cache_node -> phải MISS và scope NON_CACHEABLE
    res = cache_node({
        "question": "Nhắc tôi ôn thi ngày mai",
        "category": "TOOL_ACTION",
        "tool_intent": "SET_REMINDER",
    })
    assert res["cache_hit"] is False
    assert res["cache_policy"]["scope"] == CacheScope.NON_CACHEABLE
    assert res["cache_policy"]["cacheable"] is False
    assert res["cache_policy"]["reason_code"] == "TOOL_ACTION_MUTABLE"

    # 3. Thử lưu một tool action SEND_EMAIL
    save_chat_node({
        "question": "Gửi email cho thầy giảng viên",
        "answer": "Đã gửi email thành công.",
        "category": "TOOL_ACTION",
        "sources": [],
        "tool_intent": "SEND_EMAIL",
        "cache_hit": False,
    })
    assert cache.size() == 0


def test_cache_policy_decision_matrix():
    # 1. Global Safe
    dec1 = decide_cache_policy(
        query="Ngành Công nghệ thông tin học những gì?",
        category="DOMAIN_DATA",
    )
    assert dec1.cacheable is True
    assert dec1.scope == CacheScope.GLOBAL_SAFE
    assert dec1.profile_digest is None
    assert "::global" in dec1.cache_key

    # 2. Profile Scoped
    dec2 = decide_cache_policy(
        query="Kế hoạch học tập cho tôi",
        category="DOMAIN_DATA",
        relevant_profile={"preferred_name": "Tuấn", "cohort": "K19"},
    )
    assert dec2.cacheable is True
    assert dec2.scope == CacheScope.PROFILE_SCOPED
    assert dec2.profile_digest is not None
    assert f"::profile:{dec2.profile_digest}" in dec2.cache_key

    # 3. Session Sensitive - Followup question with active entity
    dec3 = decide_cache_policy(
        query="Email thì sao?",
        category="DOMAIN_DATA",
        session_context={"active_course_code": "FIT4201"},
    )
    assert dec3.cacheable is False
    assert dec3.scope == CacheScope.SESSION_SENSITIVE
    assert dec3.cache_key is None

    # 4. Session Sensitive - Pronoun reference
    dec4 = decide_cache_policy(
        query="Môn đó mấy tín chỉ?",
        category="DOMAIN_DATA",
    )
    assert dec4.cacheable is False
    assert dec4.scope == CacheScope.SESSION_SENSITIVE

    # 5. Non Cacheable - Tool intent
    dec5 = decide_cache_policy(
        query="Đặt lịch nhắc lúc 8h",
        category="TOOL_ACTION",
        tool_intent="SET_REMINDER",
    )
    assert dec5.cacheable is False
    assert dec5.scope == CacheScope.NON_CACHEABLE


def test_profile_mutation_and_isolation():
    """Kiểm tra Profile Mutation Safety và Profile Isolation."""
    cache = get_exact_cache()
    cache.clear()

    prof_a = {"preferred_name": "Tuấn", "cohort": "K18"}
    prof_b = {"preferred_name": "Phong", "cohort": "K18"}  # mutated name
    prof_c = {"preferred_name": "Tuấn", "cohort": "K19"}  # mutated cohort

    q = "Tư vấn lộ trình học kỳ tới"

    # User A (Tuấn, K18) hỏi và lưu cache
    save_chat_node({
        "question": q,
        "answer": "Chào Tuấn K18, lộ trình của bạn gồm...",
        "category": "DOMAIN_DATA",
        "student_profile": prof_a,
        "sources": [],
        "cache_hit": False,
    })

    # User A truy vấn lại -> HIT
    res_a = cache_node({
        "question": q,
        "category": "DOMAIN_DATA",
        "student_profile": prof_a,
    })
    assert res_a["cache_hit"] is True
    assert "Chào Tuấn K18" in res_a["answer"]

    # Profile mutation 1: tên đổi thành Phong -> MISS
    res_b = cache_node({
        "question": q,
        "category": "DOMAIN_DATA",
        "student_profile": prof_b,
    })
    assert res_b["cache_hit"] is False

    # Profile mutation 2: khóa đổi thành K19 -> MISS
    res_c = cache_node({
        "question": q,
        "category": "DOMAIN_DATA",
        "student_profile": prof_c,
    })
    assert res_c["cache_hit"] is False

    # Không có profile -> MISS
    res_none = cache_node({
        "question": q,
        "category": "DOMAIN_DATA",
        "student_profile": {},
    })
    assert res_none["cache_hit"] is False


def test_session_sensitive_bypass_followup():
    """RÀNG BUỘC C.1: Follow-up 'Email thì sao?' khi có active course tuyệt đối bypass cache."""
    cache = get_exact_cache()
    cache.clear()

    q_followup = "Email thì sao?"

    # Dù kẻ xấu cố tình lưu câu hỏi này vào cache
    cache.set(
        key="DOMAIN_DATA::email thì sao?::global",
        answer="Email giảng viên FIT4201 là gv@dainam.edu.vn",
        category="DOMAIN_DATA",
    )

    # Trong phiên làm việc có active_course_code
    res = cache_node({
        "question": q_followup,
        "category": "DOMAIN_DATA",
        "session_context": {"active_course_code": "FIT3101"},
        "student_profile": {},
    })

    # Phải MISS và bypass cache hoàn toàn
    assert res["cache_hit"] is False
    assert res["cache_policy"]["scope"] == CacheScope.SESSION_SENSITIVE
    assert res["cache_policy"]["cacheable"] is False
    assert "answer" not in res or res["answer"] == ""
