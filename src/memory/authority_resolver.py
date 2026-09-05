"""
Authority Resolver: Cơ chế phân giải quyền lực và giải quyết xung đột dữ liệu theo từng miền nghiệp vụ riêng biệt.
Không sử dụng một thứ tự ưu tiên số học toàn cục duy nhất.
"""
import logging
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)


class AuthorityDomain:
    ACADEMIC_TRUTH = "ACADEMIC_TRUTH"
    PERSONAL_PREFERENCE = "PERSONAL_PREFERENCE"
    CONVERSATION_ENTITY = "CONVERSATION_ENTITY"


def resolve_academic_fact(
    rag_fact: Any,
    personal_claim: Optional[Any] = None,
    session_claim: Optional[Any] = None,
) -> Tuple[Any, str]:
    """
    Phân giải sự thật học vụ (Academic Factual Truth):
    OFFICIAL RAG DOCUMENT > Personal Memory > Session Memory.
    Sự thật học vụ từ tài liệu chính thống luôn luôn là tối thượng (Sole Source of Truth).
    Personal Memory tuyệt đối không bao giờ được ghi đè thông tin học vụ nhà trường.
    """
    if rag_fact is not None and rag_fact != "":
        if personal_claim is not None and personal_claim != rag_fact:
            logger.warning(
                f"Authority Conflict [Academic]: RAG fact '{rag_fact}' OVERRIDES personal claim '{personal_claim}'"
            )
        return rag_fact, "OFFICIAL_RAG"

    if personal_claim is not None:
        logger.info("Authority Fallback [Academic]: RAG is empty, personal claim referenced with low authority")
        return personal_claim, "PERSONAL_CLAIM"

    return session_claim, "SESSION_CLAIM"


def resolve_personal_preference(
    fact_key: str,
    explicit_current: Optional[Any] = None,
    stored_personal: Optional[Any] = None,
    system_default: Optional[Any] = None,
) -> Tuple[Any, str]:
    """
    Phân giải sở thích / thông tin cá nhân (Personal Identity & Preferences):
    CURRENT EXPLICIT USER STATEMENT > EXPLICIT STORED PERSONAL MEMORY > SYSTEM DEFAULT.
    """
    if explicit_current is not None and explicit_current != "":
        return explicit_current, "CURRENT_EXPLICIT_STATEMENT"

    if stored_personal is not None and stored_personal != "":
        return stored_personal, "STORED_PERSONAL_MEMORY"

    return system_default, "SYSTEM_DEFAULT"


def resolve_conversation_entity(
    entity_type: str,
    explicit_query_entity: Optional[str] = None,
    session_state_entity: Optional[str] = None,
    personal_memory_entity: Optional[str] = None,
) -> Tuple[Optional[str], str]:
    """
    Phân giải thực thể hội thoại (Conversation Entity Context):
    CURRENT EXPLICIT QUERY > SESSION STATE > OLD PERSONAL/EPISODIC MEMORY.
    """
    if explicit_query_entity:
        return explicit_query_entity, "CURRENT_EXPLICIT_QUERY"

    if session_state_entity:
        return session_state_entity, "SESSION_STATE"

    if personal_memory_entity:
        return personal_memory_entity, "PERSONAL_MEMORY"

    return None, "NONE"
