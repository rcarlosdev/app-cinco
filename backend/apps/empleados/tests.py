from datetime import date
from decimal import Decimal
from unittest import TestCase
from unittest.mock import MagicMock, patch

from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from apps.empleados.services.empleado_service import EmpleadoService
from apps.empleados.views.empleado_view import EmpleadoViewSet


class EmpleadoServiceTests(TestCase):
    def test_eliminar_hard_delete_requires_superuser(self):
        instance = MagicMock()
        actor = MagicMock(is_authenticated=True, is_superuser=False)

        result = EmpleadoService.eliminar(
            instance,
            actor_user=actor,
            hard_delete=True,
        )

        self.assertFalse(result)
        instance.delete.assert_not_called()

    def test_eliminar_hard_delete_superuser(self):
        instance = MagicMock()
        actor = MagicMock(is_authenticated=True, is_superuser=True)

        result = EmpleadoService.eliminar(
            instance,
            actor_user=actor,
            hard_delete=True,
        )

        self.assertTrue(result)
        instance.delete.assert_called_once()

    def test_eliminar_soft_delete_changes_estado(self):
        instance = MagicMock(estado="ACTIVO")

        result = EmpleadoService.eliminar(
            instance,
            actor_user=None,
            hard_delete=False,
        )

        self.assertTrue(result)
        self.assertEqual(instance.estado, "INACTIVO")
        instance.save.assert_called_once_with(update_fields=["estado"])

    @patch("apps.empleados.services.empleado_service.Empleado.objects")
    def test_listar_uses_estado_activo_when_missing(self, empleado_objects):
        queryset = MagicMock()
        empleado_objects.filter.return_value = queryset

        EmpleadoService.listar({})

        empleado_objects.filter.assert_called_once_with(estado="ACTIVO")

    @patch("apps.empleados.services.empleado_service.timezone.localdate", return_value=date(2026, 5, 28))
    @patch("apps.empleados.services.empleado_service.EmpleadoService._obtener_registro_siigo_por_cedula")
    def test_construir_contexto_certificado_usa_datos_siigo(self, siigo_lookup, mocked_localdate):
        empleado = MagicMock(
            id=12,
            cedula="123456789",
            nombre="ANA",
            apellido="PEREZ",
            cargo="TECNICO",
            fecha_ingreso=None,
            permiso="",
            pasaporte="",
        )
        siigo_lookup.return_value = MagicMock(
            salario="1750905.00",
            datos={
                "cargo": "009-TECNICOS INSTALACIONES",
                "f_ingreso": "2025-02-04 00:00:00",
                "tipo_contrato": "OBRA Y LABOR",
                "nombre_empleado": "ANA PEREZ",
            },
        )

        context = EmpleadoService.construir_contexto_certificado_laboral(
            empleado=empleado,
            document_type="",
        )

        self.assertEqual(context["nombre_completo"], "ANA PEREZ")
        self.assertEqual(context["cargo"], "TECNICOS INSTALACIONES")
        self.assertEqual(context["document_type"], "CC")
        self.assertEqual(context["document_type_label"], "CC")
        self.assertEqual(context["salario"], Decimal("1750905.00"))
        self.assertEqual(context["salario_texto"], "$1.750.905")
        self.assertEqual(context["fecha_ingreso"], date(2025, 2, 4))
        self.assertEqual(context["fecha_expedicion"], date(2026, 5, 28))
        self.assertEqual(context["fecha_expedicion_texto"], "28/05/2026")
        self.assertEqual(context["contrato"], "Obra y labor")

    @patch("apps.empleados.services.empleado_service.EmpleadoService._obtener_registro_siigo_por_cedula")
    def test_construir_contexto_certificado_permiso_infiere_pt(self, siigo_lookup):
        empleado = MagicMock(
            id=21,
            cedula="99887766",
            nombre="LUIS",
            apellido="GOMEZ",
            cargo="AUXILIAR",
            fecha_ingreso=date(2024, 1, 15),
            permiso="PEP123",
            pasaporte="",
        )
        siigo_lookup.return_value = None

        context = EmpleadoService.construir_contexto_certificado_laboral(empleado=empleado)

        self.assertEqual(context["document_type"], "PT")
        self.assertEqual(context["document_type_label"], "PT")
        self.assertTrue(context["document_flags"]["PT"])

    def test_normalize_contract_value_fixes_broken_accents(self):
        contract = EmpleadoService._normalize_contract_value("T?rmino Indefinido.")

        self.assertEqual(contract, "Término indefinido")

    @patch("apps.empleados.services.empleado_service.EmpleadoService._obtener_registro_siigo_por_cedula")
    def test_generar_certificado_laboral_pdf_real(self, siigo_lookup):
        empleado = MagicMock(
            id=12,
            cedula="123456789",
            nombre="ANA",
            apellido="PEREZ",
            cargo="TECNICO",
            fecha_ingreso=date(2025, 2, 4),
            permiso="",
            pasaporte="",
        )
        siigo_lookup.return_value = MagicMock(
            salario="1750905.00",
            datos={
                "cargo": "009-TECNICOS INSTALACIONES",
                "f_ingreso": "2025-02-04 00:00:00",
                "tipo_contrato": "OBRA Y LABOR",
                "nombre_empleado": "ANA PEREZ",
            },
        )

        result = EmpleadoService.generar_certificado_laboral(
            empleado=empleado,
            document_type="CC",
        )

        self.assertTrue(result["filename"].startswith("certificado_laboral_"))
        self.assertTrue(result["filename"].endswith(".pdf"))
        self.assertEqual(len(result["filename"]), 60)
        self.assertTrue(result["content"].startswith(b"%PDF"))
        self.assertEqual(result["context"]["nombre_completo"], "ANA PEREZ")
        self.assertEqual(result["context"]["cargo"], "TECNICOS INSTALACIONES")
        self.assertEqual(result["context"]["contrato"], "Obra y labor")

    @patch("apps.empleados.services.empleado_service.EmpleadoService._obtener_registro_siigo_por_cedula")
    def test_generar_certificado_laboral_error_si_no_hay_datos_siigo(self, siigo_lookup):
        empleado = MagicMock(
            id=12,
            cedula="123456789",
            nombre="ANA",
            apellido="PEREZ",
            cargo="TECNICO",
            fecha_ingreso=date(2025, 2, 4),
            permiso="",
            pasaporte="",
        )
        siigo_lookup.return_value = None

        with self.assertRaises(ValueError) as context:
            EmpleadoService.generar_certificado_laboral(
                empleado=empleado,
                document_type="CC",
            )
        self.assertIn("No se encontró información del empleado en la base de datos de SIIGO", str(context.exception))


class EmpleadoViewSetTests(TestCase):
    @patch("apps.empleados.views.empleado_view.EmpleadoService.generar_certificado_laboral")
    def test_certificado_laboral_retorna_pdf(self, generate_certificate):
        generate_certificate.return_value = {
            "filename": "certificado_laboral_123.pdf",
            "content": b"%PDF-1.4",
            "context": {"cedula": "123"},
        }
        request = APIRequestFactory().get(
            "/empleados/empleados/1/certificado-laboral/",
            {
                "document_type": "CC",
            },
        )
        request = Request(request)
        view = EmpleadoViewSet()
        empleado = MagicMock()

        with patch.object(EmpleadoViewSet, "get_object", return_value=empleado):
            response = view.certificado_laboral(request, pk="1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn('attachment; filename="certificado_laboral_123.pdf"', response["Content-Disposition"])
        self.assertEqual(response.content, b"%PDF-1.4")
