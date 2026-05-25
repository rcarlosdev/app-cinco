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
    CapabilityPackBundle,
    capability_pack_trace_payload,
    load_inventory_capability_pack,
)
from apps.ia_dev.domains.empleados.paquete_capacidades_loader import (
    capability_pack_trace_payload as employee_capability_pack_trace_payload,
)
from apps.ia_dev.domains.empleados.paquete_capacidades_loader import (
    load_employee_capability_pack,
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

EMPLOYEES_CONSULTED_METADATA = [
    "ai_dictionary.dd_tablas",
    "ai_dictionary.dd_campos",
    "ai_dictionary.dd_relaciones",
    "ai_dictionary.dd_sinonimos",
    "ai_dictionary.dd_reglas",
    "ai_dictionary.ia_dev_capacidades_columna",
    "ToolRegistryService",
    "ResolvedQuerySpec",
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
    "inventory_provider_serial_validation": {
        "candidate_capability": "inventory_provider_serial_validation",
        "planner_route_hint": "inventory.serial.validation.provider_file",
        "response_profile": "inventory.serial.validation.provider_file.detail",
        "expected_output": "validacion_seriales_proveedor",
        "grain": "serial_proveedor_validado",
        "columns": [
            "fila_archivo",
            "serial_proveedor",
            "material_proveedor",
            "denominacion_proveedor",
            "familia_proveedor",
            "encontrado",
            "fuente",
            "estado",
            "estado_contiene_movil",
            "movil_asociado",
            "cedula_persona",
            "nombre",
            "apellido",
            "empleado",
            "bodega",
            "codigo_interno",
            "descripcion_interna",
            "ultima_fecha_encontrada",
            "duplicado_en_archivo",
            "ocurrencias_archivo",
            "solo_historico",
            "fuentes_coincidencia",
            "tablas_consultadas",
            "tablas_historicas_no_existian",
            "observacion_operativa",
        ],
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
    "inventory_provider_serial_validation": "inventory_provider_serial_validation",
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
    migration_pending: bool = False
    unresolved_reason: str = ""
    legacy_mapping_used: bool = False
    legacy_reason: str = ""
    legacy_retained_reason: str = ""
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
    capability_pack_coverage: float = 0.0
    templates_pack_driven_count: int = 0
    templates_legacy_allowed_count: int = 0
    templates_missing_selection_rules: list[str] = field(default_factory=list)

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
            "migration_pending": bool(self.migration_pending),
            "unresolved_reason": str(self.unresolved_reason or ""),
            "legacy_mapping_used": bool(self.legacy_mapping_used),
            "legacy_reason": str(self.legacy_reason or ""),
            "legacy_retained_reason": str(self.legacy_retained_reason or self.legacy_reason or ""),
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
            "capability_pack_coverage": float(self.capability_pack_coverage or 0.0),
            "templates_pack_driven_count": int(self.templates_pack_driven_count or 0),
            "templates_legacy_allowed_count": int(self.templates_legacy_allowed_count or 0),
            "templates_missing_selection_rules": [
                str(item or "") for item in list(self.templates_missing_selection_rules or []) if str(item or "").strip()
            ],
        }


class SemanticCapabilityRegistry:
    def __init__(self, *, tool_registry_service: ToolRegistryService | None = None):
        self.tool_registry_service = tool_registry_service or ToolRegistryService()

    def resolve(self, request: SemanticBindingRequest) -> SemanticBindingDecision:
        domain = str(request.domain or "").strip().lower()
        if domain == "inventario_logistica":
            return self._resolve_inventory(request=request)
        if domain == "empleados":
            return self._resolve_empleados(request=request)
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

    def _resolve_empleados(self, *, request: SemanticBindingRequest) -> SemanticBindingDecision:
        semantic_context = dict(request.semantic_context or {})
        plan_payload = self._plan_payload(request.business_query_semantic_plan)
        resolved_semantic = dict(semantic_context.get("resolved_semantic") or {})
        source_hints = dict(request.source_hints or {})
        capability_pack = load_employee_capability_pack(tool_registry_service=self.tool_registry_service)
        capability_pack_trace = employee_capability_pack_trace_payload(capability_pack)
        filters = dict(request.normalized_filters or plan_payload.get("normalized_filters") or {})
        intent = str(request.intent or plan_payload.get("intent") or "").strip().lower()
        group_by = [
            str(item or "").strip().lower()
            for item in list(request.group_by or source_hints.get("group_by") or [])
            if str(item or "").strip()
        ]
        message = str(request.message or "").strip().lower()
        explicit_template = str(
            source_hints.get("template_id")
            or plan_payload.get("template_id")
            or ""
        ).strip().lower()
        metrics = [
            str(item or "").strip().lower()
            for item in list(source_hints.get("metrics") or plan_payload.get("metrics") or [])
            if str(item or "").strip()
        ]
        field_match = dict(resolved_semantic.get("field_match") or semantic_context.get("semantic_field_match") or {})
        status_value = str(filters.get("estado") or filters.get("estado_empleado") or "").strip().upper()
        detail_filters_present = {
            key
            for key in ("cedula", "cedula_empleado", "identificacion", "documento", "id_empleado", "movil", "nombre", "area", "cargo", "supervisor", "carpeta", "sede", "tipo_labor", "estado", "estado_empleado", "search")
            if (
                isinstance(filters.get(key), dict) and bool(filters.get(key))
            ) or str(filters.get(key) or "").strip()
        }
        has_identifier = any(
            str(filters.get(key) or "").strip()
            for key in (
                "cedula",
                "cedula_empleado",
                "identificacion",
                "documento",
                "id_empleado",
                "movil",
                "codigo_sap",
                "nombre",
                "search",
            )
        )
        is_birthday_query = bool(
            str(filters.get("fnacimiento_month") or "").strip()
            or explicit_template == "count_records_by_period"
            or any(token in message for token in ("cumple", "cumpleanos", "nacimiento"))
        )
        is_turnover_query = "turnover_rate" in metrics or any(token in message for token in ("rotacion", "turnover"))
        is_missingness_query = any(isinstance(value, dict) and value for value in filters.values())
        field_logical_name = str(field_match.get("logical_name") or "").strip().lower()
        is_heights_query = bool(
            field_logical_name.startswith("certificado_alturas_")
            or any(token in message for token in ("certificado de altura", "certificados de altura", "alturas"))
        )
        is_explicit_detail_request = bool(
            explicit_template == "detail_by_entity_and_period"
            or intent == "detail"
            or has_identifier
        )
        if (
            not status_value
            and not is_explicit_detail_request
            and not any((is_birthday_query, is_turnover_query, is_heights_query, is_missingness_query))
        ):
            filters["estado"] = "ACTIVO"
            status_value = "ACTIVO"
        business_concepts = {
            concept
            for concept, applies in (
                ("birthday", is_birthday_query),
                ("turnover", is_turnover_query),
                ("heights_certificate_validity", is_heights_query),
                ("missingness", is_missingness_query),
            )
            if applies
        }
        date_semantics = self._employee_date_semantics(
            message=message,
            filters=filters,
            group_by=group_by,
            business_concepts=business_concepts,
        )
        is_grouped_ambiguous_query = bool(
            not group_by
            and not business_concepts
            and any(token in message for token in ("distribucion", "agrupa", "agrupado"))
        )
        is_detail_candidate = bool(is_explicit_detail_request or (has_identifier and not group_by))
        template_id = explicit_template or (
            "detail_by_entity_and_period"
            if is_detail_candidate
            else ("aggregate_by_group_and_period" if group_by else "count_entities_by_status")
        )
        matched_rules: list[str] = []
        metadata_rule_trace: list[str] = []
        candidate_capability = ""
        response_profile = ""
        planner_route_hint = ""
        output_profile: dict[str, Any] = {}
        source = ""
        confidence = 0.0
        fallback_used = False
        legacy_mapping_used = False
        legacy_reason = ""
        unresolved_reason = ""
        migration_pending = False
        fallback_sombreado_usado = False

        pack_template_id, binding, selection_rule_trace, pack_match_failure = self._resolve_employee_template_from_capability_pack(
            capability_pack=capability_pack,
            template_id=template_id,
            intent=intent,
            filters=filters,
            group_by=group_by,
            status_value=status_value,
            has_identifier=has_identifier,
            business_concepts=business_concepts,
            date_semantics=date_semantics,
        )
        if pack_template_id:
            template_id = pack_template_id
            capability = dict(capability_pack.capabilities_by_template.get(pack_template_id) or {})
            profile = dict(
                capability_pack.response_profiles_by_id.get(str(binding.get("response_profile") or capability.get("response_profile") or "").strip())
                or {}
            )
            source = "capability_pack"
            confidence = (
                0.94
                if template_id == "count_entities_by_status"
                else (0.93 if template_id == "aggregate_by_group_and_period" else 0.92)
            )
            matched_rules.extend(
                [
                    "employee_count_entities_by_status_pack"
                    if template_id == "count_entities_by_status"
                    else (
                        "employee_aggregate_by_group_pack"
                        if template_id == "aggregate_by_group_and_period"
                        else "employee_detail_by_entity_pack"
                    )
                ]
            )
            matched_rules.extend(selection_rule_trace)
            metadata_rule_trace.extend(
                [
                    str(item or "").strip()
                    for item in selection_rule_trace
                    if str(item or "").strip().startswith("empleados.")
                ]
            )
            candidate_capability = str(binding.get("candidate_capability") or capability.get("capability_id") or "").strip()
            response_profile = str(binding.get("response_profile") or capability.get("response_profile") or "").strip()
            planner_route_hint = str(binding.get("planner_route_hint") or capability.get("planner_route_hint") or "").strip()
            output_profile = self._build_employee_output_profile(
                template_id=template_id,
                group_by=group_by,
                response_profile=response_profile,
                capability_pack=capability_pack,
                filters=filters,
            )
        else:
            source = "legacy_shadow_fallback"
            confidence = 0.71
            fallback_used = True
            legacy_mapping_used = True
            migration_pending = True
            fallback_sombreado_usado = True
            matched_rules.append("legacy_employee_template_map_fallback")
            if template_id == "detail_by_entity_and_period" or has_identifier:
                template_id = "detail_by_entity_and_period"
                candidate_capability = "empleados.detail.v1"
                response_profile = "empleados.detail.safe_table"
                planner_route_hint = "empleados.population.detail_legacy"
                legacy_reason = pack_match_failure or "empleados.limit.detail_ambiguous_request"
            elif is_birthday_query:
                template_id = "count_records_by_period"
                response_profile = "empleados.birthday.summary"
                planner_route_hint = "empleados.birthdays.pending_pack"
                legacy_reason = pack_match_failure or "empleados.limit.birthday_ambiguous_period"
            elif is_heights_query:
                template_id = "count_entities_by_status"
                candidate_capability = "empleados.count.active.v1"
                response_profile = "empleados.certificados_alturas.summary"
                planner_route_hint = "empleados.heights_certificate.pending_pack"
                legacy_reason = "empleados.limit.heights_certificate_pending_pack"
            elif is_turnover_query:
                template_id = "count_entities_by_status"
                candidate_capability = "empleados.count.active.v1"
                response_profile = "empleados.count.grouped.summary"
                planner_route_hint = "empleados.turnover.pending_pack"
                legacy_reason = "empleados.limit.turnover_pending_pack"
            elif is_missingness_query:
                template_id = "detail_by_entity_and_period"
                response_profile = "empleados.detail.safe_table"
                planner_route_hint = "empleados.missingness.pending_pack"
                legacy_reason = "empleados.limit.missingness_pending_pack"
            elif group_by:
                template_id = "aggregate_by_group_and_period"
                candidate_capability = "empleados.count.active.v1"
                response_profile = "empleados.count.grouped.summary"
                planner_route_hint = "empleados.population.grouped_legacy"
                legacy_reason = pack_match_failure or "empleados.limit.grouped_population_metadata_gap"
            elif is_grouped_ambiguous_query:
                template_id = "aggregate_by_group_and_period"
                candidate_capability = "empleados.count.active.v1"
                response_profile = "empleados.count.grouped.summary"
                planner_route_hint = "empleados.population.grouped_legacy"
                legacy_reason = "empleados.limit.grouped_population_ambiguous_request"
            else:
                template_id = template_id or "count_entities_by_status"
                candidate_capability = "empleados.count.active.v1" if status_value in {"ACTIVO", "INACTIVO"} else ""
                response_profile = "empleados.count.active.summary"
                planner_route_hint = "empleados.population.pending_pack"
                legacy_reason = pack_match_failure or "empleados.limit.grouped_population_metadata_gap"
            output_profile = self._build_employee_output_profile(
                template_id=template_id,
                group_by=group_by,
                response_profile=response_profile,
                capability_pack=capability_pack,
                filters=filters,
            )
        tool_id = self.tool_registry_service.map_capability_to_tool(candidate_capability) if candidate_capability else ""
        if tool_id:
            matched_rules.append("tool_id_resolved_via_tool_registry")
        if not template_id:
            unresolved_reason = "employee_template_unresolved"
        if not candidate_capability and template_id not in {"count_records_by_period"}:
            unresolved_reason = unresolved_reason or "employee_capability_unresolved"
        return SemanticBindingDecision(
            domain="empleados",
            intent=intent,
            entity=self._entity_from_filters(filters),
            normalized_filters=filters,
            output_profile=output_profile,
            candidate_capability=candidate_capability,
            template_id=template_id,
            planner_route_hint=planner_route_hint,
            response_profile=response_profile,
            tool_id=tool_id,
            source=source,
            matched_rules=list(dict.fromkeys(matched_rules)),
            consulted_metadata=list(EMPLOYEES_CONSULTED_METADATA),
            confidence=confidence,
            fallback_used=fallback_used,
            migration_pending=migration_pending,
            unresolved_reason=unresolved_reason,
            legacy_mapping_used=legacy_mapping_used,
            legacy_reason=legacy_reason,
            legacy_retained_reason=legacy_reason,
            migration_target="semantic_capability_registry.empleados_pack_migration" if migration_pending else "",
            regla_metadata_usada=list(dict.fromkeys(metadata_rule_trace)),
            fuente_dd=[
                "ai_dictionary.dd_tablas",
                "ai_dictionary.dd_campos",
                "ai_dictionary.dd_relaciones",
                "ai_dictionary.dd_sinonimos",
                "ai_dictionary.dd_reglas",
                "ai_dictionary.ia_dev_capacidades_columna",
            ],
            fallback_sombreado_usado=fallback_sombreado_usado,
            regla_legacy_detectada=legacy_mapping_used,
            regla_migrada=bool(source == "capability_pack"),
            paquete_capacidad_usado=str(capability_pack_trace.get("paquete_capacidad_usado") or ""),
            version_paquete=str(capability_pack_trace.get("version_paquete") or ""),
            capacidades_declaradas=list(capability_pack_trace.get("capacidades_declaradas") or []),
            reglas_declaradas=list(capability_pack_trace.get("reglas_declaradas") or []),
            perfiles_respuesta=list(capability_pack_trace.get("perfiles_respuesta") or []),
            evaluaciones_asociadas=list(capability_pack_trace.get("evaluaciones_asociadas") or []),
            capability_pack_coverage=float(capability_pack_trace.get("capability_pack_coverage") or 0.0),
            templates_pack_driven_count=int(capability_pack_trace.get("templates_pack_driven_count") or 0),
            templates_legacy_allowed_count=int(capability_pack_trace.get("templates_legacy_allowed_count") or 0),
            templates_missing_selection_rules=list(capability_pack_trace.get("templates_missing_selection_rules") or []),
        )

    @staticmethod
    def _build_employee_output_profile(
        *,
        template_id: str,
        group_by: list[str],
        response_profile: str,
        capability_pack: Any,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        profile = dict(capability_pack.response_profiles_by_id.get(str(response_profile or "").strip()) or {})
        if template_id == "aggregate_by_group_and_period":
            columns = [str(item or "").strip() for item in list(group_by or []) if str(item or "").strip()]
            return {
                "expected_output": str(profile.get("expected_output") or "total_personal_agrupado"),
                "grain": str(profile.get("grain") or "total_por_dimension"),
                "columns": [*columns, "cantidad"],
            }
        normalized_filters = dict(filters or {})
        if template_id == "detail_by_entity_and_period" and str(normalized_filters.get("fnacimiento_month") or "").strip():
            return {
                "expected_output": "cumpleanos_personal",
                "grain": "empleado",
                "columns": ["cedula", "nombre", "apellido", "cargo", "area", "fecha_nacimiento", "estado"],
            }
        if profile:
            return {
                "expected_output": str(profile.get("expected_output") or ""),
                "grain": str(profile.get("grain") or ""),
                "columns": [str(item or "") for item in list(profile.get("columnas") or []) if str(item or "").strip()],
            }
        if template_id == "detail_by_entity_and_period":
            if str(normalized_filters.get("movil") or "").strip():
                columns = ["cedula", "nombre", "apellido", "cargo", "area", "carpeta", "tipo_labor", "movil", "estado"]
            else:
                columns = ["cedula", "nombre", "apellido", "cargo", "area", "supervisor", "carpeta", "tipo_labor", "movil", "sede", "estado"]
            return {"expected_output": "detalle_empleado_seguro", "grain": "empleado", "columns": columns}
        if template_id == "aggregate_by_group_and_period":
            return {"expected_output": "total_personal_agrupado", "grain": "total_por_dimension", "columns": [*group_by, "cantidad"]}
        if template_id == "count_records_by_period":
            return {"expected_output": "cumpleanos_personal", "grain": "empleado", "columns": ["cedula", "nombre", "fecha_nacimiento", "area"]}
        return {"expected_output": "total_personal", "grain": "kpi_total_personal", "columns": ["estado", "total_empleados"]}

    @staticmethod
    def _resolve_employee_template_from_capability_pack(
        *,
        capability_pack: Any,
        template_id: str,
        intent: str,
        filters: dict[str, Any],
        group_by: list[str],
        status_value: str,
        has_identifier: bool,
        business_concepts: set[str],
        date_semantics: set[str],
    ) -> tuple[str, dict[str, Any], list[str], str]:
        template_candidates: list[str] = []
        normalized_template = str(template_id or "").strip().lower()
        if normalized_template:
            template_candidates.append(normalized_template)
        if group_by:
            template_candidates.append("aggregate_by_group_and_period")
        elif normalized_template == "detail_by_entity_and_period" or intent == "detail" or has_identifier:
            template_candidates.append("detail_by_entity_and_period")
        else:
            template_candidates.append("count_entities_by_status")
        for candidate_template in list(dict.fromkeys(template_candidates)):
            binding = dict(capability_pack.semantic_bindings_by_template.get(candidate_template) or {})
            if not binding:
                continue
            matched_rules = SemanticCapabilityRegistry._employee_selection_rules_match(
                binding=binding,
                intent=intent,
                filters=filters,
                group_by=group_by,
                status_value=status_value,
                has_identifier=has_identifier,
                business_concepts=business_concepts,
                date_semantics=date_semantics,
            )
            if matched_rules:
                return candidate_template, binding, matched_rules, ""

        if normalized_template == "detail_by_entity_and_period" or intent == "detail" or has_identifier:
            detail_binding = dict(capability_pack.semantic_bindings_by_template.get("detail_by_entity_and_period") or {})
            return "", {}, [], SemanticCapabilityRegistry._employee_detail_pack_failure_reason(
                binding=detail_binding,
                filters=filters,
                group_by=group_by,
            )
        if group_by:
            declared_groupings = {
                str(item or "").strip().lower()
                for item in list(
                    (capability_pack.semantic_bindings_by_template.get("aggregate_by_group_and_period") or {}).get("grouping_fields") or []
                )
                if str(item or "").strip()
            }
            normalized_group_by = {str(item or "").strip().lower() for item in list(group_by or []) if str(item or "").strip()}
            if declared_groupings and not normalized_group_by.issubset(declared_groupings):
                return "", {}, [], "empleados.limit.grouped_population_undeclared_dimension"
            if "birthday" in business_concepts and date_semantics and not (date_semantics & {"birthday_month", "birthday_by_month"}):
                return "", {}, [], "empleados.limit.birthday_ambiguous_period"
            return "", {}, [], "empleados.limit.grouped_population_metadata_gap"

        if "birthday" in business_concepts:
            if date_semantics & {"birthday_today", "birthday_upcoming"}:
                return "", {}, [], "empleados.limit.birthday_ambiguous_period"
            if not date_semantics or "birthday_generic" in date_semantics:
                return "", {}, [], "empleados.limit.birthday_insufficient_metadata"
            return "", {}, [], "empleados.limit.birthday_insufficient_metadata"

        return "", {}, [], ""

    @staticmethod
    def _employee_detail_pack_failure_reason(
        *,
        binding: dict[str, Any],
        filters: dict[str, Any],
        group_by: list[str],
    ) -> str:
        if group_by:
            return "empleados.limit.detail_ambiguous_request"
        declared_filter_fields = {
            str(item or "").strip()
            for item in list(binding.get("filter_fields") or [])
            if str(item or "").strip()
        }
        alias_to_canonical = {
            "cedula_empleado": "cedula",
            "identificacion": "cedula",
            "documento": "cedula",
            "id_empleado": "cedula",
            "estado_empleado": "estado",
        }
        populated_scalar_filters = {
            alias_to_canonical.get(str(key or "").strip(), str(key or "").strip())
            for key, value in dict(filters or {}).items()
            if str(key or "").strip()
            and not isinstance(value, dict)
            and str(value or "").strip()
        }
        populated_structured_filters = {
            alias_to_canonical.get(str(key or "").strip(), str(key or "").strip())
            for key, value in dict(filters or {}).items()
            if str(key or "").strip() and isinstance(value, dict) and bool(value)
        }
        populated_filters = populated_scalar_filters | populated_structured_filters
        if populated_filters == {"search"}:
            return "empleados.limit.detail_unverifiable_entity"
        if populated_filters - declared_filter_fields:
            return "empleados.limit.detail_undeclared_filter"
        if not populated_filters:
            return "empleados.limit.detail_ambiguous_request"
        if not declared_filter_fields:
            return "empleados.limit.detail_insufficient_metadata"
        return "empleados.limit.detail_insufficient_metadata"

    @staticmethod
    def _employee_selection_rules_match(
        *,
        binding: dict[str, Any],
        intent: str,
        filters: dict[str, Any],
        group_by: list[str],
        status_value: str,
        has_identifier: bool,
        business_concepts: set[str],
        date_semantics: set[str],
    ) -> list[str]:
        normalized_group_by = [str(item or "").strip().lower() for item in list(group_by or []) if str(item or "").strip()]
        for selector in list(binding.get("selection_rules") or []):
            if not isinstance(selector, dict):
                continue
            selector_intents = {
                str(item or "").strip().lower()
                for item in list(selector.get("intent_ids") or binding.get("intent_ids") or [])
                if str(item or "").strip()
            }
            if selector_intents and str(intent or "").strip().lower() not in selector_intents and str(intent or "").strip():
                continue
            if selector.get("group_by_required") and not normalized_group_by:
                continue
            selector_grouping_fields = {
                str(item or "").strip().lower()
                for item in list(selector.get("group_by_all_in") or [])
                if str(item or "").strip()
            }
            if selector_grouping_fields and not set(normalized_group_by).issubset(selector_grouping_fields):
                continue
            required_status_values = {
                str(item or "").strip().upper()
                for item in list(selector.get("required_status_values") or [])
                if str(item or "").strip()
            }
            if required_status_values and str(status_value or "").strip().upper() not in required_status_values:
                continue
            if has_identifier and list(selector.get("normalized_filters_absent") or []):
                continue
            if any(str(filters.get(key) or "").strip() for key in list(selector.get("normalized_filters_absent") or [])):
                continue
            if selector.get("group_by_absent") and normalized_group_by:
                continue
            normalized_filters_any_of = {
                str(item or "").strip()
                for item in list(selector.get("normalized_filters_any_of") or [])
                if str(item or "").strip()
            }
            if normalized_filters_any_of and not any(str(filters.get(key) or "").strip() for key in normalized_filters_any_of):
                continue
            normalized_filters_all_in = {
                str(item or "").strip()
                for item in list(selector.get("normalized_filters_all_in") or [])
                if str(item or "").strip()
            }
            populated_filter_keys = {
                str(key or "").strip()
                for key, value in dict(filters or {}).items()
                if str(key or "").strip()
                and (
                    (isinstance(value, dict) and bool(value))
                    or str(value or "").strip()
                )
            }
            alias_to_canonical = {
                "cedula_empleado": "cedula",
                "identificacion": "cedula",
                "documento": "cedula",
                "id_empleado": "cedula",
                "estado_empleado": "estado",
            }
            populated_filter_keys = {
                alias_to_canonical.get(item, item)
                for item in populated_filter_keys
            }
            if normalized_filters_all_in and not populated_filter_keys.issubset(normalized_filters_all_in):
                continue
            forbidden_concepts = {
                str(item or "").strip()
                for item in list(selector.get("forbid_business_concepts") or [])
                if str(item or "").strip()
            }
            if forbidden_concepts & set(business_concepts or set()):
                continue
            required_concepts = {
                str(item or "").strip()
                for item in list(selector.get("required_business_concepts") or [])
                if str(item or "").strip()
            }
            if required_concepts and not required_concepts.issubset(set(business_concepts or set())):
                continue
            period_fields_any_of = {
                str(item or "").strip()
                for item in list(selector.get("period_fields_any_of") or [])
                if str(item or "").strip()
            }
            if period_fields_any_of and not any(str(filters.get(key) or "").strip() for key in period_fields_any_of):
                continue
            selector_date_semantics = {
                str(item or "").strip()
                for item in list(selector.get("date_semantics_any_of") or [])
                if str(item or "").strip()
            }
            if selector_date_semantics and not (selector_date_semantics & set(date_semantics or set())):
                continue
            declared_rules = [
                str(item or "").strip()
                for item in list(selector.get("declared_rules") or [])
                if str(item or "").strip()
            ]
            return declared_rules or [str(binding.get("template_id") or "").strip()]
        return []

    @staticmethod
    def _employee_date_semantics(
        *,
        message: str,
        filters: dict[str, Any],
        group_by: list[str],
        business_concepts: set[str],
    ) -> set[str]:
        if "birthday" not in set(business_concepts or set()):
            return set()
        normalized_message = str(message or "").strip().lower()
        if str(filters.get("fnacimiento_month") or "").strip():
            return {"birthday_month"}
        normalized_group_by = {str(item or "").strip().lower() for item in list(group_by or []) if str(item or "").strip()}
        if "birth_month" in normalized_group_by:
            return {"birthday_by_month"}
        if "hoy" in normalized_message:
            return {"birthday_today"}
        if "proxim" in normalized_message:
            return {"birthday_upcoming"}
        return {"birthday_generic"}

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
        if "runtime_attachment_summary" not in inference and semantic_context.get("runtime_attachment_summary"):
            inference["runtime_attachment_summary"] = dict(semantic_context.get("runtime_attachment_summary") or {})
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
        template_id, governed_binding_payload, metadata_rule_trace = self._resolve_inventory_template_from_capability_pack(
            capability_pack=capability_pack,
            intent=intent,
            entity=entity,
            filters=filters,
            group_by=group_by,
            inference=inference,
            plan_payload=plan_payload,
            explicit_template=explicit_template,
            ignore_explicit_template=self._should_ignore_explicit_inventory_template(
                explicit_template=explicit_template,
                filters=filters,
                group_by=group_by,
                inference=inference,
                governed_match=governed_match,
            ),
        )
        if template_id:
            source = "capability_pack"
            matched_rules.extend(metadata_rule_trace)
            confidence = 0.96 if governed_match.get("coincidencia_gobernada") else 0.93

        if not template_id:
            template_id = self._resolve_inventory_template_legacy(
                intent=intent,
                entity=entity,
                filters=filters,
                group_by=group_by,
                inference=inference,
            )
            if template_id:
                source = "legacy_shadow_fallback"
                matched_rules.append("legacy_inventory_template_map_fallback")
                confidence = 0.7
                legacy_mapping_used = True
                fallback_sombreado_usado = True
                legacy_reason = "semantic_registry_rule_not_available_for_inventory_shape"
                migration_target = "semantic_capability_registry.inventory_template_resolution"
                governed_binding_payload, metadata_rule_trace = self._binding_payload_from_template_or_rules(
                    template_id=template_id,
                    governed_rules=governed_rules,
                    capability_pack=capability_pack,
                )

        semantic_binding = dict(
            capability_pack.semantic_bindings_by_template.get(template_id) or {}
        )
        legacy_binding = dict(INVENTORY_TEMPLATE_BINDINGS.get(template_id) or {})
        binding = {
            **legacy_binding,
            **semantic_binding,
            **governed_binding_payload,
        }
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
        if template_id and not semantic_binding:
            matched_rules.append("capability_pack_semantic_binding_missing_template")
            fallback_sombreado_usado = True
        if pack_binding:
            source = source or "capability_pack_validated_binding"
        elif semantic_binding:
            source = source or "capability_pack_semantic_binding"
        candidate_capability = (
            str(plan_payload.get("candidate_capability") or "").strip()
            or str(governed_match.get("capacidad_candidata") or "").strip()
            or str(semantic_binding.get("candidate_capability") or "").strip()
            or str(pack_binding.get("capability_id") or "").strip()
            or str(binding.get("candidate_capability") or "").strip()
        )
        if candidate_capability:
            matched_rules.append("candidate_capability_bound_from_registry")
        declared_tool_ids = list(
            dict.fromkeys(
                [
                    *[
                        str(item or "").strip()
                        for item in list(pack_binding.get("tools") or [])
                        if str(item or "").strip()
                    ],
                    str(semantic_binding.get("tool_id") or "").strip(),
                ]
            )
        )
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
            binding={
                **binding,
                **({"response_profile": semantic_binding.get("response_profile")} if semantic_binding else {}),
                **({"response_profile": pack_binding.get("response_profile")} if pack_binding else {}),
            },
            filters=filters,
            inference=inference,
            governed_rules=governed_rules,
        )
        planner_route_hint = str(
            semantic_binding.get("planner_route_hint")
            or pack_binding.get("planner_route_hint")
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
        templates_missing_selection_rules = list(capability_pack_trace.get("templates_missing_selection_rules") or [])

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
            migration_pending=legacy_mapping_used,
            unresolved_reason=unresolved_reason,
            legacy_mapping_used=legacy_mapping_used,
            legacy_reason=legacy_reason,
            legacy_retained_reason=legacy_reason,
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
            capability_pack_coverage=float(capability_pack_trace.get("capability_pack_coverage") or 0.0),
            templates_pack_driven_count=int(capability_pack_trace.get("templates_pack_driven_count") or 0),
            templates_legacy_allowed_count=int(capability_pack_trace.get("templates_legacy_allowed_count") or 0),
            templates_missing_selection_rules=templates_missing_selection_rules,
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
        capability_pack: CapabilityPackBundle,
    ) -> tuple[dict[str, Any], list[str]]:
        template = str(template_id or "").strip()
        if not template:
            return {}, []
        for rule in sorted(governed_rules, key=lambda item: int(item.get("priority") or 0), reverse=True):
            result = dict(rule.get("result_json") or {})
            if str(result.get("template_id") or "").strip() == template:
                return dict(result), [str(rule.get("codigo") or rule.get("rule_name") or "").strip()]
        semantic_binding = dict(capability_pack.semantic_bindings_by_template.get(template) or {})
        if semantic_binding:
            return semantic_binding, []
        return dict(INVENTORY_TEMPLATE_BINDINGS.get(template) or {}), []

    def _resolve_inventory_template_from_capability_pack(
        self,
        *,
        capability_pack: CapabilityPackBundle,
        intent: str,
        entity: dict[str, Any],
        filters: dict[str, Any],
        group_by: list[str],
        inference: dict[str, Any],
        plan_payload: dict[str, Any],
        explicit_template: str,
        ignore_explicit_template: bool,
    ) -> tuple[str, dict[str, Any], list[str]]:
        entity_field = str(entity.get("field") or "").strip().lower()
        output_profile = dict(plan_payload.get("output") or {})
        requested_grain = str(output_profile.get("grain") or "").strip().lower()
        grouped_fields = {
            str(item or "").strip().lower()
            for item in list(group_by or [])
            if str(item or "").strip()
        }
        available_rules = {
            str(rule_id or "").strip()
            for binding in list(capability_pack.semantic_bindings or [])
            if isinstance(binding, dict)
            for rule_id in list((capability_pack.capabilities_by_template.get(str(binding.get("template_id") or "").strip()) or {}).get("reglas") or [])
            if str(rule_id or "").strip()
        }
        selected: tuple[int, str, dict[str, Any], list[str]] | None = None
        for binding in list(capability_pack.semantic_bindings or []):
            if not isinstance(binding, dict):
                continue
            template_id = str(binding.get("template_id") or "").strip().lower()
            if not template_id:
                continue
            selectors = [dict(item) for item in list(binding.get("selection_rules") or []) if isinstance(item, dict)]
            if not selectors:
                selectors = [dict(binding)]
            capability = dict(capability_pack.capabilities_by_template.get(template_id) or {})
            for selector in selectors:
                if not self._inventory_pack_selector_matches(
                    selector=selector,
                    binding=binding,
                    available_rules=available_rules,
                    intent=intent,
                    entity_field=entity_field,
                    filters=filters,
                    group_by=grouped_fields,
                    inference=inference,
                    requested_grain=requested_grain,
                ):
                    continue
                priority = int(selector.get("priority") or binding.get("selection_priority") or 0)
                declared_rules = [
                    str(item or "").strip()
                    for item in list(selector.get("declared_rules") or capability.get("reglas") or [])
                    if str(item or "").strip()
                ]
                candidate = (priority, template_id, dict(binding), declared_rules)
                if selected is None or candidate[0] > selected[0]:
                    selected = candidate
        if selected is not None:
            _, template_id, binding, declared_rules = selected
            return template_id, binding, declared_rules
        return "", {}, []

    @staticmethod
    def _inventory_pack_selector_matches(
        *,
        selector: dict[str, Any],
        binding: dict[str, Any],
        available_rules: set[str],
        intent: str,
        entity_field: str,
        filters: dict[str, Any],
        group_by: set[str],
        inference: dict[str, Any],
        requested_grain: str,
    ) -> bool:
        intent_ids = {
            str(item or "").strip().lower()
            for item in list(selector.get("intent_ids") or binding.get("intent_ids") or [])
            if str(item or "").strip()
        }
        if intent_ids and str(intent or "").strip().lower() not in intent_ids:
            return False
        raw_entity_fields = selector.get("entity_fields") if "entity_fields" in selector else binding.get("entity_fields")
        entity_fields = {
            str(item or "").strip().lower()
            for item in list(raw_entity_fields or [])
            if str(item or "").strip()
        }
        if entity_fields:
            normalized_filter_fields = {
                str(key or "").strip().lower()
                for key, value in dict(filters or {}).items()
                if value not in (None, "", [], {})
            }
            if entity_field in entity_fields:
                pass
            elif entity_fields & normalized_filter_fields:
                pass
            else:
                return False
        families = {
            str(item or "").strip().lower()
            for item in list(selector.get("families") or binding.get("families") or [])
            if str(item or "").strip()
        }
        if families and not (families & SemanticCapabilityRegistry._inventory_family_candidates(filters=filters, inference=inference)):
            return False
        output_profiles = {
            str(item or "").strip().lower()
            for item in list(selector.get("output_profiles") or binding.get("output_profiles") or [])
            if str(item or "").strip()
        }
        if output_profiles and requested_grain and requested_grain not in output_profiles:
            return False
        require_any_filters = {
            str(item or "").strip().lower()
            for item in list(selector.get("normalized_filters_any_of") or [])
            if str(item or "").strip()
        }
        if require_any_filters and not any(str(filters.get(field) or "").strip() for field in require_any_filters):
            return False
        require_all_filters = {
            str(item or "").strip().lower()
            for item in list(selector.get("normalized_filters_all_of") or [])
            if str(item or "").strip()
        }
        if require_all_filters and any(not str(filters.get(field) or "").strip() for field in require_all_filters):
            return False
        forbid_filters = {
            str(item or "").strip().lower()
            for item in list(selector.get("normalized_filters_absent") or [])
            if str(item or "").strip()
        }
        if forbid_filters and any(str(filters.get(field) or "").strip() for field in forbid_filters):
            return False
        expected_filter_values = dict(selector.get("normalized_filter_values") or {})
        for field_name, expected_values in expected_filter_values.items():
            current_value = str(filters.get(field_name) or "").strip().upper()
            allowed_values = {
                str(item or "").strip().upper()
                for item in list(expected_values or [])
                if str(item or "").strip()
            }
            if allowed_values and current_value not in allowed_values:
                return False
        stock_scopes = {
            str(item or "").strip().lower()
            for item in list(selector.get("stock_scopes") or [])
            if str(item or "").strip()
        }
        if stock_scopes and str(filters.get("stock_scope") or "").strip().lower() not in stock_scopes:
            return False
        group_by_any_of = {
            str(item or "").strip().lower()
            for item in list(selector.get("group_by_any_of") or [])
            if str(item or "").strip()
        }
        if group_by_any_of and not (group_by & group_by_any_of):
            return False
        group_by_all_of = {
            str(item or "").strip().lower()
            for item in list(selector.get("group_by_all_of") or [])
            if str(item or "").strip()
        }
        if group_by_all_of and not group_by_all_of.issubset(group_by):
            return False
        group_by_absent = {
            str(item or "").strip().lower()
            for item in list(selector.get("forbid_group_by_any_of") or [])
            if str(item or "").strip()
        }
        if group_by_absent and group_by_absent & group_by:
            return False
        business_concepts = {
            str(item or "").strip().lower()
            for item in list(selector.get("business_concepts") or [])
            if str(item or "").strip()
        }
        if business_concepts and str(inference.get("business_concept") or "").strip().lower() not in business_concepts:
            return False
        forbid_business_concepts = {
            str(item or "").strip().lower()
            for item in list(selector.get("forbid_business_concepts") or [])
            if str(item or "").strip()
        }
        if forbid_business_concepts and str(inference.get("business_concept") or "").strip().lower() in forbid_business_concepts:
            return False
        if bool(selector.get("requires_attachment")) and not bool(
            ((inference.get("attachment_summary") or {}).get("present"))
            or ((inference.get("runtime_attachment_summary") or {}).get("present"))
            or filters.get("attachment_present")
        ):
            return False
        declared_rules = {
            str(item or "").strip()
            for item in list(selector.get("declared_rules") or [])
            if str(item or "").strip()
        }
        if declared_rules and not declared_rules.issubset(available_rules):
            return False
        return True

    @staticmethod
    def _inventory_family_candidates(*, filters: dict[str, Any], inference: dict[str, Any]) -> set[str]:
        alias_map = {
            "materiales": {"material", "ferretero", "generic_inventory"},
            "material": {"material"},
            "ferretero": {"ferretero"},
            "serializados": {"serializados", "equipos", "cpe"},
            "equipos": {"serializados", "equipos", "cpe"},
            "cpe": {"serializados", "equipos", "cpe"},
        }
        candidates: set[str] = set()
        material_family = str(inference.get("material_family") or "").strip().lower()
        if material_family and material_family != "unknown":
            candidates.add(material_family)
            candidates.update(alias_map.get(material_family, set()))
        tipo_value = filters.get("tipo")
        if isinstance(tipo_value, list):
            normalized = {str(item or "").strip().lower() for item in tipo_value if str(item or "").strip()}
            if normalized == {"material", "ferretero"}:
                candidates.add("generic_inventory")
            candidates.update(normalized)
        else:
            tipo = str(tipo_value or "").strip().lower()
            if tipo:
                candidates.add(tipo)
        if str(filters.get("material_family") or "").strip():
            candidates.update({"serializados", "equipos", "cpe"})
        if not candidates:
            candidates.update({"generic_inventory", "material", "ferretero"})
        return candidates

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
            "association_query": "inventory_serial_association_departures",
            "serial_holder_query": "inventory_serial_by_operational_holder",
            "reconciliation_query": "inventory_reconciliation_pending_validation",
            "external_reconciliation_query": "inventory_external_reconciliation_pending",
            "document_generation": "inventory_document_generation_pending",
            "report_generation": "inventory_semantic_report",
            "alert_query": "inventory_alert_semantic_report",
            "notification_query": "inventory_notification_pending",
            "assignment_distribution_query": "inventory_assignment_distribution_pending",
            "movement_query": "inventory_entries_by_month" if "mes" in set(group_by) else "",
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
