from __future__ import annotations

from copy import deepcopy

from django.test import SimpleTestCase

from apps.ia_dev.application.runtime.semantic_gap_review_service import SemanticGapReviewService


class _FakeGapRepo:
    def __init__(self):
        self.rows_by_id: dict[int, dict] = {}
        self.rows_by_key: dict[str, dict] = {}
        self._next_id = 1

    def get_gap_record_by_idempotency(self, idempotency_key: str):
        row = self.rows_by_key.get(idempotency_key)
        return deepcopy(row) if row else None

    def create_gap_record(self, payload: dict):
        item = deepcopy(payload)
        item["id"] = self._next_id
        self._next_id += 1
        self.rows_by_id[int(item["id"])] = deepcopy(item)
        self.rows_by_key[str(item.get("clave_idempotencia") or item["id"])] = deepcopy(item)
        return deepcopy(item)

    def get_gap_record(self, registro_id: int):
        row = self.rows_by_id.get(int(registro_id))
        return deepcopy(row) if row else None

    def update_gap_record(self, registro_id: int, updates: dict):
        current = self.rows_by_id.get(int(registro_id))
        if not current:
            return None
        merged = {**deepcopy(current), **deepcopy(updates)}
        self.rows_by_id[int(registro_id)] = deepcopy(merged)
        self.rows_by_key[str(merged.get("clave_idempotencia") or registro_id)] = deepcopy(merged)
        return deepcopy(merged)

    def list_gap_records(self, **kwargs):
        return [deepcopy(item) for item in self.rows_by_id.values()]


def _seed_gap(repo: _FakeGapRepo, *, brecha_id: int = 1, categoria: str = "falta_sinonimo") -> dict:
    payload = {
        "id": brecha_id,
        "fecha_creacion": 1710000000,
        "consulta_original": "que tiene juan perez",
        "usuario_id": "user:1",
        "sesion_id": "sess-1",
        "task_id": "task-1",
        "run_id": "run-1",
        "dominio_detectado": "inventario_logistica",
        "intencion_detectada": "stock_balance",
        "capacidad_candidata": "inventory_stock_balance_by_mobile",
        "herramienta_candidata": "query_execution_planner.sql_assisted",
        "etapa_fallo": "semantic_resolution",
        "categoria_brecha": categoria,
        "motivo_brecha": "missing_structural_context",
        "requiere_aclaracion": False,
        "fuera_de_alcance": False,
        "falta_metadata": True,
        "faltan_tablas": False,
        "faltan_campos": False,
        "faltan_relaciones": False,
        "faltan_sinonimos": categoria == "falta_sinonimo",
        "faltan_reglas": categoria == "falta_regla",
        "falta_capacidad": categoria == "falta_capacidad",
        "falta_tool": categoria == "falta_tool",
        "falta_agente": categoria == "falta_agente",
        "fallo_planner": False,
        "fallo_evidencia": False,
        "fallo_validacion": False,
        "error_tecnico": False,
        "fallback_sombreado_usado": False,
        "evidencia_disponible": {"reply": "respuesta"},
        "sugerencia_resolucion": "Proponer mejora gobernada",
        "prioridad": "media",
        "estado_revision": "nueva",
        "asignado_a": "",
        "fecha_resolucion": None,
        "tipo_resolucion": "",
        "referencia_metadata_creada": "",
        "referencia_capacidad_creada": "",
        "referencia_agente_creado": "",
        "clave_idempotencia": f"gap-{brecha_id}",
        "origen_registro": "runtime",
        "metadata": {
            "flujo_revision": {
                "estado_actual": "nueva",
                "historial": [],
                "propuesta_mejora": {},
                "evaluaciones_vinculadas": [],
                "casos_reales_reproducibles": [],
            }
        },
    }
    repo.rows_by_id[brecha_id] = deepcopy(payload)
    repo.rows_by_key[payload["clave_idempotencia"]] = deepcopy(payload)
    repo._next_id = max(repo._next_id, brecha_id + 1)
    return deepcopy(payload)


