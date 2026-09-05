# KINH NGHIỆM THIẾT KẾ BỘ NHỚ CÁ NHÂN VÀ PHÂN GIẢI THẨM QUYỀN TRONG AGENTIC RAG (ROUND C)
## PERSONAL MEMORY + MEMORY POLICY + AUTHORITY RESOLVER: ARCHITECTURAL INSIGHTS & PRACTICAL LESSONS

- **Dự án**: AI Academic Advisor / Agentic RAG
- **Phiên bản**: Personal Memory V1 (Round C)
- **Thời gian hoàn thiện**: 2026-09-06
- **Trạng thái**: `ACCEPTED`
- **Chi phí API Router & Memory Policy**: `0 cuộc gọi LLM bên ngoài (Zero paid API calls)`
- **Số ca kiểm thử thực nghiệm**: `60/60 (100.0% Pass)` trên 11 nhóm nghiệp vụ
- **Hồi quy Router V2**: `103/103 (100.0% Pass)`
- **Hồi quy Session Memory**: `50/50 (100.0% Pass)`
- **Độ trễ đọc P95**: `0.07 ms` (Tiêu chuẩn $< 10$ ms)
- **Độ trễ ghi P95**: `1.59 ms` (Tiêu chuẩn $< 10$ ms)

---

## 1. Mục Tiêu Và Bối Cảnh (Context & Purpose)

Trước Round C, hệ thống lưu trữ hồ sơ người dùng trong tệp phẳng `runtime/student_profile.json` dùng chung toàn cục. Kiến trúc cũ bộc lộ 4 điểm yếu nghiêm trọng:
1. **Không phân lập người dùng (No User Partitioning)**: Toàn bộ hệ thống chia sẻ chung một hồ sơ duy nhất, gây ô nhiễm chéo giữa các sinh viên khác nhau.
2. **Nhiễm bẩn giá trị mặc định (System Placeholder Pollution)**: Các giá trị mẫu của giao diện như `"Sinh viên CNTT"`, `"student@dainam.edu.vn"`, `"K19"`, `"Thực hành"` bị coi nhầm là sự thật cá nhân của người dùng.
3. **Không nhận thức nguồn gốc (No Provenance & Audit)**: Không phân biệt được giữa sự thật người dùng nói tường minh, sự thật suy diễn, hay giá trị template.
4. **Nguy cơ ghi đè chân lý học vụ (No Authority Separation)**: Khi người dùng nói *"Môn FIT4201 có 5 tín chỉ nhé"*, hệ thống cũ có nguy cơ lưu thông tin sai này và trả lời sai cho các lượt sau.

**Round C giải quyết triệt để vấn đề này bằng cách thiết lập tầng Personal Memory độc lập, bảo vệ chân lý học vụ tối thượng của RAG, và kiểm soát chính sách ghi nhớ hoàn toàn cục bộ với chi phí 0 đồng.**

---

## 2. Kiến Trúc Phân Tầng Bộ Nhớ Và Danh Tính (Architecture Subsystem)

```
                       [ Incoming User Request ]
                                   │
                                   ▼
             ┌──────────────────────────────────────────┐
             │         Principal Identity Layer         │
             │   (PrincipalContext, resolve_principal)  │
             └─────────────────────┬────────────────────┘
                                   │ user_id
                     ┌─────────────┴─────────────┐
                     ▼                           ▼
        ┌─────────────────────────┐ ┌─────────────────────────┐
        │  Personal Memory Policy │ │   Session Memory V2     │
        │ - Deterministic Regex   │ │ - SessionState (Active) │
        │ - Strict Whitelist      │ │ - Pronoun & Entity Res  │
        │ - Academic Rejection    │ └────────────┬────────────┘
        │ - Transient Rejection   │              │
        └────────────┬────────────┘              │
                     ▼                           ▼
        ┌─────────────────────────────────────────────────────┐
        │         Domain-Specific Authority Resolver          │
        │  - Academic Truth    : OFFICIAL_RAG > Memory        │
        │  - Personal Pref     : CURRENT_EXPLICIT > Stored    │
        │  - Active Entity     : EXPLICIT_QUERY > Session     │
        └──────────────────────────┬──────────────────────────┘
                                   │
                                   ▼
        ┌─────────────────────────────────────────────────────┐
        │        SQLite Local Store (WAL Mode, ACID)          │
        │  - personal_facts (user_id, fact_key, value)        │
        │  - memory_events  (user_id, event_type, audit)      │
        │  - sessions       (session_id, user_id, state)      │
        │  - messages       (session_id, role, content)       │
        └─────────────────────────────────────────────────────┘
```

