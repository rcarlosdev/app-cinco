from __future__ import annotations

import os
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.ia_dev.application.context.run_context import RunContext
from apps.ia_dev.application.contracts.query_intelligence_contracts import (
    QueryExecutionPlan,
    ResolvedQuerySpec,
    SatisfactionValidation,
    StructuredQueryIntent,
)
from apps.ia_dev.application.semantic.query_pattern_memory_service import (
    QueryPatternMemoryService,
)


class _FakeMemoryWriter:
    def __init__(self):
        self.calls: list[dict] = []

    def create_proposal(self, *, user_key: str, payload: dict, source_run_id: str | None = None) -> dict:
        self.calls.append(
            {
                "user_key": user_key,
                "payload": dict(payload or {}),
                "source_run_id": source_run_id,
            }
        )
        idx = len(self.calls)
        return {
            "ok": True,
            "proposal": {
                "proposal_id": f"proposal-{idx}",
                "status": "pending",
            },
        }

    def approve_proposal(self, *, proposal_id: str, actor_user_key: str, actor_role: str, comment: str = "") -> dict:
        return {
            "ok": True,
            "proposal": {
                "proposal_id": proposal_id,
                "status": "applied",
            },
        }


class QueryPatternMemoryServiceTests(SimpleTestCase):
    @staticmethod
    def _build_resolved_query(*, with_cedula: bool) -> ResolvedQuerySpec:
        filters = {"estado": "ACTIVO"}
        if with_cedula:
            filters["cedula"] = "1055837370"
        intent = StructuredQueryIntent(
            raw_query="Cantidad ausentismos",
            domain_code="ausentismo",
            operation="count",
            template_id="count_records_by_period",
            filters=filters,
            period={"label": "ultimos_6_meses"},
            metrics=["count"],
            confidence=0.9,
            source="rules",
        )
        return ResolvedQuerySpec(
            intent=intent,
            semantic_context={
                "resolved_semantic": {
                    "synonyms": [{"requested_term": "jefe", "canonical_term": "supervisor"}],
                    "columns": [{"canonical_term": "estado"}],
                    "relations": [{"relation_name": "ausentismo_empleado"}],
                }
            },
            normalized_filters=filters,
            normalized_period={
                "label": "ultimos_6_meses",
                "start_date": "2025-10-14",
                "end_date": "2026-04-13",
            },
            mapped_columns={"estado": "estado"},
        )

    @staticmethod
    def _build_execution_plan(*, with_cedula: bool) -> QueryExecutionPlan:
        filters = {"estado": "ACTIVO"}
        if with_cedula:
            filters["cedula"] = "1055837370"
        return QueryExecutionPlan(
            strategy="capability",
            reason="test",
            domain_code="attendance",
            capability_id="attendance.unjustified.summary.v1",
            constraints={
                "filters": filters,
                "group_by": [],
                "metrics": ["count"],
                "period_scope": {
                    "label": "ultimos_6_meses",
                    "start_date": "2025-10-14",
                    "end_date": "2026-04-13",
                },
            },
        )

    @staticmethod
    def _build_validation(*, with_period_gap: bool = False) -> SatisfactionValidation:
        checks = {
            "expected_cedula": "",
            "expected_group_by": [],
        }
        if with_period_gap:
            checks["expected_period"] = {"start_date": "2025-10-14", "end_date": "2026-04-13"}
            checks["resolved_period_from_response"] = None
        return SatisfactionValidation(
            satisfied=True,
            reason="ok",
            checks=checks,
        )

    def test_record_success_blocks_business_scope_when_identifier_exists(self):
        writer = _FakeMemoryWriter()
        service = QueryPatternMemoryService(memory_writer=writer)
        run_context = RunContext.create(message="test", session_id="sess-pm-1")
        with patch.dict(
            os.environ,
            {
                "IA_DEV_QUERY_PATTERN_MEMORY_ENABLED": "1",
                "IA_DEV_MEMORY_PROPOSALS_ENABLED": "1",
                "IA_DEV_QUERY_PATTERN_MEMORY_USER_ENABLED": "1",
                "IA_DEV_QUERY_PATTERN_MEMORY_BUSINESS_ENABLED": "1",
                "IA_DEV_QUERY_PATTERN_MEMORY_MIN_SCORE": "0.70",
            },
            clear=False,
        ):
            result = service.record_success(
                user_key="user:test",
                resolved_query=self._build_resolved_query(with_cedula=True),
                execution_plan=self._build_execution_plan(with_cedula=True),
                validation=self._build_validation(with_period_gap=False),
                run_context=run_context,
                response={"data": {"kpis": {"total": 10}, "table": {"columns": [], "rows": [], "rowcount": 0}}},
                observability=None,
            )
        self.assertTrue(bool(result.get("saved")))
        self.assertEqual(len(writer.calls), 1)
        self.assertEqual(str(writer.calls[0]["payload"].get("scope") or ""), "user")
        business_result = dict(result.get("business_result") or {})
        self.assertFalse(bool(business_result.get("ok")))
        self.assertEqual(str(business_result.get("error") or ""), "business_scope_blocked_by_identifiers")

    def test_record_success_persists_user_and_business_without_identifiers(self):
        writer = _FakeMemoryWriter()
        service = QueryPatternMemoryService(memory_writer=writer)
        run_context = RunContext.create(message="test", session_id="sess-pm-2")
        with patch.dict(
            os.environ,
            {
                "IA_DEV_QUERY_PATTERN_MEMORY_ENABLED": "1",
                "IA_DEV_MEMORY_PROPOSALS_ENABLED": "1",
                "IA_DEV_QUERY_PATTERN_MEMORY_USER_ENABLED": "1",
                "IA_DEV_QUERY_PATTERN_MEMORY_BUSINESS_ENABLED": "1",
                "IA_DEV_QUERY_PATTERN_MEMORY_MIN_SCORE": "0.70",
            },
            clear=False,
        ):
            result = service.record_success(
                user_key="user:test",
                resolved_query=self._build_resolved_query(with_cedula=False),
                execution_plan=self._build_execution_plan(with_cedula=False),
                validation=self._build_validation(with_period_gap=False),
                run_context=run_context,
                response={"data": {"kpis": {"total": 15}, "table": {"columns": ["estado"], "rows": [], "rowcount": 0}}},
                observability=None,
            )
        self.assertTrue(bool(result.get("saved")))
        self.assertEqual(len(writer.calls), 2)
        scopes = [str(item["payload"].get("scope") or "") for item in writer.calls]
        self.assertEqual(scopes, ["user", "business"])
        self.assertTrue(bool((result.get("business_result") or {}).get("ok")))

    def test_record_success_respects_min_score_threshold(self):
        writer = _FakeMemoryWriter()
        service = QueryPatternMemoryService(memory_writer=writer)
        run_context = RunContext.create(message="test", session_id="sess-pm-3")
        with patch.dict(
            os.environ,
            {
                "IA_DEV_QUERY_PATTERN_MEMORY_ENABLED": "1",
                "IA_DEV_MEMORY_PROPOSALS_ENABLED": "1",
                "IA_DEV_QUERY_PATTERN_MEMORY_USER_ENABLED": "1",
                "IA_DEV_QUERY_PATTERN_MEMORY_BUSINESS_ENABLED": "0",
                "IA_DEV_QUERY_PATTERN_MEMORY_MIN_SCORE": "0.90",
            },
            clear=False,
        ):
            result = service.record_success(
                user_key="user:test",
                resolved_query=self._build_resolved_query(with_cedula=False),
                execution_plan=self._build_execution_plan(with_cedula=False),
                validation=self._build_validation(with_period_gap=True),
                run_context=run_context,
                response={"data": {"kpis": {"total": 3}, "table": {"columns": [], "rows": [], "rowcount": 0}}},
                observability=None,
            )
        self.assertFalse(bool(result.get("saved")))
        self.assertEqual(str(result.get("reason") or ""), "satisfaction_score_below_threshold")
        self.assertEqual(len(writer.calls), 0)

    def test_idempotency_key_is_stable_across_runs_for_same_pattern(self):
        writer = _FakeMemoryWriter()
        service = QueryPatternMemoryService(memory_writer=writer)
        with patch.dict(
            os.environ,
            {
                "IA_DEV_QUERY_PATTERN_MEMORY_ENABLED": "1",
                "IA_DEV_MEMORY_PROPOSALS_ENABLED": "1",
                "IA_DEV_QUERY_PATTERN_MEMORY_USER_ENABLED": "1",
                "IA_DEV_QUERY_PATTERN_MEMORY_BUSINESS_ENABLED": "0",
                "IA_DEV_QUERY_PATTERN_MEMORY_MIN_SCORE": "0.70",
            },
            clear=False,
        ):
            service.record_success(
                user_key="user:test",
                resolved_query=self._build_resolved_query(with_cedula=False),
                execution_plan=self._build_execution_plan(with_cedula=False),
                validation=self._build_validation(with_period_gap=False),
                run_context=RunContext.create(message="test", session_id="sess-pm-4"),
                response={"data": {"kpis": {"total": 1}, "table": {"columns": [], "rows": [], "rowcount": 0}}},
                observability=None,
            )
            service.record_success(
                user_key="user:test",
                resolved_query=self._build_resolved_query(with_cedula=False),
                execution_plan=self._build_execution_plan(with_cedula=False),
                validation=self._build_validation(with_period_gap=False),
                run_context=RunContext.create(message="test", session_id="sess-pm-5"),
                response={"data": {"kpis": {"total": 1}, "table": {"columns": [], "rows": [], "rowcount": 0}}},
                observability=None,
            )
        self.assertEqual(len(writer.calls), 2)
        first_key = str(writer.calls[0]["payload"].get("idempotency_key") or "")
        second_key = str(writer.calls[1]["payload"].get("idempotency_key") or "")
        self.assertTrue(first_key)
        self.assertEqual(first_key, second_key)

