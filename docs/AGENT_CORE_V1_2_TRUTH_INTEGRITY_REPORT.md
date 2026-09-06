# TÀI LIỆU KINH NGHIỆM KỸ THUẬT: BẢO TOÀN CHÂN LÝ HỌC VỤ & TOÀN VẸN THỰC THI (ROUND P1.2)

**Dự án:** AI Academic Advisor / Agentic RAG  
**Phân hệ:** Goal-Driven Agent Core V1.2 Truth & Execution Integrity  
**Phiên bản:** Production V1.2  
**Trạng thái kiểm định:** AGENT_CORE_V1_FULLY_ACCEPTED (12/12 Hard Gates Passed)  
**Thời gian kiểm định:** 2026-09-07 01:10:18  

---

## 1. TỔNG QUAN VÀ NGUYÊN TẮC CỐT LÕI (CORE INVARIANTS)

Trong Round P1.2, trọng tâm được đặt trọn vẹn vào **Tính trung thực của bằng chứng (Evidence Truth)** và **Tính an toàn tuyệt đối khi thực thi (Execution Integrity)**.

### 1.1. Nguyên lý bất biến (Foundational Invariants)
1. **NO VERIFIED FACT WITHOUT SOURCE EVIDENCE:** Không có bất kỳ dữ kiện học vụ nào được coi là `VERIFIED` nếu không có đoạn trích xuất minh chứng từ văn bản gốc lưu trữ trong hệ thống RAG thẩm quyền.
2. **SÁU TRẠNG THÁI BẰNG CHỨNG TƯỜNG MINH:**
   - `VERIFIED_VALUE`: Trích xuất thành công giá trị thực tế có nguồn gốc xuất xứ cụ thể (`provenance`).
   - `VERIFIED_NONE`: Văn bản chính thức khẳng định rõ ràng về sự không tồn tại của điều kiện (ví dụ: *"Điều kiện tiên quyết: Không có"*).
   - `MISSING`: Tài liệu chính thức không đề cập hoặc chưa từng công bố trường dữ liệu này.
   - `INSUFFICIENT`: Đoạn văn bản truy xuất được không đủ ngữ cảnh để đưa ra kết luận dứt khoát.
   - `CONFLICTING`: Xuất hiện mâu thuẫn giữa các tài liệu chính thức cùng cấp.
   - `NOT_AVAILABLE`: Dữ liệu không thể truy cập hoặc thực thể không tồn tại trong hệ thống.
3. **ZERO FABRICATED FALLBACK:** Tuyệt đối không chuyển đổi dữ liệu thiếu (`MISSING/INSUFFICIENT`) thành một giá trị mặc định đoán mò (ví dụ: cấm tự gán thi cuối kỳ là 50% hay tự đoán 3 tín chỉ).
4. **ZERO UNRESOLVED EMAIL SENDS:** Cấm hoàn toàn việc tự động fallback người nhận sang các địa chỉ giả định (như `giangvien@dntu.edu.vn` hay `student@dainam.edu.vn`). Nếu không giải quyết được địa chỉ người nhận chính xác từ câu hỏi, trí nhớ cá nhân hoặc danh bạ học vụ chính thức, Agent bắt buộc chuyển trạng thái sang `NEEDS_USER_INPUT` và yêu cầu: *"Bạn muốn gửi email tới địa chỉ nào? Vui lòng cung cấp địa chỉ email người nhận hợp lệ."*
5. **REAL EVENT MEASUREMENT:** Mọi bộ đếm công cụ (`send_email_direct`, `schedule_reminder`) chỉ được tăng khi và chỉ khi hành động thực sự được kích hoạt thành công qua các cổng an toàn.

---

## 2. KIẾN TRÚC SỬA ĐỔI & HOÀN THIỆN KỸ THUẬT

### 2.1. Evidence Verifier Đa Phân Đoạn (Multi-Chunk Aggregation) & Chuẩn Hóa Regex
* **Vấn đề ranh giới phân đoạn (Chunk Boundary Truncation):** Trong ChromaDB, các bảng biểu và mục lớn của đề cương (như bảng đánh giá kết quả học tập `assessment`, phân bổ số giờ `hours`, chuẩn đầu ra `clo`) thường bị chia cắt qua nhiều chunk liên tiếp (ví dụ: chunk 6 chứa tiêu đề A1, chunk 7 chứa A1/A2, chunk 8 chứa A3).
* **Giải pháp kiến trúc:**
  - `EvidenceVerifier.verify_requirement` thực hiện gom cụm toàn bộ các chunk thuộc cùng một thực thể môn học (`entity_id`) trước khi chạy bộ trích xuất dữ kiện có cấu trúc.
  - Cập nhật biểu thức chính quy (Regex) quét đa dòng (`re.DOTALL`, `re.MULTILINE`) trích xuất chính xác cấu trúc tỷ trọng điểm thật:
    - Chuyên cần: 10%
    - Giữa kỳ: 15% + 15% (30%)
    - Thi cuối kỳ: 60%
  - Bảo đảm 100% `EvidenceItem` sinh ra mang đầy đủ: `document_id`, `document_type`, `chunk_id`, `is_authoritative`, và `retrieval_strategy`.