### 2.1. Phân định Danh tính Dịch vụ (PrincipalContext)
- Mô hình định danh tối giản, tách bạch giữa chế độ cục bộ và tương lai đa người dùng:
  - `user_id`: Định danh sinh viên (mặc định: `"local-user"`).
  - `authenticated`: Cờ xác thực (mặc định: `False`).
  - `source`: Nguồn gốc định danh (`"LOCAL_MODE"`, `"HEADER"`, hoặc `"AUTH_TOKEN"`).
- **Ranh giới an toàn (Security Boundary)**: Đây là cơ chế cô lập mức dịch vụ (service-level data scoping), **chưa phải** hệ thống phân quyền multi-tenant bảo mật cao có JWT/OAuth2. Mọi truy vấn đọc/ghi bộ nhớ cá nhân bắt buộc gắn liền với `user_id`.

### 2.2. Bảng Cơ Sở Dữ Liệu SQLite (Schema Design)
Bổ sung bảng `personal_facts` và `memory_events` vào `runtime/advisor_memory.db`:

```sql
CREATE TABLE IF NOT EXISTS personal_facts (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    fact_key TEXT NOT NULL,
    value TEXT NOT NULL,
    source_type TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    status TEXT DEFAULT 'ACTIVE',
    UNIQUE(user_id, fact_key)
);
CREATE INDEX IF NOT EXISTS idx_personal_facts_user ON personal_facts(user_id);

CREATE TABLE IF NOT EXISTS memory_events (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    fact_key TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    source_type TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_memory_events_user ON memory_events(user_id, timestamp);
```

---

## 3. Chính Sách Bộ Nhớ An Toàn (Personal Memory Policy)

Nhằm đảm bảo **Zero External LLM Cost**, module `personal_policy.py` áp dụng quy tắc tất định 100% bằng Regex và bộ lọc ngữ nghĩa cục bộ:

1. **Danh mục sự thật được phép (Strict Whitelist)**:
   - Chỉ cho phép 9 khóa nghiệp vụ: `preferred_name`, `major`, `cohort`, `current_semester`, `preferred_language`, `response_style`, `learning_goal`, `own_email`, `specialization`.
   - Mọi khóa lạ (ví dụ: `hair_color`, `secret_token`) bị từ chối ngay lập tức.
2. **Từ chối tuyên bố học vụ (Academic Claim Rejection)**:
   - Các câu chứa mã môn học (`[A-Z]{2,4}\d{4}`) hoặc thuật ngữ học vụ trường lớp (`"tín chỉ"`, `"học phí"`, `"giảng viên"`, `"đề cương"`) **tuyệt đối không được lưu vào bộ nhớ cá nhân**. Chân lý học vụ thuộc độc quyền của tài liệu RAG chính thống.
3. **Từ chối phát ngôn cảm xúc / nhất thời (Transient & Emotional Rejection)**:
   - Các câu nói mang tính bộc phát như *"Hôm nay tôi mệt quá"*, *"Tôi đang buồn vì thi trượt"*, *"Tôi đói bụng"* bị loại bỏ, không lưu thành sự thật lâu dài.
4. **Từ chối thông tin nhạy cảm (Sensitive Privacy Rejection)**:
   - Mật khẩu, số tài khoản, CCCD, dư nợ vay, tình trạng sức khỏe bị chặn lưu trữ.
5. **Miễn nhiễm với Placeholder giả định (Placeholder Immunity)**:
   - Khi di chuyển hồ sơ từ file JSON cũ (`student_profile.json`), hệ thống chủ động bỏ qua các giá trị mẫu `"Sinh viên CNTT"`, `"student@dainam.edu.vn"`, `"K19"`, `"Thực hành"`, ngăn ngừa ô nhiễm cơ sở dữ liệu mới.

---

## 4. Cơ Chế Phân Giải Thẩm Quyền (Authority Resolver)

Hệ thống **không** dùng một thứ tự ưu tiên số học toàn cục duy nhất, mà phân định theo từng miền nghiệp vụ cụ thể:

### A. Miền Sự Thật Học Vụ (Academic Truth)
$$\text{OFFICIAL\_RAG} > \text{PERSONAL\_MEMORY} > \text{SESSION\_STATE}$$
- Tài liệu đào tạo chính thức của Khoa CNTT là chân lý tối thượng.
- Nếu sinh viên nói môn FIT4201 có 5 tín chỉ nhưng đề cương ghi 2 tín chỉ &rarr; Hệ thống chọn **2 tín chỉ** từ RAG và giải thích đính chính cho sinh viên.

