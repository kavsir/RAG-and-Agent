# ADR-001: Layered Routing Architecture & Proximity-Based Tool Intent Detection

- **Status**: PROPOSED
- **Date**: 2026-09-06
- **Author**: AI Architecture Team / Agentic RAG
- **Component**: `src/agent/nodes.py` (`router_node`), `src/rag/query_analyzer.py`

---

## 1. Context (Bối Cảnh)

Hệ thống AI Academic Advisor phục vụ sinh viên Khoa CNTT, Đại học Đại Nam cần phân luồng chính xác giữa 3 nhóm nghiệp vụ chính:
1. `DOMAIN_DATA`: Tra cứu học phần, chương trình đào tạo, quy chế học vụ qua RAG.
2. `GENERAL_LLM`: Trả lời kiến thức khoa học máy tính chung, lập trình, giải thuật hoặc chào hỏi.
3. `TOOL_ACTION`: Thực thi tác vụ hỗ trợ sinh viên (đặt lịch nhắc nhở `SET_REMINDER`, soạn email `SEND_EMAIL`).

Tại Benchmark V2 đối kháng (62 test cases), Router đạt **95.16%** (59/62 cases). Tuy nhiên, phân tích nghiệm thu xác nhận **3/8 ca thất bại** bắt nguồn từ khâu định tuyến (`v2-gen-02`, `v2-gen-03`, `v2-gen-05`) và **1 ca** do nhận diện công cụ (`v2-tool-04`).

---

## 2. Current Architecture (Kiến Trúc Hiện Tại)

Hiện tại, `router_node` thực thi tuần tự theo chuỗi heuristic đơn tầng:
1. **Kiểm tra Tool Heuristic**: Quét chuỗi con tuyệt đối (exact substring):
   `["nhắc tôi", "nhắc lịch", "hẹn giờ", "báo lịch", "đặt lịch nhắc"]` và `["gửi email", "gửi mail", "soạn email", "send email"]`.
2. **Kiểm tra Domain Heuristic**:
   `has_course_code or has_domain_target or has_domain_kw`
   Trong đó:
   - `has_course_code`: Trích xuất từ regex mã môn (`[A-Z]{3,4}\d{4}`).
   - `has_domain_target`: Trích xuất từ `TARGET_KEYWORDS` của `query_analyzer.py` (chứa các từ đơn như `"điểm"`, `"thi"`, `"học"`, `"kế hoạch"`).
   - `has_domain_kw`: Quét danh sách 18 từ khóa học vụ tĩnh.
3. **Kiểm tra General Heuristic**: Quét danh sách tĩnh 10 từ khóa (`dijkstra`, `python`, `java`, `sql`, `git`, `rest api`...).
4. **Fallback LLM**: Nếu trượt cả 3 bước trên, gọi prompt phân loại LLM với fallback mặc định về `DOMAIN_DATA`.

---

## 3. Problem Statement & Root Cause Analysis (Vấn Đề & Nguyên Nhân Gốc Rễ)

Kiến trúc hiện tại có 3 khiếm khuyết cơ bản:
1. **Ô nhiễm Target từ Query Analyzer (Target Contamination)**:
   - Từ khóa `"điểm"` nằm trong mục tiêu `assessment` của `query_analyzer.py`.
   - Khi người dùng hỏi: *"Điểm khác biệt cơ bản giữa giao thức TCP và UDP là gì?"* (`v2-gen-03`), bộ bóc tách gán `targets = ["assessment"]`.
   - `router_node` kiểm tra `has_domain_target = True` và lập tức điều hướng sang `DOMAIN_DATA` trước khi đến bộ lọc General!
