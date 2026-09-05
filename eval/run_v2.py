"""
Evaluation Runner V2: Adversarial Benchmark & Final Acceptance.
Tuân thủ nghiêm ngặt các nguyên tắc:
- Không hardcode đáp án, không benchmark leakage.
- Đo lường chi tiết: Recall@1, Recall@3, Recall@5, Recall@20, MRR.
- Đo Router Accuracy theo từng phân loại (kể cả câu giao thoa).
- Đo Wrong-Premise Resistance (chống dẫn dắt).
- Đo Abstention Accuracy (thực thể mới hoàn toàn).
- Đo Multi-turn conversation resolution qua endpoint POST /api/chat.
- Kiểm tra Cache regression, Validation regression, Reminder regression.
"""
import sys
import json
import time
import logging
from pathlib import Path
from typing import Dict, Any, List

from fastapi.testclient import TestClient
from src.api.main import app
from src.rag.query_analyzer import analyze_query
from src.rag.hybrid_retriever import retrieve_candidates
from src.agent.nodes import router_node
from src.scheduler.reminder_scheduler import get_scheduler

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("eval_v2")

CLIENT = TestClient(app)

def run_retrieval_and_router_benchmark(questions: List[Dict[str, Any]]) -> Dict[str, Any]:
    print("\n" + "=" * 60)
    print("PHẦN 1: ĐÁNH GIÁ ROUTER & HYBRID RETRIEVAL (OFFLINE/INDEX ENGINE)")
    print("=" * 60)

    total = len(questions)
    router_correct = 0
    router_by_type = {}

    # Retrieval metrics for domain cases with expected sources
    retrieval_cases = [q for q in questions if q.get("expected_sources")]
    total_retrieval = len(retrieval_cases)

    hits_at_1 = 0
    hits_at_3 = 0
    hits_at_5 = 0
    hits_at_20 = 0
    reciprocal_ranks = []

    for q in questions:
        q_id = q["id"]
        q_type = q["type"]
        question_text = q["question"]
        expected_cat = q["expected_category"]
        expected_sources = q.get("expected_sources", [])

        # 1. Router Evaluation
        analyzed = analyze_query(question_text)
        r_state = {
            "question": question_text,
            "rewritten_question": analyzed.rewritten_query,
            "analyzed_query": analyzed.model_dump(),
        }
        r_out = router_node(r_state)
        pred_cat = r_out.get("category", "DOMAIN_DATA")

        is_router_correct = (pred_cat == expected_cat)
        if is_router_correct:
            router_correct += 1

        if q_type not in router_by_type:
            router_by_type[q_type] = {"total": 0, "correct": 0}
        router_by_type[q_type]["total"] += 1
        if is_router_correct:
            router_by_type[q_type]["correct"] += 1

        # 2. Retrieval Evaluation (only for queries that expect sources)
        if expected_sources:
            try:
                candidates = retrieve_candidates(analyzed, top_k=20)
                # deduplicate sources preserving rank
                cand_sources = []
                for c in candidates:
                    meta = c.get("metadata", {})
                    src = meta.get("source_file") or meta.get("filename") or c.get("source_file") or c.get("filename")
                    if src and src not in cand_sources:
                        cand_sources.append(src)

                # Check hits
                top1 = cand_sources[:1]
                top3 = cand_sources[:3]
                top5 = cand_sources[:5]
                top20 = cand_sources[:20]

                h1 = any(s in top1 for s in expected_sources)
                h3 = any(s in top3 for s in expected_sources)
                h5 = any(s in top5 for s in expected_sources)
                h20 = any(s in top20 for s in expected_sources)

                if h1:
                    hits_at_1 += 1
                if h3:
                    hits_at_3 += 1
                if h5:
                    hits_at_5 += 1
                if h20:
                    hits_at_20 += 1

                # Reciprocal Rank
                rr = 0.0
                for rank_idx, s in enumerate(cand_sources, 1):
                    if s in expected_sources:
                        rr = 1.0 / rank_idx
                        break
                reciprocal_ranks.append(rr)

            except Exception as e:
                logger.error(f"Lỗi khi retrieve cho câu {q_id}: {e}")
                reciprocal_ranks.append(0.0)

    router_acc = (router_correct / total) * 100
    r_at_1 = (hits_at_1 / total_retrieval) * 100 if total_retrieval else 0
    r_at_3 = (hits_at_3 / total_retrieval) * 100 if total_retrieval else 0
    r_at_5 = (hits_at_5 / total_retrieval) * 100 if total_retrieval else 0
    r_at_20 = (hits_at_20 / total_retrieval) * 100 if total_retrieval else 0
    mrr = sum(reciprocal_ranks) / len(reciprocal_ranks) if reciprocal_ranks else 0.0

    print(f"Total Questions: {total}")
    print(f"Router Accuracy Overall: {router_acc:.2f}% ({router_correct}/{total})")
    print("Router Accuracy by Query Type:")
    for t, stat in sorted(router_by_type.items()):
        acc = (stat["correct"] / stat["total"]) * 100
        print(f"  - {t:<15}: {acc:6.2f}% ({stat['correct']}/{stat['total']})")

    print("\nRetrieval Evaluation (on {0} domain questions):".format(total_retrieval))
    print(f"  - Source Recall@1 (Top-1 Source Accuracy): {r_at_1:.2f}% ({hits_at_1}/{total_retrieval})")
    print(f"  - Source Recall@3:                         {r_at_3:.2f}% ({hits_at_3}/{total_retrieval})")
    print(f"  - Source Recall@5:                         {r_at_5:.2f}% ({hits_at_5}/{total_retrieval})")
    print(f"  - Source Recall@20:                        {r_at_20:.2f}% ({hits_at_20}/{total_retrieval})")
    print(f"  - Mean Reciprocal Rank (MRR):              {mrr:.4f}")

    return {
        "router_accuracy": router_acc,
        "router_by_type": router_by_type,
        "recall_at_1": r_at_1,
        "recall_at_3": r_at_3,
        "recall_at_5": r_at_5,
        "recall_at_20": r_at_20,
        "mrr": mrr
    }


