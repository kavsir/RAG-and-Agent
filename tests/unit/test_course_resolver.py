"""
Unit tests for CourseEntityResolver V2 (Round UX2).
Validates multi-stage resolution, typo tolerance, abbreviation expansion,
session context inheritance, and confidence policy.
"""
import time
from src.agent_core.course_resolver import (
    get_course_resolver,
    ResolutionStatus,
)


def test_resolver_code_variants():
    resolver = get_course_resolver()
    variants = [
        "FIT4113 có mấy tín chỉ?",
        "fit4113 bao nhiêu tín chỉ",
        "fit 4113 có mấy tín chỉ",
        "FIT 4113",
        "fit-4113",
        "FIT_4113",
    ]
    for q in variants:
        res = resolver.resolve(q)
        assert res.status == ResolutionStatus.RESOLVED, f"Failed for {q}"
        assert res.course_code == "FIT4113", f"Wrong code for {q}: {res.course_code}"


def test_resolver_typo_and_abbreviations_fit4113():
    resolver = get_course_resolver()
    typos = [
        "cn điện toán máy",
        "công nghệ điện toán máy",
        "điện toán mây",
        "môn cloud",
        "công nghệ đám mây",
        "môn điện toán đám mây",
    ]
    for q in typos:
        res = resolver.resolve(q)
        assert res.status == ResolutionStatus.RESOLVED, f"Failed for '{q}', got status {res.status}"
        assert res.course_code == "FIT4113", f"Expected FIT4113 for '{q}', got {res.course_code} (stage={res.stage})"


def test_resolver_catalog_generalization():
    resolver = get_course_resolver()
    # Test abbreviations across catalog
    cases = [
        ("môn mmt học gì", "FIT4006"),                  # mạng máy tính
        ("mạng máy tính có mấy tín chỉ", "FIT4006"),
        ("môn ctdl có mấy tín chỉ", "FIT4004"),          # cấu trúc dữ liệu
        ("cấu trúc dữ liệu và giải thuật", "FIT4004"),
        ("môn lập trình mobile có mấy tín chỉ", "FIT4102"),
    ]
    for q, expected_code in cases:
        res = resolver.resolve(q)
        assert res.status == ResolutionStatus.RESOLVED, f"Failed for '{q}'"
        assert res.course_code == expected_code, f"For '{q}': expected {expected_code}, got {res.course_code}"


def test_resolver_pronoun_and_session_context():
    resolver = get_course_resolver()
    session = {"active_course_code": "FIT4113"}

    for q in ["môn này học kỳ nào", "nó có mấy tín chỉ", "học phần này điều kiện gì"]:
        res = resolver.resolve(q, session_context=session)
        assert res.status == ResolutionStatus.RESOLVED, f"Failed for pronoun query '{q}'"
        assert res.course_code == "FIT4113"

    # When no session context is present, pronoun query returns MISSING_ENTITY
    res_no_session = resolver.resolve("môn này học kỳ nào", session_context=None)
    assert res_no_session.status in (ResolutionStatus.MISSING_ENTITY, ResolutionStatus.NEEDS_USER_CONFIRMATION)


def test_resolver_unknown_code():
    resolver = get_course_resolver()
    res = resolver.resolve("FIT9999 có bao nhiêu tín chỉ?")
    assert res.status == ResolutionStatus.UNKNOWN_CODE
    assert res.course_code == "FIT9999"


def test_resolver_entity_conflict():
    resolver = get_course_resolver()
    # FIT4201 (Hệ thống nhúng) with Full-Stack (FIT4104)
    res = resolver.resolve("FIT4201 môn Full-Stack có bao nhiêu tín chỉ?")
    assert res.status == ResolutionStatus.ENTITY_CONFLICT


def test_resolver_latency_p95():
    resolver = get_course_resolver()
    times = []
    for _ in range(50):
        t0 = time.perf_counter()
        resolver.resolve("cn điện toán máy có mấy tín chỉ")
        times.append(time.perf_counter() - t0)
    times.sort()
    p95 = times[int(len(times) * 0.95)] * 1000
    assert p95 < 200.0, f"Expected p95 < 200ms, got {p95:.2f}ms"
