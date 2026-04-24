from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from apps.ia_dev.application.context.run_context import RunContext
from apps.ia_dev.application.memory.memory_write_service import MemoryWriteService


class ReasoningMemoryService:
    def __init__(self, *, memory_writer: MemoryWriteService | None = None):
        self.memory_writer = memory_writer or MemoryWriteService()

    @staticmethod
    def _flag_enabled(name: str, default: str = "1") -> bool:
        raw = str(os.getenv(name, default) or "").strip().lower()
        return raw in {"1", "true", "yes", "on"}

    def record_patterns(
        self,
        *,
        user_key: str | None,
        diagnostics: dict[str, Any],
        run_context: RunContext,
        response: dict[str, Any],
    ) -> dict[str, Any]:
        if not self._flag_enabled("IA_DEV_REASONING_MEMORY_ENABLED", "1"):
            return {"enabled": False, "saved": False}
        if not self._flag_enabled("IA_DEV_MEMORY_PROPOSALS_ENABLED", "1"):
            return {"enabled": True, "saved": False, "reason": "memory_proposals_disabled"}

        items = [
            dict(item)
            for item in list((diagnostics or {}).get("items") or [])
            if isinstance(item, dict)
        ]
        if not items:
            return {"enabled": True, "saved": False, "reason": "no_diagnostics"}

        user_results: list[dict[str, Any]] = []
        business_results: list[dict[str, Any]] = []
        for item in items[:5]:
            signature = str(item.get("signature") or "").strip().lower()
            if not signature:
                continue
            payload = self._build_pattern_value(
                diagnostic=item,
                response=response,
            )
            domain_code = str(item.get("domain_code") or "general").strip().upper() or "GENERAL"
            capability_id = str(item.get("capability_id") or "").strip()
            sensitivity = "medium" if str(item.get("severity") or "").strip().lower() == "warning" else "low"

            if user_key and self._flag_enabled("IA_DEV_REASONING_MEMORY_USER_ENABLED", "1"):
                user_results.append(
                    self.memory_writer.create_proposal(
                        user_key=user_key,
                        payload={
                            "scope": "user",
                            "candidate_key": f"reasoning.pattern.user.{signature}",
                            "candidate_value": payload,
                            "reason": "reasoning_diagnostic_pattern",
                            "sensitivity": sensitivity,
                            "domain_code": domain_code,
                            "capability_id": capability_id,
                            "idempotency_key": self._idempotency_key(
                                scope="user",
                                domain_code=domain_code,
                                capability_id=capability_id,
                                signature=signature,
                                payload=payload,
                                user_key=user_key,
                            ),
                        },
                        source_run_id=run_context.run_id,
                    )
                )

            if self._flag_enabled("IA_DEV_REASONING_MEMORY_BUSINESS_ENABLED", "1"):
                business_result = self.memory_writer.create_proposal(
                    user_key=user_key or "system_reasoning_runtime",
                    payload={
                        "scope": "business",
                        "candidate_key": f"reasoning.pattern.domain.{domain_code.lower()}.{signature}",
                        "candidate_value": payload,
                        "reason": "reasoning_collective_pattern",
                        "sensitivity": sensitivity,
                        "domain_code": domain_code,
                        "capability_id": capability_id,
                        "idempotency_key": self._idempotency_key(
                            scope="business",
                            domain_code=domain_code,
                            capability_id=capability_id,
                            signature=signature,
                            payload=payload,
                            user_key=user_key or "system_reasoning_runtime",
                        ),
                    },
                    source_run_id=run_context.run_id,
                )
                business_results.append(
                    self._autoapply_business_pattern_if_safe(
                        result=business_result,
                        fallback_actor=user_key or "system_reasoning_runtime",
                    )
                )

        return {
            "enabled": True,
            "saved": any(bool(item.get("ok")) for item in user_results + business_results),
            "user_results": user_results,
            "business_results": business_results,
        }

    def _autoapply_business_pattern_if_safe(
        self,
        *,
        result: dict[str, Any],
        fallback_actor: str,
    ) -> dict[str, Any]:
        payload = dict(result or {})
        if not self._flag_enabled("IA_DEV_REASONING_MEMORY_BUSINESS_AUTOAPPLY_ENABLED", "1"):
            return payload
        if not bool(payload.get("ok")):
            return payload
        proposal = dict(payload.get("proposal") or {})
        proposal_id = str(proposal.get("proposal_id") or "").strip()
        status = str(proposal.get("status") or "").strip().lower()
        if not proposal_id or status not in {"pending", "approved"}:
            return payload
        apply_result = self.memory_writer.approve_proposal(
            proposal_id=proposal_id,
            actor_user_key=str(fallback_actor or "system_reasoning_runtime"),
            actor_role="system",
            comment="auto_apply_business_reasoning_pattern_low_risk",
        )
        if bool(apply_result.get("ok")):
            payload["proposal"] = dict(apply_result.get("proposal") or proposal)
            payload["auto_applied"] = True
        return payload

    @staticmethod
    def _idempotency_key(
        *,
        scope: str,
        domain_code: str,
        capability_id: str,
        signature: str,
        payload: dict[str, Any],
        user_key: str,
    ) -> str:
        raw = json.dumps(
            {
                "scope": scope,
                "domain_code": domain_code,
                "capability_id": capability_id,
                "signature": signature,
                "payload": payload,
                "user_key": user_key if scope == "user" else "collective",
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]
        return f"reasoning-{digest}"

    @staticmethod
    def _build_pattern_value(
        *,
        diagnostic: dict[str, Any],
        response: dict[str, Any],
    ) -> dict[str, Any]:
        item = dict(diagnostic or {})
        response_table = dict(dict((response or {}).get("data") or {}).get("table") or {})
        evidence_signature = {
            "response_rowcount": int(response_table.get("rowcount") or len(list(response_table.get("rows") or []))),
            "severity": str(item.get("severity") or ""),
            "family": str(item.get("family") or ""),
            "stage": str(item.get("stage") or ""),
        }
        return {
            "signature": str(item.get("signature") or "").strip().lower(),
            "family": str(item.get("family") or "").strip().lower(),
            "severity": str(item.get("severity") or "").strip().lower(),
            "stage": str(item.get("stage") or "").strip().lower(),
            "domain_code": str(item.get("domain_code") or "").strip().lower(),
            "capability_id": str(item.get("capability_id") or "").strip(),
            "summary": str(item.get("summary") or "").strip(),
            "recommended_action": str(item.get("recommended_action") or "").strip(),
            "pattern_strength": max(0.0, min(float(item.get("confidence") or 0.0), 1.0)),
            "evidence_signature": evidence_signature,
        }
