from __future__ import annotations

import hashlib
import os
from typing import Any

from apps.ia_dev.application.context.run_context import RunContext
from apps.ia_dev.application.memory.memory_router import MemoryRouter


def _env_flag(name: str, default: str = "1") -> bool:
    value = os.getenv(name, default)
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _normalize(text: str | None) -> str:
    return str(text or "").strip().lower()


class ChatMemoryRuntimeService:
    def __init__(self, *, router: MemoryRouter | None = None):
        self.router = router or MemoryRouter()

    @staticmethod
    def flags() -> dict[str, bool]:
        return {
            "read_enabled": _env_flag("IA_DEV_MEMORY_READ_ENABLED", "1"),
            "write_enabled": _env_flag("IA_DEV_MEMORY_WRITE_ENABLED", "1"),
            "proposals_enabled": _env_flag("IA_DEV_MEMORY_PROPOSALS_ENABLED", "1"),
        }

    def load_context_for_chat(
        self,
        *,
        user_key: str | None,
        domain_code: str | None,
        capability_id: str | None,
        run_context: RunContext,
        observability=None,
    ) -> dict[str, Any]:
        flags = self.flags()
        decision = self.router.decide_for_chat(operation="read", flags=flags)
        if decision.action != "read":
            return {
                "flags": flags,
                "decision": {
                    "action": decision.action,
                    "reason": decision.reason,
                    "metadata": dict(decision.metadata),
                },
                "user_memory": [],
                "business_memory": [],
                "used": False,
            }

        user_memory: list[dict[str, Any]] = []
        if user_key:
            user_memory = self.router.reader.get_user_preferences(user_key=user_key, limit=30)

        business_memory = self.router.reader.get_business_hints(
            domain_code=(domain_code or "").strip().upper() or None,
            capability_id=(capability_id or "").strip() or None,
            limit=30,
        )
        business_memory = self._merge_memory_entries(
            base_entries=business_memory,
            extra_entries=self._load_business_query_patterns(
                domain_code=(domain_code or "").strip().upper() or None,
                capability_id=(capability_id or "").strip() or None,
            ),
            limit=45,
        )
        business_memory = self._merge_memory_entries(
            base_entries=business_memory,
            extra_entries=self._load_collective_reasoning_patterns(
                domain_code=(domain_code or "").strip().upper() or None,
                capability_id=(capability_id or "").strip() or None,
            ),
            limit=45,
        )
        used = bool(user_memory or business_memory)

        if used and observability is not None and hasattr(observability, "record_event"):
            observability.record_event(
                event_type="memory_used_in_chat",
                source="ChatMemoryRuntimeService",
                meta={
                    "run_id": run_context.run_id,
                    "trace_id": run_context.trace_id,
                    "session_id": run_context.session_id,
                    "user_key": user_key,
                    "domain_code": (domain_code or "").strip().upper() or None,
                    "capability_id": capability_id,
                    "user_memory_count": len(user_memory),
                    "business_memory_count": len(business_memory),
                },
            )

        return {
            "flags": flags,
            "decision": {
                "action": decision.action,
                "reason": decision.reason,
                "metadata": dict(decision.metadata),
            },
            "user_memory": user_memory,
            "business_memory": business_memory,
            "used": used,
        }

    def _load_business_query_patterns(
        self,
        *,
        domain_code: str | None,
        capability_id: str | None,
    ) -> list[dict[str, Any]]:
        scoped = self.router.reader.get_business_hints(
            domain_code=domain_code,
            capability_id=capability_id,
            memory_key_prefix="query.pattern.domain.",
            limit=20,
        )
        normalized_domain = str(domain_code or "").strip().upper()
        if normalized_domain and normalized_domain not in {"GENERAL", "LEGACY"}:
            return list(scoped or [])
        global_patterns = self.router.reader.get_business_hints(
            domain_code=None,
            capability_id=None,
            memory_key_prefix="query.pattern.domain.",
            limit=20,
        )
        return self._merge_memory_entries(base_entries=scoped, extra_entries=global_patterns, limit=20)

    def _load_collective_reasoning_patterns(
        self,
        *,
        domain_code: str | None,
        capability_id: str | None,
    ) -> list[dict[str, Any]]:
        scoped = self.router.reader.get_business_hints(
            domain_code=domain_code,
            capability_id=capability_id,
            memory_key_prefix="reasoning.pattern.",
            limit=20,
        )
        global_patterns = self.router.reader.get_business_hints(
            domain_code=None,
            capability_id=None,
            memory_key_prefix="reasoning.pattern.",
            limit=20,
        )
        return self._merge_memory_entries(base_entries=scoped, extra_entries=global_patterns, limit=20)

    @staticmethod
    def _merge_memory_entries(
        *,
        base_entries: list[dict[str, Any]] | None,
        extra_entries: list[dict[str, Any]] | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str, str]] = set()
        for row in list(base_entries or []) + list(extra_entries or []):
            if not isinstance(row, dict):
                continue
            fingerprint = (
                str(row.get("domain_code") or "").strip().upper(),
                str(row.get("capability_id") or "").strip(),
                str(row.get("memory_key") or "").strip().lower(),
                str(row.get("id") or "").strip(),
            )
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            merged.append(dict(row))
            if len(merged) >= max(1, int(limit)):
                break
        return merged

    def detect_candidates(
        self,
        *,
        message: str,
        classification: dict[str, Any],
        planned_capability: dict[str, Any],
        legacy_response: dict[str, Any],
        run_context: RunContext,
        user_key: str | None,
        observability=None,
    ) -> list[dict[str, Any]]:
        if not user_key:
            return []

        msg = _normalize(message)
        source = dict(planned_capability.get("source") or {})
        capability_id = str(planned_capability.get("capability_id") or "")
        domain = str(source.get("domain") or classification.get("domain") or "general").strip().lower()
        domain_code = domain.upper()
        output_mode = str(source.get("output_mode") or classification.get("output_mode") or "summary").strip().lower()
        used_tools = list(classification.get("used_tools") or [])
        data = dict((legacy_response or {}).get("data") or {})
        table = dict(data.get("table") or {})
        rowcount = int(table.get("rowcount") or 0)

        candidates: list[dict[str, Any]] = []

        if domain == "attendance":
            if any(token in msg for token in ("agrupado", "resumen", "agrupar")):
                candidates.append(
                    {
                        "scope": "user",
                        "candidate_key": "attendance.output_mode",
                        "candidate_value": {"value": "grouped"},
                        "reason": "preferencia detectada para salida agrupada",
                        "sensitivity": "low",
                        "domain_code": "ATTENDANCE",
                        "capability_id": capability_id,
                    }
                )
            elif any(token in msg for token in ("dia a dia", "detalle", "itemizado", "por fecha")):
                candidates.append(
                    {
                        "scope": "user",
                        "candidate_key": "attendance.output_mode",
                        "candidate_value": {"value": "itemized"},
                        "reason": "preferencia detectada para salida dia a dia",
                        "sensitivity": "low",
                        "domain_code": "ATTENDANCE",
                        "capability_id": capability_id,
                    }
                )
            elif output_mode in {"summary", "table"}:
                candidates.append(
                    {
                        "scope": "user",
                        "candidate_key": "attendance.output_mode",
                        "candidate_value": {"value": output_mode},
                        "reason": "preferencia inferida desde output_mode de la ejecucion",
                        "sensitivity": "low",
                        "domain_code": "ATTENDANCE",
                        "capability_id": capability_id,
                    }
                )

            if any(token in msg for token in ("activos", "solo activos")):
                candidates.append(
                    {
                        "scope": "user",
                        "candidate_key": "attendance.personal_status",
                        "candidate_value": {"value": "activos"},
                        "reason": "filtro de personal detectado en conversacion",
                        "sensitivity": "low",
                        "domain_code": "ATTENDANCE",
                        "capability_id": capability_id,
                    }
                )
            elif any(token in msg for token in ("inactivos", "solo inactivos")):
                candidates.append(
                    {
                        "scope": "user",
                        "candidate_key": "attendance.personal_status",
                        "candidate_value": {"value": "inactivos"},
                        "reason": "filtro de personal detectado en conversacion",
                        "sensitivity": "low",
                        "domain_code": "ATTENDANCE",
                        "capability_id": capability_id,
                    }
                )

            if (
                "get_attendance_recurrent_unjustified_with_supervisor" in used_tools
                and rowcount > 0
            ):
                candidates.append(
                    {
                        "scope": "business",
                        "candidate_key": "attendance.recurrence.default_view",
                        "candidate_value": {
                            "value": "grouped",
                            "evidence": {
                                "tool": "get_attendance_recurrent_unjustified_with_supervisor",
                                "rowcount": rowcount,
                            },
                        },
                        "reason": "patron reusable detectado para reincidencia en attendance",
                        "sensitivity": "medium",
                        "domain_code": "ATTENDANCE",
                        "capability_id": capability_id or "attendance.recurrence.grouped.v1",
                    }
                )

            if any(token in msg for token in ("grafica", "grafico", "chart", "linea", "barra", "barras")):
                chart_type = "bar"
                if "linea" in msg:
                    chart_type = "line"
                elif "area" in msg:
                    chart_type = "area"
                candidates.append(
                    {
                        "scope": "user",
                        "candidate_key": "attendance.analytics.chart_type",
                        "candidate_value": {"value": chart_type},
                        "reason": "preferencia de visualizacion detectada en conversacion",
                        "sensitivity": "low",
                        "domain_code": "ATTENDANCE",
                        "capability_id": capability_id or "attendance.trend.daily.v1",
                    }
                )

            if "top " in msg:
                for token in msg.split():
                    if token.isdigit():
                        top_n = max(1, min(int(token), 50))
                        candidates.append(
                            {
                                "scope": "user",
                                "candidate_key": "attendance.analytics.top_n",
                                "candidate_value": {"value": str(top_n)},
                                "reason": "preferencia top_n detectada en conversacion",
                                "sensitivity": "low",
                                "domain_code": "ATTENDANCE",
                                "capability_id": capability_id or "attendance.summary.by_supervisor.v1",
                            }
                        )
                        break
        elif domain == "transport":
            if any(token in msg for token in ("hoy", "hoy dia")):
                candidates.append(
                    {
                        "scope": "user",
                        "candidate_key": "transport.default_period_label",
                        "candidate_value": {"value": "hoy"},
                        "reason": "preferencia detectada para consultas de transporte en hoy",
                        "sensitivity": "low",
                        "domain_code": "TRANSPORT",
                        "capability_id": capability_id or "transport.departures.summary.v1",
                    }
                )
            elif any(token in msg for token in ("ayer", "dia anterior", "día anterior")):
                candidates.append(
                    {
                        "scope": "user",
                        "candidate_key": "transport.default_period_label",
                        "candidate_value": {"value": "ayer"},
                        "reason": "preferencia detectada para consultas de transporte en ayer",
                        "sensitivity": "low",
                        "domain_code": "TRANSPORT",
                        "capability_id": capability_id or "transport.departures.summary.v1",
                    }
                )

        if any(token in msg for token in ("para todos", "globalmente", "en toda la empresa")):
            candidates.append(
                {
                    "scope": "general",
                    "candidate_key": "general.response.style",
                    "candidate_value": {"value": "enterprise_concise"},
                    "reason": "solicitud explicita de preferencia global",
                    "sensitivity": "medium",
                    "domain_code": domain_code or "GENERAL",
                    "capability_id": capability_id or "general.answer.v1",
                }
            )

        deduped: list[dict[str, Any]] = []
        seen = set()
        for item in candidates:
            fingerprint = (
                str(item.get("scope") or ""),
                str(item.get("candidate_key") or ""),
                str(item.get("candidate_value") or ""),
            )
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            deduped.append(item)
            if observability is not None and hasattr(observability, "record_event"):
                observability.record_event(
                    event_type="memory_candidate_detected",
                    source="ChatMemoryRuntimeService",
                    meta={
                        "run_id": run_context.run_id,
                        "trace_id": run_context.trace_id,
                        "scope": item.get("scope"),
                        "candidate_key": item.get("candidate_key"),
                        "domain_code": item.get("domain_code"),
                        "capability_id": item.get("capability_id"),
                    },
                )
        return deduped

    def persist_candidates(
        self,
        *,
        user_key: str | None,
        candidates: list[dict[str, Any]],
        run_context: RunContext,
        observability=None,
    ) -> dict[str, Any]:
        if not user_key:
            return {
                "memory_candidates": [],
                "pending_proposals": [],
                "actions": [],
            }

        flags = self.flags()
        materialized_candidates: list[dict[str, Any]] = []
        pending_proposals: list[dict[str, Any]] = []

        for candidate in candidates:
            scope = str(candidate.get("scope") or "user").strip().lower()
            decision = self.router.decide_for_chat(
                operation="propose",
                scope=scope,
                flags=flags,
            )
            candidate_view = {
                "scope": scope,
                "candidate_key": candidate.get("candidate_key"),
                "candidate_value": candidate.get("candidate_value"),
                "reason": candidate.get("reason"),
                "sensitivity": candidate.get("sensitivity", "low"),
                "domain_code": candidate.get("domain_code"),
                "capability_id": candidate.get("capability_id"),
                "decision": decision.action,
                "decision_reason": decision.reason,
                "proposal_id": None,
            }
            if decision.action != "propose":
                materialized_candidates.append(candidate_view)
                continue

            hash_source = (
                f"{run_context.run_id}|{scope}|{candidate.get('candidate_key')}|"
                f"{candidate.get('candidate_value')}"
            )
            idempotency_key = "chatmem-" + hashlib.sha1(hash_source.encode("utf-8")).hexdigest()[:20]
            payload = {
                "scope": scope,
                "candidate_key": str(candidate.get("candidate_key") or "").strip(),
                "candidate_value": candidate.get("candidate_value"),
                "reason": str(candidate.get("reason") or "").strip(),
                "sensitivity": str(candidate.get("sensitivity") or "low").strip().lower(),
                "domain_code": candidate.get("domain_code"),
                "capability_id": candidate.get("capability_id"),
                "idempotency_key": idempotency_key,
                "direct_write": False,
            }
            result = self.router.propose_or_write(
                user_key=user_key,
                payload=payload,
                source_run_id=run_context.run_id,
            )
            proposal = dict(result.get("proposal") or {})
            proposal_id = str(proposal.get("proposal_id") or "").strip() or None
            candidate_view["proposal_id"] = proposal_id
            candidate_view["result_ok"] = bool(result.get("ok"))
            candidate_view["idempotent"] = bool(result.get("idempotent"))
            candidate_view["auto_applied"] = bool(result.get("auto_applied"))
            if not result.get("ok"):
                candidate_view["error"] = str(result.get("error") or "unknown_error")
            materialized_candidates.append(candidate_view)

            if result.get("ok") and proposal_id and str(proposal.get("status") or "") in {
                "pending",
                "approved",
            }:
                pending_proposals.append(proposal)
            if result.get("ok") and observability is not None and hasattr(observability, "record_event"):
                observability.record_event(
                    event_type="memory_proposal_created",
                    source="ChatMemoryRuntimeService",
                    meta={
                        "run_id": run_context.run_id,
                        "trace_id": run_context.trace_id,
                        "proposal_id": proposal_id,
                        "scope": scope,
                        "candidate_key": payload["candidate_key"],
                        "idempotent": bool(result.get("idempotent")),
                        "auto_applied": bool(result.get("auto_applied")),
                    },
                )

        if not pending_proposals:
            pending_proposals = self.router.writer.repo.list_learning_proposals(
                status="pending",
                proposer_user_key=user_key,
                limit=5,
            )
            pending_proposals = [
                self.router.writer.attach_workflow(item)
                for item in pending_proposals
            ]

        actions: list[dict[str, Any]] = []
        if pending_proposals:
            workflow_statuses: dict[str, int] = {}
            for item in pending_proposals:
                status_key = str(item.get("workflow_status") or item.get("status") or "pending").strip().lower()
                workflow_statuses[status_key] = int(workflow_statuses.get(status_key) or 0) + 1
            actions.append(
                {
                    "id": f"action-memory-review-{run_context.run_id}",
                    "type": "memory_review",
                    "label": f"Revisar {len(pending_proposals)} propuesta(s) de memoria",
                    "payload": {
                        "run_id": run_context.run_id,
                        "trace_id": run_context.trace_id,
                        "pending_count": len(pending_proposals),
                        "workflow_statuses": workflow_statuses,
                    },
                }
            )

        return {
            "memory_candidates": materialized_candidates,
            "pending_proposals": pending_proposals,
            "actions": actions,
        }
