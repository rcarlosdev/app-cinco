from __future__ import annotations

import logging
import os
import re
import unicodedata
from typing import Any, Callable

from apps.ia_dev.application.context.run_context import RunContext
from apps.ia_dev.application.memory.chat_memory_runtime_service import (
    ChatMemoryRuntimeService,
)
from apps.ia_dev.application.orchestration.response_assembler import (
    ResponseAssembler,
)
from apps.ia_dev.application.reasoning.diagnostic_orchestrator import (
    DiagnosticOrchestrator,
)
from apps.ia_dev.application.reasoning.reasoning_ledger_service import (
    ReasoningLedgerService,
)
from apps.ia_dev.application.reasoning.reasoning_memory_service import (
    ReasoningMemoryService,
)
from apps.ia_dev.application.contracts.query_intelligence_contracts import (
    QueryExecutionPlan,
    ResolvedQuerySpec,
    StructuredQueryIntent,
)
from apps.ia_dev.application.policies.policy_guard import PolicyGuard
from apps.ia_dev.application.runtime.runtime_capability_adapter import (
    RuntimeCapabilityAdapter,
)
from apps.ia_dev.application.routing.capability_catalog import CapabilityCatalog
from apps.ia_dev.application.semantic.query_execution_planner import QueryExecutionPlanner
from apps.ia_dev.application.semantic.query_intent_resolver import QueryIntentResolver
from apps.ia_dev.application.semantic.query_pattern_memory_service import QueryPatternMemoryService
from apps.ia_dev.application.semantic.context_builder import ContextBuilder
from apps.ia_dev.application.semantic.canonical_resolution_service import (
    CanonicalResolutionService,
)
from apps.ia_dev.application.semantic.semantic_normalization_service import (
    SemanticNormalizationService,
)
from apps.ia_dev.application.semantic.result_satisfaction_validator import (
    ResultSatisfactionValidator,
)
from apps.ia_dev.application.semantic.satisfaction_review_gate import (
    SatisfactionReviewGate,
)
from apps.ia_dev.application.semantic.semantic_business_resolver import SemanticBusinessResolver
from apps.ia_dev.application.taxonomia_dominios import (
    agente_desde_dominio,
    dominio_desde_capacidad,
    es_capacidad_de_dominio_operativo,
    normalizar_codigo_dominio,
    normalizar_dominio_operativo,
)
from apps.ia_dev.application.workflow.task_state_service import TaskStateService
from apps.ia_dev.services.intent_arbitration_service import IntentArbitrationService
from apps.ia_dev.services.memory_service import SessionMemoryStore


logger = logging.getLogger(__name__)


