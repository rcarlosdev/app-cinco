from __future__ import annotations

from typing import Any


def build_inventory_business_response(
    *,
    resolved_query: dict[str, Any],
    rows: list[dict[str, Any]] | None = None,
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    rows = list(rows or [])
    semantic_context = dict((resolved_query.get("semantic_context") or {}))
    inventory = dict((semantic_context.get("inventory_semantic_inference") or {}))
    business_concept = str(inventory.get("business_concept") or semantic_context.get("business_concept") or "")
    runtime_flow = str(
        ((semantic_context.get("resolved_semantic") or {}).get("runtime_flow_hint") or "sql_assisted")
    )
    limitations = list(limitations or ((semantic_context.get("resolved_semantic") or {}).get("limitations") or []))
    query_intent = dict(resolved_query.get("intent") or {})

    dato = ""
    hallazgo = ""
    riesgo = ""
    recomendacion = ""
    siguiente_accion = ""

    if rows:
        dato = f"Se obtuvieron {len(rows)} registros relevantes para inventario."
        hallazgo = "La consulta se resolvio con metadata estructural validada antes de ejecutar SQL."
        recomendacion = "Usa un desglose adicional por bodega, responsable o estado para priorizar accion."
        siguiente_accion = "Solicita el detalle o un agrupado por la dimension operativa que quieras revisar."
    elif limitations:
        dato = "La intencion del negocio se entendio, pero no es seguro responder con SQL productivo aun."
        hallazgo = "; ".join(limitations[:3])
        riesgo = "Responder sin validacion estructural podria inventar saldo, responsable o trazabilidad."
        recomendacion = "Valida la metadata faltante en ai_dictionary o confirma la regla de negocio pendiente."
        siguiente_accion = "Ejecuta audit_yaml_agent_against_db y luego sync_yaml_agent_to_dictionary --dry-run."
    else:
        dato = "No hubo filas para la consulta en este corte."
        hallazgo = "El runtime protegió la ejecucion con validacion estructural."
        recomendacion = "Revisa filtros, periodo o familia de material para ampliar el alcance."
        siguiente_accion = "Pide otro periodo o elimina filtros especificos."

    return {
        "dato": dato,
        "hallazgo": hallazgo,
        "riesgo_o_interpretacion": riesgo,
        "riesgo": riesgo,
        "interpretacion": riesgo,
        "recomendacion": recomendacion,
        "siguiente_accion": siguiente_accion,
        "metadata": {
            "domain": "inventario_logistica",
            "material_family": str(inventory.get("material_family") or ""),
            "intent": str(inventory.get("intent") or query_intent.get("template_id") or ""),
            "business_concept": business_concept,
            "operation": str(inventory.get("operation") or query_intent.get("operation") or ""),
            "tables_used": list(inventory.get("candidate_tables") or []),
            "fields_used": list(inventory.get("candidate_fields") or []),
            "filters": dict(inventory.get("filters") or {}),
            "group_by": list(inventory.get("group_by") or []),
            "runtime_flow": runtime_flow,
            "limitations": limitations,
            "requires_business_validation": bool(inventory.get("requires_business_validation")),
            "requires_external_source": bool(inventory.get("requires_external_source")),
            "missing_metadata": list(inventory.get("missing_metadata") or []),
            "implementation_status": str(inventory.get("implementation_status") or ""),
            "requires_threshold_metadata": bool(inventory.get("requires_threshold_metadata")),
        },
    }
