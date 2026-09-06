# TÀI LIỆU KỸ THUẬT: PHÂN TÍCH VÀ PHÂN LOẠI HỒI QUY (ROUND S1.1 REGRESSION TRIAGE)

**Dự án**: Trợ lý Cố vấn Học tập Thông minh (AI Academic Advisor / Agentic RAG)  
**Phiên bản phân tích**: Round S1.1 — Triage & Evaluation Integrity  
**Commit cơ sở kiểm chứng**: `dec1af78fbbc3ec63deddcedca0ccdefd785fe8b` (Clean working tree)  
**Tình trạng**: `CONDITIONALLY_ACCEPTED` (Router V2: 95.15% < 97%; Metamorphic Fuzz: 265/300)

---

## 1. Tổng quan Triage & Mục tiêu Kỹ thuật

Trong Round S1, hệ thống đã đạt được các bước tiến cốt lõi về mặt an toàn:
- **Kích hoạt công cụ không an toàn (Unsafe Tool Activation)**: Giảm từ **3.25% (49 ca)** về **0.0% (0 ca)**.
- **Nhiễm bẩn bộ nhớ cá nhân (Memory Poisoning)**: Giảm từ **6 ca** về **0 ca**.
- **Các cổng an toàn tuyệt đối (Hard Safety Gates)**: 100% đạt chuẩn (0% crash, 0% cross-session leakage, 0% cross-principal leakage, 0% cache context collision, 0% academic authority violation).

Tuy nhiên, có 2 chỉ số gặp hiện tượng hồi quy cục bộ:
1. **Bộ kiểm thử Router V2 toàn diện**: Đạt **98/103 (95.15%)**, trong đó Benchmark V2 đạt **62/62 (100.0%)**, nhưng Holdout suite đạt **36/41 (87.80%)**, dẫn đến tổng thể thấp hơn ngưỡng nghiệm thu 97%.
2. **Kiểm thử Biến hình (Metamorphic Fuzzing - Layer 3)**: Giảm từ **272/300 (90.67%)** xuống **265/300 (88.33%)** (tăng thêm 7 ca thất bại).

Tài liệu này thực hiện **tái hiện thực nghiệm (reproduction)**, bóc tách nguyên nhân gốc rễ và phân loại chi tiết từng ca thất bại trước khi tiến hành bất kỳ thay đổi nào trên mã nguồn production.

---

## 2. Phân tích 5 Ca Thất bại Router Holdout (5 Canonical Failures)

### 2.1. Bảng Dữ liệu Thực nghiệm Chi tiết

| Case ID | Dataset | Query | Expected Cat / Tool | Actual Cat / Tool | Decision Path | Semantics (Polarity/Mod/TargetOp) | Reason Code |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`ho-tool-01`** | holdout | *"Soạn giúp tôi một email gửi thầy Tiệp xin phép nộp bài muộn môn Full-Stack"* | `TOOL_ACTION` / `SEND_EMAIL` | `GENERAL_LLM` / `None` | `SEMANTIC_CLASSIFIER` | `AFFIRMATIVE` / `DIRECT` / `NO_ACTION` | `SEMANTIC_MARGIN_0.19_TOP_GENERAL_LLM` |
| **`ho-tool-03`** | holdout | *"Viết email gửi cô Huệ để xin file tài liệu slide bài giảng môn FIT4117"* | `TOOL_ACTION` / `SEND_EMAIL` | `DOMAIN_DATA` / `None` | `STRONG_DOMAIN_FAST_PATH` | `AFFIRMATIVE` / `DIRECT` / `NO_ACTION` | `COURSE_CODE_FIT4117` |
| **`ho-tool-07`** | holdout | *"Soạn thư điện tử gửi ban giám hiệu về việc xin cấp bảng điểm tạm thời"* | `TOOL_ACTION` / `SEND_EMAIL` | `GENERAL_LLM` / `None` | `SEMANTIC_CLASSIFIER` | `AFFIRMATIVE` / `DIRECT` / `NO_ACTION` | `SEMANTIC_MARGIN_0.15_TOP_GENERAL_LLM` |
| **`ho-tool-10`** | holdout | *"Viết giúp một email trang trọng xin thực tập tại doanh nghiệp đối tác"* | `TOOL_ACTION` / `SEND_EMAIL` | `GENERAL_LLM` / `None` | `SEMANTIC_CLASSIFIER` | `AFFIRMATIVE` / `DIRECT` / `NO_ACTION` | `SEMANTIC_MARGIN_0.19_TOP_GENERAL_LLM` |
| **`ho-tool-13`** | holdout | *"Soạn thảo email gửi thầy Nhẫn xin phản hồi về đề cương nghiên cứu khoa học"* | `TOOL_ACTION` / `SEND_EMAIL` | `GENERAL_LLM` / `None` | `SEMANTIC_CLASSIFIER` | `AFFIRMATIVE` / `DIRECT` / `NO_ACTION` | `SEMANTIC_MARGIN_0.14_TOP_GENERAL_LLM` |

