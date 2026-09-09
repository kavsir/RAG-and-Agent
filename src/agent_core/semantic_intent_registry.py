"""
Semantic Intent Registry (Round P2.1):
Quản lý tập exemplars tiếng Việt tự nhiên cho từng nhóm ý định mục tiêu (GoalIntent)
và tính toán độ tương đồng ngữ nghĩa bằng Singleton BAAI/bge-m3.
Embeddings của exemplars được mã hóa trước 1 lần lúc khởi động (pre-computed).
"""
import logging
from typing import Dict, List, Tuple, Optional
import numpy as np

from src.agent_core.schemas import GoalIntent
from src.ingestion.vector_store import get_embedding_model

logger = logging.getLogger(__name__)

# Tập hợp các exemplars tự nhiên bằng tiếng Việt cho từng GoalIntent
INTENT_EXEMPLARS: Dict[GoalIntent, List[str]] = {
    GoalIntent.COURSE_OVERVIEW: [
        "cho mình biết về môn này",
        "môn này học gì vậy",
        "kể sơ qua học phần này",
        "môn này có những nội dung gì",
        "giới thiệu giúp mình môn này",
        "môn này là như thế nào",
        "cho mình xem tổng quan",
        "mình muốn tìm hiểu học phần này",
        "kể mình nghe về môn này",
        "môn này có gì hay",
        "thông tin cơ bản về môn học",
        "học phần này dạy cái gì",
        "cho xem thông tin môn",
        "nội dung môn học này thế nào",
        "tổng quan môn học",
        "môn này học những gì vậy",
        "kể mình nghe về môn cloud",
        "tìm hiểu về môn học",
    ],
    GoalIntent.COURSE_FULL_DETAILS: [
        "cho mình biết hết về môn này",
        "chi tiết toàn bộ học phần",
        "tất cả thông tin về môn đó",
        "mình muốn xem đầy đủ môn này",
        "nói kỹ hết về học phần này",
        "nói kỹ hơn đi",
        "cho mình xem hết",
        "còn gì nữa không nói hết đi",
        "tất cả luôn",
        "mình muốn biết đầy đủ mọi thứ",
        "xem toàn bộ chi tiết",
        "mình muốn biết hết về môn vừa nói",
        "nói kỹ hết đi",
        "cho xem hết thông tin môn vừa rồi",
        "chi tiết tổng thể mọi thứ",
    ],
    GoalIntent.COURSE_FIELD_LOOKUP: [
        "ai đứng lớp",
        "môn này mấy tín",
        "đầu ra có gì",
        "thi kiểu gì",
        "có học trước môn nào không",
        "thực hành nhiều không",
        "nó có nặng thực hành không",
        "ai dạy vậy",
        "môn vừa rồi ai đứng lớp",
        "môn này bao nhiêu tín chỉ",
        "chuẩn đầu ra môn này",
        "đánh giá môn này ra sao",
        "môn tiên quyết là gì",
        "thời lượng thực hành lý thuyết",
        "giảng viên phụ trách là ai",
        "email thầy cô",
        "cái này có làm lab nhiều không",
        "CLO nào liên quan AWS",
        "có bao nhiêu CLO",
        "FIT4113 có bao nhiêu CLO",
        "học kỳ mấy thì học",
    ],
    GoalIntent.COURSE_COMPARISON: [
        "so sánh hai môn này",
        "hai môn này môn nào thực hành nhiều hơn",
        "so cloud với nhúng xem môn nào nặng hơn",
        "môn nào nhiều tín chỉ hơn",
        "khác nhau giữa hai học phần này",
        "nên học môn nào trước giữa hai môn này",
        "so sánh cấu trúc đánh giá hai môn",
        "so 2 môn này xem môn nào thực hành nhiều hơn",
        "so sánh nội dung giữa hai môn",
        "cloud với nhúng môn nào thực hành nhiều hơn",
        "môn nào ít thi hơn",
        "đối chiếu hai học phần",
    ],
    GoalIntent.REGULATION_LOOKUP: [
        "điều kiện tốt nghiệp ngành cntt",
        "quy chế cảnh báo học vụ đại nam",
        "bao nhiêu điểm thì bị buộc thôi học",
        "quy định học lại cải thiện điểm",
        "chuẩn đầu ra ngoại ngữ tốt nghiệp",
        "điều kiện xét tốt nghiệp",
        "quy định làm đồ án tốt nghiệp",
        "xét học bổng khuyến khích",
        "quy chế đào tạo đại học",
    ],
    GoalIntent.GENERAL_TOPIC_EXPLANATION: [
        "hệ thống nhúng là lĩnh vực gì",
        "khái niệm điện toán đám mây là gì",
        "giải thích nguyên lý hoạt động của tcp ip",
        "thuật toán dijkstra hoạt động như thế nào",
        "tính đa hình trong oop nghĩa là gì",
        "cloud là gì",
        "hệ thống nhúng là gì",
        "định nghĩa kiến trúc vi dịch vụ microservices",
        "nguyên lý hoạt động của docker container",
        "sự khác nhau giữa rest api và graphql",
    ],
    GoalIntent.TOOL_ACTION: [
        "soạn giúp mình email gửi thầy",
        "gửi thư cho giảng viên phụ trách",
        "nhắc tôi nộp bài tập lớn lúc 17h",
        "đặt lịch nhắc ôn thi sáng mai",
        "soạn thảo thư xin nghỉ học",
        "hẹn giờ nhắc tôi ôn tập",
        "gửi email xin tài liệu môn học",
    ],
}


