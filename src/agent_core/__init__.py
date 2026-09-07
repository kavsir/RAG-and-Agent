"""
Agent Core V1 package.
Implements bounded goal-driven agent execution:
UNDERSTAND -> OBSERVE -> PLAN -> ACT -> VERIFY -> PROGRESS -> ASK_USER / FINISH.
"""
from src.agent_core.schemas import (
    AgentGoalState,
    AgentStatus,
    StopReason,
    EvidenceStatus,
    EvidenceRequirement,
    ActionType,
    QuestionType,
    GoalType,
    ActionPlan,
    ActionObservation,
    ProgressSnapshot,
)
def __getattr__(name: str):
    if name in ("get_agent_loop", "AgentLoop"):
        from src.agent_core.loop import get_agent_loop, AgentLoop
        return get_agent_loop if name == "get_agent_loop" else AgentLoop
    if name in ("get_agent_core_service", "AgentCoreService"):
        from src.agent_core.service import get_agent_core_service, AgentCoreService
        return get_agent_core_service if name == "get_agent_core_service" else AgentCoreService
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

__all__ = [
    "AgentGoalState",
    "AgentStatus",
    "StopReason",
    "EvidenceStatus",
    "EvidenceRequirement",
    "ActionType",
    "QuestionType",
    "GoalType",
    "ActionPlan",
    "ActionObservation",
    "ProgressSnapshot",
    "AgentLoop",
    "get_agent_loop",
    "AgentCoreService",
    "get_agent_core_service",
]
