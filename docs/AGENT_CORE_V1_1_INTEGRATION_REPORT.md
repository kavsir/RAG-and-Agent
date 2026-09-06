# TÀI LIỆU KINH NGHIỆM KỸ THUẬT: TÍCH HỢP AGENT CORE VÀO PRODUCTION & KHÔI PHỤC TÍNH TRUNG THỰC CỦA BẰNG CHỨNG (ROUND P1.1)

**Dự án:** AI Academic Advisor / Agentic RAG  
**Phân hệ:** Goal-Driven Agent Core V1.1 Production Integration & Verification Engine  
**Trạng thái kiến trúc:** Hoàn thiện tích hợp luồng sản xuất thực tế & Chuẩn hóa chân lý bằng chứng  

---

## 1. TỔNG QUAN VẤN ĐỀ & BỐI CẢNH NÂNG CẤP KIẾN TRÚC

Trong giai đoạn Round P1, hệ thống đã xây dựng thành công lõi tác tử theo vòng lặp có chặn:
`UNDERSTAND -> OBSERVE -> PLAN -> ACT -> VERIFY -> PROGRESS -> ASK_USER / FINISH`.

Tuy nhiên, khi đưa vào kiểm chứng thực tế và kiểm toán mã nguồn, 5 lỗ hổng kiến trúc nghiêm trọng đã bộc lộ:
1. **Cô lập luồng Demo:** Endpoint sản xuất `POST /api/chat` vẫn chạy đồ thị cũ (`src.agent.graph.graph`), trong khi `AgentCoreService` chỉ tồn tại như một bản demo độc lập.
2. **Kiến trúc truy xuất kép (Second Retrieval Architecture):** `actions.py` tái phát kiến trúc đọc file `.docx` trực tiếp qua `python-docx` và lưu bộ nhớ đệm `_doc_cache`, bỏ qua hoàn toàn hạ tầng `HybridRetriever` và `ChromaDB` đã được nghiệm thu.
3. **Bằng chứng giả tạo (Fabricated Evidence Fallback):** `verifier.py` chứa các chuỗi fallback tĩnh (ví dụ: gán cứng tỷ lệ thi cuối kỳ `50%` hoặc mặc định không tiên quyết), vi phạm nguyên tắc bất biến của hệ thống học vụ.
4. **Từ điển tĩnh thay thế CSDL học vụ:** `environment_catalog.py` và `entity_catalog.py` nhúng cứng các thông tin tín chỉ, giảng viên bằng Python dictionary thủ công thay vì phát sinh tất định từ dữ liệu nguồn.
5. **Chỉ số an toàn hình thức:** Các biến đếm chống lặp vô hạn, chống thao tác công cụ không an toàn bắt đầu bằng 0 và kết thúc bằng 0 mà không có nguồn sự kiện đo lường thực tế.

Tài liệu này đúc kết những kinh nghiệm xương máu trong quá trình giải quyết dứt điểm các vấn đề trên tại Round P1.1.

---

## 2. NĂM NGUYÊN LÝ KỸ THUẬT CỐT LÕI (CORE LESSONS LEARNED)

### 2.1. CATALOG != ACADEMIC TRUTH (Danh mục không phải là Chân lý Học vụ)

* **Vấn đề nhận thức sai lệch:** Ban đầu, chúng tôi đưa toàn bộ thông tin số tín chỉ, giảng viên, chuẩn đầu ra vào `EntityCatalog` dưới dạng code Python. Điều này vô tình biến code nguồn thành một "CSDL học vụ thứ hai", dễ phân rã khi văn bản nhà trường cập nhật.
* **Kinh nghiệm kiến trúc:**
  - `EntityCatalog` và `KnowledgeEnvironment` chỉ đóng vai trò **siêu dữ liệu định tuyến** (routing metadata, entity ID, canonical name, aliases, source references, available document types).
  - Không bao giờ nhúng cứng các dữ kiện học vụ biến động (`credits`, `assessment`, `lecturer`, `lecturer_email`, `hours`) trực tiếp vào file mã nguồn Python.
  - Toàn bộ chân lý học vụ phải được sinh ra tất định từ dữ liệu nguồn thông qua `src/agent_core/build_knowledge_env.py` -> `runtime/knowledge_environment.json`. Mọi giá trị học vụ phải đi kèm xuất xứ xuất bản (`provenance`: `source_file`, `document_type`, `extracted_at`, `ingestion_version`). Không có provenance đồng nghĩa với việc không phải là bằng chứng thẩm quyền.

### 2.2. EVIDENCE != RETRIEVAL RESULT (Bằng chứng không phải là Kết quả Truy xuất Thô)

