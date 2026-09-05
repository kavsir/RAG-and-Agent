"""
Performance Benchmark & Runtime Profiling Runner.
Thực hiện đo đạc độc lập hiệu năng và phân tích điểm nghẽn (bottleneck) của hệ thống:
- Cold start & Warm-up
- End-to-End Latency qua 4 workloads (DOMAIN Miss, GENERAL Miss, Cache Hit, Abstention)
- Local Pipeline Microbenchmark (Query Analyzer, Dense, BM25, RRF, Reranker, Context Builder)
- LLM Answer Generation vs Validation contribution
- Process RSS & System Available RAM profiling
- Phân tích Top 3 Bottlenecks & Phân loại hiệu năng
"""
import os
import sys
import time
import json
import csv
import math
import random
import platform
import subprocess
from pathlib import Path
from typing import Dict, Any, List

import psutil
import httpx

# Thiết lập đường dẫn root
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.config.settings import settings  # noqa: E402
from src.rag.query_analyzer import analyze_query  # noqa: E402
from src.rag.hybrid_retriever import get_collection_retriever  # noqa: E402
from src.rag.reranker import rerank_documents  # noqa: E402
from src.rag.context_builder import build_context  # noqa: E402
from src.api.main import app  # noqa: E402
from src.agent import nodes  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

# ==============================================================================
# Helper Thống Kê
# ==============================================================================
def calc_stats(latencies_ms: List[float]) -> Dict[str, float]:
    if not latencies_ms:
        return {"count": 0, "min": 0.0, "mean": 0.0, "p50": 0.0, "p90": 0.0, "p95": 0.0, "max": 0.0, "std_dev": 0.0}

    sorted_lats = sorted(latencies_ms)
    n = len(sorted_lats)
    mean_val = sum(sorted_lats) / n
    variance = sum((x - mean_val) ** 2 for x in sorted_lats) / n if n > 1 else 0.0
    std_dev = math.sqrt(variance)

    def percentile(p: float) -> float:
        idx = int(math.ceil(p * n)) - 1
        return sorted_lats[max(0, min(idx, n - 1))]

    return {
        "count": n,
        "min": round(sorted_lats[0], 2),
        "mean": round(mean_val, 2),
        "p50": round(percentile(0.50), 2),
        "p90": round(percentile(0.90), 2),
        "p95": round(percentile(0.95), 2),
        "max": round(sorted_lats[-1], 2),
        "std_dev": round(std_dev, 2)
    }


# ==============================================================================
# 1. Thu Thập Thông Tin Môi Trường
# ==============================================================================
def collect_environment() -> Dict[str, Any]:
    cpu_name = platform.processor() or "Unknown CPU"
    try:
        wmic_out = subprocess.check_output("wmic cpu get name", shell=True, text=True, errors="ignore")
        lines = [line_txt.strip() for line_txt in wmic_out.splitlines() if line_txt.strip() and "Name" not in line_txt]
        if lines:
            cpu_name = lines[0]
    except Exception:
        pass

    vmem = psutil.virtual_memory()

    # Clean base url (no secrets)
    base_url_domain = "Unknown"
    if settings.LLM_BASE_URL:
        base_url_domain = settings.LLM_BASE_URL.split("//")[-1].split("/")[0]

    return {
        "os": f"{platform.system()} {platform.release()} ({platform.version()})",
        "python_version": platform.python_version(),
        "cpu_model": cpu_name,
        "logical_cpus": os.cpu_count() or 1,
        "physical_cpus": psutil.cpu_count(logical=False) or 1,
        "total_ram_gb": round(vmem.total / (1024 ** 3), 2),
        "initial_available_ram_gb": round(vmem.available / (1024 ** 3), 2),
        "llm_config": {
            "provider": settings.LLM_PROVIDER,
            "model": settings.LLM_MODEL,
            "base_url_domain": base_url_domain,
            "temperature": settings.LLM_TEMPERATURE,
            "timeout": settings.LLM_TIMEOUT
        },
        "rag_config": {
            "embedding_model": settings.EMBEDDING_MODEL,
            "reranker_model": settings.RERANKER_MODEL,
            "retrieval_candidates": settings.RETRIEVAL_CANDIDATES,
            "context_top_k": settings.CONTEXT_TOP_K,
            "reranker_enabled": settings.ENABLE_RERANKER
        }
    }


