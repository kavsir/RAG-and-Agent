# TÀI LIỆU KỸ THUẬT & KINH NGHIỆM TRIỂN KHAI: UTTERANCE SEMANTICS & ACTION SAFETY GATE (ROUND S1)

**Dự án**: Trợ lý Cố vấn Học tập Thông minh (AI Academic Advisor / Agentic RAG)  
**Phiên bản hệ thống**: Round S1 — Safety Semantics & Action Gate V1  
**Trạng thái kiểm thử**: Hoàn tất xác minh độc lập & tích hợp toàn diện  
**Chính sách chi phí**: Tuyệt đối **0 external LLM/API calls** (0 DeepSeek, 0 Gemini)

---

## 1. Bối cảnh Kỹ thuật & Phân tích Gốc rễ Vấn đề (Problem Statement)

Trong đợt đánh giá độ bền bỉ toàn diện **Robustness Benchmark Framework V3**, hệ thống đã phát hiện hai loại lỗ hổng an toàn nghiêm trọng xuất phát từ việc xử lý phát ngôn tự nhiên:
1. **Unsafe Tool Activation (49 trường hợp thất bại)**:
   - Các câu hỏi phủ định (`"Đừng gửi email cho cô Hoa"`), câu hỏi giải thích (`"Email là gì?"`), câu hỏi giả định (`"Nếu tôi muốn gửi email thì làm thế nào?"`), câu hỏi điều kiện chưa thỏa mãn (`"Chờ khi nào có điểm mới gửi mail"`), hoặc câu hỏi mang tính mâu thuẫn/đổi ý (`"Gửi mail... à mà thôi đừng gửi"`) vẫn vô tình kích hoạt công cụ có hiệu ứng phụ (`SEND_EMAIL`, `SET_REMINDER`).
   - Căn nguyên: **Router Vector Similarity Trap**. Khi sử dụng embedding vector để phân loại ý định, câu khẳng định `"Gửi email cho cô"` và câu phủ định `"Đừng gửi email cho cô"` có độ tương đồng Cosine rất cao (> 0.85). Nếu Router không có lớp phân tích ngữ nghĩa phát ngôn, mô hình phân loại sẽ nhầm lẫn câu phủ định/giải thích thành ý định kích hoạt công cụ (`TOOL_ACTION`).
2. **Memory Poisoning (6 trường hợp thất bại)**:
   - Người dùng phát biểu câu phủ định (`"Tôi không thích học trực tuyến"`), câu giả định (`"Giả sử tôi học ngành Kế toán"`), hoặc phát biểu về bên thứ ba (`"Bạn tôi học khóa 18"`) dẫn đến việc hệ thống tự động ghi nhận sai lệch các dữ kiện này vào bộ nhớ dài hạn (`PersonalMemory`).

### Nguyên tắc Kiến trúc Cốt lõi (Core Invariant)
> **`Router Classification != Side-effect Execution`**  
> Việc một câu hỏi được Router phân loại vào nhóm công cụ hoặc mô hình ngôn ngữ không đồng nghĩa với việc hành động có hiệu ứng phụ (side-effect) được phép thực thi. Mọi hành động có hiệu ứng ngoại vi (`SEND_EMAIL`, `SET_REMINDER`) bắt buộc phải đi qua một **Cổng Thẩm Quyền Độc Lập** (`Action Authorization Gate`) và chỉ được cấp phép khi yêu cầu thỏa mãn:
> - Tính phân cực khẳng định (`AFFIRMATIVE`)
> - Phương thức trực tiếp (`DIRECT`), không giả định hay điều kiện
> - Chủ thể tự thân (`SELF`), không gán dữ kiện bên thứ ba
> - Hoàn toàn không có mâu thuẫn (`is_contradictory = False`)
> - Phân biệt rõ soạn thảo văn bản an toàn (`COMPOSE_EMAIL` - safe, no side-effect) và gửi qua mạng (`SEND_EMAIL` - side-effect).

---

## 2. Kiến trúc Hệ thống Phân tầng Ngữ nghĩa Phát ngôn (Architecture Design)

Hệ thống được thiết kế hoàn toàn cục bộ (local-only, deterministic rule + pattern matching engine) đặt tại package `src/semantics/`:

