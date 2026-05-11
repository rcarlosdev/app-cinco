from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class BusinessQuerySemanticEntity:
    type: str = ""
    identifier: str = ""
    field: str = ""
    physical_field: str = ""
    resolution_source: str = "deterministic"

    def as_dict(self) -> dict[str, Any]:
        return {
            "type": str(self.type or ""),
            "identifier": str(self.identifier or ""),
            "field": str(self.field or ""),
            "physical_field": str(self.physical_field or ""),
            "resolution_source": str(self.resolution_source or "deterministic"),
        }


@dataclass(slots=True)
class BusinessQuerySemanticScope:
    families: list[str] = field(default_factory=list)
    include_serialized: bool = False
    stock_scope: str = ""
    group_dimensions: list[str] = field(default_factory=list)
    coverage: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "families": [str(item or "") for item in list(self.families or []) if str(item or "").strip()],
            "include_serialized": bool(self.include_serialized),
            "stock_scope": str(self.stock_scope or ""),
            "group_dimensions": [str(item or "") for item in list(self.group_dimensions or []) if str(item or "").strip()],
            "coverage": str(self.coverage or ""),
        }


@dataclass(slots=True)
class BusinessQuerySemanticOutput:
    expected_output: str = ""
    grain: str = ""
    columns: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "expected_output": str(self.expected_output or ""),
            "grain": str(self.grain or ""),
            "columns": [str(item or "") for item in list(self.columns or []) if str(item or "").strip()],
        }


@dataclass(slots=True)
class BusinessQuerySemanticExecution:
    capability: str = ""
    requires_sql_planner: bool = True
    planner_authority: str = "QueryExecutionPlanner"
    execute_authority: str = "planner_only"

    def as_dict(self) -> dict[str, Any]:
        return {
            "capability": str(self.capability or ""),
            "requires_sql_planner": bool(self.requires_sql_planner),
            "planner_authority": str(self.planner_authority or "QueryExecutionPlanner"),
            "execute_authority": str(self.execute_authority or "planner_only"),
        }


@dataclass(slots=True)
class BusinessQuerySemanticPlan:
    query: str
    domain: str
    intent: str
    main_entity: BusinessQuerySemanticEntity = field(default_factory=BusinessQuerySemanticEntity)
    governed_physical_field: str = ""
    grouping_dimension: list[str] = field(default_factory=list)
    inventory_family: str = ""
    scope: BusinessQuerySemanticScope = field(default_factory=BusinessQuerySemanticScope)
    output: BusinessQuerySemanticOutput = field(default_factory=BusinessQuerySemanticOutput)
    candidate_capability: str = ""
    normalized_filters: dict[str, Any] = field(default_factory=dict)
    requires_enrichment: bool = False
    applicable_business_rules: list[str] = field(default_factory=list)
    possible_alerts: list[str] = field(default_factory=list)
    known_limitations: list[str] = field(default_factory=list)
    execution: BusinessQuerySemanticExecution = field(default_factory=BusinessQuerySemanticExecution)
    ambiguity_notes: list[str] = field(default_factory=list)
    consulted_sources: list[str] = field(default_factory=list)
    memory_keys_used: list[str] = field(default_factory=list)
    llm_policy: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "query": str(self.query or ""),
            "domain": str(self.domain or ""),
            "intent": str(self.intent or ""),
            "entity": self.main_entity.as_dict(),
            "governed_physical_field": str(self.governed_physical_field or ""),
            "grouping_dimension": [str(item or "") for item in list(self.grouping_dimension or []) if str(item or "").strip()],
            "inventory_family": str(self.inventory_family or ""),
            "scope": self.scope.as_dict(),
            "output": self.output.as_dict(),
            "candidate_capability": str(self.candidate_capability or ""),
            "normalized_filters": dict(self.normalized_filters or {}),
            "requires_enrichment": bool(self.requires_enrichment),
            "applicable_business_rules": [
                str(item or "") for item in list(self.applicable_business_rules or []) if str(item or "").strip()
            ],
            "possible_alerts": [str(item or "") for item in list(self.possible_alerts or []) if str(item or "").strip()],
            "known_limitations": [str(item or "") for item in list(self.known_limitations or []) if str(item or "").strip()],
            "execution": self.execution.as_dict(),
            "ambiguity_notes": [str(item or "") for item in list(self.ambiguity_notes or []) if str(item or "").strip()],
            "consulted_sources": [str(item or "") for item in list(self.consulted_sources or []) if str(item or "").strip()],
            "memory_keys_used": [str(item or "") for item in list(self.memory_keys_used or []) if str(item or "").strip()],
            "llm_policy": dict(self.llm_policy or {}),
        }


