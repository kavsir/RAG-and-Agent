import json
import os
import sys
import time
import numpy as np

# Ensure root dir in path
sys.path.insert(0, r"D:\RAG-and-Agent")
sys.stdout.reconfigure(encoding="utf-8")

from src.agent_core.semantic_goal_interpreter import get_semantic_goal_interpreter  # noqa: E402

EVAL_DIR = r"D:\RAG-and-Agent\eval\goal_understanding"

def run_benchmark():
    interpreter = get_semantic_goal_interpreter()

    print("=" * 60)
    print("RUNNING P2.1 SEMANTIC GOAL UNDERSTANDING BENCHMARK")
    print("=" * 60)

    # 1. Warmup
    print("Warming up embedding model...")
    for _ in range(3):
        interpreter.interpret("FIT4201 bao nhiêu tín chỉ?")

    # 2. SEEN EVALUATION
    with open(os.path.join(EVAL_DIR, "p2_1_seen.json"), "r", encoding="utf-8") as f:
        seen_data = json.load(f)

    seen_intent_correct = 0
    seen_entity_correct = 0
    for item in seen_data:
        frame = interpreter.interpret(item["query"], session_context=item.get("context"))
        if frame.intent.value == item["expected_intent"]:
            seen_intent_correct += 1
        expected_ents = item.get("expected_entities", [])
        if not expected_ents or any(e in frame.entities for e in expected_ents):
            seen_entity_correct += 1

    seen_intent_acc = seen_intent_correct / len(seen_data)
    seen_entity_acc = seen_entity_correct / len(seen_data)
    print(f"Seen Intent Accuracy: {seen_intent_acc * 100:.1f}% ({seen_intent_correct}/{len(seen_data)})")
    print(f"Seen Entity Accuracy: {seen_entity_acc * 100:.1f}% ({seen_entity_correct}/{len(seen_data)})")

    # 3. UNSEEN HOLDOUT EVALUATION
    with open(os.path.join(EVAL_DIR, "p2_1_holdout.json"), "r", encoding="utf-8") as f:
        holdout_data = json.load(f)

    holdout_intent_correct = 0
    holdout_entity_correct = 0
    holdout_field_correct = 0
    holdout_constraint_correct = 0
    holdout_aggr_correct = 0
    holdout_referent_correct = 0
    latencies = []

    unnecessary_clarification_count = 0

    for item in holdout_data:
        t0 = time.perf_counter()
        frame = interpreter.interpret(item["query"], session_context=item.get("context"))
        dur_ms = (time.perf_counter() - t0) * 1000.0
        latencies.append(dur_ms)

        # Intent check
        if frame.intent.value == item["expected_intent"]:
            holdout_intent_correct += 1

        # Entity check
        expected_ents = item.get("expected_entities", [])
        if not expected_ents or all(e in frame.entities for e in expected_ents):
            holdout_entity_correct += 1

        # Field check
        expected_fields = item.get("expected_fields", [])
        if not expected_fields or all(f in frame.requested_fields for f in expected_fields):
            holdout_field_correct += 1

        # Constraint check
        expected_constraints = item.get("expected_constraints", [])
        if not expected_constraints or all(c in frame.constraints for c in expected_constraints):
            holdout_constraint_correct += 1

        # Aggregation check
        expected_aggr = item.get("expected_aggregation")
        if not expected_aggr or frame.aggregation.value == expected_aggr:
            holdout_aggr_correct += 1

        # Referent check
        expected_refs = item.get("expected_referents", [])
        if not expected_refs or any(r.value in expected_refs for r in frame.referents):
            holdout_referent_correct += 1

        # Unnecessary clarification
        if frame.missing_slots and "data" not in frame.missing_slots:
            if not item.get("expected_missing_slots"):
                unnecessary_clarification_count += 1

    holdout_intent_acc = holdout_intent_correct / len(holdout_data)
    holdout_entity_acc = holdout_entity_correct / len(holdout_data)
    holdout_field_acc = holdout_field_correct / len(holdout_data)
    holdout_constraint_acc = holdout_constraint_correct / len(holdout_data)
    holdout_aggr_acc = holdout_aggr_correct / len(holdout_data)
    holdout_referent_acc = holdout_referent_correct / len(holdout_data)
    unnecessary_clarification_rate = unnecessary_clarification_count / len(holdout_data)

    p50_latency = np.percentile(latencies, 50)
    p95_latency = np.percentile(latencies, 95)

    print(f"Unseen Holdout Intent Accuracy: {holdout_intent_acc * 100:.1f}% ({holdout_intent_correct}/{len(holdout_data)})")
    print(f"Holdout Entity Accuracy: {holdout_entity_acc * 100:.1f}% ({holdout_entity_correct}/{len(holdout_data)})")
    print(f"Holdout Field Accuracy: {holdout_field_acc * 100:.1f}% ({holdout_field_correct}/{len(holdout_data)})")
    print(f"Constraint Preservation: {holdout_constraint_acc * 100:.1f}% ({holdout_constraint_correct}/{len(holdout_data)})")
    print(f"Aggregation Accuracy: {holdout_aggr_acc * 100:.1f}% ({holdout_aggr_correct}/{len(holdout_data)})")
    print(f"Referent Accuracy: {holdout_referent_acc * 100:.1f}% ({holdout_referent_correct}/{len(holdout_data)})")
    print(f"Unnecessary Clarification Rate: {unnecessary_clarification_rate * 100:.1f}%")
    print(f"Semantic UNDERSTAND p50: {p50_latency:.2f} ms | p95: {p95_latency:.2f} ms")

    # 4. ADVERSARIAL EVALUATION
    with open(os.path.join(EVAL_DIR, "p2_1_adversarial.json"), "r", encoding="utf-8") as f:
        adv_data = json.load(f)

    wrong_confident_intent = 0
    wrong_confident_entity = 0
    unauthorized_reinterpretation = 0

    for item in adv_data:
        frame = interpreter.interpret(item["query"], session_context=item.get("context"))

        # Safety check: tool action
        if item.get("expected_no_tool_action") and frame.tool_action:
            wrong_confident_intent += 1

        # Ambiguity check
        exp_ambig = item.get("expected_ambiguous_slot")
        if exp_ambig and exp_ambig not in frame.missing_slots:
            wrong_confident_intent += 1

        # Unavailable fields check: must not reinterpret as credits or other fields
        if item.get("expected_missing_slots"):
            for m in item["expected_missing_slots"]:
                if m not in frame.missing_slots:
                    unauthorized_reinterpretation += 1

    print(f"Wrong Confident Intent: {wrong_confident_intent}")
    print(f"Wrong Confident Entity: {wrong_confident_entity}")
    print(f"Unauthorized Goal Reinterpretation: {unauthorized_reinterpretation}")

    # 5. MULTI-TURN SCENARIOS
    with open(os.path.join(EVAL_DIR, "p2_1_multiturn.json"), "r", encoding="utf-8") as f:
        multi_data = json.load(f)

    total_turns = 0
    correct_turns = 0

    for scenario in multi_data:
        context = {}
        for t in scenario["turns"]:
            total_turns += 1
            frame = interpreter.interpret(t["query"], session_context=context)

            turn_ok = True
            if frame.intent.value != t["expected_intent"]:
                turn_ok = False
            if t.get("expected_entities") and not all(e in frame.entities for e in t["expected_entities"]):
                turn_ok = False
            if t.get("expected_fields") and not all(f in frame.requested_fields for f in t["expected_fields"]):
                turn_ok = False
            if t.get("expected_constraints") and not all(c in frame.constraints for c in t["expected_constraints"]):
                turn_ok = False
            if t.get("expected_aggregation") and frame.aggregation.value != t["expected_aggregation"]:
                turn_ok = False

            if turn_ok:
                correct_turns += 1

            # Update conversational state for next turn
            if frame.entities:
                context["last_academic_entity"] = frame.entities[0]
            context["last_intent"] = frame.intent.value
            context["last_scope"] = frame.scope.value
            context["last_requested_fields"] = list(frame.requested_fields)
            context["last_constraints"] = list(frame.constraints)

    multiturn_acc = correct_turns / total_turns
    print(f"Multi-turn Goal Accuracy: {multiturn_acc * 100:.1f}% ({correct_turns}/{total_turns})")

    metrics = interpreter.get_metrics()
    llm_fallback_rate = metrics["goal_parser_llm_fallback_rate"]
    print(f"LLM Fallback Rate: {llm_fallback_rate * 100:.1f}%")

    results = {
        "seen_intent_acc": seen_intent_acc,
        "seen_entity_acc": seen_entity_acc,
        "holdout_intent_acc": holdout_intent_acc,
        "holdout_entity_acc": holdout_entity_acc,
        "holdout_field_acc": holdout_field_acc,
        "constraint_preservation": holdout_constraint_acc,
        "aggregation_accuracy": holdout_aggr_acc,
        "referent_accuracy": holdout_referent_acc,
        "unnecessary_clarification_rate": unnecessary_clarification_rate,
        "wrong_confident_intent": wrong_confident_intent,
        "wrong_confident_entity": wrong_confident_entity,
        "unauthorized_reinterpretation": unauthorized_reinterpretation,
        "multiturn_accuracy": multiturn_acc,
        "llm_fallback_rate": llm_fallback_rate,
        "latency_p50_ms": p50_latency,
        "latency_p95_ms": p95_latency,
    }

    with open(os.path.join(EVAL_DIR, "benchmark_results.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    # Acceptance Verdict Check
    passed = (
        seen_intent_acc >= 0.98
        and holdout_intent_acc >= 0.95
        and holdout_entity_acc >= 0.98
        and holdout_referent_acc >= 0.98
        and holdout_constraint_acc >= 0.95
        and holdout_aggr_acc >= 0.95
        and multiturn_acc >= 0.95
        and wrong_confident_intent == 0
        and wrong_confident_entity == 0
        and unauthorized_reinterpretation == 0
    )

    verdict = "SEMANTIC_GOAL_UNDERSTANDING_ACCEPTED" if passed else "SEMANTIC_GOAL_UNDERSTANDING_REMAINS_CONDITIONAL"
    print("=" * 60)
    print(f"FINAL VERDICT: {verdict}")
    print("=" * 60)
    return results

if __name__ == "__main__":
    run_benchmark()
