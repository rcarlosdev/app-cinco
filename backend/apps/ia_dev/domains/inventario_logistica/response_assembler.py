from __future__ import annotations

from typing import Any

from apps.ia_dev.application.orchestration.dashboard_composition_planner import (
    DashboardCompositionPlanner,
)


LIMITACIONES_DECLARADAS = {
    "external_source_pending:sap": "La fuente SAP o documental requerida no esta habilitada como fuente productiva para esta consulta.",
    "document_generation_pending": "La generacion documental o de actas todavia no esta habilitada de forma productiva.",
    "inventory_document_generation_pending": "La generacion documental o de actas todavia no esta habilitada de forma productiva.",
    "serializados_employee_kardex_not_available": (
        "La trazabilidad cronologica confiable de serializados por cedula no esta disponible para este alcance."
    ),
    "missing_physical_column:bodega_destino": (
        "La metadata gobernada todavia no expone una columna fisica segura para bodega destino."
    ),
    "scope_required:operacion_hfc": "La regla gobernada exige precisar el alcance operativo operacion_hfc.",
}

LIMITACIONES_NO_NEGOCIO = {"legacy_semantic_binding_shadowed"}
_DASHBOARD_COMPOSITION_PLANNER = DashboardCompositionPlanner()


def _inventory_type_scope_label(*, filters: dict[str, Any], semantic_plan: dict[str, Any]) -> str:
    familias = [
        str(item or "").strip().lower()
        for item in list((semantic_plan.get("scope") or {}).get("families") or [])
        if str(item or "").strip()
    ]
    familias_set = set(familias)
    if familias_set == {"material_claro", "ferretero"}:
        return "material claro y ferretero"
    if familias_set == {"material_claro"}:
        return "material claro"
    if familias_set == {"ferretero"}:
        return "ferretero"
    if familias_set == {"serializados"}:
        return "serializados"
    tipo_filter = filters.get("tipo")
    if isinstance(tipo_filter, (list, tuple, set)):
        normalized = {
            str(value or "").strip().lower()
            for value in tipo_filter
            if str(value or "").strip()
        }
        if normalized == {"material", "ferretero"}:
            return "material claro y ferretero"
    elif str(tipo_filter or "").strip().lower() == "material":
        return "material claro"
    elif str(tipo_filter or "").strip().lower() == "ferretero":
        return "ferretero"
    return "materiales"


def _output_profile(semantic_binding: dict[str, Any], semantic_plan: dict[str, Any]) -> dict[str, Any]:
    plan_output = dict(semantic_plan.get("output") or {})
    binding_output = dict(semantic_binding.get("output_profile") or {})
    return {
        "id": str(semantic_binding.get("response_profile") or ""),
        "expected_output": str(
            binding_output.get("expected_output") or plan_output.get("expected_output") or ""
        ),
        "grain": str(binding_output.get("grain") or plan_output.get("grain") or ""),
        "columns": [
            str(item or "")
            for item in list(binding_output.get("columns") or plan_output.get("columns") or [])
            if str(item or "").strip()
        ],
    }


def _limitation_text(limitations: list[str]) -> str:
    normalized = [
        str(item or "").strip()
        for item in limitations
        if str(item or "").strip() and str(item or "").strip() not in LIMITACIONES_NO_NEGOCIO
    ]
    for limitation in normalized:
        if limitation in LIMITACIONES_DECLARADAS:
            return LIMITACIONES_DECLARADAS[limitation]
    return "; ".join(normalized[:3])


def _response_status(
    *,
    clarification_question: str,
    limitations: list[str],
    main_rowcount: int,
    extra_rowcount: int,
) -> tuple[str, str]:
    if clarification_question:
        return "clarification_required", "missing_structural_context"
    if limitations and main_rowcount <= 0 and extra_rowcount <= 0:
        return "limitation_declared", "known_limitation"
    if main_rowcount > 0 or extra_rowcount > 0:
        return "success", ""
    return "empty_result", "result_set_empty"


