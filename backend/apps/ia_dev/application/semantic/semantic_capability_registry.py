from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from apps.ia_dev.application.contracts.query_intelligence_contracts import (
    BusinessQuerySemanticPlan,
    BusinessQuerySemanticEntity,
)
from apps.ia_dev.application.runtime.tool_registry_service import ToolRegistryService
from apps.ia_dev.domains.inventario_logistica.metadata_gobernada_inventario import (
    FUENTES_DD_GOBERNADAS,
    construir_metadata_gobernada_inventario,
)
from apps.ia_dev.domains.inventario_logistica.paquete_capacidades_loader import (
    capability_pack_trace_payload,
    load_inventory_capability_pack,
)


INVENTORY_CONSULTED_METADATA = [
    "ai_dictionary.dd_tablas",
    "ai_dictionary.dd_campos",
    "ai_dictionary.dd_relaciones",
    "ai_dictionary.dd_sinonimos",
    "ai_dictionary.dd_reglas",
    "ai_dictionary.ia_dev_capacidades_columna",
    "ToolRegistryService",
    "BusinessQuerySemanticPlan",
    "semantic_context",
]

INVENTORY_TEMPLATE_BINDINGS: dict[str, dict[str, Any]] = {
    "inventory_material_stock_mobile": {
        "candidate_capability": "inventory_stock_balance_by_mobile",
        "planner_route_hint": "inventory.material_stock.mobile",
        "response_profile": "inventory.stock.mobile.detail",
        "expected_output": "saldo_inventario",
        "grain": "saldo_por_codigo",
        "columns": [
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
        ],
    },
    "inventory_material_stock_grouped_dimension": {
        "candidate_capability": "inventory_stock_balance_by_material_dimension",
        "planner_route_hint": "inventory.material_stock.dimension",
        "response_profile": "inventory.stock.dimension.summary",
        "expected_output": "saldo_inventario",
        "grain": "saldo_por_dimension_y_codigo",
        "columns": [
            "dimension",
            "cedula",
            "empleado",
            "movil",
            "bodega",
            "codigo",
            "descripcion",
            "tipo",
            "entregas",
            "devoluciones",
            "consumos",
            "cobros",
            "saldo",
        ],
    },
    "inventory_material_stock_by_warehouse": {
        "candidate_capability": "inventory_stock_balance_by_warehouse",
        "planner_route_hint": "inventory.material_stock.warehouse",
        "response_profile": "inventory.stock.warehouse.detail",
        "expected_output": "saldo_inventario",
        "grain": "saldo_por_codigo",
        "columns": [
            "codigo",
            "descripcion",
            "tipo",
            "bodega",
            "entregas",
            "devoluciones",
            "consumos",
            "cobros",
            "saldo",
        ],
    },
    "inventory_material_stock_balance": {
        "candidate_capability": "inventory_stock_balance",
        "planner_route_hint": "inventory.material_stock.balance",
        "response_profile": "inventory.stock.balance.summary",
        "expected_output": "saldo_inventario",
        "grain": "saldo_por_codigo",
        "columns": [
            "codigo",
            "descripcion",
            "tipo",
            "saldo",
        ],
    },
    "inventory_material_critical_by_employee": {
        "candidate_capability": "inventory_stock_balance_by_mobile",
        "planner_route_hint": "inventory.material_stock.critical_employee",
        "response_profile": "inventory.stock.critical.employee",
        "expected_output": "saldo_inventario",
        "grain": "saldo_por_codigo",
        "columns": [
            "cedula",
            "movil",
            "codigo",
            "descripcion",
            "tipo",
            "saldo_actual",
            "consumo_ultimos_8_dias",
            "umbral_3_dias",
            "estado_critico",
        ],
    },
    "inventory_kardex_by_employee": {
        "candidate_capability": "inventory_kardex_by_employee",
        "planner_route_hint": "inventory.kardex.employee",
        "response_profile": "inventory.kardex.employee.detail",
        "expected_output": "kardex_operativo",
        "grain": "movimiento_por_codigo",
        "columns": [
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
    },
    "inventory_kardex_consolidated": {
        "candidate_capability": "inventory_kardex_consolidated",
        "planner_route_hint": "inventory.kardex.consolidated",
        "response_profile": "inventory.kardex.consolidated.detail",
        "expected_output": "kardex_operativo",
        "grain": "movimiento_por_fecha_y_codigo",
        "columns": ["fecha", "tipo_movimiento", "codigo", "cantidad", "origen", "destino"],
    },
    "inventory_traceability_by_serial": {
        "candidate_capability": "inventory_traceability_by_serial",
        "planner_route_hint": "inventory.traceability.serial",
        "response_profile": "inventory.traceability.serial.detail",
        "expected_output": "inventario_serializado",
        "grain": "serial_por_codigo_y_estado",
        "columns": ["serial", "codigo", "descripcion", "familia", "estado", "ubicacion", "fecha"],
    },
    "inventory_serial_by_operational_holder": {
        "candidate_capability": "inventory_serial_by_operational_holder",
        "planner_route_hint": "inventory.serial.holder",
        "response_profile": "inventory.serial.holder.detail",
        "expected_output": "inventario_serializado",
        "grain": "serial_por_codigo_y_estado",
        "columns": ["serial", "codigo", "descripcion", "familia", "estado", "cedula", "movil", "saldo"],
    },
    "inventory_serial_stock_by_family_grouped_dimension": {
        "candidate_capability": "inventory_serial_stock_by_family_grouped_dimension",
        "planner_route_hint": "inventory.serial_stock.family_dimension",
        "response_profile": "inventory.serial.stock.dimension.detail",
        "expected_output": "inventario_serializado",
        "grain": "saldo_serializado_por_dimension_y_codigo",
        "columns": [
            "dimension",
            "cedula",
            "empleado",
            "movil",
            "bodega",
            "codigo",
            "descripcion",
            "familia",
            "seriales_total",
            "cedulas_asociadas",
            "en_movil",
            "en_base",
            "cobros",
            "saldo",
        ],
    },
    "inventory_serial_stock_by_dimension": {
        "candidate_capability": "inventory_serial_stock_by_dimension",
        "planner_route_hint": "inventory.serial.stock.dimension",
        "response_profile": "inventory.serial.dimension.summary",
        "expected_output": "inventario_serializado",
        "grain": "serial_por_codigo_y_estado",
        "columns": ["estado", "codigo", "descripcion", "saldo"],
    },
    "inventory_risk_consumo_movil_sin_validar": {
        "candidate_capability": "inventory_risk_consumo_movil_sin_validar",
        "planner_route_hint": "inventory.risk.consumo_movil_sin_validar",
        "response_profile": "inventory.risk.serial.detail",
        "expected_output": "inventario_serializado",
        "grain": "serial_por_codigo_y_estado",
        "columns": ["serial", "codigo", "estado", "ubicacion", "fecha"],
    },
    "inventory_consumption_top": {
        "candidate_capability": "inventory_consumption_top",
        "planner_route_hint": "inventory.consumption.top",
        "response_profile": "inventory.consumption.top.summary",
        "expected_output": "saldo_inventario",
        "grain": "saldo_por_codigo",
        "columns": ["codigo", "descripcion", "tipo", "cantidad"],
    },
    "inventory_consumption_by_dimension": {
        "candidate_capability": "inventory_consumption_by_dimension",
        "planner_route_hint": "inventory.consumption.dimension",
        "response_profile": "inventory.consumption.dimension.summary",
        "expected_output": "saldo_inventario",
        "grain": "saldo_por_codigo",
        "columns": ["codigo", "descripcion", "tipo", "cantidad"],
    },
    "inventory_transfer_warehouse": {
        "candidate_capability": "inventory_transfer_warehouse",
        "planner_route_hint": "inventory.transfer.warehouse",
        "response_profile": "inventory.transfer.warehouse.detail",
        "expected_output": "saldo_inventario",
        "grain": "movimiento_por_fecha_y_codigo",
        "columns": ["codigo", "cantidad", "bodega", "movimiento", "estado"],
    },
    "inventory_transfer_other_ally": {
        "candidate_capability": "inventory_transfer_other_ally",
        "planner_route_hint": "inventory.transfer.other_ally",
        "response_profile": "inventory.transfer.other_ally.detail",
        "expected_output": "saldo_inventario",
        "grain": "movimiento_por_fecha_y_codigo",
        "columns": ["codigo", "cantidad", "bodega", "movimiento", "estado"],
    },
    "inventory_transfer_destination_not_available": {
        "candidate_capability": "",
        "planner_route_hint": "inventory.transfer.destination_unresolved",
        "response_profile": "inventory.transfer.destination.blocked",
        "expected_output": "saldo_inventario",
        "grain": "movimiento_por_fecha_y_codigo",
        "columns": ["codigo", "cantidad", "bodega"],
    },
    "inventory_serial_association_departures": {
        "candidate_capability": "inventory_serial_association_departures",
        "planner_route_hint": "inventory.serial.association.departures",
        "response_profile": "inventory.serial.association.departures.detail",
        "expected_output": "inventario_serializado",
        "grain": "serial_por_codigo_y_estado",
        "columns": ["serial", "codigo", "fecha_asociacion", "bodega_salida", "estado_asociacion"],
    },
    "inventory_entries_by_month": {
        "candidate_capability": "inventory_entries_by_month",
        "planner_route_hint": "inventory.entries.month",
        "response_profile": "inventory.entries.month.summary",
        "expected_output": "saldo_inventario",
        "grain": "movimiento_por_fecha_y_codigo",
        "columns": ["codigo", "cantidad", "fecha", "bodega"],
    },
    "inventory_movement_detail": {
        "candidate_capability": "inventory_movement_detail",
        "planner_route_hint": "inventory.movement.detail",
        "response_profile": "inventory.movement.detail",
        "expected_output": "saldo_inventario",
        "grain": "movimiento_por_fecha_y_codigo",
        "columns": ["codigo", "cantidad", "fecha", "bodega"],
    },
    "inventory_consumption_billing_operacion_hfc": {
        "candidate_capability": "inventory_consumption_billing_operacion_hfc",
        "planner_route_hint": "inventory.reconciliation.operacion_hfc",
        "response_profile": "inventory.reconciliation.operacion_hfc",
        "expected_output": "saldo_inventario",
        "grain": "saldo_por_codigo",
        "columns": ["codigo", "cantidad", "orden_trabajo", "tipo", "bodega"],
    },
    "inventory_reconciliation_pending_validation": {
        "candidate_capability": "",
        "planner_route_hint": "inventory.reconciliation.pending_validation",
        "response_profile": "inventory.reconciliation.pending_validation",
        "expected_output": "saldo_inventario",
        "grain": "saldo_por_codigo",
        "columns": ["codigo", "cantidad", "bodega"],
    },
    "inventory_external_reconciliation_pending": {
        "candidate_capability": "",
        "planner_route_hint": "inventory.external_reconciliation.pending",
        "response_profile": "inventory.external_reconciliation.pending",
        "expected_output": "saldo_inventario",
        "grain": "saldo_por_codigo",
        "columns": ["codigo", "cantidad", "fecha"],
    },
    "inventory_document_generation_pending": {
        "candidate_capability": "inventory_document_generation_pending",
        "planner_route_hint": "inventory.document_generation.pending",
        "response_profile": "inventory.document_generation.pending",
        "expected_output": "document_generation_pending",
        "grain": "documento_pendiente",
        "columns": ["documento", "codigo", "serial", "fecha"],
    },
    "inventory_semantic_report": {
        "candidate_capability": "inventory_semantic_report",
        "planner_route_hint": "inventory.semantic_report",
        "response_profile": "inventory.semantic_report",
        "expected_output": "saldo_inventario",
        "grain": "saldo_por_codigo",
        "columns": ["codigo", "cantidad", "fecha"],
    },
    "inventory_notification_pending": {
        "candidate_capability": "",
        "planner_route_hint": "inventory.notification.pending",
        "response_profile": "inventory.notification.pending",
        "expected_output": "saldo_inventario",
        "grain": "saldo_por_codigo",
        "columns": ["codigo", "cantidad", "proveedor", "compra", "fecha"],
    },
    "inventory_assignment_distribution_pending": {
        "candidate_capability": "",
        "planner_route_hint": "inventory.assignment_distribution.pending",
        "response_profile": "inventory.assignment_distribution.pending",
        "expected_output": "saldo_inventario",
        "grain": "saldo_por_codigo",
        "columns": ["cedula", "movil", "codigo", "cantidad"],
    },
    "inventory_alert_semantic_report": {
        "candidate_capability": "",
        "planner_route_hint": "inventory.alert.semantic_report",
        "response_profile": "inventory.alert.semantic_report",
        "expected_output": "saldo_inventario",
        "grain": "saldo_por_codigo",
        "columns": ["codigo", "cantidad"],
    },
}

INVENTORY_INTENT_IDS_BY_TEMPLATE = {
    "inventory_material_stock_mobile": "inventory_stock_by_mobile",
    "inventory_material_stock_grouped_dimension": "inventory_stock_by_dimension",
    "inventory_material_stock_by_warehouse": "inventory_stock_by_warehouse",
    "inventory_material_stock_balance": "inventory_stock_balance",
    "inventory_material_critical_by_employee": "inventory_stock_by_mobile",
    "inventory_kardex_by_employee": "inventory_kardex",
    "inventory_kardex_consolidated": "inventory_kardex",
    "inventory_serial_by_operational_holder": "inventory_serial_by_holder",
    "inventory_serial_stock_by_family_grouped_dimension": "inventory_stock_by_dimension",
    "inventory_traceability_by_serial": "inventory_traceability_serial",
    "inventory_document_generation_pending": "inventory_document_generation",
}


@dataclass(slots=True)
class SemanticBindingRequest:
    domain: str
    message: str = ""
    intent: str = ""
    entity: BusinessQuerySemanticEntity | dict[str, Any] | None = None
    normalized_filters: dict[str, Any] = field(default_factory=dict)
    group_by: list[str] = field(default_factory=list)
    semantic_context: dict[str, Any] = field(default_factory=dict)
    business_query_semantic_plan: BusinessQuerySemanticPlan | dict[str, Any] | None = None
    source_hints: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SemanticBindingDecision:
    domain: str
    intent: str = ""
    entity: dict[str, Any] = field(default_factory=dict)
    normalized_filters: dict[str, Any] = field(default_factory=dict)
    output_profile: dict[str, Any] = field(default_factory=dict)
    candidate_capability: str = ""
    template_id: str = ""
    planner_route_hint: str = ""
    response_profile: str = ""
    tool_id: str = ""
    source: str = ""
    matched_rules: list[str] = field(default_factory=list)
    consulted_metadata: list[str] = field(default_factory=list)
    confidence: float = 0.0
    fallback_used: bool = False
    unresolved_reason: str = ""
    legacy_mapping_used: bool = False
    legacy_reason: str = ""
    migration_target: str = ""
    regla_metadata_usada: list[str] = field(default_factory=list)
    fuente_dd: list[str] = field(default_factory=list)
    fallback_sombreado_usado: bool = False
    regla_legacy_detectada: bool = False
    regla_migrada: bool = False
    paquete_capacidad_usado: str = ""
    version_paquete: str = ""
    capacidades_declaradas: list[str] = field(default_factory=list)
    reglas_declaradas: list[str] = field(default_factory=list)
    perfiles_respuesta: list[str] = field(default_factory=list)
    evaluaciones_asociadas: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "domain": str(self.domain or ""),
            "intent": str(self.intent or ""),
            "entity": dict(self.entity or {}),
            "normalized_filters": dict(self.normalized_filters or {}),
            "output_profile": dict(self.output_profile or {}),
            "candidate_capability": str(self.candidate_capability or ""),
            "template_id": str(self.template_id or ""),
            "planner_route_hint": str(self.planner_route_hint or ""),
            "response_profile": str(self.response_profile or ""),
            "tool_id": str(self.tool_id or ""),
            "source": str(self.source or ""),
            "matched_rules": [str(item or "") for item in list(self.matched_rules or []) if str(item or "").strip()],
            "consulted_metadata": [
                str(item or "") for item in list(self.consulted_metadata or []) if str(item or "").strip()
            ],
            "confidence": float(self.confidence or 0.0),
            "fallback_used": bool(self.fallback_used),
            "unresolved_reason": str(self.unresolved_reason or ""),
            "legacy_mapping_used": bool(self.legacy_mapping_used),
            "legacy_reason": str(self.legacy_reason or ""),
            "migration_target": str(self.migration_target or ""),
            "regla_metadata_usada": [
                str(item or "") for item in list(self.regla_metadata_usada or []) if str(item or "").strip()
            ],
            "fuente_dd": [str(item or "") for item in list(self.fuente_dd or []) if str(item or "").strip()],
            "fallback_sombreado_usado": bool(self.fallback_sombreado_usado),
            "regla_legacy_detectada": bool(self.regla_legacy_detectada),
            "regla_migrada": bool(self.regla_migrada),
            "paquete_capacidad_usado": str(self.paquete_capacidad_usado or ""),
            "version_paquete": str(self.version_paquete or ""),
            "capacidades_declaradas": [
                str(item or "") for item in list(self.capacidades_declaradas or []) if str(item or "").strip()
            ],
            "reglas_declaradas": [
                str(item or "") for item in list(self.reglas_declaradas or []) if str(item or "").strip()
            ],
            "perfiles_respuesta": [
                str(item or "") for item in list(self.perfiles_respuesta or []) if str(item or "").strip()
            ],
            "evaluaciones_asociadas": [
                str(item or "") for item in list(self.evaluaciones_asociadas or []) if str(item or "").strip()
            ],
        }


