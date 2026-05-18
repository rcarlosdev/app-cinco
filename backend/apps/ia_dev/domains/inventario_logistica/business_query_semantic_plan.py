from __future__ import annotations

from typing import Any

from apps.ia_dev.application.contracts.query_intelligence_contracts import (
    BusinessQuerySemanticEntity,
    BusinessQuerySemanticExecution,
    BusinessQuerySemanticOutput,
    BusinessQuerySemanticPlan,
    BusinessQuerySemanticScope,
)
from apps.ia_dev.application.memory.repositories import MemoryRepository
from apps.ia_dev.application.semantic.semantic_capability_registry import (
    SemanticBindingRequest,
    SemanticCapabilityRegistry,
)


INVENTORY_SEMANTIC_MATRIX: list[dict[str, Any]] = [
    {
        "family": "saldo_empleado",
        "triggers": ["saldo", "empleado|tecnico", "cedula"],
        "domain": "inventario_logistica",
        "intent": "stock_balance",
        "capability": "inventory_stock_balance_by_mobile",
        "entity_type": "empleado",
        "identifier_field": "cedula",
        "output_grain": "saldo_por_codigo",
        "include_serialized": False,
        "rules": [
            "empleado_tecnico_numerico_es_cedula",
            "saldo_incluye_positivos_cero_negativos",
        ],
    },
    {
        "family": "saldo_movil",
        "triggers": ["saldo", "movil|cuadrilla", "alfanumerico"],
        "domain": "inventario_logistica",
        "intent": "stock_balance",
        "capability": "inventory_stock_balance_by_mobile",
        "entity_type": "movil",
        "identifier_field": "movil",
        "output_grain": "saldo_por_codigo_y_empleado",
        "include_serialized": True,
        "rules": [
            "movil_alfanumerica_se_resuelve_en_personal",
            "inventario_generico_incluye_materiales_y_serializados",
        ],
    },
    {
        "family": "kardex_empleado",
        "triggers": ["kardex|movimientos|entradas y salidas", "empleado|tecnico", "cedula"],
        "domain": "inventario_logistica",
        "intent": "movement_history",
        "capability": "inventory_kardex_by_employee",
        "entity_type": "empleado",
        "identifier_field": "cedula",
        "output_grain": "movimiento_por_codigo",
        "include_serialized": False,
        "rules": [
            "kardex_equivale_a_movimientos_y_saldos_por_codigo",
            "empleado_tecnico_numerico_es_cedula",
        ],
    },
    {
        "family": "kardex_codigo",
        "triggers": ["kardex|movimientos", "codigo"],
        "domain": "inventario_logistica",
        "intent": "movement_history",
        "capability": "inventory_kardex_consolidated",
        "entity_type": "codigo",
        "identifier_field": "codigo",
        "output_grain": "movimiento_por_fecha_y_codigo",
        "include_serialized": False,
        "rules": ["kardex_equivale_a_movimientos_y_saldos_por_codigo"],
    },
    {
        "family": "serializados",
        "triggers": ["serial|seriales|equipos|cpe"],
        "domain": "inventario_logistica",
        "intent": "serial_holder_query",
        "capability": "inventory_serial_by_operational_holder",
        "entity_type": "serial",
        "identifier_field": "serial",
        "output_grain": "serial_por_codigo_y_estado",
        "include_serialized": True,
        "rules": ["serializados_usan_conteo_no_cantidad"],
    },
]


