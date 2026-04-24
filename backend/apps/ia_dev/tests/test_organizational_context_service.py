from __future__ import annotations

from django.test import SimpleTestCase

from apps.ia_dev.services.organizational_context_service import (
    OrganizationalContextService,
    OrganizationalParameter,
)


class _FakeOrganizationalContextService(OrganizationalContextService):
    def active_areas(self) -> list[OrganizationalParameter]:
        return [
            OrganizationalParameter(
                tipo="AREA",
                condicion="I&M",
                valor="I&M",
                tipo_area="",
                datos={"centros_costo": [{"centro_costo": 20, "subcentro_costo": [1, 2]}]},
            ),
            OrganizationalParameter(
                tipo="AREA",
                condicion="IMPLEMENTACION FO",
                valor="IMPLEMENTACION FO",
                tipo_area="",
                datos={"centros_costo": [{"centro_costo": 20, "subcentro_costo": [9]}]},
            ),
        ]

    def active_carpetas(self) -> list[OrganizationalParameter]:
        return [
            OrganizationalParameter(
                tipo="CARPETA",
                condicion="I&M",
                valor="FTTH",
                tipo_area="",
                datos={"centro_costo": 20, "subcentro_costo": 1},
            ),
        ]


class OrganizationalContextServiceTests(SimpleTestCase):
    def test_resolves_root_area_when_message_does_not_request_carpeta(self):
        service = _FakeOrganizationalContextService()

        resolved = service.resolve_reference(message="Rotación de empelados de I&M")

        self.assertTrue(resolved.get("resolved"))
        self.assertEqual(dict(resolved.get("filters") or {}), {"area": "I&M"})

    def test_resolves_partial_area_typo_for_attendance_context(self):
        service = _FakeOrganizationalContextService()

        resolved = service.resolve_reference(message="Recurrentes del ultimo mes de Implementacio")

        self.assertTrue(resolved.get("resolved"))
        self.assertEqual(dict(resolved.get("filters") or {}), {"area": "IMPLEMENTACION FO"})

    def test_formats_cost_center_from_area_and_carpeta_metadata(self):
        service = _FakeOrganizationalContextService()

        self.assertEqual(service.cost_center_for(area="I&M"), "20-1, 20-2")
        self.assertEqual(service.cost_center_for(carpeta="FTTH"), "20-1")
