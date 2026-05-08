from __future__ import annotations

from typing import Any

from .yaml_agent_loader import get_examples_as_query_patterns, load_inventory_agent_yaml


def get_inventory_query_examples(path: str | None = None) -> list[dict[str, Any]]:
    return get_examples_as_query_patterns(load_inventory_agent_yaml(path))
