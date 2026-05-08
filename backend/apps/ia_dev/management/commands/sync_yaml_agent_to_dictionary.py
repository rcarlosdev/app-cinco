from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from apps.ia_dev.domains.inventario_logistica.inventory_dictionary_sync import (
    InventoryDictionarySyncService,
)


class Command(BaseCommand):
    help = "Sincroniza un agente YAML-first a ai_dictionary en dry-run o apply."

    def add_arguments(self, parser):
        parser.add_argument("--agent", type=str, default="inventario_logistica")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--audit-only", action="store_true")
        parser.add_argument("--database", type=str, default="default")
        parser.add_argument("--yaml-path", type=str, default="")

    def handle(self, *args, **options):
        selected_modes = sum(
            1
            for key in ("dry_run", "apply", "audit_only")
            if bool(options.get(key))
        )
        if selected_modes > 1:
            raise CommandError("Usa solo uno entre --dry-run, --apply o --audit-only.")

        mode = "dry_run"
        if bool(options.get("apply")):
            mode = "apply"
        elif bool(options.get("audit_only")):
            mode = "audit_only"

        summary = InventoryDictionarySyncService().sync(
            agent_code=str(options.get("agent") or "inventario_logistica").strip(),
            mode=mode,
            yaml_path=str(options.get("yaml_path") or "").strip() or None,
            database_alias=str(options.get("database") or "default").strip(),
        )
        self.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2))
