# TÀI LIỆU KỸ THUẬT & ĐÚC KẾT KINH NGHIỆM: KIẾN TRÚC CONTEXT-SAFE CACHE
## Tối Ưu Hóa Tầng Bộ Đệm Trong Hệ Thống Hội Thoại Agentic RAG

> **Tài liệu kỹ thuật**: Đúc kết sai lầm kiến trúc, bài học thực chiến và giải pháp thiết kế tầng Cache an toàn ngữ cảnh (Context-Safe Cache Architecture) cho hệ thống AI Academic Advisor.

---

## 1. Bản Chất Của Vấn Đề: "CACHE ≠ MEMORY"

Trong các hệ thống RAG hội thoại nhiều lượt (Multi-turn Agentic RAG), một sai lầm kiến trúc rất phổ biến là **đặt tầng Exact Cache ở cổng vào đầu tiên của đồ thị (Graph Entrypoint)** trước khi tiến hành phân tích câu hỏi (Query Analysis) và định tuyến ý định (Router).

```
[ LỖI THIẾT KẾ BAN ĐẦU ]
User Query ──> [ Exact Cache ] ──(Hit)──> Trả kết quả ngay (BỎ QUA SESSION & PROFILE)
                     │ (Miss)
                     ▼
             [ Query Analysis & Intent Router ]
```

### Hậu quả tai hại trong thực tế:
1. **Ô nhiễm chéo giữa các phiên hội thoại (Cross-Session Collision)**:
   - Phiên 1: Sinh viên hỏi về môn *FIT4201 (Hệ thống nhúng)*. Lượt tiếp theo sinh viên hỏi: *"Email thì sao?"*. Hệ thống trả về email của thầy Nguyễn Văn Nhẫn và lưu vào Exact Cache với key `"email thì sao?"`.
   - Phiên 2: Sinh viên khác đang hỏi về môn *FIT3101 (Lập trình Web)*. Lượt tiếp theo sinh viên cũng hỏi: *"Email thì sao?"*.
   - **Thảm họa xảy ra**: Exact Cache lập tức đánh trúng (Cache HIT) và trả về email của thầy dạy môn Hệ thống nhúng cho sinh viên đang hỏi môn Lập trình Web!
2. **Thực thi lặp rỗng công cụ (Tool Action Staling)**:
   - Khi sinh viên yêu cầu: *"Nhắc tôi ôn thi vào 8h sáng mai"*.
   - Nếu câu này bị cache, lần tiếp theo sinh viên nhắc lại yêu cầu tương tự, hệ thống lấy luôn câu trả lời đã cache từ hôm trước mà **không hề kích hoạt Scheduler tạo tác vụ mới**.
3. **Mù lòa trước biến động hồ sơ cá nhân (Profile Mutation Blindness)**:
   - Sinh viên đổi chuyên ngành từ *Công nghệ thông tin* sang *Kỹ thuật phần mềm*, hoặc đổi phong cách từ *Ngắn gọn* sang *Chi tiết*.
   - Do fingerprint cache cũ chỉ băm sơ sài một vài trường hoặc dùng khóa câu hỏi thô, câu trả lời cá nhân hóa cũ bị trả lại, làm mất tính đồng bộ của Personal Memory.

---

## 2. Giải Pháp Kiến Trúc: Đưa Phân Loại & Phân Giải Lên Trước Cache

Nguyên tắc cốt lõi: **Không một câu hỏi nào được phép tra cứu Cache trước khi hệ thống biết rõ danh mục ý định (Category) và thực thể phiên (Session State).**

### Luồng điều hướng chuẩn tắc mới trong LangGraph:

```
                  [ ENTRY: query_analysis ]
                             │
                             ▼
                    [ router_node (0ms) ]
                             │
                             ▼
                     [ cache_node ]
           (Đánh giá CachePolicy: 4 Phạm Vi)
                             │
         ┌───────────────────┴───────────────────┐
         │ (Cache HIT)                           │ (Cache MISS / BYPASS)
         ▼                                       ▼
   [ save_chat ]                     Phân nhánh theo Router:
         │                           ├─► DOMAIN_DATA  ──> [ retrieve ] ──> [ rerank ] ──> ...
         ▼                           ├─► GENERAL_LLM  ──> [ general_answer ] ──> ...
       [ END ]                       ├─► TOOL (Email) ──> [ email_node ] ──> ...
                                     └─► TOOL (Remind)──> [ reminder_node ] ──> ...
```

---

## 3. Ma Trận Phân Loại 4 Phạm Vi Cache (Cache Scope Taxonomy)

Mỗi câu truy vấn đi qua `decide_cache_policy()` được phân loại tất định thành một trong 4 phạm vi:

| Phạm vi (Scope) | Điều kiện kích hoạt | Hành vi Cache | Định dạng Khóa chuẩn tắc (Cache Key) |
| :--- | :--- | :--- | :--- |
| **`GLOBAL_SAFE`** | Câu hỏi tri thức chung, mã môn rõ ràng, không phụ thuộc phiên hay cá nhân | Cho phép Cache & Hit toàn cục | `{category}::{normalized_query}::global` |
| **`PROFILE_SCOPED`** | Câu hỏi có tiêm ngữ cảnh Personal Memory (kế hoạch, phong cách, tên gọi) | Cache phân vùng theo hồ sơ | `{category}::{normalized_query}::profile:{digest}` |
| **`SESSION_SENSITIVE`** | Câu hỏi chứa đại từ (*môn đó, học phần này*), câu hỏi tỉnh lược (*email thì sao, ai dạy*) | **BẮT BUỘC BYPASS CACHE** | `None` (Không lưu, không đọc) |
| **`NON_CACHEABLE`** | Tác vụ công cụ thay đổi trạng thái thế giới (*SET_REMINDER, SEND_EMAIL*) | **TUYỆT ĐỐI KHÔNG CACHE** | `None` (Luôn thực thi mới) |

### Cơ chế băm hồ sơ chuẩn tắc (Canonical Profile Digest):
Để bảo mật thông tin cá nhân và tránh phụ thuộc vào thứ tự key trong JSON:
1. Lọc bỏ các trường rỗng hoặc `None`.
2. Sắp xếp key theo thứ tự bảng chữ cái (`sort_keys=True`).
3. Chuẩn hóa chuỗi Unicode NFC và định dạng JSON chặt chẽ (`separators=(',', ':')`).
4. Băm `SHA-256` và lấy 16 ký tự hex đầu tiên. Tuyệt đối không lưu plaintext PII trong khóa cache.

---

## 4. Kết Quả Thực Nghiệm Độc Lập

Bộ kiểm thử độc lập tại `eval/cache/run_cache_eval.py` gồm **42 trường hợp kiểm thử** trên 10 nhóm kịch bản đối kháng:

```
================================================================================
ROUND C.1 — CONTEXT-SAFE CACHE EVALUATION SUITE
Total test cases: 42
Cost Policy: Verified zero external API calls
================================================================================

EVALUATION RESULTS BREAKDOWN BY GROUP:
  - GLOBAL_SAFE_DOMAIN            : 5/5 (100.0%)
  - GLOBAL_SAFE_GENERAL           : 4/4 (100.0%)
  - PROFILE_SCOPED_PLANNING       : 4/4 (100.0%)
  - PROFILE_MUTATION_SAFETY       : 4/4 (100.0%)
  - PROFILE_ISOLATION             : 3/3 (100.0%)
  - SESSION_SENSITIVE_PRONOUN     : 4/4 (100.0%)
  - SESSION_SENSITIVE_FOLLOWUP    : 4/4 (100.0%)
  - SESSION_COLLISION_SAFETY      : 4/4 (100.0%)
  - ENTITY_SWITCH_SAFETY          : 4/4 (100.0%)
  - TOOL_ACTION_NON_CACHEABLE     : 6/6 (100.0%)
--------------------------------------------------------------------------------
Overall Policy Classification Accuracy: 42/42 (100.00%)
Policy Latency P50: 34.75 us | P95: 121.54 us (0.1215 ms) | P99: 1479.49 us
--------------------------------------------------------------------------------
Safety & Integrity Invariants Verification:
  [1] Global Safe Cache Accuracy     : 100%
  [2] Profile Isolation Accuracy     : 100%
  [3] Profile Mutation Safety        : 100%
  [4] Session Collision Safety       : 100%
  [5] Entity Switch Safety           : 100%
  [6] Tool Non-cacheability          : 100%
  [7] Cache Payload Integrity        : 100%
  [8] Local Overhead Latency P95     : 0.1215 ms (Target: < 2.0 ms)
  [9] External API Calls             : 0 (Strict Cost Policy: PASS)
================================================================================
ROUND C.1 FINAL VERDICT: ACCEPTED
```

---

## 5. Đúc Kết Kinh Nghiệm Thực Chiến

1. **Hiệu năng không thể đánh đổi sự chính xác**:
   - Cache tại entrypoint có thể tiết kiệm thêm 5-10ms cho câu hỏi follow-up, nhưng trả giá bằng việc làm sai lệch thông tin giữa các sinh viên và giữa các phiên hội thoại.
   - Chuyển Cache ra sau Query Analysis và Router chỉ làm tăng ~0.12ms cho khâu tính toán policy (chạy bằng Python thuần), nhưng loại bỏ hoàn toàn 100% nguy cơ ô nhiễm chéo.
2. **Phân biệt rạch ròi giữa Cache và State**:
   - Cache là bộ nhớ tạm tối ưu hóa thời gian tính toán của các tác vụ tất định không đổi.
   - Hội thoại nhiều lượt là quá trình dịch chuyển trạng thái (State Transition). Một câu hỏi tỉnh lược ngắn ngủi như *"ở đâu?"* hay *"email thì sao?"* mang ngữ nghĩa hoàn toàn khác nhau phụ thuộc vào trạng thái thực thể của phiên hiện tại. Vì vậy, các câu hỏi phụ thuộc phiên bắt buộc phải bypass Exact Cache.
3. **Mọi thay đổi hồ sơ phải tự động làm mất hiệu lực Cache cũ**:
   - Sử dụng Canonical Profile Digest gắn liền vào khóa cache đảm bảo rằng ngay khi sinh viên cập nhật thông tin cá nhân, toàn bộ câu trả lời cache cũ tự động bị bỏ qua mà không cần cơ chế quét xóa cache phức tạp.
