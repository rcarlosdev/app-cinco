from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from apps.ia_dev.application.context.run_context import RunContext
from apps.ia_dev.application.contracts.tool_contracts import (
    ToolApprovalPolicy,
    ToolDefinition,
    ToolExecutionPolicy,
)
from apps.ia_dev.application.memory.repositories import MemoryRepository
from apps.ia_dev.application.runtime.approval_runtime_service import ApprovalRuntimeService


class SemanticGapReviewService:
    SERVICE_VERSION = "semantic_gap_review.v1"
    ESTADOS_REVISION = {
        "nueva",
        "en_revision",
        "requiere_metadata",
        "requiere_sinonimo",
        "requiere_regla",
        "requiere_relacion",
        "requiere_capacidad",
        "requiere_tool",
        "requiere_agente",
        "requiere_aclaracion_usuario",
        "fuera_de_alcance",
        "resuelta",
        "descartada",
    }
    ESTADOS_FINALES = {"resuelta", "descartada"}
    TIPOS_PROPUESTA = {
        "nuevo_sinonimo",
        "nueva_regla",
        "nueva_relacion",
        "nueva_capacidad",
        "nuevo_tool",
        "nuevo_agente",
        "mejora_perfil_respuesta",
        "mejora_eval",
        "aclaracion_ux",
    }
    TIPOS_PROPUESTA_SENSIBLES = {
        "nuevo_sinonimo",
        "nueva_regla",
        "nueva_relacion",
        "nueva_capacidad",
        "nuevo_tool",
        "nuevo_agente",
    }
    TRANSICIONES = {
        "nueva": {
            "en_revision",
            "requiere_metadata",
            "requiere_sinonimo",
            "requiere_regla",
            "requiere_relacion",
            "requiere_capacidad",
            "requiere_tool",
            "requiere_agente",
            "requiere_aclaracion_usuario",
            "fuera_de_alcance",
            "descartada",
            "resuelta",
        },
        "en_revision": ESTADOS_REVISION - {"nueva"},
        "requiere_metadata": {"en_revision", "descartada", "resuelta"},
        "requiere_sinonimo": {"en_revision", "descartada", "resuelta"},
        "requiere_regla": {"en_revision", "descartada", "resuelta"},
        "requiere_relacion": {"en_revision", "descartada", "resuelta"},
        "requiere_capacidad": {"en_revision", "descartada", "resuelta"},
        "requiere_tool": {"en_revision", "descartada", "resuelta"},
        "requiere_agente": {"en_revision", "descartada", "resuelta"},
        "requiere_aclaracion_usuario": {"en_revision", "descartada", "resuelta"},
        "fuera_de_alcance": {"en_revision", "descartada", "resuelta"},
        "resuelta": set(),
        "descartada": set(),
    }

    def __init__(
        self,
        *,
        repo: MemoryRepository | None = None,
        approval_runtime_service: ApprovalRuntimeService | None = None,
    ) -> None:
        self.repo = repo or MemoryRepository()
        self.approval_runtime_service = approval_runtime_service or ApprovalRuntimeService()

    def listar_brechas_pendientes(self, *, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.repo.list_gap_records(limit=limit)
        return [row for row in rows if str(row.get("estado_revision") or "") not in self.ESTADOS_FINALES]

    def agrupar_por_categoria(self, *, limit: int = 100) -> list[dict[str, Any]]:
        counter: dict[str, int] = {}
        for row in self.repo.list_gap_records(limit=limit):
            categoria = str(row.get("categoria_brecha") or "")
            if categoria:
                counter[categoria] = int(counter.get(categoria, 0)) + 1
        return [
            {"categoria_brecha": key, "count": value}
            for key, value in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
        ]

    def ver_brechas_frecuentes(self, *, limit: int = 100) -> list[dict[str, Any]]:
        counter: dict[tuple[str, str], int] = {}
        for row in self.repo.list_gap_records(limit=limit):
            key = (
                str(row.get("categoria_brecha") or ""),
                str(row.get("motivo_brecha") or ""),
            )
            counter[key] = int(counter.get(key, 0)) + 1
        return [
            {"categoria_brecha": key[0], "motivo_brecha": key[1], "count": value}
            for key, value in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
        ]

    def obtener_brecha(self, brecha_id: int) -> dict[str, Any]:
        record = self.repo.get_gap_record(int(brecha_id))
        if not record:
            raise ValueError("brecha_no_encontrada")
        return record

    def marcar_en_revision(
        self,
        *,
        brecha_id: int,
        revisado_por: str,
        asignado_a: str = "",
        comentario: str = "",
    ) -> dict[str, Any]:
        return self._cambiar_estado(
            brecha_id=brecha_id,
            nuevo_estado="en_revision",
            revisado_por=revisado_por,
            asignado_a=asignado_a,
            decision="marcar_en_revision",
            comentario=comentario,
        )

    def marcar_descartada(
        self,
        *,
        brecha_id: int,
        revisado_por: str,
        decision: str,
        comentario: str = "",
    ) -> dict[str, Any]:
        return self._cambiar_estado(
            brecha_id=brecha_id,
            nuevo_estado="descartada",
            revisado_por=revisado_por,
            decision=decision or "descartar_brecha",
            comentario=comentario,
            tipo_resolucion="descartada",
            fecha_resolucion=self._now_ts(),
        )

    def marcar_resuelta(
        self,
        *,
        brecha_id: int,
        revisado_por: str,
        decision: str,
        comentario: str = "",
        prueba_validacion: str = "",
    ) -> dict[str, Any]:
        return self._cambiar_estado(
            brecha_id=brecha_id,
            nuevo_estado="resuelta",
            revisado_por=revisado_por,
            decision=decision or "resolver_brecha",
            comentario=comentario,
            tipo_resolucion="gobernada",
            fecha_resolucion=self._now_ts(),
            metadata_extra={
                "flujo_revision": {
                    "prueba_validacion": str(prueba_validacion or ""),
                }
            },
        )

    def crear_propuesta(
        self,
        *,
        brecha_id: int,
        revisado_por: str,
        tipo_propuesta: str,
        descripcion: str,
        destino_sugerido: str,
        valor_sugerido: Any,
        evidencia: dict[str, Any] | None = None,
        riesgo: str = "medio",
    ) -> dict[str, Any]:
        record = self.obtener_brecha(brecha_id)
        normalized_type = str(tipo_propuesta or "").strip().lower()
        if normalized_type not in self.TIPOS_PROPUESTA:
            raise ValueError("tipo_propuesta_no_valido")
        requiere_aprobacion = normalized_type in self.TIPOS_PROPUESTA_SENSIBLES
        approval_runtime: dict[str, Any] = {}
        estado_aprobacion = "no_requerida"
        if requiere_aprobacion:
            approval_runtime = self._build_runtime_approval(
                record=record,
                tipo_propuesta=normalized_type,
                revisado_por=revisado_por,
                evidencia=evidencia or {},
            )
            estado_aprobacion = "pendiente"
        propuesta = {
            "tipo_propuesta": normalized_type,
            "descripcion": str(descripcion or ""),
            "destino_sugerido": str(destino_sugerido or ""),
            "valor_sugerido": valor_sugerido,
            "evidencia": dict(evidencia or {}),
            "riesgo": str(riesgo or "medio"),
            "requiere_aprobacion": requiere_aprobacion,
            "estado_aprobacion": estado_aprobacion,
            "aplicado_en": "",
            "validado_por_eval": False,
            "approval_runtime": approval_runtime,
            "creado_por": str(revisado_por or ""),
            "creado_en": self._now_iso(),
        }
        next_state = self._estado_requerido_por_propuesta(normalized_type)
        updated = self._cambiar_estado(
            brecha_id=brecha_id,
            nuevo_estado=next_state,
            revisado_por=revisado_por,
            decision="crear_propuesta_gobernada",
            comentario=str(descripcion or ""),
            metadata_extra={"flujo_revision": {"propuesta_mejora": propuesta}},
        )
        return {"brecha": updated, "propuesta_mejora": propuesta}

    def aprobar_propuesta(
        self,
        *,
        brecha_id: int,
        aprobado_por: str,
        rol_aprobador: str,
        evidencia_post_aprobacion: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        record = self.obtener_brecha(brecha_id)
        propuesta = self._propuesta_de(record)
        if not propuesta:
            raise ValueError("propuesta_no_encontrada")
        if not bool(propuesta.get("requiere_aprobacion")):
            propuesta["estado_aprobacion"] = "no_requerida"
            return self._guardar_propuesta(
                record=record,
                propuesta=propuesta,
                revisado_por=aprobado_por,
                decision="confirmar_propuesta_sin_aprobacion",
            )
        runtime = dict(propuesta.get("approval_runtime") or {})
        approvals = list(runtime.get("approvals") or [])
        if not approvals:
            raise ValueError("approval_runtime_no_disponible")
        approved = self.approval_runtime_service.approve_request(
            request=dict(approvals[0] or {}),
            approved_by=aprobado_por,
            approver_role=rol_aprobador,
            evidence_after_approval=evidencia_post_aprobacion or {},
        )
        propuesta["estado_aprobacion"] = "aprobada" if str((approved.get("approval") or {}).get("approval_status") or "") == "approved" else "rechazada"
        propuesta["approval_runtime"] = {
            **runtime,
            "approval_status": str((approved.get("approval") or {}).get("approval_status") or ""),
            "approvals": [dict(approved.get("approval") or {})],
            "approval_trace": [*list(runtime.get("approval_trace") or []), dict(approved.get("approval_trace") or {})],
        }
        return self._guardar_propuesta(
            record=record,
            propuesta=propuesta,
            revisado_por=aprobado_por,
            decision="aprobar_propuesta",
        )

    def aplicar_propuesta_gobernada(
        self,
        *,
        brecha_id: int,
        aplicado_por: str,
        aplicado_en: str,
        referencia_metadata_creada: str = "",
        referencia_capacidad_creada: str = "",
        referencia_agente_creado: str = "",
        prueba_validacion: str = "",
        validado_por_eval: bool = False,
    ) -> dict[str, Any]:
        record = self.obtener_brecha(brecha_id)
        propuesta = self._propuesta_de(record)
        if not propuesta:
            raise ValueError("propuesta_no_encontrada")
        if bool(propuesta.get("requiere_aprobacion")) and str(propuesta.get("estado_aprobacion") or "") != "aprobada":
            raise ValueError("aprobacion_requerida_para_aplicar")
        propuesta["aplicado_en"] = str(aplicado_en or "")
        propuesta["validado_por_eval"] = bool(validado_por_eval)
        updated = self._cambiar_estado(
            brecha_id=brecha_id,
            nuevo_estado="resuelta",
            revisado_por=aplicado_por,
            decision="aplicar_propuesta_gobernada",
            comentario=str(aplicado_en or ""),
            tipo_resolucion="gobernada",
            fecha_resolucion=self._now_ts(),
            referencia_metadata_creada=referencia_metadata_creada,
            referencia_capacidad_creada=referencia_capacidad_creada,
            referencia_agente_creado=referencia_agente_creado,
            metadata_extra={
                "flujo_revision": {
                    "propuesta_mejora": propuesta,
                    "prueba_validacion": str(prueba_validacion or ""),
                }
            },
        )
        return {"brecha": updated, "propuesta_mejora": propuesta}

    def vincular_eval(
        self,
        *,
        brecha_id: int,
        eval_id: str,
        vinculado_por: str,
        caso_real_reproducible: str = "",
        eval_actualizado: bool = False,
    ) -> dict[str, Any]:
        record = self.obtener_brecha(brecha_id)
        metadata = self._metadata_review(record)
        evaluaciones = list(metadata.get("evaluaciones_vinculadas") or [])
        if eval_id and eval_id not in evaluaciones:
            evaluaciones.append(str(eval_id))
        casos_reales = list(metadata.get("casos_reales_reproducibles") or [])
        if caso_real_reproducible and caso_real_reproducible not in casos_reales:
            casos_reales.append(str(caso_real_reproducible))
        return self._cambiar_estado(
            brecha_id=brecha_id,
            nuevo_estado=str(record.get("estado_revision") or "nueva"),
            revisado_por=vinculado_por,
            decision="vincular_eval",
            comentario=str(eval_id or ""),
            metadata_extra={
                "flujo_revision": {
                    "evaluaciones_vinculadas": evaluaciones,
                    "casos_reales_reproducibles": casos_reales,
                    "eval_actualizado": bool(eval_actualizado),
                }
            },
        )

    def build_operations_snapshot(self, *, limit: int = 50) -> dict[str, Any]:
        rows = self.repo.list_gap_records(limit=limit)
        return {
            "brechas_pendientes": self.listar_brechas_pendientes(limit=limit),
            "brechas_por_categoria": self.agrupar_por_categoria(limit=limit),
            "brechas_frecuentes": self.ver_brechas_frecuentes(limit=limit),
            "totales": {
                "brechas": len(rows),
                "pendientes": sum(
                    1
                    for row in rows
                    if str(row.get("estado_revision") or "") not in self.ESTADOS_FINALES
                ),
                "resueltas": sum(
                    1 for row in rows if str(row.get("estado_revision") or "") == "resuelta"
                ),
                "descartadas": sum(
                    1 for row in rows if str(row.get("estado_revision") or "") == "descartada"
                ),
            },
        }

    def _cambiar_estado(
        self,
        *,
        brecha_id: int,
        nuevo_estado: str,
        revisado_por: str,
        decision: str,
        comentario: str = "",
        asignado_a: str | None = None,
        tipo_resolucion: str | None = None,
        fecha_resolucion: int | None = None,
        referencia_metadata_creada: str | None = None,
        referencia_capacidad_creada: str | None = None,
        referencia_agente_creado: str | None = None,
        metadata_extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        record = self.obtener_brecha(brecha_id)
        current_state = str(record.get("estado_revision") or "nueva")
        target_state = str(nuevo_estado or "").strip().lower()
        if target_state not in self.ESTADOS_REVISION:
            raise ValueError("estado_revision_no_valido")
        if target_state != current_state and target_state not in self.TRANSICIONES.get(current_state, set()):
            raise ValueError("transicion_estado_no_valida")
        metadata = dict(record.get("metadata") or {})
        flujo = self._metadata_review(record)
        historial = list(flujo.get("historial") or [])
        historial.append(
            {
                "estado_anterior": current_state,
                "estado_nuevo": target_state,
                "revisado_por": str(revisado_por or ""),
                "fecha": self._now_iso(),
                "decision": str(decision or ""),
                "comentario": str(comentario or ""),
            }
        )
        merged_review = {
            **flujo,
            **dict((metadata_extra or {}).get("flujo_revision") or {}),
            "estado_actual": target_state,
            "ultimo_revisor": str(revisado_por or ""),
            "ultima_decision": str(decision or ""),
            "historial": historial,
        }
        metadata["review_service_version"] = self.SERVICE_VERSION
        metadata["flujo_revision"] = merged_review
        updates = {
            "estado_revision": target_state,
            "metadata": metadata,
        }
        if asignado_a is not None:
            updates["asignado_a"] = str(asignado_a or "")
        if tipo_resolucion is not None:
            updates["tipo_resolucion"] = str(tipo_resolucion or "")
        if fecha_resolucion is not None:
            updates["fecha_resolucion"] = int(fecha_resolucion or 0) or None
        if referencia_metadata_creada is not None:
            updates["referencia_metadata_creada"] = str(referencia_metadata_creada or "")
        if referencia_capacidad_creada is not None:
            updates["referencia_capacidad_creada"] = str(referencia_capacidad_creada or "")
        if referencia_agente_creado is not None:
            updates["referencia_agente_creado"] = str(referencia_agente_creado or "")
        updated = self.repo.update_gap_record(int(brecha_id), updates)
        if not updated:
            raise ValueError("brecha_no_encontrada")
        return updated

    def _guardar_propuesta(
        self,
        *,
        record: dict[str, Any],
        propuesta: dict[str, Any],
        revisado_por: str,
        decision: str,
    ) -> dict[str, Any]:
        return {
            "brecha": self._cambiar_estado(
                brecha_id=int(record.get("id") or 0),
                nuevo_estado=str(record.get("estado_revision") or "nueva"),
                revisado_por=revisado_por,
                decision=decision,
                metadata_extra={"flujo_revision": {"propuesta_mejora": propuesta}},
            ),
            "propuesta_mejora": propuesta,
        }

    def _build_runtime_approval(
        self,
        *,
        record: dict[str, Any],
        tipo_propuesta: str,
        revisado_por: str,
        evidencia: dict[str, Any],
    ) -> dict[str, Any]:
        run_context = RunContext.create(
            message=f"aplicar_propuesta_brecha:{int(record.get('id') or 0)}",
            session_id=str(record.get("sesion_id") or f"gap-review:{int(record.get('id') or 0)}"),
            reset_memory=False,
        )
        run_context.run_id = str(record.get("run_id") or f"gap-review-{int(record.get('id') or 0)}")
        tool_definition = ToolDefinition(
            tool_id="semantic_gap_review.apply_proposal",
            capability_id=f"semantic_gap_review.{tipo_propuesta}",
            domain=str(record.get("dominio_detectado") or "runtime"),
            handler_key="semantic_gap_review_service",
            title="Aplicar propuesta gobernada de brecha",
            description="Aplica una mejora gobernada sobre metadata, capability, tool o agente.",
            execution_policy=ToolExecutionPolicy(
                mode="governed",
                runtime_authority="semantic_gap_review_service",
                idempotent=True,
            ),
            approval_policy=ToolApprovalPolicy(
                mode="manual",
                approval_required=True,
                reason=f"aprobacion_requerida_para_{tipo_propuesta}",
                approval_type="human_review",
                required_role="governance",
                risk_level="high",
            ),
        )
        approval = self.approval_runtime_service.evaluate_tool_execution(
            run_context=run_context,
            tool_definition=tool_definition,
            requested_by_agent=str(revisado_por or "semantic_gap_review"),
            target_action=f"aplicar_{tipo_propuesta}",
            evidence_before_approval={
                "brecha_id": int(record.get("id") or 0),
                "categoria_brecha": str(record.get("categoria_brecha") or ""),
                "tipo_propuesta": tipo_propuesta,
                "evidencia": dict(evidencia or {}),
            },
        )
        return approval

    def _estado_requerido_por_propuesta(self, tipo_propuesta: str) -> str:
        mapping = {
            "nuevo_sinonimo": "requiere_sinonimo",
            "nueva_regla": "requiere_regla",
            "nueva_relacion": "requiere_relacion",
            "nueva_capacidad": "requiere_capacidad",
            "nuevo_tool": "requiere_tool",
            "nuevo_agente": "requiere_agente",
            "mejora_perfil_respuesta": "en_revision",
            "mejora_eval": "en_revision",
            "aclaracion_ux": "requiere_aclaracion_usuario",
        }
        return mapping.get(tipo_propuesta, "en_revision")

    @staticmethod
    def _propuesta_de(record: dict[str, Any]) -> dict[str, Any]:
        return dict(
            ((dict(record.get("metadata") or {}).get("flujo_revision") or {}).get("propuesta_mejora") or {})
        )

    @staticmethod
    def _metadata_review(record: dict[str, Any]) -> dict[str, Any]:
        metadata = dict(record.get("metadata") or {})
        base = dict(metadata.get("flujo_revision") or {})
        return {
            "estado_actual": str(base.get("estado_actual") or record.get("estado_revision") or "nueva"),
            "historial": list(base.get("historial") or []),
            "propuesta_mejora": dict(base.get("propuesta_mejora") or {}),
            "evaluaciones_vinculadas": list(base.get("evaluaciones_vinculadas") or []),
            "casos_reales_reproducibles": list(base.get("casos_reales_reproducibles") or []),
            "ultimo_revisor": str(base.get("ultimo_revisor") or ""),
            "ultima_decision": str(base.get("ultima_decision") or ""),
        }

    @staticmethod
    def _now_ts() -> int:
        return int(datetime.now(timezone.utc).timestamp())

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()
