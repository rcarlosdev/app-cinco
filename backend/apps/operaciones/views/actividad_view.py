
from rest_framework import status
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
from rest_framework.viewsets import ModelViewSet

from apps.operaciones.serializers.actividad_serializer import (
    ActividadSerializer,
    ActividadWriteSerializer
)
from apps.operaciones.services.actividad_service import ActividadService


class ActividadViewSet(ModelViewSet):
    """
    ViewSet para gestionar actividades/solicitudes.
    
    Proporciona listar, crear, actualizar y eliminar actividades.
    Soporta filtrado avanzado por perfil, OT, estado, área, carpeta, etc.
    
    Autenticación requerida: Token Bearer o API Key
    """

    FILTER_PARAMS = (
        'ot',
        'estado',
        'area',
        'carpeta',
        'responsable_id',
        'buscar',
        'zona',
        'nodo',
        'fecha_inicio_desde',
        'fecha_inicio_hasta',
    )

    def _get_filtros(self):
        request = getattr(self, 'request', None)
        if request is None:
            return {}
        params = getattr(request, 'query_params', getattr(request, 'GET', {}))
        return {
            key: params.get(key)
            for key in self.FILTER_PARAMS
            if params.get(key)
        }

    @staticmethod
    def _get_authenticated_user_id(user):
        if user and getattr(user, 'is_authenticated', False):
            return user.id
        return None

    def get_queryset(self):
        request = getattr(self, 'request', None)
        user = getattr(request, 'user', None) if request else None
        usuario_id = self._get_authenticated_user_id(user)
        return ActividadService.listar(
            usuario_id=usuario_id,
            filtros=self._get_filtros(),
        )

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return ActividadWriteSerializer
        return ActividadSerializer

    @extend_schema(
        summary="Listar actividades/solicitudes",
        description="""
        Obtiene un listado de actividades filtradas según el perfil del usuario actual.
        
        **Comportamiento de filtrado por perfil:**
        - Por defecto, solo muestra actividades que el usuario creó (created_by) 
          O donde es el responsable (responsable_snapshot.empleado_id)
        
        **Parámetros de filtrado disponibles:**
        - `ot`: Filtra por alguna OT relacionada (búsqueda parcial)
        - `estado`: Filtra por estado (pendiente, en_progreso, completada, cancelada, pausada, reprogramada)
        - `area`: Filtra por área del responsable (búsqueda parcial)
        - `carpeta`: Filtra por carpeta del responsable (búsqueda parcial)
        - `responsable_id`: Filtra por ID del empleado responsable
        - `buscar`: Búsqueda general en descripción, tipo de trabajo, OT y nombre del responsable
        - `zona`: Filtra por zona de ubicación (búsqueda parcial)
        - `nodo`: Filtra por nodo de ubicación (búsqueda parcial)
        - `fecha_inicio_desde`: Filtra actividades con fecha de inicio >= a esta fecha (YYYY-MM-DD)
        - `fecha_inicio_hasta`: Filtra actividades con fecha de inicio <= a esta fecha (YYYY-MM-DD)
        """,
        tags=["operaciones"],
        parameters=[
            OpenApiParameter(
                name='ot',
                description='Filtra por alguna OT relacionada (búsqueda parcial). Ej: OT-2024-001',
                required=False,
                type=OpenApiTypes.STR
            ),
            OpenApiParameter(
                name='estado',
                description='Filtra por estado de la actividad. Valores: pendiente, en_progreso, completada, cancelada, pausada, reprogramada',
                required=False,
                type=OpenApiTypes.STR,
                enum=['pendiente', 'en_progreso', 'completada', 'cancelada', 'pausada', 'reprogramada']
            ),
            OpenApiParameter(
                name='area',
                description='Filtra por área del responsable (búsqueda parcial)',
                required=False,
                type=OpenApiTypes.STR
            ),
            OpenApiParameter(
                name='carpeta',
                description='Filtra por carpeta del responsable (búsqueda parcial)',
                required=False,
                type=OpenApiTypes.STR
            ),
            OpenApiParameter(
                name='responsable_id',
                description='Filtra por ID del empleado responsable',
                required=False,
                type=OpenApiTypes.INT
            ),
            OpenApiParameter(
                name='buscar',
                description='Búsqueda general en descripción, tipo de trabajo, OT y nombre del responsable',
                required=False,
                type=OpenApiTypes.STR
            ),
            OpenApiParameter(
                name='zona',
                description='Filtra por zona de ubicación (búsqueda parcial)',
                required=False,
                type=OpenApiTypes.STR
            ),
            OpenApiParameter(
                name='nodo',
                description='Filtra por nodo de ubicación (búsqueda parcial)',
                required=False,
                type=OpenApiTypes.STR
            ),
            OpenApiParameter(
                name='fecha_inicio_desde',
                description='Filtra actividades con fecha de inicio >= a esta fecha (YYYY-MM-DD)',
                required=False,
                type=OpenApiTypes.DATE
            ),
            OpenApiParameter(
                name='fecha_inicio_hasta',
                description='Filtra actividades con fecha de inicio <= a esta fecha (YYYY-MM-DD)',
                required=False,
                type=OpenApiTypes.DATE
            ),
        ]
    )
    def list(self, request, *args, **kwargs):
        """Lista actividades con filtros aplicados"""
        return super().list(request, *args, **kwargs)

    @extend_schema(
        summary="Crear una nueva actividad/solicitud",
        description="""
        Crea una nueva actividad con sus detalles de ubicación.
        
        **Nota:** La actividad será creada por el usuario autenticado (created_by).
        El responsable debe ser un empleado válido existente en la base de datos de empleados.
        
        **Campos requeridos:**
        - `ots`: Lista de OTs relacionadas. Debe incluir al menos una.
        - `responsable_id`: ID del empleado responsable
        - `detalle`: Objeto con descripción y tipo de trabajo
        - `ubicacion`: Objeto con datos de ubicación
        
        **Campos opcionales:**
        - `fecha_inicio`: Fecha de inicio (YYYY-MM-DD)
        - `fecha_fin_estimado`: Fecha fin estimada (YYYY-MM-DD)
        - `fecha_fin_real`: Fecha fin real (YYYY-MM-DD)
        """,
        tags=["operaciones"],
        request=ActividadWriteSerializer,
        responses={201: ActividadSerializer}
    )
    def create(self, request, *args, **kwargs):
        """Crear una nueva actividad"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        actor_user_id = self._get_authenticated_user_id(request.user)
        actividad = ActividadService.crear(
            serializer.validated_data,
            actor_user_id=actor_user_id,
        )

        return Response(
            ActividadSerializer(actividad).data,
            status=status.HTTP_201_CREATED
        )

    @extend_schema(
        summary="Obtener detalles de una actividad",
        description="Obtiene toda la información de una actividad específica incluyendo detalles, ubicación y snapshot del responsable.",
        tags=["operaciones"],
        responses={200: ActividadSerializer}
    )
    def retrieve(self, request, *args, **kwargs):
        """Obtener detalles de una actividad"""
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        summary="Actualizar una actividad completamente",
        description="Actualiza todos los campos de una actividad. Se requieren todos los campos requeridos.",
        tags=["operaciones"],
        request=ActividadWriteSerializer,
        responses={200: ActividadSerializer}
    )
    def update(self, request, *args, **kwargs):
        """Actualizar una actividad completamente"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(
            instance,
            data=request.data,
            partial=partial,
            context={**self.get_serializer_context(), 'actor_user_id': self._get_authenticated_user_id(request.user)},
        )
        serializer.is_valid(raise_exception=True)
        actividad = serializer.save()
        return Response(ActividadSerializer(actividad).data)

    @extend_schema(
        summary="Actualizar parcialmente una actividad",
        description="Actualiza solo los campos proporcionados de una actividad.",
        tags=["operaciones"],
        request=ActividadWriteSerializer,
        responses={200: ActividadSerializer}
    )
    def partial_update(self, request, *args, **kwargs):
        """Actualizar parcialmente una actividad"""
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)

    @extend_schema(
        summary="Eliminar una actividad",
        description="""
        Realiza soft delete por defecto: marca la actividad como eliminada (`is_deleted=true`) sin borrarla físicamente.

        **Eliminación física (caso específico):**
        - Enviar `?hard_delete=true`
        - Requiere usuario administrador (`is_superuser`)
        """,
        tags=["operaciones"],
        parameters=[
            OpenApiParameter(
                name='hard_delete',
                description='Si es true y el usuario es superusuario, elimina físicamente el registro',
                required=False,
                type=OpenApiTypes.BOOL
            ),
        ],
        responses={204: None}
    )
    def destroy(self, request, *args, **kwargs):
        """Eliminar una actividad (soft delete por defecto)"""
        instance = self.get_object()

        hard_delete = str(request.query_params.get('hard_delete', '')).lower() in ('1', 'true', 'yes')
        was_deleted = ActividadService.eliminar(
            instance,
            actor_user=request.user,
            hard_delete=hard_delete,
        )

        if not was_deleted:
            return Response(
                {'detail': 'No tienes permisos para eliminación física.'},
                status=status.HTTP_403_FORBIDDEN
            )

        return Response(status=status.HTTP_204_NO_CONTENT)


