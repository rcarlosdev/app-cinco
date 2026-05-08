from __future__ import annotations

from io import StringIO
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.test import SimpleTestCase

from apps.ia_dev.services.ai_dictionary_deduplication_service import (
    AIDictionaryDeduplicationService,
)


class Phase8DictionaryDeduplicationTests(SimpleTestCase):
    def setUp(self):
        self.service = AIDictionaryDeduplicationService(context_loader=MagicMock())
        self.service.context_loader.load_from_files.return_value = {}

    def test_detects_equivalent_field_duplicates(self):
        rows = {
            "domains": [],
            "tables": [],
            "fields": [
                {
                    "id": 4,
                    "tabla_id": 1,
                    "domain_code": "EMPLEADOS",
                    "domain_key": "empleados",
                    "schema_name": "cincosas_cincosas",
                    "table_name": "cinco_base_de_personal",
                    "campo_logico": "area",
                    "column_name": "area",
                    "tipo_campo": "LITERAL",
                    "tipo_dato_tecnico": "varchar",
                    "es_clave": 0,
                    "supports_metric": 0,
                    "supports_group_by": 1,
                    "supports_dimension": 1,
                    "is_date": 0,
                    "is_identifier": 0,
                },
                {
                    "id": 51,
                    "tabla_id": 2,
                    "domain_code": "AUSENTISMOS",
                    "domain_key": "ausentismo",
                    "schema_name": "cincosas_cincosas",
                    "table_name": "cinco_base_de_personal",
                    "campo_logico": "area_negocio",
                    "column_name": "area",
                    "tipo_campo": "LITERAL",
                    "tipo_dato_tecnico": "varchar",
                    "es_clave": 0,
                    "supports_metric": 0,
                    "supports_group_by": 1,
                    "supports_dimension": 1,
                    "is_date": 0,
                    "is_identifier": 0,
                },
            ],
            "synonyms": [],
            "rules": [],
            "relations": [],
        }

        candidates = self.service._build_field_candidates(rows=rows)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(str(candidates[0].get("classification") or ""), "equivalent")
        self.assertFalse(bool(candidates[0].get("can_auto_merge")))
        self.assertTrue(bool(candidates[0].get("requires_manual_review")))

    def test_detects_conflicting_field_duplicates(self):
        rows = {
            "domains": [],
            "tables": [],
            "fields": [
                {
                    "id": 4,
                    "tabla_id": 1,
                    "domain_code": "EMPLEADOS",
                    "domain_key": "empleados",
                    "schema_name": "cincosas_cincosas",
                    "table_name": "cinco_base_de_personal",
                    "campo_logico": "cedula",
                    "column_name": "cedula",
                    "tipo_campo": "LITERAL",
                    "tipo_dato_tecnico": "varchar",
                    "es_clave": 1,
                    "supports_metric": 0,
                    "supports_group_by": 0,
                    "supports_dimension": 0,
                    "is_date": 0,
                    "is_identifier": 1,
                },
                {
                    "id": 5,
                    "tabla_id": 1,
                    "domain_code": "EMPLEADOS",
                    "domain_key": "empleados",
                    "schema_name": "cincosas_cincosas",
                    "table_name": "cinco_base_de_personal",
                    "campo_logico": "cedula_texto",
                    "column_name": "cedula",
                    "tipo_campo": "LITERAL",
                    "tipo_dato_tecnico": "varchar",
                    "es_clave": 0,
                    "supports_metric": 1,
                    "supports_group_by": 0,
                    "supports_dimension": 0,
                    "is_date": 0,
                    "is_identifier": 0,
                },
            ],
            "synonyms": [],
            "rules": [],
            "relations": [],
        }

        candidates = self.service._build_field_candidates(rows=rows)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(str(candidates[0].get("classification") or ""), "conflicting")
        self.assertFalse(bool(candidates[0].get("can_auto_merge")))

    def test_dry_run_does_not_modify_db(self):
        analysis = {
            "domains": ["ausentismo"],
            "legacy_duplicate_signal_count": 0,
            "total_duplicates": 1,
            "auto_merge_candidates": 1,
            "manual_review_required": 1,
            "conflicts": 0,
            "duplicates_by_type": {"field": 1},
            "legacy_duplicate_signal_breakdown": {},
            "recommended_sql_or_actions": [],
            "duplicates": [
                {
                    "entity_type": "field",
                    "can_auto_merge": True,
                    "canonical_record": {"id": 1},
                    "duplicate_record": {"id": 2},
                }
            ],
        }
        with patch(
            "apps.ia_dev.management.commands.ia_dictionary_deduplicate.AIDictionaryDeduplicationService.analyze",
            return_value=analysis,
        ):
            with patch(
                "apps.ia_dev.management.commands.ia_dictionary_deduplicate.AIDictionaryDeduplicationService._apply_safe_candidate"
            ) as apply_candidate:
                output = StringIO()
                call_command(
                    "ia_dictionary_deduplicate",
                    "--domain",
                    "ausentismo",
                    "--dry-run",
                    stdout=output,
                )
        apply_candidate.assert_not_called()
        self.assertIn("dry_run=True", output.getvalue())

    def test_apply_safe_only_applies_safe_candidates(self):
        analysis = {
            "duplicates": [
                {
                    "entity_type": "field",
                    "can_auto_merge": True,
                    "canonical_record": {"id": 1},
                    "duplicate_record": {"id": 2},
                },
                {
                    "entity_type": "field",
                    "can_auto_merge": False,
                    "canonical_record": {"id": 1},
                    "duplicate_record": {"id": 3},
                },
            ]
        }
        with patch.object(
            self.service,
            "_apply_safe_candidate",
            side_effect=[{"entity_type": "field", "status": "applied", "canonical_id": 1, "duplicate_id": 2}],
        ) as apply_candidate:
            result = self.service.apply_safe(analysis=analysis)

        apply_candidate.assert_called_once()
        self.assertEqual(int(result.get("applied_merge_count") or 0), 1)
        self.assertEqual(int(result.get("skipped_merge_count") or 0), 1)

    def test_command_reports_real_data_diagnose_green(self):
        out = StringIO()
        with patch(
            "apps.ia_dev.management.commands.ia_runtime_diagnose.run_functional_validation_suite",
            return_value={
                "domain": "ausentismo",
                "with_empleados": True,
                "questions_executed": 10,
                "real_data": True,
                "passed": 10,
                "failed": 0,
                "fallback_count": 0,
                "sql_assisted_count": 9,
                "handler_count": 1,
                "legacy_count": 0,
                "questions_without_actionable_insight": [],
                "relations_used": [],
                "most_used_columns": [],
                "real_data_validation": {
                    "queries_exitosas": 9,
                    "queries_sin_datos": 0,
                    "errores_sql": 0,
                    "insights_accionables_generados": 9,
                    "columnas_nulas_criticas": [],
                    "casos_tecnicamente_validos_pero_pobres": [],
                },
                "results": [],
                "errors_or_blockers": [],
            },
        ):
            call_command(
                "ia_runtime_diagnose",
                "--domain",
                "ausentismo",
                "--with-empleados",
                "--real-data",
                stdout=out,
            )

        printed = out.getvalue()
        self.assertIn("failed=0", printed)
        self.assertIn("legacy_count=0", printed)
        self.assertIn("errores_sql=0", printed)
