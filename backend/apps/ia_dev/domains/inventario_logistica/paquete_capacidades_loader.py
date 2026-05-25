from __future__ import annotations

import re
from functools import lru_cache
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from apps.ia_dev.application.runtime.tool_registry_service import ToolRegistryService

from .metadata_gobernada_inventario import construir_metadata_gobernada_inventario


DOMINIO_CAPABILITY_PACK = "inventario_logistica"
_BASE_DIR = Path(__file__).resolve().parent
_ARCHIVOS_PACK = {
    "paquete": _BASE_DIR / "paquete_capacidades.yaml",
    "reglas": _BASE_DIR / "reglas_semanticas.yaml",
    "perfiles": _BASE_DIR / "perfiles_respuesta.yaml",
    "aprobaciones": _BASE_DIR / "politicas_aprobacion.yaml",
    "evaluaciones": _BASE_DIR / "evaluaciones.yaml",
}
_MARCAS_SQL_PROHIBIDAS = re.compile(r"\b(select|insert|update|delete|drop|alter|truncate)\b", re.IGNORECASE)
_MARCAS_PROMPT_INSEGURO = re.compile(
    r"(ignore\s+previous\s+instructions|system\s+prompt|chain[- ]of[- ]thought|cot\b|jailbreak)",
    re.IGNORECASE,
)
_INVENTORY_TEMPLATE_LITERAL_RE = re.compile(r"\binventory_[a-z0-9_]+\b")
_FOCAL_VALIDATION_TEST_FILES = (
    _BASE_DIR.parents[1] / "tests" / "test_inventory_capability_pack_loader.py",
    _BASE_DIR.parents[1] / "tests" / "test_semantic_capability_registry.py",
    _BASE_DIR.parents[1] / "tests" / "test_inventario_semantic_resolver.py",
    _BASE_DIR.parents[1] / "tests" / "test_inventario_runtime_eval_suite.py",
)
_KNOWN_LEGACY_TEMPLATE_IDS = {
    "inventory_alert_semantic_report",
    "inventory_assignment_distribution_pending",
    "inventory_consumption_billing_operacion_hfc",
    "inventory_consumption_top",
    "inventory_entries_by_month",
    "inventory_external_reconciliation_pending",
    "inventory_movement_detail",
    "inventory_notification_pending",
    "inventory_reconciliation_pending_validation",
    "inventory_risk_consumo_movil_sin_validar",
    "inventory_semantic_report",
    "inventory_serial_association_departures",
    "inventory_serial_stock_by_dimension",
}


def _read_yaml_text(path: Path) -> str:
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")


def _safe_load_yaml(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(_read_yaml_text(path)) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"El archivo {path.name} debe cargar un objeto raiz.")
    return raw


@dataclass(slots=True)
class CapabilityPackValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": bool(self.ok),
            "errors": [str(item or "") for item in list(self.errors or []) if str(item or "").strip()],
            "warnings": [str(item or "") for item in list(self.warnings or []) if str(item or "").strip()],
        }


@dataclass(slots=True)
class CapabilityPackCoverageReport:
    templates_declared: list[str] = field(default_factory=list)
    templates_with_selection_rules: list[str] = field(default_factory=list)
    templates_without_selection_rules: list[str] = field(default_factory=list)
    templates_used_by_tests: list[str] = field(default_factory=list)
    templates_used_by_evals: list[str] = field(default_factory=list)
    templates_used_by_legacy: list[str] = field(default_factory=list)
    templates_pending_migration: list[str] = field(default_factory=list)
    templates_legacy_allowed: list[str] = field(default_factory=list)
    templates_missing_selection_rules: list[str] = field(default_factory=list)
    capability_pack_coverage: float = 0.0
    templates_pack_driven_count: int = 0
    templates_legacy_allowed_count: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "templates_declared": list(self.templates_declared or []),
            "templates_with_selection_rules": list(self.templates_with_selection_rules or []),
            "templates_without_selection_rules": list(self.templates_without_selection_rules or []),
            "templates_used_by_tests": list(self.templates_used_by_tests or []),
            "templates_used_by_evals": list(self.templates_used_by_evals or []),
            "templates_used_by_legacy": list(self.templates_used_by_legacy or []),
            "templates_pending_migration": list(self.templates_pending_migration or []),
            "templates_legacy_allowed": list(self.templates_legacy_allowed or []),
            "templates_missing_selection_rules": list(self.templates_missing_selection_rules or []),
            "capability_pack_coverage": float(self.capability_pack_coverage or 0.0),
            "templates_pack_driven_count": int(self.templates_pack_driven_count or 0),
            "templates_legacy_allowed_count": int(self.templates_legacy_allowed_count or 0),
            "errors": [str(item or "") for item in list(self.errors or []) if str(item or "").strip()],
            "warnings": [str(item or "") for item in list(self.warnings or []) if str(item or "").strip()],
        }


