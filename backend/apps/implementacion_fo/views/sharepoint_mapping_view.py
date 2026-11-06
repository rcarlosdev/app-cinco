from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from drf_spectacular.utils import extend_schema

from apps.implementacion_fo.models import SharePointMappingConfig
from apps.implementacion_fo.serializers import SharePointMappingConfigSerializer
from apps.implementacion_fo.services import SharePointMappingService


class SharePointMappingConfigViewSet(ModelViewSet):
    """
    ViewSet para administrar las configuraciones de enlace entre Barrios de Mapping
    y sus archivos/tablas en Microsoft SharePoint.
    """

    queryset = SharePointMappingConfig.objects.all().order_by("barrio")
    serializer_class = SharePointMappingConfigSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        qs = SharePointMappingConfig.objects.all().order_by("barrio")
        request = getattr(self, "request", None)
        if request:
            params = getattr(request, "query_params", getattr(request, "GET", {}))
            tipo = params.get("tipo_destino")
            if tipo:
                qs = qs.filter(tipo_destino=tipo)
        return qs

    def perform_create(self, serializer):
        user = self.request.user if self.request.user.is_authenticated else None
        serializer.save(created_by=user, updated_by=user)

    def perform_update(self, serializer):
        user = self.request.user if self.request.user.is_authenticated else None
        serializer.save(updated_by=user)

    @extend_schema(
        summary="Probar conexión con Microsoft Graph / SharePoint",
        description="Valida que las credenciales de Azure y el enlace a SharePoint sean válidos.",
    )
    @action(detail=False, methods=["get"], url_path="test-conexion", permission_classes=[AllowAny])
    def test_conexion(self, request):
        try:
            token = SharePointMappingService.get_access_token()
            site_id = SharePointMappingService.resolve_site_id()
            drives = SharePointMappingService.list_drives(site_id)
            drives_summary = [
                {"id": d.get("id"), "name": d.get("name"), "description": d.get("description")}
                for d in drives
            ]
            return Response(
                {
                    "success": True,
                    "message": "Conexión exitosa con Microsoft Graph y SharePoint.",
                    "site_id": site_id,
                    "drives_count": len(drives),
                    "drives": drives_summary,
                },
                status=status.HTTP_200_OK,
            )
        except Exception as exc:
            return Response(
                {
                    "success": False,
                    "error": str(exc),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    @extend_schema(
        summary="Listar archivos Excel disponibles en SharePoint",
        description="Explora la biblioteca de documentos y lista los archivos .xlsx para asociar barrios.",
    )
    @action(detail=False, methods=["get"], url_path="archivos-disponibles", permission_classes=[AllowAny])
    def archivos_disponibles(self, request):
        try:
            site_id = SharePointMappingService.resolve_site_id()
            drives = SharePointMappingService.list_drives(site_id)
            if not drives:
                return Response(
                    {"success": False, "error": "No se encontraron bibliotecas de documentos en SharePoint."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            archivos = []
            req_drive_id = request.query_params.get("drive_id")
            if req_drive_id:
                drive_id = req_drive_id
                archivos = SharePointMappingService.list_excel_files(req_drive_id)
            else:
                drive_id = drives[0]["id"]
                for d in drives:
                    found = SharePointMappingService.list_excel_files(d["id"])
                    archivos.extend(found)
                    if found and drive_id == drives[0]["id"]:
                        drive_id = d["id"]

            return Response(
                {
                    "success": True,
                    "drive_id": drive_id,
                    "total": len(archivos),
                    "archivos": archivos,
                    "drives": [{"id": d.get("id"), "name": d.get("name")} for d in drives],
                },
                status=status.HTTP_200_OK,
            )
        except Exception as exc:
            return Response({"success": False, "error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Listar listas disponibles en SharePoint",
        description="Obtiene las listas personalizadas creadas en el sitio para asociar barrios.",
    )
    @action(detail=False, methods=["get"], url_path="listas-disponibles", permission_classes=[AllowAny])
    def listas_disponibles(self, request):
        try:
            listas = SharePointMappingService.list_sharepoint_lists()
            return Response(
                {
                    "success": True,
                    "total": len(listas),
                    "listas": listas,
                },
                status=status.HTTP_200_OK,
            )
        except Exception as exc:
            return Response({"success": False, "error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Auto-descubrir y sincronizar barrios desde Listas de SharePoint",
        description="Escanea exclusivamente listas personalizadas de SharePoint (Microsoft Lists) y crea/actualiza configuraciones por barrio.",
    )
    @action(detail=False, methods=["post"], url_path="auto-descubrir")
    def auto_descubrir(self, request):
        try:
            # Descubrir ÚNICAMENTE Listas de SharePoint (Microsoft Lists)
            res_listas = SharePointMappingService.auto_descubrir_listas()

            return Response(
                {
                    "success": True,
                    "listas": res_listas,
                },
                status=status.HTTP_200_OK,
            )
        except Exception as exc:
            return Response({"success": False, "error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

