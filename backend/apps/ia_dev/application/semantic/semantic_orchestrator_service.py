from __future__ import annotations

import json
import os
import re
import unicodedata
from typing import Any, Callable

from apps.ia_dev.application.context.run_context import RunContext
from apps.ia_dev.application.contracts.agent_contract_loader import AgentContractLoader
from apps.ia_dev.application.semantic.semantic_capability_registry import (
    INVENTORY_INTENT_IDS_BY_TEMPLATE,
    SemanticBindingRequest,
    SemanticCapabilityRegistry,
)
from apps.ia_dev.domains.inventario_logistica.matcher_semantico_gobernado_inventario import (
    MatcherSemanticoGobernadoInventario,
)
from apps.ia_dev.application.runtime.tool_registry_service import ToolRegistryService
from apps.ia_dev.infrastructure.ai.openai_gateway_contracts import OpenAIGatewayRequest
from apps.ia_dev.infrastructure.ai.openai_gateway_service import OpenAIGatewayService


class SemanticOrchestratorService:
    MIN_CONFIDENCE = 0.65
    ROUTE_BY_STRATEGY = {
        "sql_assisted": "sql_assisted",
        "handler": "handler",
        "semantic_only": "semantic_only",
        "external_pending": "external_pending",
    }
    TECHNICAL_RISK_FLAGS = {
        "invalid_domain",
        "invalid_intent",
        "invalid_capability",
        "unsupported_filter",
        "table_not_governed",
        "join_not_allowed",
        "low_confidence",
        "missing_required_filter",
        "external_source_pending",
        "real_ambiguity_detected",
    }
    INVENTORY_EMPLOYEE_STOCK_RE = re.compile(
        r"\bsaldo(?:\s+de)?(?:\s+materiales?)?\s+(?:del?\s+)?(?:emplead\w*|tecnico)\s+([0-9]{5,15})\b"
    )
    INVENTORY_DOMAIN_SIGNAL_RE = re.compile(
        r"\b("
        r"inventario|logistica|material(?:es)?|ferretero(?:s)?|serial(?:es)?|equipo(?:s)?|"
        r"stock|saldo(?:s)?|existencia(?:s)?|bodega(?:s)?|almacen|almacenes|"
        r"kardex|traslado(?:s)?|entrada(?:s)?|salida(?:s)?|devolucion(?:es)?|consumo(?:s)?|"
        r"operacion_hfc|operacion\s+hfc|hfc"
        r")\b"
    )

    def __init__(
        self,
        *,
        contract_loader: AgentContractLoader | None = None,
        llm_resolver: Callable[..., dict[str, Any]] | None = None,
        gateway: OpenAIGatewayService | None = None,
        tool_registry_service: ToolRegistryService | None = None,
    ) -> None:
        self.contract_loader = contract_loader or AgentContractLoader()
        self._llm_resolver = llm_resolver
        self.gateway = gateway or OpenAIGatewayService()
        self.tool_registry_service = tool_registry_service or ToolRegistryService()
        self.matcher_gobernado_inventario = MatcherSemanticoGobernadoInventario()
        self.semantic_capability_registry = SemanticCapabilityRegistry(
            tool_registry_service=self.tool_registry_service
        )

    def orchestrate(
        self,
        *,
        user_message: str,
        candidate_domain: str | None,
        candidate_agent: str | None,
        agent_contract: dict[str, Any] | None,
        ai_dictionary_summary: dict[str, Any] | None,
        domain_semantic_summary: dict[str, Any] | None,
        memory_context: dict[str, Any] | None,
        route_debug_hints: dict[str, Any] | None,
        run_context: RunContext | None = None,
        observability=None,
    ) -> dict[str, Any]:
        initial_contract = dict(agent_contract or {})
        dictionary_summary = dict(ai_dictionary_summary or {})
        semantic_summary = dict(domain_semantic_summary or {})
        memory_payload = dict(memory_context or {})
        debug_hints = dict(route_debug_hints or {})
        deterministic = self._deterministic_output(
            user_message=user_message,
            candidate_domain=candidate_domain,
            candidate_agent=candidate_agent,
            contract_payload=initial_contract,
            ai_dictionary_summary=dictionary_summary,
            domain_semantic_summary=semantic_summary,
            memory_context=memory_payload,
            route_debug_hints=debug_hints,
        )
        resolved_contract = self._resolve_contract(
            candidate_domain=str(deterministic.get("domain") or candidate_domain or ""),
            candidate_agent=str(deterministic.get("agent_id") or candidate_agent or ""),
            contract_payload=initial_contract,
        )

        llm_payload: dict[str, Any] | None = None
        if self._llm_enabled() and self._openai_api_key():
            try:
                llm_payload = self._invoke_llm(
                    user_message=user_message,
                    candidate_domain=candidate_domain,
                    candidate_agent=candidate_agent,
                    contract_payload=resolved_contract,
                    ai_dictionary_summary=dictionary_summary,
                    domain_semantic_summary=semantic_summary,
                    memory_context=memory_payload,
                    route_debug_hints=debug_hints,
                    deterministic_output=deterministic,
                    run_context=run_context,
                    observability=observability,
                )
            except Exception:
                llm_payload = None

        selected = llm_payload if isinstance(llm_payload, dict) and llm_payload else deterministic
        validated = self._validate_output(
            output=selected,
            fallback=deterministic,
            user_message=user_message,
            contract_payload=resolved_contract,
            ai_dictionary_summary=dictionary_summary,
            domain_semantic_summary=semantic_summary,
            route_debug_hints=debug_hints,
        )
        validated["source"] = "llm_validated" if llm_payload else "deterministic"
        return validated

    def _deterministic_output(
        self,
        *,
        user_message: str,
        candidate_domain: str | None,
        candidate_agent: str | None,
        contract_payload: dict[str, Any],
        ai_dictionary_summary: dict[str, Any],
        domain_semantic_summary: dict[str, Any],
        memory_context: dict[str, Any],
        route_debug_hints: dict[str, Any],
    ) -> dict[str, Any]:
        del memory_context
        normalized = self._normalize(user_message)
        match_gobernado = self.matcher_gobernado_inventario.resolver(mensaje=user_message, contexto_semantico={})
        domain = self._resolve_domain(
            normalized=normalized,
            candidate_domain=candidate_domain,
            candidate_agent=candidate_agent,
            contract_payload=contract_payload,
        )
        if match_gobernado.get("coincidencia_gobernada") and str(match_gobernado.get("dominio_candidato") or "") == "inventario_logistica":
            domain = "inventario_logistica"
        contract = self._resolve_contract(
            candidate_domain=domain,
            candidate_agent=candidate_agent,
            contract_payload=contract_payload,
        )
        agent_id = str(contract.get("agent_id") or candidate_agent or "").strip()

        filters = self._extract_filters(normalized=normalized, raw_message=user_message)
        entities = self._extract_entities(normalized=normalized, raw_message=user_message)
        if match_gobernado.get("coincidencia_gobernada"):
            filters.update({key: value for key, value in dict(match_gobernado.get("filtros") or {}).items() if value not in (None, "")})
            entities.update({key: value for key, value in dict(match_gobernado.get("entidades") or {}).items() if value not in (None, "")})
        dimensions = self._extract_dimensions(normalized=normalized)
        metrics = self._extract_metrics(normalized=normalized)
        scope = self._resolve_scope(normalized=normalized, filters=filters, entities=entities)
        intent_id, capability_id, confidence = self._resolve_intent_and_capability(
            normalized=normalized,
            domain=domain,
            contract_payload=contract,
            filters=filters,
            entities=entities,
            dimensions=dimensions,
        )
        if match_gobernado.get("coincidencia_gobernada") and domain == "inventario_logistica":
            intent_id = self._mapear_intencion_inventario(match_gobernado=match_gobernado, intent_id_actual=intent_id)
            capability_id = str(match_gobernado.get("capacidad_candidata") or capability_id or "")
            confidence = 0.94 if not match_gobernado.get("requiere_aclaracion") else 0.58

        required_tables = self._intent_tables(contract_payload=contract, intent_id=intent_id)
        required_joins = self._resolve_required_joins(
            required_tables=required_tables,
            ai_dictionary_summary=ai_dictionary_summary,
        )
        business_rules = self._business_rules_for_intent(
            contract_payload=contract,
            intent_id=intent_id,
            domain_semantic_summary=domain_semantic_summary,
        )
        risk_flags: list[str] = []
        needs_clarification = False
        clarification_question: str | None = None

        if self._is_real_ambiguity(normalized=normalized):
            risk_flags.append("real_ambiguity_detected")
            needs_clarification = True
            clarification_question = (
                "¿Necesitas información del empleado, saldo de inventario o ausencias para ese identificador?"
            )
            confidence = min(confidence, 0.50)

        strategy = self._intent_strategy(contract_payload=contract, intent_id=intent_id)
        recommended_route = self.ROUTE_BY_STRATEGY.get(strategy, "needs_clarification")
        if self._looks_external_pending(normalized=normalized, domain=domain):
            recommended_route = "external_pending"
            risk_flags.append("external_source_pending")

        required_filters = self._intent_required_filters(contract_payload=contract, intent_id=intent_id)
        missing_required_filters = [
            item
            for item in required_filters
            if not str(filters.get(item) or entities.get(item) or "").strip()
        ]
        if missing_required_filters:
            risk_flags.append("missing_required_filter")
            needs_clarification = True
            clarification_question = self._missing_filter_question(
                domain=domain,
                capability_id=capability_id,
                missing_filters=missing_required_filters,
            )
        if bool(match_gobernado.get("requiere_aclaracion")):
            risk_flags.append("real_ambiguity_detected")
            needs_clarification = True
            clarification_question = str(match_gobernado.get("pregunta_aclaracion") or "").strip() or clarification_question

        if confidence < self.MIN_CONFIDENCE:
            risk_flags.append("low_confidence")
            needs_clarification = True
            clarification_question = clarification_question or (
                "Necesito una precisión corta para asegurar el dominio, el filtro principal y la ruta correcta."
            )

        if needs_clarification:
            recommended_route = "needs_clarification"

        reasoning_summary = self._build_reasoning_summary(
            domain=domain,
            intent_id=intent_id,
            capability_id=capability_id,
            filters=filters,
            route=recommended_route,
            candidate_domain=candidate_domain,
            route_debug_hints=route_debug_hints,
        )
        return {
            "domain": domain,
            "agent_id": agent_id,
            "intent": intent_id,
            "capability": capability_id,
            "confidence": round(confidence, 4),
            "scope": scope,
            "filters": filters,
            "entities": entities,
            "dimensions": dimensions,
            "metrics": metrics,
            "required_tables": required_tables,
            "required_joins": required_joins,
            "business_rules": business_rules,
            "risk_flags": risk_flags,
            "needs_clarification": needs_clarification,
            "clarification_question": clarification_question,
            "recommended_route": recommended_route,
            "reasoning_summary": reasoning_summary,
            "user_response_strategy": self._build_user_response_strategy(
                domain=domain,
                recommended_route=recommended_route,
                risk_flags=risk_flags,
                needs_clarification=needs_clarification,
            ),
        }

    @staticmethod
    def _mapear_intencion_inventario(*, match_gobernado: dict[str, Any], intent_id_actual: str) -> str:
        intencion = str(match_gobernado.get("intencion") or "").strip().lower()
        capacidad = str(match_gobernado.get("capacidad_candidata") or "").strip().lower()
        if capacidad == "inventory_stock_balance_by_mobile" or intencion == "stock_balance":
            return "inventory_stock_by_mobile"
        if capacidad == "inventory_kardex_by_employee":
            return "inventory_kardex"
        if capacidad == "inventory_kardex_consolidated":
            return "inventory_kardex"
        if capacidad == "inventory_serial_by_operational_holder":
            return "inventory_serial_by_holder"
        if capacidad == "inventory_document_generation_pending":
            return "inventory_document_generation"
        return str(intent_id_actual or "")

    def _validate_output(
        self,
        *,
        output: dict[str, Any],
        fallback: dict[str, Any],
        user_message: str,
        contract_payload: dict[str, Any],
        ai_dictionary_summary: dict[str, Any],
        domain_semantic_summary: dict[str, Any],
        route_debug_hints: dict[str, Any],
    ) -> dict[str, Any]:
        del user_message, domain_semantic_summary
        validated = self._base_output()
        validated.update({key: value for key, value in dict(fallback or {}).items() if key in validated})
        validated.update({key: value for key, value in dict(output or {}).items() if key in validated})

        risk_flags = {
            str(item).strip()
            for item in list(validated.get("risk_flags") or [])
            if str(item).strip()
        }
        contract = self._resolve_contract(
            candidate_domain=validated.get("domain"),
            candidate_agent=validated.get("agent_id"),
            contract_payload=contract_payload,
        )
        validated["domain"] = str(contract.get("domain") or validated.get("domain") or "").strip().lower()
        validated["agent_id"] = str(contract.get("agent_id") or validated.get("agent_id") or "").strip()

        valid_intents = {
            str(item.get("id") or "").strip(): dict(item)
            for item in list(contract.get("intents") or [])
            if isinstance(item, dict) and str(item.get("id") or "").strip()
        }
        valid_capabilities = {
            str(item.get("id") or "").strip(): dict(item)
            for item in list(contract.get("capabilities") or [])
            if isinstance(item, dict) and str(item.get("id") or "").strip()
        }
        if str(validated.get("intent") or "").strip() not in valid_intents:
            validated["intent"] = str(fallback.get("intent") or "").strip()
            risk_flags.add("invalid_intent")
        if str(validated.get("capability") or "").strip() not in valid_capabilities:
            validated["capability"] = str(fallback.get("capability") or "").strip()
            risk_flags.add("invalid_capability")

        intent_payload = dict(valid_intents.get(str(validated.get("intent") or "").strip()) or {})
        capability_payload = dict(valid_capabilities.get(str(validated.get("capability") or "").strip()) or {})
        if str(intent_payload.get("capability") or "").strip() and str(intent_payload.get("capability") or "").strip() != str(validated.get("capability") or "").strip():
            validated["capability"] = str(intent_payload.get("capability") or "").strip()

        supported_filter_keys = set(self._allowed_filter_keys(contract_payload=contract, intent_payload=intent_payload))
        validated_filters: dict[str, Any] = {}
        for key, value in dict(validated.get("filters") or {}).items():
            clean_key = str(key or "").strip()
            if not clean_key:
                continue
            if clean_key in supported_filter_keys:
                validated_filters[clean_key] = value
            else:
                risk_flags.add("unsupported_filter")
        validated["filters"] = validated_filters

        required_tables = []
        allowed_table_names = {
            str(item).strip().lower()
            for item in list(ai_dictionary_summary.get("table_names") or [])
            if str(item).strip()
        }
        for table_name in list(validated.get("required_tables") or []):
            clean_table = str(table_name or "").strip()
            if clean_table.lower() in allowed_table_names:
                required_tables.append(clean_table)
            else:
                risk_flags.add("table_not_governed")
        if not required_tables and list(intent_payload.get("tables") or []):
            required_tables = [
                str(item)
                for item in list(intent_payload.get("tables") or [])
                if str(item).strip().lower() in allowed_table_names
            ]
        validated["required_tables"] = required_tables

        allowed_joins = {
            str(item.get("join_sql") or "").strip()
            for item in list(ai_dictionary_summary.get("joins") or [])
            if isinstance(item, dict) and str(item.get("join_sql") or "").strip()
        }
        required_joins = []
        for join_sql in list(validated.get("required_joins") or []):
            clean_join = str(join_sql or "").strip()
            if clean_join in allowed_joins:
                required_joins.append(clean_join)
            else:
                risk_flags.add("join_not_allowed")
        validated["required_joins"] = required_joins

        required_filters = self._intent_required_filters(contract_payload=contract, intent_id=validated["intent"])
        missing_required_filters = [
            item
            for item in required_filters
            if not str(validated_filters.get(item) or dict(validated.get("entities") or {}).get(item) or "").strip()
        ]
        if missing_required_filters:
            risk_flags.add("missing_required_filter")
            validated["needs_clarification"] = True
            validated["clarification_question"] = self._missing_filter_question(
                domain=validated["domain"],
                capability_id=validated["capability"],
                missing_filters=missing_required_filters,
            )

        recommended_route = str(validated.get("recommended_route") or "").strip().lower()
        allowed_route = self.ROUTE_BY_STRATEGY.get(str(intent_payload.get("strategy") or capability_payload.get("type") or "").strip().lower())
        if recommended_route == "external_pending":
            risk_flags.add("external_source_pending")
        elif allowed_route:
            validated["recommended_route"] = allowed_route
        else:
            validated["recommended_route"] = "needs_clarification"

        confidence = float(validated.get("confidence") or 0.0)
        if confidence < self.MIN_CONFIDENCE:
            risk_flags.add("low_confidence")
            validated["needs_clarification"] = True
            validated["recommended_route"] = "needs_clarification"
            validated["clarification_question"] = str(validated.get("clarification_question") or "").strip() or (
                "Necesito una aclaración breve para continuar con seguridad."
            )

        pre_router_confident = bool((route_debug_hints.get("pre_router") or {}).get("high_confidence"))
        pre_router_domain = str((route_debug_hints.get("pre_router") or {}).get("domain") or "").strip().lower()
        if pre_router_confident and pre_router_domain and pre_router_domain != str(validated["domain"] or "").strip().lower():
            risk_flags.add("pre_router_conflict")
            validated["reasoning_summary"] = (
                f"Se mantuvo el dominio {pre_router_domain} por pre-router determinístico de alta confianza; "
                f"el enriquecimiento semántico quedó en shadow para evitar cambiar la ruta sin validación fuerte."
            )

        validated["risk_flags"] = sorted(risk_flags)
        validated["business_rules"] = [
            str(item or "").strip()
            for item in list(validated.get("business_rules") or [])
            if str(item or "").strip()
        ][:8]
        validated["dimensions"] = [
            str(item or "").strip()
            for item in list(validated.get("dimensions") or [])
            if str(item or "").strip()
        ][:8]
        validated["metrics"] = [
            str(item or "").strip()
            for item in list(validated.get("metrics") or [])
            if str(item or "").strip()
        ][:6]
        return validated

    def _resolve_domain(
        self,
        *,
        normalized: str,
        candidate_domain: str | None,
        candidate_agent: str | None,
        contract_payload: dict[str, Any],
    ) -> str:
        if self._is_inventory_operational_cross_query(normalized):
            return "inventario_logistica"
        if re.search(r"\bausenc(?:ia|ias)|ausent(?:e|es|ismo)\b", normalized) and "empleado" in normalized:
            return "ausentismo"
        if re.search(r"\b(informacion|información|info|datos|ficha)\b", normalized) and "empleado" in normalized:
            return "empleados"
        if re.search(r"\b(inventario|material|serial|stock|saldo|kardex|bodega|garantia|garantía|sin stock|sin rotacion|sin rotación)\b", normalized):
            return "inventario_logistica"
        if re.search(r"\b(ausentismo|incapacidad|vacaciones|ausencias?)\b", normalized):
            return "ausentismo"
        if re.search(r"\b(empleado|empleados|cedula|cédula|movil|m[oó]vil|cargo|supervisor)\b", normalized):
            return "empleados"
        if re.search(r"\b(transporte|vehiculo|vehículo|vehiculos|vehículos|salidas)\b", normalized):
            return "transporte"
        if re.search(r"\b(propuesta|sinonimo|sinónimo|regla|aprobar|rechazar)\b", normalized):
            return "knowledge"
        contract_domain = str(contract_payload.get("domain") or "").strip().lower()
        if contract_domain:
            return contract_domain
        if str(candidate_domain or "").strip():
            return str(candidate_domain or "").strip().lower()
        if candidate_agent:
            record = self.contract_loader.get(str(candidate_agent))
            if record is not None:
                return str(record.domain or "").strip().lower()
        return "general"

    def _resolve_intent_and_capability(
        self,
        *,
        normalized: str,
        domain: str,
        contract_payload: dict[str, Any],
        filters: dict[str, Any],
        entities: dict[str, Any],
        dimensions: list[str] | None = None,
    ) -> tuple[str, str, float]:
        filters = dict(filters or {})
        dimensions = [str(item or "").strip().lower() for item in list(dimensions or []) if str(item or "").strip()]
        if not str(filters.get("grouping_dimension") or "").strip():
            for candidate in ("movil", "cedula", "bodega"):
                if candidate in dimensions:
                    filters["grouping_dimension"] = candidate
                    break
        confidence = 0.72
        if domain == "inventario_logistica":
            entity_payload = {}
            for field, entity_type in (("cedula", "empleado"), ("movil", "movil"), ("codigo", "codigo"), ("serial", "serial")):
                value = str((entities or {}).get(field) or filters.get(field) or "").strip()
                if value:
                    entity_payload = {"type": entity_type, "identifier": value, "field": field}
                    break
            intent_hint = ""
            if any(token in normalized for token in ("acta", "spa", "sap")):
                intent_hint = "document_generation"
            elif any(token in normalized for token in ("equipo", "equipos", "serial", "serializados")) and any(
                token in normalized for token in ("cargados", "asociados", "movil", "cuadrilla", "brigada", "cedula", "tecnico")
            ):
                intent_hint = "serial_holder_query"
            elif any(token in normalized for token in ("kardex", "movimientos", "entradas y salidas")):
                intent_hint = "movement_history"
            elif "facturacion" in normalized or "facturaciÃ³n" in normalized:
                intent_hint = "reconciliation_query"
            elif "stock" in normalized or "saldo" in normalized or "inventario" in normalized or "sin stock" in normalized:
                intent_hint = "stock_balance"
            binding = self.semantic_capability_registry.resolve(
                SemanticBindingRequest(
                    domain=domain,
                    message=normalized,
                    intent=intent_hint,
                    entity=entity_payload or None,
                    normalized_filters=filters,
                    group_by=dimensions,
                    source_hints={
                        "governed_match": dict(
                            self.matcher_gobernado_inventario.resolver(
                                mensaje=normalized,
                                contexto_semantico={},
                            )
                            or {}
                        ),
                    },
                )
            )
            capability_id = str(binding.candidate_capability or "").strip()
            if capability_id:
                intent_id = str(
                    INVENTORY_INTENT_IDS_BY_TEMPLATE.get(str(binding.template_id or "").strip().lower())
                    or self._inventory_intent_from_capability(capability_id)
                    or "inventory_stock_by_mobile"
                )
                return intent_id, capability_id, max(float(binding.confidence or 0.0), 0.72)
            if any(token in normalized for token in ("equipo", "equipos", "serial", "serializados")) and any(
                token in normalized for token in ("cargados", "asociados", "movil", "cuadrilla", "brigada", "cedula", "tecnico")
            ):
                return "inventory_serial_by_holder", "inventory_serial_by_operational_holder", 0.92
            if self._is_inventory_operational_cross_query(normalized):
                return "inventory_stock_by_mobile", "inventory_stock_balance_by_mobile", 0.92
            if "kardex" in normalized:
                return "inventory_kardex", "inventory_kardex_consolidated", 0.93
            if "facturacion" in normalized or "facturación" in normalized:
                return "inventory_consumption_billing", "inventory_consumption_billing_operacion_hfc", 0.82
            if "stock" in normalized or "saldo" in normalized or "sin stock" in normalized:
                if any(key in entities for key in ("cedula", "movil")) or "cuadrilla" in normalized or "tecnico" in normalized or "técnico" in normalized:
                    return "inventory_stock_by_mobile", "inventory_stock_balance_by_mobile", 0.85
                return "inventory_stock_by_warehouse", "inventory_stock_balance_by_warehouse", 0.90
            if any(token in normalized for token in ("garantia", "garantía", "seriales perdidos", "sin rotacion", "sin rotación", "materiales criticos", "materiales críticos")):
                return "inventory_semantic_report", "inventory_semantic_report", 0.76
            if any(token in normalized for token in ("acta", "spa", "sap")):
                return "inventory_document_generation", "inventory_document_generation_pending", 0.78
        if domain == "empleados":
            if any(token in normalized for token in ("informacion", "información", "info", "ficha", "datos")) or entities:
                return "employee_detail", "empleados.detail.v1", 0.92
            return "employee_count", "empleados.count.active.v1", 0.78
        if domain == "ausentismo":
            if any(token in normalized for token in ("reincid",)):
                return "attendance_recurrence", "attendance.recurrence.grouped.v1", 0.85
            if any(token in normalized for token in ("historico", "histórico", "tendencia")):
                return "attendance_trend", "attendance.trend.daily.v1", 0.82
            if any(token in normalized for token in ("detalle", "ausencias empleado", "ausencias del empleado", "personal")) or entities:
                return "attendance_detail", "attendance.unjustified.table_with_personal.v1", 0.90
            return "attendance_summary", "attendance.unjustified.summary.v1", 0.80
        if domain == "transporte":
            return "transport_departures_summary", "transport.departures.summary.v1", 0.86
        if domain == "knowledge":
            if "aprueba" in normalized or "aprobar" in normalized:
                return "knowledge_approve", "knowledge.proposal.approve.v1", 0.88
            if "rechaza" in normalized or "rechazar" in normalized:
                return "knowledge_reject", "knowledge.proposal.reject.v1", 0.88
            return "knowledge_change_request", "knowledge.proposal.create.v1", 0.86
        intents = list(contract_payload.get("intents") or [])
        capabilities = list(contract_payload.get("capabilities") or [])
        intent_id = str((intents[0] or {}).get("id") or "") if intents else ""
        capability_id = str((capabilities[0] or {}).get("id") or "") if capabilities else ""
        return intent_id, capability_id, confidence

    @staticmethod
    def _inventory_intent_from_capability(capability_id: str) -> str:
        capability = str(capability_id or "").strip().lower()
        if capability in {"inventory_stock_balance_by_mobile", "inventory_stock_balance_by_warehouse", "inventory_stock_balance"}:
            return "inventory_stock_by_mobile"
        if capability == "inventory_stock_balance_by_material_dimension":
            return "inventory_stock_by_dimension"
        if capability in {"inventory_kardex_by_employee", "inventory_kardex_consolidated"}:
            return "inventory_kardex"
        if capability == "inventory_serial_by_operational_holder":
            return "inventory_serial_by_holder"
        if capability == "inventory_document_generation_pending":
            return "inventory_document_generation"
        return ""

    @staticmethod
    def _extract_filters(*, normalized: str, raw_message: str) -> dict[str, Any]:
        filters: dict[str, Any] = {}
        guarded_cedula = SemanticOrchestratorService._match_inventory_employee_stock_query(normalized)
        if guarded_cedula:
            filters["cedula"] = guarded_cedula
            filters["stock_scope"] = "movil"
        if re.search(r"\boperacion[_\s-]?hfc\b", normalized):
            filters["bodega"] = "operacion_hfc"
        explicit_code_match = re.search(r"\bc(?:o|ó)d(?:igo)?\s+([a-z0-9_-]+)\b", raw_message, re.IGNORECASE)
        if explicit_code_match:
            filters["codigo"] = str(explicit_code_match.group(1) or "").strip().upper()
        code_match = re.search(r"\bkardex\s+del?\s+c[oó]digo\s+([a-z0-9_-]+)\b", normalized)
        if code_match:
            filters["codigo"] = str(code_match.group(1) or "").strip().upper()
        serial_match = re.search(r"\bserial(?:es)?\s+([a-z0-9_-]{3,})\b", normalized)
        if serial_match:
            filters["serial"] = str(serial_match.group(1) or "").strip().upper()
        ot_match = re.search(r"\bot\s+([a-z0-9_-]{2,})\b", normalized)
        if ot_match:
            filters["orden_trabajo"] = str(ot_match.group(1) or "").strip().upper()
        numeric_id = re.search(r"\b([0-9]{5,15})\b", raw_message)
        if numeric_id and "codigo" not in filters:
            filters.setdefault("cedula", str(numeric_id.group(1) or "").strip())
        return filters

    @staticmethod
    def _extract_entities(*, normalized: str, raw_message: str) -> dict[str, Any]:
        entities: dict[str, Any] = {}
        guarded_cedula = SemanticOrchestratorService._match_inventory_employee_stock_query(normalized)
        explicit_code_match = re.search(r"\bc(?:o|ó)d(?:igo)?\s+([a-z0-9_-]+)\b", raw_message, re.IGNORECASE)
        numeric_id = re.search(r"\b([0-9]{5,15})\b", raw_message)
        if guarded_cedula:
            entities["cedula"] = guarded_cedula
        elif explicit_code_match:
            entities["codigo"] = str(explicit_code_match.group(1) or "").strip().upper()
        elif numeric_id:
            entities["cedula"] = str(numeric_id.group(1) or "").strip()
        movil_match = re.search(r"\b([A-Z]{2,}[A-Z0-9_-]*\d{2,})\b", raw_message)
        if movil_match and "cedula" not in entities:
            entities["movil"] = str(movil_match.group(1) or "").strip().upper()
        if "tecnico" in normalized or "técnico" in normalized:
            entities["persona_tipo"] = "tecnico"
        if "empleado" in normalized:
            entities["persona_tipo"] = "empleado"
        return entities

    @staticmethod
    def _extract_dimensions(*, normalized: str) -> list[str]:
        if SemanticOrchestratorService._match_inventory_employee_stock_query(normalized):
            return []
        dimensions: list[str] = []
        for token, dimension in (
            ("bodega", "bodega"),
            ("almacen", "bodega"),
            ("movil", "movil"),
            ("móvil", "movil"),
            ("cuadrilla", "movil"),
            ("brigada", "movil"),
            ("tecnico", "cedula"),
            ("técnico", "cedula"),
            ("empleado", "cedula"),
            ("cedula", "cedula"),
            ("cédula", "cedula"),
            ("area", "area"),
            ("cargo", "cargo"),
            ("supervisor", "supervisor"),
        ):
            if token in normalized:
                dimensions.append(dimension)
        return list(dict.fromkeys(dimensions))

    @staticmethod
    def _extract_metrics(*, normalized: str) -> list[str]:
        metrics: list[str] = []
        for token, metric in (
            ("cuanto", "cantidad"),
            ("cuánto", "cantidad"),
            ("stock", "cantidad"),
            ("saldo", "cantidad"),
            ("consumo", "cantidad"),
            ("facturacion", "cantidad"),
            ("facturación", "cantidad"),
        ):
            if token in normalized:
                metrics.append(metric)
        return list(dict.fromkeys(metrics))

    def _resolve_required_joins(
        self,
        *,
        required_tables: list[str],
        ai_dictionary_summary: dict[str, Any],
    ) -> list[str]:
        if len(required_tables) < 2:
            return []
        joins: list[str] = []
        required = {str(item).strip().lower() for item in list(required_tables or []) if str(item).strip()}
        for item in list(ai_dictionary_summary.get("joins") or []):
            if not isinstance(item, dict):
                continue
            from_table = str(item.get("from_table") or "").strip().lower()
            to_table = str(item.get("to_table") or "").strip().lower()
            join_sql = str(item.get("join_sql") or "").strip()
            if join_sql and from_table in required and to_table in required:
                joins.append(join_sql)
        return joins[:6]

    def _business_rules_for_intent(
        self,
        *,
        contract_payload: dict[str, Any],
        intent_id: str,
        domain_semantic_summary: dict[str, Any],
    ) -> list[str]:
        rules = [
            str(item)
            for item in list(self._intent_validation_rules(contract_payload=contract_payload, intent_id=intent_id))
            if str(item).strip()
        ]
        rules.extend(
            str(item)
            for item in list(domain_semantic_summary.get("business_rules") or [])
            if str(item).strip()
        )
        return list(dict.fromkeys(rules))[:8]

    def _build_user_response_strategy(
        self,
        *,
        domain: str,
        recommended_route: str,
        risk_flags: list[str],
        needs_clarification: bool,
    ) -> dict[str, Any]:
        next_best_action = "Entregar respuesta empresarial con resultado y alerta accionable."
        if recommended_route == "external_pending":
            next_best_action = "Explicar la limitación concreta y dejar lista la siguiente validación operativa."
        elif recommended_route == "semantic_only":
            next_best_action = "Entregar interpretación de negocio y sugerencia de reporte o validación."
        elif needs_clarification:
            next_best_action = "Pedir una sola aclaración específica antes de continuar."
        warnings = []
        if "external_source_pending" in risk_flags:
            warnings.append("La fuente externa aún no está habilitada como productiva.")
        if "missing_required_filter" in risk_flags:
            warnings.append("Falta un filtro requerido para responder con seguridad.")
        return {
            "tone": "business",
            "sections": [
                "Que entendi",
                "Datos usados",
                "Resultado",
                "Alertas",
                "Limitaciones",
                "Siguiente accion",
            ],
            "warnings_to_include": warnings,
            "next_best_action": next_best_action if domain else "Confirmar primero el dominio correcto.",
        }

    @staticmethod
    def _is_real_ambiguity(*, normalized: str) -> bool:
        return bool(
            ("informacion" in normalized or "información" in normalized or "info" in normalized)
            and "saldo" in normalized
            and "empleado" in normalized
        )

    @staticmethod
    def _looks_external_pending(*, normalized: str, domain: str) -> bool:
        if domain != "inventario_logistica":
            return False
        return any(token in normalized for token in ("sap", "spa", "acta", "compras"))

    def _invoke_llm(
        self,
        *,
        user_message: str,
        candidate_domain: str | None,
        candidate_agent: str | None,
        contract_payload: dict[str, Any],
        ai_dictionary_summary: dict[str, Any],
        domain_semantic_summary: dict[str, Any],
        memory_context: dict[str, Any],
        route_debug_hints: dict[str, Any],
        deterministic_output: dict[str, Any],
        run_context: RunContext | None,
        observability,
    ) -> dict[str, Any]:
        if self._llm_resolver is not None:
            return dict(
                self._llm_resolver(
                    user_message=user_message,
                    candidate_domain=candidate_domain,
                    candidate_agent=candidate_agent,
                    contract_payload=contract_payload,
                    ai_dictionary_summary=ai_dictionary_summary,
                    domain_semantic_summary=domain_semantic_summary,
                    memory_context=memory_context,
                    route_debug_hints=route_debug_hints,
                    deterministic_output=deterministic_output,
                    run_context=run_context,
                    observability=observability,
                )
                or {}
            )
        prompt = {
            "user_message": user_message,
            "candidate_domain": str(candidate_domain or ""),
            "candidate_agent": str(candidate_agent or ""),
            "agent_contract": {
                "agent_id": str(contract_payload.get("agent_id") or ""),
                "domain": str(contract_payload.get("domain") or ""),
                "intents": [dict(item) for item in list(contract_payload.get("intents") or [])[:12] if isinstance(item, dict)],
                "capabilities": [dict(item) for item in list(contract_payload.get("capabilities") or [])[:16] if isinstance(item, dict)],
            },
            "ai_dictionary_summary": ai_dictionary_summary,
            "domain_semantic_summary": domain_semantic_summary,
            "memory_context": memory_context,
            "route_debug_hints": route_debug_hints,
            "deterministic_baseline": deterministic_output,
        }
        request = OpenAIGatewayRequest(
            component="semantic_orchestrator_service",
            model_route="semantic_orchestrator",
            timeout_seconds=30,
            retries=1,
            trace_metadata={
                "flow": "semantic_orchestrator",
                "run_id": str((run_context.run_id if run_context else "") or ""),
                "trace_id": str((run_context.trace_id if run_context else "") or ""),
            },
            metadata={"candidate_domain": str(candidate_domain or "")},
            tools=self.tool_registry_service.list_openai_function_tools(
                tool_ids=[
                    ToolRegistryService.SEMANTIC_DICTIONARY_TOOL_ID,
                    ToolRegistryService.SEMANTIC_DOMAIN_TOOL_ID,
                    ToolRegistryService.SEMANTIC_MEMORY_TOOL_ID,
                    ToolRegistryService.SEMANTIC_BASELINE_TOOL_ID,
                    ToolRegistryService.SEMANTIC_ROUTE_HINTS_TOOL_ID,
                ],
            ),
            tool_choice="auto",
            input=[
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "Devuelve solo JSON valido. No generes SQL. "
                                "No inventes tablas, columnas, joins, execute, legacy ni cambios de base de datos. "
                                "Respeta agent_contract y ai_dictionary como autoridad estructural. "
                                "Si necesitas evidencia adicional, usa solo las tools disponibles."
                            ),
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": json.dumps(prompt, ensure_ascii=True)}],
                },
            ],
        )
        if self._native_tools_enabled():
            tool_loop = self.gateway.run_function_tool_loop(
                request=request,
                tool_executor=lambda function_call: self._execute_native_tool_call(
                    function_call=function_call,
                    ai_dictionary_summary=ai_dictionary_summary,
                    domain_semantic_summary=domain_semantic_summary,
                    memory_context=memory_context,
                    route_debug_hints=route_debug_hints,
                    deterministic_output=deterministic_output,
                    run_context=run_context,
                    observability=observability,
                ),
                on_tool_result=lambda trace: self._record_native_tool_trace(
                    trace=trace,
                    run_context=run_context,
                    observability=observability,
                ),
            )
            response = tool_loop.response
            if run_context is not None:
                run_context.metadata["response_native_tool_loop"] = {
                    "component": "semantic_orchestrator_service",
                    "response_ids": list(tool_loop.response_ids or []),
                    "turns": int(tool_loop.turns or 0),
                    "tool_trace_count": len(list(tool_loop.tool_traces or [])),
                }
        else:
            response = self.gateway.create(request)
        payload = json.loads(str(response.output_text or "{}"))
        return dict(payload or {})

    def _execute_native_tool_call(
        self,
        *,
        function_call: dict[str, Any],
        ai_dictionary_summary: dict[str, Any],
        domain_semantic_summary: dict[str, Any],
        memory_context: dict[str, Any],
        route_debug_hints: dict[str, Any],
        deterministic_output: dict[str, Any],
        run_context: RunContext | None,
        observability,
    ) -> dict[str, Any]:
        del observability
        tool_id = str(function_call.get("name") or "").strip()
        output: dict[str, Any]
        if tool_id == ToolRegistryService.SEMANTIC_DICTIONARY_TOOL_ID:
            output = dict(ai_dictionary_summary or {})
        elif tool_id == ToolRegistryService.SEMANTIC_DOMAIN_TOOL_ID:
            output = dict(domain_semantic_summary or {})
        elif tool_id == ToolRegistryService.SEMANTIC_MEMORY_TOOL_ID:
            output = dict(memory_context or {})
        elif tool_id == ToolRegistryService.SEMANTIC_BASELINE_TOOL_ID:
            output = dict(deterministic_output or {})
        elif tool_id == ToolRegistryService.SEMANTIC_ROUTE_HINTS_TOOL_ID:
            output = dict(route_debug_hints or {})
        else:
            return {
                "output": {"ok": False, "error": f"tool_not_supported:{tool_id}"},
                "execution_status": "blocked",
                "validation_status": "tool_not_supported",
                "evidence_metadata": {"tool_id": tool_id},
            }
        return {
            "output": output,
            "execution_status": "completed",
            "validation_status": "validated",
            "evidence_metadata": {
                "tool_id": tool_id,
                "run_id": str((run_context.run_id if run_context else "") or ""),
            },
        }

    def _record_native_tool_trace(
        self,
        *,
        trace: dict[str, Any],
        run_context: RunContext | None,
        observability,
    ) -> None:
        if run_context is not None:
            registry_trace = self.tool_registry_service.build_native_trace(
                run_id=run_context.run_id,
                trace_id=run_context.trace_id,
                started_at=str(trace.get("started_at") or run_context.started_at_iso),
                finished_at=str(trace.get("finished_at") or run_context.started_at_iso),
                tool_id=str(trace.get("tool_name") or ""),
                tool_call_id=str(trace.get("tool_call_id") or ""),
                arguments=dict(trace.get("arguments") or {}),
                duration_ms=int(trace.get("duration_ms") or 0),
                execution_status=str(trace.get("execution_status") or ""),
                validation_status=str(trace.get("validation_status") or ""),
                output_payload=dict(trace.get("output_payload") or {}),
                evidence_metadata=dict(trace.get("evidence_metadata") or {}),
                model_response_id=str(trace.get("model_response_id") or ""),
                loop_iteration=int(trace.get("loop_iteration") or 0),
            )
            native_traces = list(run_context.metadata.get("response_native_tool_trace") or [])
            native_traces.append(registry_trace)
            run_context.metadata["response_native_tool_trace"] = native_traces
        if observability is not None and hasattr(observability, "record_event"):
            observability.record_event(
                event_type="response_native_tool_executed",
                source="SemanticOrchestratorService",
                duration_ms=int(trace.get("duration_ms") or 0),
                meta={
                    "tool_call_id": str(trace.get("tool_call_id") or ""),
                    "tool_name": str(trace.get("tool_name") or ""),
                    "execution_status": str(trace.get("execution_status") or ""),
                    "validation_status": str(trace.get("validation_status") or ""),
                    "model_response_id": str(trace.get("model_response_id") or ""),
                    "loop_iteration": int(trace.get("loop_iteration") or 0),
                },
            )

    def _resolve_contract(
        self,
        *,
        candidate_domain: str | None,
        candidate_agent: str | None,
        contract_payload: dict[str, Any],
    ) -> dict[str, Any]:
        payload = dict(contract_payload or {})
        if payload.get("agent_id") and payload.get("domain"):
            return payload
        if candidate_domain:
            record = self.contract_loader.get_by_domain(str(candidate_domain))
            if record is not None:
                return dict(record.payload or {})
        if candidate_agent:
            record = self.contract_loader.get(str(candidate_agent))
            if record is not None:
                return dict(record.payload or {})
        return payload

    @staticmethod
    def _normalize(text: str) -> str:
        lowered = str(text or "").strip().lower()
        lowered = "".join(
            char for char in unicodedata.normalize("NFKD", lowered) if not unicodedata.combining(char)
        )
        return re.sub(r"\s+", " ", lowered)

    @classmethod
    def _match_inventory_employee_stock_query(cls, normalized: str) -> str:
        match = cls.INVENTORY_EMPLOYEE_STOCK_RE.search(str(normalized or ""))
        if not match:
            return ""
        return "".join(ch for ch in str(match.group(1) or "") if ch.isdigit())

    @classmethod
    def _is_inventory_operational_cross_query(cls, normalized: str) -> bool:
        text = str(normalized or "")
        if cls._match_inventory_employee_stock_query(text):
            return True
        has_inventory_signal = bool(cls.INVENTORY_DOMAIN_SIGNAL_RE.search(text))
        has_operational_holder = bool(
            re.search(r"\b(movil|cuadrilla|brigada|cedula|tecnico|emplead\w*|responsable)\b", text)
            or re.search(r"\b[0-9]{5,15}\b", text)
            or "datos del empleado" in text
        )
        return has_inventory_signal and has_operational_holder

    @staticmethod
    def _base_output() -> dict[str, Any]:
        return {
            "domain": "",
            "agent_id": "",
            "intent": "",
            "capability": "",
            "confidence": 0.0,
            "scope": "",
            "filters": {},
            "entities": {},
            "dimensions": [],
            "metrics": [],
            "required_tables": [],
            "required_joins": [],
            "business_rules": [],
            "risk_flags": [],
            "needs_clarification": False,
            "clarification_question": None,
            "recommended_route": "needs_clarification",
            "reasoning_summary": "",
            "user_response_strategy": {
                "tone": "business",
                "sections": [],
                "warnings_to_include": [],
                "next_best_action": "",
            },
        }

    @staticmethod
    def _intent_tables(*, contract_payload: dict[str, Any], intent_id: str) -> list[str]:
        for item in list(contract_payload.get("intents") or []):
            if isinstance(item, dict) and str(item.get("id") or "").strip() == str(intent_id or "").strip():
                return [str(value) for value in list(item.get("tables") or []) if str(value).strip()]
        return []

    @staticmethod
    def _intent_strategy(*, contract_payload: dict[str, Any], intent_id: str) -> str:
        for item in list(contract_payload.get("intents") or []):
            if isinstance(item, dict) and str(item.get("id") or "").strip() == str(intent_id or "").strip():
                return str(item.get("strategy") or "").strip().lower()
        return ""

    @staticmethod
    def _intent_required_filters(*, contract_payload: dict[str, Any], intent_id: str) -> list[str]:
        for item in list(contract_payload.get("intents") or []):
            if isinstance(item, dict) and str(item.get("id") or "").strip() == str(intent_id or "").strip():
                return [str(value) for value in list(item.get("required_filters") or []) if str(value).strip()]
        return []

    @staticmethod
    def _intent_validation_rules(*, contract_payload: dict[str, Any], intent_id: str) -> list[str]:
        for item in list(contract_payload.get("intents") or []):
            if isinstance(item, dict) and str(item.get("id") or "").strip() == str(intent_id or "").strip():
                return [str(value) for value in list(item.get("validation_rules") or []) if str(value).strip()]
        return []

    @staticmethod
    def _allowed_filter_keys(*, contract_payload: dict[str, Any], intent_payload: dict[str, Any]) -> list[str]:
        supported = set()
        supported.update(str(item) for item in list(intent_payload.get("required_filters") or []) if str(item).strip())
        supported.update(str(item) for item in list(intent_payload.get("optional_filters") or []) if str(item).strip())
        if not supported:
            for item in list(contract_payload.get("intents") or []):
                if isinstance(item, dict):
                    supported.update(str(value) for value in list(item.get("required_filters") or []) if str(value).strip())
                    supported.update(str(value) for value in list(item.get("optional_filters") or []) if str(value).strip())
        supported.update({"cedula", "movil", "codigo", "serial", "orden_trabajo", "bodega"})
        return sorted(supported)

    @staticmethod
    def _resolve_scope(*, normalized: str, filters: dict[str, Any], entities: dict[str, Any]) -> str:
        if str(filters.get("bodega") or "").strip() == "operacion_hfc":
            return "operacion_hfc"
        if "movil" in entities or "cedula" in entities or "cuadrilla" in normalized or "tecnico" in normalized:
            return "persona_operativa"
        return "general"

    @staticmethod
    def _missing_filter_question(*, domain: str, capability_id: str, missing_filters: list[str]) -> str:
        missing = ", ".join(missing_filters)
        if domain == "inventario_logistica" and "inventory_kardex" in capability_id:
            return "¿Cuál es el código del material para consultar el kardex?"
        if domain == "inventario_logistica" and "traceability" in capability_id:
            return "¿Cuál es el serial específico que quieres rastrear?"
        return f"¿Qué valor debo usar para el filtro requerido: {missing}?"

    @staticmethod
    def _build_reasoning_summary(
        *,
        domain: str,
        intent_id: str,
        capability_id: str,
        filters: dict[str, Any],
        route: str,
        candidate_domain: str | None,
        route_debug_hints: dict[str, Any],
    ) -> str:
        pre_router = dict(route_debug_hints.get("pre_router") or {})
        parts = [
            f"Dominio propuesto: {domain or 'general'}.",
            f"Intent: {intent_id or 'sin_resolver'}.",
            f"Capability: {capability_id or 'sin_resolver'}.",
            f"Ruta recomendada: {route}.",
        ]
        if filters:
            parts.append(f"Filtros gobernados: {', '.join(sorted(filters.keys()))}.")
        if pre_router:
            parts.append(f"Pre-router observado: {str(pre_router.get('reason') or pre_router.get('signal') or 'si')}.")
        elif candidate_domain:
            parts.append(f"Dominio candidato inicial: {candidate_domain}.")
        return " ".join(parts)

    @staticmethod
    def _llm_enabled() -> bool:
        return str(os.getenv("IA_DEV_SEMANTIC_ORCHESTRATOR_OPENAI_ENABLED", "1") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    @staticmethod
    def _native_tools_enabled() -> bool:
        return str(os.getenv("IA_DEV_OPENAI_NATIVE_TOOLS_ENABLED", "1") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    @staticmethod
    def _openai_api_key() -> str:
        return str(os.getenv("OPENAI_API_KEY") or os.getenv("IA_DEV_OPENAI_API_KEY") or "").strip()
