from __future__ import annotations

import re
import unicodedata
from typing import Any

from apps.ia_dev.application.taxonomia_dominios import (
    dominio_desde_capacidad,
    normalizar_codigo_dominio,
)


class IntentToCapabilityBridge:
    _ITEMIZED_TOKENS = (
        "dia a dia",
        "por ausentismo",
        "fecha por fecha",
        "registro por registro",
        "detalle por dia",
        "itemizado",
    )
    _GROUPED_TOKENS = (
        "agrupado",
        "resumen por empleado",
        "por empleado",
    )
    _SUMMARY_TOKENS = (
        "resumen",
        "kpi",
        "totales",
        "total de",
        "cantidad",
        "numero",
        "cuantos",
        "cuantas",
    )
    _TABLE_TOKENS = (
        "tabla",
        "lista",
        "detalle",
        "mostrar",
    )
    _PERSONAL_TOKENS = (
        "empleado",
        "personal",
        "supervisor",
        "area",
        "cargo",
        "nombre",
        "apellido",
    )
    _TRANSPORT_TOKENS = (
        "transporte",
        "ruta",
        "movilidad",
        "vehiculo",
        "vehiculos",
        "salieron",
        "salidas",
    )
    _EMPLOYEES_TOKENS = (
        "empleado",
        "empleados",
        "personal",
        "colaborador",
        "colaboradores",
        "cedula",
        "cedulas",
        "rrhh",
        "recurso humano",
        "recursos humanos",
        "movil",
    )
    _TURNOVER_TOKENS = (
        "rotacion",
        "rotaciones",
        "turnover",
    )
    _ACTIVE_STATUS_TOKENS = (
        "activo",
        "activos",
        "empleados activos",
        "habilitado",
        "habilitados",
        "vigente",
        "vigentes",
    )
    _TREND_TOKENS = (
        "tendencia",
        "evolucion",
        "comportamiento",
        "historico",
        "historica",
    )
    _MONTHLY_TOKENS = (
        "mensual",
        "por mes",
        "mes a mes",
        "mes anterior",
        "ultimo mes",
        "ultimos meses",
    )
    _DAILY_TOKENS = (
        "diaria",
        "diario",
        "por dia",
        "dia a dia",
    )
    _CHART_TOKENS = (
        "grafica",
        "grafico",
        "chart",
        "linea",
        "barras",
        "barra",
    )
    _ANALYTICS_TOKENS = (
        "comparativo",
        "distribucion",
        "top",
        "cantidad",
        "total",
        "resumen",
        "concentra",
        "concentran",
        "concentracion",
    )
    _BY_SUPERVISOR_TOKENS = (
        "por supervisor",
        "supervisor",
        "supervisores",
        "jefe directo",
        "jefe",
        "jefes",
        "lider",
        "lideres",
    )
    _BY_AREA_TOKENS = (
        "por area",
        "area",
        "areas",
    )
    _BY_CARGO_TOKENS = (
        "por cargo",
        "cargo",
    )
    _BY_CARPETA_TOKENS = (
        "por carpeta",
        "carpeta",
    )
    _BY_TIPO_LABOR_TOKENS = (
        "por labor",
        "labor",
        "labores",
        "por tipo labor",
        "tipo labor",
        "por tipo de labor",
        "tipo de labor",
    )
    _BY_CENTRO_COSTO_TOKENS = (
        "por centro de costo",
        "centro de costo",
        "centros de costo",
        "por centro costo",
        "centro costo",
        "por cc",
        " cc",
    )
    _BY_JUSTIFICACION_TOKENS = (
        "por justificacion",
        "justificacion",
        "por motivo",
        "motivo",
        "por causa",
        "causa",
    )
    _BY_TIPO_TOKENS = (
        "por tipo",
        "tipo",
        "por estado",
        "estado",
    )
    _COMPARATIVE_TOKENS = (
        "comparativo",
        "comparar",
        "vs",
        "versus",
        "contra",
    )
    _DISTRIBUTION_TOKENS = (
        "distribucion",
        "distribucion porcentual",
        "participacion",
        "participacion porcentual",
    )
    _TOP_TOKENS = (
        "top",
        "top 5",
        "top 10",
    )

    @staticmethod
    def _normalize(text: str) -> str:
        lowered = str(text or "").strip().lower()
        normalized = unicodedata.normalize("NFKD", lowered)
        return "".join(ch for ch in normalized if not unicodedata.combining(ch))

    def resolve(
        self,
        *,
        message: str,
        classification: dict[str, Any],
    ) -> dict[str, Any]:
        msg = self._normalize(message)
        intent = str(classification.get("intent") or "general_question")
        domain = normalizar_codigo_dominio(classification.get("domain") or "general")
        output_mode = str(classification.get("output_mode") or "summary")
        needs_database = bool(classification.get("needs_database"))
        used_tools = list(classification.get("used_tools") or [])
        needs_personal_join = bool(classification.get("needs_personal_join"))
        mentions_attendance = any(
            token in msg for token in ("ausent", "asistenc", "injustific", "justific", "incapacidad", "vacaciones")
        )
        canonical_alignment = dict(classification.get("canonical_alignment") or {})
        canonical_safe = bool(canonical_alignment.get("safe"))
        canonical_capability_hint = str(canonical_alignment.get("capability_hint") or "").strip()
        canonical_domain_hint = str(canonical_alignment.get("domain_hint") or "").strip().lower()
        canonical_intent_hint = str(canonical_alignment.get("intent_hint") or "").strip().lower()
        if canonical_safe and canonical_capability_hint:
            return {
                "capability_id": canonical_capability_hint,
                "reason": "legacy_bridge_aligned_from_canonical_capability",
                "source_intent": canonical_intent_hint or intent,
                "source_domain": canonical_domain_hint or domain,
                "output_mode": output_mode,
                "needs_database": needs_database,
            }
        if canonical_safe and canonical_domain_hint and canonical_domain_hint not in {"general", "legacy"}:
            domain = normalizar_codigo_dominio(canonical_domain_hint)
            if canonical_intent_hint:
                intent = canonical_intent_hint

        capability_id = "legacy.passthrough.v1"
        reason = "fallback_to_legacy"

        if intent == "attendance_period_probe":
            capability_id = "attendance.period.resolve.v1"
            reason = "legacy_intent_match_attendance_period_probe"
        elif intent == "knowledge_change_request":
            capability_id = "knowledge.proposal.create.v1"
            reason = "legacy_intent_match_knowledge_change_request"
        elif domain == "ausentismo" or mentions_attendance:
            wants_itemized = any(token in msg for token in self._ITEMIZED_TOKENS)
            wants_grouped = any(token in msg for token in self._GROUPED_TOKENS)
            wants_summary = any(token in msg for token in self._SUMMARY_TOKENS)
            wants_table = any(token in msg for token in self._TABLE_TOKENS)
            wants_chart = any(token in msg for token in self._CHART_TOKENS)
            wants_trend = any(token in msg for token in self._TREND_TOKENS)
            wants_monthly = any(token in msg for token in self._MONTHLY_TOKENS)
            wants_daily = any(token in msg for token in self._DAILY_TOKENS)
            wants_analytics = wants_chart or wants_trend or any(
                token in msg for token in self._ANALYTICS_TOKENS
            )
            wants_by_supervisor = any(token in msg for token in self._BY_SUPERVISOR_TOKENS)
            wants_by_area = any(token in msg for token in self._BY_AREA_TOKENS)
            wants_by_cargo = any(token in msg for token in self._BY_CARGO_TOKENS)
            wants_by_carpeta = any(token in msg for token in self._BY_CARPETA_TOKENS)
            wants_by_tipo_labor = any(token in msg for token in self._BY_TIPO_LABOR_TOKENS)
            wants_by_centro_costo = any(token in msg for token in self._BY_CENTRO_COSTO_TOKENS)
            wants_by_justificacion = any(token in msg for token in self._BY_JUSTIFICACION_TOKENS)
            wants_by_tipo = any(token in msg for token in self._BY_TIPO_TOKENS)
            wants_group_dimension = any(
                (
                    wants_by_supervisor,
                    wants_by_area,
                    wants_by_cargo,
                    wants_by_carpeta,
                    wants_by_tipo_labor,
                    wants_by_centro_costo,
                    wants_by_justificacion,
                    wants_by_tipo,
                )
            )
            contextual_reference = bool(classification.get("contextual_reference"))
            last_group_dimension_key = str(classification.get("last_group_dimension_key") or "").strip().lower()
            wants_personal_join = needs_personal_join or any(
                token in msg for token in self._PERSONAL_TOKENS
            )
            is_recurrence = (
                "get_attendance_recurrent_unjustified_with_supervisor" in used_tools
                or intent in {"attendance_recurrence", "ausentismo_recurrencia"}
                or "reincid" in msg
            )

            if is_recurrence:
                wants_itemized = (
                    wants_itemized
                    or "get_attendance_unjustified_with_personal" in used_tools
                )
                if wants_grouped and not wants_itemized:
                    capability_id = "attendance.recurrence.grouped.v1"
                    reason = "attendance_recurrence_grouped_detected"
                else:
                    capability_id = (
                        "attendance.recurrence.itemized.v1"
                        if wants_itemized
                        else "attendance.recurrence.grouped.v1"
                    )
                    reason = "attendance_recurrence_detected"
            elif (
                wants_chart
                and contextual_reference
                and last_group_dimension_key
                and not (wants_trend or wants_monthly or wants_daily)
            ):
                if last_group_dimension_key == "supervisor":
                    capability_id = "attendance.summary.by_supervisor.v1"
                    reason = "attendance_followup_chart_from_context_supervisor"
                elif last_group_dimension_key == "area":
                    capability_id = "attendance.summary.by_area.v1"
                    reason = "attendance_followup_chart_from_context_area"
                elif last_group_dimension_key == "cargo":
                    capability_id = "attendance.summary.by_cargo.v1"
                    reason = "attendance_followup_chart_from_context_cargo"
                else:
                    capability_id = "attendance.summary.by_attribute.v1"
                    reason = "attendance_followup_chart_from_context_attribute"
            elif wants_trend or (wants_chart and ("tendencia" in msg or "evolucion" in msg)):
                capability_id = (
                    "attendance.trend.monthly.v1"
                    if wants_monthly and not wants_daily
                    else "attendance.trend.daily.v1"
                )
                reason = "attendance_trend_detected"
            elif wants_by_supervisor and (wants_analytics or wants_summary or output_mode == "summary"):
                capability_id = "attendance.summary.by_supervisor.v1"
                reason = "attendance_summary_by_supervisor_detected"
            elif wants_by_area and (wants_analytics or wants_summary or output_mode == "summary"):
                capability_id = "attendance.summary.by_area.v1"
                reason = "attendance_summary_by_area_detected"
            elif wants_by_cargo and (wants_analytics or wants_summary or output_mode == "summary"):
                capability_id = "attendance.summary.by_cargo.v1"
                reason = "attendance_summary_by_cargo_detected"
            elif wants_group_dimension and (wants_analytics or wants_summary):
                capability_id = "attendance.summary.by_attribute.v1"
                reason = "attendance_summary_by_attribute_detected"
            elif wants_chart and not wants_table:
                capability_id = (
                    "attendance.trend.monthly.v1"
                    if wants_monthly and not wants_daily
                    else "attendance.trend.daily.v1"
                )
                reason = "attendance_chart_detected"
            elif "get_attendance_summary" in used_tools or (
                output_mode == "summary" and not wants_table
            ) or (wants_summary and not wants_table):
                capability_id = "attendance.unjustified.summary.v1"
                reason = "attendance_summary_detected"
            elif (
                "get_attendance_unjustified_with_personal" in used_tools
                or "get_attendance_detail_with_personal" in used_tools
                or wants_personal_join
            ):
                capability_id = "attendance.unjustified.table_with_personal.v1"
                reason = "attendance_table_with_personal_detected"
            else:
                capability_id = "attendance.unjustified.table.v1"
                reason = "attendance_table_detected"
        elif (
            domain in {"empleados", "rrhh"}
            or any(token in msg for token in self._EMPLOYEES_TOKENS)
            or re.search(r"\b(?:info|informacion|detalle|datos|ficha)\s+de\s+[a-z0-9_-]{3,40}\b", msg)
            or re.search(r"^\s*(?:info|informacion|detalle|datos|ficha)\s+[a-z0-9_-]{3,40}\s*$", msg)
        ):
            wants_count = any(token in msg for token in self._SUMMARY_TOKENS)
            wants_active = any(token in msg for token in self._ACTIVE_STATUS_TOKENS)
            wants_turnover = any(token in msg for token in self._TURNOVER_TOKENS)
            wants_detail = any(token in msg for token in ("detalle", "info", "informacion", "ficha", "datos"))
            has_identifier_hint = bool(
                any(token in msg for token in ("cedula", "movil", "codigo sap", "codigo_sap"))
                or re.search(r"\b\d{6,13}\b", msg)
                or re.search(r"\b(?:info|informacion|detalle|datos|ficha)\s+de\s+[a-z0-9_-]{3,40}\b", msg)
                or re.search(r"^\s*(?:info|informacion|detalle|datos|ficha)\s+[a-z0-9_-]{3,40}\s*$", msg)
            )
            wants_group_dimension = any(
                token in msg
                for token in (
                    *self._BY_SUPERVISOR_TOKENS,
                    *self._BY_AREA_TOKENS,
                    *self._BY_CARGO_TOKENS,
                    *self._BY_CARPETA_TOKENS,
                    *self._BY_TIPO_LABOR_TOKENS,
                    *self._BY_CENTRO_COSTO_TOKENS,
                )
            )
            if wants_turnover:
                capability_id = "empleados.count.active.v1"
                reason = "empleados_turnover_detected"
            elif wants_active and (wants_count or wants_group_dimension or output_mode == "summary"):
                capability_id = "empleados.count.active.v1"
                reason = "empleados_active_summary_detected"
            elif wants_detail and has_identifier_hint:
                capability_id = "empleados.detail.v1"
                reason = "empleados_detail_identifier_detected"
            elif wants_group_dimension and output_mode == "summary":
                capability_id = "empleados.count.active.v1"
                reason = "empleados_grouped_summary_default_active"
            elif wants_count:
                capability_id = "empleados.count.active.v1"
                reason = "empleados_count_default_active"
            else:
                capability_id = "general.answer.v1"
                reason = "empleados_query_without_supported_capability"
        elif not needs_database:
            capability_id = "general.answer.v1"
            reason = "legacy_general_no_database"
        elif domain == "general":
            capability_id = "general.answer.v1"
            reason = "legacy_general_domain"

        return {
            "capability_id": capability_id,
            "reason": reason,
            "source_intent": intent,
            "source_domain": domain,
            "output_mode": output_mode,
            "needs_database": needs_database,
        }

    def compare(
        self,
        *,
        classification: dict[str, Any],
        planned_capability: dict[str, Any],
    ) -> dict[str, Any]:
        intent = str(classification.get("intent") or "")
        domain = normalizar_codigo_dominio(classification.get("domain") or "general")
        capability_id = str(planned_capability.get("capability_id") or "legacy.passthrough.v1")
        capability_domain = dominio_desde_capacidad(capability_id) or "legacy"

        if capability_domain == "legacy":
            diverged = False
            reason = "legacy_passthrough"
        elif intent == "knowledge_change_request":
            diverged = capability_domain != "knowledge"
            reason = "knowledge_capability_expected"
        elif domain == "ausentismo":
            diverged = capability_domain != "ausentismo"
            reason = "ausentismo_capability_expected"
        elif domain in {"empleados", "rrhh"}:
            diverged = capability_domain != "empleados"
            reason = "empleados_capability_expected"
        elif domain == "general":
            diverged = capability_domain not in ("general", "knowledge")
            reason = "general_capability_expected"
        else:
            diverged = False
            reason = "domain_not_mapped_in_pr1"

        return {
            "legacy_intent": intent,
            "legacy_domain": domain,
            "planned_capability_id": capability_id,
            "planned_capability_domain": capability_domain,
            "diverged": bool(diverged),
            "reason": reason,
        }

    def resolve_candidates(
        self,
        *,
        message: str,
        classification: dict[str, Any],
        max_candidates: int = 4,
    ) -> list[dict[str, Any]]:
        signals = self._semantic_signals(message)
        canonical_alignment = dict(classification.get("canonical_alignment") or {})
        canonical_safe = bool(canonical_alignment.get("safe"))
        canonical_capability_hint = str(canonical_alignment.get("capability_hint") or "").strip()
        primary = self.resolve(message=message, classification=classification)
        primary["semantic_signals"] = dict(signals)
        candidates: list[dict[str, Any]] = [dict(primary)]
        if canonical_safe and canonical_capability_hint and canonical_capability_hint != str(primary.get("capability_id") or ""):
            candidates.insert(
                0,
                {
                    "capability_id": canonical_capability_hint,
                    "reason": "legacy_bridge_aligned_from_canonical_candidates",
                    "source_intent": str(classification.get("intent") or ""),
                    "source_domain": str(classification.get("domain") or "general"),
                    "output_mode": str(classification.get("output_mode") or "summary"),
                    "needs_database": bool(classification.get("needs_database")),
                    "semantic_signals": {
                        **dict(signals),
                        "canonical_alignment_applied": True,
                    },
                },
            )

        domain = normalizar_codigo_dominio(classification.get("domain"))
        needs_database = bool(classification.get("needs_database"))
        contextual_reference = bool(classification.get("contextual_reference"))
        last_group_dimension_key = str(
            classification.get("last_group_dimension_key") or ""
        ).strip().lower()

        def add(capability_id: str, reason: str) -> None:
            if not capability_id:
                return
            candidates.append(
                {
                    "capability_id": capability_id,
                    "reason": reason,
                    "source_intent": str(classification.get("intent") or ""),
                    "source_domain": str(classification.get("domain") or "general"),
                    "output_mode": str(classification.get("output_mode") or "summary"),
                    "needs_database": needs_database,
                    "semantic_signals": signals,
                }
            )

        if domain == "ausentismo":
            if (
                signals["wants_chart"]
                and contextual_reference
                and last_group_dimension_key
                and not (signals["wants_trend"] or signals["wants_monthly"] or signals["wants_daily"])
            ):
                if last_group_dimension_key == "supervisor":
                    add(
                        "attendance.summary.by_supervisor.v1",
                        "semantic_followup_chart_from_context_supervisor",
                    )
                elif last_group_dimension_key == "area":
                    add(
                        "attendance.summary.by_area.v1",
                        "semantic_followup_chart_from_context_area",
                    )
                elif last_group_dimension_key == "cargo":
                    add(
                        "attendance.summary.by_cargo.v1",
                        "semantic_followup_chart_from_context_cargo",
                    )
                else:
                    add(
                        "attendance.summary.by_attribute.v1",
                        "semantic_followup_chart_from_context_attribute",
                    )
            if signals["wants_trend"] or signals["wants_comparative"]:
                add("attendance.trend.monthly.v1", "semantic_alt_monthly_trend")
                add("attendance.trend.daily.v1", "semantic_alt_daily_trend")
            if signals["wants_chart"] and not signals["wants_trend"]:
                add("attendance.trend.daily.v1", "semantic_chart_daily_trend")
                add("attendance.trend.monthly.v1", "semantic_chart_monthly_trend")
            if signals["wants_by_supervisor"]:
                add("attendance.summary.by_supervisor.v1", "semantic_alt_group_supervisor")
            if signals["wants_by_area"]:
                add("attendance.summary.by_area.v1", "semantic_alt_group_area")
            if signals["wants_by_cargo"]:
                add("attendance.summary.by_cargo.v1", "semantic_alt_group_cargo")
            if signals["wants_group_dimension"] and not (
                signals["wants_by_supervisor"] or signals["wants_by_area"] or signals["wants_by_cargo"]
            ):
                add("attendance.summary.by_attribute.v1", "semantic_alt_group_attribute")
            if signals["wants_distribution"]:
                add("attendance.summary.by_area.v1", "semantic_distribution_area")
                add("attendance.summary.by_cargo.v1", "semantic_distribution_cargo")
            if signals["wants_top"]:
                add("attendance.summary.by_supervisor.v1", "semantic_top_supervisor")

        if domain in {"empleados", "rrhh"} or (
            signals["mentions_empleados"] and domain in {"general", "rrhh", ""}
        ):
            if signals["wants_turnover"]:
                add("empleados.count.active.v1", "semantic_empleados_turnover")
            elif signals["wants_group_dimension"]:
                add("empleados.count.active.v1", "semantic_empleados_grouped_default_active")
            elif signals["wants_count"] or signals["wants_active"]:
                add("empleados.count.active.v1", "semantic_empleados_count_active")

        if domain in {"general", "rrhh"} and needs_database and (
            signals["mentions_attendance"] or signals["wants_trend"] or signals["wants_chart"]
        ):
            # Reduce fallback erratico a general/rrhh cuando semantica sugiere ausentismo analytics.
            add("attendance.summary.by_supervisor.v1", "semantic_recovery_from_general_or_rrhh")
            if signals["wants_group_dimension"]:
                add("attendance.summary.by_attribute.v1", "semantic_recovery_attendance_group_attribute")
            add("attendance.trend.daily.v1", "semantic_recovery_attendance_trend")

        deduped: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for candidate in candidates:
            capability_id = str(candidate.get("capability_id") or "").strip()
            if not capability_id or capability_id in seen_ids:
                continue
            seen_ids.add(capability_id)
            deduped.append(candidate)
            if len(deduped) >= max(1, int(max_candidates)):
                break
        return deduped

    def _semantic_signals(self, message: str) -> dict[str, bool]:
        msg = self._normalize(message)
        return {
            "wants_chart": any(token in msg for token in self._CHART_TOKENS),
            "wants_trend": any(token in msg for token in self._TREND_TOKENS),
            "wants_count": any(token in msg for token in self._SUMMARY_TOKENS),
            "wants_monthly": any(token in msg for token in self._MONTHLY_TOKENS),
            "wants_daily": any(token in msg for token in self._DAILY_TOKENS),
            "wants_comparative": any(token in msg for token in self._COMPARATIVE_TOKENS),
            "wants_distribution": any(token in msg for token in self._DISTRIBUTION_TOKENS),
            "wants_top": any(token in msg for token in self._TOP_TOKENS),
            "wants_active": any(token in msg for token in self._ACTIVE_STATUS_TOKENS),
            "wants_turnover": any(token in msg for token in self._TURNOVER_TOKENS),
            "wants_by_supervisor": any(token in msg for token in self._BY_SUPERVISOR_TOKENS),
            "wants_by_area": any(token in msg for token in self._BY_AREA_TOKENS),
            "wants_by_cargo": any(token in msg for token in self._BY_CARGO_TOKENS),
            "wants_group_dimension": any(
                token in msg
                for token in (
                    *self._BY_SUPERVISOR_TOKENS,
                    *self._BY_AREA_TOKENS,
                    *self._BY_CARGO_TOKENS,
                    *self._BY_CARPETA_TOKENS,
                    *self._BY_JUSTIFICACION_TOKENS,
                    *self._BY_TIPO_TOKENS,
                    *self._BY_CENTRO_COSTO_TOKENS,
                )
            ),
            "mentions_attendance": any(token in msg for token in ("ausent", "asistencia", "injustific", "reincid")),
            "mentions_empleados": any(token in msg for token in self._EMPLOYEES_TOKENS),
            "mentions_transport": any(token in msg for token in self._TRANSPORT_TOKENS),
        }

    def resolve_semantic_candidates(
        self,
        *,
        resolved_query: dict[str, Any] | None,
        execution_plan: dict[str, Any] | None = None,
        max_candidates: int = 4,
    ) -> list[dict[str, Any]]:
        payload = dict(resolved_query or {})
        intent = dict(payload.get("intent") or {})
        normalized_filters = dict(payload.get("normalized_filters") or {})
        normalized_period = dict(payload.get("normalized_period") or {})
        domain = str(intent.get("domain_code") or "").strip().lower()
        template_id = str(intent.get("template_id") or "").strip().lower()
        operation = str(intent.get("operation") or "").strip().lower()
        group_by = [str(item).strip().lower() for item in list(intent.get("group_by") or []) if str(item).strip()]
        metrics = [str(item).strip().lower() for item in list(intent.get("metrics") or []) if str(item).strip()]

        if domain == "rrhh":
            domain = "empleados"

        strategy = str((execution_plan or {}).get("strategy") or "").strip().lower()
        selected_capability = str((execution_plan or {}).get("capability_id") or "").strip()
        constraints = dict((execution_plan or {}).get("constraints") or {})
        needs_database = domain not in {"general", ""}
        output_mode = "summary" if operation in {"count", "summary"} else "table"

        candidates: list[dict[str, Any]] = []

        def add(capability_id: str, reason: str) -> None:
            if not capability_id:
                return
            candidates.append(
                {
                    "capability_id": capability_id,
                    "reason": reason,
                    "source_intent": operation or "query",
                    "source_domain": domain or "general",
                    "output_mode": output_mode,
                    "needs_database": needs_database,
                    "semantic_signals": {
                        "semantic_resolved": True,
                        "template_id": template_id,
                        "strategy": strategy,
                        "group_by": list(group_by),
                        "metrics": list(metrics),
                    },
                    "query_constraints": constraints,
                }
            )

        if selected_capability:
            add(selected_capability, "semantic_execution_plan_capability")

        if domain == "empleados":
            estado = self._resolve_employee_status(normalized_filters)
            raw_query = str(intent.get("raw_query") or "").lower()
            has_identifier = bool(
                str((normalized_filters or {}).get("cedula") or "").strip()
                or str((normalized_filters or {}).get("movil") or "").strip()
                or str((normalized_filters or {}).get("codigo_sap") or "").strip()
                or str((normalized_filters or {}).get("search") or "").strip()
            )
            if "turnover_rate" in metrics or re.search(r"\b(rotacion|rotaciones|turnover)\b", raw_query):
                add("empleados.count.active.v1", "semantic_empleados_turnover")
            elif template_id == "count_entities_by_status" and estado in {"ACTIVO", "INACTIVO"}:
                add("empleados.count.active.v1", "semantic_empleados_count_by_status")
            elif template_id == "detail_by_entity_and_period" and has_identifier:
                add("empleados.detail.v1", "semantic_empleados_detail_by_identifier")
            elif template_id == "aggregate_by_group_and_period" and group_by and estado in {"ACTIVO", "INACTIVO"}:
                add("empleados.count.active.v1", "semantic_empleados_grouped_default_active")
            elif group_by and operation in {"aggregate", "compare", "summary", "count"} and estado in {"ACTIVO", "INACTIVO"}:
                add("empleados.count.active.v1", "semantic_empleados_grouped_operation")
            elif operation == "count":
                add("empleados.count.active.v1", "semantic_empleados_count_fallback")

        elif domain == "ausentismo":
            raw_query = str(intent.get("raw_query") or "").lower()
            if re.search(r"\b(reincid\w*|recurrent\w*|recurren\w*)\b", raw_query):
                add("attendance.recurrence.grouped.v1", "semantic_attendance_recurrence")
            elif template_id == "detail_by_entity_and_period":
                add("attendance.unjustified.table_with_personal.v1", "semantic_attendance_detail_by_entity")
            elif template_id == "count_records_by_period":
                add("attendance.unjustified.summary.v1", "semantic_attendance_count_by_period")
            elif template_id == "aggregate_by_group_and_period":
                if "supervisor" in group_by:
                    add("attendance.summary.by_supervisor.v1", "semantic_attendance_group_supervisor")
                elif "area" in group_by:
                    add("attendance.summary.by_area.v1", "semantic_attendance_group_area")
                elif "cargo" in group_by:
                    add("attendance.summary.by_cargo.v1", "semantic_attendance_group_cargo")
                else:
                    add("attendance.summary.by_attribute.v1", "semantic_attendance_group_attribute")
            elif template_id == "trend_by_period":
                period_label = str(normalized_period.get("label") or "").strip().lower()
                if any(token in period_label for token in ("mes", "monthly")):
                    add("attendance.trend.monthly.v1", "semantic_attendance_trend_monthly")
                else:
                    add("attendance.trend.daily.v1", "semantic_attendance_trend_daily")
            else:
                add("attendance.unjustified.summary.v1", "semantic_attendance_default")

        if not candidates:
            add("legacy.passthrough.v1", "semantic_fallback_legacy")

        deduped: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for item in candidates:
            capability_id = str(item.get("capability_id") or "").strip()
            if not capability_id or capability_id in seen_ids:
                continue
            seen_ids.add(capability_id)
            deduped.append(item)
            if len(deduped) >= max(1, int(max_candidates)):
                break
        return deduped

    @staticmethod
    def _resolve_employee_status(filters: dict[str, Any]) -> str:
        for key in ("estado", "estado_empleado"):
            value = str((filters or {}).get(key) or "").strip().upper()
            if value in {"ACTIVO", "INACTIVO"}:
                return value
        return ""
