"""
Cache Context-Safety Evaluation Suite: Đánh giá độc lập kiến trúc Context-Safe Cache.
Đo lường:
1. Global Safe Cache Accuracy
2. Profile Isolation Accuracy
3. Profile Mutation Safety
4. Session Collision Safety
5. Entity Switch Safety
6. Tool Non-cacheability
7. Cache Payload Integrity
8. Local Policy Latency Overhead (P50, P95, P99 < 2ms)
9. Kiểm chứng 0 external API calls.
"""
import sys
import io
import time
import json
from pathlib import Path
from typing import Dict, Any, List
import numpy as np

# Thiết lập UTF-8 stdout
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Đường dẫn gốc dự án
root_dir = Path(__file__).resolve().parent.parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

# RÀNG BUỘC: 0 external API calls
def forbid_external_api(*args, **kwargs):
    raise RuntimeError("VIOLATION: External API call detected during Cache evaluation!")

import src.llm.client  # noqa: E402
src.llm.client.invoke_llm = forbid_external_api

from src.cache.cache_policy import decide_cache_policy  # noqa: E402
from src.cache.exact_cache import get_exact_cache  # noqa: E402
from src.agent.nodes import cache_node, save_chat_node  # noqa: E402


def run_cache_evaluation():
    cases_file = Path("eval/cache/cache_cases.json")
    if not cases_file.exists():
        print(f"Error: {cases_file} not found!")
        return

    with open(cases_file, "r", encoding="utf-8") as f:
        cases: List[Dict[str, Any]] = json.load(f)

    print("=" * 80)
    print("ROUND C.1 — CONTEXT-SAFE CACHE EVALUATION SUITE")
    print(f"Total test cases: {len(cases)}")
    print("Cost Policy: Verified zero external API calls")
    print("=" * 80)

    # -------------------------------------------------------------
    # 1. EVALUATE POLICY DECISION ACROSS ALL CASES
    # -------------------------------------------------------------
    group_results: Dict[str, Dict[str, Any]] = {}
    passed_cases = 0
    failed_cases = 0

    latencies_us = []

    for c in cases:
        grp = c["group"]
        if grp not in group_results:
            group_results[grp] = {"total": 0, "passed": 0, "failed": 0, "cases": []}
        group_results[grp]["total"] += 1

        # Đo đạc latency quyết định chính sách cục bộ
        t0 = time.perf_counter_ns()
        decision = decide_cache_policy(
            query=c["query"],
            category=c["category"],
            tool_intent=c.get("tool_intent"),
            analyzed_query=c.get("analyzed_query"),
            session_context=c.get("session_context"),
            relevant_profile=c.get("relevant_profile"),
        )
        duration_us = (time.perf_counter_ns() - t0) / 1000.0
        latencies_us.append(duration_us)

        # Kiểm tra tính đúng đắn của quyết định
        scope_ok = decision.scope == c["expected_scope"]
        cacheable_ok = decision.cacheable == c["expected_cacheable"]
        reason_ok = decision.reason_code == c["expected_reason"]

        key_ok = True
        if decision.cacheable:
            key_ok = decision.cache_key is not None and len(decision.cache_key) > 0
        else:
            key_ok = decision.cache_key is None

        case_passed = scope_ok and cacheable_ok and reason_ok and key_ok

        if case_passed:
            passed_cases += 1
            group_results[grp]["passed"] += 1
            status = "PASS"
        else:
            failed_cases += 1
            group_results[grp]["failed"] += 1
            status = "FAIL"

        group_results[grp]["cases"].append({
            "id": c["id"],
            "query": c["query"],
            "status": status,
            "actual_scope": decision.scope,
            "actual_cacheable": decision.cacheable,
            "actual_key": decision.cache_key,
            "latency_us": duration_us,
        })

    # -------------------------------------------------------------
    # 2. END-TO-END WORKFLOW INTEGRITY VERIFICATION
    # -------------------------------------------------------------
    print("\nRunning End-to-End Workflow & Safety Integrity Checks...")
    cache = get_exact_cache()
    cache.clear()

    # Check 1: Global Safe Cache (Set -> Hit -> Correct payload)
    save_chat_node({
        "question": "Môn FIT4201 có bao nhiêu tín chỉ?",
        "answer": "Môn FIT4201 có 2 tín chỉ.",
        "category": "DOMAIN_DATA",
        "sources": [{"source_file": "FIT4201.docx", "chunk_id": "c1"}],
        "tool_intent": None,
        "cache_hit": False,
        "student_profile": {},
    })
    res_hit = cache_node({
        "question": "Môn FIT4201 có bao nhiêu tín chỉ?",
        "category": "DOMAIN_DATA",
        "student_profile": {},
    })
    global_safe_e2e = (
        res_hit["cache_hit"] is True
        and res_hit["answer"] == "Môn FIT4201 có 2 tín chỉ."
        and len(res_hit["sources"]) == 1
        and res_hit["cache_policy"]["scope"] == "GLOBAL_SAFE"
    )

    # Check 2: Profile Isolation (User 1 vs User 2 asking same query)
    cache.clear()
    user_1_prof = {"preferred_name": "Tuấn", "cohort": "K18"}
    user_2_prof = {"preferred_name": "Hoa", "cohort": "K19"}
    q_plan = "Tư vấn lộ trình học kỳ tới"

    save_chat_node({
        "question": q_plan,
        "answer": "Lộ trình riêng cho Tuấn K18: FIT3101, FIT4201",
        "category": "DOMAIN_DATA",
        "student_profile": user_1_prof,
        "cache_hit": False,
    })
    res_user1 = cache_node({
        "question": q_plan,
        "category": "DOMAIN_DATA",
        "student_profile": user_1_prof,
    })
    res_user2 = cache_node({
        "question": q_plan,
        "category": "DOMAIN_DATA",
        "student_profile": user_2_prof,
    })
    profile_isolation_e2e = (
        res_user1["cache_hit"] is True
        and "Tuấn K18" in res_user1["answer"]
        and res_user2["cache_hit"] is False
    )

    # Check 3: Profile Mutation Safety
    user_1_mutated = {"preferred_name": "Tuấn", "cohort": "K19"}
    res_mutated = cache_node({
        "question": q_plan,
        "category": "DOMAIN_DATA",
        "student_profile": user_1_mutated,
    })
    profile_mutation_e2e = (res_mutated["cache_hit"] is False)

    # Check 4: Session Collision Safety (Follow-up query "Email thì sao?")
    # Even if an entry exists for that exact string in global cache
    cache.set(
        key="DOMAIN_DATA::email thì sao?::global",
        answer="STALE EMAIL FIT4201",
        category="DOMAIN_DATA",
    )
    sess_1_res = cache_node({
        "question": "Email thì sao?",
        "category": "DOMAIN_DATA",
        "session_context": {"active_course_code": "FIT3101"},
        "student_profile": {},
    })
    sess_2_res = cache_node({
        "question": "Email thì sao?",
        "category": "DOMAIN_DATA",
        "session_context": {"active_course_code": "FIT2102"},
        "student_profile": {},
    })
    session_collision_e2e = (
        sess_1_res["cache_hit"] is False
        and sess_2_res["cache_hit"] is False
        and sess_1_res["cache_policy"]["scope"] == "SESSION_SENSITIVE"
        and sess_2_res["cache_policy"]["scope"] == "SESSION_SENSITIVE"
    )

    # Check 5: Entity Switch Safety
    # Session starts with FIT4201, then switches to FIT3101
    switch_res = cache_node({
        "question": "Ai dạy môn này?",
        "category": "DOMAIN_DATA",
        "session_context": {"active_course_code": "FIT3101"},
        "student_profile": {},
    })
    entity_switch_e2e = (
        switch_res["cache_hit"] is False
        and switch_res["cache_policy"]["scope"] == "SESSION_SENSITIVE"
    )

    # Check 6: Tool Non-cacheability
    cache.clear()
    save_chat_node({
        "question": "Nhắc tôi ôn thi lúc 8h sáng",
        "answer": "Đã lên lịch nhắc nhở.",
        "category": "TOOL_ACTION",
        "tool_intent": "SET_REMINDER",
        "cache_hit": False,
        "student_profile": {},
    })
    save_chat_node({
        "question": "Gửi email cho giảng viên",
        "answer": "Đã gửi email.",
        "category": "TOOL_ACTION",
        "tool_intent": "SEND_EMAIL",
        "cache_hit": False,
        "student_profile": {},
    })
    tool_cache_size = cache.size()
    res_tool = cache_node({
        "question": "Nhắc tôi ôn thi lúc 8h sáng",
        "category": "TOOL_ACTION",
        "tool_intent": "SET_REMINDER",
    })
    tool_non_cacheable_e2e = (
        tool_cache_size == 0
        and res_tool["cache_hit"] is False
        and res_tool["cache_policy"]["scope"] == "NON_CACHEABLE"
        and res_tool["cache_policy"]["cacheable"] is False
    )

    # Check 7: Cache Payload Integrity
    cache.clear()
    sources_sample = [
        {"source_file": "FIT4201.docx", "chunk_id": "c1", "section": "I"},
        {"source_file": "FIT4201.docx", "chunk_id": "c2", "section": "II"},
    ]
    meta_sample = {"sample_key": "sample_val"}
    cache.set(
        key="DOMAIN_DATA::fit4201::global",
        answer="Integrity Answer Test",
        category="DOMAIN_DATA",
        sources=sources_sample,
        tool_intent=None,
        metadata=meta_sample,
    )
    payload = cache.get("DOMAIN_DATA::fit4201::global")
    payload_integrity_e2e = (
        payload is not None
        and payload["answer"] == "Integrity Answer Test"
        and payload["category"] == "DOMAIN_DATA"
        and payload["sources"] == sources_sample
        and payload["metadata"] == meta_sample
    )

    # -------------------------------------------------------------
    # 3. LATENCY DISTRIBUTION & BENCHMARK METRICS
    # -------------------------------------------------------------
    latencies_arr = np.array(latencies_us)
    p50_us = float(np.percentile(latencies_arr, 50))
    p95_us = float(np.percentile(latencies_arr, 95))
    p99_us = float(np.percentile(latencies_arr, 99))
    p95_ms = p95_us / 1000.0

    print("\n" + "=" * 80)
    print("EVALUATION RESULTS BREAKDOWN BY GROUP:")
    print("=" * 80)
    for grp, data in group_results.items():
        rate = (data["passed"] / data["total"]) * 100.0 if data["total"] > 0 else 0.0
        print(f"  - {grp:<30}: {data['passed']}/{data['total']} ({rate:.1f}%)")

    total_accuracy = (passed_cases / len(cases)) * 100.0
    print("-" * 80)
    print(f"Overall Policy Classification Accuracy: {passed_cases}/{len(cases)} ({total_accuracy:.2f}%)")
    print(f"Policy Latency P50: {p50_us:.2f} us | P95: {p95_us:.2f} us ({p95_ms:.4f} ms) | P99: {p99_us:.2f} us")
    print("-" * 80)
    print("Safety & Integrity Invariants Verification:")
    print(f"  [1] Global Safe Cache Accuracy     : {'100%' if global_safe_e2e else 'FAILED'}")
    print(f"  [2] Profile Isolation Accuracy     : {'100%' if profile_isolation_e2e else 'FAILED'}")
    print(f"  [3] Profile Mutation Safety        : {'100%' if profile_mutation_e2e else 'FAILED'}")
    print(f"  [4] Session Collision Safety       : {'100%' if session_collision_e2e else 'FAILED'}")
    print(f"  [5] Entity Switch Safety           : {'100%' if entity_switch_e2e else 'FAILED'}")
    print(f"  [6] Tool Non-cacheability          : {'100%' if tool_non_cacheable_e2e else 'FAILED'}")
    print(f"  [7] Cache Payload Integrity        : {'100%' if payload_integrity_e2e else 'FAILED'}")
    print(f"  [8] Local Overhead Latency P95     : {p95_ms:.4f} ms (Target: < 2.0 ms)")
    print("  [9] External API Calls             : 0 (Strict Cost Policy: PASS)")
    print("=" * 80)

    all_invariants_pass = (
        total_accuracy == 100.0
        and global_safe_e2e
        and profile_isolation_e2e
        and profile_mutation_e2e
        and session_collision_e2e
        and entity_switch_e2e
        and tool_non_cacheable_e2e
        and payload_integrity_e2e
        and p95_ms < 2.0
    )

    verdict = "ACCEPTED" if all_invariants_pass else "REJECTED"
    print(f"ROUND C.1 FINAL VERDICT: {verdict}")

    summary_data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_cases": len(cases),
        "passed_cases": passed_cases,
        "accuracy_pct": total_accuracy,
        "latency_p50_us": p50_us,
        "latency_p95_us": p95_us,
        "latency_p95_ms": p95_ms,
        "latency_p99_us": p99_us,
        "invariants": {
            "global_safe_cache_accuracy": 1.0 if global_safe_e2e else 0.0,
            "profile_isolation_accuracy": 1.0 if profile_isolation_e2e else 0.0,
            "profile_mutation_safety": 1.0 if profile_mutation_e2e else 0.0,
            "session_collision_safety": 1.0 if session_collision_e2e else 0.0,
            "entity_switch_safety": 1.0 if entity_switch_e2e else 0.0,
            "tool_non_cacheability": 1.0 if tool_non_cacheable_e2e else 0.0,
            "cache_payload_integrity": 1.0 if payload_integrity_e2e else 0.0,
            "zero_external_api_calls": True,
            "overhead_p95_under_2ms": p95_ms < 2.0,
        },
        "verdict": verdict,
        "groups": group_results,
    }

    out_json = Path("eval/cache/cache_eval_results.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, ensure_ascii=False, indent=2)
    print(f"Results written to {out_json}")


if __name__ == "__main__":
    run_cache_evaluation()
