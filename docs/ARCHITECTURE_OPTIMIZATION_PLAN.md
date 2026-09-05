# KẾ HOẠCH TỐI ƯU HÓA KIẾN TRÚC & PHÂN BỔ QUYẾT ĐỊNH
## (Architecture Review & Optimization Decision Framework)

**Dự án**: AI Academic Advisor / Agentic RAG — Đại học Đại Nam  
**Ngày thực hiện**: 06/09/2026  
**Trạng thái kiểm định**: **REVIEW ONLY — ĐÓNG BĂNG 100% PRODUCTION CODE**  

---

## 1. GHI NHẬN BASELINE ĐÓNG BĂNG (FROZEN BASELINE RECORD)

| Chỉ số / Thông số | Giá trị xác thực từ hệ thống |
| :--- | :--- |
| **Current Git HEAD** | `e4f5f6a94124c5db1ba3033090d25c773af1d3e9` |
| **Product Baseline Commit** | `4cf04cca394870b6c83e7cb54984b98bcffda846` (Điểm chốt code freeze ban đầu) |
| **Benchmark Suite Version** | `Benchmark V2 (Adversarial Acceptance Suite, 62 test cases)` |
| **Quality Acceptance Verdict** | **`LEVEL_4_ACCEPTED_WITH_MINOR_LIMITATIONS`** (Pass Rate: 87.10%, 0 Hallucinations) |
| **Performance Verdict** | **`PERFORMANCE_ACCEPTABLE`** (Local RAG: 81.67ms, RAM Steady: 167MB, No memory leak) |
| **Uncommitted Changes** | **NONE (Working tree completely clean)** |

> [!IMPORTANT]
> **Cam kết nguyên tắc**:
> - Tài liệu này là **đánh giá kiến trúc thuần túy (Architecture Review Only)**.
> - **KHÔNG sửa đổi mã nguồn sản xuất** (`src/rag/`, `src/agent/`, `src/llm/`, `src/memory/`, `src/tools/`, `src/scheduler/`).
> - **KHÔNG tối ưu số liệu** để làm đẹp benchmark.
> - **KHÔNG coi lỗi cấu trúc (Structural Defect) là bài toán tinh chỉnh tham số (Parameter Tuning)**.

---

## 2. MỤC TIÊU & HỆ QUY CHIẾU PHÂN LOẠI CAN THIỆP

Mọi đề xuất tối ưu hóa trong lộ trình phát triển tiếp theo bắt buộc phải được phân loại chính xác vào đúng 1 trong 6 chiều can thiệp kỹ thuật:

1. **`ARCHITECTURE`**: Tái cấu trúc luồng điều khiển, thêm tầng xử lý mới, thay đổi mô hình lưu trữ, tách rời trách nhiệm giữa các thành phần.
2. **`ALGORITHM_POLICY`**: Điều chỉnh quy tắc logic, thứ tự ưu tiên, regex patterns, chính sách điều hướng intent hoặc heuristic rules.
3. **`PARAMETER_CONFIG`**: Tinh chỉnh giá trị số lượng (Top-K, threshold, timeout, temperature, buffer size) trong cấu hình `settings.py`.
4. **`MODEL_CHOICE`**: Đổi mô hình AI nền tảng (LLM checkpoint, Embedding weights, Cross-Encoder weights).
5. **`EVALUATOR_ONLY`**: Điều chỉnh tiêu chuẩn bộ đo kiểm định (ví dụ: chấp nhận ký tự `&` tương đương `and`), tuyệt đối không làm thay đổi hành vi sản phẩm.
6. **`NO_CHANGE_NEEDED`**: Thành phần đã đạt trạng thái tối ưu, ổn định, không chạm vào.

---

## 3. KIỂM ĐỊNH HIỆN TRẠNG KIẾN TRÚC HỆ THỐNG (CURRENT VS PROPOSED)

### 3.1. Luồng Vận Hành Thực Tế Hiện Tại (Current Runtime Flow)

