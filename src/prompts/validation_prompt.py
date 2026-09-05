"""
Prompt kiểm tra tính trung thực (Groundedness) và đầy đủ (Completeness) của câu trả lời.
"""

VALIDATION_PROMPT = """Bạn là kiểm định viên chất lượng câu trả lời AI cho hệ thống cố vấn học tập.
Hãy đánh giá câu trả lời dựa trên Câu hỏi và Context được cung cấp.

TIÊU CHÍ ĐÁNH GIÁ:
1. Tính Trung thực (Groundedness):
   - Mọi dữ kiện thực tế trong câu trả lời (tên thầy cô, số tín chỉ, tuần học, quy chế) có được hỗ trợ bởi Context không?
   - Nếu câu trả lời chứa thông tin không có trong Context -> KHÔNG HỢP LỆ (Hallucination).
2. Xử lý thiếu dữ liệu (Sufficient Evidence):
   - Nếu Context không có thông tin và câu trả lời nêu rõ "Chưa tìm thấy đủ dữ liệu trong tài liệu hiện có để trả lời chính xác." -> HỢP LỆ (Hệ thống đã từ chối đúng).
3. Đúng trọng tâm (Relevance):
   - Câu trả lời có giải quyết đúng điều người dùng hỏi không? (Ví dụ: Hỏi giảng viên thì trả lời giảng viên, không bắt buộc phải có CLO hay mục tiêu môn học).

[Context]:
{context}

[Câu hỏi]:
{question}

[Câu trả lời cần kiểm định]:
{answer}

Hãy trả về DUY NHẤT một chuỗi JSON hợp lệ theo định dạng sau (không kèm markdown hay giải thích):
{{"valid": true}} hoặc {{"valid": false, "reason": "Lý do ngắn gọn", "missing_keywords": ["từ khóa cần bổ sung"]}}
"""