def _semantic_trace_payload(
    *,
    semantic_binding: dict[str, Any],
    resolved_semantic: dict[str, Any],
) -> dict[str, Any]:
    binding_trace = dict(resolved_semantic.get("binding_trace") or {})
    return {
        "source": str(
            semantic_binding.get("source")
            or binding_trace.get("source")
            or ""
        ),
        "template_id": str(
            semantic_binding.get("template_id")
            or resolved_semantic.get("binding_template_id")
            or ""
        ),
        "candidate_capability": str(
            semantic_binding.get("candidate_capability")
            or resolved_semantic.get("candidate_capability")
            or ""
        ),
        "planner_route_hint": str(
            semantic_binding.get("planner_route_hint")
            or resolved_semantic.get("planner_route_hint")
            or ""
        ),
        "regla_metadata_usada": list(
            semantic_binding.get("regla_metadata_usada")
            or binding_trace.get("regla_metadata_usada")
            or []
        ),
        "fuente_dd": list(
            semantic_binding.get("fuente_dd") or binding_trace.get("fuente_dd") or []
        ),
        "fallback_sombreado_usado": bool(
            semantic_binding.get("fallback_sombreado_usado")
            or binding_trace.get("fallback_sombreado_usado")
        ),
        "fallback_used": bool(
            semantic_binding.get("fallback_used")
            or binding_trace.get("fallback_used")
        ),
        "legacy_mapping_used": bool(
            semantic_binding.get("legacy_mapping_used")
            or binding_trace.get("legacy_mapping_used")
        ),
        "regla_legacy_detectada": bool(
            semantic_binding.get("regla_legacy_detectada")
            or binding_trace.get("regla_legacy_detectada")
        ),
        "legacy_retained_reason": str(
            semantic_binding.get("legacy_retained_reason")
            or binding_trace.get("legacy_retained_reason")
            or binding_trace.get("reason")
            or ""
        ),
        "paquete_capacidad_usado": str(
            semantic_binding.get("paquete_capacidad_usado")
            or binding_trace.get("paquete_capacidad_usado")
            or ""
        ),
        "version_paquete": str(
            semantic_binding.get("version_paquete")
            or binding_trace.get("version_paquete")
            or ""
        ),
        "capacidades_declaradas": list(
            semantic_binding.get("capacidades_declaradas")
            or binding_trace.get("capacidades_declaradas")
            or []
        ),
        "reglas_declaradas": list(
            semantic_binding.get("reglas_declaradas")
            or binding_trace.get("reglas_declaradas")
            or []
        ),
        "perfiles_respuesta": list(
            semantic_binding.get("perfiles_respuesta")
            or binding_trace.get("perfiles_respuesta")
            or []
        ),
        "evaluaciones_asociadas": list(
            semantic_binding.get("evaluaciones_asociadas")
            or binding_trace.get("evaluaciones_asociadas")
            or []
        ),
    }


def _evidence_summary(
    *,
    semantic_context: dict[str, Any],
    semantic_plan: dict[str, Any],
    semantic_binding: dict[str, Any],
    rows: list[dict[str, Any]],
    supplemental_tables: list[dict[str, Any]],
    result_set: dict[str, Any],
    response_profile: dict[str, Any],
    fallback_narrativo_usado: bool,
    missing_evidence_reason: str,
) -> dict[str, Any]:
    resolved_semantic = dict(semantic_context.get("resolved_semantic") or {})
    evidence_sources_used = list(
        dict.fromkeys(
            [
                "semantic_context",
                "business_query_semantic_plan",
                "semantic_capability_registry",
                *list(semantic_binding.get("fuente_dd") or []),
                *list(semantic_binding.get("regla_metadata_usada") or []),
                *list(resolved_semantic.get("consulted_sources") or []),
                *(
                    ["result_set"]
                    if int(result_set.get("rowcount") or len(rows) or 0) > 0
                    else []
                ),
                *(
                    ["data.extra_tables"]
                    if any(
                        int(dict(item).get("rowcount") or 0) > 0
                        for item in supplemental_tables
                        if isinstance(item, dict)
                    )
                    else []
                ),
            ]
        )
    )
    semantic_trace = _semantic_trace_payload(
        semantic_binding=semantic_binding,
        resolved_semantic=resolved_semantic,
    )
    return {
        "response_profile_usado": str(response_profile.get("id") or ""),
        "evidence_sources_used": evidence_sources_used,
        "semantic_context_used": bool(semantic_context),
        "fallback_narrativo_usado": bool(fallback_narrativo_usado),
        "missing_evidence_reason": str(missing_evidence_reason or ""),
        "semantic_trace": semantic_trace,
        "result_set": {
            "rowcount": int(result_set.get("rowcount") or len(rows) or 0),
            "total_records": int(
                result_set.get("total_records") or result_set.get("rowcount") or len(rows) or 0
            ),
            "returned_records": int(
                result_set.get("returned_records") or result_set.get("rowcount") or len(rows) or 0
            ),
            "truncated": bool(result_set.get("truncated")),
        },
        "extra_tables": [
            {
                "name": str(item.get("name") or ""),
                "rowcount": int(item.get("rowcount") or 0),
                "skipped": bool(item.get("skipped")),
                "reason": str(item.get("reason") or ""),
            }
            for item in supplemental_tables
            if isinstance(item, dict)
        ],
        "output_profile": dict(response_profile),
        "entity": dict(semantic_plan.get("entity") or {}),
        "filters": dict(
            semantic_binding.get("normalized_filters")
            or resolved_semantic.get("final_filters")
            or {}
        ),
        "capability_pack": {
            "paquete_capacidad_usado": str(semantic_binding.get("paquete_capacidad_usado") or ""),
            "version_paquete": str(semantic_binding.get("version_paquete") or ""),
            "capacidades_declaradas": list(semantic_binding.get("capacidades_declaradas") or []),
            "reglas_declaradas": list(semantic_binding.get("reglas_declaradas") or []),
            "perfiles_respuesta": list(semantic_binding.get("perfiles_respuesta") or []),
            "evaluaciones_asociadas": list(semantic_binding.get("evaluaciones_asociadas") or []),
        },
    }


