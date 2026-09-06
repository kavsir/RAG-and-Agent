"""
Robustness Benchmark V3 Generators: Các bộ sinh dữ liệu tất định phục vụ Property-Based Testing và Fuzzing.
"""
import random
from typing import List, Dict, Any, Set
from eval.robustness.invariants import KNOWN_COURSE_CODES


def generate_unknown_course_codes(seed: int = 20260906, count: int = 300) -> List[str]:
    """
    Sinh tất định danh sách mã môn học giả mạo (không tồn tại trong hệ thống đào tạo).
    Kiểm tra đối chiếu với KNOWN_COURSE_CODES để tuyệt đối không trùng với mã môn thật.
    """
    rng = random.Random(seed)
    prefixes = ["FIT", "SE", "CS", "AI", "IT", "MAT", "ENG", "XYZ", "ABC", "DNTU"]
    generated: Set[str] = set()

    while len(generated) < count:
        pref = rng.choice(prefixes)
        num = rng.randint(1000, 9999)
        code = f"{pref}{num}"
        if code not in KNOWN_COURSE_CODES:
            generated.add(code)

    return sorted(list(generated))


def generate_boundary_inputs() -> List[Dict[str, Any]]:
    """
    Sinh các đầu vào dị biệt ở biên (Empty, Whitespace, Newlines, Huge Strings, Control Characters).
    """
    return [
        {"id": "BOUND-01", "name": "empty_string", "text": ""},
        {"id": "BOUND-02", "name": "single_space", "text": " "},
        {"id": "BOUND-03", "name": "multiple_spaces", "text": "          "},
        {"id": "BOUND-04", "name": "newlines_only", "text": "\n\n\n\n\n"},
        {"id": "BOUND-05", "name": "mixed_whitespace", "text": "  \t  \r\n  \t  "},
        {"id": "BOUND-06", "name": "single_char_letter", "text": "a"},
        {"id": "BOUND-07", "name": "single_char_punct", "text": "?"},
        {"id": "BOUND-08", "name": "single_char_digit", "text": "1"},
        {"id": "BOUND-09", "name": "control_null_byte", "text": "Môn FIT4201\x00 có bao nhiêu tín chỉ?"},
        {"id": "BOUND-10", "name": "control_escape_chars", "text": "\x1b[31mMôn FIT4201\x1b[0m tín chỉ?"},
        {"id": "BOUND-11", "name": "repeated_char_1kb", "text": "A" * 1024},
        {"id": "BOUND-12", "name": "repeated_word_4kb", "text": ("tín chỉ " * 500)[:4096]},
        {"id": "BOUND-13", "name": "large_text_16kb", "text": ("Môn FIT4201 có bao nhiêu tín chỉ? " * 500)[:16384]},
        {"id": "BOUND-14", "name": "huge_text_64kb", "text": ("Học kỳ tới tôi nên học những môn gì trong chương trình? " * 1200)[:65536]},
    ]


def generate_interleaved_session_chaos(count: int = 100, seed: int = 20260906) -> List[Dict[str, Any]]:
    """
    Sinh 100 lượt hội thoại đan xen ngẫu nhiên giữa 3 phiên độc lập:
    - Session Alpha: ngữ cảnh FIT4201
    - Session Beta: ngữ cảnh FIT3101
    - Session Gamma: ngữ cảnh FIT4104
    Đo lường tính bất biến cô lập phiên (Session Isolation Invariant).
    """
    rng = random.Random(seed)
    sessions = {
        "sess-alpha": {"active": "FIT4201", "name": "Hệ thống nhúng"},
        "sess-beta": {"active": "FIT3101", "name": "Lập trình Web"},
        "sess-gamma": {"active": "FIT4104", "name": "Full-Stack"},
    }

    turns = []
    sess_keys = list(sessions.keys())

    # Khởi tạo mỗi phiên 1 câu hỏi định danh môn
    for sid, sinfo in sessions.items():
        turns.append({
            "session_id": sid,
            "query": f"Môn {sinfo['active']} có bao nhiêu tín chỉ?",
            "expected_active_entity": sinfo["active"],
            "type": "INITIALIZE",
        })

    # Các lượt tiếp theo đan xen
    followup_templates = [
        "Email thì sao?",
        "Ai phụ trách môn này?",
        "Môn đó có mấy tín chỉ?",
        "Có thực hành không?",
        "Đề cương chi tiết thế nào?",
        "Dijkstra là gì?",
        "asdf ???",
        "Chào bot",
    ]

    while len(turns) < count:
        sid = rng.choice(sess_keys)
        template = rng.choice(followup_templates)
        expected_entity = sessions[sid]["active"]
        turns.append({
            "session_id": sid,
            "query": template,
            "expected_active_entity": expected_entity,
            "type": "INTERLEAVED_TURN",
        })

    return turns
