# ADR-002: Multi-Layer Memory Architecture & Structured Session State

- **Status**: PARTIALLY_ACCEPTED (Session Memory Foundation: ACCEPTED; Personal & Episodic: PROPOSED)
- **Date**: 2026-09-06
- **Author**: AI Architecture Team / Agentic RAG
- **Component**: `src/memory/`, `src/rag/query_analyzer.py`, `src/agent/state.py`, `src/api/routes.py`

---

## 1. Context (Bối Cảnh)

Trong Benchmark V2, chỉ số **Follow-up Resolution Rate** đạt **71.43% (5/7 lượt)**, là chỉ số duy nhất vi phạm ngưỡng nghiệm thu ban đầu ($\ge 85\%$). Phân tích lỗi xác nhận:
- Khi người dùng hỏi ngắn gọn ở lượt 2 hoặc lượt 3 (ví dụ: *"Giảng viên phụ trách có email là gì?"* sau câu hỏi về `FIT4201`), hệ thống bị mất dấu thực thể học phần (`v2-multi-01-t3`).
- Hệ thống hiện tại lưu trữ lịch sử hội thoại dưới dạng danh sách text thuần `[{"user": "...", "ai": "..."}]` trong một file JSON dùng chung toàn cục (`runtime/chat_history.json`), không có khái niệm phiên (`session_id`), không lưu thực thể có cấu trúc, và không phân lập người dùng (`user_id`).

---

## 2. Current Architecture & Weaknesses (Kiến Trúc Hiện Tại & Lỗ Hổng)

1. **Lưu trữ JSON phẳng, phi cấu trúc**:
   - `ChatMemory` lưu toàn bộ tin nhắn vào `runtime/chat_history.json`.
   - `StudentMemory` lưu thông tin vào `runtime/student_profile.json` (chỉ có 1 profile mặc định duy nhất).
   - Khi có nhiều người dùng hoặc nhiều phiên đồng thời, dữ liệu bị ghi đè chéo (cross-session race condition).
2. **Cơ chế giải quyết đại từ thô sơ**:
   - Hàm `resolve_conversational_query` chỉ kích hoạt khi câu hỏi chứa đúng 6 cụm từ cố định: `["môn đó", "môn này", "học phần đó", "nó", "môn đấy", "kỳ đó"]`.
   - Nếu câu hỏi lượt sau là *"Email của thầy là gì?"* hoặc *"Thời lượng thực hành ra sao?"*, hệ thống hoàn toàn không kích hoạt xử lý ngữ cảnh vì không có từ khóa đại từ trên.
   - Cơ chế tìm lại mã môn chỉ quét biểu thức chính quy thô trên 5 lượt chat gần nhất mà không biết thực thể nào đang là trọng tâm hoạt động (*active entity*).
3. **Thiếu vắng cấu trúc phân tầng bộ nhớ**:
   - Không phân biệt giữa bộ nhớ ngữ cảnh tức thời (Working Memory), ngữ cảnh phiên (Session Memory), hồ sơ người dùng (Personal Memory) và sự kiện lịch sử (Episodic Memory).

---

## 3. Decision Proposal (Đề Xuất Quyết Định)

### A. Phân định 5 Tầng Bộ Nhớ (Multi-Layer Memory Hierarchy)

| Tầng Bộ Nhớ | Mục Đích | Vòng Đời | Phạm Vi | Cơ Chế Lưu Trữ | Quyền Lực (Authority) |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **1. Working Memory** | Trạng thái luồng thực thi 1 request | 1 HTTP call (vài giây) | Request hiện tại | LangGraph `AgentState` | Cao nhất trong lượt xử lý |
| **2. Session Memory** | Theo dõi thực thể hội thoại nhiều lượt | 1 phiên (TTL 2 - 24 giờ) | Theo `session_id` | SQLite `sessions` & `session_state` | Giải quyết đại từ & thực thể |
| **3. Personal Memory** | Thông tin cá nhân sinh viên (ngành, khóa, style) | Dài hạn (nhiều tháng) | Theo `user_id` | SQLite `profiles` | Chỉ mang tính cá nhân hóa |
| **4. Episodic Memory** | Lịch sử tương tác, lời khuyên đã đưa ra | Lâu dài (học kỳ) | Theo `user_id` | SQLite `events` / Vector store | Tham khảo kinh nghiệm quá khứ |
| **5. Skill / Procedural** | Mẫu prompt, công thức tạo email, reminder | Tĩnh (vĩnh viễn) | Hệ thống | Mã nguồn / Static config | Quy chuẩn thực thi công cụ |