def _success_response(
    *,
    response_profile_id: str,
    response_profile: dict[str, Any],
    semantic_plan: dict[str, Any],
    semantic_context: dict[str, Any],
    filters: dict[str, Any],
    rows: list[dict[str, Any]],
    supplemental_tables: list[dict[str, Any]],
) -> tuple[str, str, str, str, bool]:
    entity = dict(semantic_plan.get("entity") or {})
    identifier = str(entity.get("identifier") or filters.get("movil") or filters.get("cedula") or "").strip()
    entity_field = str(entity.get("field") or "").strip().lower()
    material_scope_label = _inventory_type_scope_label(filters=filters, semantic_plan=semantic_plan)
    columns = [str(item or "") for item in list(response_profile.get("columns") or []) if str(item or "").strip()]
    limitations = list((dict(semantic_context.get("resolved_semantic") or {})).get("limitations") or [])
    serial_table = next(
        (
            item
            for item in supplemental_tables
            if isinstance(item, dict) and str(item.get("name") or "") == "serializados_equipos"
        ),
        {},
    )
    grouping_dimension = str(filters.get("grouping_dimension") or "").strip().lower()
    if not grouping_dimension:
        grouping_dimensions = [
            str(item or "").strip().lower()
            for item in list((semantic_plan.get("grouping_dimension") or []))
            if str(item or "").strip()
        ]
        for candidate in ("movil", "cedula", "bodega"):
            if candidate in grouping_dimensions:
                grouping_dimension = candidate
                break

    if response_profile_id == "inventory.kardex.employee.detail":
        codigo = str(filters.get("codigo") or "").strip()
        if codigo and identifier:
            dato = f"Se consolido el kardex del codigo {codigo} para el empleado {identifier}."
        elif identifier:
            dato = f"Se consolido el kardex del empleado {identifier}."
        else:
            dato = "Se consolido el kardex operativo del alcance consultado."
        hallazgo = (
            "La respuesta se armo desde el resultado ejecutado y conserva "
            + ", ".join(columns[:10])
            + "."
        )
        interpretacion = (
            "El saldo del kardex proviene de la corrida cronologica validada por la ejecucion, no de texto inferido."
        )
        recomendacion = "Si quieres, puedo filtrar el kardex por codigo o resumirlo por tipo de material."
        if "serializados_employee_kardex_not_available" in limitations:
            hallazgo += " La trazabilidad serializada por cedula quedo declarada como limitacion."
        return dato, hallazgo, interpretacion, recomendacion, False

    if response_profile_id in {
        "inventory.stock.mobile.detail",
        "inventory.stock.mobile.dual_block",
        "inventory.stock.critical.employee",
        "inventory.stock.dimension.summary",
    }:
        is_grouped_dimension_scope = bool(
            grouping_dimension in {"movil", "cedula", "bodega"}
            and str(entity.get("field") or "").strip().lower() not in {"movil", "cedula"}
            and not any(str(filters.get(key) or "").strip() for key in ("movil", "cedula"))
            and any(str(filters.get(key) or "").strip() for key in ("codigo", "descripcion", "tipo", "material_family"))
        )
        if response_profile_id == "inventory.stock.dimension.summary" or is_grouped_dimension_scope:
            dimension_field = grouping_dimension or "dimension"
            dimension_label = "móvil" if dimension_field == "movil" else "técnico" if dimension_field == "cedula" else "bodega"
            dimension_label_plural = "móviles" if dimension_field == "movil" else "técnicos" if dimension_field == "cedula" else "bodegas"
            material_ref = str(filters.get("codigo") or filters.get("descripcion") or material_scope_label).strip()
            total_saldo = sum(float(item.get("saldo") or 0) for item in rows if isinstance(item, dict))
            dimensiones = {
                str(
                    item.get(dimension_field)
                    or item.get("dimension")
                    or item.get("movil")
                    or item.get("cedula")
                    or item.get("bodega")
                    or ""
                ).strip()
                for item in rows
                if isinstance(item, dict)
            }
            dimensiones.discard("")
            codigos = {
                str(item.get("codigo") or "").strip()
                for item in rows
                if isinstance(item, dict) and str(item.get("codigo") or "").strip()
            }
            dato = (
                f"Consulté el saldo del material {material_ref} agrupado por {dimension_label}. "
                f"Total general: {total_saldo:g}. "
                f"{dimension_label_plural.capitalize()} con saldo: {len(dimensiones)}."
            )
            hallazgo = (
                f"La evidencia se consolidó en {len(rows)} filas agrupadas por {dimension_label} y código, "
                f"con {len(codigos)} código(s) coincidente(s)."
            )
            interpretacion = (
                "La respuesta se armó desde evidencia agregada por dimensión y no desde detalle operativo sin resumir."
            )
            recomendacion = (
                f"La tabla muestra {dimension_label}, código, descripción, tipo, entregas, devoluciones, consumos, cobros y saldo."
            )
            return dato, hallazgo, interpretacion, recomendacion, False
        scope_text = "movil" if entity_field == "movil" else "empleado"
        if response_profile_id == "inventory.stock.mobile.dual_block" and not bool(serial_table.get("skipped")):
            serial_rowcount = int(serial_table.get("rowcount") or 0)
            dato = (
                f"Se consolidaron {len(rows)} registros de {material_scope_label} y "
                f"{serial_rowcount} registros de serializados/equipos para {scope_text} {identifier}."
            ).strip()
            hallazgo = (
                "La respuesta entrega dos bloques evidenciados por la ejecucion: "
                "materiales/ferretero y serializados/equipos."
            )
            interpretacion = (
                "El alcance generico de inventario se resolvio con doble bloque porque la semantica gobernada no restringio una sola familia."
            )
            recomendacion = "Si quieres, puedo resumir cualquiera de los dos bloques por movil, cedula o codigo."
            return dato, hallazgo, interpretacion, recomendacion, False
        if identifier:
            dato = (
                f"Se consolidaron {len(rows)} registros de inventario operativo de {material_scope_label} para "
                f"{scope_text} {identifier}."
            )
        else:
            dato = f"Se consolidaron {len(rows)} registros de inventario operativo de {material_scope_label}."
        hallazgo = (
            "La respuesta conserva el grano validado por la ejecucion y muestra "
            + ", ".join(columns[:10])
            + "."
        )
        interpretacion = (
            "El inventario se presenta por evidencia operativa ejecutada; no se agrego un saldo narrativo fuera del result_set."
        )
        recomendacion = "Si quieres, puedo filtrar por cedula, movil o codigo para revisar el detalle."
        return dato, hallazgo, interpretacion, recomendacion, False

    if response_profile_id in {
        "inventory.serial.stock.dimension.summary",
        "inventory.serial.stock.dimension.detail",
    }:
        dimension_field = grouping_dimension or "dimension"
        dimension_label = "movil" if dimension_field == "movil" else "tecnico" if dimension_field == "cedula" else "bodega"
        dimension_label_plural = "moviles" if dimension_field == "movil" else "tecnicos" if dimension_field == "cedula" else "bodegas"
        family_value = str(filters.get("material_family") or "").strip()
        total_saldo = sum(float(item.get("saldo") or 0) for item in rows if isinstance(item, dict))
        total_seriales = sum(float(item.get("seriales_total") or 0) for item in rows if isinstance(item, dict))
        distinct_dimensions = {
            str(
                item.get(dimension_field)
                or item.get("dimension")
                or item.get("movil")
                or item.get("cedula")
                or item.get("bodega")
                or ""
            ).strip()
            for item in rows
            if isinstance(item, dict)
        }
        distinct_dimensions.discard("")
        distinct_codes = {
            str(item.get("codigo") or "").strip()
            for item in rows
            if isinstance(item, dict) and str(item.get("codigo") or "").strip()
        }
        subtotal_table = next(
            (
                item
                for item in supplemental_tables
                if isinstance(item, dict)
                and str(item.get("name") or "").strip().startswith("subtotales_serializados_por_")
            ),
            {},
        )
        dato = (
            f"Encontre equipos de familias del catalogo que contienen {family_value} en estado MOVIL. "
            "La tabla muestra el saldo por empleado, movil y codigo."
        ).strip()
        hallazgo = (
            f"El detalle conserva cedula, empleado, movil, estado_empleado, codigo, descripcion y familia, "
            f"con {len(distinct_codes)} codigo(s), {len(distinct_dimensions)} {dimension_label_plural} y {total_seriales:g} serial(es) en MOVIL."
        )
        if subtotal_table:
            hallazgo += f" Tambien se generaron subtotales por {dimension_label} para el dashboard."
        interpretacion = (
            "La respuesta usa la ruta serializada validada por catalogo, filtra estado MOVIL y calcula saldo por conteo, no por cantidad."
        )
        recomendacion = (
            f"Si quieres, puedo resumir la familia {family_value} por otra dimension operativa "
            "o profundizar en un movil, cuadrilla, tecnico o bodega puntual."
        )
        return dato, hallazgo, interpretacion, recomendacion, False

    if response_profile_id == "inventory.serial.holder.detail":
        dato = f"Se consolidaron {len(rows)} registros de serializados para el alcance consultado."
        hallazgo = (
            "La respuesta conserva serial, codigo, descripcion, familia, estado, cedula y movil desde el bloque ejecutado."
        )
        interpretacion = "El saldo serializado se basa en conteos y estados ejecutados, no en cantidades inferidas."
        recomendacion = "Si quieres, puedo resumirlo por estado, codigo o portador operativo."
        return dato, hallazgo, interpretacion, recomendacion, False

    if response_profile_id.endswith(".blocked") or response_profile_id.endswith(".pending"):
        dato = "La consulta quedo bloqueada por una limitacion declarada del dominio."
        hallazgo = "No se presento exito porque la metadata o la fuente requerida no permite una ejecucion confiable."
        interpretacion = "La salida informa el bloqueo declarado por la semantica gobernada."
        recomendacion = "Si quieres, puedo ayudarte a reformular la consulta dentro del alcance habilitado."
        return dato, hallazgo, interpretacion, recomendacion, False

    dato = f"Se obtuvieron {len(rows)} registros respaldados por la ejecucion para inventario_logistica."
    hallazgo = "La respuesta se armo desde plan semantico, binding gobernado y result_set."
    interpretacion = "La semantica y la ejecucion coinciden en el alcance consultado."
    recomendacion = "Si quieres, puedo profundizar el resultado por la dimension operativa que necesites."
    return dato, hallazgo, interpretacion, recomendacion, True


