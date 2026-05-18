from __future__ import annotations

from dataclasses import dataclass

from apps.ia_dev.infrastructure.ai.model_routing import resolve_model


@dataclass(frozen=True)
class GatewayModelSelection:
    component: str
    route_key: str
    model: str
    source: str


class OpenAIModelPolicy:
    def resolve(
        self,
        *,
        component: str,
        route_key: str | None = None,
        explicit_model: str | None = None,
    ) -> GatewayModelSelection:
        if str(explicit_model or "").strip():
            return GatewayModelSelection(
                component=str(component or "").strip(),
                route_key=str(route_key or "").strip(),
                model=str(explicit_model or "").strip(),
                source="explicit",
            )
        if str(route_key or "").strip():
            resolution = resolve_model(str(route_key), log_selection=False)
            return GatewayModelSelection(
                component=str(component or "").strip(),
                route_key=str(route_key or "").strip(),
                model=str(resolution.selected_model or "").strip(),
                source=str(resolution.selected_source or "routing"),
            )
        raise ValueError("route_key or explicit_model is required")
