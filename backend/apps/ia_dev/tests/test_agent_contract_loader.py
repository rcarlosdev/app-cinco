from __future__ import annotations

import json
from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase

from apps.ia_dev.application.contracts.agent_contract_loader import AgentContractLoader
from apps.ia_dev.application.routing.capability_catalog import CapabilityCatalog


class AgentContractLoaderTests(SimpleTestCase):
    def test_agent_contracts_load_for_first_class_agents(self):
        loader = AgentContractLoader()

        contracts = loader.load_all()

        self.assertEqual(
            set(contracts.keys()),
            {
                "analista_agent",
                "knowledge_agent",
                "empleados_agent",
                "ausentismo_agent",
                "transport_agent",
                "inventario_logistica_agent",
            },
        )

    def test_all_declared_intents_have_declared_capabilities(self):
        loader = AgentContractLoader()

        for record in loader.load_all().values():
            capability_ids = {
                str(item.get("id") or "").strip()
                for item in list(record.payload.get("capabilities") or [])
                if isinstance(item, dict)
            }
            for intent in list(record.payload.get("intents") or []):
                capability_id = str((intent or {}).get("capability") or "").strip()
                self.assertTrue(capability_id)
                self.assertIn(capability_id, capability_ids)

    def test_capability_catalog_is_built_from_contracts(self):
        catalog = CapabilityCatalog(contract_loader=AgentContractLoader())

        self.assertIsNotNone(catalog.get("inventory_stock_balance_by_warehouse"))
        self.assertIsNotNone(catalog.get("knowledge.proposal.create.v1"))
        self.assertIsNotNone(catalog.get("general.answer.v1"))

    def test_agent_contract_audit_dry_run_lists_agents(self):
        out = StringIO()

        call_command("agent_contract_audit", "--dry-run", stdout=out)

        rendered = out.getvalue()
        self.assertIn("agent_contract_audit --dry-run", rendered)
        self.assertIn("inventario_logistica_agent", rendered)
        self.assertIn("analista_agent", rendered)

    def test_inventory_contract_disables_legacy_fallback(self):
        loader = AgentContractLoader()

        record = loader.get("inventario_logistica_agent")

        self.assertIsNotNone(record)
        self.assertFalse(bool(dict(record.payload.get("fallback_policy") or {}).get("legacy_allowed")))

    def test_agent_contract_audit_reports_policy_state_and_legacy_domains(self):
        out = StringIO()

        call_command("agent_contract_audit", "--dry-run", "--format", "json", stdout=out)

        payload = json.loads(out.getvalue())
        summary = dict(payload.get("summary") or {})
        self.assertIn("legacy_allowed_domains", summary)
        self.assertIn("covered_domains_with_reachable_legacy", summary)
        self.assertIn("response_policy_applied", summary)
        self.assertIn("memory_policy_applied", summary)