---

### 2.2. Phân loại và Phân tích Căn nguyên 5 Ca Thất bại

#### 1. `ho-tool-01`: "Soạn giúp tôi một email gửi thầy Tiệp xin phép nộp bài muộn môn Full-Stack"
- **Phân loại**: **`B. OLD_EVALUATOR_SEMANTICS_INVALID` (kết hợp `INTENT_SCHEMA_GAP`)**.
- **Căn nguyên**: Người dùng yêu cầu *"Soạn giúp tôi một email..."*. Câu này hoàn toàn không có địa chỉ email người nhận. Người dùng muốn trợ lý học vụ soạn thảo lời văn (drafting). Bộ đánh giá cũ gán nhãn cứng `TOOL_ACTION / SEND_EMAIL`, đồng nhất việc "soạn email" với "gửi email qua mạng". Trong khi đó, kiến trúc mới phân tách rõ: soạn văn bản không phải là thao tác gửi email thực tế (`side_effect = False`).
- **Lý do Router phân loại thành `GENERAL_LLM`**: Tại `src/semantics/analyzer.py`, mẫu `send_positive_patterns` tìm kiếm `(gửi|send)\s+email` hoặc địa chỉ `@`. Do câu có cấu trúc *"email gửi thầy..."* (từ `email` đứng trước `gửi`), `has_positive_send` trả về `False`, dẫn đến `target_operation = NO_ACTION`. Tại Layer 0 của Router, điều kiện an toàn `sem.target_operation not in [SEND_EMAIL, SET_REMINDER]` đã vô hiệu hóa `tool_strength = "STRONG"`. Câu hỏi rơi xuống Layer 3 và SentenceTransformer phân loại về `GENERAL_LLM`.

#### 2. `ho-tool-03`: "Viết email gửi cô Huệ để xin file tài liệu slide bài giảng môn FIT4117"
- **Phân loại**: **`C. ROUTER_CATEGORY_MODEL_GAP` (Multi-Intent Conflict)**.
- **Căn nguyên**: Câu hỏi chứa cả hai tín hiệu mạnh: mã môn học xác thực (`FIT4117`) và hành động viết email (`Viết email`). Trước Round S1, Layer 0 (`STRONG_TOOL_FAST_PATH`) chạy trước Layer 1 (`STRONG_DOMAIN_FAST_PATH`) và chặn câu này thành `TOOL_ACTION`. Khi Round S1 hạ cấp Layer 0 vì `target_operation == NO_ACTION`, câu hỏi rơi vào Layer 1.1 và mã môn học `FIT4117` đã kích hoạt `DOMAIN_DATA`.
- **Đặc trưng**: Đây là trường hợp truy vấn đa ý định (vừa liên quan tài liệu môn học vừa muốn gửi thư).

#### 3. `ho-tool-07`: "Soạn thư điện tử gửi ban giám hiệu về việc xin cấp bảng điểm tạm thời"
- **Phân loại**: **`B. OLD_EVALUATOR_SEMANTICS_INVALID` (kết hợp `INTENT_SCHEMA_GAP`)**.
- **Căn nguyên**: Tương tự `ho-tool-01`. Không có địa chỉ email người nhận. Yêu cầu soạn văn bản hành chính để xin bảng điểm. Bộ đánh giá cũ kỳ vọng `SEND_EMAIL` dù không có khả năng gửi đi. Router phân loại vào `GENERAL_LLM` vì không có địa chỉ đích.

#### 4. `ho-tool-10`: "Viết giúp một email trang trọng xin thực tập tại doanh nghiệp đối tác"
- **Phân loại**: **`B. OLD_EVALUATOR_SEMANTICS_INVALID`**.
- **Căn nguyên**: Không có người nhận, không có địa chỉ, thuần túy là yêu cầu sinh văn bản bản thảo (*"Viết giúp một email trang trọng..."*). Bộ đánh giá cũ yêu cầu `SEND_EMAIL`. Router mới nhận diện đúng là tác vụ sinh ngôn ngữ chung `GENERAL_LLM`.