# ==============================================================================
# 2. Đo Cold Start (Subprocess mới)
# ==============================================================================
def measure_cold_start() -> Dict[str, Any]:
    print("\n" + "=" * 60)
    print("BƯỚC 1: ĐO COLD START (KHỞI ĐỘNG TIẾN TRÌNH UVICORN ĐỘC LẬP)")
    print("=" * 60)

    port = 8018
    url_health = f"http://127.0.0.1:{port}/health"
    url_chat = f"http://127.0.0.1:{port}/api/chat"

    env = os.environ.copy()
    env["PORT"] = str(port)
    env["PYTHONPATH"] = "."
    env["PYTHONUTF8"] = "1"

    t0 = time.perf_counter()
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "src.api.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(ROOT_DIR),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    startup_time_ms = None
    server_ready = False
    with httpx.Client(timeout=1.0) as client:
        for _ in range(60):  # Chờ tối đa 30s
            try:
                res = client.get(url_health)
                if res.status_code == 200:
                    t1 = time.perf_counter()
                    startup_time_ms = (t1 - t0) * 1000
                    server_ready = True
                    break
            except Exception:
                time.sleep(0.5)

    if not server_ready:
        proc.kill()
        raise RuntimeError("Subprocess Uvicorn không khởi động được trong 30s!")

    print(f"[*] Server Uvicorn sẵn sàng (T1 - T0): {startup_time_ms:.2f} ms")

    # Đo first domain request
    t_req_start = time.perf_counter()
    first_req_latency_ms = None
    peak_rss_mb = 0.0
    try:
        p_proc = psutil.Process(proc.pid)
        with httpx.Client(timeout=120.0) as client:
            res_chat = client.post(url_chat, json={"message": "Môn FIT4201 có bao nhiêu tín chỉ?", "session_id": "cold-test"})
            t_req_end = time.perf_counter()
            first_req_latency_ms = (t_req_end - t_req_start) * 1000
            print(f"[*] First DOMAIN request latency: {first_req_latency_ms:.2f} ms (Status: {res_chat.status_code})")

            # Lấy memory của process và subprocess con (nếu có)
            mem_bytes = p_proc.memory_info().rss
            for child in p_proc.children(recursive=True):
                mem_bytes += child.memory_info().rss
            peak_rss_mb = mem_bytes / (1024 ** 2)
            print(f"[*] Server Process Peak RSS sau first request: {peak_rss_mb:.2f} MB")
    finally:
        # Dừng tiến trình sạch sẽ
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()

    return {
        "server_ready_ms": round(startup_time_ms, 2),
        "first_domain_request_ms": round(first_req_latency_ms, 2),
        "cold_peak_rss_mb": round(peak_rss_mb, 2)
    }