@dataclass(slots=True)
class CapabilityPackBundle:
    domain: str
    pack_name: str
    version: str
    package_payload: dict[str, Any]
    semantic_bindings: list[dict[str, Any]]
    semantic_bindings_by_template: dict[str, dict[str, Any]]
    rules_by_id: dict[str, dict[str, Any]]
    response_profiles_by_id: dict[str, dict[str, Any]]
    approval_policies_by_id: dict[str, dict[str, Any]]
    evaluations_by_id: dict[str, dict[str, Any]]
    capabilities_by_template: dict[str, dict[str, Any]]
    capabilities_by_id: dict[str, dict[str, Any]]
    validation: CapabilityPackValidationResult
    coverage: CapabilityPackCoverageReport | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "domain": str(self.domain or ""),
            "pack_name": str(self.pack_name or ""),
            "version": str(self.version or ""),
            "package_payload": dict(self.package_payload or {}),
            "semantic_bindings": [dict(item or {}) for item in list(self.semantic_bindings or []) if isinstance(item, dict)],
            "semantic_bindings_by_template": {
                str(key): dict(value or {}) for key, value in dict(self.semantic_bindings_by_template or {}).items()
            },
            "rules_by_id": {str(key): dict(value or {}) for key, value in dict(self.rules_by_id or {}).items()},
            "response_profiles_by_id": {
                str(key): dict(value or {}) for key, value in dict(self.response_profiles_by_id or {}).items()
            },
            "approval_policies_by_id": {
                str(key): dict(value or {}) for key, value in dict(self.approval_policies_by_id or {}).items()
            },
            "evaluations_by_id": {
                str(key): dict(value or {}) for key, value in dict(self.evaluations_by_id or {}).items()
            },
            "capabilities_by_template": {
                str(key): dict(value or {}) for key, value in dict(self.capabilities_by_template or {}).items()
            },
            "capabilities_by_id": {
                str(key): dict(value or {}) for key, value in dict(self.capabilities_by_id or {}).items()
            },
            "validation": self.validation.as_dict(),
            "coverage": self.coverage.as_dict() if isinstance(self.coverage, CapabilityPackCoverageReport) else {},
            "trace": capability_pack_trace_payload(self),
        }