```
[Người dùng]
     │
     ▼
[POST /api/chat] (src/api/routes.py)
     │  - Tạo session_id/conv_id
     │  - Đọc lịch sử thô từ ChatMemory (toàn cục, bỏ qua session_id)
     │  - Đọc profile từ StudentMemory (file json đơn lẻ)
     ▼
[LangGraph Agent] (src/agent/graph.py)
     │
     ├──► [Node 1: Cache Node] (src/agent/nodes.py)
     │         ├── (Hit) ──► [Save Chat Node] ──► Trả về câu trả lời (<150ms)
     │         └── (Miss)
     │               │
     │               ▼
     ├──► [Node 2: Query Analysis Node]
     │         ├── Regex bóc tách mã môn (`[A-Z]{3,4}\d{4}`)
     │         ├── Regex bóc tách targets (quét mảng từ khóa tĩnh TARGET_KEYWORDS)
     │         └── Giải quyết đại từ hội thoại (chỉ kích hoạt nếu có 6 cụm từ cố định)
     │               │
     │               ▼
     ├──► [Node 3: Router Node]
     │         ├── 1. Quét tool substring tĩnh ("nhắc tôi", "soạn email")
     │         ├── 2. Quét domain (có mã môn HOẶC có target HOẶC có domain keyword)
     │         ├── 3. Quét general (10 từ khóa tĩnh: dijkstra, python, java...)
     │         └── 4. LLM Fallback (mặc định về DOMAIN_DATA)
     │               │
     │   ┌───────────┴───────────┐
     │   ▼                       ▼
     │ [Nhánh GENERAL]       [Nhánh TOOL_ACTION]
     │   │                       ├── Reminder (APScheduler)
     │   │                       └── Email (EmailSender)
     │   │                               │
     │   │                               ▼
     │   │                       [Save Chat Node]
     │   ▼                               │
     │ [General Answer Node] ────────────┘
     │   (LLM Direct)
     │
     ▼
[Nhánh DOMAIN_DATA (RAG)]
     │
     ├──► [Node 4: Retrieve Node]
     │         └── retrieve_candidates:
     │               ├── Dense Search (ChromaDB + BGE-M3 local embedding: ~75ms)
     │               └── BM25 Search (Chroma path pickle: ~0.9ms)
     │               └── RRF Fusion ($k=60$)
     │
     ├──► [Node 5: Rerank Node]
     │         └── Cross-Encoder (tắt trong baseline: ENABLE_RERANKER=false)
     │
     ├──► [Node 6: Context Node]
     │         └── build_context: Lọc trùng, tính target boost, giới hạn ký tự
     │
     ├──► [Node 7: Grounded Answer Node]
     │         └── invoke_llm: Gọi DeepSeek sinh câu trả lời (~3.4s)
     │
     ├──► [Node 8: Validation Node (Guardrail)]
     │         └── invoke_llm: Gọi DeepSeek kiểm định factuality (~8.7s)
     │               ├── Hợp lệ ──► [Save Chat Node]
     │               └── Không hợp lệ ──► Retry (tối đa 2 lần) hoặc Cưỡng chế ABSTAIN
     │
     ▼
[Node 9: Save Chat Node]
     ├── Ghi Exact Cache (nếu hợp lệ và không phải câu từ chối)
     └── Ghi vào MemoryManager:
           ├── chat_history.json (ghi đè append toàn cục)
           └── Chroma user_memory (ghi embedding nhưng không bao giờ đọc)
```

---

## 4. PHÂN TÍCH CHI TIẾT BỘ ĐỊNH TUYẾN (ROUTER ARCHITECTURE REVIEW)

Trong Benchmark V2, có 5 ca thất bại trực tiếp liên quan đến định tuyến:
- `v2-gen-02` (QuickSort &rarr; DOMAIN_DATA)
- `v2-gen-03` (TCP vs UDP &rarr; DOMAIN_DATA)
- `v2-gen-05` (Cloud computing &rarr; DOMAIN_DATA)
- `v2-tool-04` ("Soạn giúp tôi email..." &rarr; DOMAIN_DATA)

### Bản chất Nguyên nhân Gốc rễ:
1. **Ô nhiễm mục tiêu (Target Contamination)**: Từ `"điểm"` nằm trong `TARGET_KEYWORDS["assessment"]` của `query_analyzer.py`. Khi câu hỏi có cụm từ *"Điểm khác biệt..."*, nó bị gán `targets = ["assessment"]`, khiến `has_domain_target = True` và bị ép sang `DOMAIN_DATA` trước khi đến bộ lọc General.
2. **Lỗi thứ tự & Danh sách từ khóa tĩnh hạn hẹp (Ordering & Coverage Flaw)**: Kiểm tra Domain đứng trước General; danh sách `general_keywords` chỉ có 10 từ nên các giải thuật kinh điển như QuickSort bị đẩy vào fallback LLM.
3. **So khớp chuỗi con cứng nhắc (Rigid Substring Matching)**: `"soạn email"` trượt câu `"Soạn giúp tôi email..."` do có từ chen giữa.

