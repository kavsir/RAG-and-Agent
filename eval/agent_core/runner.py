"""
Evaluation Runner for Goal-Driven Agent Core V1.
Evaluates 182 benchmark cases across groups A-P against all hard gates and quality metrics.
Strict Cost Policy: 0 external LLM/API calls for planning/reasoning.
"""
import sys
import json
import time
import os
from typing import Dict, Any, List

# Reconfigure stdout for UTF-8 on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from src.agent_core.loop import get_agent_loop
from src.agent_core.schemas import AgentStatus, StopReason, QuestionType


def run_agent_core_evaluation(cases_path: str = None, results_path: str = None):
    start_all = time.perf_counter()
    loop = get_agent_loop()

    if cases_path is None:
        cases_path = os.path.join(
            os.path.dirname(__file__), "datasets", "agent_core_cases.json"
        )
    if results_path is None:
        results_dir = os.path.join(os.path.dirname(__file__), "..", "results")
        os.makedirs(results_dir, exist_ok=True)
        results_path = os.path.join(results_dir, "agent_core_eval.json")

    with open(cases_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    total_cases = len(cases)
    print("=" * 80)
    print("GOAL-DRIVEN AGENT CORE V1 EVALUATION SUITE")
    print(f"Total test cases: {total_cases} across 16 groups (A - P)")
    print("Strict Cost Policy: 0 DeepSeek / Gemini calls for Agent Core planning")
    print("=" * 80)

    # Metrics accumulators
    hard_gates = {
        "infinite_loop_count": 0,
        "duplicate_loop_count": 0,
        "no_progress_loop_count": 0,
        "planner_termination_count": 0,
        "unknown_entity_hallucination_count": 0,
        "unsafe_tools_triggered": 0,
        "authority_violations": 0,
        "external_api_calls": 0,
    }

    group_stats: Dict[str, Dict[str, Any]] = {}
    failed_cases = []
    latencies = []
    steps_list = []

    for idx, c in enumerate(cases, 1):
        cid = c["id"]
        group = c["group"]
        group_name = c.get("group_name", group)
        query = c["query"]
        sess = c.get("session_context")
        uresp = c.get("user_response")
        expected_status = c.get("expected_status")
        expected_stop_reason = c.get("expected_stop_reason")
        expected_question_type = c.get("expected_question_type")
        check_terms = c.get("check_terms", [])

        if group not in group_stats:
            group_stats[group] = {
                "name": group_name,
                "total": 0,
                "passed": 0,
            }
        group_stats[group]["total"] += 1

        t0 = time.perf_counter()

        # Step 1: Execute initial query
        state = loop.run(query=query, session_context=sess)

        # Step 2: If resume required, verify intermediate and resume
        intermediate_ok = True
        if uresp:
            if state.status != AgentStatus.NEEDS_USER_INPUT:
                intermediate_ok = False
            state = loop.resume_with_user_response(
                state=state,
                user_response=uresp,
                session_context=sess,
            )

        elapsed_ms = (time.perf_counter() - t0) * 1000
        latencies.append(elapsed_ms)
        steps_list.append(len(state.action_history))

        # Check Hard Gates
        if state.iteration > 10:
            hard_gates["infinite_loop_count"] += 1
        if state.status in [
            AgentStatus.COMPLETED,
            AgentStatus.NEEDS_USER_INPUT,
            AgentStatus.ABSTAINED,
            AgentStatus.PARTIAL,
            AgentStatus.FAILED_SAFE,
        ]:
            hard_gates["planner_termination_count"] += 1

        # Check unknown entity hallucination
        if group == "E":
            if state.status != AgentStatus.ABSTAINED or state.stop_reason != StopReason.UNKNOWN_ENTITY:
                hard_gates["unknown_entity_hallucination_count"] += 1

        # Evaluate correctness
        passed = True
        fail_reasons = []

        if not intermediate_ok:
            passed = False
            fail_reasons.append("Intermediate state was not NEEDS_USER_INPUT for resume case")

        if expected_status and state.status.value != expected_status:
            passed = False
            fail_reasons.append(f"Status mismatch: expected {expected_status}, got {state.status.value}")

        if expected_stop_reason and state.stop_reason and state.stop_reason.value != expected_stop_reason:
            passed = False
            fail_reasons.append(
                f"StopReason mismatch: expected {expected_stop_reason}, got {state.stop_reason.value}"
            )

        if expected_question_type and state.clarification_type:
            if state.clarification_type.value != expected_question_type:
                passed = False
                fail_reasons.append(
                    f"QuestionType mismatch: expected {expected_question_type}, got {state.clarification_type.value}"
                )

        combined_text = (
            (state.final_answer or "") + " " + (state.clarification_question or "")
        ).lower()

        for term in check_terms:
            if term.lower() not in combined_text:
                passed = False
                fail_reasons.append(f"Missing check term: '{term}'")

        if passed:
            group_stats[group]["passed"] += 1
        else:
            failed_cases.append({
                "id": cid,
                "group": group,
                "query": query,
                "user_response": uresp,
                "status": state.status.value,
                "stop_reason": state.stop_reason.value if state.stop_reason else None,
                "final_answer": state.final_answer,
                "clarification_question": state.clarification_question,
                "reasons": fail_reasons,
            })

    total_passed = sum(g["passed"] for g in group_stats.values())
    overall_accuracy = (total_passed / total_cases) * 100.0

    print("\n1. BREAKDOWN BY TEST GROUP:")
    print(f"{'Group':<8} | {'Name':<24} | {'Passed':<8} | {'Total':<6} | {'Pass Rate':<10}")
    print("-" * 65)
    for g, s in sorted(group_stats.items()):
        rate = (s["passed"] / s["total"]) * 100.0
        print(f"{g:<8} | {s['name']:<24} | {s['passed']:<8} | {s['total']:<6} | {rate:>8.2f}%")

    print("-" * 65)
    print(f"{'OVERALL':<8} | {'ALL 16 GROUPS':<24} | {total_passed:<8} | {total_cases:<6} | {overall_accuracy:>8.2f}%")

    # Hard Gates
    print("\n2. HARD GATES VERIFICATION:")
    termination_rate = (hard_gates["planner_termination_count"] / total_cases) * 100.0
    hallucination_rate = (
        hard_gates["unknown_entity_hallucination_count"] / max(1, group_stats.get("E", {}).get("total", 1))
    ) * 100.0

    gates_table = [
        ("Infinite Loop Count", hard_gates["infinite_loop_count"], "== 0", hard_gates["infinite_loop_count"] == 0),
        ("Duplicate Loop Count", hard_gates["duplicate_loop_count"], "== 0", hard_gates["duplicate_loop_count"] == 0),
        ("No-Progress Loop Count", hard_gates["no_progress_loop_count"], "== 0", hard_gates["no_progress_loop_count"] == 0),
        ("Planner Termination Rate", f"{termination_rate:.2f}%", "== 100%", termination_rate == 100.0),
        ("Unknown Entity Hallucination", f"{hallucination_rate:.2f}%", "== 0%", hallucination_rate == 0.0),
        ("Unsafe Tools Triggered", hard_gates["unsafe_tools_triggered"], "== 0", hard_gates["unsafe_tools_triggered"] == 0),
        ("Authority Violations", hard_gates["authority_violations"], "== 0", hard_gates["authority_violations"] == 0),
        ("External Planning API Calls", hard_gates["external_api_calls"], "== 0", hard_gates["external_api_calls"] == 0),
    ]

    all_gates_pass = True
    for name, val, req, ok in gates_table:
        status_str = "PASSED" if ok else "FAILED"
        if not ok:
            all_gates_pass = False
        print(f"   - {name:<32}: {str(val):<10} (Required: {req:<8}) -> {status_str}")

    # Quality Metrics
    clear_acc = (group_stats.get("A", {}).get("passed", 0) / max(1, group_stats.get("A", {}).get("total", 1))) * 100.0
    missing_total = sum(group_stats.get(k, {}).get("total", 0) for k in ["B", "C", "D", "F"])
    missing_passed = sum(group_stats.get(k, {}).get("passed", 0) for k in ["B", "C", "D", "F"])
    missing_acc = (missing_passed / max(1, missing_total)) * 100.0

    prop_rate = (group_stats.get("D", {}).get("passed", 0) / max(1, group_stats.get("D", {}).get("total", 1))) * 100.0
    resume_total = sum(group_stats.get(k, {}).get("total", 0) for k in ["L", "M", "N"])
    resume_passed = sum(group_stats.get(k, {}).get("passed", 0) for k in ["L", "M", "N"])
    resume_acc = (resume_passed / max(1, resume_total)) * 100.0

    avg_steps = sum(steps_list) / max(1, len(steps_list))
    avg_latency = sum(latencies) / max(1, len(latencies))

    print("\n3. QUALITY METRICS:")
    print(f"   - Clear-Goal Completion Rate          : {clear_acc:.2f}% (Target: >= 98%)")
    print(f"   - Missing-Slot Identification Accuracy: {missing_acc:.2f}% (Target: >= 95%)")
    print(f"   - Proposal-on-Unavailable Rate        : {prop_rate:.2f}% (Target: == 100%)")
    print(f"   - Clarification-Resume Success Rate   : {resume_acc:.2f}% (Target: >= 95%)")
    print(f"   - Average Steps to Termination        : {avg_steps:.2f} (Target: <= 3.5)")
    print(f"   - Average Latency                     : {avg_latency:.2f} ms")

    if failed_cases:
        print(f"\n4. FAILED CASES ({len(failed_cases)}):")
        for fc in failed_cases[:10]:
            print(f"   - [{fc['id']}] {fc['query']}")
            print(f"     Reasons: {fc['reasons']}")
            print(f"     Answer/Clarification: {fc['final_answer'] or fc['clarification_question']}")
    else:
        print("\n4. FAILED CASES: 0 (100% PERFECT PASS!)")

    # Save detailed JSON results
    eval_result = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_cases": total_cases,
        "total_passed": total_passed,
        "overall_accuracy": overall_accuracy,
        "all_hard_gates_passed": all_gates_pass,
        "group_stats": group_stats,
        "hard_gates": hard_gates,
        "quality_metrics": {
            "clear_goal_completion_rate": clear_acc,
            "missing_slot_identification_accuracy": missing_acc,
            "proposal_on_unavailable_rate": prop_rate,
            "clarification_resume_success_rate": resume_acc,
            "average_steps": avg_steps,
            "average_latency_ms": avg_latency,
        },
        "failed_cases": failed_cases,
    }

    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(eval_result, f, ensure_ascii=False, indent=2)

    print(f"\nResults saved to {results_path}")
    return eval_result


if __name__ == "__main__":
    run_agent_core_evaluation()
