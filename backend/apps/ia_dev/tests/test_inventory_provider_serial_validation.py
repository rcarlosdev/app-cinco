from __future__ import annotations

import base64
from collections import defaultdict
from copy import deepcopy

from django.test import SimpleTestCase

from apps.ia_dev.application.orchestration.dashboard_composition_planner import (
    DashboardCompositionPlanner,
)
from apps.ia_dev.domains.inventario_logistica.validador_seriales_proveedor import (
    ValidadorSerialesProveedorService,
)


def _csv_attachment(*, headers: list[str], rows: list[list[str]]) -> dict[str, str]:
    content = "\n".join(
        [",".join(headers), *[",".join(str(value) for value in row) for row in rows]]
    )
    return {
        "name": "seriales_proveedor.csv",
        "mime_type": "text/csv",
        "content_base64": base64.b64encode(content.encode("utf-8")).decode("ascii"),
    }


def _default_discovery() -> dict[str, list[dict[str, object]]]:
    return {
        "existing_tables": [
            {
                "schema": "logistica_cinco",
                "table": "logistica_base_seriales",
                "kind": "base_actual",
                "label": "base actual",
                "fqn": "logistica_cinco.logistica_base_seriales",
                "year": None,
                "columns": ["serial", "estado", "cedula", "movil", "bodega"],
            }
        ],
        "missing_tables": [
            {
                "schema": "z_c3nc4_f3sc1l",
                "table": "logistica_base_seriales_2024",
                "kind": "backup_base",
                "label": "backup base seriales anio 2024",
                "year": 2024,
            }
        ],
    }


class _StubValidator(ValidadorSerialesProveedorService):
    def __init__(
        self,
        *,
        discovery: dict[str, list[dict[str, object]]] | None = None,
        matches: list[dict[str, object]] | None = None,
        personal_rows: list[dict[str, object]] | None = None,
    ):
        super().__init__(dashboard_planner=DashboardCompositionPlanner())
        self.stub_discovery = deepcopy(discovery or _default_discovery())
        self.stub_matches = [dict(item) for item in list(matches or [])]
        self.stub_personal_rows = [dict(item) for item in list(personal_rows or [])]
        self.discovered_years: list[int] = []
        self.last_serials: list[str] = []

    def _discover_tables(self, *, years: list[int]) -> dict[str, object]:
        self.discovered_years = list(years)
        return deepcopy(self.stub_discovery)

    def _query_all_tables(
        self,
        *,
        normalized_serials: list[str],
        tables: list[dict[str, object]],
    ) -> dict[str, object]:
        self.last_serials = list(normalized_serials)
        matches_by_serial: dict[str, list[dict[str, object]]] = defaultdict(list)
        for item in self.stub_matches:
            matches_by_serial[str(item.get("serial_normalizado") or "")].append(dict(item))
        table_results = []
        for table in tables:
            label = str(table.get("label") or "")
            count = sum(1 for item in self.stub_matches if str(item.get("source_label") or "") == label)
            table_results.append({"label": label, "match_count": count})
        return {
            "matches": [dict(item) for item in self.stub_matches],
            "matches_by_serial": matches_by_serial,
            "table_results": table_results,
        }

    def _enrich_personal(self, *, matches: list[dict[str, object]]) -> list[dict[str, object]]:
        return [dict(item) for item in self.stub_personal_rows]


class _UppercaseInfoSchemaPlanner:
    def execute_governed_select(self, **kwargs):
        query = str(kwargs.get("query") or "")
        if "information_schema.columns" in query:
            return {
                "ok": True,
                "rows": [
                    {"COLUMN_NAME": "numero_serial"},
                    {"COLUMN_NAME": "estado"},
                    {"COLUMN_NAME": "cedula"},
                ],
                "rowcount": 3,
            }
        return {"ok": False, "error": "unexpected_query"}


class _CaptureQueryPlanner:
    def __init__(self):
        self.queries: list[str] = []

    def execute_governed_select(self, **kwargs):
        self.queries.append(str(kwargs.get("query") or ""))
        return {
            "ok": True,
            "rows": [
                {
                    "serial_raw": "LD25BA082708",
                    "estado": "BODEGA INGRESO",
                    "lote": "VALORADO",
                    "cedula": "811042087",
                    "bodega": "red_externa",
                    "codigo": "4073898",
                    "fecha": "2026-03-26 11:46:56",
                }
            ],
            "rowcount": 1,
        }


class _CanonicalFallbackSkippingPlanner:
    def __init__(self):
        self.audit_queries = 0
        self.exact_queries = 0
        self.fallback_queries = 0

    def execute_governed_select(self, **kwargs):
        query = str(kwargs.get("query") or "")
        if "<> UPPER(TRIM(CAST(" in query:
            self.audit_queries += 1
            return {"ok": True, "rows": [], "rowcount": 0}
        if " IN (" in query and "UPPER(TRIM(CAST(" in query:
            self.fallback_queries += 1
            return {"ok": True, "rows": [], "rowcount": 0}
        self.exact_queries += 1
        return {"ok": True, "rows": [], "rowcount": 0}


