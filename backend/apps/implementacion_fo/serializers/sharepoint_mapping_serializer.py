from rest_framework import serializers
from apps.implementacion_fo.models import SharePointMappingConfig


class SharePointMappingConfigSerializer(serializers.ModelSerializer):
    """
    Serializer para consultar y administrar la configuración de SharePoint por Barrio/Proyecto de Mapping.
    """

    class Meta:
        model = SharePointMappingConfig
        fields = [
            "id",
            "barrio",
            "descripcion",
            "tipo_destino",
            "sp_drive_id",
            "sp_item_id",
            "sp_table_name",
            "sp_list_id",
            "activo",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_barrio(self, value):
        return (value or "").strip().upper()
