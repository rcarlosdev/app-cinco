from __future__ import annotations

import os
import re
import time
from typing import Any

from django.db import connections

from apps.ia_dev.application.context.run_context import RunContext
from apps.ia_dev.application.delegation.domain_registry import DomainRegistry
from apps.ia_dev.application.delegation.task_aggregator import TaskAggregator
from apps.ia_dev.application.delegation.task_contracts import DelegationResult, DelegationTask
from apps.ia_dev.application.delegation.task_planner import TaskPlanner
from apps.ia_dev.application.policies.policy_guard import PolicyAction, PolicyGuard
from apps.ia_dev.domains.ausentismo.handler_delegacion import AusentismoDelegacionHandler
from apps.ia_dev.domains.empleados.handler import EmpleadosHandler


class DelegationCoordinator:
    def __init__(
        self,
        *,
        registry: DomainRegistry | None = None,
        planner: TaskPlanner | None = None,
        aggregator: TaskAggregator | None = None,
        policy_guard: PolicyGuard | None = None,
        ausentismo_handler: AusentismoDelegacionHandler | None = None,
        empleados_handler: EmpleadosHandler | None = None,
    ):
        self.registry = registry or DomainRegistry()
        self.planner = planner or TaskPlanner(domain_registry=self.registry)
        self.aggregator = aggregator or TaskAggregator()
        self.policy_guard = policy_guard or PolicyGuard()
        self.ausentismo_handler = ausentismo_handler or AusentismoDelegacionHandler()
        self.empleados_handler = empleados_handler or EmpleadosHandler()

    @staticmethod
    def _flag_enabled(name: str, default: str = "0") -> bool:
        raw = str(os.getenv(name, default) or "").strip().lower()
        return raw in {"1", "true", "yes", "on"}

    @classmethod
    def resolve_mode(cls) -> str:
        enabled = cls._flag_enabled("IA_DEV_DELEGATION_ENABLED", "0")
        if not enabled:
            return "off"
        raw_mode = str(os.getenv("IA_DEV_DELEGATION_MODE", "shadow") or "shadow").strip().lower()
        if raw_mode not in {"off", "shadow", "active"}:
            return "shadow"
        return raw_mode

    @staticmethod
    def _sql_assisted_enabled() -> bool:
        raw = str(os.getenv("IA_DEV_SQL_ASSISTED_ENABLED", "0") or "").strip().lower()
        return raw in {"1", "true", "yes", "on"}

    def plan_and_maybe_execute(
        self,
        *,
        message: str,
        classification: dict[str, Any],
        planned_candidates: list[dict[str, Any]],
        run_context: RunContext,
        observability=None,
    ) -> dict[str, Any]:
        mode = self.resolve_mode()
        enable_sync = self._flag_enabled("IA_DEV_DOMAIN_REGISTRY_SYNC_ENABLED", "0")
        if mode == "off":
            return {
                "mode": mode,
                "should_delegate": False,
                "plan_reason": "delegation_disabled",
                "tasks": [],
                "executed": False,
                "response": None,
            }

        try:
            if enable_sync:
                sync_result = self.registry.sync_from_ai_dictionary()
                self._record_event(
                    observability=observability,
                    event_type="domain_registry_sync",
                    source="DelegationCoordinator",
                    meta={
                        "run_id": run_context.run_id,
                        "trace_id": run_context.trace_id,
                        "sync_result": dict(sync_result or {}),
                    },
                )
            self.registry.reload()
        except Exception:
            pass

        planning = self.planner.plan_tasks(
            message=message,
            classification=classification,
            planned_candidates=planned_candidates,
            run_id=run_context.run_id,
            trace_id=run_context.trace_id,
        )
        tasks = list(planning.get("tasks") or [])
        self._enrich_tasks_with_empleados_scope(message=message, tasks=tasks, observability=observability)
        self._record_plan_events(
            observability=observability,
            run_context=run_context,
            mode=mode,
            planning=planning,
            tasks=tasks,
        )

        if mode == "shadow":
            return {
                "mode": mode,
                "should_delegate": bool(planning.get("should_delegate")),
                "plan_reason": str(planning.get("reason") or ""),
                "selected_domains": list(planning.get("selected_domains") or []),
                "tasks": [item.as_dict() for item in tasks],
                "executed": False,
                "response": None,
                "warnings": list(planning.get("warnings") or []),
            }

        if not bool(planning.get("should_delegate")) or not tasks:
            return {
                "mode": mode,
                "should_delegate": False,
                "plan_reason": str(planning.get("reason") or "empty_plan"),
                "selected_domains": list(planning.get("selected_domains") or []),
                "tasks": [item.as_dict() for item in tasks],
                "executed": False,
                "response": None,
                "warnings": list(planning.get("warnings") or []),
            }

        results = self._execute_tasks(
            tasks=tasks,
            run_context=run_context,
            observability=observability,
        )
        self._apply_onboarding_workflow(
            run_context=run_context,
            selected_domains=list(planning.get("selected_domains") or []),
            results=results,
            observability=observability,
        )
        aggregated = self.aggregator.aggregate_results(tasks=tasks, results=results)
        response_payload = aggregated.as_payload()
        planning_warnings = list(planning.get("warnings") or [])
        result_warnings = self._extract_result_warnings(results=results)
        all_warnings = planning_warnings + result_warnings
        if all_warnings:
            response_payload.setdefault("data", {})
            response_payload["data"].setdefault("insights", [])
            response_payload["data"]["insights"].extend(all_warnings)
        response_payload.setdefault("orchestrator", {})
        response_payload["orchestrator"]["delegation"] = {
            "mode": mode,
            "plan_reason": str(planning.get("reason") or ""),
            "is_multi_domain": bool(planning.get("is_multi_domain")),
            "task_count": len(tasks),
            "result_count": len(results),
            "selected_domains": list(planning.get("selected_domains") or []),
            "tasks": [item.as_dict() for item in tasks],
            "results": [item.as_dict() for item in results],
            "warnings": all_warnings,
        }
        return {
            "mode": mode,
            "should_delegate": True,
            "plan_reason": str(planning.get("reason") or ""),
            "selected_domains": list(planning.get("selected_domains") or []),
            "tasks": [item.as_dict() for item in tasks],
            "executed": True,
            "response": response_payload,
            "results": [item.as_dict() for item in results],
            "warnings": all_warnings,
        }

    def _execute_tasks(
        self,
        *,
        tasks: list[DelegationTask],
        run_context: RunContext,
        observability=None,
    ) -> list[DelegationResult]:
        results: list[DelegationResult] = []
        pending = sorted(tasks, key=lambda item: int(item.priority), reverse=True)
        completed_ids: set[str] = set()
        task_result_map: dict[str, DelegationResult] = {}
        wait_counts: dict[str, int] = {}
        max_cycles = max(1, len(pending) * 2)
        cycles = 0
        while pending and cycles < max_cycles:
            cycles += 1
            task = pending.pop(0)
            unmet_deps = [item for item in list(task.depends_on or []) if item not in completed_ids]
            if unmet_deps:
                task_waits = int(wait_counts.get(task.task_id) or 0) + 1
                wait_counts[task.task_id] = task_waits
                if task_waits > len(tasks):
                    results.append(
                        DelegationResult(
                            task_id=task.task_id,
                            domain_code=task.domain_code,
                            status="error",
                            error_code=f"unresolved_dependencies:{','.join(unmet_deps)}",
                        )
                    )
                    completed_ids.add(task.task_id)
                    self._record_task_event(
                        observability=observability,
                        run_context=run_context,
                        task=task,
                        status="error",
                        meta={"reason": f"unresolved_dependencies:{','.join(unmet_deps)}"},
                    )
                    continue
                pending.append(task)
                continue

            self._record_task_event(
                observability=observability,
                run_context=run_context,
                task=task,
                status="start",
            )
            policy_decision = self.policy_guard.evaluate(
                run_context=run_context,
                planned_capability={
                    "capability_id": task.capability_id or "",
                    "source": {
                        "needs_database": True,
                        "domain": task.domain_code,
                    },
                    "policy_tags": ["contains_operational_data"],
                },
            )
            if policy_decision.action != PolicyAction.ALLOW:
                denied = DelegationResult(
                    task_id=task.task_id,
                    domain_code=task.domain_code,
                    status="denied",
                    error_code=f"policy_{policy_decision.action.value}",
                    policy_decisions=[
                        {
                            "action": policy_decision.action.value,
                            "policy_id": policy_decision.policy_id,
                            "reason": policy_decision.reason,
                        }
                    ],
                )
                results.append(denied)
                completed_ids.add(task.task_id)
                task_result_map[task.task_id] = denied
                self._record_task_event(
                    observability=observability,
                    run_context=run_context,
                    task=task,
                    status="fallback",
                    meta={"reason": denied.error_code},
                )
                continue

            if task.execution_strategy == "sql_assisted_read_only":
                sql_result = self._execute_sql_asistido_restringido(
                    task=task,
                    run_context=run_context,
                    observability=observability,
                )
                results.append(sql_result)
                completed_ids.add(task.task_id)
                task_result_map[task.task_id] = sql_result
                self._record_task_event(
                    observability=observability,
                    run_context=run_context,
                    task=task,
                    status="success" if sql_result.status == "ok" else "fallback",
                    meta={"reason": sql_result.error_code},
                )
                continue

            self._inject_dependency_context(
                task=task,
                task_result_map=task_result_map,
            )

            if task.domain_code == "ausentismo":
                outcome = self.ausentismo_handler.resolver_subtarea(
                    task=task,
                    observability=observability,
                )
                results.append(outcome)
                completed_ids.add(task.task_id)
                task_result_map[task.task_id] = outcome
                self._record_task_event(
                    observability=observability,
                    run_context=run_context,
                    task=task,
                    status="success" if outcome.status in {"ok", "partial"} else "error",
                    meta={"result_status": outcome.status, "error_code": outcome.error_code},
                )
                continue

            if task.domain_code == "empleados":
                outcome = self.empleados_handler.resolver_subtarea(
                    task=task,
                    observability=observability,
                )
                results.append(outcome)
                completed_ids.add(task.task_id)
                task_result_map[task.task_id] = outcome
                self._record_task_event(
                    observability=observability,
                    run_context=run_context,
                    task=task,
                    status="success" if outcome.status in {"ok", "partial"} else "error",
                    meta={"result_status": outcome.status, "error_code": outcome.error_code},
                )
                continue

            unsupported = DelegationResult(
                task_id=task.task_id,
                domain_code=task.domain_code,
                status="partial",
                error_code=f"domain_handler_not_implemented:{task.domain_code}",
            )
            results.append(unsupported)
            completed_ids.add(task.task_id)
            task_result_map[task.task_id] = unsupported
            self._record_task_event(
                observability=observability,
                run_context=run_context,
                task=task,
                status="fallback",
                meta={"reason": unsupported.error_code},
            )
        if pending:
            for task in pending:
                if task.task_id in completed_ids:
                    continue
                timed_out = DelegationResult(
                    task_id=task.task_id,
                    domain_code=task.domain_code,
                    status="error",
                    error_code="delegation_execution_timeout",
                )
                results.append(timed_out)
                completed_ids.add(task.task_id)
                task_result_map[task.task_id] = timed_out
                self._record_task_event(
                    observability=observability,
                    run_context=run_context,
                    task=task,
                    status="error",
                    meta={"reason": timed_out.error_code},
                )
        return results

    def _enrich_tasks_with_empleados_scope(self, *, message: str, tasks: list[DelegationTask], observability=None) -> None:
        if not tasks:
            return
        if not any(token in str(message or "").lower() for token in ("empleado", "supervisor", "area", "cargo", "carpeta")):
            return
        scope = self.empleados_handler.resolver_entidad_objetivo(consulta=message, limite=200)
        entity_ids = list(scope.get("entity_ids") or [])
        if not entity_ids:
            return
        for task in tasks:
            if task.domain_code != "ausentismo":
                continue
            task.entity_scope.entity_ids = list(entity_ids)
            task.entity_scope.entity_attributes = {
                **dict(task.entity_scope.entity_attributes or {}),
                "resolucion_empleados": {
                    "entity_type": scope.get("entity_type"),
                    "total_empleados": int((scope.get("entity_attributes") or {}).get("total_empleados") or len(entity_ids)),
                    "filtros_normalizados": dict((scope.get("entity_attributes") or {}).get("filtros_normalizados") or {}),
                },
            }
        self._record_event(
            observability=observability,
            event_type="delegation_scope_enriched_with_empleados",
            source="DelegationCoordinator",
            meta={
                "entity_type": scope.get("entity_type"),
                "entity_ids_count": len(entity_ids),
            },
        )

    @staticmethod
    def _record_plan_events(
        *,
        observability,
        run_context: RunContext,
        mode: str,
        planning: dict[str, Any],
        tasks: list[DelegationTask],
    ) -> None:
        if observability is None or not hasattr(observability, "record_event"):
            return
        observability.record_event(
            event_type="delegation_plan_generated",
            source="DelegationCoordinator",
            meta={
                "run_id": run_context.run_id,
                "trace_id": run_context.trace_id,
                "mode": mode,
                "should_delegate": bool(planning.get("should_delegate")),
                "plan_reason": str(planning.get("reason") or ""),
                "selected_domains": list(planning.get("selected_domains") or []),
                "task_count": len(tasks),
            },
        )
        for task in tasks:
            observability.record_event(
                event_type="delegation_task_planned",
                source="DelegationCoordinator",
                meta={
                    "run_id": run_context.run_id,
                    "trace_id": run_context.trace_id,
                    "mode": mode,
                    "task": task.as_dict(),
                },
            )

    def _apply_onboarding_workflow(
        self,
        *,
        run_context: RunContext,
        selected_domains: list[dict[str, Any]],
        results: list[DelegationResult],
        observability=None,
    ) -> None:
        if not self._flag_enabled("IA_DEV_DOMAIN_ONBOARDING_WORKFLOW_ENABLED", "1"):
            return
        result_by_domain: dict[str, list[DelegationResult]] = {}
        for item in results:
            result_by_domain.setdefault(str(item.domain_code or "").strip().lower(), []).append(item)

        for domain_row in selected_domains:
            domain_code = str((domain_row or {}).get("domain_code") or "").strip().lower()
            domain_status = str((domain_row or {}).get("domain_status") or "").strip().lower()
            if not domain_code or domain_status not in {"planned", "partial"}:
                continue
            domain_results = list(result_by_domain.get(domain_code) or [])
            if not domain_results:
                continue
            statuses = {str(item.status or "").strip().lower() for item in domain_results}
            if domain_status == "planned" and statuses & {"ok", "partial"}:
                transition = self.registry.transition_domain_status(
                    domain_code=domain_code,
                    to_status="partial",
                    actor="delegation_coordinator",
                    reason="first_delegated_execution",
                    run_id=run_context.run_id,
                    trace_id=run_context.trace_id,
                )
                self._record_event(
                    observability=observability,
                    event_type="domain_onboarding_transition",
                    source="DelegationCoordinator",
                    meta={
                        "run_id": run_context.run_id,
                        "trace_id": run_context.trace_id,
                        "domain_code": domain_code,
                        "from_status": "planned",
                        "to_status": "partial",
                        "transition_result": transition,
                    },
                )
            elif domain_status == "partial" and statuses == {"ok"}:
                transition = self.registry.transition_domain_status(
                    domain_code=domain_code,
                    to_status="active",
                    actor="delegation_coordinator",
                    reason="stable_delegated_execution",
                    run_id=run_context.run_id,
                    trace_id=run_context.trace_id,
                )
                self._record_event(
                    observability=observability,
                    event_type="domain_onboarding_transition",
                    source="DelegationCoordinator",
                    meta={
                        "run_id": run_context.run_id,
                        "trace_id": run_context.trace_id,
                        "domain_code": domain_code,
                        "from_status": "partial",
                        "to_status": "active",
                        "transition_result": transition,
                    },
                )

    @staticmethod
    def _extract_result_warnings(*, results: list[DelegationResult]) -> list[str]:
        warnings: list[str] = []
        for item in results:
            if item.status in {"partial", "denied", "error"}:
                warning = (
                    f"Tarea {item.task_id} en dominio {item.domain_code} quedo en estado {item.status}"
                    + (f" ({item.error_code})" if item.error_code else "")
                )
                warnings.append(warning)
        return warnings

    def _execute_sql_asistido_restringido(
        self,
        *,
        task: DelegationTask,
        run_context: RunContext,
        observability=None,
    ) -> DelegationResult:
        if task.domain_status not in {"planned", "partial"}:
            return DelegationResult(
                task_id=task.task_id,
                domain_code=task.domain_code,
                status="denied",
                error_code="sql_assisted_only_for_planned_or_partial",
                insights=["SQL asistido restringido solo aplica para dominios planned/partial."],
            )
        if not self._sql_assisted_enabled():
            return DelegationResult(
                task_id=task.task_id,
                domain_code=task.domain_code,
                status="partial",
                error_code="sql_assisted_disabled_by_flag",
                insights=["SQL asistido restringido deshabilitado por feature flag."],
            )

        sql_query = str(task.constraints.get("generated_sql") or "").strip()
        if not sql_query:
            return DelegationResult(
                task_id=task.task_id,
                domain_code=task.domain_code,
                status="partial",
                error_code="sql_assisted_query_missing",
                insights=["No se recibio consulta SQL asistida para la subtarea."],
            )

        valid, reason = self._validate_sql_restringido(task=task, query=sql_query)
        if not valid:
            return DelegationResult(
                task_id=task.task_id,
                domain_code=task.domain_code,
                status="denied",
                error_code=reason,
                insights=["La consulta SQL asistida fue rechazada por guardrails de seguridad."],
            )

        started = time.perf_counter()
        db_alias = str(os.getenv("IA_DEV_DB_READONLY_ALIAS", os.getenv("IA_DEV_DB_ALIAS", "default")) or "default").strip()
        try:
            with connections[db_alias].cursor() as cursor:
                cursor.execute(sql_query)
                rows = cursor.fetchall()
                columns = [str(getattr(col, "name", col[0]) or "") for col in (cursor.description or [])]
            duration_ms = int((time.perf_counter() - started) * 1000)
            self._record_event(
                observability=observability,
                event_type="sql_assisted_query_executed",
                source="DelegationCoordinator",
                meta={
                    "run_id": run_context.run_id,
                    "trace_id": run_context.trace_id,
                    "task_id": task.task_id,
                    "domain_code": task.domain_code,
                    "db_alias": db_alias,
                    "duration_ms": duration_ms,
                    "rowcount": len(rows),
                    "origin": "delegation_sql_assisted_read_only",
                    "query": sql_query,
                },
            )
            rows_payload = [
                {columns[idx]: row[idx] for idx in range(len(columns))}
                for row in rows
            ]
            return DelegationResult(
                task_id=task.task_id,
                domain_code=task.domain_code,
                status="ok",
                reply_text="Consulta SQL asistida ejecutada en modo restringido.",
                table={
                    "columns": columns,
                    "rows": rows_payload,
                    "rowcount": len(rows_payload),
                },
                kpis={"rowcount": len(rows_payload)},
                insights=["Resultado exploratorio obtenido mediante SQL asistido restringido de solo lectura."],
            )
        except Exception as exc:
            self._record_event(
                observability=observability,
                event_type="sql_assisted_query_error",
                source="DelegationCoordinator",
                meta={
                    "run_id": run_context.run_id,
                    "trace_id": run_context.trace_id,
                    "task_id": task.task_id,
                    "domain_code": task.domain_code,
                    "origin": "delegation_sql_assisted_read_only",
                    "query": sql_query,
                    "error": str(exc),
                },
            )
            return DelegationResult(
                task_id=task.task_id,
                domain_code=task.domain_code,
                status="error",
                error_code=f"sql_assisted_execution_error:{exc}",
            )

    def _validate_sql_restringido(self, *, task: DelegationTask, query: str) -> tuple[bool, str]:
        normalized = re.sub(r"\s+", " ", str(query or "").strip(), flags=re.MULTILINE).strip().lower()
        if not normalized.startswith("select "):
            return False, "sql_must_start_with_select"
        forbidden = (" insert ", " update ", " delete ", " alter ", " drop ", " create ", " truncate ", " merge ")
        padded = f" {normalized} "
        if any(token in padded for token in forbidden):
            return False, "sql_contains_forbidden_operation"
        if " limit " not in padded:
            return False, "sql_limit_required"

        limit_match = re.search(r"\blimit\s+(\d+)\b", normalized)
        if not limit_match:
            return False, "sql_limit_invalid"
        limit_value = int(limit_match.group(1))
        max_limit = max(1, min(int(task.constraints.get("max_limit") or 500), 5000))
        if limit_value > max_limit:
            return False, "sql_limit_exceeds_max"

        domain = self.registry.get_domain(task.domain_code)
        if domain is None:
            return False, "sql_domain_not_registered"
        allowed_tables = []
        for table in list(domain.raw_context.get("tables") or []):
            if not isinstance(table, dict):
                continue
            table_name = str(table.get("table_name") or "").strip().lower()
            table_fqn = str(table.get("table_fqn") or "").strip().lower()
            if table_name:
                allowed_tables.append(table_name)
            if table_fqn:
                allowed_tables.append(table_fqn)
        if allowed_tables:
            if not any(f" {name} " in padded or f" {name}," in padded or f" {name}\n" in query.lower() for name in allowed_tables):
                return False, "sql_uses_unregistered_table"
        return True, "ok"

    def _inject_dependency_context(
        self,
        *,
        task: DelegationTask,
        task_result_map: dict[str, DelegationResult],
    ) -> None:
        if task.domain_code != "ausentismo":
            return
        for dep_id in list(task.depends_on or []):
            dep = task_result_map.get(dep_id)
            if dep is None:
                continue
            if dep.domain_code != "empleados":
                continue
            rows = list((dep.table or {}).get("rows") or [])
            entity_ids = [str(item.get("cedula") or "").strip() for item in rows if str(item.get("cedula") or "").strip()]
            if entity_ids:
                task.entity_scope.entity_ids = entity_ids
                task.entity_scope.entity_attributes = {
                    **dict(task.entity_scope.entity_attributes or {}),
                    "resolucion_empleados_task_id": dep.task_id,
                    "resolucion_empleados_total": len(entity_ids),
                }
                return

    def _record_task_event(
        self,
        *,
        observability,
        run_context: RunContext,
        task: DelegationTask,
        status: str,
        meta: dict[str, Any] | None = None,
    ) -> None:
        event_map = {
            "start": "delegation_task_start",
            "success": "delegation_task_success",
            "fallback": "delegation_task_fallback",
            "error": "delegation_task_error",
        }
        event_type = event_map.get(status, "delegation_task_event")
        self._record_event(
            observability=observability,
            event_type=event_type,
            source="DelegationCoordinator",
            meta={
                "run_id": run_context.run_id,
                "trace_id": run_context.trace_id,
                "task": task.as_dict(),
                "status": status,
                **dict(meta or {}),
            },
        )

    @staticmethod
    def _record_event(*, observability, event_type: str, source: str, meta: dict[str, Any]) -> None:
        if observability is None or not hasattr(observability, "record_event"):
            return
        observability.record_event(
            event_type=event_type,
            source=source,
            meta=dict(meta or {}),
        )