def load_inventory_capability_pack(
    *,
    tool_registry_service: ToolRegistryService | None = None,
) -> CapabilityPackBundle:
    tool_registry = tool_registry_service or ToolRegistryService()
    package_payload = _safe_load_yaml(_ARCHIVOS_PACK["paquete"])
    rules_payload = _safe_load_yaml(_ARCHIVOS_PACK["reglas"])
    response_profiles_payload = _safe_load_yaml(_ARCHIVOS_PACK["perfiles"])
    approval_payload = _safe_load_yaml(_ARCHIVOS_PACK["aprobaciones"])
    evaluations_payload = _safe_load_yaml(_ARCHIVOS_PACK["evaluaciones"])

    rules_by_id = _index_by_id(rules_payload.get("reglas"), key_name="id")
    response_profiles_by_id = _index_by_id(response_profiles_payload.get("perfiles_respuesta"), key_name="id")
    approval_policies_by_id = _index_by_id(approval_payload.get("politicas_aprobacion"), key_name="id")
    evaluations_by_id = _index_by_id(evaluations_payload.get("evaluaciones"), key_name="id")

    capabilities = [
        dict(item or {})
        for item in list(package_payload.get("capacidades") or [])
        if isinstance(item, dict)
    ]
    semantic_bindings = [
        dict(item or {})
        for item in list(package_payload.get("semantic_bindings") or [])
        if isinstance(item, dict)
    ]
    semantic_bindings_by_template = {
        str(item.get("template_id") or "").strip(): item
        for item in semantic_bindings
        if str(item.get("template_id") or "").strip()
    }
    capabilities_by_template = {
        str(item.get("template_id") or "").strip(): item
        for item in capabilities
        if str(item.get("template_id") or "").strip()
    }
    capabilities_by_id = {
        str(item.get("capability_id") or "").strip(): item
        for item in capabilities
        if str(item.get("capability_id") or "").strip()
    }

    validation = validate_inventory_capability_pack(
        package_payload=package_payload,
        rules_by_id=rules_by_id,
        response_profiles_by_id=response_profiles_by_id,
        approval_policies_by_id=approval_policies_by_id,
        evaluations_by_id=evaluations_by_id,
        capabilities=capabilities,
        semantic_bindings=semantic_bindings,
        tool_registry_service=tool_registry,
    )
    bundle = CapabilityPackBundle(
        domain=str(package_payload.get("dominio") or "").strip(),
        pack_name=str(package_payload.get("nombre_paquete") or "").strip(),
        version=str(package_payload.get("version") or "").strip(),
        package_payload=package_payload,
        semantic_bindings=semantic_bindings,
        semantic_bindings_by_template=semantic_bindings_by_template,
        rules_by_id=rules_by_id,
        response_profiles_by_id=response_profiles_by_id,
        approval_policies_by_id=approval_policies_by_id,
        evaluations_by_id=evaluations_by_id,
        capabilities_by_template=capabilities_by_template,
        capabilities_by_id=capabilities_by_id,
        validation=validation,
    )
    bundle.coverage = build_inventory_capability_pack_coverage(bundle)
    return bundle


