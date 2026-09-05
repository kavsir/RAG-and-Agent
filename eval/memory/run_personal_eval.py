"""
Personal Memory Evaluation Suite: Đánh giá độc lập bộ nhớ cá nhân có cấu trúc (Personal Memory V1).
Kiểm thử 60 trường hợp trên 11 nhóm: ghi nhận sự thật, cập nhật, xóa, từ chối phát ngôn học vụ,
từ chối placeholder mặc định, phân giải quyền lực, cô lập danh tính người dùng,
và đo đạc chi tiết độ trễ đọc/ghi/xóa/tiêm ngữ cảnh trên SQLite.
Đảm bảo 100% cục bộ, tuyệt đối 0 cuộc gọi API bên ngoài (Strict Zero Cost Policy).
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
    raise RuntimeError("VIOLATION: External API call detected during Personal Memory evaluation!")

import src.llm.client  # noqa: E402
src.llm.client.invoke_llm = forbid_external_api

from src.memory.sqlite_store import SQLiteSessionStore  # noqa: E402
from src.memory.personal_memory import PersonalMemoryService  # noqa: E402
from src.memory.authority_resolver import (  # noqa: E402
    resolve_academic_fact,
    resolve_personal_preference,
    resolve_conversation_entity,
)
from src.agent.nodes import _compute_profile_fingerprint  # noqa: E402


def run_personal_evaluation():
    cases_file = Path("eval/memory/personal_cases.json")
    if not cases_file.exists():
        print(f"Error: {cases_file} not found!")
        return

    with open(cases_file, "r", encoding="utf-8") as f:
        cases: List[Dict[str, Any]] = json.load(f)

    print("=" * 80)
    print("PERSONAL MEMORY V1 EVALUATION SUITE")
    print(f"Total benchmark test cases: {len(cases)} across 11 groups")
    print("Strict Cost Policy: Verified zero external API calls")
    print("=" * 80)

    # CSDL tạm thời phục vụ benchmark sạch
    bench_db_path = Path("runtime/eval_personal_memory.db")
    if bench_db_path.exists():
        try:
            bench_db_path.unlink()
        except Exception:
            pass

    store = SQLiteSessionStore(db_path=bench_db_path)
    service = PersonalMemoryService(store=store)

    # Đo độ trễ
    lat_reads = []
    lat_writes = []
    lat_deletes = []
    lat_contexts = []

    results = []

    for c in cases:
        cid = c["id"]
        group = c["group"]
        passed = False
        detail = ""

        # =====================================================================
        # GROUP A: EXPLICIT FACT SAVE
        # =====================================================================
        if group == "explicit_fact_save":
            user_id = c["user_id"]
            msg = c["input_message"]

            t0 = time.perf_counter()
            write_res = service.process_user_message(user_id=user_id, message=msg)
            lat_writes.append((time.perf_counter() - t0) * 1000)

            exp_key = c["expected_fact_key"]
            exp_val = c["expected_value"]
            exp_act = c["expected_action"]

            match_res = next((r for r in write_res if r.fact_key == exp_key), None)
            if match_res and match_res.action == exp_act and match_res.new_value == exp_val:
                t_r0 = time.perf_counter()
                fact = service.get_fact(user_id=user_id, fact_key=exp_key)
                lat_reads.append((time.perf_counter() - t_r0) * 1000)
                if fact and fact.value == exp_val:
                    passed = True
                else:
                    detail = f"Fact store mismatch: {fact}"
            else:
                detail = f"Write result mismatch: got {write_res}"

        # =====================================================================
        # GROUP B: PROFILE UPDATE VIA TYPED API
        # =====================================================================
        elif group == "profile_update_api":
            user_id = c["user_id"]
            k = c["api_fact_key"]
            v = c["api_value"]

            t0 = time.perf_counter()
            res = service.set_profile_fact(user_id=user_id, fact_key=k, value=v, source_type="PROFILE_API")
            lat_writes.append((time.perf_counter() - t0) * 1000)

            exp_allowed = c["expected_allowed"]
            exp_act = c["expected_action"]

            if exp_allowed:
                t_r0 = time.perf_counter()
                fact = service.get_fact(user_id=user_id, fact_key=k)
                lat_reads.append((time.perf_counter() - t_r0) * 1000)
                if res.action == exp_act and fact and fact.value == c["expected_value"]:
                    passed = True
                else:
                    detail = f"Expected allowed fact mismatch: res={res}, fact={fact}"
            else:
                if res.action == exp_act:
                    passed = True
                else:
                    detail = f"Expected reject but got action={res.action}"

        # =====================================================================
        # GROUP C: CROSS-SESSION RECALL
        # =====================================================================
        elif group == "cross_session_recall":
            user_id = c["user_id"]
            k = c["setup_fact_key"]
            v = c["setup_value"]

            # Session 1 lưu fact
            service.set_profile_fact(user_id=user_id, fact_key=k, value=v, source_type="PROFILE_API")

            # Session 2 đọc fact
            t_r0 = time.perf_counter()
            profile = service.get_user_profile(user_id=user_id)
            lat_reads.append((time.perf_counter() - t_r0) * 1000)

            if profile.get(k) == c["expected_recalled_value"]:
                passed = True
            else:
                detail = f"Cross-session recall failed: expected {c['expected_recalled_value']}, got {profile.get(k)}"

        # =====================================================================
        # GROUP D: PREFERENCE PERSONALIZATION & MINIMAL INJECTION
        # =====================================================================
        elif group == "preference_personalization":
            user_id = c["user_id"]
            if c.get("cache_fingerprint_check"):
                fp_a = _compute_profile_fingerprint({"response_style": c["style_a"]})
                fp_b = _compute_profile_fingerprint({"response_style": c["style_b"]})
                passed = (fp_a != fp_b) and (fp_a is not None) and (fp_b is not None)
                detail = f"fp_a={fp_a}, fp_b={fp_b}"
            else:
                # Setup facts
                for k, v in c["user_facts"].items():
                    service.set_profile_fact(user_id=user_id, fact_key=k, value=v)

                t_c0 = time.perf_counter()
                ctx = service.get_relevant_profile_context(query=c["query"], category=c["category"], user_id=user_id)
                lat_contexts.append((time.perf_counter() - t_c0) * 1000)

                has_all_exp = all(k in ctx for k in c["expected_injected_keys"])
                excludes_all = all(k not in ctx for k in c["expected_excluded_keys"])

                passed = has_all_exp and excludes_all
                if not passed:
                    detail = f"Context mismatch: ctx={ctx}, expected={c['expected_injected_keys']}, excluded={c['expected_excluded_keys']}"

        # =====================================================================
        # GROUP E: FACT UPDATE
        # =====================================================================
        elif group == "fact_update":
            user_id = c["user_id"]
            k = c["fact_key"]
            init_v = c["initial_value"]

            # Khởi tạo giá trị ban đầu
            service.set_profile_fact(user_id=user_id, fact_key=k, value=init_v)

            # Người dùng cập nhật bằng tin nhắn
            t_w0 = time.perf_counter()
            write_res = service.process_user_message(user_id=user_id, message=c["update_message"])
            lat_writes.append((time.perf_counter() - t_w0) * 1000)

            match_res = next((r for r in write_res if r.fact_key == k), None)
            exp_act = c["expected_action"]
            exp_val = c["expected_updated_value"]

            t_r0 = time.perf_counter()
            fact = service.get_fact(user_id=user_id, fact_key=k)
            lat_reads.append((time.perf_counter() - t_r0) * 1000)

            if match_res and match_res.action == exp_act and fact and fact.value == exp_val:
                passed = True
            else:
                detail = f"Fact update mismatch: match_res={match_res}, fact={fact}"

        # =====================================================================
        # GROUP F: FORGET ONE FACT
        # =====================================================================
        elif group == "forget_one_fact":
            user_id = c["user_id"]
            service.clear_memory(user_id=user_id)
            for k, v in c["setup_facts"].items():
                service.set_profile_fact(user_id=user_id, fact_key=k, value=v)

            del_k = c["delete_key"]
            t_d0 = time.perf_counter()
            del_ok = service.delete_fact(user_id=user_id, fact_key=del_k)
            lat_deletes.append((time.perf_counter() - t_d0) * 1000)

            exp_del = c["expected_deleted"]
            profile = service.get_user_profile(user_id=user_id)

            if del_ok == exp_del:
                if "expected_remaining_keys" in c:
                    rem_keys = sorted(list(profile.keys()))
                    exp_rem = sorted(c["expected_remaining_keys"])
                    passed = (rem_keys == exp_rem)
                    if not passed:
                        detail = f"Remaining keys mismatch: {rem_keys} != {exp_rem}"
                elif c.get("expected_audit_event"):
                    evts = store.get_memory_events(user_id=user_id, limit=5)
                    passed = any(e.event_type == c["expected_audit_event"] and e.fact_key == del_k for e in evts)
                    if not passed:
                        detail = f"Audit event not found in {evts}"
                else:
                    passed = True
            else:
                detail = f"Delete return mismatch: got {del_ok}, expected {exp_del}"

        # =====================================================================
        # GROUP G: CLEAR PROFILE
        # =====================================================================
        elif group == "clear_profile":
            user_id = c["user_id"]
            if c.get("verify_session_history_intact"):
                sess_id = c["session_id"]
                store.create_session(sess_id)
                store.append_message(sess_id, "user", c["user_message"])
                store.append_message(sess_id, "assistant", c["ai_message"])
                # Xóa profile
                service.clear_memory(user_id=user_id)
                # Kiểm tra messages trong session không bị xóa
                msgs = store.get_recent_messages(sess_id, k=5)
                passed = (len(msgs) == c["expected_session_messages_count"])
                detail = f"Messages count: {len(msgs)}"
            elif c.get("verify_rag_intact"):
                from src.config.settings import settings as app_settings
                service.clear_memory(user_id=user_id)
                passed = app_settings.CHROMA_PATH.exists()
                detail = "Chroma path intact check"
            elif c.get("expected_audit_event"):
                service.set_profile_fact(user_id=user_id, fact_key="cohort", value="K19")
                service.clear_memory(user_id=user_id)
                evts = store.get_memory_events(user_id=user_id, limit=5)
                passed = any(e.event_type == c["expected_audit_event"] for e in evts)
                detail = f"Audit event DELETE_ALL in {evts}"
            else:
                for k, v in c["setup_facts"].items():
                    service.set_profile_fact(user_id=user_id, fact_key=k, value=v)
                t_d0 = time.perf_counter()
                cleared_cnt = service.clear_memory(user_id=user_id)
                lat_deletes.append((time.perf_counter() - t_d0) * 1000)
                profile = service.get_user_profile(user_id=user_id)
                passed = (cleared_cnt == c["expected_cleared_count"]) and (profile == c["expected_profile_after"])
                detail = f"Cleared: {cleared_cnt}, profile: {profile}"

        # =====================================================================
        # GROUP H: SYSTEM DEFAULT / PLACEHOLDER REJECTION
        # =====================================================================
        elif group == "placeholder_rejection":
            if c.get("check_presentation_default"):
                user_id = c["user_id"]
                facts = service.get_user_profile(user_id=user_id)
                passed = (len(facts) == c["expected_db_facts_count"])
                detail = f"Facts count in db: {len(facts)}"
            else:
                # Giả lập file legacy
                tmp_json = Path("runtime/test_legacy_profile.json")
                with open(tmp_json, "w", encoding="utf-8") as f:
                    json.dump(c["legacy_data"], f, ensure_ascii=False)
                summary = service.migrate_legacy_profile(legacy_profile_path=tmp_json, user_id="test-legacy-user")
                tmp_json.unlink(missing_ok=True)

                if c["expected_ignored_placeholder"]:
                    passed = len(summary["ignored_placeholders"]) > 0 and len(summary["migrated"]) == 0
                    detail = f"Summary: {summary}"
                else:
                    passed = len(summary["migrated"]) > 0
                    detail = f"Summary: {summary}"

        # =====================================================================
        # GROUP I: ACADEMIC CLAIM REJECTION
        # =====================================================================
        elif group == "academic_claim_rejection":
            user_id = c["user_id"]
            msg = c["input_message"]
            write_res = service.process_user_message(user_id=user_id, message=msg)
            # Không được có bất kỳ fact nào được CREATED hay UPDATED
            allowed_facts = [r for r in write_res if r.action in ["CREATED", "UPDATED"]]
            passed = (len(allowed_facts) == 0)
            if not passed:
                detail = f"Academic claim inappropriately allowed: {allowed_facts}"

        # =====================================================================
        # GROUP J: AUTHORITY CONFLICT RESOLUTION
        # =====================================================================
        elif group == "authority_conflict":
            dom = c["domain"]
            if dom == "ACADEMIC_TRUTH":
                chosen, auth = resolve_academic_fact(rag_fact=c["rag_fact"], personal_claim=c["personal_claim"])
                passed = (chosen == c["expected_chosen"]) and (auth == c["expected_authority"])
                detail = f"Academic authority: {chosen} ({auth})"
            elif dom == "PERSONAL_PREFERENCE":
                chosen, auth = resolve_personal_preference(
                    fact_key="response_style",
                    explicit_current=c["explicit_current"],
                    stored_personal=c["stored_personal"],
                    system_default=c["system_default"],
                )
                passed = (chosen == c["expected_chosen"]) and (auth == c["expected_authority"])
                detail = f"Personal preference authority: {chosen} ({auth})"
            elif dom == "CONVERSATION_ENTITY":
                chosen, auth = resolve_conversation_entity(
                    entity_type="course",
                    explicit_query_entity=c["explicit_query"],
                    session_state_entity=c["session_state"],
                    personal_memory_entity=c["personal_memory"],
                )
                passed = (chosen == c["expected_chosen"]) and (auth == c["expected_authority"])
                detail = f"Entity authority: {chosen} ({auth})"

        # =====================================================================
        # GROUP K: PRINCIPAL ISOLATION
        # =====================================================================
        elif group == "principal_isolation":
            p_a = c["principal_a"]
            p_b = c["principal_b"]

            if c.get("action") == "delete_a_only":
                service.delete_fact(p_a, c["delete_key"])
                prof_b = service.get_user_profile(p_b)
                passed = (c["delete_key"] in prof_b)
                detail = f"Profile B after A deleted: {prof_b}"
            elif c.get("action") == "clear_a_only":
                service.clear_memory(p_a)
                prof_b = service.get_user_profile(p_b)
                passed = (len(prof_b) == c["expected_b_count_intact"])
                detail = f"Profile B length: {len(prof_b)}"
            else:
                k = c["fact_key"]
                service.set_profile_fact(user_id=p_a, fact_key=k, value=c["val_a"])
                service.set_profile_fact(user_id=p_b, fact_key=k, value=c["val_b"])

                fact_a = service.get_fact(p_a, k)
                fact_b = service.get_fact(p_b, k)

                passed = (fact_a.value == c["val_a"]) and (fact_b.value == c["val_b"])
                detail = f"A={fact_a.value if fact_a else None}, B={fact_b.value if fact_b else None}"

        results.append({
            "id": cid,
            "group": group,
            "passed": passed,
            "detail": detail,
        })

    # TÍNH TOÁN METRICS VÀ REPORT
    def calc_rate(grp_name):
        items = [r for r in results if r["group"] == grp_name]
        if not items:
            return 0.0, 0, 0
        corr = sum(1 for r in items if r["passed"])
        return round((corr / len(items)) * 100, 2), corr, len(items)

    overall_passed = sum(1 for r in results if r["passed"])
    overall_acc = round((overall_passed / len(results)) * 100, 2)

    exp_write_acc, exp_corr, exp_cnt = calc_rate("explicit_fact_save")
    prof_api_acc, prof_corr, prof_cnt = calc_rate("profile_update_api")
    cross_acc, cross_corr, cross_cnt = calc_rate("cross_session_recall")
    pref_acc, pref_corr, pref_cnt = calc_rate("preference_personalization")
    update_acc, update_corr, update_cnt = calc_rate("fact_update")
    forget_acc, forget_corr, forget_cnt = calc_rate("forget_one_fact")
    clear_acc, clear_corr, clear_cnt = calc_rate("clear_profile")
    place_acc, place_corr, place_cnt = calc_rate("placeholder_rejection")
    acad_acc, acad_corr, acad_cnt = calc_rate("academic_claim_rejection")
    auth_acc, auth_corr, auth_cnt = calc_rate("authority_conflict")
    iso_acc, iso_corr, iso_cnt = calc_rate("principal_isolation")

    # Độ trễ
    p95_read = round(float(np.percentile(lat_reads, 95)), 2) if lat_reads else 0.0
    p95_write = round(float(np.percentile(lat_writes, 95)), 2) if lat_writes else 0.0
    p95_del = round(float(np.percentile(lat_deletes, 95)), 2) if lat_deletes else 0.0
    p95_ctx = round(float(np.percentile(lat_contexts, 95)), 2) if lat_contexts else 0.0

    print("\n1. CHỈ SỐ NGHIỆM THU BỘ NHỚ CÁ NHÂN (ACCEPTANCE GATES):")
    print(f"   - Explicit Fact Write Accuracy   : {exp_corr}/{exp_cnt} ({exp_write_acc}%) [Gate: >= 95%]")
    print(f"   - Profile API Update Accuracy    : {prof_corr}/{prof_cnt} ({prof_api_acc}%) [Gate: >= 95%]")
    print(f"   - Cross-session Personal Recall  : {cross_corr}/{cross_cnt} ({cross_acc}%) [Gate: = 100%]")
    print(f"   - Preference Personalization     : {pref_corr}/{pref_cnt} ({pref_acc}%) [Gate: >= 95%]")
    print(f"   - Fact Update Accuracy           : {update_corr}/{update_cnt} ({update_acc}%) [Gate: >= 95%]")
    print(f"   - Forget One Fact Accuracy       : {forget_corr}/{forget_cnt} ({forget_acc}%) [Gate: = 100%]")
    print(f"   - Clear Profile Accuracy         : {clear_corr}/{clear_cnt} ({clear_acc}%) [Gate: = 100%]")
    print(f"   - System Default Rejection       : {place_corr}/{place_cnt} ({place_acc}%) [Gate: = 100%]")
    print(f"   - Academic Claim Rejection       : {acad_corr}/{acad_cnt} ({acad_acc}%) [Gate: = 100%]")
    print(f"   - Authority Conflict Resolution  : {auth_corr}/{auth_cnt} ({auth_acc}%) [Gate: = 100%]")
    print(f"   - Principal Service Isolation    : {iso_corr}/{iso_cnt} ({iso_acc}%) [Gate: = 100%]")
    print(f"   - Overall Tests Passed           : {overall_passed}/{len(results)} ({overall_acc}%) [Gate: >= 95%]")

    print("\n2. ĐỘ TRỄ THAO TÁC CƠ SỞ DỮ LIỆU SQLITE (LATENCY PROFILING):")
    print(f"   - Personal Fact Read  (P95): {p95_read} ms [Gate: < 10 ms]")
    print(f"   - Personal Fact Write (P95): {p95_write} ms [Gate: < 10 ms]")
    print(f"   - Personal Fact Delete(P95): {p95_del} ms [Gate: < 10 ms]")
    print(f"   - Minimal Context Gen (P95): {p95_ctx} ms [Gate: < 10 ms]")

    failed_cases = [r for r in results if not r["passed"]]
    print(f"\n3. CÁC TRƯỜNG HỢP THẤT BẠI ({len(failed_cases)}):")
    if not failed_cases:
        print("   - 0 FAILED CASES! 100% PERFECT PASS SCORE!")
    else:
        for fc in failed_cases:
            print(f"   - [{fc['id']}] Group: {fc['group']} | Detail: {fc['detail']}")

    out_eval = Path("eval/results/personal_memory_eval.json")
    out_eval.parent.mkdir(parents=True, exist_ok=True)
    with open(out_eval, "w", encoding="utf-8") as f:
        json.dump({
            "overall_accuracy": overall_acc,
            "overall_passed": overall_passed,
            "total_cases": len(results),
            "metrics": {
                "explicit_fact_write_accuracy": exp_write_acc,
                "profile_api_update_accuracy": prof_api_acc,
                "cross_session_recall": cross_acc,
                "preference_personalization": pref_acc,
                "fact_update_accuracy": update_acc,
                "delete_accuracy": forget_acc,
                "clear_profile_accuracy": clear_acc,
                "placeholder_rejection": place_acc,
                "academic_claim_rejection": acad_acc,
                "authority_conflict": auth_acc,
                "principal_isolation": iso_acc,
            },
            "latencies_p95_ms": {
                "read": p95_read,
                "write": p95_write,
                "delete": p95_del,
                "context": p95_ctx,
            },
            "cases": results,
        }, f, ensure_ascii=False, indent=2)

    print(f"\nSaved detailed evaluation to {out_eval}\n")


if __name__ == "__main__":
    run_personal_evaluation()
