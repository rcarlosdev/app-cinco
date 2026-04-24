from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.ia_dev.application.context.run_context import RunContext
from apps.ia_dev.application.orchestration.chat_application_service import (
    ChatApplicationService,
)
from apps.ia_dev.application.policies.policy_guard import (
    PolicyAction,
    PolicyDecision,
)
from apps.ia_dev.application.routing.capability_catalog import CapabilityCatalog
from apps.ia_dev.application.routing.intent_to_capability_bridge import (
    IntentToCapabilityBridge,
)


def _legacy_response(reply: str) -> dict:
    return {
        "session_id": "sess-legacy-align",
        "reply": reply,
        "orchestrator": {
            "intent": "general_question",
            "domain": "general",
            "selected_agent": "analista_agent",
            "classifier_source": "test",
            "needs_database": False,
            "output_mode": "summary",
            "used_tools": [],
        },
        "data": {"kpis": {"total": 1}, "table": {"columns": [], "rows": [], "rowcount": 0}},
    }


def _build_plan(capability_id: str) -> dict:
    catalog = CapabilityCatalog()
    definition = catalog.get(capability_id)
    domain = capability_id.split(".", 1)[0] if "." in capability_id else "general"
    return {
        "capability_id": capability_id,
        "capability_exists": bool(definition),
        "rollout_enabled": True,
        "handler_key": definition.handler_key if definition else "legacy.passthrough",
        "policy_tags": list(definition.policy_tags) if definition else [],
        "legacy_intents": list(definition.legacy_intents) if definition else [],
        "reason": "planner_default",
        "source": {
            "intent": "general_question",
            "domain": domain,
            "output_mode": "summary",
            "needs_database": domain not in {"general", "legacy"},
        },
        "dictionary_hints": {},
        "candidate_rank": 1,
        "candidate_score": 100,
    }


class _PlannerByClassification:
    def plan_from_legacy(self, *, message: str, classification: dict, planning_context=None):
        domain = str((classification or {}).get("domain") or "").strip().lower()
        if domain in {"empleados", "rrhh"}:
            return _build_plan("empleados.count.active.v1")
        if domain == "attendance":
            return _build_plan("attendance.summary.by_supervisor.v1")
        return _build_plan("general.answer.v1")

    def plan_candidates_from_legacy(self, *, message: str, classification: dict, planning_context=None, max_candidates=4):
        return [self.plan_from_legacy(message=message, classification=classification, planning_context=planning_context)]


class _PolicyGuardDeny:
    def evaluate(self, **kwargs):
        return PolicyDecision(
            action=PolicyAction.DENY,
            policy_id="policy.test.deny",
            reason="deny for safety",
            metadata={"runtime_action": "force_legacy_fallback"},
        )


class _PolicyGuardAllow:
    def evaluate(self, **kwargs):
        return PolicyDecision(
            action=PolicyAction.ALLOW,
            policy_id="policy.test.allow",
            reason="allow",
            metadata={},
        )


class _BridgeStub:
    def compare(self, **kwargs):
        planned = dict(kwargs.get("planned_capability") or {})
        capability_id = str(planned.get("capability_id") or "")
        return {
            "legacy_intent": "general_question",
            "legacy_domain": "general",
            "planned_capability_id": capability_id,
            "planned_capability_domain": capability_id.split(".", 1)[0] if "." in capability_id else "legacy",
            "diverged": False,
            "reason": "test",
        }


class _NoDelegationCoordinator:
    def plan_and_maybe_execute(self, **kwargs):
        return {
            "mode": "off",
            "should_delegate": False,
            "plan_reason": "",
            "selected_domains": [],
            "tasks": [],
            "executed": False,
            "response": None,
            "warnings": [],
        }


class _MemoryRuntimeStub:
    def load_context_for_chat(self, **kwargs):
        return {
            "flags": {"read_enabled": True, "write_enabled": True, "proposals_enabled": True},
            "decision": {"action": "read", "reason": "test"},
            "user_memory": [],
            "business_memory": [],
            "used": False,
        }

    def detect_candidates(self, **kwargs):
        return []

    def persist_candidates(self, **kwargs):
        return {"memory_candidates": [], "pending_proposals": [], "actions": []}


