from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


RUNTIME_DOMAIN_CODE = "inventario_logistica"
DEFAULT_AGENT_PATH = Path(__file__).with_name("inventario_materiales_agent_hybrid.yaml")


def _read_yaml_text(path: Path) -> str:
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")


def _yaml_path(path: str | None = None) -> Path:
    return Path(path) if path else DEFAULT_AGENT_PATH


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value or {}) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value or []) if isinstance(value, list) else []


def get_runtime_domain_code(config: dict[str, Any] | None = None) -> str:
    return RUNTIME_DOMAIN_CODE


def get_business_domain_code(config: dict[str, Any]) -> str:
    business_domain = _as_dict(config.get("business_domain"))
    return str(business_domain.get("code") or "inventario_materiales").strip().lower()


def load_inventory_agent_yaml(path: str | None = None) -> dict[str, Any]:
    yaml_path = _yaml_path(path)
    raw = yaml.safe_load(_read_yaml_text(yaml_path)) or {}
    if not isinstance(raw, dict):
        raise ValueError("El YAML del agente de inventario debe cargar un objeto raiz.")
    raw.setdefault("_runtime_domain_code", get_runtime_domain_code(raw))
    raw.setdefault("_yaml_path", str(yaml_path))
    return raw


def get_tables_for_dictionary(config: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    domain_code = get_runtime_domain_code(config)
    for table_name, table in _as_dict(config.get("tables")).items():
        table_data = _as_dict(table)
        rows.append(
            {
                "domain_code": domain_code,
                "yaml_business_domain_code": get_business_domain_code(config),
                "schema_name": str(table_data.get("schema_name") or ""),
                "table_name": str(table_name),
                "business_name": str(table_data.get("business_name") or ""),
                "description": str(table_data.get("description") or ""),
                "primary_role": str(table_data.get("primary_role") or ""),
                "material_family": str(table_data.get("material_family") or ""),
                "movement_type": str(table_data.get("movement_type") or ""),
                "sync_to_dd_tablas": bool(table_data.get("sync_to_dd_tablas", False)),
            }
        )
    return rows


def get_fields_for_dictionary(config: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for table_name, table in _as_dict(config.get("tables")).items():
        table_data = _as_dict(table)
        for column_name, column in _as_dict(table_data.get("columns")).items():
            column_data = _as_dict(column)
            rows.append(
                {
                    "domain_code": get_runtime_domain_code(config),
                    "schema_name": str(table_data.get("schema_name") or ""),
                    "table_name": str(table_name),
                    "column_name": str(column_name),
                    "data_type": str(column_data.get("data_type") or ""),
                    "semantic_role": str(column_data.get("semantic_role") or ""),
                    "business_concepts": _as_list(column_data.get("business_concepts")),
                    "allowed_operations": _as_list(column_data.get("allowed_operations")),
                    "synonyms": _as_list(column_data.get("synonyms")),
                    "is_groupable": bool(column_data.get("is_groupable", False)),
                    "is_filterable": bool(column_data.get("is_filterable", False)),
                    "is_selectable": bool(column_data.get("is_selectable", False)),
                    "is_metric": bool(column_data.get("is_metric", False)),
                    "is_time_dimension": bool(column_data.get("is_time_dimension", False)),
                    "required": bool(column_data.get("required", False)),
                    "missing_metadata_allowed": bool(column_data.get("missing_metadata_allowed", False)),
                    "sync_to_dd_campos": bool(column_data.get("sync_to_dd_campos", True)),
                    "note": str(column_data.get("note") or ""),
                }
            )
    return rows


def _build_join_sql(relationship: dict[str, Any]) -> str:
    from_table = str(relationship.get("from_table") or "").strip()
    from_column = str(relationship.get("from_column") or "").strip()
    to_table = str(relationship.get("to_table") or "").strip()
    to_column = str(relationship.get("to_column") or "").strip()
    if not all((from_table, from_column, to_table, to_column)):
        return ""
    return f"{from_table}.{from_column} = {to_table}.{to_column}"


def get_relationships_for_dictionary(config: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for relationship_code, relationship in _as_dict(config.get("relationships")).items():
        relationship_data = _as_dict(relationship)
        rows.append(
            {
                "code": str(relationship_code),
                "domain_code": get_runtime_domain_code(config),
                "from_table": str(relationship_data.get("from_table") or ""),
                "from_column": str(relationship_data.get("from_column") or ""),
                "to_table": str(relationship_data.get("to_table") or ""),
                "to_column": str(relationship_data.get("to_column") or ""),
                "relationship_type": str(relationship_data.get("relationship_type") or ""),
                "allowed": bool(relationship_data.get("allowed", False)),
                "join_purpose": str(relationship_data.get("join_purpose") or ""),
                "join_sql": _build_join_sql(relationship_data),
                "sync_to_dd_relaciones": bool(relationship_data.get("sync_to_dd_relaciones", True)),
            }
        )
    return rows


def get_synonyms_for_dictionary(config: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    domain_code = get_runtime_domain_code(config)

    def add_synonym(
        *,
        synonym: str,
        canonical_value: str,
        target_type: str,
        target_table: str = "",
        target_column: str = "",
        extra: dict[str, Any] | None = None,
    ) -> None:
        clean_synonym = str(synonym or "").strip()
        if not clean_synonym:
            return
        payload = {
            "synonym": clean_synonym,
            "canonical_value": str(canonical_value or "").strip(),
            "target_type": str(target_type or "").strip(),
            "target_table": str(target_table or "").strip(),
            "target_column": str(target_column or "").strip(),
            "domain_code": domain_code,
        }
        if extra:
            payload.update(dict(extra))
        rows.append(payload)

    for target_group, values in _as_dict(config.get("synonyms")).items():
        for canonical_key, payload in _as_dict(values).items():
            synonym_data = _as_dict(payload)
            canonical_value = str(synonym_data.get("canonical") or canonical_key).strip()
            target_type = str(synonym_data.get("target_type") or target_group).strip()
            for value in _as_list(synonym_data.get("values")):
                add_synonym(
                    synonym=str(value),
                    canonical_value=canonical_value,
                    target_type=target_type,
                    extra={"synonym_group": str(target_group)},
                )

    for field in get_fields_for_dictionary(config):
        for synonym in _as_list(field.get("synonyms")):
            add_synonym(
                synonym=str(synonym),
                canonical_value=str(field.get("column_name") or ""),
                target_type="column",
                target_table=str(field.get("table_name") or ""),
                target_column=str(field.get("column_name") or ""),
            )

    for concept_name, concept in _as_dict(config.get("business_concepts")).items():
        for synonym in _as_list(_as_dict(concept).get("synonyms")):
            add_synonym(
                synonym=str(synonym),
                canonical_value=str(concept_name),
                target_type="business_concept",
            )

    for dimension_name, dimension in _as_dict(config.get("groupable_dimensions")).items():
        dimension_data = _as_dict(dimension)
        for synonym in _as_list(dimension_data.get("synonyms")):
            add_synonym(
                synonym=str(synonym),
                canonical_value=str(dimension_name),
                target_type="groupable_dimension",
                extra={"allowed_operations": _as_list(dimension_data.get("allowed_operations"))},
            )

    deduplicated: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for row in rows:
        key = (
            str(row.get("synonym") or "").lower(),
            str(row.get("canonical_value") or "").lower(),
            str(row.get("target_type") or "").lower(),
            str(row.get("target_table") or "").lower(),
            str(row.get("target_column") or "").lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(row)
    return deduplicated


def get_groupable_dimensions(config: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for dimension_name, dimension in _as_dict(config.get("groupable_dimensions")).items():
        dimension_data = _as_dict(dimension)
        rows.append(
            {
                "dimension_name": str(dimension_name),
                "description": str(dimension_data.get("description") or ""),
                "synonyms": _as_list(dimension_data.get("synonyms")),
                "canonical_fields": _as_list(dimension_data.get("canonical_fields")),
                "allowed_operations": _as_list(dimension_data.get("allowed_operations")),
            }
        )
    return rows


def get_business_concepts(config: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for concept_name, concept in _as_dict(config.get("business_concepts")).items():
        concept_data = _as_dict(concept)
        rows.append(
            {
                "concept_name": str(concept_name),
                "description": str(concept_data.get("description") or ""),
                "applies_to": _as_list(concept_data.get("applies_to")),
                "preferred_intent": str(concept_data.get("preferred_intent") or ""),
                "required_tables": _as_list(concept_data.get("required_tables")),
                "metric": _as_dict(concept_data.get("metric")),
                "semantic_formula": _as_dict(concept_data.get("semantic_formula")),
                "filters": _as_dict(concept_data.get("filters")),
                "primary_table": str(concept_data.get("primary_table") or ""),
                "primary_identifier": _as_dict(concept_data.get("primary_identifier")),
                "maps_to": _as_dict(concept_data.get("maps_to")),
                "risk_level": str(concept_data.get("risk_level") or ""),
                "expected_output": _as_list(concept_data.get("expected_output")),
                "default_group_by": str(concept_data.get("default_group_by") or ""),
            }
        )
    return rows


def get_business_rules(config: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rule_name, rule in _as_dict(config.get("business_rules")).items():
        rule_data = _as_dict(rule)
        rows.append({"rule_name": str(rule_name), **rule_data})
    return rows


def get_examples_as_query_patterns(config: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for example in _as_list(config.get("examples")):
        example_data = _as_dict(example)
        rows.append(
            {
                "id": str(example_data.get("id") or ""),
                "query": str(example_data.get("query") or ""),
                "expected": _as_dict(example_data.get("expected")),
            }
        )
    return rows


def validate_yaml_integrity(config: dict[str, Any]) -> dict[str, Any]:
    errores: list[str] = []
    advertencias: list[str] = []

    agent = _as_dict(config.get("agent"))
    business_domain = _as_dict(config.get("business_domain"))
    tables = _as_dict(config.get("tables"))
    relationships = get_relationships_for_dictionary(config)
    fields = get_fields_for_dictionary(config)
    groupable_dimensions = get_groupable_dimensions(config)
    examples = get_examples_as_query_patterns(config)

    if str(agent.get("code") or "").strip() != "inventario_materiales_agent":
        errores.append("agent.code debe ser inventario_materiales_agent")
    if not str(business_domain.get("code") or "").strip():
        errores.append("business_domain.code es obligatorio")
    if not tables:
        errores.append("tables no puede estar vacio")
    if not examples:
        errores.append("examples no puede estar vacio")

    columns_by_table: dict[str, set[str]] = {}
    missing_allowed_by_table: dict[str, set[str]] = {}
    for field in fields:
        table_name = str(field.get("table_name") or "")
        column_name = str(field.get("column_name") or "")
        columns_by_table.setdefault(table_name, set()).add(column_name)
        if bool(field.get("missing_metadata_allowed")):
            missing_allowed_by_table.setdefault(table_name, set()).add(column_name)

    for relationship in relationships:
        from_table = str(relationship.get("from_table") or "")
        to_table = str(relationship.get("to_table") or "")
        from_column = str(relationship.get("from_column") or "")
        to_column = str(relationship.get("to_column") or "")
        if from_table not in tables:
            errores.append(f"relationship {relationship.get('code')} usa from_table inexistente: {from_table}")
        if to_table not in tables:
            errores.append(f"relationship {relationship.get('code')} usa to_table inexistente: {to_table}")
        if from_table in columns_by_table and from_column not in columns_by_table.get(from_table, set()):
            errores.append(f"relationship {relationship.get('code')} usa from_column inexistente: {from_table}.{from_column}")
        if to_table in columns_by_table and to_column not in columns_by_table.get(to_table, set()):
            errores.append(f"relationship {relationship.get('code')} usa to_column inexistente: {to_table}.{to_column}")

    for dimension in groupable_dimensions:
        dimension_name = str(dimension.get("dimension_name") or "")
        for field_ref in _as_list(dimension.get("canonical_fields")):
            table_name, _, column_name = str(field_ref).partition(".")
            if not table_name or not column_name:
                errores.append(f"groupable_dimensions.{dimension_name} tiene canonical_field invalido: {field_ref}")
                continue
            if column_name not in columns_by_table.get(table_name, set()):
                if column_name in missing_allowed_by_table.get(table_name, set()):
                    advertencias.append(f"groupable_dimensions.{dimension_name} depende de metadata faltante permitida: {field_ref}")
                else:
                    errores.append(f"groupable_dimensions.{dimension_name} referencia campo inexistente: {field_ref}")

    for example in examples:
        expected = _as_dict(example.get("expected"))
        if not str(expected.get("domain") or "").strip():
            errores.append(f"example {example.get('id')} no declara expected.domain")
        if not str(expected.get("intent") or "").strip():
            errores.append(f"example {example.get('id')} no declara expected.intent")

    return {
        "ok": not errores,
        "status": "passed" if not errores else "failed",
        "errors": errores,
        "warnings": advertencias,
        "runtime_domain_code": get_runtime_domain_code(config),
        "business_domain_code": get_business_domain_code(config),
    }
