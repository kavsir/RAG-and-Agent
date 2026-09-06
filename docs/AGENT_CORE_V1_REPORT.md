# KINH NGHIỆM KIẾN TRÚC & TRIỂN KHAI: GOAL-DRIVEN AGENT CORE V1

**Dự án:** AI Academic Advisor / Agentic RAG  
**Phân hệ:** Goal-Driven Agent Core V1 (`src/agent_core/`)  
**Tài liệu:** Đúc kết kinh nghiệm thiết kế kiến trúc và bài học kỹ thuật thực tế.

---

## 1. BỐI CẢNH VÀ NGUYÊN LÝ THIẾT KẾ

Trong các hệ thống Agentic RAG truyền thống, hai lỗi kiến trúc phổ biến nhất thường xảy ra:
1. **Pipeline tuyến tính tĩnh (`User Query -> Router -> RAG -> LLM Answer`):** Không xử lý được các câu hỏi mơ hồ, câu hỏi thiếu thực thể, câu hỏi yêu cầu so sánh đa học phần hoặc dữ liệu ngoài phạm vi chính thức.
2. **Vòng lặp ReAct tự do (`Think -> Act -> Think -> Act vô tận`):** Dẫn đến suy diễn lan man (hallucination), bẫy lặp vô tận (infinite loop), và tự ý quy đổi mục tiêu người dùng mà không có căn cứ (ví dụ: tự ý lấy số tín chỉ để trả lời cho "môn nào khó hơn").

**Triết lý kiến trúc của Goal-Driven Agent Core V1:**
Lấy **MỤC TIÊU THỰC SỰ CỦA NGƯỜI DÙNG** làm trung tâm, vận hành theo vòng lặp có chặn (Bounded Loop):
```
USER
  │
  ▼
UNDERSTAND (Phân tích thực thể, ý định, phát hiện khoảng trống dữ liệu)
  │
  ▼
OBSERVE (Thu thập quan sát có cấu trúc từ môi trường & hệ thống con)
  │
  ▼
PLAN (Lập kế hoạch hành động đơn lẻ tiếp theo kèm ActionFingerprint)
  │
  ▼
ACT (Thực thi nguyên tử: Catalog Lookup, Exact Retrieval, Compare, Ask User, Abstain)
  │
  ▼
VERIFY (Thẩm định bằng chứng học vụ dựa trên tài liệu chính quy)
  │
  ▼
KIỂM TRA TIẾN TRÌNH & ĐIỀU KIỆN DỪNG:
┌──────────────────────────────────────────────┐
│ - Goal hoàn thành?                           │
│ - Dữ liệu đã đủ & chính quy?                 │
│ - User intent đủ rõ ràng?                    │
│ - Có tiến triển mới giữa các snapshot không? │
└──────────────────────┬───────────────────────┘
                       │
       ┌───────────────┴───────────────┐
       ▼                               ▼
    ASK USER                         FINISH
(Làm rõ / Duyệt phương án)   (Xuất kết quả kèm nguồn)
```

---

## 2. NGUYÊN TẮC CỐT LÕI: USER GOAL > AGENT ASSUMPTION

Một trong những bài học quan trọng nhất khi xây dựng tác tử tư vấn học vụ: **Tuyệt đối không để Agent tự ý thay đổi hoặc suy diễn mục tiêu của người dùng.**

- **Kịch bản thực tế:** Khi sinh viên hỏi: *"Môn nào khó hơn giữa FIT4201 và FIT4104?"*
- **Sai lầm phổ biến:** Agent tự gán nhãn môn 3 tín chỉ là khó hơn môn 2 tín chỉ và khẳng định với sinh viên. Đây là thông tin suy diễn sai lệch, vi phạm tính chính quy của văn bản đào tạo.
- **Giải pháp chuẩn hóa trong Agent Core V1:**
  1. Nhận diện `difficulty` là trường dữ liệu không công bố chính thức (`UNAVAILABLE_FIELDS`).
  2. Không đoán mò, không gán nhãn.
  3. Kích hoạt cơ chế **Đề xuất phương án thay thế có sự phê duyệt của người dùng (Human-in-the-loop Alternative Proposal)**.
  4. Đặt câu hỏi: *"Tài liệu chính thức không xếp hạng độ khó. Mình có thể so sánh gián tiếp bằng số tín chỉ, tỷ trọng thực hành và hình thức đánh giá. Bạn có muốn dùng các tiêu chí này để so sánh không?"*
  5. Nếu người dùng chấp thuận: Thực hiện so sánh theo các tiêu chí đã duyệt.
  6. Nếu người dùng từ chối: Dừng tra cứu an toàn (`ABSTAINED`) với thái độ chuẩn mực.

---

## 3. "SUY NGHĨ" (THINKING) = CẤU TRÚC QUYẾT ĐỊNH TƯỜNG MINH