@dataclass(slots=True)
class StructuredQueryIntent:
    raw_query: str
    domain_code: str
    operation: str
    template_id: str
    entity_type: str = ""
    entity_value: str = ""
    filters: dict[str, Any] = field(default_factory=dict)
    period: dict[str, Any] = field(default_factory=dict)
    group_by: list[str] = field(default_factory=list)
    metrics: list[str] = field(default_factory=list)
    confidence: float = 0.0
    source: str = "rules"
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "raw_query": str(self.raw_query or ""),
            "domain_code": str(self.domain_code or ""),
            "operation": str(self.operation or ""),
            "template_id": str(self.template_id or ""),
            "entity_type": str(self.entity_type or ""),
            "entity_value": str(self.entity_value or ""),
            "filters": dict(self.filters or {}),
            "period": dict(self.period or {}),
            "group_by": list(self.group_by or []),
            "metrics": list(self.metrics or []),
            "confidence": float(self.confidence or 0.0),
            "source": str(self.source or "rules"),
            "warnings": list(self.warnings or []),
        }


@dataclass(slots=True)
class ResolvedQuerySpec:
    intent: StructuredQueryIntent
    semantic_context: dict[str, Any] = field(default_factory=dict)
    normalized_filters: dict[str, Any] = field(default_factory=dict)
    normalized_period: dict[str, Any] = field(default_factory=dict)
    mapped_columns: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent.as_dict(),
            "semantic_context": dict(self.semantic_context or {}),
            "normalized_filters": dict(self.normalized_filters or {}),
            "normalized_period": dict(self.normalized_period or {}),
            "mapped_columns": dict(self.mapped_columns or {}),
            "warnings": list(self.warnings or []),
        }


@dataclass(slots=True)
class ColumnSemanticResolution:
    requested_term: str
    canonical_term: str
    table_name: str = ""
    column_name: str = ""
    supports_filter: bool = False
    supports_group_by: bool = False
    supports_metric: bool = False
    supports_dimension: bool = False
    is_date: bool = False
    is_identifier: bool = False
    is_chart_dimension: bool = False
    is_chart_measure: bool = False
    allowed_values: list[str] = field(default_factory=list)
    confidence: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "requested_term": str(self.requested_term or ""),
            "canonical_term": str(self.canonical_term or ""),
            "table_name": str(self.table_name or ""),
            "column_name": str(self.column_name or ""),
            "supports_filter": bool(self.supports_filter),
            "supports_group_by": bool(self.supports_group_by),
            "supports_metric": bool(self.supports_metric),
            "supports_dimension": bool(self.supports_dimension),
            "is_date": bool(self.is_date),
            "is_identifier": bool(self.is_identifier),
            "is_chart_dimension": bool(self.is_chart_dimension),
            "is_chart_measure": bool(self.is_chart_measure),
            "allowed_values": list(self.allowed_values or []),
            "confidence": float(self.confidence or 0.0),
        }


@dataclass(slots=True)
class RelationSemanticResolution:
    from_entity: str
    to_entity: str
    relation_name: str = ""
    join_sql: str = ""
    cardinality: str = ""
    valid: bool = False
    confidence: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "from_entity": str(self.from_entity or ""),
            "to_entity": str(self.to_entity or ""),
            "relation_name": str(self.relation_name or ""),
            "join_sql": str(self.join_sql or ""),
            "cardinality": str(self.cardinality or ""),
            "valid": bool(self.valid),
            "confidence": float(self.confidence or 0.0),
        }


@dataclass(slots=True)
class QueryExecutionPlan:
    strategy: str
    reason: str
    domain_code: str
    capability_id: str | None = None
    sql_query: str | None = None
    requires_context: bool = False
    missing_context: list[str] = field(default_factory=list)
    constraints: dict[str, Any] = field(default_factory=dict)
    policy: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "strategy": str(self.strategy or ""),
            "reason": str(self.reason or ""),
            "domain_code": str(self.domain_code or ""),
            "capability_id": self.capability_id,
            "sql_query": self.sql_query,
            "requires_context": bool(self.requires_context),
            "missing_context": list(self.missing_context or []),
            "constraints": dict(self.constraints or {}),
            "policy": dict(self.policy or {}),
            "metadata": dict(self.metadata or {}),
        }


