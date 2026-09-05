"""
Context Builder: Chọn lọc, ưu tiên theo target, loại bỏ trùng lặp và đóng gói context kèm metadata nguồn.
"""
import logging
from typing import List, Dict, Any, Tuple, Optional
from src.config.settings import settings

logger = logging.getLogger(__name__)


def calculate_target_relevance(doc: Dict[str, Any], targets: List[str]) -> float:
    """Tính điểm cộng ưu tiên nếu chunk chứa section phù hợp với targets của câu hỏi."""
    boost = 0.0
    text = doc.get("text", "").lower()
    meta = doc.get("metadata", {})
    section = str(meta.get("section", "")).lower()
    subsection = str(meta.get("subsection", "")).lower()

    for target in targets:
        if target == "lecturer":
            if "thông tin giảng viên" in text or "giảng viên" in section or "mục ii" in section:
                boost += 0.5
        elif target == "clo":
            if "chuẩn đầu ra" in text or "clo" in text or "mục v" in section:
                boost += 0.5
        elif target == "course_plan":
            if "kế hoạch giảng dạy" in text or "tuần" in subsection or "mục vii" in section:
                boost += 0.5
        elif target == "credits":
            if "tín chỉ" in text or "thông tin chung" in section or "mục i" in section:
                boost += 0.3
        elif target == "assessment":
            if "đánh giá" in text or "chuyên cần" in text or "mục viii" in section:
                boost += 0.4
        elif target == "regulation":
            if "điều" in section or "chương" in subsection:
                boost += 0.3

    return boost


def build_context(
    documents: List[Dict[str, Any]],
    targets: Optional[List[str]] = None,
    max_chunks: Optional[int] = None,
    max_char_budget: int = 6000,
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Xây dựng chuỗi context tối ưu cho LLM và danh sách nguồn tham khảo chuẩn hóa.
    Returns:
        (context_string, sources_list)
    """
    if not documents:
        return "", []

    k = max_chunks or settings.CONTEXT_TOP_K
    active_targets = targets or []

    # 1. Đánh giá và sắp xếp lại tài liệu kết hợp target boost
    scored_docs = []
    for doc in documents:
        base_score = doc.get("rerank_score") or doc.get("score") or 0.0
        boost = calculate_target_relevance(doc, active_targets)
        final_priority = base_score + boost
        scored_docs.append((final_priority, doc))

    scored_docs.sort(key=lambda x: x[0], reverse=True)

    # 2. Lọc trùng lặp nội dung
    selected_docs = []
    seen_texts = set()
    total_chars = 0

    for _, doc in scored_docs:
        text = doc.get("text", "").strip()
        if not text:
            continue

        # Check trùng lặp sơ bộ qua 80 ký tự đầu
        prefix = text[:80].lower()
        if prefix in seen_texts:
            continue

        if len(selected_docs) >= k:
            break

        if total_chars + len(text) > max_char_budget and len(selected_docs) >= 2:
            break

        seen_texts.add(prefix)
        selected_docs.append(doc)
        total_chars += len(text)

    # 3. Tạo context formatted và trích xuất danh sách nguồn (sources)
    context_blocks = []
    sources = []
    seen_source_keys = set()

    for idx, doc in enumerate(selected_docs, 1):
        meta = doc.get("metadata", {})
        source_file = meta.get("source_file") or meta.get("filename", "Tài liệu học vụ")
        section = meta.get("section", "")
        subsection = meta.get("subsection", "")
        doc_type = meta.get("document_type", "course_detail")
        course_code = meta.get("course_code", "")
        course_name = meta.get("course_name", "")
        chunk_id = doc.get("id", meta.get("chunk_id", f"chunk_{idx}"))

        # Header cho từng block context
        header_parts = [f"Nguồn {idx}: {source_file}"]
        if section:
            header_parts.append(f"Mục: {section}")
        if subsection:
            header_parts.append(f"Chi tiết: {subsection}")

        header = " | ".join(header_parts)
        context_blocks.append(f"[{header}]\n{doc['text']}")

        # Đóng gói metadata nguồn cho API
        source_key = (source_file, section, subsection, chunk_id)
        if source_key not in seen_source_keys:
            seen_source_keys.add(source_key)
            sources.append({
                "source_file": source_file,
                "document_type": doc_type,
                "course_code": course_code,
                "course_name": course_name,
                "section": section,
                "subsection": subsection,
                "chunk_id": chunk_id,
            })

    context_str = "\n\n".join(context_blocks)
    logger.info(f"Da dong goi context: {len(selected_docs)} chunks, {len(context_str)} ky tu, {len(sources)} sources")
    return context_str, sources