### Đề xuất Kiến trúc Router Phân Tầng (Layered Router Architecture):
*Chi tiết tại: [`docs/adr/ADR-001-routing-architecture.md`](adr/ADR-001-routing-architecture.md)*

- **Layer 0 (Tool Proximity Intent)**: Dùng regex khoảng cách từ `ACTION` + `OBJECT` trong bán kính 25 ký tự.
- **Layer 1 (Strong Domain Evidence)**: Nhận diện mã môn (`[A-Z]{3,4}\d{4}`) hoặc thực thể học vụ chính danh của Đại Nam.
- **Layer 2 (Strong General Concept)**: Nhận diện mẫu câu hỏi nguyên lý, thuật toán, so sánh công nghệ chung không chứa mã môn.
- **Layer 3 (Target-Entity Co-occurrence)**: Loại trừ các từ khóa giao thoa (ví dụ: `"điểm"` chỉ tính là học vụ khi đi kèm mã môn hoặc từ khóa đánh giá học phần; loại bỏ `"điểm khác biệt"`).
- **Layer 4 (Balanced Semantic LLM Fallback)**: Prompt LLM định tuyến cân bằng cho các câu hỏi còn mơ hồ.

---

## 5. ĐÁNH GIÁ ĐỊNH TUYẾN CÔNG CỤ (TOOL ROUTING REVIEW)

- **Bản chất vấn đề**: `ALGORITHM_POLICY` (Chính sách khớp mẫu).
- **Giải pháp tối thiểu**: Thay thế việc kiểm tra `in q_lower` cứng nhắc bằng Regex Proximity Token:
  - Email Action: `r"(soạn|gửi|viết|draft)\b.{0,25}\b(email|mail|thư)"`
  - Reminder Action: `r"(nhắc|hẹn|đặt lịch|báo)\b.{0,25}\b(tôi|lịch|deadline|giờ|ngày|thi|bài tập)"`
- Không cần thay đổi kiến trúc LangGraph hay thêm LLM router.

---

## 6. ĐÁNH GIÁ HỘI THOẠI NHIỀU LƯỢT & BỘ NHỚ PHIÊN (MULTI-TURN & SESSION REVIEW)

Trả lời trực tiếp 6 câu hỏi kiểm định mã nguồn hiện tại:

| Câu hỏi kiểm định | Hiện trạng mã nguồn thực tế |
| :--- | :--- |
| **1. Hiện tại lưu trữ những gì?** | Chỉ lưu cặp chuỗi thô `{"user": "...", "ai": "..."}` trong file `runtime/chat_history.json`. |
| **2. Lưu chat thô hay thực thể cấu trúc?** | **CHỈ LƯU CHAT THÔ**. Hoàn toàn không lưu `course_code`, `targets`, hay `sources` đã giải quyết. |
| **3. Query Rewriting giải quyết đại từ thế nào?** | Chỉ kích hoạt nếu có đúng 6 cụm từ (`"môn đó"`, `"môn này"`, `"học phần đó"`, `"nó"`, `"môn đấy"`, `"kỳ đó"`). Nếu người dùng hỏi *"Email của thầy là gì?"* &rarr; **Bỏ qua hoàn toàn**, không giải quyết. |
| **4. Định danh phiên (session_id) lưu ở đâu?** | API nhận `conversation_id` nhưng `MemoryManager` **bỏ qua hoàn toàn**, không lưu hay phân lập theo session. |
| **5. Dữ liệu gì tồn tại qua các request?** | Danh sách chuỗi tin nhắn trong file `chat_history.json` dùng chung cho mọi user/session. |
| **6. Dữ liệu gì tồn tại sau khi khởi động lại server?** | Nội dung file `chat_history.json` trên ổ cứng (nhưng vẫn dùng chung, không phân tách). |

### Kết Luận Can Thiệp:
Yếu kém ở chỉ số Follow-up Resolution (**71.43%**) là **LỖI KIẾN TRÚC (ARCHITECTURE)**.  
Việc tăng `history_window` từ 5 lên 10 **hoàn toàn không thể khắc phục** câu hỏi *"Email của giảng viên là gì?"*. Cần phải bổ sung cấu trúc **`SessionState`** lưu vết thực thể chủ động (`active_course_code`, `active_target`).

