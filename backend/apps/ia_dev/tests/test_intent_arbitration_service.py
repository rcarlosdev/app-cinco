from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase

from apps.ia_dev.application.contracts.query_intelligence_contracts import StructuredQueryIntent
from apps.ia_dev.services.intent_arbitration_service import IntentArbitrationService


class IntentArbitrationServiceTests(SimpleTestCase):
    def _service(self) -> IntentArbitrationService:
        with patch.dict("os.environ", {"IA_DEV_USE_OPENAI_INTENT_ARBITRATION": "0"}, clear=False):
            return IntentArbitrationService()

    @staticmethod
    def _dictionary_context() -> dict:
        return {
            "fields": [
                {"logical_name": "area", "table_name": "cinco_base_de_personal", "supports_group_by": True},
                {"logical_name": "cargo", "table_name": "cinco_base_de_personal", "supports_group_by": True},
                {"logical_name": "movil", "table_name": "cinco_base_de_personal", "supports_group_by": True},
                {"logical_name": "supervisor", "table_name": "cinco_base_de_personal", "supports_group_by": True},
                {"logical_name": "fecha_nacimiento", "table_name": "cinco_base_de_personal", "column_name": "fnacimiento", "is_date": True},
            ],
            "relations": [{"nombre_relacion": "ausentismo_empleado"}],
            "rules": [],
            "synonyms": [
                {"termino": "fecha_nacimiento", "sinonimo": "cumpleanos"},
                {"termino": "movil", "sinonimo": "cuadrilla"},
                {"termino": "supervisor", "sinonimo": "jefe"},
            ],
        }

    def test_analytics_questions_do_not_create_kpro(self):
        service = self._service()

        result = service.arbitrate(
            original_question="Que patrones existen por area, cargo y sede",
            candidate_domain="ausentismo",
            heuristic_intent={"intent": "empleados_query", "domain": "empleados", "confidence": 0.51},
            llm_intent=StructuredQueryIntent(
                raw_query="Que patrones existen por area, cargo y sede",
                domain_code="ausentismo",
                operation="aggregate",
                template_id="aggregate_by_group_and_period",
                confidence=0.86,
                source="openai",
                group_by=["area", "cargo", "sede"],
            ),
            candidate_capabilities=[{"capability_id": "attendance.summary.by_attribute.v1"}],
            ai_dictionary_context=self._dictionary_context(),
            action_risk={"level": "low"},
            knowledge_governance_signals={"explicit_change_request": False, "explicit_apply_request": False},
        )

        self.assertEqual(str(result.get("final_intent") or ""), "analytics_query")
        self.assertEqual(str(result.get("final_domain") or ""), "ausentismo")
        self.assertFalse(bool(result.get("should_create_kpro")))
        self.assertTrue(bool(result.get("should_execute_query")))
        self.assertTrue(bool(result.get("should_use_sql_assisted")))

    def test_real_knowledge_change_requests_create_kpro(self):
        service = self._service()

        result = service.arbitrate(
            original_question="Modifica el diccionario para que incapacidad sea sinonimo de ausencia medica",
            candidate_domain="ausentismo",
            heuristic_intent={"intent": "knowledge_change_request", "domain": "knowledge", "confidence": 0.8},
            llm_intent=StructuredQueryIntent(
                raw_query="Modifica el diccionario para que incapacidad sea sinonimo de ausencia medica",
                domain_code="ausentismo",
                operation="summary",
                template_id="",
                confidence=0.61,
                source="rules",
            ),
            candidate_capabilities=[{"capability_id": "knowledge.proposal.create.v1"}],
            ai_dictionary_context=self._dictionary_context(),
            action_risk={"level": "medium"},
            knowledge_governance_signals={"explicit_change_request": True, "explicit_apply_request": False},
        )

        self.assertEqual(str(result.get("final_intent") or ""), "knowledge_change_request")
        self.assertTrue(bool(result.get("should_create_kpro")))
        self.assertFalse(bool(result.get("should_execute_query")))
        self.assertFalse(bool(result.get("should_use_sql_assisted")))

    def test_ambiguous_questions_require_clarification(self):
        service = self._service()

        result = service.arbitrate(
            original_question="Y eso como seria?",
            candidate_domain="general",
            heuristic_intent={"intent": "general_question", "domain": "general", "confidence": 0.2},
            llm_intent=StructuredQueryIntent(
                raw_query="Y eso como seria?",
                domain_code="general",
                operation="summary",
                template_id="",
                confidence=0.21,
                source="rules",
            ),
            candidate_capabilities=[],
            ai_dictionary_context={},
            action_risk={"level": "low"},
            knowledge_governance_signals={"explicit_change_request": False, "explicit_apply_request": False},
        )

        self.assertEqual(str(result.get("final_intent") or ""), "fallback")
        self.assertTrue(bool(result.get("should_fallback")))
        self.assertIn("Aclara", str(result.get("required_clarification") or ""))

    def test_openai_arbitration_prevails_over_conflicting_heuristic(self):
        service = self._service()
        service.enable_openai = True

        with patch.object(
            service,
            "_arbitrate_openai",
            return_value={
                "final_intent": "analytics_query",
                "final_domain": "ausentismo",
                "should_execute_query": True,
                "should_create_kpro": False,
                "should_use_sql_assisted": True,
                "should_use_handler": False,
                "should_fallback": False,
                "confidence": 0.91,
                "reasoning_summary": "Consulta analitica sobre datos existentes.",
                "required_clarification": "",
            },
        ):
            result = service.arbitrate(
                original_question="Que cargos concentran mas incapacidades",
                candidate_domain="ausentismo",
                heuristic_intent={"intent": "knowledge_change_request", "domain": "knowledge", "confidence": 0.83},
                llm_intent=StructuredQueryIntent(
                    raw_query="Que cargos concentran mas incapacidades",
                    domain_code="ausentismo",
                    operation="aggregate",
                    template_id="aggregate_by_group_and_period",
                    confidence=0.73,
                    source="openai",
                    group_by=["cargo"],
                ),
                candidate_capabilities=[{"capability_id": "attendance.summary.by_cargo.v1"}],
                ai_dictionary_context=self._dictionary_context(),
                action_risk={"level": "low"},
                knowledge_governance_signals={"explicit_change_request": False, "explicit_apply_request": False},
            )

        self.assertEqual(str(result.get("final_intent") or ""), "analytics_query")
        self.assertFalse(bool(result.get("should_create_kpro")))
        self.assertTrue(bool(result.get("should_execute_query")))

    def test_deterministic_fallback_keeps_analytics_authority_over_conflicting_heuristic(self):
        service = self._service()

        analytics_messages = [
            ("Que patrones existen por area, cargo y sede", ["area", "cargo", "sede"]),
            ("Que empleados tienen mas riesgo de ausentismo", ["empleado"]),
            ("Que cargos concentran mas incapacidades", ["cargo"]),
            ("Que sedes presentan mas ausencias", ["sede"]),
        ]

        for message, group_by in analytics_messages:
            with self.subTest(message=message):
                result = service.arbitrate(
                    original_question=message,
                    candidate_domain="ausentismo",
                    heuristic_intent={
                        "intent": "knowledge_change_request",
                        "domain": "knowledge",
                        "confidence": 0.83,
                    },
                    llm_intent=StructuredQueryIntent(
                        raw_query=message,
                        domain_code="ausentismo",
                        operation="aggregate",
                        template_id="aggregate_by_group_and_period",
                        confidence=0.79,
                        source="rules",
                        group_by=group_by,
                    ),
                    candidate_capabilities=[{"capability_id": "attendance.summary.by_attribute.v1"}],
                    ai_dictionary_context=self._dictionary_context(),
                    action_risk={"level": "low"},
                    knowledge_governance_signals={
                        "explicit_change_request": False,
                        "explicit_apply_request": False,
                    },
                )

                self.assertEqual(str(result.get("final_intent") or ""), "analytics_query")
                self.assertFalse(bool(result.get("should_create_kpro")))
                self.assertTrue(bool(result.get("should_execute_query")))
                self.assertTrue(bool(result.get("should_use_sql_assisted")))

    def test_employee_population_queries_stay_in_analytics_count_lane(self):
        service = self._service()

        result = service.arbitrate(
            original_question="personal activo hoy",
            candidate_domain="empleados",
            heuristic_intent={"intent": "empleados_query", "domain": "empleados", "confidence": 0.64},
            llm_intent=StructuredQueryIntent(
                raw_query="personal activo hoy",
                domain_code="empleados",
                operation="count",
                template_id="count_entities_by_status",
                confidence=0.82,
                source="rules",
                filters={"estado": "ACTIVO"},
            ),
            candidate_capabilities=[{"capability_id": "empleados.count.active.v1"}],
            ai_dictionary_context=self._dictionary_context(),
            action_risk={"level": "low"},
            knowledge_governance_signals={"explicit_change_request": False, "explicit_apply_request": False},
        )

        self.assertEqual(str(result.get("final_intent") or ""), "analytics_query")
        self.assertEqual(str(result.get("final_domain") or ""), "empleados")
        self.assertTrue(bool(result.get("should_execute_query")))
        self.assertTrue(bool(result.get("should_use_sql_assisted")))
        self.assertFalse(bool(result.get("should_fallback")))

    def test_employee_grouped_movil_queries_do_not_require_clarification(self):
        service = self._service()

        result = service.arbitrate(
            original_question="Que moviles o cuadrillas tienen mas tecnicos asignados",
            candidate_domain="general",
            heuristic_intent={"intent": "general_question", "domain": "general", "confidence": 0.31},
            llm_intent=StructuredQueryIntent(
                raw_query="Que moviles o cuadrillas tienen mas tecnicos asignados",
                domain_code="empleados",
                operation="aggregate",
                template_id="aggregate_by_group_and_period",
                confidence=0.78,
                source="rules",
                group_by=["movil"],
                filters={"tipo_labor": "OPERATIVO"},
            ),
            candidate_capabilities=[{"capability_id": "empleados.count.active.v1"}],
            ai_dictionary_context=self._dictionary_context(),
            action_risk={"level": "low"},
            knowledge_governance_signals={"explicit_change_request": False, "explicit_apply_request": False},
        )

        self.assertEqual(str(result.get("final_intent") or ""), "analytics_query")
        self.assertEqual(str(result.get("final_domain") or ""), "empleados")
        self.assertTrue(bool(result.get("should_execute_query")))
        self.assertTrue(bool(result.get("should_use_sql_assisted")))
        self.assertFalse(bool(result.get("should_fallback")))
        self.assertIn("movil", list(result.get("valid_group_dimensions") or []))

    def test_birthday_queries_expose_structural_semantic_inference(self):
        service = self._service()

        result = service.arbitrate(
            original_question="Cumpleaños de mayo",
            candidate_domain="empleados",
            heuristic_intent={"intent": "general_question", "domain": "general", "confidence": 0.31},
            llm_intent=StructuredQueryIntent(
                raw_query="Cumpleaños de mayo",
                domain_code="empleados",
                operation="detail",
                template_id="detail_by_entity_and_period",
                filters={"fnacimiento_month": "5"},
                confidence=0.88,
                source="rules",
            ),
            candidate_capabilities=[{"capability_id": "empleados.detail.v1"}],
            ai_dictionary_context=self._dictionary_context(),
            action_risk={"level": "low"},
            knowledge_governance_signals={"explicit_change_request": False, "explicit_apply_request": False},
        )

        self.assertEqual(str(result.get("final_intent") or ""), "analytics_query")
        self.assertEqual(str(result.get("candidate_domain") or ""), "empleados")
        self.assertEqual(str(result.get("candidate_table") or ""), "cinco_base_de_personal")
        self.assertEqual(str(result.get("candidate_field") or ""), "fecha_nacimiento")
        self.assertEqual(str(result.get("inferred_business_concept") or ""), "birthday")
        self.assertEqual(str((result.get("temporal_filter") or {}).get("value") or ""), "5")

    def test_explicit_knowledge_change_requests_still_require_kpro(self):
        service = self._service()

        knowledge_messages = [
            "Agrega una regla para interpretar sede como zona_nodo",
            "Modifica el diccionario para que incapacidad sea sinonimo de ausencia medica",
        ]

        for message in knowledge_messages:
            with self.subTest(message=message):
                result = service.arbitrate(
                    original_question=message,
                    candidate_domain="ausentismo",
                    heuristic_intent={"intent": "empleados_query", "domain": "empleados", "confidence": 0.41},
                    llm_intent=StructuredQueryIntent(
                        raw_query=message,
                        domain_code="ausentismo",
                        operation="summary",
                        template_id="",
                        confidence=0.58,
                        source="rules",
                    ),
                    candidate_capabilities=[{"capability_id": "knowledge.proposal.create.v1"}],
                    ai_dictionary_context=self._dictionary_context(),
                    action_risk={"level": "medium"},
                    knowledge_governance_signals={
                        "explicit_change_request": True,
                        "explicit_apply_request": False,
                    },
                )

                self.assertEqual(str(result.get("final_intent") or ""), "knowledge_change_request")
                self.assertTrue(bool(result.get("should_create_kpro")))
                self.assertFalse(bool(result.get("should_execute_query")))
