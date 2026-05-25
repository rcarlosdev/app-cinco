from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from apps.ia_dev.application.runtime.tool_registry_service import ToolRegistryService


DOMINIO_CAPABILITY_PACK = "empleados"
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
_KNOWN_DETAIL_FILTER_ALIASES = {
    "cedula_empleado": "cedula",
    "identificacion": "cedula",
    "documento": "cedula",
    "id_empleado": "cedula",
    "estado_empleado": "estado",
}
_ALLOWED_PERIOD_FIELDS = {
    "fnacimiento_month",
}
_ALLOWED_DATE_SEMANTICS = {
    "birthday_month",
    "birthday_by_month",
    "birthday_today",
    "birthday_upcoming",
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


def _index_by_id(value: Any, *, key_name: str) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for item in list(value or []):
        if not isinstance(item, dict):
            continue
        key = str(item.get(key_name) or "").strip()
        if key:
            rows[key] = dict(item)
    return rows


@dataclass(slots=True)
class CapabilityPackValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": bool(self.ok),
            "errors": list(self.errors or []),
            "warnings": list(self.warnings or []),
        }


@dataclass(slots=True)
class CapabilityPackCoverageReport:
    templates_declared: list[str] = field(default_factory=list)
    templates_with_selection_rules: list[str] = field(default_factory=list)
    templates_without_selection_rules: list[str] = field(default_factory=list)
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
            "templates_used_by_legacy": list(self.templates_used_by_legacy or []),
            "templates_pending_migration": list(self.templates_pending_migration or []),
            "templates_legacy_allowed": list(self.templates_legacy_allowed or []),
            "templates_missing_selection_rules": list(self.templates_missing_selection_rules or []),
            "capability_pack_coverage": float(self.capability_pack_coverage or 0.0),
            "templates_pack_driven_count": int(self.templates_pack_driven_count or 0),
            "templates_legacy_allowed_count": int(self.templates_legacy_allowed_count or 0),
            "errors": list(self.errors or []),
            "warnings": list(self.warnings or []),
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