---

## 7. MÔ HÌNH PHÂN TẦNG BỘ NHỚ (MULTI-LAYER MEMORY ARCHITECTURE)

*Chi tiết tại: [`docs/adr/ADR-002-memory-architecture.md`](adr/ADR-002-memory-architecture.md)*

Hệ thống cần phân lập minh bạch 5 tầng bộ nhớ:
1. **Working Memory**: Tồn tại trong vòng đời 1 request (`AgentState` trong LangGraph).
2. **Session Memory**: Theo dõi thực thể hội thoại nhiều lượt (`SessionState` theo `session_id`, TTL 24h).
3. **Personal Memory**: Hồ sơ sinh viên cá nhân hóa (ngành, khóa, sở thích) theo `user_id`.
4. **Episodic Memory**: Nhật ký sự kiện, lịch sử nhắc nhở đã tạo, tương tác học vụ đã qua.
5. **Skill / Procedural Memory**: Quy chuẩn hệ thống, biểu mẫu email, câu lệnh nhắc nhở.

---

## 8. MÔ HÌNH THẨM QUYỀN & GIẢI QUYẾT XUNG ĐỘT (AUTHORITY & CONFLICT MODEL)

Thứ tự quyền lực xử lý thông tin:
1. **Chỉ thị hiện thời của người dùng** (Explicit Current User Input)
2. **Tài liệu học vụ chính thức từ RAG** (Authoritative University Documents) &larr; **BẤT BIẾN**
3. **Trạng thái phiên làm việc** (Structured Session State)
4. **Hồ sơ sinh viên cá nhân** (Personal Profile Memory)
5. **Ký ức sự kiện quá khứ** (Episodic Memory)
6. **Mặc định hệ thống** (Skill Defaults)

> [!CAUTION]
> **Quy tắc An toàn Tuyệt đối**: Mọi thông tin học vụ (tín chỉ, giảng viên, môn tiên quyết, điều kiện tốt nghiệp) **BẮT BUỘC do Tier 2 (Tài liệu RAG) quyết định**. Bộ nhớ cá nhân hoặc ký ức của sinh viên không bao giờ được phép ghi đè chân lý học vụ của nhà trường.

---

## 9. ĐÁNH GIÁ HẠ TẦNG LƯU TRỮ BỘ NHỚ (STORAGE REVIEW: JSON VS SQLITE)

- **Hiện trạng (JSON files)**: Dễ gặp xung đột ghi đồng thời (race condition), không phân lập người dùng, dung lượng tăng vô hạn không có index hay TTL.
- **Quyết định (SQLite `runtime/advisor_memory.db`)**:
  - Không cần thêm server hay hạ tầng nặng (chạy trực tiếp local, zero-config).
  - ACID transactions bảo vệ dữ liệu tuyệt đối.
  - Hỗ trợ index nhanh theo `session_id` và `user_id`.
  - Phân loại: **`ARCHITECTURE`**.

---

## 10. ĐÁNH GIÁ TỐC ĐỘ TRUY XUẤT RAG (RETRIEVAL SPEED ARCHITECTURE)

Số liệu thực tế đo lường:
- **Local RAG Pipeline**: **~81.67 ms**
  - Dense Search (BGE-M3 trên CPU): **~75.82 ms (92.8%)**
  - BM25 Search: **~0.94 ms (1.2%)**
  - Context Builder: **~0.61 ms (0.7%)**
- **Chất lượng hiện tại**: Recall@5 = **100.0%**, MRR = **0.9399**.

### Đánh giá các phương án tối ưu:
*Chi tiết tại: [`docs/adr/ADR-003-retrieval-speed-architecture.md`](adr/ADR-003-retrieval-speed-architecture.md)*

1. **Exact Entity Fast Path (`ARCHITECTURE`)**: Bỏ qua dense search khi đã có mã môn xác thực, truy vấn trực tiếp pre-indexed chunks. Giảm latency từ 80ms xuống < 5ms. **Nên làm (P1)**.
2. **Query Embedding Cache (`ARCHITECTURE`)**: LRU Cache lưu vector 1024 chiều của các query chuẩn hóa. Giảm latency forward-pass CPU từ 75ms xuống 0.01ms. **Nên làm (P1)**.
3. **Thay mô hình nhỏ hơn MiniLM (`MODEL_CHOICE`)**: **BÁC BỎ (REJECT)**. Rủi ro cực cao làm suy giảm 100% Recall@5 trên văn bản học vụ tiếng Việt.
4. **Adaptive Top-K & RRF_K (`PARAMETER_CONFIG`)**: Đưa vào giai đoạn Parameter Sweep thử nghiệm.

