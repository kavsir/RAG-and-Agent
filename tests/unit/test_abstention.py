import pytest
from src.rag.query_analyzer import analyze_query
from src.rag.hybrid_retriever import retrieve_candidates
from src.agent.graph import graph
from src.llm.client import set_mock_llm_handler
from src.memory.memory_manager import get_memory_manager
from src.cache.exact_cache import get_exact_cache


def mock_safe_llm(prompt, system_prompt=None):
    p = prompt.lower()
    if "kiểm định" in p or "tiêu chí" in p:
        return '{"valid": true}'
    return "Chưa tìm thấy đủ dữ liệu trong tài liệu hiện có để trả lời chính xác."


@pytest.fixture(autouse=True)
def setup_mock():
    set_mock_llm_handler(mock_safe_llm)
    get_memory_manager().clear()
    get_exact_cache().clear()
    yield
    set_mock_llm_handler(None)
    get_memory_manager().clear()
    get_exact_cache().clear()


@pytest.mark.parametrize("course_code", ["FIT9999", "XYZ1234", "FIT8888"])
def test_unknown_course_code_no_filter_drop(course_code):
    query = f"Học phần {course_code} có bao nhiêu tín chỉ?"
    analyzed = analyze_query(query)

    assert analyzed.course_code == course_code

    # Retrieval phải áp dụng filter và KHÔNG fallback bỏ filter để lấy nhầm môn khác
    candidates = retrieve_candidates(analyzed, top_k=10)
    assert len(candidates) == 0, f"Retrieval cho môn không tồn tại {course_code} phải trả về rỗng!"

    # Graph invocation phải trả về câu từ chối chuẩn mực và sources = []
    res = graph.invoke({"question": query})
    assert "chưa tìm thấy đủ dữ liệu" in res.get("answer", "").lower()
    assert res.get("sources") == [], f"Sources cho {course_code} phải rỗng, không được chứa môn khác!"
