from __future__ import annotations

from django.test import SimpleTestCase

from apps.ia_dev.application.orchestration.chat_application_service import (
    ChatApplicationService,
)


class ChatBootstrapContextTests(SimpleTestCase):
    def test_followup_chart_message_keeps_ausentismo_domain_from_session_context(self):
        classification = ChatApplicationService._bootstrap_classification(
            message="grafica de este reporte",
            session_context={
                "last_domain": "ausentismo",
                "last_needs_database": True,
                "last_output_mode": "summary",
            },
        )
        self.assertEqual(classification.get("domain"), "ausentismo")
        self.assertEqual(classification.get("intent"), "ausentismo_query")
        self.assertEqual(classification.get("selected_agent"), "ausentismo_agent")
        self.assertTrue(classification.get("needs_database"))

    def test_bootstrap_classifies_rrhh_employee_queries_into_empleados_domain(self):
        classification = ChatApplicationService._bootstrap_classification(
            message="Cantidad empleados activos",
            session_context={},
        )
        self.assertEqual(classification.get("domain"), "empleados")
        self.assertEqual(classification.get("intent"), "empleados_query")
        self.assertEqual(classification.get("selected_agent"), "empleados_agent")

    def test_bootstrap_classifies_colaboradores_habilitados_query_into_empleados_domain(self):
        classification = ChatApplicationService._bootstrap_classification(
            message="¿Cuántos colaboradores habilitados tenemos hoy?",
            session_context={},
        )
        self.assertEqual(classification.get("domain"), "empleados")
        self.assertEqual(classification.get("intent"), "empleados_query")
        self.assertEqual(classification.get("output_mode"), "summary")

    def test_bootstrap_classifies_employee_dimension_only_query_into_empleados_domain(self):
        classification = ChatApplicationService._bootstrap_classification(
            message="cantidad de tipo de labor por area",
            session_context={},
        )
        self.assertEqual(classification.get("domain"), "empleados")
        self.assertEqual(classification.get("intent"), "empleados_query")

    def test_bootstrap_normalizes_common_employee_typos(self):
        classification = ChatApplicationService._bootstrap_classification(
            message="cantidad empelados por áres",
            session_context={},
        )
        self.assertEqual(classification.get("domain"), "empleados")
        self.assertEqual(classification.get("intent"), "empleados_query")

    def test_bootstrap_sets_summary_for_grouped_count_attendance(self):
        classification = ChatApplicationService._bootstrap_classification(
            message="Cantidad de ausentismos por supervisor los ultimos 15 dias",
            session_context={},
        )
        self.assertEqual(classification.get("domain"), "ausentismo")
        self.assertEqual(classification.get("selected_agent"), "ausentismo_agent")
        self.assertEqual(classification.get("output_mode"), "summary")

    def test_canonical_classification_keeps_summary_mode_for_attendance_aggregate(self):
        classification = ChatApplicationService._canonical_classification_for_routing(
            canonical_domain="ausentismo",
            canonical_intent="aggregate",
            fallback_classification={
                "selected_agent": "ausentismo_agent",
                "needs_personal_join": True,
                "used_tools": [],
                "dictionary_context": {},
            },
        )
        self.assertEqual(classification.get("domain"), "ausentismo")
        self.assertEqual(classification.get("intent"), "ausentismo_query")
        self.assertEqual(classification.get("selected_agent"), "ausentismo_agent")
        self.assertEqual(classification.get("output_mode"), "summary")
