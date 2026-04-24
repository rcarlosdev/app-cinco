from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from apps.ia_dev.application.taxonomia_dominios import (
    DOMINIOS_OPERATIVOS_CANONICOS,
    normalizar_codigo_dominio,
)
from apps.ia_dev.application.delegation.domain_context_loader import DomainContextLoader
from apps.ia_dev.services.sql_store import IADevSqlStore


@dataclass(frozen=True, slots=True)
class DomainDescriptor:
    domain_code: str
    domain_name: str
    domain_status: str
    maturity_level: str
    schema_confidence: float
    business_goal: str
    main_entity: str
    source_of_truth: str
    raw_context: dict[str, Any]

    @property
    def is_active(self) -> bool:
        return self.domain_status == "active"

    @property
    def is_partial(self) -> bool:
        return self.domain_status == "partial"

    @property
    def is_planned(self) -> bool:
        return self.domain_status == "planned"

    def as_dict(self) -> dict[str, Any]:
        return {
            "domain_code": self.domain_code,
            "domain_name": self.domain_name,
            "domain_status": self.domain_status,
            "maturity_level": self.maturity_level,
            "schema_confidence": self.schema_confidence,
            "business_goal": self.business_goal,
            "main_entity": self.main_entity,
            "source_of_truth": self.source_of_truth,
            "flags": dict(self.raw_context.get("flags") or {}),
            "capabilities": list(self.raw_context.get("capabilities") or []),
        }