class SemanticGapReviewServiceTests(SimpleTestCase):
    def setUp(self):
        self.repo = _FakeGapRepo()
        _seed_gap(self.repo, brecha_id=1, categoria="falta_sinonimo")
        _seed_gap(self.repo, brecha_id=2, categoria="falta_regla")
        self.service = SemanticGapReviewService(repo=self.repo)

    def test_cambia_estado_a_en_revision_y_traza_revisor(self):
        result = self.service.marcar_en_revision(
            brecha_id=1,
            revisado_por="user:reviewer",
            asignado_a="equipo_semantica",
            comentario="Tomada para revision.",
        )

        self.assertEqual(str(result.get("estado_revision") or ""), "en_revision")
        self.assertEqual(str(result.get("asignado_a") or ""), "equipo_semantica")
        history = list((dict(result.get("metadata") or {}).get("flujo_revision") or {}).get("historial") or [])
        self.assertEqual(len(history), 1)
        self.assertEqual(str((history[0] or {}).get("revisado_por") or ""), "user:reviewer")

    def test_crea_propuesta_sensible_y_genera_approval_runtime(self):
        result = self.service.crear_propuesta(
            brecha_id=1,
            revisado_por="user:reviewer",
            tipo_propuesta="nuevo_sinonimo",
            descripcion="Agregar sinonimo cuadrilla -> movil.",
            destino_sugerido="dd_sinonimos",
            valor_sugerido={"termino": "movil", "sinonimo": "cuadrilla"},
            evidencia={"pregunta": "que tiene la cuadrilla TIRAN224"},
            riesgo="medio",
        )

        brecha = dict(result.get("brecha") or {})
        propuesta = dict(result.get("propuesta_mejora") or {})
        self.assertEqual(str(brecha.get("estado_revision") or ""), "requiere_sinonimo")
        self.assertTrue(bool(propuesta.get("requiere_aprobacion")))
        self.assertEqual(str(propuesta.get("estado_aprobacion") or ""), "pendiente")
        runtime = dict(propuesta.get("approval_runtime") or {})
        self.assertEqual(str(runtime.get("approval_status") or ""), "awaiting_approval")

    def test_aprueba_propuesta_y_actualiza_estado_aprobacion(self):
        self.service.crear_propuesta(
            brecha_id=1,
            revisado_por="user:reviewer",
            tipo_propuesta="nuevo_sinonimo",
            descripcion="Agregar sinonimo cuadrilla -> movil.",
            destino_sugerido="dd_sinonimos",
            valor_sugerido={"termino": "movil", "sinonimo": "cuadrilla"},
        )

        result = self.service.aprobar_propuesta(
            brecha_id=1,
            aprobado_por="user:governance",
            rol_aprobador="governance",
        )

        propuesta = dict(result.get("propuesta_mejora") or {})
        self.assertEqual(str(propuesta.get("estado_aprobacion") or ""), "aprobada")
        runtime = dict(propuesta.get("approval_runtime") or {})
        self.assertEqual(str(runtime.get("approval_status") or ""), "approved")

    def test_no_aplica_propuesta_sensible_sin_aprobacion(self):
        self.service.crear_propuesta(
            brecha_id=1,
            revisado_por="user:reviewer",
            tipo_propuesta="nuevo_tool",
            descripcion="Registrar tool gobernada.",
            destino_sugerido="ToolRegistryService",
            valor_sugerido={"tool_id": "inventory.new.tool"},
        )

        with self.assertRaisesMessage(ValueError, "aprobacion_requerida_para_aplicar"):
            self.service.aplicar_propuesta_gobernada(
                brecha_id=1,
                aplicado_por="user:reviewer",
                aplicado_en="tool_registry_service.py",
            )

    def test_marca_resuelta_y_vincula_prueba(self):
        result = self.service.marcar_resuelta(
            brecha_id=2,
            revisado_por="user:reviewer",
            decision="regla_documentada",
            prueba_validacion="inventario_runtime_eval_v1:case-22",
        )

        self.assertEqual(str(result.get("estado_revision") or ""), "resuelta")
        self.assertEqual(str(result.get("tipo_resolucion") or ""), "gobernada")
        flujo = dict((dict(result.get("metadata") or {}).get("flujo_revision") or {}))
        self.assertEqual(str(flujo.get("prueba_validacion") or ""), "inventario_runtime_eval_v1:case-22")

    def test_marca_descartada(self):
        result = self.service.marcar_descartada(
            brecha_id=2,
            revisado_por="user:reviewer",
            decision="duplicado_funcional",
            comentario="Ya cubierto por otra brecha.",
        )

        self.assertEqual(str(result.get("estado_revision") or ""), "descartada")
        self.assertEqual(str(result.get("tipo_resolucion") or ""), "descartada")

    def test_agrupa_por_categoria(self):
        grouped = self.service.agrupar_por_categoria(limit=10)
        labels = {str(item.get("categoria_brecha") or "") for item in grouped}
        self.assertIn("falta_sinonimo", labels)
        self.assertIn("falta_regla", labels)

    def test_vincula_eval_y_caso_real(self):
        result = self.service.vincular_eval(
            brecha_id=1,
            eval_id="inventario_runtime_eval_v1",
            vinculado_por="user:reviewer",
            caso_real_reproducible="chat:sess-1:run-1",
            eval_actualizado=True,
        )

        flujo = dict((dict(result.get("metadata") or {}).get("flujo_revision") or {}))
        self.assertIn("inventario_runtime_eval_v1", list(flujo.get("evaluaciones_vinculadas") or []))
        self.assertIn("chat:sess-1:run-1", list(flujo.get("casos_reales_reproducibles") or []))
