# AI Academic Advisor (Agentic RAG)
### Trợ lý Cố vấn Học tập Thông minh - Khoa Công nghệ Thông tin, Trường Đại học Đại Nam

[![CI Pipeline](https://github.com/kavsir/RAG-and-Agent/actions/workflows/ci.yml/badge.svg)](https://github.com/kavsir/RAG-and-Agent/actions)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Agentic%20Workflow-orange.svg)](https://langchain-ai.github.io/langgraph/)
[![Quality Verdict](https://img.shields.io/badge/Quality%20Verdict-LEVEL__4__ACCEPTED-brightgreen.svg)]()
[![Performance Verdict](https://img.shields.io/badge/Performance-ACCEPTABLE-blue.svg)]()

Hệ thống hỗ trợ sinh viên Khoa Công nghệ Thông tin tra cứu chương trình đào tạo, đề cương chi tiết học phần, quy chế học vụ và đặt lịch nhắc nhở học tập với cơ chế **Agentic RAG** chống ảo giác (Anti-Hallucination) và trích dẫn minh bạch nguồn tài liệu.

> **Trạng thái Nghiệm thu Cuối cùng (Final Acceptance Verdict)**: `LEVEL_4_ACCEPTED_WITH_MINOR_LIMITATIONS`  
> **Trạng thái Hiệu năng (Performance Verdict)**: `PERFORMANCE_ACCEPTABLE`  
> **Cam kết thiết kế**: Chạy trực tiếp trên Python Virtual Environment cục bộ.  
> **KHÔNG Docker**, **KHÔNG Kubernetes**, **KHÔNG Streamlit**, **KHÔNG Node.js/npm**.

---

## 1. Công nghệ & Kiến trúc (Tech Stack)

- **Backend**: FastAPI, Pydantic v2, Uvicorn, APScheduler.
- **Frontend**: Giao diện Chat & Evaluation Dashboard thuần Vanilla HTML5 / CSS3 / JavaScript / SVG (phục vụ trực tiếp qua FastAPI static mount, **100% không phụ thuộc CDN ngoài**).
- **Orchestration**: LangGraph (StateGraph với vòng lặp kiểm định factuality guardrail an toàn và hỗ trợ hội thoại nhiều lượt).
- **Retrieval & Rerank**:
  - **Dense Retrieval**: Embedding `BAAI/bge-m3` qua ChromaDB (3 collections: `course_detail`, `curriculum`, `regulation`).
  - **Sparse Retrieval**: BM25 Okapi indexes song song.
  - **Hybrid Fusion**: Reciprocal Rank Fusion (RRF, $k=60$).
  - **Reranker**: Cross-Encoder `cross-encoder/ms-marco-MiniLM-L-6-v2` (tùy chọn bật/tắt an toàn).
- **LLM Gateway**: Chuẩn `openai_compatible` hỗ trợ DeepSeek, OpenAI, Groq, vLLM hoặc Mock Handler.
- **Cache**: Structured Exact Query Cache lưu trữ đầy đủ payload (`answer`, `category`, `sources`, `tool_intent`).

---

## 2. Yêu cầu Hệ thống (Prerequisites)

- **Hệ điều hành**: Windows, macOS, hoặc Linux
- **Python**: Phiên bản 3.11 hoặc 3.12 (khuyến nghị 3.11 hoặc 3.12)
- **Git**: Đã cài đặt trên máy
- **RAM**: Tối thiểu 4GB (Khuyến nghị 6GB – 8GB, hệ thống chạy ổn định chỉ tiêu thụ ~167 MB RSS)

---

## 3. Hướng dẫn Cài đặt & Khởi chạy Nhanh (Quickstart)

### Bước 1: Clone Repository
```bash
git clone https://github.com/kavsir/RAG-and-Agent.git
cd RAG-and-Agent
```

### Bước 2: Tạo và Kích hoạt Môi trường Ảo (Virtual Environment)
- **Trên Windows (PowerShell)**:
  ```powershell
  python -m venv venv
  .\venv\Scripts\Activate.ps1
  ```
- **Trên Linux / macOS**:
  ```bash
  python3 -m venv venv
  source venv/bin/activate
  ```

### Bước 3: Cài đặt Thư viện Phụ thuộc
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Bước 4: Thiết lập File Cấu hình `.env`
Sao chép file mẫu `.env.example` thành `.env`:
```bash
# Trên Windows PowerShell:
Copy-Item .env.example .env

# Trên Linux / macOS:
cp .env.example .env
```
Mở file `.env` và cấu hình nhà cung cấp LLM mong muốn (ví dụ DeepSeek hoặc OpenAI):
```env
LLM_PROVIDER=openai_compatible
LLM_API_KEY=your_actual_api_key_here
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-pro
```
*(Nếu chưa cấu hình API Key, hệ thống vẫn vượt qua toàn bộ unit tests và benchmark đánh giá nhờ cơ chế Mock LLM offline tích hợp sẵn).*

### Bước 5: Nạp Dữ liệu Học vụ vào Cơ sở Dữ liệu Vector (ChromaDB)
```bash
python -m src.ingestion.ingest_pipeline --rebuild
```
Lệnh này sẽ nạp và bóc tách các tài liệu học vụ từ `data_raw/`, sinh vector chunks và xây dựng các chỉ mục BM25.

### Bước 6: Kiểm tra Tình trạng Hệ thống (Health Check)
```bash
python -m src.healthcheck
```
Kết quả mong đợi: `>>> SYSTEM STATUS: HEALTHY & READY TO SERVE <<<`

### Bước 7: Khởi chạy Ứng dụng Web & Dashboard
```bash
uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --reload
```
- 💬 **Giao diện Chat Cố vấn Học tập**: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- 📊 **Evaluation & Benchmark Dashboard**: [http://127.0.0.1:8000/evaluation/](http://127.0.0.1:8000/evaluation/)

---

## 4. Kết quả Nghiệm thu & Đo lường Hiệu năng (Benchmark & Evaluation)

### 4.1. Bộ Kiểm thử Đối kháng Toàn diện Benchmark V2
Thực thi trên **62 test cases độc lập** từ dữ liệu học vụ thực tế:
```bash
$env:PYTHONPATH="."
$env:ENABLE_RERANKER="false"
python -m eval.run_v2
```

| Chỉ số Chất lượng (Quality Gate) | Kết quả Thực tế | Ngưỡng Yêu cầu | Trạng thái | Ghi chú |
| :--- | :---: | :---: | :---: | :--- |
| **Router Accuracy** | **95.16%** (59/62) | $\ge 90\%$ | ✅ **PASS** | Nhận diện chính xác ý định học vụ, công cụ và từ chối |
| **Source Recall@1 (Top-1)** | **90.70%** (39/43) | $\ge 70\%$ | ✅ **PASS** | 90.7% câu hỏi học vụ có tài liệu đích ở ngay Rank 1 |
| **Source Recall@3 (Top-3)** | **97.67%** (42/43) | $\ge 80\%$ | ✅ **PASS** | Tài liệu chuẩn tập trung cao trong top đầu |
| **Source Recall@5 (Top-5)** | **100.00%** (43/43) | $\ge 85\%$ | ✅ **PASS** | 100% tài liệu đúng được đưa vào ngữ cảnh |
| **Recall@20 (Coverage)** | **100.00%** (43/43) | $\ge 95\%$ | ✅ **PASS** | Độ phủ ứng viên tuyệt đối (không coi là accuracy) |
| **Mean Reciprocal Rank (MRR)** | **0.9399** | $\ge 0.75$ | ✅ **PASS** | Thứ hạng bình quân tiệm cận hoàn hảo 1.0 |
| **Abstention Accuracy** | **100.00%** (7/7) | $\ge 90\%$ | ✅ **PASS** | 100% thực thể lạ bị từ chối an toàn, `sources = []` |
| **Wrong-Premise Resistance** | **100.00%** (5/5) | $\ge 90\%$ | ✅ **PASS** | Phản bác hoàn toàn các câu hỏi bẫy, đính chính đúng fact |
| **Domain Source Presence** | **100.00%** (23/23) | $\ge 95\%$ | ✅ **PASS** | 100% câu trả lời học vụ có trích dẫn nguồn chuẩn |
| **Critical Hallucinations** | **0** | $== 0$ | ✅ **PASS** | Tuyệt đối không bịa đặt nguồn hoặc đồng ý giả định sai |
| **Follow-up Resolution Rate** | **71.43%** (5/7) | $\ge 85\%$ | ⚠️ **LIMITATION** | Hạn chế ở các lượt hỏi nối tiếp ngắn trích xuất chi tiết sâu |
| **Tỷ lệ Pass Runtime Tổng thể** | **87.10%** (54/62) | $\ge 85\%$ | ✅ **PASS** | **LEVEL_4_ACCEPTED_WITH_MINOR_LIMITATIONS** |

Chi tiết xem tại: [`docs/FINAL_ACCEPTANCE_REPORT.md`](docs/FINAL_ACCEPTANCE_REPORT.md).

---

### 4.2. Hồ sơ Đo lường Hiệu năng Thực tế (Performance & Runtime Profiling)
Đo lường trên phần cứng thực tế (CPU AMD Ryzen 5 5600H, RAM 5.86 GB, Windows 10):
```bash
python -m eval.performance.run_performance
```

| Workload | Samples | Mean (ms) | P50 (ms) | P95 (ms) | Đánh giá |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Cold Start (Server Ready)** | 1 | **27,536.0** | 27,536.0 | 27,536.0 | 🟡 ACCEPTABLE |
| **Cold Start (First Request)** | 1 | **32,798.7** | 32,798.7 | 32,798.7 | 🟡 ACCEPTABLE |
| **DOMAIN Cache Miss (E2E)** | 8 | **12,188.7** | **10,062.4** | 34,736.5 | 🟡 ACCEPTABLE |
| **GENERAL Cache Miss (E2E)** | 5 | **14,222.1** | **14,605.4** | 18,938.0 | 🟡 ACCEPTABLE |
| **DOMAIN Cache Hit** | 10 | **142.0** | **114.9** | 373.7 | 🟢 EXCELLENT |
| **GENERAL Cache Hit** | 10 | **23.9** | **21.3** | 35.3 | 🟢 EXCELLENT |
| **Safe Abstention** | 5 | **194.3** | **191.7** | 220.2 | 🟢 EXCELLENT |

- **Local Pipeline Time (CPU)**: **~81.67 ms** (Query Analyzer: 0.27ms, Dense Search: 75.8ms, BM25: 0.94ms, Context Builder: 0.61ms).
- **RAM Footprint**: Peak RSS đạt **430.11 MB** khi tải BGE-M3; ổn định ở **167.21 MB** sau Garbage Collection.
- **Memory Leak**: **NONE** (*No memory leak detected during this benchmark run*).
- **Primary Bottleneck**: Các lượt gọi Cloud LLM API từ xa (DeepSeek) chiếm **> 99.3%** tổng latency do thực hiện cơ chế xác thực kép (Answer Generation + Factuality Guardrail).

Chi tiết xem tại: [`docs/PERFORMANCE_REPORT.md`](docs/PERFORMANCE_REPORT.md).

---

### 4.3. Bảng Điều khiển Nghiệm thu Trực quan (Evaluation Dashboard)
Truy cập tại: **`http://127.0.0.1:8000/evaluation/`**

Các phân hệ chính:
1. **Overview & Cards**: Trực quan hóa 8 chỉ số Acceptance Gates kèm Status Badge chính thức.
2. **Question Groups View**: Bảng đánh giá 9 nhóm câu hỏi (DIRECT_DOMAIN, PARAPHRASE, NO_CODE, TYPO_NOISY, WRONG_PREMISE, UNKNOWN_ENTITY, GENERAL_LLM, TOOL_ACTION, MULTI_TURN), sắp xếp yếu nhất lên đầu; nhấp hàng để lọc Cases.
3. **Failure Root Cause Analysis**: Phân rã nguyên nhân lỗi deterministic (Router, Answer Extraction, Entity Resolution, Answer Grounding, Tool Routing).
4. **Retrieval Distribution**: Biểu đồ phân bố thứ hạng nguồn đúng (Rank 1, 2, 3, 4-5, >5).
5. **Performance & Memory Profiling**: Bảng đo độ trễ các workloads, microbenchmarks CPU, và timeline RAM qua 4 giai đoạn.
6. **Case Explorer**: Bộ lọc đa tiêu chí (Status, Group, Root Cause), tìm kiếm theo từ khóa/mã môn, bảng trượt xem chi tiết từng query, expected facts, actual answer và citations mà không lộ chain-of-thought bí mật.
7. **History & Trend**: Lưu trữ snapshot phục vụ so sánh xu hướng qua các lần kiểm định.

---

### 4.4. Kiểm thử Tự động (Automated Testing)
```bash
# Chạy toàn bộ Unit & Dashboard API tests
pytest tests/unit/ -v

# Kiểm tra quy chuẩn mã nguồn (Linting)
ruff check src/ tests/ eval/
```
*(38/38 unit tests pass 100%, ruff 0 lỗi).*

---

## 5. Cấu trúc Thư mục Dự án

```
RAG-and-Agent/
├── .github/
│   ├── workflows/ci.yml       # Workflow CI tự động trên GitHub Actions
│   └── copilot-instructions.md# Hướng dẫn quy chuẩn cho trợ lý AI
├── data_raw/                  # Tài liệu học vụ gốc (.docx)
│   ├── course_detail/         # Đề cương chi tiết học phần
│   ├── curriculum/            # Chương trình đào tạo CNTT K19
│   └── regulation/            # Quy chế đào tạo và tốt nghiệp
├── docs/                      # Tài liệu kỹ thuật chính thức
│   ├── ARCHITECTURE.md        # Bản vẽ và đặc tả kiến trúc chi tiết
│   ├── FINAL_ACCEPTANCE_REPORT.md # Báo cáo nghiệm thu đối kháng Benchmark V2
│   ├── PERFORMANCE_REPORT.md  # Báo cáo đo lường hiệu năng & profiling runtime
│   ├── PROJECT_AUDIT.md       # Báo cáo kiểm định hiện trạng ban đầu
│   ├── REALITY_CHECK.md       # Báo cáo đối soát thực tế độc lập
│   └── BLOCKER_FIX_REPORT.md  # Báo cáo khắc phục các blocker kỹ thuật
├── eval/                      # Bộ benchmark và đánh giá chất lượng
│   ├── questions_v2.json      # 62 câu hỏi đối kháng Benchmark V2
│   ├── run_v2.py              # Runner nghiệm thu đối kháng Benchmark V2
│   ├── benchmark_v2_results.json # Kết quả nghiệm thu chi tiết JSON
│   ├── performance/           # Module đo lường hiệu năng thực tế
│   │   └── run_performance.py # Runner profiling CPU, Memory, Latency
│   └── results/               # Kết quả benchmark và lịch sử
│       ├── performance_latest.json
│       ├── performance_cases.csv
│       └── history/           # Snapshot các đợt kiểm định
├── frontend/                  # Giao diện Web (Vanilla HTML/CSS/JS)
│   ├── css/style.css          # Giao diện Chatbot
│   ├── js/app.js              # Logic client Chatbot
│   ├── index.html             # Trang chủ Chatbot
│   └── evaluation/            # Evaluation Dashboard
│       ├── index.html         # Giao diện Dashboard
│       ├── dashboard.css      # CSS Dashboard (Zero CDN dependency)
│       └── dashboard.js       # Logic Dashboard & SVG Charts
├── src/                       # Mã nguồn cốt lõi
│   ├── agent/                 # Đồ thị LangGraph (Nodes, State, Graph)
│   ├── api/                   # REST API Backend (FastAPI, Routers, Schemas)
│   │   ├── evaluation_router.py # Endpoints phục vụ Evaluation Dashboard
│   │   ├── evaluation_service.py# Logic tổng hợp metrics & root causes
│   │   ├── routes.py          # Endpoints Chat & Health
│   │   └── main.py            # Entrypoint ứng dụng FastAPI
│   ├── cache/                 # Bộ đệm Structured Exact Cache
│   ├── config/                # Quản lý cấu hình Settings tập trung
│   ├── ingestion/             # Loaders, Chunkers, Vector Store, BM25 Index
│   ├── llm/                   # Provider-Neutral LLM Client Gateway
│   ├── memory/                # Three-tier Memory (Profile, Chat, Vector)
│   ├── prompts/               # System Prompts (Routing, Answer, Validation)
│   ├── rag/                   # Query Analyzer, Hybrid Retriever, Context Builder
│   ├── scheduler/             # APScheduler nhắc nhở học tập
│   ├── tools/                 # Tool actions (EmailSender)
│   └── healthcheck.py         # Script kiểm tra sức khỏe hệ thống CLI
├── tests/                     # Toàn bộ bài test tự động (Unit & Integration)
│   ├── unit/                  # 38 Unit tests bao phủ toàn bộ phân hệ
│   │   └── test_evaluation_api.py # Test endpoints Evaluation Dashboard
│   └── integration/           # Integration tests
├── .env.example               # File mẫu cấu hình biến môi trường
├── .gitignore                 # Cấu hình bỏ qua tệp nhị phân và dữ liệu runtime
├── pyproject.toml             # Cấu hình pytest và ruff
└── requirements.txt           # Danh mục thư viện Python
```

---

## 6. Bản quyền & Thông tin Phát triển

Phát triển phục vụ sinh viên Khoa Công nghệ Thông tin, Trường Đại học Đại Nam.  
Bản quyền © 2026. Mọi quyền được bảo lưu.