def load_employee_capability_pack(
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

    validation = validate_employee_capability_pack(
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
    bundle.coverage = build_employee_capability_pack_coverage(bundle)
    return bundle


def validate_employee_capability_pack(
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
        errors.append("dominio invalido para el Capability Pack de empleados")
    if not str(package_payload.get("version") or "").strip():
        errors.append("version obligatoria en paquete_capacidades.yaml")
    if not capabilities:
        errors.append("el pack de empleados debe declarar al menos una capability activa")
    if not semantic_bindings:
        errors.append("el pack de empleados debe declarar al menos un semantic_binding")

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
    declared_limitations = {
        str(item or "").strip()
        for item in list(package_payload.get("limitaciones_declaradas") or [])
        if str(item or "").strip()
    }
    declared_entities = {
        str(item or "").strip()
        for item in list(package_payload.get("entidades") or [])
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
        if not capability_id:
            errors.append("capability sin capability_id declarado")
        if not template_id:
            errors.append(f"{capability_id or 'capability'} sin template_id")
        elif template_id in seen_templates:
            errors.append(f"template_id duplicado en el pack de empleados: {template_id}")
        else:
            seen_templates.add(template_id)
        response_profile_id = str(capability.get("response_profile") or "").strip()
        if not response_profile_id or response_profile_id not in response_profiles_by_id:
            errors.append(f"{capability_id or template_id}: response_profile inexistente o no declarado")
        approval_policy_id = str(capability.get("approval_policy") or "").strip()
        if approval_policy_id and approval_policy_id not in approval_policies_by_id:
            errors.append(f"{capability_id or template_id}: approval_policy inexistente")
        tool_ids = [str(item or "").strip() for item in list(capability.get("tools") or []) if str(item or "").strip()]
        if not tool_ids:
            errors.append(f"{capability_id or template_id}: tools vacios")
        for tool_id in tool_ids:
            if tool_registry_service.get_tool(tool_id) is None:
                errors.append(f"{capability_id or template_id}: tool no existe en ToolRegistryService -> {tool_id}")
        rule_ids = [str(item or "").strip() for item in list(capability.get("reglas") or []) if str(item or "").strip()]
        if not rule_ids:
            errors.append(f"{capability_id or template_id}: reglas vacias")
        for rule_id in rule_ids:
            if rule_id not in rules_by_id:
                errors.append(f"{capability_id or template_id}: regla no declarada -> {rule_id}")
        eval_ids = [str(item or "").strip() for item in list(capability.get("evaluaciones") or []) if str(item or "").strip()]
        if not eval_ids:
            errors.append(f"{capability_id or template_id}: evaluaciones vacias")
        for eval_id in eval_ids:
            if eval_id not in evaluations_by_id:
                errors.append(f"{capability_id or template_id}: evaluacion no declarada -> {eval_id}")
        limitation_ids = [str(item or "").strip() for item in list(capability.get("limitaciones") or []) if str(item or "").strip()]
        if not limitation_ids:
            errors.append(f"{capability_id or template_id}: limitaciones vacias")
        for limitation_id in limitation_ids:
            if limitation_id not in declared_limitations:
                errors.append(f"{capability_id or template_id}: limitacion no declarada -> {limitation_id}")

    seen_semantic_templates: set[str] = set()
    for binding in semantic_bindings:
        template_id = str(binding.get("template_id") or "").strip()
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
        candidate_capability = str(binding.get("candidate_capability") or "").strip()
        if candidate_capability and candidate_capability not in capabilities_by_id:
            errors.append(f"semantic_binding {template_id}: candidate_capability no declarado -> {candidate_capability}")
        if candidate_capability != str(capability.get("capability_id") or "").strip():
            errors.append(f"semantic_binding {template_id}: candidate_capability no coincide con capability_id declarado")
        planner_route_hint = str(binding.get("planner_route_hint") or "").strip()
        if planner_route_hint != str(capability.get("planner_route_hint") or "").strip():
            errors.append(f"semantic_binding {template_id}: planner_route_hint no coincide con la capability declarada")
        response_profile_id = str(binding.get("response_profile") or "").strip()
        if response_profile_id != str(capability.get("response_profile") or "").strip():
            errors.append(f"semantic_binding {template_id}: response_profile no coincide con la capability declarada")
        if response_profile_id not in response_profiles_by_id:
            errors.append(f"semantic_binding {template_id}: response_profile no declarado -> {response_profile_id}")
        required_binding_keys = (
            "intent_ids",
            "entity_fields",
            "filter_fields",
            "grouping_fields",
            "selection_rules",
        )
        for required_key in required_binding_keys:
            if required_key not in binding:
                errors.append(f"semantic_binding {template_id}: {required_key} obligatorio en el binding")
        if not str(binding.get("candidate_capability") or "").strip():
            errors.append(f"semantic_binding {template_id}: candidate_capability obligatorio")
        elif str(binding.get("candidate_capability") or "").strip() != str(capability.get("capability_id") or "").strip():
            errors.append(f"semantic_binding {template_id}: candidate_capability no coincide con capability_id declarado")
        if not list(binding.get("selection_rules") or []):
            errors.append(f"semantic_binding {template_id}: selection_rules obligatorias")
        declared_tool_ids = {
            str(item or "").strip()
            for item in list(capability.get("tools") or [])
            if str(item or "").strip()
        }
        tool_id = str(binding.get("tool_id") or "").strip()
        if tool_id:
            if tool_registry_service.get_tool(tool_id) is None:
                errors.append(f"semantic_binding {template_id}: tool_id no existe en ToolRegistryService -> {binding.get('tool_id')}")
            elif tool_id not in declared_tool_ids:
                errors.append(f"semantic_binding {template_id}: tool_id no esta declarado en tools de la capability")
        entity_fields = {
            str(item or "").strip()
            for item in list(binding.get("entity_fields") or [])
            if str(item or "").strip()
        }
        filter_fields = {
            str(item or "").strip()
            for item in list(binding.get("filter_fields") or [])
            if str(item or "").strip()
        }
        if template_id == "detail_by_entity_and_period" and not filter_fields:
            errors.append(f"semantic_binding {template_id}: filter_fields obligatorios para detalle gobernado")
        if entity_fields and not entity_fields.issubset(declared_entities):
            errors.append(f"semantic_binding {template_id}: entity_fields fuera del set permitido del pack")
        if filter_fields and not filter_fields.issubset(declared_entities):
            errors.append(f"semantic_binding {template_id}: filter_fields fuera del set permitido del pack")
        grouping_fields = {
            str(item or "").strip()
            for item in list(binding.get("grouping_fields") or [])
            if str(item or "").strip()
        }
        if grouping_fields and not grouping_fields.issubset(declared_entities):
            errors.append(f"semantic_binding {template_id}: grouping_fields fuera del set permitido del pack")
        period_fields = {
            str(item or "").strip()
            for item in list(binding.get("period_fields") or [])
            if str(item or "").strip()
        }
        if period_fields and not period_fields.issubset(_ALLOWED_PERIOD_FIELDS):
            errors.append(f"semantic_binding {template_id}: period_fields fuera del set permitido")
        date_semantics = {
            str(item or "").strip()
            for item in list(binding.get("date_semantics") or [])
            if str(item or "").strip()
        }
        if date_semantics and not date_semantics.issubset(_ALLOWED_DATE_SEMANTICS):
            errors.append(f"semantic_binding {template_id}: date_semantics fuera del set permitido")
        if template_id == "count_records_by_period":
            if not period_fields:
                errors.append(f"semantic_binding {template_id}: period_fields obligatorios para cumpleanos gobernados")
            if not date_semantics:
                errors.append(f"semantic_binding {template_id}: date_semantics obligatorios para cumpleanos gobernados")
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
            if not declared_rule_ids:
                errors.append(f"semantic_binding {template_id}: selection_rules[{idx}] requiere declared_rules")
            for rule_id in declared_rule_ids:
                if rule_id not in rules_by_id:
                    errors.append(
                        f"semantic_binding {template_id}: selection_rules[{idx}] referencia regla no declarada -> {rule_id}"
                    )
            selector_grouping_fields = {
                str(item or "").strip()
                for item in list(selector.get("group_by_all_in") or [])
                if str(item or "").strip()
            }
            if selector.get("group_by_required") and not selector_grouping_fields and template_id == "aggregate_by_group_and_period":
                errors.append(
                    f"semantic_binding {template_id}: selection_rules[{idx}] requiere group_by_all_in para validar agrupaciones"
                )
            if selector_grouping_fields and not selector_grouping_fields.issubset(grouping_fields):
                errors.append(
                    f"semantic_binding {template_id}: selection_rules[{idx}] usa grouping_fields fuera de los permitidos"
                )
            selector_period_fields = {
                str(item or "").strip()
                for item in list(selector.get("period_fields_any_of") or [])
                if str(item or "").strip()
            }
            if selector_period_fields and not selector_period_fields.issubset(period_fields):
                errors.append(
                    f"semantic_binding {template_id}: selection_rules[{idx}] usa period_fields_any_of fuera de period_fields"
                )
            selector_date_semantics = {
                str(item or "").strip()
                for item in list(selector.get("date_semantics_any_of") or [])
                if str(item or "").strip()
            }
            if selector_date_semantics and not selector_date_semantics.issubset(date_semantics):
                errors.append(
                    f"semantic_binding {template_id}: selection_rules[{idx}] usa date_semantics_any_of fuera de date_semantics"
                )
            selector_filter_any = {
                _KNOWN_DETAIL_FILTER_ALIASES.get(str(item or "").strip(), str(item or "").strip())
                for item in list(selector.get("normalized_filters_any_of") or [])
                if str(item or "").strip()
            }
            if selector_filter_any and not selector_filter_any.issubset(filter_fields):
                errors.append(
                    f"semantic_binding {template_id}: selection_rules[{idx}] usa normalized_filters_any_of fuera de filter_fields"
                )
            selector_filter_all = {
                _KNOWN_DETAIL_FILTER_ALIASES.get(str(item or "").strip(), str(item or "").strip())
                for item in list(selector.get("normalized_filters_all_in") or [])
                if str(item or "").strip()
            }
            if selector_filter_all and not selector_filter_all.issubset(filter_fields):
                errors.append(
                    f"semantic_binding {template_id}: selection_rules[{idx}] usa normalized_filters_all_in fuera de filter_fields"
                )
            if template_id == "detail_by_entity_and_period":
                if not selector.get("group_by_absent"):
                    errors.append(
                        f"semantic_binding {template_id}: selection_rules[{idx}] debe exigir group_by_absent para detalle gobernado"
                    )
                if not selector_filter_any:
                    errors.append(
                        f"semantic_binding {template_id}: selection_rules[{idx}] requiere normalized_filters_any_of para seleccionar detalle"
                    )
                if not selector_filter_all:
                    errors.append(
                        f"semantic_binding {template_id}: selection_rules[{idx}] requiere normalized_filters_all_in para blindar filtros permitidos"
                    )
            if template_id == "count_records_by_period":
                if not selector.get("group_by_absent"):
                    errors.append(
                        f"semantic_binding {template_id}: selection_rules[{idx}] debe exigir group_by_absent para cumpleanos gobernados"
                    )
                if not selector_period_fields:
                    errors.append(
                        f"semantic_binding {template_id}: selection_rules[{idx}] requiere period_fields_any_of para cumpleanos gobernados"
                    )
                if not selector_date_semantics:
                    errors.append(
                        f"semantic_binding {template_id}: selection_rules[{idx}] requiere date_semantics_any_of para cumpleanos gobernados"
                    )

    for response_profile_id, response_profile in response_profiles_by_id.items():
        if not list(response_profile.get("columnas") or []):
            errors.append(f"perfil {response_profile_id}: columnas obligatorias")

    coverage = build_employee_capability_pack_coverage_from_components(
        declared_templates=set(capabilities_by_template) | {str(item.get('template_id') or '').strip() for item in semantic_bindings},
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


def build_employee_capability_pack_coverage(bundle: CapabilityPackBundle | None = None) -> CapabilityPackCoverageReport:
    if bundle is None:
        return _cached_employee_capability_pack_coverage()
    declared_templates = set(bundle.capabilities_by_template) | set(bundle.semantic_bindings_by_template)
    return build_employee_capability_pack_coverage_from_components(
        declared_templates=declared_templates,
        semantic_bindings=bundle.semantic_bindings,
    )


@lru_cache(maxsize=1)
def _cached_employee_capability_pack_coverage() -> CapabilityPackCoverageReport:
    bundle = load_employee_capability_pack()
    return build_employee_capability_pack_coverage(bundle)


def build_employee_capability_pack_coverage_from_components(
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
    return CapabilityPackCoverageReport(
        templates_declared=sorted(normalized_declared),
        templates_with_selection_rules=sorted(templates_with_selection_rules),
        templates_without_selection_rules=sorted(templates_without_selection_rules),
        templates_used_by_legacy=[],
        templates_pending_migration=[],
        templates_legacy_allowed=[],
        templates_missing_selection_rules=sorted(templates_without_selection_rules),
        capability_pack_coverage=round(len(templates_with_selection_rules) / max(1, len(normalized_declared)), 4),
        templates_pack_driven_count=len(templates_with_selection_rules),
        templates_legacy_allowed_count=0,
        errors=[] if not templates_without_selection_rules else [
            f"template activo sin selection_rules declarativas: {template_id}"
            for template_id in sorted(templates_without_selection_rules)
        ],
        warnings=[],
    )
