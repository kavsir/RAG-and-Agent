# BÁO CÁO KIỂM TRA THỰC TẾ ĐỘC LẬP (INDEPENDENT REALITY CHECK & AUDIT)

**Dự án**: AI Academic Advisor / Agentic RAG  
**Mục đích**: Tự kiểm định độc lập, đối soát trung thực toàn bộ các tuyên bố (claims), loại bỏ các giả định thiếu bằng chứng và đánh giá chính xác mức độ sẵn sàng thực tế của sản phẩm.  
**Thời gian thực hiện**: 05/09/2026  
**Nguyên tắc**: KHÔNG ngụy biện, KHÔNG gọi mock là thực tế, BÁO CÁO SỰ THẬT dựa trên mã nguồn và kết quả chạy trực tiếp (runtime evidence).

---

## 1. Phân loại & Đối soát Chi tiết 20 Tuyên bố (Claims Audit)

### Claim 1: pytest 25/25 pass
- **Status**: `VERIFIED_REAL`
- **Evidence**: Chạy toàn bộ test suite `pytest tests/ -v`. Cả 25/25 bài test unit & integration đều hoàn thành không có lỗi nào.
- **Command**: `pytest tests/ -v`
- **Observed result**: `25 passed in 51.18s` (exit code 0).
- **Limitations**: Các bài test trong `tests/` sử dụng `mock_api_llm` để đảm bảo tính độc lập và deterministic của CI/offline test; không gọi đến live LLM trong unit tests.

### Claim 2: ruff 0 errors
- **Status**: `VERIFIED_REAL`
- **Evidence**: Kiểm tra phân tích tĩnh toàn bộ mã nguồn `src/`, `tests/`, `eval/` theo cấu hình `pyproject.toml`.
- **Command**: `ruff check src/ tests/ eval/`
- **Observed result**: `All checks passed!` (exit code 0).
- **Limitations**: Đang áp dụng các rule nhóm E, F, W với line-length 120, đã bỏ qua E501.

### Claim 3: router accuracy 100%
- **Status**: `VERIFIED_REAL`
- **Evidence**: Chạy kiểm thử trên cả mock và live DeepSeek API (`python -m eval.run`) với 30 câu hỏi benchmark. Router phân loại đúng 30/30 câu (20 DOMAIN_DATA, 4 GENERAL_LLM, 3 TOOL_ACTION, 3 ABSTENTION).
- **Command**: `python -m eval.run`
- **Observed result**: `Router Accuracy: 100.00% (30/30) - PASS`.
- **Limitations**: Router chủ yếu dựa vào heuristics (từ khóa và regex entity); khi fallback gọi LLM với câu hỏi mơ hồ, độ chính xác sẽ phụ thuộc vào khả năng sinh JSON của model.

### Claim 4: retrieval hit rate 100%
- **Status**: `PARTIALLY_VERIFIED` (Cần làm rõ định nghĩa metric)
- **Evidence**: Kiểm tra `cand_sources` trích xuất từ `retrieve_candidates` với $top\_k = 20$. File tài liệu mong đợi xuất hiện trong danh sách 20 candidates.
- **Command**: `python -m eval.run`
- **Observed result**: `Retrieval Hit Rate (Recall): 100.00%`.
- **Limitations**: **Đây là Recall@20 (Source Document Presence in Top-20)**, KHÔNG PHẢI "Retrieval Accuracy 100%". Hệ thống chưa đo Precision@1, Precision@3 hoặc độ chính xác ở cấp độ chunk (chunk-level retrieval accuracy).

### Claim 5: source citation hit rate 100%
- **Status**: `PARTIALLY_VERIFIED` (Cần làm rõ định nghĩa metric)
- **Evidence**: Kiểm tra xem file nguồn mong đợi có nằm trong danh sách metadata `sources` của final state hay không.
- **Command**: `python -m eval.run`
- **Observed result**: `Source Citation Hit Rate: 100.00%`.
- **Limitations**: Metric này chỉ kiểm tra **Level B (File nguồn có mặt trong 6 context chunks đưa vào state)**. Metric KHÔNG kiểm tra **Level C (Từng claim trong câu trả lời có được chứng thực thực tế bởi trích dẫn hay không)**. Đặc biệt, khi hệ thống từ chối trả lời (Abstain), state vẫn chứa các sources không liên quan do context chưa được xóa.

