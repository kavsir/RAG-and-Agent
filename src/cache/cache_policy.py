"""
Cache Policy Engine: Định nghĩa chính sách phân loại, phạm vi lưu trữ và tạo khóa an toàn ngữ cảnh.
Đảm bảo:
1. GLOBAL_SAFE: Độc lập hoàn toàn với session và personal context.
2. PROFILE_SCOPED: Phụ thuộc vào Personal Memory, băm toàn bộ relevant profile thành digest an toàn.
3. SESSION_SENSITIVE: Phụ thuộc vào thực thể/đại từ trong phiên -> Bắt buộc BYPASS Exact Cache.
4. NON_CACHEABLE: Các hành động Tool (gửi email, đặt lịch nhắc) -> Bắt buộc KHÔNG được cache.
"""
import re
import json
import hashlib
import unicodedata
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class CacheScope:
    GLOBAL_SAFE = "GLOBAL_SAFE"
    PROFILE_SCOPED = "PROFILE_SCOPED"
    SESSION_SENSITIVE = "SESSION_SENSITIVE"
    NON_CACHEABLE = "NON_CACHEABLE"


class CachePolicyDecision(BaseModel):
    """Quyết định phân loại chính sách bộ đệm cho một câu truy vấn."""
    cacheable: bool
    scope: str  # GLOBAL_SAFE | PROFILE_SCOPED | SESSION_SENSITIVE | NON_CACHEABLE
    reason_code: str
    cache_key: Optional[str] = None
    profile_digest: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


def compute_profile_digest(profile: Optional[Dict[str, Any]]) -> Optional[str]:
    """
    Tính toán digest an toàn (SHA-256 rút gọn) của TOÀN BỘ ngữ cảnh hồ sơ được tiêm.
    Canonicalization:
    - Loại bỏ giá trị rỗng/None
    - Sắp xếp khóa theo thứ tự bảng chữ cái (sorted keys)
    - JSON tất định (separators=(',', ':'))
    - Chuẩn hóa Unicode NFC
    - Băm SHA-256, lấy 16 ký tự hex đầu tiên (không lưu plaintext giá trị nhạy cảm)
    """
    if not profile:
        return None

    clean = {str(k): v for k, v in profile.items() if v is not None and v != ""}
    if not clean:
        return None

    canonical_json = json.dumps(clean, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    norm_json = unicodedata.normalize("NFC", canonical_json)
    return hashlib.sha256(norm_json.encode("utf-8")).hexdigest()[:16]


def is_session_sensitive(
    query: str,
    analyzed_query: Optional[Dict[str, Any]] = None,
    session_context: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Xác định xem câu hỏi có phụ thuộc vào ngữ cảnh phiên hội thoại (Session State) hay không.
    Nếu phụ thuộc phiên -> SESSION_SENSITIVE -> Bắt buộc bypass Exact Cache.
    """
    query_norm = unicodedata.normalize("NFC", query.strip().lower())

    # 1. Kiểm tra resolution_source từ query analysis
    if analyzed_query:
        res_source = analyzed_query.get("resolution_source", "")
        if res_source in ["SESSION", "RESOLVED"]:
            return True
        if analyzed_query.get("resolved_course_code"):
            return True

    # 2. Câu hỏi chứa đại từ trỏ vào thực thể phiên
    pronoun_pattern = (
        r"\b(môn đó|môn này|môn đấy|môn nầy|học phần đó|học phần này|học phần đấy|"
        r"nó|thầy đó|cô đó|thầy này|cô này|giảng viên đó|giảng viên này|học kỳ đó)\b"
    )
    if re.search(pronoun_pattern, query_norm, re.IGNORECASE):
        return True

    # 3. Câu hỏi tỉnh lược (follow-up/ellipsis) khi phiên đang có active entity
    has_active_entity = bool(session_context and session_context.get("active_course_code"))
    has_explicit_entity = bool(analyzed_query and analyzed_query.get("explicit_course_code"))

    if has_active_entity and not has_explicit_entity:
        targets = analyzed_query.get("targets", []) if analyzed_query else []
        if targets:
            return True

        followup_cues = (
            r"\b(ai dạy|giảng viên|thầy|cô|email|mail|tín chỉ|tiên quyết|thực hành|"
            r"lý thuyết|thi|đề cương|học phí|thì sao|thế nào|bao nhiêu|ở đâu)\b"
        )
        if re.search(followup_cues, query_norm, re.IGNORECASE):
            return True

    return False


def make_cache_key(
    query: str,
    category: str,
    scope: str,
    profile_digest: Optional[str] = None,
) -> str:
    """
    Tạo khóa cache chuẩn tắc, an toàn ngữ cảnh.
    Format:
      - GLOBAL_SAFE:    "{category}::{normalized_query}::global"
      - PROFILE_SCOPED: "{category}::{normalized_query}::profile:{digest}"
    """
    norm_q = unicodedata.normalize("NFC", query.strip().lower())
    norm_q = re.sub(r"\s+", " ", norm_q)

    if scope == CacheScope.PROFILE_SCOPED and profile_digest:
        return f"{category}::{norm_q}::profile:{profile_digest}"
    return f"{category}::{norm_q}::global"


def decide_cache_policy(
    query: str,
    category: str,
    tool_intent: Optional[str] = None,
    analyzed_query: Optional[Dict[str, Any]] = None,
    session_context: Optional[Dict[str, Any]] = None,
    relevant_profile: Optional[Dict[str, Any]] = None,
) -> CachePolicyDecision:
    """
    Quyết định chính sách Cache cho câu truy vấn dựa trên phân loại Router và thực thể ngữ cảnh.
    """
    # 1. TOOL_ACTION -> Bắt buộc NON_CACHEABLE
    if category == "TOOL_ACTION" or tool_intent is not None:
        return CachePolicyDecision(
            cacheable=False,
            scope=CacheScope.NON_CACHEABLE,
            reason_code="TOOL_ACTION_MUTABLE",
            cache_key=None,
            profile_digest=None,
            metadata={"category": category, "tool_intent": tool_intent},
        )

    # 2. SESSION_SENSITIVE -> Bắt buộc BYPASS CACHE
    if is_session_sensitive(query, analyzed_query=analyzed_query, session_context=session_context):
        return CachePolicyDecision(
            cacheable=False,
            scope=CacheScope.SESSION_SENSITIVE,
            reason_code="SESSION_DEPENDENT_REFERENCE",
            cache_key=None,
            profile_digest=None,
            metadata={"inherited_course": session_context.get("active_course_code") if session_context else None},
        )

    # 3. PROFILE_SCOPED -> PROFILE CACHE
    digest = compute_profile_digest(relevant_profile)
    if digest:
        cache_key = make_cache_key(
            query=query,
            category=category,
            scope=CacheScope.PROFILE_SCOPED,
            profile_digest=digest,
        )
        return CachePolicyDecision(
            cacheable=True,
            scope=CacheScope.PROFILE_SCOPED,
            reason_code="PROFILE_PERSONALIZED",
            cache_key=cache_key,
            profile_digest=digest,
            metadata={"injected_keys": sorted(list(relevant_profile.keys())) if relevant_profile else []},
        )

    # 4. GLOBAL_SAFE -> GLOBAL CACHE
    cache_key = make_cache_key(
        query=query,
        category=category,
        scope=CacheScope.GLOBAL_SAFE,
        profile_digest=None,
    )
    return CachePolicyDecision(
        cacheable=True,
        scope=CacheScope.GLOBAL_SAFE,
        reason_code="GLOBAL_DETERMINISTIC",
        cache_key=cache_key,
        profile_digest=None,
        metadata={"category": category},
    )