class SemanticIntentMatcher:
    """
    Bộ so khớp ý định mục tiêu bằng Cosine Similarity trên BGE-M3 embeddings.
    Khởi tạo 1 lần (Singleton), không tái nhúng exemplars qua từng truy vấn.
    """

    def __init__(self, model_name: Optional[str] = None):
        self._embedding_model = get_embedding_model(model_name)
        self._intent_matrices: Dict[GoalIntent, np.ndarray] = {}
        self._intent_exemplar_texts: Dict[GoalIntent, List[str]] = {}
        self._initialize_exemplars()

    def _initialize_exemplars(self) -> None:
        """Tiền mã hóa tất cả exemplars thành ma trận vector chuẩn hóa L2."""
        logger.info("SemanticIntentMatcher: Đang tiền mã hóa intent exemplars bằng BGE-M3...")
        for intent, exemplars in INTENT_EXEMPLARS.items():
            if not exemplars:
                continue
            embeddings = self._embedding_model.encode(
                exemplars,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            self._intent_matrices[intent] = np.array(embeddings, dtype=np.float32)
            self._intent_exemplar_texts[intent] = exemplars

        logger.info(
            f"SemanticIntentMatcher: Khởi tạo hoàn tất với {len(self._intent_matrices)} nhóm ý định."
        )

    def match_intent(
        self, query: str
    ) -> Tuple[GoalIntent, float, GoalIntent, float, float, Dict[GoalIntent, float]]:
        """
        So khớp câu hỏi với các exemplars của từng intent.
        Mã hóa query đúng 1 lần.

        Returns:
            (top1_intent, top1_score, top2_intent, top2_score, confidence_margin, all_scores)
        """
        clean_q = (query or "").strip()
        if not clean_q:
            return (
                GoalIntent.UNKNOWN,
                0.0,
                GoalIntent.UNKNOWN,
                0.0,
                0.0,
                {intent: 0.0 for intent in self._intent_matrices},
            )

        q_vec = self._embedding_model.encode(
            clean_q,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        q_vec = np.array(q_vec, dtype=np.float32)

        # Tính toán max similarity cho từng intent
        scores: Dict[GoalIntent, float] = {}
        for intent, matrix in self._intent_matrices.items():
            sims = np.dot(matrix, q_vec)
            # Dùng max similarity của exemplar gần nhất
            scores[intent] = float(np.max(sims))

        # Sắp xếp giảm dần
        sorted_intents = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        top1_intent, top1_score = sorted_intents[0]
        top2_intent, top2_score = sorted_intents[1] if len(sorted_intents) > 1 else (GoalIntent.UNKNOWN, 0.0)
        margin = top1_score - top2_score

        return top1_intent, top1_score, top2_intent, top2_score, margin, scores


# Global Singleton instance
_matcher_singleton: Optional[SemanticIntentMatcher] = None


def get_semantic_intent_matcher() -> SemanticIntentMatcher:
    """Lấy Singleton SemanticIntentMatcher."""
    global _matcher_singleton
    if _matcher_singleton is None:
        _matcher_singleton = SemanticIntentMatcher()
    return _matcher_singleton
