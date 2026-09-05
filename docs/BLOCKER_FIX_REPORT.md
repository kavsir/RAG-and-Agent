# BÁO CÁO KHẮC PHỤC BLOCKER VÀ NGHIỆM THU THỰC TẾ (BLOCKER FIX & ACCEPTANCE REPORT)

**Dự án**: AI Academic Advisor / Agentic RAG (Khoa CNTT - Đại học Đại Nam)  
**Ngày thực hiện**: 06/09/2026  
**Trạng thái kiểm định trước**: `CONDITIONALLY_READY_WITH_FIXES`  
**Kết luận sau khi khắc phục**: **`BLOCKERS_FIXED`**

---

## 1. TỔNG QUAN CÁC THAY ĐỔI THEO TỪNG VẤN ĐỀ

Toàn bộ các blocker xác định trong đợt *Reality Check* đã được khắc phục triệt để và kiểm chứng bằng test tự động cũng như chạy runtime thực tế với DeepSeek API:

| Mã Blocker | Mức độ | Vấn đề ban đầu | Giải pháp thực hiện | Trạng thái |
| :--- | :--- | :--- | :--- | :--- |
| **P0-1** | P0 | ExactCache chỉ lưu chuỗi answer; gán cứng `category=DOMAIN_DATA` và `sources=[]` khi cache hit | Refactor ExactCache lưu structured payload `{answer, category, tool_intent, sources, metadata}`. Khôi phục đầy đủ metadata khi hit | **ĐÃ KHẮC PHỤC** |
| **P0-2** | P0 | Môn học lạ (FIT9999) rơi vào un-filtered fallback làm ô nhiễm context và vẫn trả về sources | Chặn tuyệt đối fallback bỏ filter khi có thực thể mạnh (`course_code`). Reset `sources=[]` khi model từ chối trả lời | **ĐÃ KHẮC PHỤC** |
| **P1-1** | P1 | Validation có cơ chế fail-open khi lỗi JSON/Exception; khi retry quá số lần vẫn chấp nhận câu trả lời cũ | Fail-safe: Exception và JSON lỗi được tính là `valid=False`. Khi chạm ngưỡng retry (2), cưỡng chế câu từ chối chuẩn và xóa `sources` | **ĐÃ KHẮC PHỤC** |
| **P1-2** | P1 | Reminder chỉ trả chuỗi template giả lập, không gọi APScheduler thật | Viết bộ bóc tách thời gian (`parse_reminder_datetime`), tích hợp `schedule_reminder()` đăng ký job thật vào APScheduler | **ĐÃ KHẮC PHỤC** |
| **Email Fix** | P1 | Gửi email không có người nhận tự động fallback về `student@dainam.edu.vn` | Kiểm tra regex email hợp lệ; nếu thiếu email thì từ chối gửi và yêu cầu người dùng cung cấp địa chỉ | **ĐÃ KHẮC PHỤC** |
| **Eval Cleanup**| P2 | Tên nhãn đánh giá gây hiểu nhầm ("Retrieval Hit Rate", "Source Citation Hit Rate") | Đổi tên chuẩn xác thành `Source Recall@20` và `Context Source Presence Rate` | **ĐÃ KHẮC PHỤC** |

---

## 2. CHI TIẾT KỸ THUẬT CÁC THAY ĐỔI (CODE DIFF & ARCHITECTURE)