@dataclass(slots=True)
class SatisfactionValidation:
    satisfied: bool
    reason: str
    checks: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "satisfied": bool(self.satisfied),
            "reason": str(self.reason or ""),
            "checks": dict(self.checks or {}),
        }


@dataclass(slots=True)
class SatisfactionReviewGateResult:
    approved: bool
    answered_user_goal: bool
    semantic_alignment: bool
    domain_alignment: bool
    intent_alignment: bool
    capability_alignment: bool
    evidence_sufficient: bool
    response_safe: bool
    technical_leak_detected: bool
    fallback_justified: bool
    satisfaction_score: float
    issues: list[dict[str, Any]] = field(default_factory=list)
    retry_reason: str = ""
    next_action: str = "approve"
    review_meta: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "approved": bool(self.approved),
            "answered_user_goal": bool(self.answered_user_goal),
            "semantic_alignment": bool(self.semantic_alignment),
            "domain_alignment": bool(self.domain_alignment),
            "intent_alignment": bool(self.intent_alignment),
            "capability_alignment": bool(self.capability_alignment),
            "evidence_sufficient": bool(self.evidence_sufficient),
            "response_safe": bool(self.response_safe),
            "technical_leak_detected": bool(self.technical_leak_detected),
            "fallback_justified": bool(self.fallback_justified),
            "satisfaction_score": float(self.satisfaction_score or 0.0),
            "issues": [dict(item or {}) for item in list(self.issues or []) if isinstance(item, dict)],
            "retry_reason": str(self.retry_reason or ""),
            "next_action": str(self.next_action or "approve"),
            "review_meta": dict(self.review_meta or {}),
        }


@dataclass(slots=True)
class LoopControllerDecision:
    cycle_index: int
    strategy: str
    satisfaction_score: float
    gate_status: str
    decision: str
    stop_reason: str = ""
    retry_reason: str = ""
    next_action: str = "continue"
    approved: bool = False
    should_continue: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "cycle_index": int(self.cycle_index or 0),
            "strategy": str(self.strategy or ""),
            "satisfaction_score": float(self.satisfaction_score or 0.0),
            "gate_status": str(self.gate_status or ""),
            "decision": str(self.decision or ""),
            "stop_reason": str(self.stop_reason or ""),
            "retry_reason": str(self.retry_reason or ""),
            "next_action": str(self.next_action or "continue"),
            "approved": bool(self.approved),
            "should_continue": bool(self.should_continue),
            "metadata": dict(self.metadata or {}),
        }


@dataclass(slots=True)
class QueryPatternMemory:
    scope: str
    candidate_key: str
    candidate_value: dict[str, Any]
    reason: str
    sensitivity: str = "low"
    domain_code: str = ""
    capability_id: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "scope": str(self.scope or "user"),
            "candidate_key": str(self.candidate_key or ""),
            "candidate_value": dict(self.candidate_value or {}),
            "reason": str(self.reason or ""),
            "sensitivity": str(self.sensitivity or "low"),
            "domain_code": str(self.domain_code or ""),
            "capability_id": str(self.capability_id or ""),
        }


