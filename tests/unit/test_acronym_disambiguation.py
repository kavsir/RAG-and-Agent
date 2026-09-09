"""
Unit tests for Ambiguous Acronym Disambiguation (Round UX2).
Verifies that short ambiguous tech acronyms trigger clarification instead of confident guessing.
"""
from src.router.acronym_disambiguator import check_ambiguous_acronym


def test_ambiguous_dpf():
    for q in ["thuật toán dpf", "dpf là gì", "khái niệm dpf", "dpf"]:
        res = check_ambiguous_acronym(q)
        assert res.is_ambiguous is True, f"Expected ambiguous for '{q}'"
        assert res.acronym == "DPF"
        assert "Distributed Point Function" in res.clarification_question
        assert "Directional Preference Function" in res.clarification_question
        assert len(res.clarification_options) >= 2


def test_ambiguous_dfa():
    for q in ["thuật toán dfa", "dfa là gì"]:
        res = check_ambiguous_acronym(q)
        assert res.is_ambiguous is True, f"Expected ambiguous for '{q}'"
        assert res.acronym == "DFA"
        assert "Deterministic Finite Automaton" in res.clarification_question


def test_unambiguous_or_domain_queries():
    unambiguous = [
        "thuật toán dijkstra hoạt động như thế nào",
        "môn FIT4113 có mấy tín chỉ",
        "quy chế tốt nghiệp ĐNTU",
        "giải thuật tìm kiếm nhị phân",
        "thuật toán dpf trong mật mã học và mpc",  # Already has disambiguating context!
    ]
    for q in unambiguous:
        res = check_ambiguous_acronym(q)
        assert res.is_ambiguous is False, f"Erroneously flagged '{q}' as ambiguous"