Agent Core V1 quán triệt nguyên tắc: **NÓI KHÔNG VỚI CHUỖI VĂN BẢN SUY DIỄN TỰ DO (`chain_of_thought` / `reasoning_text`).**

Toàn bộ quá trình "suy nghĩ" của tác tử được biểu diễn bằng các cấu trúc dữ liệu Pydantic chặt chẽ:
- **`GoalSpec`:** Đặc tả mục tiêu, phân loại độ rõ ràng (`CLEAR`, `UNDERSPECIFIED`, `AMBIGUOUS`), xác định rõ `missing_slot` (`intent`, `entity`, `data`, `entity_conflict`, `unknown_entity`).
- **`ActionPlan`:** Kế hoạch thực thi hành động đơn lẻ kế tiếp, chứa `ActionFingerprint`, `reason_code` và payload làm rõ.
- **`ActionObservation`:** Kết quả quan sát sau thực thi, đo lường số bằng chứng mới thu thập được, danh sách requirement đã thỏa mãn.
- **`ProgressSnapshot`:** Ảnh chụp tiến trình tại từng bước (`iteration`, `satisfied_requirements`, `missing_requirements`, `evidence_count`).

Nhờ cấu trúc hóa 100%, hệ thống:
- Có thể kiểm thử tự động mọi bước chuyển trạng thái (State Transition).
- Dễ dàng debug và tái hiện lỗi mà không phụ thuộc vào độ bất định của LLM tự do.
- Đạt độ trễ trung bình cực nhỏ (~2.35 ms) do không phụ thuộc vào LLM external calls.

---

## 4. BA CHỐT CHẶN CHỐNG LẶP VÔ TẬN (ANTI-LOOP INVARIANTS)

Để đảm bảo tỷ lệ kết thúc của Agent luôn là 100% trong mọi tình huống fuzz/malformed, Agent Core V1 phối hợp 3 cơ chế độc lập:

### 4.1. Max Iterations Per Requirement
- Mỗi yêu cầu bằng chứng (`EvidenceRequirement`) chỉ được phép thử tối đa **2 lần** (`attempt_count <= 2`).
- Nếu sau 2 lần thử mà tài liệu không cung cấp đủ thông tin, requirement bị đánh dấu cạn kiệt (`EXHAUSTED`).
- Hệ thống tự động chuyển sang phương án kết thúc từng phần (`PARTIAL_ANSWER`) hoặc từ chối (`ABSTAIN`), không bao giờ thử lại mù quáng.

### 4.2. No-Progress Detection qua ProgressSnapshot
- Sau mỗi hành động, hệ thống tạo một `ProgressSnapshot` và so sánh với snapshot trước đó.
- Nếu sau một hành động mà:
  - Không có bằng chứng mới (`new_evidence_count == 0`).
  - Số requirement được thỏa mãn không đổi.
  - Snapshot hiện tại giống hệt snapshot trước đó.
- Tác tử kích hoạt cơ chế dừng do đình trệ tiến trình (`NO_PROGRESS`), ngăn chặn hoàn toàn việc thực thi lặp lại các tác vụ không sinh thêm giá trị.

### 4.3. Duplicate Action Prevention qua ActionFingerprint
- Mỗi hành động được băm thành một fingerprint duy nhất:
  `action_type|entity|requested_field|document_type|metadata_filter|strategy`
- Ví dụ: `RETRIEVE_EXACT|FIT4201|credits|course_outline|*|exact_match`
- Tác tử lưu trữ registry các fingerprint đã thực hiện trong phiên (`attempted_actions`).
- Nếu một hành động có fingerprint đã tồn tại được lên kế hoạch lần thứ hai, hệ thống chặn ngay trước khi thực thi, chuyển sang trạng thái dừng an toàn (`DUPLICATE_ACTION`).

---

## 5. PHÂN LOẠI BA VÙNG TRỐNG THÔNG TIN CHUẨN TẮC

| Loại khoảng trống | Nhận diện | Hành vi xử lý của Agent | Kịch bản ví dụ |
| :--- | :--- | :--- | :--- |
| **`MISSING_INTENT`** | Có thực thể trong câu nhưng không có trường thông tin hoặc động từ tra cứu cụ thể. | Dừng vòng lặp, gửi câu hỏi làm rõ các tiêu chí tra cứu cho người dùng. | *"FIT4201 với FIT4104 thì sao?"*, *"Môn FIT4113"*, *"FIT4201?"* |
| **`MISSING_ENTITY`** | Có trường thông tin yêu cầu nhưng câu hỏi và session memory đều không có mã môn học. | Đưa Agent vào trạng thái `NEEDS_USER_INPUT`, hỏi đích danh mã hoặc tên môn học. | *"Môn đó bao nhiêu tín chỉ?"*, *"Học phần này thi hình thức nào?"* |
| **`MISSING_DATA`** | Câu hỏi nhắm vào trường dữ liệu không công bố trong tài liệu chính quy. | Tạo đề xuất phương án thay thế gián tiếp, chờ người dùng phê duyệt. | *"FIT4201 tỷ lệ trượt bao nhiêu?"*, *"FIT4104 có khó không?"* |

