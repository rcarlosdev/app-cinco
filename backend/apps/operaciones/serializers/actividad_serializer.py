from rest_framework import serializers
from apps.operaciones.models import (
    Actividad,
    ActividadDetalle,
    ActividadOT,
    ActividadUbicacion,
    normalize_ot_values,
)
from apps.empleados.services import EmpleadoService
from apps.operaciones.services.actividad_service import ActividadService


class ActividadDetalleSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActividadDetalle
        exclude = ('actividad',)


class ActividadUbicacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActividadUbicacion
        exclude = ('actividad',)


class ActividadOTSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActividadOT
        fields = (
            'id',
            'ot',
            'fecha_inicio',
            'fecha_fin',
            'is_active',
            'created_at',
            'created_by',
            'updated_at',
            'updated_by',
        )


class ActividadOTWriteSerializer(serializers.Serializer):
    ot = serializers.CharField(max_length=100)
    fecha_inicio = serializers.DateField(
        input_formats=["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"],
        required=True
    )
    fecha_fin = serializers.DateField(
        input_formats=["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"],
        required=True
    )


class ActividadWriteSerializer(serializers.ModelSerializer):
    detalle = ActividadDetalleSerializer()
    ubicacion = ActividadUbicacionSerializer()
    ots = ActividadOTWriteSerializer(many=True, required=True)
    ot = serializers.CharField(required=False, allow_blank=False, write_only=True)
    
    # fecha_inicio = serializers.DateTimeField(
    #      input_formats=[
    #         "%Y-%m-%d",
    #         "%Y-%m-%dT%H:%M:%S",
    #         "%Y-%m-%dT%H:%M",
    #     ]
    # )
    
    # fecha_fin_estimado = serializers.DateTimeField(
    #     input_formats=[
    #         "%Y-%m-%d",
    #         "%Y-%m-%dT%H:%M:%S",
    #         "%Y-%m-%dT%H:%M",
    #     ]
    # )

    fecha_fin_real = serializers.DateField(
        input_formats=[
            "",
            "%Y-%m-%d",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M",
        ],
        required=False,
        allow_null=True
    )

    class Meta:
        model = Actividad
        fields = (
            'ot',
            'ots',
            'estado',
            'responsable_id',
            'fecha_inicio',
            'fecha_fin_estimado',
            'fecha_fin_real',
            'detalle',
            'ubicacion'
        )

    def validate_responsable_id(self, value):
        if not EmpleadoService().existe(value):
            raise serializers.ValidationError("El empleado no existe.")
        return value

    def validate(self, attrs):
        ot = attrs.pop('ot', None)
        ots = attrs.get('ots')

        ot_codes = [item['ot'].strip() for item in ots if item.get('ot')] if ots else []
        
        normalized_ots = normalize_ot_values(ot_codes)
        if not normalized_ots:
            raise serializers.ValidationError(
                {"ots": "Debe registrar al menos una OT relacionada."}
            )

        try:
            ActividadService.validar_ots_unicas(
                normalized_ots,
                actividad_id=self.instance.id if self.instance else None,
            )
        except ValueError as exc:
            raise serializers.ValidationError({"ots": str(exc)}) from exc

        # Limpiar espacios de los códigos en attrs
        for item in ots:
            item['ot'] = item['ot'].strip()

        attrs['ots'] = ots
        return attrs

    def update(self, instance, validated_data):
        actor_user_id = self.context.get('actor_user_id')
        return ActividadService.actualizar(
            instance,
            validated_data,
            actor_user_id=actor_user_id,
        )

class ActividadSerializer(serializers.ModelSerializer):
    detalle = ActividadDetalleSerializer(read_only=True)
    ubicacion = ActividadUbicacionSerializer(read_only=True)
    responsable_snapshot = serializers.SerializerMethodField()
    ots = serializers.SerializerMethodField()
    ot_items = serializers.SerializerMethodField()

    class Meta:
        model = Actividad
        fields = "__all__"

    def get_responsable_snapshot(self, obj):
        if hasattr(obj, 'responsable_snapshot'):
            return {
                "nombre": obj.responsable_snapshot.nombre,
                "area": obj.responsable_snapshot.area,
                "carpeta": obj.responsable_snapshot.carpeta,
                "cargo": obj.responsable_snapshot.cargo,
                "movil": obj.responsable_snapshot.movil,
            }
        return None

    def get_ots(self, obj):
        return obj.ots_list

    def get_ot_items(self, obj):
        prefetched = getattr(obj, '_prefetched_objects_cache', {}).get('ot_relaciones')
        if prefetched is not None:
            relaciones = [relation for relation in prefetched if relation.is_active]
        else:
            relaciones = obj.ot_relaciones.filter(is_active=True)
        return ActividadOTSerializer(relaciones, many=True).data
