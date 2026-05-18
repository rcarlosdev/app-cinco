from __future__ import annotations

from django.test import SimpleTestCase

from apps.ia_dev.application.context.run_context import RunContext
from apps.ia_dev.application.runtime.tool_registry_service import ToolRegistryService


class ToolRegistryServiceTests(SimpleTestCase):
    def setUp(self):
        self.service = ToolRegistryService()

    def test_registry_maps_capability_to_declarative_tool(self):
        tool = self.service.get_tool_for_capability("empleados.count.active.v1")

        self.assertIsNotNone(tool)
        self.assertEqual(str(tool.tool_id), "empleados.count.active.v1")
        self.assertEqual(str(tool.execution_policy.mode), "handler")
        self.assertIn("message", dict(tool.input_schema.get("properties") or {}))

    def test_registry_exposes_sql_assisted_planner_tool(self):
        tool = self.service.get_tool(ToolRegistryService.SQL_ASSISTED_TOOL_ID)

        self.assertIsNotNone(tool)
        self.assertEqual(str(tool.execution_policy.runtime_authority), "query_execution_planner")
        self.assertEqual(str(tool.execution_policy.mode), "sql_assisted")

    def test_registry_converts_selected_tools_to_openai_function_schema(self):
        tools = self.service.list_openai_function_tools(
            tool_ids=[
                ToolRegistryService.SEMANTIC_DICTIONARY_TOOL_ID,
                "empleados.count.active.v1",
            ]
        )

        self.assertEqual(len(tools), 2)
        self.assertEqual(str((tools[0] or {}).get("type") or ""), "function")
        self.assertEqual(str((tools[0] or {}).get("name") or ""), ToolRegistryService.SEMANTIC_DICTIONARY_TOOL_ID)
        self.assertEqual(str((((tools[1] or {}).get("parameters") or {}).get("type") or "")), "object")

    def test_build_runtime_trace_includes_tool_definition_and_audit_metadata(self):
        run_context = RunContext.create(message="personal activo hoy", session_id="sess-registry", reset_memory=False)

        trace = self.service.build_runtime_trace(
            run_context=run_context,
            response_flow="handler",
            capability_id="empleados.count.active.v1",
            route_payload={"selected_capability_id": "empleados.count.active.v1"},
            execution_plan={"strategy": "capability", "capability_id": "empleados.count.active.v1"},
            response={
                "reply": "Hay 10 empleados activos.",
                "data": {"table": {"rowcount": 1}},
                "orchestrator": {"used_tools": ["get_empleados_count_active"]},
                "observability": {"duration_ms": 12},
            },
            fallback_used={"used": False, "reason": "", "flow": ""},
            validation_result={"satisfied": True},
        )

        self.assertEqual(len(trace), 1)
        entry = dict(trace[0] or {})
        self.assertEqual(str(entry.get("tool_id") or ""), "empleados.count.active.v1")
        self.assertEqual(str((entry.get("tool_definition") or {}).get("tool_id") or ""), "empleados.count.active.v1")
        self.assertEqual(str((entry.get("execution_policy") or {}).get("mode") or ""), "handler")
        self.assertEqual(str((entry.get("audit_metadata") or {}).get("registry_version") or ""), "tool_registry.v1")
        self.assertEqual(str((((entry.get("tool_definition") or {}).get("audit_metadata") or {}).get("sensitivity") or "")), "governed_read_only")
