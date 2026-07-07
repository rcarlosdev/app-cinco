from apps.empleados.models import Empleado
from rest_framework.viewsets import ModelViewSet
from apps.empleados.serializers import EmpleadoSerializer
from rest_framework.response import Response
from rest_framework import status
from rest_framework import filters
from rest_framework.decorators import action
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse, OpenApiTypes
from django.http import HttpResponse
from apps.empleados.services import EmpleadoService


class EmpleadoViewSet(ModelViewSet):
    """
    ViewSet para gestionar empleados.
    
    Proporciona listar, crear, actualizar y eliminar empleados.
    Filtra automáticamente solo empleados activos.
    Soporta búsqueda en: cédula, nombre, apellido, cargo, móvil.
    
    Autenticación requerida: Token Bearer o API Key
    """
    queryset = Empleado.objects.all()
    serializer_class = EmpleadoSerializer
    # Usa permisos por defecto: IsAuthenticatedOrAPIKey
    filter_backends = [filters.SearchFilter]
    search_fields = ['cedula', 'nombre', 'apellido', 'cargo', 'movil']

    def get_queryset(self):
        return EmpleadoService.listar(self.request.query_params)

    @extend_schema(
        summary="Listar empleados activos",
        description="""
        Obtiene un listado de empleados con filtros avanzados.
        
        **Filtrado automático por estado:**
        - Si no envías `estado`, retorna solo empleados `ACTIVO`
        - Si envías `estado`, filtra por ese valor (`ACTIVO`, `INACTIVO`, `SUSPENDIDO`)
        
        **Parámetros de filtro disponibles:**
        - `search`: Búsqueda general en cédula, nombre, apellido, cargo, móvil
        - `cedula`, `nombre`, `apellido`, `area`, `carpeta`, `cargo`, `movil`
        - `supervisor`, `sede`, `codigo_sap`, `estado`
        
        **Campos incluidos:**
        - id, cédula, nombre, apellido, área, carpeta, cargo, móvil, estado, etc.
        """,
        tags=["empleados"],
        parameters=[
            OpenApiParameter(
                name='search',
                description='Búsqueda en cédula, nombre, apellido, cargo o móvil (búsqueda parcial, insensible a mayúsculas)',
                required=False,
                type=OpenApiTypes.STR
            ),
            OpenApiParameter(
                name='cedula',
                description='Filtra por cédula (búsqueda parcial)',
                required=False,
                type=OpenApiTypes.STR
            ),
            OpenApiParameter(
                name='nombre',
                description='Filtra por nombre (búsqueda parcial)',
                required=False,
                type=OpenApiTypes.STR
            ),
            OpenApiParameter(
                name='apellido',
                description='Filtra por apellido (búsqueda parcial)',
                required=False,
                type=OpenApiTypes.STR
            ),
            OpenApiParameter(
                name='area',
                description='Filtra por área (búsqueda parcial)',
                required=False,
                type=OpenApiTypes.STR
            ),
            OpenApiParameter(
                name='carpeta',
                description='Filtra por carpeta (búsqueda parcial)',
                required=False,
                type=OpenApiTypes.STR
            ),
            OpenApiParameter(
                name='cargo',
                description='Filtra por cargo (búsqueda parcial)',
                required=False,
                type=OpenApiTypes.STR
            ),
            OpenApiParameter(
                name='movil',
                description='Filtra por móvil (búsqueda parcial)',
                required=False,
                type=OpenApiTypes.STR
            ),
            OpenApiParameter(
                name='supervisor',
                description='Filtra por supervisor (búsqueda parcial)',
                required=False,
                type=OpenApiTypes.STR
            ),
            OpenApiParameter(
                name='sede',
                description='Filtra por sede (búsqueda parcial)',
                required=False,
                type=OpenApiTypes.STR
            ),
            OpenApiParameter(
                name='codigo_sap',
                description='Filtra por código SAP (búsqueda parcial)',
                required=False,
                type=OpenApiTypes.STR
            ),
            OpenApiParameter(
                name='estado',
                description='Filtra por estado. Valores: ACTIVO, INACTIVO, SUSPENDIDO',
                required=False,
                type=OpenApiTypes.STR,
                enum=['ACTIVO', 'INACTIVO', 'SUSPENDIDO']
            ),
        ]
    )
    def list(self, request, *args, **kwargs):
        """Lista empleados activos con búsqueda"""
        return super().list(request, *args, **kwargs)

    @extend_schema(
        summary="Crear un nuevo empleado",
        description="""
        Crea un nuevo empleado.
        
        **Campos requeridos:**
        - cedula: Cédula única
        - nombre: Nombre del empleado
        - apellido: Apellido del empleado
        - cargo: Cargo del empleado
        - area: Área a la que pertenece
        - carpeta: Carpeta asignada
        - movil: Número de móvil
        
        **Campos opcionales:**
        - estado: Estado del empleado (por defecto ACTIVO)
        - email: Correo electrónico
        """,
        tags=["empleados"],
    )
    def create(self, request, *args, **kwargs):
        """Crear un nuevo empleado"""
        return super().create(request, *args, **kwargs)

    @extend_schema(
        summary="Obtener detalles de un empleado",
        description="Obtiene toda la información de un empleado específico",
        tags=["empleados"],
    )
    def retrieve(self, request, *args, **kwargs):
        """Obtener detalles de un empleado"""
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        summary="Actualizar un empleado completamente",
        description="Actualiza todos los campos de un empleado. Se requieren todos los campos requeridos.",
        tags=["empleados"],
    )
    def update(self, request, *args, **kwargs):
        """Actualizar un empleado completamente"""
        return super().update(request, *args, **kwargs)

    @extend_schema(
        summary="Actualizar parcialmente un empleado",
        description="Actualiza solo los campos proporcionados de un empleado.",
        tags=["empleados"],
    )
    def partial_update(self, request, *args, **kwargs):
        """Actualizar parcialmente un empleado"""
        return super().partial_update(request, *args, **kwargs)

    @extend_schema(
        summary="Eliminar un empleado",
        description="""
        Realiza soft delete por defecto cambiando `estado` a `INACTIVO`.

        **Eliminación física (caso específico):**
        - Enviar `?hard_delete=true`
        - Requiere una cuenta administradora (`is_superuser`)
        """,
        tags=["empleados"],
        parameters=[
            OpenApiParameter(
                name='hard_delete',
                description='Si es true y la cuenta es superusuaria, elimina físicamente el registro',
                required=False,
                type=OpenApiTypes.BOOL
            ),
        ]
    )
    def destroy(self, request, *args, **kwargs):
        """Eliminar un empleado (soft delete por defecto)"""
        instance = self.get_object()

        hard_delete = str(request.query_params.get('hard_delete', '')).lower() in ('1', 'true', 'yes')
        was_deleted = EmpleadoService.eliminar(
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

    @extend_schema(
        summary="Generar certificado laboral en PDF",
        description="""
        Genera un certificado laboral en PDF a partir de la información del empleado y
        del complemento en `cinco_base_de_personal_siigo`.

        **Fuente principal de datos:**
        - `cinco_base_de_personal`: nombre, cédula, cargo base, fecha ingreso
        - `cinco_base_de_personal_siigo`: salario, tipo contrato, cargo SIIGO y extras JSON

        **Parámetros opcionales:**
        - `document_type`: fuerza el tipo de documento (`CC`, `PT`, `TI`, `CE`)
        """,
        tags=["empleados"],
        parameters=[
            OpenApiParameter(
                name="document_type",
                description="Tipo de documento a marcar en el certificado",
                required=False,
                type=OpenApiTypes.STR,
                enum=["CC", "PT", "TI", "CE"],
            ),
        ],
        responses={
            (200, "application/pdf"): OpenApiResponse(
                response=OpenApiTypes.BINARY,
                description="Archivo PDF del certificado laboral.",
            ),
        },
    )
    @action(detail=True, methods=["get"], url_path="certificado-laboral")
    def certificado_laboral(self, request, *args, **kwargs):
        instance = self.get_object()
        try:
            result = EmpleadoService.generar_certificado_laboral(
                empleado=instance,
                document_type=request.query_params.get("document_type", ""),
            )
        except RuntimeError as exc:
            detail = str(exc)
            if detail == "reportlab_no_instalado":
                return Response(
                    {"detail": "El servidor no tiene instalada la dependencia para generar PDF."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
            raise

        response = HttpResponse(result["content"], content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{result["filename"]}"'
        return response
