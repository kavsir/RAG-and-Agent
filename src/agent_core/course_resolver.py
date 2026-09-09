"""
CourseEntityResolver V2: Multi-Stage Academic Course Resolver for Goal-Driven Agent Core.
Handles real student query variations:
- Stage 1: Exact course code regex (e.g. "fit 4113", "FIT-4113", "fit_4113", "FIT4113")
- Stage 2: Exact canonical name & catalog aliases
- Stage 3: Normalized text & abbreviation expansion (cn -> công nghệ, mmt -> mạng máy tính, ctdl -> cấu trúc dữ liệu, cloud -> điện toán đám mây...)
- Stage 4: Typo & fuzzy token matching (Levenshtein + token overlap, e.g. "cn điện toán máy", "công nghệ điện toán máy" -> FIT4113)
- Stage 5: Local BGE semantic embedding matching (0 external calls, < 50ms)
- Stage 6: Conversational context & pronoun resolution ("môn này", "nó", "học phần đó" -> active course)
- Stage 7: Confidence policy (RESOLVED >= 0.85, NEEDS_USER_CONFIRMATION 0.60-0.85, MISSING_ENTITY < 0.60)
"""
import re
import enum
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple, Set

import numpy as np

from src.agent_core.entity_catalog import get_entity_catalog, EntityCatalog


class ResolutionStatus(str, enum.Enum):
    RESOLVED = "RESOLVED"
    NEEDS_USER_CONFIRMATION = "NEEDS_USER_CONFIRMATION"
    MISSING_ENTITY = "MISSING_ENTITY"
    UNKNOWN_CODE = "UNKNOWN_CODE"
    ENTITY_CONFLICT = "ENTITY_CONFLICT"


@dataclass
class CourseResolutionResult:
    status: ResolutionStatus
    course_code: Optional[str] = None
    canonical_name: Optional[str] = None
    confidence_score: float = 0.0
    stage: str = "none"
    clarification_question: Optional[str] = None
    clarification_options: List[str] = field(default_factory=list)
    matched_text: Optional[str] = None
    conflicting_code: Optional[str] = None


def strip_accents(text: str) -> str:
    """Loại bỏ dấu tiếng Việt, chuyển thành chữ không dấu chuẩn."""
    if not text:
        return ""
    s = unicodedata.normalize("NFD", text)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.replace("đ", "d").replace("Đ", "d")
    return s


def normalize_course_text(text: str, remove_accents: bool = False) -> str:
    """Chuẩn hóa văn bản: chữ thường, chuẩn unicode, loại bỏ ký tự đặc biệt, gộp khoảng trắng."""
    if not text:
        return ""
    s = text.strip().lower()
    if remove_accents:
        s = strip_accents(s)
    else:
        s = unicodedata.normalize("NFC", s)
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


ABBREVIATIONS: Dict[str, str] = {
    r"\bcn\b": "công nghệ",
    r"\bđt\b": "điện toán",
    r"\bdt\b": "dien toan",
    r"\bđm\b": "đám mây",
    r"\bdm\b": "dam may",
    r"\bmmt\b": "mạng máy tính",
    r"\bctdl\b": "cấu trúc dữ liệu",
    r"\bctdlgt\b": "cấu trúc dữ liệu và giải thuật",
    r"\bktlt\b": "kỹ thuật lập trình",
    r"\bcslt\b": "cơ sở lập trình",
    r"\bhdh\b": "hệ điều hành",
    r"\bcsdl\b": "cơ sở dữ liệu",
    r"\bhqt\s*csdl\b": "hệ quản trị cơ sở dữ liệu",
    r"\bhqtdl\b": "hệ quản trị cơ sở dữ liệu",
    r"\bptpm\b": "phát triển phần mềm",
    r"\btkpm\b": "thiết kế phần mềm",
    r"\bktpm\b": "kỹ thuật phần mềm",
    r"\bai\b": "trí tuệ nhân tạo",
    r"\bttnt\b": "trí tuệ nhân tạo",
    r"\biot\b": "internet vạn vật",
    r"\bcloud\b": "điện toán đám mây",
    r"\bmobile\b": "di động",
    r"\bweb\b": "phát triển web",
    r"\battt\b": "an toàn thông tin",
    r"\bbmtt\b": "bảo mật thông tin",
    r"\bantm\b": "an toàn mạng",
}