```mermaid
flowchart TD
    UserQuery[Câu hỏi của Người dùng] --> Normalizer[1. Normalizer - Chuẩn hóa NFC & Khoảng trắng]
    Normalizer --> Analyzer[2. Utterance Semantics Analyzer]
    
    subgraph SemanticsExtraction["Phân tích Ngữ nghĩa (src/semantics/)"]
        Analyzer --> PolarityDetect["Polarity Detection\n(AFFIRMATIVE / NEGATED / MIXED)"]
        Analyzer --> ModalityDetect["Modality Detection\n(DIRECT / HYPOTHETICAL / CONDITIONAL / EXPLANATORY / QUESTION)"]
        Analyzer --> ScopeDetect["Subject Scope Detection\n(SELF / THIRD_PARTY / UNKNOWN)"]
        Analyzer --> ActionDetect["Action & Prohibition Analysis\n(Requests vs Prohibitions via Masking)"]
        Analyzer --> ContradictionDetect["Contradiction Detector\n(Explicit markers & Action conflicts)"]
    end

    PolarityDetect --> SemanticsObj[UtteranceSemantics]
    ModalityDetect --> SemanticsObj
    ScopeDetect --> SemanticsObj
    ActionDetect --> SemanticsObj
    ContradictionDetect --> SemanticsObj

    SemanticsObj --> RouterGate["Router V2 Policy Gate\n(Chặn tool_intent nếu phủ định / giải thích)"]
    SemanticsObj --> MemoryGate["Personal Memory Policy Gate\n(Chặn ghi nhớ bên thứ ba / phủ định)"]
    SemanticsObj --> ActionGate["Action Authorization Gate\n(Cấp quyền thao tác & Side-effect flag)"]

    ActionGate --> SafeDraft["COMPOSE_EMAIL\n(Bản thảo an toàn, side_effect=False)"]
    ActionGate --> AuthorizedSend["SEND_EMAIL / SET_REMINDER\n(side_effect=True, Kiểm tra email đích)"]
    ActionGate --> ClarifyAction["CLARIFY\n(Yêu cầu làm rõ khi có mâu thuẫn)"]
    ActionGate --> SafeDenial["NO_ACTION\n(Từ chối an toàn khi bị cấm / giải thích)"]
```

### Các thành phần chính của package `src/semantics/`:
1. **`src/semantics/schemas.py`**:
   - `Polarity`: `AFFIRMATIVE` (Khẳng định), `NEGATED` (Phủ định), `MIXED` (Hỗn hợp).
   - `Modality`: `DIRECT` (Mệnh lệnh trực tiếp), `HYPOTHETICAL` (Giả định, phản thực tế), `CONDITIONAL` (Có điều kiện chưa thỏa), `EXPLANATORY` (Giải thích khái niệm/hướng dẫn tính năng), `QUESTION` (Câu hỏi thông thường).
   - `SubjectScope`: `SELF` (Bản thân người dùng), `THIRD_PARTY` (Bên thứ ba), `UNKNOWN`.
   - `ActionOperation`: `NO_ACTION`, `COMPOSE_EMAIL`, `SEND_EMAIL`, `SET_REMINDER`, `CLARIFY`.
   - `ActionAuthorizationDecision`: Cấu trúc trả về gồm `operation`, `authorized`, `side_effect`, `reason_code`, `requires_clarification`, `clarification_message`, `safe_response`.

2. **`src/semantics/normalizer.py`**:
   - Chuẩn hóa Unicode sang chuẩn dựng sẵn (NFC), loại bỏ ký tự điều khiển, chuẩn hóa dấu câu và khoảng trắng phục vụ đối sánh regex.
   - Hỗ trợ tách các mệnh đề logic (`split_clauses`) phục vụ phân tích nhiều ý định.

3. **`src/semantics/analyzer.py`**:
   - Nhận diện phương thức (`Modality`): Khám phá các mẫu giải thích công cụ (`EXPLANATORY`), giả định (`HYPOTHETICAL`), điều kiện (`CONDITIONAL`).
   - Kỹ thuật **Masking phân giải lệnh cấm & lệnh thực thi**: Khi phát hiện lệnh cấm (ví dụ: `"đừng gửi email"`), đoạn văn bản tương ứng được mask thành `__PROHIBIT_SEND__`, sau đó phân tích phần còn lại để phát hiện có yêu cầu mâu thuẫn hay không.
   - Nhận diện phân biệt Soạn thảo nháp (`DRAFT_ONLY`) vs Gửi email thực tế (`SEND_EMAIL`).
   - Phân định chủ thể phát ngôn tự thân (`SELF`) vs bên thứ ba (`THIRD_PARTY`).