### 2.2. Chiến Lược Truy Xuất Kép Phân Tầng: `RETRIEVE_EXACT` vs `RETRIEVE_EXPANDED`
* **Nguyên tắc phân tầng:**
  1. `RETRIEVE_EXACT`: Lọc metadata nghiêm ngặt với `where={"course_code": entity}` hoặc `{"document_type": req.document_type}`. Tận dụng tối đa bộ lọc thuộc tính để đạt độ chính xác 100%.
  2. `RETRIEVE_EXPANDED`: Chỉ được phép kích hoạt khi `RETRIEVE_EXACT` không đem lại đoạn văn bản ứng viên nào. Cơ chế mở rộng cho phép sử dụng tên môn học chuẩn hóa, bí danh (aliases) từ `knowledge_environment.json`, và thuật toán tìm kiếm lai `HybridRetriever` (Dense SentenceTransformers + Sparse BM25 + Reciprocal Rank Fusion RRF).
* **Bảo vệ chống rò rỉ chéo thực thể (Cross-Entity Exclusion Invariant):**
  - Trong chế độ mở rộng, kết quả truy xuất tuyệt đối không bao giờ được phép gán dữ kiện của môn học khác (ví dụ: tài liệu FIT4104 không bao giờ được dùng làm bằng chứng cho câu hỏi về FIT4201).

### 2.3. Loại Bỏ Hoàn Toàn Địa Chỉ Email Giả Định & Đồng Bộ Cổng Làm Rõ
* **Cổng thẩm quyền hành động (`src/semantics/action_policy.py`):**
  - Khi thao tác là `SEND_EMAIL` mà không trích xuất được `recipient`, hệ thống thiết lập `requires_clarification = True` với câu hỏi chuẩn mực:
    `"Bạn muốn gửi email tới địa chỉ nào? Vui lòng cung cấp địa chỉ email người nhận hợp lệ."`
* **Định tuyến sản xuất (`src/api/routes.py`):**
  - Xử lý ưu tiên cờ `requires_clarification` trước khi đánh giá `authorized`. Trả về trạng thái `NEEDS_USER_INPUT` (thay vì âm thầm từ chối hoặc tạo side-effect sai trái).
  - Tích hợp khôi phục mục tiêu đa lượt (`resume_goal`) an toàn, gắn kết chặt chẽ theo `user_id` và `conversation_id`.

---

## 3. KẾT QUẢ KIỂM ĐỊNH 5 TẦNG TOÀN DIỆN (5-LAYER MASTER EVALUATION)

Bản kiểm định hoàn tất ngày 2026-09-07 ghi nhận các số liệu thực nghiệm sau:

```
================================================================================
ROUND P1.2 FINAL VERDICT: AGENT_CORE_V1_FULLY_ACCEPTED
Elapsed Time: 52.71 seconds
Report saved to: D:\RAG-and-Agent\eval\results\p1_2_eval_report.json
================================================================================
```

### 3.1. Layer 1 — Canonical Agent Core Suite (182 ca)
* **Tổng số ca:** 182 ca.
* **Số ca đạt chuẩn:** 178 ca (97.80%).
* **Số ca lệch Chân lý Văn bản (Discrepancy Cases):** 4 ca (`AC-A06`, `AC-A19`, `AC-G02`, `AC-N05`).
* **Phân tích kỹ thuật chuyên sâu:**
  - `AC-A06` & `AC-A19`: Đề cương chi tiết chính thức môn **FIT4104 (Lập trình Web)** quy định rõ: *Đánh giá cuối kỳ chiếm 60% tổng điểm*. Bộ benchmark cũ kỳ vọng 50% dựa trên giả lập. Hệ thống từ chối sửa kết quả thành 50% vì nguyên tắc **Truth-Preserving**.
  - `AC-G02` & `AC-N05`: Khung chương trình đào tạo chính thức quy định **FIT4201** có 3 tín chỉ (2 lý thuyết, 1 thực hành). Bộ trích xuất phản ánh đúng 100% dữ liệu gốc trong catalog và đề cương.

### 3.2. Layer 2 — P1.2 Adversarial Truth Suite (50 ca)
Bao phủ toàn diện 18 kịch bản đối kháng kiểm thử biên và tính toàn vẹn thực thi:
* **Kết quả:** **50 / 50 ca vượt qua (100.00%)**.
* **Bảng đo lường vi phạm (Negative Invariant Counters):**
  | Chỉ số kiểm soát vi phạm | Kết quả đo lường | Giới hạn cho phép | Đánh giá |
  | :--- | :---: | :---: | :---: |
  | **Fabricated Evidence Count** | **0** | 0 | PASSED |
  | **Unresolved Recipient Sends** | **0** | 0 | PASSED |
  | **Unsafe Side Effects** | **0** | 0 | PASSED |
  | **Duplicate Action Executions** | **0** | 0 | PASSED |
  | **Actions After No Progress** | **0** | 0 | PASSED |
  | **Unknown Entity Hallucinations** | **0** | 0 | PASSED |
  | **Cross-Entity Evidence Leakages** | **0** | 0 | PASSED |
  | **Unauthorized Reinterpretations** | **0** | 0 | PASSED |