### B. Miền Sở Thích Cá Nhân (Personal Preferences)
$$\text{CURRENT\_EXPLICIT\_STATEMENT} > \text{STORED\_PERSONAL\_MEMORY} > \text{SYSTEM\_DEFAULT}$$
- Chỉ thị người dùng trong câu hỏi hiện tại luôn có quyền lực tối cao để ghi đè sở thích đã lưu.
- Ví dụ: Hồ sơ lưu `response_style="detailed"`, nhưng câu hỏi hiện tại yêu cầu *"Hãy trả lời ngắn gọn thôi"* &rarr; Hệ thống tuân theo câu hỏi hiện tại (`"concise"`).

### C. Miền Thực Thể Hội Thoại (Conversation Entities)
$$\text{CURRENT\_EXPLICIT\_QUERY} > \text{SESSION\_STATE} > \text{PERSONAL\_MEMORY}$$
- Thực thể xuất hiện trực tiếp trong câu hỏi luôn ghi đè thực thể đang kích hoạt trong phiên hoặc ngành học cá nhân.

---

## 5. An Toàn Bộ Nhớ Đệm Khi Cá Nhân Hóa (Cache Personalization Safety)

Để tránh hiện tượng câu trả lời cá nhân hóa của sinh viên này (ví dụ: style ngắn gọn, sinh viên K19) bị lưu vào `ExactCache` và trả nhầm cho sinh viên khác (cần câu trả lời chi tiết):
- Hàm `_compute_profile_fingerprint` tạo chuỗi băm đại diện hồ sơ (ví dụ: `"cohort=K19|response_style=concise"`).
- `ExactCache._make_key` ghép fingerprint vào cache key:
  ```
  key::profile:cohort=K19|response_style=concise
  ```
- Kết quả: Các hồ sơ khác nhau có cache key độc lập, loại bỏ 100% rủi ro va chạm cache cá nhân hóa.

---

## 6. Kết Quả Đo Lường Thực Tế & Kinh Nghiệm Kiểm Thử (Personal Memory Evaluation Suite)

Thực nghiệm trên toàn bộ 60 ca kiểm thử của file `eval/memory/personal_cases.json`:

| STT | Nhóm Kiểm Thử (Benchmark Group) | Số Ca | Kết Quả | Tiêu Chuẩn Đánh Giá | Trạng Thái |
| :---: | :--- | :---: | :---: | :---: | :---: |
| 1 | **Explicit Fact Save** (Ghi sự thật từ chat) | 7 | 7/7 (100.0%) | $\ge 95\%$ | **PASSED** |
| 2 | **Profile Update via API** (Cập nhật qua API) | 5 | 5/5 (100.0%) | $\ge 95\%$ | **PASSED** |
| 3 | **Cross-session Personal Recall** (Nhớ chéo phiên) | 5 | 5/5 (100.0%) | $= 100\%$ | **PASSED** |
| 4 | **Preference Personalization** (Tiêm ngữ cảnh) | 5 | 5/5 (100.0%) | $\ge 95\%$ | **PASSED** |
| 5 | **Fact Update** (Cập nhật giá trị sự thật) | 5 | 5/5 (100.0%) | $\ge 95\%$ | **PASSED** |
| 6 | **Forget One Fact** (Xóa 1 sự thật riêng lẻ) | 5 | 5/5 (100.0%) | $= 100\%$ | **PASSED** |
| 7 | **Clear Profile** (Xóa toàn bộ hồ sơ) | 4 | 4/4 (100.0%) | $= 100\%$ | **PASSED** |
| 8 | **System Default Rejection** (Chống ô nhiễm mẫu) | 6 | 6/6 (100.0%) | $= 100\%$ | **PASSED** |
| 9 | **Academic Claim Rejection** (Chống sửa học vụ) | 8 | 8/8 (100.0%) | $= 100\%$ | **PASSED** |
| 10 | **Authority Conflict Resolution** (Phân giải quyền lực) | 5 | 5/5 (100.0%) | $= 100\%$ | **PASSED** |
| 11 | **Principal Service Isolation** (Cô lập User A và B) | 5 | 5/5 (100.0%) | $= 100\%$ | **PASSED** |
| **Tổng** | **Toàn bộ Suite Thực Nghiệm** | **60** | **60/60 (100.0%)** | **$\ge 95\%$** | **ACCEPTED** |