### 2.1. P0-1 — Structured Exact Cache
* **Tệp thay đổi**: [`src/cache/exact_cache.py`](file:///D:/RAG-and-Agent/src/cache/exact_cache.py), [`src/agent/nodes.py`](file:///D:/RAG-and-Agent/src/agent/nodes.py)
* **Nguyên nhân gốc**: `ExactCache.get()` chỉ trả về `str`. Trong `cache_node`, code gán cứng `category = "DOMAIN_DATA"` và `sources = []`. Do đó:
  1. Câu hỏi chung (`GENERAL_LLM`) khi cache hit bị biến thành `DOMAIN_DATA`.
  2. Câu hỏi học vụ (`DOMAIN_DATA`) khi cache hit bị mất toàn bộ danh sách trích dẫn nguồn (`sources`).
* **Giải pháp**:
  - `ExactCache.set()` nhận: `key`, `answer`, `category`, `sources`, `tool_intent`, `metadata`.
  - `cache_node` khôi phục đúng nguyên vẹn `category`, `sources`, `tool_intent` từ cache.
  - `save_chat_node` ghi đầy đủ payload có cấu trúc vào cache.

### 2.2. P0-2 — Safe Abstention & Unknown Entity Retrieval Isolation
* **Tệp thay đổi**: [`src/rag/hybrid_retriever.py`](file:///D:/RAG-and-Agent/src/rag/hybrid_retriever.py), [`src/agent/nodes.py`](file:///D:/RAG-and-Agent/src/agent/nodes.py), [`src/api/routes.py`](file:///D:/RAG-and-Agent/src/api/routes.py)
* **Nguyên nhân gốc**: Khi tìm kiếm môn học lạ như `FIT9999`, bộ lọc ChromaDB trả về 0 kết quả. Retriever tự động fallback sang tìm kiếm không filter, kéo theo chunks của các môn học khác (`FIT4201`, `FIT3101`...) đưa vào context. Model tuy có thể từ chối nhưng API response vẫn chứa sources không liên quan.
* **Giải pháp**:
  - Trong `hybrid_retriever.py`: Thêm cờ `has_strong_entity = bool(where_filter and "course_code" in where_filter)`. Nếu `has_strong_entity == True`, tuyệt đối KHÔNG fallback bỏ bộ lọc và KHÔNG mở rộng cross-collection.
  - Trong `grounded_answer_node` & `validation_node`: Nếu `len(context_chunks) == 0` hoặc câu trả lời là từ chối (*"chưa tìm thấy đủ dữ liệu"*), bắt buộc reset `sources = []`.
  - Trong `routes.py`: Đảm bảo tầng API cũng bảo vệ quy tắc `sources = []` khi câu trả lời là từ chối.

### 2.3. P1-1 — Fail-Safe Validation Node
* **Tệp thay đổi**: [`src/agent/nodes.py`](file:///D:/RAG-and-Agent/src/agent/nodes.py)
* **Nguyên nhân gốc**: Khối `try...except` bắt ngoại lệ trong `validation_node` trả về `{"valid": True}` (fail-open). Khi retry vượt quá `MAX_VALIDATION_RETRIES`, code cũng trả về `{"valid": True}` mà không thay đổi nội dung, dẫn tới rò rỉ câu trả lời hallucinated.
* **Giải pháp**:
  - Khi bắt ngoại lệ parse JSON hoặc LLM API lỗi: đặt `valid = False`.
  - Nếu `retry_count < MAX_VALIDATION_RETRIES`: tăng `retry_count + 1`, định tuyến quay lại `retrieve` để lấy thêm context hoặc sinh lại.
  - Nếu `retry_count >= MAX_VALIDATION_RETRIES`: Cưỡng chế câu trả lời về câu từ chối chuẩn:
    `"Chưa tìm thấy đủ dữ liệu trong tài liệu hiện có để trả lời chính xác."`, đồng thời reset `sources = []`, đặt `valid = True` để thoát khỏi vòng lặp an toàn sang node `save_chat`.

### 2.4. P1-2 — Tích hợp APScheduler Thật cho Nhắc nhở
* **Tệp thay đổi**: [`src/agent/nodes.py`](file:///D:/RAG-and-Agent/src/agent/nodes.py), [`src/scheduler/reminder_scheduler.py`](file:///D:/RAG-and-Agent/src/scheduler/reminder_scheduler.py)
* **Nguyên nhân gốc**: `parse_reminder_node` sinh chuỗi text xác nhận giả lập mà không hề thêm job vào scheduler.
* **Giải pháp**:
  - Xây dựng hàm `parse_reminder_datetime(text)` hỗ trợ bóc tách giờ phút (`17h`, `17:00`, `8 giờ`), ngày tháng (`20/12/2026`, `20/12`), các từ chỉ thời gian tương đối (`hôm nay`, `ngày mai`).
  - Gọi `schedule_reminder(target_dt, _reminder_job_callback, [content])` để đăng ký job thật vào APScheduler `BackgroundScheduler`.
  - Trả về tin nhắn xác nhận kèm thông tin đầy đủ: Mã lịch nhắc (`job.id`), Nội dung nhắc, Thời gian nhắc.
  - Nếu người dùng chưa cung cấp thời gian cụ thể hoặc thời gian ở quá khứ: Phản hồi yêu cầu cung cấp thời gian rõ ràng và không tạo job rác.

### 2.5. Email Safety Check
* **Tệp thay đổi**: [`src/agent/nodes.py`](file:///D:/RAG-and-Agent/src/agent/nodes.py)
* **Nguyên nhân gốc**: Gán cứng `to_email = "student@dainam.edu.vn"` khi người dùng không ghi địa chỉ email trong tin nhắn.
* **Giải pháp**: Dùng regex kiểm tra định dạng email `[\w\.-]+@[\w\.-]+\.\w+`. Nếu không tìm thấy email, phản hồi lịch sự hướng dẫn người dùng cung cấp địa chỉ email người nhận và không thực hiện gửi.

### 2.6. Chuẩn hóa Nhãn Đánh giá
* **Tệp thay đổi**: [`eval/run.py`](file:///D:/RAG-and-Agent/eval/run.py)
* Đổi tên `Retrieval Hit Rate` thành `Source Recall@20` (Đúng với bản chất: tìm thấy tài liệu nguồn trong top-20 candidates).
* Đổi tên `Source Citation Hit Rate` thành `Context Source Presence Rate` (Đúng với bản chất: tài liệu nguồn có mặt trong context window 6 chunks).

---

## 3. BẰNG CHỨNG KIỂM ĐỊNH RUNTIME & THỰC NGHIỆM

### 3.1. Phân tích tĩnh (Static Analysis)
- **Lệnh**: `ruff check src/ tests/ eval/`
- **Kết quả**:
  ```text
  All checks passed!
  ```
- **Exit code**: `0`

### 3.2. Test Suite Tự động Toàn diện (39/39 Tests Pass)
- **Lệnh**: `pytest tests/ -v`
- **Kết quả**:
  ```text
  ============================= test session starts =============================
  platform win32 -- Python 3.12.10, pytest-9.0.3, pluggy-1.6.0
  rootdir: D:\RAG-and-Agent
  configfile: pyproject.toml
  collected 39 items

  tests/integration/test_api.py::test_health_endpoint PASSED               [  2%]
  tests/integration/test_api.py::test_chat_domain_data PASSED              [  5%]
  tests/integration/test_api.py::test_chat_general_llm PASSED              [  7%]
  tests/integration/test_api.py::test_chat_tool_reminder PASSED            [ 10%]
  tests/integration/test_api.py::test_chat_insufficient_evidence PASSED    [ 12%]
  tests/integration/test_api.py::test_chat_invalid_request PASSED          [ 15%]
  tests/integration/test_api.py::test_profile_lifecycle PASSED             [ 17%]
  tests/integration/test_api.py::test_clear_conversations PASSED           [ 20%]
  tests/test_agent_smoke.py::test_agent_graph_routes PASSED                [ 23%]
  tests/unit/test_abstention.py::test_unknown_course_code_no_filter_drop[FIT9999] PASSED [ 25%]
  tests/unit/test_abstention.py::test_unknown_course_code_no_filter_drop[XYZ1234] PASSED [ 28%]
  tests/unit/test_abstention.py::test_unknown_course_code_no_filter_drop[FIT8888] PASSED [ 30%]
  tests/unit/test_cache.py::test_exact_cache_operations PASSED             [ 33%]
  tests/unit/test_cache.py::test_cache_node_domain_restoration PASSED      [ 35%]
  tests/unit/test_cache.py::test_cache_node_general_llm_preservation PASSED [ 38%]
  tests/unit/test_cache.py::test_cache_node_tool_action_preservation PASSED [ 41%]
  tests/unit/test_context_builder.py::test_target_relevance_boost PASSED   [ 43%]
  tests/unit/test_context_builder.py::test_build_context_deduplication PASSED [ 46%]
  tests/unit/test_context_builder.py::test_build_context_budget_limit PASSED [ 48%]
  tests/unit/test_query_analyzer.py::test_extract_course_code PASSED       [ 51%]
  tests/unit/test_query_analyzer.py::test_extract_lecturer_target PASSED   [ 53%]
  tests/unit/test_query_analyzer.py::test_conversational_query_resolution PASSED [ 56%]
  tests/unit/test_query_analyzer.py::test_analyze_query_domain_regulation PASSED [ 58%]
  tests/unit/test_query_analyzer.py::test_analyze_query_domain_curriculum PASSED [ 61%]
  tests/unit/test_router.py::test_router_domain_data_with_code PASSED      [ 64%]
  tests/unit/test_router.py::test_router_domain_data_with_keywords PASSED  [ 66%]
  tests/unit/test_router.py::test_router_general_llm PASSED                [ 69%]
  tests/unit/test_router.py::test_router_tool_reminder PASSED              [ 71%]
  tests/unit/test_router.py::test_router_tool_email PASSED                 [ 74%]
  tests/unit/test_tools.py::test_email_sender_disabled_fallback PASSED     [ 76%]
  tests/unit/test_scheduler_lifecycle PASSED                               [ 79%]
  tests/unit/test_tools.py::test_reminder_node_creates_real_job PASSED     [ 82%]
  tests/unit/test_tools.py::test_reminder_node_insufficient_time_info PASSED [ 84%]
  tests/unit/test_tools.py::test_email_safety_no_recipient PASSED          [ 87%]
  tests/unit/test_validation.py::test_validation_valid PASSED              [ 89%]
  tests/unit/test_validation.py::test_validation_invalid_retry_under_limit PASSED [ 92%]
  tests/unit/test_validation.py::test_validation_invalid_retry_limit_reached_abstains PASSED [ 94%]
  tests/unit/test_validation.py::test_validation_malformed_json_fails_safe PASSED [ 97%]
  tests/unit/test_validation.py::test_validation_exception_fails_safe PASSED [100%]

  ============================= 39 passed in 38.21s =============================
  ```

### 3.3. Kiểm thử Trực tiếp API Live End-to-End (`tests/test_live_acceptance.py`)
Kiểm thử 5 kịch bản chấp nhận trực tiếp trên nền tảng FastAPI Client với Live DeepSeek LLM:

1. **Acceptance 1: DOMAIN CACHE**
   - Lượt 1: Hỏi `"Môn FIT4201 có bao nhiêu tín chỉ?"` $\rightarrow$ Phản hồi từ LLM, `category = DOMAIN_DATA`, `sources_count = 5`.
   - Lượt 2: Hỏi lại đúng câu trên $\rightarrow$ Cache HIT tức thì, `category = DOMAIN_DATA`, `sources_count = 5` (giữ nguyên đầy đủ trích dẫn và danh mục).
   - **Kết quả**: `PASS: DOMAIN CACHE`.

2. **Acceptance 2: GENERAL CACHE**
   - Lượt 1: Hỏi `"Dijkstra là gì?"` $\rightarrow$ `category = GENERAL_LLM`, `sources_count = 0`.
   - Lượt 2: Hỏi lại câu trên $\rightarrow$ Cache HIT tức thì, `category = GENERAL_LLM`, `sources_count = 0` (không bị đổi thành DOMAIN_DATA).
   - **Kết quả**: `PASS: GENERAL CACHE`.

3. **Acceptance 3: SAFE ABSTENTION CHO MÃ MÔN LẠ**
   - Hỏi `"Môn FIT9999 có bao nhiêu tín chỉ?"`.
   - Retriever lọc chính xác theo `course_code = FIT9999`, trả về 0 candidates (không fallback làm rò rỉ môn khác).
   - Answer: `"Chưa tìm thấy đủ dữ liệu trong tài liệu hiện có để trả lời chính xác."`.
   - `sources_count = 0`.
   - **Kết quả**: `PASS: SAFE ABSTENTION`.

4. **Acceptance 4: MULTI-TURN CONVERSATION RESOLUTION**
   - Lượt 1: `"FIT4201 là môn gì?"` $\rightarrow$ Trả lời: *"FIT4201 là mã học phần của môn Hệ thống nhúng..."*.
   - Lượt 2: `"Môn đó có bao nhiêu tín chỉ?"` $\rightarrow$ Bộ giải quyết ngữ cảnh tự động chuyển đổi thành `"môn FIT4201 có bao nhiêu tín chỉ?"`, truy xuất đúng tài liệu và trả lời: *"Học phần Hệ thống nhúng (mã học phần: FIT4201) có 2 tín chỉ..."* kèm trích dẫn chính xác.
   - **Kết quả**: `PASS: MULTI-TURN FOLLOW-UP`.

5. **Acceptance 5: ĐẶT LỊCH NHẮC NHỞ APSCHEDULER THẬT**
   - Yêu cầu: `"Nhắc tôi nộp bài tập lớn lúc 17h ngày 20/12/2026"`.
   - Số job trước yêu cầu: `0`.
   - Số job sau yêu cầu: `1`.
   - Nội dung phản hồi:
     ```text
     ✅ Đã lên lịch nhắc nhở thành công!
     - Nội dung: Nhắc tôi nộp bài tập lớn lúc 17h ngày 20/12/2026
     - Thời gian: 20/12/2026 17:00
     - Mã lịch nhắc: 518d54e7bd1d41cd850b46ae74725610
     ```
   - **Kết quả**: `PASS: REMINDER CREATION`.

```text
>>> ALL 5 LIVE ACCEPTANCE TESTS PASSED! <<<
```

---

## 4. CÁC HẠN CHẾ CÒN LẠI VÀ KHUYẾN NGHỊ VẬN HÀNH (LIMITATIONS & OPS)

1. **Bộ phân tích thời gian nhắc nhở (Datetime parser)**:
   - Hiện tại bộ parser hỗ trợ tốt các định dạng ngày/tháng/năm chuẩn của người Việt (`17h ngày 20/12/2026`, `8:30 ngày mai`, `15h hôm nay`).
   - Các biểu đạt phức tạp như *"thứ hai tuần tới"* hoặc *"cuối tuần này"* chưa được quy đổi tự động mà hệ thống sẽ yêu cầu người dùng chỉ định rõ ngày giờ cụ thể để đảm bảo tính an toàn.
2. **Lưu trữ Job của APScheduler**:
   - Hiện cấu hình mặc định dùng `MemoryJobStore`. Khi tắt server, các nhắc nhở chưa chạy trong RAM sẽ mất đi. Trong môi trường production lâu dài, có thể chuyển sang `SQLAlchemyJobStore` với file SQLite có sẵn.
3. **Exact Cache Scope**:
   - Cache hiện tại là Exact Query String Cache (đã chuẩn hóa lowercase/strip). Nếu câu hỏi thay đổi một vài từ đồng nghĩa, hệ thống sẽ thực hiện Agentic RAG đầy đủ thay vì cache hit. Đây là chủ đích thiết kế để đảm bảo không trả nhầm dữ liệu.

---

## 5. KẾT LUẬN CUỐI CÙNG (FINAL VERDICT)

Sau khi kiểm định độc lập và khắc phục toàn bộ các lỗi thực tế (P0-1, P0-2, P1-1, P1-2, Email Safety, Eval Labels), hệ thống đã đạt trạng thái sẵn sàng cao, hoạt động an toàn, chính xác và không còn bất kỳ blocker nào.

**KẾT LUẬN**: **`BLOCKERS_FIXED`**
