from __future__ import annotations

import json
import os
import re
import unicodedata
from typing import Any, Callable

from apps.ia_dev.application.context.run_context import RunContext
from apps.ia_dev.application.contracts.query_intelligence_contracts import (
    SemanticNormalizationOutput,
)
from apps.ia_dev.application.taxonomia_dominios import (
    dominio_desde_capacidad,
    normalizar_codigo_dominio,
)
from apps.ia_dev.services.employee_identifier_service import EmployeeIdentifierService


class SemanticNormalizationService:
    """
    Normalizacion semantica incremental.
    Esta capa no decide estrategia final ni altera el runtime por defecto.
    """

    _EMPLOYEE_INACTIVE_SIGNAL_RE = re.compile(
        r"\b("
        r"inactivo|inactivos|"
        r"egreso|egresos|egresado|egresados|"
        r"retiro|retiros|retirado|retirados|"
        r"desvinculacion|desvinculaciones|desvinculado|desvinculados|"
        r"baja|bajas|rotacion|rotaciones"
        r")\b"
    )
    _EMPLOYEE_ACTIVE_SIGNAL_RE = re.compile(
        r"\b(activo|activa|activos|activas|vigente|vigentes|habilitado|habilitados|vinculado|vinculados)\b"
    )
    _TEMPORAL_REFERENCE_RE = re.compile(
        r"\b(hoy|ayer|esta\s+semana|semana\s+actual|semana\s+pasad[ao]|semana\s+anterior|"
        r"ultima\s+semana|ultim[oa]s?\s+\d+\s+(?:dias|semanas|meses)|rolling(?:\s+de)?\s+\d+\s+"
        r"(?:dias|semanas|meses)|este\s+mes|mes\s+actual|mes\s+pasado|mes\s+anterior|"
        r"este\s+ano|ano\s+actual|ano\s+pasado|\d{4}-\d{2}-\d{2})\b"
    )

    _LOCAL_EQUIVALENCES = {
        "personal": "empleados",
        "persona": "empleado",
        "personas": "empleados",
        "colaboradores": "empleados",
        "colaborador": "empleado",
        "jefe": "supervisor",
        "jefes": "supervisor",
        "jefe directo": "supervisor",
        "jefe inmediata": "supervisor",
        "jefe inmediato": "supervisor",
        "habilitado": "activo",
        "habilitados": "activos",
        "vigente": "activo",
        "vigentes": "activos",
        "labor": "tipo_labor",
        "labores": "tipo_labor",
        "tipo labor": "tipo_labor",
        "tipo de labor": "tipo_labor",
    }

    _ATTENDANCE_REASON_SIGNALS = {
        "vacaciones": ("justificacion", "VACACIONES"),
        "vacacion": ("justificacion", "VACACIONES"),
        "incapacidad": ("justificacion", "INCAPACIDAD"),
        "incapacidades": ("justificacion", "INCAPACIDAD"),
        "licencia": ("justificacion", "LICENCIA"),
        "licencias": ("justificacion", "LICENCIA"),
        "permiso": ("justificacion", "PERMISO"),
        "permisos": ("justificacion", "PERMISO"),
        "calamidad": ("justificacion", "CALAMIDAD"),
    }

    _DOMAIN_ALIASES = {
        "rrhh": "empleados",
        "human_resources": "empleados",
        "attendance": "ausentismo",
        "ausentismo": "ausentismo",
        "transport": "transporte",
        "transporte": "transporte",
    }

    _IMPLICIT_FILTER_SIGNALS = {
        "activo": ("estado", "ACTIVO"),
        "activa": ("estado", "ACTIVO"),
        "activos": ("estado", "ACTIVO"),
        "activas": ("estado", "ACTIVO"),
        "habilitado": ("estado", "ACTIVO"),
        "habilitados": ("estado", "ACTIVO"),
        "vigente": ("estado", "ACTIVO"),
        "vigentes": ("estado", "ACTIVO"),
        "inactivo": ("estado", "INACTIVO"),
        "inactivos": ("estado", "INACTIVO"),
        "egreso": ("estado", "INACTIVO"),
        "egresos": ("estado", "INACTIVO"),
        "egresado": ("estado", "INACTIVO"),
        "egresados": ("estado", "INACTIVO"),
        "retiro": ("estado", "INACTIVO"),
        "retiros": ("estado", "INACTIVO"),
        "retirado": ("estado", "INACTIVO"),
        "retirados": ("estado", "INACTIVO"),
        "desvinculacion": ("estado", "INACTIVO"),
        "desvinculaciones": ("estado", "INACTIVO"),
        "desvinculado": ("estado", "INACTIVO"),
        "desvinculados": ("estado", "INACTIVO"),
        "baja": ("estado", "INACTIVO"),
        "bajas": ("estado", "INACTIVO"),
        "rotacion": ("estado", "INACTIVO"),
        "rotaciones": ("estado", "INACTIVO"),
    }

    def __init__(
        self,
        *,
        llm_resolver: Callable[..., dict[str, Any]] | None = None,
    ):
        self._llm_resolver = llm_resolver

    def normalize(
        self,
        *,
        raw_query: str,
        semantic_context: dict[str, Any] | None = None,
        context_builder_output: dict[str, Any] | None = None,
        memory_hints: dict[str, Any] | None = None,
        runtime_flags: dict[str, Any] | None = None,
        capability_hints: list[dict[str, Any]] | None = None,
        base_classification: dict[str, Any] | None = None,
        run_context: RunContext | None = None,
        observability=None,
    ) -> SemanticNormalizationOutput:
        context = self._resolve_context(
            semantic_context=semantic_context,
            context_builder_output=context_builder_output,
        )
        flags = dict(runtime_flags or {})
        classification = dict(base_classification or {})
        hints = dict(memory_hints or {})

        normalized_query = self._normalize_text(raw_query)
        semantic_aliases = self._collect_semantic_aliases(
            context=context,
            query=normalized_query,
        )
        canonical_query = self._canonicalize_query(
            normalized_query=normalized_query,
            semantic_aliases=semantic_aliases,
        )
        candidate_domains = self._candidate_domains(
            query=normalized_query,
            classification=classification,
            capability_hints=capability_hints,
        )
        candidate_intents = self._candidate_intents(
            query=normalized_query,
            classification=classification,
        )
        candidate_entities = self._candidate_entities(query=normalized_query)
        candidate_filters = self._candidate_filters(
            query=normalized_query,
            memory_hints=hints,
            semantic_aliases=semantic_aliases,
        )
        normalized_capability_hints = self._normalize_capability_hints(capability_hints=capability_hints)

        deterministic_confidence = self._deterministic_confidence(
            candidate_domains=candidate_domains,
            candidate_intents=candidate_intents,
            normalized_capability_hints=normalized_capability_hints,
            candidate_filters=candidate_filters,
        )
        exact_capability_match = bool(
            normalized_capability_hints
            and normalized_capability_hints[0].get("exact_match")
        )
        possible_equivalence = normalized_query != canonical_query
        falls_to_general = str((candidate_domains[0] if candidate_domains else {}).get("domain") or "") == "general"
        conflict_qi_vs_legacy = self._has_qi_legacy_conflict(
            classification=classification,
            candidate_domains=candidate_domains,
            normalized_capability_hints=normalized_capability_hints,
        )
        strong_rule_match = deterministic_confidence >= 0.88 and not possible_equivalence
        deterministic_ambiguities = self._build_ambiguities(
            candidate_domains=candidate_domains,
            candidate_intents=candidate_intents,
            candidate_filters=candidate_filters,
            conflict_qi_vs_legacy=conflict_qi_vs_legacy,
        )
        top_capability_hint = self._top_capability_hint(normalized_capability_hints=normalized_capability_hints)

        baseline_snapshot = self._build_semantic_snapshot(
            canonical_query=canonical_query,
            candidate_domains=candidate_domains,
            candidate_intents=candidate_intents,
            candidate_filters=candidate_filters,
            semantic_aliases=semantic_aliases,
            capability_hint=top_capability_hint,
            confidence=deterministic_confidence,
            ambiguities=deterministic_ambiguities,
            resolved_by="deterministic_rules",
            llm_invoked=False,
        )

        llm_mode = self._llm_mode(flags=flags)
        llm_rollout_mode = self._llm_rollout_mode(flags=flags)
        llm_enabled = bool(flags.get("llm_enabled", True))
        if llm_rollout_mode == "off":
            should_invoke_llm = False
            llm_decision_reason = "llm_rollout_off"
        else:
            should_invoke_llm, llm_decision_reason = self._should_invoke_llm(
                llm_mode=llm_mode,
                llm_enabled=llm_enabled,
                exact_capability_match=exact_capability_match,
                strong_rule_match=strong_rule_match,
                possible_equivalence=possible_equivalence,
                conflict_qi_vs_legacy=conflict_qi_vs_legacy,
                falls_to_general=falls_to_general,
                confidence=deterministic_confidence,
                require_review=bool(flags.get("require_review")),
            )

        review_notes = [f"llm_decision:{llm_decision_reason}"]
        llm_invoked = False
        llm_applied = False
        normalization_status = "deterministic_only"
        confidence = deterministic_confidence
        llm_snapshot = dict(baseline_snapshot)
        llm_comparison = self._build_llm_comparison(
            off_snapshot=baseline_snapshot,
            on_snapshot=baseline_snapshot,
            llm_invoked=False,
            llm_rollout_mode=llm_rollout_mode,
        )

        if should_invoke_llm:
            mini_context = self._build_domain_mini_context(
                normalized_query=normalized_query,
                canonical_query=canonical_query,
                candidate_domains=candidate_domains,
                candidate_intents=candidate_intents,
                candidate_filters=candidate_filters,
                semantic_aliases=semantic_aliases,
                capability_hints=normalized_capability_hints,
                context=context,
                memory_hints=hints,
                base_classification=classification,
                deterministic_ambiguities=deterministic_ambiguities,
            )
            llm_payload = self._invoke_llm(
                raw_query=raw_query,
                normalized_query=normalized_query,
                canonical_query=canonical_query,
                semantic_aliases=semantic_aliases,
                candidate_domains=candidate_domains,
                candidate_intents=candidate_intents,
                candidate_entities=candidate_entities,
                candidate_filters=candidate_filters,
                capability_hints=normalized_capability_hints,
                context=context,
                memory_hints=hints,
                mini_context=mini_context,
                baseline_snapshot=baseline_snapshot,
            )
            if llm_payload.get("ok"):
                llm_invoked = True
                llm_normalized = self._normalize_llm_semantic_payload(
                    llm_payload=llm_payload,
                    fallback_snapshot=baseline_snapshot,
                    semantic_aliases=semantic_aliases,
                    fallback_capability_hint=top_capability_hint,
                )
                llm_snapshot = dict(llm_normalized.get("snapshot") or baseline_snapshot)
                llm_candidate_domains = list(llm_normalized.get("candidate_domains") or [])
                llm_candidate_intents = list(llm_normalized.get("candidate_intents") or [])
                llm_candidate_filters = list(llm_normalized.get("candidate_filters") or [])
                llm_review_notes = [str(item or "").strip() for item in list(llm_normalized.get("review_notes") or []) if str(item or "").strip()]
                review_notes.extend([f"llm_note:{note}" for note in llm_review_notes])

                llm_comparison = self._build_llm_comparison(
                    off_snapshot=baseline_snapshot,
                    on_snapshot=llm_snapshot,
                    llm_invoked=True,
                    llm_rollout_mode=llm_rollout_mode,
                )

                if llm_rollout_mode == "active":
                    llm_applied = True
                    normalization_status = "hybrid_llm_augmented"
                    canonical_query = str(llm_snapshot.get("canonical_query") or canonical_query).strip() or canonical_query
                    confidence = max(confidence, float(llm_snapshot.get("confidence") or confidence))
                    candidate_domains = self._merge_ranked(
                        base=candidate_domains,
                        llm_items=llm_candidate_domains,
                    )
                    candidate_intents = self._merge_ranked(
                        base=candidate_intents,
                        llm_items=llm_candidate_intents,
                    )
                    candidate_filters = self._merge_ranked(
                        base=candidate_filters,
                        llm_items=llm_candidate_filters,
                        key_name="filter",
                    )
                    if str(llm_snapshot.get("capability_hint") or "").strip():
                        top_capability_hint = str(llm_snapshot.get("capability_hint") or "").strip()
                else:
                    normalization_status = "hybrid_llm_shadow"
            else:
                normalization_status = "deterministic_fallback_after_llm_error"
                review_notes.append(f"llm_error:{str(llm_payload.get('error') or 'unknown_error')}")

        ambiguities = self._build_ambiguities(
            candidate_domains=candidate_domains,
            candidate_intents=candidate_intents,
            candidate_filters=candidate_filters,
            conflict_qi_vs_legacy=conflict_qi_vs_legacy,
        )
        if ambiguities:
            review_notes.append("ambiguities_detected")

        domain_code = self._top_domain_code(candidate_domains=candidate_domains)
        intent_code = self._top_intent_code(candidate_intents=candidate_intents)
        normalized_filters = self._top_filter_map(candidate_filters=candidate_filters)
        if llm_applied and llm_comparison.get("llm_changed_anything"):
            resolved_by = "llm_semantic_normalization_prompt"
        elif llm_invoked:
            resolved_by = "deterministic_rules_with_llm_shadow"
        else:
            resolved_by = "deterministic_rules"

        output = SemanticNormalizationOutput(
            raw_query=str(raw_query or ""),
            normalized_query=normalized_query,
            canonical_query=canonical_query,
            domain_code=domain_code,
            intent_code=intent_code,
            normalized_filters=normalized_filters,
            capability_hint=top_capability_hint,
            resolved_by=resolved_by,
            semantic_aliases=semantic_aliases,
            candidate_domains=candidate_domains,
            candidate_intents=candidate_intents,
            candidate_entities=candidate_entities,
            candidate_filters=candidate_filters,
            capability_hints=normalized_capability_hints,
            ambiguities=ambiguities,
            llm_invoked=llm_invoked,
            llm_mode=llm_mode,
            normalization_status=normalization_status,
            confidence=confidence,
            llm_comparison=llm_comparison,
            review_notes=review_notes,
        )

        self._record_event(
            observability=observability,
            run_context=run_context,
            event_type="semantic_normalization_completed",
            meta={
                "input": {
                    "raw_query": str(raw_query or "")[:220],
                    "domain_hint": str(classification.get("domain") or ""),
                    "capability_hints_count": len(normalized_capability_hints),
                    "memory_hints_keys": sorted([str(key) for key in hints.keys()])[:20],
                },
                "decision": {
                    "llm_mode": llm_mode,
                    "llm_rollout_mode": llm_rollout_mode,
                    "llm_invoked": llm_invoked,
                    "llm_applied": llm_applied,
                    "llm_decision_reason": llm_decision_reason,
                    "exact_capability_match": exact_capability_match,
                    "strong_rule_match": strong_rule_match,
                    "conflict_qi_vs_legacy": conflict_qi_vs_legacy,
                    "falls_to_general": falls_to_general,
                },
                "output": {
                    "status": normalization_status,
                    "confidence": confidence,
                    "top_domain": domain_code,
                    "top_intent": intent_code,
                    "ambiguities": len(ambiguities),
                    "resolved_by": resolved_by,
                },
                "ab_delta": {
                    "llm_changed_canonical_query": bool(llm_comparison.get("llm_changed_canonical_query")),
                    "llm_changed_domain": bool(llm_comparison.get("llm_changed_domain")),
                    "llm_changed_intent": bool(llm_comparison.get("llm_changed_intent")),
                    "llm_changed_filters": bool(llm_comparison.get("llm_changed_filters")),
                    "llm_improved_confidence": bool(llm_comparison.get("llm_improved_confidence")),
                },
            },
        )
        return output

    @staticmethod
    def _resolve_context(
        *,
        semantic_context: dict[str, Any] | None,
        context_builder_output: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if isinstance(context_builder_output, dict):
            candidate = dict(context_builder_output.get("context") or {})
            if candidate:
                return candidate
        return dict(semantic_context or {})

    @classmethod
    def _collect_semantic_aliases(
        cls,
        *,
        context: dict[str, Any],
        query: str,
    ) -> list[dict[str, Any]]:
        aliases: dict[str, str] = {}
        for row in list((context.get("dictionary") or {}).get("synonyms") or []):
            if not isinstance(row, dict):
                continue
            term = cls._normalize_text(row.get("termino"))
            synonym = cls._normalize_text(row.get("sinonimo"))
            if term and synonym:
                aliases[synonym] = term
                aliases.setdefault(term, term)
        for alias, canonical in cls._LOCAL_EQUIVALENCES.items():
            aliases.setdefault(cls._normalize_text(alias), cls._normalize_text(canonical))
        results: list[dict[str, Any]] = []
        for alias, canonical in sorted(aliases.items()):
            if not alias or not canonical:
                continue
            if alias in query:
                results.append(
                    {
                        "alias": alias,
                        "canonical": canonical,
                        "source": "dictionary_or_local_equivalence",
                    }
                )
        return results

    @classmethod
    def _canonicalize_query(
        cls,
        *,
        normalized_query: str,
        semantic_aliases: list[dict[str, Any]],
    ) -> str:
        canonical = str(normalized_query or "")
        for row in sorted(list(semantic_aliases or []), key=lambda item: len(str(item.get("alias") or "")), reverse=True):
            alias = str(row.get("alias") or "").strip()
            target = str(row.get("canonical") or "").strip()
            if alias and target:
                canonical = re.sub(rf"\b{re.escape(alias)}\b", target, canonical)
        canonical = re.sub(r"\s+", " ", canonical).strip()
        return canonical

    @classmethod
    def _candidate_domains(
        cls,
        *,
        query: str,
        classification: dict[str, Any],
        capability_hints: list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        score = {"empleados": 0.0, "ausentismo": 0.0, "general": 0.1}
        has_employee_inactive_signal = cls._has_employee_inactive_signal(query)
        if any(
            token in query
            for token in (
                "empleado",
                "empleados",
                "colaborador",
                "colaboradores",
                "personal",
                "persona",
                "personas",
                "rrhh",
                "cedula",
                "habilitad",
                "vigent",
                "rotacion",
                "rotaciones",
            )
        ):
            score["empleados"] += 0.65
        if has_employee_inactive_signal:
            score["empleados"] += 0.65
        if EmployeeIdentifierService.has_movil_identifier(query):
            score["empleados"] += 0.65
        if re.search(
            r"\b(tipo_labor|tipo\s+labor|tipo\s+de\s+labor|labor(?:es)?|area(?:s)?|cargo(?:s)?|supervisor(?:es)?|jefe(?:s)?|lider(?:es)?|carpeta(?:s)?|sede(?:s)?)\b",
            query,
        ) and not any(
            token in query
            for token in ("ausent", "asistencia", "injustific", "vacacion", "vacaciones", "incapacidad", "licencia", "permiso", "calamidad")
        ):
            score["empleados"] += 0.45
        if re.search(r"\b(?:info|informacion|detalle|datos|ficha)\s+de\s+[a-z0-9_-]{3,40}\b", query):
            score["empleados"] += 0.55
        if re.search(r"^\s*(?:info|informacion|detalle|datos|ficha)\s+[a-z0-9_-]{3,40}\s*$", query):
            score["empleados"] += 0.55
        has_people_scope = any(
            token in query
            for token in ("empleado", "empleados", "colaborador", "colaboradores", "personal", "persona", "personas")
        )
        has_attendance_reason = any(
            token in query for token in ("vacacion", "vacaciones", "incapacidad", "licencia", "permiso", "calamidad")
        )
        if any(token in query for token in ("ausent", "asistencia", "injustific", "supervisor", "jefe")):
            score["ausentismo"] += 0.45
        if has_attendance_reason:
            score["ausentismo"] += 0.55
        if has_people_scope and has_attendance_reason:
            score["ausentismo"] += 0.35
        base_domain = cls._normalize_domain_code(classification.get("domain"))
        if base_domain in score:
            score[base_domain] += 0.2
        for hint in list(capability_hints or []):
            capability_id = str((hint or {}).get("capability_id") or "").strip().lower()
            if capability_id.startswith("empleados."):
                score["empleados"] += 0.25
            elif capability_id.startswith("attendance."):
                score["ausentismo"] += 0.2
        ranked = sorted(score.items(), key=lambda item: item[1], reverse=True)
        return [
            {
                "domain": str(domain),
                "confidence": min(1.0, round(float(conf), 4)),
                "source": "deterministic_signals",
            }
            for domain, conf in ranked
            if conf > 0
        ]

    @classmethod
    def _candidate_intents(
        cls,
        *,
        query: str,
        classification: dict[str, Any],
    ) -> list[dict[str, Any]]:
        intent_scores = {"count": 0.0, "detail": 0.0, "aggregate": 0.0, "trend": 0.0, "summary": 0.2}
        if any(token in query for token in ("cantidad", "numero", "cuantos", "cuantas", "total")) or bool(
            re.search(r"\bcantid[a-z]*\b", query)
        ):
            intent_scores["count"] += 0.7
        if cls._has_employee_status_metric_signal(query):
            intent_scores["count"] += 0.62
        if any(token in query for token in ("detalle", "tabla", "listar", "lista", "informacion", "info", "ficha", "datos")):
            intent_scores["detail"] += 0.6
        if EmployeeIdentifierService.has_movil_identifier(query) or bool(re.search(r"\b\d{6,13}\b", query)):
            intent_scores["detail"] += 0.55
        if any(token in query for token in ("vacacion", "vacaciones", "incapacidad", "licencia", "permiso", "calamidad")) and any(
            token in query for token in ("empleado", "empleados", "colaborador", "colaboradores", "personal", "persona", "personas")
        ):
            intent_scores["detail"] += 0.55
        if any(token in query for token in ("por ", "concentran", "distribucion", "top", "compar")):
            intent_scores["aggregate"] += 0.45
        if any(token in query for token in ("tendencia", "historico", "evolucion", "trend")):
            intent_scores["trend"] += 0.5
        base_intent = str(classification.get("intent") or "").strip().lower()
        if "count" in base_intent:
            intent_scores["count"] += 0.15
        ranked = sorted(intent_scores.items(), key=lambda item: item[1], reverse=True)
        return [
            {
                "intent": intent,
                "confidence": min(1.0, round(float(confidence), 4)),
                "source": "deterministic_rules",
            }
            for intent, confidence in ranked
            if confidence > 0
        ]

    @staticmethod
    def _candidate_entities(*, query: str) -> list[dict[str, Any]]:
        entities: list[dict[str, Any]] = []
        cedula_match = re.search(r"\b\d{6,13}\b", query)
        if cedula_match:
            entities.append(
                {
                    "entity_type": "cedula",
                    "entity_value": "".join(ch for ch in cedula_match.group(0) if ch.isdigit()),
                    "confidence": 0.95,
                }
            )
        movil_match = EmployeeIdentifierService.extract_movil_identifier(query)
        if movil_match:
            entities.append(
                {
                    "entity_type": "movil",
                    "entity_value": movil_match,
                    "confidence": 0.93,
                }
            )
        if any(token in query for token in ("empleado", "empleados", "colaborador", "colaboradores", "personal", "persona", "personas")):
            entities.append(
                {
                    "entity_type": "empleado",
                    "entity_value": "",
                    "confidence": 0.7,
                }
            )
        return entities

    @classmethod
    def _candidate_filters(
        cls,
        *,
        query: str,
        memory_hints: dict[str, Any],
        semantic_aliases: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        filters: list[dict[str, Any]] = []
        canonical_aliases = {str(item.get("alias") or ""): str(item.get("canonical") or "") for item in list(semantic_aliases or [])}
        if any(token in query for token in ("activo", "activa", "activos", "activas", "habilitado", "habilitados", "vigente", "vigentes")):
            filters.append({"filter": "estado", "value": "ACTIVO", "confidence": 0.9, "source": "deterministic"})
        elif cls._has_employee_inactive_signal(query):
            filters.append({"filter": "estado", "value": "INACTIVO", "confidence": 0.9, "source": "deterministic"})
        elif (
            canonical_aliases.get("habilitado") == "activo"
            or canonical_aliases.get("habilitados") == "activos"
            or canonical_aliases.get("vigente") == "activo"
            or canonical_aliases.get("vigentes") == "activos"
        ):
            filters.append({"filter": "estado", "value": "ACTIVO", "confidence": 0.8, "source": "alias"})

        personal_status = str(memory_hints.get("personal_status") or "").strip().upper()
        if personal_status in {"ACTIVO", "INACTIVO"} and not any(item.get("filter") == "estado" for item in filters):
            filters.append(
                {
                    "filter": "estado",
                    "value": personal_status,
                    "confidence": 0.65,
                    "source": "memory_hint",
                }
            )
        for token, (filter_name, value) in cls._ATTENDANCE_REASON_SIGNALS.items():
            if token in query:
                filters.append(
                    {
                        "filter": filter_name,
                        "value": value,
                        "confidence": 0.88,
                        "source": "deterministic_attendance_reason",
                    }
                )
                break
        return filters

    @staticmethod
    def _normalize_capability_hints(
        *,
        capability_hints: list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for row in list(capability_hints or []):
            if not isinstance(row, dict):
                continue
            capability_id = str(row.get("capability_id") or "").strip().lower()
            if not capability_id:
                continue
            reason = str(row.get("reason") or "").strip()
            normalized.append(
                {
                    "capability_id": capability_id,
                    "reason": reason,
                    "exact_match": bool("exact" in reason.lower() or "semantic_execution_plan_capability" in reason.lower()),
                    "score": float(row.get("score") or 0.0),
                }
            )
        return normalized

    @staticmethod
    def _deterministic_confidence(
        *,
        candidate_domains: list[dict[str, Any]],
        candidate_intents: list[dict[str, Any]],
        normalized_capability_hints: list[dict[str, Any]],
        candidate_filters: list[dict[str, Any]],
    ) -> float:
        domain_conf = float((candidate_domains[0] if candidate_domains else {}).get("confidence") or 0.0)
        intent_conf = float((candidate_intents[0] if candidate_intents else {}).get("confidence") or 0.0)
        capability_bonus = 0.1 if normalized_capability_hints else 0.0
        filter_bonus = min(0.12, len(candidate_filters) * 0.04)
        return min(1.0, round((domain_conf * 0.45) + (intent_conf * 0.45) + capability_bonus + filter_bonus, 4))

    @staticmethod
    def _has_qi_legacy_conflict(
        *,
        classification: dict[str, Any],
        candidate_domains: list[dict[str, Any]],
        normalized_capability_hints: list[dict[str, Any]],
    ) -> bool:
        legacy_domain = normalizar_codigo_dominio(classification.get("domain"))
        top_domain = normalizar_codigo_dominio((candidate_domains[0] if candidate_domains else {}).get("domain"))
        if legacy_domain and top_domain and legacy_domain != top_domain:
            return True
        if normalized_capability_hints:
            first_capability = str(normalized_capability_hints[0].get("capability_id") or "")
            capability_domain = dominio_desde_capacidad(first_capability)
            if capability_domain and top_domain and capability_domain != top_domain:
                return True
        return False

    @staticmethod
    def _llm_mode(*, flags: dict[str, Any]) -> str:
        mode = str(flags.get("llm_mode") or os.getenv("IA_DEV_SEMANTIC_NORMALIZATION_LLM_MODE", "hybrid")).strip().lower()
        if mode in {"off", "disabled", "none", "never"}:
            return "never"
        if mode in {"always", "force"}:
            return "always"
        return "hybrid"

    @staticmethod
    def _llm_rollout_mode(*, flags: dict[str, Any]) -> str:
        mode = str(
            flags.get("llm_rollout_mode")
            or os.getenv("IA_DEV_SEMANTIC_NORMALIZATION_LLM_ROLLOUT_MODE", "active")
        ).strip().lower()
        if mode in {"off", "disabled", "none", "never"}:
            return "off"
        if mode in {"shadow", "observe", "dry_run"}:
            return "shadow"
        return "active"

    @staticmethod
    def _should_invoke_llm(
        *,
        llm_mode: str,
        llm_enabled: bool,
        exact_capability_match: bool,
        strong_rule_match: bool,
        possible_equivalence: bool,
        conflict_qi_vs_legacy: bool,
        falls_to_general: bool,
        confidence: float,
        require_review: bool,
    ) -> tuple[bool, str]:
        if not llm_enabled:
            return False, "llm_disabled_by_policy"
        if llm_mode == "never":
            return False, "llm_mode_never"
        if exact_capability_match and strong_rule_match and confidence >= 0.85:
            return False, "exact_match_high_confidence"
        if llm_mode == "always":
            return True, "llm_mode_always"
        reasons: list[str] = []
        if not exact_capability_match:
            reasons.append("no_exact_capability_match")
        if conflict_qi_vs_legacy:
            reasons.append("qi_legacy_conflict")
        if possible_equivalence:
            reasons.append("possible_synonym_equivalence")
        if falls_to_general:
            reasons.append("falls_to_general")
        if confidence <= 0.75:
            reasons.append("low_or_medium_confidence")
        if require_review:
            reasons.append("require_review")
        if reasons:
            return True, "+".join(reasons)
        return False, "deterministic_sufficient"

    def _invoke_llm(
        self,
        *,
        raw_query: str,
        normalized_query: str,
        canonical_query: str,
        semantic_aliases: list[dict[str, Any]],
        candidate_domains: list[dict[str, Any]],
        candidate_intents: list[dict[str, Any]],
        candidate_entities: list[dict[str, Any]],
        candidate_filters: list[dict[str, Any]],
        capability_hints: list[dict[str, Any]],
        context: dict[str, Any],
        memory_hints: dict[str, Any],
        mini_context: dict[str, Any],
        baseline_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        if self._llm_resolver is not None:
            payload = dict(
                self._llm_resolver(
                    raw_query=raw_query,
                    normalized_query=normalized_query,
                    canonical_query=canonical_query,
                    semantic_aliases=semantic_aliases,
                    candidate_domains=candidate_domains,
                    candidate_intents=candidate_intents,
                    candidate_entities=candidate_entities,
                    candidate_filters=candidate_filters,
                    capability_hints=capability_hints,
                    context=context,
                    memory_hints=memory_hints,
                    mini_context=mini_context,
                    baseline_snapshot=baseline_snapshot,
                )
                or {}
            )
            if "ok" not in payload:
                payload["ok"] = bool(payload)
            return payload

        api_key = str(os.getenv("OPENAI_API_KEY") or os.getenv("IA_DEV_OPENAI_API_KEY") or "").strip()
        if not api_key:
            return {"ok": False, "error": "missing_openai_api_key"}
        try:
            from openai import OpenAI

            client = OpenAI(api_key=api_key)
            prompt_payload = {
                "raw_query": raw_query,
                "normalized_query": normalized_query,
                "deterministic_baseline": baseline_snapshot,
                "mini_context": mini_context,
                "candidate_entities": candidate_entities,
            }
            response = client.responses.create(
                model=str(os.getenv("IA_DEV_SEMANTIC_NORMALIZATION_LLM_MODEL", os.getenv("IA_DEV_MODEL", "gpt-5-nano")) or "gpt-5-nano"),
                input=[
                    {
                        "role": "system",
                        "content": self._semantic_normalization_system_prompt(),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(prompt_payload, ensure_ascii=False),
                    },
                ],
            )
            text = str(getattr(response, "output_text", "") or "").strip()
            payload = self._safe_json(text)
            return {"ok": True, **payload}
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}:{exc}"}

    @staticmethod
    def _semantic_normalization_system_prompt() -> str:
        return (
            "Eres un nodo enterprise de semantic normalization para consultas de negocio.\n"
            "No clasifiques intencion general del chat: solo normaliza semantica.\n"
            "Devuelve SOLO JSON estricto con EXACTAMENTE estas llaves:\n"
            "canonical_query, domain_code, intent_code, filters, aliases_detected, capability_hint, confidence, ambiguities.\n"
            "Reglas:\n"
            "1) filters debe ser objeto clave/valor normalizado.\n"
            "2) aliases_detected debe ser lista de alias detectados.\n"
            "3) confidence entre 0 y 1.\n"
            "4) Usa SIEMPRE ambas capas del contexto: YAML de negocio y metadata estructurada de DB.\n"
            "5) Usa mini_context.semantic_contract, candidate_tables, candidate_columns, candidate_group_dimensions y default_runtime_rules como fuente primaria.\n"
            "6) Si la consulta usa 'por <dimension>' y esa dimension existe en candidate_group_dimensions, prioriza intent_code=aggregate.\n"
            "7) Si hay duda, conserva baseline deterministico y reporta ambiguity.\n"
            "8) Prohibido SQL, explicaciones o texto fuera del JSON."
        )

    @classmethod
    def _build_domain_mini_context(
        cls,
        *,
        normalized_query: str,
        canonical_query: str,
        candidate_domains: list[dict[str, Any]],
        candidate_intents: list[dict[str, Any]],
        candidate_filters: list[dict[str, Any]],
        semantic_aliases: list[dict[str, Any]],
        capability_hints: list[dict[str, Any]],
        context: dict[str, Any],
        memory_hints: dict[str, Any],
        base_classification: dict[str, Any],
        deterministic_ambiguities: list[dict[str, Any]],
    ) -> dict[str, Any]:
        domain_candidate = cls._top_domain_code(candidate_domains=candidate_domains)
        if not domain_candidate:
            domain_candidate = cls._normalize_domain_code(base_classification.get("domain"))
        if not domain_candidate:
            domain_candidate = cls._normalize_domain_code(context.get("domain_code"))
        domain_candidate = domain_candidate or "general"

        business_equivalences: list[str] = []
        for row in list((context.get("dictionary") or {}).get("synonyms") or []):
            if not isinstance(row, dict):
                continue
            canonical = cls._normalize_text(row.get("termino"))
            synonym = cls._normalize_text(row.get("sinonimo"))
            if not canonical or not synonym:
                continue
            if synonym in normalized_query or canonical in normalized_query:
                business_equivalences.append(f"{synonym}={canonical}")
        for row in list(semantic_aliases or []):
            if not isinstance(row, dict):
                continue
            alias = cls._normalize_text(row.get("alias"))
            canonical = cls._normalize_text(row.get("canonical"))
            if alias and canonical:
                business_equivalences.append(f"{alias}={canonical}")
        if domain_candidate == "empleados":
            business_equivalences.extend(
                [
                    "personal=empleados",
                    "colaborador=empleado",
                    "vigente=activo",
                    "habilitado=activo",
                    "egresos=inactivo",
                    "retiros=inactivo",
                ]
            )
        frequent_capabilities: list[str] = []
        for row in list(capability_hints or []):
            if not isinstance(row, dict):
                continue
            capability_id = str(row.get("capability_id") or "").strip().lower()
            if capability_id:
                frequent_capabilities.append(capability_id)
        for row in list(context.get("capabilities") or []):
            if len(frequent_capabilities) >= 5:
                break
            if isinstance(row, dict):
                capability_id = str(row.get("capability_id") or row.get("id") or "").strip().lower()
            else:
                capability_id = str(row or "").strip().lower()
            if not capability_id:
                continue
            if domain_candidate in {"general", ""} or capability_id.startswith(f"{domain_candidate}."):
                frequent_capabilities.append(capability_id)

        implicit_filter_signals: list[str] = []
        for token, (key, value) in cls._IMPLICIT_FILTER_SIGNALS.items():
            if token in normalized_query:
                implicit_filter_signals.append(f"{token}->{key}={value}")
        top_filters = cls._top_filter_map(candidate_filters=candidate_filters)
        if top_filters:
            implicit_filter_signals.append(f"deterministic_filters={top_filters}")
        personal_status = str(memory_hints.get("personal_status") or "").strip().upper()
        if personal_status in {"ACTIVO", "INACTIVO"}:
            implicit_filter_signals.append(f"memory.personal_status->estado={personal_status}")

        semantic_rules: list[str] = []
        for row in list((context.get("dictionary") or {}).get("rules") or [])[:6]:
            if not isinstance(row, dict):
                continue
            rule_name = str(row.get("rule_name") or row.get("nombre_regla") or "").strip()
            condition = str(row.get("condition") or row.get("condicion") or "").strip()
            action = str(row.get("action") or row.get("accion") or "").strip()
            compact = " | ".join([item for item in [rule_name, condition, action] if item])
            if compact:
                semantic_rules.append(compact[:160])
        if domain_candidate == "empleados":
            semantic_rules.extend(
                [
                    "si consulta de cantidad + estado activo, priorizar intent_code=count",
                    "si aparece vigente/habilitado, normalizar filter estado=ACTIVO",
                    "si aparece egreso/retiro/desvinculacion, normalizar filter estado=INACTIVO",
                    "si hay periodo y estado=INACTIVO, priorizar fecha_egreso como columna temporal",
                ]
            )

        ambiguity_types = [
            str(item.get("type") or "").strip()
            for item in list(deterministic_ambiguities or [])
            if isinstance(item, dict) and str(item.get("type") or "").strip()
        ]
        candidate_tables = cls._mini_context_candidate_tables(context=context)
        candidate_columns = cls._mini_context_candidate_columns(
            context=context,
            domain_candidate=domain_candidate,
        )
        candidate_group_dimensions = cls._mini_context_candidate_group_dimensions(
            context=context,
            domain_candidate=domain_candidate,
        )
        candidate_filter_columns = cls._mini_context_candidate_filter_columns(
            context=context,
            domain_candidate=domain_candidate,
        )
        join_paths = cls._mini_context_join_paths(context=context)
        default_runtime_rules = cls._mini_context_default_runtime_rules(
            domain_candidate=domain_candidate,
            candidate_group_dimensions=candidate_group_dimensions,
            candidate_filter_columns=candidate_filter_columns,
            candidate_tables=candidate_tables,
        )
        semantic_contract = {
            "source_of_truth": str(context.get("source_of_truth") or "").strip().lower() or "hybrid",
            "use_yaml_business_context": True,
            "use_db_structured_metadata": True,
            "yaml_context_layers": ["contexto_agente", "reglas_negocio", "ejemplos_consulta"],
            "db_context_layers": ["dictionary", "tables", "column_profiles", "relation_profiles", "query_hints"],
        }

        return {
            "domain_candidate": domain_candidate,
            "semantic_contract": semantic_contract,
            "business_equivalences": list(dict.fromkeys([item for item in business_equivalences if item]))[:12],
            "frequent_capabilities": list(dict.fromkeys([item for item in frequent_capabilities if item]))[:5],
            "implicit_filter_signals": list(dict.fromkeys([item for item in implicit_filter_signals if item]))[:8],
            "semantic_rules": list(dict.fromkeys([item for item in semantic_rules if item]))[:8],
            "candidate_tables": candidate_tables,
            "candidate_columns": candidate_columns,
            "candidate_group_dimensions": candidate_group_dimensions,
            "candidate_filter_columns": candidate_filter_columns,
            "join_paths": join_paths,
            "default_runtime_rules": default_runtime_rules,
            "canonical_resolution_hints": {
                "canonical_query_baseline": canonical_query,
                "domain_hint_base_classification": cls._normalize_domain_code(base_classification.get("domain")),
                "intent_hint_base_classification": str(base_classification.get("intent") or "").strip().lower(),
                "deterministic_top_domain": cls._top_domain_code(candidate_domains=candidate_domains),
                "deterministic_top_intent": cls._top_intent_code(candidate_intents=candidate_intents),
                "deterministic_ambiguity_types": ambiguity_types[:6],
            },
            "memory_hints": {
                "personal_status": str(memory_hints.get("personal_status") or "").strip().upper(),
                "keys": sorted([str(key) for key in memory_hints.keys()])[:12],
            },
        }

    @classmethod
    def _mini_context_candidate_tables(
        cls,
        *,
        context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        values: list[dict[str, Any]] = []
        for row in list(context.get("tables") or [])[:8]:
            if not isinstance(row, dict):
                continue
            table_name = str(row.get("table_name") or "").strip().lower()
            if not table_name:
                continue
            values.append(
                {
                    "table_name": table_name,
                    "table_fqn": str(row.get("table_fqn") or "").strip().lower(),
                    "role": str(row.get("rol") or "").strip().lower(),
                    "is_primary": bool(row.get("es_principal")),
                }
            )
        return values

    @classmethod
    def _mini_context_candidate_columns(
        cls,
        *,
        context: dict[str, Any],
        domain_candidate: str,
    ) -> list[dict[str, Any]]:
        values: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in list(context.get("column_profiles") or []):
            if not isinstance(row, dict):
                continue
            logical_name = str(row.get("logical_name") or "").strip().lower()
            column_name = str(row.get("column_name") or "").strip().lower()
            if not logical_name and not column_name:
                continue
            key = logical_name or column_name
            if key in seen:
                continue
            seen.add(key)
            tags: list[str] = []
            if bool(row.get("supports_filter")):
                tags.append("filter")
            if bool(row.get("supports_group_by")) or bool(row.get("supports_dimension")):
                tags.append("group_by")
            if bool(row.get("supports_metric")):
                tags.append("metric")
            if bool(row.get("is_identifier")):
                tags.append("identifier")
            if bool(row.get("is_date")):
                tags.append("date")
            values.append(
                {
                    "logical_name": logical_name or column_name,
                    "column_name": column_name or logical_name,
                    "table_name": str(row.get("table_name") or "").strip().lower(),
                    "tags": tags,
                }
            )

        for logical_name in cls._mini_context_candidate_group_dimensions(
            context=context,
            domain_candidate=domain_candidate,
        ):
            if logical_name in seen:
                continue
            seen.add(logical_name)
            values.append(
                {
                    "logical_name": logical_name,
                    "column_name": logical_name,
                    "table_name": "cinco_base_de_personal" if logical_name in {"supervisor", "area", "cargo", "carpeta"} else "",
                    "tags": ["group_by"],
                }
            )
        return values[:16]

    @classmethod
    def _mini_context_candidate_group_dimensions(
        cls,
        *,
        context: dict[str, Any],
        domain_candidate: str,
    ) -> list[str]:
        dimensions: list[str] = []
        for row in list(context.get("column_profiles") or []):
            if not isinstance(row, dict):
                continue
            if not (bool(row.get("supports_group_by")) or bool(row.get("supports_dimension"))):
                continue
            logical_name = str(row.get("logical_name") or row.get("column_name") or "").strip().lower()
            if logical_name:
                dimensions.append(logical_name)

        has_personal_join = any(
            str(item.get("table_name") or "").strip().lower() == "cinco_base_de_personal"
            for item in list(context.get("tables") or [])
            if isinstance(item, dict)
        ) or any(
            "cinco_base_de_personal" in str(item.get("join_sql") or "").strip().lower()
            for item in list(context.get("relation_profiles") or [])
            if isinstance(item, dict)
        )
        if domain_candidate == "empleados":
            dimensions.extend(["supervisor", "area", "cargo", "carpeta", "tipo_labor", "sede"])
        if domain_candidate == "ausentismo":
            dimensions.extend(["justificacion", "estado_justificacion"])
            if has_personal_join:
                dimensions.extend(["supervisor", "area", "cargo", "carpeta", "tipo_labor", "sede"])
        return list(dict.fromkeys([item for item in dimensions if item]))[:10]

    @classmethod
    def _mini_context_candidate_filter_columns(
        cls,
        *,
        context: dict[str, Any],
        domain_candidate: str,
    ) -> list[str]:
        values = [
            str(row.get("logical_name") or row.get("column_name") or "").strip().lower()
            for row in list(context.get("column_profiles") or [])
            if isinstance(row, dict) and bool(row.get("supports_filter"))
        ]
        if domain_candidate == "empleados":
            values.append("estado")
        return list(dict.fromkeys([item for item in values if item]))[:10]

    @classmethod
    def _mini_context_join_paths(
        cls,
        *,
        context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        values: list[dict[str, Any]] = []
        for row in list(context.get("relation_profiles") or [])[:6]:
            if not isinstance(row, dict):
                continue
            values.append(
                {
                    "relation_name": str(row.get("relation_name") or "").strip().lower(),
                    "join_sql": str(row.get("join_sql") or "").strip(),
                    "cardinality": str(row.get("cardinality") or "").strip().lower(),
                }
            )
        return values

    @classmethod
    def _mini_context_default_runtime_rules(
        cls,
        *,
        domain_candidate: str,
        candidate_group_dimensions: list[str],
        candidate_filter_columns: list[str],
        candidate_tables: list[dict[str, Any]],
    ) -> list[str]:
        rules = ["si la consulta usa 'por <dimension>', interpretar aggregate/group_by"]
        if domain_candidate == "empleados":
            rules.append("si no se especifica estado en empleados, usar estado=ACTIVO")
        if domain_candidate == "ausentismo" and any(
            str(item.get("table_name") or "").strip().lower() == "cinco_base_de_personal"
            for item in list(candidate_tables or [])
            if isinstance(item, dict)
        ):
            rules.append("para area/cargo/supervisor/carpeta usar join con cinco_base_de_personal")
            rules.append("si aparecen vacaciones/incapacidad/licencia/permiso, usar filtro justificacion")
        if "estado" in candidate_filter_columns:
            rules.append("si se detecta habilitado/vigente, normalizar estado=ACTIVO")
        if candidate_group_dimensions:
            rules.append(f"dimensiones agrupables preferidas={','.join(candidate_group_dimensions[:6])}")
        return rules[:8]

    @classmethod
    def _normalize_llm_semantic_payload(
        cls,
        *,
        llm_payload: dict[str, Any],
        fallback_snapshot: dict[str, Any],
        semantic_aliases: list[dict[str, Any]],
        fallback_capability_hint: str,
    ) -> dict[str, Any]:
        payload = dict(llm_payload or {})
        scoped = dict(payload.get("semantic_normalization") or {})
        if scoped:
            payload = scoped

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

        domain_code = cls._normalize_domain_code(payload.get("domain_code"))
        if not domain_code and candidate_domains:
            domain_code = cls._normalize_domain_code((candidate_domains[0] or {}).get("domain"))
        intent_code = str(payload.get("intent_code") or payload.get("operation") or "").strip().lower()
        if not intent_code and candidate_intents:
            intent_code = str((candidate_intents[0] or {}).get("intent") or "").strip().lower()

        filters_map = payload.get("filters") if isinstance(payload.get("filters"), dict) else {}
        if not filters_map and candidate_filters:
            filters_map = cls._top_filter_map(candidate_filters=candidate_filters)
        if filters_map and not candidate_filters:
            candidate_filters = [
                {
                    "filter": str(key),
                    "value": value,
                    "confidence": float(payload.get("confidence") or fallback_snapshot.get("confidence") or 0.0),
                    "source": "llm_semantic_normalization_prompt",
                }
                for key, value in dict(filters_map).items()
                if str(key).strip()
            ]

        aliases_detected_raw = payload.get("aliases_detected")
        aliases_detected: list[dict[str, Any]] = []
        if isinstance(aliases_detected_raw, list):
            for item in aliases_detected_raw:
                if isinstance(item, dict):
                    alias = cls._normalize_text(item.get("alias"))
                    canonical = cls._normalize_text(item.get("canonical"))
                    if alias or canonical:
                        aliases_detected.append({"alias": alias, "canonical": canonical})
                else:
                    alias = cls._normalize_text(item)
                    if alias:
                        aliases_detected.append({"alias": alias, "canonical": ""})
        if not aliases_detected:
            aliases_detected = [dict(item) for item in list(semantic_aliases or []) if isinstance(item, dict)]

        confidence = float(payload.get("confidence") or fallback_snapshot.get("confidence") or 0.0)
        confidence = max(0.0, min(1.0, confidence))
        capability_hint = str(payload.get("capability_hint") or fallback_capability_hint or "").strip().lower()
        ambiguities = [
            dict(item)
            for item in list(payload.get("ambiguities") or [])
            if isinstance(item, dict)
        ]

        if not candidate_domains and domain_code:
            candidate_domains = [
                {
                    "domain": domain_code,
                    "confidence": confidence,
                    "source": "llm_semantic_normalization_prompt",
                }
            ]
        if not candidate_intents and intent_code:
            candidate_intents = [
                {
                    "intent": intent_code,
                    "confidence": confidence,
                    "source": "llm_semantic_normalization_prompt",
                }
            ]

        canonical_query = str(payload.get("canonical_query") or fallback_snapshot.get("canonical_query") or "").strip()
        snapshot = cls._build_semantic_snapshot(
            canonical_query=canonical_query,
            candidate_domains=candidate_domains or [
                {
                    "domain": str(fallback_snapshot.get("domain_code") or ""),
                    "confidence": float(fallback_snapshot.get("confidence") or 0.0),
                    "source": "deterministic_fallback",
                }
            ],
            candidate_intents=candidate_intents or [
                {
                    "intent": str(fallback_snapshot.get("intent_code") or ""),
                    "confidence": float(fallback_snapshot.get("confidence") or 0.0),
                    "source": "deterministic_fallback",
                }
            ],
            candidate_filters=candidate_filters or [
                {"filter": key, "value": value, "confidence": 0.7, "source": "deterministic_fallback"}
                for key, value in dict(fallback_snapshot.get("filters") or {}).items()
            ],
            semantic_aliases=aliases_detected,
            capability_hint=capability_hint,
            confidence=confidence,
            ambiguities=ambiguities or list(fallback_snapshot.get("ambiguities") or []),
            resolved_by="llm_semantic_normalization_prompt",
            llm_invoked=True,
        )
        review_notes = [
            str(item or "").strip()
            for item in list(payload.get("review_notes") or [])
            if str(item or "").strip()
        ]
        return {
            "snapshot": snapshot,
            "candidate_domains": candidate_domains,
            "candidate_intents": candidate_intents,
            "candidate_filters": candidate_filters,
            "review_notes": review_notes,
        }

    @classmethod
    def _build_semantic_snapshot(
        cls,
        *,
        canonical_query: str,
        candidate_domains: list[dict[str, Any]],
        candidate_intents: list[dict[str, Any]],
        candidate_filters: list[dict[str, Any]],
        semantic_aliases: list[dict[str, Any]],
        capability_hint: str,
        confidence: float,
        ambiguities: list[dict[str, Any]],
        resolved_by: str,
        llm_invoked: bool,
    ) -> dict[str, Any]:
        return {
            "llm_invoked": bool(llm_invoked),
            "canonical_query": str(canonical_query or "").strip(),
            "domain_code": cls._top_domain_code(candidate_domains=candidate_domains),
            "intent_code": cls._top_intent_code(candidate_intents=candidate_intents),
            "filters": cls._top_filter_map(candidate_filters=candidate_filters),
            "aliases_detected": [dict(item) for item in list(semantic_aliases or []) if isinstance(item, dict)],
            "capability_hint": str(capability_hint or "").strip().lower(),
            "confidence": max(0.0, min(1.0, float(confidence or 0.0))),
            "ambiguities": [dict(item) for item in list(ambiguities or []) if isinstance(item, dict)],
            "resolved_by": str(resolved_by or ""),
        }

    @staticmethod
    def _build_llm_comparison(
        *,
        off_snapshot: dict[str, Any],
        on_snapshot: dict[str, Any],
        llm_invoked: bool,
        llm_rollout_mode: str,
    ) -> dict[str, Any]:
        off = dict(off_snapshot or {})
        on = dict(on_snapshot or {})
        changed_canonical_query = str(off.get("canonical_query") or "") != str(on.get("canonical_query") or "")
        changed_domain = str(off.get("domain_code") or "") != str(on.get("domain_code") or "")
        changed_intent = str(off.get("intent_code") or "") != str(on.get("intent_code") or "")
        changed_filters = dict(off.get("filters") or {}) != dict(on.get("filters") or {})
        changed_capability_hint = str(off.get("capability_hint") or "") != str(on.get("capability_hint") or "")
        improved_confidence = float(on.get("confidence") or 0.0) > float(off.get("confidence") or 0.0)
        changed_anything = any(
            [
                changed_canonical_query,
                changed_domain,
                changed_intent,
                changed_filters,
                changed_capability_hint,
                improved_confidence,
            ]
        )
        return {
            "llm_invoked": bool(llm_invoked),
            "llm_rollout_mode": str(llm_rollout_mode or "active"),
            "off": off,
            "on": on,
            "llm_changed_canonical_query": bool(changed_canonical_query),
            "llm_changed_domain": bool(changed_domain),
            "llm_changed_intent": bool(changed_intent),
            "llm_changed_filters": bool(changed_filters),
            "llm_improved_confidence": bool(improved_confidence),
            "llm_changed_capability_hint": bool(changed_capability_hint),
            "llm_changed_anything": bool(changed_anything),
        }

    @staticmethod
    def _top_filter_map(*, candidate_filters: list[dict[str, Any]]) -> dict[str, Any]:
        best: dict[str, tuple[Any, float]] = {}
        for row in list(candidate_filters or []):
            if not isinstance(row, dict):
                continue
            key = str(row.get("filter") or "").strip().lower()
            if not key:
                continue
            value = row.get("value")
            conf = float(row.get("confidence") or 0.0)
            current = best.get(key)
            if current is None or conf >= current[1]:
                best[key] = (value, conf)
        return {key: value for key, (value, _) in best.items()}

    @staticmethod
    def _top_domain_code(*, candidate_domains: list[dict[str, Any]]) -> str:
        return normalizar_codigo_dominio((candidate_domains[0] if candidate_domains else {}).get("domain"))

    @staticmethod
    def _top_intent_code(*, candidate_intents: list[dict[str, Any]]) -> str:
        return str((candidate_intents[0] if candidate_intents else {}).get("intent") or "").strip().lower()

    @staticmethod
    def _top_capability_hint(*, normalized_capability_hints: list[dict[str, Any]]) -> str:
        for row in list(normalized_capability_hints or []):
            if not isinstance(row, dict):
                continue
            capability_id = str(row.get("capability_id") or "").strip().lower()
            if capability_id:
                return capability_id
        return ""

    @classmethod
    def _normalize_domain_code(cls, value: Any) -> str:
        return normalizar_codigo_dominio(value)

    @staticmethod
    def _merge_ranked(
        *,
        base: list[dict[str, Any]],
        llm_items: list[dict[str, Any]],
        key_name: str | None = None,
    ) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen: set[str] = set()

        def _key(row: dict[str, Any]) -> str:
            if key_name:
                return str(row.get(key_name) or "").strip().lower()
            for candidate in ("domain", "intent", "capability_id", "filter"):
                value = str(row.get(candidate) or "").strip().lower()
                if value:
                    return value
            return ""

        for row in [*list(llm_items or []), *list(base or [])]:
            if not isinstance(row, dict):
                continue
            key = _key(row)
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(dict(row))
        return merged

    @staticmethod
    def _build_ambiguities(
        *,
        candidate_domains: list[dict[str, Any]],
        candidate_intents: list[dict[str, Any]],
        candidate_filters: list[dict[str, Any]],
        conflict_qi_vs_legacy: bool,
    ) -> list[dict[str, Any]]:
        ambiguities: list[dict[str, Any]] = []
        if len(candidate_domains) > 1:
            first = float((candidate_domains[0] if candidate_domains else {}).get("confidence") or 0.0)
            second = float((candidate_domains[1] if len(candidate_domains) > 1 else {}).get("confidence") or 0.0)
            if abs(first - second) <= 0.12:
                ambiguities.append(
                    {
                        "type": "domain_close_scores",
                        "top_domains": [candidate_domains[0], candidate_domains[1]],
                    }
                )
        if len(candidate_intents) > 1:
            first_i = float((candidate_intents[0] if candidate_intents else {}).get("confidence") or 0.0)
            second_i = float((candidate_intents[1] if len(candidate_intents) > 1 else {}).get("confidence") or 0.0)
            if abs(first_i - second_i) <= 0.1:
                ambiguities.append(
                    {
                        "type": "intent_close_scores",
                        "top_intents": [candidate_intents[0], candidate_intents[1]],
                    }
                )
        if conflict_qi_vs_legacy:
            ambiguities.append({"type": "qi_legacy_conflict"})
        estado_values = {
            str(row.get("value") or "").strip().upper()
            for row in list(candidate_filters or [])
            if str(row.get("filter") or "").strip().lower() == "estado"
        }
        if len(estado_values) > 1:
            ambiguities.append(
                {
                    "type": "state_filter_conflict",
                    "values": sorted(list(estado_values)),
                }
            )
        return ambiguities

    @staticmethod
    def _safe_json(raw: str) -> dict[str, Any]:
        text = str(raw or "").strip()
        if not text:
            return {}
        match = re.search(r"\{.*\}", text, re.DOTALL)
        body = match.group(0) if match else text
        try:
            payload = json.loads(body)
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass
        return {}

    @classmethod
    def _has_employee_inactive_signal(cls, query: str) -> bool:
        return bool(cls._EMPLOYEE_INACTIVE_SIGNAL_RE.search(str(query or "")))

    @classmethod
    def _has_employee_active_signal(cls, query: str) -> bool:
        return bool(cls._EMPLOYEE_ACTIVE_SIGNAL_RE.search(str(query or "")))

    @classmethod
    def _has_temporal_reference(cls, query: str) -> bool:
        return bool(cls._TEMPORAL_REFERENCE_RE.search(str(query or "")))

    @classmethod
    def _has_employee_status_metric_signal(cls, query: str) -> bool:
        text = str(query or "")
        if re.search(r"\b(egresos|retiros|desvinculaciones|bajas|rotacion|rotaciones)\b", text):
            return True
        if cls._has_employee_inactive_signal(text) and cls._has_temporal_reference(text):
            return True
        if cls._has_employee_active_signal(text) and cls._has_temporal_reference(text):
            return True
        return False

    @staticmethod
    def _normalize_text(value: Any) -> str:
        lowered = str(value or "").strip().lower()
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
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean

    @staticmethod
    def _record_event(
        *,
        observability,
        run_context: RunContext | None,
        event_type: str,
        meta: dict[str, Any],
    ) -> None:
        if observability is None or not hasattr(observability, "record_event"):
            return
        observability.record_event(
            event_type=event_type,
            source="SemanticNormalizationService",
            meta={
                "run_id": getattr(run_context, "run_id", ""),
                "trace_id": getattr(run_context, "trace_id", ""),
                **dict(meta or {}),
            },
        )
