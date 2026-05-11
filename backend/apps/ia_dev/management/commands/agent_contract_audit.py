from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand

from apps.ia_dev.application.contracts.agent_contract_loader import AgentContractLoader
from apps.ia_dev.application.routing.capability_catalog import CapabilityCatalog


class Command(BaseCommand):
    help = "Audita contratos canonicos de agentes y su cobertura en el runtime."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", dest="dry_run")
        parser.add_argument("--format", type=str, default="table", choices=("table", "json"))

    def handle(self, *args, **options):
        loader = AgentContractLoader()
        catalog = CapabilityCatalog(contract_loader=loader)
        audit = self._build_audit(loader=loader, catalog=catalog)

        if str(options.get("format") or "table") == "json":
            self.stdout.write(json.dumps(audit, indent=2, ensure_ascii=False))
            return

        self.stdout.write("agent_contract_audit --dry-run")
        self.stdout.write("")
        headers = [
            "agente",
            "dominio",
            "intents sin capability",
            "capabilities sin handler/planner",
            "fallback permitido",
            "legacy reachable",
            "response_policy aplicada",
            "memory_policy aplicada",
            "frontend/simulador parity",
        ]
        self.stdout.write(" | ".join(headers))
        self.stdout.write("-" * 180)
        for row in audit["agents"]:
            self.stdout.write(
                " | ".join(
                    [
                        str(row.get("agent_id") or ""),
                        str(row.get("domain") or ""),
                        self._render_list(row.get("intents_without_capability") or []),
                        self._render_list(row.get("capabilities_without_handler_or_planner") or []),
                        "si" if bool(row.get("fallback_allowed")) else "no",
                        "si" if bool(row.get("legacy_reachable")) else "no",
                        "si" if bool(row.get("response_policy_applied")) else "no",
                        "si" if bool(row.get("memory_policy_applied")) else "no",
                        self._render_parity(row.get("frontend_simulator_parity") or {}),
                    ]
                )
            )
        self.stdout.write("")
        self.stdout.write("inconsistencias_detectadas:")
        for item in audit["summary"]["issues"]:
            self.stdout.write(f"- {item}")

    def _build_audit(
        self,
        *,
        loader: AgentContractLoader,
        catalog: CapabilityCatalog,
    ) -> dict[str, Any]:
        contracts = loader.load_all()
        parity = self._detect_frontend_simulator_parity()
        policy_state = self._detect_policy_state()
        catalog_ids = {item.capability_id for item in catalog.list_all()}
        agents: list[dict[str, Any]] = []
        issues: list[str] = []
        legacy_allowed_domains: list[str] = []
        covered_domains_with_reachable_legacy: list[str] = []

        for record in contracts.values():
            payload = dict(record.payload or {})
            capabilities = {
                str(item.get("id") or "").strip(): dict(item)
                for item in list(payload.get("capabilities") or [])
                if isinstance(item, dict) and str(item.get("id") or "").strip()
            }
            intents_without_capability: list[str] = []
            for intent in list(payload.get("intents") or []):
                if not isinstance(intent, dict):
                    continue
                intent_id = str(intent.get("id") or "").strip()
                capability_id = str(intent.get("capability") or "").strip()
                if not intent_id:
                    continue
                if not capability_id or capability_id not in capabilities:
                    intents_without_capability.append(intent_id)

            missing_exec: list[str] = []
            for capability_id, capability in capabilities.items():
                if capability_id not in catalog_ids:
                    missing_exec.append(capability_id)
                    continue
                has_handler = self._has_runtime_handler(capability_id=capability_id, capability=capability)
                has_planner = self._has_runtime_planner(capability_id=capability_id, capability=capability)
                if bool(capability.get("handler_required")) and not has_handler:
                    missing_exec.append(capability_id)
                    continue
                if bool(capability.get("planner_required")) and not has_planner:
                    missing_exec.append(capability_id)

            fallback_allowed = bool(dict(payload.get("fallback_policy") or {}).get("legacy_allowed"))
            covered_by_modern_runtime = bool(dict(payload.get("execution_rules") or {}).get("covered_by_modern_runtime"))
            legacy_reachable = bool(fallback_allowed or not covered_by_modern_runtime)
            response_policy_missing = "response_policy" not in payload or not payload.get("response_policy")
            memory_policy_missing = "memory_policy" not in payload or not payload.get("memory_policy")
            if fallback_allowed:
                legacy_allowed_domains.append(record.domain)
            if covered_by_modern_runtime and legacy_reachable:
                covered_domains_with_reachable_legacy.append(record.domain)

            if intents_without_capability:
                issues.append(
                    f"{record.agent_id}: intents sin capability -> {', '.join(intents_without_capability)}"
                )
            if missing_exec:
                issues.append(
                    f"{record.agent_id}: capabilities sin handler/planner -> {', '.join(missing_exec)}"
                )
            if response_policy_missing:
                issues.append(f"{record.agent_id}: response_policy ausente")
            if memory_policy_missing:
                issues.append(f"{record.agent_id}: memory_policy ausente")
            if covered_by_modern_runtime and legacy_reachable:
                issues.append(f"{record.agent_id}: legacy reachable en dominio cubierto")

            agents.append(
                {
                    "agent_id": record.agent_id,
                    "domain": record.domain,
                    "intents_without_capability": intents_without_capability,
                    "capabilities_without_handler_or_planner": sorted(dict.fromkeys(missing_exec)),
                    "fallback_allowed": fallback_allowed,
                    "legacy_reachable": legacy_reachable,
                    "response_policy_missing": response_policy_missing,
                    "memory_policy_missing": memory_policy_missing,
                    "response_policy_applied": bool(policy_state.get("response_policy_applied")),
                    "memory_policy_applied": bool(policy_state.get("memory_policy_applied")),
                    "frontend_simulator_parity": dict(parity),
                }
            )

        if not policy_state.get("response_policy_applied"):
            issues.append("response_policy no aplicada en ChatApplicationService")
        if not policy_state.get("memory_policy_applied"):
            issues.append("memory_policy no aplicada en ChatApplicationService")
        if not parity.get("ok"):
            issues.append(f"simulator/frontend drift: {str(parity.get('reason') or 'unknown')}")
        return {
            "agents": agents,
            "summary": {
                "contracts_loaded": len(contracts),
                "issues": issues,
                "legacy_allowed_domains": sorted(dict.fromkeys(legacy_allowed_domains)),
                "covered_domains_with_reachable_legacy": sorted(dict.fromkeys(covered_domains_with_reachable_legacy)),
                "response_policy_applied": bool(policy_state.get("response_policy_applied")),
                "memory_policy_applied": bool(policy_state.get("memory_policy_applied")),
                "frontend_simulator_parity": parity,
            },
        }

    @staticmethod
    def _render_list(values: list[str]) -> str:
        if not values:
            return "-"
        return ", ".join(values)

    @staticmethod
    def _render_parity(payload: dict[str, Any]) -> str:
        status = "ok" if bool(payload.get("ok")) else "drift"
        reason = str(payload.get("reason") or "").strip()
        return status if not reason else f"{status}:{reason}"

    @staticmethod
    def _has_runtime_handler(*, capability_id: str, capability: dict[str, Any]) -> bool:
        if not bool(capability.get("handler_required")):
            return False
        normalized = str(capability_id or "").strip().lower()
        return normalized.startswith(("attendance.", "empleados.", "transport."))

    @staticmethod
    def _has_runtime_planner(*, capability_id: str, capability: dict[str, Any]) -> bool:
        if not bool(capability.get("planner_required")):
            return False
        normalized = str(capability_id or "").strip().lower()
        capability_type = str(capability.get("type") or "").strip().lower()
        if capability_type == "sql_assisted":
            return True
        return normalized.startswith(("attendance.", "empleados.", "inventory_"))

    @classmethod
    def _detect_frontend_simulator_parity(cls) -> dict[str, Any]:
        repo_root = Path(__file__).resolve().parents[5]
        simulator_path = repo_root / "backend" / "apps" / "ia_dev" / "management" / "commands" / "simulate_ia_dev_chat.py"
        contracts_path = repo_root / "backend" / "apps" / "ia_dev" / "application" / "contracts" / "chat_contracts.py"
        frontend_hook_path = repo_root / "frontend" / "src" / "modules" / "programacion" / "ia-dev" / "chat" / "hooks" / "useIADevChatTransport.ts"
        frontend_normalize_path = repo_root / "frontend" / "src" / "modules" / "programacion" / "ia-dev" / "chat" / "utils" / "normalizeChatPayload.ts"
        frontend_service_path = repo_root / "frontend" / "src" / "services" / "ia-dev.service.ts"

        simulator_text = simulator_path.read_text(encoding="utf-8", errors="ignore") if simulator_path.exists() else ""
        contracts_text = contracts_path.read_text(encoding="utf-8", errors="ignore") if contracts_path.exists() else ""
        hook_text = frontend_hook_path.read_text(encoding="utf-8", errors="ignore") if frontend_hook_path.exists() else ""
        normalize_text = frontend_normalize_path.read_text(encoding="utf-8", errors="ignore") if frontend_normalize_path.exists() else ""
        service_text = frontend_service_path.read_text(encoding="utf-8", errors="ignore") if frontend_service_path.exists() else ""

        has_service_mode = 'help="service:' in simulator_text or "ChatApplicationService directo" in simulator_text
        has_pending_progress = "buildPendingProgressFrames" in hook_text
        synthetic_progress_tagged = 'progress_source: "synthetic"' in hook_text
        backend_progress_tagged = 'progress_source: "backend"' in hook_text
        uses_http_contract = "/ia-dev/chat/" in service_text
        has_shared_envelope = "response_envelope" in contracts_text and "response_envelope" in service_text and "response_envelope" in normalize_text
        preserves_contract_fields = all(
            token in normalize_text
            for token in (
                "fallback_used",
                "legacy_used",
                "contract_policy_applied",
                "needs_clarification",
                "block_reason",
                "route",
            )
        )
        ok = uses_http_contract and has_service_mode and has_pending_progress and has_shared_envelope and preserves_contract_fields and synthetic_progress_tagged and backend_progress_tagged
        reason = ""
        if not has_shared_envelope:
            reason = "response_envelope_no_compartido"
        elif not preserves_contract_fields:
            reason = "normalize_chat_payload_no_preserva_flags_de_contrato"
        elif not synthetic_progress_tagged or not backend_progress_tagged:
            reason = "frontend_no_distingue_progreso_sintetico_vs_backend"
        elif not has_pending_progress:
            reason = "frontend_no_tiene_progreso_sintetico_controlado"
        elif not has_service_mode:
            reason = "simulador_no_tiene_modo_service"
        return {
            "ok": ok,
            "reason": reason,
            "uses_http_contract": uses_http_contract,
            "simulator_has_service_mode": has_service_mode,
            "frontend_has_synthetic_progress": has_pending_progress,
            "shared_response_envelope": has_shared_envelope,
            "normalize_preserves_contract_fields": preserves_contract_fields,
        }

    @classmethod
    def _detect_policy_state(cls) -> dict[str, Any]:
        repo_root = Path(__file__).resolve().parents[5]
        service_path = repo_root / "backend" / "apps" / "ia_dev" / "application" / "orchestration" / "chat_application_service.py"
        service_text = service_path.read_text(encoding="utf-8", errors="ignore") if service_path.exists() else ""
        return {
            "response_policy_applied": "_apply_response_policy(" in service_text,
            "memory_policy_applied": "_apply_memory_policy(" in service_text,
        }
