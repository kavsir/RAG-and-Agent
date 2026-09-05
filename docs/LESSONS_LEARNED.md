# ĐÚC KẾT KINH NGHIỆM THỰC CHIẾN: XÂY DỰNG & TỐI ƯU AGENTIC RAG
## Cẩm Nang Thiết Kế Kiến Trúc, Bài Học Kỹ Thuật & Tối Ưu Hệ Thống Cho AI Academic Advisor

> **Tài liệu tổng hợp**: Tập hợp toàn bộ kinh nghiệm kỹ thuật, thất bại thực tế, giải pháp kiến trúc và bài học tối ưu từ quá trình xây dựng Trợ lý học vụ AI (AI Academic Advisor) phục vụ sinh viên Khoa Công nghệ Thông tin - Trường Đại học Đại Nam.

---

## 1. Bối Cảnh & Thách Thức Thực Tế Của Bài Toán

Xây dựng một hệ thống RAG phục vụ tư vấn học vụ đại học phức tạp hơn rất nhiều so với một chatbot hỏi-đáp tài liệu thông thường (Naive RAG). Quá trình thử nghiệm thực tế cho thấy các mô hình RAG ngây thơ thất bại ở 4 điểm mấu chốt:

1. **Nhầm lẫn giữa câu hỏi học vụ và khái niệm chung (Domain Collision)**:
   - Sinh viên hỏi: *"Điểm giống và khác nhau giữa OOP và Functional Programming?"*
   - Naive RAG quét thấy chữ *"Điểm"* &rarr; Cưỡng ép tra cứu quy chế tính điểm học tập của trường, dẫn đến câu trả lời lạc đề và ngô nghê.
2. **Ảo giác khi gặp thực thể lạ hoặc câu hỏi bẫy (Adversarial Hallucinations)**:
   - Sinh viên hỏi: *"Môn FIT7777 có bao nhiêu tín chỉ?"* (Mã môn không hề tồn tại).
   - Naive RAG tìm thấy các chunk về môn khác có chữ "tín chỉ" và tự bịa ra thông tin cho môn FIT7777 thay vì từ chối trả lời.
   - Sinh viên hỏi bẫy: *"Tôi nghe nói môn FIT4201 có 5 tín chỉ đúng không?"* &rarr; LLM bị cuốn theo giả định sai của người dùng.
3. **Mất dấu ngữ cảnh trong hội thoại nhiều lượt (Multi-turn Context Loss)**:
   - Lượt 1: *"Môn FIT4201 học về gì?"* &rarr; AI: *"Hệ thống nhúng"*.
   - Lượt 2: *"Ai dạy môn đó?"* &rarr; AI mất dấu, không biết "môn đó" là môn nào nếu chỉ quét từ khóa thô.
   - Lượt 3: *"Email của thầy là gì?"* &rarr; Hoàn toàn thất bại vì không chứa từ khóa đại từ ("môn đó").
4. **Nguy cơ ô nhiễm chân lý học vụ (Authority Conflict)**:
   - Khi sinh viên lưu thông tin cá nhân: *"Ghi nhớ giúp tôi môn FIT4201 có 5 tín chỉ nhé"*.
   - Nếu hệ thống lưu trực tiếp vào bộ nhớ cá nhân và dùng nó để trả lời, sinh viên đã vô tình làm sai lệch quy định học vụ của toàn bộ hệ thống.

Dưới đây là **6 bài học kinh nghiệm cốt lõi** được đúc kết sau khi giải quyết triệt để các bài toán trên.

---

## 2. Kinh Nghiệm 1: Định Tuyến Ý Định (Intent Routing) 0 Đồng & Độ Trễ < 1ms

### Vấn đề thường gặp: "Lạm dụng LLM làm Router"
Nhiều kiến trúc Agentic RAG mặc định đẩy câu hỏi người dùng qua một LLM (như GPT-4o-mini hay DeepSeek) kèm prompt phân loại ý định. Cách làm này gây ra 3 hệ quả nặng nề:
- **Độ trễ cao**: Mất thêm 2.000 ms - 4.000 ms chỉ để quyết định câu hỏi thuộc loại nào.
- **Tốn chi phí token**: Mỗi câu hỏi đều mất tiền API dù chỉ là một câu chào hỏi hay câu hỏi mã môn rõ ràng.
- **Không ổn định (Non-deterministic)**: LLM đôi khi trả về format JSON sai hoặc suy diễn quá đà.

### Giải pháp kiến trúc: "5-Layer Hierarchical Fast-Path + Local Semantic"