def validate_inventory_capability_pack(
    *,
    package_payload: dict[str, Any],
    rules_by_id: dict[str, dict[str, Any]],
    response_profiles_by_id: dict[str, dict[str, Any]],
    approval_policies_by_id: dict[str, dict[str, Any]],
    evaluations_by_id: dict[str, dict[str, Any]],
    capabilities: list[dict[str, Any]],
    semantic_bindings: list[dict[str, Any]],
    tool_registry_service: ToolRegistryService,
) -> CapabilityPackValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    if str(package_payload.get("dominio") or "").strip() != DOMINIO_CAPABILITY_PACK:
        errors.append("dominio invalido para el Capability Pack de inventario_logistica")
    if not str(package_payload.get("version") or "").strip():
        errors.append("version obligatoria en paquete_capacidades.yaml")
    if not capabilities:
        errors.append("el pack debe declarar al menos una capability")
    if not semantic_bindings:
        warnings.append("el pack no declara semantic_bindings")

    capabilities_by_template = {
        str(item.get("template_id") or "").strip(): dict(item or {})
        for item in capabilities
        if str(item.get("template_id") or "").strip()
    }
    capabilities_by_id = {
        str(item.get("capability_id") or "").strip(): dict(item or {})
        for item in capabilities
        if str(item.get("capability_id") or "").strip()
    }

    metadata_payload = construir_metadata_gobernada_inventario()
    reglas_metadata = {
        str(item.get("codigo") or "").strip()
        for item in list(metadata_payload.get("dd_reglas") or [])
        if isinstance(item, dict)
    }
    sinonimos_metadata = {
        str(item.get("scope_clave") or "").strip()
        for item in list(metadata_payload.get("dd_sinonimos") or [])
        if isinstance(item, dict)
    }
    capacidades_metadata = {
        str(item.get("campo_logico") or "").strip()
        for item in list(metadata_payload.get("ia_dev_capacidades_columna") or [])
        if isinstance(item, dict)
    }

    declared_limitations = {
        str(item or "").strip()
        for item in list(package_payload.get("limitaciones_declaradas") or [])
        if str(item or "").strip()
    }

    for path in _ARCHIVOS_PACK.values():
        raw = _read_yaml_text(path)
        if _MARCAS_SQL_PROHIBIDAS.search(raw):
            errors.append(f"{path.name} contiene marcas de SQL libre no permitidas")
        if _MARCAS_PROMPT_INSEGURO.search(raw):
            errors.append(f"{path.name} contiene prompts internos inseguros")

    seen_templates: set[str] = set()
    for capability in capabilities:
        capability_id = str(capability.get("capability_id") or "").strip()
        template_id = str(capability.get("template_id") or "").strip()
        response_profile_id = str(capability.get("response_profile") or "").strip()
        approval_policy_id = str(capability.get("approval_policy") or "").strip()
        tool_ids = [
            str(item or "").strip()
            for item in list(capability.get("tools") or [])
            if str(item or "").strip()
        ]
        rule_ids = [
            str(item or "").strip()
            for item in list(capability.get("reglas") or [])
            if str(item or "").strip()
        ]
        eval_ids = [
            str(item or "").strip()
            for item in list(capability.get("evaluaciones") or [])
            if str(item or "").strip()
        ]
        limitation_ids = [
            str(item or "").strip()
            for item in list(capability.get("limitaciones") or [])
            if str(item or "").strip()
        ]
        if not capability_id:
            errors.append("capability sin capability_id declarado")
        if not template_id:
            errors.append(f"{capability_id or 'capability'} sin template_id")
        elif template_id in seen_templates:
            errors.append(f"template_id duplicado en el pack: {template_id}")
        else:
            seen_templates.add(template_id)
        if not response_profile_id or response_profile_id not in response_profiles_by_id:
            errors.append(f"{capability_id or template_id}: response_profile inexistente o no declarado")
        if approval_policy_id and approval_policy_id not in approval_policies_by_id:
            errors.append(f"{capability_id or template_id}: approval_policy inexistente")
        if not tool_ids:
            errors.append(f"{capability_id or template_id}: tools vacios")
        for tool_id in tool_ids:
            if tool_registry_service.get_tool(tool_id) is None:
                errors.append(f"{capability_id or template_id}: tool no existe en ToolRegistryService -> {tool_id}")
        if not rule_ids:
            errors.append(f"{capability_id or template_id}: reglas vacias")
        for rule_id in rule_ids:
            if rule_id not in rules_by_id:
                errors.append(f"{capability_id or template_id}: regla no declarada -> {rule_id}")
        if not eval_ids:
            errors.append(f"{capability_id or template_id}: evaluaciones vacias")
        for eval_id in eval_ids:
            if eval_id not in evaluations_by_id:
                errors.append(f"{capability_id or template_id}: evaluacion no declarada -> {eval_id}")
        if not limitation_ids:
            errors.append(f"{capability_id or template_id}: limitaciones vacias")
        for limitation_id in limitation_ids:
            if limitation_id not in declared_limitations:
                errors.append(f"{capability_id or template_id}: limitacion no declarada -> {limitation_id}")

    seen_semantic_templates: set[str] = set()
    for binding in semantic_bindings:
        template_id = str(binding.get("template_id") or "").strip()
        candidate_capability = str(binding.get("candidate_capability") or "").strip()
        planner_route_hint = str(binding.get("planner_route_hint") or "").strip()
        response_profile_id = str(binding.get("response_profile") or "").strip()
        tool_id = str(binding.get("tool_id") or "").strip()
        required_binding_keys = (
            "intent_ids",
            "entity_fields",
            "families",
            "output_profiles",
            "selection_rules",
        )
        if not template_id:
            errors.append("semantic_binding sin template_id declarado")
            continue
        if template_id in seen_semantic_templates:
            errors.append(f"semantic_binding duplicado para template_id: {template_id}")
            continue
        seen_semantic_templates.add(template_id)
        capability = capabilities_by_template.get(template_id)
        if capability is None:
            errors.append(f"semantic_binding {template_id}: template_id no existe en capacidades")
            continue
        if not candidate_capability:
            errors.append(f"semantic_binding {template_id}: candidate_capability obligatorio")
        elif candidate_capability not in capabilities_by_id:
            errors.append(f"semantic_binding {template_id}: candidate_capability no declarado -> {candidate_capability}")
        elif candidate_capability != str(capability.get("capability_id") or "").strip():
            errors.append(f"semantic_binding {template_id}: candidate_capability no coincide con capability_id declarado")
        if not planner_route_hint:
            errors.append(f"semantic_binding {template_id}: planner_route_hint obligatorio")
        elif planner_route_hint != str(capability.get("planner_route_hint") or "").strip():
            errors.append(f"semantic_binding {template_id}: planner_route_hint no coincide con la capability declarada")
        if not response_profile_id:
            errors.append(f"semantic_binding {template_id}: response_profile obligatorio")
        elif response_profile_id not in response_profiles_by_id:
            errors.append(f"semantic_binding {template_id}: response_profile no declarado -> {response_profile_id}")
        elif response_profile_id != str(capability.get("response_profile") or "").strip():
            errors.append(f"semantic_binding {template_id}: response_profile no coincide con la capability declarada")
        for required_key in required_binding_keys:
            if required_key not in binding:
                errors.append(f"semantic_binding {template_id}: {required_key} obligatorio en el binding")
        if tool_id:
            if tool_registry_service.get_tool(tool_id) is None:
                errors.append(f"semantic_binding {template_id}: tool_id no existe en ToolRegistryService -> {tool_id}")
            elif tool_id not in {
                str(item or "").strip()
                for item in list(capability.get("tools") or [])
                if str(item or "").strip()
            }:
                errors.append(f"semantic_binding {template_id}: tool_id no esta declarado en tools de la capability")
        for idx, selector in enumerate(list(binding.get("selection_rules") or []), start=1):
            if not isinstance(selector, dict):
                errors.append(f"semantic_binding {template_id}: selection_rules[{idx}] debe ser un objeto")
                continue
            selector_intents = [
                str(item or "").strip()
                for item in list(selector.get("intent_ids") or binding.get("intent_ids") or [])
                if str(item or "").strip()
            ]
            if not selector_intents:
                errors.append(f"semantic_binding {template_id}: selection_rules[{idx}] requiere intent_ids")
            declared_rule_ids = [
                str(item or "").strip()
                for item in list(selector.get("declared_rules") or capability.get("reglas") or [])
                if str(item or "").strip()
            ]
            for rule_id in declared_rule_ids:
                if rule_id not in rules_by_id:
                    errors.append(
                        f"semantic_binding {template_id}: selection_rules[{idx}] referencia regla no declarada -> {rule_id}"
                    )

    for rule_id, rule in rules_by_id.items():
        metadata_links = dict(rule.get("metadata_gobernada") or {})
        if not metadata_links:
            errors.append(f"regla {rule_id}: metadata_gobernada obligatoria")
            continue
        for metadata_rule_id in _as_list(metadata_links.get("dd_reglas")):
            if str(metadata_rule_id or "").strip() not in reglas_metadata:
                errors.append(f"regla {rule_id}: dd_reglas no vinculado a metadata gobernada -> {metadata_rule_id}")
        for synonym_scope in _as_list(metadata_links.get("dd_sinonimos")):
            if str(synonym_scope or "").strip() not in sinonimos_metadata:
                errors.append(f"regla {rule_id}: dd_sinonimos no vinculado a metadata gobernada -> {synonym_scope}")
        for field_name in _as_list(metadata_links.get("ia_dev_capacidades_columna")):
            if str(field_name or "").strip() not in capacidades_metadata:
                errors.append(
                    f"regla {rule_id}: ia_dev_capacidades_columna no vinculado a metadata gobernada -> {field_name}"
                )

    for response_profile_id, response_profile in response_profiles_by_id.items():
        if not list(response_profile.get("columnas") or []):
            errors.append(f"perfil {response_profile_id}: columnas obligatorias")

    coverage = build_inventory_capability_pack_coverage_from_components(
        declared_templates=set(capabilities_by_template) | {str(item.get("template_id") or "").strip() for item in semantic_bindings},
        semantic_bindings=semantic_bindings,
    )
    errors.extend(list(coverage.errors or []))
    warnings.extend(list(coverage.warnings or []))

    return CapabilityPackValidationResult(ok=not errors, errors=errors, warnings=warnings)