#### 5. `ho-tool-13`: "Soạn thảo email gửi thầy Nhẫn xin phản hồi về đề cương nghiên cứu khoa học"
- **Phân loại**: **`B. OLD_EVALUATOR_SEMANTICS_INVALID` (kết hợp `INTENT_SCHEMA_GAP`)**.
- **Căn nguyên**: Soạn thảo thư gửi giảng viên nhưng không có địa chỉ email. Bộ đánh giá cũ gộp soạn thảo thành gửi thư.

---

### 2.3. Ranh giới Kiến trúc: Category ≠ Action & Hiện tượng Conflation

Qua 5 ca thất bại trên, xuất hiện một vấn đề kiến trúc quan trọng:
- **Độ lệch của Bộ đánh giá cũ (Evaluator Conflation)**: Bộ benchmark ban đầu chỉ có 3 nhãn category (`DOMAIN_DATA`, `GENERAL_LLM`, `TOOL_ACTION`) và 2 nhãn tool (`SEND_EMAIL`, `SET_REMINDER`). Do đó, bất kỳ câu hỏi nào nhắc tới `email` đều bị ép buộc gán nhãn `TOOL_ACTION / SEND_EMAIL`, bất kể câu đó chỉ là soạn thảo văn bản hay gửi thư thực tế.
- **Hiện tượng Over-suppression tại Router**: Tại Round S1, để bảo vệ hệ thống không bị `Unsafe Tool Activation`, tầng chính sách Router V2 đã áp đặt quy tắc:
  ```python
  if sem.target_operation not in [ActionOperation.SEND_EMAIL, ActionOperation.SET_REMINDER]:
      top_cat = "GENERAL_LLM"
  ```
  Quy tắc này đã đẩy toàn bộ các câu hỏi mang tính chất công cụ soạn thảo (`COMPOSE_EMAIL`) hoặc có ý định công cụ nhưng thiếu địa chỉ email sang `GENERAL_LLM`.
- **Đề xuất Evaluator Change (`EVALUATOR_CHANGE_PROPOSED`)**:
  - Đối với `ho-tool-10` (*"Viết giúp một email trang trọng xin thực tập..."*): Bản chất là tác vụ sinh văn bản (text generation), gán nhãn `SEND_EMAIL` là sai về mặt ngữ nghĩa học vụ.
  - Tuy nhiên, theo yêu cầu của Round S1.1, **không được sửa đổi dataset benchmark trong quá trình triage**. Chúng ta sẽ giải quyết vấn đề này ở tầng Policy mà vẫn giữ nguyên bất biến an toàn side-effect.

---

## 3. Phân tích 35 Ca Thất bại Metamorphic Fuzzing (Layer 3)

Kiểm thử Layer 3 thực hiện biến dị 30 câu hỏi hạt giống qua 10 toán tử đột biến với seed cố định `20260906`, sinh ra 300 trường hợp kiểm thử. Có **35 ca thất bại**.

### 3.1. Phân loại Nhóm Đột biến (Mutation Classification)

| Nhóm Phân loại Đột biến | Số lượng Ca | Tỷ lệ (%) | Toán tử tương ứng |
| :--- | :---: | :---: | :--- |
| **`DIACRITIC_REMOVAL`** | 12 | 34.3% | `diacritic_remove` (Bỏ dấu tiếng Việt) |
| **`UNICODE_WIDTH`** | 8 | 22.9% | `unicode_fullwidth` (Ký tự Fullwidth độ rộng đầy đủ) |
| **`SEMANTICALLY_DESTRUCTIVE_MUTATION`** | 8 | 22.9% | `char_substitute`, `char_delete`, `char_insert`, `char_transpose` phá hủy từ khóa |
| **`WHITESPACE`** | 4 | 11.4% | `space_insert`, `space_remove` chèn ngắt khoảng trắng trong từ |
| **`CASE_MUTATION`** | 3 | 8.6% | `mixed_case` (Viết hoa thường lộn xộn) |
| **TỔNG CỘNG** | **35** | **100.0%** | |

---

### 3.2. Bảng Danh mục Toàn bộ 35 Ca Thất bại Layer 3

