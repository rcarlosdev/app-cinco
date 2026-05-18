from __future__ import annotations

from typing import Any

from apps.ia_dev.application.context.run_context import RunContext
from apps.ia_dev.application.contracts.query_intelligence_contracts import (
    QueryExecutionPlan,
    ResolvedQuerySpec,
)
from apps.ia_dev.application.runtime.approval_runtime_service import ApprovalRuntimeService
from apps.ia_dev.application.runtime.background_runtime_service import BackgroundRuntimeService
from apps.ia_dev.application.runtime.runtime_hardening_service import RuntimeHardeningService
from apps.ia_dev.application.policies.policy_guard import PolicyAction, PolicyDecision
from apps.ia_dev.application.routing.capability_catalog import CapabilityCatalog
from apps.ia_dev.application.runtime.tool_registry_service import ToolRegistryService
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
        tool_registry_service: ToolRegistryService | None = None,
        approval_runtime_service: ApprovalRuntimeService | None = None,
        background_runtime_service: BackgroundRuntimeService | None = None,
        runtime_hardening_service: RuntimeHardeningService | None = None,
        attendance_handler: AusentismoHandler | None = None,
        empleados_handler: EmpleadosHandler | None = None,
        transport_handler: TransportHandler | None = None,
    ):
        self.catalog = catalog or CapabilityCatalog()
        self.tool_registry_service = tool_registry_service or ToolRegistryService(catalog=self.catalog)
        self.approval_runtime_service = approval_runtime_service or ApprovalRuntimeService()
        self.background_runtime_service = background_runtime_service or BackgroundRuntimeService()
        self.runtime_hardening_service = runtime_hardening_service or RuntimeHardeningService()
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
        tool_definition = self.tool_registry_service.resolve_tool_for_runtime(
            response_flow="handler",
            capability_id=capability_id,
            route_payload=route,
            execution_plan=execution_plan.as_dict() if execution_plan else {},
        )
        handler = self._resolve_handler(capability_id=capability_id)
        if handler is None:
            return {
                "ok": False,
                "error": f"unsupported_capability_domain:{capability_id}",
                "meta": {
                    "capability_id": capability_id,
                    "tool_id": str((tool_definition.tool_id if tool_definition else capability_id) or ""),
                },
            }
        background_decision = self.background_runtime_service.should_run_in_background(
            tool_definition=tool_definition,
            arguments={
                "message": message,
                "session_id": session_id,
            },
            execution_plan=execution_plan.as_dict() if execution_plan else {},
            approval_pending=False,
        )
        if tool_definition is not None and bool(tool_definition.approval_policy.approval_required):
            approval_result = self.approval_runtime_service.evaluate_tool_execution(
                run_context=run_context,
                tool_definition=tool_definition,
                requested_by_agent=str((run_context.metadata.get("agents_runtime") or {}).get("selected_specialist") or "runtime"),
                target_action="execute_handler",
                evidence_before_approval={
                    "tool_id": str(tool_definition.tool_id or ""),
                    "capability_id": capability_id,
                    "candidate_domain": str((planned_capability.get("source") or {}).get("domain") or ""),
                    "candidate_intent": str((planned_capability.get("source") or {}).get("intent") or ""),
                    "message_excerpt": str(message or "")[:160],
                },
            )
            run_context.metadata["approval_runtime"] = {
                "approvals": list(approval_result.get("approvals") or []),
                "approval_trace": list(approval_result.get("approval_trace") or []),
                "status": str(approval_result.get("task_status") or "awaiting_approval"),
            }
            approval = dict(((approval_result.get("approvals") or [None])[0]) or {})
            self.background_runtime_service.mark_awaiting_approval(
                run_context=run_context,
                resume_token=str(approval.get("resume_token") or ""),
                partial_evidence=dict(approval.get("evidence_before_approval") or {}),
                tool_id=str(tool_definition.tool_id or ""),
            )
            if observability is not None and hasattr(observability, "record_event"):
                observability.record_event(
                    event_type="runtime_approval_requested",
                    source="RuntimeCapabilityAdapter",
                    meta={
                        "run_id": str(run_context.run_id or ""),
                        "trace_id": str(run_context.trace_id or ""),
                        "tool_id": str(tool_definition.tool_id or ""),
                        "capability_id": capability_id,
                        "approval_request_id": str((((approval_result.get("approvals") or [{}])[0]) or {}).get("approval_request_id") or ""),
                    },
                )
            return {
                "ok": False,
                "error": f"approval_required:{tool_definition.tool_id}",
                "meta": {
                    "tool_id": str(tool_definition.tool_id or ""),
                    "tool_definition": tool_definition.as_dict(),
                    "approval_pending": True,
                    "approval_status": str(approval_result.get("approval_status") or "awaiting_approval"),
                    "approvals": list(approval_result.get("approvals") or []),
                    "approval_trace": list(approval_result.get("approval_trace") or []),
                },
            }
        if bool(background_decision.get("enabled")):
            background_state = self.background_runtime_service.queue_run(
                run_context=run_context,
                tool_id=str((tool_definition.tool_id if tool_definition else capability_id) or ""),
                policy_reason=str(background_decision.get("reason") or ""),
                partial_evidence={
                    "tool_id": str((tool_definition.tool_id if tool_definition else capability_id) or ""),
                    "capability_id": capability_id,
                },
                timeout_seconds=int(((execution_plan.metadata if execution_plan else {}) or {}).get("timeout_seconds") or 0),
            )
            if observability is not None and hasattr(observability, "record_event"):
                observability.record_event(
                    event_type="background_run_queued",
                    source="RuntimeCapabilityAdapter",
                    meta={
                        "run_id": str(run_context.run_id or ""),
                        "trace_id": str(run_context.trace_id or ""),
                        "tool_id": str((tool_definition.tool_id if tool_definition else capability_id) or ""),
                        "policy_reason": str(background_decision.get("reason") or ""),
                    },
                )
            return {
                "ok": False,
                "error": f"background_execution_queued:{capability_id}",
                "meta": {
                    "tool_id": str((tool_definition.tool_id if tool_definition else capability_id) or ""),
                    "tool_definition": tool_definition.as_dict() if tool_definition else {},
                    "background_pending": True,
                    "background": dict(background_state.get("background") or {}),
                    "background_trace": list(background_state.get("background_trace") or []),
                    "checkpoints": list(background_state.get("checkpoints") or []),
                },
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
        tool_trace = self.tool_registry_service.build_runtime_trace(
            run_context=run_context,
            response_flow="handler",
            capability_id=capability_id,
            route_payload=route,
            execution_plan=execution_plan.as_dict() if execution_plan else {},
            response=result.response,
            fallback_used={"used": False, "reason": "", "flow": ""},
            validation_result={"satisfied": bool(result.ok)},
        )
        if tool_trace:
            run_context.metadata["runtime_tool_trace"] = list(tool_trace)
        idempotency_key = self.runtime_hardening_service.build_idempotency_key(
            run_id=run_context.run_id,
            tool_id=str((tool_definition.tool_id if tool_definition else capability_id) or ""),
            arguments={"message": message, "session_id": session_id},
        )
        return {
            "ok": bool(result.ok),
            "response": result.response,
            "error": result.error,
            "meta": {
                **dict(result.metadata or {}),
                "tool_id": str((tool_definition.tool_id if tool_definition else capability_id) or ""),
                "tool_definition": tool_definition.as_dict() if tool_definition else {},
                "tool_trace": tool_trace,
                "correlation": self.runtime_hardening_service.build_correlation_metadata(
                    run_id=run_context.run_id,
                    trace_id=run_context.trace_id,
                    session_id=run_context.session_id,
                    tool_id=str((tool_definition.tool_id if tool_definition else capability_id) or ""),
                ),
                "idempotency_key": idempotency_key,
                "constraints_applied": bool(execution_constraints),
                "constraint_keys": sorted(list(execution_constraints.keys())),
            },
        }

    def execute_registered_tool(
        self,
        *,
        run_context: RunContext,
        tool_id: str,
        arguments: dict[str, Any] | None,
        session_id: str | None,
        reset_memory: bool,
        memory_context: dict[str, Any] | None = None,
        resolved_query: ResolvedQuerySpec | None = None,
        execution_plan: QueryExecutionPlan | None = None,
        observability=None,
        sql_assisted_executor=None,
    ) -> dict[str, Any]:
        tool_definition = self.tool_registry_service.get_tool(tool_id)
        if tool_definition is None:
            return {
                "ok": False,
                "error": f"tool_not_registered:{tool_id}",
                "meta": {"tool_id": str(tool_id or "")},
            }
        if bool(tool_definition.approval_policy.approval_required):
            approval_result = self.approval_runtime_service.evaluate_tool_execution(
                run_context=run_context,
                tool_definition=tool_definition,
                requested_by_agent=str((run_context.metadata.get("agents_runtime") or {}).get("selected_specialist") or "runtime"),
                target_action="execute_registered_tool",
                evidence_before_approval={
                    "tool_id": str(tool_definition.tool_id or ""),
                    "arguments": dict(arguments or {}),
                },
            )
            run_context.metadata["approval_runtime"] = {
                "approvals": list(approval_result.get("approvals") or []),
                "approval_trace": list(approval_result.get("approval_trace") or []),
                "status": str(approval_result.get("task_status") or "awaiting_approval"),
            }
            approval = dict(((approval_result.get("approvals") or [None])[0]) or {})
            self.background_runtime_service.mark_awaiting_approval(
                run_context=run_context,
                resume_token=str(approval.get("resume_token") or ""),
                partial_evidence=dict(approval.get("evidence_before_approval") or {}),
                tool_id=str(tool_id or ""),
            )
            return {
                "ok": False,
                "error": f"tool_requires_approval:{tool_id}",
                "meta": {
                    "tool_id": str(tool_id or ""),
                    "approval_policy": tool_definition.approval_policy.as_dict(),
                    "approval_pending": True,
                    "approval_status": str(approval_result.get("approval_status") or "awaiting_approval"),
                    "approvals": list(approval_result.get("approvals") or []),
                    "approval_trace": list(approval_result.get("approval_trace") or []),
                },
            }
        payload = dict(arguments or {})
        background_decision = self.background_runtime_service.should_run_in_background(
            tool_definition=tool_definition,
            arguments=payload,
            execution_plan=execution_plan.as_dict() if execution_plan else {},
            approval_pending=False,
        )
        if bool(background_decision.get("enabled")):
            background_state = self.background_runtime_service.queue_run(
                run_context=run_context,
                tool_id=str(tool_definition.tool_id or tool_id or ""),
                policy_reason=str(background_decision.get("reason") or ""),
                partial_evidence={"tool_id": str(tool_definition.tool_id or tool_id or ""), "arguments": payload},
                timeout_seconds=int(((execution_plan.metadata if execution_plan else {}) or {}).get("timeout_seconds") or payload.get("timeout_seconds") or 0),
            )
            return {
                "ok": False,
                "error": f"background_execution_queued:{tool_id}",
                "meta": {
                    "tool_id": str(tool_id or ""),
                    "tool_definition": tool_definition.as_dict(),
                    "background_pending": True,
                    "background": dict(background_state.get("background") or {}),
                    "background_trace": list(background_state.get("background_trace") or []),
                    "checkpoints": list(background_state.get("checkpoints") or []),
                },
            }

        if tool_definition.tool_id == ToolRegistryService.SQL_ASSISTED_TOOL_ID:
            if not callable(sql_assisted_executor):
                return {
                    "ok": False,
                    "error": "sql_assisted_executor_not_configured",
                    "meta": {
                        "tool_id": tool_definition.tool_id,
                        "tool_definition": tool_definition.as_dict(),
                    },
                }
            result = dict(
                sql_assisted_executor(
                    tool_definition=tool_definition,
                    arguments=payload,
                    execution_plan=execution_plan,
                )
                or {}
            )
            result.setdefault("meta", {})
            result["meta"] = {
                **dict(result.get("meta") or {}),
                "tool_id": tool_definition.tool_id,
                "tool_definition": tool_definition.as_dict(),
            }
            return result

        capability_id = str(tool_definition.capability_id or tool_definition.tool_id or "").strip()
        planned_capability = self._build_plan(
            capability_id=capability_id,
            reason="native_tool_execution",
            classification={
                "domain": str(tool_definition.domain or ""),
                "intent": str(payload.get("intent") or ""),
                "output_mode": "table",
                "needs_database": True,
            },
            query_constraints=dict((execution_plan.constraints if execution_plan else {}) or {}),
            candidate_rank=1,
            candidate_score=100,
        )
        route = {
            "routing_mode": "capability",
            "selected_capability_id": capability_id,
            "execute_capability": True,
            "use_legacy": False,
            "reason": "native_tool_execution",
            "policy_action": "allow",
            "policy_allowed": True,
            "capability_exists": True,
            "rollout_enabled": True,
        }
        return self.execute(
            run_context=run_context,
            route=route,
            planned_capability=planned_capability,
            message=str(payload.get("message") or run_context.message or ""),
            session_id=session_id,
            reset_memory=reset_memory,
            memory_context=memory_context,
            resolved_query=resolved_query,
            execution_plan=execution_plan,
            observability=observability,
        )

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
        if domain in {"transport", "transporte"}:
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
        semantic_context = dict(payload.get("semantic_context") or {})
        resolved_semantic = dict(semantic_context.get("resolved_semantic") or {})
        if domain == "inventario_logistica":
            registry_binding = dict(
                semantic_context.get("semantic_capability_registry")
                or resolved_semantic.get("semantic_capability_registry")
                or {}
            )
            registry_capability = str(
                registry_binding.get("candidate_capability")
                or resolved_semantic.get("candidate_capability")
                or ""
            ).strip()
            if registry_capability:
                return registry_capability
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
        tool_definition = self.tool_registry_service.get_tool_for_capability(capability_id)
        return {
            "capability_id": capability_id,
            "tool_id": str((tool_definition.tool_id if tool_definition else capability_id) or ""),
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
            "tool_definition": tool_definition.as_dict() if tool_definition else {},
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
