from __future__ import annotations

from django.test import SimpleTestCase

from apps.ia_dev.application.context.run_context import RunContext
from apps.ia_dev.application.reasoning.reasoning_ledger_service import (
    ReasoningLedgerService,
)


class ReasoningLedgerServiceTests(SimpleTestCase):
    def test_ledger_tracks_updates_hypotheses_and_public_payload(self):
        run_context = RunContext.create(message="informacion TIRAN462", session_id="sess-ledger-1")
        service = ReasoningLedgerService()

        service.start_run(
            run_context=run_context,
            message="informacion TIRAN462",
            user_key="user:test",
            session_context={"last_domain": "empleados"},
        )
        service.record_progress(
            run_context=run_context,
            stage="query_intelligence",
            status="completed",
            summary="Se resolvio la consulta a empleados.detail.v1.",
            next_step="ejecutar capacidad",
            confidence=0.82,
        )
        service.record_hypothesis(
            run_context=run_context,
            key="identifier_normalization_gap",
            text="El identificador podria requerir compactacion.",
            status="open",
            confidence=0.75,
        )
        service.record_diagnostics(
            run_context=run_context,
            diagnostics={
                "items": [
                    {
                        "signature": "empty_result_with_identifier",
                        "summary": "La consulta termino vacia con identificador fuerte.",
                        "severity": "warning",
                        "stage": "post_execution",
                        "confidence": 0.88,
                        "hypotheses": [
                            {
                                "key": "overconstrained_identifier_query",
                                "text": "Hay un filtro redundante que vacia el resultado.",
                                "status": "supported",
                                "confidence": 0.88,
                            }
                        ],
                        "evidence": [
                            {
                                "source": "response",
                                "finding": "rowcount=0",
                                "confidence": 0.9,
                                "metadata": {"rowcount": 0},
                            }
                        ],
                    }
                ]
            },
        )
        service.finalize(
            run_context=run_context,
            status="completed",
            outcome={"diagnostics_activated": True},
        )

        working_updates = service.build_working_updates(run_context=run_context)
        public_payload = service.build_public_payload(run_context=run_context)

        self.assertGreaterEqual(len(working_updates), 3)
        self.assertEqual(public_payload.get("status"), "completed")
        self.assertTrue(public_payload.get("enabled"))
        self.assertTrue(any(item.get("key") == "overconstrained_identifier_query" for item in public_payload.get("hypotheses") or []))
        self.assertEqual((public_payload.get("diagnostics") or [])[0].get("signature"), "empty_result_with_identifier")