class SemanticCapabilityRegistry:
    def __init__(self, *, tool_registry_service: ToolRegistryService | None = None):
        self.tool_registry_service = tool_registry_service or ToolRegistryService()

    def resolve(self, request: SemanticBindingRequest) -> SemanticBindingDecision:
        domain = str(request.domain or "").strip().lower()
        if domain != "inventario_logistica":
            return SemanticBindingDecision(
                domain=domain,
                source="unsupported_domain",
                consulted_metadata=list(INVENTORY_CONSULTED_METADATA),
                confidence=0.0,
                fallback_used=True,
                unresolved_reason="registry_not_enabled_for_domain",
            )
        return self._resolve_inventory(request=request)

    def _resolve_inventory(self, *, request: SemanticBindingRequest) -> SemanticBindingDecision:
        semantic_context = dict(request.semantic_context or {})
        resolved_semantic = dict(semantic_context.get("resolved_semantic") or {})
        source_hints = dict(request.source_hints or {})
        capability_pack = load_inventory_capability_pack(
            tool_registry_service=self.tool_registry_service
        )
        governed_metadata = self._load_governed_inventory_metadata(semantic_context=semantic_context)
        governed_rules = list(governed_metadata.get("dd_reglas") or [])
        governed_capability_rows = list(governed_metadata.get("ia_dev_capacidades_columna") or [])
        plan_payload = self._plan_payload(request.business_query_semantic_plan)
        governed_match = dict(
            source_hints.get("governed_match")
            or semantic_context.get("inventory_governed_match")
            or {}
        )
        inference = dict(
            source_hints.get("inventory_inference")
            or semantic_context.get("inventory_semantic_inference")
            or {}
        )
        entity = self._coerce_entity(request.entity or plan_payload.get("entity") or {})
        filters = dict(request.normalized_filters or plan_payload.get("normalized_filters") or {})
        if governed_match.get("filtros"):
            filters.update(
                {
                    key: value
                    for key, value in dict(governed_match.get("filtros") or {}).items()
                    if value not in (None, "")
                }
            )
        if dict(inference.get("filters") or {}):
            filters.update(
                {
                    key: value
                    for key, value in dict(inference.get("filters") or {}).items()
                    if value not in (None, "")
                }
            )
        if not entity:
            entity = self._entity_from_filters(filters)
        intent = (
            str(request.intent or "").strip().lower()
            or str(plan_payload.get("intent") or "").strip().lower()
            or str(inference.get("intent") or "").strip().lower()
            or str(governed_match.get("intencion") or "").strip().lower()
        )
        group_by = [
            str(item or "").strip().lower()
            for item in list(request.group_by or source_hints.get("group_by") or inference.get("group_by") or [])
            if str(item or "").strip()
        ]
        matched_rules: list[str] = []
        consulted_metadata = list(INVENTORY_CONSULTED_METADATA)
        consulted_metadata.extend(list(governed_metadata.get("fuentes_dd") or FUENTES_DD_GOBERNADAS))
        memory_keys = self._memory_keys(source_hints=source_hints, resolved_semantic=resolved_semantic, semantic_context=semantic_context)
        if memory_keys:
            consulted_metadata.append("ai_dictionary.ia_dev_business_memory")

        template_id = ""
        source = ""
        confidence = 0.74
        governed_binding_payload: dict[str, Any] = {}
        metadata_rule_trace: list[str] = []
        fallback_sombreado_usado = False
        legacy_mapping_used = False
        legacy_reason = ""
        migration_target = ""

        explicit_template = self._first_inventory_template(
            [
                source_hints.get("template_id"),
                governed_match.get("template_id"),
                plan_payload.get("semantic_binding", {}).get("template_id"),
                plan_payload.get("template_id"),
            ]
        )
        if explicit_template and not self._should_ignore_explicit_inventory_template(
            explicit_template=explicit_template,
            filters=filters,
            group_by=group_by,
            inference=inference,
            governed_match=governed_match,
        ):
            template_id = explicit_template
            governed_binding_payload, metadata_rule_trace = self._binding_payload_from_template_or_rules(
                template_id=template_id,
                governed_rules=governed_rules,
            )
            source = "governed_template"
            matched_rules.extend(metadata_rule_trace or ["template_id_governed_by_existing_semantic_signal"])
            confidence = 0.96 if governed_match.get("coincidencia_gobernada") else 0.9

        if not template_id:
            governed_binding_payload, metadata_rule_trace = self._resolve_inventory_governed_binding(
                intent=intent,
                entity=entity,
                filters=filters,
                group_by=group_by,
                inference=inference,
                governed_rules=governed_rules,
                capability_rows=governed_capability_rows,
            )
            template_id = str(governed_binding_payload.get("template_id") or "")
            if template_id:
                source = "semantic_inventory_registry_metadata"
                matched_rules.extend(metadata_rule_trace)
                confidence = 0.91

        if not template_id:
            template_id = self._resolve_inventory_template_legacy(
                intent=intent,
                entity=entity,
                filters=filters,
                group_by=group_by,
                inference=inference,
            )
            if template_id:
                source = "legacy_inventory_template_map"
                matched_rules.append("legacy_inventory_template_map_fallback")
                confidence = 0.7
                legacy_mapping_used = True
                fallback_sombreado_usado = True
                legacy_reason = "semantic_registry_rule_not_available_for_inventory_shape"
                migration_target = "semantic_capability_registry.inventory_template_resolution"

        legacy_binding = dict(INVENTORY_TEMPLATE_BINDINGS.get(template_id) or {})
        binding = dict(governed_binding_payload or legacy_binding)
        pack_binding = dict(
            capability_pack.capabilities_by_template.get(template_id) or {}
        )
        pack_profile = dict(
            capability_pack.response_profiles_by_id.get(
                str(pack_binding.get("response_profile") or "").strip()
            )
            or {}
        )
        capability_pack_trace = capability_pack_trace_payload(capability_pack)
        if template_id and not capability_pack.validation.ok:
            matched_rules.append("capability_pack_validation_failed")
            fallback_sombreado_usado = True
        if template_id and not pack_binding:
            matched_rules.append("capability_pack_missing_template")
            fallback_sombreado_usado = True
        if pack_binding:
            source = source or "capability_pack_validated_binding"
        candidate_capability = (
            str(plan_payload.get("candidate_capability") or "").strip()
            or str(governed_match.get("capacidad_candidata") or "").strip()
            or str(pack_binding.get("capability_id") or "").strip()
            or str(binding.get("candidate_capability") or "").strip()
        )
        if candidate_capability:
            matched_rules.append("candidate_capability_bound_from_registry")
        declared_tool_ids = [
            str(item or "").strip()
            for item in list(pack_binding.get("tools") or [])
            if str(item or "").strip()
        ]
        tool_id = ""
        if candidate_capability:
            tool_id = self.tool_registry_service.map_capability_to_tool(candidate_capability)
        if declared_tool_ids and tool_id not in declared_tool_ids:
            runtime_tool = tool_id
            planner_tool = self.tool_registry_service.SQL_ASSISTED_TOOL_ID
            if runtime_tool and runtime_tool in declared_tool_ids:
                tool_id = runtime_tool
            elif planner_tool in declared_tool_ids:
                tool_id = planner_tool
        if tool_id:
            matched_rules.append("tool_id_resolved_via_tool_registry")
        output_profile = self._build_output_profile(
            template_id=template_id,
            binding={**binding, **({"columns": pack_profile.get("columnas")} if pack_profile else {})},
            plan_payload=plan_payload,
            filters=filters,
            inference=inference,
        )
        response_profile = self._resolve_response_profile(
            template_id=template_id,
            binding={**binding, **({"response_profile": pack_binding.get("response_profile")} if pack_binding else {})},
            filters=filters,
            inference=inference,
            governed_rules=governed_rules,
        )
        planner_route_hint = str(
            pack_binding.get("planner_route_hint")
            or binding.get("planner_route_hint")
            or ""
        ).strip()

        unresolved_reason = ""
        fallback_used = False
        if not template_id:
            fallback_used = True
            unresolved_reason = "inventory_template_unresolved"
        elif not candidate_capability:
            fallback_used = True
            unresolved_reason = "inventory_capability_unresolved"
        elif not tool_id:
            matched_rules.append("tool_registry_missing_binding")
        elif declared_tool_ids and tool_id not in declared_tool_ids:
            matched_rules.append("capability_pack_tool_mismatch")
            fallback_sombreado_usado = True

        if pack_binding and pack_profile:
            output_profile = {
                "expected_output": str(pack_profile.get("expected_output") or output_profile.get("expected_output") or ""),
                "grain": str(pack_profile.get("grain") or output_profile.get("grain") or ""),
                "columns": [
                    str(item or "")
                    for item in list(pack_profile.get("columnas") or output_profile.get("columns") or [])
                    if str(item or "").strip()
                ],
            }

        if template_id == "inventory_serial_stock_by_family_grouped_dimension" and str(filters.get("material_family") or "").strip():
            filters.setdefault("material_family_match_mode", "contains")

        pack_capabilities = list(capability_pack_trace.get("capacidades_declaradas") or [])
        pack_rules = list(capability_pack_trace.get("reglas_declaradas") or [])
        pack_profiles = list(capability_pack_trace.get("perfiles_respuesta") or [])
        pack_evals = list(capability_pack_trace.get("evaluaciones_asociadas") or [])

        return SemanticBindingDecision(
            domain="inventario_logistica",
            intent=intent,
            entity=dict(entity or {}),
            normalized_filters=filters,
            output_profile=output_profile,
            candidate_capability=candidate_capability,
            template_id=template_id,
            planner_route_hint=planner_route_hint,
            response_profile=response_profile,
            tool_id=tool_id,
            source=source or "semantic_inventory_registry",
            matched_rules=list(dict.fromkeys(matched_rules)),
            consulted_metadata=list(dict.fromkeys(consulted_metadata)),
            confidence=confidence,
            fallback_used=fallback_used or legacy_mapping_used,
            unresolved_reason=unresolved_reason,
            legacy_mapping_used=legacy_mapping_used,
            legacy_reason=legacy_reason,
            migration_target=migration_target,
            regla_metadata_usada=list(dict.fromkeys(metadata_rule_trace)),
            fuente_dd=list(governed_metadata.get("fuentes_dd") or FUENTES_DD_GOBERNADAS),
            fallback_sombreado_usado=fallback_sombreado_usado or legacy_mapping_used,
            regla_legacy_detectada=legacy_mapping_used,
            regla_migrada=bool(template_id and not legacy_mapping_used),
            paquete_capacidad_usado=str(capability_pack_trace.get("paquete_capacidad_usado") or ""),
            version_paquete=str(capability_pack_trace.get("version_paquete") or ""),
            capacidades_declaradas=pack_capabilities,
            reglas_declaradas=pack_rules,
            perfiles_respuesta=pack_profiles,
            evaluaciones_asociadas=pack_evals,
        )

    @staticmethod
    def _should_ignore_explicit_inventory_template(
        *,
        explicit_template: str,
        filters: dict[str, Any],
        group_by: list[str],
        inference: dict[str, Any],
        governed_match: dict[str, Any],
    ) -> bool:
        normalized_template = str(explicit_template or "").strip().lower()
        if normalized_template != "inventory_material_stock_grouped_dimension":
            return False
        if str(inference.get("material_family") or "").strip().lower() != "serializados":
            return False
        if not str(filters.get("material_family") or "").strip():
            return False
        grouped_dimensions = {
            str(item or "").strip().lower()
            for item in list(group_by or [])
            if str(item or "").strip()
        }
        if not (grouped_dimensions & {"movil", "cedula", "bodega"}):
            return False
        governed_capability = str(governed_match.get("capacidad_candidata") or "").strip().lower()
        governed_template = str(governed_match.get("template_id") or "").strip().lower()
        return governed_capability == "inventory_serial_stock_by_family_grouped_dimension" or (
            governed_template == "inventory_serial_stock_by_family_grouped_dimension"
        )

    @staticmethod
    def _load_governed_inventory_metadata(*, semantic_context: dict[str, Any]) -> dict[str, Any]:
        default_metadata = construir_metadata_gobernada_inventario()
        dictionary = dict(semantic_context.get("dictionary") or {})
        rules = list(dictionary.get("rules") or semantic_context.get("rules") or default_metadata.get("dd_reglas") or [])
        capabilities = list(
            semantic_context.get("ia_dev_capacidades_columna")
            or dictionary.get("ia_dev_capacidades_columna")
            or default_metadata.get("ia_dev_capacidades_columna")
            or []
        )
        return {
            "dd_reglas": [dict(item) for item in rules if isinstance(item, dict)],
            "ia_dev_capacidades_columna": [dict(item) for item in capabilities if isinstance(item, dict)],
            "fuentes_dd": list(default_metadata.get("fuentes_dd") or FUENTES_DD_GOBERNADAS),
        }

    def _binding_payload_from_template_or_rules(
        self,
        *,
        template_id: str,
        governed_rules: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], list[str]]:
        template = str(template_id or "").strip()
        if not template:
            return {}, []
        for rule in sorted(governed_rules, key=lambda item: int(item.get("priority") or 0), reverse=True):
            result = dict(rule.get("result_json") or {})
            if str(result.get("template_id") or "").strip() == template:
                return dict(result), [str(rule.get("codigo") or rule.get("rule_name") or "").strip()]
        return dict(INVENTORY_TEMPLATE_BINDINGS.get(template) or {}), []

    def _resolve_inventory_governed_binding(
        self,
        *,
        intent: str,
        entity: dict[str, Any],
        filters: dict[str, Any],
        group_by: list[str],
        inference: dict[str, Any],
        governed_rules: list[dict[str, Any]],
        capability_rows: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], list[str]]:
        entity_field = str(entity.get("field") or "").strip().lower()
        available_fields = {
            str(item.get("campo_logico") or "").strip().lower()
            for item in capability_rows
            if isinstance(item, dict)
        }
        if entity_field and available_fields and entity_field not in available_fields:
            return {}, []
        matched_rule_ids: list[str] = []
        sorted_rules = sorted(governed_rules, key=lambda item: int(item.get("priority") or 0), reverse=True)
        for rule in sorted_rules:
            condition = dict(rule.get("condition_json") or {})
            result = dict(rule.get("result_json") or {})
            if not result.get("template_id"):
                continue
            if not self._governed_rule_matches(
                intent=intent,
                entity_field=entity_field,
                filters=filters,
                group_by=group_by,
                inference=inference,
                condition=condition,
            ):
                continue
            matched_rule_ids.append(str(rule.get("codigo") or rule.get("rule_name") or "").strip())
            return result, matched_rule_ids
        return {}, []

    @staticmethod
    def _governed_rule_matches(
        *,
        intent: str,
        entity_field: str,
        filters: dict[str, Any],
        group_by: list[str],
        inference: dict[str, Any],
        condition: dict[str, Any],
    ) -> bool:
        condition_intent = str(condition.get("intent") or "").strip().lower()
        if condition_intent and condition_intent != str(intent or "").strip().lower():
            return False
        field = str(condition.get("field") or "").strip().lower()
        if field and not (entity_field == field or str(filters.get(field) or "").strip()):
            return False
        forbid_field = str(condition.get("forbid_field") or "").strip().lower()
        if forbid_field and str(filters.get(forbid_field) or "").strip():
            return False
        any_fields = {str(item or "").strip().lower() for item in list(condition.get("field_any_of") or []) if str(item or "").strip()}
        if any_fields and not any(entity_field == item or str(filters.get(item) or "").strip() for item in any_fields):
            return False
        forbid_any_fields = {
            str(item or "").strip().lower()
            for item in list(condition.get("forbid_field_any_of") or [])
            if str(item or "").strip()
        }
        if forbid_any_fields and any(str(filters.get(item) or "").strip() for item in forbid_any_fields):
            return False
        filter_any_of = {
            str(item or "").strip().lower()
            for item in list(condition.get("filter_any_of") or [])
            if str(item or "").strip()
        }
        if filter_any_of and not any(str(filters.get(item) or "").strip() for item in filter_any_of):
            return False
        if bool(condition.get("holder_scope_required")) and not any(str(filters.get(item) or "").strip() for item in ("cedula", "movil")):
            return False
        if bool(condition.get("tipo_absent")) and filters.get("tipo"):
            return False
        group_by_contains = str(condition.get("group_by_contains") or "").strip().lower()
        if group_by_contains and group_by_contains not in {str(item or "").strip().lower() for item in group_by}:
            return False
        group_by_any_of = {
            str(item or "").strip().lower()
            for item in list(condition.get("group_by_any_of") or [])
            if str(item or "").strip()
        }
        if group_by_any_of and not ({str(item or "").strip().lower() for item in group_by} & group_by_any_of):
            return False
        if "bodega_destino" in set(group_by) and str(condition.get("field") or "").strip().lower() == "cedula":
            return False
        if str(condition.get("family") or "").strip().lower() == "serializados":
            material_family = str(inference.get("material_family") or "").strip().lower()
            if material_family != "serializados":
                return False
        return True

    @staticmethod
    def _plan_payload(plan: BusinessQuerySemanticPlan | dict[str, Any] | None) -> dict[str, Any]:
        if isinstance(plan, BusinessQuerySemanticPlan):
            return plan.as_dict()
        if isinstance(plan, dict):
            return dict(plan)
        return {}

    @staticmethod
    def _coerce_entity(entity: BusinessQuerySemanticEntity | dict[str, Any] | None) -> dict[str, Any]:
        if isinstance(entity, BusinessQuerySemanticEntity):
            return entity.as_dict()
        if isinstance(entity, dict):
            return {
                "type": str(entity.get("type") or ""),
                "identifier": str(entity.get("identifier") or ""),
                "field": str(entity.get("field") or ""),
                "physical_field": str(entity.get("physical_field") or entity.get("field") or ""),
            }
        return {}

    @staticmethod
    def _memory_keys(
        *,
        source_hints: dict[str, Any],
        resolved_semantic: dict[str, Any],
        semantic_context: dict[str, Any],
    ) -> list[str]:
        candidates = (
            list(source_hints.get("memory_keys_used") or [])
            or list(resolved_semantic.get("memory_keys_used") or [])
            or [
                str(item.get("memory_key") or "")
                for item in list(semantic_context.get("semantic_memory_snapshot") or [])
                if isinstance(item, dict)
            ]
        )
        return [str(item or "") for item in candidates if str(item or "").strip()]

    @staticmethod
    def _entity_from_filters(filters: dict[str, Any]) -> dict[str, Any]:
        for entity_type, field in (
            ("empleado", "cedula"),
            ("movil", "movil"),
            ("serial", "serial"),
            ("codigo", "codigo"),
            ("bodega", "bodega"),
        ):
            value = str(filters.get(field) or "").strip()
            if value:
                return {
                    "type": entity_type,
                    "identifier": value,
                    "field": field,
                    "physical_field": field,
                }
        return {}

    @staticmethod
    def _first_inventory_template(candidates: list[Any]) -> str:
        for candidate in candidates:
            normalized = str(candidate or "").strip().lower()
            if normalized.startswith("inventory_"):
                return normalized
        return ""

    def _resolve_inventory_template(
        self,
        *,
        intent: str,
        entity: dict[str, Any],
        filters: dict[str, Any],
        group_by: list[str],
        inference: dict[str, Any],
        matched_rules: list[str],
    ) -> str:
        entity_field = str(entity.get("field") or "").strip().lower()
        material_family = str(inference.get("material_family") or "").strip().lower()
        business_concept = str(inference.get("business_concept") or "").strip().lower()
        stock_scope = str(filters.get("stock_scope") or "").strip().lower()
        if intent == "document_generation":
            matched_rules.append("intent_document_generation_to_pending_template")
            return "inventory_document_generation_pending"
        if intent == "movement_history":
            if entity_field == "cedula" or str(filters.get("cedula") or "").strip():
                matched_rules.append("movement_history_by_cedula_to_employee_kardex")
                return "inventory_kardex_by_employee"
            if entity_field == "codigo" or str(filters.get("codigo") or "").strip():
                matched_rules.append("movement_history_by_codigo_to_consolidated_kardex")
                return "inventory_kardex_consolidated"
        if intent == "traceability_query":
            matched_rules.append("traceability_query_to_serial_traceability")
            return "inventory_traceability_by_serial"
        if intent == "serial_holder_query":
            matched_rules.append("serial_holder_query_to_serial_holder_template")
            return "inventory_serial_by_operational_holder"
        if intent == "risk_detection":
            matched_rules.append("risk_detection_to_serial_risk_template")
            return "inventory_risk_consumo_movil_sin_validar"
        if intent == "consumption_query":
            matched_rules.append("consumption_query_to_consumption_template")
            return "inventory_consumption_top" if str(inference.get("operation") or "").strip().lower() == "top" else "inventory_consumption_by_dimension"
        if intent == "transfer_query":
            movement = str(filters.get("movimiento") or "").strip().upper()
            if "bodega_destino" in set(group_by):
                matched_rules.append("transfer_group_by_bodega_destino_pending_template")
                return "inventory_transfer_destination_not_available"
            if movement == "TRASLADOS_OTRO_ALIADO":
                matched_rules.append("transfer_other_ally_template")
                return "inventory_transfer_other_ally"
            if movement == "TRASLADO_BODEGA":
                matched_rules.append("transfer_warehouse_template")
                return "inventory_transfer_warehouse"
        if intent == "association_query":
            matched_rules.append("association_query_to_serial_association_template")
            return "inventory_serial_association_departures"
        if intent == "notification_query":
            matched_rules.append("notification_query_pending_template")
            return "inventory_notification_pending"
        if intent == "report_generation":
            matched_rules.append("report_generation_to_semantic_report")
            return "inventory_semantic_report"
        if intent == "alert_query":
            matched_rules.append("alert_query_to_alert_semantic_report")
            return "inventory_alert_semantic_report"
        if intent == "assignment_distribution_query":
            matched_rules.append("assignment_distribution_pending_template")
            return "inventory_assignment_distribution_pending"
        if intent == "reconciliation_query":
            if business_concept == "consumo_vs_facturacion" and str(filters.get("bodega") or "").strip().lower() == "operacion_hfc":
                matched_rules.append("reconciliation_operacion_hfc_template")
                return "inventory_consumption_billing_operacion_hfc"
            matched_rules.append("reconciliation_pending_validation_template")
            return "inventory_reconciliation_pending_validation"
        if intent == "external_reconciliation_query":
            matched_rules.append("external_reconciliation_pending_template")
            return "inventory_external_reconciliation_pending"
        if intent in {"stock_balance", "stock_query"}:
            tipo_filter = filters.get("tipo")
            if material_family == "serializados" and set(group_by) & {"movil", "cedula", "bodega"} and str(filters.get("material_family") or "").strip():
                matched_rules.append("serial_stock_family_grouped_dimension_template")
                return "inventory_serial_stock_by_family_grouped_dimension"
            if material_family == "serializados" and group_by and set(group_by).issubset({"estado", "bodega", "ubicacion", "codigo"}):
                matched_rules.append("serial_stock_dimension_template")
                return "inventory_serial_stock_by_dimension"
            if business_concept == "materiales_criticos_por_empleado":
                matched_rules.append("critical_materials_template")
                return "inventory_material_critical_by_employee"
            if (
                set(group_by) & {"movil", "cedula", "bodega"}
                and any(str(filters.get(key) or "").strip() for key in ("codigo", "descripcion"))
                and not any(str(filters.get(key) or "").strip() for key in ("cedula", "movil"))
            ):
                matched_rules.append("stock_balance_grouped_dimension_template")
                return "inventory_material_stock_grouped_dimension"
            if (
                set(group_by) & {"movil", "cedula"}
                and isinstance(tipo_filter, str)
                and not any(str(filters.get(key) or "").strip() for key in ("cedula", "movil"))
            ):
                matched_rules.append("stock_balance_family_grouped_dimension_template")
                return "inventory_material_stock_grouped_dimension"
            if stock_scope == "movil" or entity_field in {"cedula", "movil"}:
                matched_rules.append("stock_scope_movil_template")
                return "inventory_material_stock_mobile"
            if stock_scope == "bodega" or "bodega" in set(group_by):
                matched_rules.append("stock_scope_bodega_template")
                return "inventory_material_stock_by_warehouse"
            matched_rules.append("generic_stock_balance_template")
            return "inventory_material_stock_balance"
        if intent == "movement_query":
            if "mes" in set(group_by):
                matched_rules.append("movement_query_by_month_template")
                return "inventory_entries_by_month"
            matched_rules.append("movement_query_detail_template")
            return "inventory_movement_detail"
        if intent == "return_query":
            matched_rules.append("return_query_legacy_transfer_template")
            return "inventory_transfer_warehouse"
        return ""

    @staticmethod
    def _resolve_inventory_template_legacy(
        *,
        intent: str,
        entity: dict[str, Any],
        filters: dict[str, Any],
        group_by: list[str],
        inference: dict[str, Any],
    ) -> str:
        entity_field = str(entity.get("field") or "").strip().lower()
        stock_scope = str(filters.get("stock_scope") or "").strip().lower()
        business_concept = str(inference.get("business_concept") or "").strip().lower()
        material_family = str(inference.get("material_family") or "").strip().lower()
        if intent == "movement_history":
            return "inventory_kardex_by_employee" if entity_field == "cedula" else "inventory_kardex_consolidated"
        if intent in {"stock_balance", "stock_query"}:
            tipo_filter = filters.get("tipo")
            if material_family == "serializados" and set(group_by) & {"movil", "cedula", "bodega"} and str(filters.get("material_family") or "").strip():
                return "inventory_serial_stock_by_family_grouped_dimension"
            if material_family == "serializados" and group_by:
                return "inventory_serial_stock_by_dimension"
            if business_concept == "materiales_criticos_por_empleado":
                return "inventory_material_critical_by_employee"
            if (
                set(group_by) & {"movil", "cedula", "bodega"}
                and any(str(filters.get(key) or "").strip() for key in ("codigo", "descripcion"))
                and not any(str(filters.get(key) or "").strip() for key in ("cedula", "movil"))
            ):
                return "inventory_material_stock_grouped_dimension"
            if (
                set(group_by) & {"movil", "cedula"}
                and isinstance(tipo_filter, str)
                and not any(str(filters.get(key) or "").strip() for key in ("cedula", "movil"))
            ):
                return "inventory_material_stock_grouped_dimension"
            if stock_scope == "movil":
                return "inventory_material_stock_mobile"
            if stock_scope == "bodega" or "bodega" in set(group_by):
                return "inventory_material_stock_by_warehouse"
            return "inventory_material_stock_balance"
        if intent == "transfer_query":
            movement = str(filters.get("movimiento") or "").strip().upper()
            if "bodega_destino" in set(group_by):
                return "inventory_transfer_destination_not_available"
            if movement == "TRASLADOS_OTRO_ALIADO":
                return "inventory_transfer_other_ally"
            if movement == "TRASLADO_BODEGA":
                return "inventory_transfer_warehouse"
        legacy_map = {
            "traceability_query": "inventory_traceability_by_serial",
            "risk_detection": "inventory_risk_consumo_movil_sin_validar",
            "consumption_query": "inventory_consumption_top"
            if str(inference.get("operation") or "").strip().lower() == "top"
            else "inventory_consumption_by_dimension",
            "association_query": "inventory_serial_association_departures",
            "serial_holder_query": "inventory_serial_by_operational_holder",
            "reconciliation_query": "inventory_consumption_billing_operacion_hfc"
            if business_concept == "consumo_vs_facturacion" and str(filters.get("bodega") or "").strip().lower() == "operacion_hfc"
            else "inventory_reconciliation_pending_validation",
            "external_reconciliation_query": "inventory_external_reconciliation_pending",
            "document_generation": "inventory_document_generation_pending",
            "report_generation": "inventory_semantic_report",
            "alert_query": "inventory_alert_semantic_report",
            "notification_query": "inventory_notification_pending",
            "assignment_distribution_query": "inventory_assignment_distribution_pending",
            "movement_query": "inventory_entries_by_month" if "mes" in set(group_by) else "inventory_movement_detail",
            "return_query": "inventory_transfer_warehouse",
        }
        return str(legacy_map.get(intent) or "")

    @staticmethod
    def _build_output_profile(
        *,
        template_id: str,
        binding: dict[str, Any],
        plan_payload: dict[str, Any],
        filters: dict[str, Any],
        inference: dict[str, Any],
    ) -> dict[str, Any]:
        plan_output = dict(plan_payload.get("output") or {})
        columns = list(binding.get("columns") or plan_output.get("columns") or [])
        include_serialized = bool(
            ((plan_payload.get("scope") or {}).get("include_serialized"))
            or inference.get("governed_match", {}).get("incluye_serializados")
            or inference.get("material_family") == "serializados"
        )
        if template_id == "inventory_material_stock_mobile" and include_serialized and not filters.get("tipo"):
            extra = ["serializados.serial", "serializados.estado", "serializados.saldo"]
            columns = list(dict.fromkeys([*columns, *extra]))
        return {
            "expected_output": str(binding.get("expected_output") or plan_output.get("expected_output") or ""),
            "grain": str(binding.get("grain") or plan_output.get("grain") or ""),
            "columns": [str(item or "") for item in columns if str(item or "").strip()],
        }

    @staticmethod
    def _resolve_response_profile(
        *,
        template_id: str,
        binding: dict[str, Any],
        filters: dict[str, Any],
        inference: dict[str, Any],
        governed_rules: list[dict[str, Any]],
    ) -> str:
        response_profile = str(binding.get("response_profile") or "").strip()
        if template_id == "inventory_material_stock_mobile" and not filters.get("tipo"):
            for rule in governed_rules:
                if str(rule.get("codigo") or "") != "inventario.scope.dual_block_unspecified_family":
                    continue
                if bool(
                    inference.get("governed_match", {}).get("incluye_serializados")
                    or str(filters.get("movil") or "").strip()
                    or str(filters.get("cedula") or "").strip()
                ):
                    return str(
                        dict(rule.get("result_json") or {}).get("response_profile_override")
                        or "inventory.stock.mobile.dual_block"
                    )
        return response_profile