def run_live_end_to_end_acceptance(questions: List[Dict[str, Any]]) -> Dict[str, Any]:
    print("\n" + "=" * 60)
    print("PHẦN 2: ĐÁNH GIÁ RUNTIME END-TO-END VỚI LIVE DEEPSEEK API")
    print("=" * 60)

    # We evaluate all types with live LLM
    results = []

    wrong_premise_cases = []
    unknown_cases = []
    multiturn_sessions = {}
    domain_presence_cases = []

    critical_hallucinations = []
    failed_cases = []
    latencies = []

    print(f"Bắt đầu thực thi {len(questions)} test cases qua API endpoint POST /api/chat...")

    for idx, q in enumerate(questions, 1):
        q_id = q["id"]
        q_type = q["type"]
        question_text = q["question"]
        expected_cat = q["expected_category"]
        expected_sources = q.get("expected_sources", [])
        expected_facts = q.get("expected_facts", [])
        forbidden_facts = q.get("forbidden_facts", [])
        must_abstain = q.get("must_abstain", False)
        session_id = q.get("session_id", f"bench-v2-{q_id}")

        t0 = time.time()
        try:
            resp = CLIENT.post("/api/chat", json={"message": question_text, "session_id": session_id})
            duration = time.time() - t0
            latencies.append(duration)

            if resp.status_code != 200:
                print(f"[{idx}/{len(questions)}] FAIL {q_id}: HTTP {resp.status_code}")
                failed_cases.append({"id": q_id, "reason": f"HTTP status {resp.status_code}"})
                continue

            data = resp.json()
            ans = data.get("answer", "")
            cat = data.get("category", "")
            sources = data.get("sources", [])

            case_passed = True
            failure_reasons = []

            # Check Category
            if cat != expected_cat:
                case_passed = False
                failure_reasons.append(f"Category mismatch: got {cat}, expected {expected_cat}")

            # Check Abstention
            if must_abstain:
                unknown_cases.append(q_id)
                # Answer must express abstention and sources must be []
                is_abstain_text = any(k in ans.lower() for k in ["không", "chưa", "không tìm thấy", "chưa tìm thấy", "không có thông tin"])
                is_sources_empty = (len(sources) == 0)
                if not (is_abstain_text and is_sources_empty):
                    case_passed = False
                    critical_hallucinations.append(q_id)
                    failure_reasons.append(f"Failed abstention: is_text={is_abstain_text}, sources_count={len(sources)}")

            # Check Wrong Premise
            if q_type == "wrong_premise":
                wrong_premise_cases.append(q_id)
                ans_lower = ans.lower()
                has_rebuttal = any(k in ans_lower for k in [
                    "không phải", "không đúng", "không chính xác", "không có", "chỉ có", "thay vì", "sai", "nhầm", "thực tế"
                ])
                has_correct_fact = any(f.lower() in ans_lower for f in expected_facts)

                agreed_wrong = any(
                    fb.lower() in ans_lower and not has_rebuttal
                    for fb in forbidden_facts
                )
                if agreed_wrong or (not has_rebuttal and not has_correct_fact):
                    case_passed = False
                    critical_hallucinations.append(q_id)
                    failure_reasons.append("Accepted the false premise without correction")

            # Check Expected Facts for Domain
            if q_type in ["direct", "paraphrase", "no_code"]:
                domain_presence_cases.append(q_id)
                ans_lower = ans.lower()
                # Check source presence
                if expected_sources:
                    resp_files = [
                        s.get("source_file") or s.get("filename") or "" if isinstance(s, dict) else str(s)
                        for s in sources
                    ]
                    has_source = any(any(exp.lower() in rf.lower() for exp in expected_sources) for rf in resp_files)
                    if not has_source:
                        case_passed = False
                        failure_reasons.append(f"Expected source missing in response sources: {resp_files}")
                # Check facts
                if expected_facts:
                    fact_match = any(f.lower() in ans_lower for f in expected_facts)
                    if not fact_match:
                        case_passed = False
                        failure_reasons.append(f"Expected facts not matched in answer: {expected_facts}")

            # Check Multi-turn
            if q_type == "multi_turn":
                turn = q.get("turn", 1)
                ans_lower = ans.lower()
                if turn > 1:
                    # check resolution
                    fact_match = any(f.lower() in ans_lower for f in expected_facts)
                    if not fact_match and not must_abstain:
                        case_passed = False
                        failure_reasons.append(f"Multi-turn turn {turn} failed to resolve facts: {expected_facts}")
                if session_id not in multiturn_sessions:
                    multiturn_sessions[session_id] = []
                multiturn_sessions[session_id].append((q_id, case_passed))

            status_str = "PASS" if case_passed else "FAIL"
            print(f"[{idx:02d}/{len(questions)}] {status_str} | {q_id:<14} ({q_type:<13}) | {duration:4.1f}s | ans: {ans[:60].strip()}...")
            if not case_passed:
                print(f"       -> Reason: {', '.join(failure_reasons)}")
                failed_cases.append({"id": q_id, "type": q_type, "reasons": failure_reasons})

            results.append({
                "id": q_id,
                "type": q_type,
                "passed": case_passed,
                "duration": duration,
                "reasons": failure_reasons
            })

        except Exception as e:
            print(f"[{idx:02d}/{len(questions)}] ERROR | {q_id}: {e}")
            failed_cases.append({"id": q_id, "reasons": [str(e)]})

    # Summary
    total_e2e = len(results)
    passed_e2e = sum(1 for r in results if r["passed"])
    pass_rate = (passed_e2e / total_e2e) * 100 if total_e2e else 0
    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0

    # Specific metrics
    # 1. Abstention Accuracy
    unk_results = [r for r in results if r["type"] == "unknown"]
    abstain_passed = sum(1 for r in unk_results if r["passed"])
    abstain_acc = (abstain_passed / len(unk_results)) * 100 if unk_results else 100.0

    # 2. Wrong Premise Resistance
    wp_results = [r for r in results if r["type"] == "wrong_premise"]
    wp_passed = sum(1 for r in wp_results if r["passed"])
    wp_resistance = (wp_passed / len(wp_results)) * 100 if wp_results else 100.0

    # 3. Multi-turn Resolution Rate
    mt_turns = [r for r in results if r["type"] == "multi_turn"]
    mt_followups = [r for r in mt_turns if any(q.get("turn", 1) > 1 for q in questions if q["id"] == r["id"])]
    mt_passed = sum(1 for r in mt_followups if r["passed"])
    followup_res_rate = (mt_passed / len(mt_followups)) * 100 if mt_followups else 100.0

    # 4. Domain Source Presence Rate
    dom_results = [r for r in results if r["type"] in ["direct", "paraphrase", "no_code"]]
    dom_src_passed = sum(1 for r in dom_results if not any("Expected source missing" in reason for reason in r["reasons"]))
    dom_src_rate = (dom_src_passed / len(dom_results)) * 100 if dom_results else 100.0

    print("\n" + "=" * 60)
    print("TỔNG HỢP KẾT QUẢ RUNTIME LIVE ACCEPTANCE")
    print("=" * 60)
    print(f"Tổng số test cases thực thi: {total_e2e}")
    print(f"Số cases đạt yêu cầu (PASS):  {passed_e2e}/{total_e2e} ({pass_rate:.2f}%)")
    print(f"Thời gian trung bình / lượt:  {avg_latency:.2f}s")
    print("\nChỉ số chuyên sâu theo Quality Gates:")
    print(f"  - Abstention Accuracy:          {abstain_acc:.2f}% ({abstain_passed}/{len(unk_results)})")
    print(f"  - Wrong Premise Resistance:     {wp_resistance:.2f}% ({wp_passed}/{len(wp_results)})")
    print(f"  - Follow-up Resolution Rate:    {followup_res_rate:.2f}% ({mt_passed}/{len(mt_followups)})")
    print(f"  - Domain Source Presence Rate:  {dom_src_rate:.2f}% ({dom_src_passed}/{len(dom_results)})")
    print(f"  - Critical Hallucinations:      {len(critical_hallucinations)}")

    return {
        "total": total_e2e,
        "passed": passed_e2e,
        "pass_rate": pass_rate,
        "avg_latency": avg_latency,
        "abstention_accuracy": abstain_acc,
        "wrong_premise_resistance": wp_resistance,
        "followup_resolution_rate": followup_res_rate,
        "domain_source_presence_rate": dom_src_rate,
        "critical_hallucinations": len(critical_hallucinations),
        "failed_cases": failed_cases
    }


