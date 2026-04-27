from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase

from apps.ia_dev.infrastructure.ai.model_routing import (
    DEFAULT_OPENAI_MODEL,
    MODEL_ROUTES,
    resolve_model,
)


class OpenAIModelRoutingTests(SimpleTestCase):
    def test_legacy_specific_model_wins_for_every_component(self):
        env = {
            "IA_DEV_MODEL_FAST": "gpt-5.4-nano",
            "IA_DEV_MODEL_BALANCED": "gpt-5.4-mini",
            "IA_DEV_MODEL_REASONING": "gpt-5.5",
            "IA_DEV_MODEL": "global-model",
        }
        for route_key, route in MODEL_ROUTES.items():
            env[route.legacy_env] = f"legacy-{route_key}"

        with patch.dict("os.environ", env, clear=True):
            for route_key, route in MODEL_ROUTES.items():
                with self.subTest(route_key=route_key):
                    resolution = resolve_model(route_key, log_selection=False)
                    self.assertEqual(resolution.selected_model, f"legacy-{route_key}")
                    self.assertEqual(resolution.selected_source, route.legacy_env)

    def test_role_model_is_used_when_legacy_is_missing(self):
        env = {
            "IA_DEV_MODEL_FAST": "gpt-5.4-nano",
            "IA_DEV_MODEL_BALANCED": "gpt-5.4-mini",
            "IA_DEV_MODEL_REASONING": "gpt-5.5",
            "IA_DEV_MODEL": "global-model",
        }
        expected = {
            "intent_classifier": ("gpt-5.4-nano", "IA_DEV_MODEL_FAST"),
            "query_intent": ("gpt-5.4-mini", "IA_DEV_MODEL_BALANCED"),
            "semantic_normalization_llm": ("gpt-5.4-mini", "IA_DEV_MODEL_BALANCED"),
            "general_answer": ("gpt-5.4-mini", "IA_DEV_MODEL_BALANCED"),
            "period_extraction": ("gpt-5.4-nano", "IA_DEV_MODEL_FAST"),
            "followups": ("gpt-5.4-mini", "IA_DEV_MODEL_BALANCED"),
            "cause_diagnostics": ("gpt-5.5", "IA_DEV_MODEL_REASONING"),
        }

        with patch.dict("os.environ", env, clear=True):
            for route_key, (model, source) in expected.items():
                with self.subTest(route_key=route_key):
                    resolution = resolve_model(route_key, log_selection=False)
                    self.assertEqual(resolution.selected_model, model)
                    self.assertEqual(resolution.selected_source, source)

    def test_global_model_is_backward_compatible_when_role_is_missing(self):
        with patch.dict("os.environ", {"IA_DEV_MODEL": "global-model"}, clear=True):
            for route_key in MODEL_ROUTES.keys():
                with self.subTest(route_key=route_key):
                    resolution = resolve_model(route_key, log_selection=False)
                    self.assertEqual(resolution.selected_model, "global-model")
                    self.assertEqual(resolution.selected_source, "IA_DEV_MODEL")

    def test_current_hardcoded_fallback_is_preserved(self):
        with patch.dict("os.environ", {}, clear=True):
            for route_key in MODEL_ROUTES.keys():
                with self.subTest(route_key=route_key):
                    resolution = resolve_model(route_key, log_selection=False)
                    self.assertEqual(resolution.selected_model, DEFAULT_OPENAI_MODEL)
                    self.assertEqual(resolution.selected_source, "fallback")
