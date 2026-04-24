from __future__ import annotations

from django.test import SimpleTestCase

from apps.ia_dev.application.semantic.semantic_normalization_service import (
    SemanticNormalizationService,
)


class SemanticNormalizationServiceTests(SimpleTestCase):
    def setUp(self):
        self.semantic_context = {
            "domain_code": "empleados",
            "dictionary": {
                "synonyms": [
                    {"termino": "empleados", "sinonimo": "personal"},
                    {"termino": "activo", "sinonimo": "habilitado"},
                    {"termino": "activo", "sinonimo": "vigente"},
                    {"termino": "supervisor", "sinonimo": "jefe directo"},
                ]
            },
        }

    def test_equivalent_employee_queries_map_to_empleados_and_activo(self):
        service = SemanticNormalizationService()
        samples = [
            "cantidad empleados activos",
            "cantidad personal activo",
            "numero de colaboradores activos",
        ]
        for query in samples:
            with self.subTest(query=query):
                output = service.normalize(
                    raw_query=query,
                    semantic_context=self.semantic_context,
                    runtime_flags={"llm_enabled": False, "llm_mode": "never"},
                    capability_hints=[],
                    base_classification={"domain": "general", "intent": "general_question"},
                )
                payload = output.as_dict()
                self.assertEqual(str((payload.get("candidate_domains") or [{}])[0].get("domain") or ""), "empleados")
                estado = [
                    item for item in list(payload.get("candidate_filters") or [])
                    if str(item.get("filter") or "") == "estado"
                ]
                self.assertTrue(estado)
                self.assertEqual(str(estado[0].get("value") or ""), "ACTIVO")

    def test_supervisor_and_jefe_directo_are_equivalent(self):
        service = SemanticNormalizationService()
        output = service.normalize(
            raw_query="ausentismos por jefe directo",
            semantic_context=self.semantic_context,
            runtime_flags={"llm_enabled": False, "llm_mode": "never"},
            capability_hints=[],
            base_classification={"domain": "attendance", "intent": "attendance_query"},
        )
        payload = output.as_dict()
        canonical_query = str(payload.get("canonical_query") or "")
        self.assertIn("supervisor", canonical_query)
        self.assertNotIn("jefe directo", canonical_query)

    def test_llm_not_invoked_on_exact_deterministic_match(self):
        calls = {"count": 0}

        def _fake_llm(**kwargs):
            calls["count"] += 1
            return {"ok": True}

        service = SemanticNormalizationService(llm_resolver=_fake_llm)
        output = service.normalize(
            raw_query="cantidad empleados activos",
            semantic_context=self.semantic_context,
            runtime_flags={"llm_enabled": True, "llm_mode": "hybrid"},
            capability_hints=[
                {
                    "capability_id": "empleados.count.active.v1",
                    "reason": "exact_match_empleados_count_active",
                }
            ],
            base_classification={"domain": "empleados", "intent": "empleados_query"},
        )
        payload = output.as_dict()
        self.assertFalse(bool(payload.get("llm_invoked")))
        self.assertEqual(calls["count"], 0)

    def test_llm_is_considered_on_semantic_conflict(self):
        calls = {"count": 0}

        def _fake_llm(**kwargs):
            calls["count"] += 1
            return {
                "ok": True,
                "confidence": 0.91,
                "candidate_domains": [{"domain": "empleados", "confidence": 0.95, "source": "llm"}],
                "candidate_intents": [{"intent": "count", "confidence": 0.92, "source": "llm"}],
                "review_notes": ["llm_detected_rrhh_count"],
            }

        service = SemanticNormalizationService(llm_resolver=_fake_llm)
        output = service.normalize(
            raw_query="numero de colaboradores activos",
            semantic_context=self.semantic_context,
            runtime_flags={"llm_enabled": True, "llm_mode": "hybrid"},
            capability_hints=[],
            base_classification={"domain": "general", "intent": "general_question"},
        )
        payload = output.as_dict()
        self.assertTrue(bool(payload.get("llm_invoked")))
        self.assertEqual(calls["count"], 1)
        self.assertEqual(str(payload.get("normalization_status") or ""), "hybrid_llm_augmented")

    def test_rrhh_minimal_samples_have_consistent_deterministic_normalization(self):
        service = SemanticNormalizationService()
        samples = [
            "personal activo",
            "cantididad personal activo",
            "cantididad empleados activos",
            "cuántos vigentes hay",
            "número de colaboradores habilitados",
            "personas activas actualmente",
        ]
        for query in samples:
            with self.subTest(query=query):
                output = service.normalize(
                    raw_query=query,
                    semantic_context=self.semantic_context,
                    runtime_flags={"llm_enabled": False, "llm_mode": "never"},
                    capability_hints=[],
                    base_classification={"domain": "general", "intent": "general_question"},
                )
                payload = output.as_dict()
                self.assertEqual(str(payload.get("domain_code") or ""), "empleados")
                estado = str((payload.get("normalized_filters") or {}).get("estado") or "")
                self.assertEqual(estado, "ACTIVO")

    def test_employee_egresos_this_month_normalizes_to_inactive_count(self):
        service = SemanticNormalizationService()
        output = service.normalize(
            raw_query="Egresos de este mes?",
            semantic_context=self.semantic_context,
            runtime_flags={"llm_enabled": False, "llm_mode": "never"},
            capability_hints=[],
            base_classification={"domain": "general", "intent": "general_question"},
        )
        payload = output.as_dict()
        self.assertEqual(str(payload.get("domain_code") or ""), "empleados")
        self.assertEqual(str(payload.get("intent_code") or ""), "count")
        self.assertEqual(str((payload.get("normalized_filters") or {}).get("estado") or ""), "INACTIVO")

    def test_employee_turnover_normalizes_to_inactive_count(self):
        service = SemanticNormalizationService()
        output = service.normalize(
            raw_query="rotacion de personal ultimo mes?",
            semantic_context=self.semantic_context,
            runtime_flags={"llm_enabled": False, "llm_mode": "never"},
            capability_hints=[],
            base_classification={"domain": "general", "intent": "general_question"},
        )
        payload = output.as_dict()
        self.assertEqual(str(payload.get("domain_code") or ""), "empleados")
        self.assertEqual(str(payload.get("intent_code") or ""), "count")
        self.assertEqual(str((payload.get("normalized_filters") or {}).get("estado") or ""), "INACTIVO")

    def test_ab_comparison_reports_required_delta_indicators(self):
        def _fake_llm(**kwargs):
            baseline = dict(kwargs.get("baseline_snapshot") or {})
            return {
                "ok": True,
                "canonical_query": str(baseline.get("canonical_query") or "").replace("activo", "activos"),
                "domain_code": "empleados",
                "intent_code": "count",
                "filters": {"estado": "ACTIVO"},
                "aliases_detected": [{"alias": "personal", "canonical": "empleados"}],
                "capability_hint": "empleados.count.active.v1",
                "confidence": 0.93,
                "ambiguities": [],
            }

        service = SemanticNormalizationService(llm_resolver=_fake_llm)
        output = service.normalize(
            raw_query="cantididad personal activo",
            semantic_context=self.semantic_context,
            runtime_flags={
                "llm_enabled": True,
                "llm_mode": "hybrid",
                "llm_rollout_mode": "active",
            },
            capability_hints=[],
            base_classification={"domain": "general", "intent": "general_question"},
        )
        payload = output.as_dict()
        comparison = dict(payload.get("llm_comparison") or {})
        self.assertTrue(bool(payload.get("llm_invoked")))
        self.assertEqual(str(payload.get("domain_code") or ""), "empleados")
        self.assertEqual(str(payload.get("intent_code") or ""), "count")
        self.assertEqual(str((payload.get("normalized_filters") or {}).get("estado") or ""), "ACTIVO")
        self.assertIn("off", comparison)
        self.assertIn("on", comparison)
        self.assertIn("llm_changed_canonical_query", comparison)
        self.assertIn("llm_changed_domain", comparison)
        self.assertIn("llm_changed_intent", comparison)
        self.assertIn("llm_changed_filters", comparison)
        self.assertIn("llm_improved_confidence", comparison)

    def test_shadow_rollout_invokes_llm_without_applying_runtime_changes(self):
        def _fake_llm(**kwargs):
            return {
                "ok": True,
                "canonical_query": "consulta transporte",
                "domain_code": "transport",
                "intent_code": "detail",
                "filters": {"estado": "INACTIVO"},
                "aliases_detected": [],
                "capability_hint": "transport.list.v1",
                "confidence": 0.98,
                "ambiguities": [],
            }

        service = SemanticNormalizationService(llm_resolver=_fake_llm)
        output = service.normalize(
            raw_query="cantididad personal activo",
            semantic_context=self.semantic_context,
            runtime_flags={
                "llm_enabled": True,
                "llm_mode": "hybrid",
                "llm_rollout_mode": "shadow",
            },
            capability_hints=[],
            base_classification={"domain": "general", "intent": "general_question"},
        )
        payload = output.as_dict()
        self.assertTrue(bool(payload.get("llm_invoked")))
        self.assertEqual(str(payload.get("normalization_status") or ""), "hybrid_llm_shadow")
        self.assertEqual(str(payload.get("domain_code") or ""), "empleados")
        self.assertEqual(str((payload.get("normalized_filters") or {}).get("estado") or ""), "ACTIVO")

    def test_llm_mini_context_exposes_candidate_tables_and_dimensions_for_attendance(self):
        captured = {}

        def _fake_llm(**kwargs):
            captured.update(kwargs)
            return {
                "ok": True,
                "domain_code": "ausentismo",
                "intent_code": "aggregate",
                "filters": {},
                "aliases_detected": [],
                "capability_hint": "attendance.summary.by_area.v1",
                "confidence": 0.91,
                "ambiguities": [],
            }

        service = SemanticNormalizationService(llm_resolver=_fake_llm)
        output = service.normalize(
            raw_query="ausentismos por area",
            semantic_context={
                "domain_code": "ausentismo",
                "tables": [
                    {"table_name": "gestionh_ausentismo", "table_fqn": "cincosas_cincosas.gestionh_ausentismo", "rol": "hechos"},
                    {"table_name": "cinco_base_de_personal", "table_fqn": "cincosas_cincosas.cinco_base_de_personal", "rol": "dimension"},
                ],
                "relation_profiles": [
                    {
                        "relation_name": "ausentismo_empleado",
                        "join_sql": "gestionh_ausentismo.cedula = cinco_base_de_personal.cedula",
                        "cardinality": "many_to_one",
                    }
                ],
                "column_profiles": [
                    {"logical_name": "fecha_ausentismo", "column_name": "fecha_edit", "table_name": "gestionh_ausentismo", "is_date": True},
                    {"logical_name": "cedula", "column_name": "cedula", "table_name": "gestionh_ausentismo", "is_identifier": True},
                ],
                "dictionary": {"synonyms": []},
            },
            runtime_flags={"llm_enabled": True, "llm_mode": "always", "llm_rollout_mode": "active"},
            capability_hints=[],
            base_classification={"domain": "attendance", "intent": "attendance_query"},
        )
        payload = output.as_dict()
        mini_context = dict(captured.get("mini_context") or {})
        self.assertTrue(bool(payload.get("llm_invoked")))
        self.assertEqual(str(payload.get("domain_code") or ""), "ausentismo")
        self.assertIn("area", list(mini_context.get("candidate_group_dimensions") or []))
        self.assertTrue(
            any(str(item.get("table_name") or "") == "cinco_base_de_personal" for item in list(mini_context.get("candidate_tables") or []))
        )
        self.assertTrue(
            any(str(item.get("logical_name") or "") == "area" for item in list(mini_context.get("candidate_columns") or []))
        )

    def test_candidate_entities_detects_movil_lookup_token(self):
        service = SemanticNormalizationService()
        output = service.normalize(
            raw_query="info de TIRAN462",
            semantic_context=self.semantic_context,
            runtime_flags={"llm_enabled": False, "llm_mode": "never"},
            capability_hints=[],
            base_classification={"domain": "empleados", "intent": "empleados_query"},
        )
        payload = output.as_dict()
        entities = list(payload.get("candidate_entities") or [])
        self.assertTrue(any(str(item.get("entity_type") or "") == "movil" for item in entities))

    def test_candidate_entities_detects_movil_lookup_token_with_space(self):
        service = SemanticNormalizationService()
        output = service.normalize(
            raw_query="info de TIRAN 462",
            semantic_context=self.semantic_context,
            runtime_flags={"llm_enabled": False, "llm_mode": "never"},
            capability_hints=[],
            base_classification={"domain": "general", "intent": "general_question"},
        )
        payload = output.as_dict()
        entities = list(payload.get("candidate_entities") or [])
        self.assertTrue(any(str(item.get("entity_value") or "") == "TIRAN462" for item in entities))

    def test_semantic_normalization_detects_vacaciones_as_attendance_reason_filter(self):
        service = SemanticNormalizationService()
        output = service.normalize(
            raw_query="personal en vacaciones",
            semantic_context={"domain_code": "ausentismo", "dictionary": {"synonyms": []}},
            runtime_flags={"llm_enabled": False, "llm_mode": "never"},
            capability_hints=[],
            base_classification={"domain": "empleados", "intent": "empleados_query"},
        )
        payload = output.as_dict()
        self.assertEqual(str(payload.get("domain_code") or ""), "ausentismo")
        self.assertEqual(str(payload.get("intent_code") or ""), "detail")
        self.assertEqual(str((payload.get("normalized_filters") or {}).get("justificacion") or ""), "VACACIONES")