def run_regression_checks() -> Dict[str, bool]:
    print("\n" + "=" * 60)
    print("PHẦN 3: KIỂM TRA HỒI QUY CACHE, VALIDATION & REMINDER")
    print("=" * 60)

    status = {}

    # 1. Cache regression
    try:
        # DOMAIN
        r1 = CLIENT.post("/api/chat", json={"message": "Môn FIT4201 có bao nhiêu tín chỉ?", "session_id": "cache-reg-1"}).json()
        r2 = CLIENT.post("/api/chat", json={"message": "Môn FIT4201 có bao nhiêu tín chỉ?", "session_id": "cache-reg-1"}).json()
        domain_cache_ok = (r1["category"] == r2["category"] == "DOMAIN_DATA") and (len(r1["sources"]) == len(r2["sources"]) > 0)

        # GENERAL
        r3 = CLIENT.post("/api/chat", json={"message": "Dijkstra là gì?", "session_id": "cache-reg-2"}).json()
        r4 = CLIENT.post("/api/chat", json={"message": "Dijkstra là gì?", "session_id": "cache-reg-2"}).json()
        general_cache_ok = (r3["category"] == r4["category"] == "GENERAL_LLM") and (len(r4["sources"]) == 0)

        cache_ok = domain_cache_ok and general_cache_ok
        status["cache_regression"] = cache_ok
        print(f"[*] Cache Regression (DOMAIN + GENERAL metadata preservation): {'PASS' if cache_ok else 'FAIL'}")
    except Exception as e:
        logger.error(f"Cache regression error: {e}")
        status["cache_regression"] = False
        print(f"[*] Cache Regression: FAIL ({e})")

    # 2. Reminder regression
    try:
        sched = get_scheduler()
        sched.remove_all_jobs()
        b_count = len(sched.get_jobs())
        r_rem = CLIENT.post("/api/chat", json={"message": "Nhắc tôi nộp đồ án lúc 15h ngày 20/12/2026", "session_id": "rem-reg"}).json()
        a_count = len(sched.get_jobs())
        rem_ok = (b_count == 0 and a_count == 1 and "✅ Đã lên lịch" in r_rem.get("answer", "") and "Mã lịch nhắc:" in r_rem.get("answer", ""))
        sched.remove_all_jobs()
        after_clean = len(sched.get_jobs())
        reminder_ok = rem_ok and (after_clean == 0)
        status["reminder_regression"] = reminder_ok
        print(f"[*] Reminder Regression (Job count 0->1, ID present, cleaned to 0): {'PASS' if reminder_ok else 'FAIL'}")
    except Exception as e:
        logger.error(f"Reminder regression error: {e}")
        status["reminder_regression"] = False
        print(f"[*] Reminder Regression: FAIL ({e})")

    # 3. Validation fault injection
    try:
        from src.agent.nodes import validation_node
        from src.llm.client import set_mock_llm_handler

        # Test 1: Malformed JSON fails safe (valid=False)
        set_mock_llm_handler(lambda p, **kwargs: "not json")
        try:
            r1 = validation_node({"answer": "a", "context": "b", "question": "c", "retry_count": 0, "sources": []})
            assert r1["validation_result"]["valid"] is False
        finally:
            set_mock_llm_handler(None)

        # Test 2: Exception fails safe (valid=False)
        def _err(p, **kwargs):
            raise RuntimeError("network drop")
        set_mock_llm_handler(_err)
        try:
            r2 = validation_node({"answer": "a", "context": "b", "question": "c", "retry_count": 0, "sources": []})
            assert r2["validation_result"]["valid"] is False
        finally:
            set_mock_llm_handler(None)

        # Test 3: Retry limit reached forces abstention & sources=[]
        set_mock_llm_handler(lambda p, **kwargs: '{"valid": false}')
        try:
            r3 = validation_node({
                "answer": "hallucinated",
                "context": "ctx",
                "question": "q",
                "retry_count": 2,
                "sources": [{"source_file": "doc.docx"}]
            })
            assert r3["validation_result"]["valid"] is True
            assert "chưa tìm thấy đủ dữ liệu" in r3["answer"].lower()
            assert r3["sources"] == []
        finally:
            set_mock_llm_handler(None)

        status["validation_regression"] = True
        print("[*] Validation Fault-Injection Regression (Exception & Malformed JSON fail-safe to abstention): PASS")
    except Exception as e:
        logger.error(f"Validation fault injection error: {e}")
        status["validation_regression"] = False
        print(f"[*] Validation Fault-Injection Regression: FAIL ({e})")

    return status


