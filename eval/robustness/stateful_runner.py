"""
Stateful Chaos Conversation Runner for Robustness Benchmark V3.
Executes multi-turn stateful adversarial scenarios and interleaved multi-session chaos.
Validates session isolation, active entity persistence, cache scoping, and authority boundaries.
Strict zero-external-API cost policy.
"""
import time
import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from src.memory.sqlite_store import SQLiteSessionStore
from src.memory.session_memory import SessionMemoryService
from src.memory.personal_memory import PersonalMemoryService
from src.rag.query_analyzer import analyze_query, AnalyzedQuery
from src.router import get_router_service
from src.cache.cache_policy import decide_cache_policy

from eval.robustness.schemas import (
    FailureType,
    Severity,
    CaseResult,
)
from eval.robustness.invariants import (
    check_no_crash,
    check_unsafe_tool_activation,
    check_session_isolation_invariant,
    check_cache_safety_invariant,
    check_academic_authority_invariant,
)
from eval.robustness.generators import generate_interleaved_session_chaos


def run_stateful_scenarios(
    scenarios_path: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> Tuple[List[CaseResult], Dict[str, Any]]:
    """
    Chạy toàn bộ các kịch bản multi-turn chaos từ file JSON.
    """
    if scenarios_path is None:
        p = Path(__file__).resolve().parent / "datasets" / "stateful_scenarios.json"
    else:
        p = Path(scenarios_path)

    if not p.exists():
        raise FileNotFoundError(f"Stateful scenarios file not found: {p}")

    with open(p, "r", encoding="utf-8") as f:
        scenarios: List[Dict[str, Any]] = json.load(f)

    if db_path is None:
        bench_db = Path("runtime/eval_robustness_stateful.db")
    else:
        bench_db = db_path

    if bench_db.exists():
        try:
            bench_db.unlink()
        except Exception:
            pass

    store = SQLiteSessionStore(db_path=bench_db)
    session_service = SessionMemoryService(store=store)
    personal_service = PersonalMemoryService(store=store)
    router = get_router_service()

    case_results: List[CaseResult] = []
    total_turns = 0
    passed_turns = 0
    failed_turns = 0

    read_latencies = []
    write_latencies = []

    for scen in scenarios:
        scen_id = scen.get("scenario_id", "CHAOS-SCEN")
        default_session_id = scen.get("session_id", f"sess-{scen_id}")
        default_user_id = scen.get("user_id", f"user-{scen_id}")
        turns = scen.get("turns", [])

        for turn in turns:
            total_turns += 1
            turn_id = turn.get("turn_id", 0)
            user_input = turn.get("user_input", "")
            turn_session_id = turn.get("session_id", default_session_id)
            turn_user_id = turn.get("user_id", default_user_id)
            expected_entity = turn.get("expected_active_entity")
            expected_category = turn.get("expected_category")

            # 1. READ & RESOLVE CONTEXT
            t_read = time.perf_counter()
            s_state = session_service.get_session_state(turn_session_id)
            session_ctx = s_state.to_context_dict()
            resolved_code, resolved_target, res_source, unresolved_ref = session_service.resolve_context(
                conversation_id=turn_session_id,
                current_query=user_input,
            )
            read_latencies.append((time.perf_counter() - t_read) * 1000)

            # 2. QUERY ANALYSIS & ROUTING
            no_crash, res, err = check_no_crash(
                analyze_query,
                query=user_input,
                session_context=session_ctx,
            )
            if not no_crash:
                case_results.append(
                    CaseResult(
                        case_id=f"{scen_id}-T{turn_id}",
                        layer="stateful",
                        category="STATEFUL_CHAOS",
                        input_text=user_input,
                        passed=False,
                        failure_type=FailureType.MALFORMED_INPUT_CRASH,
                        severity=Severity.CRITICAL,
                        error_message=f"Crash in analyze_query: {err}",
                    )
                )
                failed_turns += 1
                continue

            aq: AnalyzedQuery = res

            no_crash_r, r_decision, err_r = check_no_crash(
                router.classify,
                query=user_input,
                analyzed_query=session_ctx,
            )
            if not no_crash_r:
                case_results.append(
                    CaseResult(
                        case_id=f"{scen_id}-T{turn_id}",
                        layer="stateful",
                        category="STATEFUL_CHAOS",
                        input_text=user_input,
                        passed=False,
                        failure_type=FailureType.MALFORMED_INPUT_CRASH,
                        severity=Severity.CRITICAL,
                        error_message=f"Crash in router: {err_r}",
                    )
                )
                failed_turns += 1
                continue

            prof_obj = personal_service.get_user_profile(turn_user_id)
            profile = prof_obj.to_dict() if hasattr(prof_obj, "to_dict") else prof_obj
            cache_decision = decide_cache_policy(
                query=user_input,
                category=r_decision.category,
                tool_intent=r_decision.tool_intent,
                analyzed_query=aq.model_dump(),
                session_context=session_ctx,
                relevant_profile=profile,
            )

            # 4. INVARIANT VERIFICATIONS
            failures = []

            # (a) Unsafe Tool
            tool_safe, tool_err = check_unsafe_tool_activation(
                user_input, r_decision.category, r_decision.tool_intent
            )
            if not tool_safe:
                failures.append((FailureType.UNSAFE_TOOL_ACTIVATION, Severity.CRITICAL, tool_err))

            # (b) Academic Authority Invariant
            auth_safe, auth_err = check_academic_authority_invariant(
                user_input, personal_service, turn_user_id
            )
            if not auth_safe:
                failures.append((FailureType.RAG_AUTHORITY_VIOLATION, Severity.CRITICAL, auth_err))

            # (c) Cache safety check
            cache_safe, cache_err = check_cache_safety_invariant(
                query=user_input,
                category=r_decision.category,
                tool_intent=r_decision.tool_intent,
                cache_decision=cache_decision,
                session_context=session_ctx,
            )
            if not cache_safe:
                failures.append((FailureType.CACHE_COLLISION, Severity.HIGH, cache_err))

            # 5. STATE UPDATE
            mock_ai = f"Thông tin môn học {aq.course_code or 'chung'} đã được xử lý."
            t_write = time.perf_counter()
            updated_state = session_service.update_turn(
                conversation_id=turn_session_id,
                user_message=user_input,
                ai_message=mock_ai,
                analyzed_query=aq.model_dump(),
            )
            write_latencies.append((time.perf_counter() - t_write) * 1000)

            # (d) Active entity tracking check
            if expected_entity is not None:
                # Trạng thái thực thể của phiên sau lượt thoại phải được bảo toàn
                if updated_state.active_course_code != expected_entity:
                    failures.append(
                        (
                            FailureType.STATE_CORRUPTION,
                            Severity.HIGH,
                            f"Active entity corrupted: expected '{expected_entity}', got '{updated_state.active_course_code}'",
                        )
                    )

                # Nếu là câu hỏi tiếp nối ngữ cảnh, kiểm tra resolved_code
                followup_markers = ["đó", "này", "môn này", "môn đó", "thì sao", "email", "ai dạy", "học phí", "tiên quyết"]
                if any(m in user_input.lower() for m in followup_markers) and ("fit" not in user_input.lower()):
                    if resolved_code != expected_entity:
                        failures.append(
                            (
                                FailureType.ENTITY_RESOLUTION_FAILURE,
                                Severity.HIGH,
                                f"Followup resolution mismatch: expected '{expected_entity}', got '{resolved_code}'",
                            )
                        )

            if failures:
                failed_turns += 1
                primary_fail = failures[0]
                case_results.append(
                    CaseResult(
                        case_id=f"{scen_id}-T{turn_id}",
                        layer="stateful",
                        category="STATEFUL_CHAOS",
                        input_text=user_input,
                        passed=False,
                        failure_type=primary_fail[0],
                        severity=primary_fail[1],
                        expected=str(expected_entity or expected_category),
                        actual=f"code={aq.course_code}, cat={r_decision.category}",
                        error_message="; ".join(f[2] for f in failures),
                    )
                )
            else:
                passed_turns += 1
                case_results.append(
                    CaseResult(
                        case_id=f"{scen_id}-T{turn_id}",
                        layer="stateful",
                        category="STATEFUL_CHAOS",
                        input_text=user_input,
                        passed=True,
                        expected=str(expected_entity or expected_category),
                        actual=f"code={aq.course_code}, cat={r_decision.category}",
                    )
                )

    metrics = {
        "total_scenarios": len(scenarios),
        "total_turns": total_turns,
        "passed_turns": passed_turns,
        "failed_turns": failed_turns,
        "pass_rate": round(passed_turns / max(1, total_turns) * 100, 2),
        "avg_read_latency_ms": round(sum(read_latencies) / max(1, len(read_latencies)), 3),
        "avg_write_latency_ms": round(sum(write_latencies) / max(1, len(write_latencies)), 3),
    }

    return case_results, metrics


def run_interleaved_chaos_test(count: int = 100) -> Tuple[List[CaseResult], Dict[str, Any]]:
    """
    Kiểm thử đa phiên xen kẽ gắt gao (Interleaved Multi-session Chaos).
    Chạy các lượt hỏi đan xen giữa 3 phiên với các môn học khác nhau
    để phát hiện bất kỳ sự rò rỉ trạng thái (Cross-session leakage) nào.
    """
    bench_db = Path("runtime/eval_interleaved_chaos.db")
    if bench_db.exists():
        try:
            bench_db.unlink()
        except Exception:
            pass

    store = SQLiteSessionStore(db_path=bench_db)
    session_service = SessionMemoryService(store=store)
    router = get_router_service()

    turns = generate_interleaved_session_chaos(count=count)
    case_results: List[CaseResult] = []

    leakage_count = 0
    passed_turns = 0

    all_sess = ["sess-alpha", "sess-beta", "sess-gamma"]
    for idx, turn in enumerate(turns):
        sess_id = turn.get("session_id")
        other_sessions = [s for s in all_sess if s != sess_id]
        user_msg = turn.get("query") or turn.get("user_message", "")
        expected_code = turn.get("expected_active_entity") or turn.get("expected_resolved_code")

        # Kiểm tra trước: các phiên khác có trạng thái ban đầu sạch sẽ không
        states_before = {
            s: session_service.get_session_state(s).active_course_code for s in other_sessions
        }

        s_state = session_service.get_session_state(sess_id)
        session_ctx = s_state.to_context_dict()

        resolved_code, resolved_target, res_source, unresolved_ref = session_service.resolve_context(
            conversation_id=sess_id,
            current_query=user_msg,
        )

        aq = analyze_query(query=user_msg, session_context=session_ctx)
        router.classify(query=user_msg, analyzed_query=session_ctx)

        # Cập nhật phiên hiện tại
        session_service.update_turn(
            conversation_id=sess_id,
            user_message=user_msg,
            ai_message=f"Trả lời cho {sess_id}: Môn {resolved_code or aq.course_code}",
            analyzed_query=aq.model_dump(),
        )

        # Kiểm tra sau: trạng thái của các phiên khác có bị biến đổi không (Leakage check)
        leakage_detected = False
        leak_msg = ""
        for s in other_sessions:
            current_other = session_service.get_session_state(s).active_course_code
            if current_other != states_before[s]:
                leakage_detected = True
                leak_msg = f"LEAKAGE: Session '{s}' mutated from '{states_before[s]}' to '{current_other}' during turn in '{sess_id}'!"
                break

        # Kiểm tra cô lập tin nhắn
        iso_safe, iso_err = check_session_isolation_invariant(
            session_service, sess_id, other_sessions[0]
        )
        if not iso_safe:
            leakage_detected = True
            leak_msg = iso_err

        if leakage_detected:
            leakage_count += 1
            case_results.append(
                CaseResult(
                    case_id=f"INTERLEAVED-CHAOS-{idx+1:03d}",
                    layer="stateful",
                    category="CROSS_SESSION_CHAOS",
                    input_text=user_msg,
                    passed=False,
                    failure_type=FailureType.MEMORY_LEAKAGE,
                    severity=Severity.CRITICAL,
                    expected=expected_code,
                    actual=str(aq.course_code),
                    error_message=leak_msg,
                )
            )
        else:
            passed_turns += 1
            case_results.append(
                CaseResult(
                    case_id=f"INTERLEAVED-CHAOS-{idx+1:03d}",
                    layer="stateful",
                    category="CROSS_SESSION_CHAOS",
                    input_text=user_msg,
                    passed=True,
                    expected=expected_code,
                    actual=str(resolved_code or aq.course_code),
                )
            )

    metrics = {
        "interleaved_turns_total": len(turns),
        "interleaved_passed": passed_turns,
        "interleaved_leakages": leakage_count,
        "cross_session_leakage_rate": round(leakage_count / max(1, len(turns)) * 100, 2),
    }

    return case_results, metrics
