from __future__ import annotations

import logging
import os
from dataclasses import dataclass


logger = logging.getLogger(__name__)


DEFAULT_OPENAI_MODEL = "gpt-5-nano"

MODEL_ROLE_FAST = "FAST"
MODEL_ROLE_BALANCED = "BALANCED"
MODEL_ROLE_REASONING = "REASONING"

ROLE_ENV_VARS: dict[str, str] = {
    MODEL_ROLE_FAST: "IA_DEV_MODEL_FAST",
    MODEL_ROLE_BALANCED: "IA_DEV_MODEL_BALANCED",
    MODEL_ROLE_REASONING: "IA_DEV_MODEL_REASONING",
}


@dataclass(frozen=True)
class ModelRoute:
    component: str
    role: str
    legacy_env: str
    fallback_model: str = DEFAULT_OPENAI_MODEL

    @property
    def role_env(self) -> str:
        return ROLE_ENV_VARS[self.role]


@dataclass(frozen=True)
class ModelResolution:
    component: str
    role: str
    selected_model: str
    selected_source: str
    fallback_chain: tuple[str, ...]

    def as_dict(self) -> dict[str, str]:
        return {
            "component": self.component,
            "role": self.role,
            "selected_model": self.selected_model,
            "selected_source": self.selected_source,
            "fallback_chain": " -> ".join(self.fallback_chain),
        }


MODEL_ROUTES: dict[str, ModelRoute] = {
    "intent_classifier": ModelRoute(
        component="intent_classifier",
        role=MODEL_ROLE_FAST,
        legacy_env="IA_DEV_INTENT_MODEL",
    ),
    "query_intent": ModelRoute(
        component="query_intent",
        role=MODEL_ROLE_BALANCED,
        legacy_env="IA_DEV_QUERY_INTENT_MODEL",
    ),
    "semantic_normalization_llm": ModelRoute(
        component="semantic_normalization_llm",
        role=MODEL_ROLE_BALANCED,
        legacy_env="IA_DEV_SEMANTIC_NORMALIZATION_LLM_MODEL",
    ),
    "general_answer": ModelRoute(
        component="general_answer",
        role=MODEL_ROLE_BALANCED,
        legacy_env="IA_DEV_GENERAL_MODEL",
    ),
    "period_extraction": ModelRoute(
        component="period_extraction",
        role=MODEL_ROLE_FAST,
        legacy_env="IA_DEV_PERIOD_MODEL",
    ),
    "followups": ModelRoute(
        component="followups",
        role=MODEL_ROLE_BALANCED,
        legacy_env="IA_DEV_FOLLOWUP_MODEL",
    ),
    "cause_diagnostics": ModelRoute(
        component="cause_diagnostics",
        role=MODEL_ROLE_REASONING,
        legacy_env="IA_DEV_CAUSE_DIAGNOSTICS_MODEL",
    ),
}


def _env_value(name: str) -> str:
    return str(os.getenv(name) or "").strip()


def resolve_model(route_key: str, *, log_selection: bool = True) -> ModelResolution:
    route = MODEL_ROUTES[str(route_key)]
    fallback_chain = (
        route.legacy_env,
        route.role_env,
        "IA_DEV_MODEL",
        route.fallback_model,
    )

    for source in fallback_chain[:-1]:
        value = _env_value(source)
        if value:
            resolution = ModelResolution(
                component=route.component,
                role=route.role,
                selected_model=value,
                selected_source=source,
                fallback_chain=fallback_chain,
            )
            break
    else:
        resolution = ModelResolution(
            component=route.component,
            role=route.role,
            selected_model=route.fallback_model,
            selected_source="fallback",
            fallback_chain=fallback_chain,
        )

    if log_selection:
        logger.info(
            "IA_DEV OpenAI model selected component=%s role=%s selected_model=%s selected_source=%s",
            resolution.component,
            resolution.role,
            resolution.selected_model,
            resolution.selected_source,
        )
    return resolution


def resolve_model_name(route_key: str, *, log_selection: bool = True) -> str:
    return resolve_model(route_key, log_selection=log_selection).selected_model


def model_matrix(*, log_selection: bool = False) -> list[ModelResolution]:
    return [
        resolve_model(route_key, log_selection=log_selection)
        for route_key in MODEL_ROUTES.keys()
    ]