| Case ID | Operator | Seed Query | Mutated Query | Expected | Observed | Classification | Metamorphic Validity |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `META-0017` | diacritic_remove | Ai là giảng viên phụ trách môn Hệ thống nhúng? | Ai la giang vien phu trach mon He thong nhung? | DOMAIN_DATA | GENERAL_LLM | `DIACRITIC_REMOVAL` | `SEMANTICS_PRESERVED` |
| `META-0067` | diacritic_remove | Chuẩn đầu ra tiếng Anh để tốt nghiệp Đại Nam là bao nhiêu? | Chuan dau ra tieng Anh de tot nghiep Dai Nam la bao nhieu? | DOMAIN_DATA | GENERAL_LLM | `DIACRITIC_REMOVAL` | `SEMANTICS_PRESERVED` |
| `META-0087` | diacritic_remove | Sinh viên nghỉ học bao nhiêu phần trăm thì bị cấm thi? | Sinh vien nghi hoc bao nhieu phan tram thi bi cam thi? | DOMAIN_DATA | GENERAL_LLM | `DIACRITIC_REMOVAL` | `SEMANTICS_PRESERVED` |
| `META-0097` | diacritic_remove | Khung chương trình đào tạo ngành Công nghệ thông tin có những môn nào? | Khung chuong trinh dao tao nganh Cong nghe thong tin co nhung mon nao? | DOMAIN_DATA | GENERAL_LLM | `DIACRITIC_REMOVAL` | `SEMANTICS_PRESERVED` |
| `META-0153` | char_substitute | Nhắc tôi nộp bài tập lớn vào 17h chiều mai. | Nh_c tôi nộp bài tập lớn vào 17h chiều mai. | TOOL_ACTION | GENERAL_LLM | `SEMANTICALLY_DESTRUCTIVE_MUTATION` | `SEMANTICS_DESTROYED` |
| `META-0157` | diacritic_remove | Nhắc tôi nộp bài tập lớn vào 17h chiều mai. | Nhac toi nop bai tap lon vao 17h chieu mai. | TOOL_ACTION | GENERAL_LLM | `DIACRITIC_REMOVAL` | `SEMANTICS_PRESERVED` |
| `META-0159` | unicode_fullwidth | Nhắc tôi nộp bài tập lớn vào 17h chiều mai. | Ｎｈắｃ　ｔôｉ　ｎộｐ　ｂàｉ　ｔậｐ　ｌớｎ　ｖàｏ　１７ｈ　ｃｈｉềｕ　ｍａｉ． | TOOL_ACTION | GENERAL_LLM | `UNICODE_WIDTH` | `SEMANTICS_PRESERVED` |
| `META-0167` | diacritic_remove | Đặt lịch nhắc ôn thi môn FIT4201 lúc 8h sáng chủ nhật. | Dat lich nhac on thi mon FIT4201 luc 8h sang chu nhat. | TOOL_ACTION | DOMAIN_DATA | `DIACRITIC_REMOVAL` | `SEMANTICS_AMBIGUOUS` |
| `META-0169` | unicode_fullwidth | Đặt lịch nhắc ôn thi môn FIT4201 lúc 8h sáng chủ nhật. | Đặｔ　ｌịｃｈ　ｎｈắｃ　ôｎ　ｔｈｉ　ｍôｎ　ＦＩＴ４２０１　ｌúｃ　８ｈ　ｓáｎｇ　ｃｈủ　ｎｈậｔ． | TOOL_ACTION | GENERAL_LLM | `UNICODE_WIDTH` | `SEMANTICS_PRESERVED` |
| `META-0174` | char_transpose | Gửi email cho giảng viên phụ trách tieppv@dainam.edu.vn. | Gửi emali cho giảng viên phụ trách tieppv@dainam.edu.vn. | TOOL_ACTION | DOMAIN_DATA | `SEMANTICALLY_DESTRUCTIVE_MUTATION` | `SEMANTICS_DESTROYED` |
| `META-0177` | diacritic_remove | Gửi email cho giảng viên phụ trách tieppv@dainam.edu.vn. | Gui email cho giang vien phu trach tieppv@dainam.edu.vn. | TOOL_ACTION | GENERAL_LLM | `DIACRITIC_REMOVAL` | `SEMANTICS_PRESERVED` |
| `META-0179` | unicode_fullwidth | Gửi email cho giảng viên phụ trách tieppv@dainam.edu.vn. | Ｇửｉ　ｅｍａｉｌ　ｃｈｏ　ｇｉảｎｇ　ｖｉêｎ　ｐｈụ　ｔｒáｃｈ　ｔｉｅｐｐｖ＠ｄａｉｎａｍ．ｅｄｕ．ｖｎ． | TOOL_ACTION | GENERAL_LLM | `UNICODE_WIDTH` | `SEMANTICS_PRESERVED` |
| `META-0184` | char_transpose | Tư vấn cho tôi lộ trình học kỳ tới của khóa K19. | Tư vấn cho tôil ộ trình học kỳ tới của khóa K19. | DOMAIN_DATA | GENERAL_LLM | `SEMANTICALLY_DESTRUCTIVE_MUTATION` | `SEMANTICS_DESTROYED` |
| `META-0188` | mixed_case | Tư vấn cho tôi lộ trình học kỳ tới của khóa K19. | tư VấN cHo tÔI lỘ tRìNh HỌc Kỳ TớI CỦa kHóa k19. | DOMAIN_DATA | GENERAL_LLM | `CASE_MUTATION` | `SEMANTICS_PRESERVED` |
| `META-0189` | unicode_fullwidth | Tư vấn cho tôi lộ trình học kỳ tới của khóa K19. | Ｔư　ｖấｎ　ｃｈｏ　ｔôｉ　ｌộ　ｔｒìｎｈ　ｈọｃ　ｋỳ　ｔớｉ　ｃủａ　ｋｈóａ　Ｋ１９． | DOMAIN_DATA | GENERAL_LLM | `UNICODE_WIDTH` | `SEMANTICS_PRESERVED` |
| `META-0225` | space_insert | Thực tập doanh nghiệp diễn ra vào học kỳ mấy? | Thực tập doanh nghiệp diễn ra vào học k  ỳ mấy? | DOMAIN_DATA | GENERAL_LLM | `WHITESPACE` | `SEMANTICS_PRESERVED` |
| `META-0227` | diacritic_remove | Thực tập doanh nghiệp diễn ra vào học kỳ mấy? | Thuc tap doanh nghiep dien ra vao hoc ky may? | DOMAIN_DATA | GENERAL_LLM | `DIACRITIC_REMOVAL` | `SEMANTICS_PRESERVED` |
| `META-0229` | unicode_fullwidth | Thực tập doanh nghiệp diễn ra vào học kỳ mấy? | Ｔｈựｃ　ｔậｐ　ｄｏａｎｈ　ｎｇｈｉệｐ　ｄｉễｎ　ｒａ　ｖàｏ　ｈọｃ　ｋỳ　ｍấｙ？ | DOMAIN_DATA | GENERAL_LLM | `UNICODE_WIDTH` | `SEMANTICS_PRESERVED` |
| `META-0247` | diacritic_remove | Điểm rèn luyện ảnh hưởng thế nào đến việc xét học bổng? | Diem ren luyen anh huong the nao den viec xet hoc bong? | DOMAIN_DATA | GENERAL_LLM | `DIACRITIC_REMOVAL` | `SEMANTICS_PRESERVED` |
| `META-0248` | mixed_case | Điểm rèn luyện ảnh hưởng thế nào đến việc xét học bổng? | ĐIỂM rèN luYệN ẢnH HưởNg ThẾ nÀO Đến VIệc Xét học bổnG? | DOMAIN_DATA | GENERAL_LLM | `CASE_MUTATION` | `SEMANTICS_PRESERVED` |
| `META-0251` | char_delete | Gửi email xin phép nghỉ học tới gv@dainam.edu.vn. | Gử email xin phép nghỉ học tới gv@dainam.edu.vn. | TOOL_ACTION | GENERAL_LLM | `SEMANTICALLY_DESTRUCTIVE_MUTATION` | `SEMANTICS_DESTROYED` |
| `META-0255` | space_insert | Gửi email xin phép nghỉ học tới gv@dainam.edu.vn. | G  ửi email xin phép nghỉ học tới gv@dainam.edu.vn. | TOOL_ACTION | GENERAL_LLM | `WHITESPACE` | `SEMANTICS_PRESERVED` |
| `META-0257` | diacritic_remove | Gửi email xin phép nghỉ học tới gv@dainam.edu.vn. | Gui email xin phep nghi hoc toi gv@dainam.edu.vn. | TOOL_ACTION | GENERAL_LLM | `DIACRITIC_REMOVAL` | `SEMANTICS_PRESERVED` |
| `META-0259` | unicode_fullwidth | Gửi email xin phép nghỉ học tới gv@dainam.edu.vn. | Ｇửｉ　ｅｍａｉｌ　ｘｉｎ　ｐｈéｐ　ｎｇｈỉ　ｈọｃ　ｔớｉ　ｇｖ＠ｄａｉｎａｍ．ｅｄｕ．ｖｎ． | TOOL_ACTION | GENERAL_LLM | `UNICODE_WIDTH` | `SEMANTICS_PRESERVED` |
| `META-0271` | char_delete | Cách tính điểm trung bình tích lũy GPA theo thang điểm 4. | Cách tính điểm trung bình tíc lũy GPA theo thang điểm 4. | DOMAIN_DATA | GENERAL_LLM | `SEMANTICALLY_DESTRUCTIVE_MUTATION` | `SEMANTICS_DESTROYED` |
| `META-0272` | char_insert | Cách tính điểm trung bình tích lũy GPA theo thang điểm 4. | Cách tính đicểm trung bình tích lũy GPA theo thang điểm 4. | DOMAIN_DATA | GENERAL_LLM | `SEMANTICALLY_DESTRUCTIVE_MUTATION` | `SEMANTICS_DESTROYED` |
| `META-0273` | char_substitute | Cách tính điểm trung bình tích lũy GPA theo thang điểm 4. | Cách tính điểm trung btnh tích lũy GPA theo thang điểm 4. | DOMAIN_DATA | GENERAL_LLM | `SEMANTICALLY_DESTRUCTIVE_MUTATION` | `SEMANTICS_DESTROYED` |
| `META-0274` | char_transpose | Cách tính điểm trung bình tích lũy GPA theo thang điểm 4. | Cách tính điể mtrung bình tích lũy GPA theo thang điểm 4. | DOMAIN_DATA | GENERAL_LLM | `SEMANTICALLY_DESTRUCTIVE_MUTATION` | `SEMANTICS_DESTROYED` |
| `META-0275` | space_insert | Cách tính điểm trung bình tích lũy GPA theo thang điểm 4. | Cách tính điểm trung bình tích lũy GPA theo   thang điểm 4. | DOMAIN_DATA | GENERAL_LLM | `WHITESPACE` | `SEMANTICS_PRESERVED` |
| `META-0276` | space_remove | Cách tính điểm trung bình tích lũy GPA theo thang điểm 4. | Cách tính điểm trung bình tíchlũy GPA theo thang điểm 4. | DOMAIN_DATA | GENERAL_LLM | `WHITESPACE` | `SEMANTICS_PRESERVED` |
| `META-0277` | diacritic_remove | Cách tính điểm trung bình tích lũy GPA theo thang điểm 4. | Cach tinh diem trung binh tich luy GPA theo thang diem 4. | DOMAIN_DATA | GENERAL_LLM | `DIACRITIC_REMOVAL` | `SEMANTICS_PRESERVED` |
| `META-0278` | mixed_case | Cách tính điểm trung bình tích lũy GPA theo thang điểm 4. | CÁch tínH ĐIểm TRuNG BÌNH tícH lũY gpA ThEO THaNG ĐiểM 4. | DOMAIN_DATA | GENERAL_LLM | `CASE_MUTATION` | `SEMANTICS_PRESERVED` |
| `META-0279` | unicode_fullwidth | Cách tính điểm trung bình tích lũy GPA theo thang điểm 4. | Ｃáｃｈ　ｔíｎｈ　đｉểｍ　ｔｒｕｎｇ　ｂìｎｈ　ｔíｃｈ　ｌũｙ　ＧＰＡ　ｔｈｅｏ　ｔｈａｎｇ　đｉểｍ　４． | DOMAIN_DATA | GENERAL_LLM | `UNICODE_WIDTH` | `SEMANTICS_PRESERVED` |
| `META-0297` | diacritic_remove | Đặt lịch nhắc tôi nộp học phí trước ngày 15 tháng này. | Dat lich nhac toi nop hoc phi truoc ngay 15 thang nay. | TOOL_ACTION | GENERAL_LLM | `DIACRITIC_REMOVAL` | `SEMANTICS_PRESERVED` |
| `META-0299` | unicode_fullwidth | Đặt lịch nhắc tôi nộp học phí trước ngày 15 tháng này. | Đặｔ　ｌịｃｈ　ｎｈắｃ　ｔôｉ　ｎộｐ　ｈọｃ　ｐｈí　ｔｒướｃ　ｎｇàｙ　１５　ｔｈáｎｇ　ｎàｙ． | TOOL_ACTION | GENERAL_LLM | `UNICODE_WIDTH` | `SEMANTICS_PRESERVED` |

