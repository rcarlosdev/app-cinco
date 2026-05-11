from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from apps.ia_dev.services.ai_dictionary_remediation_service import (
    AIDictionaryRemediationService,
)


class Command(BaseCommand):
    help = "Remedia ai_dictionary para dominios empresariales priorizados sin eliminar compatibilidad."

    def add_arguments(self, parser):
        parser.add_argument("--domain", type=str, default="ausentismo")
        parser.add_argument("--with-empleados", action="store_true")
        parser.add_argument("--as-json", action="store_true")

    def handle(self, *args, **options):
        summary = AIDictionaryRemediationService().remediate(
            domain=str(options.get("domain") or "ausentismo").strip().lower(),
            with_empleados=bool(options.get("with_empleados")),
        )
        if bool(options.get("as_json")):
            self.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2))
            return

        self.stdout.write("IA dictionary remediation")
        self.stdout.write("domains={domains}".format(domains=", ".join(list(summary.get("domains") or []))))
        for key in (
            "domains_upserted",
            "tables_upserted",
            "fields_upserted",
            "field_capabilities_upserted",
            "relations_upserted",
            "rules_upserted",
            "synonyms_upserted",
        ):
            self.stdout.write(f"{key}={int(summary.get(key) or 0)}")
        warnings = list(summary.get("warnings") or [])
        self.stdout.write(f"warnings={len(warnings)}")
        for item in warnings:
            self.stdout.write(f"  - {item}")
