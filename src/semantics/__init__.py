"""
Utterance Semantics and Action Authorization Package.
Part of Round S1.
Provides centralized linguistic semantics analysis and action authorization gate.
"""
from src.semantics.schemas import (
    Polarity,
    Modality,
    SubjectScope,
    ActionOperation,
    UtteranceSemantics,
    ActionAuthorizationDecision,
)
from src.semantics.analyzer import (
    UtteranceSemanticsAnalyzer,
    get_semantics_analyzer,
    analyze_utterance,
)
from src.semantics.action_policy import (
    ActionAuthorizationGate,
    authorize_tool_action,
)

__all__ = [
    "Polarity",
    "Modality",
    "SubjectScope",
    "ActionOperation",
    "UtteranceSemantics",
    "ActionAuthorizationDecision",
    "UtteranceSemanticsAnalyzer",
    "get_semantics_analyzer",
    "analyze_utterance",
    "ActionAuthorizationGate",
    "authorize_tool_action",
]
