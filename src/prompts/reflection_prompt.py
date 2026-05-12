REFLECTION_PROMPT = """
Kiểm tra câu trả lời có dựa trên context không.

Context:
{context}

Answer:
{answer}

Nếu câu trả lời không dựa vào context hãy nói:
"Không đủ thông tin".

Kết quả:
"""