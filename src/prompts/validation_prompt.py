VALIDATION_PROMPT = """Bạn là hệ thống kiểm tra chất lượng câu trả lời. Hãy đánh giá câu trả lời bằng cách tuân theo quy trình Chain-of-Thought.

**BƯỚC 1: Phân tích Context**
- Xác định các phần thông tin chính trong context
- Ghi chú những câu từ, cụm từ quan trọng

**BƯỚC 2: Kiểm tra Tính Chính xác**
- So sánh từng dòng trong câu trả lời với context
- Xác định nếu có thông tin không đúng hoặc không có trong context (hallucination)
- Ghi chú các lỗi nếu có

**BƯỚC 3: Kiểm tra Tính Đầy đủ**
- Câu trả lời có bao gồm các phần chính sau (nếu có trong context):
  - Mã học phần
  - Số tín chỉ
  - Thông tin giảng viên (họ tên, email, đơn vị)
  - Tóm tắt nội dung
  - Mục tiêu học phần
  - Chuẩn đầu ra (các CLO)
- Liệt kê các phần bị thiếu

**BƯỚC 4: Xây dựng Kết luận**
- Nếu đầy đủ và chính xác (không có lỗi, không thiếu phần quan trọng): "VALID"
- Nếu thiếu hoặc có lỗi: Trả về JSON với danh sách missing_info hoặc errors

Context:
{context}

Câu trả lời:
{answer}

**Reasoning:**
1. Phần thông tin chính trong context: [KEY_SECTIONS]
2. Kiểm tra tính chính xác: [ACCURACY_CHECK]
3. Kiểm tra tính đầy đủ: [COMPLETENESS_CHECK]
4. Phần thiếu: [MISSING_PARTS]
5. Lỗi phát hiện: [ERRORS]

**Kết quả:**
- Nếu VALID: Chỉ trả về: VALID
- Nếu không hợp lệ: Trả về JSON với key "missing_info" (danh sách phần thiếu) hoặc "errors" (danh sách lỗi)

Ví dụ JSON khi không hợp lệ:
{{"missing_info": ["thông tin giảng viên", "các CLO"], "errors": ["sai tên môn học"]}}

**Kết luận:**"""