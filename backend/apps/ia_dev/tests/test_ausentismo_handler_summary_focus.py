from __future__ import annotations

from django.test import SimpleTestCase
from unittest.mock import patch

from apps.ia_dev.application.context.run_context import RunContext
from apps.ia_dev.application.contracts.query_intelligence_contracts import QueryExecutionPlan
from apps.ia_dev.domains.ausentismo.handler import AusentismoHandler


class _FakeAusentismoBusinessTool:
    def __init__(self):
        self.calls: list[dict[str, str | None]] = []
        self.ausentismo_table = "cincosas_cincosas.gestionh_ausentismo"
        self.ausentismo_table_source = "dd_tablas"
        self.personal_table = "bd_c3nc4s1s.cinco_base_de_personal"
        self.personal_table_source = "dd_tablas"

    def get_attendance_summary(
        self,
        *,
        period,
        cedula: str | None = None,
        focus: str = "all",
        justificacion_filter: str | None = None,
    ) -> dict:
        self.calls.append(
            {
                "focus": focus,
                "justificacion_filter": justificacion_filter,
                "period_start": period.start.isoformat(),
                "period_end": period.end.isoformat(),
            }
        )
        if focus == "unjustified":
            return {
                "periodo_inicio": period.start.isoformat(),
                "periodo_fin": period.end.isoformat(),
                "total_ausentismos": 629,
                "justificados": 0,
                "injustificados": 629,
            }
        return {
            "periodo_inicio": period.start.isoformat(),
            "periodo_fin": period.end.isoformat(),
            "total_ausentismos": 2095,
            "justificados": 1466,
            "injustificados": 629,
        }


class AusentismoHandlerSummaryFocusTests(SimpleTestCase):
    def _run_handle(self, message: str) -> tuple[object, _FakeAusentismoBusinessTool]:
        tool = _FakeAusentismoBusinessTool()
        handler = AusentismoHandler(tool=tool)
        execution_plan = QueryExecutionPlan(
            strategy="capability",
            reason="test",
            domain_code="ausentismo",
            capability_id="attendance.unjustified.summary.v1",
            constraints={},
        )
        with patch("apps.ia_dev.domains.ausentismo.handler.SessionMemoryStore.get_or_create", return_value=("sid-1", {})), patch(
            "apps.ia_dev.domains.ausentismo.handler.SessionMemoryStore.get_context",
            return_value={},
        ), patch(
            "apps.ia_dev.domains.ausentismo.handler.SessionMemoryStore.update_context"
        ), patch(
            "apps.ia_dev.domains.ausentismo.handler.SessionMemoryStore.append_turn"
        ), patch(
            "apps.ia_dev.domains.ausentismo.handler.SessionMemoryStore.status",
            return_value={"used_messages": 0},
        ):
            result = handler.handle(
                capability_id="attendance.unjustified.summary.v1",
                message=message,
                session_id="sid-1",
                reset_memory=False,
                run_context=RunContext.create(message=message, session_id="sid-1"),
                planned_capability={"capability_id": "attendance.unjustified.summary.v1"},
                execution_plan=execution_plan,
            )
        return result, tool

    def test_generic_summary_uses_all_focus(self):
        result, tool = self._run_handle("Ausentismos ultimo mes")

        self.assertTrue(result.ok)
        self.assertEqual(tool.calls[0]["focus"], "all")
        response = dict(result.response or {})
        self.assertIn("justificados=1466", str(response.get("reply") or ""))
        self.assertIn("injustificados=629", str(response.get("reply") or ""))

    def test_explicit_unjustified_summary_keeps_unjustified_focus(self):
        result, tool = self._run_handle("Ausentismos injustificados ultimo mes")

        self.assertTrue(result.ok)
        self.assertEqual(tool.calls[0]["focus"], "unjustified")
        response = dict(result.response or {})
        self.assertIn("ausentismos injustificados", str(response.get("reply") or "").lower())
