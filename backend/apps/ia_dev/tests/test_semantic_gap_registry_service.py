from __future__ import annotations

from django.test import SimpleTestCase

from apps.ia_dev.application.context.run_context import RunContext
from apps.ia_dev.application.runtime.semantic_gap_registry_service import (
    SemanticGapRegistryService,
)


class _FakeGapRepo:
    def __init__(self):
        self.rows_by_key: dict[str, dict] = {}
        self._next_id = 1

    def get_gap_record_by_idempotency(self, idempotency_key: str):
        row = self.rows_by_key.get(idempotency_key)
        return dict(row) if row else None

    def create_gap_record(self, payload: dict):
        item = dict(payload or {})
        item["id"] = self._next_id
        self._next_id += 1
        self.rows_by_key[str(item.get("clave_idempotencia") or "")] = dict(item)
        return dict(item)

    def find_equivalent_open_gap_record(self, payload: dict):
        expected = (
            str(payload.get("origen_registro") or "runtime").strip().lower(),
            str(payload.get("categoria_brecha") or "").strip().lower(),
            str(payload.get("etapa_fallo") or "").strip().lower(),
            str(payload.get("motivo_brecha") or "").strip().lower(),
            str(payload.get("consulta_original") or "").strip().lower(),
            str(payload.get("dominio_detectado") or "").strip().lower(),
            str(payload.get("intencion_detectada") or "").strip().lower(),
            str(payload.get("capacidad_candidata") or "").strip(),
        )
        for row in self.rows_by_key.values():
            current = (
                str(row.get("origen_registro") or "runtime").strip().lower(),
                str(row.get("categoria_brecha") or "").strip().lower(),
                str(row.get("etapa_fallo") or "").strip().lower(),
                str(row.get("motivo_brecha") or "").strip().lower(),
                str(row.get("consulta_original") or "").strip().lower(),
                str(row.get("dominio_detectado") or "").strip().lower(),
                str(row.get("intencion_detectada") or "").strip().lower(),
                str(row.get("capacidad_candidata") or "").strip(),
            )
            if current == expected and str(row.get("estado_revision") or "") not in {"resuelta", "descartada"}:
                return dict(row)
        return None

    def summarize_gap_records(self, *, limit: int = 10):
        rows = list(self.rows_by_key.values())
        return {
            "totales": {
                "brechas": len(rows),
                "nuevas": sum(1 for row in rows if str(row.get("estado_revision") or "") in {"nueva", "nuevo"}),
                "resueltas": sum(1 for row in rows if str(row.get("estado_revision") or "") in {"resuelta", "resuelto"}),
            },
            "brechas_nuevas": rows[:limit],
            "brechas_por_categoria": [],
            "brechas_por_dominio": [],
            "brechas_por_capacidad": [],
            "brechas_frecuentes": [],
            "brechas_resueltas": [],
            "brechas_con_sugerencia_metadata": [],
        }