* **Vấn đề nhận thức sai lệch:** Nhầm lẫn giữa việc "truy xuất được một đoạn văn bản" với việc "đã có bằng chứng thỏa mãn yêu cầu".
* **Kinh nghiệm kiến trúc:**
  - Đoạn văn bản thu thập từ RAG chỉ là *văn bản ứng viên* (candidate chunks).
  - Một `EvidenceItem` chỉ được tạo ra sau khi `EvidenceVerifier` kiểm tra cấu trúc ngữ nghĩa và khẳng định đoạn trích chứa đúng thuộc tính cần tìm của đúng thực thể học vụ.
  - Loại bỏ hoàn toàn kiến trúc đọc file `.docx` cục bộ trong `actions.py`. Tái sử dụng trực tiếp `get_collection_retriever` và ChromaDB với chiến lược:
    1. *Exact Strategy:* Truy vấn lọc chính xác theo metadata (`where={"course_code": entity}`).
    2. *Expanded Strategy:* Chỉ kích hoạt khi Exact thất bại, mở rộng theo alias đã chuẩn hóa trong catalog nhưng áp đặt chặn cứng tuyệt đối không cho phép ô nhiễm chéo thực thể (cross-entity contamination).

### 2.3. MISSING != NONE (Thiếu dữ liệu khác hoàn toàn với Xác nhận Không có)

* **Vấn đề nhận thức sai lệch:** Coi việc "văn bản không đề cập đến tiên quyết" tương đương với "môn học này không yêu cầu tiên quyết", dẫn đến việc tự động fallback gán bừa kết quả.
* **Kinh nghiệm kiến trúc:**
  - **`MISSING` / `INSUFFICIENT`:** Tài liệu không chứa thông tin hoặc đoạn văn bản truy xuất không đủ dữ kiện để khẳng định. Trong trường hợp này, Agent phải trung thực thừa nhận dữ liệu chưa đủ hoặc đề xuất giải pháp thay thế. Tuyệt đối không tự suy đoán (Zero Fabricated Fallback).
  - **`VERIFIED_NONE`:** Tài liệu chính thống chứa câu văn khẳng định tường minh về sự vắng mặt của điều kiện (ví dụ: *"Điều kiện tiên quyết: Không có học phần tiên quyết"* hoặc *"Học phần tiên quyết: None"*). Trạng thái này có giá trị minh chứng độc lập, có nguồn trích xuất rõ ràng, phân biệt rành mạch với việc thiếu sót dữ liệu.

### 2.4. PLANNER != TOOL AUTHORIZATION (Lập kế hoạch không đồng nghĩa với Thẩm quyền Thực thi)

* **Vấn đề nhận thức sai lệch:** Cho rằng khi Agent Planner đề xuất hành động `SEND_EMAIL` hay `SET_REMINDER` thì hệ thống có thể gọi trực tiếp công cụ bên ngoài.
* **Kinh nghiệm kiến trúc:**
  - Kế hoạch của Planner chỉ là một *đề xuất mang tính suy luận* (intent proposal).
  - Trước khi bất kỳ tác vụ nào có hiệu ứng phụ (side effect) được gọi, nó bắt buộc phải đi qua **`ActionAuthorizationGate`** độc lập tại tầng ngữ nghĩa (`src/semantics`).
  - Nếu câu phát ngôn của người dùng mang tính phủ định (*"đừng gửi mail"*), giả định (*"nếu gửi mail thì sao"*), điều kiện chưa thỏa hoặc mâu thuẫn chỉ dẫn, Gate sẽ lập tức chặn đứng hoặc chuyển hướng sang `COMPOSE_EMAIL` (Draft-only) / `CLARIFY`.
  - Phân tách ranh giới an toàn: Planner quyết định *cần làm gì để đạt mục tiêu*, còn Gate quyết định *hệ thống có được phép tạo side-effect hay không*.

### 2.5. AGENT CORE != STANDALONE DEMO (Agent Core phải là Đường dẫn Sản xuất Trực tiếp)

* **Vấn đề nhận thức sai lệch:** Xây dựng Agent Core rất hoàn thiện nhưng chỉ chạy qua hàm `loop.run()` trong các file đánh giá, còn API phục vụ người dùng thực (`POST /api/chat`) vẫn chạy kiến trúc cũ.
* **Kinh nghiệm kiến trúc:**
  - `POST /api/chat` phải được chuyển đổi toàn diện để gọi `AgentCoreService`.
  - Hỗ trợ cơ chế tiếp tục mục tiêu đa lượt (Human-in-the-loop multi-turn goal resumption) dựa trên cấu trúc:
    `user_id` + `conversation_id` + `goal_id`.
  - Khi Agent cần người dùng làm rõ (`NEEDS_USER_INPUT`), phản hồi trả về `goal_id`, câu hỏi làm rõ và danh sách lựa chọn gợi ý (nếu có). Tin nhắn tiếp theo của người dùng trong cùng phiên sẽ tiếp tục mục tiêu đó thay vì khởi tạo lại từ đầu.
  - Lưu trữ trạng thái mục tiêu bền vững vào SQLite (`runtime/agent_goals.sqlite3`) với chế độ WAL để sống sót qua các lần khởi động lại dịch vụ (service restart).
  - Tuyệt đối ngăn chặn rò rỉ chéo phiên (cross-session leakage) và chéo người dùng (cross-principal leakage).

