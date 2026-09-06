# Tài liệu Kỹ thuật: Phân tích Khoảng trống Kiến trúc & Giới hạn Hệ thống (Architecture Gaps V3)

> **Mã Commit**: `b559599`  
> **Cập nhật ngày**: 2026-09-06T15:01:10.608385  

Tài liệu này tổng hợp toàn bộ các điểm nghẽn kiến trúc và giới hạn thiết kế được phát hiện thông qua bộ kiểm thử độ bền vững (Robustness Benchmark V3). Đây là cơ sở kỹ thuật khách quan để định hướng phát triển cho các giai đoạn tiếp theo (như Episodic Memory, Multi-Intent Decomposition, Tool Planning).

---

## 1. Danh mục Các Khoảng trống Kiến trúc (Identified Architecture Gaps)

### GAP-01: Truy vấn Đa Ý định (Multi-Intent Query Handling)
- **Mô tả hiện tượng**: Người dùng đưa ra câu lệnh kết hợp giữa tra cứu kiến thức miền và hành động công cụ, hoặc câu hỏi kiến thức chung và dữ liệu học vụ.
- **Ví dụ tiêu biểu**:
  - `Cho tôi biết giảng viên dạy FIT4201 và lên lịch nhắc nhở tôi ôn thi vào ngày mai.` (DOMAIN_DATA + TOOL_ACTION)
  - `Thuật toán Dijkstra là gì và môn FIT4201 có dạy thuật toán này không?` (GENERAL_LLM + DOMAIN_DATA)
- **Giới hạn kiến trúc hiện tại**: Router V2 được thiết kế theo mô hình phân loại đơn nhãn (Single-label Decision Tree + Fallback). Hệ thống chỉ kích hoạt một nhánh thực thi duy nhất trong đồ thị LangGraph.
- **Giải pháp kiến trúc khuyến nghị**: Nâng cấp Router V2 thành **Intent Decomposition Node**, cho phép bóc tách truy vấn thành đồ thị con gồm nhiều task song song hoặc tuần tự.

### GAP-02: Theo dõi Đa Thực thể Trong So sánh (Multi-Entity State Tracking)
- **Mô tả hiện tượng**: Người dùng so sánh 2 hoặc nhiều môn học trong cùng một lượt thoại.
- **Ví dụ tiêu biểu**:
  - `So sánh độ khó và số tín chỉ giữa FIT4201 và FIT4104.`
  - Lượt kế tiếp: `Môn thứ hai có bắt buộc làm đồ án không?`
- **Giới hạn kiến trúc hiện tại**: `SessionState.active_course_code` là một trường chuỗi đơn lẻ (`Optional[str]`). Môn được nhận diện sau sẽ ghi đè môn trước, làm mất ngữ cảnh đối sánh ở lượt hỏi tiếp nối.
- **Giải pháp kiến trúc khuyến nghị**: Mở rộng `SessionState` hỗ trợ `active_entities: List[EntityRecord]` kèm vai trò ngữ cảnh (`primary`, `secondary`, `compared`).

### GAP-03: Nhận diện Mã môn học Không tồn tại (Non-existent Course Code Detection)
- **Mô tả hiện tượng**: Người dùng nhập mã môn học có định dạng hợp lệ (3 chữ cái + 4 số) nhưng không có trong chương trình đào tạo (ví dụ: `ABC9999`, `XYZ1234`).
- **Giới hạn hiện tại**: Bộ phân tích `analyze_query` trích xuất thành công regex nhưng chưa đối chiếu với danh mục môn học hợp lệ trước khi chuyển sang RAG. Khi RAG không tìm thấy tài liệu, hệ thống phụ thuộc vào prompt từ chối của LLM.
- **Giải pháp kiến trúc khuyến nghị**: Bổ sung bộ lọc hợp lệ danh mục môn học (`CourseCatalogValidator`) tại tầng `query_analyzer` để trả lời nhanh mà không cần tốn tài nguyên RAG/LLM.

### GAP-04: Xử lý Câu hỏi Giả định (Counterfactual / Hypothetical Reasoning)
- **Mô tả hiện tượng**: Người dùng đặt câu hỏi giả định trái ngược với quy định đào tạo ('Nếu trường đổi FIT4201 thành 5 tín chỉ thì sao?').
- **Giới hạn hiện tại**: Router phân loại vào `DOMAIN_DATA`, RAG tìm tài liệu quy chế và trả lời quy chế hiện tại, nhưng chưa giải thích rõ ràng khía cạnh giả định.
- **Giải pháp kiến trúc khuyến nghị**: Bổ sung cờ `is_hypothetical` vào `AnalyzedQuery` để hướng dẫn LLM phân định giữa sự thật hiện hành và ngữ cảnh giả định.

---

## 2. Bảng Thống kê Tần suất Xuất hiện Gaps

| Mã Gap | Tên Giới hạn | Tần suất trong Robustness V3 | Mức độ Ảnh hưởng | Hướng xử lý |
|---|---|:---:|:---:|---|
| `GAP-01` | Multi-Intent Decomposition | 16 cases | Cao | Kế hoạch Agentic Planner |
| `GAP-02` | Multi-Entity Comparison | 12 cases | Trung bình | Kế hoạch Session Memory V3 |
| `GAP-03` | Non-existent Course Catalog | 8 cases | Thấp | Bổ sung Catalog Validator |
| `GAP-04` | Hypothetical Query Flag | 6 cases | Thấp | Cập nhật AnalyzedQuery |
