from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True, slots=True)
class AgentContractRecord:
    agent_id: str
    domain: str
    payload: dict[str, Any]


class AgentContractLoader:
    REQUIRED_TOP_LEVEL_FIELDS = (
        "agent_id",
        "domain",
        "role",
        "responsibilities",
        "out_of_scope",
        "intents",
        "capabilities",
        "routing_rules",
        "fallback_policy",
        "response_policy",
        "observability",
        "tests_required",
    )

    def __init__(self, *, contracts_dir: str | Path | None = None) -> None:
        default_dir = Path(__file__).with_name("agent_contracts")
        self.contracts_dir = Path(contracts_dir) if contracts_dir else default_dir
        self._cache: dict[str, AgentContractRecord] | None = None

    def load_all(self) -> dict[str, AgentContractRecord]:
        if self._cache is not None:
            return dict(self._cache)

        contracts: dict[str, AgentContractRecord] = {}
        if not self.contracts_dir.exists():
            self._cache = {}
            return {}

        for path in sorted(self.contracts_dir.glob("*.yaml")):
            raw = yaml.safe_load(self._read_yaml_text(path)) or {}
            payload = dict(raw.get("agent_contract") or {})
            agent_id = str(payload.get("agent_id") or path.stem).strip()
            domain = str(payload.get("domain") or "").strip().lower()
            if not agent_id or not domain:
                continue
            contracts[agent_id] = AgentContractRecord(
                agent_id=agent_id,
                domain=domain,
                payload=payload,
            )

        self._cache = contracts
        return dict(contracts)

    def get(self, agent_id: str) -> AgentContractRecord | None:
        return self.load_all().get(str(agent_id or "").strip())

    def get_by_domain(self, domain: str) -> AgentContractRecord | None:
        normalized = str(domain or "").strip().lower()
        if not normalized:
            return None
        for record in self.load_all().values():
            if str(record.domain or "").strip().lower() == normalized:
                return record
        return None

    def list_agent_ids(self) -> list[str]:
        return sorted(self.load_all().keys())

    def list_capabilities(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for record in self.load_all().values():
            intents = list(record.payload.get("intents") or [])
            intent_lookup: dict[str, list[str]] = {}
            for intent in intents:
                if not isinstance(intent, dict):
                    continue
                capability_id = str(intent.get("capability") or "").strip()
                intent_id = str(intent.get("id") or "").strip()
                if not capability_id or not intent_id:
                    continue
                intent_lookup.setdefault(capability_id, []).append(intent_id)

            for capability in list(record.payload.get("capabilities") or []):
                if not isinstance(capability, dict):
                    continue
                capability_id = str(capability.get("id") or "").strip()
                if not capability_id:
                    continue
                rows.append(
                    {
                        "agent_id": record.agent_id,
                        "domain": record.domain,
                        "capability_id": capability_id,
                        "type": str(capability.get("type") or "").strip().lower(),
                        "owner": str(capability.get("owner") or "").strip(),
                        "planner_required": bool(capability.get("planner_required")),
                        "handler_required": bool(capability.get("handler_required")),
                        "response_shape": str(capability.get("response_shape") or "").strip().lower(),
                        "rollout_flag": str(capability.get("rollout_flag") or "").strip() or None,
                        "policy_tags": list(capability.get("policy_tags") or []),
                        "legacy_intents": sorted(intent_lookup.get(capability_id, [])),
                    }
                )
        return rows

    def build_audit_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for record in self.load_all().values():
            payload = dict(record.payload or {})
            capability_ids = {
                str(item.get("id") or "").strip()
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
                if not capability_id or capability_id not in capability_ids:
                    intents_without_capability.append(intent_id)

            rows.append(
                {
                    "agent_id": record.agent_id,
                    "domain": record.domain,
                    "required_fields_missing": self._missing_required_fields(payload),
                    "intents_without_capability": intents_without_capability,
                    "response_policy_missing": "response_policy" not in payload,
                    "memory_policy_missing": "memory_policy" not in payload,
                }
            )
        return rows

    def _missing_required_fields(self, payload: dict[str, Any]) -> list[str]:
        missing: list[str] = []
        for field in self.REQUIRED_TOP_LEVEL_FIELDS:
            value = payload.get(field)
            if value in (None, "", [], {}):
                missing.append(field)
        return missing

    @staticmethod
    def _read_yaml_text(path: Path) -> str:
        for encoding in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                return path.read_text(encoding=encoding)
            except UnicodeDecodeError:
                continue
        return path.read_text(encoding="utf-8", errors="ignore")
