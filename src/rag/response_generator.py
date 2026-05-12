# response_generator.py
from src.config.groq_gateway import invoke_llm
from typing import List, Dict, Any
def generate_response(query: str, retrieved_docs: List[Dict[str, Any]], student_profile: dict = None) -> str:
    # Xây dựng context
    context = "\n\n".join([
        f"[{doc['metadata'].get('source_file', 'Unknown')} - {doc['metadata'].get('week', '')}]\n{doc['text']}"
        for doc in retrieved_docs
    ])
    
    profile_info = ""
    if student_profile:
        profile_info = f"""
        Thông tin sinh viên:
        - Năm học: {student_profile.get('year', 'Chưa rõ')}
        - Chuyên ngành: {student_profile.get('major', 'CNTT')}
        - GPA: {student_profile.get('gpa', 'Chưa có')}
        """
    
    system_prompt = """Bạn là trợ lý cố vấn học tập cho sinh viên khoa CNTT, Trường Đại học Đại Nam.
    Hãy trả lời câu hỏi dựa trên các tài liệu được cung cấp bên dưới.
    Nếu câu hỏi liên quan đến thông tin cá nhân của sinh viên, hãy sử dụng thông tin profile (nếu có).
    Nếu không tìm thấy câu trả lời trong tài liệu, hãy nói rằng bạn không có đủ thông tin và đề nghị sinh viên liên hệ phòng đào tạo hoặc cố vấn học tập.
    Trả lời bằng tiếng Việt, thân thiện và chính xác."""
    
    user_prompt = f"""
    {profile_info}
    
    Tài liệu tham khảo:
    {context}
    
    Câu hỏi: {query}
    
    Câu trả lời:"""
    
    # Gọi LLM
    full_prompt = f"{system_prompt}\n\n{user_prompt}"
    answer = invoke_llm(full_prompt, temperature=0.2)
    return answer