def capability_pack_trace_payload(bundle: CapabilityPackBundle | dict[str, Any]) -> dict[str, Any]:
    if isinstance(bundle, CapabilityPackBundle):
        pack_name = bundle.pack_name
        version = bundle.version
        capabilities_by_template = bundle.capabilities_by_template
        rules_by_id = bundle.rules_by_id
        response_profiles_by_id = bundle.response_profiles_by_id
        evaluations_by_id = bundle.evaluations_by_id
        coverage_payload = bundle.coverage.as_dict() if isinstance(bundle.coverage, CapabilityPackCoverageReport) else {}
    else:
        pack_name = str(bundle.get("pack_name") or "")
        version = str(bundle.get("version") or "")
        capabilities_by_template = dict(bundle.get("capabilities_by_template") or {})
        rules_by_id = dict(bundle.get("rules_by_id") or {})
        response_profiles_by_id = dict(bundle.get("response_profiles_by_id") or {})
        evaluations_by_id = dict(bundle.get("evaluations_by_id") or {})
        coverage_payload = dict(bundle.get("coverage") or {})
    return {
        "paquete_capacidad_usado": str(pack_name or ""),
        "version_paquete": str(version or ""),
        "capacidades_declaradas": sorted(
            {
                str(item.get("capability_id") or "").strip()
                for item in dict(capabilities_by_template or {}).values()
                if isinstance(item, dict) and str(item.get("capability_id") or "").strip()
            }
        ),
        "reglas_declaradas": sorted(str(key or "").strip() for key in dict(rules_by_id or {}).keys() if str(key or "").strip()),
        "perfiles_respuesta": sorted(
            str(key or "").strip() for key in dict(response_profiles_by_id or {}).keys() if str(key or "").strip()
        ),
        "evaluaciones_asociadas": sorted(
            str(key or "").strip() for key in dict(evaluations_by_id or {}).keys() if str(key or "").strip()
        ),
        "capability_pack_coverage": float(coverage_payload.get("capability_pack_coverage") or 0.0),
        "templates_pack_driven_count": int(coverage_payload.get("templates_pack_driven_count") or 0),
        "templates_legacy_allowed_count": int(coverage_payload.get("templates_legacy_allowed_count") or 0),
        "templates_missing_selection_rules": [
            str(item or "")
            for item in list(coverage_payload.get("templates_missing_selection_rules") or [])
            if str(item or "").strip()
        ],
    }


