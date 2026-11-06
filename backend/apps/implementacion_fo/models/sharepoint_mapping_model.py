from django.conf import settings
from django.db import models


class SharePointMappingConfig(models.Model):
    """
    Configuración de enlace entre un Barrio / Proyecto de Mapping y su archivo Excel
    o Lista de destino en Microsoft SharePoint.

    Permite dirigir dinámicamente cada registro al archivo .xlsx correcto
    (ej: Barrio Belén -> archivo Mapping_Belen.xlsx).
    """

    DESTINO_CHOICES = (
        ("EXCEL", "Archivo Excel (.xlsx)"),
        ("LISTA", "Lista de SharePoint"),
    )

    barrio = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text="Nombre exacto del barrio o sector (ej: BELEN, LAURELES)",
    )
    descripcion = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Descripción o referencia del proyecto / contrato",
    )
    tipo_destino = models.CharField(
        max_length=20,
        choices=DESTINO_CHOICES,
        default="EXCEL",
        help_text="Tipo de almacenamiento en SharePoint",
    )
    sp_drive_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="ID del Drive (biblioteca de documentos de SharePoint)",
    )
    sp_item_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="ID único del archivo Excel en SharePoint (Item ID de Graph)",
    )
    sp_table_name = models.CharField(
        max_length=100,
        default="Tabla1",
        help_text="Nombre de la tabla dentro del Excel (ej: Tabla1, Registros)",
    )
    sp_list_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="ID de la lista (en caso de usar tipo_destino=LISTA)",
    )
    activo = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Habilita o deshabilita la sincronización automática para este barrio",
    )

    # Auditoría
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fo_sp_mapping_configs_creados",
        db_column="created_by",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fo_sp_mapping_configs_actualizados",
        db_column="updated_by",
    )

    class Meta:
        db_table = "implementacion_sharepoint_mapping"
        ordering = ["barrio"]
        verbose_name = "Configuración SharePoint Mapping"
        verbose_name_plural = "Configuraciones SharePoint Mapping"

    def __str__(self):
        return f"{self.barrio} -> {self.tipo_destino} ({self.sp_item_id or self.sp_list_id or 'Sin configurar'})"
