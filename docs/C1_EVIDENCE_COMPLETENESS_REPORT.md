# BÁO CÁO NGHIỆM THU ROUND C1 — EVIDENCE COMPLETENESS & MULTI-VALUE EXTRACTION

**Repository:** `https://github.com/kavsir/RAG-and-Agent.git`  
**Ngày thực hiện:** 08/09/2026  
**Trạng thái quyết định:** `EVIDENCE_COMPLETENESS_ACCEPTED`  
**Tỷ lệ đạt chuẩn:** **100.0% (6/6 C1 Benchmark Cases, 84/84 Unit/Integration Tests, 182/182 Canonical Cases, 7/7 Hard Gates, 0 Ruff Violations)**  

---

## 1. NGUYÊN TẮC CỐT LÕI & MỤC TIÊU VÒNG C1

Sau khi Agent Core V1 đạt chứng nhận hoàn tất (P1.2.2 Certification), kiểm thử thực tế từ người dùng phát hiện 3 khiếm khuyết nghiêm trọng liên quan đến **tính trọn vẹn của bằng chứng (Evidence Completeness)**:
1. **Case A**: Truy vấn giảng viên môn Hệ thống nhúng (FIT4201) trả về cụm từ rác: `"FIT4201 (giảng viên): Thông tin giảng viên học"`.
2. **Case B**: Truy vấn chuẩn đầu ra CLO của môn FIT4113 chỉ trả về 3 CLO đầu tiên (`CLO 1`, `CLO 2`, `CLO 3`), trong khi đề cương môn học công bố tổng cộng 8 CLO phân bổ trên các chunk khác nhau.
3. **Case C**: Truy vấn điều kiện xét tốt nghiệp của trường chỉ trích xuất được 1 điều kiện chung chung từ phần mở đầu, bỏ sót toàn bộ 8 điều kiện cụ thể (điểm a đến điểm h, Khoản 2 Điều 33 Quy chế đào tạo).

### Bất biến cốt lõi (Core Invariant):
$$\text{CÂU TRẢ LỜI ĐÚNG} = \text{TÍNH TRUNG THỰC (TRUTH)} + \text{TÍNH TRỌN VẸN (COMPLETENESS)}$$

- **Không cắt xén ngầm (Zero Silent Truncation)**: Một trường đa giá trị đã được xác thực không bao giờ được phép trả về chỉ phần tử đầu tiên hoặc một tập con tùy tiện.
- **Không đoán mò / Không bịa đặt**: Mọi giá trị trích xuất phải có xuất xứ nguyên văn từ tài liệu chính thống.
- **Tập hợp liên chunk (Cross-Chunk Evidence Aggregation)**: Thu thập đầy đủ dữ liệu khi bằng chứng trải dài qua ranh giới phân mảnh chunk.
- **UX đàm thoại tự nhiên**: Trả lời mạch lạc, thân thiện, loại bỏ hoàn toàn các tiền tố markdown thô (`- **CODE (trường)**:`).

---

## 2. NGUYÊN NHÂN GỐC RỄ (ROOT CAUSE ANALYSIS)

### Case A: Trích xuất giảng viên FIT4201 bị sai
- **Nguyên nhân**: Trong `verifier.py`, regex trích xuất giảng viên sử dụng cờ `re.IGNORECASE` kết hợp mẫu `[A-ZÀ-Ỵ][a-zà-ỵ]+`, dẫn đến việc chuỗi chữ thường trong câu *"Thông tin giảng viên học phần..."* bị khớp nhầm chữ *"học"*, biến thành giảng viên *"Thông tin giảng viên học"*. Đồng thời, hệ thống thiếu danh sách chặn (blacklist) các thuật ngữ học vụ chung và chưa hỗ trợ tổng hợp đồng thời nhiều giảng viên phụ trách / giảng dạy.
- **Khắc phục**: 
  - Bỏ `re.IGNORECASE` đối với tên riêng tiếng Việt, chuẩn hóa quy tắc viết hoa: `[A-ZÀ-ỴĐ][a-zà-ỵđ]+(?:\s+[A-ZÀ-ỴĐ][a-zà-ỵđ]+){1,4}`.
  - Thiết lập danh sách lọc nghiêm ngặt `BLACKLIST_WORDS` gồm 28 thuật ngữ cấm (thông tin, học phần, cán bộ, đề cương, môn học, chức danh, học vị...).
  - Bổ sung bộ nhận diện chức danh học thuật (`TS.`, `ThS.`, `PGS.`, `GS.`) theo cả hai dạng: *Học vị đứng trước tên* và *Tên kèm học vị đứng sau*.
  - Trích xuất đầy đủ tất cả giảng viên: `TS. Trần Đăng Công, ThS. Nguyễn Văn Nhân`.