---

## 11. ĐỀ XUẤT KIẾN TRÚC TRUY XUẤT MỤC TIÊU (TARGET RETRIEVAL FLOW)

```
Câu hỏi người dùng
       │
       ▼
[Query Analyzer]
       │
   Có mã môn chính xác?
   ├── YES ──► [Exact Entity Fast Index] ──(Đủ chunk & target khớp)──► [Context Builder] (<5ms)
   │                    │
   │               (Không đủ)
   └── NO ──────────────┼──────────────►
                        │
                        ▼
            [Query Embedding Cache]
               ├── (Hit) ──► Lấy vector có sẵn (<0.1ms)
               └── (Miss) ──► Chạy bge-m3 encode (~75ms)
                        │
                        ▼
            [Collection Router]
                        │
                        ▼
       [Dense Search] + [BM25 Search]
                        │
                        ▼
            [Reciprocal Rank Fusion (RRF)]
                        │
                        ▼
               [Context Builder]
```

---

## 12. BẢNG KIỂM KÊ THAM SỐ CẤU HÌNH (PARAMETER AUDIT)

| Tham Số Cấu Hình | Giá Trị Hiện Tại | Vai Trò Điều Khiển | Chỉ Số Có Thể Ảnh Hưởng | KHÔNG Thể Dùng Để Sửa |
| :--- | :---: | :--- | :--- | :--- |
| `RETRIEVAL_CANDIDATES` | 20 | Số tài liệu ứng viên lấy từ mỗi retriever | Recall@20, thời gian Dense/BM25 | Lỗi phân loại Router, mất thực thể multi-turn |
| `RERANK_TOP_K` | 8 | Số ứng viên đưa vào Cross-Encoder | Thứ hạng top đầu, thời gian rerank | Lỗi trích xuất verbatim facts |
| `CONTEXT_TOP_K` | 6 | Số chunk đóng gói gửi vào LLM prompt | Độ dài prompt, chi phí token, latency sinh | Thực thể lạ không có trong database (Abstention) |
| `MINIMUM_SCORE` | 0.1 | Ngưỡng điểm sàn lọc tài liệu | Precision, lọc nhiễu tài liệu | Sai lệch ý định người dùng ở Router |
| `RRF_K` | 60 | Hằng số làm mượt thứ hạng RRF | Trọng số cân bằng giữa Dense và BM25 | Câu hỏi thiếu mã môn |
| `LLM_TEMPERATURE` | 0.0 | Độ ngẫu nhiên khi sinh câu trả lời | Tính xác định, bám sát context | Xếp hạng tài liệu trong Vector store |
| `LLM_TIMEOUT` | 60 | Giới hạn thời gian chờ Cloud API | Khả năng chịu lỗi timeout mạng | Tốc độ xử lý của mô hình phía Cloud |
| `MAX_VALIDATION_RETRIES`| 2 | Số lần thử lại tối đa khi validation fail| Latency trường hợp xấu nhất, tỷ lệ an toàn | Lỗi trích xuất thông tin do prompt |
| `history_window` (k) | 5 | Số lượt chat đưa vào ngữ cảnh | Ngữ cảnh hội thoại gần nhất | **Không thể sửa lỗi mất dấu thực thể multi-turn** |

---

## 13. ĐÁNH GIÁ HIỆU NĂNG TỔNG THỂ (PERFORMANCE ARCHITECTURE REVIEW)

*Chi tiết tại: [`docs/adr/ADR-004-validation-performance-strategy.md`](adr/ADR-004-validation-performance-strategy.md)*

- **Bản chất thời gian xử lý E2E (~12.2s)**: Hơn 99.3% nằm ở 2 lượt gọi HTTP liên tiếp đến Cloud LLM (`api.deepseek.com`).
- **Can thiệp ưu tiên 1: Streaming Response UX (`ARCHITECTURE` - P0)**: Gửi token về UI ngay khi sinh qua Server-Sent Events (SSE), giảm Time-to-First-Token từ **10s xuống < 1.5s**.
- **Can thiệp ưu tiên 2: Single-Pass CoT Validation (`ARCHITECTURE / ALGORITHM_POLICY` - P1)**: Gộp kiểm định factsheet vào chung prompt sinh câu trả lời, giảm từ 2 lượt gọi API xuống 1 lượt duy nhất, tiết kiệm 40% – 50% tổng thời gian phản hồi.