### Đo Lường Hiệu Năng & Độ Trễ (SQLite Profiling):
- **Đọc sự thật cá nhân (P95)**: `0.07 ms` (Tiêu chuẩn: $< 10$ ms)
- **Ghi sự thật cá nhân (P95)**: `1.59 ms` (Tiêu chuẩn: $< 10$ ms)
- **Xóa sự thật cá nhân (P95)**: `0.24 ms` (Tiêu chuẩn: $< 10$ ms)
- **Tạo ngữ cảnh tối thiểu (P95)**: `0.08 ms` (Tiêu chuẩn: $< 10$ ms)
- **Số cuộc gọi API tốn phí tiêu thụ**: **0** (Tuyệt đối 0 LLM calls)

---

## 7. Kết Quả Kiểm Thử Hồi Quy Hệ Thống (Full Regression Verification)

1. **Router V2 Evaluation (`eval/router/run_router_eval.py`)**:
   - Tỷ lệ chính xác: **103/103 (100.0%)** bảo toàn nguyên vẹn.
   - Chi phí API ngoài: **0**.
2. **Session Memory Evaluation (`eval/memory/run_session_eval.py`)**:
   - Tỷ lệ chính xác: **50/50 (100.0%)** lượt chat hội thoại nhiều lượt.
   - Chi phí API ngoài: **0**.
3. **Bộ Unit Tests Toàn Hệ Thống (`pytest tests/unit/ -v`)**:
   - Kết quả: **67/67 tests passed (100.0%)**.
   - Kiểm tra mã nguồn ruff: `ruff check src/ tests/ eval/` &rarr; **0 errors**.
4. **Kiểm thử Live Đồ Thị Tác Tử với DeepSeek Thực Tế (`scratch/run_live_personal_regression.py`)**:
   - Kịch bản 1 (Phong cách ngắn gọn & tên riêng): **PASS** (trả lời 20 từ, xưng hô *"Chào Tuấn Phong"*).
   - Kịch bản 2 (Khóa K19 CNTT qua API): **PASS** (tư vấn lộ trình học kỳ với mã môn phù hợp).
   - Kịch bản 3 (Tranh chấp học vụ 5 tín chỉ vs RAG 2 tín chỉ): **PASS** (khẳng định chuẩn xác *"FIT4201 có 2 tín chỉ, không phải 5 tín chỉ"*).
   - **Tổng cuộc gọi LLM tiêu thụ**: Đúng **8 cuộc gọi**, phục vụ sinh câu trả lời và kiểm định tính xác thực.

---

## 8. Đúc Kết Kinh Nghiệm & Bài Học Thực Tiễn (Key Architectural Takeaways)

1. **Không Dùng Một Thứ Tự Ưu Tiên Toàn Cục**:
   - Thẩm quyền dữ liệu phải phụ thuộc vào miền bài toán. Với kiến thức học vụ (số tín chỉ, giảng viên, môn học), tài liệu RAG chính thống bắt buộc là chân lý tối thượng. Nhưng với phong cách trả lời hay xưng hô, chỉ thị trực tiếp trong câu nói người dùng lại có quyền lực cao nhất.
2. **Loại Bỏ Hoàn Toàn Template Giả Định Trước Khi Lưu Trữ**:
   - Các giá trị placeholder trên giao diện (như `"Sinh viên CNTT"`, `"student@dainam.edu.vn"`) rất dễ bị nhầm thành dữ liệu thực của sinh viên nếu lưu trực tiếp dạng JSON phẳng. Khi chuyển sang SQLite, cần lọc bỏ dứt điểm mọi giá trị mặc định để không làm bẩn bộ nhớ cá nhân lâu dài.
3. **Cá Nhân Hóa Bắt Buộc Đi Kèm Fingerprint Để Bảo Vệ Cache**:
   - Cache phản hồi chính xác (Exact Cache) cần băm kèm hồ sơ người dùng (`profile_fingerprint`). Nếu không, một câu trả lời ngắn gọn phục vụ người dùng thích súc tích sẽ bị trả nhầm cho người dùng cần giải thích chi tiết.
4. **Giữ Chi Phí Vận Hành Ở Mức 0 Đồng Bằng Phân Tích Cục Bộ**:
   - Toàn bộ khâu trích xuất ứng viên sự thật (Candidate Extraction) và thực thi chính sách an toàn (Memory Policy) hoàn toàn xử lý bằng Regex và bộ quy tắc tất định cục bộ trong $< 2$ ms, không tốn bất kỳ cuộc gọi API nào tới LLM bên ngoài.
