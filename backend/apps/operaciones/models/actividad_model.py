from django.db import models
from django.utils import timezone


def normalize_ot_values(values):
    if values is None:
        return []

    if isinstance(values, str):
        raw_values = values.replace(",", "\n").split("\n")
    else:
        raw_values = values

    normalized = []
    seen = set()

    for value in raw_values:
        if value is None:
            continue
        text = str(value).strip()
        if not text or text in seen:
            continue
        normalized.append(text)
        seen.add(text)

    return normalized


class Actividad(models.Model):
    ESTADO_CHOICES = [
        ('pendiente', 'Pendiente'),
        ('en_progreso', 'En Progreso'),
        ('completada', 'Completada'),
        ('cancelada', 'Cancelada'),
        ('pausada', 'Pausada'),
        ('reprogramada', 'Reprogramada'),
    ]

    ot = models.CharField(max_length=100, blank=True, default="")
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='pendiente')

    responsable_id = models.IntegerField()

    fecha_inicio = models.DateField(blank=True, null=True)
    fecha_fin_estimado = models.DateField(blank=True, null=True)
    fecha_fin_real = models.DateField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.IntegerField(null=True, blank=True)
    
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.IntegerField(null=True, blank=True)

    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = 'operaciones_actividades'
        ordering = ['-id']

    @property
    def ots_list(self):
        relaciones = getattr(self, '_prefetched_objects_cache', {}).get('ot_relaciones')
        if relaciones is not None:
            return [rel.ot for rel in relaciones if rel.is_active]
        relaciones_activas = list(self.ot_relaciones.filter(is_active=True).values_list('ot', flat=True))
        if relaciones_activas:
            return relaciones_activas
        return normalize_ot_values(self.ot)


class ActividadOT(models.Model):
    actividad = models.ForeignKey(
        Actividad,
        on_delete=models.CASCADE,
        related_name='ot_relaciones'
    )
    ot = models.CharField(max_length=100, db_index=True)
    fecha_inicio = models.DateField(blank=True, null=True)
    fecha_fin = models.DateField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.IntegerField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = 'operaciones_actividad_ots'
        ordering = ['id']
        indexes = [
            models.Index(fields=['ot', 'is_active']),
        ]


class ActividadResponsableSnapshot(models.Model):
    actividad = models.OneToOneField(
        Actividad,
        on_delete=models.CASCADE,
        related_name='responsable_snapshot'
    )

    empleado_id = models.IntegerField()
    nombre = models.CharField(max_length=150)
    area = models.CharField(max_length=100)
    carpeta = models.CharField(max_length=100)
    cargo = models.CharField(max_length=100)
    movil = models.CharField(max_length=100)

    created_at = models.DateTimeField(auto_now_add=True)


class ActividadUbicacion(models.Model):
    actividad = models.OneToOneField(
        Actividad,
        on_delete=models.CASCADE,
        related_name='ubicacion'
    )

    direccion = models.CharField(max_length=255)
    coordenada_x = models.CharField(max_length=100)
    coordenada_y = models.CharField(max_length=100)
    zona = models.CharField(max_length=100)
    nodo = models.CharField(max_length=100)


class ActividadDetalle(models.Model):
    actividad = models.OneToOneField(
        Actividad,
        on_delete=models.CASCADE,
        related_name='detalle'
    )

    tipo_trabajo = models.CharField(max_length=100)
    descripcion = models.TextField()
    extra = models.JSONField(blank=True, null=True)