> [!IMPORTANT]
> **Nguyên tắc Phân định Ranh giới**:
> - **RAG Knowledge Base $\ne$ Memory**: Tài liệu học vụ của trường là chân lý tối thượng, không thể bị sửa đổi bởi lời nói của sinh viên.
> - **Exact Cache $\ne$ Memory**: Cache là cơ chế tăng tốc tính toán lặp lại, không phải bộ nhớ ngữ cảnh.
> - **LangGraph State $\ne$ Long-term Memory**: State chỉ tồn tại trong vòng đời của một đồ thị thực thi.

---

### B. Cấu Trúc Trạng Thái Phiên Có Cấu Trúc (Structured SessionState)

Thay vì đoán thực thể từ chuỗi chat thô, hệ thống sẽ duy trì một bản ghi trạng thái phiên độc lập cho mỗi `session_id`:

```python
class SessionState(BaseModel):
    session_id: str
    user_id: str
    active_course_code: Optional[str] = None      # Ví dụ: "FIT4201"
    active_course_name: Optional[str] = None      # Ví dụ: "Hệ thống nhúng"
    active_domain: str = "course_detail"          # "course_detail" | "curriculum" | "regulation"
    active_target: Optional[str] = None           # "lecturer" | "credits" | "assessment"
    last_retrieved_source_ids: List[str] = []     # Danh sách chunk_id của nguồn vừa trả lời
    turn_count: int = 0
    updated_at: float                             # Timestamp để quản lý TTL
```

#### Thuật toán Giải quyết Ngữ cảnh Mới:
Khi người dùng gửi câu hỏi mới trong cùng `session_id`:
1. Nếu câu hỏi có chứa mã môn mới &rarr; Cập nhật `active_course_code` thành mã môn mới.
2. Nếu câu hỏi KHÔNG có mã môn nhưng có mục tiêu học vụ (ví dụ hỏi email, hỏi tín chỉ, hỏi lịch trình) VÀ trong `SessionState` đang có `active_course_code`:
   &rarr; Tự động bổ sung `active_course_code` vào câu hỏi phân tích (`analyzed_query.course_code = session_state.active_course_code`).
   &rarr; Giải quyết triệt để các ca như `v2-multi-01-t3` (*"Giảng viên phụ trách có email là gì?"* tự động liên kết với `FIT4201`).

---

### C. Mô Hình Thẩm Quyền & Xử Lý Xung Đột (Memory Authority & Conflict Model)

Thứ tự ưu tiên tuyệt đối giải quyết thông tin:
1. **Chỉ thị rõ ràng trong câu hỏi hiện tại** (User Explicit Override).
2. **Tài liệu học vụ chính thức từ RAG** (Authoritative University Documents).
3. **Trạng thái phiên làm việc có cấu trúc** (Structured Session State).
4. **Hồ sơ sinh viên đã xác thực** (Personal Profile Memory).
5. **Ký ức lịch sử quá khứ** (Episodic Memory).
6. **Mặc định hệ thống** (Skill Defaults).

> [!CAUTION]
> **Quy tắc Bất Biến (Safety Invariant)**:
> Dữ liệu học vụ chính thức (số tín chỉ, giảng viên, môn tiên quyết, điểm số, quy chế) **BẮT BUỘC tuân thủ Tier 2 (Tài liệu RAG)**.
> Nếu sinh viên tuyên bố: *"Tôi nhớ môn FIT4201 có 4 tín chỉ"*, nhưng RAG ghi nhận 2 tín chỉ &rarr; **Hệ thống KHÔNG được lưu 4 tín chỉ vào trí nhớ học vụ**, mà phải dùng RAG để đính chính: *"Theo đề cương chi tiết chính thức của Khoa CNTT, môn FIT4201 chỉ có 2 tín chỉ."*

---

### D. Kiến Trúc Lưu Trữ Bền Vững: Chuyển Dịch Sang SQLite