class _NonCanonicalFallbackPlanner:
    def __init__(self):
        self.audit_queries = 0
        self.exact_queries = 0
        self.fallback_queries = 0

    def execute_governed_select(self, **kwargs):
        query = str(kwargs.get("query") or "")
        params = list(kwargs.get("params") or [])
        if "<> UPPER(TRIM(CAST(" in query:
            self.audit_queries += 1
            return {"ok": True, "rows": [{"serial_raw": " sn-1 "}], "rowcount": 1}
        if " IN (" in query and "UPPER(TRIM(CAST(" in query:
            self.fallback_queries += 1
            return {
                "ok": True,
                "rows": [
                    {
                        "serial_raw": params[0] if params else "SN-1",
                        "estado": "BODEGA",
                        "cedula": "",
                    }
                ],
                "rowcount": 1,
            }
        self.exact_queries += 1
        return {"ok": True, "rows": [], "rowcount": 0}


class _InfoSchemaCountingPlanner:
    def __init__(self):
        self.table_exists_calls = 0
        self.table_columns_calls = 0

    def execute_governed_select(self, **kwargs):
        query = str(kwargs.get("query") or "")
        if "information_schema.tables" in query:
            self.table_exists_calls += 1
            return {"ok": True, "rows": [{"table_name": "cinco_base_de_personal"}], "rowcount": 1}
        if "information_schema.columns" in query:
            self.table_columns_calls += 1
            return {
                "ok": True,
                "rows": [
                    {"column_name": "cedula"},
                    {"column_name": "movil"},
                    {"column_name": "nombre"},
                    {"column_name": "apellido"},
                    {"column_name": "empleado"},
                    {"column_name": "estado"},
                ],
                "rowcount": 6,
            }
        return {"ok": True, "rows": [], "rowcount": 0}


class _UnionStagePlanner:
    def __init__(self):
        self.queries: list[str] = []

    def execute_governed_select(self, **kwargs):
        self.queries.append(str(kwargs.get("query") or ""))
        return {
            "ok": True,
            "rows": [
                {
                    "serial_raw": "SN-1",
                    "estado": "HIST-2024",
                    "lote": "",
                    "cedula": "",
                    "edit": "",
                    "movil": "",
                    "bodega": "",
                    "codigo": "",
                    "descripcion": "",
                    "fecha": "",
                    "source_label": "backup base seriales anio 2024",
                    "source_kind": "backup_base",
                    "source_table": "z_c3nc4_f3sc1l.logistica_base_seriales_2024",
                    "source_year": 2024,
                    "source_priority": 1,
                },
                {
                    "serial_raw": "SN-1",
                    "estado": "HIST-2025",
                    "lote": "",
                    "cedula": "",
                    "edit": "",
                    "movil": "",
                    "bodega": "",
                    "codigo": "",
                    "descripcion": "",
                    "fecha": "",
                    "source_label": "backup base seriales anio 2025",
                    "source_kind": "backup_base",
                    "source_table": "z_c3nc4_f3sc1l.logistica_base_seriales_2025",
                    "source_year": 2025,
                    "source_priority": 0,
                },
            ],
            "rowcount": 2,
        }


class _PlaceholderBudgetUnionPlanner:
    def __init__(self):
        self.params_lengths: list[int] = []

    def execute_governed_select(self, **kwargs):
        self.params_lengths.append(len(list(kwargs.get("params") or [])))
        return {"ok": True, "rows": [], "rowcount": 0}


class _RoutingValidator(ValidadorSerialesProveedorService):
    def __init__(self):
        super().__init__(dashboard_planner=DashboardCompositionPlanner())
        self.calls: list[tuple[str, list[str]]] = []

    def _query_table(self, *, table, normalized_serials, lookup_metrics=None):
        label = str(table.get("label") or "")
        serials = list(normalized_serials)
        self.calls.append((label, serials))
        if label == "base actual":
            return [
                {
                    "serial_normalizado": "CUR-1",
                    "source_label": label,
                    "source_kind": "base_actual",
                    "source_table": str(table.get("fqn") or ""),
                    "year": table.get("year"),
                    "estado": "BODEGA",
                    "lote": "",
                    "cedula": "",
                    "edit": "",
                    "movil": "",
                    "bodega": "",
                    "codigo": "",
                    "descripcion": "",
                    "fecha": "",
                }
            ]
        if label == "asociados actual":
            return [
                {
                    "serial_normalizado": "ASOC-1",
                    "source_label": label,
                    "source_kind": "asociados_actual",
                    "source_table": str(table.get("fqn") or ""),
                    "year": table.get("year"),
                    "estado": "MOVIL",
                    "lote": "",
                    "cedula": "123456",
                    "edit": "",
                    "movil": "MOV-1",
                    "bodega": "",
                    "codigo": "",
                    "descripcion": "",
                    "fecha": "",
                }
            ]
        if label == "backup base seriales anio 2025":
            return [
                {
                    "serial_normalizado": "HIST-1",
                    "source_label": label,
                    "source_kind": "backup_base",
                    "source_table": str(table.get("fqn") or ""),
                    "year": table.get("year"),
                    "estado": "HISTORICO",
                    "lote": "",
                    "cedula": "",
                    "edit": "",
                    "movil": "",
                    "bodega": "",
                    "codigo": "",
                    "descripcion": "",
                    "fecha": "",
                }
            ]
        return []