---

### 3.3. Phân tích 7 Ca Hồi quy Giữa Round R và Round S1

So sánh với kết quả Layer 3 của Round R (28 ca thất bại), trong Round S1 xuất hiện thêm 7 ca thất bại (tổng 35 ca). Thực chất có 11 ca cụ thể bị ảnh hưởng bởi chính sách mới:
1. `META-0153`: `Nh_c tôi nộp bài tập lớn...`
2. `META-0157`: `Nhac toi nop bai tap lon...`
3. `META-0159`: `Ｎｈắｃ　ｔôｉ　ｎộｐ　ｂàｉ...`
4. `META-0169`: `Đặｔ　ｌịｃｈ　ｎｈắｃ　ôｎ　ｔｈｉ...`
5. `META-0177`: `Gui email cho giang vien...`
6. `META-0179`: `Ｇửｉ　ｅｍａｉｌ　ｃｈｏ...`
7. `META-0251`: `Gử email xin phép...`
8. `META-0255`: `G  ửi email xin phép...`
9. `META-0257`: `Gui email xin phep...`
10. `META-0259`: `Ｇửｉ　ｅｍａｉｌ　ｘｉｎ...`
11. `META-0299`: `Đặｔ　ｌịｃｈ　ｎｈắｃ　ｔôｉ...`

