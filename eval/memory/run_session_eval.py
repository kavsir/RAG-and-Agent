"""
Session Memory V2 Evaluation Suite: Đánh giá độc lập bộ nhớ phiên hội thoại có cấu trúc.
Đo lường độ chính xác phân giải thực thể, kế thừa mục tiêu, chuyển đổi thực thể,
cô lập đa phiên, an toàn câu hỏi mơ hồ, độ bền vững qua khởi động lại, và đo đạc độ trễ SQLite (Read/Write).
Đảm bảo 100% cục bộ, 0 cuộc gọi API bên ngoài.
"""
import sys
import io
import time
import json
from pathlib import Path
from typing import Dict, Any, List
import numpy as np

# Thiết lập UTF-8 stdout cho Windows console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Thêm đường dẫn gốc dự án vào sys.path
root_dir = Path(__file__).resolve().parent.parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

# Chặn tuyệt đối mọi cuộc gọi external LLM / API
def forbid_external_api(*args, **kwargs):
    raise RuntimeError("VIOLATION: External API call detected during Session Memory evaluation!")

import src.llm.client  # noqa: E402
src.llm.client.invoke_llm = forbid_external_api

from src.memory.sqlite_store import SQLiteSessionStore  # noqa: E402
from src.memory.session_memory import SessionMemoryService  # noqa: E402
from src.rag.query_analyzer import analyze_query  # noqa: E402
from src.router import get_router_service  # noqa: E402