---

## 14. BẢNG TỔNG HỢP MA TRẬN CAN THIỆP (CHANGE CLASSIFICATION MATRIX)

| Khu Vực (Area) | Vấn Đề Hiện Trạng | Nguyên Nhân Gốc Rễ | Phân Loại Can Thiệp | Thay Đổi Đề Xuất | Lợi Ích Kỳ Vọng | Rủi Ro Suy Thoái | Ưu Tiên |
| :--- | :--- | :--- | :---: | :--- | :--- | :---: | :---: |
| **Router** | Sai 3 ca General (`v2-gen-02, 03, 05`) | Target contamination & Ordering | **ALGORITHM_POLICY** | Layered Router Policy | Router Acc &ge; 98% | Thấp | **P0** |
| **Tool Routing** | Trượt câu `"Soạn giúp tôi email"` | Exact substring matching | **ALGORITHM_POLICY** | Action-Object Proximity Regex | Tool Acc = 100% | Rất thấp | **P0** |
| **Multi-turn** | Trượt lượt hỏi ngắn (`v2-multi-01-t3`) | Không duy trì active entity | **ARCHITECTURE** | Structured `SessionState` | Follow-up &ge; 90% | Rất thấp | **P0** |
| **Session Memory** | Ghi chung file JSON toàn cục | Thiếu phân lập phiên | **ARCHITECTURE** | SQLite Session Store | Độc lập phiên 100% | Thấp | **P1** |
| **Personal Memory** | 1 profile mặc định duy nhất | Chưa có quản lý user_id | **ARCHITECTURE** | SQLite Profiles Table | Cá nhân hóa theo sinh viên | Thấp | **P2** |
| **Episodic Memory** | Ghi vector nhưng không bao giờ đọc | Thiếu cơ chế đọc ký ức | **ARCHITECTURE** | Đọc lại sự kiện/lời khuyên cũ | Tăng tính liền mạch | Thấp | **P3** |
| **Skill Memory** | Chưa có định nghĩa skill riêng | Nằm rải rác trong code | **NO_CHANGE_NEEDED** | Giữ nguyên implementation | Ổn định | Không | **P3** |
| **Memory Storage** | File JSON dễ lỗi race condition | Lưu trữ tệp đơn sơ | **ARCHITECTURE** | Chuyển sang SQLite DB | ACID, bền vững, zero-config | Thấp | **P1** |
| **Memory Policy** | Chưa có thứ tự quyền lực rõ ràng | Thiếu luật giải quyết xung đột | **ALGORITHM_POLICY** | 6-tier Authority Model | RAG luôn thắng trí nhớ | 0% | **P0** |
| **Exact Entity RAG** | Dense search 75ms cho môn rõ ràng | Luôn tính toán embedding CPU | **ARCHITECTURE** | Entity Fast Index Path | Giảm latency RAG < 5ms | Rất thấp | **P1** |
| **Embedding Cache** | Tính lại vector cho query lặp | Không có bộ đệm vector | **ARCHITECTURE** | LRU Embedding Cache | Tăng tốc query lặp 75ms | 0% | **P1** |
| **Collection Routing** | Đã định tuyến 3 collections | — | **NO_CHANGE_NEEDED** | Giữ nguyên hiện trạng | Hoạt động tốt | Không | — |
| **Adaptive Top-K** | Cố định 20 candidates | Chưa linh hoạt theo filter | **ALGORITHM_POLICY** | Giảm candidate khi filter mạnh | Giảm nhẹ latency | Thấp | **P2** |
| **Reranker** | Cross-Encoder tiêu tốn RAM/CPU | Tắt an toàn trong baseline | **NO_CHANGE_NEEDED** | Giữ cơ chế Fallback an toàn | An toàn trên RAM 6GB | Không | — |
| **Embedding Model** | BGE-M3 nặng (~2.2GB) | — | **NO_CHANGE_NEEDED** | **GIỮ NGUYÊN BGE-M3** | Đạt 100% Recall@5 | Rất cao nếu đổi | — |
| **Context Top-K** | Cố định 6 chunks | — | **PARAMETER_CONFIG** | Tinh chỉnh [4, 6, 8] | Tiết kiệm token prompt | Thấp | **P2** |
| **Validation Arch** | 2 remote calls liên tiếp (~12.2s) | Double-hop LLM latency | **ARCHITECTURE** | Single-pass CoT Validation | Giảm 40-50% tổng độ trễ | Trung bình | **P1** |
| **Streaming UX** | Người dùng chờ 10s mới thấy chữ | Chế độ request-response khối | **ARCHITECTURE** | SSE Streaming Response | TTFT < 1.5 giây | Thấp | **P0** |
| **Cold Start** | Khởi động 27.5s để nạp model | Load đồng bộ lúc khởi động | **ARCHITECTURE** | Lazy load / Background preload | Giảm thời gian sẵn sàng | Thấp | **P2** |

