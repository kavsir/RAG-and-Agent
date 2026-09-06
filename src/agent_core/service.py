"""
Service layer for Agent Core V1.
Manages active goal states, human-in-the-loop resumption, and singleton lifecycle.
"""
from typing import Dict, Any, Optional
import uuid

from src.agent_core.schemas import (
    AgentGoalState,
    AgentStatus,
    GoalType,
    StopReason,
)
from src.agent_core.loop import get_agent_loop, AgentLoop


class AgentCoreService:
    """
    Public Service API for Agent Core V1.
    Provides execution, session/goal management, and resumption for clarify/approval flows.
    """

    def __init__(self, loop: Optional[AgentLoop] = None):
        self.loop = loop or get_agent_loop()
        self._active_goals: Dict[str, AgentGoalState] = {}
        self._goal_history: Dict[str, AgentGoalState] = {}

    def process_query(
        self,
        query: str,
        session_context: Optional[Dict[str, Any]] = None,
        personal_context: Optional[Dict[str, Any]] = None,
        router_hint: Optional[Dict[str, Any]] = None,
        goal_id: Optional[str] = None,
    ) -> AgentGoalState:
        """
        Process a user query through the Agent Core execution loop.
        Stores pending goals waiting for user clarification.
        """
        gid = goal_id or f"goal-{uuid.uuid4().hex[:8]}"

        result = self.loop.run(
            query=query,
            session_context=session_context,
            personal_context=personal_context,
            router_hint=router_hint,
            goal_id=gid,
        )

        # Lưu trạng thái
        if result.status == AgentStatus.NEEDS_USER_INPUT:
            self._active_goals[result.goal_id] = result
        else:
            self._goal_history[result.goal_id] = result
            if result.goal_id in self._active_goals:
                del self._active_goals[result.goal_id]

        return result

    def resume_goal(
        self,
        goal_id: str,
        user_response: str,
        session_context: Optional[Dict[str, Any]] = None,
    ) -> AgentGoalState:
        """
        Resume an existing goal paused for user clarification or proposal confirmation.
        """
        state = self._active_goals.get(goal_id)
        if not state:
            state = self._goal_history.get(goal_id)
            if not state:
                return AgentGoalState(
                    goal_id=goal_id,
                    original_query=user_response,
                    current_user_input=user_response,
                    status=AgentStatus.ABSTAINED,
                    stop_reason=StopReason.FAILED,
                    final_answer=f"Không tìm thấy phiên mục tiêu tương ứng với mã '{goal_id}'.",
                )

        result = self.loop.resume_with_user_response(
            state=state,
            user_response=user_response,
            session_context=session_context,
        )

        if result.status == AgentStatus.NEEDS_USER_INPUT:
            self._active_goals[result.goal_id] = result
        else:
            self._goal_history[result.goal_id] = result
            if result.goal_id in self._active_goals:
                del self._active_goals[result.goal_id]

        return result

    def get_active_goal(self, goal_id: str) -> Optional[AgentGoalState]:
        """Retrieve an active goal awaiting input."""
        return self._active_goals.get(goal_id)

    def clear_active_goals(self):
        """Clear all active goals (for testing/cleanup)."""
        self._active_goals.clear()
        self._goal_history.clear()


# Global Singleton
_agent_core_service_instance: Optional[AgentCoreService] = None


def get_agent_core_service() -> AgentCoreService:
    global _agent_core_service_instance
    if _agent_core_service_instance is None:
        _agent_core_service_instance = AgentCoreService()
    return _agent_core_service_instance
