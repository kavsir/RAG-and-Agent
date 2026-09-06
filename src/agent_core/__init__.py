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
from src.agent_core.loop import get_agent_loop, AgentLoop
from src.agent_core.service import get_agent_core_service, AgentCoreService

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
