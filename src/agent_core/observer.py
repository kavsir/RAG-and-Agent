"""
Agent Observer for Goal-Driven Agent Core V1.
Implements the OBSERVE phase:
- Collects and structures information from Environment, Memory, Semantics, and Catalogs.
- Does NOT answer the user.
- Emits typed AgentObservation to feed the Planner.
"""
from typing import Dict, Any, Optional
from src.agent_core.schemas import AgentObservation, AgentGoalState
from src.agent_core.entity_catalog import get_entity_catalog
from src.agent_core.environment_catalog import get_knowledge_environment_catalog
from src.semantics import analyze_utterance


class AgentObserver:
    """Bộ quan sát trạng thái đa nguồn của Agent."""

    def __init__(self):
        self.entity_catalog = get_entity_catalog()
        self.env_catalog = get_knowledge_environment_catalog()

    def observe(
        self,
        current_input: str,
        state: Optional[AgentGoalState] = None,
        session_context: Optional[Dict[str, Any]] = None,
        personal_context: Optional[Dict[str, Any]] = None,
        router_hint: Optional[Dict[str, Any]] = None,
    ) -> AgentObservation:
        """Thu thập quan sát toàn diện không làm biến đổi trạng thái."""
        raw_text = (current_input or "").strip()

        # 1. Quan sát ngữ nghĩa phát ngôn
        sem_res = analyze_utterance(raw_text)
        sem_dict = {
            "polarity": sem_res.polarity.value,
            "modality": sem_res.modality.value,
            "is_contradictory": sem_res.is_contradictory,
            "prohibition_detected": sem_res.prohibition_detected,
            "action_requests": [a.value for a in sem_res.action_requests],
            "action_prohibitions": [p.value for p in sem_res.action_prohibitions],
            "target_operation": sem_res.target_operation.value,
        }

        # 2. Quan sát thực thể từ EntityCatalog
        known_ents = self.entity_catalog.extract_known_entities(raw_text)
        unknown_ents = self.entity_catalog.find_unknown_entities(raw_text)
        conflict = self.entity_catalog.check_entity_conflict(raw_text)
        conflicts_list = [conflict] if conflict else []

        # 3. Quan sát phiên làm việc
        active_entities = list(known_ents)
        if session_context:
            sess_course = session_context.get("active_course_code") or session_context.get("active_entity")
            if sess_course and sess_course not in active_entities and self.entity_catalog.is_known_code(sess_course):
                active_entities.append(sess_course)

        # 4. Quan sát môi trường tri thức
        avail_fields = list(self.env_catalog.FIELD_TO_DOC_TYPES.keys())
        unavail_fields = list(self.env_catalog.UNAVAILABLE_FIELDS.keys())

        return AgentObservation(
            current_query=raw_text,
            semantics=sem_dict,
            session_context=session_context,
            active_entities=active_entities,
            personal_context=personal_context,
            router_hint=router_hint,
            catalog_known_entities=known_ents,
            catalog_unknown_entities=unknown_ents,
            entity_conflicts=conflicts_list,
            data_available_fields=avail_fields,
            data_unavailable_fields=unavail_fields,
        )


# Singleton Instance
_observer_instance: AgentObserver = None


def get_agent_observer() -> AgentObserver:
    global _observer_instance
    if _observer_instance is None:
        _observer_instance = AgentObserver()
    return _observer_instance