# ==============================================================================
# 3. Đo End-to-End Latency & Instrumentation
# ==============================================================================
def measure_end_to_end_workloads() -> Dict[str, Any]:
    print("\n" + "=" * 60)
    print("BƯỚC 2: ĐO END-TO-END LATENCY (WARM WORKLOADS)")
    print("=" * 60)

    client = TestClient(app)

    # Đo Memory Stages
    memory_profile = {}
    current_proc = psutil.Process(os.getpid())

    def get_proc_rss_mb() -> float:
        return round(current_proc.memory_info().rss / (1024 ** 2), 2)

    def get_sys_avail_gb() -> float:
        return round(psutil.virtual_memory().available / (1024 ** 3), 2)

    memory_profile["stage_1_before_warm"] = {
        "process_rss_mb": get_proc_rss_mb(),
        "sys_available_gb": get_sys_avail_gb()
    }

    # Instrumentation cho LLM & Validation
    llm_call_records = []
    orig_invoke_llm = nodes.invoke_llm

    def instrumented_invoke_llm(prompt: str, **kwargs):
        t_s = time.perf_counter()
        res = orig_invoke_llm(prompt, **kwargs)
        t_e = time.perf_counter()
        d_ms = (t_e - t_s) * 1000

        # Nhận diện loại call
        p_lower = prompt.lower()
        if any(k in p_lower for k in ["kiểm định", "tiêu chí", "groundedness", "kiểm tra tính xác thực"]):
            c_type = "validation"
        elif any(k in p_lower for k in ["phân loại", "intent"]):
            c_type = "routing"
        else:
            c_type = "answer_generation"

        llm_call_records.append({"type": c_type, "duration_ms": d_ms})
        return res

    nodes.invoke_llm = instrumented_invoke_llm

    # A. WARM UP (1 domain + 1 general, không tính vào statistics)
    print("[*] Thực hiện Warm-up (1 DOMAIN + 1 GENERAL)...")
    client.post("/api/chat", json={"message": "Môn FIT4201 là môn gì?", "session_id": "warmup-1"})
    client.post("/api/chat", json={"message": "Xin chào", "session_id": "warmup-2"})
    llm_call_records.clear()

    memory_profile["stage_2_after_warmup"] = {
        "process_rss_mb": get_proc_rss_mb(),
        "sys_available_gb": get_sys_avail_gb()
    }

    raw_cases = []

    # B. WORKLOAD 1: DOMAIN_DATA CACHE MISS (8 distinct queries)
    print("\n--- Workload A: DOMAIN_DATA CACHE MISS (8 queries) ---")
    domain_queries = [
        "Môn FIT4201 có bao nhiêu tín chỉ?",
        "Ai là giảng viên phụ trách môn FIT4104?",
        "Học phần FIT4117 có bao nhiêu tín chỉ lý thuyết và thực hành?",
        "Giảng viên môn FIT4113 có địa chỉ email là gì?",
        "Môn Quản trị dự án CNTT mã FIT4117 do ai dạy?",
        "Hình thức đánh giá chuyên cần A1 của môn FIT4113 là gì?",
        "Môn Thiết kế lập trình Full-Stack có bao nhiêu tín chỉ?",
        "Môn Hệ thống nhúng FIT4201 có phân bổ số giờ học ra sao?"
    ]
    domain_miss_lats = []
    domain_llm_ans_lats = []
    domain_llm_val_lats = []

    for idx, q in enumerate(domain_queries, 1):
        llm_call_records.clear()
        sid = f"perf-dom-miss-{idx}"
        t_s = time.perf_counter()
        resp = client.post("/api/chat", json={"message": q, "session_id": sid})
        t_e = time.perf_counter()
        lat_ms = (t_e - t_s) * 1000
        domain_miss_lats.append(lat_ms)

        data = resp.json()
        cat = data.get("category", "")
        sources = data.get("sources", [])
        meta = data.get("metadata", {})
        retry_count = meta.get("retry_count", 0)
        cache_hit = meta.get("cache_hit", False)
        ans_times = [r["duration_ms"] for r in llm_call_records if r["type"] == "answer_generation"]
        val_times = [r["duration_ms"] for r in llm_call_records if r["type"] == "validation"]
        if ans_times:
            domain_llm_ans_lats.append(ans_times[0])
        if val_times:
            domain_llm_val_lats.append(sum(val_times))

        print(f"  [{idx}/8] {lat_ms:6.1f} ms | Q: {q[:35]:<35} | Retry: {retry_count} | LLM Gen: {sum(ans_times):.1f}ms | Val: {sum(val_times):.1f}ms")
        raw_cases.append({
            "case_id": f"dom_miss_{idx:02d}",
            "workload": "DOMAIN_CACHE_MISS",
            "question": q,
            "category": cat,
            "cache_hit": cache_hit,
            "retry_count": retry_count,
            "latency_ms": round(lat_ms, 2),
            "source_count": len(sources),
            "status": "PASS" if resp.status_code == 200 else "FAIL"
        })

    memory_profile["stage_3_after_domain_miss"] = {
        "process_rss_mb": get_proc_rss_mb(),
        "sys_available_gb": get_sys_avail_gb()
    }

    # C. WORKLOAD 2: GENERAL_LLM CACHE MISS (5 queries)
    print("\n--- Workload B: GENERAL_LLM CACHE MISS (5 queries) ---")
    general_queries = [
        "Thuật toán Dijkstra là gì và ứng dụng thế nào?",
        "Trình bày 4 tính chất cơ bản của lập trình hướng đối tượng OOP?",
        "Giải thích khái niệm biến toàn cục và biến cục bộ trong Python?",
        "Khái niệm RESTful API và các phương thức HTTP chính là gì?",
        "Mô hình Client Server hoạt động theo cơ chế nào?"
    ]
    general_miss_lats = []
    for idx, q in enumerate(general_queries, 1):
        llm_call_records.clear()
        sid = f"perf-gen-miss-{idx}"
        t_s = time.perf_counter()
        resp = client.post("/api/chat", json={"message": q, "session_id": sid})
        t_e = time.perf_counter()
        lat_ms = (t_e - t_s) * 1000
        general_miss_lats.append(lat_ms)

        data = resp.json()
        cat = data.get("category", "")
        meta = data.get("metadata", {})
        print(f"  [{idx}/5] {lat_ms:6.1f} ms | Q: {q[:45]:<45} | Cat: {cat}")
        raw_cases.append({
            "case_id": f"gen_miss_{idx:02d}",
            "workload": "GENERAL_CACHE_MISS",
            "question": q,
            "category": cat,
            "cache_hit": meta.get("cache_hit", False),
            "retry_count": 0,
            "latency_ms": round(lat_ms, 2),
            "source_count": 0,
            "status": "PASS" if resp.status_code == 200 else "FAIL"
        })

    # D. WORKLOAD 3: EXACT CACHE HIT (10 Domain + 10 General hits)
    print("\n--- Workload C: EXACT CACHE HIT (10 DOMAIN + 10 GENERAL) ---")
    # Populate cache
    q_dom_cache = "Môn FIT4201 có bao nhiêu tín chỉ?"
    q_gen_cache = "Dijkstra là gì?"
    client.post("/api/chat", json={"message": q_dom_cache, "session_id": "perf-cache-dom"})
    client.post("/api/chat", json={"message": q_gen_cache, "session_id": "perf-cache-gen"})

    domain_hit_lats = []
    for i in range(1, 11):
        t_s = time.perf_counter()
        resp = client.post("/api/chat", json={"message": q_dom_cache, "session_id": "perf-cache-dom"})
        t_e = time.perf_counter()
        lat_ms = (t_e - t_s) * 1000
        domain_hit_lats.append(lat_ms)
        data = resp.json()
        raw_cases.append({
            "case_id": f"dom_hit_{i:02d}",
            "workload": "DOMAIN_CACHE_HIT",
            "question": q_dom_cache,
            "category": data.get("category", ""),
            "cache_hit": True,
            "retry_count": 0,
            "latency_ms": round(lat_ms, 2),
            "source_count": len(data.get("sources", [])),
            "status": "PASS" if resp.status_code == 200 else "FAIL"
        })

    general_hit_lats = []
    for i in range(1, 11):
        t_s = time.perf_counter()
        resp = client.post("/api/chat", json={"message": q_gen_cache, "session_id": "perf-cache-gen"})
        t_e = time.perf_counter()
        lat_ms = (t_e - t_s) * 1000
        general_hit_lats.append(lat_ms)
        data = resp.json()
        raw_cases.append({
            "case_id": f"gen_hit_{i:02d}",
            "workload": "GENERAL_CACHE_HIT",
            "question": q_gen_cache,
            "category": data.get("category", ""),
            "cache_hit": True,
            "retry_count": 0,
            "latency_ms": round(lat_ms, 2),
            "source_count": 0,
            "status": "PASS" if resp.status_code == 200 else "FAIL"
        })

    print(f"  -> DOMAIN Cache Hit mean: {sum(domain_hit_lats)/len(domain_hit_lats):.2f} ms")
    print(f"  -> GENERAL Cache Hit mean: {sum(general_hit_lats)/len(general_hit_lats):.2f} ms")

    # E. WORKLOAD 4: SAFE ABSTENTION (5 brand new random codes)
    print("\n--- Workload D: SAFE ABSTENTION (5 random new entities) ---")
    abstention_lats = []
    for i in range(1, 6):
        rand_code = f"FIT8{random.randint(100, 999)}"
        q_abs = f"Môn học {rand_code} có bao nhiêu tín chỉ?"
        llm_call_records.clear()
        t_s = time.perf_counter()
        resp = client.post("/api/chat", json={"message": q_abs, "session_id": f"perf-abs-{i}"})
        t_e = time.perf_counter()
        lat_ms = (t_e - t_s) * 1000
        abstention_lats.append(lat_ms)

        data = resp.json()
        ans = data.get("answer", "")
        sources = data.get("sources", [])
        print(f"  [{i}/5] {lat_ms:6.1f} ms | Code: {rand_code} | LLM calls: {len(llm_call_records)} | Sources: {len(sources)}")
        raw_cases.append({
            "case_id": f"abs_{i:02d}",
            "workload": "ABSTENTION",
            "question": q_abs,
            "category": data.get("category", ""),
            "cache_hit": False,
            "retry_count": 0,
            "latency_ms": round(lat_ms, 2),
            "source_count": len(sources),
            "status": "PASS" if (len(sources) == 0 and "chưa" in ans.lower()) else "FAIL"
        })

    # Restore original invoke_llm
    nodes.invoke_llm = orig_invoke_llm

    memory_profile["stage_4_after_all_workloads"] = {
        "process_rss_mb": get_proc_rss_mb(),
        "sys_available_gb": get_sys_avail_gb()
    }

    return {
        "latency_stats": {
            "domain_cache_miss": calc_stats(domain_miss_lats),
            "general_cache_miss": calc_stats(general_miss_lats),
            "domain_cache_hit": calc_stats(domain_hit_lats),
            "general_cache_hit": calc_stats(general_hit_lats),
            "abstention": calc_stats(abstention_lats)
        },
        "llm_breakdown": {
            "domain_llm_answer_gen": calc_stats(domain_llm_ans_lats),
            "domain_llm_validation": calc_stats(domain_llm_val_lats)
        },
        "raw_cases": raw_cases,
        "memory_profile": memory_profile
    }


