from __future__ import annotations

import re
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
class CapabilityPackBundle:
    domain: str
    pack_name: str
    version: str
    package_payload: dict[str, Any]
    rules_by_id: dict[str, dict[str, Any]]
    response_profiles_by_id: dict[str, dict[str, Any]]
    approval_policies_by_id: dict[str, dict[str, Any]]
    evaluations_by_id: dict[str, dict[str, Any]]
    capabilities_by_template: dict[str, dict[str, Any]]
    capabilities_by_id: dict[str, dict[str, Any]]
    validation: CapabilityPackValidationResult

    def as_dict(self) -> dict[str, Any]:
        return {
            "domain": str(self.domain or ""),
            "pack_name": str(self.pack_name or ""),
            "version": str(self.version or ""),
            "package_payload": dict(self.package_payload or {}),
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
        tool_registry_service=tool_registry,
    )
    return CapabilityPackBundle(
        domain=str(package_payload.get("dominio") or "").strip(),
        pack_name=str(package_payload.get("nombre_paquete") or "").strip(),
        version=str(package_payload.get("version") or "").strip(),
        package_payload=package_payload,
        rules_by_id=rules_by_id,
        response_profiles_by_id=response_profiles_by_id,
        approval_policies_by_id=approval_policies_by_id,
        evaluations_by_id=evaluations_by_id,
        capabilities_by_template=capabilities_by_template,
        capabilities_by_id=capabilities_by_id,
        validation=validation,
    )


def validate_inventory_capability_pack(
    *,
    package_payload: dict[str, Any],
    rules_by_id: dict[str, dict[str, Any]],
    response_profiles_by_id: dict[str, dict[str, Any]],
    approval_policies_by_id: dict[str, dict[str, Any]],
    evaluations_by_id: dict[str, dict[str, Any]],
    capabilities: list[dict[str, Any]],
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

    return CapabilityPackValidationResult(ok=not errors, errors=errors, warnings=warnings)


def capability_pack_trace_payload(bundle: CapabilityPackBundle | dict[str, Any]) -> dict[str, Any]:
    if isinstance(bundle, CapabilityPackBundle):
        pack_name = bundle.pack_name
        version = bundle.version
        capabilities_by_template = bundle.capabilities_by_template
        rules_by_id = bundle.rules_by_id
        response_profiles_by_id = bundle.response_profiles_by_id
        evaluations_by_id = bundle.evaluations_by_id
    else:
        pack_name = str(bundle.get("pack_name") or "")
        version = str(bundle.get("version") or "")
        capabilities_by_template = dict(bundle.get("capabilities_by_template") or {})
        rules_by_id = dict(bundle.get("rules_by_id") or {})
        response_profiles_by_id = dict(bundle.get("response_profiles_by_id") or {})
        evaluations_by_id = dict(bundle.get("evaluations_by_id") or {})
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
    }


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
