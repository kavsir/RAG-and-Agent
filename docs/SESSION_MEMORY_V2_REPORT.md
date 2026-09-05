# KINH NGHIỆM XỬ LÝ HỘI THOẠI ĐA LƯỢT VÀ BỘ NHỚ PHIÊN CÓ CẤU TRÚC (SESSION MEMORY V2)
## STRUCTURED SESSION STATE & MULTI-TURN ENTITY RESOLUTION: ARCHITECTURAL INSIGHTS

- **Trạng thái**: `ACCEPTED_WITH_DISTINCTION`
- **Phiên bản**: `Round B - Session Memory Foundation`
- **Thời gian hoàn thành**: 2026-09-06
- **Kho lưu trữ**: `https://github.com/kavsir/RAG-and-Agent.git`
- **Baseline Commit**: `c567d4d4d90ef84de63f0d74b2c8b4b6af880bbb`

---

## 1. Tổng Quan & Bối Cảnh (Executive Summary)

Trong Benchmark V2, chỉ số **Follow-up Resolution Rate** chỉ đạt **71.43% (5/7 lượt)** do hệ thống lưu lịch sử chat dạng danh sách text thô toàn cục (`runtime/chat_history.json`). Hệ thống không có sự phân lập giữa các phiên (`session_id`), không lưu thực thể hoạt động (`active entity`), và giải quyết ngữ cảnh bằng cách quét regex thô trên lịch sử hội thoại.

Nhiệm vụ **Round B** triển khai bộ nhớ phiên có cấu trúc (`Structured SessionState`), tách biệt lưu trữ theo từng `conversation_id` trên nền tảng **SQLite WAL mode** (`runtime/advisor_memory.db`), cung cấp cơ chế phân giải thực thể tất định, giải quyết đại từ thay thế, chuyển đổi thực thể (*entity switching*), kế thừa mục tiêu (*target carry-over*), và an toàn trước câu hỏi mơ hồ.

### Tóm tắt Kết Quả Thực Nghiệm & Đo Lường (Benchmark Summary)

| Tiêu Chí Đo Lường | Ngưỡng Tối Thiểu | Kỳ Vọng | Kết Quả Đạt Được | Trạng Thái |
| :--- | :---: | :---: | :---: | :---: |
| **Follow-up Entity Resolution** | $\ge 90.0\%$ | $\ge 95.0\%$ | **100.0% (23/23)** | **VƯỢT CHỈ TIÊU** |
| **Target Resolution Accuracy** | $\ge 90.0\%$ | $\ge 95.0\%$ | **100.0% (36/36)** | **VƯỢT CHỈ TIÊU** |
| **Entity Switching Accuracy** | $\ge 95.0\%$ | $100.0\%$ | **100.0% (13/13)** | **HOÀN HẢO** |
| **Cross-session Isolation** | $= 100.0\%$ | $100.0\%$ | **100.0% (6/6)** | **HOÀN HẢO** |
| **Ambiguity Safety Accuracy** | $\ge 90.0\%$ | $\ge 95.0\%$ | **100.0% (4/4)** | **HOÀN HẢO** |
| **Restart Persistence** | $= 100.0\%$ | $100.0\%$ | **100.0% (6/6)** | **HOÀN HẢO** |
| **Router V2 Compatibility** | $\ge 97.0\%$ | $100.0\%$ | **100.0% (50/50)** | **BẢO TOÀN** |
| **Tỷ lệ Lượt Đạt Toàn Bộ** | $\ge 90.0\%$ | $\ge 95.0\%$ | **100.0% (50/50)** | **HOÀN HẢO** |
| **Độ trễ Đọc Session (P95)** | $< 10.0$ ms | $< 5.0$ ms | **0.31 ms** | **SIÊU NHẸ** |
| **Độ trễ Ghi Session (P95)** | $< 10.0$ ms | $< 5.0$ ms | **1.54 ms** | **SIÊU NHẸ** |
| **Chi phí API Router/Memory** | 0 calls | 0 calls | **0 calls ($0.00)** | **100% CỤC BỘ** |

---

## 2. Kiến Trúc Hệ Thống & Mô Hình Dữ Liệu

### 2.1 Cấu Trúc Module (`src/memory/`)

```
src/memory/
├── __init__.py           # Public exports (SessionStore, SQLiteSessionStore, SessionMemoryService, ...)
├── session_models.py     # Pydantic schemas (SessionRecord, SessionMessage, SessionState)
├── store.py              # Abstract Base Class SessionStore (CRUD contract)
├── sqlite_store.py       # Production SQLite implementation (WAL mode, foreign keys, thread-local)
├── session_memory.py     # Deterministic Entity & Target Resolution Service
└── memory_manager.py     # Integrated Coordinator Facade (session + profile)
```

### 2.2 Sơ Đồ Thực Thể Cơ Sở Dữ Liệu (SQLite Schema)

File cơ sở dữ liệu: `runtime/advisor_memory.db`