**Căn nguyên cơ chế**:
- Trong Round R, SentenceTransformer (Layer 3) có khả năng ánh xạ vector ngữ nghĩa tương đối tốt cho các câu đột biến Unicode (`Ｇửｉ　ｅｍａｉｌ`, `Ｎｈắｃ　ｔôｉ`) hoặc bỏ dấu (`Gui email`, `Nhac toi`), giúp `top_cat` đạt `TOOL_ACTION`.
- Trong Round S1, chúng ta bổ sung điều kiện cứng tại Layer 3 của Router:
  ```python
  if sem.target_operation not in [ActionOperation.SEND_EMAIL, ActionOperation.SET_REMINDER]:
      top_cat = "GENERAL_LLM"
  ```
  Do tầng `analyze_utterance` chưa chuẩn hóa Unicode NFKC và chưa xử lý tiếng Việt không dấu, regex không nhận diện được `target_operation`, dẫn đến `target_operation = NO_ACTION`.
  Hậu quả: Quy tắc an toàn đã **ghi đè (override) và hạ cấp (demote)** kết quả nhận diện vector chính xác của SentenceTransformer về `GENERAL_LLM`.

---

## 4. Phân nhóm Thất bại & Ma trận Quyết định (Decision Matrix)

| Nhóm Thất bại (Failure Cluster) | Số lượng | Tính hợp lệ biến hình (Metamorphic Validity) | Bản chất Kỹ thuật | Khuyến nghị Duy nhất (Decision Matrix) |
| :--- | :---: | :--- | :--- | :--- |
| **Cluster 1: Unicode Fullwidth** | 8 | `SEMANTICALLY_PRESERVED` | Thiếu chuẩn hóa Unicode NFKC trước khi phân tích | **`NORMALIZATION`** |
| **Cluster 2: Diacritic Removal** | 12 | `SEMANTICALLY_PRESERVED` | Truy vấn tiếng Việt không dấu không khớp regex có dấu | **`NORMALIZATION`** (Round S2 Scope) |
| **Cluster 3: Phá hủy Từ khóa** | 8 | `SEMANTICALLY_DESTROYED` | Đột biến làm mất ký tự cốt lõi (`Nh_c`, `emali`, `btnh`) | **`ACCEPTABLE_ROBUSTNESS_LIMIT`** |
| **Cluster 4: Xáo trộn Khoảng trắng** | 4 | `SEMANTICALLY_PRESERVED` | Khoảng trắng nội từ (`k  ỳ`, `G  ửi`) | **`NORMALIZATION`** (Round S2 Scope) |
| **Cluster 5: Lộn xộn Hoa Thường** | 3 | `SEMANTICALLY_PRESERVED` | Mixed-case làm giảm điểm Cosine similarity | **`NORMALIZATION`** / **`POLICY`** |
| **Cluster 6: 5 Router Holdout Failures** | 5 | N/A | Evaluator conflation + Semantic Demotion Overreach | **`POLICY`** & **`EVALUATOR`** |