```
[ User Query ]
      │
      ▼
┌──────────────────────────────────────────────────────────┐
│ Layer 0: Strong Tool Fast Path (Regex proximity)         │ ──> TOOL_ACTION (< 0.5 ms)
└──────────────┬───────────────────────────────────────────┘
               │ (Không khớp)
               ▼
┌──────────────────────────────────────────────────────────┐
│ Layer 1: Strong Domain Fast Path (Regex mã môn, quy chế) │ ──> DOMAIN_DATA (< 0.5 ms)
└──────────────┬───────────────────────────────────────────┘
               │ (Không khớp)
               ▼
┌──────────────────────────────────────────────────────────┐
│ Layer 2: Strong General Fast Path (Greeting, CS concept) │ ──> GENERAL_LLM (< 0.5 ms)
└──────────────┬───────────────────────────────────────────┘
               │ (Không khớp)
               ▼
┌──────────────────────────────────────────────────────────┐
│ Layer 3: Local Semantic Classifier (Singleton BGE-M3)    │ ──> Cosine Sim (Margin >= 0.05)
└──────────────┬───────────────────────────────────────────┘
               │ (Margin < 0.05)
               ▼
┌──────────────────────────────────────────────────────────┐
│ Layer 4: Low-confidence Fallback Policy (Academic Bias)  │ ──> Ưu tiên bảo vệ học vụ
└──────────────────────────────────────────────────────────┘
```

### Bài học thực tế rút ra:
1. **86% Lưu lượng được giải quyết ngay ở Fast-Path**:
   - Câu hỏi có mã môn (`[A-Z]{2,4}\d{4}`), từ khóa quy chế, hoặc hành động rõ ràng (`soạn email`, `nhắc tôi`) được nhận diện ngay lập tức bằng Regex tất định với độ trễ trung bình chỉ **0.23 ms** (P95: **0.38 ms**).
2. **Cạm bẫy từ khóa ngắn trong tiếng Việt**:
   - Tìm kiếm từ khóa ngắn như `"AI"`, `"C"`, `"IT"` bằng toán tử `in` thông thường sẽ gây lỗi nghiêm trọng (chữ "AI" nằm trong "bài tập", "hái", "phải").
   - **Giải pháp**: Bắt buộc chuẩn hóa Unicode NFC và dùng regex word-boundary (`\b`):
     ```python
     re.search(r"(?<![a-zà-ỹ0-9])ai(?![a-zà-ỹ0-9])", text_lower)
     ```
3. **Tái sử dụng Singleton Embedding Model tiết kiệm 100% RAM**:
   - Khâu phân loại ngữ nghĩa cục bộ (Layer 3) không cần tải thêm mô hình mới, mà dùng chung chính đối tượng `SentenceTransformer("BAAI/bge-m3")` đã nạp trong bộ nhớ của khâu RAG. Kết quả: **0 MB RAM phụ trội, 0 đồng chi phí API**.
4. **Thiên lệch an toàn học vụ (Academic Bias)**:
   - Khi độ tương đồng ngữ nghĩa giữa miền học vụ và kiến thức chung quá sít sao, trợ lý học vụ phải ưu tiên xếp vào `DOMAIN_DATA`. Thừa tài liệu học vụ vẫn an toàn hơn việc bỏ sót quy định chính thức của trường.

---

## 3. Kinh Nghiệm 2: Xử Lý Hội Thoại Đa Lượt & Trạng Thái Phiên (Session Memory)

### Vấn đề thường gặp: "Nhồi nhét lịch sử chat (Prompt Stuffing)"
Giải pháp ngây thơ là lấy $N$ tin nhắn gần nhất nhồi vào prompt của LLM. Điều này dẫn đến:
- Prompt ngày càng dài, chi phí tăng theo cấp số nhân.
- Hiện tượng **"Lost in the Middle"**: LLM quên mất thực thể đã nhắc ở đầu phiên.
- Nếu người dùng chuyển môn học, các môn cũ vẫn ám ảnh trong prompt khiến câu trả lời bị lẫn lộn.

### Giải pháp kiến trúc: "Active Entity State Tracking trên SQLite WAL"

Thay vì lưu text thô, hệ thống duy trì một bản ghi trạng thái phiên có cấu trúc (`SessionState`):

```python
class SessionState(BaseModel):
    session_id: str
    user_id: str
    active_course_code: Optional[str] = None      # Ví dụ: "FIT4201"
    active_course_name: Optional[str] = None      # Ví dụ: "Hệ thống nhúng"
    active_domain: str = "course_detail"
    active_target: Optional[str] = None           # "lecturer" | "credits" | "assessment"
    turn_count: int = 0
    updated_at: float
```

