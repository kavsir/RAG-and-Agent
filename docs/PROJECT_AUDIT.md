# BÁO CÁO AUDIT DỰ ÁN RAG-AND-AGENT
**Hệ thống:** AI Academic Advisor / Agentic RAG - Khoa CNTT, Trường Đại học Đại Nam  
**Ngày thực hiện:** 26/03/2026  
**Mục tiêu:** Đánh giá toàn diện hiện trạng, phát hiện lỗi và lập kế hoạch chuyển đổi sang Usable Local Product (FastAPI + Vanilla JS + LangGraph).

---

## 1. TỔNG QUAN HIỆN TRẠNG REPOSITORY

Repository ban đầu được phát triển dưới dạng prototype kết hợp LangGraph, ChromaDB, BM25 và Streamlit UI. Qua quá trình kiểm tra chi tiết từng file mã nguồn, hệ thống có nhiều thành phần nền tảng tốt (đặc biệt là logic bóc tách đề cương chi tiết trong Ingestion) nhưng gặp phải các lỗi nghiêm trọng về vòng đời ứng dụng, sự thiếu đồng bộ giữa router - tools - validation, và phụ thuộc cứng vào Streamlit / Groq API.

---

## 2. BẢNG TỔNG HỢP VẤN ĐỀ VÀ MỨC ĐỘ NGHIÊM TRỌNG

| STT | Vấn đề | Mức độ | File liên quan | Đánh giá & Hướng xử lý |
|---|---|---|---|---|
| 1 | **Xung đột phiên bản PyTorch / Torchvision** | 🔴 Nghiêm trọng (Blocker) | Môi trường Python / `requirements.txt` | `torch==2.6.0+cu124` xung đột với `torchvision==0.20.1` gây lỗi C++ operator missing, làm crash toàn bộ `transformers` và `sentence-transformers`. Đã gỡ bỏ package thừa không dùng. |
| 2 | **Router LangGraph cô lập nhánh Reminder & Email** | 🔴 Nghiêm trọng | `src/agent/graph.py`, `src/agent/nodes.py` | Router mới chỉ có `DOMAIN_DATA` và `GENERAL_LLM`. Các node reminder/email bị cô lập hoàn toàn thành dead nodes. Cần cấu trúc lại router 3 nhánh: `DOMAIN_DATA`, `GENERAL_LLM`, `TOOL_ACTION`. |
| 3 | **Xung đột logic giữa Answer Generation & Validation** | 🔴 Nghiêm trọng | `src/agent/nodes.py`, `src/prompts/validation_prompt.py` | `answer_node` cấm đưa thêm thông tin ngoài chủ đề hỏi, trong khi `validation_prompt` lại ép buộc phải có đủ mã môn, tín chỉ, CLO, mục tiêu... gây ra vòng lặp retry vô ích chạm trần `MAX_RETRIES`. |
| 4 | **Đoạn mã copy-paste lỗi ở cuối `email_sender.py`** | 🔴 Nghiêm trọng | `src/tools/email_sender.py` (L36-L40) | Đoạn code thừa `def send(self, ...): # ... phần còn lại giữ nguyên` nằm ngoài class gây lỗi ghi đè hàm module. Cần dọn dẹp và xử lý đúng method bên trong class. |
| 5 | **Phụ thuộc cứng vào Groq & Hardcoded Placeholder `#`** | 🔴 Nghiêm trọng | `src/config/groq_gateway.py`, `src/tools/response_tool.py` | `GROQ_KEYS = ["#"]`, không hỗ trợ provider chuẩn OpenAI-compatible, rải rác import `langchain_groq`. Cần chuyển đổi thành LLM Gateway thống nhất qua `.env`. |
| 6 | **Hardcoded đường dẫn tuyệt đối máy khác** | 🟠 Trung bình | `src/cache/semantic_cache.py`, `src/memory/vector_memory.py` | Chứa đường dẫn cứng `D:/Agent_AI_Levelup/Agent_AI_Levelup/...`. Cần chuyển toàn bộ sang đường dẫn tương đối động qua `pathlib.Path`. |
| 7 | **Streamlit UI gắn chặt với logic và trùng lặp Scheduler** | 🟠 Trung bình | `app.py`, `src/agent/nodes.py` | Streamlit rerun liên tục tạo nguy cơ spawn nhiều thread scheduler; nút xóa cache không xóa cache thật; không đáp ứng tiêu chuẩn kiến trúc mới (FastAPI + HTML/JS). Cần loại bỏ Streamlit và migrate toàn bộ logic sang FastAPI. |
| 8 | **Đường dẫn tương đối không an toàn trong Memory** | 🟠 Trung bình | `src/memory/student_memory.py`, `src/memory/chat_memory.py` | Dùng `"src/memory/student_profile.json"` phụ thuộc vào CWD khi chạy lệnh. Cần chuẩn hóa thư mục `runtime/` hoặc resolved path và đưa vào `.gitignore`. |
| 9 | **Lỗi cú pháp trong `requirements.txt` & Thiếu `.gitignore`** | 🟠 Trung bình | `requirements.txt`, root repo | `requirements.txt` chứa lệnh shell `pip install ...`. Repo thiếu `.gitignore` khiến hơn 30 file `__pycache__` và file binary `chroma.sqlite3` bị commit. |
| 10 | **Code mồ côi (Dead Code / Unused Files)** | 🟡 Nhẹ | `src/tools/search_tool.py`, `src/tools/response_tool.py`, `src/prompts/planner_prompt.py`, `src/ingestion/ingest_pipeline.py` | Imports sai, collections cũ (`course_db` thay vì `course_detail`), không được gọi trong luồng chính. Cần loại bỏ hoặc refactor đồng bộ. |
| 11 | **Lỗi UnicodeEncodeError trên console Windows (charmap)** | 🟡 Nhẹ | Toàn bộ codebase (lệnh `print`) | In emoji ra terminal Windows cp1252 gây văng lỗi. Cần thay thế toàn bộ lệnh `print()` tùy tiện bằng Python `logging` chuẩn UTF-8. |