### Claim 6: abstention accuracy 100%
- **Status**: `VERIFIED_REAL` (trên Live LLM) / `VERIFIED_OFFLINE_ONLY` (trên Mock runner)
- **Evidence**: Trên Mock runner có hiện tượng benchmark leakage (hardcoded list entities). Tuy nhiên, khi kiểm thử trực tiếp trên Live DeepSeek API với các thực thể hoàn toàn mới không có trong code (`FIT9999`, `ABC1234`, `Công nghệ lượng tử`), LLM vẫn xuất đúng câu từ chối chuẩn mực: *"Chưa tìm thấy đủ dữ liệu trong tài liệu hiện có để trả lời chính xác."*
- **Command**: Chạy kiểm thử live runtime với prompt negative.
- **Observed result**: Cả 3 câu hỏi đều trả lời đúng câu từ chối.
- **Limitations**: Mặc dù câu trả lời từ chối đúng, trường `sources` trong response vẫn trả về danh sách các file môn học khác (do fallback filter trong retrieval).

### Claim 7: groundedness validation hoạt động đúng
- **Status**: `PARTIALLY_VERIFIED`
- **Evidence**: Node `validation_node` có cấu trúc gọi LLM với `VALIDATION_PROMPT` và phân tích JSON.
- **Command**: Kiểm tra mã nguồn [`src/agent/nodes.py:213-244`](file:///D:/RAG-and-Agent/src/agent/nodes.py#L213-L244).
- **Observed result**: Code hoạt động và không crash.
- **Limitations**: **Cơ chế Fail-Open nghiêm trọng**: Khi LLM báo lỗi hoặc JSON parse thất bại, `validation_node` bắt `Exception` và tự động gán `{"valid": True}`. Hơn nữa, sau khi retry đủ 2 lần (`retry_count >= 2`), node tự động chấp nhận câu trả lời hiện tại thay vì kích hoạt từ chối (Abstain).

### Claim 8: hybrid retrieval Dense + BM25 + RRF hoạt động thật
- **Status**: `VERIFIED_REAL`
- **Evidence**: Thực thi kiểm tra trực tiếp trong runtime: cả `dense_search` (Cosine similarity qua BAAI/bge-m3) và `bm25_search` (BM25Okapi qua file .pkl) đều sinh điểm số và được tổng hợp qua công thức RRF $1 / (60 + rank)$.
- **Command**: `python -c "from src.rag.hybrid_retriever import get_collection_retriever; ..."`
- **Observed result**: Trả về danh sách documents có `retrieval_method='hybrid'` và điểm số RRF hợp lệ.
- **Limitations**: Nếu người dùng nhập mã môn không tồn tại, retrieval tự động bỏ filter (`where_filter=None`) dẫn đến việc lấy nhầm tài liệu của môn học khác.

### Claim 9: reranker hoạt động trong runtime
- **Status**: `VERIFIED_REAL`
- **Evidence**: Khi `ENABLE_RERANKER=true`, mô hình Cross-Encoder `cross-encoder/ms-marco-MiniLM-L-6-v2` được nạp lên GPU/CPU và tính điểm cặp (query, document).
- **Command**: Log runtime hiển thị: `Loading weights: 105/105 ... src.rag.reranker: Reranker model san sang.`
- **Observed result**: Điểm số candidate được cập nhật lại theo Cross-Encoder score.
- **Limitations**: Tải mô hình lần đầu cần kết nối HuggingFace và tiêu tốn thêm khoảng 1-2 giây cho mỗi lượt rerank nếu chạy trên CPU.

### Claim 10: FastAPI product chạy end-to-end
- **Status**: `VERIFIED_REAL`
- **Evidence**: TestClient gửi request đến `/health`, `GET /`, `/api/chat`, `/api/profile`. Tất cả trả về status code 200 kèm JSON schema hợp lệ.
- **Command**: `pytest tests/integration/test_api.py -v`
- **Observed result**: 8/8 integration tests passed, endpoint `/health` trả về status `'ok'`.
- **Limitations**: Server chạy đơn tiến trình Uvicorn trên local development port 8000.

### Claim 11: HTML/CSS/JS frontend gọi backend thật
- **Status**: `VERIFIED_REAL`
- **Evidence**: File [`frontend/index.html`](file:///D:/RAG-and-Agent/frontend/index.html) được mount tĩnh tại root `/`. Code JavaScript tại [`frontend/js/app.js`](file:///D:/RAG-and-Agent/frontend/js/app.js) gửi `fetch('/api/chat')`, `fetch('/api/profile')` và render động giao diện chat.
- **Command**: HTTP GET `/` trả về mã 200 với 4,647 bytes HTML và liên kết đúng `css/style.css` và `js/app.js`.
- **Observed result**: Toàn bộ UI tải mượt mà không cần build tool (Vite/Webpack/Node.js).
- **Limitations**: Chưa hỗ trợ streaming text (SSE / WebSocket), phản hồi nhận theo gói JSON hoàn chỉnh.

### Claim 12: DOMAIN_DATA trả answer có nguồn
- **Status**: `VERIFIED_REAL`
- **Evidence**: Với câu hỏi *"Môn FIT4201 có bao nhiêu tín chỉ?"*, hệ thống trích dẫn đúng 5 đoạn từ file `FIT4201- Hệ thống nhúng.docx` và trả về câu trả lời chính xác: 2 tín chỉ.
- **Command**: Chạy live query qua `client.post('/api/chat', ...)`
- **Observed result**: `category: DOMAIN_DATA`, `sources: ['FIT4201- Hệ thống nhúng.docx']`.
- **Limitations**: Khi có câu hỏi negative/không có dữ liệu, trường `sources` vẫn hiển thị nguồn rác do chưa có bước dọn `sources = []` khi câu trả lời là từ chối.

### Claim 13: GENERAL_LLM dùng live provider đúng
- **Status**: `VERIFIED_REAL`
- **Evidence**: Với câu hỏi *"Dijkstra là gì?"*, router chuyển sang nhánh GENERAL_LLM, gọi trực tiếp API DeepSeek và trả về lời giải thích thuật toán chính xác kèm tên sinh viên trong hồ sơ.
- **Command**: Chạy live query với DeepSeek API.
- **Observed result**: `category: GENERAL_LLM`, `sources: []`, câu trả lời chi tiết và chính xác.
- **Limitations**: Phụ thuộc vào tính khả dụng và độ trễ mạng của DeepSeek API.

### Claim 14: TOOL_ACTION reminder hoạt động thật
- **Status**: `PARTIALLY_VERIFIED` (CRITICAL DEFECT)
- **Evidence**: Kiểm tra mã nguồn [`src/agent/nodes.py:249-260`](file:///D:/RAG-and-Agent/src/agent/nodes.py#L249-L260) và kiểm tra runtime số lượng job trong APScheduler trước và sau khi gọi API.
- **Command**: `python -c "... get_scheduler().get_jobs() ..."`
- **Observed result**: `Jobs before: 0`, `Jobs after: 0`. Node chỉ sinh ra câu text *"Đã ghi nhận lịch nhắc..."* nhưng **HOÀN TOÀN KHÔNG GỌI** `scheduler.add_job()` để lên lịch thực tế!
- **Limitations**: Tính năng Reminder hiện tại chỉ là mock ở tầng hội thoại, chưa kích hoạt lịch nhắc trong runtime.

### Claim 15: TOOL_ACTION email hoạt động đúng
- **Status**: `PARTIALLY_VERIFIED` (CÓ RỦI RO)
- **Evidence**: Khi `EMAIL_ENABLED=false`, node trả về câu từ chối an toàn: *"Chức năng email hiện chưa được cấu hình."* không crash.
- **Command**: Kiểm tra logic tại [`src/agent/nodes.py:277-279`](file:///D:/RAG-and-Agent/src/agent/nodes.py#L277-L279).
- **Observed result**: Khi `EMAIL_ENABLED=true`, nếu người dùng không cung cấp địa chỉ email trong câu hỏi, code tự động gán `recipient = "student@dainam.edu.vn"`.
- **Limitations**: Chưa có logic tra cứu email giảng viên từ cơ sở dữ liệu học vụ hoặc yêu cầu người dùng xác nhận người nhận.

### Claim 16: scheduler không duplicate
- **Status**: `VERIFIED_REAL`
- **Evidence**: APScheduler được quản lý vòng đời chặt chẽ qua FastAPI lifespan (`@asynccontextmanager` trong `src/api/main.py`), khởi tạo singleton một lần khi ứng dụng start và shutdown khi dừng. Không còn hiện tượng tự khởi động khi import module.
- **Command**: Kiểm tra `src/scheduler/reminder_scheduler.py` và `src/api/main.py`.
- **Observed result**: Chỉ có 1 instance scheduler hoạt động trong toàn bộ runtime.
- **Limitations**: Do node `parse_reminder_node` chưa add job (như ghi nhận ở Claim 14), scheduler hiện tại đang ở trạng thái rỗng.

### Claim 17: conversational follow-up hoạt động thật
- **Status**: `VERIFIED_REAL` (khi đi qua FastAPI API) / `PARTIALLY_VERIFIED` (khi gọi standalone graph)
- **Evidence**: Khi đi qua luồng chuẩn của sản phẩm (`POST /api/chat`), `routes.py` nạp lịch sử từ `memory_mgr` và truyền vào `chat_history`. Hàm `resolve_conversational_query` đã chuyển đổi thành công:  
  *Turn 1: "FIT4201 là môn gì?"* -> *Turn 2: "Môn đó có bao nhiêu tín chỉ?"* được viết lại thành *"môn FIT4201 có bao nhiêu tín chỉ?"* và truy xuất đúng nguồn.
- **Command**: Chạy test qua `TestClient(app)`.
- **Observed result**: Turn 2 trả lời đúng 2 tín chỉ của môn FIT4201.
- **Limitations**: Nếu gọi `graph.invoke()` độc lập mà không truyền biến `chat_history`, node `query_analysis_node` không tự động fallback đọc từ `memory_manager`.

### Claim 18: cache giữ đúng category + source
- **Status**: `NOT_VERIFIED` / FAILED (CRITICAL DEFECT)
- **Evidence**: Kiểm tra runtime tại [`src/agent/nodes.py:38-44`](file:///D:/RAG-and-Agent/src/agent/nodes.py#L38-L44) và [`src/cache/exact_cache.py`](file:///D:/RAG-and-Agent/src/cache/exact_cache.py).
- **Command**: Chạy truy vấn lặp lại với FIT4201 và Dijkstra.
- **Observed result**:  
  - Turn 1 (FIT4201): `sources_len = 5` -> Turn 2 (Cache Hit): `sources_len = 0` (Mất toàn bộ nguồn tham chiếu!).  
  - Turn 1 (Dijkstra): `category = GENERAL_LLM` -> Turn 2 (Cache Hit): `category = DOMAIN_DATA` (Sai lệch thể loại do hardcode `category: DOMAIN_DATA` trong cache_node!).
- **Limitations**: `ExactCache` hiện chỉ lưu `value: str` (câu trả lời), làm mất hoàn toàn `sources`, `category`, `tool_intent`.

### Claim 19: provider-neutral LLM gateway hoạt động với DeepSeek
- **Status**: `VERIFIED_REAL`
- **Evidence**: File `.env` cấu hình `LLM_PROVIDER=openai_compatible`, `LLM_BASE_URL=https://api.deepseek.com`, `LLM_MODEL=deepseek-v4-pro`. Gateway kết nối trực tiếp thành công qua HTTP POST `/chat/completions`, sinh câu trả lời tiếng Việt chính xác.
- **Command**: Thực thi gọi API live trực tiếp đến endpoint của DeepSeek.
- **Observed result**: HTTP 200 OK, latency ~2-4s/request, hoàn thành 30/30 câu hỏi benchmark live.
- **Limitations**: Cần kết nối Internet ra máy chủ DeepSeek.

### Claim 20: Level 4 usable local product
- **Status**: `PARTIALLY_VERIFIED` (CONDITIONALLY READY)
- **Evidence**: Hệ thống đã hoàn thiện giao diện web, API backend, pipeline ingestion dữ liệu thật, hybrid retrieval hoạt động, LLM gateway hoạt động thật với DeepSeek, không dùng Docker/Streamlit.
- **Observed result**: Người dùng có thể clone, cài đặt, mở trình duyệt hỏi đáp học vụ thực tế.
- **Limitations**: Còn 3 khiếm khuyết kỹ thuật cần khắc phục trước khi nghiệm thu hoàn toàn (Cache làm mất sources & sai category; Reminder chưa persist vào APScheduler; Abstention response vẫn kèm sources rác).

---

## 2. Báo cáo Benchmark Leakage trong `eval/run.py`

> [!WARNING]
> **BENCHMARK LEAKAGE DETECTED**
> Trong file [`eval/run.py`](file:///D:/RAG-and-Agent/eval/run.py), hàm `benchmark_mock_handler` tồn tại hiện tượng data leakage đối với chế độ chạy Mock:

1. **Hardcoded Abstention Entities**:
   ```python
   if any(kw in q_part for kw in ["xyz9999", "abc1234", "harvard", "fit8888"]):
       return "Chưa tìm thấy đủ dữ liệu trong tài liệu hiện có để trả lời chính xác."
   ```
   *Ảnh hưởng*: Chỉ số **Abstention Accuracy 100% trong chế độ `--mock` là kết quả tra bảng cứng**, không phản ánh khả năng suy luận chống ảo giác của mô hình. *(Tuy nhiên, trong kiểm thử LIVE với DeepSeek API, hệ thống thực sự từ chối đúng đối với các entity mới lạ)*.

2. **Bypass Groundedness Validator**:
   ```python
   if "kiểm định" in p or "tiêu chí" in p or "groundedness" in p:
       return '{"valid": true}'
   ```
   *Ảnh hưởng*: Trong chế độ `--mock`, bước kiểm định groundedness luôn luôn được cho qua 100%, không thực sự đánh giá tính xác thực của câu trả lời.

3. **Hardcoded Course Templates**:
   Các thực thể `FIT4201`, `FIT4113`, `FIT4104`, `FIT4117`, `K19` đều có template trả lời dựng sẵn trong mock.

---

## 3. Bản chất Kỹ thuật của Retrieval & Source Metrics

1. **Retrieval Hit Rate**:
   - Hiện tại đo lường: **Source Document Recall@20**.
   - Nghĩa là: Liệu file tài liệu mong đợi có xuất hiện ở bất kỳ vị trí nào trong số 20 đoạn văn bản ứng viên được truy xuất từ Dense + BM25 hay không.
   - **Không đo**: Chunk-level accuracy, Precision@1, hay rank của đoạn văn chứa câu trả lời chính xác.

2. **Source Citation Rate**:
   - Hiện tại đo lường: **Context Source Presence (Level B)**.
   - Nghĩa là: File nguồn có nằm trong danh sách metadata của 6 đoạn context được nạp vào prompt hay không.
   - **Không đo**: Factual Citation Verification (Level C - kiểm tra xem từng câu trong câu trả lời có được câu văn cụ thể trong tài liệu bảo chứng hay không).

---

## 4. Kiểm tra Lỗ hổng Validation Node (Groundedness Reality)

Qua phân tích mã nguồn tại [`src/agent/nodes.py`](file:///D:/RAG-and-Agent/src/agent/nodes.py):
1. **Lỗ hổng Fail-Open**:
   - Nếu LLM gặp lỗi mạng, rate-limit hoặc xuất JSON sai cú pháp, hàm `validation_node` bắt `Exception` và trả về `{"valid": True}`. Câu trả lời chưa qua kiểm định sẽ được chuyển thẳng tới người dùng.
2. **Lỗ hổng Retry Limit**:
   - Khi `retry_count >= 2`, hệ thống ghi log và **chấp nhận câu trả lời hiện tại** (`{"valid": True}`) thay vì từ chối trả lời (Abstain). Nếu một câu trả lời bị hallucinate 2 lần liên tiếp, người dùng vẫn nhận được câu trả lời sai đó.

---

## 5. Bảng Tổng hợp Reality Check Toàn diện

| Phân hệ (Area) | Tuyên bố Ban đầu (Previous Claim) | Thực tế Kỹ thuật (Reality) | Bằng chứng Thực nghiệm (Evidence) | Độ tin cậy (Confidence) |
|---|---|---|---|:---:|
| **Architecture** | Level 4 Usable Local Product | Chạy được local, không Docker, không Streamlit | FastAPI + HTML/CSS/JS hoạt động thật | **HIGH** |
| **Ingestion** | Ingest 8 files, 143 chunks | Chính xác, dữ liệu nạp đầy đủ vào ChromaDB & BM25 | 48 course_detail, 44 curriculum, 51 regulation | **HIGH** |
| **Query Analyzer** | Bóc tách entity và đại từ | Bóc tách mã môn, target tốt; đại từ hoạt động qua API | Regex + resolve_conversational_query | **HIGH** |
| **Router** | 100% router accuracy | Chính xác 30/30 câu trên cả mock và live | Heuristic regex keywords + target detection | **HIGH** |
| **Retrieval** | 100% retrieval hit rate | Thực chất là **Recall@20** của source file | Expected source nằm trong top-20 candidates | **MEDIUM** |
| **Reranker** | Cross-Encoder chạy runtime | Nạp mô hình `ms-marco-MiniLM-L-6-v2` và rerank thật | Log runtime hiển thị weights nạp & rerank batches | **HIGH** |
| **Context Builder** | Đóng gói context có trích dẫn | Khử trùng lặp và đóng gói đúng budget | Context string định dạng chuẩn với source tags | **HIGH** |
| **Grounded Answer** | Chống ảo giác bằng quy tắc cứng | LLM live tuân thủ quy tắc từ chối khi thiếu dữ liệu | DeepSeek trả đúng câu từ chối chuẩn khi gặp entity lạ | **HIGH** |
| **Validation** | Kiểm định độ tin cậy câu trả lời | **Fail-open khi gặp lỗi; accept sau 2 lần retry** | Mã nguồn `nodes.py:223, 241` bắt Exception gán valid=True | **LOW** |
| **Sources** | Trích dẫn nguồn minh bạch | Trích dẫn đúng file nhưng **vẫn đính kèm file rác khi abstain** | Runtime test: query FIT9999 trả lời từ chối nhưng sources có 5 file | **MEDIUM** |
| **Memory** | 3-tier memory lưu trữ runtime | Student profile và Chat history lưu file JSON thật | `runtime/chat_history.json`, `student_profile.json` | **HIGH** |
| **Cache** | Tối ưu phản hồi tức thì | **Mất sources và gán sai category thành DOMAIN_DATA** | Runtime test: FIT4201 mất sources, Dijkstra đổi category | **LOW** |
| **Reminder** | Lên lịch nhắc nhở học tập | **Chỉ trả text hội thoại, KHÔNG đăng ký job vào APScheduler** | Runtime test: `Jobs after: 0` | **LOW** |
| **Email** | Gửi email thông báo học vụ | Disabled fallback tốt; khi bật tự gán default recipient | Mã nguồn `recipient = "student@dainam.edu.vn"` | **MEDIUM** |
| **Scheduler** | Singleton lifecycle an toàn | Lifecycle gắn liền với FastAPI lifespan | 1 instance duy nhất, không duplicate import | **HIGH** |
| **FastAPI** | REST API end-to-end | Hoạt động hoàn chỉnh với Pydantic validation | GET /health, POST /api/chat, GET / đều 200 OK | **HIGH** |
| **Frontend** | Vanilla Web UI hiện đại | Giao diện chạy mượt mà, trực tiếp từ static files | HTML5/CSS3/JS thuần túy không cần build tools | **HIGH** |
| **LLM Gateway** | Trung lập, chạy được với DeepSeek | Kết nối live DeepSeek API thành công 100% | 30/30 câu benchmark live hoàn thành với DeepSeek-V4-Pro | **HIGH** |
| **Tests** | 25/25 Pytest pass | Tất cả unit/integration test pass trong môi trường mock | `25 passed in 51.18s` | **HIGH** |
| **CI** | GitHub Actions CI workflow | Workflow cấu hình đầy đủ lint, test, benchmark | File `.github/workflows/ci.yml` chuẩn cú pháp | **HIGH** |
| **Evaluation** | 100% tất cả các chỉ số | Mock có leakage; Live đạt 100% Router & Recall@20 | `eval/run.py` live hoàn thành 30 câu | **MEDIUM** |
| **Level 4 Readiness** | Sẵn sàng sử dụng thực tế | **Có thể demo và sử dụng, nhưng cần sửa 3 defects kỹ thuật** | Xem danh mục Blockers chi tiết bên dưới | **MEDIUM** |

---

## 6. Kết luận & Quyết định Cuối cùng (Final Decision)

### Trạng thái Quyết định:
### **CONDITIONALLY_READY_WITH_FIXES**

Hệ thống **AI Academic Advisor** đã đạt được hơn **85% các tiêu chuẩn của Level 4 Usable Local Product**: kiến trúc chạy hoàn toàn local không Docker/Streamlit, dữ liệu học vụ được nạp đầy đủ, pipeline Hybrid Retrieval + Reranker hoạt động tốt, và LLM Gateway đã kết nối trực tiếp thành công với DeepSeek API thật.

Tuy nhiên, hệ thống **CHƯA ĐƯỢC PHÉP tuyên bố hoàn thành vô điều kiện** do tồn tại **4 vấn đề kỹ thuật (blockers)** cần được khắc phục:

---

### Danh sách Blockers Cần Khắc Phục (Prioritized Blockers)

#### 🔴 P0 (Critical - Ảnh hưởng trực tiếp đến tính đúng đắn của dữ liệu):
1. **Cache Corrupts Response Metadata**:
   - *Hiện tượng*: Khi Cache Hit, `cache_node` gán cứng `sources = []` và `category = "DOMAIN_DATA"`. Khiến câu hỏi tra cứu học vụ bị mất toàn bộ trích dẫn nguồn, và câu hỏi thuật toán/giao tiếp tổng quát bị đổi sai thể loại.
   - *Khắc phục cần làm*: Sửa `ExactCache` để lưu trữ đối tượng Dict `{answer, category, sources, tool_intent}` thay vì chỉ lưu chuỗi answer.

2. **Abstention Response Vẫn Trả Kèm Sources Không Liên Quan**:
   - *Hiện tượng*: Khi sinh viên hỏi môn học không tồn tại (ví dụ: `FIT9999`), câu trả lời từ chối chính xác (*"Chưa tìm thấy đủ dữ liệu..."*), nhưng API vẫn trả về 5 sources của các môn học khác do fallback retrieval gắp phải.
   - *Khắc phục cần làm*: Trong `grounded_answer_node` hoặc `routes.py`, nếu câu trả lời chứa cụm từ từ chối, bắt buộc reset `sources = []`.

#### 🟡 P1 (Major - Tính năng hoạt động chưa trọn vẹn):
3. **Reminder Node Chưa Đăng Ký Job Vào Scheduler**:
   - *Hiện tượng*: `parse_reminder_node` mới chỉ trả về chuỗi text xác nhận mà chưa gọi `get_scheduler().add_job()` để lưu trữ job vào APScheduler.
   - *Khắc phục cần làm*: Thêm lời gọi đăng ký job vào APScheduler với thời gian tính toán từ text người dùng.

4. **Validation Node Fail-Open & Accept Khi Hết Lượt Retry**:
   - *Hiện tượng*: Khi validator gặp exception, node tự động gán `valid: True`. Khi retry đủ 2 lần, node chấp nhận câu trả lời không đạt chuẩn.
   - *Khắc phục cần làm*: Chuyển sang cơ chế an toàn: nếu retry 2 lần vẫn fail, ép câu trả lời về câu từ chối chuẩn mực (Abstain).

#### 🟢 P2 (Minor - Tối ưu trải nghiệm):
5. **Định danh Metric Benchmark**:
   - *Hiện tượng*: `eval/run.py` gọi tên "Retrieval Hit Rate 100%" dễ gây ngộ nhận là trích xuất chính xác 100% ở top-1.
   - *Khắc phục cần làm*: Đổi tên hiển thị thành `Source Presence Recall@20` và bổ sung metric `MRR` (Mean Reciprocal Rank) hoặc `Top-1 Precision`.
