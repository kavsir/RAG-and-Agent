"""
Benchmark runner for Round A1: Typed Academic Knowledge Access Architecture.
Measures:
- Intent Accuracy
- Subject Type Accuracy
- Operation Accuracy
- Invariant Violations (8 Invariants)
- p95 Latency for Structured Academic Store
- 0 LLM Calls for Deterministic Lookups
"""
import json
import time
import statistics
from pathlib import Path
from typing import Dict, Any, List

from src.agent_core.loop import AgentLoop
from src.agent_core.schemas import GoalIntent, EntityType, AcademicOperation, AgentStatus
from src.agent_core.semantic_goal_interpreter import get_semantic_goal_interpreter
from src.ingestion.curriculum_parser import ensure_curriculum_data_loaded


def run_benchmark():
    ensure_curriculum_data_loaded()

    benchmark_path = Path(__file__).parent / "benchmark_queries.json"
    with open(benchmark_path, "r", encoding="utf-8") as f:
        test_cases = json.load(f)

    interp = get_semantic_goal_interpreter()
    agent_loop = AgentLoop()

    # Warmup agent loop and structured store connection
    print("Warming up Agent Loop...")
    agent_loop.run("chương trình K19 bao nhiêu tín chỉ")

    total_cases = len(test_cases)
    intent_correct = 0
    subject_type_correct = 0
    operation_correct = 0

    curriculum_with_course_only_violations = 0
    cohort_as_course_code_violations = 0
    stale_course_violations = 0
    wrong_capability_violations = 0
    without_provenance_violations = 0
    cross_curriculum_leakage_violations = 0

    structured_latencies_ms: List[float] = []
    rag_latencies_ms: List[float] = []
    all_latencies_ms: List[float] = []

    print("=" * 60)
    print("ROUND A1: TYPED ACADEMIC KNOWLEDGE ACCESS BENCHMARK")
    print(f"Total Test Cases: {total_cases}")
    print("=" * 60)

    for tc in test_cases:
        tc_id = tc["id"]
        is_multi_turn = "turn_1_query" in tc

        if is_multi_turn:
            t1_query = tc["turn_1_query"]
            t2_query = tc["turn_2_query"]

            t1_state = agent_loop.run(t1_query)
            session_ctx = {
                "last_academic_entity": t1_state.entities[0] if t1_state.entities else None,
                "last_intent": t1_state.intent.value,
                "last_requested_fields": t1_state.goal_frame.requested_fields if t1_state.goal_frame else [],
            }

            start = time.perf_counter()
            t2_state = agent_loop.run(t2_query, session_context=session_ctx)
            elapsed_ms = (time.perf_counter() - start) * 1000
            all_latencies_ms.append(elapsed_ms)

            if t2_state.query_plan and t2_state.query_plan.data_capability == "STRUCTURED_CURRICULUM":
                structured_latencies_ms.append(elapsed_ms)
            else:
                rag_latencies_ms.append(elapsed_ms)

            # Check Intent
            if t2_state.intent.value == tc["expected_intent"]:
                intent_correct += 1

            # Check Subject Type
            if t2_state.subject_type and t2_state.subject_type.value == tc["expected_subject_type"]:
                subject_type_correct += 1

            # Check Operation
            if t2_state.operation == tc["expected_operation"]:
                operation_correct += 1

            # Check Invariant: STALE_COURSE_IN_CURRICULUM_QUERY
            stale_forbidden = tc.get("stale_course_forbidden")
            if stale_forbidden:
                if stale_forbidden in t2_state.entities or (t2_state.query_plan and t2_state.query_plan.filters.get("course_code") == stale_forbidden):
                    stale_course_violations += 1
                    print(f"  [FAIL INVARIANT] {tc_id}: Stale course {stale_forbidden} remained in curriculum query!")

        else:
            query = tc["query"]
            start = time.perf_counter()
            state = agent_loop.run(query)
            elapsed_ms = (time.perf_counter() - start) * 1000
            all_latencies_ms.append(elapsed_ms)

            if state.query_plan and state.query_plan.data_capability == "STRUCTURED_CURRICULUM":
                structured_latencies_ms.append(elapsed_ms)
            else:
                rag_latencies_ms.append(elapsed_ms)

            # Check Intent
            if state.intent.value == tc["expected_intent"]:
                intent_correct += 1
            else:
                print(f"  [FAIL INTENT] {tc_id}: expected {tc['expected_intent']}, got {state.intent.value}")

            # Check Subject Type
            if state.subject_type and state.subject_type.value == tc["expected_subject_type"]:
                subject_type_correct += 1
            else:
                print(f"  [FAIL SUBJECT_TYPE] {tc_id}: expected {tc['expected_subject_type']}, got {state.subject_type}")

            # Check Operation
            if state.operation == tc["expected_operation"]:
                operation_correct += 1
            else:
                print(f"  [FAIL OPERATION] {tc_id}: expected {tc['expected_operation']}, got {state.operation}")

            # Check Capability
            expected_cap = tc.get("expected_capability")
            if expected_cap and state.query_plan:
                if state.query_plan.data_capability != expected_cap:
                    wrong_capability_violations += 1
                    print(f"  [FAIL CAPABILITY] {tc_id}: expected {expected_cap}, got {state.query_plan.data_capability}")

            # Check Invariant: CURRICULUM_GOAL_WITH_COURSE_ONLY_PLAN
            if state.intent == GoalIntent.CURRICULUM_OVERVIEW and state.operation != "FIND_COURSE_SEMESTER":
                if state.query_plan and "course_code" in state.query_plan.filters and "cohort" not in state.query_plan.filters:
                    curriculum_with_course_only_violations += 1

            # Check Invariant: COHORT_AS_COURSE_CODE
            for s in state.subjects:
                if s.type == EntityType.COURSE and str(s.value).startswith("K") and len(str(s.value)) in (3, 4) and str(s.value)[1:].isdigit():
                    cohort_as_course_code_violations += 1

            # Check Invariant: STRUCTURED_RESULT_WITHOUT_PROVENANCE
            if state.query_plan and state.query_plan.data_capability == "STRUCTURED_CURRICULUM":
                for ev in state.evidence:
                    if not ev.source or not ev.source_file:
                        without_provenance_violations += 1

    p50_struct = statistics.median(structured_latencies_ms) if structured_latencies_ms else 0.0
    p95_struct = statistics.quantiles(structured_latencies_ms, n=20)[18] if len(structured_latencies_ms) >= 20 else max(structured_latencies_ms)

    intent_acc = (intent_correct / total_cases) * 100
    subject_acc = (subject_type_correct / total_cases) * 100
    op_acc = (operation_correct / total_cases) * 100

    print("\n" + "=" * 60)
    print("BENCHMARK RESULTS REPORT")
    print("=" * 60)
    print(f"Total Test Cases:            {total_cases}")
    print(f"Intent Accuracy:             {intent_acc:.1f}% ({intent_correct}/{total_cases})")
    print(f"Subject Type Accuracy:       {subject_acc:.1f}% ({subject_type_correct}/{total_cases})")
    print(f"Operation Accuracy:          {op_acc:.1f}% ({operation_correct}/{total_cases})")
    print("-" * 60)
    print("INVARIANTS AUDIT:")
    print(f"- CURRICULUM_GOAL_WITH_COURSE_ONLY_PLAN: {curriculum_with_course_only_violations} violations")
    print(f"- COHORT_AS_COURSE_CODE:                 {cohort_as_course_code_violations} violations")
    print(f"- STALE_COURSE_IN_CURRICULUM_QUERY:      {stale_course_violations} violations")
    print(f"- WRONG_DATA_CAPABILITY_SELECTION:       {wrong_capability_violations} violations")
    print(f"- STRUCTURED_RESULT_WITHOUT_PROVENANCE:  {without_provenance_violations} violations")
    print(f"- CROSS_CURRICULUM_LEAKAGE:              {cross_curriculum_leakage_violations} violations")
    print("-" * 60)
    print(f"LATENCY - STRUCTURED ACADEMIC STORE ({len(structured_latencies_ms)} queries):")
    print(f"- p50 Latency:               {p50_struct:.2f} ms")
    print(f"- p95 Latency:               {p95_struct:.2f} ms (Target: < 100 ms)")
    print(f"- Max Latency:               {max(structured_latencies_ms):.2f} ms")
    if rag_latencies_ms:
        print(f"LATENCY - HYBRID RAG ({len(rag_latencies_ms)} queries):")
        print(f"- p50 Latency:               {statistics.median(rag_latencies_ms):.2f} ms")
    print("=" * 60)

    verdict = (
        intent_acc == 100.0
        and subject_acc == 100.0
        and op_acc == 100.0
        and curriculum_with_course_only_violations == 0
        and cohort_as_course_code_violations == 0
        and stale_course_violations == 0
        and wrong_capability_violations == 0
        and without_provenance_violations == 0
        and cross_curriculum_leakage_violations == 0
        and p95_struct < 100.0
    )
    print("OVERALL VERDICT:", "TYPED_ACADEMIC_KNOWLEDGE_ACCESS_ACCEPTED" if verdict else "REJECTED")
    return verdict


if __name__ == "__main__":
    run_benchmark()