### Case B: CLO môn FIT4113 bị cắt còn 3
- **Nguyên nhân**: Dòng mã `311` trong `verifier.py` cố định cắt mảng kết quả: `"; ".join(valid_clos[:3])`. Ngoài ra, tài liệu `FIT4113` có CLO trải trên 2 chunk (Chunk 2 chứa CLO 1–6, Chunk 3 chứa CLO 7–8); cơ chế trích xuất trước đây dừng ngay ở chunk đầu tiên tìm thấy dữ liệu mà không tổng hợp qua các chunk tiếp theo.
- **Khắc phục**:
  - Gỡ bỏ hoàn toàn thao tác cắt lát `[:3]`.
  - Triển khai cơ chế trích xuất đa chunk trong `verify_requirement`: quét qua toàn bộ các chunk được lọc theo mã môn, thu thập toàn bộ CLO, loại bỏ trùng lặp và sắp xếp thứ tự số học tăng dần từ `CLO 1` đến `CLO 8`.
  - Ghi nhận đầy đủ nguồn gốc xuất xứ đa chunk vào `metadata["supporting_chunks"]`.

### Case C: Điều kiện xét tốt nghiệp bị thiếu mệnh đề
- **Nguyên nhân**: Khi thực thể là `DNTU` hoặc câu hỏi quy chế chung (không có `course_code`), `actions.py` thực hiện `retriever.collection.get(limit=10)` trên bảng `regulation`. Thao tác này chỉ lấy 10 chunk đầu tiên (phần mở đầu quy chế). Vì `matching_docs` đã có 10 chunk, bước tìm kiếm BM25 bị bỏ qua, dẫn đến việc không bao giờ chạm tới `QuyetDinhChung_chunk37` (nơi chứa Điều 33 Quy chế đào tạo).
- **Khắc phục**:
  - Đối với tài liệu quy chế (`col_name == "regulation"`), kích hoạt tìm kiếm BM25 trực tiếp theo từ khóa trường và tiếng Việt (`graduation_requirements điều kiện tốt nghiệp`), đưa ngay `QuyetDinhChung_chunk37` lên vị trí kết quả số 1.
  - Trong `verifier.py`, phát triển bộ bóc tách các điều khoản liệt kê từ điểm a đến điểm h của Khoản 2 Điều 33.

---

## 3. KIẾN TRÚC GIẢI PHÁP ĐÃ TRIỂN KHAI