### Bài học thực tế rút ra:
1. **Theo dõi thực thể kích hoạt (Active Entity)**:
   - Khi người dùng hỏi: *"Ai dạy môn đó?"*, hệ thống không cần hỏi lại LLM. `SessionMemoryService` kiểm tra `active_course_code` trong phiên hiện tại &rarr; Tự động bổ sung `FIT4201` vào câu truy vấn phân tích.
   - Khi người dùng đổi môn: *"Còn môn FIT4104 thì sao?"* &rarr; Lập tức cập nhật `active_course_code = "FIT4104"` (*Entity Switching*), các câu hỏi đại từ phía sau lập tức gắn với môn mới.
2. **Kế thừa mục tiêu logic (Target Carry-over)**:
   - Lượt 1: *"Ai dạy môn đó?"* &rarr; `active_target = "lecturer"`
   - Lượt 2: *"Email của thầy là gì?"* &rarr; Kế thừa mục tiêu giảng viên của môn học để tra cứu chính xác địa chỉ email.
3. **Xử lý an toàn trước đại từ mơ hồ (Ambiguous Reference Safety)**:
   - Nếu người dùng mở đầu phiên mới bằng: *"Môn đó có bao nhiêu tín chỉ?"* mà chưa hề nhắc đến môn nào trước đó, hệ thống gắn cờ `unresolved_reference = True`. Hệ thống lịch sự yêu cầu người dùng nêu rõ tên môn, **tuyệt đối không để LLM tự đoán mò**.
4. **SQLite WAL Mode cho độ trễ đọc/ghi siêu thấp**:
   - Sử dụng SQLite với chế độ Write-Ahead Logging (WAL) giúp xử lý đồng thời cực tốt giữa các luồng: độ trễ đọc P95 là **0.31 ms**, ghi P95 là **1.54 ms**, loại bỏ 100% rủi ro hỏng file JSON khi chạy thực tế.

---

## 4. Kinh Nghiệm 3: Phân Giải Thẩm Quyền Dữ Liệu (Authority Resolver)

### Vấn đề thường gặp: "Một thứ tự ưu tiên số học cho mọi miền dữ liệu"
Nếu gán độ ưu tiên chung dạng: `User Explicit (1) > System Docs (2) > Default (3)`:
- Người dùng nói: *"Tôi thích trả lời ngắn gọn"* &rarr; Đúng, hệ thống nên nghe theo người dùng.
- Người dùng nói: *"Tôi nhớ môn FIT4201 có 5 tín chỉ nhé"* &rarr; **SAI NGHIÊM TRỌNG!** Nếu nghe theo người dùng, thông tin học vụ bị sửa sai hoàn toàn.

### Giải pháp kiến trúc: "Domain-Specific Authority Model"

Thẩm quyền phân giải thông tin phải tách biệt độc lập theo từng miền nghiệp vụ:

```
A. Miền Sự Thật Học Vụ (Academic Truth):
   OFFICIAL_RAG (Tối thượng) > PERSONAL_MEMORY > SESSION_STATE
   ==> Tài liệu chính thống từ Nhà trường là duy nhất. Mọi lời nói của sinh viên
       trái với tài liệu sẽ bị RAG đính chính công khai.

B. Miền Sở Thích Cá Nhân (Personal Preferences):
   CURRENT_EXPLICIT_STATEMENT > STORED_PERSONAL_MEMORY > SYSTEM_DEFAULT
   ==> Chỉ thị trong câu hỏi hiện tại có quyền lực cao nhất để ghi đè sở thích cũ.

C. Miền Thực Thể Hội Thoại (Conversation Entities):
   CURRENT_EXPLICIT_QUERY > SESSION_STATE > PERSONAL_MEMORY
   ==> Mã môn học nói trực tiếp luôn ghi đè mã môn đang lưu trong phiên.
```

### Bài học thực tế rút ra:
1. **Từ chối tuyên bố học vụ trong Bộ nhớ cá nhân (Academic Claim Rejection)**:
   - Khi câu nói của người dùng chứa mã môn học (`FIT4201`) hoặc từ khóa quy chế (`tín chỉ`, `học phí`, `đề cương`), module chính sách bộ nhớ **từ chối lưu trữ vào Personal Memory**, bảo vệ CSDL người dùng không bị lợi dụng làm sai lệch dữ liệu.
2. **Loại bỏ triệt để Template mẫu giả định (Placeholder Rejection)**:
   - Trên giao diện thường có các giá trị mẫu như `"Sinh viên CNTT"`, `"student@dainam.edu.vn"`, `"K19"`, `"Thực hành"`.
   - Nếu di chuyển dữ liệu cũ lên SQLite mà không lọc, các giá trị giả định này sẽ biến thành "sự thật người dùng". Hệ thống bắt buộc phải kiểm tra và bỏ qua danh mục `KNOWN_PLACEHOLDER_DEFAULTS`.
