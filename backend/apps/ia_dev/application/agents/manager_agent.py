from __future__ import annotations

from typing import Any


class ManagerAgent:
    AGENT_NAME = "manager_agent"
    ROLE = "manager"

    @classmethod
    def as_dict(cls) -> dict[str, Any]:
        return {
            "agent_name": cls.AGENT_NAME,
            "role": cls.ROLE,
            "description": (
                "Coordina intake, routing, delegacion a especialistas y consolidacion final "
                "sin reemplazar planner, validadores ni runtime deterministico."
            ),
        }

