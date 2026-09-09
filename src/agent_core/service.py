"""
Service layer for Agent Core V1.1.
Manages active goal states, human-in-the-loop resumption, and SQLite persistence.
Strictly scopes goals by (user_id, conversation_id, goal_id).
"""
from typing import Dict, Any, Optional
import uuid

from src.agent_core.schemas import (
    AgentGoalState,
    AgentStatus,
    StopReason,
)
from src.agent_core.loop import get_agent_loop, AgentLoop
from src.agent_core.goal_store import get_agent_goal_store, AgentGoalStore


class AgentCoreService:
    """
    Public Service API for Agent Core V1.1.
    Provides execution, scoped session/goal management, and resumption for clarify/approval flows.
    """

    def __init__(
        self,
        loop: Optional[AgentLoop] = None,
        goal_store: Optional[AgentGoalStore] = None,
    ):
        self.loop = loop or get_agent_loop()
        self.goal_store = goal_store or get_agent_goal_store()

    def process_query(
        self,
        query: str,
        user_id: str = "default_user",
        conversation_id: str = "default_conv",
        session_context: Optional[Dict[str, Any]] = None,
        personal_context: Optional[Dict[str, Any]] = None,
        router_hint: Optional[Dict[str, Any]] = None,
        goal_id: Optional[str] = None,
        event_sink: Optional[Any] = None,
    ) -> AgentGoalState:
        """
        Process a user query through the Agent Core execution loop.
        Persists active goals awaiting user input to SQLite.
        """
        gid = goal_id or f"goal-{uuid.uuid4().hex[:8]}"
        if event_sink and hasattr(event_sink, "set_goal_id"):
            event_sink.set_goal_id(gid)

        result = self.loop.run(
            query=query,
            session_context=session_context,
            personal_context=personal_context,
            router_hint=router_hint,
            goal_id=gid,
            event_sink=event_sink,
        )
        result.user_id = user_id
        result.conversation_id = conversation_id

        # Persist to SQLite store
        self.goal_store.save_goal(user_id=user_id, conversation_id=conversation_id, state=result)
        return result

    def resume_goal(
        self,
        user_id: str,
        conversation_id: str,
        user_response: str,
        goal_id: Optional[str] = None,
        session_context: Optional[Dict[str, Any]] = None,
        personal_context: Optional[Dict[str, Any]] = None,
        event_sink: Optional[Any] = None,
    ) -> AgentGoalState:
        """
        Resume an existing goal paused for user clarification or proposal confirmation.
        Scoped strictly by user_id and conversation_id.
        """
        state = self.goal_store.get_active_goal(
            user_id=user_id, conversation_id=conversation_id, goal_id=goal_id
        )
        if not state:
            if goal_id:
                state = self.goal_store.get_goal(user_id=user_id, conversation_id=conversation_id, goal_id=goal_id)
            if not state:
                return AgentGoalState(
                    goal_id=goal_id or f"goal-{uuid.uuid4().hex[:8]}",
                    original_query=user_response,
                    current_user_input=user_response,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    status=AgentStatus.ABSTAINED,
                    stop_reason=StopReason.FAILED,
                    final_answer="Không tìm thấy mục tiêu đang chờ làm rõ trong phiên hội thoại này.",
                )

        if event_sink and hasattr(event_sink, "set_goal_id") and state:
            event_sink.set_goal_id(state.goal_id)

        result = self.loop.resume_with_user_response(
            state=state,
            user_response=user_response,
            session_context=session_context,
            event_sink=event_sink,
        )
        result.user_id = user_id
        result.conversation_id = conversation_id

        self.goal_store.save_goal(user_id=user_id, conversation_id=conversation_id, state=result)
        return result

    def get_active_goal(
        self, user_id: str, conversation_id: str, goal_id: Optional[str] = None
    ) -> Optional[AgentGoalState]:
        """Retrieve an active goal awaiting input."""
        return self.goal_store.get_active_goal(
            user_id=user_id, conversation_id=conversation_id, goal_id=goal_id
        )

    def clear_active_goals(self):
        """Clear all active goals (for testing/cleanup)."""
        self.goal_store.clear_all()


# Global Singleton
_agent_core_service_instance: Optional[AgentCoreService] = None


def get_agent_core_service() -> AgentCoreService:
    global _agent_core_service_instance
    if _agent_core_service_instance is None:
        _agent_core_service_instance = AgentCoreService()
    return _agent_core_service_instance