def _runtime_response(
    *,
    response_status: str,
    task_status: str,
    selected_capability: str = "inventory_stock_balance_by_mobile",
    selected_tool: str = "query_execution_planner.sql_assisted",
    clarification_required: bool = False,
    clarification_question: str = "",
    metadata_governed_used: bool = True,
    shadow_fallback_used: bool = False,
    runtime_flow: str = "sql_assisted",
    block_reason_code: str = "",
    validation_satisfied: bool = True,
    validation_reason: str = "",
):
    return {
        "reply": "respuesta",
        "task_state": {
            "workflow_key": "task_runtime:run-gap-1",
            "status": task_status,
            "state": {
                "task_id": "task_runtime:run-gap-1",
                "task_status": task_status,
            },
        },
        "task": {
            "current_run": {
                "semantic_explanation": {
                    "user_question": "que tiene Juan Perez",
                    "domain": "inventario_logistica",
                    "intent": "stock_balance",
                    "selected_capability": selected_capability,
                    "selected_tool": selected_tool,
                    "clarification_needed": {
                        "required": clarification_required,
                        "question": clarification_question,
                    },
                    "metadata_used": {
                        "governed_used": metadata_governed_used,
                        "sources": ["dd_sinonimos"] if metadata_governed_used else [],
                    },
                    "fallback_used": {
                        "used": shadow_fallback_used,
                        "reason": "fallback_sombreado_usado" if shadow_fallback_used else "",
                        "flow": runtime_flow if shadow_fallback_used else "",
                        "shadow_fallback_used": shadow_fallback_used,
                        "legacy_rule_detected": shadow_fallback_used,
                    },
                    "validation_status": {
                        "status": "passed" if validation_satisfied else "review_required",
                        "satisfied": validation_satisfied,
                        "reason": validation_reason,
                        "needs_clarification": clarification_required,
                    },
                    "evidence_summary": {
                        "rowcount": 0,
                        "extra_table_count": 0,
                        "result_empty": True,
                    },
                    "capability_pack": {
                        "paquete_capacidad_usado": "inventario_logistica",
                        "version_paquete": "1.0.0",
                        "evaluaciones_asociadas": ["inventario_runtime_eval_v1"],
                    },
                    "final_state": {
                        "task_status": task_status,
                        "response_status": response_status,
                    },
                },
            }
        },
        "data_sources": {
            "runtime": {
                "flow": runtime_flow,
                "capability": selected_capability,
                "final_domain": "inventario_logistica",
                "block_reason_code": block_reason_code,
                "fallback_reason": block_reason_code,
            }
        },
        "data": {
            "business_response": {
                "metadata": {
                    "response_status": response_status,
                }
            }
        },
    }