class LegacyBridgeLexicalHardeningTests(SimpleTestCase):
    def setUp(self):
        self.bridge = IntentToCapabilityBridge()

    def test_empleados_personal_colaboradores_variants_converge(self):
        classification = {
            "intent": "empleados_query",
            "domain": "rrhh",
            "output_mode": "summary",
            "needs_database": True,
            "used_tools": [],
            "needs_personal_join": False,
        }
        messages = [
            "cantidad empleados activos",
            "cantidad personal activo",
            "numero de colaboradores activos",
        ]

        capability_ids = [
            str(self.bridge.resolve(message=message, classification=classification).get("capability_id") or "")
            for message in messages
        ]

        self.assertEqual(capability_ids[0], "empleados.count.active.v1")
        self.assertEqual(capability_ids[1], "empleados.count.active.v1")
        self.assertEqual(capability_ids[2], "empleados.count.active.v1")

    def test_employee_turnover_routes_to_empleados_capability_without_count_word(self):
        classification = {
            "intent": "knowledge_request",
            "domain": "empleados",
            "output_mode": "table",
            "needs_database": True,
            "used_tools": [],
            "needs_personal_join": False,
        }

        resolved = self.bridge.resolve(
            message="Rotación de empelados de I&M",
            classification=classification,
        )

        self.assertEqual(str(resolved.get("capability_id") or ""), "empleados.count.active.v1")

    def test_supervisor_and_jefe_directo_queries_converge(self):
        classification = {
            "intent": "attendance_query",
            "domain": "attendance",
            "output_mode": "summary",
            "needs_database": True,
            "used_tools": [],
            "needs_personal_join": True,
        }
        by_supervisor = self.bridge.resolve(
            message="ausentismos por supervisor",
            classification=classification,
        )
        by_boss = self.bridge.resolve(
            message="ausentismos por jefe directo",
            classification=classification,
        )

        self.assertEqual(str(by_supervisor.get("capability_id") or ""), "attendance.summary.by_supervisor.v1")
        self.assertEqual(str(by_boss.get("capability_id") or ""), "attendance.summary.by_supervisor.v1")


class LegacyBridgeCanonicalAlignmentSafetyTests(SimpleTestCase):
    def setUp(self):
        self.service = ChatApplicationService()

    def test_low_confidence_or_critical_conflict_does_not_alter_classification(self):
        message = "consulta libre"
        run_context = RunContext.create(message=message, session_id="sess-align-safety")
        base = self.service._bootstrap_classification(message=message, session_context={})
        query_intelligence = {
            "canonical_resolution": {
                "domain_code": "empleados",
                "intent_code": "count",
                "capability_code": "empleados.count.active.v1",
                "confidence": 0.41,
                "conflicts": [{"type": "domain_close_scores"}],
            },
            "semantic_normalization": {
                "candidate_domains": [{"domain": "empleados", "confidence": 0.42}],
                "candidate_intents": [{"intent": "count", "confidence": 0.42}],
                "ambiguities": [{"type": "domain_close_scores"}],
            },
            "resolved_query": {"semantic_context": {"dictionary": {"synonyms": []}}},
        }

        with patch.dict(
            os.environ,
            {
                "IA_DEV_LEGACY_BRIDGE_ALIGNMENT_ENABLED": "1",
                "IA_DEV_LEGACY_BRIDGE_ALIGNMENT_SHADOW_ENABLED": "1",
            },
            clear=False,
        ):
            aligned = self.service._apply_legacy_bridge_canonical_alignment(
                message=message,
                classification=base,
                query_intelligence=query_intelligence,
                run_context=run_context,
                observability=None,
            )

        self.assertEqual(str(aligned.get("domain") or ""), str(base.get("domain") or ""))
        canonical_alignment = dict(aligned.get("canonical_alignment") or {})
        self.assertFalse(bool(canonical_alignment.get("safe")))
        self.assertEqual(str(canonical_alignment.get("capability_hint") or ""), "")
        summary = dict(run_context.metadata.get("legacy_bridge_alignment") or {})
        self.assertFalse(bool(summary.get("applied")))


