from __future__ import annotations

from django.test import SimpleTestCase

from apps.ia_dev.application.context.run_context import RunContext
from apps.ia_dev.application.reasoning.reasoning_memory_service import (
    ReasoningMemoryService,
)


class _FakeMemoryWriter:
    def __init__(self):
        self.calls: list[dict] = []

    def create_proposal(self, *, user_key: str, payload: dict, source_run_id: str | None = None) -> dict:
        self.calls.append(
            {
                "user_key": user_key,
                "payload": dict(payload or {}),
                "source_run_id": source_run_id,
            }
        )
        idx = len(self.calls)
        return {
            "ok": True,
            "proposal": {
                "proposal_id": f"RPRO-{idx}",
                "scope": payload.get("scope"),
                "candidate_key": payload.get("candidate_key"),
                "candidate_value": payload.get("candidate_value"),
                "status": "pending",
            },
        }

    def approve_proposal(self, *, proposal_id: str, actor_user_key: str, actor_role: str, comment: str = "") -> dict:
        return {
            "ok": True,
            "proposal": {
                "proposal_id": proposal_id,
                "status": "applied",
            },
        }


class ReasoningMemoryServiceTests(SimpleTestCase):
    def test_record_patterns_persists_user_and_collective_learning(self):
        writer = _FakeMemoryWriter()
        service = ReasoningMemoryService(memory_writer=writer)
        run_context = RunContext.create(message="informacion tiran462", session_id="sess-reason-1")

        result = service.record_patterns(
            user_key="user:test",
            diagnostics={
                "items": [
                    {
                        "signature": "empty_result_with_identifier",
                        "family": "empty_result",
                        "severity": "warning",
                        "stage": "post_execution",
                        "domain_code": "empleados",
                        "capability_id": "empleados.detail.v1",
                        "summary": "La consulta termino vacia con identificador fuerte.",
                        "recommended_action": "Revisar normalizacion.",
                        "confidence": 0.9,
                    }
                ]
            },
            run_context=run_context,
            response={"data": {"table": {"columns": [], "rows": [], "rowcount": 0}}},
        )

        self.assertTrue(bool(result.get("saved")))
        self.assertEqual(len(writer.calls), 2)
        candidate_keys = [str(item["payload"].get("candidate_key") or "") for item in writer.calls]
        self.assertIn("reasoning.pattern.user.empty_result_with_identifier", candidate_keys)
        self.assertIn("reasoning.pattern.domain.empleados.empty_result_with_identifier", candidate_keys)
