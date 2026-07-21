import re
import uuid
from html import escape
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path

from apps.empleados.models import Empleado, EmpleadoSiigo
from django.db.models import Count, Q, Value
from django.db.models.functions import Replace, Upper
from django.utils import timezone

class EmpleadoService:
    BACKEND_DIR = Path(__file__).resolve().parents[3]
    SERVER_IMAGE_DIR = Path("/home/admcinco/public_html/images")
    LOCAL_IMAGE_DIR = BACKEND_DIR / "static" / "images"
    HEADER_FILENAME = "gghh_certificado_laboral_header.png"
    FOOTER_FILENAME = "gghh_certificado_laboral_footer.png"
    SELLO_FILENAME = "sello_cinco.png"
    FIRMA_FILENAME = "Firma-RRHH.png"
    ALLOWED_TEMPORAL_COLUMNS = {"fecha_ingreso", "fecha_egreso"}
    RESERVED_RUNTIME_PARAMS = {
        "estado",
        "search",
        "temporal_column_hint",
        "temporal_start_date",
        "temporal_end_date",
        "fnacimiento_month",
        "birth_month",
        "month_of_birth",
    }
    DOCUMENT_TYPES = {"CC", "PT", "TI", "CE"}

    def existe(self, empleado_id):
        return Empleado.objects.filter(id=empleado_id, estado="ACTIVO").exists()

    def obtener_basico(self, empleado_id):
        if not str(empleado_id).isdigit():
            return None

        empleado = (
            Empleado.objects.filter(id=empleado_id, estado="ACTIVO")
            .values(
                "id",
                "cedula",
                "nombre",
                "apellido",
                "area",
                "carpeta",
                "cargo",
                "movil",
                "supervisor",
                "estado",
                "link_foto",
            )
            .first()
        )

        return empleado

    @staticmethod
    def listar(query_params):
        queryset = EmpleadoService._build_base_queryset(estado=query_params.get("estado"))

        filtros_icontains = {
            "cedula": "cedula",
            "nombre": "nombre",
            "apellido": "apellido",
            "area": "area",
            "carpeta": "carpeta",
            "cargo": "cargo",
            "tipo_labor": "tipo_labor",
            "movil": "movil",
            "supervisor": "supervisor",
            "sede": "sede",
            "codigo_sap": "codigo_sap",
        }

        for param, field in filtros_icontains.items():
            value = query_params.get(param)
            if value:
                if field == "movil":
                    queryset = EmpleadoService._filter_by_movil_value(queryset=queryset, value=value)
                else:
                    queryset = queryset.filter(**{f"{field}__icontains": value})

        search = query_params.get("search")
        if search:
            search_filter = (
                Q(cedula__icontains=search)
                | Q(nombre__icontains=search)
                | Q(apellido__icontains=search)
                | Q(cargo__icontains=search)
                | Q(tipo_labor__icontains=search)
                | Q(movil__icontains=search)
            )
            if EmpleadoService._looks_like_movil_lookup(search):
                queryset = EmpleadoService._annotate_movil_normalized(queryset=queryset)
                search_filter |= Q(
                    movil_normalized__icontains=EmpleadoService._normalize_movil_lookup(search)
                )
            queryset = queryset.filter(search_filter)

        birth_month = EmpleadoService._parse_month_number(
            query_params.get("fnacimiento_month")
            or query_params.get("birth_month")
            or query_params.get("month_of_birth")
        )
        if birth_month:
            queryset = queryset.filter(fnacimiento__month=birth_month)

        temporal_column = str(query_params.get("temporal_column_hint") or "").strip().lower()
        start_date = EmpleadoService._parse_iso_date(query_params.get("temporal_start_date"))
        end_date = EmpleadoService._parse_iso_date(query_params.get("temporal_end_date"))
        if temporal_column in EmpleadoService.ALLOWED_TEMPORAL_COLUMNS and (start_date or end_date):
            if start_date:
                queryset = queryset.filter(**{f"{temporal_column}__gte": start_date})
            if end_date:
                queryset = queryset.filter(**{f"{temporal_column}__lte": end_date})

        return queryset

    @staticmethod
    def listar_runtime(query_params):
        queryset = EmpleadoService._build_base_queryset(estado=query_params.get("estado"))
        queryset = EmpleadoService._apply_runtime_filters(queryset=queryset, query_params=query_params)
        return queryset

    @staticmethod
    def contar_agrupado_runtime(*, query_params, group_by_field, limit=100):
        raw_group_fields = (
            group_by_field if isinstance(group_by_field, (list, tuple, set)) else [group_by_field]
        )
        group_fields = [
            EmpleadoService._resolve_model_field_name(item)
            for item in list(raw_group_fields or [])
            if str(item or "").strip()
        ]
        group_fields = [field for field in group_fields if field]
        if not group_fields:
            raise ValueError(f"campo_group_by_no_soportado:{group_by_field}")

        queryset = EmpleadoService.listar_runtime(query_params=query_params)
        safe_limit = max(1, min(int(limit), 500))
        return list(
            queryset.values(*group_fields)
            .annotate(total_empleados=Count("id"))
            .order_by("-total_empleados", *group_fields)[:safe_limit]
        )

    @staticmethod
    def calcular_rotacion_personal(*, query_params):
        start_date = EmpleadoService._parse_iso_date(query_params.get("temporal_start_date"))
        end_date = EmpleadoService._parse_iso_date(query_params.get("temporal_end_date"))
        if not start_date or not end_date:
            raise ValueError("periodo_requerido_para_rotacion")
        if start_date > end_date:
            start_date, end_date = end_date, start_date

        dimension_params = {
            key: value
            for key, value in dict(query_params or {}).items()
            if str(key or "").strip() not in EmpleadoService.RESERVED_RUNTIME_PARAMS
        }
        queryset = EmpleadoService._apply_runtime_filters(
            queryset=Empleado.objects.all(),
            query_params=dimension_params,
        )
        egresos_periodo = queryset.filter(
            estado__iexact="INACTIVO",
            fecha_egreso__gte=start_date,
            fecha_egreso__lte=end_date,
        ).count()
        ingresos_periodo = queryset.filter(
            fecha_ingreso__gte=start_date,
            fecha_ingreso__lte=end_date,
        ).count()
        planta_fin = queryset.filter(estado__iexact="ACTIVO").count()
        planta_inicio = max(int(planta_fin) - int(ingresos_periodo) + int(egresos_periodo), 0)
        planta_promedio = (float(planta_inicio) + float(planta_fin)) / 2.0
        rotacion_porcentaje = 0.0
        if planta_promedio > 0:
            rotacion_porcentaje = (float(egresos_periodo) / planta_promedio) * 100.0
        return {
            "fecha_inicio": start_date.isoformat(),
            "fecha_fin": end_date.isoformat(),
            "dias_periodo": (end_date - start_date).days + 1,
            "total_egresos": int(egresos_periodo),
            "total_ingresos": int(ingresos_periodo),
            "planta_inicio": planta_inicio,
            "planta_fin": int(planta_fin),
            "planta_promedio": round(planta_promedio, 2),
            "rotacion_porcentaje": round(rotacion_porcentaje, 2),
            "denominador_fuente": "estado_actual_mas_flujos_periodo",
        }

    @staticmethod
    def calcular_rotacion_personal_agrupada(*, query_params, group_by_field, limit=100):
        start_date = EmpleadoService._parse_iso_date(query_params.get("temporal_start_date"))
        end_date = EmpleadoService._parse_iso_date(query_params.get("temporal_end_date"))
        if not start_date or not end_date:
            raise ValueError("periodo_requerido_para_rotacion")
        if start_date > end_date:
            start_date, end_date = end_date, start_date

        raw_group_fields = (
            group_by_field if isinstance(group_by_field, (list, tuple, set)) else [group_by_field]
        )
        group_fields = [
            EmpleadoService._resolve_model_field_name(item)
            for item in list(raw_group_fields or [])
            if str(item or "").strip()
        ]
        group_fields = [field for field in group_fields if field]
        if not group_fields:
            raise ValueError(f"campo_group_by_no_soportado:{group_by_field}")

        dimension_params = {
            key: value
            for key, value in dict(query_params or {}).items()
            if str(key or "").strip() not in EmpleadoService.RESERVED_RUNTIME_PARAMS
        }
        queryset = EmpleadoService._apply_runtime_filters(
            queryset=Empleado.objects.all(),
            query_params=dimension_params,
        )

        def grouped_counts(qs):
            rows = qs.values(*group_fields).annotate(total=Count("id"))
            output: dict[tuple[str, ...], int] = {}
            for row in rows:
                key = tuple(str(row.get(field) or "").strip() or "SIN_DATO" for field in group_fields)
                output[key] = int(row.get("total") or 0)
            return output

        egresos = grouped_counts(
            queryset.filter(
                estado__iexact="INACTIVO",
                fecha_egreso__gte=start_date,
                fecha_egreso__lte=end_date,
            )
        )
        ingresos = grouped_counts(
            queryset.filter(
                fecha_ingreso__gte=start_date,
                fecha_ingreso__lte=end_date,
            )
        )
        planta_fin = grouped_counts(queryset.filter(estado__iexact="ACTIVO"))
        keys = set(egresos) | set(ingresos) | set(planta_fin)
        rows = []
        for key in keys:
            total_egresos = egresos.get(key) or 0
            total_ingresos = ingresos.get(key) or 0
            fin = planta_fin.get(key) or 0
            inicio = max(fin - total_ingresos + total_egresos, 0)
            promedio = (float(inicio) + float(fin)) / 2.0
            porcentaje = (float(total_egresos) / promedio) * 100.0 if promedio > 0 else 0.0
            rows.append(
                {
                    **{group_fields[idx]: key[idx] for idx in range(len(group_fields))},
                    "total_egresos": total_egresos,
                    "total_ingresos": total_ingresos,
                    "planta_inicio": inicio,
                    "planta_fin": fin,
                    "planta_promedio": round(promedio, 2),
                    "rotacion_porcentaje": round(porcentaje, 2),
                }
            )
        safe_limit = max(1, min(int(limit), 500))
        rows.sort(
            key=lambda item: (
                -float(item.get("rotacion_porcentaje") or 0.0),
                -int(item.get("total_egresos") or 0),
                str(item),
            )
        )
        return rows[:safe_limit]

    @staticmethod
    def eliminar(instance: Empleado, actor_user=None, hard_delete=False) -> bool:
        if hard_delete:
            if not actor_user or not actor_user.is_authenticated or not actor_user.is_superuser:
                return False
            instance.delete()
            return True

        if instance.estado != "INACTIVO":
            instance.estado = "INACTIVO"
            instance.save(update_fields=["estado"])
        return True

    @staticmethod
    def generar_certificado_laboral(*, empleado: Empleado, document_type="", manual_data=None):
        manual_data = manual_data or {}
        siigo = EmpleadoService._obtener_registro_siigo_por_cedula(empleado.cedula)
        siigo_data = EmpleadoService._normalize_siigo_data(getattr(siigo, "datos", None))
        
        contrato_raw = (
            manual_data.get("tipo_contrato")
            or (siigo_data.get("tipo_contrato") if siigo_data else None)
        )
        salario_raw = (
            manual_data.get("salario")
            if manual_data.get("salario") is not None and str(manual_data.get("salario")).strip() != ""
            else (getattr(siigo, "salario", None) if siigo else None)
        )
        
        if not siigo and not manual_data.get("salario") and not manual_data.get("tipo_contrato"):
            raise ValueError(
                "No se encontró información del empleado en SIIGO. "
                "Por favor ingrese los datos de contrato y salario manualmente para generar el certificado."
            )

        if not contrato_raw:
            raise ValueError(
                "No se encontró información sobre el tipo de contrato del empleado. "
                "Por favor ingrese el tipo de contrato manualmente."
            )
            
        if salario_raw is None or str(salario_raw).strip() == "":
            raise ValueError(
                "No se encontró información sobre el salario del empleado. "
                "Por favor ingrese el salario manualmente."
            )
            
        salario = EmpleadoService._parse_salary_value(salario_raw)
        if salario <= 0:
            raise ValueError(
                "El salario registrado para generar el certificado debe ser mayor a cero."
            )

        context = EmpleadoService.construir_contexto_certificado_laboral(
            empleado=empleado,
            document_type=document_type,
            manual_data=manual_data,
        )
        pdf_content = EmpleadoService._render_certificado_laboral_pdf(context=context)
        
        filename = f"certificado_laboral_{uuid.uuid4()}.pdf"
        
        return {
            "filename": filename,
            "content": pdf_content,
            "context": context,
        }

    @staticmethod
    def construir_contexto_certificado_laboral(*, empleado: Empleado, document_type="", manual_data=None):
        manual_data = manual_data or {}
        siigo = EmpleadoService._obtener_registro_siigo_por_cedula(empleado.cedula)
        siigo_data = EmpleadoService._normalize_siigo_data(getattr(siigo, "datos", None))
        fecha_expedicion = timezone.localdate()

        fecha_ingreso = (
            EmpleadoService._parse_datetime_value(manual_data.get("fecha_ingreso"))
            or getattr(empleado, "fecha_ingreso", None)
            or EmpleadoService._parse_datetime_value(siigo_data.get("f_ingreso"))
        )
        raw_fecha_egreso = manual_data.get("fecha_egreso") or getattr(empleado, "fecha_egreso", None)
        if isinstance(raw_fecha_egreso, (date, datetime)):
            fecha_egreso = raw_fecha_egreso
        elif isinstance(raw_fecha_egreso, str) and raw_fecha_egreso.strip():
            fecha_egreso = EmpleadoService._parse_datetime_value(raw_fecha_egreso)
        else:
            fecha_egreso = (
                EmpleadoService._parse_datetime_value(siigo_data.get("f_egreso"))
                or EmpleadoService._parse_datetime_value(siigo_data.get("fecha_egreso"))
                or EmpleadoService._parse_datetime_value(siigo_data.get("f_retiro"))
                or EmpleadoService._parse_datetime_value(siigo_data.get("fecha_retiro"))
            )

        manual_estado = manual_data.get("estado")
        raw_estado = manual_estado if isinstance(manual_estado, str) and manual_estado.strip() else getattr(empleado, "estado", None)
        if isinstance(raw_estado, str) and raw_estado.strip():
            estado = raw_estado.strip().upper()
        else:
            estado = str(siigo_data.get("estado") or "ACTIVO").strip().upper()

        is_activo = (estado != "INACTIVO") and not fecha_egreso

        raw_cargo = (
            manual_data.get("cargo")
            or siigo_data.get("cargo")
            or getattr(empleado, "cargo", "")
        )
        cargo = EmpleadoService._clean_cargo_value(raw_cargo)

        raw_contrato = (
            manual_data.get("tipo_contrato")
            or siigo_data.get("tipo_contrato")
            or "OBRA Y LABOR"
        )
        contrato = EmpleadoService._normalize_contract_value(raw_contrato)

        salario_raw = (
            manual_data.get("salario")
            if manual_data.get("salario") is not None and str(manual_data.get("salario")).strip() != ""
            else getattr(siigo, "salario", "")
        )
        salario = EmpleadoService._parse_salary_value(salario_raw)

        raw_genero = (
            manual_data.get("genero")
            or getattr(empleado, "genero", None)
            or siigo_data.get("genero")
            or siigo_data.get("sexo")
            or ""
        )
        genero_str = str(raw_genero).strip().upper()
        if genero_str.startswith("F") or genero_str in ("FEMENINO", "FEMALE", "MUJER", "SRA", "SEÑORA"):
            genero = "F"
        else:
            genero = "M"

        resolved_document_type = EmpleadoService._infer_document_type(
            empleado=empleado,
            requested_type=document_type,
        )
        return {
            "empleado_id": getattr(empleado, "id", None),
            "nombre_completo": EmpleadoService._resolve_full_name(empleado=empleado, siigo_data=siigo_data),
            "cedula": str(getattr(empleado, "cedula", "") or "").strip(),
            "genero": genero,
            "document_type": resolved_document_type,
            "document_type_label": resolved_document_type,
            "document_flags": {
                code: code == resolved_document_type for code in sorted(EmpleadoService.DOCUMENT_TYPES)
            },
            "estado": estado or "ACTIVO",
            "is_activo": is_activo,
            "cargo": cargo or "COLABORADOR",
            "salario": salario,
            "salario_texto": EmpleadoService._format_currency(salario),
            "fecha_ingreso": fecha_ingreso,
            "fecha_ingreso_texto": EmpleadoService._format_date(fecha_ingreso),
            "fecha_egreso": fecha_egreso,
            "fecha_egreso_texto": EmpleadoService._format_date(fecha_egreso),
            "fecha_expedicion": fecha_expedicion,
            "fecha_expedicion_texto": EmpleadoService._format_date(fecha_expedicion),
            "fecha_expedicion_texto_largo": EmpleadoService._format_date_long_es(fecha_expedicion),
            "contrato": contrato,
            "company_name": "Compañía Integral Negocios de Colombia",
            "company_nit": "811042087-2",
            "firmante_nombre": "FARAY MONSALVE URREGO",
            "firmante_cargo": "Dirección Gestión Humana",
        }

    @staticmethod
    def _obtener_registro_siigo_por_cedula(cedula):
        clean_cedula = str(cedula or "").strip()
        if not clean_cedula:
            return None
        return (
            EmpleadoSiigo.objects.using("azul")
            .filter(cedula=clean_cedula)
            .order_by("-fecha_edit")
            .first()
        )

    @staticmethod
    def _parse_iso_date(value) -> date | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            return date.fromisoformat(raw)
        except Exception:
            return None

    @staticmethod
    def _build_base_queryset(*, estado):
        if estado:
            if estado.lower() in ("all", "todos", "any"):
                return Empleado.objects.all()
            return Empleado.objects.filter(estado__iexact=estado)
        return Empleado.objects.filter(estado="ACTIVO")

    @staticmethod
    def _apply_runtime_filters(*, queryset, query_params):
        for raw_key, raw_value in dict(query_params or {}).items():
            key = str(raw_key or "").strip()
            if not key or key in EmpleadoService.RESERVED_RUNTIME_PARAMS:
                continue
            if raw_value in (None, ""):
                continue
            if key == "movil":
                queryset = EmpleadoService._filter_by_movil_value(queryset=queryset, value=raw_value)
                continue
            lookup = EmpleadoService._resolve_runtime_lookup(field_name=key)
            if not lookup:
                continue
            queryset = queryset.filter(**{lookup: raw_value})

        temporal_column = str(query_params.get("temporal_column_hint") or "").strip().lower()
        start_date = EmpleadoService._parse_iso_date(query_params.get("temporal_start_date"))
        end_date = EmpleadoService._parse_iso_date(query_params.get("temporal_end_date"))
        if temporal_column in EmpleadoService.ALLOWED_TEMPORAL_COLUMNS and (start_date or end_date):
            if start_date:
                queryset = queryset.filter(**{f"{temporal_column}__gte": start_date})
            if end_date:
                queryset = queryset.filter(**{f"{temporal_column}__lte": end_date})

        birth_month = EmpleadoService._parse_month_number(
            query_params.get("fnacimiento_month")
            or query_params.get("birth_month")
            or query_params.get("month_of_birth")
        )
        if birth_month:
            queryset = queryset.filter(fnacimiento__month=birth_month)

        return queryset

    @staticmethod
    def _parse_month_number(value) -> int | None:
        raw = str(value or "").strip().lower()
        if not raw:
            return None
        if raw.isdigit():
            month = int(raw)
            return month if 1 <= month <= 12 else None
        months = {
            "enero": 1,
            "febrero": 2,
            "marzo": 3,
            "abril": 4,
            "mayo": 5,
            "junio": 6,
            "julio": 7,
            "agosto": 8,
            "septiembre": 9,
            "setiembre": 9,
            "octubre": 10,
            "noviembre": 11,
            "diciembre": 12,
        }
        return months.get(raw)

    @staticmethod
    def _resolve_runtime_lookup(*, field_name):
        field = EmpleadoService._get_model_field(field_name=field_name)
        if field is None:
            return ""
        internal_type = str(field.get_internal_type() or "")
        if internal_type in {"CharField", "TextField", "EmailField", "SlugField"}:
            return f"{field.name}__icontains"
        return field.name

    @staticmethod
    def _resolve_model_field_name(group_by_field):
        field = EmpleadoService._get_model_field(field_name=group_by_field)
        return str(field.name or "") if field is not None else ""

    @staticmethod
    def _get_model_field(*, field_name):
        clean = str(field_name or "").strip()
        if not clean:
            return None
        try:
            return Empleado._meta.get_field(clean)
        except Exception:
            return None

    @staticmethod
    def _normalize_movil_lookup(value) -> str:
        normalized = re.sub(r"[\s_-]+", "", str(value or "").strip())
        return normalized.upper()

    @staticmethod
    def _looks_like_movil_lookup(value) -> bool:
        normalized = EmpleadoService._normalize_movil_lookup(value)
        if not normalized:
            return False
        if re.fullmatch(r"\d{3,5}", normalized):
            return True
        return bool(re.search(r"[A-Z]", normalized) and re.search(r"\d", normalized))

    @staticmethod
    def _annotate_movil_normalized(*, queryset):
        return queryset.annotate(
            movil_normalized=Upper(
                Replace(
                    Replace(
                        Replace("movil", Value(" "), Value("")),
                        Value("-"),
                        Value(""),
                    ),
                    Value("_"),
                    Value(""),
                )
            )
        )

    @staticmethod
    def _filter_by_movil_value(*, queryset, value):
        raw_value = str(value or "").strip()
        if not raw_value:
            return queryset
        if not EmpleadoService._looks_like_movil_lookup(raw_value):
            return queryset.filter(movil__icontains=raw_value)
        normalized_value = EmpleadoService._normalize_movil_lookup(raw_value)
        queryset = EmpleadoService._annotate_movil_normalized(queryset=queryset)
        return queryset.filter(
            Q(movil__icontains=raw_value) | Q(movil_normalized__icontains=normalized_value)
        )

    @staticmethod
    def _normalize_siigo_data(value):
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _parse_datetime_value(value):
        raw = str(value or "").strip()
        if not raw:
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(raw, fmt).date()
                if parsed.year < 1901:
                    return None
                return parsed
            except Exception:
                continue
        return None

    @staticmethod
    def _parse_salary_value(value):
        raw = str(value or "").strip()
        if not raw:
            return Decimal("0")
        normalized = raw.replace(",", "").replace("$", "").strip()
        try:
            return Decimal(normalized)
        except (InvalidOperation, ValueError):
            return Decimal("0")

    @staticmethod
    def _format_currency(value):
        try:
            amount = Decimal(value or 0)
        except (InvalidOperation, ValueError):
            amount = Decimal("0")
        quantized = amount.quantize(Decimal("0.01"))
        integer_part = f"{int(quantized):,}".replace(",", ".")
        if quantized == quantized.to_integral():
            return f"${integer_part}"
        decimals = str(quantized).split(".")[-1]
        return f"${integer_part},{decimals}"

    @staticmethod
    def _format_date(value):
        if not value:
            return ""
        return value.strftime("%d/%m/%Y")

    @staticmethod
    def _format_date_long_es(value):
        if not value:
            return ""
        months = {
            1: "ENERO",
            2: "FEBRERO",
            3: "MARZO",
            4: "ABRIL",
            5: "MAYO",
            6: "JUNIO",
            7: "JULIO",
            8: "AGOSTO",
            9: "SEPTIEMBRE",
            10: "OCTUBRE",
            11: "NOVIEMBRE",
            12: "DICIEMBRE",
        }
        month_name = months.get(value.month, "")
        return f"{value.day:02d} DE {month_name} DE {value.year}"

    @staticmethod
    def _clean_cargo_value(value):
        raw = EmpleadoService._normalize_text_value(value)
        if not raw:
            return ""
        if "-" in raw:
            left, right = raw.split("-", 1)
            if left.strip().isdigit() and right.strip():
                return right.strip()
        return raw

    @staticmethod
    def _resolve_full_name(*, empleado: Empleado, siigo_data):
        local_name = " ".join(
            EmpleadoService._normalize_text_value(part)
            for part in [getattr(empleado, "nombre", ""), getattr(empleado, "apellido", "")]
            if EmpleadoService._normalize_text_value(part)
        ).strip()
        siigo_name = EmpleadoService._normalize_text_value(siigo_data.get("nombre_empleado"))
        return local_name or siigo_name or EmpleadoService._normalize_text_value(getattr(empleado, "cedula", ""))

    @staticmethod
    def _normalize_text_value(value):
        raw = str(value or "").strip()
        if not raw:
            return ""
        replacements = {
            "├â┬í": "á",
            "├í": "á",
            "├â┬®": "é",
            "├®": "é",
            "├â┬¡": "í",
            "├¡": "í",
            "├â┬│": "ó",
            "├│": "ó",
            "├â┬║": "ú",
            "├║": "ú",
            "├â┬ü": "Á",
            "├ü": "Á",
            "├âÔÇ░": "É",
            "├ë": "É",
            "├â┬ì": "Í",
            "├ì": "Í",
            "├âÔÇ£": "Ó",
            "├ô": "Ó",
            "├â┼í": "Ú",
            "├Ü": "Ú",
            "├â┬▒": "ñ",
            "├▒": "ñ",
            "├âÔÇÿ": "Ñ",
            "├æ": "Ñ",
            "├ó┬Ç┬Ö": "'",
            "├ó┬Ç┬£": '"',
            "├ó┬Ç┬Ø": '"',
            "├é┬░": "°",
            "┬░": "°",
            "├é┬░": "°",
            "┬░": "°",
            "┬á": " ",
        }
        for source, target in replacements.items():
            raw = raw.replace(source, target)
        return re.sub(r"\s+", " ", raw).strip()

    @staticmethod
    def _normalize_contract_value(value):
        normalized = EmpleadoService._normalize_text_value(value)
        if not normalized:
            return "Obra y labor"
        lowered = normalized.lower().replace(".", "")
        canonical_map = {
            "t?rmino indefinido": "Término indefinido",
            "termino indefinido": "Término indefinido",
            "término indefinido": "Término indefinido",
            "t?rmino indefinido": "Término indefinido",
            "termino indefinido": "Término indefinido",
            "término indefinido": "Término indefinido",
            "obra y labor": "Obra y labor",
            "obra labor": "Obra y labor",
            "obra o labor": "Obra y labor",
            "fijo": "Término fijo",
            "termino fijo": "Término fijo",
            "término fijo": "Término fijo",
            "t?rmino fijo": "Término fijo",
            "fijo": "Término fijo",
            "termino fijo": "Término fijo",
            "término fijo": "Término fijo",
            "t?rmino fijo": "Término fijo",
        }
        return canonical_map.get(lowered, normalized)

    @staticmethod
    def _escape_pdf_text(value):
        return escape(EmpleadoService._normalize_text_value(value), quote=False)

    @staticmethod
    def _infer_document_type(*, empleado: Empleado, requested_type=""):
        normalized = str(requested_type or "").strip().upper()
        if normalized in EmpleadoService.DOCUMENT_TYPES:
            return normalized
        if str(getattr(empleado, "permiso", "") or "").strip():
            return "PT"
        pasaporte = str(getattr(empleado, "pasaporte", "") or "").strip()
        cedula = str(getattr(empleado, "cedula", "") or "").strip()
        if pasaporte and pasaporte != cedula:
            return "CE"
        return "CC"

    @staticmethod
    def _render_certificado_laboral_pdf(*, context):
        try:
            from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
            from reportlab.lib.units import cm
            from reportlab.lib.utils import ImageReader
            from reportlab.platypus import Flowable, Image as RLImage, Paragraph, SimpleDocTemplate, Spacer
        except ImportError as exc:
            raise RuntimeError("reportlab_no_instalado") from exc

        buffer = BytesIO()
        page_width, page_height = A4
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "CertTitle",
            parent=styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=15,
            alignment=TA_CENTER,
            spaceAfter=0.8 * cm,
        )
        body_style = ParagraphStyle(
            "CertBody",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=10,
            leading=16,
            alignment=TA_JUSTIFY,
            spaceAfter=0.45 * cm,
        )
        body_center_style = ParagraphStyle(
            "CertBodyCenter",
            parent=body_style,
            alignment=TA_LEFT,
        )
        signature_name_style = ParagraphStyle(
            "CertSignatureName",
            parent=styles["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=12,
            alignment=TA_LEFT,
            spaceAfter=0.1 * cm,
        )
        signature_role_style = ParagraphStyle(
            "CertSignatureRole",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=10,
            leading=12,
            alignment=TA_LEFT,
        )

        nombre_completo = EmpleadoService._escape_pdf_text(context["nombre_completo"])
        cedula = EmpleadoService._escape_pdf_text(context["cedula"])
        document_type_label = EmpleadoService._escape_pdf_text(
            context["document_type_label"]
        )
        company_name = EmpleadoService._escape_pdf_text(context["company_name"])
        cargo = EmpleadoService._escape_pdf_text(context["cargo"])
        salario_texto = EmpleadoService._escape_pdf_text(context["salario_texto"])
        contrato = EmpleadoService._escape_pdf_text(context["contrato"])
        fecha_ingreso_texto = EmpleadoService._escape_pdf_text(
            context["fecha_ingreso_texto"] or "sin registro"
        )
        fecha_expedicion_texto = EmpleadoService._escape_pdf_text(
            context["fecha_expedicion_texto"]
        )
        fecha_expedicion_texto_largo = EmpleadoService._escape_pdf_text(
            context.get("fecha_expedicion_texto_largo") or context["fecha_expedicion_texto"]
        )
        fecha_egreso_texto = EmpleadoService._escape_pdf_text(
            context.get("fecha_egreso_texto") or "sin registro"
        )
        firmante_nombre = EmpleadoService._escape_pdf_text(context["firmante_nombre"])
        firmante_cargo = EmpleadoService._escape_pdf_text(context["firmante_cargo"])

        is_activo = context.get("is_activo", True)
        genero = context.get("genero", "M")

        if genero == "F":
            prefijo_persona = "la señora"
            art_identificado = "identificada"
            art_interesado = "de la interesada"
        else:
            prefijo_persona = "el señor"
            art_identificado = "identificado"
            art_interesado = "del interesado"

        if is_activo:
            if contrato.strip().lower() in ("término indefinido", "término fijo"):
                contrato_phrase = f"y su contrato es a <b>{contrato}</b>."
            else:
                contrato_phrase = f"y su contrato es por <b>{contrato}</b>."

            intro = (
                f"Certifica que {prefijo_persona} <b>{nombre_completo}</b>, {art_identificado} con documento de "
                f"identificación <b>{document_type_label}</b> número <b>{cedula}</b>, ingresó a la "
                f"<b>COMPAÑÍA INTEGRAL NEGOCIOS DE COLOMBIA</b> desde el día "
                f"<b>{fecha_ingreso_texto}</b> y se desempeña como "
                f"<b>{cargo}</b>, con un salario básico de <b>{salario_texto}</b> "
                f"más auxilio de transporte {contrato_phrase}"
            )
            body = f"Esta certificación fue expedida a solicitud {art_interesado} el <b>{fecha_expedicion_texto}</b>."
        else:
            if contrato.strip().lower() in ("término indefinido", "término fijo"):
                contrato_phrase = f"y su contrato fue a <b>{contrato}</b>."
            else:
                contrato_phrase = f"y su contrato fue por <b>{contrato}</b>."

            intro = (
                f"Certifica que {prefijo_persona} <b>{nombre_completo}</b>, {art_identificado} con documento de "
                f"identificación <b>{document_type_label}</b> número <b>{cedula}</b>, ingresó a la "
                f"<b>COMPAÑÍA INTEGRAL NEGOCIOS DE COLOMBIA</b> desde el día "
                f"<b>{fecha_ingreso_texto}</b>, hasta el día <b>{fecha_egreso_texto}</b> "
                f"desempeñándose como <b>{cargo}</b>, con un salario básico de "
                f"<b>{salario_texto}</b> más auxilio de transporte {contrato_phrase}"
            )
            body = f"Esta certificación fue expedida a solicitud {art_interesado} a partir del <b>{fecha_expedicion_texto_largo}</b>."

        has_header_image = EmpleadoService._resolve_certificate_image_path(EmpleadoService.HEADER_FILENAME) is not None

        story: list[Flowable] = [
            Spacer(1, 1.2 * cm),
            Paragraph("EL DEPARTAMENTO DE RECURSOS HUMANOS", title_style),
            Spacer(1, 1.2 * cm),
            Paragraph(intro, body_style),
            Spacer(1, 0.9 * cm),
            Paragraph(body, body_style),
            Spacer(1, 3.2 * cm),
        ]

        firma_path = (
            EmpleadoService._resolve_certificate_image_path(EmpleadoService.FIRMA_FILENAME)
            or EmpleadoService._resolve_certificate_image_path("firma-rrhh.png")
            or EmpleadoService._resolve_certificate_image_path("firma_rrhh.png")
        )
        if firma_path:
            try:
                firma_img = RLImage(str(firma_path), width=4.5 * cm, height=2.2 * cm)
                firma_img.hAlign = "LEFT"
                story.append(firma_img)
                story.append(Spacer(1, -0.7 * cm))
            except Exception:
                story.append(Spacer(1, 1.8 * cm))
        else:
            story.append(Spacer(1, 1.8 * cm))

        story.extend([
            Paragraph(firmante_nombre, signature_name_style),
            Paragraph(firmante_cargo, signature_role_style),
        ])

        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=2 * cm,
            rightMargin=2 * cm,
            topMargin=4 * cm,
            bottomMargin=3.5 * cm,
            title=f"Certificado laboral {context['cedula']}",
        )
        doc.build(
            story,
            onFirstPage=lambda canvas, pdf_doc: EmpleadoService._draw_certificado_header_footer(
                canvas=canvas,
                doc=pdf_doc,
                page_width=page_width,
                page_height=page_height,
                cm_unit=cm,
                image_reader=ImageReader,
            ),
            onLaterPages=lambda canvas, pdf_doc: EmpleadoService._draw_certificado_header_footer(
                canvas=canvas,
                doc=pdf_doc,
                page_width=page_width,
                page_height=page_height,
                cm_unit=cm,
                image_reader=ImageReader,
            ),
        )
        return buffer.getvalue()

    @staticmethod
    def _draw_certificado_header_footer(*, canvas, doc, page_width, page_height, cm_unit, image_reader):
        header_path = EmpleadoService._resolve_certificate_image_path(EmpleadoService.HEADER_FILENAME)
        footer_path = EmpleadoService._resolve_certificate_image_path(EmpleadoService.FOOTER_FILENAME)
        sello_path = EmpleadoService._resolve_certificate_image_path(EmpleadoService.SELLO_FILENAME)

        if header_path:
            header = image_reader(str(header_path))
            header_w, header_h = header.getSize()
            header_draw_w = page_width
            header_draw_h = header_draw_w * header_h / header_w
            canvas.drawImage(
                header,
                x=0,
                y=page_height - header_draw_h,
                width=header_draw_w,
                height=header_draw_h,
                preserveAspectRatio=False,
                mask="auto",
            )

        if footer_path:
            footer = image_reader(str(footer_path))
            footer_w, footer_h = footer.getSize()
            footer_draw_w = page_width
            footer_draw_h = footer_draw_w * footer_h / footer_w
            canvas.drawImage(
                footer,
                x=0,
                y=0,
                width=footer_draw_w,
                height=footer_draw_h,
                preserveAspectRatio=False,
                mask="auto",
            )

        if sello_path:
            sello = image_reader(str(sello_path))
            sello_w, sello_h = sello.getSize()
            sello_draw_w = 6.8 * cm_unit
            sello_draw_h = sello_draw_w * sello_h / sello_w

            center_x = 11.5 * cm_unit
            center_y = 10.0 * cm_unit

            canvas.saveState()
            canvas.translate(center_x, center_y)
            canvas.rotate(30)
            canvas.drawImage(
                sello,
                x=-sello_draw_w / 2,
                y=-sello_draw_h / 2,
                width=sello_draw_w,
                height=sello_draw_h,
                preserveAspectRatio=True,
                mask="auto",
            )
            canvas.restoreState()

        canvas.setFont("Helvetica", 9)
        canvas.drawRightString(page_width - 1.5 * cm_unit, 1 * cm_unit, f"Página {doc.page}")

    @staticmethod
    def _resolve_certificate_image_path(filename, refresh_remote=False):
        # 1. Comprobar si existe en el directorio del servidor de producción
        server_path = EmpleadoService.SERVER_IMAGE_DIR / filename
        if server_path.exists():
            return server_path

        local_path = EmpleadoService.LOCAL_IMAGE_DIR / filename

        # 2. Si no existe localmente o se solicita actualizar, intentar descargar la versión remota
        if not local_path.exists() or refresh_remote:
            try:
                import urllib.request
                remote_url = f"https://www.cincosas.com/images/{filename}"
                EmpleadoService.LOCAL_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
                
                req = urllib.request.Request(
                    remote_url,
                    headers={"User-Agent": "Mozilla/5.0"}
                )
                with urllib.request.urlopen(req, timeout=5) as response:
                    if response.status == 200:
                        local_path.write_bytes(response.read())
                        return local_path
            except Exception:
                pass

        if local_path.exists():
            return local_path

        return None
