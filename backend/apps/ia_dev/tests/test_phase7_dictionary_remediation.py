from __future__ import annotations

from django.test import SimpleTestCase

from apps.ia_dev.application.runtime.functional_validation_suite import (
    _ausentismo_context,
    _empleados_context,
    build_functional_validation_cases,
)
from apps.ia_dev.services.ai_dictionary_remediation_service import (
    AIDictionaryRemediationService,
)


class Phase7DictionaryRemediationTests(SimpleTestCase):
    def test_curated_manifest_maps_real_schema_aliases(self):
        service = AIDictionaryRemediationService()

        ausentismo_fields = service._curated_fields(domain_code="ausentismo")
        empleados_fields = service._curated_fields(domain_code="empleados")

        self.assertTrue(
            any(
                field["logical_name"] == "sede" and field["column_name"] == "zona_nodo"
                for field in ausentismo_fields
            )
        )
        self.assertTrue(
            any(
                field["logical_name"] == "tipo_labor" and field["column_name"] == "tipo_labor"
                for field in empleados_fields
            )
        )

    def test_runtime_validation_context_uses_real_columns(self):
        ausentismo = _ausentismo_context()
        empleados = _empleados_context()

        self.assertIn("zona_nodo", list(ausentismo.get("allowed_columns") or []))
        self.assertNotIn("dias_perdidos", list(ausentismo.get("allowed_columns") or []))
        self.assertIn("fnacimiento", list(empleados.get("allowed_columns") or []))

    def test_validation_suite_replaces_unsupported_dias_perdidos_case(self):
        case_ids = {case.case_id for case in build_functional_validation_cases()}

        self.assertIn("ausentismo_justificaciones_top", case_ids)
        self.assertNotIn("ausentismo_areas_dias_perdidos", case_ids)
