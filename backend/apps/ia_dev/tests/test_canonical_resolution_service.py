from __future__ import annotations

from django.test import SimpleTestCase

from apps.ia_dev.application.semantic.canonical_resolution_service import (
    CanonicalResolutionService,
)


class CanonicalResolutionServiceTests(SimpleTestCase):
    def setUp(self):
        self.service = CanonicalResolutionService()
        self.semantic_context = {
            "dictionary": {
                "synonyms": [
                    {"termino": "empleados", "sinonimo": "personal"},
                    {"termino": "supervisor", "sinonimo": "jefe directo"},
                ]
            }
        }

    def test_empleados_vs_personal_same_resolution(self):
        empleados = self.service.resolve(
            raw_query="cantidad empleados activos",
            semantic_normalization_output={
                "canonical_query": "cantidad empleados activos",
                "candidate_domains": [{"domain": "empleados", "confidence": 0.9}],
                "candidate_intents": [{"intent": "count", "confidence": 0.9}],
                "candidate_filters": [{"filter": "estado", "value": "ACTIVO"}],
                "candidate_entities": [],
            },
            semantic_context=self.semantic_context,
            memory_hints={},
            session_context={},
            base_classification={"domain": "empleados", "intent": "empleados_query"},
            capability_hints=[],
            legacy_hints={},
        )
        personal = self.service.resolve(
            raw_query="cantidad personal activo",
            semantic_normalization_output={
                "canonical_query": "cantidad personal activo",
                "semantic_aliases": [{"alias": "personal", "canonical": "empleados"}],
                "candidate_domains": [{"domain": "general", "confidence": 0.55}],
                "candidate_intents": [{"intent": "count", "confidence": 0.8}],
                "candidate_filters": [{"filter": "estado", "value": "ACTIVO"}],
                "candidate_entities": [],
            },
            semantic_context=self.semantic_context,
            memory_hints={},
            session_context={},
            base_classification={"domain": "general", "intent": "general_question"},
            capability_hints=[],
            legacy_hints={},
        )
        self.assertEqual(empleados.domain_code, "empleados")
        self.assertEqual(personal.domain_code, "empleados")

    def test_conflict_general_vs_empleados(self):
        result = self.service.resolve(
            raw_query="numero de colaboradores activos",
            semantic_normalization_output={
                "canonical_query": "numero de colaboradores activos",
                "candidate_domains": [{"domain": "empleados", "confidence": 0.86}],
                "candidate_intents": [{"intent": "count", "confidence": 0.9}],
                "candidate_filters": [{"filter": "estado", "value": "ACTIVO"}],
            },
            semantic_context=self.semantic_context,
            memory_hints={},
            session_context={},
            base_classification={"domain": "general", "intent": "general_question"},
            capability_hints=[],
            legacy_hints={},
        )
        conflict_types = {str(item.get("type") or "") for item in list(result.conflicts or [])}
        self.assertEqual(result.domain_code, "empleados")
        self.assertIn("qi_vs_semantic_normalization", conflict_types)

    def test_exact_capability_match_precedence(self):
        result = self.service.resolve(
            raw_query="cantidad empleados activos",
            semantic_normalization_output={
                "canonical_query": "cantidad empleados activos",
                "candidate_domains": [{"domain": "empleados", "confidence": 0.8}],
                "candidate_intents": [{"intent": "count", "confidence": 0.9}],
            },
            semantic_context=self.semantic_context,
            memory_hints={},
            session_context={},
            base_classification={"domain": "general", "intent": "general_question"},
            capability_hints=[
                {
                    "capability_id": "empleados.count.active.v1",
                    "reason": "exact_match_empleados_count_active",
                    "exact_match": True,
                }
            ],
            legacy_hints={},
        )
        self.assertEqual(result.capability_code, "empleados.count.active.v1")
        self.assertEqual(result.domain_code, "empleados")
        self.assertGreaterEqual(result.confidence, 0.85)

    def test_missing_evidence_allows_general(self):
        result = self.service.resolve(
            raw_query="hola como estas",
            semantic_normalization_output={
                "canonical_query": "hola como estas",
                "candidate_domains": [{"domain": "general", "confidence": 0.2}],
                "candidate_intents": [{"intent": "summary", "confidence": 0.2}],
            },
            semantic_context={"dictionary": {"synonyms": []}},
            memory_hints={},
            session_context={},
            base_classification={"domain": "general", "intent": "general_question"},
            capability_hints=[],
            legacy_hints={},
        )
        self.assertEqual(result.domain_code, "general")
        self.assertFalse(
            any(str(item.get("type") or "") == "general_blocked_by_strong_evidence" for item in list(result.conflicts or []))
        )

    def test_detects_domain_close_scores_conflict(self):
        result = self.service.resolve(
            raw_query="resumen por jefe",
            semantic_normalization_output={
                "canonical_query": "resumen por supervisor",
                "candidate_domains": [
                    {"domain": "ausentismo", "confidence": 0.74},
                    {"domain": "empleados", "confidence": 0.68},
                ],
                "candidate_intents": [{"intent": "aggregate", "confidence": 0.7}],
                "ambiguities": [{"type": "domain_close_scores"}],
            },
            semantic_context=self.semantic_context,
            memory_hints={},
            session_context={},
            base_classification={"domain": "ausentismo", "intent": "attendance_query"},
            capability_hints=[],
            legacy_hints={},
        )
        self.assertTrue(
            any(str(item.get("type") or "") == "domain_close_scores" for item in list(result.conflicts or []))
        )
