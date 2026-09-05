"""
Intent Prototypes: Tập hợp các mẫu câu tự nhiên tiêu chuẩn (prototypes) đại diện cho
các nhóm ý định DOMAIN_DATA, GENERAL_LLM, TOOL_ACTION phục vụ phân loại ngữ nghĩa cục bộ.
Không mã hóa cứng các câu hỏi cụ thể từ tập benchmark.
"""
from typing import Dict, List
from src.router.schemas import IntentCategory

DOMAIN_PROTOTYPES: List[str] = [
    "Môn học này có bao nhiêu tín chỉ lý thuyết và thực hành?",
    "Điều kiện tiên quyết để được đăng ký học phần này là gì?",
    "Hình thức kiểm tra đánh giá điểm chuyên cần giữa kỳ và thi kết thúc học phần như thế nào?",
    "Ai là giảng viên phụ trách bộ môn và địa chỉ email liên hệ là gì?",
    "Chuẩn đầu ra CLO và mục tiêu đào tạo của học phần này gồm những gì?",
    "Kế hoạch giảng dạy chi tiết theo từng tuần và nội dung bài học ra sao?",
    "Quy chế đào tạo về cảnh báo học vụ, thôi học và xếp loại học lực của nhà trường",
    "Chương trình đào tạo ngành công nghệ thông tin gồm những môn học nào trong từng học kỳ?",
    "Điều kiện và số tín chỉ tích lũy tối thiểu để sinh viên đủ điều kiện xét tốt nghiệp",
    "Đề cương chi tiết học phần và tài liệu học tập tham khảo bắt buộc của môn học",
    "Môn học này thuộc khối kiến thức cơ sở ngành hay chuyên ngành?",
    "Sinh viên bị điểm F thì quy định học lại và thi lại của trường tính như thế nào?",
]

GENERAL_PROTOTYPES: List[str] = [
    "Khái niệm định nghĩa và nguyên lý hoạt động của thuật toán là gì?",
    "Điểm khác biệt cơ bản giữa hai công nghệ hoặc giao thức mạng này là gì?",
    "Giải thích cách thức hoạt động, kiến trúc hệ thống và luồng xử lý dữ liệu",
    "So sánh ưu điểm và nhược điểm của các giải pháp kỹ thuật phần mềm",
    "Trình bày các nguyên lý thiết kế và đặc tính cốt lõi trong lập trình hướng đối tượng",
    "Hướng dẫn cách viết hàm và cú pháp xử lý logic cơ bản bằng ngôn ngữ lập trình",
    "Tại sao lại cần sử dụng mô hình kiến trúc vi dịch vụ trong phát triển ứng dụng?",
    "Tổng quan về điện toán đám mây, trí tuệ nhân tạo và các mô hình dịch vụ phổ biến",
    "Sự khác biệt giữa thread và process trong hệ điều hành máy tính là gì?",
    "RESTful API hoạt động theo nguyên tắc nào và các phương thức HTTP chuẩn gồm những gì?",
    "Giải thích cách thức quản lý bộ nhớ và cơ chế garbage collection",
    "Cách tối ưu hóa độ phức tạp thời gian và không gian của một thuật toán tìm kiếm",
]

TOOL_PROTOTYPES: List[str] = [
    "Soạn giúp tôi một bức email gửi cho giảng viên phụ trách để xin phép nghỉ học",
    "Gửi email đến phòng đào tạo hoặc thầy cô để xin tài liệu bài giảng và đề cương",
    "Viết thư điện tử gửi văn phòng khoa trình bày lý do xin hoãn nộp bài tập lớn",
    "Soạn email xin phúc khảo điểm thi kết thúc học phần gửi bộ môn",
    "Nhắc tôi ôn bài và xem lại tài liệu học tập vào lúc tám giờ tối ngày mai",
    "Đặt lịch nhắc nhở nộp bài tập lớn và đồ án trước hạn chót tuần sau",
    "Hẹn giờ báo deadline nộp bài kiểm tra giữa kỳ vào hệ thống quản lý học tập",
    "Lên lịch hẹn nhắc nhở tham gia buổi hướng dẫn đồ án tốt nghiệp",
    "Gửi thư điện tử trao đổi công việc và thảo luận nhóm về dự án phần mềm",
    "Đặt báo thức và nhắc lịch học bù môn học vào sáng chủ nhật tuần này",
]

INTENT_PROTOTYPES: Dict[IntentCategory, List[str]] = {
    "DOMAIN_DATA": DOMAIN_PROTOTYPES,
    "GENERAL_LLM": GENERAL_PROTOTYPES,
    "TOOL_ACTION": TOOL_PROTOTYPES,
}