---

## 3. THỰC NGHIỆM ĐO ĐẠC VÀ ĐÁNH GIÁ CHẤT LƯỢNG (BENCHMARK RESULTS)

Hệ thống Round P1.1 được kiểm chứng độc lập qua 7 tầng đánh giá riêng biệt:

### 3.1. Phân tầng kiểm thử (Multi-Layer Evaluation)
1. **Layer 1 - Agent Core Unit/Component Suite:** 179/182 ca kiểm thử chuẩn hóa đạt (98.35%).
   - *Ghi nhận thực tế:* 3 ca không khớp (`AC-A06`, `AC-G02`, `AC-N05`) do đề cương thật môn FIT4104 quy định tỷ trọng thi cuối kỳ là 60% (khác với con số giả lập 50% trong benchmark cũ). Hệ thống giữ nguyên tính trung thực của dữ liệu nguồn theo Điều khoản 36, từ chối hardcode để lấy điểm 100% ảo.
2. **Layer 2 - Evidence Truth Suite:** 100% đạt chuẩn.
   - `Fabricated Evidence Count = 0`.
   - `False-Positive Precision = 100%` (Tài liệu không chứa trường yêu cầu trả về đúng `INSUFFICIENT/MISSING`).
   - `Verified None Accuracy = 100%` (Nhận diện chính xác 3/3 tài liệu có tuyên bố không tiên quyết).
   - `Evidence Traceability = 100%` (100% EvidenceItem có đầy đủ `source_file`, `chunk_id`, `document_type`).
3. **Layer 3 - RAG Adapter Integration:** Hoàn toàn loại bỏ `import docx` và `_doc_cache`. Tái sử dụng ChromaDB với lọc metadata chuẩn hóa.
4. **Layer 4 - API Agent Integration:** 100% ca kiểm thử trên endpoint sống `POST /api/chat` vượt qua (câu hỏi rõ ràng, câu hỏi mơ hồ, làm rõ, thực thể lạ, dữ liệu không công bố, công cụ phủ định, an toàn bộ nhớ đệm).
5. **Layer 5 - Human-in-the-Loop Scoped Resume:** Khôi phục mục tiêu thành công sau restart qua SQLite; 0 rò rỉ chéo phiên; 0 rò rỉ chéo người dùng.
6. **Layer 6 - Hard-Gate Instrumentation:** Đo lường trên nguồn sự kiện thật:
   - `Duplicate Action Executions = 0` (Chặn thành công hành động trùng lặp).
   - `Actions After No-Progress = 0` (Dừng vòng lặp ngay khi phát hiện bế tắc tiến độ).
   - `Unsafe Tool Side Effects = 0` (Chặn 100% hành vi tạo side effect khi câu lệnh phủ định/giả định).
   - `Academic Authority Overrides = 0` (Tài liệu RAG chính thống luôn bảo toàn quyền tối thượng).
   - `Planning External API Calls = 0` (Zero Cost Policy được bảo đảm tuyệt đối).
7. **Layer 7 - Legacy Regression Suites:**
   - Router V2: 103/103 (100.00%)
   - Personal Memory V1: 60/60 (100.00%)
   - Session Memory V2: 50/50 (100.00%)
   - Utterance Semantics & Safety Gate: 375/375 (100.00%)

---

## 4. HƯỚNG DẪN BẢO TRÌ & VẬN HÀNH

1. **Cập nhật dữ liệu học vụ mới:**
   Khi có đề cương hoặc khung đào tạo mới, đưa file `.docx` vào `data_raw/` và chạy lệnh phát sinh lại danh mục:
   ```bash
   python src/agent_core/build_knowledge_env.py
   ```
   Hệ thống sẽ tự động cập nhật `runtime/knowledge_environment.json`. Không chỉnh sửa tay trong code Python.

2. **Chạy kiểm thử định kỳ:**
   ```bash
   python eval/agent_core/run_p1_1_eval.py
   ```
   Bộ kiểm thử sẽ xuất báo cáo chi tiết tại `eval/results/p1_1_eval_report.json`.

---
*Tài liệu được lưu trữ làm bài học kỹ thuật cho toàn bộ nhóm phát triển hệ thống Agentic RAG.*\n