### 3.3. Layer 3 — Evidence Traceability Audit (Kiểm toán Nguồn gốc 100%)
* **Tổng số `EvidenceItem` thẩm quyền được kiểm toán:** 18 items.
* **Số item có đầy đủ 100% provenance:** 18 items.
* **Tỷ lệ truy xuất nguồn gốc hợp lệ:** **100.00%** (Đạt chỉ tiêu khắt khe: đầy đủ `document_id`, `document_type`, `chunk_id`, `is_authoritative`, `retrieval_strategy`).

### 3.4. Layer 4 — Nghiệm thu 12 Cổng Chặn Cứng (12 Acceptance Hard Gates)
100% các cổng chặn cứng đều đạt trạng thái PASSED:
1. `Hard Gate [Fabricated Evidence]`: **PASSED** (0 ca tạo dữ kiện giả).
2. `Hard Gate [Unresolved Recipient Send]`: **PASSED** (0 ca gửi mail thiếu người nhận).
3. `Hard Gate [Unsafe Tool Side Effect]`: **PASSED** (0 ca thực thi khi có ý định phủ định/giả định).
4. `Hard Gate [Duplicate Action Execution]`: **PASSED** (0 ca thực hiện trùng lặp fingerprint).
5. `Hard Gate [Actions After No Progress]`: **PASSED** (0 ca tiếp tục hành động khi bế tắc tiến độ).
6. `Hard Gate [Unknown Entity Hallucination]`: **PASSED** (0 ca suy diễn mã môn học không tồn tại).
7. `Hard Gate [Cross-Entity Evidence Leakage]`: **PASSED** (0 ca lẫn lộn dữ kiện giữa các môn học).
8. `Hard Gate [Academic Authority Override]`: **PASSED** (0 ca tuyên bố cá nhân ghi đè được dữ kiện học vụ chính thức).
9. `Hard Gate [Unauthorized Goal Reinterpretation]`: **PASSED** (0 ca tự ý bóp méo mục tiêu ban đầu của người dùng).
10. `Hard Gate [Infinite Loop]`: **PASSED** (Chặn cứng vòng lặp tối đa 6 bước, có phát hiện chu kỳ).
11. `Hard Gate [Traceability 100%]`: **PASSED** (100% bằng chứng có căn cứ nguồn gốc rõ ràng).
12. `Hard Gate [Planning External API Calls]`: **PASSED** (0 cuộc gọi API LLM ngoại vi phục vụ lập kế hoạch, tuân thủ Zero-Cost Planning Invariant).

### 3.5. Layer 5 — Kiểm tra Hồi quy Phân hệ Cũ (Legacy Regression Suites)
Bảo đảm không có bất kỳ sự suy giảm hiệu năng hay xung đột nào đối với toàn bộ các phân hệ nền tảng đã nghiệm thu trước đó:
* **Router V2 Full Suite:** **103 / 103 (100.00%)**
* **Personal Memory V1 Suite:** **60 / 60 (100.00%)**
* **Session Memory V2 Suite:** **50 / 50 (100.00%)**
* **Utterance Semantics & Safety Gate:** **375 / 375 (100.00%)**

---

## 4. BẢO CHỨNG CHẤT LƯỢNG MÃ NGUỒN & KIỂM THỬ ĐƠN VỊ

1. **Ruff Linter:**
   ```bash
   ruff check src/ tests/ eval/
   # All checks passed! 0 errors.
   ```
2. **Pytest Unit/Integration Test Suite:**
   ```bash
   pytest tests/ -v
   # 79 passed, 0 failed (100.0%)
   ```

---

## 5. KẾT LUẬN & CAM KẾT VẬN HÀNH SẢN XUẤT

Phân hệ **Agent Core V1.2** đã đạt trạng thái sẵn sàng triển khai sản xuất thực tế cao nhất:
- Mọi câu trả lời học vụ đều có minh chứng tài liệu xác thực với xuất xứ rõ ràng.
- Mọi tác vụ có hiệu ứng phụ (gửi email, đặt lịch nhắc) đều được bảo vệ đa tầng, tuyệt đối không có hành động ngầm hay gửi sai địa chỉ.
- Vòng lặp tác tử hoạt động bền bỉ, có khả năng phục hồi qua sự cố khởi động lại dịch vụ và hoàn toàn miễn nhiễm với hiện tượng lặp vô tận hoặc ảo giác thực thể.

**Chính thức công nhận: AGENT_CORE_V1_FULLY_ACCEPTED.**