3. **Tiêm ngữ cảnh tối thiểu (Minimal Context Injection)**:
   - Không nhồi toàn bộ thông tin cá nhân vào mọi câu hỏi.
   - Với câu hỏi lý thuyết thuật toán (Dijkstra, REST API): Tuyệt đối không tiêm ngành học, khóa học hay email cá nhân vào prompt.
   - Chỉ tiêm `major` và `cohort` khi người dùng hỏi các câu liên quan đến định hướng, lộ trình, hoặc kế hoạch học kỳ tới.

---

## 5. Kinh Nghiệm 4: Cá Nhân Hóa An Toàn Với Exact Cache

### Vấn đề thường gặp: "Rò rỉ câu trả lời cá nhân hóa qua Cache"
- Sinh viên A (thích phong cách ngắn gọn) hỏi: *"Môn FIT4201 là môn gì?"* &rarr; AI trả lời súc tích 20 từ. Hệ thống lưu vào `ExactCache` với key `"môn fit4201 là môn gì"`.
- Sinh viên B (cần giải thích chi tiết) hỏi câu tương tự &rarr; Cache hit &rarr; Trả về câu trả lời cụt lủn của sinh viên A!

### Giải pháp kiến trúc: "Profile Fingerprinting trong Cache Key"

```python
def _compute_profile_fingerprint(context: Dict[str, Any]) -> str:
    # Băm các thuộc tính ảnh hưởng đến phong cách và nội dung sinh
    parts = []
    if "cohort" in context:
        parts.append(f"cohort={context['cohort']}")
    if "response_style" in context:
        parts.append(f"response_style={context['response_style']}")
    return "|".join(sorted(parts))
```

Khóa cache hoàn chỉnh được kết hợp:
```
key = f"{normalized_query}::profile:{profile_fingerprint}"
# Ví dụ: "fit4201 là môn gì::profile:cohort=K19|response_style=concise"
```

### Bài học thực tế rút ra:
- Tách biệt hoàn toàn cache giữa các nhóm người dùng có hồ sơ và tùy chọn phản hồi khác nhau.
- Người dùng không có tùy chọn cá nhân hóa dùng chung `profile_fingerprint = ""` để tối đa hóa tỷ lệ cache hit cho các câu hỏi phổ quát.

---

## 6. Kinh Nghiệm 5: Phương Pháp Kiểm Thử Đối Kháng (Adversarial Benchmarking)

Để đo lường thực chất thay vì "làm đẹp số liệu", một bộ benchmark cho RAG bắt buộc phải bao gồm các ca kiểm thử mang tính đối kháng cao:

| Nhóm Kiểm Thử Đối Kháng | Mục Đích Thực Tế | Hành Vi Kỳ Vọng Chuẩn |
| :--- | :--- | :--- |
| **Thực thể không tồn tại (Unknown Entities)** | Đưa vào các mã môn giả tưởng (`FIT7777`, `SEC9001`, `CSC1010`) | Hệ thống dứt khoát từ chối (Abstention), không bịa đặt nội dung |
| **Câu hỏi sai tiền đề (Wrong-premise Questions)** | Hỏi gán ghép sai thông tin (*"FIT4201 có 5 tín chỉ đúng không?"*) | Hệ thống đính chính dứt khoát: *"Môn có 2 tín chỉ, không phải 5"* |
| **Câu hỏi không mã môn (No-code / Paraphrase)** | Hỏi bằng tên môn thông thường (*"Hệ thống nhúng học gì?"*) | Retriever bóc tách đúng thực thể ngữ nghĩa để tìm đúng tài liệu |
| **Nhiễu từ khóa (Typo / Noisy)** | Gõ không dấu, viết hoa lộn xộn (*"fit 4201", "tin chi fit4201"*) | Bộ chuẩn hóa Unicode NFC và regex bóc tách mã môn chính xác |

### Bài học thực tế về việc "Xóa Sources khi Từ Chối":
- Trong quá trình kiểm thử, một lỗi rất tinh vi xuất hiện: Khi hệ thống từ chối trả lời môn lạ (`FIT9999`), câu trả lời của AI nói rằng môn không tồn tại, **nhưng danh sách `sources` bên dưới vẫn hiển thị 5 tài liệu** do Retriever tìm kiếm tương đồng gần nhất.
- Điều này tạo cảm giác hệ thống bị "ảo giác có trích dẫn".
- **Giải pháp**: Bất kỳ khi nào đồ thị kích hoạt trạng thái từ chối (Abstention), hệ thống bắt buộc cưỡng chế `sources = []`.