---

## 15. NGUYÊN TẮC XÁC ĐỊNH ĐỘ ƯU TIÊN (PRIORITY FORMULA)

Công thức đánh giá:
$$\text{Priority Score} = \frac{\text{Tác động người dùng (Impact)} \times \text{Bằng chứng thực nghiệm (Evidence)}}{\text{Rủi ro suy thoái (Risk)} \times \text{Độ phức tạp thi công (Cost)}}$$

- **P0 (Khẩn cấp / Ngay lập tức)**: Ảnh hưởng trực tiếp đến các ca lỗi đã xác thực và trải nghiệm cốt lõi (Router Layering, Tool Regex, Multi-turn SessionState, Streaming UX).
- **P1 (Quan trọng / Vòng kế tiếp)**: Nâng cấp nền tảng lưu trữ và cắt giảm độ trễ chính (SQLite Memory, Entity Fast Index, Embedding Cache, Single-pass CoT Validation).
- **P2 (Cải tiến có kiểm soát)**: Tinh chỉnh tham số và tối ưu hóa thứ yếu (Adaptive Candidates, Context Top-K sweep, Cold-start preload).
- **P3 (Dài hạn / Khi cần thiết)**: Tính năng mở rộng nâng cao (Episodic Memory search, Skill registry).

---

## 16. DANH MỤC CÁC BÁO CÁO QUYẾT ĐỊNH KIẾN TRÚC (ADR REFERENCES)

1. [`docs/adr/ADR-001-routing-architecture.md`](adr/ADR-001-routing-architecture.md): *Layered Routing Architecture & Proximity-Based Tool Intent Detection*.
2. [`docs/adr/ADR-002-memory-architecture.md`](adr/ADR-002-memory-architecture.md): *Multi-Layer Memory Architecture & Structured Session State*.
3. [`docs/adr/ADR-003-retrieval-speed-architecture.md`](adr/ADR-003-retrieval-speed-architecture.md): *Retrieval Speed Optimization — Exact Entity Fast Path & Embedding Cache*.
4. [`docs/adr/ADR-004-validation-performance-strategy.md`](adr/ADR-004-validation-performance-strategy.md): *Validation Performance Strategy & Streaming UX Architecture*.

---

## 17. CÁC RÀNG BUỘC AN TOÀN BẤT BIẾN (INVARIANTS)

Mọi thay đổi kiến trúc trong tương lai **BẮT BUỘC duy trì các điều kiện tiên quyết**:
1. **`Critical Hallucinations == 0`** (Tuyệt đối không bịa đặt nguồn, không xuyên tạc môn học).
2. **`Abstention Accuracy >= 90%`** (Bảo toàn ngưỡng 100% hiện tại đối với mã môn lạ).
3. **`Wrong Premise Resistance >= 90%`** (Bảo toàn ngưỡng 100% hiện tại đối với câu hỏi bẫy).
4. **`Source Recall@5 >= 95%`** (Bảo toàn mốc 100% của bộ máy Hybrid RRF).
5. **`MRR >= 0.90`** (Bảo toàn độ tin cậy xếp hạng nguồn tiệm cận 1.0).
6. **Không rò rỉ dữ liệu chéo người dùng** (No cross-user / cross-session memory leakage).
7. **RAG luôn là chân lý tối thượng** (Không để bộ nhớ sinh viên ghi đè quy chế học vụ).
8. **Không lộ API keys / Không hardcode câu hỏi benchmark**.

---

## 18. PHÂN BIỆT RÕ RÀNG CÁC LOẠI THỬ NGHIỆM (EXPERIMENT TYPES)