def build_inventory_capability_pack_coverage(
    bundle: CapabilityPackBundle | None = None,
) -> CapabilityPackCoverageReport:
    if bundle is None:
        return _cached_inventory_capability_pack_coverage()
    declared_templates = set(bundle.capabilities_by_template) | set(bundle.semantic_bindings_by_template)
    return build_inventory_capability_pack_coverage_from_components(
        declared_templates=declared_templates,
        semantic_bindings=bundle.semantic_bindings,
    )


@lru_cache(maxsize=1)
def _cached_inventory_capability_pack_coverage() -> CapabilityPackCoverageReport:
    bundle = load_inventory_capability_pack()
    return build_inventory_capability_pack_coverage(bundle)


def build_inventory_capability_pack_coverage_from_components(
    *,
    declared_templates: set[str],
    semantic_bindings: list[dict[str, Any]],
) -> CapabilityPackCoverageReport:
    normalized_declared = {
        str(item or "").strip()
        for item in set(declared_templates or set())
        if str(item or "").strip()
    }
    templates_with_selection_rules = {
        str(binding.get("template_id") or "").strip()
        for binding in list(semantic_bindings or [])
        if str(binding.get("template_id") or "").strip() and list(binding.get("selection_rules") or [])
    }
    templates_without_selection_rules = normalized_declared - templates_with_selection_rules

    runtime_eval_templates, legacy_allowed_eval_templates = _inventory_eval_templates()
    known_templates = normalized_declared | set(_KNOWN_LEGACY_TEMPLATE_IDS) | runtime_eval_templates
    test_templates = _inventory_templates_from_focal_tests(known_templates=known_templates)
    active_templates = test_templates | runtime_eval_templates
    active_templates_without_selection_rules = active_templates - templates_with_selection_rules
    templates_used_by_legacy = set(active_templates_without_selection_rules)
    templates_pending_migration = set(templates_used_by_legacy)
    templates_pack_driven = active_templates & templates_with_selection_rules
    templates_without_selection_rules = templates_without_selection_rules | active_templates_without_selection_rules

    errors: list[str] = []
    warnings: list[str] = []
    for template_id in sorted(runtime_eval_templates):
        if template_id in templates_with_selection_rules:
            continue
        if template_id in legacy_allowed_eval_templates:
            warnings.append(f"eval template legacy_allowed sin selection_rules: {template_id}")
            continue
        errors.append(f"eval template activo sin selection_rules declarativas: {template_id}")

    return CapabilityPackCoverageReport(
        templates_declared=sorted(normalized_declared),
        templates_with_selection_rules=sorted(templates_with_selection_rules),
        templates_without_selection_rules=sorted(templates_without_selection_rules),
        templates_used_by_tests=sorted(test_templates),
        templates_used_by_evals=sorted(runtime_eval_templates),
        templates_used_by_legacy=sorted(templates_used_by_legacy),
        templates_pending_migration=sorted(templates_pending_migration),
        templates_legacy_allowed=sorted(legacy_allowed_eval_templates & templates_used_by_legacy),
        templates_missing_selection_rules=sorted(templates_pending_migration),
        capability_pack_coverage=round(len(templates_pack_driven) / max(1, len(active_templates)), 4),
        templates_pack_driven_count=len(templates_pack_driven),
        templates_legacy_allowed_count=len(legacy_allowed_eval_templates & templates_used_by_legacy),
        errors=errors,
        warnings=warnings,
    )