def run_session_evaluation():
    cases_file = Path("eval/memory/session_cases.json")
    if not cases_file.exists():
        print(f"Error: {cases_file} not found!")
        return

    with open(cases_file, "r", encoding="utf-8") as f:
        scenarios: List[Dict[str, Any]] = json.load(f)

    total_turns = sum(len(s["turns"]) for s in scenarios)

    print("=" * 80)
    print("SESSION MEMORY V2 EVALUATION SUITE")
    print(f"Total scenarios: {len(scenarios)} | Total turns: {total_turns}")
    print("Strict Cost Policy: Verified zero external API calls")
    print("=" * 80)

    # Khởi tạo CSDL benchmark tạm thời để đo lường trong sạch
    bench_db_path = Path("runtime/eval_session_memory.db")
    if bench_db_path.exists():
        try:
            bench_db_path.unlink()
        except Exception:
            pass

    store = SQLiteSessionStore(db_path=bench_db_path)
    service = SessionMemoryService(store=store)
    router = get_router_service()

    # Đo độ trễ
    read_latencies = []
    write_latencies = []

    turn_results = []

    for scen in scenarios:
        scen_id = scen["id"]
        group = scen["group"]

        for turn_idx, turn in enumerate(scen["turns"]):
            session_id = turn["session_id"]
            user_msg = turn["user_message"]
            ai_resp = turn["ai_response"]
            analyzed_mock = turn.get("analyzed_mock", {})

            # Giả lập restart tiến trình nếu kịch bản yêu cầu
            if turn.get("simulate_restart"):
                store.close()
                store = SQLiteSessionStore(db_path=bench_db_path)
                service = SessionMemoryService(store=store)

            # 1. ĐO ĐỘ TRỄ ĐỌC TRẠNG THÁI (Session Read)
            t_read_start = time.perf_counter()
            current_state = service.get_session_state(session_id)
            session_ctx = current_state.to_context_dict()
            _ = service.get_recent_messages(session_id, k=5)
            read_lat_ms = (time.perf_counter() - t_read_start) * 1000
            read_latencies.append(read_lat_ms)

            # 2. PHÂN GIẢI NGỮ CẢNH VÀ THỰC THỂ (Entity & Target Resolution)
            resolved_code, resolved_target, res_source, unresolved_ref = service.resolve_context(
                conversation_id=session_id,
                current_query=user_msg,
            )

            # 3. PHÂN TÍCH QUERY TÍCH HỢP SESSION
            aq = analyze_query(
                query=user_msg,
                session_context=session_ctx,
            )

            # 4. KIỂM ĐỊNH ĐỊNH TUYẾN ROUTER V2 (Weak contract)
            router_decision = router.classify(
                query=user_msg,
                analyzed_query=session_ctx,
            )

            # Đánh giá tính đúng đắn của turn
            exp_code = turn.get("expected_resolved_code")
            exp_src = turn.get("expected_resolution_source")
            exp_unresolved = turn.get("expected_unresolved", False)
            exp_target = turn.get("expected_target")
            exp_cat = turn.get("expected_router_category")

            code_match = (resolved_code == exp_code) and (aq.course_code == exp_code)
            src_match = (res_source == exp_src) and (aq.resolution_source == exp_src)
            unres_match = (unresolved_ref == exp_unresolved) and (aq.unresolved_reference == exp_unresolved)

            target_match = True
            if exp_target:
                # Nếu kỳ vọng target cụ thể, kiểm tra resolved_target hoặc aq.targets
                target_match = (resolved_target == exp_target) or (exp_target in aq.targets)

            router_match = True
            if exp_cat:
                router_match = (router_decision.category == exp_cat)

            turn_passed = code_match and src_match and unres_match and target_match and router_match

            # 5. ĐO ĐỘ TRỄ GHI TRẠNG THÁI (Session Write)
            t_write_start = time.perf_counter()
            service.update_turn(
                conversation_id=session_id,
                user_message=user_msg,
                ai_message=ai_resp,
                analyzed_query=analyzed_mock,
            )
            write_lat_ms = (time.perf_counter() - t_write_start) * 1000
            write_latencies.append(write_lat_ms)

            turn_record = {
                "scenario_id": scen_id,
                "group": group,
                "turn_index": turn_idx,
                "session_id": session_id,
                "user_message": user_msg,
                "expected_code": exp_code,
                "actual_code": resolved_code,
                "expected_source": exp_src,
                "actual_source": res_source,
                "expected_unresolved": exp_unresolved,
                "actual_unresolved": unresolved_ref,
                "expected_target": exp_target,
                "actual_target": resolved_target or (aq.targets[0] if aq.targets else None),
                "expected_router_cat": exp_cat,
                "actual_router_cat": router_decision.category,
                "read_lat_ms": round(read_lat_ms, 3),
                "write_lat_ms": round(write_lat_ms, 3),
                "code_match": code_match,
                "src_match": src_match,
                "unres_match": unres_match,
                "target_match": target_match,
                "router_match": router_match,
                "passed": turn_passed,
            }
            turn_results.append(turn_record)

    # TÍNH TOÁN CÁC CHỈ SỐ THEO NHÓM VÀ TOÀN DIỆN
    def calc_accuracy(items):
        if not items:
            return 0.0, 0, 0
        correct = sum(1 for x in items if x["passed"])
        return round((correct / len(items)) * 100, 2), correct, len(items)

    total_acc, total_corr, total_cnt = calc_accuracy(turn_results)

    # 1. Follow-up Entity Resolution: Các lượt kế thừa từ session (source == "SESSION")
    followup_items = [r for r in turn_results if r["expected_source"] == "SESSION"]
    followup_acc, followup_corr, followup_cnt = calc_accuracy(followup_items)

    # 2. Target Resolution: Các lượt có kiểm tra target
    target_items = [r for r in turn_results if r["expected_target"] is not None]
    target_acc = round((sum(1 for r in target_items if r["target_match"]) / len(target_items)) * 100, 2) if target_items else 100.0

    # 3. Entity Switching: Nhóm entity_switching + turn 2 nhóm restart_persistence
    switch_items = [r for r in turn_results if r["group"] == "entity_switching" or (r["group"] == "restart_persistence" and r["scenario_id"] == "scen-g-02")]
    switch_acc, switch_corr, switch_cnt = calc_accuracy(switch_items)

    # 4. Cross-session Isolation: Nhóm cross_session_isolation
    iso_items = [r for r in turn_results if r["group"] == "cross_session_isolation"]
    iso_acc, iso_corr, iso_cnt = calc_accuracy(iso_items)

    # 5. Ambiguity Safety: Nhóm ambiguous_reference
    ambig_items = [r for r in turn_results if r["group"] == "ambiguous_reference"]
    ambig_acc, ambig_corr, ambig_cnt = calc_accuracy(ambig_items)

    # 6. Restart Persistence: Nhóm restart_persistence
    restart_items = [r for r in turn_results if r["group"] == "restart_persistence"]
    restart_acc, restart_corr, restart_cnt = calc_accuracy(restart_items)

    # 7. Router V2 Regression Accuracy: Toàn bộ 50 lượt
    router_acc = round((sum(1 for r in turn_results if r["router_match"]) / len(turn_results)) * 100, 2)

    # Thống kê độ trễ
    def calc_stats(lat_list):
        arr = np.array(lat_list)
        return {
            "mean": round(float(np.mean(arr)), 2),
            "median": round(float(np.median(arr)), 2),
            "p95": round(float(np.percentile(arr, 95)), 2),
            "p99": round(float(np.percentile(arr, 99)), 2),
            "count": len(lat_list),
        }

    read_stats = calc_stats(read_latencies)
    write_stats = calc_stats(write_latencies)

    # IN BÁO CÁO NGHIỆM THU
    print("\n1. CHỈ SỐ NGHIỆM THU BỘ NHỚ PHIÊN (ACCEPTANCE GATES):")
    print(f"   - Follow-up Entity Resolution: {followup_corr}/{followup_cnt} ({followup_acc}%) [Gate: >= 90%, Preferred >= 95%]")
    print(f"   - Target Resolution Accuracy : {target_acc}% (Support: {len(target_items)}) [Gate: >= 90%]")
    print(f"   - Entity Switching Accuracy  : {switch_corr}/{switch_cnt} ({switch_acc}%) [Gate: >= 95%]")
    print(f"   - Cross-session Isolation    : {iso_corr}/{iso_cnt} ({iso_acc}%) [Gate: = 100%]")
    print(f"   - Ambiguity Safety Accuracy  : {ambig_corr}/{ambig_cnt} ({ambig_acc}%) [Gate: >= 90%]")
    print(f"   - Restart Persistence        : {restart_corr}/{restart_cnt} ({restart_acc}%) [Gate: = 100%]")
    print(f"   - Router V2 Compatibility    : {router_acc}% [Gate: >= 97%]")
    print(f"   - Overall Turns Passed       : {total_corr}/{total_cnt} ({total_acc}%)")

    print("\n2. ĐỘ TRỄ THAO TÁC CƠ SỞ DỮ LIỆU SQLITE (LATENCY PROFILING):")
    print(f"   - Session State Read  (P95): {read_stats['p95']} ms | Mean: {read_stats['mean']} ms | Median: {read_stats['median']} ms [Gate: < 10 ms]")
    print(f"   - Session State Write (P95): {write_stats['p95']} ms | Mean: {write_stats['mean']} ms | Median: {write_stats['median']} ms [Gate: < 10 ms]")

    failed_turns = [r for r in turn_results if not r["passed"]]
    if failed_turns:
        print(f"\n3. CÁC LƯỢT THẤT BẠI ({len(failed_turns)}):")
        for ft in failed_turns:
            print(f"   - [{ft['scenario_id']} T{ft['turn_index']}] '{ft['user_message']}' | Exp: code={ft['expected_code']}, src={ft['expected_source']} | Got: code={ft['actual_code']}, src={ft['actual_source']}")
    else:
        print("\n3. CÁC LƯỢT THẤT BẠI: 0 (100% PERFECT SCORE!)")

    # Lưu kết quả chi tiết
    out_file = Path("eval/results/session_memory_eval.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    summary_data = {
        "total_scenarios": len(scenarios),
        "total_turns": total_turns,
        "metrics": {
            "followup_resolution_acc": followup_acc,
            "target_resolution_acc": target_acc,
            "entity_switching_acc": switch_acc,
            "cross_session_isolation_acc": iso_acc,
            "ambiguity_safety_acc": ambig_acc,
            "restart_persistence_acc": restart_acc,
            "router_regression_acc": router_acc,
            "overall_accuracy": total_acc,
        },
        "latency": {
            "read": read_stats,
            "write": write_stats,
        },
        "failed_turns": failed_turns,
        "turn_results": turn_results,
    }
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, ensure_ascii=False, indent=2)

    print(f"\nDetailed evaluation results saved to {out_file}")


if __name__ == "__main__":
    run_session_evaluation()
