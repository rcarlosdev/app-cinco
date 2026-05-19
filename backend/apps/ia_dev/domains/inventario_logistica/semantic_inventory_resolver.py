from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Any

from apps.ia_dev.application.contracts.query_intelligence_contracts import (
    BusinessQuerySemanticPlan,
    ResolvedQuerySpec,
    StructuredQueryIntent,
)
from apps.ia_dev.application.semantic.semantic_capability_registry import (
    SemanticBindingRequest,
    SemanticCapabilityRegistry,
)

from .business_query_semantic_plan import (
    INVENTORY_SEMANTIC_MATRIX,
    InventoryBusinessQueryPlanner,
)
from .matcher_semantico_gobernado_inventario import MatcherSemanticoGobernadoInventario
from .yaml_agent_loader import (
    get_business_concepts,
    get_business_rules,
    get_groupable_dimensions,
    load_inventory_agent_yaml,
)


MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}


class InventorySemanticResolver:
    RUNTIME_DOMAIN_CODE = "inventario_logistica"
    MATERIAL_CODE_STOPWORDS = {
        "bodega",
        "claro",
        "cuadrilla",
        "de",
        "del",
        "empleado",
        "ferretero",
        "ferretero",
        "inventario",
        "material",
        "materiales",
        "movil",
        "saldo",
        "tecnico",
    }

    def __init__(self, *, yaml_path: str | None = None):
        self.config = load_inventory_agent_yaml(yaml_path)
        self.groupable_dimensions = get_groupable_dimensions(self.config)
        self.business_concepts = get_business_concepts(self.config)
        self.business_rules = get_business_rules(self.config)
        self.semantic_plan_builder = InventoryBusinessQueryPlanner()
        self.matcher_gobernado = MatcherSemanticoGobernadoInventario()
        self.semantic_capability_registry = SemanticCapabilityRegistry()

    @staticmethod
    def _normalize(text: str) -> str:
        lowered = str(text or "").strip().lower()
        lowered = "".join(char for char in unicodedata.normalize("NFKD", lowered) if not unicodedata.combining(char))
        lowered = lowered.replace("Ã¡", "a").replace("Ã©", "e").replace("Ã­", "i").replace("Ã³", "o").replace("Ãº", "u")
        lowered = lowered.replace("Ã±", "n")
        return re.sub(r"\s+", " ", lowered)

    @staticmethod
    def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
        return any(token in text for token in tokens)

    @staticmethod
    def _is_numeric_identifier(value: str) -> bool:
        return bool(re.fullmatch(r"\d{5,15}", str(value or "").strip()))

    def _extract_month(self, message: str) -> str:
        normalized = self._normalize(message)
        for month_name, month_number in MONTHS.items():
            if re.search(rf"\b{re.escape(month_name)}\b", normalized):
                return str(month_number)
        if "este mes" in normalized or "mes actual" in normalized:
            return str(date.today().month)
        return ""

    def _extract_serial(self, message: str) -> str:
        match = re.search(r"\bserial(?:es)?\s+([A-Za-z0-9_-]{3,})\b", str(message or ""), re.IGNORECASE)
        if match:
            value = str(match.group(1) or "").strip()
            if value.lower() in {"perdido", "perdidos", "garantia", "garantias"}:
                return ""
            return value
        normalized = self._normalize(message)
        if not self._contains_any(normalized, ("trazabilidad", "historial", "serial", "imei", "mac")):
            return ""
        match = re.search(r"\b([A-Z]{2,}\d{2,}[A-Z0-9_-]*)\b", str(message or ""))
        return str(match.group(1) or "").strip() if match else ""

    def _extract_operational_identifier(self, message: str) -> str:
        match = re.search(
            r"\b(?:movil|m[oó]vil|cuadrilla|brigada|asignacion|asignaci[oó]n)\s+(?:de\s+)?([A-Za-z0-9_-]{3,})\b",
            str(message or ""),
            re.IGNORECASE,
        )
        if not match:
            return ""
        value = str(match.group(1) or "").strip().upper()
        if self._is_numeric_identifier(value):
            return ""
        return value if re.search(r"[A-Z]", value) and re.search(r"\d", value) else ""

    def _extract_code(self, message: str) -> str:
        match = re.search(r"\bc(?:o|ó)d(?:igo)?\s+([A-Za-z0-9_-]{2,})\b", str(message or ""), re.IGNORECASE)
        if match:
            return str(match.group(1) or "").strip()
        match = re.search(r"\bmaterial\s+([A-Za-z0-9_-]{2,})\b", str(message or ""), re.IGNORECASE)
        if not match:
            return ""
        candidate = str(match.group(1) or "").strip()
        if self._normalize(candidate) in self.MATERIAL_CODE_STOPWORDS:
            return ""
        return candidate

    def _resolve_inventory_type_filter(self, normalized: str) -> Any:
        if "material de claro" in normalized or "material claro" in normalized:
            return "material"
        if any(token in normalized for token in ("material ferretero", "ferretero", "ferreteria")):
            return "ferretero"
        if re.search(r"\bmaterial(?:es)?\b", normalized):
            return ["material", "ferretero"]
        return ""

    def _extract_cedula(self, message: str) -> str:
        normalized = self._normalize(message)
        match = re.search(r"\bc\S*dula\s+([0-9]{5,15})\b", normalized)
        if not match:
            match = re.search(r"\bcedula\s+([0-9]{5,15})\b", normalized)
        if not match:
            match = re.search(r"\b(?:empleado|tecnico|movil|mobile)\s+([0-9]{5,15})\b", normalized)
        if not match and any(token in normalized for token in ("kardex", "historial", "movimientos", "entradas", "salidas")):
            match = re.search(r"\bpara\s+([0-9]{5,15})\b", normalized)
        return str(match.group(1) or "").strip() if match else ""

    def _extract_project(self, message: str) -> str:
        normalized = self._normalize(message)
        if "proyecto eri" in normalized or re.search(r"\beri\b", normalized):
            return "ERI"
        match = re.search(r"\bproyecto\s+([a-z0-9_-]{2,})\b", normalized)
        return str(match.group(1) or "").upper() if match else ""

    def _extract_warehouse(self, message: str) -> str:
        normalized = self._normalize(message)
        if re.search(r"\boperacion[_\s-]?hfc\b", normalized):
            return "operacion_hfc"
        match = re.search(
            r"\b(?:bodega|almacen)\s+(?!destino\b|origen\b|por\b|de\b|del\b|la\b|el\b)([a-z0-9_-]{2,})\b",
            normalized,
        )
        return str(match.group(1) or "").strip() if match else ""

    def _resolve_material_family(self, normalized: str) -> str:
        if any(token in normalized for token in ("serial", "imei", "mac", "placa", "equipo")):
            return "serializados"
        if any(token in normalized for token in ("ferretero", "ferreteria", "compania")):
            return "ferreteros"
        if any(token in normalized for token in ("material", "bodega", "codigo", "stock", "saldo")):
            return "materiales"
        return "unknown"

    def _resolve_group_by(self, normalized: str) -> list[str]:
        matched: list[str] = []
        if "bodega destino" in normalized:
            return ["bodega_destino"]
        if "por proyecto" in normalized:
            matched.append("proyecto")
        if "por area" in normalized or "a las areas" in normalized:
            matched.append("area")
        if "por tecnico" in normalized or "por empleado" in normalized or "por cedula" in normalized:
            matched.append("cedula")
        if "por proveedor" in normalized:
            matched.append("proveedor")
        if "por compra" in normalized:
            matched.append("compra")
        if "por factura" in normalized or "facturacion por" in normalized:
            matched.append("factura")
        if "por documento" in normalized:
            matched.append("documento")
        if "por origen" in normalized:
            matched.append("origen")
        if "por destino" in normalized:
            matched.append("destino")
        if "por tipo de movimiento" in normalized or "por movimiento" in normalized:
            matched.append("tipo_movimiento")
        if "por mes" in normalized or re.search(r"\bmes\b", normalized):
            matched.append("mes")
        if "por estado" in normalized or re.search(r"\bestado\b", normalized):
            matched.append("estado")
        if "por bodega" in normalized:
            matched.append("bodega")
        if "por responsable" in normalized or "por custodio" in normalized:
            matched.append("cedula")
        if "por movil" in normalized or "por cuadrilla" in normalized or "por brigada" in normalized:
            matched.append("movil")
            if any(token in normalized for token in ("cedula", "empleado", "tecnico", "nombre")):
                matched.append("cedula")
        if "materiales mas consumidos" in normalized or "mas consumidos" in normalized:
            matched.append("material")
        return list(dict.fromkeys(matched))

    def infer_for_arbitration(self, *, message: str, dictionary_context: dict[str, Any] | None = None) -> dict[str, Any]:
        coincidencia_gobernada = self.matcher_gobernado.resolver(
            mensaje=message,
            contexto_semantico=dictionary_context or {},
        )
        if coincidencia_gobernada.get("coincidencia_gobernada"):
            filtros = dict(coincidencia_gobernada.get("filtros") or {})
            familias = list(coincidencia_gobernada.get("familias") or [])
            material_family = "serializados" if familias == ["serializados"] else "materiales"
            business_concept = ""
            if coincidencia_gobernada.get("intencion") == "movement_history":
                business_concept = "kardex_operativo_por_empleado" if filtros.get("cedula") else "kardex_consolidado"
            elif coincidencia_gobernada.get("capacidad_candidata") == "inventory_document_generation_pending":
                business_concept = "documentacion_no_habilitada"
            elif coincidencia_gobernada.get("capacidad_candidata") == "inventory_serial_stock_by_family_grouped_dimension":
                business_concept = "stock_serializado_por_dimension"
            elif coincidencia_gobernada.get("capacidad_candidata") == "inventory_provider_serial_validation":
                business_concept = "validacion_seriales_externos_contra_inventario_propio"
            else:
                business_concept = "stock_movil"
            candidate_fields = ["cedula", "movil", "codigo", "tipo"]
            candidate_tables = [
                "logistica_movimientos_entrega",
                "logistica_movimientos_devolucion",
                "logistica_movimientos_consumo",
                "logistica_movimientos_cobro",
            ]
            if coincidencia_gobernada.get("intencion") == "movement_history":
                candidate_fields = ["fecha", "tipo_movimiento", "codigo", "cedula", "movil", "cantidad", "saldo_movimiento"]
            elif coincidencia_gobernada.get("capacidad_candidata") == "inventory_serial_stock_by_family_grouped_dimension":
                candidate_fields = [
                    "familia",
                    "codigo",
                    "descripcion",
                    "movil",
                    "cedula",
                    "bodega",
                    "en_movil",
                    "en_base",
                    "cobros",
                    "saldo",
                    "seriales_total",
                ]
                candidate_tables = [
                    "logistica_base_seriales",
                    "base_codigo_seriales",
                    "cinco_base_de_personal",
                ]
            elif coincidencia_gobernada.get("capacidad_candidata") == "inventory_provider_serial_validation":
                candidate_fields = [
                    "serial",
                    "estado",
                    "cedula",
                    "movil",
                    "bodega",
                    "codigo",
                    "descripcion",
                    "fecha",
                ]
                candidate_tables = [
                    "logistica_base_seriales",
                    "logistica_seriales_asociados",
                    "cinco_base_de_personal",
                ]
            return {
                "domain": self.RUNTIME_DOMAIN_CODE,
                "candidate_domain": self.RUNTIME_DOMAIN_CODE,
                "intent": str(coincidencia_gobernada.get("intencion") or ""),
                "material_family": material_family,
                "business_concept": business_concept,
                "operation": str(coincidencia_gobernada.get("operation") or "detail"),
                "filters": filtros,
                "group_by": [str(item or "") for item in list(coincidencia_gobernada.get("group_by") or []) if str(item or "").strip()],
                "candidate_tables": candidate_tables,
                "candidate_fields": candidate_fields,
                "requires_db_validation": True,
                "should_use_sql_assisted": coincidencia_gobernada.get("capacidad_candidata") != "inventory_provider_serial_validation" and not bool(coincidencia_gobernada.get("limitaciones")),
                "requires_business_validation": False,
                "requires_external_source": bool(coincidencia_gobernada.get("limitaciones")),
                "requires_threshold_metadata": False,
                "missing_metadata": [],
                "implementation_status": (
                    "ready_for_handler_execution"
                    if coincidencia_gobernada.get("capacidad_candidata") == "inventory_provider_serial_validation"
                    else ("external_source_pending" if coincidencia_gobernada.get("limitaciones") else "ready_for_dictionary_validation")
                ),
                "expected_runtime_flow": (
                    "handler"
                    if coincidencia_gobernada.get("capacidad_candidata") == "inventory_provider_serial_validation"
                    else ("external_source_pending" if coincidencia_gobernada.get("limitaciones") else "sql_assisted")
                ),
                "confidence": 0.94 if not coincidencia_gobernada.get("requiere_aclaracion") else 0.58,
                "explanation": "Consulta interpretada con matcher semantico gobernado de inventario apoyado en dd_sinonimos y dd_reglas.",
                "limitations": list(coincidencia_gobernada.get("limitaciones") or []),
                "governed_match": coincidencia_gobernada,
            }

        normalized = self._normalize(message)
        material_family = self._resolve_material_family(normalized)
        group_by = self._resolve_group_by(normalized)
        serial = self._extract_serial(message)
        codigo = self._extract_code(message)
        cedula = self._extract_cedula(message)
        operational_identifier = self._extract_operational_identifier(message)
        project = self._extract_project(message)
        warehouse = self._extract_warehouse(message)
        month = self._extract_month(message)
        inventory_type_filter = self._resolve_inventory_type_filter(normalized)
        filters: dict[str, Any] = {}
        if serial:
            filters["serial"] = serial
        if codigo:
            filters["codigo"] = codigo
        if project:
            filters["proyecto"] = project
        if warehouse:
            filters["bodega"] = warehouse
        if month:
            filters["month"] = month
        if cedula:
            filters["cedula"] = cedula
        if operational_identifier:
            filters["movil"] = operational_identifier
        if inventory_type_filter:
            filters["tipo"] = inventory_type_filter

        intent = "movement_query"
        operation = "list"
        business_concept = ""
        candidate_tables: list[str] = []
        candidate_fields: list[str] = []
        limitations: list[str] = []
        requires_business_validation = False
        requires_external_source = False
        requires_threshold_metadata = False
        missing_metadata: list[str] = []
        implementation_status = "ready_for_dictionary_validation"
        expected_runtime_flow = "sql_assisted"

        if self._contains_any(normalized, ("spa", "documento soporte")) or "acta" in normalized:
            intent = "document_generation"
            operation = "generate_document"
            requires_external_source = True
            implementation_status = "pending"
            expected_runtime_flow = "document_generation_pending"
            candidate_fields = ["documento", "codigo", "serial", "fecha", "bodega_origen", "bodega_destino"]
            business_concept = "documento_spa" if "spa" in normalized else "acta_logistica"
            if "traslado" in normalized:
                candidate_tables = ["logistica_movimientos_traslado"]
                filters["tipo_acta"] = "traslado"
            elif "ingreso" in normalized or "entrada" in normalized:
                candidate_tables = ["logistica_movimientos_entrada"]
                filters["tipo_acta"] = "ingreso"
            else:
                candidate_tables = ["logistica_movimientos_entrada", "logistica_movimientos_traslado", "logistica_movimientos_entrega"]
            limitations.append("document_generation_pending")
        elif "sap" in normalized and self._contains_any(normalized, ("kardex", "consumo", "saldos")):
            intent = "external_reconciliation_query"
            operation = "reconcile"
            business_concept = "conciliacion_sap_kardex"
            requires_external_source = True
            implementation_status = "external_source_pending"
            expected_runtime_flow = "external_source_pending"
            candidate_tables = ["logistica_movimientos_consumo"]
            candidate_fields = ["codigo", "cantidad", "fecha"]
            limitations.append("external_source_pending:sap")
            missing_metadata.append("saldo_sap")
        elif self._contains_any(normalized, ("comparativo ingreso", "conciliacion de ingresos", "saldo total por codigo")) or (
            "stock bodega" in normalized and "facturacion" in normalized
        ):
            intent = "reconciliation_query"
            operation = "reconcile"
            business_concept = "conciliacion_logistica"
            implementation_status = "semantic_limitation_only"
            expected_runtime_flow = "semantic_report"
            candidate_tables = [
                "logistica_movimientos_entrada",
                "logistica_movimientos_entrega",
                "logistica_movimientos_consumo",
                "logistica_movimientos_cobro",
                "logistica_movimientos_traslado",
            ]
            candidate_fields = ["codigo", "cantidad", "bodega", "movil", "fecha"]
            limitations.append("semantic_limitation:formula_no_aplica_por_regla_de_negocio")
        elif self._contains_any(normalized, ("entrega consumo tecnico facturacion", "material entregado no consumido", "diferencias entre entrega y facturacion")):
            intent = "reconciliation_query"
            operation = "reconcile"
            business_concept = "entrega_consumo_facturacion"
            requires_external_source = True
            implementation_status = "pending_integration_or_db_validation"
            expected_runtime_flow = "external_source_pending"
            candidate_tables = ["logistica_movimientos_entrega", "logistica_movimientos_consumo", "logistica_movimientos_cobro"]
            candidate_fields = ["codigo", "cantidad", "entregado_a", "tecnico", "factura", "fecha"]
            limitations.append("facturacion_pending_integration_or_db_validation")
        elif (
            self._contains_any(normalized, ("consumo tecnico", "consumos tecnicos", "consumo vs facturacion", "consumos vs facturacion"))
            and "facturacion" in normalized
        ):
            intent = "reconciliation_query"
            operation = "reconcile"
            business_concept = "consumo_vs_facturacion"
            candidate_tables = ["logistica_movimientos_consumo", "a_promedios_consumo", "facturacion_facturado_wfm"]
            candidate_fields = ["codigo", "cantidad", "orden_trabajo", "tipo", "f_consumo", "bodega"]
            if self._contains_any(normalized, ("operacion_hfc", "operacion hfc", "hfc")):
                filters["bodega"] = "operacion_hfc"
                implementation_status = "ready_for_dictionary_validation"
                expected_runtime_flow = "sql_assisted"
            else:
                requires_external_source = True
                implementation_status = "pending_scope_filter"
                expected_runtime_flow = "external_source_pending"
                limitations.append("scope_required:operacion_hfc")
        elif self._contains_any(normalized, ("compra", "compras")) and self._contains_any(normalized, ("logistica", "notificacion", "llegada", "recibidas")):
            intent = "notification_query"
            operation = "trace"
            business_concept = "ingreso_compras_logistica"
            requires_external_source = True
            implementation_status = "pending_integration"
            expected_runtime_flow = "external_source_pending"
            candidate_tables = ["logistica_movimientos_entrada"]
            candidate_fields = ["codigo", "cantidad", "proveedor", "compra", "fecha", "documento"]
            limitations.append("integration_pending:compras_logistica")
        elif self._contains_any(normalized, ("promedios", "cpe")) and "eri" in normalized:
            intent = "report_generation"
            operation = "semantic_report"
            business_concept = "promedios_cpe_eri"
            implementation_status = "pending_db_validation"
            expected_runtime_flow = "semantic_report"
            candidate_tables = ["logistica_movimientos_consumo", "logistica_movimientos_entrega"]
            candidate_fields = ["codigo", "cantidad", "proyecto", "fecha"]
            missing_metadata.append("cpe")
            limitations.append("missing_metadata:cpe")
            if "proyecto" not in group_by:
                group_by.append("proyecto")
        elif self._contains_any(normalized, ("distribucion", "asignacion", "asignado a tecnico", "asignado a movil", "asignado a proyecto")):
            intent = "assignment_distribution_query"
            operation = "semantic_report"
            business_concept = "distribucion_asignacion"
            implementation_status = "pending_db_validation"
            expected_runtime_flow = "semantic_report"
            candidate_tables = ["logistica_seriales_asociados", "logistica_movimientos_entrega", "logistica_movimientos_consumo"]
            candidate_fields = ["asociado_a", "entregado_a", "tecnico", "movil", "proyecto"]
            limitations.append("implementation_status:pending_db_validation")
            if "por tecnico" in normalized and "tecnico" not in group_by:
                group_by.append("tecnico")
        elif self._contains_any(normalized, ("reporte de saldos", "saldo de materiales para el area", "reporte a areas")):
            intent = "report_generation"
            operation = "semantic_report"
            business_concept = "reporte_saldos_area"
            implementation_status = "pending_db_validation"
            expected_runtime_flow = "semantic_report"
            candidate_tables = ["logistica_movimientos_entrega", "logistica_movimientos_consumo"]
            candidate_fields = ["codigo", "cantidad", "area", "responsable", "tecnico"]
            limitations.append("missing_metadata:area_responsable")
            if "area" not in group_by:
                group_by.append("area")
        elif self._contains_any(normalized, ("alerta ferretero", "stock bajo", "compra requerida", "alerta a compras", "alertar a directores")):
            intent = "alert_query"
            operation = "semantic_report"
            material_family = "ferreteros"
            business_concept = "alerta_ferretero_compras"
            requires_threshold_metadata = True
            implementation_status = "pending_threshold_validation"
            expected_runtime_flow = "semantic_report"
            candidate_tables = ["base_codigos", "logistica_movimientos_consumo", "logistica_movimientos_entrada"]
            candidate_fields = ["codigo", "descripcion", "cantidad"]
            limitations.append("threshold_metadata_pending")
        elif self._contains_any(normalized, ("consolidado de kardex y log", "log consolidado", "linea de tiempo")):
            intent = "movement_history"
            operation = "trace"
            business_concept = "log_consolidado"
            candidate_tables = [
                "logistica_movimientos_entrada",
                "logistica_movimientos_entrega",
                "logistica_movimientos_devolucion",
                "logistica_movimientos_consumo",
                "logistica_movimientos_cobro",
                "logistica_movimientos_traslado",
                "logistica_seriales_asociados",
            ]
            candidate_fields = ["codigo", "serial", "cantidad", "fecha", "tipo_movimiento", "documento"]
        elif (
            self._contains_any(normalized, ("kardex", "movimientos", "entradas y salidas"))
            and cedula
            and any(token in normalized for token in ("tecnico", "empleado", "cedula"))
        ):
            intent = "movement_history"
            operation = "detail"
            business_concept = "kardex_operativo_por_empleado"
            candidate_tables = [
                "logistica_movimientos_entrega",
                "logistica_movimientos_devolucion",
                "logistica_movimientos_consumo",
                "logistica_movimientos_cobro",
                "base_codigos",
                "cinco_base_de_personal",
            ]
            candidate_fields = [
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
            ]
            limitations.append("serializados_employee_kardex_not_available")
        elif self._contains_any(normalized, ("kardex", "movimientos")) and codigo:
            intent = "movement_history"
            operation = "trace"
            business_concept = "kardex_consolidado"
            candidate_tables = [
                "logistica_movimientos_entrada",
                "logistica_movimientos_entrega",
                "logistica_movimientos_devolucion",
                "logistica_movimientos_consumo",
                "logistica_movimientos_cobro",
                "logistica_movimientos_traslado",
            ]
            candidate_fields = ["codigo", "cantidad", "fecha", "tipo_movimiento", "origen", "destino"]
        elif "historial completo" in normalized or ("historial" in normalized and codigo):
            intent = "movement_history"
            operation = "trace"
            business_concept = "historial_movimientos_completo"
            candidate_tables = [
                "logistica_movimientos_entrada",
                "logistica_movimientos_entrega",
                "logistica_movimientos_devolucion",
                "logistica_movimientos_consumo",
                "logistica_movimientos_cobro",
                "logistica_movimientos_traslado",
            ]
            candidate_fields = ["codigo", "cantidad", "fecha", "bodega", "documento"]
        elif "sin validar" in normalized and "consumo movil" in normalized:
            intent = "risk_detection"
            operation = "list"
            material_family = "serializados"
            business_concept = "consumo_movil_sin_validar"
            filters.update({"movimiento": "consumo_movil", "validado": False})
            candidate_tables = ["logistica_base_seriales"]
            candidate_fields = ["serial", "codigo", "estado", "ubicacion", "fecha"]
        elif (("historial" in normalized and serial) or "trazabilidad" in normalized or serial) and not operational_identifier:
            intent = "traceability_query"
            operation = "trace"
            material_family = "serializados"
            business_concept = "historial_movimientos_completo" if "historial" in normalized else "trazabilidad_serial"
            candidate_tables = ["logistica_base_seriales", "logistica_seriales_asociados"]
            candidate_fields = ["serial", "codigo", "estado", "ubicacion", "fecha"]
        elif "inventario" in normalized and operational_identifier and any(
            token in normalized for token in ("cuadrilla", "brigada", "movil", "móvil", "asignacion", "asignación")
        ):
            intent = "stock_balance"
            operation = "stock_balance"
            business_concept = "stock_movil"
            filters["stock_scope"] = "movil"
            candidate_tables = [
                "logistica_movimientos_entrega",
                "logistica_movimientos_consumo",
                "logistica_movimientos_cobro",
                "logistica_movimientos_devolucion",
            ]
            candidate_fields = ["codigo", "cantidad", "f_consumo", "movil", "cedula", "estado"]
        elif "traslado" in normalized:
            intent = "transfer_query"
            operation = "aggregate" if group_by else "list"
            candidate_tables = ["logistica_movimientos_traslado"]
            candidate_fields = ["codigo", "cantidad", "f_consumo", "bodega", "movimiento", "estado", "comentario"]
            if "otro aliado" in normalized or "otro_aliado" in normalized:
                filters["movimiento"] = "TRASLADOS_OTRO_ALIADO"
                business_concept = "traslado_otro_aliado"
            elif "bodega" in normalized:
                filters["movimiento"] = "TRASLADO_BODEGA"
                business_concept = "traslado_bodega_doble_registro"
            if "bodega_destino" in group_by:
                limitations.append("missing_physical_column:bodega_destino")
        elif "asociad" in normalized and "bodega" in normalized:
            intent = "association_query"
            operation = "list"
            material_family = "serializados"
            business_concept = "salidas_de_bodega_serializados"
            candidate_tables = ["logistica_seriales_asociados"]
            candidate_fields = ["serial", "codigo", "fecha_asociacion", "bodega_salida", "estado_asociacion"]
        elif "inventario" in normalized and cedula and any(token in normalized for token in ("cuadrilla", "brigada", "movil", "empleado", "tecnico")):
            intent = "stock_balance"
            operation = "stock_balance"
            business_concept = "stock_movil"
            filters["stock_scope"] = "movil"
            candidate_tables = [
                "logistica_movimientos_entrega",
                "logistica_movimientos_consumo",
                "logistica_movimientos_cobro",
                "logistica_movimientos_devolucion",
            ]
            candidate_fields = ["codigo", "cantidad", "f_consumo", "movil", "cedula", "estado"]
        elif any(token in normalized for token in ("material", "materiales")) and (cedula or operational_identifier) and any(
            token in normalized for token in ("empleado", "tecnico", "cuadrilla", "brigada", "movil", "móvil")
        ):
            intent = "stock_balance"
            operation = "stock_balance"
            business_concept = "stock_movil"
            filters["stock_scope"] = "movil"
            candidate_tables = [
                "logistica_movimientos_entrega",
                "logistica_movimientos_consumo",
                "logistica_movimientos_cobro",
                "logistica_movimientos_devolucion",
            ]
            candidate_fields = ["codigo", "cantidad", "f_consumo", "movil", "cedula", "estado"]
        elif "materiales criticos" in normalized and any(
            token in normalized for token in ("empleado", "tecnico", "cedula", "movil", "móvil")
        ):
            intent = "stock_balance"
            operation = "aggregate"
            material_family = "materiales"
            business_concept = "materiales_criticos_por_empleado"
            filters["stock_scope"] = "movil"
            candidate_tables = [
                "logistica_movimientos_entrega",
                "logistica_movimientos_consumo",
                "logistica_movimientos_cobro",
                "logistica_movimientos_devolucion",
                "base_codigos",
                "cinco_base_de_personal",
            ]
            candidate_fields = ["codigo", "cantidad", "f_consumo", "cedula", "bodega", "descripcion", "tipo", "movil"]
        elif str(material_family or "") == "serializados" and (cedula or operational_identifier) and any(
            token in normalized for token in ("equipo", "equipos", "serial", "serializados", "cargados", "asociados")
        ):
            intent = "serial_holder_query"
            operation = "list"
            business_concept = "seriales_por_operador"
            candidate_tables = ["logistica_base_seriales", "base_codigo_seriales"]
            candidate_fields = ["serial", "codigo", "estado", "ubicacion", "movil", "cedula", "fecha"]
        elif "consum" in normalized:
            intent = "consumption_query"
            operation = "top" if ("mas" in normalized or "top" in normalized) else "aggregate"
            business_concept = "materiales_mas_consumidos" if operation == "top" else ""
            candidate_tables = ["logistica_movimientos_consumo", "base_codigos"]
            candidate_fields = ["codigo", "cantidad", "fecha", "cedula", "movil"]
        elif any(token in normalized for token in ("stock", "saldo", "existencia", "existencias")) or (
            "cuanto tengo" in normalized and warehouse
        ):
            intent = "stock_balance"
            operation = "stock_balance"
            business_concept = "stock_actual"
            candidate_tables = [
                "logistica_movimientos_entrada",
                "logistica_movimientos_entrega",
                "logistica_movimientos_devolucion",
                "logistica_movimientos_consumo",
                "logistica_movimientos_cobro",
                "logistica_movimientos_traslado",
            ]
            candidate_fields = ["codigo", "cantidad", "f_consumo", "bodega", "movimiento", "estado"]
            implementation_status = "ready_for_dictionary_validation"
            if cedula and any(token in normalized for token in ("empleado", "tecnico", "cedula")):
                business_concept = "stock_movil"
                filters["stock_scope"] = "movil"
            if (
                "movil" in normalized
                or "móvil" in normalized
                or any(token in normalized for token in ("cuadrilla", "brigada", "empleado", "tecnico"))
                or "datos del empleado" in normalized
                or any(token in group_by for token in ("tecnico", "cedula", "movil"))
            ):
                business_concept = "stock_movil"
                filters["stock_scope"] = "movil"
            elif "bodega" in normalized:
                business_concept = "stock_bodega"
                filters["stock_scope"] = "bodega"
                if "bodega" not in group_by:
                    group_by.append("bodega")
        elif "entrada" in normalized or "ingreso" in normalized:
            intent = "movement_query"
            operation = "aggregate" if group_by else "list"
            candidate_tables = ["logistica_movimientos_entrada"]
            candidate_fields = ["codigo", "cantidad", "fecha", "bodega", "responsable"]
        elif "devolucion" in normalized:
            intent = "return_query"
            operation = "aggregate" if group_by else "list"
            candidate_tables = ["logistica_movimientos_devolucion"]
            candidate_fields = ["codigo", "cantidad", "fecha", "devuelto_por"]
        elif "equipos por estado" in normalized:
            intent = "stock_query"
            operation = "aggregate"
            material_family = "serializados"
            group_by = ["estado"]
            candidate_tables = ["logistica_base_seriales"]
            candidate_fields = ["estado", "serial"]

        if cedula and intent in {"stock_query", "stock_balance"} and not business_concept:
            business_concept = "stock_movil"
        if (
            intent == "stock_balance"
            and business_concept == "stock_movil"
            and str(material_family or "") == "materiales"
            and any(token in normalized for token in ("empleado", "tecnico", "cuadrilla", "brigada", "movil", "mÃ³vil", "cedula"))
            and "codigo" not in group_by
        ):
            group_by.append("codigo")

        confidence = 0.61
        if candidate_tables:
            confidence += 0.14
        if serial or codigo or month or group_by or project:
            confidence += 0.12
        if business_concept:
            confidence += 0.08
        confidence = min(confidence, 0.96)

        explanation = (
            f"Consulta interpretada en {self.RUNTIME_DOMAIN_CODE} con intent {intent}"
            f" y familia {material_family} usando el blueprint YAML como contexto semantico."
        )
        return {
            "domain": self.RUNTIME_DOMAIN_CODE,
            "candidate_domain": self.RUNTIME_DOMAIN_CODE,
            "intent": intent,
            "material_family": material_family,
            "business_concept": business_concept,
            "operation": operation,
            "filters": filters,
            "group_by": group_by,
            "candidate_tables": candidate_tables,
            "candidate_fields": candidate_fields,
            "requires_db_validation": True,
            "should_use_sql_assisted": expected_runtime_flow == "sql_assisted",
            "requires_business_validation": requires_business_validation,
            "requires_external_source": requires_external_source,
            "requires_threshold_metadata": requires_threshold_metadata,
            "missing_metadata": missing_metadata,
            "implementation_status": implementation_status,
            "expected_runtime_flow": expected_runtime_flow,
            "confidence": round(confidence, 4),
            "explanation": explanation,
            "limitations": limitations,
        }

    def resolve_query(
        self,
        *,
        message: str,
        intent: StructuredQueryIntent,
        semantic_context: dict[str, Any],
    ) -> ResolvedQuerySpec:
        inference = self.infer_for_arbitration(message=message, dictionary_context=semantic_context)
        inferred_filters = dict(inference.get("filters") or {})
        inferred_group_by = list(inference.get("group_by") or [])
        normalized_filters = {**dict(intent.filters or {}), **inferred_filters}
        warnings = list(intent.warnings or [])
        if isinstance(inference.get("governed_match"), dict) and bool((inference.get("governed_match") or {}).get("requiere_aclaracion")):
            pregunta_aclaracion = str((inference.get("governed_match") or {}).get("pregunta_aclaracion") or "").strip()
            if pregunta_aclaracion:
                warnings.append(pregunta_aclaracion)
        limitations = list(inference.get("limitations") or [])
        explicit_template_id = str(intent.template_id or "").strip()
        binding_decision = self.semantic_capability_registry.resolve(
            SemanticBindingRequest(
                domain=self.RUNTIME_DOMAIN_CODE,
                message=message,
                intent=str(inference.get("intent") or intent.operation or ""),
                normalized_filters=normalized_filters,
                group_by=inferred_group_by,
                semantic_context=dict(semantic_context or {}),
                source_hints={
                    "template_id": explicit_template_id,
                    "inventory_inference": dict(inference or {}),
                    "governed_match": dict(inference.get("governed_match") or {}),
                },
            )
        ).as_dict()
        resolved_template_id = str(binding_decision.get("template_id") or explicit_template_id or "inventory_movement_detail")
        memory_seed_status = self.semantic_plan_builder.memory_service.ensure_confirmed_rules()
        semantic_plan: BusinessQuerySemanticPlan = self.semantic_plan_builder.build_plan(
            message=message,
            inference=inference,
            template_id=resolved_template_id,
            semantic_context=semantic_context,
            binding_decision=binding_decision,
        )
        normalized_filters = dict(binding_decision.get("normalized_filters") or normalized_filters)
        resolved_intent = StructuredQueryIntent(
            raw_query=intent.raw_query,
            domain_code=self.RUNTIME_DOMAIN_CODE,
            operation=str(inference.get("operation") or intent.operation or "list"),
            template_id=resolved_template_id,
            entity_type=str(semantic_plan.main_entity.type or ""),
            entity_value=str(semantic_plan.main_entity.identifier or ""),
            filters=normalized_filters,
            period=dict(intent.period or {}),
            group_by=inferred_group_by,
            metrics=list(intent.metrics or []),
            confidence=float(inference.get("confidence") or intent.confidence or 0.0),
            source="inventory_yaml_semantic_resolver",
            warnings=warnings,
        )

        if str(resolved_intent.template_id or "") == "inventory_stock_balance_pending_validation":
            warnings.append("inventario_stock_pendiente_validacion_db_ai_dictionary")
        semantic_context = dict(semantic_context or {})
        semantic_context["inventory_semantic_inference"] = dict(inference)
        if isinstance(inference.get("governed_match"), dict):
            semantic_context["inventory_governed_match"] = dict(inference.get("governed_match") or {})
        semantic_context["inventory_semantic_matrix"] = list(INVENTORY_SEMANTIC_MATRIX)
        semantic_context["business_query_semantic_plan"] = semantic_plan.as_dict()
        semantic_context["inventory_semantic_plan"] = semantic_plan.as_dict()
        semantic_context["semantic_memory_seed"] = dict(memory_seed_status or {})
        semantic_context["semantic_capability_registry"] = dict(binding_decision or {})
        semantic_context.setdefault("resolved_semantic", {})
        semantic_context["resolved_semantic"]["inventory"] = dict(inference)
        semantic_context["resolved_semantic"]["business_query_semantic_plan"] = semantic_plan.as_dict()
        semantic_context["resolved_semantic"]["semantic_capability_registry"] = dict(binding_decision or {})
        semantic_context["resolved_semantic"]["limitations"] = list(
            dict.fromkeys([*limitations, *list(semantic_plan.known_limitations or [])])
        )
        semantic_context["resolved_semantic"]["rules_applied"] = list(semantic_plan.applicable_business_rules or [])
        semantic_context["resolved_semantic"]["candidate_capability"] = str(
            binding_decision.get("candidate_capability") or semantic_plan.candidate_capability or ""
        )
        semantic_context["resolved_semantic"]["consulted_sources"] = list(
            dict.fromkeys(
                [
                    *list(semantic_plan.consulted_sources or []),
                    *list(binding_decision.get("consulted_metadata") or []),
                ]
            )
        )
        semantic_context["resolved_semantic"]["memory_keys_used"] = list(semantic_plan.memory_keys_used or [])
        semantic_context["resolved_semantic"]["final_filters"] = dict(binding_decision.get("normalized_filters") or semantic_plan.normalized_filters or {})
        semantic_context["resolved_semantic"]["runtime_flow_hint"] = str(
            inference.get("expected_runtime_flow")
            or ("business_validation_required" if str(resolved_intent.template_id or "").strip() == "inventory_stock_balance_pending_validation" else "sql_assisted")
        )
        semantic_context["resolved_semantic"]["binding_template_id"] = str(binding_decision.get("template_id") or "")
        semantic_context["resolved_semantic"]["binding_tool_id"] = str(binding_decision.get("tool_id") or "")
        semantic_context["resolved_semantic"]["planner_route_hint"] = str(binding_decision.get("planner_route_hint") or "")
        semantic_context["resolved_semantic"]["response_profile"] = str(binding_decision.get("response_profile") or "")
        semantic_context["resolved_semantic"]["binding_trace"] = {
            "source": str(binding_decision.get("source") or ""),
            "matched_rules": list(binding_decision.get("matched_rules") or []),
            "confidence": float(binding_decision.get("confidence") or 0.0),
            "fallback_used": bool(binding_decision.get("fallback_used")),
            "unresolved_reason": str(binding_decision.get("unresolved_reason") or ""),
            "legacy_mapping_used": bool(binding_decision.get("legacy_mapping_used")),
            "reason": str(binding_decision.get("legacy_reason") or ""),
            "migration_target": str(binding_decision.get("migration_target") or ""),
            "regla_metadata_usada": list(binding_decision.get("regla_metadata_usada") or []),
            "fuente_dd": list(binding_decision.get("fuente_dd") or []),
            "fallback_sombreado_usado": bool(binding_decision.get("fallback_sombreado_usado")),
            "regla_legacy_detectada": bool(binding_decision.get("regla_legacy_detectada")),
            "regla_migrada": bool(binding_decision.get("regla_migrada")),
            "paquete_capacidad_usado": str(binding_decision.get("paquete_capacidad_usado") or ""),
            "version_paquete": str(binding_decision.get("version_paquete") or ""),
            "capacidades_declaradas": list(binding_decision.get("capacidades_declaradas") or []),
            "reglas_declaradas": list(binding_decision.get("reglas_declaradas") or []),
            "perfiles_respuesta": list(binding_decision.get("perfiles_respuesta") or []),
            "evaluaciones_asociadas": list(binding_decision.get("evaluaciones_asociadas") or []),
        }
        semantic_context["material_family"] = str(inference.get("material_family") or "")
        semantic_context["business_concept"] = str(inference.get("business_concept") or "")

        normalized_period = dict(intent.period or {})
        month = str(normalized_filters.get("month") or "").strip()
        if month:
            normalized_period.setdefault("month", month)

        return ResolvedQuerySpec(
            intent=resolved_intent,
            semantic_context=semantic_context,
            normalized_filters=normalized_filters,
            normalized_period=normalized_period,
            mapped_columns={},
            warnings=warnings,
        )