---

## 3. PHÂN LOẠI COMPONENT: GIỮ LẠI / REFACTOR / LOẠI BỎ

### 3.1. Giữ lại (Preserve & Re-use)
* **Docx Loader & Parser**: `src/ingestion/loaders.py` (đọc file `.docx` bảng biểu và văn bản).
* **Chunking logic chuyên biệt**: `src/ingestion/chunkers.py` (bóc tách đề cương theo mục La Mã I-IX, tuần học, CLO, phương pháp đánh giá A1-A3).
* **Metadata Builder**: `src/ingestion/metadata_builder.py` (trích xuất mã môn, đợt đào tạo, giảng viên).
* **Dữ liệu gốc**: Thư mục `data_raw/` (`course_detail`, `curriculum`, `regulation`).
* **Vector Store Core**: ChromaDB persistent client và cấu hình chỉ mục HNSW cosine.

### 3.2. Cần Refactor mạnh mẽ (Refactor & Upgrade)
* **Configuration & Secrets**: Tạo `src/config/settings.py` đọc `.env` an toàn (không commit key), tạo `.env.example`.
* **LLM Gateway**: Tạo `src/llm/client.py` hỗ trợ bất kỳ LLM Provider nào (OpenAI-compatible hoặc Groq) qua `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`.
* **Query Analyzer & Follow-up Resolver**: Nâng cấp từ việc chỉ rewrite đơn giản sang trích xuất cấu trúc (`domain`, `course_code`, `targets`).
* **Hybrid Retrieval & Reranker**: Thống nhất `src/rag/hybrid_retriever.py` với cấu hình tập trung (`RETRIEVAL_CANDIDATES`, `RERANK_TOP_K`, `CONTEXT_TOP_K`), kết hợp lọc metadata khi đã nhận diện được mã học phần.
* **LangGraph Agent Workflow**: Cấu trúc lại `src/agent/graph.py` và `src/agent/nodes.py` thành 3 nhánh rõ ràng: `DOMAIN_DATA`, `GENERAL_LLM`, `TOOL_ACTION`.
* **Context Builder & Source Attribution**: Trả lời kèm trích dẫn nguồn chuẩn xác từ metadata (`source_file`, `section`, `chunk_id`).
* **Scheduler & Tools**: Quản lý vòng đời APScheduler qua FastAPI lifespan (chỉ start 1 lần); EmailSender có chế độ fallback an toàn khi `EMAIL_ENABLED=false`.
* **Ingestion CLI**: Chuẩn hóa `src/ingestion/ingest_pipeline.py` hỗ trợ chế độ rebuild / incremental và in báo cáo rõ ràng.

### 3.3. Loại bỏ (Remove / Deprecate)
* **Streamlit**: Xóa bỏ `app.py` và phụ thuộc Streamlit khỏi runtime production.
* **Dead tools & prompts**: Xóa `src/tools/search_tool.py`, `src/tools/response_tool.py`, `src/prompts/planner_prompt.py`.
* **Hardcoded Groq gateway**: Thay thế hoàn toàn `src/config/groq_gateway.py`.
* **Tracking binary/cache trong Git**: Dọn dẹp tracking các file `.pyc`, `.sqlite3`, `.bin` qua `.gitignore`.

---

## 4. KẾ HOẠCH HÀNH ĐỘNG (ACTION PLAN)

1. **Phase 2**: Thiết lập `.gitignore`, `.env.example`, sửa `requirements.txt`, xây dựng `src/config/settings.py` và `src/llm/client.py`.
2. **Phase 3**: Hoàn thiện `src/ingestion/ingest_pipeline.py`, đảm bảo tạo ra vector store và BM25 index đồng nhất.
3. **Phase 4**: Xây dựng `src/rag/query_analyzer.py` và nâng cấp `src/rag/hybrid_retriever.py`.
4. **Phase 5**: Hoàn thiện `src/rag/reranker.py` và `src/rag/context_builder.py`.
5. **Phase 6**: Cấu trúc lại State và Graph LangGraph (3 nhánh router sạch, không node chết).
6. **Phase 7**: Chuẩn hóa sinh câu trả lời có nguồn dẫn (grounded citation) và cơ chế validation không vô tận.
7. **Phase 8**: Chuẩn hóa Memory, Cache, Tool email an toàn và Scheduler theo lifespan.
8. **Phase 9**: Xây dựng FastAPI backend (`src/api/main.py`, `src/api/routes.py`, `src/api/schemas.py`).
9. **Phase 10**: Xây dựng frontend HTML/CSS/Vanilla JS trong thư mục `frontend/`.
10. **Phase 11**: Viết test suite (`tests/unit/`, `tests/integration/`) chạy offline hoàn toàn.
11. **Phase 12**: Xây dựng benchmark và script `eval/run.py`.
12. **Phase 13**: Tạo GitHub Actions workflow `.github/workflows/ci.yml`.
13. **Phase 14**: Viết script `src/healthcheck.py`, hoàn thiện `docs/ARCHITECTURE.md`, `docs/COMPLETION_REPORT.md` và `README.md`.