Khi chuyển sang giai đoạn thực thi, các nhóm công việc phải tuân thủ đúng quy trình thực nghiệm:

1. **`ARCHITECTURE EXPERIMENT`** (ví dụ: Structured Session Memory, SQLite Store):
   - Đòi hỏi đo lường Benchmark V2 trước và sau khi thay đổi để chứng minh tính cải thiện.
2. **`POLICY EXPERIMENT`** (ví dụ: Layered Router Rules, Proximity Regex):
   - Kiểm thử đơn vị cô lập (Unit test) và đối soát trên toàn bộ 62 test cases.
3. **`PARAMETER SWEEP`** (ví dụ: quét `RETRIEVAL_CANDIDATES` trong dải `[12, 16, 20]`, `CONTEXT_TOP_K` trong `[4, 6, 8]`):
   - Tuyệt đối không tinh chỉnh mò mẫm 1 giá trị duy nhất rồi kết luận. Phải chạy ma trận grid search và chọn điểm tối ưu Pareto giữa Latency và Recall.
4. **`MODEL A/B`** (ví dụ: BGE-M3 vs MiniLM):
   - So sánh trực tiếp trên bộ dữ liệu câu hỏi tiếng Việt học vụ.
5. **`EVALUATOR CHANGE`** (ví dụ: chuẩn hóa ký tự `&` thành `and` trong bộ chấm):
   - Thay đổi trong bộ đánh giá kiểm định, tuyệt đối không làm thay đổi hành vi code sản xuất.

---

## 19. ĐỀ XUẤT THỨ TỰ THỰC THI (RECOMMENDED IMPLEMENTATION ORDER)

Dựa trên bằng chứng thực tế từ Benchmark V2 và Performance Profiling, thứ tự thi công khuyến nghị:

```
[ROUND A: Sửa lỗi Định tuyến & Công cụ] (P0 — ALGORITHM_POLICY)
├── Áp dụng Layered Router Policy (Layer 0 Tool -> Layer 1 Domain -> Layer 2 General -> Layer 3 Target)
└── Áp dụng Proximity Regex cho Tool Intent (Email, Reminder)
    │ (Giải quyết ngay 4 ca lỗi Benchmark V2)
    ▼
[ROUND B: Khắc phục Hội thoại Nhiều lượt] (P0 — ARCHITECTURE)
├── Bổ sung cấu trúc SessionState vào AgentState
└── Cập nhật Query Analyzer liên kết active_course_code cho các câu hỏi tiếp nối
    │ (Giải quyết 2 ca lỗi Multi-turn, đưa Follow-up Resolution lên >= 90%)
    ▼
[ROUND C: Tối ưu Trải nghiệm Phản hồi] (P0 — ARCHITECTURE)
└── Bổ sung Server-Sent Events (SSE) Streaming endpoint (giảm TTFT xuống < 1.5s)
    │
    ▼
[ROUND D: Hợp nhất Validation & Cắt giảm Latency] (P1 — ARCHITECTURE)
└── Thiết kế Single-Pass CoT Validation (cắt giảm 40-50% độ trễ E2E, bảo toàn 0 hallucination)
    │
    ▼
[ROUND E: Nâng cấp Hạ tầng Lưu trữ Bộ nhớ] (P1 — ARCHITECTURE)
└── Di chuyển ChatMemory và StudentMemory sang SQLite (runtime/advisor_memory.db)
    │
    ▼
[ROUND F: Tăng tốc Truy xuất RAG Cục bộ] (P1 — ARCHITECTURE)
├── Triển khai Exact Entity Fast Index Path cho câu hỏi có mã môn
└── Bổ sung Query Embedding LRU Cache
    │
    ▼
[ROUND G: Parameter Sweep & Nghiệm thu Chung cuộc] (P2 — PARAMETER_CONFIG)
└── Quét tham số tối ưu (Candidates, Context Top-K, Token Budget) và chạy Full Benchmark V2
```

---

## 20. XÁC NHẬN TOÀN VẸN MÃ NGUỒN SẢN XUẤT (NO PRODUCTION CHANGES)

- `git diff -- src/` &rarr; **HOÀN TOÀN KHÔNG CÓ THAY ĐỔI**.
- Toàn bộ nội dung công việc thuộc Phase 1A chỉ bổ sung tài liệu kỹ thuật và thiết kế kiến trúc chuẩn mực.
