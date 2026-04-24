from __future__ import annotations

from datetime import date

from django.test import SimpleTestCase

from apps.ia_dev.TOOLS.business.ausentismo_business_tool import (
    AusentismoBusinessTool,
    PeriodoAusentismo,
)


class _FakeAusentismoService:
    def __init__(self):
        self.last_extra_personal_columns: list[str] = []

    def get_detail_with_personal(
        self,
        start_date: date,
        end_date: date,
        *,
        limit: int = 500,
        personal_status: str = "all",
        cedula: str | None = None,
        extra_personal_columns: list[str] | None = None,
        justificacion_filter: str | None = None,
        focus: str = "all",
    ) -> dict:
        self.last_extra_personal_columns = list(extra_personal_columns or [])
        return {
            "periodo_inicio": start_date.isoformat(),
            "periodo_fin": end_date.isoformat(),
            "rows": [
                {"cedula": "1", "area": "I&M", "carpeta": "FTTH"},
                {"cedula": "2", "area": "I&M", "carpeta": "FTTH"},
                {"cedula": "3", "area": "IMPLEMENTACION FO", "carpeta": "MANTENIMIENTO"},
            ],
        }


class _FakeOrgContext:
    @staticmethod
    def cost_center_for(*, area="", carpeta=""):
        if carpeta == "FTTH":
            return "20-1"
        if area == "IMPLEMENTACION FO":
            return "20-9"
        return "N/D"


class AusentismoBusinessToolOrgContextTests(SimpleTestCase):
    def test_centro_costo_grouping_requests_area_and_carpeta_for_enrichment(self):
        service = _FakeAusentismoService()
        tool = AusentismoBusinessTool(service=service)
        tool.org_context = _FakeOrgContext()

        result = tool.get_attendance_aggregation(
            period=PeriodoAusentismo(start=date(2026, 3, 26), end=date(2026, 4, 24)),
            group_by="centro_costo",
            focus="all",
        )

        self.assertEqual(service.last_extra_personal_columns, ["area", "carpeta"])
        rows = list(result.get("rows") or [])
        self.assertEqual(rows[0]["centro_costo"], "20-1")
        self.assertEqual(rows[0]["total_ausentismos"], 2)
        self.assertEqual(rows[1]["centro_costo"], "20-9")
        self.assertEqual(rows[1]["total_ausentismos"], 1)
