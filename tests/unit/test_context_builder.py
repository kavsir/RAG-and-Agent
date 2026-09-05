from src.rag.context_builder import build_context, calculate_target_relevance


def test_target_relevance_boost():
    doc_lecturer = {
        "text": "Thông tin giảng viên phụ trách học phần: TS. Trần Đăng Công",
        "metadata": {"section": "II. Thông tin giảng viên"}
    }
    boost = calculate_target_relevance(doc_lecturer, ["lecturer"])
    assert boost > 0.0


def test_build_context_deduplication():
    docs = [
        {"id": "1", "text": "Môn Hệ thống nhúng có 3 tín chỉ.", "metadata": {"source_file": "file1.docx", "section": "I"}},
        {"id": "2", "text": "Môn Hệ thống nhúng có 3 tín chỉ.", "metadata": {"source_file": "file1.docx", "section": "I"}},
        {"id": "3", "text": "Giảng viên: TS. Trần Đăng Công", "metadata": {"source_file": "file1.docx", "section": "II"}},
    ]
    context, sources = build_context(docs, targets=["credits"])
    assert len(sources) == 2  # Deduplicated chunk 2


def test_build_context_budget_limit():
    docs = [
        {"id": f"{i}", "text": f"Nội dung dòng thứ {i} dài một đoạn văn mẫu...", "metadata": {"source_file": f"f{i}.docx"}}
        for i in range(10)
    ]
    context, sources = build_context(docs, max_chunks=3)
    assert len(sources) <= 3