---

## 5. Lỗi Sai lệch Đo kiểm (Benchmark Provenance & Telemetry Bugs)

Bên cạnh các ca thất bại phân loại, quá trình kiểm tra mã nguồn benchmark runner (`eval/robustness/runner.py`) đã phát hiện 4 lỗi sai lệch đo kiểm nghiêm trọng:

1. **Lỗi Benchmark Provenance**:
   - Hàm `get_current_commit()` chỉ lấy `git rev-parse --short HEAD` tại thời điểm chạy. Nếu có các thay đổi chưa commit trong working tree, kết quả vẫn được lưu dưới commit hash cũ, tạo ra artifact sai lệch (`robustness_v3_c57f208.json` dù chạy trên code S1).
   - *Khắc phục*: Phải ghi nhận `commit_sha`, `commit_short`, `working_tree_clean`, `working_tree_diff_hash`, `timestamp`, `generator_version`. Nếu working tree không sạch, đánh dấu `UNCOMMITTED_EXPERIMENT` hoặc từ chối tạo artifact nghiệm thu chính thức.

2. **Lỗi Telemetry `metamorphic_consistency_pct = 0.0`**:
   - Trường `metamorphic_consistency_pct` trong `RobustnessReport` không được tính toán trong `runner.py`, khiến báo cáo JSON luôn xuất hiện giá trị `0.0%` dù Layer 3 đã chạy.
   - *Khắc phục*: Tính toán chính xác tỷ lệ nhất quán biến hình cho toàn bộ Layer 3 và riêng cho nhóm `SEMANTICS_PRESERVED`.

