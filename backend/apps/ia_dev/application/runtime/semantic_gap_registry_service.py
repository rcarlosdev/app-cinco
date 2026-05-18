from __future__ import annotations

from typing import Any

from apps.ia_dev.application.memory.repositories import MemoryRepository
from apps.ia_dev.application.workflow.task_state_service import TaskStateService
from apps.ia_dev.services.sql_store import IADevSqlStore


class SemanticGapRegistryService:
    SERVICE_VERSION = "continuous_runtime_learning.v1"
    ESTADO_REVISION_INICIAL = "nueva"
    CATEGORIAS_VALIDAS = {
        "falta_sinonimo",
        "falta_regla",
        "falta_relacion",
        "falta_campo",
        "falta_tabla",
        "falta_capacidad",
        "falta_tool",
        "falta_agente",
        "consulta_ambigua",
        "fuera_de_alcance",
        "evidencia_insuficiente",
        "bloqueo_correcto",
        "error_tecnico",
        "fallback_excesivo",
        "degradacion_semantica",
    }

    def __init__(self, *, repo: MemoryRepository | None = None) -> None:
        self.repo = repo or MemoryRepository()

    def register_from_runtime(
        self,
        *,
        response: dict[str, Any],
        run_context: Any,
    ) -> dict[str, Any]:
        payload = dict(response or {})
        task = dict(payload.get("task") or {})
        current_run = dict(task.get("current_run") or {})
        semantic_explanation = dict(current_run.get("semantic_explanation") or {})
        task_state = dict(payload.get("task_state") or {})
        task_state_data = dict(task_state.get("state") or {})
        runtime = dict(((payload.get("data_sources") or {}).get("runtime") or {}))
        business_response = dict((payload.get("data") or {}).get("business_response") or {})
        metadata = dict(business_response.get("metadata") or {})

        if not self._should_register_runtime_gap(
            semantic_explanation=semantic_explanation,
            task_state=task_state_data,
            runtime=runtime,
            metadata=metadata,
        ):
            return {"registrada": False, "motivo": "sin_brecha_accionable"}

        record = self._build_runtime_record(
            response=payload,
            run_context=run_context,
            semantic_explanation=semantic_explanation,
            task_state=task_state_data,
            runtime=runtime,
            metadata=metadata,
        )
        record["clave_idempotencia"] = IADevSqlStore.build_registro_brecha_clave_idempotencia(record)
        existing = self.repo.get_gap_record_by_idempotency(record["clave_idempotencia"])
        if existing:
            return {
                "registrada": False,
                "idempotente": True,
                "registro": existing,
            }
        equivalente = self.repo.find_equivalent_open_gap_record(record)
        if equivalente:
            return {
                "registrada": False,
                "equivalente": True,
                "registro": equivalente,
            }
        created = self.repo.create_gap_record(record)
        return {
            "registrada": True,
            "idempotente": False,
            "registro": created,
        }

    def register_from_eval_result(
        self,
        *,
        eval_result: dict[str, Any],
        dataset_version: str,
    ) -> dict[str, Any]:
        item = dict(eval_result or {})
        if str(item.get("eval_result") or "").strip().lower() != "failed":
            return {"registrada": False, "motivo": "eval_exitosa"}

        semantic_trace = dict(item.get("semantic_trace") or {})
        capability_pack = dict(item.get("capability_pack") or {})
        clasificacion = str(item.get("clasificacion") or "").strip().lower()
        categoria = "degradacion_semantica"
        etapa_fallo = "eval_p5"
        motivo = str(item.get("eval_reason") or "eval_failed").strip()
        falta_capacidad = False
        fallo_planner = False
        fallo_evidencia = False
        fallback_sombreado = bool(item.get("fallback_detected"))

        if clasificacion == "capability_incorrecta":
            categoria = "falta_capacidad"
            falta_capacidad = True
        elif clasificacion == "planner_incorrecto":
            categoria = "bloqueo_correcto"
            fallo_planner = True
        elif clasificacion == "evidence_inconsistente":
            categoria = "evidencia_insuficiente"
            fallo_evidencia = True
        elif fallback_sombreado:
            categoria = "fallback_excesivo"

        record = {
            "fecha_creacion": 0,
            "consulta_original": str(item.get("pregunta") or ""),
            "usuario_id": "",
            "sesion_id": f"eval:{dataset_version}",
            "task_id": f"eval:{dataset_version}:{str(item.get('case_id') or '').strip()}",
            "run_id": f"eval:{dataset_version}:{str(item.get('case_id') or '').strip()}",
            "dominio_detectado": "inventario_logistica",
            "intencion_detectada": str(item.get("grupo_semantico") or ""),
            "capacidad_candidata": str(item.get("candidate_capability") or ""),
            "herramienta_candidata": "query_execution_planner.sql_assisted",
            "etapa_fallo": etapa_fallo,
            "categoria_brecha": categoria,
            "motivo_brecha": motivo,
            "requiere_aclaracion": False,
            "fuera_de_alcance": False,
            "falta_metadata": not bool(item.get("metadata_used")),
            "faltan_tablas": False,
            "faltan_campos": False,
            "faltan_relaciones": False,
            "faltan_sinonimos": False,
            "faltan_reglas": False,
            "falta_capacidad": falta_capacidad,
            "falta_tool": False,
            "falta_agente": False,
            "fallo_planner": fallo_planner,
            "fallo_evidencia": fallo_evidencia,
            "fallo_validacion": False,
            "error_tecnico": False,
            "fallback_sombreado_usado": fallback_sombreado or bool(semantic_trace.get("fallback_sombreado_usado")),
            "evidencia_disponible": {
                "eval_result": str(item.get("eval_result") or ""),
                "eval_reason": motivo,
                "checks_failed": list(item.get("checks_failed") or []),
                "dataset_version": dataset_version,
                "semantic_trace": semantic_trace,
                "capability_pack": capability_pack,
            },
            "sugerencia_resolucion": self._build_suggestion(categoria),
            "prioridad": self._build_priority(
                categoria_brecha=categoria,
                error_tecnico=False,
                fuera_de_alcance=False,
                requiere_aclaracion=False,
                fallback_sombreado_usado=bool(semantic_trace.get("fallback_sombreado_usado")),
            ),
            "estado_revision": self.ESTADO_REVISION_INICIAL,
            "asignado_a": "",
            "fecha_resolucion": None,
            "tipo_resolucion": "",
            "referencia_metadata_creada": "",
            "referencia_capacidad_creada": "",
            "referencia_agente_creado": "",
            "origen_registro": "eval_p5",
            "metadata": {
                "service_version": self.SERVICE_VERSION,
                "dataset_version": dataset_version,
                "case_id": str(item.get("case_id") or ""),
                "response_status": str(item.get("response_status") or ""),
                "response_profile": str(item.get("response_profile") or ""),
                "flujo_revision": {
                    "estado_actual": self.ESTADO_REVISION_INICIAL,
                    "historial": [],
                    "propuesta_mejora": {},
                    "evaluaciones_vinculadas": [],
                    "casos_reales_reproducibles": [],
                },
            },
        }
        record["clave_idempotencia"] = IADevSqlStore.build_registro_brecha_clave_idempotencia(record)
        existing = self.repo.get_gap_record_by_idempotency(record["clave_idempotencia"])
        if existing:
            return {"registrada": False, "idempotente": True, "registro": existing}
        equivalente = self.repo.find_equivalent_open_gap_record(record)
        if equivalente:
            return {"registrada": False, "equivalente": True, "registro": equivalente}
        created = self.repo.create_gap_record(record)
        return {"registrada": True, "idempotente": False, "registro": created}

    def build_operations_snapshot(self, *, limit: int = 10) -> dict[str, Any]:
        return self.repo.summarize_gap_records(limit=limit)

    def _should_register_runtime_gap(
        self,
        *,
        semantic_explanation: dict[str, Any],
        task_state: dict[str, Any],
        runtime: dict[str, Any],
        metadata: dict[str, Any],
    ) -> bool:
        clarification = dict(semantic_explanation.get("clarification_needed") or {})
        final_state = dict(semantic_explanation.get("final_state") or {})
        validation_status = dict(semantic_explanation.get("validation_status") or {})
        fallback_used = dict(semantic_explanation.get("fallback_used") or {})
        response_status = str(final_state.get("response_status") or metadata.get("response_status") or "").strip().lower()
        task_status = str(final_state.get("task_status") or task_state.get("task_status") or "").strip().lower()
        block_reason = str(runtime.get("block_reason_code") or runtime.get("fallback_reason") or "").strip().lower()
        return any(
            [
                task_status == "blocked",
                bool(clarification.get("required")),
                response_status == "limitation_declared",
                bool(str(semantic_explanation.get("selected_capability") or "").strip()) and not bool(str(semantic_explanation.get("selected_tool") or "").strip()) and str(runtime.get("flow") or "").strip().lower() not in {"sql_assisted", "handler"},
                response_status in {"clarification_required", "blocked", "insufficient_evidence"},
                bool(fallback_used.get("shadow_fallback_used")),
                str(runtime.get("flow") or "").strip().lower() in {"controlled_runtime_limitation", "runtime_only_fallback"},
                bool(block_reason),
                not bool(validation_status.get("satisfied", True)),
            ]
        )

    def _build_runtime_record(
        self,
        *,
        response: dict[str, Any],
        run_context: Any,
        semantic_explanation: dict[str, Any],
        task_state: dict[str, Any],
        runtime: dict[str, Any],
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        clarification = dict(semantic_explanation.get("clarification_needed") or {})
        final_state = dict(semantic_explanation.get("final_state") or {})
        metadata_used = dict(semantic_explanation.get("metadata_used") or {})
        fallback_used = dict(semantic_explanation.get("fallback_used") or {})
        evidence_summary = dict(semantic_explanation.get("evidence_summary") or {})
        validation_status = dict(semantic_explanation.get("validation_status") or {})
        block_reason = str(runtime.get("block_reason_code") or runtime.get("fallback_reason") or "").strip().lower()

        categoria, etapa_fallo = self._classify_runtime_gap(
            clarification=clarification,
            final_state=final_state,
            metadata_used=metadata_used,
            fallback_used=fallback_used,
            evidence_summary=evidence_summary,
            validation_status=validation_status,
            runtime=runtime,
            selected_capability=str(semantic_explanation.get("selected_capability") or ""),
            selected_tool=str(semantic_explanation.get("selected_tool") or ""),
        )
        flags = self._derive_flags(
            categoria_brecha=categoria,
            clarification=clarification,
            final_state=final_state,
            metadata_used=metadata_used,
            fallback_used=fallback_used,
            runtime=runtime,
            block_reason=block_reason,
        )
        motivo_brecha = self._build_runtime_reason(
            categoria_brecha=categoria,
            clarification=clarification,
            final_state=final_state,
            validation_status=validation_status,
            runtime=runtime,
            fallback_used=fallback_used,
        )
        return {
            "fecha_creacion": 0,
            "consulta_original": str(semantic_explanation.get("user_question") or getattr(run_context, "message", "") or ""),
            "usuario_id": str((getattr(run_context, "metadata", {}) or {}).get("actor_user_key") or ""),
            "sesion_id": str(getattr(run_context, "session_id", "") or ""),
            "task_id": str(task_state.get("task_id") or TaskStateService.task_id_for_run(str(getattr(run_context, "run_id", "") or ""))),
            "run_id": str(getattr(run_context, "run_id", "") or ""),
            "dominio_detectado": str(semantic_explanation.get("domain") or ""),
            "intencion_detectada": str(semantic_explanation.get("intent") or ""),
            "capacidad_candidata": str(semantic_explanation.get("selected_capability") or ""),
            "herramienta_candidata": str(semantic_explanation.get("selected_tool") or ""),
            "etapa_fallo": etapa_fallo,
            "categoria_brecha": categoria,
            "motivo_brecha": motivo_brecha,
            "requiere_aclaracion": bool(clarification.get("required")),
            "fuera_de_alcance": bool(flags.get("fuera_de_alcance")),
            "falta_metadata": bool(flags.get("falta_metadata")),
            "faltan_tablas": bool(flags.get("faltan_tablas")),
            "faltan_campos": bool(flags.get("faltan_campos")),
            "faltan_relaciones": bool(flags.get("faltan_relaciones")),
            "faltan_sinonimos": bool(flags.get("faltan_sinonimos")),
            "faltan_reglas": bool(flags.get("faltan_reglas")),
            "falta_capacidad": bool(flags.get("falta_capacidad")),
            "falta_tool": bool(flags.get("falta_tool")),
            "falta_agente": bool(flags.get("falta_agente")),
            "fallo_planner": bool(flags.get("fallo_planner")),
            "fallo_evidencia": bool(flags.get("fallo_evidencia")),
            "fallo_validacion": bool(flags.get("fallo_validacion")),
            "error_tecnico": bool(flags.get("error_tecnico")),
            "fallback_sombreado_usado": bool(fallback_used.get("shadow_fallback_used")),
            "evidencia_disponible": {
                "semantic_explanation": semantic_explanation,
                "runtime": runtime,
                "task_status": str(task_state.get("task_status") or ""),
                "response_status": str(final_state.get("response_status") or ""),
                "metadata_used": bool(metadata_used.get("governed_used")),
                "response": {
                    "reply": str(response.get("reply") or ""),
                },
            },
            "sugerencia_resolucion": self._build_suggestion(categoria),
            "prioridad": self._build_priority(
                categoria_brecha=categoria,
                error_tecnico=bool(flags.get("error_tecnico")),
                fuera_de_alcance=bool(flags.get("fuera_de_alcance")),
                requiere_aclaracion=bool(clarification.get("required")),
                fallback_sombreado_usado=bool(fallback_used.get("shadow_fallback_used")),
            ),
            "estado_revision": self.ESTADO_REVISION_INICIAL,
            "asignado_a": "",
            "fecha_resolucion": None,
            "tipo_resolucion": "",
            "referencia_metadata_creada": "",
            "referencia_capacidad_creada": "",
            "referencia_agente_creado": "",
            "origen_registro": "runtime",
            "metadata": {
                "service_version": self.SERVICE_VERSION,
                "response_status": str(final_state.get("response_status") or ""),
                "task_status": str(final_state.get("task_status") or ""),
                "flow": str(runtime.get("flow") or ""),
                "block_reason_code": block_reason,
                "evaluaciones_asociadas": list(
                    (dict(semantic_explanation.get("capability_pack") or {})).get("evaluaciones_asociadas") or []
                ),
                "paquete_capacidad_usado": str(
                    (dict(semantic_explanation.get("capability_pack") or {})).get("paquete_capacidad_usado") or ""
                ),
                "metadata_gobernada_usada": bool(metadata_used.get("governed_used")),
                "semantic_explanation_disponible": True,
                "flujo_revision": {
                    "estado_actual": self.ESTADO_REVISION_INICIAL,
                    "historial": [],
                    "propuesta_mejora": {},
                    "evaluaciones_vinculadas": list(
                        (dict(semantic_explanation.get("capability_pack") or {})).get("evaluaciones_asociadas") or []
                    ),
                    "casos_reales_reproducibles": [],
                },
            },
        }

    def _classify_runtime_gap(
        self,
        *,
        clarification: dict[str, Any],
        final_state: dict[str, Any],
        metadata_used: dict[str, Any],
        fallback_used: dict[str, Any],
        evidence_summary: dict[str, Any],
        validation_status: dict[str, Any],
        runtime: dict[str, Any],
        selected_capability: str,
        selected_tool: str,
    ) -> tuple[str, str]:
        response_status = str(final_state.get("response_status") or "").strip().lower()
        flow = str(runtime.get("flow") or "").strip().lower()
        block_reason = str(runtime.get("block_reason_code") or "").strip().lower()
        if block_reason.startswith("chat_application_service_exception") or block_reason in {
            "timeout",
            "api_error",
            "openai_request_error",
        }:
            return ("error_tecnico", "runtime")
        if block_reason.startswith("unsupported_capability_domain"):
            return ("fuera_de_alcance", "semantic_capability_registry")
        if "missing_dictionary_relation" in block_reason or "relation" in block_reason or "join" in block_reason:
            return ("falta_relacion", "semantic_capability_registry")
        if "missing_dictionary_column" in block_reason or "column" in block_reason or "campo" in block_reason:
            return ("falta_campo", "semantic_capability_registry")
        if "table" in block_reason or "tabla" in block_reason:
            return ("falta_tabla", "semantic_capability_registry")
        if flow == "controlled_runtime_limitation" and response_status == "limitation_declared":
            return ("bloqueo_correcto", "runtime")
        if clarification.get("required"):
            return ("consulta_ambigua", "semantic_resolution")
        if not bool(validation_status.get("satisfied", True)) and response_status in {"", "clarification_required"}:
            return ("consulta_ambigua", "validation")
        if response_status == "limitation_declared":
            if not bool(metadata_used.get("governed_used")):
                return ("degradacion_semantica", "semantic_capability_registry")
            return ("bloqueo_correcto", "semantic_capability_registry")
        if not bool(str(selected_capability or runtime.get("capability") or "").strip()) and str(runtime.get("final_domain") or "").strip():
            return ("falta_capacidad", "semantic_capability_registry")
        if bool(str(selected_capability or runtime.get("capability") or "").strip()) and not bool(str(selected_tool or "").strip()):
            return ("falta_tool", "tool_registry")
        if fallback_used.get("shadow_fallback_used"):
            return ("fallback_excesivo", "semantic_capability_registry")
        if flow in {"runtime_only_fallback", "legacy_fallback"}:
            return ("degradacion_semantica", "runtime")
        if response_status == "insufficient_evidence" or (
            response_status in {"clarification_required", "blocked"}
            and bool(evidence_summary.get("result_empty"))
        ):
            return ("evidencia_insuficiente", "evidence")
        if str(runtime.get("block_reason_code") or "").strip():
            return ("bloqueo_correcto", "planner")
        if not bool(validation_status.get("satisfied", True)):
            return ("evidencia_insuficiente", "validation")
        return ("degradacion_semantica", "runtime")

    def _derive_flags(
        self,
        *,
        categoria_brecha: str,
        clarification: dict[str, Any],
        final_state: dict[str, Any],
        metadata_used: dict[str, Any],
        fallback_used: dict[str, Any],
        runtime: dict[str, Any],
        block_reason: str,
    ) -> dict[str, bool]:
        response_status = str(final_state.get("response_status") or "").strip().lower()
        falta_metadata = not bool(metadata_used.get("governed_used")) or categoria_brecha in {
            "falta_sinonimo",
            "falta_regla",
            "falta_relacion",
            "falta_campo",
            "falta_tabla",
        }
        return {
            "fuera_de_alcance": categoria_brecha == "fuera_de_alcance",
            "falta_metadata": falta_metadata,
            "faltan_tablas": "table" in block_reason or "tabla" in block_reason or categoria_brecha == "falta_tabla",
            "faltan_campos": "column" in block_reason or "campo" in block_reason or categoria_brecha == "falta_campo",
            "faltan_relaciones": "relation" in block_reason or "join" in block_reason or categoria_brecha == "falta_relacion",
            "faltan_sinonimos": categoria_brecha == "falta_sinonimo",
            "faltan_reglas": categoria_brecha == "falta_regla",
            "falta_capacidad": categoria_brecha == "falta_capacidad",
            "falta_tool": categoria_brecha == "falta_tool",
            "falta_agente": categoria_brecha == "falta_agente",
            "fallo_planner": categoria_brecha == "bloqueo_correcto" and bool(block_reason),
            "fallo_evidencia": categoria_brecha == "evidencia_insuficiente" or response_status == "insufficient_evidence",
            "fallo_validacion": not bool(clarification.get("required")) and not bool(
                dict(final_state or {}).get("task_status") == "completed"
            ),
            "error_tecnico": block_reason.startswith("chat_application_service_exception") or block_reason in {
                "timeout",
                "api_error",
                "openai_request_error",
            },
        }

    def _build_runtime_reason(
        self,
        *,
        categoria_brecha: str,
        clarification: dict[str, Any],
        final_state: dict[str, Any],
        validation_status: dict[str, Any],
        runtime: dict[str, Any],
        fallback_used: dict[str, Any],
    ) -> str:
        if categoria_brecha == "consulta_ambigua":
            return str(clarification.get("question") or validation_status.get("reason") or "missing_structural_context")
        if categoria_brecha in {"bloqueo_correcto", "fuera_de_alcance"}:
            return str(runtime.get("block_reason_code") or runtime.get("fallback_reason") or "blocked_without_safe_route")
        if categoria_brecha == "fallback_excesivo":
            return str(runtime.get("fallback_reason") or "fallback_sombreado_usado")
        if categoria_brecha == "evidencia_insuficiente":
            return str(validation_status.get("reason") or final_state.get("response_status") or "missing_evidence")
        if categoria_brecha == "degradacion_semantica":
            return str(runtime.get("flow") or "degradacion_semantica_detectada")
        if categoria_brecha == "falta_capacidad":
            return "candidate_capability_missing_or_incorrect"
        if categoria_brecha == "falta_tool":
            return "capability_without_registered_tool"
        if categoria_brecha == "error_tecnico":
            return str(runtime.get("block_reason_code") or "error_tecnico_controlado")
        if fallback_used.get("shadow_fallback_used"):
            return "fallback_sombreado_usado"
        return "brecha_runtime_accionable"

    def _build_suggestion(self, categoria_brecha: str) -> str:
        suggestions = {
            "falta_sinonimo": "Proponer nuevo sinonimo gobernado en dd_sinonimos. No aplicar automaticamente.",
            "falta_regla": "Proponer nueva regla gobernada en dd_reglas. No aplicar automaticamente.",
            "falta_relacion": "Proponer relacion gobernada en dd_relaciones. No aplicar automaticamente.",
            "falta_campo": "Proponer campo logico o metadata faltante en dd_campos. No aplicar automaticamente.",
            "falta_tabla": "Revisar si falta declarar la tabla fuente en ai_dictionary. No aplicar automaticamente.",
            "falta_capacidad": "Evaluar nueva capability o ajuste de binding en SemanticCapabilityRegistry. No aplicar automaticamente.",
            "falta_tool": "Evaluar binding capability -> tool en ToolRegistryService. No aplicar automaticamente.",
            "falta_agente": "Evaluar si hace falta un specialist agent o handoff dedicado. No aplicar automaticamente.",
            "consulta_ambigua": "Mejorar aclaracion de UX o sinonimia gobernada. No aplicar automaticamente.",
            "fuera_de_alcance": "Confirmar si la consulta queda fuera del alcance actual o requiere roadmap. No aplicar automaticamente.",
            "evidencia_insuficiente": "Revisar evidence plan, response profile o eval asociada. No aplicar automaticamente.",
            "bloqueo_correcto": "Mantener el bloqueo y revisar si falta metadata o capacidad gobernada. No aplicar automaticamente.",
            "error_tecnico": "Revisar manejo tecnico controlado y su trazabilidad. No aplicar automaticamente.",
            "fallback_excesivo": "Reducir fallback sombreado y reforzar metadata-first. No aplicar automaticamente.",
            "degradacion_semantica": "Revisar brecha entre metadata gobernada y fallback legacy. No aplicar automaticamente.",
        }
        return suggestions.get(categoria_brecha, "Revisar la brecha y proponer mejora gobernada. No aplicar automaticamente.")

    @staticmethod
    def _build_priority(
        *,
        categoria_brecha: str,
        error_tecnico: bool,
        fuera_de_alcance: bool,
        requiere_aclaracion: bool,
        fallback_sombreado_usado: bool,
    ) -> str:
        if error_tecnico or categoria_brecha in {"falta_capacidad", "falta_tool", "fallback_excesivo"}:
            return "alta"
        if fuera_de_alcance or requiere_aclaracion:
            return "media"
        if fallback_sombreado_usado or categoria_brecha in {"degradacion_semantica", "evidencia_insuficiente"}:
            return "media"
        return "baja"