### 3.1. Phân loại lực lượng trường (Field Cardinality Policy)
Đã kiến trúc module mới [`src/agent_core/cardinality.py`](file:///D:/RAG-and-Agent/src/agent_core/cardinality.py):
- `SINGLE_VALUE`: `credits`, `hours`, `department`, `english_name`, `prerequisites`.
- `MULTI_VALUE`: `lecturer`, `lecturer_email`, `clo`, `objectives`.
- `MULTI_COMPONENT`: `assessment` (chuyên cần, giữa kỳ, cuối kỳ).
- `MULTI_CLAUSE`: `graduation_requirements`, `academic_warning`, `attendance_rules`, `grading_scale`, `training_rules`.

### 3.2. Động cơ trích xuất tích hợp đa chunk (`verifier.py`)
Tại [`src/agent_core/verifier.py`](file:///D:/RAG-and-Agent/src/agent_core/verifier.py):
- Hàm `verify_requirement` nhận biết các trường đa giá trị (`clo`, `lecturer`, `graduation_requirements`).
- Tự động duyệt qua toàn bộ tập tài liệu ứng viên (`filtered_docs`), trích xuất độc lập từng thành phần và hợp nhất không mất mát.
- Gắn trường `supporting_chunks` vào `EvidenceItem.metadata`, cho phép truy vết chính xác danh sách các chunk đã đóng góp bằng chứng.

### 3.3. Định dạng câu trả lời hội thoại thân thiện (`actions.py`)
Tại [`src/agent_core/actions.py`](file:///D:/RAG-and-Agent/src/agent_core/actions.py):
- Bổ sung hàm `format_requirement_answer(r, catalog)` chuyển đổi các trường dữ liệu thô sang văn phong trợ lý học vụ tự nhiên:
  - *Giảng viên môn Hệ thống nhúng (FIT4201): TS. Trần Đăng Công, ThS. Nguyễn Văn Nhân.*
  - *Chuẩn đầu ra (CLO) môn Công nghệ điện toán đám mây (FIT4113): CLO 1: ...; CLO 2: ...; ...; CLO 8: ...*
  - *Điều kiện xét tốt nghiệp (DNTU): a. ...; b. ...; ...; h. ...*

---

## 4. KẾT QUẢ KIỂM NGHIỆM TOÀN DIỆN (EVALUATION METRICS)

### 4.1. Round C1 Completeness Benchmark (`run_c1_completeness_eval.py`)
| Case ID | Nội dung kiểm thử | Kết quả | Chi tiết thẩm định |
| :--- | :--- | :---: | :--- |
| **CASE_A_LECTURER** | Giảng viên môn FIT4201 | **PASSED** | Loại bỏ 100% rác `"Thông tin giảng viên học"`; Trích xuất cả `TS. Trần Đăng Công` và `ThS. Nguyễn Văn Nhân`. UX đàm thoại. |
| **CASE_B_CLO** | Chuẩn đầu ra FIT4113 | **PASSED** | Đạt đầy đủ 8/8 CLO (`CLO 1` đến `CLO 8`); Provenance đa chunk ghi nhận cả chunk 2 và chunk 3; 0% silent truncation. |
| **CASE_C_GRADUATION** | Điều kiện xét tốt nghiệp | **PASSED** | Thu nạp trọn vẹn 8 mệnh đề quy chế (Điều 33 Khoản 2 a–h); BM25 điều hướng chính xác vào chunk 37. |
| **CASE_D_ASSESSMENT** | Đánh giá môn FIT4104 | **PASSED** | Đầy đủ 3 thành phần: Chuyên cần 10%, Giữa kỳ 30%, Cuối kỳ 60%. |
| **CASE_E_HOURS** | Thời lượng môn FIT4201 | **PASSED** | Đầy đủ cả 15 giờ lý thuyết và 15 giờ thực hành. |
| **CASE_F_CARDINALITY**| Chính sách Cardinality | **PASSED** | 100% các trường học vụ tuân thủ định nghĩa lực lượng trường. |

- **Tổng kết Benchmark C1:** **6/6 PASSED (100.0%)**
- **Quyết định:** `EVIDENCE_COMPLETENESS_ACCEPTED`
- **Báo cáo JSON:** [`eval/results/c1_completeness_eval_report.json`](file:///D:/RAG-and-Agent/eval/results/c1_completeness_eval_report.json)

### 4.2. Kiểm thử hồi quy toàn diện hệ thống (System Regression Suites)
1. **Bộ kiểm thử đơn vị & tích hợp (`pytest tests/ -v`)**:
   - **84/84 tests PASSED** (100.0%) trong 14.18s.
   - Bao gồm toàn bộ suite `tests/unit/test_c1_evidence_completeness.py` (5/5 tests PASSED).
2. **Canonical Benchmark (`eval.agent_core.runner`)**:
   - **182/182 cases PASSED** (100.0%) trong 6.30s.
   - 0 trường hợp hồi quy hay đứt gãy hợp đồng dữ liệu.
3. **Hard Gates Certification (`eval.agent_core.run_p1_2_2_cert`)**:
   - **7/7 Hard Gates PASSED** (100.0%).
   - Trạng thái chứng nhận: `AGENT_CORE_V1_FULLY_ACCEPTED`.
4. **Kiểm tra tiêu chuẩn mã nguồn (`ruff check`)**:
   - **0 violations** trên toàn bộ cây thư mục `src/`, `tests/`, `eval/`.
5. **Kiểm thử trực tiếp qua API sản xuất (`POST /api/chat`)**:
   - Cả 3 ca sử dụng thực tế (Case A, Case B, Case C) đã được kích hoạt thành công qua FastAPI `TestClient`, phản hồi câu trả lời đầy đủ, trung thực và thân thiện.

---

## 5. KẾT LUẬN & PHÊ DUYỆT

Toàn bộ các khiếm khuyết về tính trọn vẹn và trích xuất đa giá trị đã được xử lý triệt để, bảo toàn 100% nguyên tắc trung thực học vụ và không làm thay đổi hay hồi quy bất kỳ tính năng nào đã được phê chuẩn trước đó.

**QUYẾT ĐỊNH CHÍNH THỨC:**
$$\mathbf{EVIDENCE\_COMPLETENESS\_ACCEPTED}$$
