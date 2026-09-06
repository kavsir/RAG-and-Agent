"""
Routing Policy Engine: Thực thi chính sách phân lớp đa tầng kết hợp Fast-Path và Semantic-Path.
Đảm bảo độ trễ thấp (< 5ms cho Fast Path) và độ chính xác phân loại cao, 0 external API calls.
"""
import re
import logging
from typing import Optional
from src.router.schemas import IntentDecision, RouterEvidence
from src.router.semantic_classifier import SemanticClassifier

logger = logging.getLogger(__name__)


def evaluate_policy(
    text: str,
    lower_text: str,
    evidence: RouterEvidence,
    semantic_classifier: Optional[SemanticClassifier] = None,
) -> IntentDecision:
    """
    Đánh giá câu hỏi qua 5 tầng chính sách phân định ý định:
    - Layer 0: Strong Tool Fast Path
    - Layer 1: Strong Domain Fast Path
    - Layer 2: Strong General Fast Path
    - Layer 3: Semantic Classifier Path
    - Layer 4: Low-confidence Fallback Policy
    """

    # =========================================================================
    # LAYER 0: STRONG TOOL FAST PATH
    # =========================================================================
    if evidence.tool_strength == "STRONG":
        from src.semantics import analyze_utterance, Polarity, Modality
        sem = analyze_utterance(text)
        if (
            sem.polarity == Polarity.NEGATED
            or sem.prohibition_detected
            or sem.modality in [Modality.EXPLANATORY, Modality.HYPOTHETICAL]
            or sem.is_contradictory
            or (sem.polarity == Polarity.MIXED and any(w in lower_text for w in ["đừng gửi", "không gửi", "chớ gửi", "thôi đừng", "không nhắc", "đừng nhắc"]))
        ):
            evidence.tool_strength = "NONE"
            evidence.tool_intent = None
        else:
            logger.info(
                f"Router Policy: Layer 0 Triggered -> TOOL_ACTION ({evidence.tool_intent})"
            )
            return IntentDecision(
                category="TOOL_ACTION",
                tool_intent=evidence.tool_intent,
                confidence=1.0,
                reason_code=f"STRONG_TOOL_{evidence.tool_intent}",
                decision_path="STRONG_TOOL_FAST_PATH",
                evidence=evidence.model_dump(),
            )

    # =========================================================================
    # LAYER 1: STRONG DOMAIN FAST PATH
    # =========================================================================
    # 1.1 Mã môn học trực tiếp trong câu hỏi hiện tại
    if evidence.course_code_strength == "STRONG":
        logger.info(
            f"Router Policy: Layer 1.1 Triggered -> DOMAIN_DATA (Course {evidence.course_code})"
        )
        return IntentDecision(
            category="DOMAIN_DATA",
            tool_intent=None,
            confidence=1.0,
            reason_code=f"COURSE_CODE_{evidence.course_code}",
            decision_path="STRONG_DOMAIN_FAST_PATH",
            evidence=evidence.model_dump(),
        )

    # 1.2 Phạm vi học vụ Đại Nam kết hợp mục tiêu hoặc quy chế/khung chương trình
    if evidence.academic_scope and (
        evidence.target_strength == "STRONG"
        or evidence.curriculum_scope
        or evidence.regulation_scope
    ):
        logger.info(
            "Router Policy: Layer 1.2 Triggered -> DOMAIN_DATA (Academic Scope + Target/Regulation)"
        )
        return IntentDecision(
            category="DOMAIN_DATA",
            tool_intent=None,
            confidence=0.98,
            reason_code="ACADEMIC_SCOPE_WITH_TARGET_OR_REGULATION",
            decision_path="STRONG_DOMAIN_FAST_PATH",
            evidence=evidence.model_dump(),
        )

    # 1.3 Quy chế đào tạo hoặc khung chương trình riêng lẻ
    if evidence.regulation_scope or evidence.curriculum_scope:
        logger.info(
            "Router Policy: Layer 1.3 Triggered -> DOMAIN_DATA (Regulation/Curriculum Scope)"
        )
        return IntentDecision(
            category="DOMAIN_DATA",
            tool_intent=None,
            confidence=0.95,
            reason_code="REGULATION_OR_CURRICULUM_SCOPE",
            decision_path="STRONG_DOMAIN_FAST_PATH",
            evidence=evidence.model_dump(),
        )

    # 1.4 Câu hỏi tiếp nối trong hội thoại (multi-turn) có mã môn học từ ngữ cảnh + mục tiêu học vụ rõ rệt
    if evidence.course_code_strength == "WEAK" and evidence.target_strength == "STRONG":
        logger.info(
            f"Router Policy: Layer 1.4 Triggered -> DOMAIN_DATA (Multi-turn Target {evidence.academic_target})"
        )
        return IntentDecision(
            category="DOMAIN_DATA",
            tool_intent=None,
            confidence=0.95,
            reason_code=f"MULTI_TURN_TARGET_{evidence.academic_target}",
            decision_path="STRONG_DOMAIN_FAST_PATH",
            evidence=evidence.model_dump(),
        )

    # 1.5 Mục tiêu học vụ rõ rệt đi kèm ngữ cảnh học đường (môn, học phần, khoa, trường, thầy cô)
    academic_context_cues = [
        "môn", "học phần", "khoa", "trường", "thầy", "cô", "giảng viên", "sinh viên", "học kỳ"
    ]
    has_academic_cue = any(cue in lower_text for cue in academic_context_cues)
    if evidence.target_strength == "STRONG" and has_academic_cue:
        logger.info(
            f"Router Policy: Layer 1.5 Triggered -> DOMAIN_DATA (Academic Target {evidence.academic_target})"
        )
        return IntentDecision(
            category="DOMAIN_DATA",
            tool_intent=None,
            confidence=0.95,
            reason_code=f"ACADEMIC_TARGET_WITH_CUES_{evidence.academic_target}",
            decision_path="STRONG_DOMAIN_FAST_PATH",
            evidence=evidence.model_dump(),
        )

    # =========================================================================
    # LAYER 2: STRONG GENERAL FAST PATH
    # =========================================================================
    general_tech_tokens = [
        "thuật toán", "giao thức", "tcp", "udp", "dijkstra", "quicksort", "bubble sort",
        "rest api", "cloud computing", "oop", "lập trình hướng đối tượng",
        "microservice", "docker", "thread", "process", "sql", "nosql",
        "python", "java", "c++", "javascript", "kiến trúc phần mềm",
        "thiết kế hệ thống", "garbage collection",
        "hệ thống nhúng", "vi điều khiển", "arm", "stm32", "esp32", "arduino"
    ]
    greetings = ["xin chào", "hello", "hi", "chào bạn", "bạn là ai", "bạn tên gì", "giới thiệu bản thân"]
    has_greeting = any(re.search(rf"\b{re.escape(gr)}\b", lower_text) for gr in greetings)
    has_general_tech = any(re.search(rf"\b{re.escape(gt)}\b", lower_text) for gt in general_tech_tokens)

    is_pure_general_signal = (
        evidence.tool_strength == "NONE"
        and evidence.course_code_strength in ["NONE", "WEAK"]
        and not evidence.academic_scope
        and not evidence.curriculum_scope
        and not evidence.regulation_scope
        and evidence.target_strength == "NONE"
    )

    if is_pure_general_signal and (has_greeting or (has_general_tech and evidence.conceptual_question_signal)):
        logger.info("Router Policy: Layer 2 Triggered -> GENERAL_LLM (Pure General/Tech Signal)")
        return IntentDecision(
            category="GENERAL_LLM",
            tool_intent=None,
            confidence=0.98,
            reason_code="STRONG_GENERAL_FAST_PATH_SIGNAL",
            decision_path="STRONG_GENERAL_FAST_PATH",
            evidence=evidence.model_dump(),
        )

    # =========================================================================
    # LAYER 3: SEMANTIC CLASSIFIER PATH (Local Vector Cosine Similarity)
    # =========================================================================
    if semantic_classifier is not None:
        top_cat, top_score, margin, scores = semantic_classifier.classify(text)
        logger.info(
            f"Router Policy: Layer 3 Evaluated -> top={top_cat} (score={top_score:.4f}, margin={margin:.4f})"
        )

        if margin >= 0.05:
            tool_intent = None
            if top_cat == "TOOL_ACTION":
                from src.semantics import analyze_utterance, Polarity, Modality
                sem = analyze_utterance(text)
                if (
                    sem.polarity == Polarity.NEGATED
                    or sem.prohibition_detected
                    or sem.modality in [Modality.EXPLANATORY, Modality.HYPOTHETICAL]
                    or sem.is_contradictory
                    or (sem.polarity == Polarity.MIXED and any(w in lower_text for w in ["đừng gửi", "không gửi", "chớ gửi", "thôi đừng", "không nhắc", "đừng nhắc"]))
                ):
                    top_cat = "GENERAL_LLM"
                    tool_intent = None
                else:
                    tool_intent = evidence.tool_intent
                    if not tool_intent:
                        tool_intent = (
                            "SEND_EMAIL"
                            if any(w in lower_text for w in ["email", "mail", "thư"])
                            else "SET_REMINDER"
                        )

            return IntentDecision(
                category=top_cat,
                tool_intent=tool_intent,
                confidence=round(min(1.0, 0.70 + top_score * 0.30), 4),
                reason_code=f"SEMANTIC_MARGIN_{margin:.2f}_TOP_{top_cat}",
                decision_path="SEMANTIC_CLASSIFIER",
                evidence={
                    **evidence.model_dump(),
                    "semantic_scores": scores,
                    "margin": margin,
                },
            )

    # =========================================================================
    # LAYER 4: LOW-CONFIDENCE FALLBACK POLICY
    # =========================================================================
    logger.info("Router Policy: Layer 4 Triggered -> Low-confidence Fallback Policy")
    if evidence.course_code_strength == "STRONG" or evidence.academic_scope or has_academic_cue:
        return IntentDecision(
            category="DOMAIN_DATA",
            tool_intent=None,
            confidence=0.55,
            reason_code="FALLBACK_ACADEMIC_BIAS",
            decision_path="LOW_CONFIDENCE_FALLBACK",
            evidence=evidence.model_dump(),
        )

    if any(w in lower_text for w in ["gửi", "soạn", "nhắc", "lịch", "báo", "hẹn"]):
        from src.semantics import analyze_utterance, Polarity, Modality
        sem = analyze_utterance(text)
        if (
            sem.polarity == Polarity.NEGATED
            or sem.prohibition_detected
            or sem.modality in [Modality.EXPLANATORY, Modality.HYPOTHETICAL]
            or sem.is_contradictory
            or (sem.polarity == Polarity.MIXED and any(w in lower_text for w in ["đừng gửi", "không gửi", "chớ gửi", "thôi đừng", "không nhắc", "đừng nhắc"]))
        ):
            return IntentDecision(
                category="GENERAL_LLM",
                tool_intent=None,
                confidence=0.55,
                reason_code="FALLBACK_NEGATED_TOOL_TO_GENERAL",
                decision_path="LOW_CONFIDENCE_FALLBACK",
                evidence=evidence.model_dump(),
            )

        tool_intent = (
            "SEND_EMAIL"
            if any(w in lower_text for w in ["email", "mail", "thư"])
            else "SET_REMINDER"
        )
        return IntentDecision(
            category="TOOL_ACTION",
            tool_intent=tool_intent,
            confidence=0.55,
            reason_code="FALLBACK_TOOL_BIAS",
            decision_path="LOW_CONFIDENCE_FALLBACK",
            evidence=evidence.model_dump(),
        )

    return IntentDecision(
        category="GENERAL_LLM",
        tool_intent=None,
        confidence=0.50,
        reason_code="FALLBACK_DEFAULT_GENERAL",
        decision_path="LOW_CONFIDENCE_FALLBACK",
        evidence=evidence.model_dump(),
    )