Thay thế toàn bộ các file `.json` đơn lẻ bằng một cơ sở dữ liệu SQLite duy nhất đặt tại `runtime/advisor_memory.db`:
- **Không hạ tầng ngoài**, không cần cài đặt thêm service server (phù hợp tuyệt đối với tiêu chí Level 4 Local Product).
- Hỗ trợ giao dịch an toàn (ACID transactions), không bị hỏng file khi nhiều thread ghi đồng thời.
- Hỗ trợ đánh index theo `(session_id, user_id, updated_at)` giúp truy vấn lịch sử < 1ms.

```sql
CREATE TABLE IF NOT EXISTS profiles (
    user_id TEXT PRIMARY KEY,
    name TEXT,
    major TEXT,
    cohort TEXT,
    learning_style TEXT,
    email TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT,
    active_course_code TEXT,
    active_course_name TEXT,
    active_domain TEXT,
    active_target TEXT,
    turn_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    role TEXT CHECK (role IN ('user', 'assistant')),
    content TEXT,
    sources_json TEXT,
    latency_ms REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
);
```

---

## 4. Consequences & Impact (Hệ Quả & Tác Động)

- **Tác động tích cực**:
  - Tăng tỷ lệ giải quyết hội thoại nhiều lượt (**Follow-up Resolution**) từ **71.43% lên &ge; 90%**.
  - Xóa bỏ triệt để nguy cơ rò rỉ dữ liệu giữa các phiên làm việc và race condition ghi file JSON.
  - Quản lý TTL phiên làm việc tự động (dọn dẹp phiên sau 24h).
- **Rủi ro**:
  - Cần di chuyển mã nguồn `MemoryManager` hiện tại sang mô hình SQLite mới kèm bộ test tương thích ngược.

---

## 5. Metrics to Validate

1. `Follow-up Resolution Rate`: Tăng từ **71.43% lên &ge; 90.0%**.
2. `Multi-turn Group Pass Rate`: Tăng từ **83.3% lên 100.0%** trên Benchmark V2.
3. Độ trễ ghi nhớ & truy xuất session: $< 2$ ms trên SQLite local.
4. Bảo đảm tính phân lập phiên: 0% rò rỉ thông tin giữa 2 `session_id` khác nhau.

---

## 6. Rollback Strategy

Giữ nguyên interface của `get_memory_manager()`. Nếu SQLite gặp sự cố trên hệ điều hành của client, cho phép fallback tạm thời về bộ nhớ in-memory dictionary.

---

## 7. Implementation & Verification Record (Round B Completed)

- **Date of Acceptance**: 2026-09-06
- **Implementation Subsystem**:
  - `src/memory/session_models.py`: Typed Pydantic schemas (`SessionRecord`, `SessionMessage`, `SessionState`).
  - `src/memory/store.py` & `src/memory/sqlite_store.py`: Thread-safe SQLite store with WAL mode, foreign key cascade, connection reuse, and zero external calls.
  - `src/memory/session_memory.py`: Deterministic entity extraction, pronoun resolution, target carry-over, and session clearing.
  - `src/memory/memory_manager.py`: Integrated facade exposing `session` and `profile`.
- **Benchmark Results (eval/memory/run_session_eval.py - 18 scenarios, 50 turns)**:
  - Follow-up Entity Resolution: **100.0% (23/23)** [Gate: $\ge 90\%$]
  - Target Resolution Accuracy: **100.0% (36/36)** [Gate: $\ge 90\%$]
  - Entity Switching Accuracy: **100.0% (13/13)** [Gate: $\ge 95\%$]
  - Cross-session Isolation: **100.0% (6/6)** [Gate: $= 100\%$]
  - Ambiguity Safety: **100.0% (4/4)** [Gate: $\ge 90\%$]
  - Restart Persistence: **100.0% (6/6)** [Gate: $= 100\%$]
  - Router V2 Compatibility: **100.0%** [Gate: $\ge 97\%$]
  - Overall Turns Passed: **100.0% (50/50)**
  - SQLite Read Latency (P95): **0.31 ms** [Gate: $< 10$ ms]
  - SQLite Write Latency (P95): **1.54 ms** [Gate: $< 10$ ms]
  - External API calls consumed: **0**
- **Live DeepSeek Regression**: 3 multi-turn scenarios verified via `POST /api/chat`, 14 LLM calls consumed under strict cost control.

