from __future__ import annotations

import os
from typing import Any

from apps.ia_dev.application.contracts.query_intelligence_contracts import (
    QueryExecutionPlan,
    ResolvedQuerySpec,
)


class DiagnosticOrchestrator:
    @staticmethod
    def enabled() -> bool:
        raw = str(os.getenv("IA_DEV_DIAGNOSTIC_ORCHESTRATOR_ENABLED", "1") or "").strip().lower()
        return raw in {"1", "true", "yes", "on"}

    def analyze(
        self,
        *,
        message: str,
        resolved_query: ResolvedQuerySpec | None,
        execution_plan: QueryExecutionPlan | None,
        response: dict[str, Any],
        planned_capability: dict[str, Any],
        route: dict[str, Any],
        execution_meta: dict[str, Any] | None = None,
        memory_hints: dict[str, Any] | None = None,
        query_intelligence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.enabled():
            return {"enabled": False, "activated": False, "items": [], "recommended_actions": []}

        items: list[dict[str, Any]] = []
        recommended_actions: list[str] = []
        execution_payload = dict(execution_meta or {})
        hints = dict(memory_hints or {})
        qi = dict(query_intelligence or {})

        rowcount = self._response_rowcount(response=response)
        identifiers = self._extract_identifier_filters(
            resolved_query=resolved_query,
            execution_plan=execution_plan,
        )
        filters = self._collect_filter_keys(
            resolved_query=resolved_query,
            execution_plan=execution_plan,
        )
        strategy = str((execution_plan.strategy if execution_plan else "") or "").strip().lower()
        domain_code = str(
            ((resolved_query.intent.domain_code if resolved_query else "") or (execution_plan.domain_code if execution_plan else ""))
        ).strip().lower()
        capability_id = str(
            ((execution_plan.capability_id if execution_plan else "") or planned_capability.get("capability_id") or "")
        ).strip()
        canonical_comparison = dict((qi.get("canonical_resolution") or {}).get("comparison") or {})
        normalization_comparison = dict((qi.get("semantic_normalization") or {}).get("comparison") or {})
        planner_sql_authority = self._planner_sql_authority_active(
            execution_plan=execution_plan,
            route=route,
            execution_meta=execution_payload,
            response=response,
        )

        if rowcount == 0 and identifiers:
            items.append(
                self._build_item(
                    signature="empty_result_with_identifier",
                    family="empty_result",
                    severity="warning",
                    stage="post_execution",
                    summary="La consulta termino sin filas pese a usar identificadores fuertes.",
                    recommended_action="Revisar normalizacion del identificador y merges de filtros redundantes antes de concluir que no hay datos.",
                    confidence=0.88,
                    domain_code=domain_code,
                    capability_id=capability_id,
                    hypotheses=[
                        {
                            "key": "overconstrained_identifier_query",
                            "text": "La consulta puede estar sobre restringida por un filtro adicional que vacia el resultado.",
                            "status": "supported",
                            "confidence": 0.82,
                        },
                        {
                            "key": "identifier_normalization_gap",
                            "text": "El identificador puede requerir una normalizacion adicional para coincidir con el dato real.",
                            "status": "open",
                            "confidence": 0.76,
                        },
                    ],
                    evidence=[
                        self._evidence(
                            source="response",
                            finding="La respuesta final tuvo rowcount=0.",
                            confidence=0.9,
                            metadata={"rowcount": rowcount},
                        ),
                        self._evidence(
                            source="query",
                            finding="La consulta incluia identificadores explicitos.",
                            confidence=0.84,
                            metadata={"identifier_keys": sorted(identifiers), "filter_keys": sorted(filters)},
                        ),
                    ],
                )
            )
            recommended_actions.append(
                "Agregar probes automaticos de existencia y comparar identificadores compactados cuando rowcount=0 con identificadores fuertes."
            )

        if strategy == "ask_context" and identifiers:
            items.append(
                self._build_item(
                    signature="ask_context_despite_identifier",
                    family="planner_context_gap",
                    severity="warning",
                    stage="planning",
                    summary="El planner pidio contexto extra aunque la consulta ya traia identificadores fuertes.",
                    recommended_action="Revisar si el dominio o la capacidad pueden inferirse directamente desde el identificador sin interrumpir al usuario.",
                    confidence=0.79,
                    domain_code=domain_code,
                    capability_id=capability_id,
                    hypotheses=[
                        {
                            "key": "planner_missing_identifier_recipe",
                            "text": "Falta una receta de planificacion para consultas resueltas por identificador.",
                            "status": "supported",
                            "confidence": 0.79,
                        }
                    ],
                    evidence=[
                        self._evidence(
                            source="planner",
                            finding="La estrategia seleccionada fue ask_context.",
                            confidence=0.8,
                            metadata={"strategy": strategy},
                        ),
                        self._evidence(
                            source="query",
                            finding="La consulta ya tenia filtros de entidad o identificador.",
                            confidence=0.78,
                            metadata={"identifier_keys": sorted(identifiers)},
                        ),
                    ],
                )
            )
            recommended_actions.append(
                "Crear atajos de planificacion por identificador para evitar preguntas innecesarias."
            )

        if (
            not planner_sql_authority
            and (
                int(canonical_comparison.get("differences_count") or 0) > 0
                or int(normalization_comparison.get("differences_count") or 0) > 0
            )
        ):
            items.append(
                self._build_item(
                    signature="semantic_runtime_divergence",
                    family="alignment",
                    severity="warning",
                    stage="resolution",
                    summary="La resolucion semantica y la intencion final no quedaron completamente alineadas.",
                    recommended_action="Comparar dominio, intencion y filtros canonicos antes de ejecutar para evitar rutas inconsistentes.",
                    confidence=0.74,
                    domain_code=domain_code,
                    capability_id=capability_id,
                    hypotheses=[
                        {
                            "key": "semantic_alignment_gap",
                            "text": "Existe una divergencia entre la resolucion canonica y la ejecucion final.",
                            "status": "supported",
                            "confidence": 0.74,
                        }
                    ],
                    evidence=[
                        self._evidence(
                            source="canonical_resolution",
                            finding="Se detectaron diferencias entre canonical_resolution e intent.",
                            confidence=0.72,
                            metadata={"differences": list(canonical_comparison.get("differences") or [])},
                        ),
                        self._evidence(
                            source="semantic_normalization",
                            finding="La normalizacion semantica propuso señales distintas a la intencion final.",
                            confidence=0.68,
                            metadata={"differences": list(normalization_comparison.get("differences") or [])},
                        ),
                    ],
                )
            )
            recommended_actions.append(
                "Persistir firmas de divergencia y revisar alignment antes del route final."
            )

        if bool(execution_payload.get("used_legacy")) and strategy in {"capability", "sql_assisted"}:
            items.append(
                self._build_item(
                    signature="legacy_fallback_after_structured_resolution",
                    family="fallback",
                    severity="info",
                    stage="execution",
                    summary="La consulta cayo a legacy despues de haber sido resuelta de forma estructurada.",
                    recommended_action="Rastrear por que la ruta estructurada no pudo completarse y guardar la firma para evitar futuros rebotes.",
                    confidence=0.71,
                    domain_code=domain_code,
                    capability_id=capability_id,
                    hypotheses=[
                        {
                            "key": "structured_execution_gap",
                            "text": "La capacidad estructurada no cubrio completamente el caso resuelto por query intelligence.",
                            "status": "supported",
                            "confidence": 0.71,
                        }
                    ],
                    evidence=[
                        self._evidence(
                            source="execution",
                            finding="El resultado uso fallback legacy.",
                            confidence=0.78,
                            metadata={"fallback_reason": str(execution_payload.get("fallback_reason") or "")},
                        ),
                        self._evidence(
                            source="query_intelligence",
                            finding="La estrategia estructurada original era distinta de legacy.",
                            confidence=0.7,
                            metadata={"strategy": strategy},
                        ),
                    ],
                )
            )

        if bool(execution_payload) and not bool(execution_payload.get("satisfied", True)):
            items.append(
                self._build_item(
                    signature="unsatisfied_execution_result",
                    family="quality",
                    severity="warning",
                    stage="validation",
                    summary="La ejecucion no cumplio completamente la intencion del usuario.",
                    recommended_action="Analizar por que el resultado no satisfizo la consulta y registrar la causa para futuros retries.",
                    confidence=0.77,
                    domain_code=domain_code,
                    capability_id=capability_id,
                    hypotheses=[
                        {
                            "key": "result_not_answering_goal",
                            "text": "La salida obtenida no coincide con la necesidad explicita de la consulta.",
                            "status": "supported",
                            "confidence": 0.77,
                        }
                    ],
                    evidence=[
                        self._evidence(
                            source="validation",
                            finding="El validador marco la respuesta como insatisfactoria.",
                            confidence=0.8,
                            metadata={"reason": str(execution_payload.get("satisfaction_reason") or "")},
                        )
                    ],
                )
            )

        if items:
            patterns = self._match_memory_patterns(
                memory_hints=hints,
                signatures={str(item.get("signature") or "").strip().lower() for item in items},
                domain_code=domain_code,
                capability_id=capability_id,
            )
            if patterns:
                for item in items:
                    matched = [
                        dict(pattern)
                        for pattern in patterns
                        if str(pattern.get("signature") or "").strip().lower()
                        == str(item.get("signature") or "").strip().lower()
                    ]
                    if matched:
                        item["matched_memory_patterns"] = matched[:3]
                        item["confidence"] = max(
                            float(item.get("confidence") or 0.0),
                            min(0.95, float(item.get("confidence") or 0.0) + 0.07),
                        )
                        evidence = list(item.get("evidence") or [])
                        evidence.append(
                            self._evidence(
                                source="memory",
                                finding="La firma ya existe en memoria colectiva o del usuario.",
                                confidence=0.83,
                                metadata={"matches": len(matched)},
                            )
                        )
                        item["evidence"] = evidence
                recommended_actions.append(
                    "Priorizar remediaciones para firmas repetidas detectadas en memoria colectiva."
                )

        deduped_actions: list[str] = []
        for action in recommended_actions:
            text = str(action or "").strip()
            if text and text not in deduped_actions:
                deduped_actions.append(text)

        return {
            "enabled": True,
            "activated": bool(items),
            "items": items,
            "recommended_actions": deduped_actions[:5],
        }

    @staticmethod
    def _planner_sql_authority_active(
        *,
        execution_plan: QueryExecutionPlan | None,
        route: dict[str, Any],
        execution_meta: dict[str, Any],
        response: dict[str, Any],
    ) -> bool:
        if str((execution_plan.strategy if execution_plan else "") or "").strip().lower() != "sql_assisted":
            return False
        if not bool(str((execution_plan.sql_query if execution_plan else "") or "").strip()):
            return False
        if not bool((execution_plan.policy if execution_plan else {}) and (execution_plan.policy or {}).get("allowed")):
            return False
        if not bool(execution_meta.get("satisfied", True)):
            return False
        if bool(execution_meta.get("used_legacy")):
            return False
        if bool(execution_meta.get("blocked_legacy_fallback")):
            return False
        if str(execution_meta.get("runtime_only_fallback_reason") or "").strip():
            return False
        if str(execution_meta.get("fallback_reason") or "").strip():
            return False
        if bool(route.get("execute_capability")):
            return False
        classifier_source = str(((response.get("orchestrator") or {}).get("classifier_source") or "")).strip().lower()
        runtime_authority = str(route.get("runtime_authority") or "").strip().lower()
        return runtime_authority == "query_execution_planner" or "sql_assisted" in classifier_source

    @staticmethod
    def _build_item(
        *,
        signature: str,
        family: str,
        severity: str,
        stage: str,
        summary: str,
        recommended_action: str,
        confidence: float,
        domain_code: str,
        capability_id: str,
        hypotheses: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "signature": str(signature or "").strip().lower(),
            "family": str(family or "").strip().lower(),
            "severity": str(severity or "").strip().lower(),
            "stage": str(stage or "").strip().lower(),
            "summary": str(summary or "").strip(),
            "recommended_action": str(recommended_action or "").strip(),
            "confidence": max(0.0, min(float(confidence or 0.0), 1.0)),
            "domain_code": str(domain_code or "").strip().lower(),
            "capability_id": str(capability_id or "").strip(),
            "hypotheses": [dict(item or {}) for item in list(hypotheses or []) if isinstance(item, dict)],
            "evidence": [dict(item or {}) for item in list(evidence or []) if isinstance(item, dict)],
        }

    @staticmethod
    def _evidence(*, source: str, finding: str, confidence: float, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "source": str(source or "").strip().lower(),
            "finding": str(finding or "").strip(),
            "confidence": max(0.0, min(float(confidence or 0.0), 1.0)),
            "metadata": dict(metadata or {}),
        }

    @staticmethod
    def _response_rowcount(*, response: dict[str, Any]) -> int:
        data = dict((response or {}).get("data") or {})
        table = dict(data.get("table") or {})
        rows = list(table.get("rows") or [])
        return int(table.get("rowcount") or len(rows))

    @staticmethod
    def _extract_identifier_filters(
        *,
        resolved_query: ResolvedQuerySpec | None,
        execution_plan: QueryExecutionPlan | None,
    ) -> set[str]:
        identifiers: set[str] = set()
        sources = []
        if resolved_query is not None:
            sources.append(dict(resolved_query.normalized_filters or {}))
        if execution_plan is not None:
            sources.append(dict((execution_plan.constraints or {}).get("filters") or {}))
        for payload in sources:
            for key, value in payload.items():
                normalized_key = str(key or "").strip().lower()
                if normalized_key in {
                    "cedula",
                    "documento",
                    "identificacion",
                    "id_empleado",
                    "movil",
                    "codigo_sap",
                    "employee_code",
                } and str(value or "").strip():
                    identifiers.add(normalized_key)
        return identifiers

    @staticmethod
    def _collect_filter_keys(
        *,
        resolved_query: ResolvedQuerySpec | None,
        execution_plan: QueryExecutionPlan | None,
    ) -> set[str]:
        filters: set[str] = set()
        if resolved_query is not None:
            filters.update(str(key or "").strip().lower() for key in dict(resolved_query.normalized_filters or {}).keys())
        if execution_plan is not None:
            filters.update(str(key or "").strip().lower() for key in dict((execution_plan.constraints or {}).get("filters") or {}).keys())
        filters.discard("")
        return filters

    @staticmethod
    def _match_memory_patterns(
        *,
        memory_hints: dict[str, Any],
        signatures: set[str],
        domain_code: str,
        capability_id: str,
    ) -> list[dict[str, Any]]:
        matches: list[dict[str, Any]] = []
        for item in list((memory_hints or {}).get("reasoning_patterns") or []):
            if not isinstance(item, dict):
                continue
            signature = str(item.get("signature") or "").strip().lower()
            if signature not in signatures:
                continue
            pattern_domain = str(item.get("domain_code") or "").strip().lower()
            pattern_capability = str(item.get("capability_id") or "").strip()
            if pattern_domain and domain_code and pattern_domain not in {domain_code, "general"}:
                continue
            if pattern_capability and capability_id and pattern_capability != capability_id:
                continue
            matches.append(dict(item))
        return matches[:5]