def _inventory_templates_from_focal_tests(*, known_templates: set[str]) -> set[str]:
    templates: set[str] = set()
    for path in _FOCAL_VALIDATION_TEST_FILES:
        if not path.exists():
            continue
        text = _read_yaml_text(path)
        templates.update(_extract_inventory_template_literals(text=text, known_templates=known_templates))
    return templates


def _extract_inventory_template_literals(*, text: str, known_templates: set[str]) -> set[str]:
    return {
        match.group(0)
        for match in _INVENTORY_TEMPLATE_LITERAL_RE.finditer(str(text or ""))
        if match.group(0) in known_templates
    }


def _inventory_eval_templates() -> tuple[set[str], set[str]]:
    from apps.ia_dev.application.runtime.inventario_runtime_eval_suite import build_inventory_runtime_eval_cases

    runtime_eval_templates: set[str] = set()
    legacy_allowed_eval_templates: set[str] = set()
    for case in build_inventory_runtime_eval_cases():
        template_id = str(getattr(case, "expected_template_id", "") or "").strip()
        if not template_id:
            continue
        runtime_eval_templates.add(template_id)
        if bool(getattr(case, "legacy_allowed", False)):
            legacy_allowed_eval_templates.add(template_id)
    return runtime_eval_templates, legacy_allowed_eval_templates


def _index_by_id(value: Any, *, key_name: str) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for item in list(value or []):
        if not isinstance(item, dict):
            continue
        key = str(item.get(key_name) or "").strip()
        if key:
            rows[key] = dict(item)
    return rows


def _as_list(value: Any) -> list[Any]:
    return list(value or []) if isinstance(value, list) else []
