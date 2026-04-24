from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
import re
from typing import Any

from apps.ia_dev.services.organizational_context_service import OrganizationalContextService
from apps.ia_dev.services.tool_ausentismo_service import AusentismoToolService


@dataclass(frozen=True, slots=True)
class PeriodoAusentismo:
    start: date
    end: date
    label: str = "hoy"
    source: str = "rules"


class AusentismoBusinessTool:
    """
    Capa tipada de negocio para ausentismo.
    Encapsula AusentismoToolService y evita acceso SQL desde orchestration/routing.
    """

    def __init__(self, *, service: AusentismoToolService | None = None):
        self.service = service or AusentismoToolService()
        self.org_context = OrganizationalContextService()

    @property
    def attendance_table(self) -> str:
        return str(getattr(self.service, "table", "") or "")

    @property
    def attendance_table_source(self) -> str:
        return str(getattr(self.service, "table_source", "") or "env")

    @property
    def ausentismo_table(self) -> str:
        return self.attendance_table

    @property
    def ausentismo_table_source(self) -> str:
        return self.attendance_table_source

    @property
    def personal_table(self) -> str:
        return str(getattr(self.service, "personal_table", "") or "")

    @property
    def personal_table_source(self) -> str:
        return str(getattr(self.service, "personal_table_source", "") or "env")

    def get_unjustified_summary(
        self,
        *,
        period: PeriodoAusentismo,
        cedula: str | None = None,
    ) -> dict[str, Any]:
        return self.service.get_summary(period.start, period.end, cedula=cedula)

    def get_attendance_summary(
        self,
        *,
        period: PeriodoAusentismo,
        cedula: str | None = None,
        focus: str = "all",
        justificacion_filter: str | None = None,
    ) -> dict[str, Any]:
        return self.service.get_attendance_summary(
            period.start,
            period.end,
            cedula=cedula,
            focus=focus,
            justificacion_filter=justificacion_filter,
        )

    def get_unjustified_table(
        self,
        *,
        period: PeriodoAusentismo,
        include_personal: bool,
        personal_status: str = "all",
        limit: int = 150,
        cedula: str | None = None,
        extra_personal_columns: list[str] | None = None,
    ) -> dict[str, Any]:
        safe_limit = max(1, min(int(limit), 500))
        if include_personal:
            return self.service.get_unjustified_with_personal(
                period.start,
                period.end,
                limit=safe_limit,
                personal_status=personal_status,
                cedula=cedula,
                extra_personal_columns=extra_personal_columns,
            )
        return self.service.get_unjustified_table(
            period.start,
            period.end,
            limit=safe_limit,
            cedula=cedula,
        )

    def get_recurrence_grouped(
        self,
        *,
        period: PeriodoAusentismo,
        threshold: int = 3,
        personal_status: str = "all",
        limit: int = 150,
        personal_filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        safe_limit = max(1, min(int(limit), 500))
        safe_threshold = max(1, int(threshold))
        recurrence = self.service.get_recurrent_unjustified_with_supervisor(
            period.start,
            period.end,
            threshold=safe_threshold,
            limit=safe_limit,
            personal_status=personal_status,
        )
        if personal_filters:
            recurrence["rows"] = self._apply_personal_filters(
                rows=list(recurrence.get("rows") or []),
                personal_filters=personal_filters,
            )
            recurrence["rowcount"] = len(recurrence["rows"])
        return {
            **recurrence,
            "rows_grouped": self.shape_grouped_rows(recurrence.get("rows") or []),
        }

    def get_recurrence_itemized(
        self,
        *,
        period: PeriodoAusentismo,
        grouped_result: dict[str, Any] | None = None,
        personal_status: str = "all",
        detail_limit: int = 500,
        personal_filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        grouped = grouped_result or self.get_recurrence_grouped(
            period=period,
            threshold=3,
            personal_status=personal_status,
            limit=150,
            personal_filters=personal_filters,
        )
        grouped_rows = list(grouped.get("rows") or [])
        recurrent_ids = {
            self._normalize_identifier(row.get("cedula"))
            for row in grouped_rows
            if row.get("cedula")
        }
        if not recurrent_ids:
            return {
                "periodo_inicio": grouped.get("periodo_inicio"),
                "periodo_fin": grouped.get("periodo_fin"),
                "threshold": int(grouped.get("threshold") or 3),
                "rowcount": 0,
                "rows": [],
                "recurrent_count": int(grouped.get("rowcount") or 0),
            }

        detail = self.service.get_unjustified_with_personal(
            period.start,
            period.end,
            limit=max(1, min(int(detail_limit), 500)),
            personal_status=personal_status,
        )
        detail_rows = list(detail.get("rows") or [])
        itemized_rows: list[dict[str, Any]] = []
        for row in detail_rows:
            if self._normalize_identifier(row.get("cedula")) not in recurrent_ids:
                continue
            itemized_rows.append({k: v for k, v in row.items() if k != "personal_match"})
        if personal_filters:
            itemized_rows = self._apply_personal_filters(
                rows=itemized_rows,
                personal_filters=personal_filters,
            )

        return {
            "periodo_inicio": grouped.get("periodo_inicio"),
            "periodo_fin": grouped.get("periodo_fin"),
            "threshold": int(grouped.get("threshold") or 2),
            "rowcount": len(itemized_rows),
            "rows": itemized_rows,
            "recurrent_count": int(grouped.get("rowcount") or 0),
            "source_grouped": grouped,
        }

    def get_unjustified_aggregation(
        self,
        *,
        period: PeriodoAusentismo,
        group_by: str,
        personal_status: str = "all",
        top_n: int = 10,
        chart_type: str = "bar",
        cedula: str | None = None,
    ) -> dict[str, Any]:
        return self.get_attendance_aggregation(
            period=period,
            group_by=group_by,
            personal_status=personal_status,
            top_n=top_n,
            chart_type=chart_type,
            cedula=cedula,
            focus="unjustified",
        )

    def get_attendance_aggregation(
        self,
        *,
        period: PeriodoAusentismo,
        group_by: str,
        personal_status: str = "all",
        top_n: int = 10,
        chart_type: str = "bar",
        cedula: str | None = None,
        focus: str = "all",
        justificacion_filter: str | None = None,
        personal_filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        safe_top_n = max(1, min(int(top_n), 50))
        safe_focus = str(focus or "all").strip().lower()
        group_key, group_label = self._resolve_group_by(group_by)
        extra_personal_columns = [group_by]
        if group_key == "centro_costo":
            extra_personal_columns = ["area", "carpeta"]
        if safe_focus == "unjustified" and not str(justificacion_filter or "").strip():
            detail = self.get_unjustified_table(
                period=period,
                include_personal=True,
                personal_status=personal_status,
                limit=500,
                cedula=cedula,
                extra_personal_columns=extra_personal_columns,
            )
        else:
            detail = self.service.get_detail_with_personal(
                period.start,
                period.end,
                limit=500,
                personal_status=personal_status,
                cedula=cedula,
                extra_personal_columns=extra_personal_columns,
                justificacion_filter=justificacion_filter,
                focus=safe_focus,
            )
        source_rows = list(detail.get("rows") or [])
        source_rows = self._enrich_organizational_rows(rows=source_rows)
        if personal_filters:
            source_rows = self._apply_personal_filters(
                rows=source_rows,
                personal_filters=personal_filters,
            )
        metric_key = "total_injustificados" if safe_focus == "unjustified" else "total_ausentismos"

        grouped_counts: dict[str, int] = defaultdict(int)
        for row in source_rows:
            grouped_value = self._normalize_group_value(row.get(group_key))
            grouped_counts[grouped_value] += 1

        total_events = len(source_rows)
        aggregated_rows = [
            {
                group_key: key,
                metric_key: int(count),
                "porcentaje": round((count / total_events) * 100.0, 2) if total_events > 0 else 0.0,
            }
            for key, count in grouped_counts.items()
        ]
        aggregated_rows.sort(
            key=lambda item: (-int(item.get(metric_key) or 0), str(item.get(group_key) or ""))
        )
        top_rows = aggregated_rows[:safe_top_n]

        labels = [str(row.get(group_key) or "N/D") for row in top_rows]
        series = [int(row.get(metric_key) or 0) for row in top_rows]
        title = (
            f"Ausentismos injustificados por {group_label}"
            if safe_focus == "unjustified"
            else f"Ausentismos por {group_label}"
        )
        chart = self.build_chart_payload(
            rows=top_rows,
            x_key=group_key,
            y_key=metric_key,
            title=title,
            chart_type=chart_type,
        )

        return {
            "periodo_inicio": detail.get("periodo_inicio") or period.start.isoformat(),
            "periodo_fin": detail.get("periodo_fin") or period.end.isoformat(),
            "group_key": group_key,
            "group_label": group_label,
            "metric_key": metric_key,
            "focus": safe_focus,
            "top_n": safe_top_n,
            "rows": top_rows,
            "rowcount": len(top_rows),
            "total_groups": len(aggregated_rows),
            "total_injustificados": total_events if safe_focus == "unjustified" else 0,
            "total_ausentismos": total_events if safe_focus != "unjustified" else 0,
            "labels": labels,
            "series": series,
            "chart": chart,
            "source_rowcount": int(detail.get("rowcount") or 0),
            "source_truncated": bool(detail.get("truncated")),
            "personal_status_filter": detail.get("personal_status_filter") or personal_status,
            "justificacion_filter": detail.get("justificacion_filter") or str(justificacion_filter or "").strip().upper(),
        }

    def get_unjustified_trend(
        self,
        *,
        period: PeriodoAusentismo,
        granularity: str = "daily",
        personal_status: str = "all",
        chart_type: str | None = None,
        cedula: str | None = None,
    ) -> dict[str, Any]:
        safe_granularity = "monthly" if str(granularity or "").strip().lower() == "monthly" else "daily"
        include_personal = str(personal_status or "all").strip().lower() != "all"
        detail = self.get_unjustified_table(
            period=period,
            include_personal=include_personal,
            personal_status=personal_status,
            limit=500,
            cedula=cedula,
        )
        source_rows = list(detail.get("rows") or [])

        buckets: dict[str, int] = defaultdict(int)
        for row in source_rows:
            raw_date = str(row.get("fecha_ausentismo") or "").strip()
            if not raw_date:
                continue
            bucket = self._date_to_bucket(raw_date, safe_granularity)
            if not bucket:
                continue
            buckets[bucket] += 1

        labels = sorted(buckets.keys())
        trend_rows = [
            {
                "periodo": label,
                "total_injustificados": int(buckets[label]),
            }
            for label in labels
        ]
        series = [int(row.get("total_injustificados") or 0) for row in trend_rows]
        title = "Tendencia mensual de ausentismos injustificados" if safe_granularity == "monthly" else "Tendencia diaria de ausentismos injustificados"
        resolved_chart_type = chart_type or ("bar" if safe_granularity == "monthly" else "line")
        chart = self.build_chart_payload(
            rows=trend_rows,
            x_key="periodo",
            y_key="total_injustificados",
            title=title,
            chart_type=resolved_chart_type,
        )

        return {
            "periodo_inicio": detail.get("periodo_inicio") or period.start.isoformat(),
            "periodo_fin": detail.get("periodo_fin") or period.end.isoformat(),
            "granularity": safe_granularity,
            "rows": trend_rows,
            "rowcount": len(trend_rows),
            "labels": labels,
            "series": series,
            "total_injustificados": int(sum(series)),
            "chart": chart,
            "source_rowcount": int(detail.get("rowcount") or 0),
            "source_truncated": bool(detail.get("truncated")),
        }

    @staticmethod
    def build_chart_payload(
        *,
        rows: list[dict[str, Any]],
        x_key: str,
        y_key: str,
        title: str,
        chart_type: str = "bar",
    ) -> dict[str, Any]:
        safe_chart_type = str(chart_type or "bar").strip().lower()
        if safe_chart_type not in {"bar", "line", "area"}:
            safe_chart_type = "bar"

        labels = [str(item.get(x_key) or "") for item in rows]
        series = [int(item.get(y_key) or 0) for item in rows]
        return {
            "type": safe_chart_type,
            "title": title,
            "x_key": x_key,
            "y_key": y_key,
            "labels": labels,
            "series": series,
            "points": [{"x": labels[idx], "y": series[idx]} for idx in range(len(labels))],
        }

    @staticmethod
    def shape_grouped_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped_rows: list[dict[str, Any]] = []
        for row in rows:
            grouped_rows.append(
                {
                    "cedula": row.get("cedula", ""),
                    "empleado": row.get("empleado", ""),
                    "supervisor": row.get("supervisor", ""),
                    "cantidad_injustificados": row.get("cantidad_incidencias", 0),
                    "fechas_ausentismo": row.get("fechas", ""),
                }
            )
        return grouped_rows

    @staticmethod
    def _normalize_identifier(value: Any) -> str:
        raw = str(value or "").strip()
        digits = "".join(ch for ch in raw if ch.isdigit())
        return digits or raw.lower()

    @staticmethod
    def _normalize_group_value(value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return "N/D"
        text = re.sub(r"\s+", " ", text)
        return text

    @staticmethod
    def _resolve_group_by(group_by: str) -> tuple[str, str]:
        value = str(group_by or "").strip().lower()
        if value == "area":
            return "area", "Area"
        if value == "cargo":
            return "cargo", "Cargo"
        if value == "carpeta":
            return "carpeta", "Carpeta"
        if value in {"centro_costo", "centro costo", "centro de costo", "cc"}:
            return "centro_costo", "Centro de costo"
        if value in {"justificacion", "causa", "motivo"}:
            return "justificacion", "Justificacion"
        if value in {"tipo_labor", "tipo labor", "tipo de labor", "labor"}:
            return "tipo_labor", "Tipo Labor"
        if value in {"estado", "estado_justificacion", "tipo_ausentismo", "tipo de ausentismo", "tipo de ausencia"}:
            return "estado_justificacion", "Estado"
        if value in {"cedula", "empleado"}:
            return "cedula", "Empleado"
        if value == "supervisor":
            return "supervisor", "Supervisor"
        label = str(value or "supervisor").replace("_", " ").strip().title()
        return value or "supervisor", label or "Supervisor"

    def _enrich_organizational_rows(self, *, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        enriched = []
        for row in list(rows or []):
            payload = dict(row or {})
            if "centro_costo" not in payload:
                payload["centro_costo"] = self.org_context.cost_center_for(
                    area=payload.get("area"),
                    carpeta=payload.get("carpeta"),
                )
            enriched.append(payload)
        return enriched

    @staticmethod
    def _normalize_text(value: Any) -> str:
        import unicodedata

        lowered = str(value or "").strip().lower()
        normalized = unicodedata.normalize("NFKD", lowered)
        return "".join(ch for ch in normalized if not unicodedata.combining(ch))

    def _apply_personal_filters(
        self,
        *,
        rows: list[dict[str, Any]],
        personal_filters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        filters = {
            str(key or "").strip().lower(): str(value or "").strip()
            for key, value in dict(personal_filters or {}).items()
            if str(key or "").strip() and str(value or "").strip()
        }
        if not filters:
            return list(rows or [])
        output = []
        for row in self._enrich_organizational_rows(rows=list(rows or [])):
            keep = True
            for key, value in filters.items():
                if self._normalize_text(row.get(key)) != self._normalize_text(value):
                    keep = False
                    break
            if keep:
                output.append(row)
        return output

    @staticmethod
    def _date_to_bucket(raw_date: str, granularity: str) -> str | None:
        try:
            parsed = date.fromisoformat(str(raw_date).strip()[:10])
        except ValueError:
            return None
        if granularity == "monthly":
            return f"{parsed.year:04d}-{parsed.month:02d}"
        return parsed.isoformat()


AttendanceBusinessTool = AusentismoBusinessTool
AttendancePeriod = PeriodoAusentismo
