import io
import csv
from decimal import Decimal
import openpyxl
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from apps.implementacion_fo.models import MappingPredio
from apps.implementacion_fo.serializers.mapping_predio_serializer import (
    clean_uppercase,
    normalizar_direccion_texto,
    parse_coordenada,
)


class MappingPredioService:
    """
    Capa de servicio y lógica de negocio para Mapping de Predios (Implementación FO).
    Encapsula consultas, validaciones, detección temprana de cuadras/planchas,
    búsquedas no bloqueantes e importación/exportación masiva.
    """

    @staticmethod
    def listar(filtros=None, actor_user=None):
        """Retorna queryset de predios activos con filtros aplicados."""
        filtros = filtros or {}
        qs = MappingPredio.objects.filter(is_deleted=False).select_related("created_by")

        barrio = filtros.get("barrio")
        if barrio:
            qs = qs.filter(barrio__icontains=barrio.strip())

        lote_amp = filtros.get("lote_amp")
        if lote_amp:
            qs = qs.filter(lote_amp__iexact=lote_amp.strip())

        nombre_calle = filtros.get("nombre_calle")
        if nombre_calle:
            qs = qs.filter(nombre_calle__icontains=normalizar_direccion_texto(nombre_calle))

        buscar = filtros.get("buscar")
        if buscar:
            termino = buscar.strip()
            qs = qs.filter(
                Q(nombre_calle__icontains=termino)
                | Q(placa_unidad__icontains=termino)
                | Q(nombre_conjunto__icontains=termino)
                | Q(barrio__icontains=termino)
                | Q(lote_amp__icontains=termino)
                | Q(distribucion__icontains=termino)
            )

        return qs.order_by("-id")

    @staticmethod
    @transaction.atomic
    def crear(actor_user, validated_data):
        """Crea un nuevo predio sin bloquear por duplicidad de dirección."""
        predio = MappingPredio(
            **validated_data,
            created_by=actor_user,
        )
        predio.save()

        def _sync_after_commit():
            try:
                from .sharepoint_mapping_service import SharePointMappingService
                SharePointMappingService.sync_predio_to_sharepoint(predio)
            except Exception:
                pass

        transaction.on_commit(_sync_after_commit)
        return predio

    @staticmethod
    @transaction.atomic
    def actualizar(instance, actor_user, validated_data):
        """Actualiza un predio existente."""
        for campo, valor in validated_data.items():
            setattr(instance, campo, valor)
        instance.updated_by = actor_user
        instance.save()
        return instance

    @staticmethod
    @transaction.atomic
    def eliminar(instance, actor_user):
        """Eliminado suave (soft-delete)."""
        instance.is_deleted = True
        instance.deleted_by = actor_user
        instance.deleted_at = timezone.now()
        instance.save(update_fields=["is_deleted", "deleted_by", "deleted_at"])
        return instance

    @staticmethod
    def verificar_cuadra(barrio, lote_amp, nombre_calle=None):
        """
        Alerta temprana de sector / cuadra / plancha:
        Permite saber al recolector si la manzana/cuadra donde se encuentra ya
        fue levantada por él u otro compañero previamente, evitando repetir trabajo.
        """
        if not barrio or not lote_amp:
            return {
                "tiene_registros": False,
                "total_predios": 0,
                "ultimo_registro_fecha": None,
                "ultimo_recolector": None,
                "mensaje": "Se requiere Barrio y Plancha (AMP) para verificar el sector.",
                "predios_recientes": [],
            }

        qs = MappingPredio.objects.filter(
            is_deleted=False,
            barrio__iexact=barrio.strip(),
            lote_amp__iexact=lote_amp.strip(),
        ).select_related("created_by")

        if nombre_calle:
            qs = qs.filter(nombre_calle__icontains=normalizar_direccion_texto(nombre_calle))

        total = qs.count()
        if total == 0:
            return {
                "tiene_registros": False,
                "total_predios": 0,
                "ultimo_registro_fecha": None,
                "ultimo_recolector": None,
                "mensaje": "Cuadra/Plancha libre. No se registran predios previos en este sector.",
                "predios_recientes": [],
            }

        ultimo = qs.order_by("-created_at").first()
        ultimo_recolector = None
        if ultimo and ultimo.created_by:
            first = getattr(ultimo.created_by, "first_name", "")
            last = getattr(ultimo.created_by, "last_name", "")
            ultimo_recolector = f"{first} {last}".strip() or ultimo.created_by.username

        recientes = list(qs.order_by("-id")[:5])

        mensaje = (
            f"⚠️ Esta cuadra/plancha ya tiene {total} predio(s) levantado(s). "
            f"Último registro el {ultimo.created_at.strftime('%d/%m/%Y %H:%M') if ultimo else ''} "
            f"por {ultimo_recolector or 'un usuario'}."
        )

        return {
            "tiene_registros": True,
            "total_predios": total,
            "ultimo_registro_fecha": ultimo.created_at if ultimo else None,
            "ultimo_recolector": ultimo_recolector,
            "mensaje": mensaje,
            "predios_recientes": recientes,
        }

    @staticmethod
    def verificar_direccion(nombre_calle, placa_unidad, interior=None, exclude_id=None):
        """
        Detección NO bloqueante de placa o dirección existente:
        Devuelve coincidencias para avisar al usuario, sin impedir el guardado.
        """
        if not nombre_calle or not placa_unidad:
            return {
                "existe_exacta": False,
                "total_coincidencias": 0,
                "coincidencias": [],
                "mensaje": None,
            }

        calle_limpia = normalizar_direccion_texto(nombre_calle)
        placa_limpia = normalizar_direccion_texto(placa_unidad)

        qs = MappingPredio.objects.filter(
            is_deleted=False,
            nombre_calle__iexact=calle_limpia,
            placa_unidad__iexact=placa_limpia,
        ).select_related("created_by")

        if exclude_id:
            qs = qs.exclude(id=exclude_id)

        coincidencias = list(qs[:10])
        total = len(coincidencias)

        mensaje = None
        if total > 0:
            primer_predio = coincidencias[0]
            desc = primer_predio.nombre_conjunto or primer_predio.barrio
            mensaje = (
                f"ℹ️ Ya existe(n) {total} predio(s) con la dirección {calle_limpia} #{placa_limpia} "
                f"({desc}). Puedes continuar guardando si es una nueva unidad o torre."
            )

        return {
            "existe_exacta": total > 0,
            "total_coincidencias": total,
            "coincidencias": coincidencias,
            "mensaje": mensaje,
        }

    @staticmethod
    def obtener_barrios_sugeridos(query=None):
        """Retorna lista única de barrios registrados para autocompletado."""
        qs = (
            MappingPredio.objects.filter(is_deleted=False)
            .exclude(barrio="")
            .values_list("barrio", flat=True)
            .distinct()
        )
        if query:
            qs = qs.filter(barrio__icontains=query.strip())
        return sorted(list(set(qs[:30])))

    @staticmethod
    def obtener_planchas_sugeridas(barrio=None, query=None):
        """Retorna lista única de planchas (AMP) registradas."""
        qs = (
            MappingPredio.objects.filter(is_deleted=False)
            .exclude(lote_amp="")
            .values_list("lote_amp", flat=True)
            .distinct()
        )
        if barrio:
            qs = qs.filter(barrio__iexact=barrio.strip())
        if query:
            qs = qs.filter(lote_amp__icontains=query.strip())
        return sorted(list(set(qs[:30])))

    @classmethod
    @transaction.atomic
    def importar_excel(cls, actor_user, archivo):
        return cls.importar_csv(actor_user, archivo)

    @classmethod
    @transaction.atomic
    def importar_csv(cls, actor_user, archivo):
        """
        Importa registros masivamente desde archivo CSV (.csv).
        Aplica la misma lógica estricta y robusta de Operaciones:
        - Valida que sea exclusivamente .csv
        - Decodifica utf-8-sig con fallback a latin-1
        - Detecta delimitador (, o ;) con muestra de los primeros 2048 bytes
        - Mapea dinámicamente las cabeceras de acuerdo a EXCEL_HEADER_MAPPING
        - Inserta masivamente con bulk_create
        """
        nombre_archivo = getattr(archivo, "name", "").lower()
        if not nombre_archivo.endswith(".csv"):
            raise ValueError("Solo se permiten archivos en formato CSV (.csv).")

        raw_bytes = archivo.read()
        try:
            contenido = raw_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            contenido = raw_bytes.decode("latin-1")

        if not contenido or not contenido.strip():
            raise ValueError("El archivo CSV está vacío.")

        sample = contenido[:2048]
        delimiter = ";" if ";" in sample and sample.count(";") > sample.count(",") else ","
        reader = csv.DictReader(io.StringIO(contenido), delimiter=delimiter)
        filas = list(reader)

        # Mapeo invertido y normalizado de cabeceras
        col_map = {
            k.upper().replace(" ", "").replace("_", ""): v
            for k, v in MappingPredio.EXCEL_HEADER_MAPPING.items()
        }

        predios_a_crear = []
        errores = []

        for idx, fila in enumerate(filas, start=2):
            datos_predio = {}
            for col_name, val in fila.items():
                if not col_name:
                    continue
                norm_col = str(col_name).strip().upper().replace(" ", "").replace("_", "")
                campo_modelo = col_map.get(norm_col)
                if campo_modelo:
                    datos_predio[campo_modelo] = val

            # Validar que al menos tenga calle o placa o conjunto
            nombre_calle = normalizar_direccion_texto(str(datos_predio.get("nombre_calle") or ""))
            placa_unidad = normalizar_direccion_texto(str(datos_predio.get("placa_unidad") or ""))
            conjunto = clean_uppercase(str(datos_predio.get("nombre_conjunto") or ""))

            if not (nombre_calle or placa_unidad or conjunto):
                errores.append(f"Fila {idx}: No contiene vía, placa ni nombre de conjunto.")
                continue

            def to_int(v, default=0):
                try:
                    return int(float(str(v).replace(",", ".").strip()))
                except (ValueError, TypeError):
                    return default

            predio = MappingPredio(
                nombre_conjunto=conjunto,
                nombre_calle=nombre_calle,
                placa_unidad=placa_unidad,
                barrio=clean_uppercase(str(datos_predio.get("barrio") or "")),
                interior=clean_uppercase(str(datos_predio.get("interior") or "")),
                num_casas=to_int(datos_predio.get("num_casas"), 0),
                num_apartamentos=to_int(datos_predio.get("num_apartamentos"), 0),
                num_locales=to_int(datos_predio.get("num_locales"), 0),
                num_pisos=max(1, to_int(datos_predio.get("num_pisos"), 1)),
                calle_alterna_2=normalizar_direccion_texto(str(datos_predio.get("calle_alterna_2") or "")),
                placa_alterna_2=normalizar_direccion_texto(str(datos_predio.get("placa_alterna_2") or "")),
                calle_alterna_3=normalizar_direccion_texto(str(datos_predio.get("calle_alterna_3") or "")),
                placa_alterna_3=normalizar_direccion_texto(str(datos_predio.get("placa_alterna_3") or "")),
                distribucion=clean_uppercase(str(datos_predio.get("distribucion") or "")),
                lote_amp=clean_uppercase(str(datos_predio.get("lote_amp") or "")),
                latitud=parse_coordenada(datos_predio.get("latitud")),
                longitud=parse_coordenada(datos_predio.get("longitud")),
                created_by=actor_user,
            )
            predios_a_crear.append(predio)

        if predios_a_crear:
            MappingPredio.objects.bulk_create(predios_a_crear, batch_size=200)

        return {
            "total_procesados": len(filas),
            "total_creados": len(predios_a_crear),
            "total_errores": len(errores),
            "errores": errores[:20],
        }

    @staticmethod
    def exportar_excel(filtros=None):
        """Genera un archivo Excel (.xlsx) con los predios filtrados."""
        qs = MappingPredioService.listar(filtros)

        wb = openpyxl.Workbook()
        ws = wb.active if wb.active is not None else wb.create_sheet(title="Mapping Predios FO")
        ws.title = "Mapping Predios FO"

        headers = [
            "ID",
            "NOMBRE CONJUNTO",
            "NOMBRECALL",
            "PLACAUNIDA",
            "NUM_CASAS",
            "APTOS",
            "LOCALES",
            "PISOS",
            "BARRIO",
            "INT",
            "NOMBRECALLANT2",
            "PLACAUNIDAANT2",
            "NOMBRECALLANT3",
            "PLACAUNIDAANT3",
            "DISTRIBUCION",
            "AMP",
            "CORDX",
            "CORDY",
            "TOTAL UNIDADES",
            "FECHA REGISTRO",
            "RECOLECTOR",
        ]
        ws.append(headers)

        for p in qs:
            recolector = ""
            if p.created_by:
                recolector = f"{p.created_by.first_name} {p.created_by.last_name}".strip() or p.created_by.username

            ws.append([
                p.id,
                p.nombre_conjunto,
                p.nombre_calle,
                p.placa_unidad,
                p.num_casas,
                p.num_apartamentos,
                p.num_locales,
                p.num_pisos,
                p.barrio,
                p.interior,
                p.calle_alterna_2,
                p.placa_alterna_2,
                p.calle_alterna_3,
                p.placa_alterna_3,
                p.distribucion,
                p.lote_amp,
                float(p.latitud) if p.latitud is not None else "",
                float(p.longitud) if p.longitud is not None else "",
                p.total_unidades,
                p.created_at.strftime("%Y-%m-%d %H:%M:%S") if p.created_at else "",
                recolector,
            ])

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return output
