from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from apps.ia_dev.application.context.run_context import RunContext
from apps.ia_dev.application.policies.policy_runtime import PolicyRuntime


class PolicyAction(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


@dataclass(slots=True, frozen=True)
class PolicyDecision:
    action: PolicyAction
    policy_id: str
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.action == PolicyAction.ALLOW


def _flag_enabled(name: str, default: str = "1") -> bool:
    value = os.getenv(name, default)
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


class PolicyGuard:
    """
    Guard transversal incremental para capability-first.
    PR6: policy runtime YAML conectado con fallback seguro.
    """

    def __init__(self, *, runtime: PolicyRuntime | None = None):
        self.runtime = runtime or PolicyRuntime()
        self.runtime_enabled = _flag_enabled("IA_DEV_POLICY_RUNTIME_ENABLED", "1")
        self.failsafe_mode = str(os.getenv("IA_DEV_POLICY_FAILSAFE_MODE", "allow") or "allow").strip().lower()

    def evaluate(
        self,
        *,
        run_context: RunContext,
        planned_capability: dict[str, Any] | None,
    ) -> PolicyDecision:
        planned = dict(planned_capability or {})
        capability_id = str(planned.get("capability_id") or "").strip()
        routing_mode = run_context.routing_mode

        if not capability_id:
            return PolicyDecision(
                action=PolicyAction.ALLOW,
                policy_id="policy.base.allow.no_capability",
                reason="No capability selected. Keep legacy execution.",
                metadata={"routing_mode": routing_mode},
            )

        if routing_mode == "intent":
            return PolicyDecision(
                action=PolicyAction.ALLOW,
                policy_id="policy.base.allow.non_blocking_mode",
                reason="Intent mode preserves legacy compatibility.",
                metadata={
                    "routing_mode": routing_mode,
                    "capability_id": capability_id,
                },
            )

        if not self.runtime_enabled:
            return self._evaluate_hardcoded_policy(
                run_context=run_context,
                planned_capability=planned,
                capability_id=capability_id,
            )

        context = self._build_runtime_context(
            run_context=run_context,
            planned_capability=planned,
            capability_id=capability_id,
        )

        fallback_action = "allow" if self.failsafe_mode == "allow" else "deny"
        try:
            runtime_decision = self.runtime.evaluate(
                policy_name="capability_runtime_policy.yaml",
                context=context,
                fallback_action=fallback_action,
                fallback_policy_id="policy.runtime.capability.fallback",
                fallback_reason="capability_runtime_unavailable",
            )
        except Exception as exc:
            metadata = {
                "routing_mode": routing_mode,
                "capability_id": capability_id,
                "runtime_error": str(exc),
                "failsafe_mode": self.failsafe_mode,
            }
            if fallback_action == "deny":
                return PolicyDecision(
                    action=PolicyAction.DENY,
                    policy_id="policy.runtime.capability.exception",
                    reason="Policy runtime failed and failsafe_mode=deny.",
                    metadata=metadata,
                )
            return PolicyDecision(
                action=PolicyAction.ALLOW,
                policy_id="policy.runtime.capability.exception_allow",
                reason="Policy runtime failed and failsafe_mode=allow.",
                metadata=metadata,
            )

        return self._map_runtime_decision(
            capability_id=capability_id,
            routing_mode=routing_mode,
            runtime_decision=runtime_decision,
        )

    def _evaluate_hardcoded_policy(
        self,
        *,
        run_context: RunContext,
        planned_capability: dict[str, Any],
        capability_id: str,
    ) -> PolicyDecision:
        routing_mode = run_context.routing_mode

        if not _flag_enabled("IA_DEV_POLICY_CAPABILITY_EXECUTION_ENABLED", "1"):
            return PolicyDecision(
                action=PolicyAction.DENY,
                policy_id="policy.capability.execution.disabled",
                reason="Capability execution is disabled by policy flag.",
                metadata={
                    "routing_mode": routing_mode,
                    "capability_id": capability_id,
                    "source": "hardcoded_fallback",
                },
            )

        if capability_id.startswith("attendance."):
            return self._evaluate_hardcoded_attendance_policy(
                run_context=run_context,
                planned_capability=planned_capability,
                capability_id=capability_id,
            )
        if capability_id.startswith("transport."):
            return self._evaluate_hardcoded_transport_policy(
                run_context=run_context,
                planned_capability=planned_capability,
                capability_id=capability_id,
            )

        return PolicyDecision(
            action=PolicyAction.ALLOW,
            policy_id="policy.base.allow.default",
            reason="Capability allowed by hardcoded fallback policy.",
            metadata={
                "routing_mode": routing_mode,
                "capability_id": capability_id,
                "source": "hardcoded_fallback",
            },
        )

    def _evaluate_hardcoded_attendance_policy(
        self,
        *,
        run_context: RunContext,
        planned_capability: dict[str, Any],
        capability_id: str,
    ) -> PolicyDecision:
        policy_tags = set(planned_capability.get("policy_tags") or [])
        source = dict(planned_capability.get("source") or {})
        needs_database = bool(source.get("needs_database", True))
        memory_preloaded = dict((run_context.metadata.get("memory_context") or {}).get("preloaded") or {})
        uses_memory = (
            int(memory_preloaded.get("user_memory_count") or 0) > 0
            or int(memory_preloaded.get("business_memory_count") or 0) > 0
        )

        if not _flag_enabled("IA_DEV_CAP_ATTENDANCE_ENABLED", "0"):
            return PolicyDecision(
                action=PolicyAction.DENY,
                policy_id="policy.attendance.capability.disabled",
                reason="Attendance capability-first is disabled.",
                metadata={"capability_id": capability_id, "source": "hardcoded_fallback"},
            )

        if not needs_database:
            return PolicyDecision(
                action=PolicyAction.DENY,
                policy_id="policy.attendance.requires_database",
                reason="Attendance capability requires database access.",
                metadata={"capability_id": capability_id, "source": "hardcoded_fallback"},
            )

        requires_personal_join = capability_id in {
            "attendance.unjustified.table_with_personal.v1",
            "attendance.recurrence.grouped.v1",
            "attendance.recurrence.itemized.v1",
        }
        if requires_personal_join and not _flag_enabled(
            "IA_DEV_POLICY_ATTENDANCE_PERSONAL_JOIN_ENABLED", "1"
        ):
            return PolicyDecision(
                action=PolicyAction.DENY,
                policy_id="policy.attendance.personal_join.disabled",
                reason="Join con personal esta restringido por politica.",
                metadata={
                    "capability_id": capability_id,
                    "requires_personal_join": True,
                    "source": "hardcoded_fallback",
                },
            )

        if uses_memory and not _flag_enabled("IA_DEV_POLICY_MEMORY_HINTS_ENABLED", "1"):
            return PolicyDecision(
                action=PolicyAction.DENY,
                policy_id="policy.attendance.memory_hints.disabled",
                reason="Uso de memory hints deshabilitado por politica.",
                metadata={
                    "capability_id": capability_id,
                    "uses_memory": uses_memory,
                    "source": "hardcoded_fallback",
                },
            )

        return PolicyDecision(
            action=PolicyAction.ALLOW,
            policy_id="policy.attendance.allow",
            reason="Attendance capability allowed by hardcoded fallback policy.",
            metadata={
                "capability_id": capability_id,
                "requires_personal_join": requires_personal_join,
                "contains_personal_data": "contains_personal_data" in policy_tags,
                "uses_memory_hints": uses_memory,
                "source": "hardcoded_fallback",
            },
        )

    def _evaluate_hardcoded_transport_policy(
        self,
        *,
        run_context: RunContext,
        planned_capability: dict[str, Any],
        capability_id: str,
    ) -> PolicyDecision:
        source = dict(planned_capability.get("source") or {})
        needs_database = bool(source.get("needs_database", True))
        memory_preloaded = dict((run_context.metadata.get("memory_context") or {}).get("preloaded") or {})
        uses_memory = (
            int(memory_preloaded.get("user_memory_count") or 0) > 0
            or int(memory_preloaded.get("business_memory_count") or 0) > 0
        )

        if not _flag_enabled("IA_DEV_CAP_TRANSPORT_ENABLED", "0"):
            return PolicyDecision(
                action=PolicyAction.DENY,
                policy_id="policy.transport.capability.disabled",
                reason="Transport capability-first is disabled.",
                metadata={"capability_id": capability_id, "source": "hardcoded_fallback"},
            )

        if _flag_enabled("IA_DEV_POLICY_TRANSPORT_FORCE_LEGACY", "0"):
            return PolicyDecision(
                action=PolicyAction.DENY,
                policy_id="policy.transport.force_legacy.flag",
                reason="Transport capability forced to legacy by policy flag.",
                metadata={
                    "capability_id": capability_id,
                    "source": "hardcoded_fallback",
                    "runtime_action": "force_legacy_fallback",
                },
            )

        if not needs_database:
            return PolicyDecision(
                action=PolicyAction.DENY,
                policy_id="policy.transport.requires_database",
                reason="Transport capability requires database access.",
                metadata={"capability_id": capability_id, "source": "hardcoded_fallback"},
            )

        if uses_memory and not _flag_enabled("IA_DEV_POLICY_MEMORY_HINTS_ENABLED", "1"):
            return PolicyDecision(
                action=PolicyAction.DENY,
                policy_id="policy.transport.memory_hints.disabled",
                reason="Uso de memory hints deshabilitado por politica.",
                metadata={
                    "capability_id": capability_id,
                    "uses_memory": uses_memory,
                    "source": "hardcoded_fallback",
                },
            )

        return PolicyDecision(
            action=PolicyAction.ALLOW,
            policy_id="policy.transport.allow",
            reason="Transport capability allowed by hardcoded fallback policy.",
            metadata={
                "capability_id": capability_id,
                "uses_memory_hints": uses_memory,
                "source": "hardcoded_fallback",
            },
        )

    @staticmethod
    def _build_runtime_context(
        *,
        run_context: RunContext,
        planned_capability: dict[str, Any],
        capability_id: str,
    ) -> dict[str, Any]:
        source = dict(planned_capability.get("source") or {})
        policy_tags = list(planned_capability.get("policy_tags") or [])
        requires_personal_join = capability_id in {
            "attendance.unjustified.table_with_personal.v1",
            "attendance.recurrence.grouped.v1",
            "attendance.recurrence.itemized.v1",
        }
        requires_transport_source = capability_id.startswith("transport.")
        memory_preloaded = dict((run_context.metadata.get("memory_context") or {}).get("preloaded") or {})
        uses_memory_hints = (
            int(memory_preloaded.get("user_memory_count") or 0) > 0
            or int(memory_preloaded.get("business_memory_count") or 0) > 0
        )
        return {
            "routing_mode": run_context.routing_mode,
            "capability_id": capability_id,
            "needs_database": bool(source.get("needs_database", True)),
            "requires_personal_join": requires_personal_join,
            "requires_transport_source": requires_transport_source,
            "policy_tags": policy_tags,
            "uses_memory_hints": uses_memory_hints,
            "domain": capability_id.split(".", 1)[0] if "." in capability_id else "legacy",
        }

    def _map_runtime_decision(
        self,
        *,
        capability_id: str,
        routing_mode: str,
        runtime_decision,
    ) -> PolicyDecision:
        action = str(runtime_decision.action or "allow").strip().lower()
        metadata = dict(runtime_decision.metadata or {})
        metadata.setdefault("runtime_action", action)
        metadata.setdefault("routing_mode", routing_mode)
        metadata.setdefault("capability_id", capability_id)

        if action == "allow":
            return PolicyDecision(
                action=PolicyAction.ALLOW,
                policy_id=str(runtime_decision.policy_id or "policy.runtime.allow"),
                reason=str(runtime_decision.reason or "allowed by runtime policy"),
                metadata=metadata,
            )
        if action == "require_approval":
            return PolicyDecision(
                action=PolicyAction.REQUIRE_APPROVAL,
                policy_id=str(runtime_decision.policy_id or "policy.runtime.require_approval"),
                reason=str(runtime_decision.reason or "approval required by runtime policy"),
                metadata=metadata,
            )
        if action in {"deny", "restrict_scope", "disable_capability", "force_legacy_fallback"}:
            return PolicyDecision(
                action=PolicyAction.DENY,
                policy_id=str(runtime_decision.policy_id or "policy.runtime.deny"),
                reason=str(runtime_decision.reason or "denied by runtime policy"),
                metadata=metadata,
            )
        if action == "mask_sensitive_fields":
            force_legacy = bool(metadata.get("force_legacy_fallback"))
            if force_legacy:
                return PolicyDecision(
                    action=PolicyAction.DENY,
                    policy_id=str(runtime_decision.policy_id or "policy.runtime.mask_force_legacy"),
                    reason=str(runtime_decision.reason or "masked by policy with forced legacy fallback"),
                    metadata=metadata,
                )
            metadata["mask_sensitive_fields"] = True
            return PolicyDecision(
                action=PolicyAction.ALLOW,
                policy_id=str(runtime_decision.policy_id or "policy.runtime.mask_allow"),
                reason=str(runtime_decision.reason or "allow with masking"),
                metadata=metadata,
            )

        # Unknown action: safe fallback
        if self.failsafe_mode == "deny":
            return PolicyDecision(
                action=PolicyAction.DENY,
                policy_id="policy.runtime.unknown_action.deny",
                reason=f"Unknown policy action '{action}' and failsafe_mode=deny.",
                metadata=metadata,
            )
        return PolicyDecision(
            action=PolicyAction.ALLOW,
            policy_id="policy.runtime.unknown_action.allow",
            reason=f"Unknown policy action '{action}' and failsafe_mode=allow.",
            metadata=metadata,
        )