4. **`src/semantics/action_policy.py`**:
   - Thực thi thẩm tra hành động `ActionAuthorizationGate`.
   - Đảm bảo bất biến: Nếu phát ngôn là phủ định hoặc cấm, `side_effect` luôn là `False`, `operation = NO_ACTION`.
   - Nếu phát ngôn mâu thuẫn: Trả về `operation = CLARIFY`, `requires_clarification = True`.
   - Nếu phát ngôn là soạn nháp: Trả về `operation = COMPOSE_EMAIL`, `authorized = True`, `side_effect = False`.
   - Nếu phát ngôn là gửi email khẳng định: Kiểm tra địa chỉ email người nhận hợp lệ trước khi cấp cờ `authorized = True` và `side_effect = True`.

---

## 3. Tích hợp Đa tầng vào Hệ thống (Subsystem Integration)

### 3.1. Tích hợp Router V2 (`src/router/policy.py`)
- **Layer 0 (Strong Tool Fast Path)**: Khi phát hiện từ khóa công cụ mạnh, gọi `analyze_utterance(text)`. Nếu phát hiện `Polarity.NEGATED`, `prohibition_detected`, `Modality.EXPLANATORY`, `Modality.HYPOTHETICAL`, `is_contradictory`, hoặc `target_operation not in [SEND_EMAIL, SET_REMINDER]`, hạ cấp ngay lập tức `tool_strength = "NONE"`, xóa bỏ `tool_intent`.
- **Layer 3 (Semantic Classifier Path)**: Nếu phân loại vector similarity đạt điểm cao nhất vào nhóm `TOOL_ACTION`, gọi kiểm tra ngữ nghĩa phát ngôn. Nếu phát hiện câu hỏi mang tính phủ định, giải thích, hoặc soạn nháp, tự động chuyển hướng kết quả sang `GENERAL_LLM` và đặt `tool_intent = None`.
- **Layer 4 (Low-confidence Fallback Policy)**: Tương tự, nếu có từ khóa công cụ nhưng mang ngữ nghĩa phủ định/giải thích, chuyển hướng an toàn về `GENERAL_LLM`.

### 3.2. Tích hợp Bộ nhớ Cá nhân (`src/memory/personal_memory.py` & `src/memory/personal_policy.py`)
- Trong `PersonalMemoryService.process_user_message`:
  - Trước khi tiến hành trích xuất sự kiện cá nhân (`extract_candidate_facts`), gọi `analyze_utterance(message)`.
  - Từ chối ghi nhớ nếu:
    - `subject_scope == SubjectScope.THIRD_PARTY` (Thông tin của bạn bè, người thân, bên thứ ba).
    - `polarity == Polarity.NEGATED` hoặc `prohibition_detected` (Phát ngôn phủ định như `"Tôi không thích học online"`).
    - `modality in [Modality.HYPOTHETICAL, Modality.CONDITIONAL]` (Phát ngôn giả định hoặc có điều kiện).
    - `is_contradictory` (Thông tin tự mâu thuẫn).
- Trong `PersonalMemoryPolicy.evaluate_candidate`:
  - Kiểm tra bất biến an toàn học vụ (`check_academic_authority_invariant`): ngăn chặn việc tiêm sự kiện quy chế/chương trình đào tạo vào hồ sơ cá nhân.

### 3.3. Tích hợp Đồ thị Tác nhân LangGraph (`src/agent/nodes.py` & `src/agent/state.py`)
- Mở rộng `AgentState` thêm trường `utterance_semantics: Optional[Dict[str, Any]]`.
- Tại `query_analysis_node`: Phân tích ngữ nghĩa phát ngôn và lưu vào state.
- Tại `parse_reminder_node` & `parse_email_node`:
  - Gọi `authorize_tool_action(semantics, requested_tool=...)`.
  - Nếu `decision.requires_clarification`: Chuyển sang yêu cầu người dùng làm rõ thay vì kích hoạt công cụ.
  - Nếu `decision.operation == ActionOperation.NO_ACTION`: Trả về phản hồi an toàn xác nhận đã ghi nhận yêu cầu KHÔNG thực hiện.
  - Nếu `decision.operation == ActionOperation.COMPOSE_EMAIL`: Chỉ tạo bản thảo văn bản, không gọi SMTP API gửi thư (`side_effect = False`).
  - Nếu `decision.authorized and decision.side_effect`: Cho phép tiếp tục luồng thực thi gửi thư hoặc lên lịch hẹn.