class DomainRegistry:
    DOMAIN_ALIASES = {
        "attendance": "ausentismo",
        "ausentismo": "ausentismo",
        "transport": "transporte",
        "transporte": "transporte",
        "rrhh": "empleados",
        "employee": "empleados",
        "empleados": "empleados",
        "viatics": "viaticos",
        "viaticos": "viaticos",
        "payroll": "nomina",
        "nomina": "nomina",
        "facturacion": "facturacion",
        "comisiones": "comisiones",
        "horas_extras": "horas_extras",
        "compras": "compras",
        "herramientas": "herramientas",
        "dominicales": "dominicales",
    }
    DOMAIN_KEYWORDS = {
        "ausentismo": ("ausent", "asistencia", "injustific"),
        "empleados": ("emplead", "supervisor", "carpeta", "area", "cargo"),
        "transporte": ("transporte", "vehicul", "ruta", "movilidad"),
        "comisiones": ("comision", "comisiones", "incentivo"),
        "facturacion": ("factur", "facturacion", "factura"),
        "viaticos": ("viatico", "viaticos"),
        "horas_extras": ("hora extra", "horas extras", "horas_extras"),
    }

    def __init__(self, *, context_loader: DomainContextLoader | None = None):
        self.context_loader = context_loader or DomainContextLoader()
        self.store = IADevSqlStore()
        self._cache: dict[str, DomainDescriptor] = {}
        self.reload()

    def reload(self) -> None:
        contexts = self.context_loader.load_all()
        cache: dict[str, DomainDescriptor] = {}
        for code, raw in contexts.items():
            domain_code = self.normalize_domain_code(code)
            cache[domain_code] = DomainDescriptor(
                domain_code=domain_code,
                domain_name=str(raw.get("domain_name") or domain_code),
                domain_status=str(raw.get("domain_status") or "planned").strip().lower(),
                maturity_level=str(raw.get("maturity_level") or "initial").strip().lower(),
                schema_confidence=float(raw.get("schema_confidence") or 0.0),
                business_goal=str(raw.get("business_goal") or ""),
                main_entity=str(raw.get("main_entity") or ""),
                source_of_truth=str(raw.get("source_of_truth") or "unknown"),
                raw_context=dict(raw),
            )
        self._cache = cache

    def list_domains(self) -> list[DomainDescriptor]:
        return list(self._cache.values())

    def get_domain(self, domain_code: str | None) -> DomainDescriptor | None:
        normalized = self.normalize_domain_code(domain_code)
        if not normalized:
            return None
        return self._cache.get(normalized)

    def is_domain_enabled(self, domain: DomainDescriptor | None) -> bool:
        if domain is None:
            return False
        if domain.domain_code not in DOMINIOS_OPERATIVOS_CANONICOS:
            return False
        flags = dict(domain.raw_context.get("flags") or {})
        if flags.get("delegation_enabled") is False:
            return False
        env_key = f"IA_DEV_DOMAIN_{self._to_flag_code(domain.domain_code)}_ENABLED"
        raw = str(os.getenv(env_key, "1") or "1").strip().lower()
        return raw in {"1", "true", "yes", "on"}

    def resolve_domain(
        self,
        *,
        classification: dict[str, Any],
        planned_capability: dict[str, Any] | None = None,
        message: str = "",
    ) -> DomainDescriptor | None:
        capability_id = str((planned_capability or {}).get("capability_id") or "").strip().lower()
        descriptor = self._domain_from_capability_id(capability_id=capability_id)
        if descriptor is not None:
            return descriptor

        classification_domain = str(classification.get("domain") or "").strip().lower()
        descriptor = self.get_domain(classification_domain)
        if descriptor is not None:
            return descriptor

        normalized_message = str(message or "").strip().lower()
        for domain_code, tokens in self.DOMAIN_KEYWORDS.items():
            if any(token in normalized_message for token in tokens):
                found = self.get_domain(domain_code)
                if found is not None:
                    return found
        return None

    def resolve_domains_for_message(
        self,
        *,
        message: str,
        classification: dict[str, Any],
        planned_candidates: list[dict[str, Any]] | None = None,
    ) -> list[DomainDescriptor]:
        domains: list[DomainDescriptor] = []
        seen: set[str] = set()

        primary = self.resolve_domain(
            classification=classification,
            planned_capability=(planned_candidates or [{}])[0] if planned_candidates else None,
            message=message,
        )
        if primary is not None and self.is_domain_enabled(primary):
            domains.append(primary)
            seen.add(primary.domain_code)

        for candidate in planned_candidates or []:
            capability_id = str(candidate.get("capability_id") or "").strip().lower()
            descriptor = self._domain_from_capability_id(capability_id=capability_id)
            if descriptor is None:
                continue
            if descriptor.domain_code in seen or not self.is_domain_enabled(descriptor):
                continue
            domains.append(descriptor)
            seen.add(descriptor.domain_code)

        msg = str(message or "").lower()
        for domain_code, tokens in self.DOMAIN_KEYWORDS.items():
            if not any(token in msg for token in tokens):
                continue
            descriptor = self.get_domain(domain_code)
            if descriptor is None:
                continue
            if descriptor.domain_code in seen or not self.is_domain_enabled(descriptor):
                continue
            domains.append(descriptor)
            seen.add(descriptor.domain_code)

        return domains

    def sync_from_ai_dictionary(self) -> dict[str, Any]:
        sync_method = getattr(self.store, "sync_dominios_desde_ai_dictionary", None)
        if not callable(sync_method):
            return {"ok": False, "error": "sync_method_not_available"}
        result = sync_method()
        self.reload()
        return result

    def transition_domain_status(
        self,
        *,
        domain_code: str,
        to_status: str,
        actor: str = "system",
        reason: str = "",
        run_id: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        transition = getattr(self.store, "transition_estado_dominio", None)
        if not callable(transition):
            return {"ok": False, "error": "transition_method_not_available"}
        result = transition(
            codigo_dominio=domain_code,
            estado_destino=to_status,
            actor=actor,
            motivo=reason,
            run_id=run_id,
            trace_id=trace_id,
        )
        self.reload()
        return result

    @classmethod
    def normalize_domain_code(cls, domain_code: str | None) -> str:
        raw = normalizar_codigo_dominio(domain_code)
        if not raw:
            return ""
        return str(cls.DOMAIN_ALIASES.get(raw, raw))

    @staticmethod
    def _to_flag_code(domain_code: str) -> str:
        clean = "".join(ch if ch.isalnum() else "_" for ch in str(domain_code or "").upper())
        while "__" in clean:
            clean = clean.replace("__", "_")
        return clean.strip("_")

    def _domain_from_capability_id(self, *, capability_id: str) -> DomainDescriptor | None:
        capability = str(capability_id or "").strip().lower()
        if not capability:
            return None
        prefix = capability.split(".", 1)[0]
        normalized = self.normalize_domain_code(prefix)
        return self.get_domain(normalized)
