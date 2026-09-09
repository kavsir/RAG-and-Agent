"""
Unit tests for Round A1.2: Remove Silent Result Truncation (Result Cardinality Contract).

Verifies the Four Hard Gates:
1. SILENT_RESULT_TRUNCATION = 0
2. ALL_SCOPE_INCOMPLETE_RESULT = 0
3. PRESENTATION_CARDINALITY_OVERRIDE = 0
4. USER_SCOPE_LOST_IN_PIPELINE = 0
"""
import pytest
from typing import Dict, Any

from src.agent_core.schemas import (
    ResultScope,
    AcademicCollectionResult,
    GoalFrame,
    GoalIntent,
    AcademicQueryPlan,
    EntityType,
    AcademicOperation,
)
from src.agent_core.academic_store import get_academic_store
from src.agent_core.query_planner import AcademicQueryPlanner, GoalPlanConsistencyValidator
from src.agent_core.semantic_goal_interpreter import get_semantic_goal_interpreter
from src.agent_core.presentation import format_curriculum_overview, format_semester_courses
from src.agent_core.loop import get_agent_loop
from src.ingestion.curriculum_parser import CurriculumParser


@pytest.fixture(scope="module")
def academic_store():
    store = get_academic_store()
    cnt = store.count_records()
    if cnt["curriculums"] == 0:
        parser = CurriculumParser()
        parser.ingest_all_curricula(store=store)
    return store


def test_gate1_all_scope_returns_100_percent_courses(academic_store):
    """
    Gate 1: SILENT_RESULT_TRUNCATION = 0.
    Chương trình CNTT K19 có 66 học phần.
    Truy vấn ALL phải trả về chính xác 66 học phần (không phải 25, 57 hay 100).
    """
    col_cntt = academic_store.get_curriculum_collection("K19", "Công nghệ thông tin", result_scope=ResultScope.ALL)
    assert col_cntt.total_count == 66
    assert col_cntt.returned_count == 66
    assert col_cntt.is_complete is True
    assert col_cntt.truncation_reason is None
    assert len(col_cntt.items) == 66

    col_khmt = academic_store.get_curriculum_collection("K19", "Khoa học máy tính", result_scope=ResultScope.ALL)
    assert col_khmt.total_count == 66
    assert col_khmt.returned_count == 66
    assert col_khmt.is_complete is True
    assert col_khmt.truncation_reason is None
    assert len(col_khmt.items) == 66


def test_gate2_all_scope_incomplete_result_invariant():
    """
    Gate 2: ALL_SCOPE_INCOMPLETE_RESULT = 0.
    Nếu result_scope == ALL mà returned_count != total_count, hợp đồng dữ liệu lập tức raise ValueError.
    """
    # Trường hợp hợp lệ
    valid_res = AcademicCollectionResult(
        items=[{"course_code": f"FIT{i}"} for i in range(10)],
        total_count=10,
        returned_count=10,
        result_scope=ResultScope.ALL,
    )
    assert valid_res.is_complete is True

    # Trường hợp vi phạm: thiếu bản ghi trong phạm vi ALL -> Phải ném ngoại lệ
    with pytest.raises(ValueError, match="ALL_SCOPE_INCOMPLETE_RESULT"):
        AcademicCollectionResult(
            items=[{"course_code": f"FIT{i}"} for i in range(5)],
            total_count=10,
            returned_count=5,
            result_scope=ResultScope.ALL,
        )


def test_gate3_presentation_cardinality_override_forbidden(academic_store):
    """
    Gate 3: PRESENTATION_CARDINALITY_OVERRIDE = 0.
    Presentation TUYỆT ĐỐI KHÔNG tự ý cắt [:25]. Phải render toàn bộ hợp đồng kết quả nhận được.
    """
    col = academic_store.get_curriculum_collection("K19", "Công nghệ thông tin", result_scope=ResultScope.ALL)
    formatted = format_curriculum_overview(col, cohort="K19", major="Công nghệ thông tin")

    # Kiểm tra số dòng trong bảng Markdown
    table_rows = [line for line in formatted.splitlines() if line.startswith("| Kỳ ") or line.startswith("| Đại cương ")]
    assert len(table_rows) == 66, f"Presentation rendered {len(table_rows)} rows instead of 66!"

    # Không chứa dòng cảnh báo cắt ngắn cũ
    assert "Hiển thị 25/" not in formatted
    assert "*(Hiển thị 25/66" not in formatted

    # Kiểm tra với TOP_K(10)
    col_top10 = academic_store.get_curriculum_collection(
        "K19", "Công nghệ thông tin", result_scope=ResultScope.TOP_K, limit=10
    )
    assert col_top10.returned_count == 10
    assert col_top10.is_complete is False
    formatted_top10 = format_curriculum_overview(col_top10, cohort="K19", major="Công nghệ thông tin")
    table_rows_top10 = [line for line in formatted_top10.splitlines() if line.startswith("| Kỳ ") or line.startswith("| Đại cương ")]
    assert len(table_rows_top10) == 10
    assert "Đang hiển thị 10/66 học phần" in formatted_top10