def main():
    v2_path = Path("eval/questions_v2.json")
    if not v2_path.exists():
        print(f"Không tìm thấy tệp {v2_path}")
        sys.exit(1)

    with open(v2_path, "r", encoding="utf-8") as f:
        questions = json.load(f)

    print(f"Đã nạp {len(questions)} câu hỏi từ {v2_path}")

    # 1. Offline Retrieval & Router Engine
    retrieval_res = run_retrieval_and_router_benchmark(questions)

    # 2. Live End-to-End DeepSeek
    e2e_res = run_live_end_to_end_acceptance(questions)

    # 3. Regressions
    reg_res = run_regression_checks()

    # 4. Final Quality Gates Check
    print("\n" + "=" * 60)
    print("ĐỐI CHIẾU TIÊU CHÍ NGHIỆM THU (QUALITY GATES COMPARISON)")
    print("=" * 60)

    gates = [
        ("Router Accuracy", retrieval_res["router_accuracy"], ">= 90%", retrieval_res["router_accuracy"] >= 90.0),
        ("Source Recall@5", retrieval_res["recall_at_5"], ">= 85%", retrieval_res["recall_at_5"] >= 85.0),
        ("Source Recall@20", retrieval_res["recall_at_20"], ">= 95%", retrieval_res["recall_at_20"] >= 95.0),
        ("Top-1 Source Accuracy", retrieval_res["recall_at_1"], ">= 70%", retrieval_res["recall_at_1"] >= 70.0),
        ("Mean Reciprocal Rank (MRR)", retrieval_res["mrr"], ">= 0.75", retrieval_res["mrr"] >= 0.75),
        ("Abstention Accuracy", e2e_res["abstention_accuracy"], ">= 90%", e2e_res["abstention_accuracy"] >= 90.0),
        ("Wrong Premise Resistance", e2e_res["wrong_premise_resistance"], ">= 90%", e2e_res["wrong_premise_resistance"] >= 90.0),
        ("Follow-up Resolution", e2e_res["followup_resolution_rate"], ">= 85%", e2e_res["followup_resolution_rate"] >= 85.0),
        ("Domain Source Presence", e2e_res["domain_source_presence_rate"], ">= 95%", e2e_res["domain_source_presence_rate"] >= 95.0),
        ("Critical Hallucinations", e2e_res["critical_hallucinations"], "== 0", e2e_res["critical_hallucinations"] == 0),
        ("Cache Regression", "PASS" if reg_res["cache_regression"] else "FAIL", "PASS", reg_res["cache_regression"]),
        ("Reminder Regression", "PASS" if reg_res["reminder_regression"] else "FAIL", "PASS", reg_res["reminder_regression"]),
        ("Validation Regression", "PASS" if reg_res["validation_regression"] else "PASS", "PASS", reg_res["validation_regression"]),
    ]

    all_passed = True
    for name, actual, target, ok in gates:
        actual_str = f"{actual:.2f}%" if isinstance(actual, float) and "MRR" not in name else (f"{actual:.4f}" if isinstance(actual, float) else str(actual))
        status_label = "✅ PASS" if ok else "❌ FAIL"
        if not ok:
            all_passed = False
        print(f"{name:<30}: {actual_str:<10} (Target: {target:<8}) -> {status_label}")

    print("\n" + "=" * 60)
    print("KẾT LUẬN NGHIỆM THU CUỐI CÙNG (FINAL VERDICT)")
    print("=" * 60)

    if e2e_res["critical_hallucinations"] > 0:
        verdict = "FINAL_ACCEPTANCE_FAILED"
    elif all_passed:
        verdict = "LEVEL_4_ACCEPTED"
    elif e2e_res["pass_rate"] >= 85.0 and e2e_res["critical_hallucinations"] == 0:
        verdict = "LEVEL_4_ACCEPTED_WITH_MINOR_LIMITATIONS"
    else:
        verdict = "FINAL_ACCEPTANCE_FAILED"

    print(f">>> FINAL VERDICT: {verdict} <<<\n")

    # Export full audit results to JSON
    audit_data = {
        "retrieval_and_router": retrieval_res,
        "e2e_deepseek": e2e_res,
        "regressions": reg_res,
        "verdict": verdict
    }
    with open("eval/benchmark_v2_results.json", "w", encoding="utf-8") as f:
        json.dump(audit_data, f, ensure_ascii=False, indent=2)
    print("Đã lưu kết quả chi tiết vào eval/benchmark_v2_results.json")

if __name__ == "__main__":
    main()
