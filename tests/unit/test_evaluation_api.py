"""
Tests cho Evaluation Dashboard API Endpoints và Static Routes.
Kiểm tra:
1. GET /evaluation/ trả về 200 và nội dung HTML
2. GET /api/evaluation/summary trả về đầy đủ metadata, cards, groups, failure analysis
3. GET /api/evaluation/cases trả về 62 cases, kiểm tra các bộ lọc (filter by status, group, search)
4. GET /api/evaluation/performance trả về số liệu workload, local pipeline, memory
5. GET /api/evaluation/history trả về danh sách snapshot
6. Xử lý an toàn khi artifact bị thiếu (Missing artifact handling)
7. Xử lý an toàn khi JSON hỏng (Invalid JSON handling)
"""
from fastapi.testclient import TestClient

from src.api.main import app
from src.api import evaluation_service

client = TestClient(app)


def test_dashboard_static_route():
    """Kiểm tra route tĩnh GET /evaluation/ trả về mã 200 và HTML."""
    res = client.get("/evaluation/")
    assert res.status_code == 200
    assert "text/html" in res.headers.get("content-type", "")
    assert "Evaluation Dashboard" in res.text


def test_dashboard_redirect_route():
    """Kiểm tra GET /evaluation (không có slash) chuyển hướng đến /evaluation/."""
    res = client.get("/evaluation", follow_redirects=False)
    assert res.status_code in (301, 307, 302)
    assert "/evaluation/" in res.headers.get("location", "")


def test_api_evaluation_summary():
    """Kiểm tra GET /api/evaluation/summary trả về đầy đủ các chỉ số và schema chuẩn."""
    res = client.get("/api/evaluation/summary")
    assert res.status_code == 200
    data = res.json()

    # Metadata
    assert "metadata" in data
    assert data["metadata"]["benchmark_name"] == "Adversarial Benchmark V2"
    assert data["metadata"]["total_cases"] == 62
    assert "verdict" in data["metadata"]

    # Quality Cards
    assert "cards" in data
    cards = data["cards"]
    assert cards["router_accuracy"] >= 90.0
    assert cards["recall_at_5"] == 100.0
    assert cards["mrr"] > 0.9
    assert cards["abstention_accuracy"] == 100.0
    assert cards["critical_hallucinations"] == 0

    # Groups & Failure Analysis
    assert "groups" in data
    assert len(data["groups"]) >= 8
    assert "failure_analysis" in data
    assert len(data["failure_analysis"]) > 0

    # Strengths & Weaknesses
    assert "system_strengths" in data
    assert len(data["system_strengths"]) > 0
    assert "system_weaknesses" in data
    assert len(data["system_weaknesses"]) > 0


def test_api_evaluation_cases():
    """Kiểm tra GET /api/evaluation/cases trả về danh sách 62 cases và hỗ trợ bộ lọc."""
    # 1. Toàn bộ cases
    res = client.get("/api/evaluation/cases")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 62
    assert len(data["cases"]) == 62

    first = data["cases"][0]
    for required_key in ["id", "group", "question", "expected_category", "actual_category", "result", "root_cause"]:
        assert required_key in first

    # 2. Lọc theo status FAIL
    res_fail = client.get("/api/evaluation/cases?status=FAIL")
    assert res_fail.status_code == 200
    data_fail = res_fail.json()
    assert data_fail["total"] == 8
    assert all(c["result"] == "FAIL" for c in data_fail["cases"])

    # 3. Lọc theo group UNKNOWN_ENTITY
    res_unk = client.get("/api/evaluation/cases?group=UNKNOWN_ENTITY")
    assert res_unk.status_code == 200
    data_unk = res_unk.json()
    assert data_unk["total"] == 7
    assert all(c["group"] == "UNKNOWN_ENTITY" for c in data_unk["cases"])

    # 4. Tìm kiếm theo từ khóa mã môn
    res_search = client.get("/api/evaluation/cases?search=FIT4201")
    assert res_search.status_code == 200
    data_search = res_search.json()
    assert data_search["total"] > 0
    assert any("FIT4201" in c["question"] or "FIT4201" in str(c.get("expected_sources", [])) for c in data_search["cases"])


def test_api_evaluation_performance():
    """Kiểm tra GET /api/evaluation/performance trả về số liệu latency, microbenchmark và RAM."""
    res = client.get("/api/evaluation/performance")
    assert res.status_code == 200
    data = res.json()

    assert data["status"] in ("available", "unavailable")
    if data["status"] == "available":
        assert "latency" in data
        assert "local_pipeline" in data
        assert "memory" in data
        assert "reranker_enabled" in data


def test_api_evaluation_history():
    """Kiểm tra GET /api/evaluation/history trả về danh sách snapshot lịch sử."""
    res = client.get("/api/evaluation/history")
    assert res.status_code == 200
    data = res.json()
    assert "count" in data
    assert "snapshots" in data
    assert isinstance(data["snapshots"], list)


def test_missing_artifact_handling(monkeypatch, tmp_path):
    """Kiểm tra hệ thống xử lý an toàn khi artifact file bị thiếu mà không throw 500 crash."""
    non_existent = tmp_path / "does_not_exist.json"
    result = evaluation_service.load_json_artifact(non_existent)
    assert result is None

    # Performance summary fallback khi thiếu artifact
    monkeypatch.setattr(evaluation_service, "RESULTS_DIR", tmp_path)
    perf_fallback = evaluation_service.get_performance_summary()
    assert perf_fallback["status"] == "unavailable"
    assert "Telemetry unavailable" in perf_fallback["message"]


def test_invalid_json_handling(tmp_path):
    """Kiểm tra hệ thống xử lý an toàn khi file JSON bị hỏng / corrupt format."""
    corrupt_file = tmp_path / "corrupt.json"
    corrupt_file.write_text("{invalid json format...", encoding="utf-8")

    result = evaluation_service.load_json_artifact(corrupt_file)
    assert result is None
