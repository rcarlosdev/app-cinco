from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from apps.ia_dev.application.runtime.functional_validation_suite import (
    run_functional_validation_suite,
)


class Command(BaseCommand):
    help = "Ejecuta la bateria funcional del runtime IA para ausentismo y empleados."

    def add_arguments(self, parser):
        parser.add_argument(
            "--domain",
            type=str,
            default="ausentismo",
            help="Dominio base a diagnosticar. Default: ausentismo.",
        )
        parser.add_argument(
            "--with-empleados",
            action="store_true",
            help="Incluye la validacion de preguntas del dominio empleados.",
        )
        parser.add_argument(
            "--as-json",
            action="store_true",
            help="Imprime el resumen completo en JSON.",
        )
        parser.add_argument(
            "--real-data",
            action="store_true",
            help="Ejecuta los casos SQL assisted contra la DB real en lugar de fixtures.",
        )

    def handle(self, *args, **options):
        summary = run_functional_validation_suite(
            domain=str(options.get("domain") or "ausentismo").strip().lower(),
            with_empleados=bool(options.get("with_empleados")),
            real_data=bool(options.get("real_data")),
        )
        if bool(options.get("as_json")):
            self.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2))
            return

        self.stdout.write("IA runtime diagnose")
        self.stdout.write(
            "domain={domain} | with_empleados={with_empleados} | questions={questions}".format(
                domain=summary.get("domain"),
                with_empleados=summary.get("with_empleados"),
                questions=summary.get("questions_executed"),
            )
        )
        self.stdout.write(f"real_data={bool(summary.get('real_data'))}")
        self.stdout.write(
            "passed={passed} | failed={failed} | fallback_count={fallback_count} | sql_assisted_count={sql} | handler_count={handler} | legacy_count={legacy}".format(
                passed=summary.get("passed"),
                failed=summary.get("failed"),
                fallback_count=summary.get("fallback_count"),
                sql=summary.get("sql_assisted_count"),
                handler=summary.get("handler_count"),
                legacy=summary.get("legacy_count"),
            )
        )

        no_insight = list(summary.get("questions_without_actionable_insight") or [])
        self.stdout.write(
            "preguntas_sin_insight_accionable={count}".format(
                count=len(no_insight),
            )
        )
        if no_insight:
            for item in no_insight:
                self.stdout.write(f"  - {item}")

        self.stdout.write("relaciones_usadas:")
        for relation in list(summary.get("relations_used") or []):
            self.stdout.write(f"  - {relation}")

        self.stdout.write("columnas_mas_usadas:")
        for item in list(summary.get("most_used_columns") or []):
            self.stdout.write(f"  - {item.get('column')}: {item.get('count')}")

        real_data_validation = dict(summary.get("real_data_validation") or {})
        self.stdout.write("validacion_datos_reales:")
        self.stdout.write(
            "  - queries_exitosas={ok} | queries_sin_datos={empty} | errores_sql={errors} | insights_accionables_generados={insights}".format(
                ok=real_data_validation.get("queries_exitosas"),
                empty=real_data_validation.get("queries_sin_datos"),
                errors=real_data_validation.get("errores_sql"),
                insights=real_data_validation.get("insights_accionables_generados"),
            )
        )
        for item in list(real_data_validation.get("columnas_nulas_criticas") or []):
            self.stdout.write(f"  - columna_nula_critica={item.get('column')} ({item.get('count')})")
        for item in list(real_data_validation.get("casos_tecnicamente_validos_pero_pobres") or []):
            self.stdout.write(f"  - caso_pobre={item}")

        self.stdout.write("detalle:")
        for item in list(summary.get("results") or []):
            self.stdout.write(
                "  - [{status}] {question} | flow={flow} | compiler={compiler} | fallback={fallback} | task_state={task_state}".format(
                    status=str(item.get("status") or "").upper(),
                    question=item.get("question"),
                    flow=item.get("runtime_flow"),
                    compiler=item.get("compiler_used") or "-",
                    fallback=item.get("fallback_reason") or "-",
                    task_state=item.get("task_state_final") or "-",
                )
            )
            failed_checks = list(item.get("failures") or [])
            if failed_checks:
                self.stdout.write(f"    failed_checks={', '.join(failed_checks)}")

        blockers = list(summary.get("errors_or_blockers") or [])
        self.stdout.write("errores_o_bloqueos:")
        if not blockers:
            self.stdout.write("  - ninguno")
            return
        for blocker in blockers:
            self.stdout.write(
                "  - {question} | fallback_reason={reason} | failed_checks={checks}".format(
                    question=blocker.get("question"),
                    reason=blocker.get("fallback_reason") or "-",
                    checks=", ".join(list(blocker.get("failed_checks") or [])) or "-",
                )
            )
