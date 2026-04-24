from __future__ import annotations

from typing import Any


DOMINIOS_OPERATIVOS_CANONICOS = frozenset({"empleados", "ausentismo", "transporte"})
DOMINIOS_META = frozenset({"general", "legacy", "knowledge"})

_ALIAS_DOMINIOS = {
    "attendance": "ausentismo",
    "ausentismo": "ausentismo",
    "asistencia": "ausentismo",
    "empleados": "empleados",
    "empleado": "empleados",
    "employee": "empleados",
    "employees": "empleados",
    "rrhh": "empleados",
    "personal": "empleados",
    "transport": "transporte",
    "transporte": "transporte",
    "knowledge": "knowledge",
    "legacy": "legacy",
    "general": "general",
}

_AGENTES_POR_DOMINIO = {
    "ausentismo": "ausentismo_agent",
    "empleados": "empleados_agent",
    "transporte": "transport_agent",
    "knowledge": "analista_agent",
    "general": "analista_agent",
    "legacy": "analista_agent",
}

_INTENCIONES_LEGACY = {
    "attendance_query": "query",
    "attendance_recurrence": "recurrence",
    "ausentismo_query": "query",
    "ausentismo_recurrencia": "recurrence",
    "empleados_query": "query",
    "transport_query": "query",
    "transporte_query": "query",
    "general_question": "query",
}


def normalizar_codigo_dominio(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    return str(_ALIAS_DOMINIOS.get(raw) or raw)


def normalizar_dominio_operativo(value: Any, *, fallback: str = "general") -> str:
    normalized = normalizar_codigo_dominio(value)
    if not normalized:
        return fallback
    if normalized in DOMINIOS_OPERATIVOS_CANONICOS or normalized in DOMINIOS_META:
        return normalized
    return fallback


def es_dominio_operativo(value: Any) -> bool:
    return normalizar_codigo_dominio(value) in DOMINIOS_OPERATIVOS_CANONICOS


def dominio_desde_capacidad(capability_id: Any) -> str:
    capability = str(capability_id or "").strip().lower()
    if not capability:
        return ""
    prefix = capability.split(".", 1)[0] if "." in capability else capability
    return normalizar_codigo_dominio(prefix)


def es_capacidad_de_dominio_operativo(capability_id: Any) -> bool:
    return es_dominio_operativo(dominio_desde_capacidad(capability_id))


def agente_desde_dominio(domain: Any, *, fallback: str = "analista_agent") -> str:
    normalized = normalizar_codigo_dominio(domain)
    if not normalized:
        return fallback
    return str(_AGENTES_POR_DOMINIO.get(normalized) or fallback)


def inferir_intencion_desde_capacidad(capability_id: Any) -> str:
    capability = str(capability_id or "").strip().lower()
    if not capability:
        return ""
    if capability.startswith("empleados.count."):
        return "count"
    if capability.startswith("empleados.detail."):
        return "detail"
    if capability.startswith("attendance.recurrence."):
        return "recurrence"
    if capability.startswith("attendance.trend."):
        return "trend"
    if capability.startswith("attendance.summary.by_"):
        return "aggregate"
    if capability.startswith("attendance.unjustified.table"):
        return "detail"
    if capability.startswith("attendance.unjustified.summary"):
        return "count"
    if capability.startswith("knowledge.proposal."):
        return "knowledge_change_request"
    return ""


def normalizar_intencion_comparable(
    value: Any,
    *,
    domain: Any = "",
    capability_id: Any = "",
) -> str:
    intent = str(value or "").strip().lower()
    inferred = inferir_intencion_desde_capacidad(capability_id)
    normalized_domain = normalizar_codigo_dominio(domain)

    if intent in _INTENCIONES_LEGACY:
        if inferred:
            return inferred
        if intent in {"attendance_recurrence", "ausentismo_recurrencia"}:
            return "recurrence"
        if normalized_domain == "empleados":
            return "count"
        return str(_INTENCIONES_LEGACY[intent])

    if intent in {
        "count",
        "detail",
        "aggregate",
        "trend",
        "compare",
        "summary",
        "recurrence",
        "knowledge_change_request",
    }:
        if intent == "summary" and inferred:
            return inferred
        return intent

    if intent.endswith("_query"):
        return inferred or "query"

    return inferred or intent


def intenciones_son_compatibles(
    expected: Any,
    actual: Any,
    *,
    expected_capability_id: Any = "",
    actual_capability_id: Any = "",
    domain: Any = "",
) -> bool:
    normalized_expected = normalizar_intencion_comparable(
        expected,
        domain=domain,
        capability_id=expected_capability_id,
    )
    normalized_actual = normalizar_intencion_comparable(
        actual,
        domain=domain,
        capability_id=actual_capability_id,
    )
    if not normalized_expected:
        return True
    if not normalized_actual:
        return False
    if normalized_expected == normalized_actual:
        return True
    if "query" in {normalized_expected, normalized_actual}:
        return True
    if {normalized_expected, normalized_actual} == {"summary", "count"}:
        return True
    return False
