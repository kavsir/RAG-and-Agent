from src.rag.query_analyzer import analyze_query, extract_regex_entities, resolve_conversational_query


def test_extract_course_code():
    extracted = extract_regex_entities("Môn FIT4201 có mấy tín chỉ?")
    assert extracted["course_code"] == "FIT4201"
    assert "credits" in extracted["targets"]


def test_extract_lecturer_target():
    extracted = extract_regex_entities("Ai là giảng viên phụ trách môn Hệ thống nhúng?")
    assert "lecturer" in extracted["targets"]


def test_conversational_query_resolution():
    history = "User: FIT4201 là môn gì?\nAI: FIT4201 là môn Hệ thống nhúng."
    resolved = resolve_conversational_query("môn đó có bao nhiêu tín chỉ?", chat_history=history)
    assert "FIT4201" in resolved


def test_analyze_query_domain_regulation():
    q = analyze_query("Điều kiện xét tốt nghiệp ra trường là gì?")
    assert q.domain == "regulation"
    assert "graduation_requirement" in q.targets or "regulation" in q.targets


def test_analyze_query_domain_curriculum():
    q = analyze_query("Khung chương trình đào tạo ngành CNTT K19 gồm những môn nào?")
    assert q.domain == "curriculum"
    assert q.cohort == "K19"