class InventoryProviderSerialValidationTests(SimpleTestCase):
    def test_detects_serial_column_numero_de_serie(self):
        validator = _StubValidator()
        result = validator.validate(
            attachment=_csv_attachment(
                headers=["Número de serie", "Material", "Denominacion", "Familia"],
                rows=[[" abc-123 ", "MAT-1", "Router", "CPE"]],
            ),
            user_message="Valida este archivo del proveedor",
            previous_year=2025,
        )

        row = result["data"]["table"]["rows"][0]
        self.assertEqual(result["status"], "success")
        self.assertEqual(row["serial_proveedor"], "abc-123")
        self.assertEqual(row["encontrado"], "NO")
        self.assertEqual(validator.last_serials, ["ABC-123"])

    def test_get_table_columns_accepts_uppercase_information_schema_keys(self):
        validator = ValidadorSerialesProveedorService(
            planner=_UppercaseInfoSchemaPlanner(),
            dashboard_planner=DashboardCompositionPlanner(),
        )

        columns = validator._get_table_columns(
            schema="logistica_cinco",
            table="logistica_base_seriales",
        )

        self.assertEqual(columns, ["numero_serial", "estado", "cedula"])

    def test_detects_renamed_serial_column_semantically(self):
        validator = _StubValidator()
        result = validator.validate(
            attachment=_csv_attachment(
                headers=["Serial equipo", "Material", "Familia"],
                rows=[["SN-900", "MAT-9", "ONT"]],
            ),
            user_message="Cruza seriales externos del contratante",
            previous_year=2025,
        )

        business_response = result["data"]["business_response"]
        self.assertEqual(result["status"], "success")
        self.assertEqual(
            business_response["metadata"]["filters"]["serial_column"],
            "Serial equipo",
        )

    def test_resolve_table_field_prefers_exact_logical_name(self):
        validator = _StubValidator()

        selected = validator._resolve_table_field(
            columns=["documento", "cedula", "codigo_empleado"],
            logical_name="cedula",
        )

        self.assertEqual(selected, "cedula")

    def test_marks_duplicate_serials_inside_file(self):
        validator = _StubValidator()
        result = validator.validate(
            attachment=_csv_attachment(
                headers=["Numero de serie", "Material"],
                rows=[["AA-1", "MAT-1"], ["AA-1", "MAT-1"]],
            ),
            user_message="Valida duplicados",
            previous_year=2025,
        )

        rows = result["data"]["table"]["rows"]
        self.assertEqual(result["data"]["kpis"]["duplicados_archivo"], 1)
        self.assertTrue(all(row["duplicado_en_archivo"] == "SI" for row in rows))
        self.assertTrue(all(row["ocurrencias_archivo"] == 2 for row in rows))

    def test_resolves_match_in_current_base(self):
        validator = _StubValidator(
            matches=[
                {
                    "serial_normalizado": "ZX-1",
                    "source_label": "base actual",
                    "source_kind": "base_actual",
                    "source_table": "logistica_cinco.logistica_base_seriales",
                    "year": None,
                    "estado": "BODEGA CENTRAL",
                    "lote": "VALORADO",
                    "cedula": "",
                    "movil": "",
                    "bodega": "BOG-1",
                    "codigo": "INT-1",
                    "descripcion": "Equipo interno",
                    "fecha": "2025-01-03 10:00:00",
                }
            ]
        )
        result = validator.validate(
            attachment=_csv_attachment(
                headers=["Numero de serie"],
                rows=[["ZX-1"]],
            ),
            user_message="Valida seriales",
            previous_year=2025,
        )

        row = result["data"]["table"]["rows"][0]
        self.assertEqual(row["encontrado"], "SI")
        self.assertEqual(row["fuente"], "base actual")
        self.assertEqual(row["solo_historico"], "NO")
        self.assertEqual(row["lote"], "VALORADO")
        self.assertEqual(row["bodega"], "BOG-1")
        self.assertEqual(result["data"]["kpis"]["coincidencias_base_actual"], 1)
        self.assertEqual(result["data"]["kpis"]["fuente_final_base_actual"], 1)

    def test_query_table_uses_unquoted_registered_table_name(self):
        planner = _CaptureQueryPlanner()
        validator = ValidadorSerialesProveedorService(
            planner=planner,
            dashboard_planner=DashboardCompositionPlanner(),
        )

        rows = validator._query_table(
            table={
                "schema": "logistica_cinco",
                "table": "logistica_base_seriales",
                "kind": "base_actual",
                "label": "base actual",
                "fqn": "logistica_cinco.logistica_base_seriales",
                "year": None,
                "columns": ["numero_serial", "estado", "cedula", "bodega", "codigo", "fecha"],
            },
            normalized_serials=["LD25BA082708"],
        )

        self.assertEqual(len(rows), 1)
        self.assertTrue(planner.queries)
        self.assertIn("FROM logistica_cinco.logistica_base_seriales AS s", planner.queries[0])

    def test_query_table_skips_normalized_fallback_when_table_is_canonical(self):
        planner = _CanonicalFallbackSkippingPlanner()
        validator = ValidadorSerialesProveedorService(
            planner=planner,
            dashboard_planner=DashboardCompositionPlanner(),
        )

        rows = validator._query_table(
            table={
                "schema": "logistica_cinco",
                "table": "logistica_base_seriales",
                "kind": "base_actual",
                "label": "base actual",
                "fqn": "logistica_cinco.logistica_base_seriales",
                "year": None,
                "columns": ["numero_serial", "estado", "cedula"],
            },
            normalized_serials=["MISS-1"],
        )

        self.assertEqual(rows, [])
        self.assertEqual(planner.audit_queries, 1)
        self.assertEqual(planner.exact_queries, 1)
        self.assertEqual(planner.fallback_queries, 0)

    def test_query_table_uses_noncanonical_cache_when_table_has_non_canonical_values(self):
        planner = _NonCanonicalFallbackPlanner()
        validator = ValidadorSerialesProveedorService(
            planner=planner,
            dashboard_planner=DashboardCompositionPlanner(),
        )

        rows = validator._query_table(
            table={
                "schema": "logistica_cinco",
                "table": "logistica_seriales_asociados",
                "kind": "asociados_actual",
                "label": "asociados actual",
                "fqn": "logistica_cinco.logistica_seriales_asociados",
                "year": None,
                "columns": ["numero_serial", "estado", "cedula"],
            },
            normalized_serials=["SN-1"],
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["serial_normalizado"], "SN-1")
        self.assertEqual(planner.audit_queries, 1)
        self.assertEqual(planner.exact_queries, 1)
        self.assertEqual(planner.fallback_queries, 0)

    def test_query_all_tables_uses_current_tables_for_all_and_history_only_for_unresolved(self):
        validator = _RoutingValidator()

        result = validator._query_all_tables(
            normalized_serials=["CUR-1", "ASOC-1", "HIST-1"],
            tables=[
                {
                    "schema": "z_c3nc4_f3sc1l",
                    "table": "logistica_base_seriales_2025",
                    "kind": "backup_base",
                    "label": "backup base seriales anio 2025",
                    "fqn": "z_c3nc4_f3sc1l.logistica_base_seriales_2025",
                    "year": 2025,
                    "columns": ["serial"],
                },
                {
                    "schema": "logistica_cinco",
                    "table": "logistica_seriales_asociados",
                    "kind": "asociados_actual",
                    "label": "asociados actual",
                    "fqn": "logistica_cinco.logistica_seriales_asociados",
                    "year": None,
                    "columns": ["serial"],
                },
                {
                    "schema": "logistica_cinco",
                    "table": "logistica_base_seriales",
                    "kind": "base_actual",
                    "label": "base actual",
                    "fqn": "logistica_cinco.logistica_base_seriales",
                    "year": None,
                    "columns": ["serial"],
                },
            ],
        )

        self.assertEqual(
            validator.calls,
            [
                ("base actual", ["CUR-1", "ASOC-1", "HIST-1"]),
                ("asociados actual", ["ASOC-1", "HIST-1"]),
                ("backup base seriales anio 2025", ["HIST-1"]),
            ],
        )
        self.assertEqual(len(list(result["matches_by_serial"].get("CUR-1") or [])), 1)
        self.assertEqual(len(list(result["matches_by_serial"].get("ASOC-1") or [])), 1)
        self.assertEqual(len(list(result["matches_by_serial"].get("HIST-1") or [])), 1)

    def test_validate_keeps_precedence_when_same_serial_exists_in_current_and_historical_sources(self):
        validator = _StubValidator(
            discovery={
                "existing_tables": [
                    {
                        "schema": "logistica_cinco",
                        "table": "logistica_base_seriales",
                        "kind": "base_actual",
                        "label": "base actual",
                        "fqn": "logistica_cinco.logistica_base_seriales",
                        "year": None,
                        "columns": ["serial", "estado"],
                    },
                    {
                        "schema": "logistica_cinco",
                        "table": "logistica_seriales_asociados",
                        "kind": "asociados_actual",
                        "label": "asociados actual",
                        "fqn": "logistica_cinco.logistica_seriales_asociados",
                        "year": None,
                        "columns": ["serial", "estado"],
                    },
                    {
                        "schema": "z_c3nc4_f3sc1l",
                        "table": "logistica_base_seriales_2025",
                        "kind": "backup_base",
                        "label": "backup base seriales anio 2025",
                        "fqn": "z_c3nc4_f3sc1l.logistica_base_seriales_2025",
                        "year": 2025,
                        "columns": ["serial", "estado"],
                    },
                ],
                "missing_tables": [],
            },
            matches=[
                {
                    "serial_normalizado": "MIX-1",
                    "source_label": "backup base seriales anio 2025",
                    "source_kind": "backup_base",
                    "source_table": "z_c3nc4_f3sc1l.logistica_base_seriales_2025",
                    "year": 2025,
                    "estado": "HISTORICO",
                    "cedula": "",
                    "movil": "",
                    "bodega": "",
                    "codigo": "",
                    "descripcion": "",
                    "fecha": "2025-01-01 00:00:00",
                },
                {
                    "serial_normalizado": "MIX-1",
                    "source_label": "asociados actual",
                    "source_kind": "asociados_actual",
                    "source_table": "logistica_cinco.logistica_seriales_asociados",
                    "year": None,
                    "estado": "ASOCIADO_MOVIL",
                    "cedula": "12345",
                    "movil": "MOV-1",
                    "bodega": "",
                    "codigo": "",
                    "descripcion": "",
                    "fecha": "2026-01-01 00:00:00",
                },
                {
                    "serial_normalizado": "MIX-1",
                    "source_label": "base actual",
                    "source_kind": "base_actual",
                    "source_table": "logistica_cinco.logistica_base_seriales",
                    "year": None,
                    "estado": "BODEGA CENTRAL",
                    "cedula": "",
                    "movil": "",
                    "bodega": "BOD-1",
                    "codigo": "",
                    "descripcion": "",
                    "fecha": "2026-02-01 00:00:00",
                },
            ],
        )

        result = validator.validate(
            attachment=_csv_attachment(headers=["Numero de serie"], rows=[["MIX-1"]]),
            user_message="Valida precedencia",
            previous_year=2025,
        )

        row = result["data"]["table"]["rows"][0]
        self.assertEqual(row["fuente"], "base actual")
        self.assertEqual(row["solo_historico"], "NO")
        self.assertIn("base actual", row["fuentes_coincidencia"].lower())
        self.assertIn("asociados actual", row["fuentes_coincidencia"].lower())
        self.assertIn("backup", row["fuentes_coincidencia"].lower())

    def test_personal_metadata_queries_are_cached_between_calls(self):
        planner = _InfoSchemaCountingPlanner()
        validator = ValidadorSerialesProveedorService(
            planner=planner,
            dashboard_planner=DashboardCompositionPlanner(),
        )
        matches = [
            {"estado": "MOVIL", "cedula": "123456", "edit": ""},
            {"estado": "MOVIL", "cedula": "789012", "edit": ""},
        ]

        validator._enrich_personal(matches=matches)
        validator._enrich_personal(matches=matches)

        self.assertEqual(planner.table_exists_calls, 1)
        self.assertEqual(planner.table_columns_calls, 1)

    def test_union_backup_stage_uses_single_query_and_keeps_newest_table_precedence(self):
        planner = _UnionStagePlanner()
        validator = ValidadorSerialesProveedorService(
            planner=planner,
            dashboard_planner=DashboardCompositionPlanner(),
        )
        metrics: dict[str, object] = {}

        rows = validator._query_tables_union_stage(
            tables=[
                {
                    "schema": "z_c3nc4_f3sc1l",
                    "table": "logistica_base_seriales_2025",
                    "kind": "backup_base",
                    "label": "backup base seriales anio 2025",
                    "fqn": "z_c3nc4_f3sc1l.logistica_base_seriales_2025",
                    "year": 2025,
                    "columns": ["serial", "estado"],
                },
                {
                    "schema": "z_c3nc4_f3sc1l",
                    "table": "logistica_base_seriales_2024",
                    "kind": "backup_base",
                    "label": "backup base seriales anio 2024",
                    "fqn": "z_c3nc4_f3sc1l.logistica_base_seriales_2024",
                    "year": 2024,
                    "columns": ["serial", "estado"],
                },
            ],
            normalized_serials=["SN-1"],
            lookup_metrics=metrics,
            skip_noncanonical_probe=True,
        )

        self.assertEqual(len(planner.queries), 1)
        self.assertIn("UNION ALL", planner.queries[0])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_table"], "z_c3nc4_f3sc1l.logistica_base_seriales_2025")
        self.assertEqual(int(metrics["query_count"]), 1)
        self.assertEqual(str(metrics["normalized_fallback_reason"]), "disabled_for_large_provider_validation")

    def test_union_backup_stage_caps_chunk_size_by_placeholder_budget(self):
        planner = _PlaceholderBudgetUnionPlanner()
        validator = ValidadorSerialesProveedorService(
            planner=planner,
            dashboard_planner=DashboardCompositionPlanner(),
        )
        metrics: dict[str, object] = {}
        serials = [f"SN-{index:04d}" for index in range(4000)]
        original_chunk_size = (
            validator._query_tables_union_stage.__globals__["_DB_LOOKUP_CHUNK_SIZE"]
        )
        validator._query_tables_union_stage.__globals__["_DB_LOOKUP_CHUNK_SIZE"] = 2000

        try:
            validator._query_tables_union_stage(
                tables=[
                    {
                        "schema": "z_c3nc4_f3sc1l",
                        "table": "logistica_base_seriales_2025",
                        "kind": "backup_base",
                        "label": "backup base seriales anio 2025",
                        "fqn": "z_c3nc4_f3sc1l.logistica_base_seriales_2025",
                        "year": 2025,
                        "columns": ["serial", "estado"],
                    },
                    {
                        "schema": "z_c3nc4_f3sc1l",
                        "table": "logistica_base_seriales_2024",
                        "kind": "backup_base",
                        "label": "backup base seriales anio 2024",
                        "fqn": "z_c3nc4_f3sc1l.logistica_base_seriales_2024",
                        "year": 2024,
                        "columns": ["serial", "estado"],
                    },
                    {
                        "schema": "z_c3nc4_f3sc1l",
                        "table": "logistica_base_seriales_2023",
                        "kind": "backup_base",
                        "label": "backup base seriales anio 2023",
                        "fqn": "z_c3nc4_f3sc1l.logistica_base_seriales_2023",
                        "year": 2023,
                        "columns": ["serial", "estado"],
                    },
                ],
                normalized_serials=serials,
                lookup_metrics=metrics,
                skip_noncanonical_probe=True,
            )
        finally:
            validator._query_tables_union_stage.__globals__["_DB_LOOKUP_CHUNK_SIZE"] = original_chunk_size

        self.assertEqual(int(metrics["chunk_size"]), 1828)
        self.assertGreater(len(planner.params_lengths), 2)
        self.assertTrue(all(length <= 5499 for length in planner.params_lengths))

    def test_resolves_match_only_in_historical_backup(self):
        validator = _StubValidator(
            discovery={
                "existing_tables": [
                    {
                        "schema": "z_c3nc4_f3sc1l",
                        "table": "logistica_base_seriales_2024",
                        "kind": "backup_base",
                        "label": "backup base seriales anio 2024",
                        "fqn": "z_c3nc4_f3sc1l.logistica_base_seriales_2024",
                        "year": 2024,
                        "columns": ["serial", "estado"],
                    }
                ],
                "missing_tables": [],
            },
            matches=[
                {
                    "serial_normalizado": "HIST-1",
                    "source_label": "backup base seriales anio 2024",
                    "source_kind": "backup_base",
                    "source_table": "z_c3nc4_f3sc1l.logistica_base_seriales_2024",
                    "year": 2024,
                    "estado": "BACKUP HISTORICO",
                    "cedula": "",
                    "movil": "",
                    "bodega": "",
                    "codigo": "",
                    "descripcion": "",
                    "fecha": "2024-12-31 23:59:59",
                }
            ],
        )
        result = validator.validate(
            attachment=_csv_attachment(
                headers=["Numero de serie"],
                rows=[["HIST-1"]],
            ),
            user_message="Valida historico",
            previous_year=2025,
        )

        row = result["data"]["table"]["rows"][0]
        self.assertEqual(row["encontrado"], "SI")
        self.assertEqual(row["solo_historico"], "SI")
        self.assertIn("backup base seriales anio 2024", row["fuente"])
        self.assertEqual(result["data"]["kpis"]["coincidencias_historico"], 1)
        self.assertEqual(result["data"]["kpis"]["fuente_final_historico"], 1)

    def test_keeps_not_found_serial_without_inventing_match(self):
        validator = _StubValidator()
        result = validator.validate(
            attachment=_csv_attachment(
                headers=["Numero de serie"],
                rows=[["MISS-1"]],
            ),
            user_message="Valida no encontrados",
            previous_year=2025,
        )

        row = result["data"]["table"]["rows"][0]
        self.assertEqual(row["encontrado"], "NO")
        self.assertEqual(row["fuente"], "no encontrado")
        self.assertIn("No hubo coincidencia", row["observacion_operativa"])

    def test_enriches_responsible_from_cedula_when_estado_contains_movil(self):
        validator = _StubValidator(
            matches=[
                {
                    "serial_normalizado": "MOV-1",
                    "source_label": "asociados actual",
                    "source_kind": "asociados_actual",
                    "source_table": "logistica_cinco.logistica_seriales_asociados",
                    "year": None,
                    "estado": "EN MOVIL OPERATIVO",
                    "cedula": "123456",
                    "movil": "MOV-77",
                    "bodega": "",
                    "codigo": "INT-9",
                    "descripcion": "ONU",
                    "fecha": "2025-02-01 08:30:00",
                }
            ],
            personal_rows=[
                {
                    "cedula": "123456",
                    "nombre": "ANA",
                    "apellido": "GOMEZ",
                    "empleado": "ANA GOMEZ",
                    "movil": "MOV-77",
                }
            ],
        )
        result = validator.validate(
            attachment=_csv_attachment(
                headers=["Numero de serie"],
                rows=[["MOV-1"]],
            ),
            user_message="Valida serial movil",
            previous_year=2025,
        )

        row = result["data"]["table"]["rows"][0]
        self.assertEqual(row["estado_contiene_movil"], "SI")
        self.assertEqual(row["cedula_original"], "123456")
        self.assertEqual(row["responsable_candidate_source"], "cedula")
        self.assertTrue(bool(row["responsable_enriched"]))
        self.assertEqual(row["cedula_persona"], "123456")
        self.assertEqual(row["empleado"], "ANA GOMEZ")
        self.assertEqual(row["movil_asociado"], "MOV-77")

    def test_enriches_responsible_from_edit_when_cedula_is_not_person(self):
        validator = _StubValidator(
            matches=[
                {
                    "serial_normalizado": "MOV-EDIT-1",
                    "source_label": "asociados actual",
                    "source_kind": "asociados_actual",
                    "source_table": "logistica_cinco.logistica_seriales_asociados",
                    "year": None,
                    "estado": "EN MOVIL OPERATIVO",
                    "cedula": "OT-7788",
                    "edit": "987654",
                    "movil": "MOV-90",
                    "bodega": "",
                    "codigo": "INT-10",
                    "descripcion": "ONU",
                    "fecha": "2025-02-01 08:30:00",
                }
            ],
            personal_rows=[
                {
                    "cedula": "987654",
                    "nombre": "JOSE",
                    "apellido": "RUIZ",
                    "empleado": "JOSE RUIZ",
                    "movil": "MOV-90",
                }
            ],
        )
        result = validator.validate(
            attachment=_csv_attachment(
                headers=["Numero de serie"],
                rows=[["MOV-EDIT-1"]],
            ),
            user_message="Valida serial movil",
            previous_year=2025,
        )

        row = result["data"]["table"]["rows"][0]
        self.assertEqual(row["cedula_original"], "OT-7788")
        self.assertEqual(row["edit_original"], "987654")
        self.assertEqual(row["responsable_candidate_source"], "edit")
        self.assertEqual(row["responsable_candidate_value"], "987654")
        self.assertTrue(bool(row["responsable_enriched"]))
        self.assertEqual(row["cedula_persona"], "987654")
        self.assertEqual(row["empleado"], "JOSE RUIZ")

    def test_asociado_movil_uses_edit_without_asserting_success_without_match(self):
        validator = _StubValidator(
            matches=[
                {
                    "serial_normalizado": "MOV-ASOC-1",
                    "source_label": "asociados actual",
                    "source_kind": "asociados_actual",
                    "source_table": "logistica_cinco.logistica_seriales_asociados",
                    "year": None,
                    "estado": "ASOCIADO_MOVIL",
                    "cedula": "OT-001",
                    "edit": "44332211",
                    "movil": "MOV-200",
                    "bodega": "",
                    "codigo": "INT-11",
                    "descripcion": "ONU",
                    "fecha": "2025-02-01 08:30:00",
                }
            ],
            personal_rows=[],
        )
        result = validator.validate(
            attachment=_csv_attachment(
                headers=["Numero de serie"],
                rows=[["MOV-ASOC-1"]],
            ),
            user_message="Valida serial movil asociado",
            previous_year=2025,
        )

        row = result["data"]["table"]["rows"][0]
        self.assertEqual(row["estado_contiene_movil"], "SI")
        self.assertEqual(row["estado_contiene_asociado"], "SI")
        self.assertEqual(row["responsable_candidate_source"], "edit")
        self.assertEqual(row["responsable_candidate_value"], "44332211")
        self.assertFalse(bool(row["responsable_enriched"]))
        self.assertEqual(row["cedula_persona"], "")
        self.assertIn(
            "Se encontro identificador asociado, pero no se pudo enriquecer responsable/persona con evidencia de personal.",
            row["limitation"],
        )

    def test_marks_movil_without_match_in_personal_as_not_enriched(self):
        validator = _StubValidator(
            matches=[
                {
                    "serial_normalizado": "MOV-NO-PERSON",
                    "source_label": "base actual",
                    "source_kind": "base_actual",
                    "source_table": "logistica_cinco.logistica_base_seriales",
                    "year": None,
                    "estado": "MOVIL TECNICO",
                    "cedula": "123123",
                    "edit": "",
                    "movil": "MOV-X",
                    "bodega": "",
                    "codigo": "INT-12",
                    "descripcion": "ONU",
                    "fecha": "2025-02-01 08:30:00",
                }
            ],
            personal_rows=[],
        )
        result = validator.validate(
            attachment=_csv_attachment(
                headers=["Numero de serie"],
                rows=[["MOV-NO-PERSON"]],
            ),
            user_message="Valida serial movil",
            previous_year=2025,
        )

        row = result["data"]["table"]["rows"][0]
        self.assertEqual(row["responsable_candidate_source"], "cedula")
        self.assertEqual(row["responsable_candidate_value"], "123123")
        self.assertFalse(bool(row["responsable_enriched"]))
        self.assertEqual(row["cedula_persona"], "")
        self.assertIn("no se pudo enriquecer responsable/persona", row["observacion_operativa"].lower())

    def test_reports_missing_historical_tables_without_failing(self):
        validator = _StubValidator()
        result = validator.validate(
            attachment=_csv_attachment(
                headers=["Numero de serie"],
                rows=[["MISS-HIST"]],
            ),
            user_message="Valida historicos faltantes",
            previous_year=2025,
        )

        row = result["data"]["table"]["rows"][0]
        evidence_summary = result["data"]["business_response"]["evidence_summary"]
        self.assertIn("backup base seriales anio 2024", row["tablas_historicas_no_existian"])
        self.assertIn(
            "backup base seriales anio 2024",
            evidence_summary["historical_tables_missing"],
        )
        self.assertEqual(validator.discovered_years, [2023, 2024, 2025])

    def test_select_best_match_tolerates_non_unix_safe_dates(self):
        validator = _StubValidator()

        selected = validator._select_best_match(
            serial_matches=[
                {
                    "source_kind": "base_actual",
                    "year": None,
                    "fecha": "1900-01-01 00:00:00",
                },
                {
                    "source_kind": "backup_base",
                    "year": 2025,
                    "fecha": "2025-01-01 00:00:00",
                },
            ]
        )

        self.assertEqual(selected["source_kind"], "base_actual")

    def test_returns_empty_result_for_empty_file(self):
        validator = _StubValidator()
        result = validator.validate(
            attachment=_csv_attachment(
                headers=["Numero de serie"],
                rows=[],
            ),
            user_message="Valida archivo vacio",
            previous_year=2025,
        )

        self.assertEqual(result["status"], "empty_result")
        self.assertEqual(result["data"]["table"]["rowcount"], 0)
        self.assertIn("archivo no contiene filas", result["reply"].lower())

    def test_dashboard_composition_contains_kpis_charts_and_drilldowns(self):
        validator = _StubValidator(
            matches=[
                {
                    "serial_normalizado": "AA-1",
                    "source_label": "base actual",
                    "source_kind": "base_actual",
                    "source_table": "logistica_cinco.logistica_base_seriales",
                    "year": None,
                    "estado": "EN MOVIL",
                    "cedula": "10",
                    "movil": "MOV-1",
                    "bodega": "BOD-1",
                    "codigo": "COD-1",
                    "descripcion": "Equipo 1",
                    "fecha": "2025-01-01 10:00:00",
                },
                {
                    "serial_normalizado": "BB-2",
                    "source_label": "backup asociados anio 2024",
                    "source_kind": "backup_asociados",
                    "source_table": "z_c3nc4_f3sc1l.logistica_seriales_asociados_2024",
                    "year": 2024,
                    "estado": "RETIRADO",
                    "cedula": "",
                    "movil": "",
                    "bodega": "",
                    "codigo": "COD-2",
                    "descripcion": "Equipo 2",
                    "fecha": "2024-06-01 10:00:00",
                },
            ],
            personal_rows=[
                {
                    "cedula": "10",
                    "nombre": "LUIS",
                    "apellido": "RUIZ",
                    "empleado": "LUIS RUIZ",
                    "movil": "MOV-1",
                }
            ],
        )
        result = validator.validate(
            attachment=_csv_attachment(
                headers=["Numero de serie", "Material", "Familia"],
                rows=[["AA-1", "MAT-A", "CPE"], ["BB-2", "MAT-B", "CPE"], ["CC-3", "MAT-B", "CPE"]],
            ),
            user_message="Valida dashboard proveedor",
            previous_year=2025,
        )

        composition = result["data"]["business_response"]["dashboard_composition"]
        kpi_ids = {item["id"] for item in composition["primary_kpis"]}
        chart_ids = {item["id"] for item in composition["recommended_charts"]}
        table_ids = {item["id"] for item in composition["priority_tables"]}
        self.assertIn("total_filas_archivo", kpi_ids)
        self.assertIn("encontrados_unicos", kpi_ids)
        self.assertIn("moviles_con_responsable_enriquecido", kpi_ids)
        self.assertIn("chart_distribucion_fuente", chart_ids)
        self.assertIn("chart_top_moviles_personas", chart_ids)
        self.assertIn("resultado_por_serial", table_ids)
        self.assertIn("seriales_en_movil", table_ids)
        self.assertIn("evidencia_tecnica_colapsada", table_ids)

    def test_kpis_separate_rows_and_unique_counts(self):
        validator = _StubValidator(
            matches=[
                {
                    "serial_normalizado": "AA-1",
                    "source_label": "base actual",
                    "source_kind": "base_actual",
                    "source_table": "logistica_cinco.logistica_base_seriales",
                    "year": None,
                    "estado": "BODEGA",
                    "cedula": "",
                    "edit": "",
                    "movil": "",
                    "bodega": "B1",
                    "codigo": "C1",
                    "descripcion": "Equipo",
                    "fecha": "2025-01-01 10:00:00",
                }
            ],
        )
        result = validator.validate(
            attachment=_csv_attachment(
                headers=["Numero de serie"],
                rows=[["AA-1"], ["AA-1"], ["MISS-1"]],
            ),
            user_message="Valida kpis",
            previous_year=2025,
        )

        kpis = result["data"]["kpis"]
        self.assertEqual(kpis["total_filas_archivo"], 3)
        self.assertEqual(kpis["seriales_unicos"], 2)
        self.assertEqual(kpis["duplicados_archivo"], 1)
        self.assertEqual(kpis["encontrados_por_fila"], 2)
        self.assertEqual(kpis["encontrados_unicos"], 1)
        self.assertEqual(kpis["no_encontrados_por_fila"], 1)
        self.assertEqual(kpis["no_encontrados_unicos"], 1)
        self.assertEqual(kpis["coincidencias_base_actual"], 1)
        self.assertEqual(kpis["fuente_final_base_actual"], 1)

    def test_payload_is_reduced_to_preview_and_keeps_full_export_artifact(self):
        validator = _StubValidator()
        rows = [[f"SN-{index:03d}"] for index in range(250)]
        result = validator.validate(
            attachment=_csv_attachment(
                headers=["Numero de serie"],
                rows=rows,
            ),
            user_message="Valida payload reducido",
            previous_year=2025,
        )

        table = result["data"]["table"]
        self.assertEqual(table["total_records"], 250)
        self.assertEqual(table["returned_records"], 200)
        self.assertTrue(bool(table["truncated"]))
        self.assertTrue(bool(table["export_truncated"]))
        self.assertEqual(table["export_limit"], 200)
        self.assertEqual(len(table["rows"]), 200)
        artifact = table["export_artifact"]
        self.assertTrue(bool(artifact["available"]))
        self.assertTrue(bool(artifact["artifact_id"]))
        self.assertFalse("path" in artifact)
        self.assertEqual(int(artifact["record_count"]), 250)

    def test_drilldown_tables_keep_preview_but_publish_full_export_artifact(self):
        validator = _StubValidator()
        rows = [[f"MISS-{index:03d}"] for index in range(60)]
        result = validator.validate(
            attachment=_csv_attachment(
                headers=["Numero de serie"],
                rows=rows,
            ),
            user_message="Valida drilldown completo",
            previous_year=2025,
        )

        composition = result["data"]["business_response"]["dashboard_composition"]
        drilldown = next(
            item for item in composition["priority_tables"] if item["id"] == "seriales_no_encontrados"
        )
        table = drilldown["table"]

        self.assertEqual(int(table["rowcount"]), 60)
        self.assertEqual(int(table["returned_records"]), 50)
        self.assertTrue(bool(table["truncated"]))
        self.assertTrue(bool(table["export_truncated"]))
        self.assertEqual(int(table["export_records"]), 60)
        self.assertTrue(bool(dict(table.get("export_artifact") or {}).get("artifact_id")))
        self.assertEqual(int(dict(table.get("export_artifact") or {}).get("record_count") or 0), 60)