class LegacyBridgeAlignmentRuntimeContinuityTests(SimpleTestCase):
    def _build_service(self, *, policy_guard):
        return ChatApplicationService(
            planner=_PlannerByClassification(),
            policy_guard=policy_guard,
            bridge=_BridgeStub(),
            memory_runtime=_MemoryRuntimeStub(),
            delegation_coordinator=_NoDelegationCoordinator(),
        )

    def test_policy_guard_still_controls_when_alignment_is_strong(self):
        service = self._build_service(policy_guard=_PolicyGuardDeny())
        service._resolve_query_intelligence = MagicMock(
            return_value={
                "mode": "active",
                "enabled": True,
                "canonical_resolution": {
                    "domain_code": "empleados",
                    "intent_code": "count",
                    "capability_code": "empleados.count.active.v1",
                    "confidence": 0.95,
                    "conflicts": [],
                },
                "semantic_normalization": {
                    "candidate_domains": [{"domain": "empleados", "confidence": 0.93}],
                    "candidate_intents": [{"intent": "count", "confidence": 0.93}],
                },
                "resolved_query": {"semantic_context": {"dictionary": {"synonyms": []}}},
                "execution_plan": {},
                "classification_override": {},
                "precomputed_response": {},
            }
        )

        legacy_runner = MagicMock(return_value=_legacy_response("legacy from policy deny"))
        with patch.dict(
            os.environ,
            {
                "IA_DEV_ROUTING_MODE": "capability",
                "IA_DEV_CANONICAL_ROUTING_ENABLED": "0",
                "IA_DEV_LEGACY_BRIDGE_ALIGNMENT_ENABLED": "1",
                "IA_DEV_LEGACY_BRIDGE_ALIGNMENT_SHADOW_ENABLED": "1",
            },
            clear=False,
        ):
            response = service.run(
                message="consulta libre",
                session_id="sess-policy-legacy-align",
                reset_memory=False,
                legacy_runner=legacy_runner,
                actor_user_key="user:test",
            )

        legacy_runner.assert_called_once()
        self.assertEqual(str(response.get("reply") or ""), "legacy from policy deny")
        shadow = dict((response.get("orchestrator") or {}).get("capability_shadow") or {})
        self.assertEqual(str(((shadow.get("planned_capability") or {}).get("capability_id") or "")), "empleados.count.active.v1")
        self.assertEqual(str(((shadow.get("policy") or {}).get("action") or "")), "deny")

    def test_low_confidence_keeps_legacy_fallback_intact(self):
        service = self._build_service(policy_guard=_PolicyGuardAllow())
        service._resolve_query_intelligence = MagicMock(
            return_value={
                "mode": "active",
                "enabled": True,
                "canonical_resolution": {
                    "domain_code": "empleados",
                    "intent_code": "count",
                    "capability_code": "empleados.count.active.v1",
                    "confidence": 0.34,
                    "conflicts": [{"type": "domain_close_scores"}],
                },
                "semantic_normalization": {
                    "candidate_domains": [{"domain": "empleados", "confidence": 0.40}],
                    "candidate_intents": [{"intent": "count", "confidence": 0.40}],
                    "ambiguities": [{"type": "domain_close_scores"}],
                },
                "resolved_query": {"semantic_context": {"dictionary": {"synonyms": []}}},
                "execution_plan": {},
                "classification_override": {},
                "precomputed_response": {},
            }
        )

        legacy_runner = MagicMock(return_value=_legacy_response("legacy still intact"))
        with patch.dict(
            os.environ,
            {
                "IA_DEV_ROUTING_MODE": "capability",
                "IA_DEV_CANONICAL_ROUTING_ENABLED": "0",
                "IA_DEV_LEGACY_BRIDGE_ALIGNMENT_ENABLED": "1",
                "IA_DEV_LEGACY_BRIDGE_ALIGNMENT_SHADOW_ENABLED": "1",
            },
            clear=False,
        ):
            response = service.run(
                message="consulta libre",
                session_id="sess-fallback-legacy-align",
                reset_memory=False,
                legacy_runner=legacy_runner,
                actor_user_key="user:test",
            )

        legacy_runner.assert_called_once()
        self.assertEqual(str(response.get("reply") or ""), "legacy still intact")
        shadow = dict((response.get("orchestrator") or {}).get("capability_shadow") or {})
        self.assertEqual(str(((shadow.get("planned_capability") or {}).get("capability_id") or "")), "general.answer.v1")
