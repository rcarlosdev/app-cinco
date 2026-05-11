from __future__ import annotations

import json
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.ia_dev.services.sql_store import IADevSqlStore


class ObservabilitySummaryCauseDiagnosticsTests(SimpleTestCase):
    def test_summary_aggregates_cause_diagnostics_by_generator_domain_and_fallback(self):
        store = IADevSqlStore()
        rows = [
            (
                "cause_diagnostics_result",
                "CauseDiagnosticsService",
                None,
                0,
                0,
                0.0,
                1710000000,
                json.dumps(
                    {
                        "generator": "openai",
                        "domain_code": "attendance",
                        "confidence": 0.82,
                        "fallback_reason": "",
                        "policy_reason": "openai_payload_validated",
                    }
                ),
            ),
            (
                "cause_diagnostics_result",
                "CauseDiagnosticsService",
                None,
                0,
                0,
                0.0,
                1710000001,
                json.dumps(
                    {
                        "generator": "heuristic",
                        "domain_code": "attendance",
                        "confidence": 0.55,
                        "fallback_reason": "openai_disabled_by_flag",
                        "policy_reason": "openai_disabled_by_flag",
                    }
                ),
            ),
            (
                "orchestrator_run",
                "LegacyOrchestratorRuntime",
                42,
                120,
                80,
                0.0012,
                1710000002,
                "{}",
            ),
        ]

        with patch.object(store, "ensure_tables", return_value=None):
            with patch.object(store, "_fetchall", return_value=rows):
                summary = store.get_observability_summary(window_seconds=3600, limit=2000)

        cause = dict(summary.get("cause_diagnostics") or {})
        self.assertEqual(int(cause.get("events") or 0), 2)
        self.assertEqual(int((cause.get("by_generator") or {}).get("openai") or 0), 1)
        self.assertEqual(int((cause.get("by_generator") or {}).get("heuristic") or 0), 1)
        self.assertEqual(int((cause.get("by_domain") or {}).get("attendance") or 0), 2)
        self.assertEqual(
            int((cause.get("by_fallback_reason") or {}).get("openai_disabled_by_flag") or 0),
            1,
        )
        self.assertEqual(
            int((cause.get("by_policy_reason") or {}).get("openai_payload_validated") or 0),
            1,
        )
        confidence = dict(cause.get("confidence") or {})
        self.assertEqual(int(confidence.get("count") or 0), 2)
        confidence_by_domain = dict(cause.get("confidence_by_domain") or {})
        self.assertEqual(
            int((dict(confidence_by_domain.get("attendance") or {})).get("count") or 0),
            2,
        )

    def test_summary_applies_cause_filters(self):
        store = IADevSqlStore()
        rows = [
            (
                "cause_diagnostics_result",
                "CauseDiagnosticsService",
                None,
                0,
                0,
                0.0,
                1710000100,
                json.dumps(
                    {
                        "generator": "openai",
                        "domain_code": "attendance",
                        "confidence": 0.81,
                        "fallback_reason": "",
                        "policy_reason": "openai_payload_validated",
                    }
                ),
            ),
            (
                "cause_diagnostics_result",
                "CauseDiagnosticsService",
                None,
                0,
                0,
                0.0,
                1710000101,
                json.dumps(
                    {
                        "generator": "heuristic",
                        "domain_code": "attendance",
                        "confidence": 0.55,
                        "fallback_reason": "openai_disabled_by_flag",
                        "policy_reason": "openai_disabled_by_flag",
                    }
                ),
            ),
        ]

        with patch.object(store, "ensure_tables", return_value=None):
            with patch.object(store, "_fetchall", return_value=rows):
                summary = store.get_observability_summary(
                    window_seconds=3600,
                    limit=2000,
                    domain_code="attendance",
                    generator="heuristic",
                    fallback_reason="openai_disabled_by_flag",
                )

        self.assertEqual(int(summary.get("sample_size") or 0), 1)
        self.assertEqual(int((summary.get("event_types") or {}).get("cause_diagnostics_result") or 0), 1)
        cause = dict(summary.get("cause_diagnostics") or {})
        self.assertEqual(int(cause.get("events") or 0), 1)
        self.assertEqual(int((cause.get("by_generator") or {}).get("heuristic") or 0), 1)
