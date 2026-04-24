import re
from apps.empleados.models import Empleado
from django.db.models import Count, Q, Value
from django.db.models.functions import Replace, Upper
from datetime import date

class EmpleadoService:
    ALLOWED_TEMPORAL_COLUMNS = {"fecha_ingreso", "fecha_egreso"}
    RESERVED_RUNTIME_PARAMS = {
        "estado",
        "search",
        "temporal_column_hint",
        "temporal_start_date",
        "temporal_end_date",
    }
    
    def existe(self, empleado_id):
        return Empleado.objects.filter(id=empleado_id, estado='ACTIVO').exists()
    
    # @staticmethod
    def obtener_basico(self, empleado_id):
        if not str(empleado_id).isdigit():
            return None
        
        empleado = (
            Empleado.objects
            .filter(id=empleado_id,estado='ACTIVO')
            .values('id', 'cedula', 'nombre', 'apellido', 'area', 'carpeta', 'cargo', 'movil', 'supervisor', 'estado', 'link_foto')
            .first()
        )
        
        return empleado

    @staticmethod
    def listar(query_params):
        queryset = EmpleadoService._build_base_queryset(estado=query_params.get('estado'))

        filtros_icontains = {
            'cedula': 'cedula',
            'nombre': 'nombre',
            'apellido': 'apellido',
            'area': 'area',
            'carpeta': 'carpeta',
            'cargo': 'cargo',
            'tipo_labor': 'tipo_labor',
            'movil': 'movil',
            'supervisor': 'supervisor',
            'sede': 'sede',
            'codigo_sap': 'codigo_sap',
        }

        for param, field in filtros_icontains.items():
            value = query_params.get(param)
            if value:
                if field == 'movil':
                    queryset = EmpleadoService._filter_by_movil_value(queryset=queryset, value=value)
                else:
                    queryset = queryset.filter(**{f'{field}__icontains': value})

        search = query_params.get('search')
        if search:
            search_filter = (
                Q(cedula__icontains=search) |
                Q(nombre__icontains=search) |
                Q(apellido__icontains=search) |
                Q(cargo__icontains=search) |
                Q(tipo_labor__icontains=search) |
                Q(movil__icontains=search)
            )
            if EmpleadoService._looks_like_movil_lookup(search):
                queryset = EmpleadoService._annotate_movil_normalized(queryset=queryset)
                search_filter |= Q(movil_normalized__icontains=EmpleadoService._normalize_movil_lookup(search))
            queryset = queryset.filter(search_filter)

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
        raw_group_fields = group_by_field if isinstance(group_by_field, (list, tuple, set)) else [group_by_field]
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
            "dias_periodo": int((end_date - start_date).days + 1),
            "total_egresos": int(egresos_periodo),
            "total_ingresos": int(ingresos_periodo),
            "planta_inicio": int(planta_inicio),
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

        raw_group_fields = group_by_field if isinstance(group_by_field, (list, tuple, set)) else [group_by_field]
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
            total_egresos = int(egresos.get(key) or 0)
            total_ingresos = int(ingresos.get(key) or 0)
            fin = int(planta_fin.get(key) or 0)
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
        rows.sort(key=lambda item: (-float(item.get("rotacion_porcentaje") or 0.0), -int(item.get("total_egresos") or 0), str(item)))
        return rows[:safe_limit]

    @staticmethod
    def eliminar(instance: Empleado, actor_user=None, hard_delete=False) -> bool:
        if hard_delete:
            if not actor_user or not actor_user.is_authenticated or not actor_user.is_superuser:
                return False
            instance.delete()
            return True

        if instance.estado != 'INACTIVO':
            instance.estado = 'INACTIVO'
            instance.save(update_fields=['estado'])
        return True

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
            return Empleado.objects.filter(estado__iexact=estado)
        return Empleado.objects.filter(estado='ACTIVO')

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

        return queryset

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
            Q(movil__icontains=raw_value)
            | Q(movil_normalized__icontains=normalized_value)
        )
    
