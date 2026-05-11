from __future__ import annotations

import os
import re
from collections import Counter, defaultdict
from typing import Any

from django.db import connections, transaction

from apps.ia_dev.application.delegation.domain_context_loader import DomainContextLoader


class AIDictionaryDeduplicationService:
    def __init__(
        self,
        *,
        db_alias: str | None = None,
        schema: str = "ai_dictionary",
        context_loader: DomainContextLoader | None = None,
    ) -> None:
        self.db_alias = str(db_alias or os.getenv("IA_DEV_DB_ALIAS", "default"))
        self.schema = str(schema or "ai_dictionary").strip() or "ai_dictionary"
        self.context_loader = context_loader or DomainContextLoader()

    def analyze(self, *, domain: str = "ausentismo", with_empleados: bool = False) -> dict[str, Any]:
        domains = [self._normalize_key(domain or "ausentismo") or "ausentismo"]
        if with_empleados and "empleados" not in domains:
            domains.append("empleados")

        rows = self._fetch_dictionary_rows(domains=domains)
        yaml_contexts = dict(self.context_loader.load_from_files() or {})
        legacy_duplicate_signals = self._analyze_legacy_duplicate_signals(
            rows=rows,
            yaml_contexts=yaml_contexts,
            domains=domains,
        )

        candidates: list[dict[str, Any]] = []
        candidates.extend(self._build_domain_candidates(rows=rows))
        candidates.extend(self._build_table_candidates(rows=rows))
        candidates.extend(self._build_field_candidates(rows=rows))
        candidates.extend(self._build_synonym_candidates(rows=rows))
        candidates.extend(self._build_rule_candidates(rows=rows))
        candidates.extend(self._build_relation_candidates(rows=rows))

        candidates.sort(
            key=lambda item: (
                str(item.get("entity_type") or ""),
                str(item.get("classification") or ""),
                str(((item.get("canonical_record") or {}).get("id")) or ""),
                str(((item.get("duplicate_record") or {}).get("id")) or ""),
            )
        )
        conflicts = [item for item in candidates if str(item.get("classification") or "") == "conflicting"]
        auto_merge_candidates = [item for item in candidates if bool(item.get("can_auto_merge"))]
        manual_review_required = [item for item in candidates if bool(item.get("requires_manual_review"))]
        recommended = self._recommended_actions(
            domains=domains,
            legacy_duplicate_signals=legacy_duplicate_signals,
            candidates=candidates,
        )
        return {
            "domains": domains,
            "legacy_duplicate_signals": legacy_duplicate_signals,
            "legacy_duplicate_signal_count": len(legacy_duplicate_signals),
            "legacy_duplicate_signal_breakdown": dict(
                Counter(str(item.get("cause") or "unknown") for item in legacy_duplicate_signals)
            ),
            "duplicates": candidates,
            "total_duplicates": len(candidates),
            "duplicates_by_type": dict(Counter(str(item.get("entity_type") or "unknown") for item in candidates)),
            "auto_merge_candidates": len(auto_merge_candidates),
            "manual_review_required": len(manual_review_required),
            "conflicts": len(conflicts),
            "conflict_items": conflicts,
            "recommended_sql_or_actions": recommended,
        }

    def apply_safe(self, *, analysis: dict[str, Any] | None = None, domain: str = "ausentismo", with_empleados: bool = False) -> dict[str, Any]:
        summary = dict(analysis or self.analyze(domain=domain, with_empleados=with_empleados))
        applied: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        for candidate in list(summary.get("duplicates") or []):
            if not bool(candidate.get("can_auto_merge")):
                skipped.append(candidate)
                continue
            applied.append(self._apply_safe_candidate(candidate=candidate))
        summary["applied_merges"] = applied
        summary["applied_merge_count"] = len(applied)
        summary["skipped_merge_count"] = len(skipped)
        return summary

    def _fetch_dictionary_rows(self, *, domains: list[str]) -> dict[str, list[dict[str, Any]]]:
        code_map = {
            "ausentismo": "AUSENTISMOS",
            "empleados": "EMPLEADOS",
        }
        wanted_codes = [code_map.get(item, item.upper()) for item in domains]
        placeholders = ", ".join(["%s"] * len(wanted_codes))

        with connections[self.db_alias].cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, codigo, nombre, descripcion, activo
                FROM {self.schema}.dd_dominios
                WHERE activo = 1
                  AND UPPER(COALESCE(codigo, '')) IN ({placeholders})
                ORDER BY id
                """,
                wanted_codes,
            )
            domains_rows = [
                {
                    "id": int(row[0]),
                    "codigo": str(row[1] or ""),
                    "nombre": str(row[2] or ""),
                    "descripcion": str(row[3] or ""),
                    "activo": int(row[4] or 0),
                    "domain_key": self._domain_key_from_code(row[1]),
                }
                for row in cursor.fetchall()
            ]
            domain_ids = [int(item["id"]) for item in domains_rows]
            if not domain_ids:
                return {
                    "domains": [],
                    "tables": [],
                    "fields": [],
                    "synonyms": [],
                    "rules": [],
                    "relations": [],
                }

            id_placeholders = ", ".join(["%s"] * len(domain_ids))
            cursor.execute(
                f"""
                SELECT t.id, t.dominio_id, d.codigo, t.schema_name, t.table_name, t.alias_negocio,
                       t.descripcion, t.clave_negocio, t.activo
                FROM {self.schema}.dd_tablas AS t
                JOIN {self.schema}.dd_dominios AS d ON d.id = t.dominio_id
                WHERE t.activo = 1
                  AND t.dominio_id IN ({id_placeholders})
                ORDER BY t.id
                """,
                domain_ids,
            )
            table_rows = [
                {
                    "id": int(row[0]),
                    "dominio_id": int(row[1]),
                    "domain_code": str(row[2] or ""),
                    "domain_key": self._domain_key_from_code(row[2]),
                    "schema_name": str(row[3] or ""),
                    "table_name": str(row[4] or ""),
                    "alias_negocio": str(row[5] or ""),
                    "descripcion": str(row[6] or ""),
                    "clave_negocio": str(row[7] or ""),
                    "activo": int(row[8] or 0),
                }
                for row in cursor.fetchall()
            ]
            table_ids = [int(item["id"]) for item in table_rows]
            table_map = {int(item["id"]): dict(item) for item in table_rows}
            fields_rows: list[dict[str, Any]] = []
            relation_rows: list[dict[str, Any]] = []
            if table_ids:
                table_placeholders = ", ".join(["%s"] * len(table_ids))
                cursor.execute(
                    f"""
                    SELECT c.id, c.tabla_id, d.codigo, t.schema_name, t.table_name,
                           c.campo_logico, c.column_name, c.tipo_campo, c.tipo_dato_tecnico,
                           c.definicion_negocio, c.es_clave, c.activo,
                           p.supports_filter, p.supports_group_by, p.supports_metric,
                           p.supports_dimension, p.is_date, p.is_identifier,
                           p.is_chart_dimension, p.is_chart_measure, p.active
                    FROM {self.schema}.dd_campos AS c
                    JOIN {self.schema}.dd_tablas AS t ON t.id = c.tabla_id
                    JOIN {self.schema}.dd_dominios AS d ON d.id = t.dominio_id
                    LEFT JOIN {self.schema}.ia_dev_capacidades_columna AS p
                      ON p.campo_id = c.id AND p.active = 1
                    WHERE c.activo = 1
                      AND c.tabla_id IN ({table_placeholders})
                    ORDER BY c.id
                    """,
                    table_ids,
                )
                fields_rows = [
                    {
                        "id": int(row[0]),
                        "tabla_id": int(row[1]),
                        "domain_code": str(row[2] or ""),
                        "domain_key": self._domain_key_from_code(row[2]),
                        "schema_name": str(row[3] or ""),
                        "table_name": str(row[4] or ""),
                        "campo_logico": str(row[5] or ""),
                        "column_name": str(row[6] or ""),
                        "tipo_campo": str(row[7] or ""),
                        "tipo_dato_tecnico": str(row[8] or ""),
                        "definicion_negocio": str(row[9] or ""),
                        "es_clave": int(row[10] or 0),
                        "activo": int(row[11] or 0),
                        "supports_filter": int(row[12] or 0),
                        "supports_group_by": int(row[13] or 0),
                        "supports_metric": int(row[14] or 0),
                        "supports_dimension": int(row[15] or 0),
                        "is_date": int(row[16] or 0),
                        "is_identifier": int(row[17] or 0),
                        "is_chart_dimension": int(row[18] or 0),
                        "is_chart_measure": int(row[19] or 0),
                        "profile_active": int(row[20] or 0),
                    }
                    for row in cursor.fetchall()
                ]
                cursor.execute(
                    f"""
                    SELECT r.id, r.tabla_origen_id, r.tabla_destino_id, r.nombre_relacion, r.join_sql,
                           r.cardinalidad, r.descripcion, r.activa
                    FROM {self.schema}.dd_relaciones AS r
                    WHERE r.activa = 1
                      AND (
                        r.tabla_origen_id IN ({table_placeholders})
                        OR r.tabla_destino_id IN ({table_placeholders})
                      )
                    ORDER BY r.id
                    """,
                    [*table_ids, *table_ids],
                )
                relation_rows = []
                for row in cursor.fetchall():
                    source = dict(table_map.get(int(row[1] or 0)) or {})
                    target = dict(table_map.get(int(row[2] or 0)) or {})
                    relation_rows.append(
                        {
                            "id": int(row[0]),
                            "tabla_origen_id": int(row[1]),
                            "tabla_destino_id": int(row[2]),
                            "nombre_relacion": str(row[3] or ""),
                            "join_sql": str(row[4] or ""),
                            "cardinalidad": str(row[5] or ""),
                            "descripcion": str(row[6] or ""),
                            "activa": int(row[7] or 0),
                            "source_domain_code": str(source.get("domain_code") or ""),
                            "target_domain_code": str(target.get("domain_code") or ""),
                            "source_domain_key": str(source.get("domain_key") or ""),
                            "target_domain_key": str(target.get("domain_key") or ""),
                            "source_table_name": str(source.get("table_name") or ""),
                            "target_table_name": str(target.get("table_name") or ""),
                            "source_schema_name": str(source.get("schema_name") or ""),
                            "target_schema_name": str(target.get("schema_name") or ""),
                        }
                    )

            cursor.execute(
                f"""
                SELECT s.id, s.termino, s.sinonimo, s.dominio_id, d.codigo, s.activo
                FROM {self.schema}.dd_sinonimos AS s
                JOIN {self.schema}.dd_dominios AS d ON d.id = s.dominio_id
                WHERE s.activo = 1
                  AND s.dominio_id IN ({id_placeholders})
                ORDER BY s.id
                """,
                domain_ids,
            )
            synonym_rows = [
                {
                    "id": int(row[0]),
                    "termino": str(row[1] or ""),
                    "sinonimo": str(row[2] or ""),
                    "dominio_id": int(row[3] or 0),
                    "domain_code": str(row[4] or ""),
                    "domain_key": self._domain_key_from_code(row[4]),
                    "activo": int(row[5] or 0),
                }
                for row in cursor.fetchall()
            ]
            cursor.execute(
                f"""
                SELECT r.id, r.codigo, r.nombre, r.dominio_id, d.codigo, r.resultado_funcional,
                       r.prioridad, r.activo
                FROM {self.schema}.dd_reglas AS r
                JOIN {self.schema}.dd_dominios AS d ON d.id = r.dominio_id
                WHERE r.activo = 1
                  AND r.dominio_id IN ({id_placeholders})
                ORDER BY r.id
                """,
                domain_ids,
            )
            rule_rows = [
                {
                    "id": int(row[0]),
                    "codigo": str(row[1] or ""),
                    "nombre": str(row[2] or ""),
                    "dominio_id": int(row[3] or 0),
                    "domain_code": str(row[4] or ""),
                    "domain_key": self._domain_key_from_code(row[4]),
                    "resultado_funcional": str(row[5] or ""),
                    "prioridad": int(row[6] or 0),
                    "activo": int(row[7] or 0),
                }
                for row in cursor.fetchall()
            ]
        return {
            "domains": domains_rows,
            "tables": table_rows,
            "fields": fields_rows,
            "synonyms": synonym_rows,
            "rules": rule_rows,
            "relations": relation_rows,
        }

    def _build_domain_candidates(self, *, rows: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
        groups = self._group_rows(
            rows=list(rows.get("domains") or []),
            key_builder=lambda item: (
                self._normalize_key(item.get("codigo")),
                self._normalize_key(item.get("nombre")),
            ),
        )
        return self._rows_to_candidates(entity_type="domain", groups=groups)

    def _build_table_candidates(self, *, rows: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
        groups = self._group_rows(
            rows=list(rows.get("tables") or []),
            key_builder=lambda item: (
                self._normalize_key(item.get("schema_name")),
                self._normalize_key(item.get("table_name")),
            ),
        )
        return self._rows_to_candidates(entity_type="table", groups=groups)

    def _build_field_candidates(self, *, rows: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
        groups = self._group_rows(
            rows=list(rows.get("fields") or []),
            key_builder=lambda item: (
                self._normalize_key(item.get("schema_name")),
                self._normalize_key(item.get("table_name")),
                self._normalize_key(item.get("column_name")),
            ),
        )
        return self._rows_to_candidates(entity_type="field", groups=groups)

    def _build_synonym_candidates(self, *, rows: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
        groups = self._group_rows(
            rows=list(rows.get("synonyms") or []),
            key_builder=lambda item: (
                self._normalize_key(item.get("termino")),
                self._normalize_key(item.get("sinonimo")),
            ),
        )
        return self._rows_to_candidates(entity_type="synonym", groups=groups)

    def _build_rule_candidates(self, *, rows: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
        groups = self._group_rows(
            rows=list(rows.get("rules") or []),
            key_builder=lambda item: self._normalize_key(item.get("codigo")) or self._normalize_key(item.get("nombre")),
        )
        return self._rows_to_candidates(entity_type="rule", groups=groups)

    def _build_relation_candidates(self, *, rows: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
        groups = self._group_rows(
            rows=list(rows.get("relations") or []),
            key_builder=lambda item: self._normalize_relation(item.get("join_sql")) or self._normalize_key(item.get("nombre_relacion")),
        )
        return self._rows_to_candidates(entity_type="relation", groups=groups)

    def _rows_to_candidates(
        self,
        *,
        entity_type: str,
        groups: dict[Any, list[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for group_rows in groups.values():
            if len(group_rows) <= 1:
                continue
            canonical = self._select_canonical_record(rows=group_rows)
            classification = self._classify_group(entity_type=entity_type, rows=group_rows)
            reason = self._conflict_reason(entity_type=entity_type, classification=classification, rows=group_rows)
            action = self._recommended_action(entity_type=entity_type, classification=classification, rows=group_rows)
            can_auto_merge = self._can_auto_merge(entity_type=entity_type, classification=classification, rows=group_rows)
            for duplicate in group_rows:
                if int(duplicate.get("id") or 0) == int(canonical.get("id") or 0):
                    continue
                candidates.append(
                    {
                        "entity_type": entity_type,
                        "classification": classification,
                        "domains": sorted(
                            {
                                str(item.get("domain_key") or "")
                                for item in group_rows
                                if str(item.get("domain_key") or "")
                            }
                        ),
                        "canonical_record": self._record_brief(canonical),
                        "duplicate_record": self._record_brief(duplicate),
                        "conflict_reason": reason,
                        "recommended_action": action,
                        "can_auto_merge": bool(can_auto_merge),
                        "requires_manual_review": not bool(can_auto_merge),
                    }
                )
        return candidates

    @staticmethod
    def _group_rows(*, rows: list[dict[str, Any]], key_builder) -> dict[Any, list[dict[str, Any]]]:
        grouped: dict[Any, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            key = key_builder(row)
            if isinstance(key, tuple):
                if not any(str(item or "").strip() for item in key):
                    continue
            elif not str(key or "").strip():
                continue
            grouped[key].append(dict(row))
        return grouped

    def _select_canonical_record(self, *, rows: list[dict[str, Any]]) -> dict[str, Any]:
        return dict(
            sorted(
                rows,
                key=lambda item: (
                    0 if str(item.get("domain_key") or "") == "empleados" else 1,
                    int(item.get("id") or 0),
                ),
            )[0]
        )

    def _classify_group(self, *, entity_type: str, rows: list[dict[str, Any]]) -> str:
        if entity_type == "domain":
            signatures = {
                (
                    self._normalize_key(item.get("codigo")),
                    self._normalize_key(item.get("nombre")),
                )
                for item in rows
            }
            return "equivalent" if len(signatures) == 1 else "conflicting"
        if entity_type == "table":
            signatures = {
                (
                    self._normalize_key(item.get("clave_negocio")),
                    self._normalize_key(item.get("schema_name")),
                    self._normalize_key(item.get("table_name")),
                )
                for item in rows
            }
            return "equivalent" if len(signatures) == 1 else "conflicting"
        if entity_type == "field":
            if self._fields_are_multiple_semantic_views(rows=rows):
                return "equivalent"
            tipo_campo = {
                self._normalize_key(item.get("tipo_campo"))
                for item in rows
                if self._normalize_key(item.get("tipo_campo"))
            }
            tipo_dato = {
                self._normalize_key(item.get("tipo_dato_tecnico"))
                for item in rows
                if self._normalize_key(item.get("tipo_dato_tecnico"))
            }
            supports_metric = {int(item.get("supports_metric") or 0) for item in rows}
            is_identifier = {int(item.get("is_identifier") or 0) for item in rows}
            is_date = {int(item.get("is_date") or 0) for item in rows}
            if len(tipo_campo) > 1 or len(tipo_dato) > 1:
                return "conflicting"
            if 1 in supports_metric and (1 in is_identifier or 1 in is_date):
                return "conflicting"
            return "equivalent"
        if entity_type == "synonym":
            return "equivalent"
        if entity_type == "rule":
            signatures = {
                (
                    self._normalize_key(item.get("nombre")),
                    self._normalize_text(item.get("resultado_funcional")),
                )
                for item in rows
            }
            return "equivalent" if len(signatures) == 1 else "conflicting"
        if entity_type == "relation":
            signatures = {
                (
                    self._normalize_relation(item.get("join_sql")),
                    self._normalize_key(item.get("cardinalidad")),
                )
                for item in rows
            }
            return "equivalent" if len(signatures) == 1 else "conflicting"
        return "conflicting"

    def _conflict_reason(self, *, entity_type: str, classification: str, rows: list[dict[str, Any]]) -> str:
        if classification == "equivalent":
            if entity_type == "field":
                if self._fields_are_multiple_semantic_views(rows=rows):
                    return "multiple_semantic_views_over_same_physical_column"
                return "shared_physical_column_across_metadata_scopes"
            if entity_type == "table":
                return "shared_physical_table_across_domains"
            return "semantically_equivalent_duplicate"
        if entity_type == "field":
            return "same_physical_column_declared_with_incompatible_semantics"
        if entity_type == "table":
            return "same_physical_table_declared_with_conflicting_business_contract"
        if entity_type == "rule":
            return "same_rule_code_with_different_functional_outcome"
        if entity_type == "relation":
            return "same_relation_declared_with_different_join_or_cardinality"
        return "duplicate_metadata_requires_reconciliation"

    def _recommended_action(self, *, entity_type: str, classification: str, rows: list[dict[str, Any]]) -> str:
        if classification == "equivalent" and self._can_auto_merge(entity_type=entity_type, classification=classification, rows=rows):
            return f"safe_merge_{entity_type}_and_deactivate_duplicate"
        if classification == "equivalent":
            return f"keep_{entity_type}_scoped_and_exclude_from_conflict_audit"
        return f"manual_reconcile_{entity_type}_before_merge"

    def _can_auto_merge(self, *, entity_type: str, classification: str, rows: list[dict[str, Any]]) -> bool:
        if classification != "equivalent":
            return False
        if entity_type == "field":
            table_ids = {int(item.get("tabla_id") or 0) for item in rows}
            return len(table_ids) == 1
        if entity_type == "table":
            domain_ids = {int(item.get("dominio_id") or 0) for item in rows}
            return len(domain_ids) == 1
        if entity_type == "synonym":
            domain_ids = {int(item.get("dominio_id") or 0) for item in rows}
            return len(domain_ids) == 1
        if entity_type == "rule":
            domain_ids = {int(item.get("dominio_id") or 0) for item in rows}
            return len(domain_ids) == 1
        if entity_type == "relation":
            origins = {int(item.get("tabla_origen_id") or 0) for item in rows}
            destinations = {int(item.get("tabla_destino_id") or 0) for item in rows}
            return len(origins) == 1 and len(destinations) == 1
        if entity_type == "domain":
            return True
        return False

    def _apply_safe_candidate(self, *, candidate: dict[str, Any]) -> dict[str, Any]:
        entity_type = str(candidate.get("entity_type") or "")
        canonical = dict(candidate.get("canonical_record") or {})
        duplicate = dict(candidate.get("duplicate_record") or {})
        canonical_id = int(canonical.get("id") or 0)
        duplicate_id = int(duplicate.get("id") or 0)
        if canonical_id <= 0 or duplicate_id <= 0:
            return {"entity_type": entity_type, "status": "skipped", "reason": "invalid_candidate"}

        with transaction.atomic(using=self.db_alias):
            with connections[self.db_alias].cursor() as cursor:
                if entity_type == "domain":
                    for table_name, column_name in (
                        ("dd_tablas", "dominio_id"),
                        ("dd_sinonimos", "dominio_id"),
                        ("dd_reglas", "dominio_id"),
                    ):
                        cursor.execute(
                            f"UPDATE {self.schema}.{table_name} SET {column_name} = %s WHERE {column_name} = %s",
                            [canonical_id, duplicate_id],
                        )
                    cursor.execute(
                        f"UPDATE {self.schema}.dd_dominios SET activo = 0 WHERE id = %s",
                        [duplicate_id],
                    )
                elif entity_type == "table":
                    cursor.execute(
                        f"UPDATE {self.schema}.dd_campos SET tabla_id = %s WHERE tabla_id = %s",
                        [canonical_id, duplicate_id],
                    )
                    for column_name in ("tabla_origen_id", "tabla_destino_id"):
                        cursor.execute(
                            f"UPDATE {self.schema}.dd_relaciones SET {column_name} = %s WHERE {column_name} = %s",
                            [canonical_id, duplicate_id],
                        )
                    cursor.execute(
                        f"UPDATE {self.schema}.dd_tablas SET activo = 0 WHERE id = %s",
                        [duplicate_id],
                    )
                elif entity_type == "field":
                    cursor.execute(
                        f"UPDATE {self.schema}.ia_dev_capacidades_columna SET campo_id = %s WHERE campo_id = %s",
                        [canonical_id, duplicate_id],
                    )
                    cursor.execute(
                        f"UPDATE {self.schema}.dd_campos SET activo = 0 WHERE id = %s",
                        [duplicate_id],
                    )
                elif entity_type == "synonym":
                    cursor.execute(
                        f"UPDATE {self.schema}.dd_sinonimos SET activo = 0 WHERE id = %s",
                        [duplicate_id],
                    )
                elif entity_type == "rule":
                    cursor.execute(
                        f"UPDATE {self.schema}.dd_reglas SET activo = 0 WHERE id = %s",
                        [duplicate_id],
                    )
                elif entity_type == "relation":
                    cursor.execute(
                        f"UPDATE {self.schema}.dd_relaciones SET activa = 0 WHERE id = %s",
                        [duplicate_id],
                    )
                else:
                    return {"entity_type": entity_type, "status": "skipped", "reason": "unsupported_entity"}
        return {
            "entity_type": entity_type,
            "status": "applied",
            "canonical_id": canonical_id,
            "duplicate_id": duplicate_id,
        }

    def _recommended_actions(
        self,
        *,
        domains: list[str],
        legacy_duplicate_signals: list[dict[str, Any]],
        candidates: list[dict[str, Any]],
    ) -> list[str]:
        actions: list[str] = []
        if legacy_duplicate_signals:
            actions.append(
                "Corregir el auditor para contar por registro y por scope compuesto (tabla+campo), evitando falsos positivos self-duplicate."
            )
        if any(str(item.get("entity_type") or "") == "table" for item in candidates):
            actions.append(
                "Mantener tablas fisicas compartidas por dominio como equivalentes scoped; no mergear cross-domain sin redisenar scoping runtime."
            )
        if any(str(item.get("classification") or "") == "conflicting" for item in candidates):
            actions.append(
                "Resolver manualmente conflictos semanticos antes de desactivar registros en ai_dictionary."
            )
        if not actions:
            actions.append(
                "Sin acciones de DB recomendadas: el inventario activo no presenta duplicados conflictivos ni auto-mergeables."
            )
        return actions

    def _analyze_legacy_duplicate_signals(
        self,
        *,
        rows: dict[str, list[dict[str, Any]]],
        yaml_contexts: dict[str, Any],
        domains: list[str],
    ) -> list[dict[str, Any]]:
        table_index = {
            int(item.get("id") or 0): str(item.get("table_name") or "")
            for item in list(rows.get("tables") or [])
        }
        per_domain_fields: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in list(rows.get("fields") or []):
            per_domain_fields[str(item.get("domain_key") or "")].append(item)

        signals: list[dict[str, Any]] = []
        for domain in domains:
            contributions: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for field in list(per_domain_fields.get(domain) or []):
                field_id = int(field.get("id") or 0)
                table_name = str(field.get("table_name") or table_index.get(int(field.get("tabla_id") or 0)) or "")
                contributions["dd_campos"].append(
                    {
                        "record_ref": f"dd_campos:{field_id}",
                        "value": self._normalize_key(field.get("column_name")),
                        "table_name": table_name,
                    }
                )
                contributions["dd_campos"].append(
                    {
                        "record_ref": f"dd_campos:{field_id}",
                        "value": self._normalize_key(field.get("campo_logico")),
                        "table_name": table_name,
                    }
                )
            yaml_context = dict(yaml_contexts.get(domain) or {})
            for index, column in enumerate(list(yaml_context.get("columns") or [])):
                if not isinstance(column, dict):
                    continue
                table_name = str(column.get("table_name") or "")
                contributions["yaml_columns"].append(
                    {
                        "record_ref": f"yaml_columns:{index}",
                        "value": self._normalize_key(column.get("column_name")),
                        "table_name": table_name,
                    }
                )
                contributions["yaml_columns"].append(
                    {
                        "record_ref": f"yaml_columns:{index}",
                        "value": self._normalize_key(column.get("nombre_columna_logico")),
                        "table_name": table_name,
                    }
                )

            for source, items in contributions.items():
                counter: Counter[str] = Counter(item["value"] for item in items if item.get("value"))
                for value, count in counter.items():
                    if count <= 1:
                        continue
                    matching = [item for item in items if item.get("value") == value]
                    unique_records = {str(item.get("record_ref") or "") for item in matching}
                    unique_tables = {self._normalize_key(item.get("table_name")) for item in matching if self._normalize_key(item.get("table_name"))}
                    cause = "self_duplicate_signal" if len(unique_records) == 1 else "multi_record_same_token"
                    signals.append(
                        {
                            "domain": domain,
                            "source": source,
                            "value": value,
                            "count": int(count),
                            "unique_records": len(unique_records),
                            "unique_tables": len(unique_tables),
                            "cause": cause,
                        }
                    )
        signals.sort(key=lambda item: (str(item.get("domain") or ""), str(item.get("source") or ""), str(item.get("value") or "")))
        return signals

    @staticmethod
    def _record_brief(record: dict[str, Any]) -> dict[str, Any]:
        keys = (
            "id",
            "domain_code",
            "domain_key",
            "schema_name",
            "table_name",
            "campo_logico",
            "column_name",
            "codigo",
            "nombre",
            "termino",
            "sinonimo",
            "nombre_relacion",
            "join_sql",
        )
        return {key: record[key] for key in keys if key in record}

    @staticmethod
    def _domain_key_from_code(value: Any) -> str:
        token = str(value or "").strip().upper()
        if "AUSENT" in token:
            return "ausentismo"
        if "EMPLEAD" in token:
            return "empleados"
        return str(value or "").strip().lower()

    @staticmethod
    def _normalize_key(value: Any) -> str:
        return str(value or "").strip().lower().replace(" ", "_")

    @staticmethod
    def _normalize_relation(value: Any) -> str:
        return " ".join(str(value or "").strip().lower().split())

    @staticmethod
    def _normalize_text(value: Any) -> str:
        return " ".join(str(value or "").strip().lower().split())

    @classmethod
    def _fields_are_multiple_semantic_views(cls, *, rows: list[dict[str, Any]]) -> bool:
        if len(rows) <= 1:
            return False
        schema_names = {cls._normalize_key(item.get("schema_name")) for item in rows if cls._normalize_key(item.get("schema_name"))}
        table_names = {cls._normalize_key(item.get("table_name")) for item in rows if cls._normalize_key(item.get("table_name"))}
        column_names = {cls._normalize_key(item.get("column_name")) for item in rows if cls._normalize_key(item.get("column_name"))}
        if len(schema_names) != 1 or len(table_names) != 1 or len(column_names) != 1:
            return False
        semantic_views: set[tuple[str, str, str]] = set()
        for item in rows:
            tags = cls._parse_semantic_tags(str(item.get("definicion_negocio") or ""))
            json_path = str(tags.get("json_path") or "").strip()
            semantic_type = str(tags.get("semantic_type") or "").strip()
            semantic_view = str(tags.get("semantic_view") or "").strip()
            if not any((json_path, semantic_type, semantic_view)):
                continue
            semantic_views.add((json_path, semantic_type, semantic_view))
        return len(semantic_views) > 1

    @staticmethod
    def _parse_semantic_tags(text: str) -> dict[str, str]:
        payload: dict[str, str] = {}
        for key, value in re.findall(r"\[([a-zA-Z0-9_]+)=(.*?)\](?=\[|$)", str(text or "")):
            clean_key = str(key or "").strip().lower()
            clean_value = str(value or "").strip()
            if clean_key and clean_value:
                payload[clean_key] = clean_value
        return payload