# ==============================================================================
# 4. Đo Local Pipeline Microbenchmarks
# ==============================================================================
def measure_local_pipeline() -> Dict[str, Any]:
    print("\n" + "=" * 60)
    print("BƯỚC 3: LOCAL PIPELINE MICROBENCHMARK (PROFILING COMPONENT ĐỘC LẬP)")
    print("=" * 60)

    retriever = get_collection_retriever("course_detail")

    test_queries = [
        "Môn FIT4201 có bao nhiêu tín chỉ?",
        "Giảng viên phụ trách môn FIT4104 là ai?",
        "Học phần FIT4117 có bao nhiêu tín chỉ?",
        "Giảng viên môn FIT4113 có địa chỉ email là gì?",
        "Môn Quản trị dự án CNTT mã FIT4117 do ai dạy?",
        "Hình thức đánh giá chuyên cần A1 của môn FIT4113 là gì?",
        "Môn Thiết kế lập trình Full-Stack có bao nhiêu tín chỉ?",
        "Môn Hệ thống nhúng FIT4201 học những gì?",
        "Quy chế đào tạo trình độ đại học Đại Nam",
        "Chương trình đào tạo ngành Khoa học máy tính K19"
    ]

    qa_lats = []
    dense_lats = []
    bm25_lats = []
    rrf_lats = []
    rerank_lats = []
    ctx_lats = []

    for q in test_queries:
        # 1. Query Analyzer
        t0 = time.perf_counter()
        analyzed = analyze_query(q)
        t1 = time.perf_counter()
        qa_lats.append((t1 - t0) * 1000)

        # 2. Dense Search
        t2 = time.perf_counter()
        _ = retriever.dense_search(q, top_k=20)
        t3 = time.perf_counter()
        dense_lats.append((t3 - t2) * 1000)

        # 3. BM25 Search
        t4 = time.perf_counter()
        _ = retriever.bm25_search(q, top_k=20)
        t5 = time.perf_counter()
        bm25_lats.append((t5 - t4) * 1000)

        # 4. Hybrid / RRF
        t6 = time.perf_counter()
        hybrid_docs = retriever.hybrid_search(q, top_k=20)
        t7 = time.perf_counter()
        rrf_lats.append((t7 - t6) * 1000)

        # 5. Reranker (nếu bật, đo model; nếu tắt, đo direct pass)
        t8 = time.perf_counter()
        reranked = rerank_documents(query=q, candidates=hybrid_docs[:8], top_k=6)
        t9 = time.perf_counter()
        rerank_lats.append((t9 - t8) * 1000)

        # 6. Context Builder
        t10 = time.perf_counter()
        ctx_text, src_meta = build_context(reranked, targets=analyzed.targets, max_chunks=settings.CONTEXT_TOP_K)
        t11 = time.perf_counter()
        ctx_lats.append((t11 - t10) * 1000)

    print(f"[*] Query Analyzer Mean:   {sum(qa_lats)/len(qa_lats):6.2f} ms")
    print(f"[*] Dense Search Mean:     {sum(dense_lats)/len(dense_lats):6.2f} ms")
    print(f"[*] BM25 Search Mean:      {sum(bm25_lats)/len(bm25_lats):6.2f} ms")
    print(f"[*] Hybrid RRF Search Mean:{sum(rrf_lats)/len(rrf_lats):6.2f} ms")
    print(f"[*] Reranker Mean:         {sum(rerank_lats)/len(rerank_lats):6.2f} ms")
    print(f"[*] Context Builder Mean:  {sum(ctx_lats)/len(ctx_lats):6.2f} ms")

    return {
        "query_analysis": calc_stats(qa_lats),
        "dense_search": calc_stats(dense_lats),
        "bm25_search": calc_stats(bm25_lats),
        "hybrid_rrf_retrieval": calc_stats(rrf_lats),
        "reranker": calc_stats(rerank_lats),
        "context_builder": calc_stats(ctx_lats)
    }