class SemanticGapRegistryServiceTests(SimpleTestCase):
    def setUp(self):
        self.repo = _FakeGapRepo()
        self.service = SemanticGapRegistryService(repo=self.repo)
        self.run_context = RunContext.create(
            message="que tiene Juan Perez",
            session_id="sess-gap-1",
            reset_memory=False,
        )
        self.run_context.run_id = "run-gap-1"
        self.run_context.metadata["actor_user_key"] = "user:123"

    def test_creates_record_for_structural_clarification(self):
        response = _runtime_response(
            response_status="clarification_required",
            task_status="needs_input",
            clarification_required=True,
            clarification_question="Aclara si buscas por cedula, movil o codigo.",
            validation_satisfied=False,
            validation_reason="missing_structural_context",
        )

        result = self.service.register_from_runtime(response=response, run_context=self.run_context)

        self.assertTrue(bool(result.get("registrada")))
        registro = dict(result.get("registro") or {})
        self.assertEqual(str(registro.get("categoria_brecha") or ""), "consulta_ambigua")
        self.assertTrue(bool(registro.get("requiere_aclaracion")))
        self.assertEqual(str(registro.get("etapa_fallo") or ""), "semantic_resolution")

    def test_creates_record_for_declared_limitation(self):
        response = _runtime_response(
            response_status="limitation_declared",
            task_status="completed",
            runtime_flow="controlled_runtime_limitation",
            block_reason_code="unsupported_capability_domain:document_generation",
        )

        result = self.service.register_from_runtime(response=response, run_context=self.run_context)

        self.assertTrue(bool(result.get("registrada")))
        registro = dict(result.get("registro") or {})
        self.assertEqual(str(registro.get("categoria_brecha") or ""), "fuera_de_alcance")
        self.assertTrue(bool(registro.get("fuera_de_alcance")))

    def test_creates_record_for_missing_tool_binding(self):
        response = _runtime_response(
            response_status="blocked",
            task_status="blocked",
            selected_tool="",
            runtime_flow="runtime_only_fallback",
            block_reason_code="capability_without_registered_tool",
        )

        result = self.service.register_from_runtime(response=response, run_context=self.run_context)

        self.assertTrue(bool(result.get("registrada")))
        registro = dict(result.get("registro") or {})
        self.assertEqual(str(registro.get("categoria_brecha") or ""), "falta_tool")
        self.assertTrue(bool(registro.get("falta_tool")))

    def test_creates_record_for_shadow_fallback_excess(self):
        response = _runtime_response(
            response_status="success",
            task_status="completed",
            selected_tool="query_execution_planner.sql_assisted",
            shadow_fallback_used=True,
        )

        result = self.service.register_from_runtime(response=response, run_context=self.run_context)

        self.assertTrue(bool(result.get("registrada")))
        registro = dict(result.get("registro") or {})
        self.assertEqual(str(registro.get("categoria_brecha") or ""), "fallback_excesivo")
        self.assertTrue(bool(registro.get("fallback_sombreado_usado")))

    def test_does_not_create_record_for_normal_success(self):
        response = _runtime_response(
            response_status="success",
            task_status="completed",
            validation_satisfied=True,
        )

        result = self.service.register_from_runtime(response=response, run_context=self.run_context)

        self.assertFalse(bool(result.get("registrada")))
        self.assertEqual(len(self.repo.rows_by_key), 0)

    def test_register_from_runtime_is_idempotent_for_same_gap(self):
        response = _runtime_response(
            response_status="clarification_required",
            task_status="needs_input",
            clarification_required=True,
            clarification_question="Aclara si buscas por cedula, movil o codigo.",
            validation_satisfied=False,
            validation_reason="missing_structural_context",
        )

        first = self.service.register_from_runtime(response=response, run_context=self.run_context)
        second = self.service.register_from_runtime(response=response, run_context=self.run_context)

        self.assertTrue(bool(first.get("registrada")))
        self.assertFalse(bool(second.get("registrada")))
        self.assertTrue(bool(second.get("idempotente")))
        self.assertEqual(len(self.repo.rows_by_key), 1)

    def test_register_from_eval_result_creates_gap(self):
        result = self.service.register_from_eval_result(
            dataset_version="p5_inventario_runtime_eval_v1",
            eval_result={
                "case_id": "fallback_sombreado_controlado",
                "pregunta": "movimientos del tecnico 5098747",
                "grupo_semantico": "kardex_empleado",
                "clasificacion": "capability_incorrecta",
                "eval_result": "failed",
                "eval_reason": "capability_mismatch",
                "candidate_capability": "inventory_kardex_consolidated",
                "fallback_detected": True,
                "metadata_used": False,
                "semantic_trace": {
                    "fallback_sombreado_usado": True,
                },
                "capability_pack": {
                    "paquete_capacidad_usado": "inventario_logistica",
                },
            },
        )

        self.assertTrue(bool(result.get("registrada")))
        registro = dict(result.get("registro") or {})
        self.assertEqual(str(registro.get("origen_registro") or ""), "eval_p5")
        self.assertEqual(str(registro.get("categoria_brecha") or ""), "falta_capacidad")
        self.assertTrue(bool(registro.get("falta_capacidad")))

    def test_operations_snapshot_exposes_registered_gaps(self):
        self.service.register_from_eval_result(
            dataset_version="p5_inventario_runtime_eval_v1",
            eval_result={
                "case_id": "fallback_sombreado_controlado",
                "pregunta": "movimientos del tecnico 5098747",
                "grupo_semantico": "kardex_empleado",
                "clasificacion": "capability_incorrecta",
                "eval_result": "failed",
                "eval_reason": "capability_mismatch",
                "candidate_capability": "inventory_kardex_consolidated",
                "fallback_detected": True,
                "metadata_used": False,
                "semantic_trace": {},
                "capability_pack": {},
            },
        )

        snapshot = self.service.build_operations_snapshot(limit=5)

        self.assertEqual(int((dict(snapshot.get("totales") or {})).get("brechas") or 0), 1)
        self.assertEqual(len(list(snapshot.get("brechas_nuevas") or [])), 1)

    def test_register_from_runtime_does_not_duplicate_equivalent_gap(self):
        response = _runtime_response(
            response_status="clarification_required",
            task_status="needs_input",
            clarification_required=True,
            clarification_question="Aclara si buscas por cedula, movil o codigo.",
            validation_satisfied=False,
            validation_reason="missing_structural_context",
        )

        first = self.service.register_from_runtime(response=response, run_context=self.run_context)
        self.run_context.run_id = "run-gap-2"
        second = self.service.register_from_runtime(response=response, run_context=self.run_context)

        self.assertTrue(bool(first.get("registrada")))
        self.assertFalse(bool(second.get("registrada")))
        self.assertTrue(bool(second.get("equivalente")))
        self.assertEqual(len(self.repo.rows_by_key), 1)
