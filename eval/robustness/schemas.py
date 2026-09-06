"""
Schemas & Data Models for Robustness Benchmark Framework V3.
Provides standardized models for adversarial inputs, metamorphic tests,
stateful scenarios, execution results, and reporting metrics.
"""
from enum import Enum
from typing import Dict, Any, List, Optional, Union
from pydantic import BaseModel, Field


class FailureType(str, Enum):
    ROUTING_FAILURE = "ROUTING_FAILURE"
    ENTITY_RESOLUTION_FAILURE = "ENTITY_RESOLUTION_FAILURE"
    MEMORY_POISONING = "MEMORY_POISONING"
    MEMORY_LEAKAGE = "MEMORY_LEAKAGE"
    CACHE_COLLISION = "CACHE_COLLISION"
    UNSAFE_TOOL_ACTIVATION = "UNSAFE_TOOL_ACTIVATION"
    RAG_AUTHORITY_VIOLATION = "RAG_AUTHORITY_VIOLATION"
    UNRELATED_SOURCE = "UNRELATED_SOURCE"
    PROMPT_INJECTION_FAILURE = "PROMPT_INJECTION_FAILURE"
    MALFORMED_INPUT_CRASH = "MALFORMED_INPUT_CRASH"
    STATE_CORRUPTION = "STATE_CORRUPTION"
    ARCHITECTURE_GAP_MULTI_INTENT = "ARCHITECTURE_GAP_MULTI_INTENT"
    ARCHITECTURE_GAP_MULTI_ENTITY = "ARCHITECTURE_GAP_MULTI_ENTITY"
    OTHER = "OTHER"


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class AdversarialCase(BaseModel):
    case_id: str
    category: str
    input_text: str
    expected_category: Optional[str] = None
    expected_course_code: Optional[str] = None
    invariants: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MetamorphicSeed(BaseModel):
    seed_id: str
    seed_query: str
    expected_category: str
    expected_course_code: Optional[str] = None
    relation_type: str = "LABEL_INVARIANCE"  # LABEL_INVARIANCE | CODE_INVARIANCE
    description: str = ""


class ChaosTurn(BaseModel):
    turn_id: int
    user_input: str
    expected_category: Optional[str] = None
    expected_active_entity: Optional[str] = None
    verify_session_isolation: bool = True
    verify_cache_safety: bool = True
    adversarial_type: Optional[str] = None


class StatefulScenario(BaseModel):
    scenario_id: str
    title: str
    session_id: str
    user_id: str = "local-user"
    turns: List[ChaosTurn]


class CaseResult(BaseModel):
    case_id: str
    layer: str  # canonical | adversarial | mutation | property | stateful | live
    group: str = "DEFAULT"
    category: Optional[str] = None
    input_text: str
    passed: bool
    expected: Optional[str] = None
    actual: Optional[str] = None
    failure_type: Optional[FailureType] = None
    severity: Optional[Severity] = None
    latency_ms: float = 0.0
    detail: str = ""
    error_message: Optional[str] = None
    observed: Dict[str, Any] = Field(default_factory=dict)
    mutation_trace: Optional[List[str]] = None


class LayerMetric(BaseModel):
    layer_name: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    accuracy_pct: float = 0.0
    pass_rate: float = 0.0
    avg_latency_ms: float = 0.0
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0
    failures_by_type: Dict[str, int] = Field(default_factory=dict)
    failures_by_severity: Dict[str, int] = Field(default_factory=dict)


class RobustnessReport(BaseModel):
    commit_sha: str = ""
    commit_hash: Optional[str] = None
    timestamp: str
    seed: int = 20260906
    total_cases: int = 0
    passed_cases: int = 0
    failed_cases: int = 0
    overall_pass_rate: float = 0.0
    hard_safety_passed: bool = True
    verdict: str = "ROBUSTNESS_V3_ACCEPTED"
    crash_rate_pct: float = 0.0
    crash_rate: float = 0.0
    unsafe_tool_rate_pct: float = 0.0
    unsafe_tool_activation_rate: float = 0.0
    cross_session_leakage_pct: float = 0.0
    cross_session_leakage_rate: float = 0.0
    cross_principal_leakage_rate: float = 0.0
    memory_poisoning_rate_pct: float = 0.0
    unknown_entity_hallucination_pct: float = 0.0
    cache_collision_pct: float = 0.0
    cache_collision_rate: float = 0.0
    academic_authority_violation_pct: float = 0.0
    academic_authority_violation_rate: float = 0.0
    prompt_injection_violation_pct: float = 0.0
    metamorphic_consistency_pct: float = 0.0
    architecture_gap_count: int = 0
    critical_failure_count: int = 0
    external_llm_calls: int = 0
    external_api_calls: Dict[str, Any] = Field(default_factory=dict)
    layers: List[LayerMetric] = Field(default_factory=list)
    layer_metrics: Dict[str, LayerMetric] = Field(default_factory=dict)
    failure_taxonomy: Dict[str, int] = Field(default_factory=dict)
    architecture_gaps: List[Dict[str, Any]] = Field(default_factory=list)