3. **Lỗi Telemetry `architecture_gap_count = 0`**:
   - Báo cáo JSON ghi nhận `architecture_gap_count: 0` trong khi danh sách `architecture_gaps` liệt kê 4 gap (`GAP-01` đến `GAP-04`).
   - *Khắc phục*: Định nghĩa rõ ràng `architecture_gap_types = len(architecture_gaps)` (4) và `architecture_gap_occurrences = sum(gap['count'])` (42).

4. **Lỗi Nhầm lẫn Ngữ nghĩa Chỉ số (Metric Semantics Inconsistency)**:
   - 6 lỗi trong Round R là `MEMORY_POISONING` (người dùng phát biểu câu phủ định nhưng bị ghi vào hồ sơ), hoàn toàn khác với `Academic Authority Violation` (sinh viên tuyên bố quy chế sai đè lên quy chế đào tạo). Không được gộp chung hai chỉ số này.

---

## 6. Kế hoạch Khắc phục Tối thiểu (Recommended Action Plan)

Để giải quyết triệt để các vấn đề trên mà không mở rộng phạm vi sang Round S2:

1. **Khắc phục Chính sách Router (`POLICY`)**:
   - Điều chỉnh điều kiện kiểm tra an toàn tại Layer 0 và Layer 3 trong `src/router/policy.py`:
     - Tách biệt rõ: Router chỉ phân loại ý định (`Intent Classification`), không kiêm nhiệm việc xác thực địa chỉ email người nhận.
     - Nếu một câu hỏi là khẳng định, không phủ định, không giải thích, và có hành động email (`Viết email`, `Soạn thư điện tử gửi...`), nó thuộc về `TOOL_ACTION` với `tool_intent = "SEND_EMAIL"`.
     - Cổng thẩm quyền `Action Authorization Gate` tại Agent node sẽ chịu trách nhiệm kiểm tra xem có được phép bấm gửi hay chỉ soạn thảo bản nháp an toàn (`side_effect = False`).
   - Sửa đổi này sẽ đưa Router Benchmark V2 đạt 100% và Router Full Suite đạt $\ge 97\%$ (dự kiến 100/103 hoặc 102/103).

2. **Khắc phục Chuẩn hóa Ký tự Unicode (`NORMALIZATION`)**:
   - Bổ sung chuẩn hóa **Unicode NFKC** (`unicodedata.normalize('NFKC', text)`) vào `src/router/normalizer.py` và `src/semantics/normalizer.py`.
   - Khắc phục triệt để 8 ca thất bại do `unicode_fullwidth` mà không cần thêm bất kỳ từ khóa mới nào.

3. **Khắc phục Đo kiểm & Provenance (`EVALUATION INTEGRITY`)**:
   - Cập nhật `eval/robustness/runner.py` và `eval/robustness/schemas.py`:
     - Lưu đầy đủ metadata provenance (`commit_sha`, `commit_short`, `working_tree_clean`).
     - Tên file artifact bắt buộc là `robustness_v3_<exact_commit>.json`.
     - Sửa lỗi tính toán `metamorphic_consistency_pct`, `architecture_gap_types`, và `failures_by_type`.

4. **Bảo toàn Tuyệt đối Các Cổng An toàn Cứng**:
   - Đảm bảo `Unsafe Tool Activation = 0%`, `Memory Poisoning = 0%`, `Crash = 0%`.