def build_inventory_business_response(
    *,
    resolved_query: dict[str, Any],
    rows: list[dict[str, Any]] | None = None,
    limitations: list[str] | None = None,
    supplemental_tables: list[dict[str, Any]] | None = None,
    result_set: dict[str, Any] | None = None,
    execution_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rows = list(rows or [])
    supplemental_tables = [dict(item) for item in list(supplemental_tables or []) if isinstance(item, dict)]
    result_set = dict(result_set or {})
    execution_metadata = dict(execution_metadata or {})
    semantic_context = dict((resolved_query.get("semantic_context") or {}))
    inventory = dict((semantic_context.get("inventory_semantic_inference") or {}))
    business_concept = str(
        inventory.get("business_concept") or semantic_context.get("business_concept") or ""
    )
    runtime_flow = str(
        ((semantic_context.get("resolved_semantic") or {}).get("runtime_flow_hint") or "sql_assisted")
    )
    semantic_plan = dict(semantic_context.get("business_query_semantic_plan") or {})
    semantic_binding = dict(
        semantic_context.get("semantic_capability_registry")
        or ((semantic_context.get("resolved_semantic") or {}).get("semantic_capability_registry") or {})
    )
    resolved_semantic = dict(semantic_context.get("resolved_semantic") or {})
    limitations = [
        item
        for item in list(limitations or resolved_semantic.get("limitations") or execution_metadata.get("limitations") or [])
        if str(item or "").strip() and str(item or "").strip() not in LIMITACIONES_NO_NEGOCIO
    ]
    query_intent = dict(resolved_query.get("intent") or {})
    filters = dict(
        semantic_binding.get("normalized_filters")
        or resolved_semantic.get("final_filters")
        or inventory.get("filters")
        or query_intent.get("filters")
        or {}
    )
    clarification_question = str(
        (semantic_context.get("inventory_governed_match") or {}).get("pregunta_aclaracion")
        or ""
    ).strip()
    if not clarification_question:
        warnings = [
            str(item or "").strip()
            for item in list(query_intent.get("warnings") or [])
            if str(item or "").strip()
        ]
        if warnings and "?" in warnings[0]:
            clarification_question = warnings[0]

    response_profile = _output_profile(semantic_binding, semantic_plan)
    response_profile_id = str(response_profile.get("id") or "")
    main_rowcount = int(result_set.get("rowcount") or len(rows) or 0)
    extra_rowcount = sum(
        int(item.get("rowcount") or 0)
        for item in supplemental_tables
        if not bool(item.get("skipped"))
    )
    status, missing_evidence_reason = _response_status(
        clarification_question=clarification_question,
        limitations=limitations,
        main_rowcount=main_rowcount,
        extra_rowcount=extra_rowcount,
    )

    fallback_narrativo_usado = False
    if status == "clarification_required":
        dato = clarification_question
        hallazgo = "La consulta no se ejecuto porque falta contexto estructural para identificar el portador correcto."
        interpretacion = "La aclaracion viene de la resolucion semantica gobernada, no de una intuicion narrativa."
        recomendacion = "Indica cedula, movil o cuadrilla para continuar con una ruta ejecutable."
    elif status == "limitation_declared":
        dato = "La consulta quedo limitada antes de presentar un resultado como exitoso."
        hallazgo = _limitation_text(limitations)
        interpretacion = "La limitacion proviene de metadata gobernada o de una fuente externa no habilitada."
        recomendacion = "Si quieres, puedo ayudarte a reformular la consulta dentro del alcance actualmente soportado."
    elif status == "empty_result":
        filtro_texto = str(filters.get("codigo") or filters.get("descripcion") or filters.get("tipo") or "").strip()
        serial_family = str(filters.get("material_family") or "").strip()
        if str((semantic_plan.get("inventory_family") or "")).strip().lower() == "serializados" and serial_family:
            dato = (
                f"Encontre codigos del catalogo con familia que contiene {serial_family}, "
                "pero no hay seriales en estado MOVIL para esos codigos."
            )
            hallazgo = "La validacion se hizo contra el catalogo gobernado de serializados y la ejecucion no devolvio filas operativas en MOVIL."
            interpretacion = "La familia existe en el catalogo, pero no hay evidencia de seriales en estado MOVIL para el alcance consultado."
            recomendacion = "Si quieres, puedo revisar la misma familia por otra dimension operativa o validar otra familia del catalogo."
        else:
            dato = "La consulta se ejecuto, pero no devolvio filas para el alcance solicitado."
            hallazgo = (
                "El result_set principal y los bloques suplementarios quedaron vacios "
                + (
                    f"para el filtro {filtro_texto}."
                    if filtro_texto
                    else f"con los filtros {', '.join(sorted(str(key) for key in filters.keys())) or 'aplicados'}."
                )
            )
            interpretacion = "No hay evidencia suficiente para afirmar inventario, movimientos o asignacion para ese alcance."
            recomendacion = "Revisa el identificador, amplia el alcance o cambia la familia consultada."
    else:
        dato, hallazgo, interpretacion, recomendacion, fallback_narrativo_usado = _success_response(
            response_profile_id=response_profile_id,
            response_profile=response_profile,
            semantic_plan=semantic_plan,
            semantic_context=semantic_context,
            filters=filters,
            rows=rows,
            supplemental_tables=supplemental_tables,
        )

    evidence_summary = _evidence_summary(
        semantic_context=semantic_context,
        semantic_plan=semantic_plan,
        semantic_binding=semantic_binding,
        rows=rows,
        supplemental_tables=supplemental_tables,
        result_set={
            **result_set,
            "rowcount": main_rowcount,
        },
        response_profile=response_profile,
        fallback_narrativo_usado=fallback_narrativo_usado,
        missing_evidence_reason=missing_evidence_reason,
    )
    dashboard_composition = _DASHBOARD_COMPOSITION_PLANNER.plan(
        user_question=str(
            resolved_query.get("message")
            or (dict(resolved_query.get("intent") or {}).get("raw_query"))
            or resolved_query.get("query")
            or ""
        ),
        rows=rows,
        result_set={
            **result_set,
            "rowcount": main_rowcount,
            "returned_records": int(result_set.get("returned_records") or main_rowcount),
            "total_records": int(result_set.get("total_records") or main_rowcount),
        },
        semantic_explanation={
            "domain": "inventario_logistica",
            "intent": str(inventory.get("intent") or query_intent.get("template_id") or ""),
            "entity": dict(semantic_plan.get("entity") or {}),
            "filters": filters,
            "candidate_capability": str(semantic_binding.get("candidate_capability") or ""),
            "planner_route_hint": str(semantic_binding.get("planner_route_hint") or ""),
        },
        response_profile=response_profile,
        supplemental_tables=supplemental_tables,
    )
    evidence_summary["dashboard_composition_generated"] = bool(dashboard_composition)

    return {
        "dato": dato,
        "hallazgo": hallazgo,
        "riesgo_o_interpretacion": interpretacion,
        "riesgo": interpretacion,
        "interpretacion": interpretacion,
        "recomendacion": recomendacion,
        "siguiente_accion": recomendacion,
        "response_profile": response_profile,
        "dashboard_composition": dashboard_composition,
        "evidence_summary": evidence_summary,
        "metadata": {
            "domain": "inventario_logistica",
            "response_status": status,
            "material_family": str(inventory.get("material_family") or ""),
            "intent": str(inventory.get("intent") or query_intent.get("template_id") or ""),
            "business_concept": business_concept,
            "operation": str(inventory.get("operation") or query_intent.get("operation") or ""),
            "tables_used": list(inventory.get("candidate_tables") or []),
            "fields_used": list(inventory.get("candidate_fields") or []),
            "filters": filters,
            "group_by": list(inventory.get("group_by") or []),
            "runtime_flow": runtime_flow,
            "limitations": limitations,
            "requires_business_validation": bool(inventory.get("requires_business_validation")),
            "requires_external_source": bool(inventory.get("requires_external_source")),
            "missing_metadata": list(inventory.get("missing_metadata") or []),
            "implementation_status": str(inventory.get("implementation_status") or ""),
            "requires_threshold_metadata": bool(inventory.get("requires_threshold_metadata")),
            "template_id": str(semantic_binding.get("template_id") or query_intent.get("template_id") or ""),
            "candidate_capability": str(semantic_binding.get("candidate_capability") or ""),
            "planner_route_hint": str(semantic_binding.get("planner_route_hint") or ""),
            "response_profile_usado": str(response_profile.get("id") or ""),
            "tool_id": str(semantic_binding.get("tool_id") or ""),
            "paquete_capacidad_usado": str(semantic_binding.get("paquete_capacidad_usado") or ""),
            "version_paquete": str(semantic_binding.get("version_paquete") or ""),
            "capacidades_declaradas": list(semantic_binding.get("capacidades_declaradas") or []),
            "reglas_declaradas": list(semantic_binding.get("reglas_declaradas") or []),
            "perfiles_respuesta": list(semantic_binding.get("perfiles_respuesta") or []),
            "evaluaciones_asociadas": list(semantic_binding.get("evaluaciones_asociadas") or []),
            "evidence_sources_used": list(evidence_summary.get("evidence_sources_used") or []),
            "semantic_context_used": bool(evidence_summary.get("semantic_context_used")),
            "fallback_narrativo_usado": bool(evidence_summary.get("fallback_narrativo_usado")),
            "missing_evidence_reason": str(evidence_summary.get("missing_evidence_reason") or ""),
            "semantic_trace": dict(evidence_summary.get("semantic_trace") or {}),
            "dashboard_composition_generated": bool(dashboard_composition),
        },
    }
