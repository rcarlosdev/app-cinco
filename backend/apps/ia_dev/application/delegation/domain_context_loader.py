from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from apps.ia_dev.services.sql_store import IADevSqlStore


class DomainContextLoader:
    STRUCTURAL_YAML_KEYS = {
        "tables": ("tablas_asociadas", "tables"),
        "columns": ("columnas_clave", "columns"),
        "relationships": ("joins_conocidos", "relationships"),
        "capabilities": ("capacidades", "capabilities"),
        "supported_filters": ("filtros_soportados",),
        "supported_group_by": ("group_by_soportados",),
        "supported_metrics": ("metricas_soportadas",),
    }

    def __init__(
        self,
        *,
        registry_dir: str | Path | None = None,
        store: IADevSqlStore | None = None,
    ):
        self.domains_dir = Path(__file__).resolve().parents[2] / "domains"
        if registry_dir is None:
            registry_dir = self.domains_dir / "registry"
        self.registry_dir = Path(registry_dir)
        self.store = store or IADevSqlStore()

    def load_all(self) -> dict[str, dict[str, Any]]:
        company_context = self._load_company_context()
        file_contexts = self.load_from_files()
        db_contexts = self.load_from_db()
        merged: dict[str, dict[str, Any]] = {}
        all_codes = set(file_contexts.keys()) | set(db_contexts.keys())
        for code in sorted(all_codes):
            merged_payload = self._merge_context(
                file_context=file_contexts.get(code),
                db_context=db_contexts.get(code),
            )
            if company_context:
                merged_payload["company_context"] = dict(company_context)
            merged[code] = merged_payload
        return merged

    def _load_company_context(self) -> dict[str, Any]:
        getter = getattr(self.store, "get_contexto_compania", None)
        if not callable(getter):
            return {}
        company_code = str(os.getenv("IA_DEV_COMPANY_CODE", "CINCO") or "CINCO").strip() or "CINCO"
        try:
            payload = getter(codigo_compania=company_code)
        except Exception:
            return {}
        return dict(payload or {}) if isinstance(payload, dict) else {}

    def load_from_files(self) -> dict[str, dict[str, Any]]:
        contexts: dict[str, dict[str, Any]] = {}
        for path in self._iter_domain_definition_paths():
            try:
                raw = yaml.safe_load(path.read_text(encoding="utf-8", errors="ignore")) or {}
            except Exception:
                continue
            if not isinstance(raw, dict):
                continue
            normalized = self._normalize_file_context(raw=raw, source_path=path)
            code = str(normalized.get("domain_code") or "").strip().lower()
            if not code:
                continue
            complementos = self._load_archivos_complementarios(domain_code=code)
            if complementos:
                normalized = self._merge_file_companions(
                    base_context=normalized,
                    companion_payloads=complementos,
                )
            if code in contexts:
                contexts[code] = self._merge_context(
                    file_context=contexts.get(code),
                    db_context=normalized,
                )
                contexts[code]["source_of_truth"] = "file"
                contexts[code]["source_ref"] = str(path)
            else:
                contexts[code] = normalized
        return contexts

    def _iter_domain_definition_paths(self) -> list[Path]:
        paths: list[Path] = []
        if self.registry_dir.exists():
            paths.extend(sorted(self.registry_dir.glob("*.domain.yaml")))
        if self.domains_dir.exists():
            for domain_dir in sorted(self.domains_dir.iterdir()):
                if not domain_dir.is_dir():
                    continue
                if domain_dir.name.startswith("__") or domain_dir.name == "registry":
                    continue
                domain_file = domain_dir / "dominio.yaml"
                if domain_file.exists():
                    paths.append(domain_file)
        return paths

    def load_from_db(self) -> dict[str, dict[str, Any]]:
        contexts: dict[str, dict[str, Any]] = {}
        list_dominios = getattr(self.store, "list_dominios", None)
        if not callable(list_dominios):
            return contexts
        try:
            rows = list_dominios(limit=300)
        except Exception:
            return contexts
        for row in rows:
            if not isinstance(row, dict):
                continue
            code = str(row.get("codigo_dominio") or row.get("domain_code") or "").strip().lower()
            if not code:
                continue
            domain_id = int(row.get("id") or 0)
            tables = self._load_domain_tables(domain_id=domain_id)
            columns = self._load_domain_columns(domain_id=domain_id)
            relationships = self._load_domain_relationships(domain_id=domain_id)
            capabilities = self._load_domain_capabilities(domain_id=domain_id)
            skills = self._load_domain_skills(domain_id=domain_id)
            contexts[code] = {
                "domain_code": code,
                "domain_name": str(row.get("nombre_dominio") or code),
                "business_goal": str(row.get("objetivo_negocio") or ""),
                "main_entity": str(row.get("entidad_principal") or ""),
                "domain_status": str(row.get("estado_dominio") or row.get("status") or "planned").strip().lower(),
                "maturity_level": str(row.get("nivel_madurez") or "initial").strip().lower(),
                "schema_confidence": float(row.get("nivel_confianza_esquema") or 0.0),
                "flags": dict(row.get("flags_json") or {}),
                "source_of_truth": "db",
                "source_ref": str(row.get("source_ref") or ""),
                "tables": tables,
                "columns": columns,
                "relationships": relationships,
                "capabilities": capabilities,
                "skills": skills,
            }
        return contexts

    @staticmethod
    def _normalize_file_context(*, raw: dict[str, Any], source_path: Path) -> dict[str, Any]:
        code = str(raw.get("dominio") or raw.get("domain_code") or source_path.stem.split(".", 1)[0]).strip().lower()
        yaml_structural_inventory = DomainContextLoader._extract_yaml_structural_inventory(raw=raw)
        yaml_fields_ignored = sorted(
            key for key, value in yaml_structural_inventory.items() if DomainContextLoader._has_structural_payload(value)
        )
        return {
            "domain_code": code,
            "domain_name": str(raw.get("nombre_dominio") or raw.get("domain_name") or code),
            "business_goal": str(raw.get("objetivo_negocio") or raw.get("business_goal") or ""),
            "main_entity": str(raw.get("entidad_principal") or raw.get("main_entity") or ""),
            "domain_status": str(raw.get("estado_dominio") or raw.get("domain_status") or "planned").strip().lower(),
            "maturity_level": str(raw.get("nivel_madurez") or raw.get("maturity_level") or "initial").strip().lower(),
            "schema_confidence": float(raw.get("nivel_confianza_esquema") or raw.get("schema_confidence") or 0.0),
            "flags": dict(raw.get("flags") or {}),
            "source_of_truth": "file",
            "source_ref": str(source_path),
            "skills": list(raw.get("skills_metadata") or raw.get("skills") or []),
            "sensitividades": list(raw.get("sensitividades") or []),
            "contexto_agente": dict(raw.get("contexto_agente") or {}),
            "reglas_negocio": list(raw.get("reglas_negocio") or []),
            "ejemplos_consulta": list(raw.get("ejemplos_consulta") or []),
            "vocabulario_negocio": list(raw.get("vocabulario_negocio") or []),
            "tablas_prioritarias": list(raw.get("tablas_prioritarias") or []),
            "columnas_prioritarias": list(raw.get("columnas_prioritarias") or []),
            "legacy_capabilities": list(raw.get("capacidades") or raw.get("capabilities") or []),
            "yaml_role": "narrative_only",
            "yaml_structural_inventory": yaml_structural_inventory,
            "yaml_fields_ignored": yaml_fields_ignored,
            "yaml_fields_removed": list(yaml_fields_ignored),
            "yaml_structural_ignored": bool(yaml_fields_ignored),
        }

    @classmethod
    def _extract_yaml_structural_inventory(cls, *, raw: dict[str, Any]) -> dict[str, Any]:
        inventory: dict[str, Any] = {}
        for canonical_key, aliases in cls.STRUCTURAL_YAML_KEYS.items():
            value: Any = []
            for alias in aliases:
                candidate = raw.get(alias)
                if candidate not in (None, "", [], {}):
                    value = candidate
                    break
            if isinstance(value, list):
                inventory[canonical_key] = list(value)
            elif isinstance(value, dict):
                inventory[canonical_key] = dict(value)
            elif value in (None, ""):
                inventory[canonical_key] = []
            else:
                inventory[canonical_key] = [value]
        return inventory

    @staticmethod
    def _has_structural_payload(value: Any) -> bool:
        if isinstance(value, dict):
            return bool(value)
        if isinstance(value, list):
            return any(item not in (None, "", [], {}) for item in value)
        return value not in (None, "", [], {})

    def _load_archivos_complementarios(self, *, domain_code: str) -> dict[str, Any]:
        complementos: dict[str, Any] = {}
        sufijos = ("contexto", "reglas", "ejemplos")
        for sufijo in sufijos:
            for path in self._resolve_companion_candidate_paths(domain_code=domain_code, sufijo=sufijo):
                if not path.exists():
                    continue
                try:
                    raw = yaml.safe_load(path.read_text(encoding="utf-8", errors="ignore")) or {}
                except Exception:
                    continue
                if not isinstance(raw, dict):
                    continue
                complementos[sufijo] = raw
        return complementos

    def _resolve_companion_candidate_paths(self, *, domain_code: str, sufijo: str) -> list[Path]:
        domain_dir = self.domains_dir / domain_code
        return [
            domain_dir / f"{sufijo}.yaml",
            self.registry_dir / f"{domain_code}.{sufijo}.yaml",
        ]

    @staticmethod
    def _merge_file_companions(
        *,
        base_context: dict[str, Any],
        companion_payloads: dict[str, Any],
    ) -> dict[str, Any]:
        merged = dict(base_context or {})
        contexto = dict(companion_payloads.get("contexto") or {})
        reglas = dict(companion_payloads.get("reglas") or {})
        ejemplos = dict(companion_payloads.get("ejemplos") or {})

        if contexto:
            merged["contexto_agente"] = {
                **dict(merged.get("contexto_agente") or {}),
                **dict(contexto.get("contexto_agente") or contexto),
            }
            merged["vocabulario_negocio"] = list(
                dict.fromkeys(
                    [
                        *list(merged.get("vocabulario_negocio") or []),
                        *list(contexto.get("vocabulario_negocio") or []),
                    ]
                )
            )
            merged["tablas_prioritarias"] = list(
                dict.fromkeys(
                    [
                        *list(merged.get("tablas_prioritarias") or []),
                        *list(contexto.get("tablas_prioritarias") or []),
                    ]
                )
            )
            merged["columnas_prioritarias"] = list(
                dict.fromkeys(
                    [
                        *list(merged.get("columnas_prioritarias") or []),
                        *list(contexto.get("columnas_prioritarias") or []),
                    ]
                )
            )

        if reglas:
            merged["reglas_negocio"] = list(merged.get("reglas_negocio") or []) + list(reglas.get("reglas_negocio") or [])

        if ejemplos:
            merged["ejemplos_consulta"] = list(merged.get("ejemplos_consulta") or []) + list(
                ejemplos.get("ejemplos_consulta") or []
            )

        return merged

    @staticmethod
    def _merge_context(
        *,
        file_context: dict[str, Any] | None,
        db_context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        file_payload = dict(file_context or {})
        db_payload = dict(db_context or {})
        if not file_payload:
            return db_payload
        if not db_payload:
            return file_payload

        merged = dict(file_payload)
        for key in (
            "domain_name",
            "business_goal",
            "main_entity",
            "domain_status",
            "maturity_level",
            "schema_confidence",
        ):
            if db_payload.get(key) not in (None, ""):
                merged[key] = db_payload.get(key)
        merged["flags"] = {**dict(file_payload.get("flags") or {}), **dict(db_payload.get("flags") or {})}
        if db_payload.get("tables"):
            merged["tables"] = list(db_payload.get("tables") or [])
        if db_payload.get("columns"):
            merged["columns"] = list(db_payload.get("columns") or [])
        if db_payload.get("relationships"):
            merged["relationships"] = list(db_payload.get("relationships") or [])
        if db_payload.get("capabilities"):
            merged["capabilities"] = list(db_payload.get("capabilities") or [])
        if db_payload.get("skills"):
            merged["skills"] = list(db_payload.get("skills") or [])
        merged["source_of_truth"] = "hybrid"
        merged["source_ref"] = str(db_payload.get("source_ref") or file_payload.get("source_ref") or "")
        return merged

    def _load_domain_tables(self, *, domain_id: int) -> list[dict[str, Any]]:
        if domain_id <= 0:
            return []
        getter = getattr(self.store, "list_tablas_dominio", None)
        if not callable(getter):
            return []
        try:
            return list(getter(dominio_id=domain_id, status="active", limit=200))
        except Exception:
            return []

    def _load_domain_columns(self, *, domain_id: int) -> list[dict[str, Any]]:
        if domain_id <= 0:
            return []
        getter = getattr(self.store, "list_columnas_dominio", None)
        if not callable(getter):
            return []
        try:
            return list(getter(dominio_id=domain_id, status="active", limit=1000))
        except Exception:
            return []

    def _load_domain_relationships(self, *, domain_id: int) -> list[dict[str, Any]]:
        if domain_id <= 0:
            return []
        getter = getattr(self.store, "list_relaciones_dominio", None)
        if not callable(getter):
            return []
        try:
            return list(getter(dominio_id=domain_id, status="active", limit=1000))
        except Exception:
            return []

    def _load_domain_capabilities(self, *, domain_id: int) -> list[dict[str, Any]]:
        if domain_id <= 0:
            return []
        getter = getattr(self.store, "list_capacidades_dominio", None)
        if not callable(getter):
            return []
        try:
            return list(getter(dominio_id=domain_id, status="active", limit=200))
        except Exception:
            return []

    def _load_domain_skills(self, *, domain_id: int) -> list[dict[str, Any]]:
        if domain_id <= 0:
            return []
        getter = getattr(self.store, "list_skills_dominio", None)
        if not callable(getter):
            return []
        try:
            return list(getter(dominio_id=domain_id, status="active", limit=200))
        except Exception:
            return []
