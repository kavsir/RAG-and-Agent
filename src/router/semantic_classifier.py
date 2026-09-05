"""
Semantic Classifier: Phân loại ý định bằng vector similarity với các câu prototypes chuẩn hóa.
Sử dụng singleton SentenceTransformer từ `src.ingestion.vector_store` để không tốn thêm RAM.
Hoàn toàn cục bộ, 0 lệnh gọi API bên ngoài.
"""
from typing import Dict, Tuple, Optional
import numpy as np
import logging
from src.ingestion.vector_store import get_embedding_model
from src.router.prototypes import INTENT_PROTOTYPES
from src.router.schemas import IntentCategory

logger = logging.getLogger(__name__)


class SemanticClassifier:
    """
    Bộ phân loại ngữ nghĩa cục bộ sử dụng Cosine Similarity với tập prototypes tiêu chuẩn.
    """

    def __init__(self, model_name: Optional[str] = None):
        self.embedding_model = get_embedding_model(model_name)
        self._prototype_matrices: Dict[IntentCategory, np.ndarray] = {}
        self._initialize_prototypes()

    def _initialize_prototypes(self) -> None:
        """Mã hóa trước toàn bộ prototypes thành các ma trận vector chuẩn hóa (L2 unit vectors)."""
        logger.info("SemanticClassifier: Dang ma hoa tap prototypes cuc bo...")
        for category, prototypes in INTENT_PROTOTYPES.items():
            embeddings = self.embedding_model.encode(
                prototypes,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            self._prototype_matrices[category] = np.array(embeddings, dtype=np.float32)
        logger.info(
            f"SemanticClassifier: Khoi tao thanh cong voi {len(self._prototype_matrices)} nhom y dinh."
        )

    def classify(
        self, query: str
    ) -> Tuple[IntentCategory, float, float, Dict[str, float]]:
        """
        Phân loại ngữ nghĩa câu hỏi dựa trên độ tương đồng Cosine cực đại / top-k.

        Returns:
            (top_category, top_score, margin, all_scores)
            - top_category: Nhóm ý định có điểm cao nhất.
            - top_score: Điểm tương đồng của nhóm cao nhất (0.0 - 1.0).
            - margin: Khoảng cách giữa nhóm hạng nhất và nhóm hạng nhì.
            - all_scores: Dict điểm số của từng nhóm.
        """
        if not query or not query.strip():
            return "GENERAL_LLM", 0.0, 0.0, {"DOMAIN_DATA": 0.0, "GENERAL_LLM": 0.0, "TOOL_ACTION": 0.0}

        query_vec = self.embedding_model.encode(
            query,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        query_vec = np.array(query_vec, dtype=np.float32)

        scores: Dict[str, float] = {}
        for category, matrix in self._prototype_matrices.items():
            # Ma trận đã được chuẩn hóa L2, query_vec cũng chuẩn hóa L2 -> dot product chính là Cosine Similarity
            sims = np.dot(matrix, query_vec)
            # Lấy trung bình cộng của top 2 prototypes gần nhất để giảm thiểu variance
            if len(sims) >= 2:
                top2 = np.partition(sims, -2)[-2:]
                score = float(np.mean(top2))
            else:
                score = float(np.max(sims))
            scores[category] = round(score, 4)

        sorted_cats = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        top_cat: IntentCategory = sorted_cats[0][0]  # type: ignore
        top_score = sorted_cats[0][1]
        second_score = sorted_cats[1][1]
        margin = round(top_score - second_score, 4)

        return top_cat, top_score, margin, scores
