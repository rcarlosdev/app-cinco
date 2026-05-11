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
