"""
Router V2 Evaluation Suite: Đánh giá độc lập hệ thống phân loại ý định cục bộ.
Đo lường độ chính xác trên tập Benchmark V2 (62 câu) và tập Holdout (41 câu),
kiểm chứng 0 cuộc gọi API bên ngoài, và đo đạc phân bố độ trễ (Fast-Path vs Semantic-Path).
"""
import sys
import io
import time
import json
from pathlib import Path
from typing import Dict, Any, List
import numpy as np

# Thiết lập UTF-8 stdout để tránh lỗi mã hóa trên Windows console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Thêm đường dẫn gốc dự án vào sys.path
root_dir = Path(__file__).resolve().parent.parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

# Chặn tuyệt đối mọi cuộc gọi external LLM / API trong suốt quá trình routing evaluation
def forbid_external_api(*args, **kwargs):
    raise RuntimeError("VIOLATION: External API call detected during Router evaluation!")

import src.llm.client  # noqa: E402
src.llm.client.invoke_llm = forbid_external_api

from src.router import get_router_service  # noqa: E402


def run_evaluation():
    cases_file = Path("eval/router/cases_v2_1.json")
    if not cases_file.exists():
        print(f"Error: {cases_file} not found!")
        return

    with open(cases_file, "r", encoding="utf-8") as f:
        cases: List[Dict[str, Any]] = json.load(f)

    print("=" * 80)
    print("ROUTER V2 EVALUATION SUITE")
    print(f"Total test cases: {len(cases)}")
    print("Strict Cost Policy: Verified zero external API calls")
    print("=" * 80)

    # Warmup Router Service (loads embedding model and encodes prototypes)
    print("Initializing RouterService (singleton)...")
    t0 = time.perf_counter()
    router = get_router_service()
    # 1 warmup classification
    _ = router.classify("Xin chào")
    init_time = (time.perf_counter() - t0) * 1000
    print(f"RouterService initialized in {init_time:.2f} ms.\n")

    results = []
    fast_path_latencies = []
    semantic_path_latencies = []

    for c in cases:
        q = c["question"]
        expected_cat = c["expected_category"]
        expected_tool = c.get("expected_tool_intent")
        ctx = c.get("analyzed_context")

        start = time.perf_counter()
        decision = router.classify(query=q, analyzed_query=ctx)
        latency_ms = (time.perf_counter() - start) * 1000

        if "FAST_PATH" in decision.decision_path:
            fast_path_latencies.append(latency_ms)
        else:
            semantic_path_latencies.append(latency_ms)

        cat_match = (decision.category == expected_cat)
        tool_match = True
        if expected_cat == "TOOL_ACTION" and expected_tool:
            tool_match = (decision.tool_intent == expected_tool)

        passed = cat_match and tool_match

        res_entry = {
            "id": c["id"],
            "dataset": c["dataset"],
            "type": c.get("type", "unknown"),
            "question": q,
            "expected_category": expected_cat,
            "expected_tool_intent": expected_tool,
            "predicted_category": decision.category,
            "predicted_tool_intent": decision.tool_intent,
            "decision_path": decision.decision_path,
            "reason_code": decision.reason_code,
            "confidence": decision.confidence,
            "latency_ms": round(latency_ms, 3),
            "passed": passed,
        }
        results.append(res_entry)

    # Metrics computation
    v2_cases = [r for r in results if r["dataset"] == "benchmark_v2"]
    ho_cases = [r for r in results if r["dataset"] == "holdout"]

    v2_correct = sum(1 for r in v2_cases if r["passed"])
    ho_correct = sum(1 for r in ho_cases if r["passed"])
    total_correct = sum(1 for r in results if r["passed"])

    v2_accuracy = (v2_correct / len(v2_cases)) * 100 if v2_cases else 0.0
    ho_accuracy = (ho_correct / len(ho_cases)) * 100 if ho_cases else 0.0
    total_accuracy = (total_correct / len(results)) * 100 if results else 0.0

    # Group metrics for Benchmark V2
    types_v2 = {}
    for r in v2_cases:
        t = r["type"]
        if t not in types_v2:
            types_v2[t] = {"total": 0, "correct": 0}
        types_v2[t]["total"] += 1
        if r["passed"]:
            types_v2[t]["correct"] += 1

    # Category metrics for V2
    v2_cats = {}
    for r in v2_cases:
        ec = r["expected_category"]
        if ec not in v2_cats:
            v2_cats[ec] = {"total": 0, "correct": 0}
        v2_cats[ec]["total"] += 1
        if r["passed"]:
            v2_cats[ec]["correct"] += 1

    # Confusion Matrix
    categories = ["DOMAIN_DATA", "GENERAL_LLM", "TOOL_ACTION"]
    conf_matrix = {ec: {pc: 0 for pc in categories} for ec in categories}
    for r in results:
        ec = r["expected_category"]
        pc = r["predicted_category"]
        if ec in conf_matrix and pc in conf_matrix[ec]:
            conf_matrix[ec][pc] += 1

    # Precision, Recall, F1 per category across all 103 cases
    prf_metrics = {}
    for cat in categories:
        tp = conf_matrix[cat][cat]
        fn = sum(conf_matrix[cat][other] for other in categories if other != cat)
        fp = sum(conf_matrix[other][cat] for other in categories if other != cat)
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0
        prf_metrics[cat] = {
            "precision": round(prec * 100, 2),
            "recall": round(rec * 100, 2),
            "f1": round(f1 * 100, 2),
            "support": tp + fn,
        }

    # Latency Stats
    def calc_stats(lat_list):
        if not lat_list:
            return {"mean": 0.0, "median": 0.0, "p95": 0.0, "p99": 0.0, "count": 0}
        arr = np.array(lat_list)
        return {
            "mean": round(float(np.mean(arr)), 2),
            "median": round(float(np.median(arr)), 2),
            "p95": round(float(np.percentile(arr, 95)), 2),
            "p99": round(float(np.percentile(arr, 99)), 2),
            "count": len(lat_list),
        }

    fast_stats = calc_stats(fast_path_latencies)
    semantic_stats = calc_stats(semantic_path_latencies)
    all_stats = calc_stats(fast_path_latencies + semantic_path_latencies)

    # Print Summary Report
    print("1. BENCHMARK V2 RESULTS (62 cases)")
    print(f"   Accuracy: {v2_correct}/{len(v2_cases)} ({v2_accuracy:.2f}%) [Baseline was 95.16%]")
    print("   Breakdown by Type:")
    for t, data in sorted(types_v2.items()):
        pct = (data["correct"] / data["total"]) * 100
        print(f"     - {t:<15}: {data['correct']:>2}/{data['total']:>2} ({pct:.1f}%)")
    print("   Category Pass Rates:")
    for c_name, data in sorted(v2_cats.items()):
        pct = (data["correct"] / data["total"]) * 100
        print(f"     - {c_name:<15}: {data['correct']:>2}/{data['total']:>2} ({pct:.1f}%)")

    print("\n2. HOLDOUT RESULTS (41 unseen cases)")
    print(f"   Accuracy: {ho_correct}/{len(ho_cases)} ({ho_accuracy:.2f}%)")
    ho_cats = {}
    for r in ho_cases:
        ec = r["expected_category"]
        if ec not in ho_cats:
            ho_cats[ec] = {"total": 0, "correct": 0}
        ho_cats[ec]["total"] += 1
        if r["passed"]:
            ho_cats[ec]["correct"] += 1
    for c_name, data in sorted(ho_cats.items()):
        pct = (data["correct"] / data["total"]) * 100
        print(f"     - {c_name:<15}: {data['correct']:>2}/{data['total']:>2} ({pct:.1f}%)")

    print(f"\n3. OVERALL ACCURACY (103 cases): {total_correct}/{len(results)} ({total_accuracy:.2f}%)")

    print("\n4. CONFUSION MATRIX (Expected rows -> Predicted cols):")
    header = f"{'':<15} | " + " | ".join(f"{c:>12}" for c in categories)
    print(header)
    print("-" * len(header))
    for ec in categories:
        row_str = f"{ec:<15} | " + " | ".join(f"{conf_matrix[ec][pc]:>12}" for pc in categories)
        print(row_str)

    print("\n5. PRECISION / RECALL / F1:")
    for cat, m in prf_metrics.items():
        print(f"   {cat:<15}: Precision={m['precision']:>5}%, Recall={m['recall']:>5}%, F1={m['f1']:>5}% (Support={m['support']})")

    print("\n6. LATENCY PROFILING:")
    print(f"   Fast-Path     (count={fast_stats['count']:>2}): Mean={fast_stats['mean']:>6.2f} ms | Median={fast_stats['median']:>6.2f} ms | P95={fast_stats['p95']:>6.2f} ms")
    print(f"   Semantic-Path (count={semantic_stats['count']:>2}): Mean={semantic_stats['mean']:>6.2f} ms | Median={semantic_stats['median']:>6.2f} ms | P95={semantic_stats['p95']:>6.2f} ms")
    print(f"   Overall       (count={all_stats['count']:>2}): Mean={all_stats['mean']:>6.2f} ms | Median={all_stats['median']:>6.2f} ms | P95={all_stats['p95']:>6.2f} ms")

    failed_cases = [r for r in results if not r["passed"]]
    if failed_cases:
        print(f"\n7. FAILED CASES ({len(failed_cases)}):")
        for fc in failed_cases:
            print(f"   - [{fc['id']}] Q: '{fc['question']}' | Exp: {fc['expected_category']}/{fc['expected_tool_intent']} | Got: {fc['predicted_category']}/{fc['predicted_tool_intent']} (Path: {fc['decision_path']}, Reason: {fc['reason_code']})")
    else:
        print("\n7. FAILED CASES: 0 (100% PERFECT SCORE!)")

    # Save to file
    out_file = Path("eval/results/router_v2_eval.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    summary_data = {
        "total_cases": len(cases),
        "benchmark_v2": {
            "total": len(v2_cases),
            "correct": v2_correct,
            "accuracy": v2_accuracy,
            "types": types_v2,
            "categories": v2_cats,
        },
        "holdout": {
            "total": len(ho_cases),
            "correct": ho_correct,
            "accuracy": ho_accuracy,
            "categories": ho_cats,
        },
        "overall": {
            "total": len(results),
            "correct": total_correct,
            "accuracy": total_accuracy,
            "confusion_matrix": conf_matrix,
            "prf_metrics": prf_metrics,
        },
        "latency": {
            "fast_path": fast_stats,
            "semantic_path": semantic_stats,
            "overall": all_stats,
        },
        "failed_cases": failed_cases,
        "results": results,
    }
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, ensure_ascii=False, indent=2)
    print(f"\nDetailed results saved to {out_file}")


if __name__ == "__main__":
    run_evaluation()
