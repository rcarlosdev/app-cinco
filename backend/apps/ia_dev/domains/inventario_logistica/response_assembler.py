from __future__ import annotations

from typing import Any


def _inventory_type_scope_label(filters: dict[str, Any], raw_query: str) -> str:
    tipo_filter = filters.get("tipo")
    if isinstance(tipo_filter, (list, tuple, set)):
        normalized = {str(value or "").strip().lower() for value in tipo_filter if str(value or "").strip()}
        if normalized == {"material", "ferretero"}:
            return "material claro y ferretero"
    elif str(tipo_filter or "").strip().lower() == "material":
        return "material claro"
    elif str(tipo_filter or "").strip().lower() == "ferretero":
        return "ferretero"
    if "material claro" in raw_query or "material de claro" in raw_query:
        return "material claro"
    if "material ferretero" in raw_query or "ferretero" in raw_query:
        return "ferretero"
    if "material" in raw_query:
        return "material claro y ferretero"
    return "materiales"


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
        filters = dict(inventory.get("filters") or query_intent.get("filters") or {})
        bodega = str(filters.get("bodega") or "").strip()
        movil = str(filters.get("movil") or "").strip()
        template_id = str(query_intent.get("template_id") or "")
        raw_query = str((query_intent.get("raw_query") or "")).lower()
        material_scope_label = _inventory_type_scope_label(filters=filters, raw_query=raw_query)
        first_row = rows[0] if isinstance(rows[0], dict) else {}
        row_keys = {str(key) for row in rows if isinstance(row, dict) for key in row.keys()}
        invalid_count = 0
        zero_stock = 0
        for row in rows:
            try:
                invalid_count += int(row.get("registros_cantidad_invalida") or 0)
            except Exception:
                pass
            try:
                if float(row.get("saldo_bodega") or 0) == 0:
                    zero_stock += 1
            except Exception:
                pass
        if {"consumo_ultimos_8_dias", "umbral_3_dias", "estado_critico"} <= row_keys:
            scope = f" en {bodega}" if bodega else ""
            dato = (
                f"Se identificaron {len(rows)} materiales criticos por empleado{scope}. "
                "La criticidad se calculo con consumo de los ultimos 8 dias y cobertura estimada de 3 dias."
            )
            hallazgo = "Cada fila muestra cedula, movil, codigo, saldo actual, consumo reciente y umbral operativo."
            riesgo = "Los materiales marcados como CRITICO no cubren tres dias de operacion con el ritmo reciente de consumo."
            recomendacion = "Prioriza reposicion o redistribucion sobre los codigos con mayor brecha frente al umbral."
            siguiente_accion = "Si quieres, puedo resumirlo por movil o mostrar solo los tecnicos con mayor brecha."
        elif {"fecha", "tipo_movimiento", "codigo", "descripcion", "tipo", "cedula", "empleado", "movil", "cantidad", "efecto", "saldo_movimiento"} <= row_keys:
            codigo_scope = str(filters.get("codigo") or "").strip()
            cedula_scope = str(filters.get("cedula") or "").strip()
            if not codigo_scope:
                codigos = {
                    str((row or {}).get("codigo") or "").strip()
                    for row in rows
                    if str((row or {}).get("codigo") or "").strip()
                }
                if len(codigos) == 1:
                    codigo_scope = next(iter(codigos))
            if not cedula_scope:
                cedulas = {
                    str((row or {}).get("cedula") or "").strip()
                    for row in rows
                    if str((row or {}).get("cedula") or "").strip()
                }
                if len(cedulas) == 1:
                    cedula_scope = next(iter(cedulas))
            if codigo_scope and cedula_scope:
                dato = f"Se consolido el kardex del codigo {codigo_scope} para el empleado {cedula_scope}."
            elif cedula_scope:
                dato = f"Se consolido el kardex del empleado {cedula_scope}."
            else:
                dato = (
                    "Se consolido el kardex operativo por empleado y codigo. "
                    f"El detalle conserva fecha, movimiento, codigo, cantidad y efecto sobre saldo de {material_scope_label}."
                )
            hallazgo = (
                "Cada fila muestra fecha, tipo de movimiento, codigo, descripcion, tipo, cedula, empleado, movil, "
                "estado_empleado, bodega, orden_trabajo, ticket, entrada, salida, cantidad, efecto y saldo_movimiento."
            )
            if "serializados_employee_kardex_not_available" in limitations:
                hallazgo += " El bloque serializado no se incluyo porque no hay trazabilidad cronologica confiable por cedula."
            riesgo = (
                "El saldo se calcula como corrida cronologica ascendente por codigo dentro de los movimientos auditados del empleado, "
                "aunque la visualizacion pueda ordenarse descendente."
            )
            recomendacion = "Revisa primero consumos, cobros o devoluciones atipicas para detectar descuadres operativos."
            siguiente_accion = "Si quieres, puedo filtrar el kardex por codigo o resumirlo por tipo de material."
        elif {"codigo", "descripcion", "tipo", "cedula", "movil", "saldo"} <= row_keys:
            scope = f" en {bodega}" if bodega else ""
            if "por cuadrilla" in raw_query:
                dato = (
                    f"Se consolidaron {len(rows)} registros de inventario por cuadrilla, empleado y codigo{scope}. "
                    f"Cada fila conserva el detalle de {material_scope_label}."
                )
            else:
                dato = (
                    f"Se consolidaron {len(rows)} saldos de {material_scope_label} por tecnico y codigo{scope}. "
                    "El resultado conserva el detalle por cedula y codigo."
                )
            hallazgo = (
                "Cada fila muestra codigo, descripcion, tipo, cedula, empleado, movil, "
                "entregas, devoluciones, consumos, cobros y saldo. "
                "Se conservan saldos positivos, cero y negativos cuando existan."
            )
            riesgo = "No se devolvio un saldo agregado por empleado o cuadrilla; el saldo operativo se conserva por codigo."
            recomendacion = "Revisa primero codigos con saldo negativo, cero o movimientos atipicos para priorizar control operativo."
            siguiente_accion = "Si quieres, puedo filtrar por una cedula, movil o codigo puntual para revisar el detalle."
        elif {"codigo", "descripcion", "tipo", "saldo_movil"} <= row_keys:
            employee_scope = [item.strip() for item in str(first_row.get("cedulas_relacionadas") or "").split(";") if item.strip()]
            if movil and employee_scope:
                dato = (
                    f"Se encontraron {len(employee_scope)} empleados asociados a la movil {movil}. "
                    f"El inventario de {material_scope_label} se calculo por codigo usando esas cedulas oficiales."
                )
            elif movil:
                dato = f"Se calculo el inventario de {material_scope_label} de la movil {movil} por codigo."
            else:
                dato = f"Se obtuvieron {len(rows)} codigos con saldo de {material_scope_label} en el alcance consultado."
            hallazgo = f"Cada fila muestra codigo, descripcion, tipo, movimientos y saldo actual de {material_scope_label}."
            riesgo = "El saldo mostrado es operativo por codigo; no representa un saldo global agregado engañoso."
            recomendacion = "Valida primero los codigos con saldo negativo o con movimientos atipicos."
            siguiente_accion = "Si quieres, puedo resumir el mismo alcance por tecnico o abrir el detalle de un codigo puntual."
        if not dato and (
            business_concept == "stock_bodega" or str(query_intent.get("template_id") or "") == "inventory_material_stock_by_warehouse"
        ):
            scope = f": {bodega}" if bodega else ""
            dato = (
                f"Saldo de bodega{scope}. Calcule {len(rows)} codigos con movimientos auditados de materiales: "
                "entradas - entregas + devoluciones - cobros - traslados a otro aliado, "
                "considerando traslados de bodega segun el doble registro confirmado."
            )
            hallazgo = (
                f"Registros con cantidad invalida: {invalid_count}. "
                f"Codigos sin stock en el resultado: {zero_stock}."
            )
            riesgo = "La facturacion no se uso para descontar inventario."
            recomendacion = "Revisar primero los saldos negativos y los registros con cantidad invalida."
            siguiente_accion = "Pide el detalle de un codigo o exporta el resultado si necesitas conciliacion operativa."
        elif not dato:
            dato = f"Se obtuvieron {len(rows)} registros relevantes para inventario."
            hallazgo = "La consulta se resolvio con metadata estructural validada antes de ejecutar SQL."
            recomendacion = "Usa un desglose adicional por bodega, movil, cedula o estado para priorizar accion."
            siguiente_accion = "Solicita el detalle o un agrupado por la dimension operativa que quieras revisar."
    elif limitations:
        dato = "La intencion del negocio se entendio, pero no es seguro responder con SQL productivo aun."
        hallazgo = "; ".join(limitations[:3])
        riesgo = "Responder sin validacion estructural podria inventar saldo, identificadores operativos o trazabilidad."
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