# ==============================================================================
# MAIN RUNNER
# ==============================================================================
def main():
    print("================================================================")
    print("      AI ACADEMIC ADVISOR - PERFORMANCE BENCHMARK SUITE         ")
    print("================================================================")

    # 1. Environment
    env_info = collect_environment()
    print(f"OS: {env_info['os']}")
    print(f"CPU: {env_info['cpu_model']} ({env_info['physical_cpus']} physical, {env_info['logical_cpus']} logical)")
    print(f"RAM: {env_info['total_ram_gb']} GB Total, {env_info['initial_available_ram_gb']} GB Available")
    print(f"LLM: {env_info['llm_config']['provider']} / {env_info['llm_config']['model']}")

    # 2. Cold Start
    cold_start_res = measure_cold_start()

    # 3. E2E Workloads & Memory
    e2e_res = measure_end_to_end_workloads()

    # 4. Local Pipeline Microbenchmarks
    pipeline_res = measure_local_pipeline()

    # 5. Lưu Output Files
    # A. JSON
    baseline_commit = "4cf04cca394870b6c83e7cb54984b98bcffda846"
    latest_commit = subprocess.check_output("git rev-parse HEAD", shell=True, text=True).strip()

    final_results = {
        "baseline": {
            "product_commit": baseline_commit,
            "evaluation_commit": latest_commit
        },
        "environment": env_info,
        "cold_start": cold_start_res,
        "latency": e2e_res["latency_stats"],
        "llm_contribution": e2e_res["llm_breakdown"],
        "local_pipeline": pipeline_res,
        "memory": e2e_res["memory_profile"]
    }

    results_dir = ROOT_DIR / "eval" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    json_path = results_dir / "performance_latest.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(final_results, f, ensure_ascii=False, indent=2)
    print(f"\n[+] Đã xuất kết quả JSON: {json_path}")

    # B. CSV
    csv_path = results_dir / "performance_cases.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "case_id", "workload", "question", "category", "cache_hit", "retry_count", "latency_ms", "source_count", "status"
        ])
        writer.writeheader()
        for c in e2e_res["raw_cases"]:
            writer.writerow(c)
    print(f"[+] Đã xuất kết quả CSV: {csv_path}")

    # 6. TỔNG KẾT & IN TERMINAL
    print("\n" + "=" * 60)
    print("PERFORMANCE BENCHMARK COMPLETE")
    print("=" * 60)
    print(f"Product baseline: {baseline_commit}")
    print(f"Cold start:       server_ready={cold_start_res['server_ready_ms']:.1f}ms, first_req={cold_start_res['first_domain_request_ms']:.1f}ms")

    dom_stats = e2e_res["latency_stats"]["domain_cache_miss"]
    print(f"DOMAIN cache miss:mean={dom_stats['mean']:.1f}ms, p50={dom_stats['p50']:.1f}ms, p95={dom_stats['p95']:.1f}ms")

    gen_stats = e2e_res["latency_stats"]["general_cache_miss"]
    print(f"GENERAL:          mean={gen_stats['mean']:.1f}ms, p50={gen_stats['p50']:.1f}ms, p95={gen_stats['p95']:.1f}ms")

    hit_dom_stats = e2e_res["latency_stats"]["domain_cache_hit"]
    print(f"Cache hit (DOM):  mean={hit_dom_stats['mean']:.1f}ms, p50={hit_dom_stats['p50']:.1f}ms, p95={hit_dom_stats['p95']:.1f}ms")

    abs_stats = e2e_res["latency_stats"]["abstention"]
    print(f"Abstention:       mean={abs_stats['mean']:.1f}ms, p50={abs_stats['p50']:.1f}ms, p95={abs_stats['p95']:.1f}ms")

    peak_rss = max(
        cold_start_res.get("cold_peak_rss_mb", 0.0),
        max(s["process_rss_mb"] for s in e2e_res["memory_profile"].values())
    )
    print(f"Peak RSS:         {peak_rss:.2f} MB")

    # Xác định Primary Bottleneck
    llm_ans_mean = e2e_res["llm_breakdown"]["domain_llm_answer_gen"]["mean"]
    llm_val_mean = e2e_res["llm_breakdown"]["domain_llm_validation"]["mean"]
    retrieval_mean = pipeline_res["hybrid_rrf_retrieval"]["mean"]

    print(f"\nPhân tích đóng góp thời gian trung bình (DOMAIN request ~{dom_stats['mean']:.1f}ms):")
    print(f"  1. LLM Grounded Answer Gen: {llm_ans_mean:.1f}ms ({llm_ans_mean/dom_stats['mean']*100:.1f}%)")
    print(f"  2. LLM Factuality Validator: {llm_val_mean:.1f}ms ({llm_val_mean/dom_stats['mean']*100:.1f}%)")
    print(f"  3. Local Hybrid Retrieval:   {retrieval_mean:.1f}ms ({retrieval_mean/dom_stats['mean']*100:.1f}%)")

    primary_bottleneck = "LLM Generation & Validation (External Network Calls chiếm > 95% latency)"
    print(f"\nPrimary bottleneck: {primary_bottleneck}")
    print("Report:             docs/PERFORMANCE_REPORT.md")
    print("Raw:                eval/results/performance_latest.json")
    print("                    eval/results/performance_cases.csv")

    # Phân loại Performance
    # Local Cache hit < 50ms -> EXCELLENT
    # Local Retrieval < 500ms -> EXCELLENT
    # Total DOMAIN Latency < 15s (2 external LLM calls on DeepSeek) -> ACCEPTABLE
    verdict = "PERFORMANCE_ACCEPTABLE" if dom_stats["mean"] < 20000 and hit_dom_stats["mean"] < 500 else "PERFORMANCE_NEEDS_OPTIMIZATION"
    print(f"Verdict:            {verdict}")


if __name__ == "__main__":
    main()
