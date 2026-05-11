from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from apps.ia_dev.services.runtime_governance_service import RuntimeGovernanceService


class Command(BaseCommand):
    help = "Resume telemetria operativa del runtime analytics por dominio."

    def add_arguments(self, parser):
        parser.add_argument("--domain", type=str, default="ausentismo")
        parser.add_argument("--days", type=int, default=7)
        parser.add_argument("--as-json", action="store_true")

    def handle(self, *args, **options):
        summary = RuntimeGovernanceService().build_monitor_summary(
            domain=str(options.get("domain") or "ausentismo").strip().lower(),
            days=int(options.get("days") or 7),
        )
        if bool(options.get("as_json")):
            self.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2))
            return

        self.stdout.write("IA runtime monitor")
        self.stdout.write(
            "domain={domain} | days={days} | volumen_consultas={volumen}".format(
                domain=summary.get("domain"),
                days=summary.get("days"),
                volumen=summary.get("volumen_consultas"),
            )
        )
        self.stdout.write(
            "sql_assisted={sql} ({sql_pct}%) | handler={handler} ({handler_pct}%)".format(
                sql=summary.get("sql_assisted_count"),
                sql_pct=summary.get("sql_assisted_pct"),
                handler=summary.get("handler_count"),
                handler_pct=summary.get("handler_pct"),
            )
        )
        self.stdout.write(
            "runtime_only_fallbacks={runtime_only} | legacy_bloqueado={blocked} | unsafe_sql_plan={unsafe}".format(
                runtime_only=summary.get("runtime_only_fallback_count"),
                blocked=summary.get("blocked_legacy_fallback_count"),
                unsafe=summary.get("unsafe_sql_plan_count"),
            )
        )
        self.stdout.write(
            "no_metric_column_declared={metric} | no_allowed_dimension={dimension} | missing_relation={relation} | missing_column={column} | satisfaction_review_failed={satisfaction}".format(
                metric=summary.get("no_metric_column_declared_count"),
                dimension=summary.get("no_allowed_dimension_count"),
                relation=summary.get("missing_dictionary_relation_count"),
                column=summary.get("missing_dictionary_column_count"),
                satisfaction=summary.get("satisfaction_review_failed_count"),
            )
        )

        self.stdout.write("top_preguntas_fallidas:")
        for item in list(summary.get("top_preguntas_fallidas") or []):
            self.stdout.write(f"  - {item.get('question')}: {item.get('count')}")
        self.stdout.write("top_columnas_usadas:")
        for item in list(summary.get("top_columnas_usadas") or []):
            self.stdout.write(f"  - {item.get('column')}: {item.get('count')}")
        self.stdout.write("top_relaciones_usadas:")
        for item in list(summary.get("top_relaciones_usadas") or []):
            self.stdout.write(f"  - {item.get('relation')}: {item.get('count')}")
        self.stdout.write("recomendaciones_ai_dictionary:")
        for item in list(summary.get("recomendaciones") or []):
            self.stdout.write(f"  - {item}")

