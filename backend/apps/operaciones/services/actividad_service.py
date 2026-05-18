from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.empleados.services import EmpleadoService
from apps.operaciones.models import (
    Actividad,
    ActividadDetalle,
    ActividadOT,
    ActividadResponsableSnapshot,
    ActividadUbicacion,
    normalize_ot_values,
)


class ActividadService:
    @staticmethod
    def _sync_ots(actividad: Actividad, ots, actor_user_id=None):
        normalized_ots = normalize_ot_values(ots)
        actividad.ot = normalized_ots[0] if normalized_ots else ""
        actividad.save(update_fields=['ot', 'updated_at'])

        existing_relations = {
            relation.ot: relation
            for relation in ActividadOT.objects.filter(actividad=actividad)
        }

        current_active = set()
        for ot in normalized_ots:
            relation = existing_relations.get(ot)
            if relation:
                updates = []
                if not relation.is_active:
                    relation.is_active = True
                    updates.append('is_active')
                if actor_user_id is not None:
                    relation.updated_by = actor_user_id
                    updates.append('updated_by')
                if updates:
                    relation.save(update_fields=updates + ['updated_at'])
            else:
                ActividadOT.objects.create(
                    actividad=actividad,
                    ot=ot,
                    created_by=actor_user_id,
                    updated_by=actor_user_id,
                )
            current_active.add(ot)

        for ot, relation in existing_relations.items():
            if ot not in current_active and relation.is_active:
                relation.is_active = False
                relation.updated_by = actor_user_id
                relation.save(update_fields=['is_active', 'updated_by', 'updated_at'])

    @staticmethod
    def validar_ots_unicas(ots, actividad_id=None):
        normalized_ots = normalize_ot_values(ots)
        if not normalized_ots:
            return

        queryset = ActividadOT.objects.filter(ot__in=normalized_ots, is_active=True)
        if actividad_id is not None:
            queryset = queryset.exclude(actividad_id=actividad_id)

        duplicates = list(queryset.values_list('ot', flat=True))
        if duplicates:
            duplicated = ", ".join(sorted(set(duplicates)))
            raise ValueError(
                f"Las siguientes OTs ya están asociadas a otra actividad: {duplicated}"
            )

    @staticmethod
    def crear(data: dict, actor_user_id=None) -> Actividad:
        payload = data.copy()
        detalle_data = payload.pop('detalle')
        ubicacion_data = payload.pop('ubicacion')
        ots = payload.pop('ots', None)
        payload.pop('ot', None)

        with transaction.atomic():
            empleado = EmpleadoService().obtener_basico(payload['responsable_id'])
            ActividadService.validar_ots_unicas(ots)

            payload['created_by'] = actor_user_id
            payload['updated_by'] = actor_user_id
            payload['ot'] = ots[0]

            actividad = Actividad.objects.create(**payload)

            ActividadResponsableSnapshot.objects.create(
                actividad=actividad,
                empleado_id=empleado['id'],
                nombre=empleado['nombre'],
                area=empleado['area'],
                carpeta=empleado['carpeta'],
                cargo=empleado['cargo'],
                movil=empleado['movil'],
            )

            ActividadUbicacion.objects.create(
                actividad=actividad,
                **ubicacion_data,
            )

            ActividadDetalle.objects.create(
                actividad=actividad,
                **detalle_data,
            )

            ActividadService._sync_ots(
                actividad,
                ots,
                actor_user_id=actor_user_id,
            )

            return actividad

    @staticmethod
    def actualizar(instance: Actividad, validated_data: dict, actor_user_id=None) -> Actividad:
        detalle_data = validated_data.pop('detalle', None)
        ubicacion_data = validated_data.pop('ubicacion', None)
        ots = validated_data.pop('ots', None)

        with transaction.atomic():
            if ots is not None:
                ActividadService.validar_ots_unicas(ots, actividad_id=instance.id)

            for field, value in validated_data.items():
                setattr(instance, field, value)

            if actor_user_id is not None:
                instance.updated_by = actor_user_id

            instance.save()

            if detalle_data:
                ActividadDetalle.objects.update_or_create(
                    actividad=instance,
                    defaults=detalle_data,
                )

            if ubicacion_data:
                ActividadUbicacion.objects.update_or_create(
                    actividad=instance,
                    defaults=ubicacion_data,
                )

            if 'responsable_id' in validated_data:
                empleado = EmpleadoService().obtener_basico(instance.responsable_id)
                ActividadResponsableSnapshot.objects.update_or_create(
                    actividad=instance,
                    defaults={
                        'empleado_id': empleado['id'],
                        'nombre': empleado['nombre'],
                        'area': empleado['area'],
                        'carpeta': empleado['carpeta'],
                        'cargo': empleado['cargo'],
                        'movil': empleado['movil'],
                    },
                )

            if ots is not None:
                ActividadService._sync_ots(
                    instance,
                    ots,
                    actor_user_id=actor_user_id,
                )

        return instance

    @staticmethod
    def listar(usuario_id=None, filtros=None):
        queryset = Actividad.objects.filter(is_deleted=False).select_related(
            'detalle',
            'ubicacion',
            'responsable_snapshot',
        ).prefetch_related('ot_relaciones')
        filtros = filtros or {}

        if usuario_id:
            queryset = queryset.filter(
                Q(created_by=usuario_id) |
                Q(responsable_snapshot__empleado_id=usuario_id)
            ).distinct()

        if filtros.get('ot'):
            queryset = queryset.filter(
                Q(ot__icontains=filtros['ot']) |
                Q(ot_relaciones__ot__icontains=filtros['ot'], ot_relaciones__is_active=True)
            ).distinct()

        if filtros.get('estado'):
            queryset = queryset.filter(estado=filtros['estado'])

        if filtros.get('area'):
            queryset = queryset.filter(
                responsable_snapshot__area__icontains=filtros['area']
            )

        if filtros.get('carpeta'):
            queryset = queryset.filter(
                responsable_snapshot__carpeta__icontains=filtros['carpeta']
            )

        if filtros.get('buscar'):
            buscar = filtros['buscar']
            queryset = queryset.filter(
                Q(detalle__descripcion__icontains=buscar) |
                Q(detalle__tipo_trabajo__icontains=buscar) |
                Q(ot__icontains=buscar) |
                Q(ot_relaciones__ot__icontains=buscar, ot_relaciones__is_active=True) |
                Q(responsable_snapshot__nombre__icontains=buscar)
            ).distinct()

        if filtros.get('responsable_id'):
            queryset = queryset.filter(
                responsable_snapshot__empleado_id=filtros['responsable_id']
            )

        if filtros.get('fecha_inicio_desde'):
            queryset = queryset.filter(
                fecha_inicio__gte=filtros['fecha_inicio_desde']
            )

        if filtros.get('fecha_inicio_hasta'):
            queryset = queryset.filter(
                fecha_inicio__lte=filtros['fecha_inicio_hasta']
            )

        if filtros.get('zona'):
            queryset = queryset.filter(
                ubicacion__zona__icontains=filtros['zona']
            )

        if filtros.get('nodo'):
            queryset = queryset.filter(
                ubicacion__nodo__icontains=filtros['nodo']
            )

        return queryset

    @staticmethod
    def eliminar(instance: Actividad, actor_user=None, hard_delete=False) -> bool:
        if hard_delete:
            if not actor_user or not actor_user.is_authenticated or not actor_user.is_superuser:
                return False
            instance.delete()
            return True

        deleted_by = actor_user.id if actor_user and actor_user.is_authenticated else None
        instance.is_deleted = True
        instance.deleted_at = timezone.now()
        instance.deleted_by = deleted_by
        instance.save(update_fields=['is_deleted', 'deleted_at', 'deleted_by', 'updated_at'])
        return True
