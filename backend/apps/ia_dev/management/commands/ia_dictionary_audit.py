from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from apps.ia_dev.services.runtime_governance_service import RuntimeGovernanceService


class Command(BaseCommand):
    help = "Audita consistencia entre diagnostico funcional, YAML y ai_dictionary."

    def add_arguments(self, parser):
        parser.add_argument("--domain", type=str, default="ausentismo")
        parser.add_argument("--with-empleados", action="store_true")
        parser.add_argument("--as-json", action="store_true")

    def handle(self, *args, **options):
        summary = RuntimeGovernanceService().audit_dictionary(
            domain=str(options.get("domain") or "ausentismo").strip().lower(),
            with_empleados=bool(options.get("with_empleados")),
        )
        if bool(options.get("as_json")):
            self.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2))
            return

        self.stdout.write("IA dictionary audit")
        self.stdout.write(
            "domains={domains}".format(domains=", ".join(list(summary.get("domains") or [])))
        )
        for key in (
            "missing_columns",
            "missing_metrics",
            "missing_relations",
            "missing_synonyms",
            "missing_rules",
            "duplicated_definitions",
            "yaml_structural_leaks",
            "yaml_fields_ignored",
            "yaml_fields_removed",
            "missing_dictionary_metadata",
        ):
            values = list(summary.get(key) or [])
            self.stdout.write(f"{key}={len(values)}")
            for item in values:
                self.stdout.write(f"  - {item}")