2. **Thứ tự ưu tiên cứng nhắc (Ordering Flaw) & Danh sách tĩnh hạn hẹp**:
   - Bước kiểm tra `DOMAIN_DATA` đứng trước `GENERAL_LLM`. Các câu hỏi giải thuật phổ biến như QuickSort (`v2-gen-02`) không có trong danh sách 10 từ khóa tĩnh, rơi vào LLM fallback và bị ép về `DOMAIN_DATA`.
   - Câu hỏi công nghệ mang tính khái niệm chung như *"Cloud computing là gì?"* (`v2-gen-05`) trùng với tên môn học *"Công nghệ điện toán đám mây"*, dẫn đến xung đột ranh giới.
3. **Khớp chuỗi công cụ thiếu linh hoạt (Rigid Substring Matching)**:
   - Câu lệnh: *"Soạn giúp tôi email xin hoãn nộp bài tập lớn..."* (`v2-tool-04`) chứa từ `"Soạn"` và `"email"` nhưng bị xen giữa bởi `"giúp tôi"`, dẫn đến không khớp chuỗi tĩnh `"soạn email"`.

---

## 4. Options Considered (Các Phương Án Cân Nhắc)

### Phương án A: Thêm thủ công các từ khóa thất bại vào danh sách tĩnh
- *Mô tả*: Thêm `"quicksort"`, `"soạn giúp tôi email"` vào list.
- *Đánh giá*: **BÁC BỎ (REJECT)**. Đây là hành vi *benchmark overfitting*, vi phạm nguyên tắc thiết kế. Hệ thống sẽ tiếp tục gãy khi gặp MergeSort, HeapSort hoặc *"Nhờ bạn viết thư..."*.

### Phương án B: Chuyển 100% việc định tuyến cho LLM phân loại
- *Mô tả*: Bỏ toàn bộ heuristic, mọi câu hỏi đều gọi LLM để phân loại intent.
- *Đánh giá*: **BÁC BỎ (REJECT)**. Làm tăng độ trễ thêm 3 - 5 giây cho mỗi truy vấn, tốn chi phí token không đáng có, và giảm độ tin cậy của các trường hợp có mã môn rõ ràng (`FIT4201`).

### Phương án C: Kiến trúc Định tuyến Phân tầng có Điều kiện (Layered Router Architecture) — *ĐƯỢC CHỌN*
- *Mô tả*: Xây dựng Router 4 tầng với nguyên tắc: Dấu hiệu thực thể mạnh & công cụ &rarr; Ngữ cảnh kỹ thuật chung &rarr; Ngữ cảnh học vụ gắn kết thực thể &rarr; LLM Ambiguity Resolver.

---

## 5. Decision Proposal (Đề Xuất Quyết Định)

Áp dụng mô hình **Layered Routing Policy** phân cấp:

```
Input Query
    │
    ▼
[Layer 0: Tool Intent Engine] ──(Khớp Proximity Action-Object)──► TOOL_ACTION
    │ (Không khớp)
    ▼
[Layer 1: Strong Explicit Domain Evidence] ──(Có mã môn hoặc quy chế ĐN)──► DOMAIN_DATA
    │ (Không có mã môn / trường từ học vụ Đại Nam)
    ▼
[Layer 2: Strong Technical & General Intent] ──(Giải thích thuật ngữ, CS)──► GENERAL_LLM
    │ (Không phải câu hỏi kỹ thuật thuần túy)
    ▼
[Layer 3: Target-Entity Co-occurrence Validation] ──(Target gắn với Học vụ)──► DOMAIN_DATA
    │ (Target độc lập, ngôn ngữ tự nhiên chung)
    ▼
[Layer 4: Balanced Semantic LLM Fallback] ──(Định tuyến ngữ nghĩa)──► DOMAIN / GENERAL
```

### Quy tắc chi tiết từng tầng:

1. **Layer 0 (Tool Proximity Intent)**:
   - Dùng mẫu quy tắc khoảng cách từ:
     `ACTION_TOKENS = ["soạn", "gửi", "viết", "draft", "send", "nhắc", "hẹn", "báo", "đặt lịch"]`
     `OBJECT_TOKENS = ["email", "mail", "thư", "lịch", "giờ", "hạn", "deadline", "bài tập", "thi"]`
   - Bắt mẫu: `r"(soạn|gửi|viết|draft)\b.{0,25}\b(email|mail|thư)"` &rarr; `TOOL_ACTION (SEND_EMAIL)`.
   - Bắt mẫu: `r"(nhắc|hẹn|đặt lịch|báo)\b.{0,25}\b(tôi|lịch|ôn thi|nộp|deadline|giờ)"` &rarr; `TOOL_ACTION (SET_REMINDER)`.

2. **Layer 1 (Strong Domain Evidence)**:
   - Nếu có `course_code` chuẩn (regex `[A-Z]{3,4}\d{4}`) &rarr; 100% `DOMAIN_DATA`.
   - Nếu chứa cụm từ cơ quan/quy chế riêng biệt: `"đại học đại nam"`, `"khoa cntt"`, `"quy chế đào tạo"`, `"chuẩn đầu ra clo"` &rarr; `DOMAIN_DATA`.

3. **Layer 2 (Strong General Concepts)**:
   - Nhận diện mẫu câu hỏi khái niệm công nghệ: *"là gì"*, *"nguyên lý hoạt động"*, *"so sánh khác biệt giữa A và B"*, *"cách cài đặt"*, *"thuật toán"*, *"giao thức"*.
   - Nếu câu hỏi dạng này KHÔNG đi kèm mã môn học hoặc từ khóa Đại Nam &rarr; `GENERAL_LLM`.
   - Khắc phục triệt để `v2-gen-02` (QuickSort) và `v2-gen-03` (TCP vs UDP).

4. **Layer 3 (Target-Entity Co-occurrence)**:
   - Sửa lỗi ô nhiễm: Từ `"điểm"` chỉ kích hoạt `DOMAIN_DATA` nếu đi kèm với `"môn"`, `"học phần"`, `"tín chỉ"`, `"chuyên cần"` hoặc mã môn. Từ `"điểm"` trong cụm `"điểm khác biệt"`, `"ưu điểm"`, `"nhược điểm"` bị loại trừ (blacklist filter).
   - Với `"Cloud computing là gì?"`: Nếu câu hỏi không hỏi số tín chỉ, giảng viên hay mã môn mà chỉ hỏi định nghĩa và mô hình &rarr; `GENERAL_LLM`.

---

## 6. Consequences & Impact (Hệ Quả & Tác Động)

- **Tích cực**:
  - Giải quyết dứt điểm 4/4 ca lỗi định tuyến trong Benchmark V2 mà không cần hardcode câu hỏi.
  - Tăng Router Accuracy từ **95.16% lên &ge; 98.0%**.
  - Không làm tăng latency cục bộ (< 1ms cho toàn bộ 4 tầng logic).
- **Tiêu cực**:
  - Logic phân luồng nhiều điều kiện hơn, đòi hỏi kiểm thử unit test chặt chẽ cho từng tầng.

---

## 7. Metrics to Validate (Chỉ Số Kiểm Định Sau Khi Áp Dụng)

1. `Router Accuracy`: $\ge 96.0\%$ trên Benchmark V2.
2. `General Category Accuracy`: $\ge 90.0\%$ (hiện tại 40.0% do 3 ca lỗi).
3. `Tool Category Accuracy`: $100.0\%$ (hiện tại 80.0%).
4. Không làm suy giảm `Domain Category Accuracy` (giữ vững $\ge 95\%$).

---

## 8. Rollback Strategy (Chiến Lược Hoàn Tác)

Nếu layer mới gây sai lệch cho các câu hỏi học vụ có sẵn:
- Khôi phục hàm `router_node` nguyên bản từ commit baseline `4cf04cc`.
- Cấu hình cờ chuyển đổi tính năng `FEATURE_LAYERED_ROUTER=true/false` trong `settings.py`.
