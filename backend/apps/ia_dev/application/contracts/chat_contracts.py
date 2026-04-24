from __future__ import annotations

import copy
from typing import Any


CHAT_RESPONSE_CONTRACT_VERSION = "ia_dev.chat_response.v1"

# Snapshot congelado del shape esperado por frontend para /ia-dev/chat/
CHAT_RESPONSE_SNAPSHOT_V1: dict[str, Any] = {
    "session_id": "",
    "reply": "",
    "orchestrator": {
        "intent": "",
        "domain": "",
        "selected_agent": "",
        "classifier_source": "",
        "needs_database": False,
        "output_mode": "summary",
        "used_tools": [],
    },
    "data": {
        "kpis": {},
        "series": [],
        "labels": [],
        "insights": [],
        "cause_generation_meta": {},
        "table": {
            "columns": [],
            "rows": [],
            "rowcount": 0,
        },
    },
    "actions": [],
    "memory_candidates": [],
    "pending_proposals": [],
    "working_updates": [],
    "reasoning": {
        "enabled": False,
        "version": "ia_dev.reasoning.v1",
        "status": "disabled",
        "working_goal": "",
        "current_next_step": "",
        "hypotheses": [],
        "diagnostics": [],
        "memory_summary": {},
        "duration_ms": 0,
    },
    "data_sources": {},
    "trace": [],
    "memory": {
        "used_messages": 0,
        "capacity_messages": 0,
        "usage_ratio": 0.0,
        "trim_events": 0,
        "saturated": False,
    },
    "observability": {
        "enabled": False,
        "duration_ms": 0,
        "tool_latencies_ms": {},
        "tokens_in": 0,
        "tokens_out": 0,
        "estimated_cost_usd": 0.0,
    },
    "active_nodes": [],
}


def build_chat_response_snapshot() -> dict[str, Any]:
    return copy.deepcopy(CHAT_RESPONSE_SNAPSHOT_V1)


def ensure_chat_response_contract(payload: dict[str, Any] | None) -> dict[str, Any]:
    response = dict(payload or {})

    if not isinstance(response.get("session_id"), str):
        response["session_id"] = str(response.get("session_id") or "")
    if not isinstance(response.get("reply"), str):
        response["reply"] = str(response.get("reply") or "")

    orchestrator = response.get("orchestrator")
    if not isinstance(orchestrator, dict):
        orchestrator = {}
    orchestrator.setdefault("intent", "")
    orchestrator.setdefault("domain", "")
    orchestrator.setdefault("selected_agent", "")
    orchestrator.setdefault("classifier_source", "")
    orchestrator.setdefault("needs_database", False)
    orchestrator.setdefault("output_mode", "summary")
    if not isinstance(orchestrator.get("used_tools"), list):
        orchestrator["used_tools"] = []
    response["orchestrator"] = orchestrator

    data = response.get("data")
    if not isinstance(data, dict):
        data = {}
    if not isinstance(data.get("kpis"), dict):
        data["kpis"] = {}
    if not isinstance(data.get("series"), list):
        data["series"] = []
    if not isinstance(data.get("labels"), list):
        data["labels"] = []
    if not isinstance(data.get("insights"), list):
        data["insights"] = []
    if not isinstance(data.get("cause_generation_meta"), dict):
        data["cause_generation_meta"] = {}
    table = data.get("table")
    if not isinstance(table, dict):
        table = {}
    if not isinstance(table.get("columns"), list):
        table["columns"] = []
    if not isinstance(table.get("rows"), list):
        table["rows"] = []
    table["rowcount"] = int(table.get("rowcount") or len(table.get("rows") or []))
    data["table"] = table
    response["data"] = data

    if not isinstance(response.get("actions"), list):
        response["actions"] = []
    if not isinstance(response.get("memory_candidates"), list):
        response["memory_candidates"] = []
    if not isinstance(response.get("pending_proposals"), list):
        response["pending_proposals"] = []
    if not isinstance(response.get("working_updates"), list):
        response["working_updates"] = []
    reasoning = response.get("reasoning")
    if not isinstance(reasoning, dict):
        reasoning = {}
    reasoning.setdefault("enabled", False)
    reasoning.setdefault("version", "ia_dev.reasoning.v1")
    reasoning.setdefault("status", "disabled")
    reasoning.setdefault("working_goal", "")
    reasoning.setdefault("current_next_step", "")
    if not isinstance(reasoning.get("hypotheses"), list):
        reasoning["hypotheses"] = []
    if not isinstance(reasoning.get("diagnostics"), list):
        reasoning["diagnostics"] = []
    if not isinstance(reasoning.get("memory_summary"), dict):
        reasoning["memory_summary"] = {}
    reasoning.setdefault("duration_ms", 0)
    response["reasoning"] = reasoning
    if not isinstance(response.get("data_sources"), dict):
        response["data_sources"] = {}
    if not isinstance(response.get("trace"), list):
        response["trace"] = []

    memory = response.get("memory")
    if not isinstance(memory, dict):
        memory = {}
    memory.setdefault("used_messages", 0)
    memory.setdefault("capacity_messages", 0)
    memory.setdefault("usage_ratio", 0.0)
    memory.setdefault("trim_events", 0)
    memory.setdefault("saturated", False)
    response["memory"] = memory

    observability = response.get("observability")
    if not isinstance(observability, dict):
        observability = {}
    observability.setdefault("enabled", False)
    observability.setdefault("duration_ms", 0)
    if not isinstance(observability.get("tool_latencies_ms"), dict):
        observability["tool_latencies_ms"] = {}
    observability.setdefault("tokens_in", 0)
    observability.setdefault("tokens_out", 0)
    observability.setdefault("estimated_cost_usd", 0.0)
    response["observability"] = observability

    if not isinstance(response.get("active_nodes"), list):
        response["active_nodes"] = []

    return response