class ChatApplicationService:
    CLEANUP_PHASE = "phase_7"
    PILOT_PHASE = "phase_9"
    PRODUCTIVE_PILOT_DOMAINS = {"ausentismo", "attendance", "empleados", "rrhh"}

    def __init__(
        self,
        *,
        catalog: CapabilityCatalog | None = None,
        capability_runtime_adapter: RuntimeCapabilityAdapter | None = None,
        policy_guard: PolicyGuard | None = None,
        response_assembler: ResponseAssembler | None = None,
        memory_runtime: ChatMemoryRuntimeService | None = None,
        delegation_coordinator: Any | None = None,
        semantic_business_resolver: SemanticBusinessResolver | None = None,
        context_builder: ContextBuilder | None = None,
        semantic_normalization_service: SemanticNormalizationService | None = None,
        canonical_resolution_service: CanonicalResolutionService | None = None,
        query_intent_resolver: QueryIntentResolver | None = None,
        query_execution_planner: QueryExecutionPlanner | None = None,
        result_satisfaction_validator: ResultSatisfactionValidator | None = None,
        satisfaction_review_gate: SatisfactionReviewGate | None = None,
        loop_controller: Any | None = None,
        query_pattern_memory_service: QueryPatternMemoryService | None = None,
        reasoning_ledger_service: ReasoningLedgerService | None = None,
        diagnostic_orchestrator: DiagnosticOrchestrator | None = None,
        reasoning_memory_service: ReasoningMemoryService | None = None,
        task_state_service: TaskStateService | None = None,
        intent_arbitration_service: IntentArbitrationService | None = None,
    ):
        self.catalog = catalog or CapabilityCatalog()
        self.capability_runtime = capability_runtime_adapter or RuntimeCapabilityAdapter(
            catalog=self.catalog
        )
        self.policy_guard = policy_guard or PolicyGuard()
        self.response_assembler = response_assembler or ResponseAssembler()
        self.memory_runtime = memory_runtime or ChatMemoryRuntimeService()
        self.delegation_coordinator = delegation_coordinator
        self.semantic_business_resolver = semantic_business_resolver or SemanticBusinessResolver()
        self.context_builder = context_builder or ContextBuilder(
            semantic_business_resolver=self.semantic_business_resolver
        )
        self.semantic_normalization_service = (
            semantic_normalization_service or SemanticNormalizationService()
        )
        self.canonical_resolution_service = (
            canonical_resolution_service or CanonicalResolutionService()
        )
        self.query_intent_resolver = query_intent_resolver or QueryIntentResolver()
        self.query_execution_planner = query_execution_planner or QueryExecutionPlanner(catalog=self.catalog)
        self.result_satisfaction_validator = result_satisfaction_validator or ResultSatisfactionValidator()
        self.satisfaction_review_gate = satisfaction_review_gate or SatisfactionReviewGate()
        self.loop_controller = loop_controller
        self.query_pattern_memory_service = query_pattern_memory_service or QueryPatternMemoryService()
        self.reasoning_ledger_service = reasoning_ledger_service or ReasoningLedgerService()
        self.diagnostic_orchestrator = diagnostic_orchestrator or DiagnosticOrchestrator()
        self.reasoning_memory_service = reasoning_memory_service or ReasoningMemoryService()
        self.task_state_service = task_state_service or TaskStateService()
        self.intent_arbitration_service = intent_arbitration_service or IntentArbitrationService()

    def run(
        self,
        *,
        message: str,
        session_id: str | None,
        reset_memory: bool,
        legacy_runner: Callable[..., dict[str, Any]],
        observability=None,
        actor_user_key: str | None = None,
    ) -> dict[str, Any]:
        run_context = RunContext.create(
            message=message,
            session_id=session_id,
            reset_memory=reset_memory,
        )
        session_context: dict[str, Any] = {}
        if run_context.session_id and not run_context.reset_memory:
            try:
                session_context = SessionMemoryStore.get_context(run_context.session_id)
            except Exception:
                session_context = {}
        user_key = self._resolve_user_key(actor_user_key=actor_user_key, run_context=run_context)
        self.reasoning_ledger_service.start_run(
            run_context=run_context,
            message=message,
            user_key=user_key,
            session_context=session_context,
        )

        pre_classification = self._bootstrap_classification(
            message=message,
            session_context=session_context,
        )
        self.reasoning_ledger_service.record_progress(
            run_context=run_context,
            stage="bootstrap",
            status="completed",
            summary="Clasificacion base y dominio inicial resueltos.",
            details={
                "intent": str(pre_classification.get("intent") or ""),
                "domain": str(pre_classification.get("domain") or ""),
                "selected_agent": str(pre_classification.get("selected_agent") or ""),
            },
            next_step="cargar memoria relevante antes de la resolucion semantica",
            confidence=0.6,
        )
        pre_query_memory_context = self.memory_runtime.load_context_for_chat(
            user_key=user_key,
            domain_code=str(pre_classification.get("domain") or "").strip().upper() or None,
            capability_id=None,
            run_context=run_context,
            observability=observability,
        )
        pre_query_memory_hints = self._extract_memory_hints(pre_query_memory_context)
        pre_query_workflow_hints = self._load_workflow_hints(user_key=user_key)
        self.reasoning_ledger_service.attach_memory_hints(
            run_context=run_context,
            memory_hints=pre_query_memory_hints,
            phase="pre_query",
        )
        run_context.metadata["memory_context"] = {
            "user_key": user_key,
            "session_context": {
                "last_domain": session_context.get("last_domain"),
                "last_intent": session_context.get("last_intent"),
                "last_output_mode": session_context.get("last_output_mode"),
                "last_period_start": session_context.get("last_period_start"),
                "last_period_end": session_context.get("last_period_end"),
            },
            "flags": dict(pre_query_memory_context.get("flags") or {}),
            "preloaded": {
                "user_memory_count": len(pre_query_memory_context.get("user_memory") or []),
                "business_memory_count": len(pre_query_memory_context.get("business_memory") or []),
                "domain_code": str(pre_classification.get("domain") or "").strip().upper() or None,
                "capability_id": None,
            },
            "hints": pre_query_memory_hints,
            "workflow_hints": pre_query_workflow_hints,
        }
        query_intelligence = self._resolve_query_intelligence(
            message=message,
            base_classification=pre_classification,
            session_context=session_context,
            run_context=run_context,
            observability=observability,
        )
        resolved_query_payload = dict(query_intelligence.get("resolved_query") or {})
        resolved_query_intent = dict(resolved_query_payload.get("intent") or {})
        resolved_query_filters = dict(resolved_query_payload.get("normalized_filters") or {})
        resolved_query_period = dict(resolved_query_payload.get("normalized_period") or {})
        resolved_query_semantic = dict(resolved_query_payload.get("semantic_context") or {})
        resolved_temporal_scope = dict((resolved_query_semantic.get("resolved_semantic") or {}).get("temporal_scope") or {})
        self.reasoning_ledger_service.record_progress(
            run_context=run_context,
            stage="query_intelligence",
            status="completed",
            summary="La consulta fue resuelta a un plan estructurado.",
            details={
                "mode": str(query_intelligence.get("mode") or "off"),
                "strategy": str((query_intelligence.get("execution_plan") or {}).get("strategy") or ""),
                "domain_code": str(resolved_query_intent.get("domain_code") or ""),
                "template_id": str(resolved_query_intent.get("template_id") or ""),
                "status_value": str(
                    resolved_query_filters.get("estado")
                    or resolved_query_filters.get("estado_empleado")
                    or ""
                ),
                "period_label": str(resolved_query_period.get("label") or ""),
                "temporal_column_hint": str(resolved_temporal_scope.get("column_hint") or ""),
            },
            next_step="elegir la mejor capacidad y ejecutar la respuesta",
            confidence=float((resolved_query_intent.get("confidence") or 0.0) or 0.0),
        )
        self._save_task_state(
            run_context=run_context,
            status="planned",
            original_question=message,
            detected_domain=str(resolved_query_intent.get("domain_code") or pre_classification.get("domain") or ""),
            plan={
                "query_intelligence_mode": str(query_intelligence.get("mode") or "off"),
                "execution_plan": dict(query_intelligence.get("execution_plan") or {}),
                "candidate_capabilities": [],
            },
            source_used=self._build_source_used_payload(
                query_intelligence=query_intelligence,
                route=None,
                response_flow="new_runtime",
            ),
        )
        query_intelligence_mode = str(query_intelligence.get("mode") or "off")
        planner_authority_active = self._query_execution_planner_authority_active(
            query_intelligence=query_intelligence,
        )
        classification_override = dict(query_intelligence.get("classification_override") or {})
        if query_intelligence_mode == "active" and classification_override:
            pre_classification = {
                **pre_classification,
                **classification_override,
            }
        bootstrap_plan = self.capability_runtime.build_bootstrap_plan(
            classification=pre_classification,
            query_intelligence=query_intelligence,
        )
        pre_memory_context = self.memory_runtime.load_context_for_chat(
            user_key=user_key,
            domain_code=self._domain_code_from_capability(bootstrap_plan),
            capability_id=str(bootstrap_plan.get("capability_id") or "").strip() or None,
            run_context=run_context,
            observability=observability,
        )
        memory_hints = self._extract_memory_hints(pre_memory_context)
        workflow_hints = self._load_workflow_hints(user_key=user_key)
        run_context.metadata["memory_context"] = {
            "user_key": user_key,
            "session_context": {
                "last_domain": session_context.get("last_domain"),
                "last_intent": session_context.get("last_intent"),
                "last_output_mode": session_context.get("last_output_mode"),
                "last_period_start": session_context.get("last_period_start"),
                "last_period_end": session_context.get("last_period_end"),
            },
            "flags": dict(pre_memory_context.get("flags") or {}),
            "preloaded": {
                "user_memory_count": len(pre_memory_context.get("user_memory") or []),
                "business_memory_count": len(pre_memory_context.get("business_memory") or []),
                "domain_code": self._domain_code_from_capability(bootstrap_plan),
                "capability_id": bootstrap_plan.get("capability_id"),
            },
            "hints": memory_hints,
            "workflow_hints": workflow_hints,
        }
        self.reasoning_ledger_service.attach_memory_hints(
            run_context=run_context,
            memory_hints=memory_hints,
            phase="execution",
        )

        candidate_plans = self._plan_candidates(
            message=message,
            classification=pre_classification,
            planning_context={
                "memory_hints": memory_hints,
                "workflow_hints": workflow_hints,
                "routing_mode": run_context.routing_mode,
                "query_intelligence": query_intelligence,
            },
            fallback_plan=bootstrap_plan,
        )
        candidate_plans = [
            self._apply_attendance_memory_hints(
                message=message,
                planned_capability=plan,
                memory_context=pre_memory_context,
                run_context=run_context,
                observability=observability,
            )
            for plan in candidate_plans
        ]
        candidate_plans = self._apply_query_intelligence_plan_overrides(
            candidate_plans=candidate_plans,
            fallback_plan=bootstrap_plan,
            query_intelligence=query_intelligence,
            classification=pre_classification,
        )
        candidate_plans = self._apply_canonical_routing_overrides(
            message=message,
            candidate_plans=candidate_plans,
            fallback_plan=bootstrap_plan,
            query_intelligence=query_intelligence,
            classification=pre_classification,
            run_context=run_context,
            observability=observability,
        )
        run_context.metadata["planned_candidates"] = [
            {
                "capability_id": str(item.get("capability_id") or ""),
                "reason": str(item.get("reason") or ""),
                "candidate_rank": int(item.get("candidate_rank") or 0),
                "candidate_score": int(item.get("candidate_score") or 0),
            }
            for item in candidate_plans
        ]
        self._save_task_state(
            run_context=run_context,
            status="planned",
            original_question=message,
            detected_domain=str(resolved_query_intent.get("domain_code") or pre_classification.get("domain") or ""),
            plan={
                "query_intelligence_mode": str(query_intelligence.get("mode") or "off"),
                "execution_plan": dict(query_intelligence.get("execution_plan") or {}),
                "candidate_capabilities": list(run_context.metadata.get("planned_candidates") or []),
            },
            source_used=self._build_source_used_payload(
                query_intelligence=query_intelligence,
                route=None,
                response_flow="new_runtime",
            ),
        )
        self.reasoning_ledger_service.record_progress(
            run_context=run_context,
            stage="planning",
            status="completed",
            summary="Se generaron candidatos de capacidad para resolver la consulta.",
            details={
                "candidate_count": len(candidate_plans),
                "top_capability_id": (
                    "query_execution_planner.sql_assisted"
                    if str((query_intelligence.get("execution_plan") or {}).get("strategy") or "").strip().lower()
                    == "sql_assisted"
                    else str((candidate_plans[0] if candidate_plans else {}).get("capability_id") or "")
                ),
                "top_reason": str((candidate_plans[0] if candidate_plans else {}).get("reason") or ""),
            },
            next_step="ejecutar la ruta principal y validar el resultado",
            confidence=0.72,
        )

        execution_result_snapshot = dict(query_intelligence.get("execution_result") or {})
        precomputed_response = dict(query_intelligence.get("precomputed_response") or {})
        if (
            not precomputed_response
            and self._planner_valid_sql_result_wins(
                query_intelligence=query_intelligence,
                execution_meta=execution_result_snapshot,
            )
        ):
            precomputed_response = dict(execution_result_snapshot.get("response") or {})

        run_context.metadata["delegation"] = {
            "mode": "off",
            "should_delegate": False,
            "plan_reason": "delegation_pruned_wave_5",
            "selected_domains": [],
            "tasks": [],
            "executed": False,
            "is_multi_domain": False,
            "warnings": [],
            "compatibility_only": False,
            "delegation_compat_used": False,
            "delegation_compat_reason": "",
        }

        if precomputed_response:
            execution = dict(query_intelligence.get("execution_result") or {})
            execution_plan_meta = dict(((query_intelligence.get("execution_plan") or {}).get("metadata") or {}))
            for key in (
                "analytics_router_decision",
                "legacy_analytics_isolated",
                "legacy_analytics_fallback_disabled",
                "blocked_legacy_fallback",
                "blocked_tool_ausentismo_service",
                "blocked_run_legacy_for_analytics",
                "runtime_only_fallback_reason",
                "fallback_reason",
                "cleanup_phase",
            ):
                if key not in execution and key in execution_plan_meta:
                    execution[key] = execution_plan_meta.get(key)
            planned_capability = dict(candidate_plans[0] if candidate_plans else bootstrap_plan)
            policy_decision = self.policy_guard.evaluate(
                run_context=run_context,
                planned_capability=planned_capability,
            )
            route = {
                "routing_mode": run_context.routing_mode,
                "selected_capability_id": (
                    "query_execution_planner.sql_assisted"
                    if str((query_intelligence.get("execution_plan") or {}).get("strategy") or "").strip().lower()
                    == "sql_assisted"
                    else str(
                        planned_capability.get("capability_id")
                        or f"query_intelligence.{str(query_intelligence.get('execution_plan', {}).get('strategy') or 'precomputed')}.v1"
                    )
                ),
                "execute_capability": False,
                "use_legacy": False,
                "shadow_enabled": True,
                "selected_capability_authoritative": False,
                "runtime_authority": "query_execution_planner",
                "planner_was_authority": True,
                "planner_selected_strategy": str(
                    (query_intelligence.get("execution_plan") or {}).get("strategy") or ""
                ),
                "legacy_capability_path_used": False,
                "reason": f"query_intelligence_{query_intelligence_mode}_precomputed_response",
                "policy_action": policy_decision.action.value,
                "policy_allowed": policy_decision.allowed,
                "capability_exists": bool(planned_capability.get("capability_exists")),
                "rollout_enabled": bool(planned_capability.get("rollout_enabled", True)),
            }
            route = self._enforce_planner_sql_authority_route(
                route=route,
                query_intelligence=query_intelligence,
                execution_meta=execution,
            )
            primary_response = precomputed_response
            self._save_task_state(
                run_context=run_context,
                status="executing",
                original_question=message,
                detected_domain=str(pre_classification.get("domain") or ""),
                plan={"execution_plan": dict(query_intelligence.get("execution_plan") or {})},
                source_used=self._build_source_used_payload(
                    query_intelligence=query_intelligence,
                    route=route,
                    response_flow="sql_assisted",
                ),
                executed_query=str(((query_intelligence.get("execution_plan") or {}).get("sql_query") or "")),
            )
            run_context.metadata.pop("proactive_loop", None)
        elif planner_authority_active:
            planner_execution = self._execute_query_execution_planner_authority(
                message=message,
                session_id=session_id,
                reset_memory=reset_memory,
                run_context=run_context,
                query_intelligence=query_intelligence,
                candidate_plans=candidate_plans,
                bootstrap_plan=bootstrap_plan,
                legacy_runner=legacy_runner,
                observability=observability,
                memory_context=pre_memory_context,
            )
            execution = dict(planner_execution.get("execution") or {})
            planned_capability = dict(
                planner_execution.get("planned_capability") or (candidate_plans[0] if candidate_plans else bootstrap_plan)
            )
            policy_decision = planner_execution.get("policy_decision")
            route = dict(planner_execution.get("route") or {})
            if policy_decision is None:
                policy_decision = self.policy_guard.evaluate(
                    run_context=run_context,
                    planned_capability=planned_capability,
                )
            primary_response = dict(planner_execution.get("response") or {})
        else:
            execution = self._execute_with_proactive_loop(
                message=message,
                session_id=session_id,
                reset_memory=reset_memory,
                run_context=run_context,
                planned_candidates=candidate_plans,
                legacy_runner=legacy_runner,
                observability=observability,
                memory_context=pre_memory_context,
            )
            planned_capability = dict(
                execution.get("planned_capability") or (candidate_plans[0] if candidate_plans else bootstrap_plan)
            )
            policy_decision = execution.get("policy_decision")
            route = dict(execution.get("route") or {})
            if policy_decision is None:
                policy_decision = self.policy_guard.evaluate(
                    run_context=run_context,
                    planned_capability=planned_capability,
                )
            primary_response = dict(execution.get("response") or {})
        execution_meta = self._resolve_runtime_execution_metadata(
            query_intelligence=query_intelligence,
            execution_meta=dict((execution or {}) if "execution" in locals() else {}),
        )
        route = self._enforce_planner_sql_authority_route(
            route=route,
            query_intelligence=query_intelligence,
            execution_meta=execution_meta,
        )
        response_flow = self._resolve_runtime_response_flow(
            query_intelligence=query_intelligence,
            route=route,
            response=primary_response,
            execution_meta=execution_meta,
        )
        classification = self._extract_classification(primary_response)

        divergence = {"diverged": False, "reason": "legacy_capability_routing_pruned"}

        # Refresh business hints using resolved capability/domain for better relevance.
        resolved_memory_context = self.memory_runtime.load_context_for_chat(
            user_key=user_key,
            domain_code=self._domain_code_from_capability(planned_capability),
            capability_id=str(planned_capability.get("capability_id") or "").strip() or None,
            run_context=run_context,
            observability=observability,
        )
        run_context.metadata["memory_context"]["resolved"] = {
            "user_memory_count": len(resolved_memory_context.get("user_memory") or []),
            "business_memory_count": len(resolved_memory_context.get("business_memory") or []),
            "domain_code": self._domain_code_from_capability(planned_capability),
            "capability_id": planned_capability.get("capability_id"),
        }
        resolved_memory_hints = self._extract_memory_hints(resolved_memory_context)
        run_context.metadata["memory_context"]["resolved_hints"] = resolved_memory_hints
        self.reasoning_ledger_service.attach_memory_hints(
            run_context=run_context,
            memory_hints=resolved_memory_hints,
            phase="resolved",
        )

        candidates = self.memory_runtime.detect_candidates(
            message=message,
            classification=classification,
            planned_capability=planned_capability,
            legacy_response=primary_response,
            run_context=run_context,
            user_key=user_key,
            observability=observability,
        )
        memory_effects = self.memory_runtime.persist_candidates(
            user_key=user_key,
            candidates=candidates,
            run_context=run_context,
            observability=observability,
        )
        memory_effects = self._record_query_pattern_memory(
            user_key=user_key,
            run_context=run_context,
            response=primary_response,
            memory_effects=memory_effects,
            observability=observability,
        )
        run_context.metadata["runtime_execution_meta"] = dict(execution_meta)
        run_context.metadata["runtime_compatibility"] = self._build_runtime_compatibility_metadata(
            query_intelligence=query_intelligence,
            route=route,
            execution_meta=execution_meta,
        )
        runtime_metadata = self._resolve_runtime_execution_metadata(
            query_intelligence=query_intelligence,
            execution_meta=execution_meta,
        )
        cleanup_guard = {
            "legacy_analytics_fallback_disabled": bool(
                runtime_metadata.get("legacy_analytics_fallback_disabled")
            ),
            "blocked_legacy_fallback": bool(
                runtime_metadata.get("blocked_legacy_fallback")
            ),
            "analytics_router_decision": str(runtime_metadata.get("analytics_router_decision") or ""),
            "legacy_analytics_isolated": bool(runtime_metadata.get("legacy_analytics_isolated")),
            "blocked_tool_ausentismo_service": bool(
                runtime_metadata.get("blocked_tool_ausentismo_service")
            ),
            "blocked_run_legacy_for_analytics": bool(
                runtime_metadata.get("blocked_run_legacy_for_analytics")
            ),
            "runtime_only_fallback_reason": str(
                runtime_metadata.get("runtime_only_fallback_reason") or ""
            ),
            "fallback_reason": str(
                runtime_metadata.get("fallback_reason") or ""
            ),
            "cleanup_phase": str(runtime_metadata.get("cleanup_phase") or ""),
        }
        run_context.metadata["cleanup_guard"] = dict(cleanup_guard)
        diagnostics = self._record_reasoning_diagnostics(
            user_key=user_key,
            run_context=run_context,
            response=primary_response,
            planned_capability=planned_capability,
            route=route,
            execution_meta=execution_meta,
            memory_effects=memory_effects,
        )
        self.reasoning_ledger_service.record_progress(
            run_context=run_context,
            stage="response",
            status="completed",
            summary="La respuesta final fue ensamblada con diagnosticos y memoria de aprendizaje.",
            details={
                "reply_present": bool(str(primary_response.get("reply") or "").strip()),
                "diagnostics_activated": bool(diagnostics.get("activated")),
                "memory_candidates": len(list(memory_effects.get("memory_candidates") or [])),
                "pending_proposals": len(list(memory_effects.get("pending_proposals") or [])),
            },
            next_step="respuesta lista",
            confidence=0.85,
        )
        satisfaction_snapshot = self._build_satisfaction_snapshot(
            run_context=run_context,
            execution_meta=execution_meta,
        )
        fallback_payload = {
            "used": bool(execution_meta.get("used_legacy")),
            "reason": str(
                runtime_metadata.get("fallback_reason")
                or cleanup_guard.get("fallback_reason")
                or route.get("reason")
                or ""
            ),
            "flow": "legacy_fallback" if bool(execution_meta.get("used_legacy")) else "",
            "legacy_analytics_fallback_disabled": bool(cleanup_guard.get("legacy_analytics_fallback_disabled")),
            "blocked_legacy_fallback": bool(cleanup_guard.get("blocked_legacy_fallback")),
            "analytics_router_decision": str(cleanup_guard.get("analytics_router_decision") or ""),
            "legacy_analytics_isolated": bool(cleanup_guard.get("legacy_analytics_isolated")),
            "blocked_tool_ausentismo_service": bool(cleanup_guard.get("blocked_tool_ausentismo_service")),
            "blocked_run_legacy_for_analytics": bool(cleanup_guard.get("blocked_run_legacy_for_analytics")),
            "runtime_only_fallback_reason": str(cleanup_guard.get("runtime_only_fallback_reason") or ""),
            "cleanup_phase": str(cleanup_guard.get("cleanup_phase") or ""),
        }
        final_task_status = "completed" if satisfaction_snapshot.get("satisfied", True) else "verified"
        if str((query_intelligence.get("execution_plan") or {}).get("strategy") or "") == "ask_context":
            final_task_status = "needs_input"
        display_planned_capability_id = str(planned_capability.get("capability_id") or "")
        planned_capability_authoritative = bool(route.get("execute_capability"))
        if response_flow == "sql_assisted" and not bool(route.get("execute_capability")):
            display_planned_capability_id = "query_execution_planner.sql_assisted"
            planned_capability_authoritative = False
        self._save_task_state(
            run_context=run_context,
            status=final_task_status,
            original_question=message,
            detected_domain=str(classification.get("domain") or ""),
            plan={
                "planned_capability": {
                    "capability_id": display_planned_capability_id,
                    "reason": str(planned_capability.get("reason") or ""),
                    "authoritative": planned_capability_authoritative,
                },
                "route": dict(route or {}),
                "query_intelligence": {
                    "mode": str(query_intelligence.get("mode") or "off"),
                    "execution_plan": dict(query_intelligence.get("execution_plan") or {}),
                    "result_set": dict(
                        (
                            dict((dict(primary_response.get("data") or {}).get("meta") or {}).get("result_set") or {})
                            or (
                                (dict(primary_response.get("data") or {}).get("table") or {})
                                if isinstance((dict(primary_response.get("data") or {}).get("table") or {}), dict)
                                else {}
                            )
                        )
                    ),
                },
            },
            source_used=self._build_source_used_payload(
                query_intelligence=query_intelligence,
                route=route,
                response_flow=response_flow,
                cleanup_metadata=cleanup_guard,
            ),
            executed_query=str(((query_intelligence.get("execution_plan") or {}).get("sql_query") or "")),
            validation_result=satisfaction_snapshot,
            fallback_used=fallback_payload,
            recommendations=self._build_runtime_recommendations(
                response=primary_response,
                response_flow=response_flow,
                fallback_used=fallback_payload,
            ),
        )
        self._record_runtime_resolution_event(
            observability=observability,
            run_context=run_context,
            query_intelligence=query_intelligence,
            route=route,
            response=primary_response,
            execution_meta=execution_meta,
            response_flow=response_flow,
            satisfaction_snapshot=satisfaction_snapshot,
        )
        self.reasoning_ledger_service.finalize(
            run_context=run_context,
            status="completed",
            outcome={
                "diagnostics_activated": bool(diagnostics.get("activated")),
                "top_signature": str(((diagnostics.get("items") or [{}])[0] or {}).get("signature") or ""),
                "pending_proposals": len(list(memory_effects.get("pending_proposals") or [])),
            },
        )

        self._record_shadow_observability(
            observability=observability,
            run_context=run_context,
            classification=classification,
            planned_capability=planned_capability,
            route=route,
            divergence=divergence,
        )

        assembled = self.response_assembler.assemble(
            legacy_response=primary_response,
            run_context=run_context,
            planned_capability=planned_capability,
            route=route,
            policy_decision=policy_decision,
            divergence=divergence,
            memory_effects=memory_effects,
        )
        return self._attach_runtime_metadata(
            response=assembled,
            run_context=run_context,
            response_flow=response_flow,
        )

    def _resolve_query_intelligence(
        self,
        *,
        message: str,
        base_classification: dict[str, Any],
        session_context: dict[str, Any] | None = None,
        run_context: RunContext,
        observability,
    ) -> dict[str, Any]:
        mode = self._query_intelligence_mode()
        if mode == "off":
            run_context.metadata["query_intelligence"] = {
                "mode": mode,
                "enabled": False,
            }
            return {"mode": mode, "enabled": False}

        try:
            classification_for_qi = dict(base_classification or {})
            memory_hints = dict(((run_context.metadata.get("memory_context") or {}).get("hints") or {}))
            domain_code = str(classification_for_qi.get("domain") or "").strip().lower()
            rescued_domain = self._rescue_query_domain(
                message=message,
                domain_code=domain_code,
            )
            if rescued_domain and rescued_domain != domain_code:
                classification_for_qi["domain"] = rescued_domain
                classification_for_qi["intent"] = "empleados_query"
                classification_for_qi["selected_agent"] = "empleados_agent"
                classification_for_qi["needs_database"] = True
                domain_code = rescued_domain
                self._record_event(
                    observability=observability,
                    event_type="query_domain_rescued",
                    source="ChatApplicationService",
                    meta={
                        "run_id": run_context.run_id,
                        "trace_id": run_context.trace_id,
                        "from_domain": str(base_classification.get("domain") or ""),
                        "to_domain": rescued_domain,
                        "reason": "rrhh_signals_detected",
                    },
                    only_if=True,
                )
            semantic_context = self.semantic_business_resolver.build_semantic_context(
                domain_code=domain_code,
                include_dictionary=True,
            )
            query_pattern_ranking = self._rank_query_patterns(memory_hints=memory_hints)
            if query_pattern_ranking:
                self._record_event(
                    observability=observability,
                    event_type="query_pattern_candidates_loaded",
                    source="ChatApplicationService",
                    meta={
                        "run_id": run_context.run_id,
                        "trace_id": run_context.trace_id,
                        "candidate_count": int(len(list(memory_hints.get("query_patterns") or []))),
                        "ranking": query_pattern_ranking,
                    },
                    only_if=True,
                )
            context_builder_enabled = self._context_builder_enabled()
            context_builder_shadow_enabled = self._context_builder_shadow_enabled()
            context_builder_payload: dict[str, Any] = {}
            if context_builder_enabled or context_builder_shadow_enabled:
                context_builder_payload = self.context_builder.build(
                    domain_code=domain_code,
                    include_dictionary=True,
                    run_context=run_context,
                    observability=observability,
                    legacy_context=semantic_context,
                    active=context_builder_enabled,
                    shadow=context_builder_shadow_enabled and not context_builder_enabled,
                )
                run_context.metadata["context_builder"] = dict(context_builder_payload.get("meta") or {})
                self._record_event(
                    observability=observability,
                    event_type="context_builder_comparison",
                    source="ChatApplicationService",
                    meta={
                        "run_id": run_context.run_id,
                        "trace_id": run_context.trace_id,
                        "domain_code": domain_code,
                        "active": context_builder_enabled,
                        "shadow": context_builder_shadow_enabled and not context_builder_enabled,
                        "differences_count": int((context_builder_payload.get("meta") or {}).get("differences_count") or 0),
                        "differences": list((context_builder_payload.get("meta") or {}).get("differences") or []),
                    },
                    only_if=True,
                )
                if context_builder_enabled:
                    semantic_context = dict(context_builder_payload.get("context") or semantic_context)
            else:
                run_context.metadata["context_builder"] = {
                    "active": False,
                    "shadow": False,
                    "domain_code": domain_code,
                    "differences": [],
                    "differences_count": 0,
                }
            semantic_normalization_enabled = self._semantic_normalization_enabled()
            semantic_normalization_shadow_enabled = self._semantic_normalization_shadow_enabled()
            semantic_normalization_payload: dict[str, Any] = {}
            capability_hints = self.capability_runtime.build_candidate_hints(
                message=message,
                classification=classification_for_qi,
                query_intelligence={},
                max_candidates=4,
            )

            fastpath_intent = self.query_intent_resolver.match_query_pattern(
                message=message,
                base_classification=classification_for_qi,
                semantic_context=semantic_context,
                memory_hints=memory_hints,
            )
            if not isinstance(fastpath_intent, StructuredQueryIntent):
                fastpath_intent = None
            canonical_resolution_enabled = self._canonical_resolution_enabled()
            canonical_resolution_shadow_enabled = self._canonical_resolution_shadow_enabled()
            should_compute_semantic_normalization = bool(
                semantic_normalization_enabled or semantic_normalization_shadow_enabled
            )
            should_compute_canonical_resolution = bool(
                canonical_resolution_enabled or canonical_resolution_shadow_enabled
            )

            if should_compute_semantic_normalization:
                semantic_normalization_output = self.semantic_normalization_service.normalize(
                    raw_query=message,
                    semantic_context=semantic_context,
                    context_builder_output=context_builder_payload if context_builder_payload else None,
                    memory_hints=memory_hints,
                    runtime_flags={
                        "active": semantic_normalization_enabled,
                        "shadow": semantic_normalization_shadow_enabled and not semantic_normalization_enabled,
                        "llm_enabled": self._semantic_normalization_llm_enabled(),
                        "llm_mode": self._semantic_normalization_llm_mode(),
                        "llm_rollout_mode": self._semantic_normalization_llm_rollout_mode(),
                        "require_review": self._semantic_normalization_require_review(),
                    },
                    capability_hints=capability_hints,
                    base_classification=classification_for_qi,
                    run_context=run_context,
                    observability=observability,
                )
                semantic_normalization_payload = (
                    semantic_normalization_output.as_dict()
                    if hasattr(semantic_normalization_output, "as_dict")
                    else dict(semantic_normalization_output or {})
                )
            run_context.metadata["semantic_normalization"] = {
                **dict(semantic_normalization_payload or {}),
                "active": bool(semantic_normalization_enabled),
                "shadow": bool(semantic_normalization_shadow_enabled and not semantic_normalization_enabled),
            }
            canonical_resolution_payload: dict[str, Any] = {}
            legacy_hints = {
                "last_domain": str((session_context or {}).get("last_domain") or ""),
                "last_intent": str((session_context or {}).get("last_intent") or ""),
                "last_output_mode": str((session_context or {}).get("last_output_mode") or ""),
                "contextual_reference": bool(classification_for_qi.get("contextual_reference")),
                "last_group_dimension_key": str(classification_for_qi.get("last_group_dimension_key") or ""),
                "last_group_dimension_label": str(classification_for_qi.get("last_group_dimension_label") or ""),
            }
            if should_compute_canonical_resolution:
                canonical_output = self.canonical_resolution_service.resolve(
                    raw_query=message,
                    semantic_normalization_output=semantic_normalization_payload,
                    semantic_context=semantic_context,
                    memory_hints=memory_hints,
                    session_context=dict(session_context or {}),
                    base_classification=classification_for_qi,
                    capability_hints=capability_hints,
                    legacy_hints=legacy_hints,
                    run_context=run_context,
                    observability=observability,
                )
                canonical_resolution_payload = (
                    canonical_output.as_dict()
                    if hasattr(canonical_output, "as_dict")
                    else dict(canonical_output or {})
                )
            run_context.metadata["canonical_resolution"] = {
                **dict(canonical_resolution_payload or {}),
                "active": bool(canonical_resolution_enabled),
                "shadow": bool(canonical_resolution_shadow_enabled and not canonical_resolution_enabled),
            }
            if fastpath_intent is not None:
                intent = fastpath_intent
                semantic_normalization_payload = dict(semantic_normalization_payload or {})
                canonical_resolution_payload = dict(canonical_resolution_payload or {})
                semantic_normalization_payload["query_pattern_fastpath"] = True
                canonical_resolution_payload["query_pattern_fastpath"] = True
                if not should_compute_semantic_normalization:
                    semantic_normalization_payload["skipped_by"] = "query_pattern_fastpath"
                if not should_compute_canonical_resolution:
                    canonical_resolution_payload["skipped_by"] = "query_pattern_fastpath"
                run_context.metadata["semantic_normalization"] = {
                    **dict(run_context.metadata.get("semantic_normalization") or {}),
                    **dict(semantic_normalization_payload or {}),
                }
                run_context.metadata["canonical_resolution"] = {
                    **dict(run_context.metadata.get("canonical_resolution") or {}),
                    **dict(canonical_resolution_payload or {}),
                }
                self._record_event(
                    observability=observability,
                    event_type="query_pattern_fastpath_hit",
                    source="ChatApplicationService",
                    meta={
                        "run_id": run_context.run_id,
                        "trace_id": run_context.trace_id,
                        "domain_code": str(intent.domain_code or ""),
                        "template_id": str(intent.template_id or ""),
                        "operation": str(intent.operation or ""),
                        "candidate_count": int(len(list(memory_hints.get("query_patterns") or []))),
                        "openai_avoided": True,
                        "estimated_saved_ms": self._query_pattern_fastpath_saved_ms_estimate(),
                        "ranking": query_pattern_ranking,
                    },
                    only_if=True,
                )
            else:
                intent = self.query_intent_resolver.resolve(
                    message=message,
                    base_classification=classification_for_qi,
                    semantic_context=semantic_context,
                    memory_hints=memory_hints,
                )
                if query_pattern_ranking:
                    self._record_event(
                        observability=observability,
                        event_type="query_pattern_fastpath_miss",
                        source="ChatApplicationService",
                        meta={
                            "run_id": run_context.run_id,
                            "trace_id": run_context.trace_id,
                            "candidate_count": int(len(list(memory_hints.get("query_patterns") or []))),
                            "ranking": query_pattern_ranking,
                        },
                        only_if=True,
                    )
            resolved_intent_domain = normalizar_codigo_dominio(
                str(getattr(intent, "domain_code", "") or "")
            )
            current_context_domain = normalizar_codigo_dominio(
                semantic_context.get("domain_code")
                or semantic_context.get("domain")
                or domain_code
                or ""
            )
            if (
                resolved_intent_domain
                and resolved_intent_domain not in {"general", "knowledge"}
                and resolved_intent_domain != current_context_domain
            ):
                semantic_context = self.semantic_business_resolver.build_semantic_context(
                    domain_code=resolved_intent_domain,
                    include_dictionary=True,
                )
                self._record_event(
                    observability=observability,
                    event_type="semantic_context_realigned",
                    source="ChatApplicationService",
                    meta={
                        "run_id": run_context.run_id,
                        "trace_id": run_context.trace_id,
                        "from_domain": current_context_domain,
                        "to_domain": resolved_intent_domain,
                        "reason": "intent_domain_override",
                    },
                    only_if=True,
                )
            intent_arbitration = self.intent_arbitration_service.arbitrate(
                original_question=message,
                candidate_domain=domain_code or str(intent.domain_code or ""),
                heuristic_intent=classification_for_qi,
                llm_intent=intent,
                candidate_capabilities=capability_hints,
                ai_dictionary_context=dict(semantic_context.get("dictionary") or {}),
                action_risk=self._build_intent_arbitration_action_risk(
                    candidate_capabilities=capability_hints,
                ),
                knowledge_governance_signals=self._build_intent_arbitration_knowledge_signals(
                    message=message,
                    classification=classification_for_qi,
                    semantic_context=semantic_context,
                    candidate_capabilities=capability_hints,
                ),
            )
            intent = self._apply_intent_arbitration_to_structured_intent(
                intent=intent,
                arbitration=intent_arbitration,
            )
            classification_for_qi = self._apply_intent_arbitration_to_classification(
                classification=classification_for_qi,
                arbitration=intent_arbitration,
                intent=intent,
            )
            run_context.metadata["intent_arbitration"] = dict(intent_arbitration or {})
            self._record_event(
                observability=observability,
                event_type="intent_arbitration_resolved",
                source="ChatApplicationService",
                meta={
                    "run_id": run_context.run_id,
                    "trace_id": run_context.trace_id,
                    "heuristic_intent": str(intent_arbitration.get("heuristic_intent") or ""),
                    "llm_intent": str(intent_arbitration.get("llm_intent") or ""),
                    "arbitrated_intent": str(intent_arbitration.get("final_intent") or ""),
                    "arbitration_confidence": float(intent_arbitration.get("confidence") or 0.0),
                    "arbitration_reason": str(intent_arbitration.get("reasoning_summary") or ""),
                    "kpro_blocked_by_arbitration": bool(
                        intent_arbitration.get("kpro_blocked_by_arbitration")
                    ),
                    "sql_assisted_selected_by_arbitration": bool(
                        intent_arbitration.get("sql_assisted_selected_by_arbitration")
                    ),
                },
                only_if=True,
            )
            canonical_comparison = self._compare_canonical_resolution_with_intent(
                canonical_resolution=canonical_resolution_payload,
                intent=intent,
            )
            canonical_meta = dict(run_context.metadata.get("canonical_resolution") or {})
            canonical_meta["comparison"] = canonical_comparison
            run_context.metadata["canonical_resolution"] = canonical_meta
            self._record_event(
                observability=observability,
                event_type="canonical_resolution_vs_intent",
                source="ChatApplicationService",
                meta={
                    "run_id": run_context.run_id,
                    "trace_id": run_context.trace_id,
                    "active": bool(canonical_resolution_enabled),
                    "shadow": bool(canonical_resolution_shadow_enabled and not canonical_resolution_enabled),
                    **dict(canonical_comparison or {}),
                },
                only_if=bool(canonical_resolution_enabled or canonical_resolution_shadow_enabled),
            )
            normalization_comparison = self._compare_semantic_normalization_with_intent(
                semantic_normalization=semantic_normalization_payload,
                intent=intent,
                base_classification=classification_for_qi,
            )
            semantic_normalization_meta = dict(run_context.metadata.get("semantic_normalization") or {})
            semantic_normalization_meta["comparison"] = normalization_comparison
            run_context.metadata["semantic_normalization"] = semantic_normalization_meta
            self._record_event(
                observability=observability,
                event_type="semantic_normalization_vs_intent",
                source="ChatApplicationService",
                meta={
                    "run_id": run_context.run_id,
                    "trace_id": run_context.trace_id,
                    "active": bool(semantic_normalization_enabled),
                    "shadow": bool(semantic_normalization_shadow_enabled and not semantic_normalization_enabled),
                    **dict(normalization_comparison or {}),
                },
                only_if=bool(semantic_normalization_enabled or semantic_normalization_shadow_enabled),
            )
            resolved_query = self.semantic_business_resolver.resolve_query(
                message=message,
                intent=intent,
                base_classification=classification_for_qi,
                semantic_context_override=semantic_context if context_builder_enabled else None,
            )
            execution_plan = self.query_execution_planner.plan(
                run_context=run_context,
                resolved_query=resolved_query,
            )
            execution_plan = self._apply_intent_arbitration_to_execution_plan(
                execution_plan=execution_plan,
                arbitration=intent_arbitration,
            )
            if (
                execution_plan.strategy == "sql_assisted"
                and str((execution_plan.metadata or {}).get("response_category") or "") == "data_quality"
                and str((execution_plan.metadata or {}).get("data_quality_operator") or "")
            ):
                intent_arbitration = {
                    **dict(intent_arbitration or {}),
                    "should_fallback": False,
                    "required_clarification": "",
                }
            semantic_normalization_meta = dict(run_context.metadata.get("semantic_normalization") or {})
            semantic_normalization_meta["ab_evaluation"] = self._build_semantic_normalization_ab_evaluation(
                semantic_normalization=semantic_normalization_meta,
                canonical_resolution=run_context.metadata.get("canonical_resolution") or {},
                execution_plan=execution_plan,
            )
            run_context.metadata["semantic_normalization"] = semantic_normalization_meta
            self._record_query_intelligence_semantic_events(
                observability=observability,
                run_context=run_context,
                resolved_query=resolved_query,
            )

            classification_override = self._build_query_intelligence_classification_override(
                resolved_query=resolved_query,
                intent_arbitration=intent_arbitration,
            )
            precomputed_response: dict[str, Any] = {}
            execution_result: dict[str, Any] | None = None
            if bool(intent_arbitration.get("should_fallback")) and str(
                intent_arbitration.get("required_clarification") or ""
            ).strip():
                precomputed_response = self._build_intent_arbitration_clarification_response(
                    run_context=run_context,
                    arbitration=intent_arbitration,
                )
            if mode == "active":
                if precomputed_response:
                    execution_result = {
                        "ok": True,
                        "response": precomputed_response,
                        "used_legacy": False,
                        "fallback_reason": "intent_arbitration_clarification_required",
                    }
                elif execution_plan.strategy == "ask_context":
                    precomputed_response = self.query_execution_planner.build_missing_context_response(
                        run_context=run_context,
                        resolved_query=resolved_query,
                        execution_plan=execution_plan,
                    )
                elif execution_plan.strategy == "sql_assisted":
                    execution_result = self.query_execution_planner.execute_sql_assisted(
                        run_context=run_context,
                        resolved_query=resolved_query,
                        execution_plan=execution_plan,
                        observability=observability,
                    )
                    if bool(execution_result.get("ok")) and isinstance(execution_result.get("response"), dict):
                        candidate_response = dict(execution_result.get("response") or {})
                        validation = self.result_satisfaction_validator.validate(
                            message=message,
                            response=candidate_response,
                            resolved_query=resolved_query,
                            execution_plan=execution_plan,
                        )
                        if validation.satisfied:
                            execution_result.update(
                                {
                                    "satisfied": True,
                                    "satisfaction_reason": str(validation.reason or "ok"),
                                }
                            )
                            precomputed_response = candidate_response
                        else:
                            execution_result.update(
                                {
                                    "validation": validation.as_dict(),
                                    "satisfied": False,
                                    "satisfaction_reason": str(
                                        validation.reason or "validation_failed"
                                    ),
                                }
                            )
                    if not precomputed_response:
                        fallback_meta = self._build_runtime_only_sql_failure_meta(
                            execution_plan=execution_plan,
                            resolved_query=resolved_query,
                            execution_result=execution_result,
                        )
                        if fallback_meta:
                            execution_plan.metadata.update(
                                {
                                    key: value
                                    for key, value in fallback_meta.items()
                                    if key != "fallback_reason"
                                }
                            )
                            precomputed_response = self._build_runtime_only_fallback_response(
                                run_context=run_context,
                                resolved_query=resolved_query,
                                runtime_execution_plan=execution_plan,
                                fallback_reason=str(
                                    fallback_meta.get("runtime_only_fallback_reason")
                                    or fallback_meta.get("fallback_reason")
                                    or "unsafe_sql_plan"
                                ),
                            )
                            execution_result = {
                                **dict(execution_result or {}),
                                "ok": True,
                                "response": precomputed_response,
                                "used_legacy": False,
                                **fallback_meta,
                            }
                elif (
                    execution_plan.strategy == "fallback"
                    and bool((execution_plan.metadata or {}).get("blocked_legacy_fallback"))
                ):
                    precomputed_response = self._build_runtime_only_fallback_response(
                        run_context=run_context,
                        resolved_query=resolved_query,
                        runtime_execution_plan=execution_plan,
                        fallback_reason=str(
                            (execution_plan.metadata or {}).get("runtime_only_fallback_reason")
                            or (execution_plan.metadata or {}).get("fallback_reason")
                            or execution_plan.reason
                            or "unsafe_sql_plan"
                        ),
                    )
                    execution_result = {
                        "ok": True,
                        "response": precomputed_response,
                        "used_legacy": False,
                        **dict(execution_plan.metadata or {}),
                    }

            payload = {
                "mode": mode,
                "enabled": True,
                "intent": intent.as_dict(),
                "resolved_query": resolved_query.as_dict(),
                "execution_plan": execution_plan.as_dict(),
                "classification_override": classification_override,
                "precomputed_response": precomputed_response,
                "execution_result": dict(execution_result or {}),
                "semantic_normalization": dict(run_context.metadata.get("semantic_normalization") or {}),
                "canonical_resolution": dict(run_context.metadata.get("canonical_resolution") or {}),
                "intent_arbitration": dict(intent_arbitration or {}),
                "query_pattern_fastpath": {
                    "hit": bool(fastpath_intent is not None),
                    "openai_avoided": bool(fastpath_intent is not None),
                    "estimated_saved_ms": self._query_pattern_fastpath_saved_ms_estimate() if fastpath_intent is not None else 0,
                    "candidate_count": int(len(list(memory_hints.get("query_patterns") or []))),
                    "ranking": query_pattern_ranking,
                },
            }
            run_context.metadata["query_intelligence"] = payload

            self._record_event(
                observability=observability,
                event_type="query_intelligence_resolved",
                source="ChatApplicationService",
                meta={
                    "run_id": run_context.run_id,
                    "trace_id": run_context.trace_id,
                    "mode": mode,
                    "domain_code": resolved_query.intent.domain_code,
                    "template_id": resolved_query.intent.template_id,
                    "strategy": execution_plan.strategy,
                    "capability_id": execution_plan.capability_id,
                    "precomputed": bool(precomputed_response),
                },
                only_if=True,
            )
            return payload
        except Exception as exc:
            run_context.metadata["query_intelligence"] = {
                "mode": mode,
                "enabled": True,
                "error": str(exc),
            }
            self._record_event(
                observability=observability,
                event_type="query_intelligence_error",
                source="ChatApplicationService",
                meta={
                    "run_id": run_context.run_id,
                    "trace_id": run_context.trace_id,
                    "mode": mode,
                    "error": str(exc),
                },
                only_if=True,
            )
            return {"mode": mode, "enabled": True, "error": str(exc)}

    def _apply_query_intelligence_plan_overrides(
        self,
        *,
        candidate_plans: list[dict[str, Any]],
        fallback_plan: dict[str, Any],
        query_intelligence: dict[str, Any],
        classification: dict[str, Any],
    ) -> list[dict[str, Any]]:
        plans = [dict(item) for item in list(candidate_plans or []) if isinstance(item, dict)]
        if str(query_intelligence.get("mode") or "off") != "active":
            return plans
        execution_plan = dict(query_intelligence.get("execution_plan") or {})
        capability_id = str(execution_plan.get("capability_id") or "").strip()
        plan_constraints = dict(execution_plan.get("constraints") or {})
        if not capability_id:
            return plans
        override_mode = self._query_intelligence_plan_override_mode()
        plans = self._apply_query_constraints_to_matching_plan(
            plans=plans,
            capability_id=capability_id,
            plan_constraints=plan_constraints,
        )
        if plans:
            if override_mode == "off":
                return plans
            first_capability = str(plans[0].get("capability_id") or "").strip()
            if first_capability == capability_id:
                return plans
            if override_mode == "soft":
                if first_capability.startswith("legacy.") or first_capability.startswith("general."):
                    first = self._switch_capability(
                        current=plans[0],
                        capability_id=capability_id,
                        reason_suffix="query_intelligence_soft_override",
                    )
                    first["candidate_rank"] = 1
                    first["candidate_score"] = max(int(first.get("candidate_score") or 0), 130)
                    first["query_constraints"] = plan_constraints
                    plans[0] = first
                    return plans
                if not any(str(item.get("capability_id") or "").strip() == capability_id for item in plans):
                    injected = self._build_query_intelligence_fallback_plan(
                        capability_id=capability_id,
                        fallback_plan=fallback_plan,
                        classification=classification,
                    )
                    injected["query_constraints"] = plan_constraints
                    injected["candidate_rank"] = len(plans) + 1
                    plans.append(injected)
                return plans

            # hard override
            first = self._switch_capability(
                current=plans[0],
                capability_id=capability_id,
                reason_suffix="query_intelligence_hard_override",
            )
            first["candidate_rank"] = 1
            first["candidate_score"] = max(int(first.get("candidate_score") or 0), 130)
            first["query_constraints"] = plan_constraints
            plans[0] = first
            return plans

        plan = self._build_query_intelligence_fallback_plan(
            capability_id=capability_id,
            fallback_plan=fallback_plan,
            classification=classification,
        )
        plan["query_constraints"] = plan_constraints
        return [plan]

    def _apply_canonical_routing_overrides(
        self,
        *,
        message: str,
        candidate_plans: list[dict[str, Any]],
        fallback_plan: dict[str, Any],
        query_intelligence: dict[str, Any],
        classification: dict[str, Any],
        run_context: RunContext,
        observability,
    ) -> list[dict[str, Any]]:
        plans = [dict(item) for item in list(candidate_plans or []) if isinstance(item, dict)]
        active_enabled = self._canonical_routing_enabled()
        shadow_enabled = self._canonical_routing_shadow_enabled()
        comparison: dict[str, Any] = {
            "active": bool(active_enabled),
            "shadow": bool(shadow_enabled and not active_enabled),
            "influenced": False,
            "influence_reason": "canonical_routing_flags_off",
            "differences": [],
            "differences_count": 0,
            "decision_actual": {},
            "decision_canonic": {},
        }

        current = dict(plans[0] if plans else fallback_plan)
        current_capability = str(current.get("capability_id") or "").strip()
        current_domain = self._capability_domain(current_capability) or str(
            ((current.get("source") or {}).get("domain") or "")
        ).strip().lower()
        comparison["decision_actual"] = {
            "capability_id": current_capability,
            "domain_code": current_domain or "general",
            "reason": str(current.get("reason") or ""),
            "candidate_score": int(current.get("candidate_score") or 0),
        }

        canonical_resolution = dict(query_intelligence.get("canonical_resolution") or {})
        if not canonical_resolution:
            comparison["shadow"] = False
        if not canonical_resolution:
            comparison["influence_reason"] = "canonical_resolution_missing"
            return self._finalize_canonical_routing_comparison(
                plans=plans,
                comparison=comparison,
                query_intelligence=query_intelligence,
                run_context=run_context,
                observability=observability,
            )

        canonical_target = self._canonical_target_from_resolution(
            message=message,
            canonical_resolution=canonical_resolution,
            classification=classification,
            fallback_plan=fallback_plan,
        )
        canonical_domain = str(canonical_target.get("domain_code") or "general").strip().lower() or "general"
        canonical_capability = str(canonical_target.get("capability_id") or "").strip()
        critical_conflicts = list(canonical_target.get("critical_conflicts") or [])
        conflicts = list(canonical_target.get("conflicts") or [])
        confidence = float(canonical_target.get("confidence") or 0.0)

        comparison["decision_canonic"] = {
            "capability_id": canonical_capability,
            "domain_code": canonical_domain,
            "intent_code": str(canonical_target.get("intent_code") or ""),
            "confidence": confidence,
            "critical_conflicts": critical_conflicts,
            "conflicts_count": len(conflicts),
            "target_source": str(canonical_target.get("source") or ""),
        }

        differences: list[str] = []
        if canonical_domain and current_domain and canonical_domain != current_domain:
            differences.append("domain_mismatch")
        if canonical_capability and current_capability and canonical_capability != current_capability:
            differences.append("capability_mismatch")
        if (
            current_domain in {"", "general", "legacy"}
            and canonical_domain not in {"", "general", "legacy"}
            and confidence >= self._canonical_routing_confidence_threshold()
        ):
            differences.append("runtime_general_vs_canonical_specific")
        comparison["differences"] = differences
        comparison["differences_count"] = len(differences)

        if not (active_enabled or shadow_enabled):
            return self._finalize_canonical_routing_comparison(
                plans=plans,
                comparison=comparison,
                query_intelligence=query_intelligence,
                run_context=run_context,
                observability=observability,
            )

        if not bool(canonical_target.get("safe")):
            comparison["influence_reason"] = str(canonical_target.get("unsafe_reason") or "canonical_not_safe")
            return self._finalize_canonical_routing_comparison(
                plans=plans,
                comparison=comparison,
                query_intelligence=query_intelligence,
                run_context=run_context,
                observability=observability,
            )

        if not canonical_capability:
            comparison["influence_reason"] = "canonical_capability_unresolved"
            return self._finalize_canonical_routing_comparison(
                plans=plans,
                comparison=comparison,
                query_intelligence=query_intelligence,
                run_context=run_context,
                observability=observability,
            )

        should_influence = bool(
            active_enabled
            and canonical_domain not in {"", "general", "legacy"}
            and (
                self._is_general_or_legacy_capability(current_capability)
                or not current_capability
            )
            and canonical_capability != current_capability
        )
        if not should_influence:
            comparison["influence_reason"] = "shadow_or_no_safe_runtime_correction_needed"
            return self._finalize_canonical_routing_comparison(
                plans=plans,
                comparison=comparison,
                query_intelligence=query_intelligence,
                run_context=run_context,
                observability=observability,
            )

        if plans:
            updated = self._switch_capability(
                current=current,
                capability_id=canonical_capability,
                reason_suffix="canonical_routing_active_override",
            )
            updated["candidate_rank"] = 1
            updated["candidate_score"] = max(int(updated.get("candidate_score") or 0), 132)
            updated["canonical_routing"] = {
                "source": str(canonical_target.get("source") or ""),
                "confidence": confidence,
                "domain_code": canonical_domain,
                "intent_code": str(canonical_target.get("intent_code") or ""),
            }
            plans[0] = updated
        else:
            injected = self._build_query_intelligence_fallback_plan(
                capability_id=canonical_capability,
                fallback_plan=fallback_plan,
                classification=classification,
            )
            injected["reason"] = "canonical_routing_fallback_plan"
            injected["candidate_rank"] = 1
            injected["candidate_score"] = 132
            injected["canonical_routing"] = {
                "source": str(canonical_target.get("source") or ""),
                "confidence": confidence,
                "domain_code": canonical_domain,
                "intent_code": str(canonical_target.get("intent_code") or ""),
            }
            plans = [injected]
        comparison["influenced"] = True
        comparison["influence_reason"] = "active_override_from_strong_canonical_resolution"

        return self._finalize_canonical_routing_comparison(
            plans=plans,
            comparison=comparison,
            query_intelligence=query_intelligence,
            run_context=run_context,
            observability=observability,
        )

    def _finalize_canonical_routing_comparison(
        self,
        *,
        plans: list[dict[str, Any]],
        comparison: dict[str, Any],
        query_intelligence: dict[str, Any],
        run_context: RunContext,
        observability,
    ) -> list[dict[str, Any]]:
        summary = dict(comparison or {})
        summary["selected_capability_after"] = str((plans[0] if plans else {}).get("capability_id") or "")
        run_context.metadata["canonical_routing"] = summary
        query_intelligence["canonical_routing"] = summary

        query_intelligence_meta = dict(run_context.metadata.get("query_intelligence") or {})
        query_intelligence_meta["canonical_routing"] = summary
        run_context.metadata["query_intelligence"] = query_intelligence_meta

        self._record_event(
            observability=observability,
            event_type="canonical_resolution_planner_router_comparison",
            source="ChatApplicationService",
            meta={
                "run_id": run_context.run_id,
                "trace_id": run_context.trace_id,
                **summary,
            },
            only_if=bool(summary.get("active") or summary.get("shadow")),
        )
        return plans

    def _canonical_target_from_resolution(
        self,
        *,
        message: str,
        canonical_resolution: dict[str, Any],
        classification: dict[str, Any],
        fallback_plan: dict[str, Any],
    ) -> dict[str, Any]:
        payload = dict(canonical_resolution or {})
        confidence = float(payload.get("confidence") or 0.0)
        conflicts = [dict(item) for item in list(payload.get("conflicts") or []) if isinstance(item, dict)]
        critical_conflicts = self._canonical_critical_conflicts(conflicts=conflicts)
        threshold = self._canonical_routing_confidence_threshold()
        canonical_domain = str(payload.get("domain_code") or "").strip().lower() or "general"
        canonical_intent = str(payload.get("intent_code") or "").strip().lower()
        canonical_query = str(payload.get("canonical_query") or message or "")
        explicit_capability = str(payload.get("capability_code") or "").strip()
        target_capability = ""
        source = "canonical_default"
        if explicit_capability and self.catalog.get(explicit_capability):
            target_capability = explicit_capability
            source = "canonical_resolution_capability_code"
        else:
            default_capability = self._canonical_default_capability(
                canonical_domain=canonical_domain,
                canonical_intent=canonical_intent,
            )
            if default_capability and self.catalog.get(default_capability):
                target_capability = default_capability
                source = "canonical_domain_intent_fallback"

        if not target_capability:
            fallback_capability = str(fallback_plan.get("capability_id") or "").strip()
            if fallback_capability and self.catalog.get(fallback_capability):
                target_capability = fallback_capability
                source = "fallback_plan_capability"

        target_domain = self._capability_domain(target_capability)
        safe = bool(
            confidence >= threshold
            and not critical_conflicts
            and canonical_domain not in {"", "general", "legacy"}
            and target_capability
            and target_domain == canonical_domain
        )
        if safe:
            unsafe_reason = ""
        elif confidence < threshold:
            unsafe_reason = "canonical_low_confidence"
        elif critical_conflicts:
            unsafe_reason = "canonical_critical_conflicts_detected"
        elif canonical_domain in {"", "general", "legacy"}:
            unsafe_reason = "canonical_domain_not_specific"
        else:
            unsafe_reason = "canonical_target_capability_missing"

        return {
            "domain_code": canonical_domain,
            "intent_code": canonical_intent,
            "capability_id": target_capability,
            "confidence": confidence,
            "conflicts": conflicts,
            "critical_conflicts": critical_conflicts,
            "safe": safe,
            "unsafe_reason": unsafe_reason,
            "source": source,
        }

    @staticmethod
    def _canonical_default_capability(*, canonical_domain: str, canonical_intent: str) -> str:
        domain = normalizar_codigo_dominio(canonical_domain)
        operation = str(canonical_intent or "").strip().lower()
        if domain in {"empleados", "rrhh"}:
            return "empleados.count.active.v1"
        if domain == "ausentismo":
            if operation in {"detail", "list", "table"}:
                return "attendance.unjustified.table_with_personal.v1"
            if operation in {"trend", "timeseries"}:
                return "attendance.trend.daily.v1"
            if operation in {"aggregate", "group"}:
                return "attendance.summary.by_attribute.v1"
            return "attendance.unjustified.summary.v1"
        if domain == "knowledge":
            return "knowledge.proposal.create.v1"
        if domain == "general":
            return "general.answer.v1"
        return ""

    @staticmethod
    def _canonical_intent_to_legacy_intent(*, domain: str, operation: str) -> str:
        normalized_domain = normalizar_codigo_dominio(domain)
        normalized_operation = str(operation or "").strip().lower()
        if normalized_domain in {"empleados", "rrhh"}:
            return "empleados_query"
        if normalized_domain == "ausentismo":
            if normalized_operation in {"recurrence", "recurrent"}:
                return "ausentismo_recurrencia"
            return "ausentismo_query"
        if normalized_domain == "knowledge":
            return "knowledge_change_request"
        if normalized_operation in {"general_question", "summary"}:
            return "general_question"
        return "general_question"

    @staticmethod
    def _canonical_critical_conflicts(*, conflicts: list[dict[str, Any]]) -> list[str]:
        critical_types = {
            "capability_vs_domain",
            "domain_close_scores",
        }
        detected: list[str] = []
        for row in conflicts:
            conflict_type = str((row or {}).get("type") or "").strip()
            if conflict_type in critical_types:
                detected.append(conflict_type)
        return detected

    @staticmethod
    def _capability_domain(capability_id: str) -> str:
        return dominio_desde_capacidad(capability_id)

    @staticmethod
    def _is_general_or_legacy_capability(capability_id: str) -> bool:
        domain = ChatApplicationService._capability_domain(capability_id)
        return domain in {"", "general", "legacy"}

    @staticmethod
    def _query_intelligence_plan_override_mode() -> str:
        raw = str(os.getenv("IA_DEV_QUERY_INTELLIGENCE_PLAN_OVERRIDE_MODE", "soft") or "").strip().lower()
        if raw in {"0", "false", "off", "disabled", "none"}:
            return "off"
        if raw in {"hard", "force", "strict"}:
            return "hard"
        return "soft"

    @staticmethod
    def _apply_query_constraints_to_matching_plan(
        *,
        plans: list[dict[str, Any]],
        capability_id: str,
        plan_constraints: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if not capability_id:
            return [dict(item) for item in list(plans or [])]
        updated: list[dict[str, Any]] = []
        for plan in list(plans or []):
            payload = dict(plan or {})
            if str(payload.get("capability_id") or "").strip() == capability_id and plan_constraints:
                merged = dict(payload.get("query_constraints") or {})
                merged.update(plan_constraints)
                payload["query_constraints"] = merged
                payload["candidate_score"] = max(int(payload.get("candidate_score") or 0), 125)
            updated.append(payload)
        return updated

    def _build_query_intelligence_fallback_plan(
        self,
        *,
        capability_id: str,
        fallback_plan: dict[str, Any],
        classification: dict[str, Any],
    ) -> dict[str, Any]:
        definition = self.catalog.get(capability_id)
        source = {
            "intent": str(classification.get("intent") or ""),
            "domain": str(classification.get("domain") or ""),
            "output_mode": str(classification.get("output_mode") or "summary"),
            "needs_database": bool(classification.get("needs_database", True)),
        }
        return {
            "capability_id": capability_id,
            "capability_exists": bool(definition),
            "rollout_enabled": bool(definition),
            "handler_key": definition.handler_key if definition else str(fallback_plan.get("handler_key") or "legacy.passthrough"),
            "policy_tags": list(definition.policy_tags) if definition else [],
            "legacy_intents": list(definition.legacy_intents) if definition else [],
            "reason": "query_intelligence_fallback_plan",
            "source": source,
            "dictionary_hints": dict(fallback_plan.get("dictionary_hints") or {}),
            "policy_planner_hint": {},
            "semantic_signals": {},
            "candidate_rank": 1,
            "candidate_score": 130,
            "workflow_hints": {},
        }

    @staticmethod
    def _build_query_intelligence_classification_override(
        *,
        resolved_query: ResolvedQuerySpec,
        intent_arbitration: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        arbitration = dict(intent_arbitration or {})
        final_intent = str(arbitration.get("final_intent") or "").strip().lower()
        if final_intent == "knowledge_change_request":
            return {
                "intent": "knowledge_change_request",
                "domain": "general",
                "selected_agent": "analista_agent",
                "classifier_source": "query_intelligence_intent_arbitration_knowledge",
                "needs_database": False,
                "output_mode": "summary",
                "needs_personal_join": False,
            }
        if final_intent == "fallback" and bool(arbitration.get("should_fallback")):
            return {
                "intent": "general_question",
                "domain": "general",
                "selected_agent": "analista_agent",
                "classifier_source": "query_intelligence_intent_arbitration_fallback",
                "needs_database": False,
                "output_mode": "summary",
                "needs_personal_join": False,
            }
        domain = normalizar_codigo_dominio(resolved_query.intent.domain_code)
        company_scope = dict((resolved_query.semantic_context or {}).get("company_operational_scope") or {})
        if (
            bool(company_scope.get("domain_known"))
            and not bool(company_scope.get("domain_operational", True))
        ):
            return {
                "intent": str(resolved_query.intent.operation or "query"),
                "domain": "general",
                "selected_agent": "analista_agent",
                "classifier_source": f"query_intelligence_{resolved_query.intent.source}_domain_known_not_operational",
                "needs_database": False,
                "output_mode": "summary",
                "needs_personal_join": False,
                "domain_known_but_not_operational": True,
                "contextual_domain": domain,
                "supported_domains": list(company_scope.get("supported_domains") or []),
            }
        routing_domain = normalizar_dominio_operativo(domain, fallback="general")
        output_mode = "summary"
        if resolved_query.intent.operation in {"detail", "aggregate", "trend"}:
            output_mode = "table"
        if resolved_query.intent.operation == "count":
            output_mode = "summary"
        return {
            "intent": str(resolved_query.intent.operation or "query"),
            "domain": routing_domain,
            "selected_agent": agente_desde_dominio(routing_domain),
            "classifier_source": f"query_intelligence_{resolved_query.intent.source}",
            "needs_database": routing_domain not in {"general", ""},
            "output_mode": output_mode,
            "needs_personal_join": bool(
                set(dict(resolved_query.normalized_filters or {}).keys())
                & {"cedula", "cedula_empleado", "identificacion", "documento", "id_empleado"}
            ),
        }

    @staticmethod
    def _build_intent_arbitration_action_risk(
        *,
        candidate_capabilities: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        capability_ids = [
            str(item.get("capability_id") or "").strip()
            for item in list(candidate_capabilities or [])
            if isinstance(item, dict)
        ]
        write_like = any(capability_id.startswith("knowledge.") for capability_id in capability_ids)
        return {
            "level": "medium" if write_like else "low",
            "candidate_capabilities": capability_ids[:6],
            "has_write_capability": write_like,
        }

    @staticmethod
    def _build_intent_arbitration_knowledge_signals(
        *,
        message: str,
        classification: dict[str, Any],
        semantic_context: dict[str, Any],
        candidate_capabilities: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        normalized = ChatApplicationService._normalize_text(message)
        explicit_change_request = bool(
            re.search(
                r"\b(agrega|agregar|modifica|modificar|actualiza|actualizar|cambia|cambiar|aprueba|aprobar|aplica|aplicar)\b",
                normalized,
            )
            and re.search(
                r"\b(regla|diccionario|metadata|metadatos|definicion|sinonim|propuesta)\b",
                normalized,
            )
        )
        return {
            "explicit_change_request": explicit_change_request,
            "explicit_apply_request": bool(
                re.search(r"\b(aprueba|aprobar|aplica|aplicar)\b", normalized)
                and "propuesta" in normalized
            ),
            "candidate_has_knowledge_capability": any(
                str(item.get("capability_id") or "").startswith("knowledge.")
                for item in list(candidate_capabilities or [])
                if isinstance(item, dict)
            ),
            "dictionary_has_source_of_truth": bool(
                ((semantic_context or {}).get("source_of_truth") or {}).get("used_dictionary")
            ),
        }

    @staticmethod
    def _apply_intent_arbitration_to_structured_intent(
        *,
        intent: StructuredQueryIntent,
        arbitration: dict[str, Any] | None,
    ) -> StructuredQueryIntent:
        payload = dict(arbitration or {})
        final_intent = str(payload.get("final_intent") or "").strip().lower()
        final_domain = normalizar_codigo_dominio(payload.get("final_domain") or intent.domain_code)
        confidence = max(float(intent.confidence or 0.0), float(payload.get("confidence") or 0.0))
        warnings = list(intent.warnings or [])
        if payload.get("required_clarification"):
            warnings.append(str(payload.get("required_clarification") or ""))
        if final_intent == "knowledge_change_request":
            return StructuredQueryIntent(
                raw_query=intent.raw_query,
                domain_code="general",
                operation="knowledge_change_request",
                template_id="",
                entity_type=intent.entity_type,
                entity_value=intent.entity_value,
                filters=dict(intent.filters or {}),
                period=dict(intent.period or {}),
                group_by=list(intent.group_by or []),
                metrics=list(intent.metrics or []),
                confidence=confidence,
                source=f"{intent.source}_arbitrated",
                warnings=warnings,
            )
        if final_intent == "fallback":
            return StructuredQueryIntent(
                raw_query=intent.raw_query,
                domain_code="general",
                operation="general_question",
                template_id=intent.template_id,
                entity_type=intent.entity_type,
                entity_value=intent.entity_value,
                filters=dict(intent.filters or {}),
                period=dict(intent.period or {}),
                group_by=list(intent.group_by or []),
                metrics=list(intent.metrics or []),
                confidence=confidence,
                source=f"{intent.source}_arbitrated",
                warnings=warnings,
            )
        return StructuredQueryIntent(
            raw_query=intent.raw_query,
            domain_code=final_domain or intent.domain_code,
            operation=intent.operation,
            template_id=intent.template_id,
            entity_type=intent.entity_type,
            entity_value=intent.entity_value,
            filters=dict(intent.filters or {}),
            period=dict(intent.period or {}),
            group_by=list(intent.group_by or []),
            metrics=list(intent.metrics or []),
            confidence=confidence,
            source=f"{intent.source}_arbitrated",
            warnings=warnings,
        )

    @staticmethod
    def _apply_intent_arbitration_to_classification(
        *,
        classification: dict[str, Any],
        arbitration: dict[str, Any] | None,
        intent: StructuredQueryIntent,
    ) -> dict[str, Any]:
        base = dict(classification or {})
        payload = dict(arbitration or {})
        final_intent = str(payload.get("final_intent") or "").strip().lower()
        final_domain = normalizar_codigo_dominio(payload.get("final_domain") or intent.domain_code)
        if final_intent == "knowledge_change_request":
            base.update(
                {
                    "intent": "knowledge_change_request",
                    "domain": "general",
                    "selected_agent": "analista_agent",
                    "needs_database": False,
                    "output_mode": "summary",
                    "classifier_source": "intent_arbitration_knowledge",
                }
            )
            return base
        if final_intent == "fallback":
            base.update(
                {
                    "intent": "general_question",
                    "domain": "general",
                    "selected_agent": "analista_agent",
                    "needs_database": False,
                    "output_mode": "summary",
                    "classifier_source": "intent_arbitration_fallback",
                }
            )
            return base
        base.update(
            {
                "intent": str(intent.operation or base.get("intent") or "query"),
                "domain": final_domain or base.get("domain") or "general",
                "selected_agent": agente_desde_dominio(final_domain, fallback=str(base.get("selected_agent") or "analista_agent")),
                "needs_database": bool(payload.get("should_execute_query")),
                "classifier_source": "intent_arbitration_query",
            }
        )
        return base

    @staticmethod
    def _apply_intent_arbitration_to_execution_plan(
        *,
        execution_plan: QueryExecutionPlan,
        arbitration: dict[str, Any] | None,
    ) -> QueryExecutionPlan:
        payload = dict(arbitration or {})
        metadata = {
            **dict(execution_plan.metadata or {}),
            "heuristic_intent": str(payload.get("heuristic_intent") or ""),
            "llm_intent": str(payload.get("llm_intent") or ""),
            "arbitrated_intent": str(payload.get("final_intent") or ""),
            "arbitration_confidence": float(payload.get("confidence") or 0.0),
            "arbitration_reason": str(payload.get("reasoning_summary") or ""),
            "kpro_blocked_by_arbitration": bool(payload.get("kpro_blocked_by_arbitration")),
            "sql_assisted_selected_by_arbitration": bool(payload.get("sql_assisted_selected_by_arbitration")),
        }
        final_intent = str(payload.get("final_intent") or "").strip().lower()
        if (
            execution_plan.strategy == "sql_assisted"
            and str((execution_plan.metadata or {}).get("response_category") or "") == "data_quality"
            and str((execution_plan.metadata or {}).get("data_quality_operator") or "")
        ):
            payload["should_fallback"] = False
        if (
            execution_plan.strategy == "sql_assisted"
            and str((execution_plan.metadata or {}).get("metric_used") or "").strip().lower()
            == "certificado_alturas_vigencia"
        ):
            payload["should_fallback"] = False
        if final_intent == "knowledge_change_request":
            return QueryExecutionPlan(
                strategy="fallback",
                reason="intent_arbitration_knowledge_change_request",
                domain_code="general",
                capability_id="knowledge.proposal.create.v1",
                constraints=dict(execution_plan.constraints or {}),
                policy={
                    "allowed": False,
                    "reason": "intent_arbitration_knowledge_change_request",
                },
                metadata=metadata,
            )
        if bool(payload.get("should_fallback")):
            return QueryExecutionPlan(
                strategy="fallback",
                reason="intent_arbitration_fallback",
                domain_code=str(execution_plan.domain_code or "general"),
                capability_id=execution_plan.capability_id,
                constraints=dict(execution_plan.constraints or {}),
                policy={
                    "allowed": False,
                    "reason": "intent_arbitration_fallback",
                },
                metadata=metadata,
            )
        return QueryExecutionPlan(
            strategy=execution_plan.strategy,
            reason=execution_plan.reason,
            domain_code=execution_plan.domain_code,
            capability_id=execution_plan.capability_id,
            sql_query=execution_plan.sql_query,
            requires_context=execution_plan.requires_context,
            missing_context=list(execution_plan.missing_context or []),
            constraints=dict(execution_plan.constraints or {}),
            policy=dict(execution_plan.policy or {}),
            metadata=metadata,
        )

    @staticmethod
    def _build_intent_arbitration_clarification_response(
        *,
        run_context: RunContext,
        arbitration: dict[str, Any] | None,
    ) -> dict[str, Any]:
        payload = dict(arbitration or {})
        clarification = str(
            payload.get("required_clarification")
            or "Aclara la intencion antes de ejecutar la solicitud."
        ).strip()
        return {
            "reply": clarification,
            "session_id": str(run_context.session_id or ""),
            "payload": {
                "kpis": {},
                "series": [],
                "labels": [],
                "insights": [str(payload.get("reasoning_summary") or clarification)],
                "table": {"columns": [], "rows": [], "rowcount": 0},
            },
            "orchestrator": {
                "runtime_flow": "intent_arbitration_clarification",
                "classifier_source": "intent_arbitration_clarification",
                "intent": "general_question",
                "domain": "general",
            },
        }

    @staticmethod
    def _query_intelligence_mode() -> str:
        enabled = str(os.getenv("IA_DEV_QUERY_INTELLIGENCE_ENABLED", "0") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if not enabled:
            return "off"
        mode = str(os.getenv("IA_DEV_QUERY_INTELLIGENCE_MODE", "shadow") or "shadow").strip().lower()
        if mode not in {"off", "shadow", "active"}:
            return "shadow"
        return mode

    @staticmethod
    def _context_builder_enabled() -> bool:
        return str(os.getenv("IA_DEV_CONTEXT_BUILDER_ENABLED", "0") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    @staticmethod
    def _context_builder_shadow_enabled() -> bool:
        return str(os.getenv("IA_DEV_CONTEXT_BUILDER_SHADOW_ENABLED", "0") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    @staticmethod
    def _semantic_normalization_enabled() -> bool:
        return str(os.getenv("IA_DEV_SEMANTIC_NORMALIZATION_ENABLED", "0") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    @staticmethod
    def _semantic_normalization_shadow_enabled() -> bool:
        return str(os.getenv("IA_DEV_SEMANTIC_NORMALIZATION_SHADOW_ENABLED", "0") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    @staticmethod
    def _semantic_normalization_llm_enabled() -> bool:
        return str(os.getenv("IA_DEV_SEMANTIC_NORMALIZATION_LLM_ENABLED", "1") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    @staticmethod
    def _semantic_normalization_llm_mode() -> str:
        mode = str(os.getenv("IA_DEV_SEMANTIC_NORMALIZATION_LLM_MODE", "hybrid") or "hybrid").strip().lower()
        if mode in {"off", "disabled", "none", "never"}:
            return "never"
        if mode in {"always", "force"}:
            return "always"
        return "hybrid"

    @staticmethod
    def _semantic_normalization_llm_rollout_mode() -> str:
        mode = str(
            os.getenv("IA_DEV_SEMANTIC_NORMALIZATION_LLM_ROLLOUT_MODE", "active") or "active"
        ).strip().lower()
        if mode in {"off", "disabled", "none", "never"}:
            return "off"
        if mode in {"shadow", "observe", "dry_run"}:
            return "shadow"
        return "active"

    @staticmethod
    def _semantic_normalization_require_review() -> bool:
        return str(os.getenv("IA_DEV_SEMANTIC_NORMALIZATION_REQUIRE_REVIEW", "0") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    @staticmethod
    def _canonical_resolution_enabled() -> bool:
        return str(os.getenv("IA_DEV_CANONICAL_RESOLUTION_ENABLED", "0") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    @staticmethod
    def _canonical_resolution_shadow_enabled() -> bool:
        return str(os.getenv("IA_DEV_CANONICAL_RESOLUTION_SHADOW_ENABLED", "1") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    @staticmethod
    def _canonical_routing_enabled() -> bool:
        return str(os.getenv("IA_DEV_CANONICAL_ROUTING_ENABLED", "0") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    @staticmethod
    def _canonical_routing_shadow_enabled() -> bool:
        return str(os.getenv("IA_DEV_CANONICAL_ROUTING_SHADOW_ENABLED", "1") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    @staticmethod
    def _canonical_routing_confidence_threshold() -> float:
        raw = str(os.getenv("IA_DEV_CANONICAL_ROUTING_CONFIDENCE_THRESHOLD", "0.80") or "0.80").strip()
        try:
            value = float(raw)
        except ValueError:
            value = 0.80
        return max(0.0, min(1.0, value))

    @staticmethod
    def _satisfaction_review_gate_enabled() -> bool:
        return str(os.getenv("IA_DEV_SATISFACTION_REVIEW_GATE_ENABLED", "0") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    @staticmethod
    def _satisfaction_review_gate_shadow_enabled() -> bool:
        return str(os.getenv("IA_DEV_SATISFACTION_REVIEW_GATE_SHADOW_ENABLED", "1") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    @staticmethod
    def _satisfaction_review_gate_llm_reviewer_enabled() -> bool:
        return str(os.getenv("IA_DEV_SATISFACTION_REVIEW_GATE_LLM_REVIEWER_ENABLED", "0") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    @staticmethod
    def _loop_controller_enabled() -> bool:
        return str(os.getenv("IA_DEV_LOOP_CONTROLLER_ENABLED", "0") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    @staticmethod
    def _loop_controller_shadow_enabled() -> bool:
        return str(os.getenv("IA_DEV_LOOP_CONTROLLER_SHADOW_ENABLED", "1") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    @staticmethod
    def _compare_satisfaction_review_gate_with_legacy(
        *,
        legacy_validation: dict[str, Any],
        gate_result: dict[str, Any],
    ) -> dict[str, Any]:
        legacy_satisfied = bool((legacy_validation or {}).get("satisfied", True))
        gate_approved = bool((gate_result or {}).get("approved", True))
        differences: list[str] = []
        if legacy_satisfied != gate_approved:
            differences.append("legacy_vs_gate_decision")
        if bool((gate_result or {}).get("technical_leak_detected")):
            differences.append("technical_leak_detected")
        if not bool((gate_result or {}).get("evidence_sufficient", True)):
            differences.append("evidence_insufficient")
        if not bool((gate_result or {}).get("domain_alignment", True)):
            differences.append("domain_alignment_failed")
        if not bool((gate_result or {}).get("capability_alignment", True)):
            differences.append("capability_alignment_failed")
        if any(str((item or {}).get("code") or "") == "unjustified_fall_to_general" for item in list((gate_result or {}).get("issues") or [])):
            differences.append("unjustified_fall_to_general")
        return {
            "legacy_satisfied": legacy_satisfied,
            "legacy_reason": str((legacy_validation or {}).get("reason") or ""),
            "gate_approved": gate_approved,
            "gate_retry_reason": str((gate_result or {}).get("retry_reason") or ""),
            "gate_score": float((gate_result or {}).get("satisfaction_score") or 0.0),
            "issues_count": len(list((gate_result or {}).get("issues") or [])),
            "differences": differences,
            "differences_count": len(differences),
        }

    @staticmethod
    def _build_satisfaction_review_gate_audit(
        *,
        gate_result: dict[str, Any],
        active: bool,
        shadow: bool,
        loop_iteration: int | None = None,
    ) -> dict[str, Any]:
        payload = dict(gate_result or {})
        issues = [item for item in list(payload.get("issues") or []) if isinstance(item, dict)]
        return {
            "active": bool(active),
            "shadow": bool(shadow),
            "iteration": int(loop_iteration or 0),
            "approved": bool(payload.get("approved")),
            "satisfaction_score": float(payload.get("satisfaction_score") or 0.0),
            "next_action": str(payload.get("next_action") or ""),
            "issues_count": len(issues),
            "retry_reason": str(payload.get("retry_reason") or ""),
        }

    @staticmethod
    def _build_semantic_normalization_ab_evaluation(
        *,
        semantic_normalization: dict[str, Any],
        canonical_resolution: dict[str, Any],
        execution_plan: QueryExecutionPlan,
    ) -> dict[str, Any]:
        payload = dict(semantic_normalization or {})
        llm_comparison = dict(payload.get("llm_comparison") or {})
        off_snapshot = dict(llm_comparison.get("off") or {})
        on_snapshot = dict(llm_comparison.get("on") or off_snapshot)
        canonical_payload = dict(canonical_resolution or {})

        final_capability = (
            str(getattr(execution_plan, "capability_id", "") or "").strip()
            or str(canonical_payload.get("capability_code") or "").strip()
        )
        runtime_resolved_by = str(payload.get("resolved_by") or "").strip() or str(on_snapshot.get("resolved_by") or "").strip()

        off_case = {
            "llm_invoked": False,
            "canonical_query": str(off_snapshot.get("canonical_query") or payload.get("canonical_query") or "").strip(),
            "domain_code": str(off_snapshot.get("domain_code") or payload.get("domain_code") or "").strip().lower(),
            "intent_code": str(off_snapshot.get("intent_code") or payload.get("intent_code") or "").strip().lower(),
            "filters": dict(off_snapshot.get("filters") or payload.get("normalized_filters") or {}),
            "capability_hint": str(off_snapshot.get("capability_hint") or payload.get("capability_hint") or "").strip(),
            "confidence": float(off_snapshot.get("confidence") or payload.get("confidence") or 0.0),
            "final_capability": final_capability,
            "resolved_by": str(off_snapshot.get("resolved_by") or "deterministic_rules"),
        }
        on_case = {
            "llm_invoked": bool(payload.get("llm_invoked")),
            "canonical_query": str(on_snapshot.get("canonical_query") or payload.get("canonical_query") or "").strip(),
            "domain_code": str(on_snapshot.get("domain_code") or payload.get("domain_code") or "").strip().lower(),
            "intent_code": str(on_snapshot.get("intent_code") or payload.get("intent_code") or "").strip().lower(),
            "filters": dict(on_snapshot.get("filters") or payload.get("normalized_filters") or {}),
            "capability_hint": str(on_snapshot.get("capability_hint") or payload.get("capability_hint") or "").strip(),
            "confidence": float(on_snapshot.get("confidence") or payload.get("confidence") or 0.0),
            "final_capability": final_capability,
            "resolved_by": runtime_resolved_by or "deterministic_rules",
        }
        improved_confidence = bool(llm_comparison.get("llm_improved_confidence"))
        if not llm_comparison:
            improved_confidence = float(on_case.get("confidence") or 0.0) > float(off_case.get("confidence") or 0.0)
        return {
            "llm_rollout_mode": str(llm_comparison.get("llm_rollout_mode") or ""),
            "off": off_case,
            "on": on_case,
            "llm_changed_canonical_query": bool(llm_comparison.get("llm_changed_canonical_query")),
            "llm_changed_domain": bool(llm_comparison.get("llm_changed_domain")),
            "llm_changed_intent": bool(llm_comparison.get("llm_changed_intent")),
            "llm_changed_filters": bool(llm_comparison.get("llm_changed_filters")),
            "llm_improved_confidence": improved_confidence,
        }

    @staticmethod
    def _compare_semantic_normalization_with_intent(
        *,
        semantic_normalization: dict[str, Any],
        intent: StructuredQueryIntent,
        base_classification: dict[str, Any],
    ) -> dict[str, Any]:
        payload = dict(semantic_normalization or {})
        candidate_domains = [
            dict(item)
            for item in list(payload.get("candidate_domains") or [])
            if isinstance(item, dict)
        ]
        candidate_intents = [
            dict(item)
            for item in list(payload.get("candidate_intents") or [])
            if isinstance(item, dict)
        ]
        candidate_filters = [
            dict(item)
            for item in list(payload.get("candidate_filters") or [])
            if isinstance(item, dict)
        ]
        top_domain = str((candidate_domains[0] if candidate_domains else {}).get("domain") or "").strip().lower()
        top_intent = str((candidate_intents[0] if candidate_intents else {}).get("intent") or "").strip().lower()
        runtime_domain = str(intent.domain_code or "").strip().lower()
        runtime_intent = str(intent.operation or "").strip().lower()
        expected_estado = str(
            next(
                (
                    row.get("value")
                    for row in candidate_filters
                    if str(row.get("filter") or "").strip().lower() == "estado"
                ),
                "",
            )
            or ""
        ).strip().upper()
        runtime_estado = str((intent.filters or {}).get("estado") or "").strip().upper()
        differences: list[str] = []
        if top_domain and runtime_domain and top_domain != runtime_domain:
            differences.append("domain_mismatch")
        if top_intent and runtime_intent and top_intent != runtime_intent:
            differences.append("intent_mismatch")
        if expected_estado and runtime_estado and expected_estado != runtime_estado:
            differences.append("estado_filter_mismatch")
        return {
            "candidate_domain": top_domain,
            "runtime_domain": runtime_domain,
            "candidate_intent": top_intent,
            "runtime_intent": runtime_intent,
            "expected_estado": expected_estado,
            "runtime_estado": runtime_estado,
            "differences": differences,
            "differences_count": len(differences),
            "base_domain": str(base_classification.get("domain") or "").strip().lower(),
            "llm_invoked": bool(payload.get("llm_invoked")),
            "normalization_status": str(payload.get("normalization_status") or ""),
        }

    @staticmethod
    def _compare_canonical_resolution_with_intent(
        *,
        canonical_resolution: dict[str, Any],
        intent: StructuredQueryIntent,
    ) -> dict[str, Any]:
        payload = dict(canonical_resolution or {})
        canonical_domain = str(payload.get("domain_code") or "").strip().lower()
        canonical_intent = str(payload.get("intent_code") or "").strip().lower()
        runtime_domain = str(intent.domain_code or "").strip().lower()
        runtime_intent = str(intent.operation or "").strip().lower()
        differences: list[str] = []
        if canonical_domain and runtime_domain and canonical_domain != runtime_domain:
            differences.append("domain_mismatch")
        if canonical_intent and runtime_intent and canonical_intent != runtime_intent:
            differences.append("intent_mismatch")
        return {
            "canonical_domain": canonical_domain,
            "runtime_domain": runtime_domain,
            "canonical_intent": canonical_intent,
            "runtime_intent": runtime_intent,
            "capability_code": str(payload.get("capability_code") or ""),
            "differences": differences,
            "differences_count": len(differences),
            "canonical_confidence": float(payload.get("confidence") or 0.0),
            "conflicts_count": len(list(payload.get("conflicts") or [])),
        }

    @staticmethod
    def _rescue_query_domain(*, message: str, domain_code: str) -> str:
        normalized_domain = str(domain_code or "").strip().lower()
        if normalized_domain not in {"", "general"}:
            return normalized_domain
        normalized_message = ChatApplicationService._normalize_text(message)
        if ChatApplicationService._has_rrhh_domain_signals(normalized_message):
            return "empleados"
        return normalized_domain or "general"

    @staticmethod
    def _has_rrhh_domain_signals(normalized_message: str) -> bool:
        clean = str(normalized_message or "").strip().lower()
        if not clean:
            return False
        has_attendance_signal = any(
            token in clean for token in ("ausent", "asistencia", "injustific", "vacacion", "vacaciones", "incapacidad", "licencia", "permiso", "calamidad")
        )
        return bool(
            re.search(
                r"\b(colaborador(?:es)?|personal|emplead\w*|cedula|rrhh|habilitad\w*|vigent\w*|tipo_labor|tipo\s+labor|tipo\s+de\s+labor|labor(?:es)?|area(?:s)?|cargo(?:s)?|supervisor(?:es)?|jefe(?:s)?|lider(?:es)?|carpeta(?:s)?|sede(?:s)?|cumple\w*|nacimiento|edad|antiguedad|egreso(?:s)?|retiro(?:s)?|retirad\w*|salida(?:s)?)\b",
                clean,
            )
        ) and not has_attendance_signal

    def _record_query_intelligence_semantic_events(
        self,
        *,
        observability,
        run_context: RunContext,
        resolved_query: ResolvedQuerySpec,
    ) -> None:
        semantic_context = dict(resolved_query.semantic_context or {})
        seed_payload = dict(semantic_context.get("dictionary_seed") or {})
        if seed_payload.get("enabled"):
            status = str(seed_payload.get("status") or "skipped").strip().lower()
            event_type = "dictionary_rrhh_synonym_seed_skipped"
            if status == "applied":
                event_type = "dictionary_rrhh_synonym_seed_applied"
            elif status == "error":
                event_type = "dictionary_rrhh_synonym_seed_error"
            self._record_event(
                observability=observability,
                event_type=event_type,
                source="ChatApplicationService",
                meta={
                    "run_id": run_context.run_id,
                    "trace_id": run_context.trace_id,
                    "status": status,
                    "inserted": int(seed_payload.get("inserted") or 0),
                    "skipped": int(seed_payload.get("skipped") or 0),
                    "errors": list(seed_payload.get("errors") or []),
                },
                only_if=True,
            )

        for event in list(semantic_context.get("semantic_events") or []):
            if not isinstance(event, dict):
                continue
            event_type = str(event.get("event_type") or "").strip()
            if not event_type:
                continue
            self._record_event(
                observability=observability,
                event_type=event_type,
                source="ChatApplicationService",
                meta={
                    "run_id": run_context.run_id,
                    "trace_id": run_context.trace_id,
                    "domain_code": str(resolved_query.intent.domain_code or ""),
                    **dict(event),
                },
                only_if=True,
            )

    def _record_query_pattern_memory(
        self,
        *,
        user_key: str | None,
        run_context: RunContext,
        response: dict[str, Any],
        memory_effects: dict[str, Any],
        observability,
    ) -> dict[str, Any]:
        effects = dict(memory_effects or {})
        metadata = dict(run_context.metadata.get("query_intelligence") or {})
        hydrated = self._hydrate_query_intelligence_contracts(metadata=metadata)
        resolved_query = hydrated.get("resolved_query")
        execution_plan = hydrated.get("execution_plan")
        if resolved_query is None or execution_plan is None:
            return effects
        validation = self.result_satisfaction_validator.validate(
            message=str(resolved_query.intent.raw_query or ""),
            response=response,
            resolved_query=resolved_query,
            execution_plan=execution_plan,
        )
        metadata["final_satisfaction"] = validation.as_dict()
        run_context.metadata["query_intelligence"] = metadata

        try:
            result = self.query_pattern_memory_service.record_success(
                user_key=user_key,
                resolved_query=resolved_query,
                execution_plan=execution_plan,
                validation=validation,
                run_context=run_context,
                response=response,
                observability=observability,
            )
        except Exception as exc:
            result = {"saved": False, "reason": f"pattern_memory_error:{type(exc).__name__}"}
            self._record_event(
                observability=observability,
                event_type="query_pattern_memory_failed",
                source="ChatApplicationService",
                meta={
                    "run_id": run_context.run_id,
                    "trace_id": run_context.trace_id,
                    "error_type": type(exc).__name__,
                },
                only_if=True,
            )
        metadata["pattern_memory"] = dict(result or {})
        run_context.metadata["query_intelligence"] = metadata

        if bool(result.get("saved")):
            proposal = dict((result.get("result") or {}).get("proposal") or {})
            if proposal:
                pending = list(effects.get("pending_proposals") or [])
                pending.append(proposal)
                effects["pending_proposals"] = pending
        return effects

    def _record_reasoning_diagnostics(
        self,
        *,
        user_key: str | None,
        run_context: RunContext,
        response: dict[str, Any],
        planned_capability: dict[str, Any],
        route: dict[str, Any],
        execution_meta: dict[str, Any],
        memory_effects: dict[str, Any],
    ) -> dict[str, Any]:
        effects = memory_effects if isinstance(memory_effects, dict) else {}
        metadata = dict(run_context.metadata.get("query_intelligence") or {})
        hydrated = self._hydrate_query_intelligence_contracts(metadata=metadata)
        diagnostics = self.diagnostic_orchestrator.analyze(
            message=str(run_context.message or ""),
            resolved_query=hydrated.get("resolved_query"),
            execution_plan=hydrated.get("execution_plan"),
            response=response,
            planned_capability=planned_capability,
            route=route,
            execution_meta=execution_meta,
            memory_hints=dict(((run_context.metadata.get("memory_context") or {}).get("resolved_hints") or ((run_context.metadata.get("memory_context") or {}).get("hints") or {}))),
            query_intelligence=metadata,
        )
        metadata["diagnostics"] = diagnostics
        run_context.metadata["query_intelligence"] = metadata
        self.reasoning_ledger_service.record_diagnostics(
            run_context=run_context,
            diagnostics=diagnostics,
        )
        if not bool(diagnostics.get("activated")):
            return diagnostics

        try:
            learning = self.reasoning_memory_service.record_patterns(
                user_key=user_key,
                diagnostics=diagnostics,
                run_context=run_context,
                response=response,
            )
        except Exception:
            learning = {"enabled": True, "saved": False, "reason": "reasoning_memory_error"}
        metadata = dict(run_context.metadata.get("query_intelligence") or {})
        metadata["reasoning_memory"] = learning
        run_context.metadata["query_intelligence"] = metadata

        for result in list(learning.get("user_results") or []) + list(learning.get("business_results") or []):
            if not isinstance(result, dict) or not bool(result.get("ok")):
                continue
            proposal = dict(result.get("proposal") or {})
            if not proposal:
                continue
            pending = list(effects.get("pending_proposals") or [])
            if not any(str(item.get("proposal_id") or "") == str(proposal.get("proposal_id") or "") for item in pending if isinstance(item, dict)):
                pending.append(proposal)
            effects["pending_proposals"] = pending
            candidates = list(effects.get("memory_candidates") or [])
            candidate_key = str(proposal.get("candidate_key") or "")
            if candidate_key:
                candidates.append(
                    {
                        "scope": str(proposal.get("scope") or ""),
                        "candidate_key": candidate_key,
                        "candidate_value": proposal.get("candidate_value"),
                        "reason": "reasoning_learning_pattern",
                        "decision": "propose",
                        "proposal_id": str(proposal.get("proposal_id") or ""),
                        "result_ok": True,
                    }
                )
                effects["memory_candidates"] = candidates
        return diagnostics

    def _hydrate_query_intelligence_contracts(self, *, metadata: dict[str, Any]) -> dict[str, Any]:
        resolved_query_payload = metadata.get("resolved_query")
        execution_plan_payload = metadata.get("execution_plan")
        if not isinstance(resolved_query_payload, dict) or not isinstance(execution_plan_payload, dict):
            return {"resolved_query": None, "execution_plan": None}

        resolved_intent_payload = dict(resolved_query_payload.get("intent") or {})
        intent = StructuredQueryIntent(
            raw_query=str(resolved_intent_payload.get("raw_query") or ""),
            domain_code=str(resolved_intent_payload.get("domain_code") or ""),
            operation=str(resolved_intent_payload.get("operation") or ""),
            template_id=str(resolved_intent_payload.get("template_id") or ""),
            entity_type=str(resolved_intent_payload.get("entity_type") or ""),
            entity_value=str(resolved_intent_payload.get("entity_value") or ""),
            filters=dict(resolved_intent_payload.get("filters") or {}),
            period=dict(resolved_intent_payload.get("period") or {}),
            group_by=list(resolved_intent_payload.get("group_by") or []),
            metrics=list(resolved_intent_payload.get("metrics") or []),
            confidence=float(resolved_intent_payload.get("confidence") or 0.0),
            source=str(resolved_intent_payload.get("source") or "rules"),
            warnings=list(resolved_intent_payload.get("warnings") or []),
        )
        resolved_query = ResolvedQuerySpec(
            intent=intent,
            semantic_context=dict(resolved_query_payload.get("semantic_context") or {}),
            normalized_filters=dict(resolved_query_payload.get("normalized_filters") or {}),
            normalized_period=dict(resolved_query_payload.get("normalized_period") or {}),
            mapped_columns=dict(resolved_query_payload.get("mapped_columns") or {}),
            warnings=list(resolved_query_payload.get("warnings") or []),
        )
        execution_plan = QueryExecutionPlan(
            strategy=str(execution_plan_payload.get("strategy") or ""),
            reason=str(execution_plan_payload.get("reason") or ""),
            domain_code=str(execution_plan_payload.get("domain_code") or ""),
            capability_id=str(execution_plan_payload.get("capability_id") or "") or None,
            sql_query=str(execution_plan_payload.get("sql_query") or "") or None,
            requires_context=bool(execution_plan_payload.get("requires_context")),
            missing_context=list(execution_plan_payload.get("missing_context") or []),
            constraints=dict(execution_plan_payload.get("constraints") or {}),
            policy=dict(execution_plan_payload.get("policy") or {}),
            metadata=dict(execution_plan_payload.get("metadata") or {}),
        )
        return {
            "resolved_query": resolved_query,
            "execution_plan": execution_plan,
        }

    def _plan_candidates(
        self,
        *,
        message: str,
        classification: dict[str, Any],
        planning_context: dict[str, Any],
        fallback_plan: dict[str, Any],
    ) -> list[dict[str, Any]]:
        max_candidates = self._proactive_loop_max_iterations() + 1
        planned = self.capability_runtime.build_candidate_plans(
            message=message,
            classification=classification,
            planning_context=planning_context,
            fallback_plan=fallback_plan,
            max_candidates=max_candidates,
        )
        if planned:
            return [dict(item) for item in planned if isinstance(item, dict)]
        return [dict(fallback_plan)]

    @staticmethod
    def _query_execution_planner_authority_active(*, query_intelligence: dict[str, Any]) -> bool:
        if str(query_intelligence.get("mode") or "off") != "active":
            return False
        strategy = str((query_intelligence.get("execution_plan") or {}).get("strategy") or "").strip().lower()
        return strategy in {"capability", "fallback"}

    @staticmethod
    def _select_query_execution_planner_plan(
        *,
        candidate_plans: list[dict[str, Any]],
        bootstrap_plan: dict[str, Any],
        execution_plan: dict[str, Any],
    ) -> dict[str, Any]:
        capability_id = str(execution_plan.get("capability_id") or "").strip()
        if capability_id:
            for plan in list(candidate_plans or []):
                if str((plan or {}).get("capability_id") or "").strip() == capability_id:
                    return dict(plan)
        return dict((candidate_plans or [bootstrap_plan])[0] or bootstrap_plan or {})

    def _build_query_execution_planner_route(
        self,
        *,
        run_context: RunContext,
        query_intelligence: dict[str, Any],
        planned_capability: dict[str, Any],
        policy_decision,
    ) -> dict[str, Any]:
        execution_plan = dict(query_intelligence.get("execution_plan") or {})
        strategy = str(execution_plan.get("strategy") or "fallback").strip().lower() or "fallback"
        route = self.capability_runtime.build_route(
            run_context=run_context,
            planned_capability=planned_capability,
            policy_decision=policy_decision,
        )
        route["runtime_authority"] = "query_execution_planner"
        route["planner_was_authority"] = True
        route["planner_selected_strategy"] = strategy
        route["selected_capability_id"] = str(
            execution_plan.get("capability_id")
            or route.get("selected_capability_id")
            or planned_capability.get("capability_id")
            or ""
        ).strip()
        route["execute_capability"] = strategy == "capability" and bool(route.get("selected_capability_id"))
        route["use_legacy"] = not bool(route.get("execute_capability"))
        route["reason"] = (
            "query_execution_planner_selected_handler"
            if bool(route.get("execute_capability"))
            else "query_execution_planner_selected_fallback"
        )
        return route

    def _execute_query_execution_planner_authority(
        self,
        *,
        message: str,
        session_id: str | None,
        reset_memory: bool,
        run_context: RunContext,
        query_intelligence: dict[str, Any],
        candidate_plans: list[dict[str, Any]],
        bootstrap_plan: dict[str, Any],
        legacy_runner: Callable[..., dict[str, Any]],
        observability,
        memory_context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        execution_plan_payload = dict(query_intelligence.get("execution_plan") or {})
        hydrated = self._hydrate_query_intelligence_contracts(metadata=query_intelligence)
        resolved_query = hydrated.get("resolved_query")
        execution_plan = hydrated.get("execution_plan")
        planned_capability = self._select_query_execution_planner_plan(
            candidate_plans=candidate_plans,
            bootstrap_plan=bootstrap_plan,
            execution_plan=execution_plan_payload,
        )
        policy_decision = self.policy_guard.evaluate(
            run_context=run_context,
            planned_capability=planned_capability,
        )
        route = self._build_query_execution_planner_route(
            run_context=run_context,
            query_intelligence=query_intelligence,
            planned_capability=planned_capability,
            policy_decision=policy_decision,
        )
        execution = self._execute_primary_path(
            message=message,
            session_id=session_id,
            reset_memory=reset_memory,
            run_context=run_context,
            planned_capability=planned_capability,
            route=route,
            legacy_runner=legacy_runner,
            observability=observability,
            memory_context=memory_context,
            resolved_query=resolved_query,
            execution_plan=execution_plan,
            allow_legacy_fallback=True,
        )
        run_context.metadata.pop("proactive_loop", None)
        return {
            "response": dict(execution.get("response") or {}),
            "execution": dict(execution or {}),
            "planned_capability": planned_capability,
            "policy_decision": policy_decision,
            "route": route,
        }

    @staticmethod
    def _build_runtime_compatibility_metadata(
        *,
        query_intelligence: dict[str, Any],
        route: dict[str, Any],
        execution_meta: dict[str, Any],
    ) -> dict[str, Any]:
        execution_plan = dict(query_intelligence.get("execution_plan") or {})
        planner_strategy = str(execution_plan.get("strategy") or "").strip().lower()
        if ChatApplicationService._planner_valid_sql_result_wins(
            query_intelligence=query_intelligence,
            execution_meta=execution_meta,
        ):
            return {
                "runtime_authority": "query_execution_planner",
                "planner_was_authority": True,
                "planner_selected_strategy": "sql_assisted",
                "routing_mode": str(route.get("routing_mode") or ""),
                "legacy_capability_path_used": False,
            }
        runtime_authority = str(route.get("runtime_authority") or "")
        if not runtime_authority and str(query_intelligence.get("mode") or "off") == "active":
            runtime_authority = "query_execution_planner"
        return {
            "runtime_authority": runtime_authority,
            "planner_was_authority": bool(
                route.get("planner_was_authority") or runtime_authority == "query_execution_planner"
            ),
            "planner_selected_strategy": planner_strategy,
            "routing_mode": str(route.get("routing_mode") or ""),
            "legacy_capability_path_used": bool(route.get("use_legacy") or execution_meta.get("used_legacy")),
        }

    def _execute_with_proactive_loop(
        self,
        *,
        message: str,
        session_id: str | None,
        reset_memory: bool,
        run_context: RunContext,
        planned_candidates: list[dict[str, Any]],
        legacy_runner: Callable[..., dict[str, Any]],
        observability,
        memory_context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        candidates = [dict(item) for item in planned_candidates if isinstance(item, dict)]
        if not candidates:
            candidates = [
                self.capability_runtime.build_bootstrap_plan(
                    classification=self._bootstrap_classification(message=message),
                    query_intelligence=dict(run_context.metadata.get("query_intelligence") or {}),
                )
            ]
        query_intelligence_meta = dict(run_context.metadata.get("query_intelligence") or {})
        hydrated = self._hydrate_query_intelligence_contracts(metadata=query_intelligence_meta)
        resolved_query = hydrated.get("resolved_query")
        execution_plan = hydrated.get("execution_plan")
        selected_plan = dict(candidates[0])
        selected_policy = self.policy_guard.evaluate(
            run_context=run_context,
            planned_capability=selected_plan,
        )
        selected_route = self.capability_runtime.build_route(
            run_context=run_context,
            planned_capability=selected_plan,
            policy_decision=selected_policy,
        )
        selected_route["planner_was_authority"] = False
        selected_execution = self._execute_primary_path(
            message=message,
            session_id=session_id,
            reset_memory=reset_memory,
            run_context=run_context,
            planned_capability=selected_plan,
            route=selected_route,
            legacy_runner=legacy_runner,
            observability=observability,
            memory_context=memory_context,
            resolved_query=resolved_query,
            execution_plan=execution_plan,
            allow_legacy_fallback=True,
        )
        if self._proactive_loop_enabled(run_context=run_context):
            run_context.metadata["proactive_loop"] = {
                "enabled": True,
                "iterations_ran": 1,
                "max_iterations": 1,
                "selected_capability_id": selected_plan.get("capability_id"),
                "used_legacy": bool(selected_execution.get("used_legacy")),
                "satisfied": bool(selected_execution.get("satisfied", True)),
                "satisfaction_reason": str(selected_execution.get("satisfaction_reason") or ""),
            }
        else:
            run_context.metadata.pop("proactive_loop", None)
        run_context.metadata.pop("loop_controller", None)
        return {
            "response": dict(selected_execution.get("response") or {}),
            "planned_capability": selected_plan,
            "policy_decision": selected_policy,
            "route": selected_route,
            "execution_meta": selected_execution,
            **dict(selected_execution or {}),
        }

    def _execute_primary_path(
        self,
        *,
        message: str,
        session_id: str | None,
        reset_memory: bool,
        run_context: RunContext,
        planned_capability: dict[str, Any],
        route: dict[str, Any],
        legacy_runner: Callable[..., dict[str, Any]],
        observability,
        memory_context: dict[str, Any] | None,
        resolved_query: ResolvedQuerySpec | None = None,
        execution_plan: QueryExecutionPlan | None = None,
        allow_legacy_fallback: bool = True,
    ) -> dict[str, Any]:
        capability_id = str(planned_capability.get("capability_id") or "")
        plan_constraints = dict(planned_capability.get("query_constraints") or {})
        runtime_execution_plan = execution_plan
        if runtime_execution_plan is None and plan_constraints:
            runtime_execution_plan = QueryExecutionPlan(
                strategy="capability",
                reason="planned_capability_query_constraints",
                domain_code=self._domain_code_from_capability(planned_capability) or "",
                capability_id=capability_id or None,
                constraints=plan_constraints,
            )
        elif runtime_execution_plan is not None and plan_constraints and not dict(runtime_execution_plan.constraints or {}):
            runtime_execution_plan.constraints = plan_constraints
        capability_domain = dominio_desde_capacidad(capability_id)
        is_domain_capability = es_capacidad_de_dominio_operativo(capability_id)
        selected_event_type = f"{capability_domain}_capability_selected"
        executed_event_type = f"{capability_domain}_handler_executed"
        fallback_event_type = f"{capability_domain}_fallback_legacy"
        cleanup_guard = self._resolve_cleanup_guard(
            route=route,
            resolved_query=resolved_query,
            execution_plan=runtime_execution_plan,
            planned_capability=planned_capability,
        )
        if cleanup_guard.get("blocked_legacy_fallback"):
            response = self._build_runtime_only_fallback_response(
                run_context=run_context,
                resolved_query=resolved_query,
                runtime_execution_plan=runtime_execution_plan,
                fallback_reason=str(cleanup_guard.get("runtime_only_fallback_reason") or "unsafe_sql_plan"),
            )
            return {
                "response": response,
                "executed_capability": False,
                "ok": True,
                "used_legacy": False,
                "fallback_reason": str(cleanup_guard.get("runtime_only_fallback_reason") or "unsafe_sql_plan"),
                "analytics_router_decision": str(cleanup_guard.get("analytics_router_decision") or "runtime_only_fallback"),
                "legacy_analytics_isolated": bool(cleanup_guard.get("legacy_analytics_isolated", True)),
                "legacy_analytics_fallback_disabled": True,
                "blocked_legacy_fallback": True,
                "blocked_tool_ausentismo_service": bool(cleanup_guard.get("blocked_tool_ausentismo_service", True)),
                "blocked_run_legacy_for_analytics": bool(cleanup_guard.get("blocked_run_legacy_for_analytics", True)),
                "runtime_only_fallback_reason": str(cleanup_guard.get("runtime_only_fallback_reason") or "unsafe_sql_plan"),
                "cleanup_phase": str(cleanup_guard.get("cleanup_phase") or self.CLEANUP_PHASE),
            }

        if bool(route.get("execute_capability")):
            self._record_event(
                observability=observability,
                event_type=selected_event_type,
                source="ChatApplicationService",
                meta={
                    "run_id": run_context.run_id,
                    "trace_id": run_context.trace_id,
                    "session_id": run_context.session_id,
                    "capability_id": capability_id,
                    "capability_domain": capability_domain,
                    "route_reason": route.get("reason"),
                },
                only_if=is_domain_capability,
            )
            capability_result = self.capability_runtime.execute(
                run_context=run_context,
                route=route,
                planned_capability=planned_capability,
                message=message,
                session_id=session_id,
                reset_memory=reset_memory,
                memory_context=memory_context,
                resolved_query=resolved_query,
                execution_plan=runtime_execution_plan,
                observability=observability,
            )
            if capability_result.get("ok") and isinstance(capability_result.get("response"), dict):
                self._record_event(
                    observability=observability,
                    event_type=executed_event_type,
                    source="ChatApplicationService",
                    meta={
                        "run_id": run_context.run_id,
                        "trace_id": run_context.trace_id,
                        "session_id": run_context.session_id,
                        "capability_id": capability_id,
                        "capability_domain": capability_domain,
                        "route_reason": route.get("reason"),
                        "meta": dict(capability_result.get("meta") or {}),
                    },
                    only_if=is_domain_capability,
                )
                return {
                    "response": dict(capability_result.get("response") or {}),
                    "executed_capability": True,
                    "ok": True,
                    "used_legacy": False,
                    "fallback_reason": None,
                }

            fallback_reason = str(capability_result.get("error") or "capability_handler_failed")
            self._record_event(
                observability=observability,
                event_type=fallback_event_type,
                source="ChatApplicationService",
                meta={
                    "run_id": run_context.run_id,
                    "trace_id": run_context.trace_id,
                    "session_id": run_context.session_id,
                    "capability_id": capability_id,
                    "capability_domain": capability_domain,
                    "fallback_reason": fallback_reason,
                },
                only_if=is_domain_capability,
            )
            if not allow_legacy_fallback:
                return {
                    "response": {},
                    "executed_capability": True,
                    "ok": False,
                    "used_legacy": False,
                    "fallback_reason": fallback_reason,
                }

        elif run_context.is_capability_mode_requested and is_domain_capability:
            self._record_event(
                observability=observability,
                event_type=fallback_event_type,
                source="ChatApplicationService",
                meta={
                    "run_id": run_context.run_id,
                    "trace_id": run_context.trace_id,
                    "session_id": run_context.session_id,
                    "capability_id": capability_id,
                    "capability_domain": capability_domain,
                    "fallback_reason": str(route.get("reason") or "route_use_legacy"),
                },
            )
            if not allow_legacy_fallback:
                return {
                    "response": {},
                    "executed_capability": False,
                    "ok": False,
                    "used_legacy": False,
                    "fallback_reason": str(route.get("reason") or "route_use_legacy"),
                }

        if not allow_legacy_fallback:
            return {
                "response": {},
                "executed_capability": False,
                "ok": False,
                "used_legacy": False,
                "fallback_reason": str(route.get("reason") or "route_use_legacy"),
            }

        legacy_response = legacy_runner(
            message=message,
            session_id=session_id,
            reset_memory=reset_memory,
        )
        return {
            "response": dict(legacy_response or {}),
            "executed_capability": False,
            "ok": True,
            "used_legacy": True,
            "fallback_reason": str(route.get("reason") or "legacy_runner"),
        }

    def _apply_attendance_memory_hints(
        self,
        *,
        message: str,
        planned_capability: dict[str, Any],
        memory_context: dict[str, Any],
        run_context: RunContext,
        observability,
    ) -> dict[str, Any]:
        capability_id = str(planned_capability.get("capability_id") or "")
        if not capability_id.startswith("attendance."):
            return planned_capability

        hints = self._extract_memory_hints(memory_context)
        updated = dict(planned_capability)
        used_hints: list[dict[str, Any]] = []

        preferred_view = str(hints.get("recurrence_view") or hints.get("output_mode") or "").strip().lower()
        if capability_id == "attendance.recurrence.grouped.v1":
            if preferred_view == "itemized" and not self._message_wants_grouped(message):
                updated = self._switch_capability(
                    current=updated,
                    capability_id="attendance.recurrence.itemized.v1",
                    reason_suffix="memory_hint_itemized",
                )
                used_hints.append(
                    {
                        "memory_key": "attendance.recurrence.default_view",
                        "memory_value": "itemized",
                        "reason": "planner_switched_to_itemized_from_memory_hint",
                    }
                )
        elif capability_id == "attendance.recurrence.itemized.v1":
            if preferred_view in {"grouped", "summary"} and not self._message_wants_itemized(message):
                updated = self._switch_capability(
                    current=updated,
                    capability_id="attendance.recurrence.grouped.v1",
                    reason_suffix="memory_hint_grouped",
                )
                used_hints.append(
                    {
                        "memory_key": "attendance.recurrence.default_view",
                        "memory_value": preferred_view,
                        "reason": "planner_switched_to_grouped_from_memory_hint",
                    }
                )

        memory_meta = run_context.metadata.get("memory_context")
        if isinstance(memory_meta, dict):
            memory_meta["hints"] = hints
            memory_meta["hints_used"] = used_hints

        for hint in used_hints:
            self._record_event(
                observability=observability,
                event_type="attendance_memory_hint_used",
                source="ChatApplicationService",
                meta={
                    "run_id": run_context.run_id,
                    "trace_id": run_context.trace_id,
                    "capability_id": updated.get("capability_id"),
                    "memory_key": hint.get("memory_key"),
                    "memory_value": hint.get("memory_value"),
                    "reason": hint.get("reason"),
                },
            )

        if hints:
            updated["memory_hints"] = hints
        return updated

    def _switch_capability(
        self,
        *,
        current: dict[str, Any],
        capability_id: str,
        reason_suffix: str,
    ) -> dict[str, Any]:
        switched = dict(current)
        definition = self.catalog.get(capability_id)
        switched["capability_id"] = capability_id
        switched["capability_exists"] = bool(definition)
        if definition is not None:
            switched["handler_key"] = definition.handler_key
            switched["policy_tags"] = list(definition.policy_tags)
            switched["legacy_intents"] = list(definition.legacy_intents)
        switched["reason"] = f"{str(current.get('reason') or 'planned')}|{reason_suffix}"
        return switched

    @staticmethod
    def _extract_memory_hints(memory_context: dict[str, Any]) -> dict[str, Any]:
        user_memory = list(memory_context.get("user_memory") or [])
        business_memory = list(memory_context.get("business_memory") or [])

        hints: dict[str, Any] = {}
        for row in user_memory:
            key = str(row.get("memory_key") or "").strip().lower()
            value = ChatApplicationService._memory_value_to_text(row.get("memory_value"))
            if key == "attendance.output_mode" and value:
                hints["output_mode"] = value
            elif key == "attendance.personal_status" and value:
                hints["personal_status"] = value
            elif key == "attendance.team" and value:
                hints["team"] = value
            elif key == "attendance.supervisor" and value:
                hints["supervisor"] = value
            elif key == "attendance.analytics.chart_type" and value:
                hints["analytics_chart_type"] = value
            elif key == "attendance.analytics.top_n" and value:
                hints["analytics_top_n"] = value
            elif key == "transport.default_period_label" and value:
                hints["transport_default_period_label"] = value
            elif key == "transport.output_mode" and value:
                hints["transport_output_mode"] = value
            elif key.startswith("query.pattern.") or key.startswith("query.pattern.domain."):
                pattern = ChatApplicationService._extract_query_pattern_hint(
                    scope="user",
                    memory_key=key,
                    memory_value=row.get("memory_value"),
                )
                if pattern:
                    hints.setdefault("query_patterns", []).append(pattern)
            elif key.startswith("reasoning.pattern."):
                pattern = ChatApplicationService._extract_reasoning_pattern_hint(
                    scope="user",
                    memory_key=key,
                    memory_value=row.get("memory_value"),
                )
                if pattern:
                    hints.setdefault("reasoning_patterns", []).append(pattern)

        for row in business_memory:
            key = str(row.get("memory_key") or "").strip().lower()
            value = ChatApplicationService._memory_value_to_text(row.get("memory_value"))
            if key == "attendance.recurrence.default_view" and value:
                hints["recurrence_view"] = value
            elif key == "attendance.default.personal_status" and value and not hints.get("personal_status"):
                hints["personal_status"] = value
            elif key == "attendance.analytics.default_chart_type" and value and not hints.get("analytics_chart_type"):
                hints["analytics_chart_type"] = value
            elif key.startswith("query.pattern.") or key.startswith("query.pattern.domain."):
                pattern = ChatApplicationService._extract_query_pattern_hint(
                    scope="business",
                    memory_key=key,
                    memory_value=row.get("memory_value"),
                )
                if pattern:
                    hints.setdefault("query_patterns", []).append(pattern)
            elif key.startswith("reasoning.pattern."):
                pattern = ChatApplicationService._extract_reasoning_pattern_hint(
                    scope="business",
                    memory_key=key,
                    memory_value=row.get("memory_value"),
                )
                if pattern:
                    hints.setdefault("reasoning_patterns", []).append(pattern)

        if list(hints.get("query_patterns") or []):
            hints["query_patterns"] = sorted(
                list(hints.get("query_patterns") or []),
                key=lambda item: (
                    -float(item.get("score") or 0.0),
                    str(item.get("domain_code") or ""),
                    str(item.get("template_id") or ""),
                ),
            )[:5]
            hints["query_pattern_ranking"] = ChatApplicationService._rank_query_patterns(memory_hints=hints)
        if list(hints.get("reasoning_patterns") or []):
            hints["reasoning_patterns"] = sorted(
                list(hints.get("reasoning_patterns") or []),
                key=lambda item: (
                    -float(item.get("pattern_strength") or 0.0),
                    str(item.get("domain_code") or ""),
                    str(item.get("signature") or ""),
                ),
            )[:5]

        return hints

    @staticmethod
    def _memory_value_to_text(value: Any) -> str | None:
        raw = value
        if isinstance(value, dict):
            if "value" in value:
                raw = value.get("value")
            elif value:
                raw = next(iter(value.values()))
        text = str(raw or "").strip().lower()
        return text or None

    @staticmethod
    def _extract_query_pattern_hint(*, scope: str, memory_key: str, memory_value: Any) -> dict[str, Any] | None:
        payload = dict(memory_value or {}) if isinstance(memory_value, dict) else {}
        if not payload:
            return None
        surface_pattern = dict(payload.get("surface_pattern") or {})
        semantic_pattern = dict(payload.get("semantic_pattern") or {})
        execution_pattern = dict(payload.get("execution_pattern") or {})
        satisfaction = dict(payload.get("satisfaction") or {})
        query_shape_key = str(surface_pattern.get("query_shape_key") or "").strip().lower()
        capability_id = str(execution_pattern.get("capability_id") or "").strip()
        template_id = str(payload.get("template_id") or "").strip().lower()
        domain_code = str(payload.get("domain_code") or "").strip().lower()
        if not query_shape_key or not capability_id or not template_id or not domain_code:
            return None
        return {
            "scope": str(scope or "").strip().lower(),
            "memory_key": str(memory_key or "").strip().lower(),
            "domain_code": domain_code,
            "template_id": template_id,
            "operation": str(payload.get("operation") or "").strip().lower(),
            "capability_id": capability_id,
            "group_by": [str(item).strip().lower() for item in list(semantic_pattern.get("group_by") or []) if str(item).strip()],
            "metrics": [str(item).strip().lower() for item in list(semantic_pattern.get("metrics") or []) if str(item).strip()],
            "filters": dict(semantic_pattern.get("filters") or {}),
            "query_shape_key": query_shape_key,
            "normalized_query": str(surface_pattern.get("normalized_query") or "").strip().lower(),
            "score": float(satisfaction.get("score") or 0.0),
        }

    @staticmethod
    def _extract_reasoning_pattern_hint(*, scope: str, memory_key: str, memory_value: Any) -> dict[str, Any] | None:
        payload = dict(memory_value or {}) if isinstance(memory_value, dict) else {}
        if not payload:
            return None
        signature = str(payload.get("signature") or "").strip().lower()
        if not signature:
            return None
        return {
            "scope": str(scope or "").strip().lower(),
            "memory_key": str(memory_key or "").strip().lower(),
            "signature": signature,
            "family": str(payload.get("family") or "").strip().lower(),
            "severity": str(payload.get("severity") or "").strip().lower(),
            "stage": str(payload.get("stage") or "").strip().lower(),
            "domain_code": str(payload.get("domain_code") or "").strip().lower(),
            "capability_id": str(payload.get("capability_id") or "").strip(),
            "summary": str(payload.get("summary") or "").strip(),
            "recommended_action": str(payload.get("recommended_action") or "").strip(),
            "pattern_strength": float(payload.get("pattern_strength") or 0.0),
        }

    @staticmethod
    def _rank_query_patterns(*, memory_hints: dict[str, Any]) -> list[dict[str, Any]]:
        ranking: dict[str, dict[str, Any]] = {}
        for item in list((memory_hints or {}).get("query_patterns") or []):
            if not isinstance(item, dict):
                continue
            domain_code = str(item.get("domain_code") or "general").strip().lower() or "general"
            current = ranking.setdefault(
                domain_code,
                {
                    "domain_code": domain_code,
                    "count": 0,
                    "top_score": 0.0,
                    "top_capability_id": "",
                    "top_template_id": "",
                },
            )
            current["count"] = int(current.get("count") or 0) + 1
            score = float(item.get("score") or 0.0)
            if score >= float(current.get("top_score") or 0.0):
                current["top_score"] = score
                current["top_capability_id"] = str(item.get("capability_id") or "").strip()
                current["top_template_id"] = str(item.get("template_id") or "").strip().lower()
        return sorted(
            list(ranking.values()),
            key=lambda item: (
                -float(item.get("top_score") or 0.0),
                -int(item.get("count") or 0),
                str(item.get("domain_code") or ""),
            ),
        )[:5]

    @staticmethod
    def _query_pattern_fastpath_saved_ms_estimate() -> int:
        raw = str(os.getenv("IA_DEV_QUERY_PATTERN_FASTPATH_SAVED_MS_ESTIMATE", "900") or "900").strip()
        try:
            value = int(raw)
        except ValueError:
            value = 900
        return max(0, min(value, 15000))

    @staticmethod
    def _message_wants_grouped(message: str) -> bool:
        normalized = str(message or "").strip().lower()
        return any(token in normalized for token in ("agrupado", "por empleado", "resumen"))

    @staticmethod
    def _message_wants_itemized(message: str) -> bool:
        normalized = str(message or "").strip().lower()
        return any(
            token in normalized
            for token in ("dia a dia", "detalle", "itemizado", "por ausentismo", "fecha por fecha")
        )

    @staticmethod
    def _bootstrap_classification(
        *,
        message: str,
        session_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized = ChatApplicationService._normalize_text(message)
        context = dict(session_context or {})
        last_domain = normalizar_codigo_dominio(context.get("last_domain"))
        last_needs_db = bool(context.get("last_needs_database"))
        if last_domain == "ausentismo" and last_needs_db and ChatApplicationService._is_chart_request(normalized):
            return {
                "intent": "ausentismo_query",
                "domain": "ausentismo",
                "selected_agent": "ausentismo_agent",
                "classifier_source": "bootstrap_context_followup",
                "needs_database": True,
                "output_mode": "summary",
                "needs_personal_join": bool(context.get("last_output_mode") == "table"),
                "contextual_reference": ChatApplicationService._is_contextual_reference_request(normalized),
                "last_group_dimension_key": str(context.get("last_group_dimension_key") or "").strip().lower(),
                "last_group_dimension_label": str(context.get("last_group_dimension_label") or "").strip(),
                "last_aggregation_focus": str(context.get("last_aggregation_focus") or "").strip().lower(),
                "last_metric_key": str(context.get("last_metric_key") or "").strip().lower(),
                "used_tools": [],
                "dictionary_context": {},
            }
        if ChatApplicationService._should_preserve_session_domain(
            normalized_message=normalized,
            session_context=context,
        ):
            return {
                "intent": "ausentismo_query" if last_domain == "ausentismo" else "empleados_query",
                "domain": last_domain or "general",
                "selected_agent": agente_desde_dominio(last_domain, fallback="analista_agent"),
                "classifier_source": "bootstrap_session_continuity",
                "needs_database": bool(last_needs_db),
                "output_mode": "summary",
                "needs_personal_join": last_domain == "ausentismo",
                "used_tools": [],
                "dictionary_context": {},
            }
        if any(token in normalized for token in ("ausent", "ausenc", "ausencia", "ausencias", "asistenc", "injustificad", "incapacid")):
            intent = "ausentismo_recurrencia" if "reincid" in normalized else "ausentismo_query"
            wants_table = any(token in normalized for token in ("tabla", "detalle", "lista", "mostrar"))
            wants_count = any(token in normalized for token in ("cantidad", "cuantos", "cuantas", "total", "resumen"))
            wants_group = any(
                token in normalized
                for token in (
                    "por supervisor",
                    "por area",
                    "por cargo",
                    "por carpeta",
                    "por justificacion",
                    "por causa",
                    "por tipo",
                    "por estado",
                )
            )
            output_mode = "table" if wants_table and not (wants_count and wants_group) else "summary"
            needs_personal_join = any(
                token in normalized
                for token in ("empleado", "personal", "supervisor", "area", "cargo", "nombre", "apellido")
            ) or intent == "ausentismo_recurrencia"
            return {
                "intent": intent,
                "domain": "ausentismo",
                "selected_agent": "ausentismo_agent",
                "classifier_source": "bootstrap_rules",
                "needs_database": True,
                "output_mode": output_mode,
                "needs_personal_join": needs_personal_join,
                "used_tools": [],
                "dictionary_context": {},
            }
        if ChatApplicationService._has_rrhh_domain_signals(normalized):
            return {
                "intent": "empleados_query",
                "domain": "empleados",
                "selected_agent": "empleados_agent",
                "classifier_source": "bootstrap_rules",
                "needs_database": True,
                "output_mode": "summary" if any(
                    token in normalized for token in ("cantidad", "cuantos", "cuantas", "total", "numero")
                ) else "table",
                "needs_personal_join": False,
                "used_tools": [],
                "dictionary_context": {},
            }
        if re.search(r"\b(regla|propuesta|diccionario|metadata|metadatos|sinonim|definicion)\b", normalized):
            return {
                "intent": "knowledge_change_request",
                "domain": "knowledge",
                "selected_agent": "analista_agent",
                "classifier_source": "bootstrap_rules",
                "needs_database": False,
                "output_mode": "summary",
                "used_tools": [],
                "dictionary_context": {},
            }
        return {
            "intent": "general_question",
            "domain": "general",
            "selected_agent": "analista_agent",
            "classifier_source": "bootstrap_rules",
            "needs_database": False,
            "output_mode": "summary",
            "used_tools": [],
            "dictionary_context": {},
        }

    @staticmethod
    def _should_preserve_session_domain(
        *,
        normalized_message: str,
        session_context: dict[str, Any] | None = None,
    ) -> bool:
        normalized = str(normalized_message or "")
        context = dict(session_context or {})
        last_domain = normalizar_codigo_dominio(context.get("last_domain"))
        if last_domain not in {"ausentismo", "empleados"}:
            return False
        if not bool(context.get("last_needs_database")):
            return False
        if not normalized or ChatApplicationService._has_rrhh_domain_signals(normalized):
            return last_domain == "ausentismo" and not re.search(
                r"\b(activo|activos|inactivo|inactivos|habilitado|habilitados|cedula|movil)\b",
                normalized,
            )
        if any(token in normalized for token in ("ausent", "ausenc", "incapacid")):
            return False
        if re.search(r"\b(regla|propuesta|diccionario|metadata|metadatos|sinonim|definicion)\b", normalized):
            return False
        return bool(
            re.match(r"^\s*(que|cuales|como|donde|quienes|cantidad|cuantos|cuantas)\b", normalized)
            or " por " in normalized
        )

    @staticmethod
    def _is_chart_request(normalized_message: str) -> bool:
        return any(
            token in normalized_message
            for token in (
                "grafica",
                "grafico",
                "graficar",
                "chart",
                "linea",
                "barra",
                "barras",
                "visual",
                "visualizar",
            )
        )

    @staticmethod
    def _is_contextual_reference_request(normalized_message: str) -> bool:
        return any(
            token in normalized_message
            for token in (
                "reporte",
                "resultado",
                "consulta",
                "este reporte",
                "este resultado",
                "esta consulta",
                "ese reporte",
                "ese resultado",
                "informacion anterior",
                "info anterior",
                "lo anterior",
                "mismo periodo",
                "mismo rango",
                "ese periodo",
                "ese rango",
            )
        )

    @staticmethod
    def _normalize_text(text: str) -> str:
        lowered = str(text or "").strip().lower()
        normalized = unicodedata.normalize("NFKD", lowered)
        clean = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        replacements = (
            (r"\bempelados\b", "empleados"),
            (r"\bempelado\b", "empleado"),
            (r"\bempeladas\b", "empleadas"),
            (r"\bempelada\b", "empleada"),
            (r"\bcantididad\b", "cantidad"),
            (r"\bares\b", "areas"),
            (r"\bvacasiones\b", "vacaciones"),
        )
        for pattern, replacement in replacements:
            clean = re.sub(pattern, replacement, clean)
        return re.sub(r"\s+", " ", clean).strip()

    @staticmethod
    def _resolve_user_key(*, actor_user_key: str | None, run_context: RunContext) -> str | None:
        explicit = str(actor_user_key or "").strip()
        if explicit:
            return explicit
        if run_context.session_id:
            return f"session:{run_context.session_id}"
        return None

    @staticmethod
    def _domain_code_from_capability(planned_capability: dict[str, Any]) -> str | None:
        capability_id = str(planned_capability.get("capability_id") or "").strip()
        if not capability_id:
            return None
        domain = dominio_desde_capacidad(capability_id)
        return str(domain or "").upper() or None

    @staticmethod
    def _extract_classification(response: dict[str, Any]) -> dict[str, Any]:
        orchestrator = dict((response or {}).get("orchestrator") or {})
        data_sources = dict((response or {}).get("data_sources") or {})
        ai_dictionary = dict(data_sources.get("ai_dictionary") or {})
        dictionary_context = ai_dictionary.get("context")
        if not isinstance(dictionary_context, dict):
            dictionary_context = {}
        return {
            "intent": str(orchestrator.get("intent") or ""),
            "domain": str(orchestrator.get("domain") or ""),
            "selected_agent": str(orchestrator.get("selected_agent") or ""),
            "classifier_source": str(orchestrator.get("classifier_source") or ""),
            "needs_database": bool(orchestrator.get("needs_database")),
            "output_mode": str(orchestrator.get("output_mode") or "summary"),
            "used_tools": list(orchestrator.get("used_tools") or []),
            "dictionary_context": dictionary_context,
        }

    def _evaluate_result_satisfaction(
        self,
        *,
        message: str,
        planned_capability: dict[str, Any],
        execution: dict[str, Any],
        resolved_query: ResolvedQuerySpec | None = None,
        execution_plan: QueryExecutionPlan | None = None,
        run_context: RunContext | None = None,
        observability=None,
        loop_iteration: int | None = None,
        route: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not bool(execution.get("ok")):
            return {"satisfied": False, "reason": "execution_not_ok"}
        validation_enabled = str(
            os.getenv("IA_DEV_QUERY_SATISFACTION_VALIDATION_ENABLED", "1") or "1"
        ).strip().lower() in {"1", "true", "yes", "on"}
        response = dict(execution.get("response") or {})
        legacy_validation: dict[str, Any]
        if not validation_enabled:
            legacy_validation = {"satisfied": True, "reason": "validation_disabled_by_flag", "checks": {}}
        else:
            validation = self.result_satisfaction_validator.validate(
                message=message,
                response=response,
                resolved_query=resolved_query,
                execution_plan=execution_plan,
            )
            legacy_validation = validation.as_dict()

        gate_enabled = self._satisfaction_review_gate_enabled()
        gate_shadow_enabled = self._satisfaction_review_gate_shadow_enabled()
        if not (gate_enabled or gate_shadow_enabled):
            return legacy_validation

        canonical_resolution = dict(
            ((run_context.metadata.get("query_intelligence") or {}).get("canonical_resolution") or {})
        ) if run_context is not None else {}
        if not canonical_resolution and run_context is not None:
            canonical_resolution = dict(run_context.metadata.get("canonical_resolution") or {})
        runtime_intent = resolved_query.intent if resolved_query is not None else None
        strategy = str((execution_plan.strategy if execution_plan else "") or "").strip()
        if not strategy:
            strategy = str(((execution.get("meta") or {}).get("strategy") or "")).strip()

        gate_result = self.satisfaction_review_gate.evaluate(
            raw_query=message,
            canonical_resolution=canonical_resolution,
            runtime_intent=runtime_intent,
            resolved_query=resolved_query,
            execution_result=execution,
            candidate_response=response,
            strategy=strategy,
            planned_capability=planned_capability,
            loop_metadata={
                "iteration": int(loop_iteration or 0),
                "route_reason": str((route or {}).get("reason") or ""),
                "route_use_legacy": bool((route or {}).get("use_legacy")),
                "route_execute_capability": bool((route or {}).get("execute_capability")),
            },
            legacy_validation=legacy_validation,
            runtime_flags={
                "active": gate_enabled,
                "shadow": gate_shadow_enabled and not gate_enabled,
                "llm_reviewer_enabled": self._satisfaction_review_gate_llm_reviewer_enabled(),
            },
        )
        gate_payload = (
            gate_result.as_dict()
            if hasattr(gate_result, "as_dict")
            else dict(gate_result or {})
        )
        gate_audit = self._build_satisfaction_review_gate_audit(
            gate_result=gate_payload,
            active=bool(gate_enabled),
            shadow=bool(gate_shadow_enabled and not gate_enabled),
            loop_iteration=loop_iteration,
        )
        comparison = self._compare_satisfaction_review_gate_with_legacy(
            legacy_validation=legacy_validation,
            gate_result=gate_payload,
        )
        self._record_event(
            observability=observability,
            event_type="satisfaction_review_gate_evaluated",
            source="ChatApplicationService",
            meta={
                "run_id": getattr(run_context, "run_id", ""),
                "trace_id": getattr(run_context, "trace_id", ""),
                "loop_iteration": int(loop_iteration or 0),
                "active": bool(gate_enabled),
                "shadow": bool(gate_shadow_enabled and not gate_enabled),
                "gate_result": gate_payload,
                "comparison": comparison,
            },
            only_if=True,
        )

        if run_context is not None:
            gate_history = list(run_context.metadata.get("satisfaction_review_gate_history") or [])
            gate_history.append(
                {
                    "iteration": int(loop_iteration or 0),
                    "active": bool(gate_enabled),
                    "shadow": bool(gate_shadow_enabled and not gate_enabled),
                    "result": gate_payload,
                    "comparison": comparison,
                }
            )
            run_context.metadata["satisfaction_review_gate_history"] = gate_history
            run_context.metadata["satisfaction_review_gate"] = {
                "active": bool(gate_enabled),
                "shadow": bool(gate_shadow_enabled and not gate_enabled),
                "last_result": gate_payload,
                "last_comparison": comparison,
                "audit": gate_audit,
            }
            query_intelligence_meta = dict(run_context.metadata.get("query_intelligence") or {})
            gate_audit_history = list(query_intelligence_meta.get("satisfaction_review_gate_audit_history") or [])
            gate_audit_history.append(dict(gate_audit))
            query_intelligence_meta["satisfaction_review_gate_audit"] = dict(gate_audit)
            query_intelligence_meta["satisfaction_review_gate_audit_history"] = gate_audit_history[-20:]
            run_context.metadata["query_intelligence"] = query_intelligence_meta

        if not gate_enabled:
            return {
                **legacy_validation,
                "satisfaction_review_gate": gate_payload,
                "satisfaction_review_gate_comparison": comparison,
                "satisfaction_review_gate_audit": gate_audit,
            }

        approved = bool(gate_payload.get("approved"))
        legacy_satisfied = bool(legacy_validation.get("satisfied", True))
        satisfied = bool(legacy_satisfied and approved)
        if satisfied:
            reason = str(legacy_validation.get("reason") or "ok")
        elif not legacy_satisfied:
            reason = str(legacy_validation.get("reason") or "legacy_validation_failed")
        else:
            reason = str(gate_payload.get("retry_reason") or "satisfaction_review_gate_rejected")
        checks = dict(legacy_validation.get("checks") or {})
        checks["satisfaction_review_gate"] = {
            "score": float(gate_payload.get("satisfaction_score") or 0.0),
            "issues_count": len(list(gate_payload.get("issues") or [])),
            "next_action": str(gate_payload.get("next_action") or ""),
            "approved": approved,
        }
        return {
            "satisfied": satisfied,
            "reason": reason,
            "checks": checks,
            "satisfaction_review_gate": gate_payload,
            "satisfaction_review_gate_comparison": comparison,
            "satisfaction_review_gate_audit": gate_audit,
        }

    @staticmethod
    def _extract_cedula_from_message(message: str) -> str | None:
        match = re.search(r"\b\d{6,13}\b", str(message or ""))
        if not match:
            return None
        return ChatApplicationService._normalize_digits(match.group(0)) or None

    @staticmethod
    def _normalize_digits(value: str) -> str:
        return "".join(ch for ch in str(value or "") if ch.isdigit())

    @staticmethod
    def _extract_period_from_response(*, response: dict[str, Any]) -> tuple[Any, Any] | None:
        candidates = []
        data = dict(response.get("data") or {})
        table = dict(data.get("table") or {})
        rows = list(table.get("rows") or [])
        if rows and isinstance(rows[0], dict):
            first = rows[0]
            # Opcional futuro: periodo en filas.
            if first.get("periodo_inicio") and first.get("periodo_fin"):
                candidates.append((str(first.get("periodo_inicio")), str(first.get("periodo_fin"))))

        reply = str(response.get("reply") or "")
        m = re.search(r"periodo\s+(\d{4}-\d{2}-\d{2})\s+al\s+(\d{4}-\d{2}-\d{2})", reply.lower())
        if m:
            candidates.append((m.group(1), m.group(2)))

        for start_text, end_text in candidates:
            try:
                from datetime import date
                return date.fromisoformat(start_text), date.fromisoformat(end_text)
            except Exception:
                continue
        return None

    def _record_policy_decision_event(
        self,
        *,
        observability,
        run_context: RunContext,
        planned_capability: dict[str, Any],
        policy_decision,
        loop_iteration: int | None = None,
    ) -> None:
        self._record_event(
            observability=observability,
            event_type="policy_runtime_decision",
            source="ChatApplicationService",
            meta={
                "run_id": run_context.run_id,
                "trace_id": run_context.trace_id,
                "session_id": run_context.session_id,
                "capability_id": planned_capability.get("capability_id"),
                "policy_action": policy_decision.action.value,
                "policy_id": policy_decision.policy_id,
                "policy_reason": policy_decision.reason,
                "policy_metadata": dict(policy_decision.metadata or {}),
                "loop_iteration": loop_iteration,
            },
        )

    @staticmethod
    def _proactive_loop_enabled(*, run_context: RunContext) -> bool:
        if not run_context.is_capability_mode_requested:
            return False
        value = str(os.getenv("IA_DEV_PROACTIVE_LOOP_ENABLED", "0") or "").strip().lower()
        return value in {"1", "true", "yes", "on"}

    @staticmethod
    def _proactive_loop_max_iterations() -> int:
        raw = str(os.getenv("IA_DEV_PROACTIVE_LOOP_MAX_ITERATIONS", "2") or "2").strip()
        try:
            value = int(raw)
        except ValueError:
            value = 2
        return max(1, min(value, 5))

    def _load_workflow_hints(self, *, user_key: str | None) -> dict[str, Any]:
        if not user_key:
            return {"pending_count": 0}
        try:
            writer = getattr(getattr(self.memory_runtime, "router", None), "writer", None)
            workflow = getattr(writer, "workflow_state", None)
            if workflow is None or not hasattr(workflow, "list_proposal_workflows"):
                return {"pending_count": 0}
            pending = workflow.list_proposal_workflows(status="pending", limit=20)
            user_pending = [
                item for item in list(pending or [])
                if str((item or {}).get("actor_user_key") or "").strip() in {"", user_key}
            ]
            return {
                "pending_count": len(user_pending),
            }
        except Exception:
            logger.exception("No se pudieron cargar workflow hints para planner")
            return {"pending_count": 0}

    def _save_task_state(
        self,
        *,
        run_context: RunContext,
        status: str,
        original_question: str,
        detected_domain: str,
        plan: dict[str, Any],
        source_used: dict[str, Any],
        executed_query: str | None = None,
        validation_result: dict[str, Any] | None = None,
        fallback_used: dict[str, Any] | None = None,
        recommendations: list[str] | None = None,
    ) -> None:
        try:
            workflow = self.task_state_service.save(
                run_id=run_context.run_id,
                status=status,
                original_question=original_question,
                detected_domain=detected_domain,
                plan=plan,
                source_used=source_used,
                executed_query=executed_query,
                validation_result=validation_result,
                fallback_used=fallback_used,
                recommendations=recommendations,
            )
            run_context.metadata["task_state"] = dict(workflow or {})
        except Exception:
            logger.exception("No se pudo persistir task state runtime")

    def _build_runtime_only_sql_failure_meta(
        self,
        *,
        execution_plan: QueryExecutionPlan,
        resolved_query: ResolvedQuerySpec,
        execution_result: dict[str, Any] | None,
    ) -> dict[str, Any]:
        metadata = dict((execution_plan.metadata if execution_plan else {}) or {})
        if not bool(metadata.get("legacy_analytics_isolated")):
            return {}
        if str(metadata.get("analytics_router_decision") or "").strip().lower() != "join_aware_sql":
            return {}
        raw_reason = str(
            (execution_result or {}).get("error")
            or ((execution_result or {}).get("validation") or {}).get("reason")
            or metadata.get("fallback_reason")
            or metadata.get("sql_reason")
            or execution_plan.reason
            or "unsafe_sql_plan"
        ).strip()
        runtime_reason = self.query_execution_planner._map_runtime_only_fallback_reason(
            reason=raw_reason
        )
        return {
            **metadata,
            "analytics_router_decision": "runtime_only_fallback",
            "legacy_analytics_isolated": True,
            "legacy_analytics_fallback_disabled": True,
            "blocked_legacy_fallback": True,
            "blocked_tool_ausentismo_service": True,
            "blocked_run_legacy_for_analytics": True,
            "runtime_only_fallback_reason": str(runtime_reason or "unsafe_sql_plan"),
            "fallback_reason": raw_reason or str(runtime_reason or "unsafe_sql_plan"),
            "cleanup_phase": str(metadata.get("cleanup_phase") or self.CLEANUP_PHASE),
            "domain_code": str(resolved_query.intent.domain_code or ""),
            "capability_id": str(execution_plan.capability_id or ""),
        }

    @staticmethod
    def _sql_assisted_execution_succeeded(
        *,
        query_intelligence: dict[str, Any],
        execution_meta: dict[str, Any],
    ) -> bool:
        execution_plan = dict(query_intelligence.get("execution_plan") or {})
        policy = dict(execution_plan.get("policy") or {})
        return (
            str(execution_plan.get("strategy") or "").strip().lower() == "sql_assisted"
            and bool(str(execution_plan.get("sql_query") or "").strip())
            and bool(policy.get("allowed"))
            and bool(execution_meta.get("satisfied", True))
            and not bool(execution_meta.get("used_legacy"))
            and not bool(execution_meta.get("blocked_legacy_fallback"))
            and not str(execution_meta.get("runtime_only_fallback_reason") or "").strip()
            and not str(execution_meta.get("fallback_reason") or "").strip()
        )

    @classmethod
    def _resolve_runtime_execution_metadata(
        cls,
        *,
        query_intelligence: dict[str, Any],
        execution_meta: dict[str, Any],
    ) -> dict[str, Any]:
        resolved = dict(((query_intelligence.get("execution_plan") or {}).get("metadata") or {}))
        resolved.update(dict(execution_meta or {}))
        if cls._sql_assisted_execution_succeeded(
            query_intelligence=query_intelligence,
            execution_meta=resolved,
        ):
            resolved.update(
                {
                    "analytics_router_decision": "sql_assisted",
                    "legacy_analytics_isolated": False,
                    "legacy_analytics_fallback_disabled": False,
                    "blocked_legacy_fallback": False,
                    "blocked_tool_ausentismo_service": False,
                    "blocked_run_legacy_for_analytics": False,
                    "runtime_only_fallback_reason": "",
                    "fallback_reason": "",
                    "cleanup_phase": "",
                }
            )
        return resolved

    @classmethod
    def _planner_valid_sql_result_wins(
        cls,
        *,
        query_intelligence: dict[str, Any],
        execution_meta: dict[str, Any] | None = None,
    ) -> bool:
        execution_plan = dict(query_intelligence.get("execution_plan") or {})
        policy = dict(execution_plan.get("policy") or {})
        if str(execution_plan.get("strategy") or "").strip().lower() != "sql_assisted":
            return False
        if not bool(str(execution_plan.get("sql_query") or "").strip()):
            return False
        if not bool(policy.get("allowed")):
            return False

        resolved_meta = cls._resolve_runtime_execution_metadata(
            query_intelligence=query_intelligence,
            execution_meta=dict(execution_meta or query_intelligence.get("execution_result") or {}),
        )
        response_payload = dict(resolved_meta.get("response") or {})
        if not response_payload:
            response_payload = dict(query_intelligence.get("precomputed_response") or {})
        if not response_payload:
            return False

        validation = dict(resolved_meta.get("validation") or {})
        if validation and not bool(validation.get("satisfied")):
            return False

        return (
            bool(resolved_meta.get("satisfied", True))
            and not bool(resolved_meta.get("used_legacy"))
            and not bool(resolved_meta.get("blocked_legacy_fallback"))
            and not str(resolved_meta.get("runtime_only_fallback_reason") or "").strip()
            and not str(resolved_meta.get("fallback_reason") or "").strip()
        )

    @classmethod
    def _enforce_planner_sql_authority_route(
        cls,
        *,
        route: dict[str, Any],
        query_intelligence: dict[str, Any],
        execution_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_route = dict(route or {})
        if not cls._planner_valid_sql_result_wins(
            query_intelligence=query_intelligence,
            execution_meta=execution_meta,
        ):
            return normalized_route

        selected_capability_id = str(normalized_route.get("selected_capability_id") or "").strip()
        execution_plan = dict(query_intelligence.get("execution_plan") or {})
        compat_capability_id = str(
            execution_plan.get("capability_id")
            or (execution_plan.get("metadata") or {}).get("capability_id")
            or ""
        ).strip()
        normalized_route.update(
            {
                "selected_capability_id": selected_capability_id or "query_execution_planner.sql_assisted",
                "selected_capability_compat_id": compat_capability_id,
                "execute_capability": False,
                "use_legacy": False,
                "shadow_enabled": bool(selected_capability_id or compat_capability_id),
                "selected_capability_authoritative": False,
                "runtime_authority": "query_execution_planner",
                "planner_was_authority": True,
                "planner_selected_strategy": "sql_assisted",
                "legacy_capability_path_used": False,
                "reason": "query_execution_planner_sql_assisted_authority",
            }
        )
        return normalized_route

    @staticmethod
    def _build_source_used_payload(
        *,
        query_intelligence: dict[str, Any],
        route: dict[str, Any] | None,
        response_flow: str,
        cleanup_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        resolved_query = dict(query_intelligence.get("resolved_query") or {})
        semantic_context = dict(resolved_query.get("semantic_context") or {})
        source_of_truth = dict(semantic_context.get("source_of_truth") or {})
        execution_plan = dict(query_intelligence.get("execution_plan") or {})
        payload = {
            "response_flow": response_flow,
            "query_intelligence_mode": str(query_intelligence.get("mode") or "off"),
            "route_reason": str((route or {}).get("reason") or ""),
            "runtime_authority": str((route or {}).get("runtime_authority") or ""),
            "planner_selected_strategy": str(execution_plan.get("strategy") or ""),
            "legacy_capability_path_used": bool((route or {}).get("legacy_capability_path_used")),
            "used_ai_dictionary": bool(source_of_truth.get("used_dictionary", True)),
            "used_yaml": bool(source_of_truth.get("used_yaml", True)),
            "structural_source": str(source_of_truth.get("structural_source") or source_of_truth.get("structural") or "ai_dictionary"),
            "narrative_source": str(source_of_truth.get("narrative") or "yaml_domain_context"),
            "structural_authority": str(source_of_truth.get("structural_authority") or "dictionary_first"),
            "yaml_role": str(source_of_truth.get("yaml_role") or "narrative_only"),
            "yaml_structural_ignored": bool(source_of_truth.get("yaml_structural_ignored")),
            "runtime_structural_context": dict(source_of_truth.get("runtime_structural_context") or {}),
        }
        cleanup = dict(cleanup_metadata or {})
        if cleanup:
            payload.update(
                {
                    "legacy_analytics_fallback_disabled": bool(cleanup.get("legacy_analytics_fallback_disabled")),
                    "blocked_legacy_fallback": bool(cleanup.get("blocked_legacy_fallback")),
                    "analytics_router_decision": str(cleanup.get("analytics_router_decision") or ""),
                    "legacy_analytics_isolated": bool(cleanup.get("legacy_analytics_isolated")),
                    "blocked_tool_ausentismo_service": bool(cleanup.get("blocked_tool_ausentismo_service")),
                    "blocked_run_legacy_for_analytics": bool(cleanup.get("blocked_run_legacy_for_analytics")),
                    "runtime_only_fallback_reason": str(cleanup.get("runtime_only_fallback_reason") or ""),
                    "fallback_reason": str(cleanup.get("fallback_reason") or ""),
                    "cleanup_phase": str(cleanup.get("cleanup_phase") or ""),
                }
            )
        return payload

    @staticmethod
    def _resolve_runtime_response_flow(
        *,
        query_intelligence: dict[str, Any],
        route: dict[str, Any],
        response: dict[str, Any],
        execution_meta: dict[str, Any],
    ) -> str:
        if ChatApplicationService._planner_valid_sql_result_wins(
            query_intelligence=query_intelligence,
            execution_meta=execution_meta,
        ):
            return "sql_assisted"
        if bool(execution_meta.get("blocked_legacy_fallback")):
            return "runtime_only_fallback"
        if bool(execution_meta.get("used_legacy")):
            return "legacy_fallback"
        classifier_source = str(((response.get("orchestrator") or {}).get("classifier_source") or "")).strip().lower()
        if "runtime_only_fallback" in classifier_source:
            return "runtime_only_fallback"
        if "sql_assisted" in classifier_source:
            return "sql_assisted"
        if bool(route.get("execute_capability")):
            return "handler"
        if classifier_source.startswith("openai") or classifier_source == "general_answer":
            return "openai_only"
        if str((query_intelligence.get("execution_plan") or {}).get("strategy") or "") == "sql_assisted":
            return "sql_assisted"
        return "new_runtime"

    @staticmethod
    def _build_runtime_recommendations(
        *,
        response: dict[str, Any],
        response_flow: str,
        fallback_used: dict[str, Any],
    ) -> list[str]:
        recommendations: list[str] = []
        if response_flow == "sql_assisted":
            recommendations.append("Explorar el mismo analisis por sede, area, cargo o fecha.")
        if response_flow == "runtime_only_fallback":
            recommendations.append(
                "Completar ai_dictionary para esta consulta antes de rehabilitar cualquier fallback legacy."
            )
        if response_flow == "legacy_fallback":
            recommendations.append(
                f"Revisar la razon del fallback para estructurar mejor la capacidad: {str(fallback_used.get('reason') or 'sin_detalle')}."
            )
        recommendations.extend(
            [
                str(item or "").strip()
                for item in list(((response.get("data") or {}).get("insights") or []))[:2]
                if str(item or "").strip()
            ]
        )
        return recommendations[:5]

    @staticmethod
    def _build_satisfaction_snapshot(
        *,
        run_context: RunContext,
        execution_meta: dict[str, Any],
    ) -> dict[str, Any]:
        gate = dict(run_context.metadata.get("satisfaction_review_gate") or {})
        last_result = dict(gate.get("last_result") or {})
        return {
            "satisfied": bool(execution_meta.get("satisfied", True)),
            "reason": str(execution_meta.get("satisfaction_reason") or ""),
            "gate_approved": bool(last_result.get("approved", True)),
            "gate_score": float(last_result.get("satisfaction_score") or 0.0),
        }

    def _record_runtime_resolution_event(
        self,
        *,
        observability,
        run_context: RunContext,
        query_intelligence: dict[str, Any],
        route: dict[str, Any],
        response: dict[str, Any],
        execution_meta: dict[str, Any],
        response_flow: str,
        satisfaction_snapshot: dict[str, Any],
    ) -> None:
        resolved_query = dict(query_intelligence.get("resolved_query") or {})
        semantic_context = dict(resolved_query.get("semantic_context") or {})
        resolved_semantic = dict(semantic_context.get("resolved_semantic") or {})
        source_of_truth = dict(semantic_context.get("source_of_truth") or {})
        runtime_metadata = self._resolve_runtime_execution_metadata(
            query_intelligence=query_intelligence,
            execution_meta=execution_meta,
        )
        domain_resolved = str(((resolved_query.get("intent") or {}).get("domain_code") or ""))
        pilot_enabled = self._productive_pilot_enabled_for_domain(domain_code=domain_resolved)
        runtime_compatibility = dict(run_context.metadata.get("runtime_compatibility") or {})
        columns_used = self._resolve_columns_used_for_runtime_event(
            query_intelligence=query_intelligence,
            response=response,
        )
        insight_quality = self._resolve_insight_quality(
            response=response,
            response_flow=response_flow,
            execution_meta=execution_meta,
            satisfaction_snapshot=satisfaction_snapshot,
        )
        self._record_event(
            observability=observability,
            event_type="runtime_response_resolved",
            source="ChatApplicationService",
            meta={
                "run_id": run_context.run_id,
                "trace_id": run_context.trace_id,
                "original_question": str(run_context.message or ""),
                "response_flow": response_flow,
                "domain_resolved": domain_resolved,
                "tables_detected": [
                    str(item.get("table_name") or "")
                    for item in list(semantic_context.get("tables") or [])
                    if isinstance(item, dict)
                ],
                "columns_detected": [
                    str(item.get("column_name") or "")
                    for item in list(semantic_context.get("column_profiles") or [])[:25]
                    if isinstance(item, dict)
                ],
                "columns_used": columns_used,
                "relations_used": list(
                    (query_intelligence.get("execution_plan") or {}).get("metadata", {}).get("relations_used")
                    or resolved_semantic.get("relations")
                    or []
                ),
                "compiler_used": str(
                    (query_intelligence.get("execution_plan") or {}).get("metadata", {}).get("compiler")
                    or ((response.get("data_sources") or {}).get("query_intelligence") or {}).get("compiler")
                    or ""
                ),
                "metric_used": str(
                    (query_intelligence.get("execution_plan") or {}).get("metadata", {}).get("metric_used")
                    or ((response.get("data_sources") or {}).get("query_intelligence") or {}).get("metric_used")
                    or ""
                ),
                "aggregation_used": str(
                    (query_intelligence.get("execution_plan") or {}).get("metadata", {}).get("aggregation_used")
                    or ((response.get("data_sources") or {}).get("query_intelligence") or {}).get("aggregation_used")
                    or ""
                ),
                "dimensions_used": list(
                    (query_intelligence.get("execution_plan") or {}).get("metadata", {}).get("dimensions_used")
                    or ((response.get("data_sources") or {}).get("query_intelligence") or {}).get("dimensions_used")
                    or []
                ),
                "declared_metric_source": str(
                    (query_intelligence.get("execution_plan") or {}).get("metadata", {}).get("declared_metric_source")
                    or ((response.get("data_sources") or {}).get("query_intelligence") or {}).get("declared_metric_source")
                    or ""
                ),
                "declared_dimensions_source": str(
                    (query_intelligence.get("execution_plan") or {}).get("metadata", {}).get("declared_dimensions_source")
                    or ((response.get("data_sources") or {}).get("query_intelligence") or {}).get("declared_dimensions_source")
                    or ""
                ),
                "used_ai_dictionary": bool(source_of_truth.get("used_dictionary", True)),
                "used_yaml": bool(source_of_truth.get("used_yaml", True)),
                "structural_source": str(source_of_truth.get("structural_source") or source_of_truth.get("structural") or "ai_dictionary"),
                "yaml_role": str(source_of_truth.get("yaml_role") or "narrative_only"),
                "yaml_structural_ignored": bool(source_of_truth.get("yaml_structural_ignored")),
                "route_reason": str(route.get("reason") or ""),
                "runtime_authority": str(runtime_compatibility.get("runtime_authority") or ""),
                "planner_selected_strategy": str(runtime_compatibility.get("planner_selected_strategy") or ""),
                "legacy_capability_path_used": bool(runtime_compatibility.get("legacy_capability_path_used")),
                "fallback_reason": str(runtime_metadata.get("fallback_reason") or ""),
                "sql_reason": str(
                    execution_meta.get("sql_reason")
                    or ((query_intelligence.get("execution_plan") or {}).get("metadata") or {}).get("sql_reason")
                    or ""
                ),
                "legacy_analytics_fallback_disabled": bool(
                    runtime_metadata.get("legacy_analytics_fallback_disabled")
                ),
                "blocked_legacy_fallback": bool(
                    runtime_metadata.get("blocked_legacy_fallback")
                ),
                "analytics_router_decision": str(runtime_metadata.get("analytics_router_decision") or ""),
                "legacy_analytics_isolated": bool(runtime_metadata.get("legacy_analytics_isolated")),
                "blocked_tool_ausentismo_service": bool(
                    runtime_metadata.get("blocked_tool_ausentismo_service")
                ),
                "blocked_run_legacy_for_analytics": bool(
                    runtime_metadata.get("blocked_run_legacy_for_analytics")
                ),
                "runtime_only_fallback_reason": str(runtime_metadata.get("runtime_only_fallback_reason") or ""),
                "cleanup_phase": str(runtime_metadata.get("cleanup_phase") or ""),
                "satisfaction_review": dict(satisfaction_snapshot or {}),
                "classifier_source": str(((response.get("orchestrator") or {}).get("classifier_source") or "")),
                "sql_used": self._resolve_sql_used_for_runtime_event(
                    response=response,
                    query_intelligence=query_intelligence,
                ),
                "insight_quality": insight_quality,
                "pilot_enabled": pilot_enabled,
                "pilot_mode": "productive_pilot" if pilot_enabled else "",
                "pilot_phase": self.PILOT_PHASE,
                "pilot_scope": "attendance_employees_real_traffic" if pilot_enabled else "",
            },
            only_if=True,
        )

    @staticmethod
    def _attach_runtime_metadata(
        *,
        response: dict[str, Any],
        run_context: RunContext,
        response_flow: str,
    ) -> dict[str, Any]:
        payload = dict(response or {})
        orchestrator = dict(payload.get("orchestrator") or {})
        intent_arbitration = dict(run_context.metadata.get("intent_arbitration") or {})
        query_intelligence = dict(run_context.metadata.get("query_intelligence") or {})
        execution_plan = dict(query_intelligence.get("execution_plan") or {})
        execution_meta = ChatApplicationService._resolve_runtime_execution_metadata(
            query_intelligence=query_intelligence,
            execution_meta=dict(run_context.metadata.get("runtime_execution_meta") or {}),
        )
        resolved_query = dict(query_intelligence.get("resolved_query") or {})
        semantic_context = dict(resolved_query.get("semantic_context") or {})
        source_of_truth = dict(semantic_context.get("source_of_truth") or {})
        runtime_compatibility = dict(run_context.metadata.get("runtime_compatibility") or {})
        resolved_final_intent = ChatApplicationService._resolve_runtime_final_intent(
            intent_arbitration=intent_arbitration,
            execution_plan=execution_plan,
            response_flow=response_flow,
        )
        orchestrator["runtime_flow"] = response_flow
        orchestrator["arbitrated_intent"] = str(intent_arbitration.get("final_intent") or "")
        orchestrator["final_intent"] = resolved_final_intent
        orchestrator["final_domain"] = str(
            intent_arbitration.get("final_domain")
            or execution_plan.get("domain_code")
            or orchestrator.get("domain")
            or ""
        ).strip().lower()
        orchestrator["compiler_used"] = str(
            execution_meta.get("compiler")
            or execution_meta.get("compiler_used")
            or ((payload.get("data_sources") or {}).get("query_intelligence") or {}).get("compiler")
            or ""
        )
        orchestrator["analytics_router_decision"] = str(
            execution_meta.get("analytics_router_decision")
            or (run_context.metadata.get("cleanup_guard") or {}).get("analytics_router_decision")
            or ""
        )
        orchestrator["fallback_reason"] = str(
            execution_meta.get("fallback_reason") or ""
        )
        payload["orchestrator"] = orchestrator
        payload["task_state"] = dict((run_context.metadata.get("task_state") or {}))
        data_sources = dict(payload.get("data_sources") or {})
        cleanup_guard = dict(run_context.metadata.get("cleanup_guard") or {})
        data_sources["runtime"] = {
            "ok": True,
            "flow": response_flow,
            "arbitrated_intent": str(intent_arbitration.get("final_intent") or ""),
            "final_intent": resolved_final_intent,
            "final_domain": str(
                intent_arbitration.get("final_domain")
                or execution_plan.get("domain_code")
                or orchestrator.get("domain")
                or ""
            ).strip().lower(),
            "task_state_key": str(((payload.get("task_state") or {}).get("workflow_key") or "")),
            "runtime_authority": str(runtime_compatibility.get("runtime_authority") or ""),
            "planner_was_authority": bool(runtime_compatibility.get("planner_was_authority")),
            "legacy_capability_path_used": bool(runtime_compatibility.get("legacy_capability_path_used")),
            "routing_mode": str(runtime_compatibility.get("routing_mode") or ""),
            "legacy_analytics_fallback_disabled": bool(execution_meta.get("legacy_analytics_fallback_disabled")),
            "blocked_legacy_fallback": bool(execution_meta.get("blocked_legacy_fallback")),
            "analytics_router_decision": str(
                execution_meta.get("analytics_router_decision")
                or cleanup_guard.get("analytics_router_decision")
                or ""
            ),
            "legacy_analytics_isolated": bool(execution_meta.get("legacy_analytics_isolated")),
            "blocked_tool_ausentismo_service": bool(execution_meta.get("blocked_tool_ausentismo_service")),
            "blocked_run_legacy_for_analytics": bool(execution_meta.get("blocked_run_legacy_for_analytics")),
            "runtime_only_fallback_reason": str(execution_meta.get("runtime_only_fallback_reason") or ""),
            "fallback_reason": str(execution_meta.get("fallback_reason") or ""),
            "cleanup_phase": str(execution_meta.get("cleanup_phase") or ""),
            "compiler_used": str(
                execution_meta.get("compiler")
                or execution_meta.get("compiler_used")
                or ((payload.get("data_sources") or {}).get("query_intelligence") or {}).get("compiler")
                or ""
            ),
            "structural_source": str(source_of_truth.get("structural_source") or source_of_truth.get("structural") or "ai_dictionary"),
            "yaml_role": str(source_of_truth.get("yaml_role") or "narrative_only"),
            "yaml_structural_ignored": bool(source_of_truth.get("yaml_structural_ignored")),
            "pilot_enabled": ChatApplicationService._productive_pilot_enabled_for_domain(
                domain_code=str((orchestrator.get("domain") or "") or "")
            ),
            "pilot_phase": ChatApplicationService.PILOT_PHASE,
        }
        payload["data_sources"] = data_sources
        return payload

    @staticmethod
    def _resolve_runtime_final_intent(
        *,
        intent_arbitration: dict[str, Any],
        execution_plan: dict[str, Any],
        response_flow: str,
    ) -> str:
        final_intent = str(intent_arbitration.get("final_intent") or "").strip().lower()
        final_domain = str(intent_arbitration.get("final_domain") or execution_plan.get("domain_code") or "").strip().lower()
        execution_meta = dict(execution_plan.get("metadata") or {})
        compiler_used = str(
            execution_meta.get("compiler")
            or execution_meta.get("compiler_used")
            or ""
        ).strip().lower()
        constraints = dict(execution_plan.get("constraints") or {})
        group_by = [
            str(item or "").strip().lower()
            for item in list(constraints.get("group_by") or [])
            if str(item or "").strip()
        ]
        filters = dict(constraints.get("filters") or {})
        has_valid_employee_analytics_plan = bool(
            final_domain in {"empleados", "rrhh"}
            and str(response_flow or "").strip().lower() == "sql_assisted"
            and compiler_used == "employee_semantic_sql"
            and group_by
            and bool(filters)
        )
        if has_valid_employee_analytics_plan:
            return "analytics_query"
        return final_intent or ""

    def _resolve_cleanup_guard(
        self,
        *,
        route: dict[str, Any],
        resolved_query: ResolvedQuerySpec | None,
        execution_plan: QueryExecutionPlan | None,
        planned_capability: dict[str, Any],
    ) -> dict[str, Any]:
        metadata = dict((execution_plan.metadata if execution_plan else {}) or {})
        if not bool(metadata.get("blocked_legacy_fallback")):
            return {}
        guard = {
            "legacy_analytics_fallback_disabled": bool(metadata.get("legacy_analytics_fallback_disabled")),
            "blocked_legacy_fallback": bool(metadata.get("blocked_legacy_fallback")),
            "analytics_router_decision": str(metadata.get("analytics_router_decision") or ""),
            "legacy_analytics_isolated": bool(metadata.get("legacy_analytics_isolated")),
            "blocked_tool_ausentismo_service": bool(metadata.get("blocked_tool_ausentismo_service")),
            "blocked_run_legacy_for_analytics": bool(metadata.get("blocked_run_legacy_for_analytics")),
            "runtime_only_fallback_reason": str(
                metadata.get("runtime_only_fallback_reason")
                or ((execution_plan.reason if execution_plan else "") or "")
            ),
            "fallback_reason": str(
                metadata.get("fallback_reason")
                or metadata.get("sql_reason")
                or ((execution_plan.reason if execution_plan else "") or "")
            ),
            "cleanup_phase": str(metadata.get("cleanup_phase") or self.CLEANUP_PHASE),
            "capability_id": str(planned_capability.get("capability_id") or route.get("selected_capability_id") or ""),
            "domain_code": str((resolved_query.intent.domain_code if resolved_query else "") or ""),
        }
        return guard

    def _build_runtime_only_fallback_response(
        self,
        *,
        run_context: RunContext,
        resolved_query: ResolvedQuerySpec | None,
        runtime_execution_plan: QueryExecutionPlan | None,
        fallback_reason: str,
    ) -> dict[str, Any]:
        normalized_reason = str(fallback_reason or "unsafe_sql_plan").strip().lower() or "unsafe_sql_plan"
        reason_text, missing_text = self._runtime_only_fallback_copy(reason=normalized_reason)
        domain_code = str((resolved_query.intent.domain_code if resolved_query else "") or "ausentismo")
        reply = (
            "El piloto analytics quedo aislado del fallback legacy para esta consulta. "
            f"{reason_text} {missing_text}"
        ).strip()
        runtime_meta = {
            "ok": True,
            "mode": "runtime_only_fallback",
            "strategy": "fallback",
            "compiler": str(((runtime_execution_plan.metadata if runtime_execution_plan else {}) or {}).get("compiler") or ""),
            "reason": normalized_reason,
            "analytics_router_decision": "runtime_only_fallback",
            "legacy_analytics_isolated": True,
            "legacy_analytics_fallback_disabled": True,
            "blocked_legacy_fallback": True,
            "blocked_tool_ausentismo_service": True,
            "blocked_run_legacy_for_analytics": True,
            "runtime_only_fallback_reason": normalized_reason,
            "fallback_reason": str(
                ((runtime_execution_plan.metadata if runtime_execution_plan else {}) or {}).get("fallback_reason")
                or normalized_reason
            ),
            "cleanup_phase": self.CLEANUP_PHASE,
        }
        return {
            "session_id": str(run_context.session_id or ""),
            "reply": reply,
            "orchestrator": {
                "intent": str((resolved_query.intent.operation if resolved_query else "") or "aggregate"),
                "domain": domain_code,
                "selected_agent": agente_desde_dominio(domain_code, fallback="analista_agent"),
                "classifier_source": "query_intelligence_runtime_only_fallback",
                "needs_database": True,
                "output_mode": "summary",
                "used_tools": [],
            },
            "data": {
                "kpis": {},
                "series": [],
                "labels": [],
                "insights": [
                    "No se ejecuto run_legacy: el piloto analytics quedo bloqueado para evitar recaidas silenciosas al legado.",
                    missing_text,
                ],
                "table": {"columns": [], "rows": [], "rowcount": 0},
                "findings": [],
            },
            "actions": [
                {
                    "id": f"runtime-only-fallback-{run_context.run_id}",
                    "type": "governance_followup",
                    "label": "Completar ai_dictionary",
                    "payload": {
                        "reason": normalized_reason,
                        "cleanup_phase": self.CLEANUP_PHASE,
                    },
                }
            ],
            "data_sources": {
                "query_intelligence": runtime_meta,
            },
            "trace": [],
            "observability": {"enabled": True, "duration_ms": 0},
            "active_nodes": ["q", "gpt", "route", "result"],
        }

    @staticmethod
    def _runtime_only_fallback_copy(*, reason: str) -> tuple[str, str]:
        normalized = str(reason or "unsafe_sql_plan").strip().lower()
        mapping = {
            "unsupported_metric": (
                "La metrica pedida todavia no esta soportada por el compiler join-aware.",
                "Falta declarar la metrica en ai_dictionary.dd_campos y su capacidad en ai_dictionary.ia_dev_capacidades_columna.",
            ),
            "unsupported_dimension": (
                "La dimension solicitada no quedo soportada de forma segura en el piloto.",
                "Falta modelar la dimension y sus sinonimos en ai_dictionary.dd_campos y ai_dictionary.dd_sinonimos.",
            ),
            "missing_dictionary_relation": (
                "No existe una relacion utilizable en ai_dictionary para resolver el join de esta analitica.",
                "Falta registrar la relacion en ai_dictionary.dd_relaciones entre ausentismo y empleados.",
            ),
            "missing_dictionary_column": (
                "El compiler no encontro una columna gobernada suficiente para armar el SQL.",
                "Falta declarar la columna requerida en ai_dictionary.dd_campos y habilitar su uso analitico.",
            ),
            "no_actionable_insight": (
                "La consulta no produjo un insight accionable con la informacion gobernada disponible.",
                "Falta enriquecer ai_dictionary con columnas o reglas que permitan una conclusion util.",
            ),
            "unsafe_sql_plan": (
                "El plan SQL no paso las validaciones de seguridad del runtime.",
                "Hay que ajustar ai_dictionary para que tablas, columnas y relaciones queden completamente trazables.",
            ),
        }
        return mapping.get(normalized, mapping["unsafe_sql_plan"])

    @classmethod
    def _productive_pilot_enabled_for_domain(cls, *, domain_code: str) -> bool:
        normalized_domain = normalizar_codigo_dominio(domain_code)
        if normalized_domain not in cls.PRODUCTIVE_PILOT_DOMAINS:
            return False
        raw = str(os.getenv("IA_DEV_ATTENDANCE_EMPLOYEES_PILOT_ENABLED", "0") or "").strip().lower()
        return raw in {"1", "true", "yes", "on"}

    @staticmethod
    def _resolve_sql_used_for_runtime_event(
        *,
        response: dict[str, Any],
        query_intelligence: dict[str, Any],
    ) -> str:
        data_sources = dict(response.get("data_sources") or {})
        query_intelligence_source = dict(data_sources.get("query_intelligence") or {})
        if str(query_intelligence_source.get("query") or "").strip():
            return str(query_intelligence_source.get("query") or "").strip()
        return str(((query_intelligence.get("execution_plan") or {}).get("sql_query") or "")).strip()

    @staticmethod
    def _resolve_columns_used_for_runtime_event(
        *,
        query_intelligence: dict[str, Any],
        response: dict[str, Any],
    ) -> list[str]:
        metadata = dict(((query_intelligence.get("execution_plan") or {}).get("metadata") or {}))
        columns_used = [
            str(item or "").strip().lower()
            for item in list(metadata.get("physical_columns_used") or metadata.get("columns_detected") or [])
            if str(item or "").strip()
        ]
        if columns_used:
            return sorted(dict.fromkeys(columns_used))
        table = dict((response.get("data") or {}).get("table") or {})
        fallback_columns = [
            str(item or "").strip().lower()
            for item in list(table.get("columns") or [])
            if str(item or "").strip()
        ]
        return sorted(dict.fromkeys(fallback_columns))

    @staticmethod
    def _resolve_insight_quality(
        *,
        response: dict[str, Any],
        response_flow: str,
        execution_meta: dict[str, Any],
        satisfaction_snapshot: dict[str, Any],
    ) -> str:
        normalized_flow = str(response_flow or "").strip().lower()
        fallback_reason = str(execution_meta.get("fallback_reason") or "").strip().lower()
        insights = [
            str(item or "").strip()
            for item in list(((response.get("data") or {}).get("insights") or []))
            if str(item or "").strip()
        ]
        if normalized_flow in {"runtime_only_fallback", "legacy_fallback"}:
            return "poor"
        if not bool((satisfaction_snapshot or {}).get("satisfied", True)):
            return "poor"
        if "no_actionable_insight" in fallback_reason:
            return "poor"
        if not insights:
            return "poor"
        if len(insights) == 1:
            return "fair"
        return "good"

    @staticmethod
    def _record_event(
        *,
        observability,
        event_type: str,
        source: str,
        meta: dict[str, Any],
        only_if: bool = True,
    ) -> None:
        if not only_if:
            return
        if observability is None or not hasattr(observability, "record_event"):
            return
        try:
            observability.record_event(
                event_type=event_type,
                source=source,
                meta=meta,
            )
        except Exception:
            logger.exception("No se pudo registrar evento de observabilidad")

    @staticmethod
    def _record_shadow_observability(
        *,
        observability,
        run_context: RunContext,
        classification: dict[str, Any],
        planned_capability: dict[str, Any],
        route: dict[str, Any],
        divergence: dict[str, Any],
    ) -> None:
        return