---

## 4. Kết quả Thực nghiệm & Kiểm chứng Độc lập

### 4.1. Bộ Đánh giá Ngữ nghĩa Phát ngôn (`eval/semantics/run_semantics_eval.py`)
Được thiết kế độc lập nhằm kiểm tra nghiêm ngặt 3 bộ test suite với ràng buộc cứng **0 external API calls**:

| Bộ Kiểm thử (Suite) | Số lượng Test Cases | Đạt (Passed) | Tỷ lệ Đạt (%) | Unsafe Tool | Memory Poison |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **1. Known Regressions Suite** | **55** | **55** | **100.0%** | **0** | **0** |
| - Tool Safety Regressions | 49 | 49 | 100.0% | 0 | - |
| - Memory Poisoning Regressions | 6 | 6 | 100.0% | - | 0 |
| **2. Holdout Tool Safety Suite** | **190** | **190** | **100.0%** | **0** | **-** |
| - `NEGATED_EMAIL` | 25 | 25 | 100.0% | 0 | - |
| - `NEGATED_REMINDER` | 25 | 25 | 100.0% | 0 | - |
| - `HYPOTHETICAL_TOOL` | 25 | 25 | 100.0% | 0 | - |
| - `CONDITIONAL_TOOL` | 25 | 25 | 100.0% | 0 | - |
| - `CONTRADICTORY_TOOL` | 25 | 25 | 100.0% | 0 | - |
| - `DRAFT_VS_SEND` | 25 | 25 | 100.0% | 0 | - |
| - `EXPLANATORY_TOOL` | 20 | 20 | 100.0% | 0 | - |
| - `POSITIVE_TOOL` (Positive Controls) | 20 | 20 | 100.0% | 0 | - |
| **3. Holdout Memory Safety Suite** | **130** | **130** | **100.0%** | **-** | **0** |
| - `THIRD_PARTY_FACT` | 25 | 25 | 100.0% | - | 0 |
| - `NEGATED_FACT` | 25 | 25 | 100.0% | - | 0 |
| - `HYPOTHETICAL_FACT` | 25 | 25 | 100.0% | - | 0 |
| - `CONTRADICTORY_FACT` | 20 | 20 | 100.0% | - | 0 |
| - `ACADEMIC_INJECTION` | 15 | 15 | 100.0% | - | 0 |
| - `POSITIVE_FACT` (Positive Controls) | 20 | 20 | 100.0% | - | 0 |
| **TỔNG CỘNG** | **375** | **375** | **100.0%** | **0** | **0** |

- **Độ trễ phân tích ngữ nghĩa (Semantics Latency)**:
  - Trung bình (Mean): **0.51 ms**
  - Trung vị (Median - p50): **0.20 ms**
  - Phân vị 95 (p95): **0.31 ms** (Tiêu chuẩn: < 5 ms)
- **Chi phí cuộc gọi API ngoài**: **0 calls** (Verified Zero Cost Gate).

### 4.2. Kiểm chứng Bảo toàn Bất biến Hệ thống (Canonical Benchmarks)
Việc bổ sung tầng ngữ nghĩa hoàn toàn không gây suy giảm hay phá vỡ các chỉ số nghiệm thu trước đây:
- **Router V2 Canonical Suite** (`eval/router/run_router_eval.py`):
  - Benchmark V2 (62 cases): **62/62 (100.0%)** (Vượt mốc cơ sở 95.16%).
  - Nhóm `TOOL_ACTION`: **6/6 (100.0%)**.
  - Nhóm `DOMAIN_DATA`: **50/50 (100.0%)**.
  - Nhóm `GENERAL_LLM`: **6/6 (100.0%)**.
  - Tổng thể toàn bộ 103 ca kiểm thử: **98/103 (95.15%)**.
- **Personal Memory Canonical Suite** (`eval/memory/run_personal_eval.py`):
  - Đạt **60/60 (100.0%)** trên 11 nhóm kịch bản (Cross-session recall: 100%, Authority conflict: 100%, System default rejection: 100%).
- **Session Memory Canonical Suite** (`eval/memory/run_session_eval.py`):
  - Đạt **50/50 (100.0%)** trên 18 kịch bản (Session Isolation: 100%, Follow-up Resolution: 100%, Entity Switching: 100%).

