from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from apps.ia_dev.services.runtime_governance_service import RuntimeGovernanceService


class Command(BaseCommand):
    help = "Resume auditoria del piloto productivo IA para trafico real."

    def add_arguments(self, parser):
        parser.add_argument("--domain", type=str, default="ausentismo")
        parser.add_argument("--days", type=int, default=7)
        parser.add_argument("--since-fix", action="store_true")
        parser.add_argument("--created-after", type=str, default="")
        parser.add_argument("--as-json", action="store_true")

    def handle(self, *args, **options):
        report = RuntimeGovernanceService().build_pilot_report(
            domain=str(options.get("domain") or "ausentismo").strip().lower(),
            days=int(options.get("days") or 7),
            since_fix=bool(options.get("since_fix")),
            created_after=str(options.get("created_after") or "").strip() or None,
        )
        if bool(options.get("as_json")):
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
            return

        self.stdout.write("IA runtime pilot report")
        self.stdout.write(
            "domain={domain} | days={days} | total_consultas_reales={total} | since_fix={since_fix} | created_after={created_after}".format(
                domain=report.get("domain"),
                days=report.get("days"),
                total=report.get("total_consultas_reales"),
                since_fix=str(bool(report.get("since_fix"))).lower(),
                created_after=report.get("created_after"),
            )
        )
        self.stdout.write(
            "sql_assisted_count={sql} | handler_count={handler} | runtime_only_fallback_count={runtime_only} | legacy_count={legacy} | blocked_legacy_count={blocked}".format(
                sql=report.get("sql_assisted_count"),
                handler=report.get("handler_count"),
                runtime_only=report.get("runtime_only_fallback_count"),
                legacy=report.get("legacy_count"),
                blocked=report.get("blocked_legacy_count"),
            )
        )
        self.stdout.write(
            "errores_sql={errors} | satisfaction_review_failed_count={satisfaction} | insight_poor_count={poor}".format(
                errors=report.get("errores_sql"),
                satisfaction=report.get("satisfaction_review_failed_count"),
                poor=report.get("insight_poor_count"),
            )
        )

        self.stdout.write("top_preguntas:")
        for item in list(report.get("top_preguntas") or []):
            self.stdout.write(f"  - {item.get('question')}: {item.get('count')}")
        self.stdout.write("top_fallos:")
        for item in list(report.get("top_fallos") or []):
            self.stdout.write(f"  - {item.get('failure')}: {item.get('count')}")
        self.stdout.write("compiladores_usados:")
        for item in list(report.get("compiladores_usados") or []):
            self.stdout.write(f"  - {item.get('compiler')}: {item.get('count')}")
        self.stdout.write("columnas_usadas:")
        for item in list(report.get("columnas_usadas") or []):
            self.stdout.write(f"  - {item.get('column')}: {item.get('count')}")
        self.stdout.write("relaciones_usadas:")
        for item in list(report.get("relaciones_usadas") or []):
            self.stdout.write(f"  - {item.get('relation')}: {item.get('count')}")
        self.stdout.write("insights_pobres:")
        poor_insights = list(report.get("insights_pobres") or [])
        if not poor_insights:
            self.stdout.write("  - ninguno")
        for item in poor_insights:
            self.stdout.write(
                "  - {question} | flow={flow} | fallback_reason={reason}".format(
                    question=item.get("question"),
                    flow=item.get("response_flow"),
                    reason=item.get("fallback_reason") or "-",
                )
            )
        self.stdout.write("recomendaciones_ai_dictionary:")
        for item in list(report.get("recomendaciones_ai_dictionary") or []):
            self.stdout.write(f"  - {item}")
