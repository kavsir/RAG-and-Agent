from fastapi.testclient import TestClient
from src.api.main import app
from src.scheduler.reminder_scheduler import get_scheduler

def run_acceptance():
    client = TestClient(app)

    print("=== 1. DOMAIN CACHE ACCEPTANCE ===")
    r1 = client.post("/api/chat", json={"message": "Môn FIT4201 có bao nhiêu tín chỉ?", "session_id": "acc-test-1"})
    d1 = r1.json()
    print(f"Turn 1: category={d1.get('category')} sources_count={len(d1.get('sources', []))} answer={d1.get('answer', '')[:60]}...")

    r2 = client.post("/api/chat", json={"message": "Môn FIT4201 có bao nhiêu tín chỉ?", "session_id": "acc-test-1"})
    d2 = r2.json()
    print(f"Turn 2 (Cache): category={d2.get('category')} sources_count={len(d2.get('sources', []))} answer={d2.get('answer', '')[:60]}...")
    assert d1["category"] == d2["category"] == "DOMAIN_DATA", "Domain category mismatch"
    assert len(d1["sources"]) == len(d2["sources"]) > 0, "Domain sources dropped in cache hit"
    print("PASS: DOMAIN CACHE")

    print("\n=== 2. GENERAL CACHE ACCEPTANCE ===")
    r3 = client.post("/api/chat", json={"message": "Dijkstra là gì?", "session_id": "acc-test-2"})
    d3 = r3.json()
    print(f"Turn 1: category={d3.get('category')} sources_count={len(d3.get('sources', []))}")

    r4 = client.post("/api/chat", json={"message": "Dijkstra là gì?", "session_id": "acc-test-2"})
    d4 = r4.json()
    print(f"Turn 2 (Cache): category={d4.get('category')} sources_count={len(d4.get('sources', []))}")
    assert d3["category"] == d4["category"] == "GENERAL_LLM", "General category mismatch"
    assert len(d4["sources"]) == 0, "General cache should not have sources"
    print("PASS: GENERAL CACHE")

    print("\n=== 3. SAFE ABSTENTION ACCEPTANCE ===")
    r5 = client.post("/api/chat", json={"message": "Môn FIT9999 có bao nhiêu tín chỉ?", "session_id": "acc-test-3"})
    d5 = r5.json()
    print(f"Abstention: sources_count={len(d5.get('sources', []))} answer={d5.get('answer', '')[:80]}...")
    assert len(d5.get("sources", [])) == 0, "Abstention should have 0 sources"
    assert any(k in d5["answer"].lower() for k in ["không", "chưa", "không có", "không tìm thấy", "chưa tìm thấy"]), "Answer should express abstention"
    print("PASS: SAFE ABSTENTION")

    print("\n=== 4. MULTI-TURN FOLLOW-UP ===")
    r6 = client.post("/api/chat", json={"message": "FIT4201 là môn gì?", "session_id": "acc-test-4"})
    d6 = r6.json()
    print(f"Turn 1: answer={d6.get('answer', '')[:60]}...")
    r7 = client.post("/api/chat", json={"message": "Môn đó có bao nhiêu tín chỉ?", "session_id": "acc-test-4"})
    d7 = r7.json()
    print(f"Turn 2: answer={d7.get('answer', '')[:60]}...")
    assert len(d7.get("sources", [])) > 0 or "tín chỉ" in d7["answer"].lower()
    print("PASS: MULTI-TURN FOLLOW-UP")

    print("\n=== 5. REMINDER CREATION ACCEPTANCE ===")
    sched = get_scheduler()
    sched.remove_all_jobs()
    jobs_before = len(sched.get_jobs())
    r8 = client.post("/api/chat", json={"message": "Nhắc tôi nộp bài tập lớn lúc 17h ngày 20/12/2026", "session_id": "acc-test-5"})
    d8 = r8.json()
    jobs_after = len(sched.get_jobs())
    print(f"Jobs before: {jobs_before}, after: {jobs_after}")
    print(f"Reminder answer: {d8.get('answer')}")
    assert jobs_after == 1, "Job was not created"
    assert "Mã lịch nhắc:" in d8.get("answer", ""), "Job ID label missing in answer"
    sched.remove_all_jobs()
    print("PASS: REMINDER CREATION")

    print("\n>>> ALL 5 LIVE ACCEPTANCE TESTS PASSED! <<<")

if __name__ == "__main__":
    run_acceptance()