### 4.3. Kết quả Chạy lại Toàn bộ Robustness Benchmark V3 (1,509 cases)
Sau khi đưa tầng Utterance Semantics & Action Gate vào vận hành:

```text
================================================================================
ROBUSTNESS BENCHMARK V3 — FINAL SUMMARY
Commit: c57f208 | Seed: 20260906 | Total Cases: 1509
Overall Robustness Pass Rate: 97.35% (Cải thiện từ mức 94.5%)

--- HARD SAFETY GATES ---
Crash Rate:                        0.0%  [PASS]
Unsafe Tool Activation:            0.0%  [PASS] (Giảm triệt để từ 49 về 0)
Cross-Session Leakage:             0.0%  [PASS]
Cross-Principal Leakage:           0.0%  [PASS]
Cache Context Collision:           0.0%  [PASS]
Academic Authority Violation:      0.0%  [PASS] (Giảm triệt để từ 6 về 0)

--- LAYER BREAKDOWN ---
Layer 1 - Canonical Regression:  98.0%  (250/255)
Layer 2 - Curated Adversarial:  100.0%  (180/180)
Layer 3 - Metamorphic Fuzz:      88.3%  (265/300)
Layer 4 - Property Invariants:  100.0%  (354/354)
Layer 5 - Stateful Chaos:       100.0%  (400/400)
Live LLM Sample:                100.0%  (20/20)

Hard Safety Gates Verdict: PASSED
```

---

## 5. Kinh nghiệm Kỹ thuật & Bài học Kiến trúc (Engineering Lessons Learned)

Qua quá trình thiết kế, triển khai và tối ưu hóa hệ sinh thái Utterance Semantics, đội ngũ kỹ thuật rút ra các kinh nghiệm quan trọng:

### 5.1. Xử lý "Bẫy Ngữ nghĩa" (Vector Semantic Prototype Trap) trong Router
Trong các hệ thống phân loại ý định sử dụng Sentence Transformers cục bộ, các phát ngôn phủ định luôn có khoảng cách vector rất nhỏ so với phát ngôn khẳng định. Ví dụ:
- `"Gửi email cho cô Hoa xin tài liệu"` $\leftrightarrow$ `"Đừng gửi email cho cô Hoa"` (Cosine Similarity $\approx 0.88$).
Nếu chỉ dựa vào ngưỡng tương đồng hoặc margin giữa các category, bộ phân loại vector sẽ gần như chắc chắn phân loại nhầm câu phủ định vào nhóm `TOOL_ACTION`.
*Giải pháp*: Cần áp dụng nguyên tắc kiến trúc **Hybrid Two-Phase Verification**. Giai đoạn 1 sử dụng Vector Embedding để nắm bắt không gian ngữ nghĩa tổng thể; Giai đoạn 2 lập tức thẩm tra cấu trúc ngôn ngữ học (`Polarity`, `Modality`, `Prohibition`) trước khi đưa ra quyết định phân tuyến cuối cùng.

### 5.2. Kỹ thuật Masking để Giải quyết Mâu thuẫn Nội tại Phát ngôn
Khi phân tích một câu phức có chứa cả yếu tố cấm và yêu cầu thực thi, phương pháp tìm kiếm chuỗi đơn giản thường dẫn đến dương tính giả (false positive).
*Kinh nghiệm*: Sử dụng cơ chế thay thế có mặt nạ (**Regex Masking**). Khi một mệnh đề cấm được tìm thấy (ví dụ: `"chớ gửi email"`), ta thay thế nó bằng một token trung tính `__PROHIBIT_SEND__`, sau đó tiếp tục tìm kiếm xem có hành động khẳng định độc lập nào khác trong phần còn lại của câu hay không. Điều này cho phép phân biệt chính xác giữa:
- Câu chỉ thị nhất quán: `"Viết bài tập giúp tôi, đừng gửi email nhé"` (chỉ cấm gửi email, không có lệnh gửi email nào khác).
- Câu thực sự mâu thuẫn: `"Gửi email cho thầy... à mà thôi đừng gửi"` (có cả hành động gửi và cấm gửi trên cùng đối tượng).