def expand_abbreviations(text: str) -> str:
    """Mở rộng các từ viết tắt phổ biến của sinh viên CNTT."""
    result = text
    # Tránh nhầm lẫn giữa đại từ nghi vấn "ai" (ai dạy, ai đứng lớp) và từ viết tắt "AI" (Trí tuệ nhân tạo)
    is_who_pronoun = bool(re.search(r"\bai\s+(?:dạy|đứng\s+lớp|hướng\s+dẫn|phụ\s+trách|chấm|là|coi|nào)\b", text, re.IGNORECASE))
    for pattern, replacement in ABBREVIATIONS.items():
        if pattern == r"\bai\b" and is_who_pronoun:
            continue
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result


def levenshtein_ratio(s1: str, s2: str) -> float:
    """Tính tỷ lệ tương đồng Levenshtein giữa 2 chuỗi (0.0 đến 1.0)."""
    if s1 == s2:
        return 1.0
    len1, len2 = len(s1), len(s2)
    if len1 == 0 or len2 == 0:
        return 0.0

    dp = [[0] * (len2 + 1) for _ in range(len1 + 1)]
    for i in range(len1 + 1):
        dp[i][0] = i
    for j in range(len2 + 1):
        dp[0][j] = j

    for i in range(1, len1 + 1):
        for j in range(1, len2 + 1):
            cost = 0 if s1[i - 1] == s2[j - 1] else 1
            dp[i][j] = min(
                dp[i - 1][j] + 1,      # deletion
                dp[i][j - 1] + 1,      # insertion
                dp[i - 1][j - 1] + cost  # substitution
            )

    dist = dp[len1][len2]
    max_len = max(len1, len2)
    return 1.0 - (dist / max_len)


def token_overlap_score(query: str, target: str) -> float:
    """
    Tính điểm tương đồng token kết hợp F1 Dice coefficient, query coverage và Levenshtein:
    - F1 token overlap có dấu và không dấu (giải quyết lỗi gõ dấu như 'máy' vs 'mây')
    - Query token coverage (tỷ lệ các từ trong câu hỏi khớp vào tên môn học)
    - Sequence Levenshtein
    """
    q_norm = normalize_course_text(query)
    t_norm = normalize_course_text(target)

    # Loại bỏ các stop words phổ biến trước khi so khớp token
    stop_words = {"mon", "hoc", "phan", "cho", "minh", "hoi", "ve", "la", "gi", "co", "may", "bao", "nhieu", "tin", "chi", "cua"}
    q_words = [w for w in q_norm.split() if w not in stop_words]
    t_words = [w for w in t_norm.split() if w not in stop_words]

    if not q_words or not t_words:
        return 0.0

    q_tokens = set(q_words)
    t_tokens = set(t_words)

    # 1. Exact accented F1
    inter_acc = q_tokens.intersection(t_tokens)
    f1_acc = (2.0 * len(inter_acc)) / (len(q_tokens) + len(t_tokens))

    # 2. Unaccented F1 (bắt trọn các lỗi gõ sai dấu thanh/dấu mũ tiếng Việt: máy/mây, mạng/mang...)
    q_unaccent = set(normalize_course_text(" ".join(q_words), remove_accents=True).split())
    t_unaccent = set(normalize_course_text(" ".join(t_words), remove_accents=True).split())
    inter_unacc = q_unaccent.intersection(t_unaccent)
    f1_unacc = (2.0 * len(inter_unacc)) / (len(q_unaccent) + len(t_unaccent))

    # 3. Query recall: bao nhiêu % từ khóa môn trong query có mặt trong target
    query_recall = len(inter_unacc) / len(q_unaccent) if q_unaccent else 0.0

    # 4. Levenshtein ratio
    seq_ratio = levenshtein_ratio(q_norm, t_norm)
    seq_unaccent = levenshtein_ratio(
        normalize_course_text(query, remove_accents=True),
        normalize_course_text(target, remove_accents=True)
    )

    # Điểm tổng hợp: nếu query recall cao và F1 unaccented cao -> điểm tương đồng rất cao
    if query_recall >= 0.80 and len(inter_unacc) >= 2:
        token_score = max(f1_unacc, (f1_unacc * 0.7 + query_recall * 0.3))
    else:
        token_score = max(f1_acc, f1_unacc * 0.9)

    final_score = max(
        token_score,
        seq_ratio,
        seq_unaccent * 0.9,
    )
    return float(final_score)


