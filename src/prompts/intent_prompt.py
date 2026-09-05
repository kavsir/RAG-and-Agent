"""
Prompt phân loại Intent người dùng thành 3 nhóm chính:
- DOMAIN_DATA: Dữ liệu nội bộ trường/khoa (môn học, đề cương, CTĐT, quy chế) -> RAG
- GENERAL_LLM: Kiến thức lập trình, thuật toán chung, chào hỏi -> Trả lời trực tiếp
- TOOL_ACTION: Đặt lịch nhắc (SET_REMINDER) hoặc Soạn/Gửi email (SEND_EMAIL)
"""

INTENT_ROUTER_PROMPT = """Bạn là trợ lý phân loại ý định câu hỏi của sinh viên Khoa CNTT, Trường Đại học Đại Nam.
Hãy phân tích câu hỏi sau và xác định chính xác nó thuộc nhóm nào:

1. DOMAIN_DATA:
   - Các câu hỏi liên quan đến thông tin nội bộ của trường/khoa/học phần:
   - Mã học phần, số tín chỉ, giảng viên, chuẩn đầu ra (CLO), mục tiêu học phần, kế hoạch giảng dạy từng tuần, lịch học, lịch thi, đề cương.
   - Chương trình đào tạo theo khóa (K19, K18...), danh sách môn theo học kỳ.
   - Quy chế đào tạo tín chỉ, điều kiện tốt nghiệp, cảnh báo học vụ, điểm rèn luyện.
   - Dấu hiệu: Có mã môn (FIT...), tên môn, chữ "tín chỉ", "CLO", "giảng viên", "quy chế", "học kỳ", "học phần".

2. GENERAL_LLM:
   - Các câu hỏi kiến thức công nghệ chung, thuật toán, lập trình tổng quát:
   - "Dijkstra là gì?", "Python decorator hoạt động thế nào?", "Giải thích REST API", "Git là gì?".
   - Chào hỏi giao tiếp thông thường: "Xin chào", "Bạn là ai", "Cảm ơn bạn".
   - Không chứa yêu cầu tra cứu tài liệu học vụ cụ thể của Đại học Đại Nam.

3. TOOL_ACTION:
   - SET_REMINDER: Yêu cầu đặt lịch nhắc nhở, hẹn giờ, báo lịch thi/học.
     (Ví dụ: "Nhắc tôi ôn thi ngày 20/12", "Nhắc tôi nộp bài tập trước 2 ngày")
   - SEND_EMAIL: Yêu cầu gửi email thông báo, chúc mừng, xin phép.
     (Ví dụ: "Gửi email xin nghỉ học cho thầy...", "Gửi mail chúc mừng sinh nhật...")

Câu hỏi: {question}

Hãy trả về DUY NHẤT một chuỗi JSON hợp lệ theo cấu trúc sau (không kèm markdown, không giải thích):
{{"category": "DOMAIN_DATA" | "GENERAL_LLM" | "TOOL_ACTION", "tool_intent": "SET_REMINDER" | "SEND_EMAIL" | null}}
"""
