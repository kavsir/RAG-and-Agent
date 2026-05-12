import json
from src.config.groq_gateway import invoke_llm

PROMPT = """
Extract student information from the message.

Return ONLY a valid JSON object with the following fields:
- name: the student's name (if mentioned)
- major: the student's major (if mentioned)
- cohort: the student's cohort (if mentioned, e.g., K19)
- style: any learning style (if mentioned)
- email: the student's email address (if mentioned)

If a field is not mentioned, set its value to null. Do not include any other text, explanation, or code.

Examples:
- Message: "Tên tôi là Nguyễn Văn A, học CNTT" -> {{"name": "Nguyễn Văn A", "major": "CNTT", "cohort": null, "style": null, "email": null}}
- Message: "tôi là Phong" -> {{"name": "Phong", "major": null, "cohort": null, "style": null, "email": null}}
- Message: "Email của tôi là abc@gmail.com" -> {{"name": null, "major": null, "cohort": null, "style": null, "email": "abc@gmail.com"}}
- Message: "Mình là Phong, sinh viên K19 ngành IoT, email phong@example.com" -> {{"name": "Phong", "major": "IoT", "cohort": "K19", "style": null, "email": "phong@example.com"}}

Message: {message}

JSON:
"""

def extract_profile(message):
    prompt = PROMPT.format(message=message)
    result = invoke_llm(prompt)
    # Loại bỏ các dấu hiệu markdown nếu có
    result = result.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(result)
    except Exception as e:
        print(f"Lỗi parse JSON: {e}, raw result: {result}")
        return {}