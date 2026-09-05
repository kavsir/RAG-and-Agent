"""
Evaluation API Router:
Cung cấp các read-only endpoints phục vụ Evaluation Dashboard.
Tuyệt đối không gọi LLM hay trigger benchmark lại.
"""
from typing import Optional
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from src.api.evaluation_service import (
    get_evaluation_summary,
    get_all_evaluation_cases,
    get_performance_summary,
    get_history_snapshots,
)

eval_router = APIRouter(prefix="/api/evaluation", tags=["Evaluation"])


@eval_router.get("/summary")
async def api_evaluation_summary():
    """Lấy tổng hợp chỉ số Acceptance Gates, Group Strength, Root Causes, Strengths/Weaknesses."""
    try:
        data = get_evaluation_summary()
        return JSONResponse(status_code=200, content=data)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@eval_router.get("/cases")
async def api_evaluation_cases(
    group: Optional[str] = Query(None, description="Lọc theo nhóm câu hỏi"),
    status: Optional[str] = Query(None, description="Lọc theo kết quả (PASS hoặc FAIL)"),
    root_cause: Optional[str] = Query(None, description="Lọc theo nguyên nhân lỗi"),
    search: Optional[str] = Query(None, description="Tìm kiếm theo ID, từ khóa câu hỏi, mã môn"),
):
    """Lấy danh sách chi tiết các test cases có hỗ trợ bộ lọc và tìm kiếm."""
    try:
        cases = get_all_evaluation_cases()

        if status:
            stat_upper = status.strip().upper()
            cases = [c for c in cases if c["result"] == stat_upper]

        if group:
            grp_upper = group.strip().upper()
            cases = [c for c in cases if c["group"].upper() == grp_upper]

        if root_cause:
            rc_upper = root_cause.strip().upper()
            cases = [c for c in cases if c["root_cause"].upper() == rc_upper]

        if search:
            kw = search.strip().lower()
            cases = [
                c for c in cases
                if (
                    kw in c["id"].lower()
                    or kw in c["question"].lower()
                    or kw in c["resolved_query"].lower()
                    or any(kw in src.lower() for src in c.get("expected_sources", []))
                )
            ]

        return JSONResponse(status_code=200, content={"total": len(cases), "cases": cases})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@eval_router.get("/performance")
async def api_evaluation_performance():
    """Lấy dữ liệu đo lường hiệu năng, latency từng workload, local pipeline và memory profile."""
    try:
        data = get_performance_summary()
        return JSONResponse(status_code=200, content=data)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@eval_router.get("/history")
async def api_evaluation_history():
    """Lấy danh sách các run snapshot trong lịch sử phục vụ vẽ biểu đồ Trend."""
    try:
        snapshots = get_history_snapshots()
        return JSONResponse(status_code=200, content={"count": len(snapshots), "snapshots": snapshots})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
