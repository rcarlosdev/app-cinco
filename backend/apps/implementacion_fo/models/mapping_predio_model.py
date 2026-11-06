from django.conf import settings
from django.db import models


class MappingPredio(models.Model):
    """
    Modelo para el levantamiento de información cartográfica y predial (Mapping)
    del área de Implementación de Fibra Óptica (Implementación FO).
    
    Tabla: implementacion_mapping_predios
    
    Diseñado para captura rápida en campo y oficina sin bloqueos por duplicidad.
    Permite registrar direcciones principales, alternativas, tipología de inmuebles,
    plancha/lote AMP y coordenadas geográficas.
    """

    # 1. Identificación y Ubicación Principal
    nombre_conjunto = models.CharField(
        max_length=150,
        blank=True,
        default="",
        help_text="Nombre de la unidad cerrada, edificio o conjunto (ej: EDIFICIO NUEVO MILENIUM)",
    )
    nombre_calle = models.CharField(
        max_length=100,
        blank=True,
        default="",
        db_index=True,
        help_text="Tipo y nombre de vía principal (ej: CL 21C, CRA 45)",
    )
    placa_unidad = models.CharField(
        max_length=50,
        blank=True,
        default="",
        db_index=True,
        help_text="Placa / número del predio (ej: 40A-15)",
    )
    barrio = models.CharField(
        max_length=100,
        blank=True,
        default="",
        db_index=True,
        help_text="Nombre del barrio, vereda o sector (ej: BELEN)",
    )
    interior = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Número o placa de interiores/torres/bloques (ej: 6)",
    )

    # 2. Conteo de Inmuebles y Capacidad
    num_casas = models.PositiveIntegerField(
        default=0,
        help_text="Número de casas en el predio",
    )
    num_apartamentos = models.PositiveIntegerField(
        default=0,
        help_text="Número de apartamentos en el predio",
    )
    num_locales = models.PositiveIntegerField(
        default=0,
        help_text="Número de locales comerciales en el predio",
    )
    num_pisos = models.PositiveIntegerField(
        default=1,
        help_text="Número de pisos/niveles del predio",
    )

    # 3. Direcciones Alternativas (Esquinas, accesos secundarios o placas anteriores)
    calle_alterna_2 = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Vía alternativa 2 (ej: CRA 22)",
    )
    placa_alterna_2 = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Placa alternativa 2 (ej: 30-15)",
    )
    calle_alterna_3 = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Vía alternativa 3",
    )
    placa_alterna_3 = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Placa alternativa 3",
    )

    # 4. Distribución Interna y Plancha Cartográfica
    distribucion = models.TextField(
        blank=True,
        default="",
        help_text="Distribución interna de los aptos o locales (ej: AP 101-102-103-201-202-203)",
    )
    lote_amp = models.CharField(
        max_length=50,
        blank=True,
        default="",
        db_index=True,
        help_text="Lote o manzana marcado en la plancha de levantamiento de información (ej: 1)",
    )

    # 5. Georreferenciación (GPS)
    latitud = models.DecimalField(
        max_digits=12,
        decimal_places=8,
        null=True,
        blank=True,
        help_text="Latitud geográfica / CORDX (ej: 6.308625)",
    )
    longitud = models.DecimalField(
        max_digits=12,
        decimal_places=8,
        null=True,
        blank=True,
        help_text="Longitud geográfica / CORDY (ej: -75.545410)",
    )

    # 6. Observaciones y Notas Adicionales
    observaciones = models.TextField(
        blank=True,
        default="",
        help_text="Notas u observaciones de campo",
    )

    # 7. Auditoría y Trazabilidad
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fo_mapping_predios_creados",
        db_column="created_by",
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fo_mapping_predios_actualizados",
        db_column="updated_by",
    )
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fo_mapping_predios_eliminados",
        db_column="deleted_by",
    )

    # 8. Sincronización con SharePoint / Excel
    sp_synced = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Indica si el registro ya fue sincronizado con el archivo de SharePoint",
    )
    sp_synced_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Fecha y hora de sincronización exitosa",
    )
    sp_sync_error = models.TextField(
        blank=True,
        default="",
        help_text="Mensaje de error en caso de fallo al sincronizar con SharePoint",
    )

    EXCEL_HEADER_MAPPING = {
        "NOMBRE CONJUNTO": "nombre_conjunto",
        "NOMBRECALL": "nombre_calle",
        "PLACAUNIDA": "placa_unidad",
        "NUM_CASAS": "num_casas",
        "APTOS": "num_apartamentos",
        "LOCALES": "num_locales",
        "PISOS": "num_pisos",
        "BARRIO": "barrio",
        "INT": "interior",
        "NOMBRECALLANT2": "calle_alterna_2",
        "PLACAUNIDAANT2": "placa_alterna_2",
        "NOMBRECALLANT3": "calle_alterna_3",
        "PLACAUNIDAANT3": "placa_alterna_3",
        "DISTRIBUCION": "distribucion",
        "AMP": "lote_amp",
        "CORDX": "latitud",
        "CORDY": "longitud",
    }

    class Meta:
        db_table = "implementacion_mapping_predios"
        ordering = ["-id"]
        verbose_name = "Mapping de Predio (Implementación FO)"
        verbose_name_plural = "Mapping de Predios (Implementación FO)"
        indexes = [
            models.Index(fields=["barrio", "lote_amp"], name="idx_fo_mp_barrio_amp"),
            models.Index(fields=["nombre_calle", "placa_unidad"], name="idx_fo_mp_calle_placa"),
            models.Index(fields=["is_deleted", "-id"], name="idx_fo_mp_deleted_id"),
            models.Index(fields=["sp_synced", "-id"], name="idx_fo_mp_sp_synced"),
        ]

    def __str__(self):
        direccion = f"{self.nombre_calle} #{self.placa_unidad}".strip()
        conjunto = f" ({self.nombre_conjunto})" if self.nombre_conjunto else ""
        return f"{direccion}{conjunto} - {self.barrio} [AMP: {self.lote_amp}]"

    @property
    def total_unidades(self) -> int:
        return (self.num_casas or 0) + (self.num_apartamentos or 0) + (self.num_locales or 0)

    @property
    def direccion_completa(self) -> str:
        partes = []
        if self.nombre_calle:
            partes.append(self.nombre_calle)
        if self.placa_unidad:
            partes.append(f"#{self.placa_unidad}")
        if self.interior:
            partes.append(f"Int. {self.interior}")
        return " ".join(partes)
