from __future__ import annotations

import logging
import os
import re
import unicodedata
from typing import Any, Callable

from apps.ia_dev.application.context.run_context import RunContext
from apps.ia_dev.application.delegation.delegation_coordinator import (
    DelegationCoordinator,
)
from apps.ia_dev.application.memory.chat_memory_runtime_service import (
    ChatMemoryRuntimeService,
)
from apps.ia_dev.application.orchestration.loop_controller import LoopController
from apps.ia_dev.application.orchestration.response_assembler import (
    LegacyResponseAssembler,
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
from apps.ia_dev.application.routing.capability_catalog import CapabilityCatalog
from apps.ia_dev.application.routing.capability_planner import CapabilityPlanner
from apps.ia_dev.application.routing.capability_router import CapabilityRouter
from apps.ia_dev.application.routing.intent_to_capability_bridge import (
    IntentToCapabilityBridge,
)
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
from apps.ia_dev.services.memory_service import SessionMemoryStore


logger = logging.getLogger(__name__)


class ChatApplicationService:
    def __init__(
        self,
        *,
        catalog: CapabilityCatalog | None = None,
        planner: CapabilityPlanner | None = None,
        router: CapabilityRouter | None = None,
        bridge: IntentToCapabilityBridge | None = None,
        policy_guard: PolicyGuard | None = None,
        response_assembler: LegacyResponseAssembler | None = None,
        memory_runtime: ChatMemoryRuntimeService | None = None,
        delegation_coordinator: DelegationCoordinator | None = None,
        semantic_business_resolver: SemanticBusinessResolver | None = None,
        context_builder: ContextBuilder | None = None,
        semantic_normalization_service: SemanticNormalizationService | None = None,
        canonical_resolution_service: CanonicalResolutionService | None = None,
        query_intent_resolver: QueryIntentResolver | None = None,
        query_execution_planner: QueryExecutionPlanner | None = None,
        result_satisfaction_validator: ResultSatisfactionValidator | None = None,
        satisfaction_review_gate: SatisfactionReviewGate | None = None,
        loop_controller: LoopController | None = None,
        query_pattern_memory_service: QueryPatternMemoryService | None = None,
        reasoning_ledger_service: ReasoningLedgerService | None = None,
        diagnostic_orchestrator: DiagnosticOrchestrator | None = None,
        reasoning_memory_service: ReasoningMemoryService | None = None,
    ):
        self.catalog = catalog or CapabilityCatalog()
        self.bridge = bridge or IntentToCapabilityBridge()
        self.planner = planner or CapabilityPlanner(catalog=self.catalog, bridge=self.bridge)
        self.router = router or CapabilityRouter()
        self.policy_guard = policy_guard or PolicyGuard()
        self.response_assembler = response_assembler or LegacyResponseAssembler()
        self.memory_runtime = memory_runtime or ChatMemoryRuntimeService()
        self.delegation_coordinator = delegation_coordinator or DelegationCoordinator()
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
        self.loop_controller = loop_controller or LoopController()
        self.query_pattern_memory_service = query_pattern_memory_service or QueryPatternMemoryService()
        self.reasoning_ledger_service = reasoning_ledger_service or ReasoningLedgerService()
        self.diagnostic_orchestrator = diagnostic_orchestrator or DiagnosticOrchestrator()
        self.reasoning_memory_service = reasoning_memory_service or ReasoningMemoryService()

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
        query_intelligence_mode = str(query_intelligence.get("mode") or "off")
        classification_override = dict(query_intelligence.get("classification_override") or {})
        if query_intelligence_mode == "active" and classification_override:
            pre_classification = {
                **pre_classification,
                **classification_override,
            }
        pre_classification = self._apply_legacy_bridge_canonical_alignment(
            message=message,
            classification=pre_classification,
            query_intelligence=query_intelligence,
            run_context=run_context,
            observability=observability,
        )
        bootstrap_plan = self.planner.plan_from_legacy(
            message=message,
            classification=pre_classification,
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
        self.reasoning_ledger_service.record_progress(
            run_context=run_context,
            stage="planning",
            status="completed",
            summary="Se generaron candidatos de capacidad para resolver la consulta.",
            details={
                "candidate_count": len(candidate_plans),
                "top_capability_id": str((candidate_plans[0] if candidate_plans else {}).get("capability_id") or ""),
                "top_reason": str((candidate_plans[0] if candidate_plans else {}).get("reason") or ""),
            },
            next_step="ejecutar la ruta principal y validar el resultado",
            confidence=0.72,
        )

        precomputed_response = dict(query_intelligence.get("precomputed_response") or {})

        delegation_decision = {
            "mode": "off",
            "should_delegate": False,
            "plan_reason": "query_intelligence_precomputed_response",
            "selected_domains": [],
            "tasks": [],
            "executed": False,
            "response": None,
            "warnings": [],
        }
        if not precomputed_response:
            delegation_decision = self.delegation_coordinator.plan_and_maybe_execute(
                message=message,
                classification=pre_classification,
                planned_candidates=candidate_plans,
                run_context=run_context,
                observability=observability,
            )
        run_context.metadata["delegation"] = {
            "mode": str(delegation_decision.get("mode") or "off"),
            "should_delegate": bool(delegation_decision.get("should_delegate")),
            "plan_reason": str(delegation_decision.get("plan_reason") or ""),
            "selected_domains": list(delegation_decision.get("selected_domains") or []),
            "tasks": list(delegation_decision.get("tasks") or []),
            "executed": bool(delegation_decision.get("executed")),
            "is_multi_domain": len(list(delegation_decision.get("selected_domains") or [])) > 1,
            "warnings": list(delegation_decision.get("warnings") or []),
        }

        delegated_response = dict(delegation_decision.get("response") or {})
        if delegated_response:
            delegated_response.setdefault("session_id", str(run_context.session_id or ""))
            orchestrator = delegated_response.get("orchestrator")
            if not isinstance(orchestrator, dict):
                orchestrator = {}
            orchestrator.setdefault("intent", str(pre_classification.get("intent") or ""))
            orchestrator.setdefault("domain", str(pre_classification.get("domain") or ""))
            orchestrator.setdefault("selected_agent", str(pre_classification.get("selected_agent") or ""))
            orchestrator.setdefault("classifier_source", "delegation_active")
            orchestrator.setdefault("needs_database", bool(pre_classification.get("needs_database")))
            orchestrator.setdefault("output_mode", "summary")
            delegated_response["orchestrator"] = orchestrator
            if "data_sources" not in delegated_response or not isinstance(delegated_response.get("data_sources"), dict):
                delegated_response["data_sources"] = {}

        if precomputed_response:
            planned_capability = dict(candidate_plans[0] if candidate_plans else bootstrap_plan)
            policy_decision = self.policy_guard.evaluate(
                run_context=run_context,
                planned_capability=planned_capability,
            )
            route = {
                "routing_mode": run_context.routing_mode,
                "selected_capability_id": str(
                    planned_capability.get("capability_id")
                    or f"query_intelligence.{str(query_intelligence.get('execution_plan', {}).get('strategy') or 'precomputed')}.v1"
                ),
                "execute_capability": False,
                "use_legacy": False,
                "shadow_enabled": True,
                "reason": f"query_intelligence_{query_intelligence_mode}_precomputed_response",
                "policy_action": policy_decision.action.value,
                "policy_allowed": policy_decision.allowed,
                "capability_exists": bool(planned_capability.get("capability_exists")),
                "rollout_enabled": bool(planned_capability.get("rollout_enabled", True)),
            }
            primary_response = precomputed_response
            run_context.metadata["proactive_loop"] = {
                "enabled": False,
                "iterations_ran": 0,
                "max_iterations": 0,
                "selected_capability_id": planned_capability.get("capability_id"),
                "used_legacy": False,
                "iterations": [],
            }
        elif delegated_response and bool(delegation_decision.get("executed")):
            planned_capability = dict(candidate_plans[0] if candidate_plans else bootstrap_plan)
            policy_decision = self.policy_guard.evaluate(
                run_context=run_context,
                planned_capability=planned_capability,
            )
            route = {
                "routing_mode": run_context.routing_mode,
                "selected_capability_id": str(planned_capability.get("capability_id") or "delegation.ausentismo.v1"),
                "execute_capability": True,
                "use_legacy": False,
                "shadow_enabled": True,
                "reason": "delegation_active_mode",
                "policy_action": policy_decision.action.value,
                "policy_allowed": policy_decision.allowed,
                "capability_exists": True,
                "rollout_enabled": True,
            }
            primary_response = delegated_response
            run_context.metadata["proactive_loop"] = {
                "enabled": False,
                "iterations_ran": 0,
                "max_iterations": 0,
                "selected_capability_id": planned_capability.get("capability_id"),
                "used_legacy": False,
                "iterations": [],
            }
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
        classification = self._extract_classification(primary_response)

        divergence = self.bridge.compare(
            classification=classification,
            planned_capability=planned_capability,
        )

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
        execution_meta = dict((execution or {}) if "execution" in locals() else {})
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

        return self.response_assembler.assemble(
            legacy_response=primary_response,
            run_context=run_context,
            planned_capability=planned_capability,
            route=route,
            policy_decision=policy_decision,
            divergence=divergence,
            memory_effects=memory_effects,
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
            capability_hints: list[dict[str, Any]] = []
            try:
                if hasattr(self.bridge, "resolve_candidates"):
                    capability_hints = list(
                        self.bridge.resolve_candidates(
                            message=message,
                            classification=classification_for_qi,
                            max_candidates=4,
                        )
                        or []
                    )
                elif hasattr(self.bridge, "resolve"):
                    hint = self.bridge.resolve(
                        message=message,
                        classification=classification_for_qi,
                    )
                    if isinstance(hint, dict) and hint:
                        capability_hints = [hint]
            except Exception:
                capability_hints = []

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
            )
            precomputed_response: dict[str, Any] = {}
            execution_result: dict[str, Any] | None = None
            if mode == "active":
                if execution_plan.strategy == "ask_context":
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
                            precomputed_response = candidate_response
                        else:
                            execution_result["validation"] = validation.as_dict()

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

    def _apply_legacy_bridge_canonical_alignment(
        self,
        *,
        message: str,
        classification: dict[str, Any],
        query_intelligence: dict[str, Any],
        run_context: RunContext,
        observability,
    ) -> dict[str, Any]:
        base = dict(classification or {})
        active_enabled = self._legacy_bridge_alignment_enabled()
        shadow_enabled = self._legacy_bridge_alignment_shadow_enabled()
        if not (active_enabled or shadow_enabled):
            return base

        target = self._build_legacy_bridge_alignment_target(
            message=message,
            query_intelligence=query_intelligence,
            threshold=self._legacy_bridge_alignment_confidence_threshold(),
        )
        legacy_domain = normalizar_codigo_dominio(base.get("domain"))
        legacy_intent = str(base.get("intent") or "").strip().lower()
        aligned_domain = normalizar_codigo_dominio(target.get("domain_code"))
        aligned_intent = str(target.get("intent_code") or "").strip().lower()
        aligned_capability = str(target.get("capability_code") or "").strip()
        confidence = float(target.get("confidence") or 0.0)
        target_safe = bool(target.get("safe"))
        bridge_hint_enabled = bool(active_enabled and target_safe)
        apply_alignment = bool(
            bridge_hint_enabled
            and aligned_domain not in {"", "general", "legacy"}
            and legacy_domain in {"", "general", "legacy"}
        )

        updated = dict(base)
        if apply_alignment:
            updated["domain"] = aligned_domain
            updated["intent"] = self._canonical_intent_to_legacy_intent(
                domain=aligned_domain,
                operation=aligned_intent,
            )
            updated["needs_database"] = aligned_domain not in {"", "general", "legacy"}
            updated["selected_agent"] = agente_desde_dominio(
                aligned_domain,
                fallback=str(updated.get("selected_agent") or "analista_agent"),
            )
            updated["classifier_source"] = "legacy_bridge_alignment_canonical"

        updated["canonical_alignment"] = {
            "active": bool(active_enabled),
            "shadow": bool(shadow_enabled and not active_enabled),
            "safe": bool(bridge_hint_enabled),
            "domain_hint": aligned_domain,
            "intent_hint": aligned_intent,
            "capability_hint": aligned_capability if bridge_hint_enabled else "",
            "source": str(target.get("source") or ""),
            "confidence": confidence,
            "alias_matches": list(target.get("alias_matches") or []),
            "critical_conflicts": list(target.get("critical_conflicts") or []),
        }

        summary = {
            "active": bool(active_enabled),
            "shadow": bool(shadow_enabled and not active_enabled),
            "applied": bool(apply_alignment),
            "would_apply": bool((not active_enabled) and target_safe and aligned_domain not in {"", "general", "legacy"}),
            "bridge_hint_applied": bool(bridge_hint_enabled),
            "would_apply_bridge_hint": bool((not active_enabled) and target_safe),
            "source": str(target.get("source") or ""),
            "confidence": confidence,
            "legacy_domain": legacy_domain,
            "legacy_intent": legacy_intent,
            "aligned_domain": aligned_domain,
            "aligned_intent": aligned_intent,
            "aligned_capability": aligned_capability,
            "alias_matches": list(target.get("alias_matches") or []),
            "critical_conflicts": list(target.get("critical_conflicts") or []),
            "safety_reason": str(target.get("safety_reason") or ""),
        }
        run_context.metadata["legacy_bridge_alignment"] = summary
        query_intelligence["legacy_bridge_alignment"] = summary
        query_intelligence_meta = dict(run_context.metadata.get("query_intelligence") or {})
        query_intelligence_meta["legacy_bridge_alignment"] = summary
        run_context.metadata["query_intelligence"] = query_intelligence_meta

        self._record_event(
            observability=observability,
            event_type="legacy_bridge_canonical_alignment",
            source="ChatApplicationService",
            meta={
                "run_id": run_context.run_id,
                "trace_id": run_context.trace_id,
                **summary,
            },
            only_if=True,
        )
        return updated

    def _build_legacy_bridge_alignment_target(
        self,
        *,
        message: str,
        query_intelligence: dict[str, Any],
        threshold: float,
    ) -> dict[str, Any]:
        normalized_message = self._normalize_text(message)
        aliases = self._resolve_legacy_alignment_alias_matches(
            normalized_message=normalized_message,
            query_intelligence=query_intelligence,
        )
        canonical = dict(query_intelligence.get("canonical_resolution") or {})
        canonical_domain = str(canonical.get("domain_code") or "").strip().lower()
        canonical_intent = str(canonical.get("intent_code") or "").strip().lower()
        canonical_confidence = float(canonical.get("confidence") or 0.0)
        canonical_conflicts = [
            dict(item)
            for item in list(canonical.get("conflicts") or [])
            if isinstance(item, dict)
        ]
        critical_conflicts = self._canonical_critical_conflicts(conflicts=canonical_conflicts)
        canonical_capability = str(canonical.get("capability_code") or "").strip()
        if not canonical_capability and canonical_domain:
            canonical_capability = self._canonical_default_capability(
                canonical_domain=canonical_domain,
                canonical_intent=canonical_intent,
            )
        if canonical_capability and not self.catalog.get(canonical_capability):
            canonical_capability = ""
        canonical_safe = bool(
            canonical_domain not in {"", "general", "legacy"}
            and canonical_confidence >= threshold
            and not critical_conflicts
        )
        if canonical_safe:
            return {
                "source": "canonical_resolution",
                "safe": True,
                "safety_reason": "safe",
                "domain_code": canonical_domain,
                "intent_code": canonical_intent,
                "capability_code": canonical_capability,
                "confidence": canonical_confidence,
                "alias_matches": aliases,
                "critical_conflicts": critical_conflicts,
            }

        semantic = dict(query_intelligence.get("semantic_normalization") or {})
        candidate_domains = [
            dict(item)
            for item in list(semantic.get("candidate_domains") or [])
            if isinstance(item, dict)
        ]
        candidate_intents = [
            dict(item)
            for item in list(semantic.get("candidate_intents") or [])
            if isinstance(item, dict)
        ]
        ambiguities = [
            dict(item)
            for item in list(semantic.get("ambiguities") or [])
            if isinstance(item, dict)
        ]
        semantic_domain = str((candidate_domains[0] if candidate_domains else {}).get("domain") or "").strip().lower()
        semantic_intent = str((candidate_intents[0] if candidate_intents else {}).get("intent") or "").strip().lower()
        semantic_confidence = float((candidate_domains[0] if candidate_domains else {}).get("confidence") or semantic.get("confidence") or 0.0)
        semantic_critical_conflicts = []
        if any(str((item or {}).get("type") or "") == "domain_close_scores" for item in ambiguities):
            semantic_critical_conflicts.append("domain_close_scores")
        semantic_capability = self._canonical_default_capability(
            canonical_domain=semantic_domain,
            canonical_intent=semantic_intent,
        )
        if semantic_capability and not self.catalog.get(semantic_capability):
            semantic_capability = ""
        semantic_safe = bool(
            semantic_domain not in {"", "general", "legacy"}
            and semantic_confidence >= threshold
            and not semantic_critical_conflicts
        )
        if semantic_safe:
            return {
                "source": "semantic_normalization",
                "safe": True,
                "safety_reason": "safe",
                "domain_code": semantic_domain,
                "intent_code": semantic_intent,
                "capability_code": semantic_capability,
                "confidence": semantic_confidence,
                "alias_matches": aliases,
                "critical_conflicts": semantic_critical_conflicts,
            }

        count_tokens = ("cantidad", "cuantos", "cuantas", "total", "numero")
        active_tokens = ("activo", "activos", "habilitado", "habilitados", "vigente", "vigentes")
        attendance_tokens = ("ausent", "asistenc", "injustific", "vacaciones")
        employee_alias_present = any(
            token in normalized_message
            for token in ("empleado", "empleados", "personal", "colaborador", "colaboradores")
        ) or any(str(item).startswith("empleados:") for item in aliases)
        supervisor_alias_present = any(
            token in normalized_message
            for token in ("supervisor", "jefe directo", "jefe", "lider")
        ) or any(str(item).startswith("supervisor:") for item in aliases)
        if employee_alias_present and any(token in normalized_message for token in count_tokens) and any(token in normalized_message for token in active_tokens):
            return {
                "source": "dictionary_alias_rules",
                "safe": True,
                "safety_reason": "safe_alias_match",
                "domain_code": "empleados",
                "intent_code": "count",
                "capability_code": "empleados.count.active.v1",
                "confidence": max(0.8, float(threshold)),
                "alias_matches": aliases,
                "critical_conflicts": [],
            }
        if supervisor_alias_present and any(token in normalized_message for token in attendance_tokens):
            return {
                "source": "dictionary_alias_rules",
                "safe": True,
                "safety_reason": "safe_alias_match",
                "domain_code": "ausentismo",
                "intent_code": "aggregate",
                "capability_code": "attendance.summary.by_supervisor.v1",
                "confidence": max(0.8, float(threshold)),
                "alias_matches": aliases,
                "critical_conflicts": [],
            }

        return {
            "source": "legacy_fallback",
            "safe": False,
            "safety_reason": "low_confidence_or_critical_conflicts",
            "domain_code": canonical_domain or semantic_domain,
            "intent_code": canonical_intent or semantic_intent,
            "capability_code": "",
            "confidence": max(canonical_confidence, semantic_confidence),
            "alias_matches": aliases,
            "critical_conflicts": critical_conflicts or semantic_critical_conflicts,
        }

    def _resolve_legacy_alignment_alias_matches(
        self,
        *,
        normalized_message: str,
        query_intelligence: dict[str, Any],
    ) -> list[str]:
        matches: list[str] = []
        alias_tokens = {
            "empleados": ("personal", "colaborador", "colaboradores", "empleado", "empleados"),
            "supervisor": ("jefe directo", "jefe", "supervisor"),
            "activo": ("habilitado", "habilitados", "vigente", "vigentes", "activo", "activos"),
        }
        for canonical_term, tokens in alias_tokens.items():
            for token in tokens:
                if token and token in normalized_message:
                    matches.append(f"{canonical_term}:{token}")

        resolved_query = dict(query_intelligence.get("resolved_query") or {})
        semantic_context = dict(resolved_query.get("semantic_context") or {})
        dictionary = dict(semantic_context.get("dictionary") or {})
        synonyms = [dict(item) for item in list(dictionary.get("synonyms") or []) if isinstance(item, dict)]
        for row in synonyms:
            term = self._normalize_text(str(row.get("termino") or ""))
            synonym = self._normalize_text(str(row.get("sinonimo") or ""))
            if term and term in normalized_message:
                matches.append(f"{term}:{term}")
            if synonym and synonym in normalized_message:
                matches.append(f"{term}:{synonym}")

        deduped: list[str] = []
        seen: set[str] = set()
        for item in matches:
            key = str(item or "").strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(key)
        return deduped

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
            canonical_classification = self._canonical_classification_for_routing(
                canonical_domain=canonical_domain,
                canonical_intent=canonical_intent,
                fallback_classification=classification,
            )
            try:
                bridge_candidate = self.bridge.resolve(
                    message=canonical_query,
                    classification=canonical_classification,
                )
            except Exception:
                bridge_candidate = {}
            candidate_capability = str((bridge_candidate or {}).get("capability_id") or "").strip()
            candidate_domain = self._capability_domain(candidate_capability)
            if (
                candidate_capability
                and self.catalog.get(candidate_capability)
                and (
                    canonical_domain in {"", "general", "legacy"}
                    or candidate_domain == canonical_domain
                    or candidate_domain not in {"general", "legacy", ""}
                )
            ):
                target_capability = candidate_capability
                source = "bridge_resolve_with_canonical_classification"
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
    def _canonical_classification_for_routing(
        *,
        canonical_domain: str,
        canonical_intent: str,
        fallback_classification: dict[str, Any],
    ) -> dict[str, Any]:
        domain = normalizar_codigo_dominio(canonical_domain) or normalizar_codigo_dominio(
            fallback_classification.get("domain") or "general"
        )
        operation = str(canonical_intent or "").strip().lower()
        intent = ChatApplicationService._canonical_intent_to_legacy_intent(
            domain=domain,
            operation=operation,
        )
        output_mode = "summary" if operation in {"count", "summary", "aggregate", "group", "compare"} else "table"
        if domain in {"general", "legacy", ""}:
            output_mode = "summary"
        return {
            "intent": intent,
            "domain": domain or "general",
            "selected_agent": agente_desde_dominio(
                domain,
                fallback=str(fallback_classification.get("selected_agent") or "analista_agent"),
            ),
            "classifier_source": "canonical_routing_classification",
            "needs_database": domain not in {"", "general", "legacy"},
            "output_mode": output_mode,
            "needs_personal_join": bool(fallback_classification.get("needs_personal_join")),
            "used_tools": list(fallback_classification.get("used_tools") or []),
            "dictionary_context": dict(fallback_classification.get("dictionary_context") or {}),
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
    ) -> dict[str, Any]:
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
    def _legacy_bridge_alignment_enabled() -> bool:
        return str(os.getenv("IA_DEV_LEGACY_BRIDGE_ALIGNMENT_ENABLED", "0") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    @staticmethod
    def _legacy_bridge_alignment_shadow_enabled() -> bool:
        return str(os.getenv("IA_DEV_LEGACY_BRIDGE_ALIGNMENT_SHADOW_ENABLED", "1") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    @staticmethod
    def _legacy_bridge_alignment_confidence_threshold() -> float:
        raw = str(os.getenv("IA_DEV_LEGACY_BRIDGE_ALIGNMENT_CONFIDENCE_THRESHOLD", "0.80") or "0.80").strip()
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
                r"\b(colaborador(?:es)?|personal|emplead\w*|cedula|rrhh|habilitad\w*|vigent\w*|tipo_labor|tipo\s+labor|tipo\s+de\s+labor|labor(?:es)?|area(?:s)?|cargo(?:s)?|supervisor(?:es)?|jefe(?:s)?|lider(?:es)?|carpeta(?:s)?|sede(?:s)?)\b",
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
        if hasattr(self.planner, "plan_candidates_from_legacy"):
            try:
                planned = self.planner.plan_candidates_from_legacy(
                    message=message,
                    classification=classification,
                    planning_context=planning_context,
                    max_candidates=max_candidates,
                )
            except TypeError:
                planned = self.planner.plan_candidates_from_legacy(
                    message=message,
                    classification=classification,
                )
            if planned:
                return [dict(item) for item in planned if isinstance(item, dict)]

        try:
            single = self.planner.plan_from_legacy(
                message=message,
                classification=classification,
                planning_context=planning_context,
            )
        except TypeError:
            single = self.planner.plan_from_legacy(
                message=message,
                classification=classification,
            )
        if isinstance(single, dict) and single:
            return [dict(single)]
        return [dict(fallback_plan)]

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
            candidates = [self.planner.plan_from_legacy(message=message, classification=self._bootstrap_classification(message=message))]
        query_intelligence_meta = dict(run_context.metadata.get("query_intelligence") or {})
        hydrated = self._hydrate_query_intelligence_contracts(metadata=query_intelligence_meta)
        resolved_query = hydrated.get("resolved_query")
        execution_plan = hydrated.get("execution_plan")

        loop_enabled = self._proactive_loop_enabled(run_context=run_context)
        max_iterations = self._proactive_loop_max_iterations()
        if not loop_enabled:
            max_iterations = 1
        loop_controller_enabled = self._loop_controller_enabled()
        loop_controller_shadow_enabled = self._loop_controller_shadow_enabled()

        visited_capabilities: set[str] = set()
        iteration_summaries: list[dict[str, Any]] = []
        loop_controller_history: list[dict[str, Any]] = []
        same_plan_retry_counts: dict[str, int] = {}
        replans_used = 0
        llm_review_passes = 0

        selected_plan = dict(candidates[0])
        selected_policy = self.policy_guard.evaluate(
            run_context=run_context,
            planned_capability=selected_plan,
        )
        selected_route = self.router.route(
            run_context=run_context,
            planned_capability=selected_plan,
            policy_decision=selected_policy,
        )
        selected_execution: dict[str, Any] | None = None

        iterations_ran = 0
        loop_stopped = False
        for idx, plan in enumerate(candidates):
            if iterations_ran >= max_iterations or loop_stopped:
                break
            capability_id = str(plan.get("capability_id") or "").strip()
            if capability_id and capability_id in visited_capabilities:
                continue
            if capability_id:
                visited_capabilities.add(capability_id)
            while True:
                if iterations_ran >= max_iterations:
                    break
                iterations_ran += 1

                policy_decision = self.policy_guard.evaluate(
                    run_context=run_context,
                    planned_capability=plan,
                )
                self._record_policy_decision_event(
                    observability=observability,
                    run_context=run_context,
                    planned_capability=plan,
                    policy_decision=policy_decision,
                    loop_iteration=iterations_ran,
                )
                route = self.router.route(
                    run_context=run_context,
                    planned_capability=plan,
                    policy_decision=policy_decision,
                )

                self._record_event(
                    observability=observability,
                    event_type="proactive_loop_iteration",
                    source="ChatApplicationService",
                    meta={
                        "run_id": run_context.run_id,
                        "trace_id": run_context.trace_id,
                        "session_id": run_context.session_id,
                        "iteration": iterations_ran,
                        "max_iterations": max_iterations,
                        "capability_id": plan.get("capability_id"),
                        "candidate_rank": plan.get("candidate_rank"),
                        "route_reason": route.get("reason"),
                        "policy_action": policy_decision.action.value,
                    },
                    only_if=loop_enabled,
                )

                execution = self._execute_primary_path(
                    message=message,
                    session_id=session_id,
                    reset_memory=reset_memory,
                    run_context=run_context,
                    planned_capability=plan,
                    route=route,
                    legacy_runner=legacy_runner,
                    observability=observability,
                    memory_context=memory_context,
                    resolved_query=resolved_query,
                    execution_plan=execution_plan,
                    allow_legacy_fallback=not loop_enabled,
                )
                satisfaction = self._evaluate_result_satisfaction(
                    message=message,
                    planned_capability=plan,
                    execution=execution,
                    resolved_query=resolved_query,
                    execution_plan=execution_plan,
                    run_context=run_context,
                    observability=observability,
                    loop_iteration=iterations_ran,
                    route=route,
                )
                gate_audit = dict(satisfaction.get("satisfaction_review_gate_audit") or {})
                execution["satisfied"] = bool(satisfaction.get("satisfied", True))
                execution["satisfaction_reason"] = str(satisfaction.get("reason") or "")

                loop_controller_decision_payload: dict[str, Any] = {}
                if loop_controller_enabled or loop_controller_shadow_enabled:
                    cycle_strategy = str((execution_plan.strategy if execution_plan else "") or "").strip()
                    if not cycle_strategy:
                        cycle_strategy = str((execution.get("meta") or {}).get("strategy") or "capability")
                    loop_decision = self.loop_controller.evaluate_cycle(
                        cycle_index=iterations_ran,
                        strategy=cycle_strategy,
                        planned_capability=plan,
                        route=route,
                        execution=execution,
                        satisfaction=satisfaction,
                        history=loop_controller_history,
                        same_plan_retries=int(same_plan_retry_counts.get(capability_id, 0)),
                        replans_used=int(replans_used),
                        llm_review_passes=int(llm_review_passes),
                    )
                    loop_controller_decision_payload = (
                        loop_decision.as_dict()
                        if hasattr(loop_decision, "as_dict")
                        else dict(loop_decision or {})
                    )
                    loop_controller_history.append(loop_controller_decision_payload)
                    self._record_event(
                        observability=observability,
                        event_type="loop_controller_cycle_evaluated",
                        source="ChatApplicationService",
                        meta={
                            "run_id": run_context.run_id,
                            "trace_id": run_context.trace_id,
                            "cycle_index": int(iterations_ran),
                            "strategy": str(loop_controller_decision_payload.get("strategy") or cycle_strategy),
                            "satisfaction_score": float(loop_controller_decision_payload.get("satisfaction_score") or 0.0),
                            "gate_status": str(loop_controller_decision_payload.get("gate_status") or ""),
                            "decision": str(loop_controller_decision_payload.get("decision") or ""),
                            "stop_reason": str(loop_controller_decision_payload.get("stop_reason") or ""),
                            "retry_reason": str(loop_controller_decision_payload.get("retry_reason") or ""),
                            "next_action": str(loop_controller_decision_payload.get("next_action") or ""),
                        },
                        only_if=True,
                    )

                iteration_summary = {
                    "iteration": iterations_ran,
                    "capability_id": str(plan.get("capability_id") or ""),
                    "route_reason": str(route.get("reason") or ""),
                    "policy_action": policy_decision.action.value,
                    "ok": bool(execution.get("ok")),
                    "satisfied": bool(execution.get("satisfied", True)),
                    "satisfaction_reason": str(execution.get("satisfaction_reason") or ""),
                    "used_legacy": bool(execution.get("used_legacy")),
                    "fallback_reason": execution.get("fallback_reason"),
                    "loop_controller_decision": str(loop_controller_decision_payload.get("decision") or ""),
                    "loop_controller_stop_reason": str(loop_controller_decision_payload.get("stop_reason") or ""),
                    "loop_controller_retry_reason": str(loop_controller_decision_payload.get("retry_reason") or ""),
                    "loop_controller_next_action": str(loop_controller_decision_payload.get("next_action") or ""),
                    "loop_controller_score": float(loop_controller_decision_payload.get("satisfaction_score") or 0.0),
                    "satisfaction_gate_approved": bool(gate_audit.get("approved")),
                    "satisfaction_gate_score": float(gate_audit.get("satisfaction_score") or 0.0),
                    "satisfaction_gate_next_action": str(gate_audit.get("next_action") or ""),
                    "satisfaction_gate_issues_count": int(gate_audit.get("issues_count") or 0),
                    "satisfaction_gate_retry_reason": str(gate_audit.get("retry_reason") or ""),
                }
                iteration_summaries.append(iteration_summary)

                selected_plan = dict(plan)
                selected_policy = policy_decision
                selected_route = dict(route)
                selected_execution = dict(execution or {})

                if loop_controller_enabled and loop_controller_decision_payload:
                    decision = str(loop_controller_decision_payload.get("decision") or "")
                    if decision == "retry_same_plan":
                        same_plan_retry_counts[capability_id] = int(same_plan_retry_counts.get(capability_id, 0)) + 1
                        execution["satisfied"] = False
                        execution["satisfaction_reason"] = str(
                            loop_controller_decision_payload.get("retry_reason")
                            or execution.get("satisfaction_reason")
                            or "retry_same_plan"
                        )
                        self._record_event(
                            observability=observability,
                            event_type="proactive_loop_unsatisfied_result",
                            source="ChatApplicationService",
                            meta={
                                "run_id": run_context.run_id,
                                "trace_id": run_context.trace_id,
                                "iteration": iterations_ran,
                                "capability_id": plan.get("capability_id"),
                                "reason": execution.get("satisfaction_reason"),
                            },
                            only_if=loop_enabled,
                        )
                        continue
                    if decision == "replan":
                        replans_used += 1
                        break
                    if decision in {"ask_user", "escalate_human", "stop"}:
                        execution["satisfied"] = False
                        execution["satisfaction_reason"] = str(
                            loop_controller_decision_payload.get("stop_reason")
                            or loop_controller_decision_payload.get("retry_reason")
                            or decision
                        )
                        self._record_event(
                            observability=observability,
                            event_type="proactive_loop_stop",
                            source="ChatApplicationService",
                            meta={
                                "run_id": run_context.run_id,
                                "trace_id": run_context.trace_id,
                                "stop_reason": execution.get("satisfaction_reason"),
                                "iteration": iterations_ran,
                                "capability_id": plan.get("capability_id"),
                            },
                            only_if=loop_enabled,
                        )
                        loop_stopped = True
                        break
                    if decision == "approved":
                        self._record_event(
                            observability=observability,
                            event_type="proactive_loop_stop",
                            source="ChatApplicationService",
                            meta={
                                "run_id": run_context.run_id,
                                "trace_id": run_context.trace_id,
                                "stop_reason": "loop_controller_approved",
                                "iteration": iterations_ran,
                                "capability_id": plan.get("capability_id"),
                            },
                            only_if=loop_enabled,
                        )
                        loop_stopped = True
                        break

                if bool(execution.get("ok")) and bool(execution.get("satisfied", True)):
                    self._record_event(
                        observability=observability,
                        event_type="proactive_loop_stop",
                        source="ChatApplicationService",
                        meta={
                            "run_id": run_context.run_id,
                            "trace_id": run_context.trace_id,
                            "stop_reason": "capability_executed_and_satisfied",
                            "iteration": iterations_ran,
                            "capability_id": plan.get("capability_id"),
                        },
                        only_if=loop_enabled,
                    )
                    loop_stopped = True
                    break
                if bool(execution.get("ok")) and not bool(execution.get("satisfied", True)):
                    self._record_event(
                        observability=observability,
                        event_type="proactive_loop_unsatisfied_result",
                        source="ChatApplicationService",
                        meta={
                            "run_id": run_context.run_id,
                            "trace_id": run_context.trace_id,
                            "iteration": iterations_ran,
                            "capability_id": plan.get("capability_id"),
                            "reason": execution.get("satisfaction_reason"),
                        },
                        only_if=loop_enabled,
                    )
                break
            if loop_stopped:
                break

        if selected_execution is None:
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

        if loop_enabled and not bool(selected_execution.get("ok")):
            fallback_constraints = dict((execution_plan.constraints if execution_plan else {}) or {})
            fallback_filters = dict(fallback_constraints.get("filters") or {})
            forced_attendance_reason_capability = (
                str(selected_plan.get("capability_id") or "").startswith("attendance.")
                and bool(
                    str(fallback_filters.get("justificacion") or "").strip()
                    or str(fallback_filters.get("motivo_justificacion") or "").strip()
                )
            )
            legacy_route = dict(selected_route or {})
            if forced_attendance_reason_capability:
                legacy_route["execute_capability"] = True
                legacy_route["use_legacy"] = False
                legacy_route["reason"] = "forced_attendance_reason_capability_fallback"
            else:
                # Safe fallback to legacy with first candidate context.
                legacy_route["execute_capability"] = False
                legacy_route["use_legacy"] = True
                legacy_route["reason"] = "proactive_loop_exhausted_all_candidates"
            selected_execution = self._execute_primary_path(
                message=message,
                session_id=session_id,
                reset_memory=reset_memory,
                run_context=run_context,
                planned_capability=selected_plan,
                route=legacy_route,
                legacy_runner=legacy_runner,
                observability=observability,
                memory_context=memory_context,
                resolved_query=resolved_query,
                execution_plan=execution_plan,
                allow_legacy_fallback=True,
            )
            selected_route = legacy_route
            self._record_event(
                observability=observability,
                event_type="proactive_loop_fallback_legacy",
                source="ChatApplicationService",
                meta={
                    "run_id": run_context.run_id,
                    "trace_id": run_context.trace_id,
                    "iterations": iterations_ran,
                    "capability_id": selected_plan.get("capability_id"),
                    "route_reason": selected_route.get("reason"),
                },
            )

        run_context.metadata["proactive_loop"] = {
            "enabled": loop_enabled,
            "iterations_ran": iterations_ran,
            "max_iterations": max_iterations,
            "selected_capability_id": selected_plan.get("capability_id"),
            "used_legacy": bool(selected_execution.get("used_legacy")),
            "satisfied": bool(selected_execution.get("satisfied", True)),
            "satisfaction_reason": str(selected_execution.get("satisfaction_reason") or ""),
            "iterations": iteration_summaries,
        }
        run_context.metadata["loop_controller"] = {
            "active": bool(loop_controller_enabled),
            "shadow": bool(loop_controller_shadow_enabled and not loop_controller_enabled),
            "cycles_evaluated": len(loop_controller_history),
            "same_plan_retries": dict(same_plan_retry_counts or {}),
            "replans_used": int(replans_used),
            "llm_review_passes": int(llm_review_passes),
            "history": loop_controller_history,
        }

        return {
            "response": dict(selected_execution.get("response") or {}),
            "planned_capability": selected_plan,
            "policy_decision": selected_policy,
            "route": selected_route,
            "execution_meta": selected_execution,
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
            capability_result = self.router.execute(
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
        if (
            last_domain == "ausentismo"
            and last_needs_db
            and ChatApplicationService._is_chart_request(normalized)
        ):
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
        if any(token in normalized for token in ("ausent", "asistenc", "injustificad")):
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
        if any(token in normalized for token in ("regla", "propuesta", "knowledge", "gobernanza")):
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
        if run_context.routing_mode == "intent":
            return
        if observability is None or not hasattr(observability, "record_event"):
            return
        try:
            observability.record_event(
                event_type="capability_shadow_divergence",
                source="ChatApplicationService",
                meta={
                    "run_id": run_context.run_id,
                    "trace_id": run_context.trace_id,
                    "routing_mode": run_context.routing_mode,
                    "legacy_intent": classification.get("intent"),
                    "legacy_domain": classification.get("domain"),
                    "planned_capability_id": planned_capability.get("capability_id"),
                    "planned_reason": planned_capability.get("reason"),
                    "route_reason": route.get("reason"),
                    "execute_capability": bool(route.get("execute_capability")),
                    "diverged": bool(divergence.get("diverged")),
                    "divergence_reason": divergence.get("reason"),
                },
            )
        except Exception:
            logger.exception("No se pudo registrar observabilidad de capability shadow")
