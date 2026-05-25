from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase

from apps.ia_dev.application.agents.agents_runtime_service import AgentsRuntimeService
from apps.ia_dev.application.context.run_context import RunContext


class _ObservabilityStub:
    def __init__(self):
        self.events: list[dict] = []

    def record_event(self, *, event_type: str, source: str, meta: dict):
        self.events.append({"event_type": event_type, "source": source, "meta": dict(meta or {})})


class AgentsRuntimeServiceTests(SimpleTestCase):
    def test_orchestrate_selects_inventory_specialist_and_persists_trace(self):
        service = AgentsRuntimeService()
        observability = _ObservabilityStub()
        run_context = RunContext.create(
            message="inventario de la cuadrilla TIRAN224",
            session_id="sess-agents",
            reset_memory=False,
        )

        with patch.dict("os.environ", {"OPENAI_API_KEY": "", "IA_DEV_AGENTS_RUNTIME_ENABLED": "1"}, clear=False):
            payload = service.orchestrate(
                user_message=run_context.message,
                candidate_domain="inventario_logistica",
                candidate_intent="stock_balance",
                candidate_capability="inventory_stock_balance_by_mobile",
                semantic_orchestrator={"reasoning_summary": "Inventario operativo por movil."},
                route_debug_hints={},
                run_context=run_context,
                observability=observability,
            )

        self.assertTrue(bool(payload.get("enabled")))
        self.assertEqual(str(payload.get("selected_specialist") or ""), "inventory_agent")
        self.assertEqual(len(list(payload.get("agents") or [])), 2)
        self.assertEqual(len(list(payload.get("handoffs") or [])), 1)
        self.assertEqual(len(list(payload.get("handoff_trace") or [])), 1)
        self.assertEqual(len(list(payload.get("agent_trace") or [])), 2)
        self.assertEqual(str((((payload.get("agents") or [])[1] or {}).get("agent_name") or "")), "inventory_agent")
        self.assertEqual(str((((payload.get("handoffs") or [])[0] or {}).get("handoff_target") or "")), "inventory_agent")
        self.assertTrue(bool((((payload.get("handoffs") or [])[0] or {}).get("handoff_id") or "")))
        self.assertEqual(str((((run_context.metadata.get("agents_runtime") or {}).get("routing") or {}).get("selected_specialist") or "")), "inventory_agent")
        self.assertTrue(any(event.get("event_type") == "agents_runtime_handoff" for event in observability.events))
        self.assertTrue(any(event.get("event_type") == "agents_runtime_handoff_trace_recorded" for event in observability.events))

    def test_orchestrate_falls_back_to_semantic_resolution_specialist(self):
        service = AgentsRuntimeService()

        with patch.dict("os.environ", {"OPENAI_API_KEY": "", "IA_DEV_AGENTS_RUNTIME_ENABLED": "1"}, clear=False):
            payload = service.orchestrate(
                user_message="necesito aclarar la ruta",
                candidate_domain="general",
                candidate_intent="fallback",
                candidate_capability="",
                semantic_orchestrator={"reasoning_summary": "Ambiguedad real detectada."},
                route_debug_hints={},
                run_context=None,
                observability=None,
            )

        self.assertEqual(str(payload.get("selected_specialist") or ""), "semantic_resolution_agent")