---

## 6. THẨM ĐỊNH BẰNG CHỨNG HỌC VỤ & CHÍNH SÁCH CHI PHÍ

- **Nguồn tài liệu thực tế:** Toàn bộ dữ liệu được liên kết và thẩm định trực tiếp từ 8 file Word nguyên bản trong thư mục `data_raw/`:
  - 4 đề cương chi tiết: `FIT4104`, `FIT4113`, `FIT4117`, `FIT4201`.
  - 3 khung chương trình đào tạo K19: KHMT, CNTT, HTTT (bao quát đầy đủ 63 môn học).
  - 1 văn bản quy chế đào tạo đại học chính quy ĐNTU (`QuyetDinhChung.docx`).
- **Chính sách chi phí (Cost Policy):**
  - Số cuộc gọi DeepSeek cho Agent Core planning: **0**
  - Số cuộc gọi Gemini cho Agent Core planning: **0**
  - Số cuộc gọi External LLM: **0**
  - Vận hành 100% cục bộ, ổn định, bảo mật và phản hồi thời gian thực.

---

## 7. KẾT QUẢ ĐÁNH GIÁ TRÊN BỘ BENCHMARK 182 CASES

Bộ kiểm thử `eval/agent_core/` bao quát 16 nhóm kiểm định khắt khe (A đến P) đạt kết quả tuyệt đối:

```text
================================================================================
GOAL-DRIVEN AGENT CORE V1 EVALUATION SUITE
Total test cases: 182 across 16 groups (A - P)
Strict Cost Policy: 0 DeepSeek / Gemini calls for Agent Core planning
================================================================================

1. BREAKDOWN BY TEST GROUP:
Group    | Name                     | Passed   | Total  | Pass Rate 
-----------------------------------------------------------------
A        | CLEAR_GOAL               | 20       | 20     |   100.00%
B        | MISSING_INTENT           | 12       | 12     |   100.00%
C        | MISSING_ENTITY           | 12       | 12     |   100.00%
D        | MISSING_DATA             | 14       | 14     |   100.00%
E        | UNKNOWN_ENTITY           | 12       | 12     |   100.00%
F        | ENTITY_CONFLICT          | 10       | 10     |   100.00%
G        | MULTI_FIELD              | 12       | 12     |   100.00%
H        | MULTI_ENTITY             | 12       | 12     |   100.00%
I        | PARTIAL_EVIDENCE         | 10       | 10     |   100.00%
J        | NO_PROGRESS              | 8        | 8      |   100.00%
K        | DUPLICATE_ACTION         | 8        | 8      |   100.00%
L        | APPROVED_ALTERNATIVE     | 10       | 10     |   100.00%
M        | REJECTED_ALTERNATIVE     | 8        | 8      |   100.00%
N        | CLARIFICATION_RESUME     | 12       | 12     |   100.00%
O        | MALFORMED_QUERY          | 12       | 12     |   100.00%
P        | MULTI_INTENT             | 10       | 10     |   100.00%
-----------------------------------------------------------------
OVERALL  | ALL 16 GROUPS            | 182      | 182    |   100.00%

2. HARD GATES VERIFICATION:
   - Infinite Loop Count             : 0          (Required: == 0    ) -> PASSED
   - Duplicate Loop Count            : 0          (Required: == 0    ) -> PASSED
   - No-Progress Loop Count          : 0          (Required: == 0    ) -> PASSED
   - Planner Termination Rate        : 100.00%    (Required: == 100% ) -> PASSED
   - Unknown Entity Hallucination    : 0.00%      (Required: == 0%   ) -> PASSED
   - Unsafe Tools Triggered          : 0          (Required: == 0    ) -> PASSED
   - Authority Violations            : 0          (Required: == 0    ) -> PASSED
   - External Planning API Calls     : 0          (Required: == 0    ) -> PASSED

3. QUALITY METRICS:
   - Clear-Goal Completion Rate          : 100.00% (Target: >= 98%)
   - Missing-Slot Identification Accuracy: 100.00% (Target: >= 95%)
   - Proposal-on-Unavailable Rate        : 100.00% (Target: == 100%)
   - Clarification-Resume Success Rate   : 100.00% (Target: >= 95%)
   - Average Steps to Termination        : 1.91 (Target: <= 3.5)
   - Average Latency                     : 2.35 ms
```
