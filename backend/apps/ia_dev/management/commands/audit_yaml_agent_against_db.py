from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from apps.ia_dev.domains.inventario_logistica.inventory_dictionary_audit import (
    InventoryDictionaryAuditService,
)


class Command(BaseCommand):
    help = "Audita el YAML de un agente contra la DB fisica del dominio."

    def add_arguments(self, parser):
        parser.add_argument("--agent", type=str, default="inventario_logistica")
        parser.add_argument("--database", type=str, default="logistica_cinco")
        parser.add_argument("--yaml-path", type=str, default="")

    def handle(self, *args, **options):
        summary = InventoryDictionaryAuditService().audit(
            agent_code=str(options.get("agent") or "inventario_logistica").strip(),
            database_alias=str(options.get("database") or "logistica_cinco").strip(),
            yaml_path=str(options.get("yaml_path") or "").strip() or None,
        )
        self.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2))
