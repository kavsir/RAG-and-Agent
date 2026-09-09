"""
Acronym Disambiguator (Round UX2):
Detects ambiguous technical acronyms in short general queries (e.g. "thuật toán dpf", "dpf là gì")
where confident single-meaning hallucination would harm student learning.
Instead of guessing, asks clarification first.
"""
import re
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class DisambiguationResult:
    is_ambiguous: bool
    acronym: Optional[str] = None
    clarification_question: Optional[str] = None
    clarification_options: List[str] = field(default_factory=list)


AMBIGUOUS_ACRONYMS: Dict[str, Dict[str, Any]] = {
    "dpf": {
        "meanings": [
            "**Distributed Point Function** (Hàm phân tán điểm trong Mật mã học / Tính toán an toàn nhiều bên MPC)",
            "**Directional Preference Function** (Hàm ưu tiên định hướng trong Tối ưu hóa đa mục tiêu / Học tăng cường RL)",
        ],
        "options": [
            "Distributed Point Function (Mật mã / MPC)",
            "Directional Preference Function (Tối ưu / RL)",
        ],
        "context_keywords": ["mật mã", "mpc", "crypto", "pir", "tối ưu", "rl", "học tăng cường", "hàm"],
    },
    "dfa": {
        "meanings": [
            "**Deterministic Finite Automaton** (Otomat hữu hạn đơn định trong Lý thuyết tính toán / Trình biên dịch)",
            "**Design For Assembly** (Thiết kế để lắp ráp trong Kỹ thuật phần cứng / Hệ thống nhúng)",
        ],
        "options": [
            "Deterministic Finite Automaton (Otomat / Trình biên dịch)",
            "Design For Assembly (Kỹ thuật hệ thống / Nhúng)",
        ],
        "context_keywords": ["otomat", "automaton", "ngôn ngữ", "trình biên dịch", "compiler", "lắp ráp", "assembly"],
    },
    "tps": {
        "meanings": [
            "**Transactions Per Second** (Số giao dịch mỗi giây trong Cơ sở dữ liệu / Blockchain)",
            "**Testing & Planning Specification** (Quy cách kiểm thử phần mềm)",
        ],
        "options": [
            "Transactions Per Second (Giao dịch CSDL/Blockchain)",
            "Testing Specification (Quy cách kiểm thử)",
        ],
        "context_keywords": ["giao dịch", "transaction", "giây", "blockchain", "csdl", "database", "throughput"],
    },
}


def check_ambiguous_acronym(query: str) -> DisambiguationResult:
    """
    Check if a query contains a known ambiguous acronym with insufficient context words (< 5 words).
    Returns DisambiguationResult with is_ambiguous=True if clarification is required.
    """
    if not query:
        return DisambiguationResult(is_ambiguous=False)

    lower = query.strip().lower()
    words = lower.split()

    # Rule: Short queries (< 6 words) are prone to ambiguous acronym misunderstanding
    if len(words) > 6:
        return DisambiguationResult(is_ambiguous=False)

    # Check for course markers: if user is asking about a specific university course, don't trigger
    if any(k in lower for k in ["fit", "csc", "dnu", "môn", "học phần", "tín chỉ", "đề cương"]):
        return DisambiguationResult(is_ambiguous=False)

    for acronym, config in AMBIGUOUS_ACRONYMS.items():
        pattern = rf"\b{re.escape(acronym)}\b"
        if re.search(pattern, lower):
            # Check if query already contains disambiguating context keywords
            has_context = any(kw in lower for kw in config.get("context_keywords", []))
            if not has_context:
                meanings_formatted = "\n".join(f"{i+1}. {m}" for i, m in enumerate(config["meanings"]))
                question = (
                    f"Khái niệm/Thuật toán **{acronym.upper()}** có thể chỉ nhiều chủ đề khác nhau trong Công nghệ Thông tin:\n\n"
                    f"{meanings_formatted}\n\n"
                    f"Bạn đang quan tâm đến hướng nào để mình có thể giải thích chính xác và chi tiết nhất?"
                )
                return DisambiguationResult(
                    is_ambiguous=True,
                    acronym=acronym.upper(),
                    clarification_question=question,
                    clarification_options=config.get("options", []),
                )

    return DisambiguationResult(is_ambiguous=False)