CONFIRMED_INVENTORY_MEMORY_RULES: list[dict[str, Any]] = [
    {
        "memory_key": "inventory.semantic.rule.material_claro",
        "capability_id": "inventory_semantic_layer",
        "memory_value": {
            "aliases": ["material claro", "material de claro"],
            "normalized_filter": {"tipo": "material"},
            "business_label": "Material Claro",
        },
    },
    {
        "memory_key": "inventory.semantic.rule.ferretero",
        "capability_id": "inventory_semantic_layer",
        "memory_value": {
            "aliases": ["ferretero", "material ferretero"],
            "normalized_filter": {"tipo": "ferretero"},
            "business_label": "Ferretero",
        },
    },
    {
        "memory_key": "inventory.semantic.rule.material_generico",
        "capability_id": "inventory_semantic_layer",
        "memory_value": {
            "aliases": ["material", "material generico"],
            "normalized_filter": {"tipo": ["material", "ferretero"]},
            "business_label": "Material Claro / Ferretero",
        },
    },
    {
        "memory_key": "inventory.semantic.rule.saldo_inventario",
        "capability_id": "inventory_stock_balance_by_mobile",
        "memory_value": {
            "rule": "saldo de inventario debe incluir positivos, cero y negativos",
            "enforced": True,
        },
    },
    {
        "memory_key": "inventory.semantic.rule.kardex",
        "capability_id": "inventory_kardex_by_employee",
        "memory_value": {
            "aliases": ["kardex", "movimientos dia a dia", "entradas y salidas"],
            "output_grain": "movimiento_por_codigo",
        },
    },
    {
        "memory_key": "inventory.semantic.rule.kardex_empleado",
        "capability_id": "inventory_kardex_by_employee",
        "memory_value": {
            "pattern": "empleado|tecnico + numero",
            "normalized_entity": {"type": "empleado", "field": "cedula"},
        },
    },
    {
        "memory_key": "inventory.semantic.rule.movil_cuadrilla",
        "capability_id": "inventory_stock_balance_by_mobile",
        "memory_value": {
            "pattern": "cuadrilla|movil + valor alfanumerico",
            "normalized_entity": {"type": "movil", "field": "movil"},
        },
    },
    {
        "memory_key": "inventory.semantic.rule.inventario_generico",
        "capability_id": "inventory_stock_balance_by_mobile",
        "memory_value": {
            "rule": "inventario generico incluye materiales, ferretero y serializados cuando aplique",
            "include_serialized": True,
        },
    },
    {
        "memory_key": "inventory.semantic.rule.enrichment_historico",
        "capability_id": "inventory_stock_balance_by_mobile",
        "memory_value": {
            "rule": "empleados no deben excluirse por estado ACTIVO en enrichment historico",
            "enforced": True,
        },
    },
    {
        "memory_key": "inventory.semantic.rule.serializados",
        "capability_id": "inventory_serial_by_operational_holder",
        "memory_value": {
            "rule": "serializados no usan cantidad; usan conteo",
            "enforced": True,
        },
    },
    {
        "memory_key": "inventory.semantic.rule.gpt_semantiza_planner_ejecuta",
        "capability_id": "inventory_semantic_layer",
        "memory_value": {
            "rule": "GPT semantiza, planner ejecuta",
            "execute_authority": "QueryExecutionPlanner",
        },
    },
]


class InventorySemanticMemoryService:
    def __init__(self, *, repository: MemoryRepository | None = None):
        self.repository = repository or MemoryRepository()
        self._snapshot_cache: list[dict[str, Any]] | None = None
        self._seed_status: dict[str, Any] | None = None

    def list_memory_snapshot(self) -> list[dict[str, Any]]:
        if self._snapshot_cache is not None:
            return list(self._snapshot_cache)
        try:
            self._snapshot_cache = self.repository.get_business_memory(
                domain_code="inventario_logistica",
                memory_key_prefix="inventory.semantic.",
                limit=100,
            )
        except Exception:
            self._snapshot_cache = []
        return list(self._snapshot_cache)

    def ensure_confirmed_rules(self) -> dict[str, Any]:
        if self._seed_status is not None:
            return dict(self._seed_status)
        saved: list[str] = []
        errors: list[str] = []
        for item in CONFIRMED_INVENTORY_MEMORY_RULES:
            key = str(item.get("memory_key") or "").strip()
            capability_id = str(item.get("capability_id") or "inventory_semantic_layer").strip()
            if not key:
                continue
            try:
                self.repository.set_business_memory(
                    domain_code="inventario_logistica",
                    capability_id=capability_id,
                    memory_key=key,
                    memory_value=dict(item.get("memory_value") or {}),
                    source_type="system_seed",
                    approved_by="system_semantic_inventory",
                )
                self.repository.add_audit_event(
                    event_type="inventory_semantic_memory_seed",
                    memory_scope="business",
                    entity_key=f"inventario_logistica:{capability_id}:{key}",
                    action="upsert",
                    actor_type="system",
                    actor_key="system_semantic_inventory",
                    after={"memory_key": key, "capability_id": capability_id},
                    meta={"source": "inventory_semantic_layer"},
                )
                saved.append(key)
            except Exception as exc:
                errors.append(f"{key}:{exc}")
        self._seed_status = {
            "saved_keys": saved,
            "error_count": len(errors),
            "errors": errors,
        }
        self._snapshot_cache = None
        return dict(self._seed_status)