def test_gate4_user_scope_lost_in_pipeline():
    """
    Gate 4: USER_SCOPE_LOST_IN_PIPELINE = 0.
    GoalPlanConsistencyValidator phải phát hiện và ngăn chặn hạ cấp phạm vi ALL.
    """
    validator = GoalPlanConsistencyValidator()
    frame = GoalFrame(
        intent=GoalIntent.CURRICULUM_OVERVIEW,
        result_scope=ResultScope.ALL,
    )
    # Plan bị hạ cấp ngầm định sang TOP_K
    bad_plan = AcademicQueryPlan(
        plan_id="p1",
        subject_type=EntityType.CURRICULUM,
        operation=AcademicOperation.LIST_COURSES.value,
        data_capability="STRUCTURED_CURRICULUM",
        result_scope=ResultScope.TOP_K,
        limit=10,
    )
    errors = validator.validate(frame, bad_plan)
    assert any("USER_SCOPE_LOST_IN_PIPELINE" in e for e in errors)

    # Planner phải tự chữa lành (self-heal)
    planner = AcademicQueryPlanner()
    plan = planner.create_plan(frame)
    assert plan.result_scope == ResultScope.ALL


def test_scope_cues_interpretation():
    """Kiểm tra nhận diện đúng phạm vi từ ngữ cảnh người dùng."""
    interp = get_semantic_goal_interpreter()

    # ALL cues
    f_all = interp.interpret("hiển thị tất cả học phần của CNTT")
    assert f_all.result_scope == ResultScope.ALL

    f_all2 = interp.interpret("toàn bộ môn học ngành khoa học máy tính")
    assert f_all2.result_scope == ResultScope.ALL

    f_all_default = interp.interpret("chương trình đào tạo CNTT có những môn nào")
    assert f_all_default.result_scope == ResultScope.ALL

    # TOP_K cues
    f_top = interp.interpret("10 môn đầu của CNTT")
    assert f_top.result_scope == ResultScope.TOP_K
    assert f_top.limit == 10

    f_top2 = interp.interpret("top 5 môn học CNTT")
    assert f_top2.result_scope == ResultScope.TOP_K
    assert f_top2.limit == 5

    # SUMMARY cues
    f_summary = interp.interpret("tổng quan ngắn chương trình CNTT")
    assert f_summary.result_scope == ResultScope.SUMMARY
    assert f_summary.limit == 10

    # PAGE cues
    f_page = interp.interpret("trang 2 chương trình CNTT")
    assert f_page.result_scope == ResultScope.PAGE
    assert f_page.page == 2


def test_semester_filter_cardinality(academic_store):
    """Kiểm tra truy vấn học kỳ cụ thể trả về đủ 100% môn trong kỳ (không bị thiếu)."""
    col_sem5 = academic_store.get_curriculum_collection(
        "K19", "Khoa học máy tính", semester=5, result_scope=ResultScope.ALL
    )
    assert col_sem5.total_count == 5
    assert col_sem5.returned_count == 5
    assert col_sem5.is_complete is True

    formatted_sem = format_semester_courses(5, col_sem5, cohort="K19", major="Khoa học máy tính")
    lines = [line for line in formatted_sem.splitlines() if line.startswith("| `")]
    assert len(lines) == 5


def test_end_to_end_production_query_trace(academic_store):
    """
    End-to-End Test cho câu hỏi thực tế:
    'hiển thị tất cả học phần của CNTT'
    Xác minh tất cả các lớp trong pipeline:
    [GOAL] -> [PLAN] -> [STORE] -> [EXECUTOR] -> [PRESENTATION]
    đều đồng nhất báo cáo chính xác 66 học phần.
    """
    query = "hiển thị tất cả học phần của CNTT"

    # 1. [GOAL]
    interp = get_semantic_goal_interpreter()
    frame = interp.interpret(query)
    assert frame.result_scope == ResultScope.ALL
    assert frame.operation == AcademicOperation.LIST_COURSES.value

    # 2. [PLAN]
    planner = AcademicQueryPlanner()
    plan = planner.create_plan(frame)
    assert plan.result_scope == ResultScope.ALL
    assert plan.data_capability == "STRUCTURED_CURRICULUM"

    # 3. [STORE]
    cohort = plan.filters.get("cohort", "K19")
    major = plan.filters.get("major", "Công nghệ thông tin")
    col_res = academic_store.get_curriculum_collection(
        cohort=cohort,
        major=major,
        result_scope=plan.result_scope,
        limit=plan.limit,
        page=plan.page,
    )
    assert col_res.total_count == 66
    assert col_res.returned_count == 66
    assert col_res.is_complete is True
    assert col_res.result_scope == ResultScope.ALL

    # 4. [EXECUTOR / LOOP]
    loop = get_agent_loop()
    state = loop.run(query)
    assert state.status.value in ("COMPLETED", "PARTIAL")

    # 5. [PRESENTATION]
    ans = state.final_answer or ""
    table_rows = [line for line in ans.splitlines() if line.startswith("| Kỳ ") or line.startswith("| Đại cương ")]
    assert len(table_rows) == 66, f"Production query rendered {len(table_rows)} rows instead of 66!"
    assert "Hiển thị 25/" not in ans

    print(f"\n[GOAL] scope={frame.result_scope.value}")
    print(f"[PLAN] scope={plan.result_scope.value}")
    print(f"[STORE] total={col_res.total_count}, returned={col_res.returned_count}, is_complete={col_res.is_complete}")
    print(f"[EXECUTOR] state.status={state.status.value}")
    print(f"[PRESENTATION] table_rows={len(table_rows)}")
    print("VERDICT: RESULT_CARDINALITY_CONTRACT_ACCEPTED")
