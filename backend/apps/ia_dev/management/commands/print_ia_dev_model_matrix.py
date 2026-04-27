from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.ia_dev.infrastructure.ai.model_routing import model_matrix


class Command(BaseCommand):
    help = "Imprime la matriz efectiva de modelos OpenAI para IA Dev."

    def handle(self, *args, **options):
        rows = [resolution.as_dict() for resolution in model_matrix(log_selection=False)]
        headers = [
            "component",
            "role",
            "selected_model",
            "selected_source",
            "fallback_chain",
        ]
        widths = {
            header: max(
                len(header),
                *(len(str(row.get(header) or "")) for row in rows),
            )
            for header in headers
        }

        def _line(values: dict[str, str]) -> str:
            return " | ".join(
                str(values.get(header) or "").ljust(widths[header])
                for header in headers
            )

        self.stdout.write(_line({header: header for header in headers}))
        self.stdout.write(
            "-+-".join("-" * widths[header] for header in headers)
        )
        for row in rows:
            self.stdout.write(_line(row))
