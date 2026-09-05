# AI Academic Advisor (Agentic RAG)
### Trợ lý Cố vấn Học tập Thông minh - Khoa Công nghệ Thông tin, Trường Đại học Đại Nam

[![CI Pipeline](https://github.com/kavsir/RAG-and-Agent/actions/workflows/ci.yml/badge.svg)](https://github.com/kavsir/RAG-and-Agent/actions)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Agentic%20Workflow-orange.svg)](https://langchain-ai.github.io/langgraph/)
[![Status](https://img.shields.io/badge/Status-READY__FOR__FINAL__ACCEPTANCE-blue.svg)]()

Hệ thống hỗ trợ sinh viên Khoa Công nghệ Thông tin tra cứu chương trình đào tạo, đề cương chi tiết học phần, quy chế học vụ và đặt lịch nhắc nhở học tập với cơ chế **Agentic RAG** chống ảo giác (Anti-Hallucination) và trích dẫn minh bạch nguồn tài liệu.

> **Trạng thái hiện tại**: `READY_FOR_FINAL_ACCEPTANCE`  
> **Cam kết thiết kế**: Chạy trực tiếp trên Python Virtual Environment cục bộ.  
> **KHÔNG Docker**, **KHÔNG Kubernetes**, **KHÔNG Streamlit**, **KHÔNG Node.js/npm**.

---

## 1. Công nghệ & Kiến trúc (Tech Stack)

- **Backend**: FastAPI, Pydantic v2, Uvicorn, APScheduler.
- **Frontend**: Giao diện Vanilla HTML5 / CSS3 / JavaScript (phục vụ trực tiếp qua FastAPI static mount).
- **Orchestration**: LangGraph (StateGraph với vòng lặp kiểm định an toàn và hỗ trợ hội thoại nhiều lượt).
- **Retrieval & Rerank**:
  - **Dense Retrieval**: Embedding `BAAI/bge-m3` qua ChromaDB (3 collections: `course_detail`, `curriculum`, `regulation`).
  - **Sparse Retrieval**: BM25 Okapi indexes song song.
  - **Hybrid Fusion**: Reciprocal Rank Fusion (RRF, $k=60$).
  - **Reranker**: Cross-Encoder `cross-encoder/ms-marco-MiniLM-L-6-v2` (tùy chọn bật/tắt an toàn).
- **LLM Gateway**: Chuẩn `openai_compatible` hỗ trợ OpenAI, DeepSeek, Groq, vLLM hoặc Mock Handler.
- **Cache**: Exact Query Cache lưu trữ payload có cấu trúc (`answer`, `category`, `sources`, `tool_intent`).

---

## 2. Yêu cầu Hệ thống (Prerequisites)

- **Hệ điều hành**: Windows, macOS, hoặc Linux
- **Python**: Phiên bản 3.11 hoặc 3.12 (khuyến nghị 3.11 hoặc 3.12)
- **Git**: Đã cài đặt trên máy

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
*(Nếu chưa cấu hình API Key, hệ thống vẫn vượt qua toàn bộ 39 bài test tự động và benchmark đánh giá nhờ cơ chế Mock LLM offline tích hợp sẵn).*

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

### Bước 7: Khởi chạy Ứng dụng Web
```bash
uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --reload
```
Mở trình duyệt web và truy cập:
👉 **[http://127.0.0.1:8000](http://127.0.0.1:8000)**

---

## 4. Kiểm thử Tự động & Đánh giá Chất lượng

### Chạy Toàn bộ Bộ Test Tự động (Pytest)
```bash
pytest tests/ -v
```
*(39/39 bài kiểm thử unit & integration test bao phủ query analyzer, router, hybrid retriever, context builder, structured exact cache, scheduler lifecycle, safe abstention, fail-safe validation và API endpoints).*

### Chạy Bộ Benchmark Đánh giá (Evaluation Runner)
```bash
python -m eval.run --mock
```
Hoặc với live LLM (khi đã cấu hình `.env`):
```bash
python -m eval.run
```
Ý nghĩa các chỉ số đo lường:
- **Router Accuracy**: Tỷ lệ phân loại chính xác ý định (DOMAIN_DATA, GENERAL_LLM, TOOL_ACTION, ABSTENTION).
- **Source Recall@20**: Tỷ lệ tài liệu nguồn có mặt trong danh sách top-20 ứng viên truy xuất.
- **Context Source Presence Rate**: Tỷ lệ tài liệu nguồn có mặt trong 6 chunks context được đưa vào prompt.
- **Keyword Recall**: Tỷ lệ từ khóa nghiệp vụ quan trọng xuất hiện trong câu trả lời.
- **Abstention Accuracy**: Tỷ lệ từ chối trả lời chuẩn mực khi thực thể lạ hoặc không có dữ liệu đối sánh.

### Phân tích Mã nguồn Tĩnh (Linting)
```bash
ruff check src/ tests/ eval/
```

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
│   ├── PROJECT_AUDIT.md       # Báo cáo kiểm định hiện trạng ban đầu
│   ├── REALITY_CHECK.md       # Báo cáo đối soát thực tế độc lập
│   ├── BLOCKER_FIX_REPORT.md  # Báo cáo khắc phục các blocker kỹ thuật
│   └── archive/               # Tài liệu phiên bản cũ lưu trữ
├── eval/                      # Bộ benchmark và đánh giá chất lượng
│   ├── questions.json         # 30 câu hỏi benchmark chuẩn hóa
│   └── run.py                 # Runner đo lường các chỉ số RAG
├── frontend/                  # Giao diện Web (Vanilla HTML/CSS/JS)
│   ├── css/style.css          # Giao diện phong cách hiện đại
│   ├── js/app.js              # Logic client gọi API và xử lý tin nhắn
│   └── index.html             # Trang chủ ứng dụng
├── src/                       # Mã nguồn cốt lõi
│   ├── agent/                 # Đồ thị LangGraph (Nodes, State, Graph)
│   ├── api/                   # REST API Backend (FastAPI, Routers, Schemas)
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
├── .env.example               # File mẫu cấu hình biến môi trường
├── .gitignore                 # Cấu hình bỏ qua tệp nhị phân và dữ liệu runtime
├── pyproject.toml             # Cấu hình pytest và ruff
└── requirements.txt           # Danh mục thư viện Python
```

---

## 6. Bản quyền & Thông tin Phát triển

Phát triển phục vụ sinh viên Khoa Công nghệ Thông tin, Trường Đại học Đại Nam.  
Bản quyền © 2026. Mọi quyền được bảo lưu.
