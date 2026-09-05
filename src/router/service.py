"""
Router Service: Singleton facade cung cấp giao diện phân loại ý định chuẩn hóa cho toàn hệ thống.
"""
import logging
from typing import Dict, Any, Optional
from src.router.schemas import IntentDecision
from src.router.normalizer import normalize_query
from src.router.evidence import extract_evidence
from src.router.policy import evaluate_policy
from src.router.semantic_classifier import SemanticClassifier

logger = logging.getLogger(__name__)

_router_service_singleton: Optional["RouterService"] = None


class RouterService:
    """
    Dịch vụ phân loại ý định cục bộ (Router V2).
    """

    def __init__(self, enable_semantic: bool = True):
        self.enable_semantic = enable_semantic
        if enable_semantic:
            self.semantic_classifier = SemanticClassifier()
        else:
            self.semantic_classifier = None
        logger.info("RouterService: Khoi tao hoan tat.")

    def classify(
        self,
        query: str,
        analyzed_query: Optional[Dict[str, Any]] = None,
    ) -> IntentDecision:
        """
        Phân loại ý định từ câu hỏi người dùng và thông tin đã phân tích (nếu có).
        """
        clean_text, lower_text = normalize_query(query)
        evidence = extract_evidence(clean_text, lower_text, analyzed_query)
        decision = evaluate_policy(
            text=clean_text,
            lower_text=lower_text,
            evidence=evidence,
            semantic_classifier=self.semantic_classifier,
        )
        return decision


def get_router_service(enable_semantic: bool = True) -> RouterService:
    """Lấy hoặc khởi tạo Singleton RouterService."""
    global _router_service_singleton
    if _router_service_singleton is None:
        _router_service_singleton = RouterService(enable_semantic=enable_semantic)
    return _router_service_singleton
