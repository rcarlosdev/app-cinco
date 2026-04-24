from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from apps.ia_dev.TOOLS.business.ausentismo_business_tool import (
    AusentismoBusinessTool,
    PeriodoAusentismo,
)
from apps.ia_dev.application.delegation.task_contracts import DelegationResult, DelegationTask


@dataclass(slots=True)
class _PeriodoResolucion:
    inicio: date
    fin: date
    etiqueta: str


class AusentismoDelegacionHandler:
    def __init__(self, *, tool: AusentismoBusinessTool | None = None):
        self.tool = tool or AusentismoBusinessTool()

    def resolver_subtarea(
        self,
        *,
        task: DelegationTask,
        observability=None,
    ) -> DelegationResult:
        try:
            periodo = self._resolver_periodo(task=task)
            if task.task_type == "resumen_supervisor":
                return self.obtener_resumen_por_supervisor(task=task, periodo=periodo, observability=observability)
            if task.task_type == "tabla_supervisor":
                return self.obtener_tabla_por_supervisor(task=task, periodo=periodo, observability=observability)
            if task.task_type in {"tendencia_mensual", "tendencia_diaria"}:
                return self._obtener_tendencia(task=task, periodo=periodo, observability=observability)
            if task.task_type == "insights_basicos":
                return self._obtener_insights_basicos(task=task, periodo=periodo, observability=observability)
            return DelegationResult(
                task_id=task.task_id,
                domain_code=task.domain_code,
                status="error",
                error_code=f"unsupported_task_type:{task.task_type}",
            )
        except Exception as exc:
            return DelegationResult(
                task_id=task.task_id,
                domain_code=task.domain_code,
                status="error",
                error_code=f"ausentismo_handler_error:{exc}",
            )

    def obtener_resumen_por_supervisor(
        self,
        *,
        task: DelegationTask,
        periodo: _PeriodoResolucion,
        observability=None,
    ) -> DelegationResult:
        top_n = max(1, min(int(task.constraints.get("top_n") or 10), 50))
        chart_type = str(task.constraints.get("chart_type") or "bar")
        summary = self.tool.get_unjustified_aggregation(
            period=PeriodoAusentismo(start=periodo.inicio, end=periodo.fin, label=periodo.etiqueta, source="delegation"),
            group_by="supervisor",
            top_n=top_n,
            chart_type=chart_type,
        )
        self._record_event(
            observability=observability,
            task=task,
            event_type="delegation_ausentismo_summary_by_supervisor",
            meta={"top_n": top_n, "period_label": periodo.etiqueta},
        )
        return DelegationResult(
            task_id=task.task_id,
            domain_code=task.domain_code,
            status="ok",
            reply_text="Resumen de ausentismo por supervisor generado.",
            kpis={
                "total_injustificados": int(summary.get("total_injustificados") or 0),
                "total_grupos": int(summary.get("total_groups") or 0),
                "top_n": int(summary.get("top_n") or top_n),
            },
            table={
                "columns": list((summary.get("rows") or [{}])[0].keys()) if summary.get("rows") else [],
                "rows": list(summary.get("rows") or []),
                "rowcount": int(summary.get("rowcount") or 0),
            },
            labels=list(summary.get("labels") or []),
            series=list(summary.get("series") or []),
            chart=dict(summary.get("chart") or {}),
            insights=self.construir_insights_basicos(summary=summary),
            data_lineage={
                "tables_used": [self.tool.attendance_table, self.tool.personal_table],
                "filters_applied": {
                    "periodo_inicio": summary.get("periodo_inicio"),
                    "periodo_fin": summary.get("periodo_fin"),
                    "group_by": "supervisor",
                },
                "rowcount": int(summary.get("rowcount") or 0),
            },
        )

    def obtener_tabla_por_supervisor(
        self,
        *,
        task: DelegationTask,
        periodo: _PeriodoResolucion,
        observability=None,
    ) -> DelegationResult:
        summary = self.tool.get_unjustified_aggregation(
            period=PeriodoAusentismo(start=periodo.inicio, end=periodo.fin, label=periodo.etiqueta, source="delegation"),
            group_by="supervisor",
            top_n=max(1, min(int(task.constraints.get("top_n") or 20), 50)),
            chart_type=str(task.constraints.get("chart_type") or "bar"),
        )
        self._record_event(
            observability=observability,
            task=task,
            event_type="delegation_ausentismo_table_by_supervisor",
            meta={"period_label": periodo.etiqueta},
        )
        rows = list(summary.get("rows") or [])
        return DelegationResult(
            task_id=task.task_id,
            domain_code=task.domain_code,
            status="ok",
            reply_text="Tabla de ausentismo por supervisor generada.",
            table={
                "columns": list(rows[0].keys()) if rows else [],
                "rows": rows,
                "rowcount": len(rows),
            },
            insights=self.construir_insights_basicos(summary=summary),
        )

    def obtener_tendencia_mensual(
        self,
        *,
        task: DelegationTask,
        periodo: _PeriodoResolucion,
        observability=None,
    ) -> DelegationResult:
        return self._obtener_tendencia(task=task, periodo=periodo, observability=observability, granularity="monthly")

    def obtener_tendencia_diaria(
        self,
        *,
        task: DelegationTask,
        periodo: _PeriodoResolucion,
        observability=None,
    ) -> DelegationResult:
        return self._obtener_tendencia(task=task, periodo=periodo, observability=observability, granularity="daily")

    def construir_insights_basicos(self, *, summary: dict[str, Any]) -> list[str]:
        rows = list(summary.get("rows") or [])
        total = int(summary.get("total_injustificados") or 0)
        if not rows:
            return ["No se encontraron ausentismos injustificados para el periodo consultado."]

        top = rows[0]
        supervisor = str(top.get("supervisor") or "N/D")
        top_value = int(top.get("total_injustificados") or 0)
        top_ratio = float(top.get("porcentaje") or 0.0)
        insights = [
            (
                f"El supervisor con mayor ausentismo injustificado es {supervisor} "
                f"con {top_value} casos ({top_ratio:.2f}%)."
            ),
            f"Total de ausentismos injustificados analizados: {total}.",
            "Posibles causas iniciales: distribucion de cargas, turnos criticos o ausencias recurrentes no atendidas.",
        ]
        return insights

    def _obtener_tendencia(
        self,
        *,
        task: DelegationTask,
        periodo: _PeriodoResolucion,
        observability=None,
        granularity: str | None = None,
    ) -> DelegationResult:
        resolved = granularity or ("monthly" if task.task_type.endswith("mensual") else "daily")
        trend = self.tool.get_unjustified_trend(
            period=PeriodoAusentismo(start=periodo.inicio, end=periodo.fin, label=periodo.etiqueta, source="delegation"),
            granularity=resolved,
            chart_type=str(task.constraints.get("chart_type") or ("bar" if resolved == "monthly" else "line")),
        )
        self._record_event(
            observability=observability,
            task=task,
            event_type="delegation_ausentismo_trend",
            meta={"granularity": resolved, "period_label": periodo.etiqueta},
        )
        rows = list(trend.get("rows") or [])
        return DelegationResult(
            task_id=task.task_id,
            domain_code=task.domain_code,
            status="ok",
            reply_text="Tendencia de ausentismo generada.",
            kpis={
                "total_injustificados": int(trend.get("total_injustificados") or 0),
                "total_periodos": len(rows),
            },
            table={
                "columns": list(rows[0].keys()) if rows else [],
                "rows": rows,
                "rowcount": len(rows),
            },
            labels=list(trend.get("labels") or []),
            series=list(trend.get("series") or []),
            chart=dict(trend.get("chart") or {}),
            insights=[
                (
                    "La tendencia muestra variaciones temporales de ausentismo; "
                    "revisa picos para identificar causas operativas."
                )
            ],
        )

    def _obtener_insights_basicos(
        self,
        *,
        task: DelegationTask,
        periodo: _PeriodoResolucion,
        observability=None,
    ) -> DelegationResult:
        summary = self.tool.get_unjustified_aggregation(
            period=PeriodoAusentismo(start=periodo.inicio, end=periodo.fin, label=periodo.etiqueta, source="delegation"),
            group_by="supervisor",
            top_n=10,
            chart_type="bar",
        )
        self._record_event(
            observability=observability,
            task=task,
            event_type="delegation_ausentismo_insights",
            meta={"period_label": periodo.etiqueta},
        )
        return DelegationResult(
            task_id=task.task_id,
            domain_code=task.domain_code,
            status="ok",
            reply_text="Insights basicos de ausentismo generados.",
            insights=self.construir_insights_basicos(summary=summary),
        )

    @staticmethod
    def _resolver_periodo(*, task: DelegationTask) -> _PeriodoResolucion:
        start_text = str(task.entity_scope.period_start or "").strip()
        end_text = str(task.entity_scope.period_end or "").strip()
        start = date.fromisoformat(start_text) if start_text else date.today()
        end = date.fromisoformat(end_text) if end_text else start
        if end < start:
            start, end = end, start
        label = str(task.entity_scope.period_label or "periodo_consulta")
        return _PeriodoResolucion(inicio=start, fin=end, etiqueta=label)

    @staticmethod
    def _record_event(*, observability, task: DelegationTask, event_type: str, meta: dict[str, Any]) -> None:
        if observability is None or not hasattr(observability, "record_event"):
            return
        observability.record_event(
            event_type=event_type,
            source="AusentismoHandler",
            meta={
                "task_id": task.task_id,
                "domain_code": task.domain_code,
                "task_type": task.task_type,
                **dict(meta or {}),
            },
        )