@dataclass(slots=True)
class SemanticNormalizationOutput:
    raw_query: str
    normalized_query: str
    canonical_query: str
    domain_code: str = ""
    intent_code: str = ""
    normalized_filters: dict[str, Any] = field(default_factory=dict)
    capability_hint: str = ""
    resolved_by: str = ""
    semantic_aliases: list[dict[str, Any]] = field(default_factory=list)
    candidate_domains: list[dict[str, Any]] = field(default_factory=list)
    candidate_intents: list[dict[str, Any]] = field(default_factory=list)
    candidate_entities: list[dict[str, Any]] = field(default_factory=list)
    candidate_filters: list[dict[str, Any]] = field(default_factory=list)
    capability_hints: list[dict[str, Any]] = field(default_factory=list)
    ambiguities: list[dict[str, Any]] = field(default_factory=list)
    llm_invoked: bool = False
    llm_mode: str = "deterministic"
    normalization_status: str = "deterministic_only"
    confidence: float = 0.0
    llm_comparison: dict[str, Any] = field(default_factory=dict)
    review_notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "raw_query": str(self.raw_query or ""),
            "normalized_query": str(self.normalized_query or ""),
            "canonical_query": str(self.canonical_query or ""),
            "domain_code": str(self.domain_code or ""),
            "intent_code": str(self.intent_code or ""),
            "normalized_filters": dict(self.normalized_filters or {}),
            "capability_hint": str(self.capability_hint or ""),
            "resolved_by": str(self.resolved_by or ""),
            "semantic_aliases": [dict(item or {}) for item in list(self.semantic_aliases or []) if isinstance(item, dict)],
            "candidate_domains": [dict(item or {}) for item in list(self.candidate_domains or []) if isinstance(item, dict)],
            "candidate_intents": [dict(item or {}) for item in list(self.candidate_intents or []) if isinstance(item, dict)],
            "candidate_entities": [dict(item or {}) for item in list(self.candidate_entities or []) if isinstance(item, dict)],
            "candidate_filters": [dict(item or {}) for item in list(self.candidate_filters or []) if isinstance(item, dict)],
            "capability_hints": [dict(item or {}) for item in list(self.capability_hints or []) if isinstance(item, dict)],
            "ambiguities": [dict(item or {}) for item in list(self.ambiguities or []) if isinstance(item, dict)],
            "llm_invoked": bool(self.llm_invoked),
            "llm_mode": str(self.llm_mode or "deterministic"),
            "normalization_status": str(self.normalization_status or "deterministic_only"),
            "confidence": float(self.confidence or 0.0),
            "llm_comparison": dict(self.llm_comparison or {}),
            "review_notes": [str(item or "") for item in list(self.review_notes or []) if str(item or "").strip()],
        }


@dataclass(slots=True)
class CanonicalResolvedQuery:
    raw_query: str
    canonical_query: str
    domain_code: str
    intent_code: str
    capability_code: str
    entities: list[dict[str, Any]] = field(default_factory=list)
    filters: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    resolution_evidence: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "raw_query": str(self.raw_query or ""),
            "canonical_query": str(self.canonical_query or ""),
            "domain_code": str(self.domain_code or ""),
            "intent_code": str(self.intent_code or ""),
            "capability_code": str(self.capability_code or ""),
            "entities": [dict(item or {}) for item in list(self.entities or []) if isinstance(item, dict)],
            "filters": [dict(item or {}) for item in list(self.filters or []) if isinstance(item, dict)],
            "confidence": float(self.confidence or 0.0),
            "resolution_evidence": [
                dict(item or {})
                for item in list(self.resolution_evidence or [])
                if isinstance(item, dict)
            ],
            "conflicts": [dict(item or {}) for item in list(self.conflicts or []) if isinstance(item, dict)],
        }


@dataclass(slots=True)
class CauseDiagnosticItem:
    finding: str
    suggestion: str
    evidence_groups: list[str] = field(default_factory=list)
    confidence: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "finding": str(self.finding or ""),
            "suggestion": str(self.suggestion or ""),
            "evidence_groups": [str(item or "") for item in list(self.evidence_groups or []) if str(item or "").strip()],
            "confidence": float(self.confidence or 0.0),
        }


@dataclass(slots=True)
class CauseGenerationMeta:
    generator: str
    evidence_rows: list[dict[str, Any]] = field(default_factory=list)
    top_group: str = ""
    top_pct: float = 0.0
    confidence: float = 0.0
    validated: bool = False
    fallback_reason: str = ""
    model: str = ""
    prompt_hash: str = ""
    validation_errors: list[str] = field(default_factory=list)
    policy_decision: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "generator": str(self.generator or ""),
            "evidence_rows": [dict(item or {}) for item in list(self.evidence_rows or []) if isinstance(item, dict)],
            "top_group": str(self.top_group or ""),
            "top_pct": float(self.top_pct or 0.0),
            "confidence": float(self.confidence or 0.0),
            "validated": bool(self.validated),
            "fallback_reason": str(self.fallback_reason or ""),
            "model": str(self.model or ""),
            "prompt_hash": str(self.prompt_hash or ""),
            "validation_errors": [str(item or "") for item in list(self.validation_errors or []) if str(item or "").strip()],
            "policy_decision": dict(self.policy_decision or {}),
        }


# Backward-compatible aliases for expanded contract naming.
ResolvedBusinessQuery = ResolvedQuerySpec
ResultSatisfactionReport = SatisfactionValidation
QueryPatternMemoryRecord = QueryPatternMemory
