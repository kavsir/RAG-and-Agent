# AI Academic Advisor (Agentic RAG)
### Trợ lý Cố vấn Học tập Thông minh — Khoa Công nghệ Thông tin, Trường Đại học Đại Nam

[![Python 3.11+](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Agentic%20Workflow-orange.svg)](https://langchain-ai.github.io/langgraph/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**AI Academic Advisor** là hệ thống trợ lý học vụ thông minh ứng dụng kiến trúc **Agentic RAG (Retrieval-Augmented Generation)**, được thiết kế chuyên biệt để đồng hành cùng sinh viên Khoa Công nghệ Thông tin, Trường Đại học Đại Nam. Hệ thống cung cấp câu trả lời chính xác, cập nhật từ kho tài liệu học vụ chính thức (đề cương chi tiết học phần, khung chương trình đào tạo, quy chế đào tạo tín chỉ), trích dẫn minh bạch nguồn tài liệu và hỗ trợ các công cụ học tập hữu ích.

---

## 🌟 Tính Năng Nổi Bật

- 🔍 **Tra Cứu Học Phần Toàn Diện**: Tra cứu nhanh thông tin số tín chỉ, giảng viên phụ trách, chuẩn đầu ra (CLO), kế hoạch giảng dạy theo tuần, hình thức đánh giá chuyên cần và thi kết thúc học phần theo mã môn (FIT4201, FIT4104...) hoặc tên môn học tự nhiên.
- 📚 **Cố Vấn Lộ Trình & Quy Chế Đào Tạo**: Hướng dẫn điều kiện học phần tiên quyết, lộ trình đào tạo theo từng học kỳ, điều kiện xét tốt nghiệp và xử lý học vụ theo đúng quy chế hiện hành của nhà trường.
- 🛡️ **Cơ Chế Chống Ảo Giác (Anti-Hallucination Guardrail)**: 
  - Quy trình kiểm định độc lập (Factuality Verification) đối chiếu câu trả lời với factsheet trước khi gửi đến người dùng.
  - Tự động từ chối an toàn (**Safe Abstention**) với 100% các thực thể lạ, mã môn học không tồn tại để tránh sai lệch thông tin.
  - Miễn nhiễm trước các câu hỏi bẫy (**Wrong-Premise Resistance**), chủ động đính chính các giả định sai.
- ⏰ **Trợ Lý Tiện Ích Học Tập (Agentic Tools)**: Tích hợp công cụ lên lịch nhắc nhở nộp bài tập lớn/ôn thi qua APScheduler và hỗ trợ soạn thảo email liên hệ thầy cô chuẩn văn phong học thuật.
- ⚡ **Phản Hồi Siêu Tốc & Tối Ưu Tài Nguyên**:
  - Tích hợp **Structured Exact Cache** phản hồi tức thì (20ms – 140ms) đối với các câu hỏi thường gặp mà vẫn bảo toàn đầy đủ danh sách trích dẫn nguồn.
  - Chuỗi xử lý RAG cục bộ (Local Pipeline) hoàn tất trong **< 85 ms**.
  - Mức chiếm dụng bộ nhớ RAM tiến trình chỉ khoảng **~167 MB**, hoạt động mượt mà ngay cả trên máy tính cá nhân cấu hình phổ thông.
- 📊 **Evaluation Dashboard Trực Quan**: Tích hợp sẵn bảng điều khiển đánh giá chất lượng mô hình, phân rã độ trễ, theo dõi bộ nhớ và khám phá chi tiết từng trường hợp kiểm định.

---

## 🏗️ Kiến Trúc Hệ Thống (Architecture)

Hệ thống hoạt động theo mô hình luồng tác tử nhiều tầng (Multi-tier Agentic Flow):

```
Người dùng ──► [FastAPI / Web Client]
                     │
                     ▼
          [Exact Query Cache] ──(Hit)──► Trả về kết quả tức thì (<150ms)
                     │ (Miss)
                     ▼
             [Query Analyzer] (Trích xuất thực thể: mã môn, target, ngữ cảnh)
                     │
                     ▼
             [Intent Router]
        ┌────────────┼────────────┐
        ▼            ▼            ▼
  [DOMAIN_DATA] [GENERAL_LLM] [TOOL_ACTION]
        │            │            │
        ▼            │            ▼
  [Hybrid Search]    │     [APScheduler / Email]
  Dense (BGE-M3)     │
  + BM25 + RRF       │
        │            │
        ▼            │
  [Context Builder]  │
        │            │
        ▼            ▼
  [Grounded Answer Generation]
        │
        ▼
  [Factuality Guardrail Validator] ──(Không đạt)──► Tự động sửa/từ chối an toàn
        │ (Đạt chuẩn)
        ▼
   Lưu Cache ──► Phản hồi người dùng kèm danh sách trích dẫn nguồn
```

---

## 🚀 Hướng Dẫn Cài Đặt & Sử Dụng (Quickstart)

### 1. Sao chép mã nguồn (Clone Repository)
```bash
git clone https://github.com/kavsir/RAG-and-Agent.git
cd RAG-and-Agent
```

### 2. Thiết lập Môi trường Ảo (Python Virtual Environment)
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

### 3. Cài đặt các thư viện phụ thuộc
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Cấu hình biến môi trường
Tạo file `.env` từ mẫu `.env.example`:
```bash
# Windows PowerShell
Copy-Item .env.example .env

# Linux / macOS
cp .env.example .env
```
Mở file `.env` và điền API Key của nhà cung cấp mô hình ngôn ngữ (hỗ trợ bất kỳ provider nào theo chuẩn OpenAI Compatible như DeepSeek, OpenAI, Groq, vLLM...):
```env
LLM_PROVIDER=openai_compatible
LLM_API_KEY=your_api_key_here
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-pro
```
*(Nếu chưa cấu hình API Key, toàn bộ test suite và chế độ mock vẫn hoạt động bình thường phục vụ mục đích kiểm thử offline).*

### 5. Nạp dữ liệu học vụ vào Cơ sở Dữ liệu Vector (ChromaDB)
```bash
python -m src.ingestion.ingest_pipeline --rebuild
```
Lệnh sẽ tự động nạp các tài liệu từ `data_raw/`, bóc tách cấu trúc, tính toán vector embeddings và khởi tạo chỉ mục BM25 Okapi.

### 6. Khởi chạy Ứng dụng
```bash
uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --reload
```

Sau khi khởi động thành công, mở trình duyệt:
- 💬 **Giao diện Trò chuyện Cố vấn Học tập**: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- 📊 **Bảng Điều khiển Đánh giá & Hiệu năng**: [http://127.0.0.1:8000/evaluation/](http://127.0.0.1:8000/evaluation/)
- 📖 **Tài liệu API Swagger**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## 📊 Đánh Giá Độ Tin Cậy & Hiệu Năng (Benchmarks)

Hệ thống đã trải qua quy trình kiểm thử đối kháng toàn diện (**Adversarial Benchmark V2**) gồm **62 trường hợp thực tế** và quy trình đo lường runtime profiling độc lập:

### 1. Độ Chính Xác & An Toàn Thông Tin (Quality Gates)

| Tiêu chí chất lượng | Kết quả thực tế | Ý nghĩa thực tiễn |
| :--- | :---: | :--- |
| **Độ chính xác Định tuyến (Router Accuracy)** | **95.16%** (59/62) | Phân loại đúng ý định học vụ, kiến thức chung và tác vụ công cụ |
| **Top-1 Source Accuracy (Recall@1)** | **90.70%** (39/43) | Tài liệu chuẩn xác xuất hiện ngay tại vị trí ưu tiên số 1 |
| **Độ phủ Ngữ cảnh (Recall@5)** | **100.00%** (43/43) | 100% tài liệu liên quan được đưa vào ngữ cảnh sinh câu trả lời |
| **Thứ hạng Nghịch đảo (MRR)** | **0.9399** | Độ tin cậy xếp hạng tài liệu tiệm cận mức tối đa 1.0 |
| **Từ chối An toàn (Abstention Accuracy)** | **100.00%** (7/7) | Tuyệt đối không bịa đặt thông tin cho các môn học không có thật |
| **Kháng Bẫy Dẫn dắt (Wrong-Premise)** | **100.00%** (5/5) | Phản bác và đính chính chính xác 100% câu hỏi chứa giả định sai |
| **Trích dẫn Nguồn Hợp lệ (Source Presence)** | **100.00%** (23/23) | Mọi câu trả lời học vụ đều hiển thị rõ tên tài liệu và vị trí mục |
| **Ảo giác Nghiêm trọng (Critical Hallucinations)** | **0 ca** | Không phát hiện ca bịa đặt tài liệu hay xuyên tạc thông tin học vụ |

📄 *Xem báo cáo phân tích chi tiết: [`docs/FINAL_ACCEPTANCE_REPORT.md`](docs/FINAL_ACCEPTANCE_REPORT.md).*

### 2. Hiệu Năng Vận Hành (Runtime Performance)

Đo lường trực tiếp trên máy tính phát triển (CPU AMD Ryzen 5 5600H, RAM 5.86 GB, Windows 10):

- **Phản hồi khi có Cache (Cache Hit)**: **~23.9 ms** (General) / **~142.0 ms** (Domain kèm đầy đủ trích dẫn).
- **Từ chối an toàn thực thể lạ**: **~194.3 ms** (Phát hiện và từ chối sớm, tiết kiệm 100% chi phí gọi LLM).
- **Thời gian xử lý Pipeline Cục bộ**: **~81.7 ms** (Query Analyzer: 0.27ms, Dense Search: 75.8ms, BM25: 0.94ms, Context Builder: 0.61ms).
- **Bộ nhớ Tiến trình (Process RSS)**: Đỉnh 430 MB khi nạp mô hình vector, duy trì ổn định ở mức **~167 MB** trong suốt quá trình phục vụ.
- **Rò rỉ Bộ nhớ (Memory Leak)**: **Không có** (*No memory leak detected*).

📄 *Xem báo cáo phân tích chi tiết: [`docs/PERFORMANCE_REPORT.md`](docs/PERFORMANCE_REPORT.md).*

---

## 🖥️ Bảng Điều Khiển Đánh Giá (Evaluation Dashboard)

Truy cập tại: **`http://127.0.0.1:8000/evaluation/`**

Dashboard được xây dựng hoàn toàn bằng công nghệ Web thuần (Vanilla HTML5/CSS3/JS, SVG native), **không cần kết nối Internet ra CDN bên ngoài**:

- 📈 **Overview & Cards**: Theo dõi trực quan 8 chỉ số nghiệm thu chất lượng theo thời gian thực.
- 🏷️ **Phân Tích Nhóm Câu Hỏi**: Đánh giá độ mạnh/yếu của từng nhóm truy vấn (Direct, Paraphrase, No-code, Typo, Wrong-premise, Unknown...). Nhấp chuột vào bất kỳ nhóm nào để lọc nhanh danh sách.
- 🎯 **Phân Tích Nguyên Nhân Lỗi (Root Cause)**: Phân loại lỗi tự động theo chứng cớ (Router Collision, Formatting, Entity Resolution) phục vụ việc cải tiến liên tục.
- 📊 **Phân Bố Thứ Hạng Tài Liệu**: Biểu đồ phân bổ Rank 1, Rank 2, Rank 3... trực quan hóa năng lực của bộ máy tìm kiếm kết hợp Hybrid RRF.
- 🔍 **Case Explorer Chi Tiết**: Cho phép tìm kiếm, lọc theo trạng thái PASS/FAIL, mở bảng xem chi tiết câu hỏi, expected facts, câu trả lời thực tế và tài liệu trích dẫn.

---

## 🧪 Kiểm Thử Tự Động (Automated Testing)

Hệ thống đi kèm bộ kiểm thử tự động toàn diện:

```bash
# 1. Chạy toàn bộ Unit Tests & Dashboard API Tests
pytest tests/unit/ -v

# 2. Kiểm tra chất lượng mã nguồn (Linting)
ruff check src/ tests/ eval/

# 3. Kiểm tra sức khỏe toàn hệ thống (Healthcheck)
python -m src.healthcheck
```

---

## 📁 Cấu Trúc Dự Án (Project Structure)

```
RAG-and-Agent/
├── data_raw/                  # Tài liệu học vụ gốc (.docx)
│   ├── course_detail/         # Đề cương chi tiết học phần
│   ├── curriculum/            # Chương trình đào tạo CNTT K19
│   └── regulation/            # Quy chế đào tạo và tốt nghiệp
├── docs/                      # Tài liệu kỹ thuật & Đúc kết kinh nghiệm
│   ├── ARCHITECTURE.md        # Thiết kế kiến trúc tổng thể
│   ├── FINAL_ACCEPTANCE_REPORT.md # Kinh nghiệm đánh giá đối kháng & Benchmark V2
│   ├── PERFORMANCE_REPORT.md  # Kinh nghiệm đo lường hiệu năng & tối ưu bottleneck
│   ├── ROUTER_V2_REPORT.md    # Kinh nghiệm tối ưu định tuyến ý định với chi phí 0 đồng
│   ├── SESSION_MEMORY_V2_REPORT.md # Kinh nghiệm xử lý hội thoại đa lượt & bộ nhớ phiên SQLite
│   └── PERSONAL_MEMORY_V1_REPORT.md # Kinh nghiệm thiết kế bộ nhớ cá nhân & phân giải thẩm quyền
├── eval/                      # Phân hệ đo lường & kiểm định
│   ├── questions_v2.json      # Bộ câu hỏi kiểm thử đối kháng
│   ├── run_v2.py              # Runner kiểm thử nghiệm thu V2
│   ├── performance/           # Runner đo lường hiệu năng & profiling
│   └── results/               # Kết quả benchmark và lịch sử snapshots
├── frontend/                  # Giao diện người dùng
│   ├── index.html             # Giao diện Chatbot học vụ
│   ├── css/ & js/             # Kiểu dáng và logic tương tác client
│   └── evaluation/            # Giao diện Evaluation Dashboard (HTML/CSS/JS/SVG)
├── src/                       # Mã nguồn ứng dụng
│   ├── agent/                 # Đồ thị trạng thái LangGraph & Factuality Guardrail
│   ├── api/                   # REST API Backend (FastAPI, Routers, Evaluation API)
│   ├── cache/                 # Bộ đệm Structured Exact Query Cache
│   ├── config/                # Cấu hình Settings và biến môi trường
│   ├── ingestion/             # Pipeline bóc tách tài liệu & nạp ChromaDB / BM25
│   ├── llm/                   # Cổng giao tiếp LLM chuẩn OpenAI-compatible
│   ├── memory/                # Hệ thống bộ nhớ 3 tầng (Profile, Session, Vector)
│   ├── rag/                   # Query Analyzer, Hybrid Retriever (Dense+BM25), Context Builder
│   └── scheduler/             # APScheduler phục vụ tác vụ nhắc nhở học tập
├── tests/                     # Bộ kiểm thử tự động (Unit & Integration tests)
├── .env.example               # Mẫu cấu hình môi trường
└── requirements.txt           # Danh mục thư viện phụ thuộc
```

---

## 📄 Bản Quyền & Giấy Phép (License)

Dự án được phát triển phục vụ sinh viên Khoa Công nghệ Thông tin, Trường Đại học Đại Nam.  
Mã nguồn được phân phối theo giấy phép [MIT License](LICENSE).
