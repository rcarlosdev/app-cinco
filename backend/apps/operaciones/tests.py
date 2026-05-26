from unittest import TestCase
from unittest.mock import MagicMock, patch

from django.test import TestCase as DjangoTestCase

from apps.operaciones.models import (
	Actividad,
	ActividadOT,
	normalize_ot_values,
)
from apps.operaciones.services.actividad_service import ActividadService


class ActividadServiceTests(TestCase):
	def test_ot_helpers_normalize_and_serialize_values(self):
		values = normalize_ot_values([" OT-1 ", "OT-2", "OT-1", "", None])

		self.assertEqual(values, ["OT-1", "OT-2"])

	def test_eliminar_hard_delete_requires_superuser(self):
		instance = MagicMock()
		actor = MagicMock(is_authenticated=True, is_superuser=False)

		result = ActividadService.eliminar(
			instance,
			actor_user=actor,
			hard_delete=True,
		)

		self.assertFalse(result)
		instance.delete.assert_not_called()

	def test_eliminar_hard_delete_superuser(self):
		instance = MagicMock()
		actor = MagicMock(is_authenticated=True, is_superuser=True)

		result = ActividadService.eliminar(
			instance,
			actor_user=actor,
			hard_delete=True,
		)

		self.assertTrue(result)
		instance.delete.assert_called_once()

	def test_eliminar_soft_delete_marks_flags(self):
		instance = MagicMock()
		actor = MagicMock(is_authenticated=True, id=99)

		result = ActividadService.eliminar(
			instance,
			actor_user=actor,
			hard_delete=False,
		)

		self.assertTrue(result)
		self.assertTrue(instance.is_deleted)
		self.assertEqual(instance.deleted_by, 99)
		instance.save.assert_called_once_with(
			update_fields=['is_deleted', 'deleted_at', 'deleted_by', 'updated_at']
		)

	@patch('apps.operaciones.services.actividad_service.Actividad.objects')
	def test_listar_applies_default_base_filter(self, actividad_objects):
		queryset = MagicMock()
		queryset.select_related.return_value = queryset
		queryset.prefetch_related.return_value = queryset
		actividad_objects.filter.return_value = queryset

		ActividadService.listar(usuario_id=None, filtros={})

		actividad_objects.filter.assert_called_once_with(is_deleted=False)
		queryset.select_related.assert_called_once_with(
			'detalle',
			'ubicacion',
			'responsable_snapshot'
		)
		queryset.prefetch_related.assert_called_once_with('ot_relaciones')


class ActividadOTRulesTests(DjangoTestCase):
	def test_validar_ots_unicas_detecta_ot_en_otra_actividad(self):
		actividad = Actividad.objects.create(
			ot='OT-100',
			responsable_id=1,
		)
		ActividadOT.objects.create(
			actividad=actividad,
			ot='OT-100',
			created_by=1,
			updated_by=1,
		)

		with self.assertRaisesMessage(
			ValueError,
			'Las siguientes OTs ya están asociadas a otra actividad: OT-100',
		):
			ActividadService.validar_ots_unicas(['OT-100'], actividad_id=2)

	def test_validar_ots_unicas_permita_ot_de_la_misma_actividad(self):
		actividad = Actividad.objects.create(
			ot='OT-100',
			responsable_id=1,
		)
		ActividadOT.objects.create(
			actividad=actividad,
			ot='OT-100',
			created_by=1,
			updated_by=1,
		)

		ActividadService.validar_ots_unicas(['OT-100'], actividad_id=actividad.id)


class ActividadServiceOTSyncTests(DjangoTestCase):
	def test_sync_ots_recalcula_fechas_padre_correctamente(self):
		actividad = Actividad.objects.create(
			responsable_id=1,
			fecha_inicio="2026-05-01",
			fecha_fin_estimado="2026-05-02"
		)

		ots_data = [
			{'ot': 'OT-A', 'fecha_inicio': '2026-05-05', 'fecha_fin': '2026-05-15'},
			{'ot': 'OT-B', 'fecha_inicio': '2026-05-03', 'fecha_fin': '2026-05-10'},
			{'ot': 'OT-C', 'fecha_inicio': '2026-05-07', 'fecha_fin': '2026-05-20'},
		]

		ActividadService._sync_ots(actividad, ots_data, actor_user_id=1)
		actividad.refresh_from_db()

		self.assertEqual(actividad.ot, 'OT-A')
		from datetime import date
		self.assertEqual(actividad.fecha_inicio, date(2026, 5, 3))
		self.assertEqual(actividad.fecha_fin_estimado, date(2026, 5, 20))
