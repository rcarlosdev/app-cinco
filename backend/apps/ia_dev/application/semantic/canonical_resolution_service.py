from __future__ import annotations

import re
import unicodedata
from typing import Any

from apps.ia_dev.application.context.run_context import RunContext
from apps.ia_dev.application.contracts.query_intelligence_contracts import (
    CanonicalResolvedQuery,
)
from apps.ia_dev.application.taxonomia_dominios import (
    normalizar_codigo_dominio,
    normalizar_intencion_comparable,
    normalizar_dominio_operativo,
    dominio_desde_capacidad,
)


class CanonicalResolutionService:
    """
    Servicio de reconciliacion canonica de señales semanticas.
    No altera el resultado final del runtime en esta fase.
    """

    def resolve(
        self,
        *,
        raw_query: str,
        semantic_normalization_output: dict[str, Any] | None,
        semantic_context: dict[str, Any] | None,
        memory_hints: dict[str, Any] | None,
        session_context: dict[str, Any] | None,
        base_classification: dict[str, Any] | None,
        capability_hints: list[dict[str, Any]] | None,
        legacy_hints: dict[str, Any] | None,
        run_context: RunContext | None = None,
        observability=None,
    ) -> CanonicalResolvedQuery:
        normalized_query = self._normalize_text(raw_query)
        semantic_norm = dict(semantic_normalization_output or {})
        context = dict(semantic_context or {})
        hints = dict(memory_hints or {})
        session = dict(session_context or {})
        base = dict(base_classification or {})
        legacy = dict(legacy_hints or {})
        capabilities = [dict(item) for item in list(capability_hints or []) if isinstance(item, dict)]

        canonical_query = str(semantic_norm.get("canonical_query") or normalized_query).strip()
        candidate_domains = [
            dict(item)
            for item in list(semantic_norm.get("candidate_domains") or [])
            if isinstance(item, dict)
        ]
        candidate_intents = [
            dict(item)
            for item in list(semantic_norm.get("candidate_intents") or [])
            if isinstance(item, dict)
        ]
        entities = [
            dict(item)
            for item in list(semantic_norm.get("candidate_entities") or [])
            if isinstance(item, dict)
        ]
        filters = [
            dict(item)
            for item in list(semantic_norm.get("candidate_filters") or [])
            if isinstance(item, dict)
        ]
        resolution_evidence: list[dict[str, Any]] = []
        conflicts: list[dict[str, Any]] = []

        selected_domain = "general"
        selected_intent = ""
        selected_capability = ""

        # 1) capability exact match
        exact_capability = self._exact_capability(capabilities)
        if exact_capability:
            capability_id = str(exact_capability.get("capability_id") or "").strip().lower()
            selected_capability = capability_id
            selected_domain = self._domain_from_capability(capability_id) or selected_domain
            resolution_evidence.append(
                {
                    "source": "capability_exact_match",
                    "precedence": 1,
                    "domain": selected_domain,
                    "capability": capability_id,
                    "confidence": 0.96,
                }
            )

        # 2) dictionary + semantic aliases
        dictionary_domain, dictionary_confidence = self._dictionary_domain_signal(
            query=canonical_query,
            semantic_context=context,
            semantic_aliases=list(semantic_norm.get("semantic_aliases") or []),
        )
        if dictionary_domain:
            resolution_evidence.append(
                {
                    "source": "dictionary_aliases",
                    "precedence": 2,
                    "domain": dictionary_domain,
                    "confidence": dictionary_confidence,
                }
            )
            if selected_domain == "general":
                selected_domain = dictionary_domain

        # 3) session/user memory
        memory_domain = self._memory_domain_signal(
            memory_hints=hints,
            session_context=session,
        )
        if memory_domain:
            resolution_evidence.append(
                {
                    "source": "session_user_memory",
                    "precedence": 3,
                    "domain": memory_domain,
                    "confidence": 0.72,
                }
            )
            if selected_domain == "general":
                selected_domain = memory_domain

        # 4) semantic normalization
        semantic_domain = normalizar_codigo_dominio(
            (candidate_domains[0] if candidate_domains else {}).get("domain")
        )
        semantic_intent = normalizar_intencion_comparable(
            (candidate_intents[0] if candidate_intents else {}).get("intent"),
            domain=semantic_domain,
            capability_id=selected_capability,
        )
        semantic_confidence = float(semantic_norm.get("confidence") or 0.0)
        if semantic_domain:
            resolution_evidence.append(
                {
                    "source": "semantic_normalization",
                    "precedence": 4,
                    "domain": semantic_domain,
                    "intent": semantic_intent,
                    "confidence": semantic_confidence,
                    "llm_invoked": bool(semantic_norm.get("llm_invoked")),
                }
            )
            if selected_domain == "general":
                selected_domain = semantic_domain
        if semantic_intent:
            selected_intent = semantic_intent

        # 5) legacy hints
        base_domain = normalizar_codigo_dominio(base.get("domain"))
        base_intent = normalizar_intencion_comparable(
            base.get("intent"),
            domain=base_domain,
            capability_id=selected_capability,
        )
        if base_domain:
            resolution_evidence.append(
                {
                    "source": "legacy_hints",
                    "precedence": 5,
                    "domain": base_domain,
                    "intent": base_intent,
                    "confidence": 0.64,
                }
            )
            if selected_domain == "general":
                selected_domain = base_domain
        if not selected_intent and base_intent:
            selected_intent = base_intent

        legacy_last_domain = normalizar_codigo_dominio(legacy.get("last_domain"))
        if legacy_last_domain and selected_domain == "general":
            selected_domain = legacy_last_domain

        # 6) general fallback
        if not selected_domain:
            selected_domain = "general"
        if not selected_intent:
            selected_intent = normalizar_intencion_comparable(
                "summary",
                domain=selected_domain,
                capability_id=selected_capability,
            ) or "summary"

        # Critical rule: do not allow general with strong specific evidence.
        strong_specific_evidence = [
            row
            for row in resolution_evidence
            if str(row.get("domain") or "").strip().lower() not in {"", "general"}
            and float(row.get("confidence") or 0.0) >= 0.72
        ]
        if selected_domain == "general" and strong_specific_evidence:
            best = sorted(strong_specific_evidence, key=lambda item: float(item.get("confidence") or 0.0), reverse=True)[0]
            selected_domain = normalizar_dominio_operativo(
                best.get("domain"),
                fallback="general",
            )
            conflicts.append(
                {
                    "type": "general_blocked_by_strong_evidence",
                    "selected_domain": selected_domain,
                    "evidence_source": str(best.get("source") or ""),
                    "evidence_confidence": float(best.get("confidence") or 0.0),
                }
            )

        # Conflict detection
        if base_domain and semantic_domain and base_domain != semantic_domain:
            conflicts.append(
                {
                    "type": "qi_vs_semantic_normalization",
                    "qi_domain": base_domain,
                    "semantic_domain": semantic_domain,
                }
            )
        if base_domain == "general" and dictionary_domain and dictionary_domain != "general":
            conflicts.append(
                {
                    "type": "legacy_vs_dictionary",
                    "legacy_domain": base_domain,
                    "dictionary_domain": dictionary_domain,
                }
            )
        if selected_capability:
            capability_domain = self._domain_from_capability(selected_capability)
            if capability_domain and capability_domain != selected_domain:
                conflicts.append(
                    {
                        "type": "capability_vs_domain",
                        "capability_domain": capability_domain,
                        "resolved_domain": selected_domain,
                        "capability_id": selected_capability,
                    }
                )
        domain_close_conflict = self._domain_close_conflict(
            candidate_domains=candidate_domains,
            semantic_ambiguities=list(semantic_norm.get("ambiguities") or []),
        )
        if domain_close_conflict:
            conflicts.append(domain_close_conflict)

        confidence = self._final_confidence(
            selected_domain=selected_domain,
            selected_capability=selected_capability,
            semantic_confidence=semantic_confidence,
            evidence=resolution_evidence,
            conflicts=conflicts,
        )

        output = CanonicalResolvedQuery(
            raw_query=str(raw_query or ""),
            canonical_query=str(canonical_query or normalized_query),
            domain_code=str(selected_domain or "general"),
            intent_code=str(selected_intent or "summary"),
            capability_code=str(selected_capability or ""),
            entities=entities,
            filters=filters,
            confidence=confidence,
            resolution_evidence=resolution_evidence,
            conflicts=conflicts,
        )

        self._record_event(
            observability=observability,
            run_context=run_context,
            event_type="canonical_resolution_completed",
            meta={
                "input": {
                    "raw_query": str(raw_query or "")[:220],
                    "base_domain": base_domain,
                    "semantic_domain": semantic_domain,
                    "capability_hints_count": len(capabilities),
                },
                "output": {
                    "domain_code": output.domain_code,
                    "intent_code": output.intent_code,
                    "capability_code": output.capability_code,
                    "confidence": output.confidence,
                },
                "conflicts": list(output.conflicts or []),
            },
        )
        return output

    @staticmethod
    def _exact_capability(capabilities: list[dict[str, Any]]) -> dict[str, Any] | None:
        for row in capabilities:
            reason = str(row.get("reason") or "").strip().lower()
            exact = bool(row.get("exact_match")) or "exact" in reason or "semantic_execution_plan_capability" in reason
            if exact and str(row.get("capability_id") or "").strip():
                return row
        return None

    @classmethod
    def _domain_from_capability(cls, capability_id: str) -> str:
        return dominio_desde_capacidad(capability_id)

    @classmethod
    def _dictionary_domain_signal(
        cls,
        *,
        query: str,
        semantic_context: dict[str, Any],
        semantic_aliases: list[dict[str, Any]],
    ) -> tuple[str, float]:
        tokens = cls._domain_token_scores()
        scores = {"empleados": 0.0, "ausentismo": 0.0}

        for term, domain in tokens.items():
            if term in query:
                scores[domain] += 0.18

        for row in semantic_aliases:
            if not isinstance(row, dict):
                continue
            canonical = cls._normalize_text(row.get("canonical"))
            for term, domain in tokens.items():
                if term and term in canonical:
                    scores[domain] += 0.16

        synonyms = list(((semantic_context.get("dictionary") or {}).get("synonyms") or []))
        for row in synonyms:
            if not isinstance(row, dict):
                continue
            term = cls._normalize_text(row.get("termino"))
            synonym = cls._normalize_text(row.get("sinonimo"))
            if term and term in query:
                for token, domain in tokens.items():
                    if token in term:
                        scores[domain] += 0.1
            if synonym and synonym in query:
                for token, domain in tokens.items():
                    if token in term or token in synonym:
                        scores[domain] += 0.1

        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        domain, score = ranked[0] if ranked else ("", 0.0)
        if score <= 0:
            return "", 0.0
        return str(domain), min(0.92, round(score, 4))

    @staticmethod
    def _memory_domain_signal(*, memory_hints: dict[str, Any], session_context: dict[str, Any]) -> str:
        hints = dict(memory_hints or {})
        session = dict(session_context or {})
        if any(str(key).startswith(("attendance", "ausentismo")) for key in hints.keys()):
            return "ausentismo"
        if any("personal_status" in str(key) for key in hints.keys()):
            return "empleados"
        last_domain = normalizar_dominio_operativo(session.get("last_domain"), fallback="")
        if last_domain in {"ausentismo", "empleados"}:
            return last_domain
        return ""

    @staticmethod
    def _domain_close_conflict(
        *,
        candidate_domains: list[dict[str, Any]],
        semantic_ambiguities: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if any(str((item or {}).get("type") or "") == "domain_close_scores" for item in semantic_ambiguities if isinstance(item, dict)):
            return {"type": "domain_close_scores", "source": "semantic_ambiguities"}
        if len(candidate_domains) < 2:
            return None
        first = float((candidate_domains[0] or {}).get("confidence") or 0.0)
        second = float((candidate_domains[1] or {}).get("confidence") or 0.0)
        if abs(first - second) <= 0.12:
            return {
                "type": "domain_close_scores",
                "top_domains": [candidate_domains[0], candidate_domains[1]],
            }
        return None

    @staticmethod
    def _final_confidence(
        *,
        selected_domain: str,
        selected_capability: str,
        semantic_confidence: float,
        evidence: list[dict[str, Any]],
        conflicts: list[dict[str, Any]],
    ) -> float:
        score = max(0.2, float(semantic_confidence or 0.0))
        if selected_capability:
            score = max(score, 0.9)
        elif selected_domain != "general":
            best = max(
                [float(item.get("confidence") or 0.0) for item in evidence if isinstance(item, dict)],
                default=0.55,
            )
            score = max(score, min(0.88, best))
        if conflicts:
            if selected_capability:
                # Con exact capability no penalizamos fuerte por conflictos secundarios
                # (ej. discrepancia QI/legacy), pero mantenemos castigo relevante para
                # conflictos criticos de resolucion.
                critical_types = {
                    "capability_vs_domain",
                    "domain_close_scores",
                    "general_blocked_by_strong_evidence",
                }
                critical_count = sum(
                    1
                    for item in list(conflicts or [])
                    if str((item or {}).get("type") or "").strip() in critical_types
                )
                non_critical_count = max(0, len(conflicts) - critical_count)
                if critical_count:
                    score -= min(0.2, (critical_count * 0.06) + (non_critical_count * 0.02))
                else:
                    score -= min(0.05, non_critical_count * 0.025)
            else:
                score -= min(0.25, len(conflicts) * 0.06)
        return max(0.05, min(1.0, round(score, 4)))

    @staticmethod
    def _domain_token_scores() -> dict[str, str]:
        return {
            "empleado": "empleados",
            "empleados": "empleados",
            "colaborador": "empleados",
            "colaboradores": "empleados",
            "personal": "empleados",
            "rrhh": "empleados",
            "ausent": "ausentismo",
            "asistenc": "ausentismo",
            "injustific": "ausentismo",
            "supervisor": "ausentismo",
            "jefe": "ausentismo",
        }

    @staticmethod
    def _normalize_text(value: Any) -> str:
        lowered = str(value or "").strip().lower()
        normalized = unicodedata.normalize("NFKD", lowered)
        clean = "".join(ch for ch in normalized if not unicodedata.combining(ch))
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
            source="CanonicalResolutionService",
            meta={
                "run_id": getattr(run_context, "run_id", ""),
                "trace_id": getattr(run_context, "trace_id", ""),
                **dict(meta or {}),
            },
        )
