from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from apps.ia_dev.application.context.run_context import RunContext
from apps.ia_dev.application.contracts.tool_contracts import (
    ToolApprovalPolicy,
    ToolDefinition,
    ToolExecutionPolicy,
    ToolExecutionTrace,
)
from apps.ia_dev.application.routing.capability_catalog import CapabilityCatalog, CapabilityDefinition


class ToolRegistryService:
    SQL_ASSISTED_TOOL_ID = "query_execution_planner.sql_assisted"
    SEMANTIC_DICTIONARY_TOOL_ID = "semantic_orchestrator.dictionary_summary.v1"
    SEMANTIC_DOMAIN_TOOL_ID = "semantic_orchestrator.domain_context_summary.v1"
    SEMANTIC_MEMORY_TOOL_ID = "semantic_orchestrator.memory_context.v1"
    SEMANTIC_BASELINE_TOOL_ID = "semantic_orchestrator.deterministic_baseline.v1"
    SEMANTIC_ROUTE_HINTS_TOOL_ID = "semantic_orchestrator.route_debug_hints.v1"
    REGISTRY_VERSION = "tool_registry.v1"

    def __init__(self, *, catalog: CapabilityCatalog | None = None):
        self.catalog = catalog or CapabilityCatalog()
        tools = self._build_tools()
        self._by_tool_id: dict[str, ToolDefinition] = {item.tool_id: item for item in tools}
        self._capability_to_tool: dict[str, str] = {
            item.capability_id: item.tool_id
            for item in tools
            if str(item.capability_id or "").strip()
        }

    def list_tools(self) -> list[ToolDefinition]:
        return list(self._by_tool_id.values())

    def list_openai_function_tools(
        self,
        *,
        tool_ids: list[str] | tuple[str, ...] | None = None,
        include_sql_assisted: bool = False,
    ) -> list[dict[str, Any]]:
        allowed = {
            str(item or "").strip()
            for item in list(tool_ids or [])
            if str(item or "").strip()
        }
        tools: list[dict[str, Any]] = []
        for tool in self.list_tools():
            if not bool(tool.enabled) or not bool(tool.model_visible):
                continue
            if tool.tool_id == self.SQL_ASSISTED_TOOL_ID and not include_sql_assisted:
                continue
            if allowed and tool.tool_id not in allowed:
                continue
            tools.append(self._to_openai_function_tool(tool))
        return tools

    def get_tool(self, tool_id: str) -> ToolDefinition | None:
        return self._by_tool_id.get(str(tool_id or "").strip())

    def get_tool_for_capability(self, capability_id: str) -> ToolDefinition | None:
        tool_id = self._capability_to_tool.get(str(capability_id or "").strip())
        if not tool_id:
            return None
        return self._by_tool_id.get(tool_id)

    def map_capability_to_tool(self, capability_id: str) -> str:
        tool = self.get_tool_for_capability(capability_id)
        if tool is None:
            return ""
        return tool.tool_id

    def resolve_tool_for_runtime(
        self,
        *,
        response_flow: str,
        capability_id: str = "",
        route_payload: dict[str, Any] | None = None,
        execution_plan: dict[str, Any] | None = None,
    ) -> ToolDefinition | None:
        normalized_flow = str(response_flow or "").strip().lower()
        if normalized_flow == "sql_assisted":
            return self.get_tool(self.SQL_ASSISTED_TOOL_ID)
        selected_capability = (
            str(capability_id or "").strip()
            or str((route_payload or {}).get("selected_capability_id") or "").strip()
            or str((execution_plan or {}).get("capability_id") or "").strip()
        )
        if not selected_capability:
            return None
        return self.get_tool_for_capability(selected_capability)

    def build_runtime_trace(
        self,
        *,
        run_context: RunContext,
        response_flow: str,
        capability_id: str,
        route_payload: dict[str, Any] | None,
        execution_plan: dict[str, Any] | None,
        response: dict[str, Any] | None,
        fallback_used: dict[str, Any] | None,
        validation_result: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        tool = self.resolve_tool_for_runtime(
            response_flow=response_flow,
            capability_id=capability_id,
            route_payload=route_payload,
            execution_plan=execution_plan,
        )
        if tool is None:
            return []

        payload = dict(response or {})
        table = dict((payload.get("data") or {}).get("table") or {})
        finished_at = datetime.now(timezone.utc).isoformat()
        fallback = dict(fallback_used or {})
        validation = dict(validation_result or {})
        duration_ms = int((payload.get("observability") or {}).get("duration_ms") or 0)
        status = "completed"
        if bool(fallback.get("used")):
            status = "fallback"
        elif not bool(validation.get("satisfied", True)):
            status = "verified"
        elif str(response_flow or "").strip().lower() in {"runtime_only_fallback", "legacy_fallback", "controlled_runtime_limitation"}:
            status = "blocked"

        trace = ToolExecutionTrace(
            tool_id=tool.tool_id,
            capability_id=str(tool.capability_id or capability_id or ""),
            status=status,
            run_id=run_context.run_id,
            trace_id=run_context.trace_id,
            started_at=run_context.started_at_iso,
            finished_at=finished_at,
            duration_ms=duration_ms,
            tool_name=tool.tool_id,
            execution_status=status,
            validation_status="validated" if bool(validation.get("satisfied", True)) else "needs_review",
            tool_definition=tool.as_dict(),
            input_payload={
                "message": str(run_context.message or ""),
                "session_id": str(run_context.session_id or ""),
                "response_flow": str(response_flow or ""),
                "route": dict(route_payload or {}),
                "execution_plan": {
                    "strategy": str((execution_plan or {}).get("strategy") or ""),
                    "constraints": dict((execution_plan or {}).get("constraints") or {}),
                },
            },
            output_payload={
                "reply_present": bool(str(payload.get("reply") or "").strip()),
                "table_rowcount": int(table.get("rowcount") or len(table.get("rows") or [])),
                "used_tools": [
                    str(item or "").strip()
                    for item in list((payload.get("orchestrator") or {}).get("used_tools") or [])
                    if str(item or "").strip()
                ],
                "fallback_used": dict(fallback),
                "validation": dict(validation),
            },
            execution_policy=tool.execution_policy.as_dict(),
            approval_policy=tool.approval_policy.as_dict(),
            evidence_metadata={
                "reply_present": bool(str(payload.get("reply") or "").strip()),
                "table_rowcount": int(table.get("rowcount") or len(table.get("rows") or [])),
                "fallback_used": bool(fallback.get("used")),
            },
            audit_metadata={
                **dict(tool.audit_metadata or {}),
                "registry_version": self.REGISTRY_VERSION,
            },
        )
        return [trace.as_dict()]

    def build_native_trace(
        self,
        *,
        run_id: str,
        trace_id: str,
        started_at: str,
        finished_at: str,
        tool_id: str,
        tool_call_id: str,
        arguments: dict[str, Any] | None,
        duration_ms: int,
        execution_status: str,
        validation_status: str,
        output_payload: dict[str, Any] | None,
        evidence_metadata: dict[str, Any] | None,
        model_response_id: str = "",
        loop_iteration: int = 0,
    ) -> dict[str, Any]:
        tool = self.get_tool(tool_id)
        tool_definition = tool.as_dict() if tool else {}
        trace = ToolExecutionTrace(
            tool_id=str(tool_id or ""),
            capability_id=str((tool.capability_id if tool else "") or ""),
            status=str(execution_status or ""),
            run_id=str(run_id or ""),
            trace_id=str(trace_id or ""),
            started_at=str(started_at or ""),
            finished_at=str(finished_at or ""),
            duration_ms=int(duration_ms or 0),
            tool_call_id=str(tool_call_id or ""),
            tool_name=str((tool.tool_id if tool else tool_id) or ""),
            arguments=dict(arguments or {}),
            execution_status=str(execution_status or ""),
            validation_status=str(validation_status or ""),
            evidence_metadata=dict(evidence_metadata or {}),
            model_response_id=str(model_response_id or ""),
            loop_iteration=int(loop_iteration or 0),
            tool_definition=tool_definition,
            input_payload={"arguments": dict(arguments or {})},
            output_payload=dict(output_payload or {}),
            execution_policy=dict((tool.execution_policy.as_dict() if tool else {}) or {}),
            approval_policy=dict((tool.approval_policy.as_dict() if tool else {}) or {}),
            audit_metadata={
                **dict((tool.audit_metadata if tool else {}) or {}),
                "registry_version": self.REGISTRY_VERSION,
            },
        )
        return trace.as_dict()

    def _build_tools(self) -> list[ToolDefinition]:
        tools = [
            self._build_semantic_dictionary_tool(),
            self._build_semantic_domain_tool(),
            self._build_semantic_memory_tool(),
            self._build_semantic_baseline_tool(),
            self._build_semantic_route_hints_tool(),
            self._build_sql_assisted_tool(),
        ]
        for capability in self.catalog.list_all():
            tools.append(self._build_tool_from_capability(capability))
        return tools

    @staticmethod
    def _to_openai_function_tool(tool: ToolDefinition) -> dict[str, Any]:
        return {
            "type": "function",
            "name": str(tool.tool_id or ""),
            "description": str(tool.description or tool.title or ""),
            "parameters": dict(tool.input_schema or {"type": "object", "properties": {}}),
        }

    @classmethod
    def _build_semantic_dictionary_tool(cls) -> ToolDefinition:
        return ToolDefinition(
            tool_id=cls.SEMANTIC_DICTIONARY_TOOL_ID,
            capability_id="",
            domain="shared",
            handler_key="semantic_orchestrator",
            title="Semantic Dictionary Summary",
            description="Entrega el resumen gobernado del ai_dictionary ya preparado para la corrida actual.",
            execution_policy=ToolExecutionPolicy(
                mode="semantic_context",
                runtime_authority="semantic_orchestrator",
            ),
            approval_policy=ToolApprovalPolicy(mode="auto", approval_required=False, approval_type="none", risk_level="low"),
            input_schema={
                "type": "object",
                "properties": {
                    "focus": {"type": "string"},
                },
                "additionalProperties": False,
            },
            output_schema={"type": "object"},
            audit_metadata={"owner": "SemanticOrchestratorService", "tool_kind": "semantic_context", "source": "runtime_registry"},
        )

    @classmethod
    def _build_semantic_domain_tool(cls) -> ToolDefinition:
        return ToolDefinition(
            tool_id=cls.SEMANTIC_DOMAIN_TOOL_ID,
            capability_id="",
            domain="shared",
            handler_key="semantic_orchestrator",
            title="Semantic Domain Summary",
            description="Entrega el resumen narrativo y de reglas del dominio ya validado para la corrida.",
            execution_policy=ToolExecutionPolicy(
                mode="semantic_context",
                runtime_authority="semantic_orchestrator",
            ),
            approval_policy=ToolApprovalPolicy(mode="auto", approval_required=False, approval_type="none", risk_level="low"),
            input_schema={
                "type": "object",
                "properties": {
                    "focus": {"type": "string"},
                },
                "additionalProperties": False,
            },
            output_schema={"type": "object"},
            audit_metadata={"owner": "SemanticOrchestratorService", "tool_kind": "semantic_context", "source": "runtime_registry"},
        )

    @classmethod
    def _build_semantic_memory_tool(cls) -> ToolDefinition:
        return ToolDefinition(
            tool_id=cls.SEMANTIC_MEMORY_TOOL_ID,
            capability_id="",
            domain="shared",
            handler_key="semantic_orchestrator",
            title="Semantic Memory Context",
            description="Entrega pistas de memoria ya gobernadas para la corrida actual.",
            execution_policy=ToolExecutionPolicy(
                mode="semantic_context",
                runtime_authority="semantic_orchestrator",
            ),
            approval_policy=ToolApprovalPolicy(mode="auto", approval_required=False, approval_type="none", risk_level="low"),
            input_schema={
                "type": "object",
                "properties": {
                    "focus": {"type": "string"},
                },
                "additionalProperties": False,
            },
            output_schema={"type": "object"},
            audit_metadata={"owner": "SemanticOrchestratorService", "tool_kind": "semantic_context", "source": "runtime_registry"},
        )

    @classmethod
    def _build_semantic_baseline_tool(cls) -> ToolDefinition:
        return ToolDefinition(
            tool_id=cls.SEMANTIC_BASELINE_TOOL_ID,
            capability_id="",
            domain="shared",
            handler_key="semantic_orchestrator",
            title="Semantic Deterministic Baseline",
            description="Entrega la interpretacion deterministica base para que el modelo continue reasoning sin inventar ruta.",
            execution_policy=ToolExecutionPolicy(
                mode="semantic_context",
                runtime_authority="semantic_orchestrator",
            ),
            approval_policy=ToolApprovalPolicy(mode="auto", approval_required=False, approval_type="none", risk_level="low"),
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            output_schema={"type": "object"},
            audit_metadata={"owner": "SemanticOrchestratorService", "tool_kind": "semantic_context", "source": "runtime_registry"},
        )

    @classmethod
    def _build_semantic_route_hints_tool(cls) -> ToolDefinition:
        return ToolDefinition(
            tool_id=cls.SEMANTIC_ROUTE_HINTS_TOOL_ID,
            capability_id="",
            domain="shared",
            handler_key="semantic_orchestrator",
            title="Semantic Route Hints",
            description="Entrega hints deterministas de routing y validacion ya observados antes del reasoning del modelo.",
            execution_policy=ToolExecutionPolicy(
                mode="semantic_context",
                runtime_authority="semantic_orchestrator",
            ),
            approval_policy=ToolApprovalPolicy(mode="auto", approval_required=False, approval_type="none", risk_level="low"),
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            output_schema={"type": "object"},
            audit_metadata={"owner": "SemanticOrchestratorService", "tool_kind": "semantic_context", "source": "runtime_registry"},
        )

    @classmethod
    def _build_sql_assisted_tool(cls) -> ToolDefinition:
        execution_policy = ToolExecutionPolicy(
            mode="sql_assisted",
            runtime_authority="query_execution_planner",
            planner_authority="QueryExecutionPlanner",
            supports_background=False,
            idempotent=True,
        )
        return ToolDefinition(
            tool_id=cls.SQL_ASSISTED_TOOL_ID,
            capability_id=cls.SQL_ASSISTED_TOOL_ID,
            domain="shared",
            handler_key="query_execution_planner",
            title="SQL Assisted Planner Execution",
            description="Ejecuta una consulta segura validada por QueryExecutionPlanner.",
            execution_policy=execution_policy,
            approval_policy=ToolApprovalPolicy(mode="auto", approval_required=False, approval_type="none", risk_level="low"),
            input_schema={
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "constraints": {"type": "object"},
                },
                "required": ["message"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "reply": {"type": "string"},
                    "table": {"type": "object"},
                    "trace": {"type": "array"},
                },
            },
            audit_metadata={
                "owner": "QueryExecutionPlanner",
                "tool_kind": "planner",
                "sensitivity": "governed_read_only",
                "approval_role_matrix": {"approve": [], "reject": []},
                "source": "runtime_registry",
            },
            model_visible=True,
        )

    @classmethod
    def _build_tool_from_capability(cls, capability: CapabilityDefinition) -> ToolDefinition:
        requires_approval = "requires_approval" in set(capability.policy_tags or ())
        supports_background = bool({"supports_background", "long_running"} & set(capability.policy_tags or ()))
        execution_mode = "handler" if bool(capability.handler_required) else "semantic_only"
        execution_policy = ToolExecutionPolicy(
            mode=execution_mode,
            runtime_authority="runtime_capability_adapter",
            planner_authority="",
            supports_background=supports_background,
            idempotent=True,
        )
        return ToolDefinition(
            tool_id=str(capability.capability_id or ""),
            capability_id=str(capability.capability_id or ""),
            domain=str(capability.domain or ""),
            handler_key=str(capability.handler_key or ""),
            title=str(capability.capability_id or ""),
            description=str(capability.description or ""),
            execution_policy=execution_policy,
            approval_policy=ToolApprovalPolicy(
                mode="manual" if requires_approval else "auto",
                approval_required=requires_approval,
                reason="policy_tag_requires_approval" if requires_approval else "",
                approval_type="human_review" if requires_approval else "none",
                required_role="governance" if requires_approval else "",
                risk_level="high" if requires_approval else "low",
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "session_id": {"type": ["string", "null"]},
                    "resolved_query": {"type": "object"},
                    "execution_plan": {"type": "object"},
                },
                "required": ["message"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "reply": {"type": "string"},
                    "data": {"type": "object"},
                    "trace": {"type": "array"},
                },
            },
            audit_metadata={
                "owner": str(capability.owner or capability.handler_key or ""),
                "tool_kind": str(capability.capability_type or "handler"),
                "sensitivity": "sensitive" if requires_approval else "governed_read_only",
                "approval_role_matrix": {
                    "approve": ["governance"] if requires_approval else [],
                    "reject": ["governance"] if requires_approval else [],
                },
                "policy_tags": list(capability.policy_tags or ()),
                "rollout_flag": capability.rollout_flag,
                "response_shape": str(capability.response_shape or ""),
                "source": "capability_catalog",
            },
            enabled=bool(capability),
            model_visible=not requires_approval,
        )
