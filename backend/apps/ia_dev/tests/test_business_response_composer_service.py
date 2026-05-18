from __future__ import annotations

from django.test import SimpleTestCase

from apps.ia_dev.application.orchestration.business_response_composer_service import (
    BusinessResponseComposerService,
)


class BusinessResponseComposerServiceTests(SimpleTestCase):
    def test_composer_hides_technical_terms_from_business_response(self):
        service = BusinessResponseComposerService()

        payload = service.compose(
            response={
                "session_id": "sess-1",
                "reply": "El planner de SQL usó ai_dictionary y fallback legacy.",
                "data": {
                    "table": {"columns": [], "rows": [], "rowcount": 0},
                },
            },
            semantic_orchestrator={
                "domain": "inventario_logistica",
                "intent": "inventory_stock_by_warehouse",
                "recommended_route": "sql_assisted",
                "user_response_strategy": {
                    "warnings_to_include": [],
                    "next_best_action": "Entregar respuesta empresarial.",
                },
            },
        )

        reply = str(payload.get("reply") or "").lower()
        composer = dict((payload.get("data") or {}).get("business_response_composer") or {})
        merged_text = " ".join(str(value or "").lower() for value in composer.values())

        self.assertNotIn("sql", reply)
        self.assertNotIn("legacy", reply)
        self.assertNotIn("ai_dictionary", reply)
        self.assertNotIn("sql", merged_text)
        self.assertNotIn("legacy", merged_text)
        self.assertNotIn("ai_dictionary", merged_text)

    def test_composer_prioritizes_structured_business_response_over_reply(self):
        service = BusinessResponseComposerService()

        payload = service.compose(
            response={
                "reply": "planner sql legacy",
                "task": {
                    "current_run": {
                        "validation": {"satisfied": True, "reason": "ok"},
                        "tool_execution": {"selected_tool_id": "query_execution_planner.sql_assisted", "trace": [{}]},
                    }
                },
                "data": {
                    "business_response": {
                        "dato": "Se consolido el inventario operativo de TIRAN224.",
                        "hallazgo": "La salida conserva codigo, cedula y saldo desde la ejecucion.",
                        "riesgo": "Conviene revisar primero los codigos con saldo negativo.",
                        "recomendacion": "Si quieres, puedo filtrar por codigo.",
                        "siguiente_accion": "Si quieres, puedo filtrar por codigo.",
                        "metadata": {
                            "response_status": "success",
                            "response_profile_usado": "inventory.stock.mobile.detail",
                        },
                        "evidence_summary": {
                            "response_profile_usado": "inventory.stock.mobile.detail",
                            "evidence_sources_used": ["semantic_context", "result_set"],
                            "semantic_context_used": True,
                            "fallback_narrativo_usado": False,
                            "missing_evidence_reason": "",
                        },
                    },
                    "table": {"rowcount": 1, "rows": [{}], "columns": []},
                },
                "data_sources": {"runtime": {"final_domain": "inventario_logistica", "final_intent": "stock_balance"}},
            },
            semantic_orchestrator={
                "domain": "inventario_logistica",
                "intent": "stock_balance",
            },
        )

        reply = str(payload.get("reply") or "").lower()
        business_response = dict((dict(payload.get("data") or {}).get("business_response") or {}))
        metadata = dict(business_response.get("metadata") or {})
        self.assertIn("inventario operativo de tiran224", reply)
        self.assertNotIn("planner", reply)
        self.assertEqual(str(metadata.get("response_profile_usado") or ""), "inventory.stock.mobile.detail")
