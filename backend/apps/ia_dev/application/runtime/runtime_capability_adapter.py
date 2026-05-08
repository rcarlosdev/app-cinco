from __future__ import annotations

from typing import Any

from apps.ia_dev.application.context.run_context import RunContext
from apps.ia_dev.application.contracts.query_intelligence_contracts import (
    QueryExecutionPlan,
    ResolvedQuerySpec,
)
from apps.ia_dev.application.policies.policy_guard import PolicyAction, PolicyDecision
from apps.ia_dev.application.routing.capability_catalog import CapabilityCatalog
from apps.ia_dev.application.taxonomia_dominios import (
    dominio_desde_capacidad,
    es_dominio_operativo,
    normalizar_codigo_dominio,
)
from apps.ia_dev.domains.ausentismo.handler import AusentismoHandler
from apps.ia_dev.domains.empleados.handler import EmpleadosHandler
from apps.ia_dev.domains.transport.handler import TransportHandler


class RuntimeCapabilityAdapter:
    def __init__(
        self,
        *,
        catalog: CapabilityCatalog | None = None,
        attendance_handler: AusentismoHandler | None = None,
        empleados_handler: EmpleadosHandler | None = None,
        transport_handler: TransportHandler | None = None,
    ):
        self.catalog = catalog or CapabilityCatalog()
        self._attendance_handler = attendance_handler
        self._empleados_handler = empleados_handler
        self._transport_handler = transport_handler

    def build_bootstrap_plan(
        self,
        *,
        classification: dict[str, Any],
        query_intelligence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        capability_id = self._resolve_primary_capability_id(
            classification=classification,
            query_intelligence=query_intelligence or {},
        )
        return self._build_plan(
            capability_id=capability_id,
            reason="runtime_bootstrap_plan",
            classification=classification,
            query_constraints=self._resolve_query_constraints(query_intelligence=query_intelligence or {}),
            candidate_rank=1,
            candidate_score=100,
        )

    def build_candidate_hints(
        self,
        *,
        message: str,
        classification: dict[str, Any],
        query_intelligence: dict[str, Any] | None = None,
        max_candidates: int = 4,
    ) -> list[dict[str, Any]]:
        plans = self.build_candidate_plans(
            message=message,
            classification=classification,
            planning_context={"query_intelligence": dict(query_intelligence or {})},
            fallback_plan=self.build_bootstrap_plan(
                classification=classification,
                query_intelligence=query_intelligence or {},
            ),
            max_candidates=max_candidates,
        )
        return [
            {
                "capability_id": str(item.get("capability_id") or ""),
                "reason": str(item.get("reason") or ""),
                "source_domain": str((item.get("source") or {}).get("domain") or ""),
                "source_intent": str((item.get("source") or {}).get("intent") or ""),
                "query_constraints": dict(item.get("query_constraints") or {}),
            }
            for item in plans
        ]

    def build_candidate_plans(
        self,
        *,
        message: str,
        classification: dict[str, Any],
        planning_context: dict[str, Any] | None,
        fallback_plan: dict[str, Any],
        max_candidates: int = 4,
    ) -> list[dict[str, Any]]:
        planning_context = dict(planning_context or {})
        query_intelligence = dict(planning_context.get("query_intelligence") or {})
        execution_plan = dict(query_intelligence.get("execution_plan") or {})
        resolved_query = dict(query_intelligence.get("resolved_query") or {})
        constraints = self._resolve_query_constraints(query_intelligence=query_intelligence)

        candidates: list[tuple[str, str]] = []
        explicit_capability = str(execution_plan.get("capability_id") or "").strip()
        if explicit_capability:
            candidates.append((explicit_capability, "runtime_execution_plan_capability"))

        semantic_capability = self._resolve_capability_from_resolved_query(resolved_query=resolved_query)
        if semantic_capability:
            candidates.append((semantic_capability, "runtime_resolved_query_capability"))

        primary_capability = self._resolve_primary_capability_id(
            classification=classification,
            query_intelligence=query_intelligence,
        )
        if primary_capability:
            candidates.append((primary_capability, "runtime_classification_capability"))

        fallback_capability = str(fallback_plan.get("capability_id") or "").strip()
        if fallback_capability:
            candidates.append((fallback_capability, "runtime_fallback_capability"))

        plans: list[dict[str, Any]] = []
        seen: set[str] = set()
        for capability_id, reason in candidates:
            if not capability_id or capability_id in seen:
                continue
            seen.add(capability_id)
            plans.append(
                self._build_plan(
                    capability_id=capability_id,
                    reason=reason,
                    classification=classification,
                    query_constraints=constraints,
                    candidate_rank=len(plans) + 1,
                    candidate_score=max(10, 110 - len(plans) * 10),
                )
            )
            if len(plans) >= max(1, int(max_candidates)):
                break
        return plans or [dict(fallback_plan)]

    def build_route(
        self,
        *,
        run_context: RunContext,
        planned_capability: dict[str, Any],
        policy_decision: PolicyDecision,
    ) -> dict[str, Any]:
        capability_id = str(planned_capability.get("capability_id") or "legacy.passthrough.v1").strip()
        routing_mode = str(run_context.routing_mode or "intent")
        capability_exists = bool(planned_capability.get("capability_exists"))
        rollout_enabled = bool(planned_capability.get("rollout_enabled", True))
        capability_domain = dominio_desde_capacidad(capability_id) or "legacy"
        policy_allows = policy_decision.action == PolicyAction.ALLOW

        if routing_mode != "capability":
            return {
                "routing_mode": routing_mode,
                "selected_capability_id": capability_id,
                "execute_capability": False,
                "use_legacy": True,
                "reason": "intent_mode_keeps_legacy_path",
                "policy_action": policy_decision.action.value,
                "policy_allowed": policy_allows,
                "capability_exists": capability_exists,
                "rollout_enabled": rollout_enabled,
            }

        if not policy_allows:
            runtime_action = str((policy_decision.metadata or {}).get("runtime_action") or "").strip().lower()
            deny_reason = "policy_denied_or_requires_approval"
            if runtime_action in {"force_legacy_fallback", "disable_capability", "restrict_scope"}:
                deny_reason = "policy_forced_legacy_fallback"
            return {
                "routing_mode": routing_mode,
                "selected_capability_id": capability_id,
                "execute_capability": False,
                "use_legacy": True,
                "reason": deny_reason,
                "policy_action": policy_decision.action.value,
                "policy_allowed": False,
                "policy_runtime_action": runtime_action or None,
                "capability_exists": capability_exists,
                "rollout_enabled": rollout_enabled,
            }

        if not capability_exists:
            return {
                "routing_mode": routing_mode,
                "selected_capability_id": capability_id,
                "execute_capability": False,
                "use_legacy": True,
                "reason": "capability_not_found",
                "policy_action": policy_decision.action.value,
                "policy_allowed": True,
                "capability_exists": False,
                "rollout_enabled": rollout_enabled,
            }

        if not rollout_enabled:
            return {
                "routing_mode": routing_mode,
                "selected_capability_id": capability_id,
                "execute_capability": False,
                "use_legacy": True,
                "reason": "capability_rollout_disabled",
                "policy_action": policy_decision.action.value,
                "policy_allowed": True,
                "capability_exists": capability_exists,
                "rollout_enabled": False,
            }

        if es_dominio_operativo(capability_domain):
            return {
                "routing_mode": routing_mode,
                "selected_capability_id": capability_id,
                "execute_capability": True,
                "use_legacy": False,
                "reason": f"capability_mode_{capability_domain}_execution_enabled",
                "policy_action": policy_decision.action.value,
                "policy_allowed": True,
                "capability_exists": capability_exists,
                "rollout_enabled": rollout_enabled,
            }

        return {
            "routing_mode": routing_mode,
            "selected_capability_id": capability_id,
            "execute_capability": False,
            "use_legacy": True,
            "reason": "capability_mode_domain_not_enabled_yet",
            "policy_action": policy_decision.action.value,
            "policy_allowed": True,
            "capability_exists": capability_exists,
            "rollout_enabled": rollout_enabled,
        }

    def execute(
        self,
        *,
        run_context: RunContext,
        route: dict[str, Any],
        planned_capability: dict[str, Any],
        message: str,
        session_id: str | None,
        reset_memory: bool,
        memory_context: dict[str, Any] | None = None,
        resolved_query: ResolvedQuerySpec | None = None,
        execution_plan: QueryExecutionPlan | None = None,
        observability=None,
    ) -> dict[str, Any]:
        if not bool(route.get("execute_capability")):
            return {
                "ok": False,
                "error": "route_does_not_execute_capability",
                "meta": {"reason": route.get("reason")},
            }

        capability_id = str(planned_capability.get("capability_id") or route.get("selected_capability_id") or "")
        execution_constraints = dict((execution_plan.constraints if execution_plan else {}) or {})
        handler = self._resolve_handler(capability_id=capability_id)
        if handler is None:
            return {
                "ok": False,
                "error": f"unsupported_capability_domain:{capability_id}",
                "meta": {"capability_id": capability_id},
            }

        result = handler.handle(
            capability_id=capability_id,
            message=message,
            session_id=session_id,
            reset_memory=reset_memory,
            run_context=run_context,
            planned_capability=planned_capability,
            memory_context=memory_context,
            resolved_query=resolved_query,
            execution_plan=execution_plan,
            observability=observability,
        )
        return {
            "ok": bool(result.ok),
            "response": result.response,
            "error": result.error,
            "meta": {
                **dict(result.metadata or {}),
                "constraints_applied": bool(execution_constraints),
                "constraint_keys": sorted(list(execution_constraints.keys())),
            },
        }

    def _resolve_primary_capability_id(
        self,
        *,
        classification: dict[str, Any],
        query_intelligence: dict[str, Any],
    ) -> str:
        execution_plan = dict(query_intelligence.get("execution_plan") or {})
        explicit_capability = str(execution_plan.get("capability_id") or "").strip()
        if explicit_capability:
            return explicit_capability

        resolved_query_capability = self._resolve_capability_from_resolved_query(
            resolved_query=dict(query_intelligence.get("resolved_query") or {})
        )
        if resolved_query_capability:
            return resolved_query_capability

        intent = str(classification.get("intent") or "").strip().lower()
        domain = normalizar_codigo_dominio(classification.get("domain") or "general")
        output_mode = str(classification.get("output_mode") or "summary").strip().lower()
        needs_database = bool(classification.get("needs_database"))

        if intent == "knowledge_change_request":
            return "knowledge.proposal.create.v1"
        if intent == "attendance_period_probe":
            return "attendance.period.resolve.v1"
        if domain in {"empleados", "rrhh"}:
            if intent in {"detail", "empleados_detail"} or output_mode == "table":
                return "empleados.detail.v1"
            return "empleados.count.active.v1"
        if domain in {"ausentismo", "attendance"}:
            if intent == "trend":
                return "attendance.trend.daily.v1"
            if intent == "detail":
                return "attendance.unjustified.table_with_personal.v1"
            if intent in {"aggregate", "count", "summary"}:
                return "attendance.summary.by_attribute.v1"
            return "attendance.unjustified.summary.v1"
        if domain == "transport":
            return "transport.departures.summary.v1"
        if not needs_database or domain == "general":
            return "general.answer.v1"
        return "legacy.passthrough.v1"

    def _resolve_capability_from_resolved_query(self, *, resolved_query: dict[str, Any]) -> str:
        payload = dict(resolved_query or {})
        intent = dict(payload.get("intent") or {})
        domain = normalizar_codigo_dominio(intent.get("domain_code") or "general")
        template_id = str(intent.get("template_id") or "").strip().lower()
        operation = str(intent.get("operation") or "").strip().lower()
        group_by = [
            str(item or "").strip().lower()
            for item in list(intent.get("group_by") or [])
            if str(item or "").strip()
        ]
        if domain in {"empleados", "rrhh"}:
            if template_id == "detail_by_entity_and_period":
                return "empleados.detail.v1"
            return "empleados.count.active.v1"
        if domain in {"ausentismo", "attendance"}:
            if template_id == "detail_by_entity_and_period":
                return "attendance.unjustified.table_with_personal.v1"
            if template_id == "trend_by_period" or operation == "trend":
                return "attendance.trend.daily.v1"
            if template_id == "count_records_by_period":
                return "attendance.unjustified.summary.v1"
            if template_id == "aggregate_by_group_and_period" or operation == "aggregate":
                if "supervisor" in group_by:
                    return "attendance.summary.by_supervisor.v1"
                if "area" in group_by:
                    return "attendance.summary.by_area.v1"
                if "cargo" in group_by:
                    return "attendance.summary.by_cargo.v1"
                return "attendance.summary.by_attribute.v1"
            return "attendance.unjustified.summary.v1"
        return ""

    @staticmethod
    def _resolve_query_constraints(*, query_intelligence: dict[str, Any]) -> dict[str, Any]:
        execution_plan = dict(query_intelligence.get("execution_plan") or {})
        return dict(execution_plan.get("constraints") or {})

    def _build_plan(
        self,
        *,
        capability_id: str,
        reason: str,
        classification: dict[str, Any],
        query_constraints: dict[str, Any],
        candidate_rank: int,
        candidate_score: int,
    ) -> dict[str, Any]:
        definition = self.catalog.get(capability_id)
        return {
            "capability_id": capability_id,
            "capability_exists": bool(definition),
            "rollout_enabled": bool(definition),
            "handler_key": definition.handler_key if definition else "legacy.passthrough",
            "policy_tags": list(definition.policy_tags) if definition else [],
            "legacy_intents": list(definition.legacy_intents) if definition else [],
            "reason": reason,
            "source": {
                "intent": str(classification.get("intent") or ""),
                "domain": str(classification.get("domain") or ""),
                "output_mode": str(classification.get("output_mode") or "summary"),
                "needs_database": bool(classification.get("needs_database", True)),
            },
            "dictionary_hints": {},
            "policy_planner_hint": {},
            "semantic_signals": {},
            "query_constraints": dict(query_constraints or {}),
            "candidate_rank": int(candidate_rank),
            "candidate_score": int(candidate_score),
            "workflow_hints": {},
        }

    def _resolve_handler(self, *, capability_id: str):
        if capability_id.startswith("attendance."):
            if self._attendance_handler is None:
                self._attendance_handler = AusentismoHandler()
            return self._attendance_handler
        if capability_id.startswith("transport."):
            if self._transport_handler is None:
                self._transport_handler = TransportHandler()
            return self._transport_handler
        if capability_id.startswith("empleados."):
            if self._empleados_handler is None:
                self._empleados_handler = EmpleadosHandler()
            return self._empleados_handler
        return None