class InventoryBusinessQueryPlanner:
    def __init__(self, *, memory_service: InventorySemanticMemoryService | None = None):
        self.memory_service = memory_service or InventorySemanticMemoryService()
        self.semantic_capability_registry = SemanticCapabilityRegistry()

    def build_plan(
        self,
        *,
        message: str,
        inference: dict[str, Any],
        template_id: str,
        semantic_context: dict[str, Any],
        binding_decision: dict[str, Any] | None = None,
    ) -> BusinessQuerySemanticPlan:
        filters = dict(inference.get("filters") or {})
        group_by = [str(item or "") for item in list(inference.get("group_by") or []) if str(item or "").strip()]
        entity = self._build_entity(filters=filters, semantic_context=semantic_context)
        families = self._resolve_scope_families(filters=filters, inference=inference, message=message)
        include_serialized = self._should_include_serialized(filters=filters, inference=inference, message=message)
        known_limitations = [str(item or "") for item in list(inference.get("limitations") or []) if str(item or "").strip()]
        consulted_sources = [
            "ai_dictionary.dd_reglas",
            "ai_dictionary.dd_sinonimos",
            "ai_dictionary.dd_relaciones",
            "ai_dictionary.dd_campos",
            "ai_dictionary.dd_tablas",
            "ai_dictionary.dd_capacidades_campo",
            "ai_dictionary.ia_dev_capacidades_columna",
            "ai_dictionary.ia_dev_business_memory",
        ]
        memory_snapshot = self.memory_service.list_memory_snapshot()
        semantic_context = dict(semantic_context or {})
        semantic_context["semantic_memory_snapshot"] = list(memory_snapshot or [])
        memory_keys_used = [
            str(item.get("memory_key") or "")
            for item in memory_snapshot
            if isinstance(item, dict) and str(item.get("memory_key") or "").startswith("inventory.semantic.")
        ]
        binding = dict(binding_decision or {})
        if not binding:
            binding = self.semantic_capability_registry.resolve(
                SemanticBindingRequest(
                    domain="inventario_logistica",
                    message=message,
                    intent=str(inference.get("intent") or ""),
                    entity=entity,
                    normalized_filters=filters,
                    group_by=group_by,
                    semantic_context=semantic_context,
                    source_hints={
                        "template_id": template_id,
                        "inventory_inference": dict(inference or {}),
                        "governed_match": dict(inference.get("governed_match") or {}),
                        "memory_keys_used": memory_keys_used,
                    },
                )
            ).as_dict()
        capability = str(binding.get("candidate_capability") or self._resolve_capability(template_id=template_id, inference=inference) or "")
        output_profile = dict(binding.get("output_profile") or {})
        output_columns = [str(item or "") for item in list(output_profile.get("columns") or []) if str(item or "").strip()]
        grain = str(output_profile.get("grain") or "").strip()
        if not output_columns or not grain:
            output_columns, grain = self._resolve_output_profile(
                capability=capability,
                inference=inference,
                include_serialized=include_serialized,
            )
        if capability == "inventory_kardex_by_employee":
            known_limitations.append("serializados_employee_kardex_not_available")
        if bool(binding.get("legacy_mapping_used")):
            known_limitations.append("legacy_semantic_binding_shadowed")
        return BusinessQuerySemanticPlan(
            query=str(message or ""),
            domain="inventario_logistica",
            intent=str(inference.get("intent") or ""),
            main_entity=entity,
            governed_physical_field=str(entity.physical_field or entity.field or ""),
            grouping_dimension=group_by,
            inventory_family=str(inference.get("material_family") or self._inventory_family_from_scope(families)),
            scope=BusinessQuerySemanticScope(
                families=families,
                include_serialized=include_serialized,
                stock_scope=str(filters.get("stock_scope") or ""),
                group_dimensions=group_by,
                coverage=self._resolve_coverage(filters=filters, entity=entity),
            ),
            output=BusinessQuerySemanticOutput(
                expected_output=str(
                    output_profile.get("expected_output")
                    or self._expected_output_for_capability(capability=capability)
                ),
                grain=grain,
                columns=output_columns,
            ),
            candidate_capability=capability,
            normalized_filters=filters,
            requires_enrichment=self._requires_enrichment(capability=capability, entity=entity, include_serialized=include_serialized),
            applicable_business_rules=self._applicable_rules(filters=filters, inference=inference, capability=capability, include_serialized=include_serialized),
            possible_alerts=self._possible_alerts(capability=capability, inference=inference, include_serialized=include_serialized),
            known_limitations=list(dict.fromkeys(known_limitations)),
            execution=BusinessQuerySemanticExecution(
                capability=capability,
                requires_sql_planner=True,
            ),
            ambiguity_notes=self._ambiguity_notes(filters=filters, inference=inference),
            consulted_sources=consulted_sources,
            memory_keys_used=memory_keys_used,
            llm_policy={
                "eligible": bool(self._ambiguity_notes(filters=filters, inference=inference)),
                "allowed_tasks": [
                    "interpret_intent",
                    "detect_ambiguity",
                    "organize_filters",
                    "suggest_capability",
                    "draft_business_summary",
                ],
                "forbidden_tasks": [
                    "generate_free_sql",
                    "invent_columns",
                    "invent_tables",
                    "decide_execute_true",
                ],
                "authority": "deterministic_and_dictionary_first",
                "semantic_binding": {
                    "template_id": str(binding.get("template_id") or template_id or ""),
                    "planner_route_hint": str(binding.get("planner_route_hint") or ""),
                    "response_profile": str(binding.get("response_profile") or ""),
                    "tool_id": str(binding.get("tool_id") or ""),
                    "source": str(binding.get("source") or ""),
                    "matched_rules": list(binding.get("matched_rules") or []),
                    "confidence": float(binding.get("confidence") or 0.0),
                    "fallback_used": bool(binding.get("fallback_used")),
                    "legacy_mapping_used": bool(binding.get("legacy_mapping_used")),
                },
            },
        )

    @staticmethod
    def _resolve_capability(*, template_id: str, inference: dict[str, Any]) -> str:
        explicit = str(template_id or "").strip()
        if explicit:
            mapping = {
                "inventory_material_stock_mobile": "inventory_stock_balance_by_mobile",
                "inventory_material_stock_by_warehouse": "inventory_material_stock_by_warehouse",
                "inventory_material_stock_balance": "inventory_stock_balance",
                "inventory_kardex_by_employee": "inventory_kardex_by_employee",
                "inventory_kardex_consolidated": "inventory_kardex_consolidated",
                "inventory_serial_by_operational_holder": "inventory_serial_by_operational_holder",
                "inventory_traceability_by_serial": "inventory_traceability_by_serial",
                "inventory_material_critical_by_employee": "inventory_stock_balance_by_mobile",
                "inventory_serial_stock_by_dimension": "inventory_serial_stock_by_dimension",
            }
            return str(mapping.get(explicit, explicit))
        return str(inference.get("capability") or "")

    @staticmethod
    def _build_entity(*, filters: dict[str, Any], semantic_context: dict[str, Any]) -> BusinessQuerySemanticEntity:
        dictionary_fields = list(((semantic_context.get("dictionary") or {}).get("fields") or []))
        for entity_type, field in (
            ("empleado", "cedula"),
            ("movil", "movil"),
            ("serial", "serial"),
            ("codigo", "codigo"),
            ("bodega", "bodega"),
        ):
            value = str(filters.get(field) or "").strip()
            if not value:
                continue
            return BusinessQuerySemanticEntity(
                type=entity_type,
                identifier=value,
                field=field,
                physical_field=InventoryBusinessQueryPlanner._resolve_physical_field(
                    logical_field=field,
                    dictionary_fields=dictionary_fields,
                ),
            )
        return BusinessQuerySemanticEntity()

    @staticmethod
    def _resolve_physical_field(*, logical_field: str, dictionary_fields: list[dict[str, Any]]) -> str:
        normalized = str(logical_field or "").strip().lower()
        for row in dictionary_fields:
            if not isinstance(row, dict):
                continue
            logical_name = str(row.get("campo_logico") or row.get("logical_name") or "").strip().lower()
            if logical_name == normalized:
                return str(row.get("column_name") or logical_field or "").strip()
        return str(logical_field or "").strip()

    @staticmethod
    def _resolve_scope_families(*, filters: dict[str, Any], inference: dict[str, Any], message: str) -> list[str]:
        governed_match = dict(inference.get("governed_match") or {})
        if list(governed_match.get("familias") or []):
            return [str(item) for item in list(governed_match.get("familias") or []) if str(item).strip()]
        tipo = filters.get("tipo")
        if isinstance(tipo, list):
            return ["material_claro" if str(item) == "material" else "ferretero" for item in tipo]
        if str(tipo or "") == "material":
            return ["material_claro"]
        if str(tipo or "") == "ferretero":
            return ["ferretero"]
        material_family = str(inference.get("material_family") or "").strip().lower()
        normalized_message = str(message or "").strip().lower()
        if material_family == "serializados":
            return ["serializados"]
        if any(token in normalized_message for token in ("serial", "serializados", "equipos", "cpe")):
            return ["serializados"]
        return ["material_claro", "ferretero"]

    @staticmethod
    def _should_include_serialized(*, filters: dict[str, Any], inference: dict[str, Any], message: str) -> bool:
        governed_match = dict(inference.get("governed_match") or {})
        if "incluye_serializados" in governed_match:
            return bool(governed_match.get("incluye_serializados"))
        normalized_message = str(message or "").strip().lower()
        if str(inference.get("material_family") or "").strip().lower() == "serializados":
            return True
        if filters.get("tipo"):
            return False
        if any(token in normalized_message for token in ("materiales", "material claro", "material de claro", "ferretero")):
            return False
        if str(filters.get("cedula") or "").strip() and not str(filters.get("movil") or "").strip():
            return False
        if any(token in normalized_message for token in ("movil", "móvil", "cuadrilla", "brigada")):
            return True
        if any(token in normalized_message for token in ("kardex", "movimientos", "entradas", "salidas")):
            return False
        return "inventario" in normalized_message

    @staticmethod
    def _resolve_output_profile(*, capability: str, inference: dict[str, Any], include_serialized: bool) -> tuple[list[str], str]:
        if capability == "inventory_kardex_by_employee":
            return (
                [
                    "fecha",
                    "tipo_movimiento",
                    "codigo",
                    "descripcion",
                    "tipo",
                    "cedula",
                    "empleado",
                    "movil",
                    "estado_empleado",
                    "bodega",
                    "orden_trabajo",
                    "ticket",
                    "entrada",
                    "salida",
                    "cantidad",
                    "efecto",
                    "saldo_movimiento",
                ],
                "movimiento_por_codigo",
            )
        if capability == "inventory_kardex_consolidated":
            return (
                ["fecha", "tipo_movimiento", "codigo", "cantidad", "origen", "destino"],
                "movimiento_por_fecha_y_codigo",
            )
        if capability in {"inventory_serial_by_operational_holder", "inventory_serial_stock_by_dimension", "inventory_traceability_by_serial"}:
            return (
                ["serial", "codigo", "descripcion", "familia", "estado", "cedula", "movil", "saldo"],
                "serial_por_codigo_y_estado",
            )
        columns = [
            "codigo",
            "descripcion",
            "tipo",
            "cedula",
            "empleado",
            "movil",
            "estado_empleado",
            "entregas",
            "devoluciones",
            "consumos",
            "cobros",
            "saldo",
        ]
        if include_serialized:
            columns.extend(["serializados.serial", "serializados.estado", "serializados.saldo"])
        return (columns, "saldo_por_codigo")

    @staticmethod
    def _inventory_family_from_scope(families: list[str]) -> str:
        normalized = set(families or [])
        if normalized == {"serializados"}:
            return "serializados"
        if "serializados" in normalized and len(normalized) > 1:
            return "mixto"
        if normalized == {"ferretero"}:
            return "ferreteros"
        return "materiales"

    @staticmethod
    def _resolve_coverage(*, filters: dict[str, Any], entity: BusinessQuerySemanticEntity) -> str:
        if str(filters.get("stock_scope") or "") == "movil":
            return "operativo_por_movil"
        if str(filters.get("stock_scope") or "") == "bodega":
            return "operativo_por_bodega"
        if entity.type == "codigo":
            return "operativo_por_codigo"
        if entity.type == "serial":
            return "operativo_por_serial"
        return "operativo_general"

    @staticmethod
    def _expected_output_for_capability(*, capability: str) -> str:
        if capability.startswith("inventory_kardex"):
            return "kardex_operativo"
        if "serial" in capability:
            return "inventario_serializado"
        return "saldo_inventario"

    @staticmethod
    def _requires_enrichment(*, capability: str, entity: BusinessQuerySemanticEntity, include_serialized: bool) -> bool:
        if entity.type in {"empleado", "movil"}:
            return True
        return include_serialized or capability in {
            "inventory_stock_balance_by_mobile",
            "inventory_kardex_by_employee",
            "inventory_serial_by_operational_holder",
        }

    @staticmethod
    def _applicable_rules(*, filters: dict[str, Any], inference: dict[str, Any], capability: str, include_serialized: bool) -> list[str]:
        rules = [
            "gpt_semantiza_planner_ejecuta",
            "saldo_incluye_positivos_cero_y_negativos" if "stock" in str(inference.get("intent") or "") else "",
        ]
        tipo = filters.get("tipo")
        if tipo == "material":
            rules.append("material_claro_equivale_tipo_material")
        elif tipo == "ferretero":
            rules.append("ferretero_equivale_tipo_ferretero")
        elif isinstance(tipo, list):
            rules.append("material_generico_equivale_material_claro_mas_ferretero")
        if str(capability or "") == "inventory_kardex_by_employee":
            rules.append("kardex_empleado_mapea_inventory_kardex_by_employee")
        if str(filters.get("cedula") or "").strip():
            rules.append("empleado_tecnico_numerico_es_cedula")
        if str(filters.get("movil") or "").strip():
            rules.append("movil_cuadrilla_alfanumerica_es_movil")
        if include_serialized:
            rules.append("inventario_generico_incluye_serializados_cuando_aplica")
        if str(inference.get("material_family") or "") == "serializados":
            rules.append("serializados_usan_conteo_no_cantidad")
        return [item for item in rules if item]

    @staticmethod
    def _possible_alerts(*, capability: str, inference: dict[str, Any], include_serialized: bool) -> list[str]:
        alerts = [
            "explicar_saldos_cero_y_negativos",
            "resaltar_movimientos_atipicos",
        ]
        if capability == "inventory_kardex_by_employee":
            alerts.append("explicar_efecto_de_cada_movimiento")
        if include_serialized:
            alerts.append("explicar_bloque_serializado_por_estado")
        if str(inference.get("business_concept") or "") == "materiales_criticos_por_empleado":
            alerts.append("alerta_material_critico_por_cobertura_3_dias")
        return alerts

    @staticmethod
    def _ambiguity_notes(*, filters: dict[str, Any], inference: dict[str, Any]) -> list[str]:
        notes: list[str] = []
        if not filters:
            notes.append("consulta_sin_filtros_explicitos")
        if str(inference.get("requires_external_source") or "").lower() == "true":
            notes.append("requiere_fuente_externa_no_habilitada")
        if str(inference.get("requires_threshold_metadata") or "").lower() == "true":
            notes.append("requiere_metadata_umbral")
        return notes
