from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from apps.ia_dev.services.runtime_governance_service import RuntimeGovernanceService


class Command(BaseCommand):
    help = "Evalua salud del piloto productivo IA por dominio."

    def add_arguments(self, parser):
        parser.add_argument("--domain", type=str, default="ausentismo")
        parser.add_argument("--days", type=int, default=1)
        parser.add_argument("--since-fix", action="store_true")
        parser.add_argument("--created-after", type=str, default="")
        parser.add_argument("--as-json", action="store_true")

    def handle(self, *args, **options):
        health = RuntimeGovernanceService().build_pilot_health(
            domain=str(options.get("domain") or "ausentismo").strip().lower(),
            days=int(options.get("days") or 1),
            since_fix=bool(options.get("since_fix")),
            created_after=str(options.get("created_after") or "").strip() or None,
        )
        if bool(options.get("as_json")):
            self.stdout.write(json.dumps(health, ensure_ascii=False, indent=2))
            if str(health.get("status") or "") == "unhealthy":
                raise CommandError("pilot unhealthy")
            return

        self.stdout.write("IA runtime pilot health")
        self.stdout.write(
            "domain={domain} | days={days} | status={status}".format(
                domain=health.get("domain"),
                days=health.get("days"),
                status=health.get("status"),
            )
        )
        for key, value in dict(health.get("checks") or {}).items():
            self.stdout.write(f"{key}={value}")
        failing = list(health.get("failing_checks") or [])
        if not failing:
            self.stdout.write("failing_checks=none")
            return
        self.stdout.write("failing_checks:")
        for item in failing:
            self.stdout.write(f"  - {item}")
        raise CommandError("pilot unhealthy")