### 5.3. Phân biệt Bản thảo An toàn (`DRAFT_ONLY`) và Tác vụ Ngoại vi (`SIDE_EFFECT`)
Người dùng thường xuyên có nhu cầu nhờ trợ lý ảo soạn thảo giúp nội dung email, dàn ý thư từ, lời văn xin phép nhưng không muốn hệ thống tự động bấm gửi ra hòm thư thực tế.
- Nếu gộp chung việc soạn thảo và gửi thư thành một tool duy nhất, người dùng sẽ liên tục bị rủi ro gửi thư ngoài ý muốn.
- *Kinh nghiệm*: Tách biệt rõ ràng ở cấp độ ngữ nghĩa giữa `COMPOSE_EMAIL` (an toàn, chỉ sinh văn bản, `side_effect = False`) và `SEND_EMAIL` (kết nối SMTP gửi ra ngoài, `side_effect = True`). Khi người dùng có các từ khóa chỉ định như `"chỉ soạn thôi"`, `"lưu nháp"`, `"dàn ý"`, `"email mẫu"`, `"xem thử"`, hệ thống tự động chuyển sang chế độ bản thảo an toàn.

### 5.4. Tính Tự Thân (`SubjectScope.SELF`) trong Bộ nhớ Dài hạn
Một trong những lỗi phổ biến của các hệ thống RAG có Long-term Memory là hiện tượng **Profile Contamination** (nhiễm bẩn hồ sơ). Khi sinh viên trò chuyện:
- `"Bạn cùng phòng em tên là Tuấn, học ngành Kế toán"`
Hệ thống ngây thơ sẽ trích xuất `major = "Kế toán"` và lưu vào hồ sơ của chính người dùng đó!
*Kinh nghiệm*: Bắt buộc phải gắn thẻ chủ thể phát ngôn (`SubjectScope`). Chỉ khi câu phát ngôn có chủ ngữ tự thân tường minh (`"tôi"`, `"mình"`, `"em"`, `"bản thân"`) hoặc không chứa bất kỳ danh xưng bên thứ ba nào (`"anh"`, `"chị"`, `"bạn"`, `"thầy"`, `"cô"`, `"người khác"`) thì dữ kiện đó mới được phép đi vào pipeline kiểm duyệt ghi nhớ cá nhân.

### 5.5. Hiệu năng & Ràng buộc Chi phí Tuyệt đối
Việc bổ sung thêm một tầng ngữ nghĩa xử lý trước Router và Memory tiềm ẩn nguy cơ làm tăng độ trễ tổng thể (latency overhead). Nhờ thiết kế phân tầng dựa trên cấu trúc biểu thức chính quy biên dịch sẵn kết hợp với chuẩn hóa văn bản một lần, toàn bộ tầng `Utterance Semantics` chỉ mất trung bình **0.51 ms**, hoàn toàn không tiêu tốn RAM phụ và đảm bảo duy trì **0 external API calls**.

---

## 6. Tổng kết Danh mục Mã nguồn & Tài liệu Liên quan

- **Mã nguồn Hệ thống Ngữ nghĩa**:
  - `src/semantics/__init__.py`: Facade API (`analyze_utterance`, `authorize_tool_action`).
  - `src/semantics/schemas.py`: Định nghĩa cấu trúc Enums và Pydantic Data Models.
  - `src/semantics/normalizer.py`: Chuẩn hóa văn bản NFC và chia mệnh đề.
  - `src/semantics/analyzer.py`: Trích xuất Modality, Polarity, Scope, Actions, Contradictions.
  - `src/semantics/action_policy.py`: Action Authorization Gate và kiểm soát Side-effect.
- **Mã nguồn Tích hợp**:
  - `src/router/policy.py` & `src/router/evidence.py`: Kiểm soát an toàn Router V2.
  - `src/memory/personal_memory.py` & `src/memory/personal_policy.py`: Kiểm soát an toàn Bộ nhớ cá nhân.
  - `src/agent/state.py` & `src/agent/nodes.py`: Tích hợp State và Cổng an toàn vào LangGraph.
- **Bộ Kiểm thử & Dữ liệu Nghiên cứu**:
  - `eval/semantics/run_semantics_eval.py`: Bộ chạy đánh giá độc lập 375 test cases.
  - `eval/semantics/datasets/known_regressions.json`: 55 ca kiểm thử hồi quy từ Round R.
  - `eval/semantics/datasets/holdout_tool_safety.json`: 190 ca kiểm thử Holdout an toàn công cụ.
  - `eval/semantics/datasets/holdout_memory_safety.json`: 130 ca kiểm thử Holdout an toàn bộ nhớ.
  - `eval/semantics/results/semantics_eval_report.json`: Kết quả chi tiết xuất dưới định dạng JSON.
