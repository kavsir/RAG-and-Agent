"""
Reranker: Xếp hạng lại danh sách tài liệu ứng viên bằng Cross-Encoder hoặc Fallback an toàn.
"""
import logging
from typing import List, Dict, Any, Optional
from src.config.settings import settings

logger = logging.getLogger(__name__)

_cross_encoder_singleton = None
_reranker_failed = False


def get_cross_encoder():
    """Tải Singleton CrossEncoder với cơ chế an toàn nếu thiếu RAM/GPU."""
    global _cross_encoder_singleton, _reranker_failed
    if _reranker_failed or not settings.ENABLE_RERANKER:
        return None

    if _cross_encoder_singleton is None:
        try:
            from sentence_transformers import CrossEncoder
            model_name = settings.RERANKER_MODEL
            logger.info(f"Dang tai Reranker model: {model_name}")
            _cross_encoder_singleton = CrossEncoder(model_name)
            logger.info("Reranker model san sang.")
        except Exception as e:
            logger.warning(f"Khong the tai CrossEncoder ({e}). Chuyen sang fallback hybrid score.")
            _reranker_failed = True
            return None

    return _cross_encoder_singleton


def rerank_documents(
    query: str,
    candidates: List[Dict[str, Any]],
    top_k: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Xếp hạng lại các tài liệu ứng viên.
    Nếu CrossEncoder khả dụng, dùng model để chấm điểm cặp (query, document).
    Nếu không khả dụng, giữ nguyên thứ tự sắp xếp theo điểm hybrid fusion hiện có.
    """
    k = top_k or settings.RERANK_TOP_K
    if not candidates:
        return []

    model = get_cross_encoder()
    if model is None:
        # Fallback to current score
        logger.debug("Dung hybrid fusion score de sap xep candidates.")
        return candidates[:k]

    try:
        pairs = [(query, doc["text"]) for doc in candidates]
        scores = model.predict(pairs)

        for i, doc in enumerate(candidates):
            doc["rerank_score"] = float(scores[i])

        reranked = sorted(candidates, key=lambda x: x.get("rerank_score", 0.0), reverse=True)
        logger.debug(f"Da rerank {len(candidates)} candidates, giu lai {len(reranked[:k])}")
        return reranked[:k]
    except Exception as e:
        logger.warning(f"Loi trong qua trinh rerank: {e}. Fallback ve hybrid order.")
        return candidates[:k]
