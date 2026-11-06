from django.http import HttpResponse
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes

from apps.implementacion_fo.serializers import (
    MappingPredioReadSerializer,
    MappingPredioWriteSerializer,
    CuadraCheckResponseSerializer,
    DireccionCheckResponseSerializer,
)
from apps.implementacion_fo.services import MappingPredioService


class MappingPredioViewSet(ModelViewSet):
    """
    ViewSet para la gestión ágil del Mapping de Predios (Implementación FO).
    Sigue el patrón ViewSet -> Service -> Serializer.
    
    Provee CRUD, verificación no bloqueante de direcciones, alerta temprana de
    cuadras/planchas ya censadas y utilidades de importación/exportación masiva.
    """

    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return MappingPredioWriteSerializer
        return MappingPredioReadSerializer

    def _get_filtros(self):
        request = getattr(self, "request", None)
        params = getattr(request, "query_params", getattr(request, "GET", {})) if request else {}
        return {
            "barrio": params.get("barrio"),
            "lote_amp": params.get("lote_amp"),
            "nombre_calle": params.get("nombre_calle"),
            "buscar": params.get("buscar"),
        }

    def get_queryset(self):
        return MappingPredioService.listar(
            filtros=self._get_filtros(),
            actor_user=self.request.user if self.request.user.is_authenticated else None,
        )

    def perform_create(self, serializer):
        actor_user = self.request.user if self.request.user.is_authenticated else None
        predio = MappingPredioService.crear(actor_user, serializer.validated_data)
        serializer.instance = predio

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        read_serializer = MappingPredioReadSerializer(serializer.instance)
        return Response(read_serializer.data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        actor_user = self.request.user if self.request.user.is_authenticated else None
        predio = MappingPredioService.actualizar(
            self.get_object(), actor_user, serializer.validated_data
        )
        serializer.instance = predio

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        read_serializer = MappingPredioReadSerializer(serializer.instance)
        return Response(read_serializer.data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        actor_user = self.request.user if self.request.user.is_authenticated else None
        MappingPredioService.eliminar(instance, actor_user)
        return Response(
            {"detail": "Predio eliminado correctamente."},
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        summary="Alerta temprana de cuadra o plancha",
        description="Verifica si una plancha (AMP) o cuadra ya fue levantada para evitar repetir trabajo.",
        parameters=[
            OpenApiParameter("barrio", OpenApiTypes.STR, required=True),
            OpenApiParameter("lote_amp", OpenApiTypes.STR, required=True),
            OpenApiParameter("nombre_calle", OpenApiTypes.STR, required=False),
        ],
        responses={200: CuadraCheckResponseSerializer},
    )
    @action(detail=False, methods=["get"], url_path="verificar-cuadra")
    def verificar_cuadra(self, request):
        barrio = request.query_params.get("barrio")
        lote_amp = request.query_params.get("lote_amp")
        nombre_calle = request.query_params.get("nombre_calle")

        resultado = MappingPredioService.verificar_cuadra(
            barrio=barrio, lote_amp=lote_amp, nombre_calle=nombre_calle
        )
        serializer = CuadraCheckResponseSerializer(resultado)
        return Response(serializer.data)

    @extend_schema(
        summary="Verificación no bloqueante de dirección",
        description="Busca coincidencias previas de calle y placa sin bloquear la captura.",
        parameters=[
            OpenApiParameter("nombre_calle", OpenApiTypes.STR, required=True),
            OpenApiParameter("placa_unidad", OpenApiTypes.STR, required=True),
            OpenApiParameter("interior", OpenApiTypes.STR, required=False),
            OpenApiParameter("exclude_id", OpenApiTypes.INT, required=False),
        ],
        responses={200: DireccionCheckResponseSerializer},
    )
    @action(detail=False, methods=["get"], url_path="verificar-direccion")
    def verificar_direccion(self, request):
        nombre_calle = request.query_params.get("nombre_calle")
        placa_unidad = request.query_params.get("placa_unidad")
        interior = request.query_params.get("interior")
        exclude_id = request.query_params.get("exclude_id")

        resultado = MappingPredioService.verificar_direccion(
            nombre_calle=nombre_calle,
            placa_unidad=placa_unidad,
            interior=interior,
            exclude_id=exclude_id,
        )
        serializer = DireccionCheckResponseSerializer(resultado)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="barrios-sugeridos")
    def barrios_sugeridos(self, request):
        q = request.query_params.get("q")
        barrios = MappingPredioService.obtener_barrios_sugeridos(q)
        return Response({"barrios": barrios})

    @action(detail=False, methods=["get"], url_path="planchas-sugeridas")
    def planchas_sugeridas(self, request):
        barrio = request.query_params.get("barrio")
        q = request.query_params.get("q")
        planchas = MappingPredioService.obtener_planchas_sugeridas(barrio=barrio, query=q)
        return Response({"planchas": planchas})

    @extend_schema(
        summary="Importación masiva desde CSV",
        description="Carga archivo CSV con el formato de levantamiento.",
    )
    @action(detail=False, methods=["post"], url_path="importar-csv")
    def importar_csv(self, request):
        archivo = request.FILES.get("archivo")
        if not archivo:
            return Response(
                {"error": "No se adjuntó ningún archivo. Selecciona un archivo .csv"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not archivo.name.lower().endswith(".csv"):
            return Response(
                {"error": "Solo se permiten archivos en formato CSV (.csv)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        actor_user = request.user if request.user.is_authenticated else None
        try:
            resumen = MappingPredioService.importar_csv(actor_user, archivo)
            return Response(resumen, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {"error": f"Error al procesar el archivo CSV: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=False, methods=["post"], url_path="importar-excel")
    def importar_excel(self, request):
        """Alias para mantener compatibilidad con importar_csv."""
        return self.importar_csv(request)

    @extend_schema(
        summary="Exportación a Excel",
        description="Genera archivo .xlsx con los predios filtrados.",
    )
    @action(detail=False, methods=["get"], url_path="exportar-excel")
    def exportar_excel(self, request):
        filtros = self._get_filtros()
        archivo_excel = MappingPredioService.exportar_excel(filtros)
        response = HttpResponse(
            archivo_excel.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = 'attachment; filename="mapping_predios_fo.xlsx"'
        return response

    @extend_schema(
        summary="Reintentar sincronización con SharePoint",
        description="Fuerza el envío del predio individual hacia la tabla de Excel en SharePoint.",
    )
    @action(detail=True, methods=["post"], url_path="sync-sharepoint")
    def sync_sharepoint(self, request, pk=None):
        from apps.implementacion_fo.services import SharePointMappingService

        predio = self.get_object()
        resultado = SharePointMappingService.sync_predio_to_sharepoint(predio)
        if resultado.get("success"):
            return Response(resultado, status=status.HTTP_200_OK)
        return Response(resultado, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Sincronización en lote hacia SharePoint por Barrio",
        description="Envía los registros pendientes de un barrio en un solo lote hacia SharePoint.",
    )
    @action(detail=False, methods=["post"], url_path="sync-sharepoint-barrio")
    def sync_sharepoint_barrio(self, request):
        from apps.implementacion_fo.services import SharePointMappingService

        barrio = request.data.get("barrio")
        if not barrio:
            return Response(
                {"error": "Debes especificar el parámetro 'barrio'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        resultado = SharePointMappingService.sync_batch_by_barrio(barrio)
        if resultado.get("success"):
            return Response(resultado, status=status.HTTP_200_OK)
        return Response(resultado, status=status.HTTP_400_BAD_REQUEST)