PRONOUN_PATTERNS = [
    r"\bm[oô]n\s+n[aà]y\b",
    r"\bh[oọ]c\s+ph[aầ]n\s+n[aà]y\b",
    r"\bn[oó]\b",
    r"\bm[oô]n\s+[đd][oó]\b",
    r"\bh[oọ]c\s+ph[aầ]n\s+[đd][oó]\b",
    r"\bm[oô]n\s+tr[eê]n\b",
    r"\bh[oọ]c\s+ph[aầ]n\s+tr[eê]n\b",
    r"\bm[oô]n\s+v[uừ]a\s+r[oồ]i\b",
    r"\bm[oô]n\s+h[oọ]c\s+[đd][oó]\b",
    r"\bm[oô]n\s+h[oọ]c\s+n[aà]y\b",
    r"\bm[oô]n\s+[aấ]y\b",
]


class CourseEntityResolver:
    """
    Bộ nhận diện và chuẩn hóa thực thể môn học đa tầng (Multi-Stage Resolver).
    Hoàn toàn khái quát hóa trên toàn bộ 70 môn học trong danh mục CTĐT K19.
    """

    def __init__(self, entity_catalog: Optional[EntityCatalog] = None):
        self.catalog = entity_catalog or get_entity_catalog()
        self.entities = self.catalog.entities
        self._target_embeddings: Optional[np.ndarray] = None
        self._embedding_entries: List[Tuple[str, str]] = []  # (code, text)
        self._embedding_model = None

        # Tiền lập chỉ mục mục tiêu để tìm kiếm token siêu tốc (< 15ms)
        self._indexed_targets: List[Tuple[str, str, Set[str]]] = []
        stop_words = {"mon", "hoc", "phan", "va", "cua", "trong", "co", "ban", "cho"}
        for code, info in self.entities.items():
            targets = [info.get("canonical_name", "")] + info.get("aliases", [])
            for t in targets:
                if not t:
                    continue
                unacc = set(normalize_course_text(t, remove_accents=True).split()) - stop_words
                self._indexed_targets.append((code, t, unacc))

    def _get_embedding_model(self):
        if self._embedding_model is None:
            try:
                from src.ingestion.vector_store import get_embedding_model
                self._embedding_model = get_embedding_model()
            except Exception:
                self._embedding_model = None
        return self._embedding_model

    def _ensure_embeddings(self) -> None:
        """Khởi tạo embeddings cho tất cả tên môn và bí danh (chạy 1 lần, cached)."""
        if self._target_embeddings is not None:
            return

        model = self._get_embedding_model()
        if model is None:
            return

        entries: List[Tuple[str, str]] = []
        texts: List[str] = []

        for code, info in self.entities.items():
            c_name = info.get("canonical_name", "")
            if c_name:
                entries.append((code, c_name))
                texts.append(c_name)
            for alias in info.get("aliases", []):
                if alias and alias != c_name:
                    entries.append((code, alias))
                    texts.append(alias)

        if texts:
            try:
                vecs = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
                self._target_embeddings = np.array(vecs, dtype=np.float32)
                self._embedding_entries = entries
            except Exception:
                self._target_embeddings = None

    def resolve(
        self,
        query: str,
        session_context: Optional[Dict[str, Any]] = None,
    ) -> CourseResolutionResult:
        """
        Nhận diện và chuẩn hóa môn học theo 7 tầng phân giải:
        1. Exact code regex (e.g. FIT 4113 -> FIT4113)
        2. Exact canonical name & aliases
        3. Normalized text & abbreviation expansion
        4. Typo / Fuzzy token matching
        5. Local semantic embedding matching (BGE-M3)
        6. Conversational context & pronoun resolution
        7. Confidence thresholding
        """
        if not query or not query.strip():
            return CourseResolutionResult(status=ResolutionStatus.MISSING_ENTITY)

        raw_query = query.strip()
        lower_query = raw_query.lower()

        # =====================================================================
        # STAGE 1: Exact Course Code Regex (FIT 4113, FIT-4113, fit4113...)
        # =====================================================================
        code_matches = re.findall(r"\b([A-Za-z]{2,5})\s*[-_]?\s*(\d{2,4})\b", raw_query)
        if code_matches:
            extracted_codes = [f"{m[0]}{m[1]}".upper() for m in code_matches]
            # Kiểm tra xem có mã nào hợp lệ trong catalog
            for code in extracted_codes:
                if self.catalog.is_known_code(code):
                    # Kiểm tra conflict với alias của môn khác trong câu
                    conflict = self.catalog.check_entity_conflict(raw_query)
                    if conflict and conflict.get("has_conflict"):
                        return CourseResolutionResult(
                            status=ResolutionStatus.ENTITY_CONFLICT,
                            course_code=code,
                            conflicting_code=conflict.get("conflicting_code"),
                            stage="stage1_entity_conflict",
                            confidence_score=1.0,
                        )
                    c_info = self.catalog.get_course_info(code)
                    canonical_name = c_info.get("canonical_name", code) if c_info else code
                    return CourseResolutionResult(
                        status=ResolutionStatus.RESOLVED,
                        course_code=code,
                        canonical_name=canonical_name,
                        confidence_score=1.0,
                        stage="stage1_exact_code",
                        matched_text=code,
                    )
            # Nếu có chuỗi dạng mã môn nhưng không tồn tại trong danh mục -> UNKNOWN_CODE
            for code in extracted_codes:
                if not self.catalog.is_known_code(code):
                    return CourseResolutionResult(
                        status=ResolutionStatus.UNKNOWN_CODE,
                        course_code=code,
                        stage="stage1_unknown_code",
                        confidence_score=0.0,
                        clarification_question=(
                            f"Mã học phần {code} không có trong danh mục chương trình đào tạo "
                            f"hoặc tài liệu chính thức của nhà trường. Vui lòng kiểm tra lại mã môn học."
                        ),
                    )

        # =====================================================================
        # STAGE 2: Exact Canonical Name & Known Aliases
        # =====================================================================
        exact_entities = self.catalog.extract_known_entities(raw_query)
        if exact_entities:
            primary_code = exact_entities[0]
            c_info = self.catalog.get_course_info(primary_code)
            canonical_name = c_info.get("canonical_name", primary_code) if c_info else primary_code
            return CourseResolutionResult(
                status=ResolutionStatus.RESOLVED,
                course_code=primary_code,
                canonical_name=canonical_name,
                confidence_score=1.0,
                stage="stage2_exact_alias",
                matched_text=canonical_name,
            )

        # =====================================================================
        # STAGE 3: Pronouns & Conversational Context ("môn này", "nó", "học phần đó"...)
        # =====================================================================
        has_pronoun = any(re.search(pat, lower_query) for pat in PRONOUN_PATTERNS)
        if has_pronoun:
            if session_context:
                active_code = (
                    session_context.get("last_academic_entity")
                    or session_context.get("active_course_code")
                    or session_context.get("active_course")
                    or session_context.get("active_entity")
                )
                if active_code and self.catalog.is_known_code(active_code):
                    c_info = self.catalog.get_course_info(active_code)
                    canonical_name = c_info.get("canonical_name", active_code) if c_info else active_code
                    return CourseResolutionResult(
                        status=ResolutionStatus.RESOLVED,
                        course_code=active_code,
                        canonical_name=canonical_name,
                        confidence_score=1.0,
                        stage="stage3_session_context",
                        matched_text="pronoun",
                    )
            # Có đại từ nhưng không có ngữ cảnh phiên -> Không đoán mò, hỏi làm rõ
            return CourseResolutionResult(
                status=ResolutionStatus.MISSING_ENTITY,
                confidence_score=0.0,
                stage="stage3_pronoun_missing_context",
                clarification_question=(
                    "Bạn đang muốn hỏi thông tin về môn học nào? "
                    "Vui lòng cung cấp mã môn (vd: FIT4113) hoặc tên đầy đủ của môn học."
                ),
                clarification_options=[],
            )

        # =====================================================================
        # STAGE 4: Normalized Text & Abbreviation Expansion
        # =====================================================================
        expanded_query = expand_abbreviations(lower_query)
        norm_expanded = normalize_course_text(expanded_query)

        # Tra cứu lại trên alias_to_code sau khi mở rộng viết tắt
        for alias, code in self.catalog.alias_to_code.items():
            norm_alias = normalize_course_text(alias)
            if len(norm_alias) >= 4 and norm_alias in norm_expanded:
                c_info = self.catalog.get_course_info(code)
                canonical_name = c_info.get("canonical_name", code) if c_info else code
                return CourseResolutionResult(
                    status=ResolutionStatus.RESOLVED,
                    course_code=code,
                    canonical_name=canonical_name,
                    confidence_score=0.96,
                    stage="stage4_abbreviation_expansion",
                    matched_text=alias,
                )

        # =====================================================================
        # STAGE 5: Typo & Fuzzy Token Matching (Levenshtein + Token Overlap)
        # =====================================================================
        candidates: List[Tuple[str, str, float]] = []  # (code, target_name, score)

        # Loại bỏ các cụm từ nghi vấn học vụ trước khi tìm kiếm mờ để không làm loãng điểm token
        cleaned_query = re.sub(
            r"\bc[oó]\s+(m[aấ]y|bao\s+nhi[eê]u)?\s*(t[ií]n\s+ch[iỉ]|ti[eế]t|gi[oờ]).*", "", expanded_query, flags=re.IGNORECASE
        )
        cleaned_query = re.sub(
            r"\b(gi[aả]ng\s+vi[eê]n|th[aà]y|c[oô])\s+(n[aà]o|l[aà]\s+ai|d[aạ]y).*", "", cleaned_query, flags=re.IGNORECASE
        )
        cleaned_query = re.sub(
            r"\b(chu[aẩ]n\s+[đd][aầ]u\s+ra|clo|m[uụ]c\s+ti[eê]u|[đd][eề]\s+c[uư][oơ]ng|h[oọ]c\s+k[yỳ]\s+n[aà]o|ti[eê]n\s+quy[eế]t|[đd][aá]nh\s+gi[aá]).*", "", cleaned_query, flags=re.IGNORECASE
        ).strip()
        if not cleaned_query:
            cleaned_query = expanded_query

        q_unacc_words = set(normalize_course_text(cleaned_query, remove_accents=True).split()) - {"mon", "hoc", "phan", "va", "cua", "trong"}

        for code, t, target_unacc in self._indexed_targets:
            # Lọc nhanh: chỉ tính toán độ tương đồng chi tiết nếu có ít nhất 1 từ khóa chung
            if not q_unacc_words.intersection(target_unacc):
                continue
            score_clean = token_overlap_score(cleaned_query, t)
            score_orig = token_overlap_score(lower_query, t) if score_clean < 0.85 else 0.0
            best_score = max(score_clean, score_orig)
            if best_score >= 0.50:
                candidates.append((code, t, best_score))

        # Sắp xếp ứng viên theo điểm giảm dần
        candidates.sort(key=lambda x: x[2], reverse=True)

        if candidates:
            best_code, best_target, best_score = candidates[0]
            second_score = 0.0
            for c, t, s in candidates[1:]:
                if c != best_code:
                    second_score = s
                    break
            margin = best_score - second_score

            c_info = self.catalog.get_course_info(best_code)
            canonical_name = c_info.get("canonical_name", best_code) if c_info else best_code

            # Ngưỡng tự động giải quyết (High Confidence)
            if best_score >= 0.85 and margin >= 0.12:
                return CourseResolutionResult(
                    status=ResolutionStatus.RESOLVED,
                    course_code=best_code,
                    canonical_name=canonical_name,
                    confidence_score=best_score,
                    stage="stage5_fuzzy_token",
                    matched_text=best_target,
                )

            # Ngưỡng cần người dùng xác nhận (Medium Confidence)
            if 0.60 <= best_score < 0.85 or (best_score >= 0.85 and margin < 0.12):
                return CourseResolutionResult(
                    status=ResolutionStatus.NEEDS_USER_CONFIRMATION,
                    course_code=best_code,
                    canonical_name=canonical_name,
                    confidence_score=best_score,
                    stage="stage5_fuzzy_confirmation",
                    clarification_question=(
                        f"Bạn có phải đang hỏi môn **{canonical_name}** ({best_code}) không?"
                    ),
                    clarification_options=[
                        f"Đúng, môn {best_code}",
                        "Không phải môn này",
                    ],
                )

        # =====================================================================
        # STAGE 6: Local Semantic Embedding Matching (BGE-M3)
        # =====================================================================
        self._ensure_embeddings()
        if self._target_embeddings is not None and self._get_embedding_model() is not None:
            try:
                model = self._get_embedding_model()
                q_vec = model.encode(expanded_query, normalize_embeddings=True, show_progress_bar=False)
                sims = np.dot(self._target_embeddings, q_vec)
                top_idx = int(np.argmax(sims))
                top_sim = float(sims[top_idx])
                top_code, top_name = self._embedding_entries[top_idx]

                second_sim = 0.0
                for idx in np.argsort(-sims):
                    other_code, _ = self._embedding_entries[idx]
                    if other_code != top_code:
                        second_sim = float(sims[idx])
                        break
                sem_margin = top_sim - second_sim

                c_info = self.catalog.get_course_info(top_code)
                canonical_name = c_info.get("canonical_name", top_code) if c_info else top_code

                if top_sim >= 0.85 and sem_margin >= 0.15:
                    return CourseResolutionResult(
                        status=ResolutionStatus.RESOLVED,
                        course_code=top_code,
                        canonical_name=canonical_name,
                        confidence_score=top_sim,
                        stage="stage6_semantic_embedding",
                        matched_text=top_name,
                    )
                elif 0.60 <= top_sim < 0.85:
                    return CourseResolutionResult(
                        status=ResolutionStatus.NEEDS_USER_CONFIRMATION,
                        course_code=top_code,
                        canonical_name=canonical_name,
                        confidence_score=top_sim,
                        stage="stage6_semantic_confirmation",
                        clarification_question=(
                            f"Bạn có phải đang hỏi môn **{canonical_name}** ({top_code}) không?"
                        ),
                        clarification_options=[
                            f"Đúng, môn {top_code}",
                            "Không phải môn này",
                        ],
                    )
            except Exception:
                pass

        # =====================================================================
        # STAGE 7: Low Confidence / Missing Entity
        # =====================================================================
        return CourseResolutionResult(
            status=ResolutionStatus.MISSING_ENTITY,
            confidence_score=0.0,
            stage="stage7_missing_entity",
            clarification_question=(
                "Mình chưa nhận diện được môn học bạn muốn hỏi. "
                "Bạn có thể cung cấp mã môn (vd: FIT4113) hoặc tên đầy đủ của môn học không?"
            ),
            clarification_options=[],
        )


# Singleton
_course_resolver_instance: Optional[CourseEntityResolver] = None


def get_course_resolver() -> CourseEntityResolver:
    global _course_resolver_instance
    if _course_resolver_instance is None:
        _course_resolver_instance = CourseEntityResolver()
    return _course_resolver_instance
