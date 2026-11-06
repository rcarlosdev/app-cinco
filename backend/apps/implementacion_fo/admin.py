from django.contrib import admin
from .models import MappingPredio, SharePointMappingConfig


@admin.register(MappingPredio)
class MappingPredioAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "nombre_calle",
        "placa_unidad",
        "nombre_conjunto",
        "barrio",
        "lote_amp",
        "total_unidades",
        "sp_synced",
        "sp_synced_at",
        "created_at",
        "created_by",
    )
    list_filter = ("sp_synced", "barrio", "lote_amp", "is_deleted")
    search_fields = (
        "nombre_calle",
        "placa_unidad",
        "nombre_conjunto",
        "barrio",
        "lote_amp",
    )
    readonly_fields = ("created_at", "updated_at", "deleted_at", "sp_synced_at", "sp_sync_error")


@admin.register(SharePointMappingConfig)
class SharePointMappingConfigAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "barrio",
        "tipo_destino",
        "sp_item_id",
        "sp_table_name",
        "activo",
        "updated_at",
    )
    list_filter = ("tipo_destino", "activo")
    search_fields = ("barrio", "descripcion", "sp_item_id")
    readonly_fields = ("created_at", "updated_at")

