from __future__ import annotations

from collections import defaultdict
from typing import Any


def _as_str(value: Any) -> str:
    return str(value or "").strip()


def _as_float(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = _as_str(value).replace(",", "")
    if not text:
        return 0.0
    try:
        return float(text)
    except Exception:
        return 0.0


def _normalize_key(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


def _humanize(value: str) -> str:
    return value.replace("_", " ").strip().title()


class DashboardCompositionPlanner:
    VERSION = "dashboard_composition.inventory.v1"
    SEMANTIC_PATTERN = "inventory.serial.stock.dimension"
    PROVIDER_FILE_PATTERN = "inventory.serial.validation.provider_file"
    SUPPORTED_RESPONSE_PROFILES = {
        "inventory.serial.stock.dimension.detail",
        "inventory.serial.stock.dimension.summary",
    }
    SUPPORTED_PROVIDER_RESPONSE_PROFILES = {
        "inventory.serial.validation.provider_file.detail",
    }
    REQUIRED_COLUMNS = {"codigo", "descripcion", "familia", "saldo"}
    DIMENSION_COLUMNS = ("movil", "cedula", "dimension", "bodega")
    PERSON_COLUMNS = ("cedula", "nombre", "apellido", "empleado")
    OPTIONAL_METRIC_COLUMNS = {"seriales_total", "en_movil"}

    def plan(
        self,
        *,
        user_question: str,
        rows: list[dict[str, Any]],
        result_set: dict[str, Any],
        semantic_explanation: dict[str, Any],
        response_profile: dict[str, Any],
        supplemental_tables: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        normalized_rows = [dict(row) for row in rows if isinstance(row, dict)]
        response_profile_id = _as_str(response_profile.get("id"))
        filters = dict(semantic_explanation.get("filters") or {})
        columns = self._collect_columns(normalized_rows)
        row_count = int(result_set.get("returned_records") or result_set.get("rowcount") or len(normalized_rows) or 0)
        total_records = int(result_set.get("total_records") or row_count)
        truncated = bool(result_set.get("truncated")) or total_records > row_count
        supplemental_tables = [dict(item) for item in list(supplemental_tables or []) if isinstance(item, dict)]

        if response_profile_id in self.SUPPORTED_PROVIDER_RESPONSE_PROFILES:
            return self._plan_provider_serial_validation(
                user_question=user_question,
                normalized_rows=normalized_rows,
                result_set=result_set,
                semantic_explanation=semantic_explanation,
                response_profile_id=response_profile_id,
                supplemental_tables=supplemental_tables,
            )
        if response_profile_id not in self.SUPPORTED_RESPONSE_PROFILES:
            return {}
        if not normalized_rows:
            return {}
        if not self.REQUIRED_COLUMNS.issubset(columns):
            return {}

        dimension_field = self._detect_dimension_field(columns=columns, filters=filters)
        if not dimension_field:
            return {}

        evidence_limitations = []
        if truncated:
            evidence_limitations.append(
                "La composicion se construyo con las filas retornadas por el result_set y puede no cubrir la totalidad del universo."
            )

        confidence = 0.78 if truncated else 0.96
        base_evidence = self._evidence(
            source_block="result_set",
            columns_used=sorted(columns),
            formula="Evidence-first over returned rows",
            row_count_used=row_count,
            confidence=confidence,
            limitation="; ".join(evidence_limitations),
        )

        code_summary_rows = self._build_code_summary(normalized_rows)
        dimension_summary_rows = self._build_dimension_summary(
            normalized_rows=normalized_rows,
            dimension_field=dimension_field,
        )
        family_summary_rows = self._build_family_summary(normalized_rows)

        primary_kpis = self._build_primary_kpis(
            normalized_rows=normalized_rows,
            dimension_field=dimension_field,
            row_count=row_count,
            confidence=confidence,
            limitation=base_evidence.get("limitation"),
        )
        ranked_breakdowns = self._build_ranked_breakdowns(
            code_summary_rows=code_summary_rows,
            dimension_summary_rows=dimension_summary_rows,
            family_summary_rows=family_summary_rows,
            row_count=row_count,
            confidence=confidence,
            limitation=base_evidence.get("limitation"),
            dimension_field=dimension_field,
        )
        recommended_charts = self._build_recommended_charts(
            ranked_breakdowns=ranked_breakdowns,
            family_summary_rows=family_summary_rows,
            row_count=row_count,
            confidence=confidence,
            limitation=base_evidence.get("limitation"),
        )
        priority_tables = self._build_priority_tables(
            normalized_rows=normalized_rows,
            code_summary_rows=code_summary_rows,
            dimension_summary_rows=dimension_summary_rows,
            row_count=row_count,
            confidence=confidence,
            limitation=base_evidence.get("limitation"),
        )
        business_insights = self._build_business_insights(
            code_summary_rows=code_summary_rows,
            dimension_summary_rows=dimension_summary_rows,
            family_summary_rows=family_summary_rows,
            total_saldo=_as_float(primary_kpis[0].get("value") if primary_kpis else 0),
            row_count=row_count,
            confidence=confidence,
            limitation=base_evidence.get("limitation"),
            dimension_field=dimension_field,
        )
        operational_alerts = self._build_operational_alerts(
            code_summary_rows=code_summary_rows,
            dimension_summary_rows=dimension_summary_rows,
            total_saldo=_as_float(primary_kpis[0].get("value") if primary_kpis else 0),
            confidence=confidence,
            limitation=base_evidence.get("limitation"),
            dimension_field=dimension_field,
        )

        family_filter = _as_str(filters.get("material_family"))
        executive_summary = {
            "requested_question": _as_str(user_question),
            "applied_family_filter": family_filter,
            "resolved_route": {
                "capability": _as_str(semantic_explanation.get("candidate_capability")),
                "planner_route_hint": _as_str(semantic_explanation.get("planner_route_hint")),
                "response_profile": response_profile_id,
            },
            "saldo_definition": (
                "Saldo corresponde a la agregacion de la columna saldo disponible en la evidencia ejecutada."
            ),
            "evidence": self._evidence(
                source_block="semantic_context+result_set",
                columns_used=sorted(columns),
                formula="Requested question + executed response profile + saldo aggregation",
                row_count_used=row_count,
                confidence=confidence,
                limitation="; ".join(evidence_limitations),
            ),
        }
        semantic_basis = {
            "domain": _as_str(semantic_explanation.get("domain")),
            "intent": _as_str(semantic_explanation.get("intent")),
            "entity": dict(semantic_explanation.get("entity") or {}),
            "filters": filters,
            "grouping_dimension": dimension_field,
            "evidence": self._evidence(
                source_block="semantic_context",
                columns_used=[dimension_field],
                formula="Semantic plan and normalized filters",
                row_count_used=row_count,
                confidence=confidence,
                limitation="",
            ),
        }
        evidence_contract = {
            "planner_id": self.VERSION,
            "supported_pattern": self.SEMANTIC_PATTERN,
            "semantic_pattern": self.SEMANTIC_PATTERN,
            "evidence_first": True,
            "data_authority": "result_set",
            "validated": True,
            "validated_columns": sorted(columns),
            "supported_response_profile": response_profile_id,
            "limitations": evidence_limitations,
            "source_blocks": ["result_set"] + [
                _as_str(item.get("name")) for item in supplemental_tables if _as_str(item.get("name"))
            ],
            "component_count": sum(
                1
                for collection in (
                    primary_kpis,
                    ranked_breakdowns,
                    recommended_charts,
                    priority_tables,
                    business_insights,
                    operational_alerts,
                )
                if collection
            ),
        }

        return {
            "executive_summary": executive_summary,
            "semantic_basis": semantic_basis,
            "primary_kpis": primary_kpis,
            "ranked_breakdowns": ranked_breakdowns,
            "recommended_charts": recommended_charts,
            "priority_tables": priority_tables,
            "business_insights": business_insights,
            "operational_alerts": operational_alerts,
            "evidence_contract": evidence_contract,
        }

    def _plan_provider_serial_validation(
        self,
        *,
        user_question: str,
        normalized_rows: list[dict[str, Any]],
        result_set: dict[str, Any],
        semantic_explanation: dict[str, Any],
        response_profile_id: str,
        supplemental_tables: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not normalized_rows:
            return {}
        columns = self._collect_columns(normalized_rows)
        required_columns = {"serial_proveedor", "encontrado", "fuente", "estado"}
        if not required_columns.issubset(columns):
            return {}

        row_count = int(result_set.get("returned_records") or result_set.get("rowcount") or len(normalized_rows) or 0)
        total_records = int(result_set.get("total_records") or row_count)
        truncated = bool(result_set.get("truncated")) or total_records > row_count
        confidence = 0.78 if truncated else 0.97
        filters = dict(semantic_explanation.get("filters") or {})
        seriales_recibidos = len(normalized_rows)
        seriales_unicos = len(
            {
                _as_str(row.get("serial_normalizado") or row.get("serial_proveedor"))
                for row in normalized_rows
                if _as_str(row.get("serial_normalizado") or row.get("serial_proveedor"))
            }
        )
        duplicados = max(0, seriales_recibidos - seriales_unicos)
        encontrados = [row for row in normalized_rows if _as_str(row.get("encontrado")).upper() == "SI"]
        no_encontrados = [row for row in normalized_rows if _as_str(row.get("encontrado")).upper() == "NO"]
        solo_historicos = [row for row in normalized_rows if _as_str(row.get("solo_historico")).upper() == "SI"]
        en_movil = [row for row in normalized_rows if _as_str(row.get("estado_contiene_movil")).upper() == "SI"]
        encontrados_unicos = {
            _as_str(row.get("serial_normalizado") or row.get("serial_proveedor"))
            for row in encontrados
            if _as_str(row.get("serial_normalizado") or row.get("serial_proveedor"))
        }
        no_encontrados_unicos = {
            _as_str(row.get("serial_normalizado") or row.get("serial_proveedor"))
            for row in no_encontrados
            if _as_str(row.get("serial_normalizado") or row.get("serial_proveedor"))
        }
        encontrados_base = {
            _as_str(row.get("serial_normalizado") or row.get("serial_proveedor"))
            for row in normalized_rows
            if "base actual" in _as_str(row.get("fuentes_coincidencia") or row.get("fuente")).lower()
        }
        encontrados_asociados = {
            _as_str(row.get("serial_normalizado") or row.get("serial_proveedor"))
            for row in normalized_rows
            if "asociados actual" in _as_str(row.get("fuentes_coincidencia") or row.get("fuente")).lower()
        }
        encontrados_historico = {
            _as_str(row.get("serial_normalizado") or row.get("serial_proveedor"))
            for row in normalized_rows
            if "backup" in _as_str(row.get("fuentes_coincidencia") or row.get("fuente")).lower()
        }
        fuente_final_base = {
            _as_str(row.get("serial_normalizado") or row.get("serial_proveedor"))
            for row in normalized_rows
            if _as_str(row.get("fuente")).lower() == "base actual"
        }
        fuente_final_asociados = {
            _as_str(row.get("serial_normalizado") or row.get("serial_proveedor"))
            for row in normalized_rows
            if _as_str(row.get("fuente")).lower() == "asociados actual"
        }
        fuente_final_historico = {
            _as_str(row.get("serial_normalizado") or row.get("serial_proveedor"))
            for row in normalized_rows
            if "backup" in _as_str(row.get("fuente")).lower()
        }
        moviles_detectados = {
            _as_str(row.get("serial_normalizado") or row.get("serial_proveedor"))
            for row in en_movil
            if _as_str(row.get("serial_normalizado") or row.get("serial_proveedor"))
        }
        moviles_enriched = {
            _as_str(row.get("serial_normalizado") or row.get("serial_proveedor"))
            for row in en_movil
            if bool(row.get("responsable_enriched"))
        }

        limitation = (
            "La composicion se construyo con una muestra truncada del result_set."
            if truncated
            else ""
        )
        primary_kpis = [
            self._composition_kpi(
                item_id="total_filas_archivo",
                title="Total filas archivo",
                value=seriales_recibidos,
                columns_used=["serial_proveedor"],
                formula="count_rows(provider_file)",
                row_count=row_count,
                confidence=confidence,
                limitation=limitation,
            ),
            self._composition_kpi(
                item_id="seriales_unicos",
                title="Seriales unicos",
                value=seriales_unicos,
                columns_used=["serial_proveedor"],
                formula="count_distinct(serial_normalizado)",
                row_count=row_count,
                confidence=confidence,
                limitation=limitation,
            ),
            self._composition_kpi(
                item_id="duplicados_archivo",
                title="Duplicados archivo",
                value=duplicados,
                columns_used=["serial_proveedor"],
                formula="count_rows - count_distinct(serial_normalizado)",
                row_count=row_count,
                confidence=confidence,
                limitation=limitation,
            ),
            self._composition_kpi(
                item_id="encontrados_por_fila",
                title="Encontrados por fila",
                value=len(encontrados),
                columns_used=["encontrado", "serial_proveedor"],
                formula="count_rows where encontrado = SI",
                row_count=row_count,
                confidence=confidence,
                limitation=limitation,
            ),
            self._composition_kpi(
                item_id="encontrados_unicos",
                title="Encontrados unicos",
                value=len(encontrados_unicos),
                columns_used=["encontrado", "serial_proveedor"],
                formula="count_distinct(serial_normalizado) where encontrado = SI",
                row_count=row_count,
                confidence=confidence,
                limitation=limitation,
            ),
            self._composition_kpi(
                item_id="no_encontrados_por_fila",
                title="No encontrados por fila",
                value=len(no_encontrados),
                columns_used=["encontrado", "serial_proveedor"],
                formula="count_rows where encontrado = NO",
                row_count=row_count,
                confidence=confidence,
                limitation=limitation,
            ),
            self._composition_kpi(
                item_id="no_encontrados_unicos",
                title="No encontrados unicos",
                value=len(no_encontrados_unicos),
                columns_used=["encontrado", "serial_proveedor"],
                formula="count_distinct(serial_normalizado) where encontrado = NO",
                row_count=row_count,
                confidence=confidence,
                limitation=limitation,
            ),
            self._composition_kpi(
                item_id="coincidencias_base_actual",
                title="Coincidencias base actual",
                value=len(encontrados_base),
                columns_used=["fuente", "serial_proveedor"],
                formula="count_distinct(serial_normalizado) with current base evidence",
                row_count=row_count,
                confidence=confidence,
                limitation=limitation,
            ),
            self._composition_kpi(
                item_id="coincidencias_asociados_actual",
                title="Coincidencias asociados actual",
                value=len(encontrados_asociados),
                columns_used=["fuente", "serial_proveedor"],
                formula="count_distinct(serial_normalizado) with current associated evidence",
                row_count=row_count,
                confidence=confidence,
                limitation=limitation,
            ),
            self._composition_kpi(
                item_id="coincidencias_historico",
                title="Coincidencias historico",
                value=len(encontrados_historico),
                columns_used=["fuente", "serial_proveedor"],
                formula="count_distinct(serial_normalizado) with historical evidence",
                row_count=row_count,
                confidence=confidence,
                limitation=limitation,
            ),
            self._composition_kpi(
                item_id="fuente_final_base_actual",
                title="Fuente final base actual",
                value=len(fuente_final_base),
                columns_used=["fuente", "serial_proveedor"],
                formula="count_distinct(serial_normalizado) where fuente final = base actual",
                row_count=row_count,
                confidence=confidence,
                limitation=limitation,
            ),
            self._composition_kpi(
                item_id="fuente_final_asociados_actual",
                title="Fuente final asociados actual",
                value=len(fuente_final_asociados),
                columns_used=["fuente", "serial_proveedor"],
                formula="count_distinct(serial_normalizado) where fuente final = asociados actual",
                row_count=row_count,
                confidence=confidence,
                limitation=limitation,
            ),
            self._composition_kpi(
                item_id="fuente_final_historico",
                title="Fuente final historico",
                value=len(fuente_final_historico),
                columns_used=["fuente", "serial_proveedor"],
                formula="count_distinct(serial_normalizado) where fuente final = historico",
                row_count=row_count,
                confidence=confidence,
                limitation=limitation,
            ),
            self._composition_kpi(
                item_id="moviles_detectados",
                title="Moviles detectados",
                value=len(moviles_detectados),
                columns_used=["estado_contiene_movil", "serial_proveedor"],
                formula="count_distinct(serial_normalizado) where estado_contiene_movil = SI",
                row_count=row_count,
                confidence=confidence,
                limitation=limitation,
            ),
            self._composition_kpi(
                item_id="moviles_con_responsable_enriquecido",
                title="Moviles con responsable enriquecido",
                value=len(moviles_enriched),
                columns_used=["estado_contiene_movil", "responsable_enriched", "serial_proveedor"],
                formula="count_distinct(serial_normalizado) where estado_contiene_movil = SI and responsable_enriched = true",
                row_count=row_count,
                confidence=confidence,
                limitation=limitation,
            ),
            self._composition_kpi(
                item_id="moviles_sin_responsable_enriquecido",
                title="Moviles sin responsable enriquecido",
                value=max(0, len(moviles_detectados) - len(moviles_enriched)),
                columns_used=["estado_contiene_movil", "responsable_enriched", "serial_proveedor"],
                formula="count_distinct(serial_normalizado) where estado_contiene_movil = SI and responsable_enriched = false",
                row_count=row_count,
                confidence=confidence,
                limitation=limitation,
            ),
            self._composition_kpi(
                item_id="encontrados_solo_en_historico",
                title="Encontrados solo en historico",
                value=len(solo_historicos),
                columns_used=["solo_historico", "serial_proveedor"],
                formula="count_distinct(serial_normalizado) where solo_historico = SI",
                row_count=row_count,
                confidence=confidence,
                limitation=limitation,
            ),
        ]

        ranked_breakdowns = [
            self._composition_rows(
                item_id="top_estados_encontrados",
                title="Top estados encontrados",
                rows=self._group_rows(normalized_rows, key="estado", metric_label="seriales", top_n=10),
                row_count=row_count,
                confidence=confidence,
                limitation=limitation,
                columns_used=["estado"],
                formula="count_distinct(serial_normalizado) by estado",
            ),
            self._composition_rows(
                item_id="top_fuentes_con_coincidencias",
                title="Top fuentes con coincidencias",
                rows=self._group_rows(encontrados, key="fuente", metric_label="seriales", top_n=10),
                row_count=row_count,
                confidence=confidence,
                limitation=limitation,
                columns_used=["fuente"],
                formula="count_distinct(serial_normalizado) by fuente",
            ),
            self._composition_rows(
                item_id="top_moviles_personas",
                title="Top moviles y personas con mas seriales",
                rows=self._group_rows(
                    en_movil,
                    key="empleado",
                    fallback_keys=("movil_asociado", "cedula_persona", "responsable_candidate_value"),
                    metric_label="seriales",
                    top_n=10,
                ),
                row_count=row_count,
                confidence=confidence,
                limitation=limitation,
                columns_used=["empleado", "movil_asociado", "cedula_persona", "responsable_candidate_value"],
                formula="count_distinct(serial_normalizado) by responsable",
            ),
            self._composition_rows(
                item_id="top_materiales_familias_proveedor",
                title="Top materiales y familias del proveedor",
                rows=self._group_rows(
                    normalized_rows,
                    key="material_proveedor",
                    fallback_keys=("familia_proveedor",),
                    metric_label="seriales",
                    top_n=10,
                ),
                row_count=row_count,
                confidence=confidence,
                limitation=limitation,
                columns_used=["material_proveedor", "familia_proveedor"],
                formula="count_rows(provider_file) by material/familia",
            ),
        ]

        recommended_charts = [
            self._composition_chart(
                item_id="chart_encontrado_no_encontrado",
                title="Distribucion encontrado/no encontrado",
                rows=self._group_rows(normalized_rows, key="encontrado", metric_label="seriales", top_n=5),
                row_count=row_count,
                confidence=confidence,
                limitation=limitation,
                columns_used=["encontrado"],
                formula="count_distinct(serial_normalizado) by encontrado",
                x_key="encontrado",
                value_key="seriales",
            ),
            self._composition_chart(
                item_id="chart_distribucion_estado",
                title="Distribucion por estado",
                rows=self._group_rows(normalized_rows, key="estado", metric_label="seriales", top_n=10),
                row_count=row_count,
                confidence=confidence,
                limitation=limitation,
                columns_used=["estado"],
                formula="count_distinct(serial_normalizado) by estado",
                x_key="estado",
                value_key="seriales",
            ),
            self._composition_chart(
                item_id="chart_distribucion_fuente",
                title="Distribucion por fuente",
                rows=self._group_rows(encontrados, key="fuente", metric_label="seriales", top_n=10),
                row_count=row_count,
                confidence=confidence,
                limitation=limitation,
                columns_used=["fuente"],
                formula="count_distinct(serial_normalizado) by fuente",
                x_key="fuente",
                value_key="seriales",
            ),
            self._composition_chart(
                item_id="chart_top_moviles_personas",
                title="Top moviles y personas",
                rows=self._group_rows(
                    en_movil,
                    key="empleado",
                    fallback_keys=("movil_asociado", "cedula_persona", "responsable_candidate_value"),
                    metric_label="seriales",
                    top_n=10,
                ),
                row_count=row_count,
                confidence=confidence,
                limitation=limitation,
                columns_used=["empleado", "movil_asociado", "cedula_persona", "responsable_candidate_value"],
                formula="count_distinct(serial_normalizado) by responsable",
                x_key="responsable",
                value_key="seriales",
            ),
            self._composition_chart(
                item_id="chart_top_materiales_familias",
                title="Top materiales y familias",
                rows=self._group_rows(
                    normalized_rows,
                    key="material_proveedor",
                    fallback_keys=("familia_proveedor",),
                    metric_label="seriales",
                    top_n=10,
                ),
                row_count=row_count,
                confidence=confidence,
                limitation=limitation,
                columns_used=["material_proveedor", "familia_proveedor"],
                formula="count_rows(provider_file) by material/familia",
                x_key="material_proveedor",
                value_key="seriales",
            ),
        ]

        priority_tables = []
        for table_name in (
            "resultado_por_serial",
            "seriales_en_movil",
            "seriales_en_movil_con_responsable",
            "seriales_no_encontrados",
            "seriales_duplicados_archivo",
            "seriales_solo_historicos",
            "evidencia_tecnica_colapsada",
        ):
            matched = next(
                (item for item in supplemental_tables if _as_str(item.get("name")) == table_name),
                {},
            )
            if matched:
                priority_tables.append(
                    {
                        "id": table_name,
                        "title": _as_str(matched.get("title") or table_name.replace("_", " ").title()),
                        "rows": list(matched.get("rows") or []),
                        "table": matched,
                        "priority": "high" if table_name == "resultado_por_serial" else "drilldown",
                        "evidence": self._evidence(
                            source_block="supplemental_tables",
                            columns_used=list(matched.get("columns") or []),
                            formula=f"drill_down:{table_name}",
                            row_count_used=int(matched.get("rowcount") or 0),
                            confidence=confidence,
                            limitation=limitation,
                        ),
                    }
                )

        executive_summary = {
            "requested_question": _as_str(user_question),
            "applied_family_filter": "serializados",
            "resolved_route": {
                "capability": _as_str(semantic_explanation.get("candidate_capability")),
                "planner_route_hint": _as_str(semantic_explanation.get("planner_route_hint")),
                "response_profile": response_profile_id,
            },
            "saldo_definition": "No aplica saldo; la metrica principal es seriales validados contra evidencia actual e historica.",
            "evidence": self._evidence(
                source_block="provider_file+governed_queries",
                columns_used=sorted(columns),
                formula="provider file rows + governed current/historical inventory matches",
                row_count_used=row_count,
                confidence=confidence,
                limitation=limitation,
            ),
        }
        semantic_basis = {
            "domain": _as_str(semantic_explanation.get("domain")),
            "intent": _as_str(semantic_explanation.get("intent")),
            "entity": dict(semantic_explanation.get("entity") or {}),
            "filters": filters,
            "grouping_dimension": "serial",
            "evidence": self._evidence(
                source_block="semantic_context",
                columns_used=["serial_proveedor"],
                formula="Semantic provider-file validation pattern",
                row_count_used=row_count,
                confidence=confidence,
                limitation="",
            ),
        }
        evidence_contract = {
            "planner_id": self.VERSION,
            "supported_pattern": self.PROVIDER_FILE_PATTERN,
            "semantic_pattern": self.PROVIDER_FILE_PATTERN,
            "evidence_first": True,
            "data_authority": "provider_file+governed_queries",
            "validated": True,
            "validated_columns": sorted(columns),
            "supported_response_profile": response_profile_id,
            "limitations": [limitation] if limitation else [],
            "source_blocks": [
                "provider_file",
                "information_schema.tables",
                "information_schema.columns",
                "current_operational_tables",
                "historical_inventory_backups",
                "personal_enrichment",
            ],
            "component_count": len(primary_kpis) + len(ranked_breakdowns) + len(recommended_charts) + len(priority_tables),
        }
        business_insights = [
            {
                "id": "provider_file_summary",
                "title": "Lectura operativa",
                "text": (
                    f"Se evaluaron {seriales_recibidos} filas del archivo; {len(encontrados_unicos)} seriales unicos tuvieron coincidencia "
                    f"y {len(moviles_enriched)} seriales MOVIL lograron enrichment real de responsable."
                ),
                "evidence": self._evidence(
                    source_block="provider_file+governed_queries",
                    columns_used=["serial_proveedor", "fuente", "solo_historico", "responsable_enriched"],
                    formula="executive provider-file validation summary",
                    row_count_used=row_count,
                    confidence=confidence,
                    limitation=limitation,
                ),
            }
        ]
        operational_alerts = []
        if no_encontrados:
            operational_alerts.append(
                {
                    "id": "not_found_attention",
                    "title": "Seriales sin evidencia",
                    "text": f"{len(no_encontrados_unicos)} seriales unicos no tuvieron coincidencia en las tablas consultadas.",
                    "severity": "medium",
                    "evidence": self._evidence(
                        source_block="governed_queries",
                        columns_used=["encontrado"],
                        formula="count_distinct(serial_normalizado) where encontrado = NO",
                        row_count_used=row_count,
                        confidence=confidence,
                        limitation=limitation,
                    ),
                }
            )
        if moviles_detectados and len(moviles_enriched) < len(moviles_detectados):
            operational_alerts.append(
                {
                    "id": "movil_without_personal_evidence",
                    "title": "MOVIL sin enrichment de responsable",
                    "text": (
                        f"{max(0, len(moviles_detectados) - len(moviles_enriched))} seriales MOVIL quedaron sin enrichment real de responsable."
                    ),
                    "severity": "medium",
                    "evidence": self._evidence(
                        source_block="governed_queries",
                        columns_used=["estado_contiene_movil", "responsable_enriched"],
                        formula="count_distinct(serial_normalizado) where estado_contiene_movil = SI and responsable_enriched = false",
                        row_count_used=row_count,
                        confidence=confidence,
                        limitation=limitation,
                    ),
                }
            )
        if solo_historicos:
            operational_alerts.append(
                {
                    "id": "historical_only_attention",
                    "title": "Coincidencias solo historicas",
                    "text": f"{len(solo_historicos)} seriales aparecieron solo en backups historicos.",
                    "severity": "medium",
                    "evidence": self._evidence(
                        source_block="historical_inventory_backups",
                        columns_used=["solo_historico"],
                        formula="count_distinct(serial_normalizado) where solo_historico = SI",
                        row_count_used=row_count,
                        confidence=confidence,
                        limitation=limitation,
                    ),
                }
            )

        return {
            "executive_summary": executive_summary,
            "semantic_basis": semantic_basis,
            "primary_kpis": primary_kpis,
            "ranked_breakdowns": ranked_breakdowns,
            "recommended_charts": recommended_charts,
            "priority_tables": priority_tables,
            "business_insights": business_insights,
            "operational_alerts": operational_alerts,
            "evidence_contract": evidence_contract,
        }

    def _composition_kpi(
        self,
        *,
        item_id: str,
        title: str,
        value: int | float,
        columns_used: list[str],
        formula: str,
        row_count: int,
        confidence: float,
        limitation: str,
    ) -> dict[str, Any]:
        return {
            "id": item_id,
            "title": title,
            "value": value,
            "evidence": self._evidence(
                source_block="provider_file+governed_queries",
                columns_used=columns_used,
                formula=formula,
                row_count_used=row_count,
                confidence=confidence,
                limitation=limitation,
            ),
        }

    def _composition_rows(
        self,
        *,
        item_id: str,
        title: str,
        rows: list[dict[str, Any]],
        row_count: int,
        confidence: float,
        limitation: str,
        columns_used: list[str],
        formula: str,
    ) -> dict[str, Any]:
        return {
            "id": item_id,
            "title": title,
            "rows": rows,
            "evidence": self._evidence(
                source_block="provider_file+governed_queries",
                columns_used=columns_used,
                formula=formula,
                row_count_used=row_count,
                confidence=confidence,
                limitation=limitation,
            ),
        }

    def _composition_chart(
        self,
        *,
        item_id: str,
        title: str,
        rows: list[dict[str, Any]],
        row_count: int,
        confidence: float,
        limitation: str,
        columns_used: list[str],
        formula: str,
        x_key: str,
        value_key: str,
    ) -> dict[str, Any]:
        return {
            "id": item_id,
            "title": title,
            "type": "bar",
            "chart": {
                "engine": "amcharts5",
                "chart_library": "amcharts5",
                "type": "bar",
                "title": title,
                "x_key": x_key,
                "series": [{"name": title, "value_key": value_key}],
                "data": rows,
            },
            "evidence": self._evidence(
                source_block="provider_file+governed_queries",
                columns_used=columns_used,
                formula=formula,
                row_count_used=row_count,
                confidence=confidence,
                limitation=limitation,
            ),
        }

    def _group_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        key: str,
        fallback_keys: tuple[str, ...] = (),
        metric_label: str = "total",
        top_n: int = 10,
    ) -> list[dict[str, Any]]:
        counter: defaultdict[str, int] = defaultdict(int)
        for row in rows:
            candidate = _as_str(row.get(key))
            if not candidate:
                for fallback_key in fallback_keys:
                    candidate = _as_str(row.get(fallback_key))
                    if candidate:
                        break
            if not candidate:
                candidate = "No informado"
            serial_key = _as_str(row.get("serial_normalizado") or row.get("serial_proveedor"))
            if serial_key:
                counter[candidate] += 1
        ordered = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
        label = key if key != "empleado" else "responsable"
        return [{label: name, metric_label: total} for name, total in ordered[:top_n]]

    def _collect_columns(self, rows: list[dict[str, Any]]) -> set[str]:
        columns: set[str] = set()
        for row in rows[:10]:
            columns.update(_normalize_key(key) for key in row.keys())
        return columns

    def _detect_dimension_field(self, *, columns: set[str], filters: dict[str, Any]) -> str:
        filter_dimension = _normalize_key(_as_str(filters.get("grouping_dimension")))
        if filter_dimension in self.DIMENSION_COLUMNS and filter_dimension in columns:
            return filter_dimension
        for candidate in self.DIMENSION_COLUMNS:
            if candidate in columns:
                return candidate
        return ""

    def _evidence(
        self,
        *,
        source_block: str,
        columns_used: list[str],
        formula: str,
        row_count_used: int,
        confidence: float,
        limitation: str,
    ) -> dict[str, Any]:
        return {
            "source_block": source_block,
            "columns_used": columns_used,
            "formula": formula,
            "row_count_used": int(row_count_used),
            "confidence": round(float(confidence), 2),
            "limitation": _as_str(limitation),
        }

    def _build_primary_kpis(
        self,
        *,
        normalized_rows: list[dict[str, Any]],
        dimension_field: str,
        row_count: int,
        confidence: float,
        limitation: str,
    ) -> list[dict[str, Any]]:
        total_saldo = sum(_as_float(row.get("saldo")) for row in normalized_rows)
        distinct_codes = {
            _as_str(row.get("codigo")) for row in normalized_rows if _as_str(row.get("codigo"))
        }
        dimensions_with_balance = {
            _as_str(row.get(dimension_field))
            for row in normalized_rows
            if _as_str(row.get(dimension_field)) and _as_float(row.get("saldo")) > 0
        }
        total_seriales = sum(_as_float(row.get("seriales_total")) for row in normalized_rows)
        return [
            {
                "id": "saldo_total",
                "title": "Saldo total",
                "value": total_saldo,
                "evidence": self._evidence(
                    source_block="result_set",
                    columns_used=["saldo"],
                    formula="sum(saldo)",
                    row_count_used=row_count,
                    confidence=confidence,
                    limitation=limitation,
                ),
            },
            {
                "id": "codigos_coincidentes",
                "title": "Codigos coincidentes",
                "value": len(distinct_codes),
                "evidence": self._evidence(
                    source_block="result_set",
                    columns_used=["codigo"],
                    formula="count_distinct(codigo)",
                    row_count_used=row_count,
                    confidence=confidence,
                    limitation=limitation,
                ),
            },
            {
                "id": "dimensiones_con_saldo",
                "title": f"{_humanize(dimension_field)} con saldo",
                "value": len(dimensions_with_balance),
                "evidence": self._evidence(
                    source_block="result_set",
                    columns_used=[dimension_field, "saldo"],
                    formula=f"count_distinct({dimension_field}) where saldo > 0",
                    row_count_used=row_count,
                    confidence=confidence,
                    limitation=limitation,
                ),
            },
            {
                "id": "registros_evidencia",
                "title": "Registros de evidencia",
                "value": row_count,
                "evidence": self._evidence(
                    source_block="result_set",
                    columns_used=[],
                    formula="count(rows)",
                    row_count_used=row_count,
                    confidence=confidence,
                    limitation=limitation,
                ),
            },
            {
                "id": "seriales_total",
                "title": "Total seriales",
                "value": total_seriales,
                "evidence": self._evidence(
                    source_block="result_set",
                    columns_used=["seriales_total"],
                    formula="sum(seriales_total)",
                    row_count_used=row_count,
                    confidence=confidence,
                    limitation="No se calcula si la columna seriales_total no existe en evidencia.",
                ),
            },
        ]

    def _build_code_summary(self, normalized_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[tuple[str, str], dict[str, Any]] = {}
        for row in normalized_rows:
            codigo = _as_str(row.get("codigo"))
            descripcion = _as_str(row.get("descripcion"))
            key = (codigo, descripcion)
            if key not in grouped:
                grouped[key] = {
                    "codigo": codigo,
                    "descripcion": descripcion,
                    "familia": _as_str(row.get("familia")),
                    "saldo_total": 0.0,
                    "seriales_total": 0.0,
                    "registros": 0,
                }
            grouped[key]["saldo_total"] += _as_float(row.get("saldo"))
            grouped[key]["seriales_total"] += _as_float(row.get("seriales_total"))
            grouped[key]["registros"] += 1
        return sorted(grouped.values(), key=lambda item: (-_as_float(item.get("saldo_total")), _as_str(item.get("codigo"))))

    def _build_dimension_summary(
        self,
        *,
        normalized_rows: list[dict[str, Any]],
        dimension_field: str,
    ) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        for row in normalized_rows:
            dimension_value = _as_str(row.get(dimension_field))
            if not dimension_value:
                continue
            current = grouped.setdefault(
                dimension_value,
                {
                    dimension_field: dimension_value,
                    "cedula": _as_str(row.get("cedula")),
                    "nombre": _as_str(row.get("nombre")),
                    "apellido": _as_str(row.get("apellido")),
                    "empleado": _as_str(row.get("empleado")),
                    "saldo_total": 0.0,
                    "seriales_total": 0.0,
                    "codigos": set(),
                    "registros": 0,
                },
            )
            current["saldo_total"] += _as_float(row.get("saldo"))
            current["seriales_total"] += _as_float(row.get("seriales_total"))
            current["registros"] += 1
            codigo = _as_str(row.get("codigo"))
            if codigo:
                current["codigos"].add(codigo)
            if not current.get("cedula"):
                current["cedula"] = _as_str(row.get("cedula"))
        rows = []
        for item in grouped.values():
            item["codigos_distintos"] = len(item.pop("codigos"))
            rows.append(item)
        return sorted(rows, key=lambda item: (-_as_float(item.get("saldo_total")), _as_str(item.get(dimension_field))))

    def _build_family_summary(self, normalized_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = defaultdict(lambda: {"familia": "", "saldo_total": 0.0, "seriales_total": 0.0, "registros": 0})
        for row in normalized_rows:
            family = _as_str(row.get("familia")) or "Sin familia"
            current = grouped[family]
            current["familia"] = family
            current["saldo_total"] += _as_float(row.get("saldo"))
            current["seriales_total"] += _as_float(row.get("seriales_total"))
            current["registros"] += 1
        return sorted(grouped.values(), key=lambda item: (-_as_float(item.get("saldo_total")), _as_str(item.get("familia"))))

    def _build_ranked_breakdowns(
        self,
        *,
        code_summary_rows: list[dict[str, Any]],
        dimension_summary_rows: list[dict[str, Any]],
        family_summary_rows: list[dict[str, Any]],
        row_count: int,
        confidence: float,
        limitation: str,
        dimension_field: str,
    ) -> list[dict[str, Any]]:
        rankings = [
            {
                "id": "top_codes_by_saldo",
                "title": "Top codigos y descripciones por saldo",
                "kind": "ranking",
                "rows": code_summary_rows[:5],
                "evidence": self._evidence(
                    source_block="result_set",
                    columns_used=["codigo", "descripcion", "saldo"],
                    formula="group_by(codigo, descripcion), sum(saldo), order desc, top 5",
                    row_count_used=row_count,
                    confidence=confidence,
                    limitation=limitation,
                ),
            },
            {
                "id": "top_dimensions_by_saldo",
                "title": f"Top {_humanize(dimension_field)} por saldo",
                "kind": "ranking",
                "rows": dimension_summary_rows[:5],
                "evidence": self._evidence(
                    source_block="result_set",
                    columns_used=[dimension_field, "cedula", "nombre", "apellido", "empleado", "saldo"],
                    formula=f"group_by({dimension_field}), sum(saldo), order desc, top 5",
                    row_count_used=row_count,
                    confidence=confidence,
                    limitation=limitation,
                ),
            },
        ]
        if family_summary_rows:
            rankings.append(
                {
                    "id": "family_distribution",
                    "title": "Distribucion por familia",
                    "kind": "distribution",
                    "rows": family_summary_rows[:8],
                    "evidence": self._evidence(
                        source_block="result_set",
                        columns_used=["familia", "saldo"],
                        formula="group_by(familia), sum(saldo), order desc",
                        row_count_used=row_count,
                        confidence=confidence,
                        limitation=limitation,
                    ),
                }
            )
        return rankings

    def _build_recommended_charts(
        self,
        *,
        ranked_breakdowns: list[dict[str, Any]],
        family_summary_rows: list[dict[str, Any]],
        row_count: int,
        confidence: float,
        limitation: str,
    ) -> list[dict[str, Any]]:
        charts: list[dict[str, Any]] = []
        code_ranking = next((item for item in ranked_breakdowns if item.get("id") == "top_codes_by_saldo"), None)
        if code_ranking and list(code_ranking.get("rows") or []):
            rows = list(code_ranking.get("rows") or [])
            charts.append(
                {
                    "id": "chart_top_codes_by_saldo",
                    "title": "Top codigos por saldo",
                    "type": "bar",
                    "chart": {
                        "engine": "amcharts5",
                        "chart_library": "amcharts5",
                        "type": "bar",
                        "title": "Top codigos por saldo",
                        "x_key": "codigo",
                        "series": [{"name": "Saldo total", "value_key": "saldo_total"}],
                        "data": rows,
                    },
                    "evidence": self._evidence(
                        source_block="result_set",
                        columns_used=["codigo", "saldo"],
                        formula="group_by(codigo), sum(saldo), top 5",
                        row_count_used=row_count,
                        confidence=confidence,
                        limitation=limitation,
                    ),
                }
            )
        dimension_ranking = next((item for item in ranked_breakdowns if item.get("id") == "top_dimensions_by_saldo"), None)
        if dimension_ranking and list(dimension_ranking.get("rows") or []):
            rows = list(dimension_ranking.get("rows") or [])
            dimension_key = next(
                (key for key in ("movil", "cedula", "dimension", "bodega") if key in dict(rows[0]).keys()),
                "dimension",
            )
            charts.append(
                {
                    "id": "chart_top_dimensions_by_saldo",
                    "title": f"Top {_humanize(dimension_key)} por saldo",
                    "type": "bar",
                    "chart": {
                        "engine": "amcharts5",
                        "chart_library": "amcharts5",
                        "type": "bar",
                        "title": f"Top {_humanize(dimension_key)} por saldo",
                        "x_key": dimension_key,
                        "series": [{"name": "Saldo total", "value_key": "saldo_total"}],
                        "data": rows,
                    },
                    "evidence": self._evidence(
                        source_block="result_set",
                        columns_used=[dimension_key, "saldo"],
                        formula=f"group_by({dimension_key}), sum(saldo), top 5",
                        row_count_used=row_count,
                        confidence=confidence,
                        limitation=limitation,
                    ),
                }
            )
        if len(family_summary_rows) > 1:
            charts.append(
                {
                    "id": "chart_family_distribution",
                    "title": "Distribucion por familia",
                    "type": "bar",
                    "chart": {
                        "engine": "amcharts5",
                        "chart_library": "amcharts5",
                        "type": "bar",
                        "title": "Distribucion por familia",
                        "x_key": "familia",
                        "series": [{"name": "Saldo total", "value_key": "saldo_total"}],
                        "data": family_summary_rows[:8],
                    },
                    "evidence": self._evidence(
                        source_block="result_set",
                        columns_used=["familia", "saldo"],
                        formula="group_by(familia), sum(saldo)",
                        row_count_used=row_count,
                        confidence=confidence,
                        limitation=limitation,
                    ),
                }
            )
        return charts

    def _build_priority_tables(
        self,
        *,
        normalized_rows: list[dict[str, Any]],
        code_summary_rows: list[dict[str, Any]],
        dimension_summary_rows: list[dict[str, Any]],
        row_count: int,
        confidence: float,
        limitation: str,
    ) -> list[dict[str, Any]]:
        return [
            {
                "id": "table_code_summary",
                "title": "Resumen por codigo y descripcion",
                "priority": "high",
                "table": {
                    "columns": ["codigo", "descripcion", "familia", "saldo_total", "seriales_total", "registros"],
                    "rows": code_summary_rows[:20],
                    "rowcount": len(code_summary_rows),
                    "total_records": len(code_summary_rows),
                    "returned_records": min(len(code_summary_rows), 20),
                },
                "evidence": self._evidence(
                    source_block="result_set",
                    columns_used=["codigo", "descripcion", "familia", "saldo", "seriales_total"],
                    formula="group_by(codigo, descripcion, familia), sum(saldo), sum(seriales_total)",
                    row_count_used=row_count,
                    confidence=confidence,
                    limitation=limitation,
                ),
            },
            {
                "id": "table_dimension_summary",
                "title": "Resumen por dimension operativa",
                "priority": "high",
                "table": {
                    "columns": list(dict.fromkeys([key for key in ["movil", "cedula", "nombre", "apellido", "empleado", "saldo_total", "seriales_total", "codigos_distintos", "registros"] if any(key in row for row in dimension_summary_rows)])),
                    "rows": dimension_summary_rows[:20],
                    "rowcount": len(dimension_summary_rows),
                    "total_records": len(dimension_summary_rows),
                    "returned_records": min(len(dimension_summary_rows), 20),
                },
                "evidence": self._evidence(
                    source_block="result_set",
                    columns_used=["movil", "cedula", "nombre", "apellido", "empleado", "saldo", "seriales_total", "codigo"],
                    formula="group_by(dimension), sum(saldo), sum(seriales_total), count_distinct(codigo)",
                    row_count_used=row_count,
                    confidence=confidence,
                    limitation=limitation,
                ),
            },
            {
                "id": "table_operational_detail",
                "title": "Detalle operativo",
                "priority": "drilldown",
                "table": {
                    "columns": list(normalized_rows[0].keys()),
                    "rows": normalized_rows[:50],
                    "rowcount": row_count,
                    "total_records": row_count,
                    "returned_records": min(row_count, 50),
                },
                "evidence": self._evidence(
                    source_block="result_set",
                    columns_used=list(normalized_rows[0].keys()),
                    formula="detail rows for drill-down only",
                    row_count_used=row_count,
                    confidence=confidence,
                    limitation="Se muestra una muestra de detalle priorizada para drill-down." if row_count > 50 else limitation,
                ),
            },
        ]

    def _build_business_insights(
        self,
        *,
        code_summary_rows: list[dict[str, Any]],
        dimension_summary_rows: list[dict[str, Any]],
        family_summary_rows: list[dict[str, Any]],
        total_saldo: float,
        row_count: int,
        confidence: float,
        limitation: str,
        dimension_field: str,
    ) -> list[dict[str, Any]]:
        insights: list[dict[str, Any]] = []
        if code_summary_rows and total_saldo > 0:
            top_code = dict(code_summary_rows[0])
            share = round((_as_float(top_code.get("saldo_total")) / total_saldo) * 100, 1)
            insights.append(
                {
                    "id": "top_code_concentration",
                    "text": f"El codigo {_as_str(top_code.get('codigo'))} concentra {share}% del saldo observado.",
                    "evidence": self._evidence(
                        source_block="result_set",
                        columns_used=["codigo", "saldo"],
                        formula="top codigo share over sum(saldo)",
                        row_count_used=row_count,
                        confidence=confidence,
                        limitation=limitation,
                    ),
                }
            )
        if dimension_summary_rows and total_saldo > 0:
            top_dimension = dict(dimension_summary_rows[0])
            share = round((_as_float(top_dimension.get("saldo_total")) / total_saldo) * 100, 1)
            insights.append(
                {
                    "id": "top_dimension_load",
                    "text": f"El {_humanize(dimension_field).lower()} {_as_str(top_dimension.get(dimension_field))} concentra {share}% del saldo agregado.",
                    "evidence": self._evidence(
                        source_block="result_set",
                        columns_used=[dimension_field, "saldo"],
                        formula=f"top {dimension_field} share over sum(saldo)",
                        row_count_used=row_count,
                        confidence=confidence,
                        limitation=limitation,
                    ),
                }
            )
        if family_summary_rows:
            top_family = dict(family_summary_rows[0])
            insights.append(
                {
                    "id": "predominant_family",
                    "text": f"La familia {_as_str(top_family.get('familia'))} predomina en la evidencia priorizada por saldo.",
                    "evidence": self._evidence(
                        source_block="result_set",
                        columns_used=["familia", "saldo"],
                        formula="top familia by sum(saldo)",
                        row_count_used=row_count,
                        confidence=confidence,
                        limitation=limitation,
                    ),
                }
            )
        return insights

    def _build_operational_alerts(
        self,
        *,
        code_summary_rows: list[dict[str, Any]],
        dimension_summary_rows: list[dict[str, Any]],
        total_saldo: float,
        confidence: float,
        limitation: str,
        dimension_field: str,
    ) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []
        if total_saldo <= 0:
            return alerts
        if dimension_summary_rows:
            top_dimension = dict(dimension_summary_rows[0])
            share = (_as_float(top_dimension.get("saldo_total")) / total_saldo) * 100
            if share >= 45:
                alerts.append(
                    {
                        "id": "high_dimension_concentration",
                        "severity": "medium",
                        "text": f"Alta concentracion operativa: el {_humanize(dimension_field).lower()} {_as_str(top_dimension.get(dimension_field))} supera {round(share, 1)}% del saldo agregado.",
                        "evidence": self._evidence(
                            source_block="result_set",
                            columns_used=[dimension_field, "saldo"],
                            formula=f"top {dimension_field} share threshold >= 45%",
                            row_count_used=max(len(dimension_summary_rows), 1),
                            confidence=confidence,
                            limitation=limitation,
                        ),
                    }
                )
        if code_summary_rows:
            top_code = dict(code_summary_rows[0])
            share = (_as_float(top_code.get("saldo_total")) / total_saldo) * 100
            if share >= 40:
                alerts.append(
                    {
                        "id": "high_code_concentration",
                        "severity": "medium",
                        "text": f"Concentracion por codigo: {_as_str(top_code.get('codigo'))} supera {round(share, 1)}% del saldo agregado.",
                        "evidence": self._evidence(
                            source_block="result_set",
                            columns_used=["codigo", "saldo"],
                            formula="top codigo share threshold >= 40%",
                            row_count_used=max(len(code_summary_rows), 1),
                            confidence=confidence,
                            limitation=limitation,
                        ),
                    }
                )
        return alerts