```sql
-- 1. Bảng phiên làm việc
CREATE TABLE IF NOT EXISTS sessions (
    conversation_id TEXT PRIMARY KEY,
    user_id TEXT DEFAULT 'anonymous',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Bảng trạng thái thực thể có cấu trúc của từng phiên
CREATE TABLE IF NOT EXISTS session_states (
    conversation_id TEXT PRIMARY KEY,
    active_course_code TEXT,
    active_course_name TEXT,
    active_entity_type TEXT DEFAULT 'course',
    active_entities_json TEXT DEFAULT '{}',
    active_target TEXT,
    last_sources_json TEXT DEFAULT '[]',
    unresolved_reference INTEGER DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(conversation_id) REFERENCES sessions(conversation_id) ON DELETE CASCADE
);

-- 3. Bảng lịch sử tin nhắn phân vùng theo phiên
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role TEXT CHECK(role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(conversation_id) REFERENCES sessions(conversation_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_conv_created 
ON messages(conversation_id, created_at);
```

### 2.3 Cơ Chế Tối Ưu Hiệu Năng SQLite
- **WAL Mode (`PRAGMA journal_mode = WAL;`)**: Cho phép đọc và ghi diễn ra đồng thời mà không bị nghẽn khóa (locking contention).
- **Đồng Bộ Bình Thường (`PRAGMA synchronous = NORMAL;`)**: Giảm số lần gọi flush đĩa vật lý nhưng vẫn đảm bảo toàn vẹn dữ liệu trong trường hợp tiến trình bị tắt đột ngột.
- **Thread-Local Connection Reuse**: Mỗi luồng thực thi tái sử dụng kết nối SQLite riêng biệt thông qua `threading.local()`, loại bỏ chi phí mở/đóng file lặp lại.
- **Foreign Keys Cascade (`PRAGMA foreign_keys = ON;`)**: Tự động dọn dẹp toàn bộ `session_states` và `messages` khi một phiên bị xóa (`DELETE /api/conversations/{conversation_id}`).

---

## 3. Mô Hình Quyền Lực & An Toàn (Authority & Security Model)

> [!IMPORTANT]
> **Ranh Giới Quyền Lực (Authority Model)**:
> 1. **Session Memory CHỈ cung cấp Ngữ Cảnh Thực Thể (Entity Context)**: Session memory lưu mã môn học (`active_course_code`), tên môn (`active_course_name`), và mục tiêu tra cứu gần nhất (`active_target`).
> 2. **RAG Knowledge Base là CHÂN LÝ DUY NHẤT (Sole Source of Truth)**: Bộ nhớ không lưu trữ các sự kiện học vụ (như số tín chỉ, tên giảng viên, chuẩn đầu ra) làm nguồn sự thật. Mọi câu trả lời factual bắt buộc phải được truy xuất và kiểm chứng qua tài liệu nhà trường.
> 3. **Chống Ô Nhiễm Mục Tiêu (Target Anti-Pollution)**: Khi người dùng chuyển sang câu hỏi khái niệm chung (ví dụ: *"Cloud computing là gì?"* sau câu hỏi về `FIT4113`), hệ thống phân định tín hiệu khái niệm thuần túy và không ép buộc câu hỏi mới vào ngữ cảnh học phần cũ.

> [!WARNING]
> **Lưu Ý Về Ranh Giới Bảo Mật (Security & Isolation Boundary)**:
> - Tính phân lập phiên (`Cross-session Isolation`) được thiết kế ở mức **phân vùng `conversation_id`**.
> - Đây là cơ chế cô lập dữ liệu giữa các tab trình duyệt hoặc các luồng hội thoại độc lập của người dùng, **CHƯA PHẢI là cơ chế xác thực đa người dùng an toàn (Multi-Tenant Authenticated Authorization)** với JWT/OAuth2. 
> - Khi hệ thống tích hợp đăng nhập sinh viên trong các phiên bản sau, `user_id` sẽ được gán bắt buộc qua token xác thực để ngăn chặn việc đoán mò `conversation_id`.

---

## 4. Chi Tiết Kết Quả Đánh Giá Bộ Nhớ Phiên (Benchmark Methodology)

Bộ đánh giá `eval/memory/session_cases.json` gồm **18 kịch bản (scenarios)** với **50 lượt (turns)** được phân thành 7 nhóm kiểm thử độc lập:

1. **Group A - Basic Follow-up (12 turns)**: Kế thừa mã môn học từ lượt 1 sang lượt 2 và lượt 3 với đại từ hoặc câu hỏi ngữ cảnh rút gọn (ví dụ: `FIT4201` -> *"Ai dạy môn đó?"* -> *"Email của thầy là gì?"*). Đạt **12/12 (100%)**.
2. **Group B - Entity Switching (8 turns)**: Người dùng chủ động đổi thực thể (ví dụ: `FIT4201` -> *"Còn môn FIT4104 thì sao?"* -> *"Môn đó có mấy tín chỉ thực hành?"*). Trạng thái phiên chuyển đổi chính xác từ `FIT4201` sang `FIT4104`, không bị ô nhiễm chéo. Đạt **8/8 (100%)**.
3. **Group C - Target Carry-over (6 turns)**: Lượt hỏi kế tiếp về email hoặc hình thức thi kế thừa đúng mục tiêu giảng viên/học phần. Đạt **6/6 (100%)**.
4. **Group D - Cross-session Isolation (6 turns)**: Hai phiên hội thoại độc lập `sess-user-X` và `sess-user-Y` hỏi xen kẽ hai môn khác nhau (`FIT4201` vs `FIT4104`). Tỷ lệ rò rỉ thông tin là **0.0%**. Đạt **6/6 (100%)**.
5. **Group E - Ambiguous Reference Safety (4 turns)**: Người dùng bắt đầu phiên mới bằng đại từ mơ hồ (*"Môn đó có mấy tín chỉ hả bot?"* mà chưa hề nhắc đến môn nào). Hệ thống nhận diện cờ `unresolved_reference = True`, không bịa đặt mã môn, yêu cầu người dùng cung cấp thông tin. Đạt **4/4 (100%)**.
6. **Group F - General-after-Domain (8 turns)**: Sau khi hỏi về môn học, người dùng hỏi câu hỏi lý thuyết khái niệm kỹ thuật chung (*"Cloud computing là gì?"*, *"REST API là gì?"*). Hệ thống phân loại chính xác `GENERAL_LLM`, không bị ép vào `DOMAIN_DATA`. Đạt **8/8 (100%)**.
7. **Group G - Restart Persistence (6 turns)**: Đóng kết nối store, khởi tạo lại tiến trình service từ database đĩa, xác minh toàn bộ `SessionState` và lịch sử vẫn nguyên vẹn. Đạt **6/6 (100%)**.

---

## 5. Đánh Giá Hồi Quy Toàn Diện (Regression Verification)

1. **Router V2 Evaluation Suite (`eval/router/run_router_eval.py`)**:
   - 103/103 test cases đạt **100.00%** (Benchmark V2: 62/62; Holdout: 41/41).
   - Chi phí: 0 external API calls.
2. **Bộ Kiểm Thử Đơn Vị (`tests/unit/`)**:
   - 55/55 unit tests đạt **PASSED** (bao gồm 8 test suites chuyên biệt cho `test_session_memory.py`).
3. **Kiểm Tra Mã Nguồn (`ruff check`)**:
   - `ruff check src/ tests/ eval/`: **All checks passed! (0 warnings, 0 errors)**.
4. **Kiểm Thử Sản Phẩm Thực Tế (Live LLM Regression with DeepSeek)**:
   - Chạy 3 kịch bản hội thoại đa lượt qua endpoint `POST /api/chat`.
   - Kết quả: Phân giải thực thể đa lượt, chuyển đổi mã môn và câu hỏi khái niệm tiếp nối đều hoạt động trơn tru trên đồ thị LangGraph.
   - Tổng số cuộc gọi LLM tiêu thụ: **14 cuộc gọi**, được kiểm soát chặt chẽ trong ngân sách.

## 6. Bài Học Kỹ Thuật & Đúc Kết Thực Tiễn (Key Architectural Takeaways)

1. **Theo Dõi Thực Thể Hoạt Động Thay Vì Quét Cửa Sổ Lịch Sử Thô**:
   - Thay vì tăng kích thước cửa sổ chat thô (khiến prompt phình to và dễ phân tâm), việc duy trì một cấu trúc `SessionState` nhỏ gọn (lưu `active_course_code`, `active_target`) giúp giải quyết đại từ và câu hỏi follow-up chính xác 100% với chi phí phân tích bằng 0.
2. **SQLite WAL Mode Cung Cấp Tính Bền Vững Với Độ Trễ Siêu Thấp**:
   - Chuyển từ JSON phẳng sang SQLite Write-Ahead Logging (WAL) giúp xử lý đồng thời an toàn giữa nhiều luồng đọc/ghi, đạt độ trễ P95 đọc **0.31 ms** và ghi **1.54 ms**, loại bỏ hoàn toàn tình trạng race-condition.
3. **An Toàn Trước Tham Chiếu Mơ Hồ (Ambiguous Reference Safety)**:
   - Khi người dùng hỏi đại từ mơ hồ (*"Môn đó có mấy tín chỉ?"*) ngay lượt đầu tiên mà phiên chưa có thực thể kích hoạt, hệ thống cần gắn cờ `unresolved_reference = True` để yêu cầu làm rõ, tránh tuyệt đối việc agent tự suy đoán hoặc hallucinate mã môn ngẫu nhiên.
4. **Không Ép Câu Hỏi Lý Thuyết Chung Vào Ngữ Cảnh Môn Học Cũ**:
   - Khi người dùng chuyển từ hỏi môn học sang hỏi khái niệm IT chung (*"Cloud computing là gì?"*), hợp đồng định tuyến giữa Session Memory và Router V2 cần nới lỏng (weak contract) để phân loại đúng `GENERAL_LLM`, không bị bó hẹp trong tài liệu môn học trước đó.