---

## 7. Kinh Nghiệm 6: Kiểm Soát Chi Phí & Đo Lường Nút Thắt Hiệu Năng (Profiling)

### Nguyên tắc phân bổ tài nguyên:
- **Tác vụ cục bộ (0 đồng API, < 2 ms)**:
  - Phân loại ý định (Fast-Path Regex + BGE-M3 Semantic Cosine).
  - Quản lý trạng thái phiên và đại từ (SQLite Session State).
  - Trích xuất và kiểm tra chính sách bộ nhớ cá nhân (Regex + Whitelist Policy).
  - Tìm kiếm tài liệu lai (ChromaDB Dense + BM25 Okapi Sparse).
- **Tác vụ LLM đám mây (Có trả phí, chỉ dùng khi cần thiết)**:
  - Sinh câu trả lời có trích dẫn nguồn (Grounded Answer Generation).
  - Kiểm tra xác thực tính trung thực của câu trả lời (Factuality Validation Guardrail).

### Phân tích thời gian chạy thực tế (Runtime Profiling):
Trong một chu trình xử lý câu hỏi học vụ đầy đủ qua API:
- **Local Fast-Path Router**: `0.23 ms` (0.01% thời gian)
- **Hybrid Retrieval (Dense + BM25)**: `80 - 150 ms` (2 - 4% thời gian)
- **Local SQLite Memory Read/Write**: `< 2 ms` (0.05% thời gian)
- **DeepSeek LLM Answer Generation**: `2.500 - 4.500 ms` (80 - 90% thời gian - **Nút thắt cổ chai chính**)
- **DeepSeek LLM Factuality Validation**: `600 - 1.200 ms` (10 - 15% thời gian)

> [!TIP]
> **Đúc kết tối ưu**: Toàn bộ pipeline cục bộ của hệ thống chạy trong **dưới 180 ms**. Nút thắt hiệu năng nằm 95% ở độ trễ sinh từ của mô hình LLM từ xa. Việc tối ưu hóa Router và Memory thành công cụ cục bộ đã giúp tiết kiệm ít nhất 3.000 ms chờ đợi cho khâu định tuyến và loại bỏ hoàn toàn chi phí token không cần thiết.

---

## 8. Bảng Tổng Hợp Chỉ Số Kiểm Chứng Thực Tế

Toàn bộ các kinh nghiệm kiến trúc trên đã được kiểm chứng thực tế qua 3 bộ benchmark tự động độc lập và kiểm tra trực tiếp với DeepSeek API:

```
1. Router V2 (eval/router/run_router_eval.py):
   - Quy mô: 103 test cases (62 Benchmark V2 + 41 Holdout unseen)
   - Tỷ lệ chính xác: 103/103 (100.0%)
   - Chi phí API ngoài: 0 cuộc gọi

2. Session Memory V2 (eval/memory/run_session_eval.py):
   - Quy mô: 50 lượt chat qua 18 kịch bản đa phiên
   - Phân giải đại từ & thực thể: 50/50 (100.0%)
   - Độ trễ đọc/ghi P95: 0.31 ms / 1.54 ms
   - Chi phí API ngoài: 0 cuộc gọi

3. Personal Memory V1 (eval/memory/run_personal_eval.py):
   - Quy mô: 60 test cases trên 11 nhóm nghiệp vụ
   - Tỷ lệ đạt tiêu chuẩn: 60/60 (100.0%)
   - Độ trễ đọc/ghi P95: 0.07 ms / 1.59 ms
   - Chi phí API ngoài: 0 cuộc gọi

4. Unit Tests Hệ Thống (pytest tests/unit/ -v):
   - Kết quả: 67/67 tests passed (100.0%)
   - Linter ruff: 0 errors
```

---

## 9. 5 Nguyên Tắc Cốt Lõi Khi Làm Agentic RAG

1. **Đừng để LLM làm những việc mà giải thuật tất định làm tốt hơn và nhanh gấp 10.000 lần.**
2. **Chân lý tài liệu là tối thượng; không cho phép bộ nhớ cá nhân sửa đổi quy chế học vụ.**
3. **Theo dõi thực thể hoạt động trong phiên thay vì nhồi nhét cả dòng lịch sử vào prompt.**
4. **Cache phản hồi luôn phải băm kèm hồ sơ cá nhân hóa để tránh ô nhiễm chéo.**
5. **Kiểm thử đối kháng bằng câu hỏi bẫy và thực thể lạ mới phản ánh đúng chất lượng hệ thống.**
