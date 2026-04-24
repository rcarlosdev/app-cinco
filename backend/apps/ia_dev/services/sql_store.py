import json
import os
import re
import threading
import time
from collections import defaultdict
from typing import Any

from django.db import connections


class IADevSqlStore:
    _init_lock = threading.Lock()
    _initialized_by_alias: set[str] = set()
    _ia_dev_table_pattern = re.compile(r"(?<![A-Za-z0-9_`\.])(ia_dev_[A-Za-z0-9_]+)\b")
    _required_system_schema = "ai_dictionary"

    def __init__(self):
        self.db_alias = (os.getenv("IA_DEV_DB_ALIAS", "default") or "default").strip()
        raw_system_schema = str(
            os.getenv("IA_DEV_SYSTEM_SCHEMA", self._required_system_schema)
            or self._required_system_schema
        ).strip()
        if not self._is_safe_identifier(raw_system_schema):
            raise ValueError("Invalid IA_DEV_SYSTEM_SCHEMA value")
        if raw_system_schema.lower() != self._required_system_schema:
            raise ValueError("IA_DEV_SYSTEM_SCHEMA must be 'ai_dictionary'")
        self.system_schema = self._required_system_schema
        # Catalogo semantico runtime con nombres especificos en espanol.
        self.tabla_catalogo_dominios = self._resolve_table_name(
            env_var="IA_DEV_TABLA_CATALOGO_DOMINIOS",
            default="ia_dev_catalogo_dominios",
        )
        self.tabla_catalogo_tablas_dominio = self._resolve_table_name(
            env_var="IA_DEV_TABLA_CATALOGO_TABLAS_DOMINIO",
            default="ia_dev_catalogo_tablas_dominio",
        )
        # Nombres legacy para migracion sin ruptura.
        self._tabla_legacy_dominios = "ia_dev_dominios"
        self._tabla_legacy_tablas_dominio = "ia_dev_tablas_dominio"
        self._tabla_legacy_columnas = "ia_dev_columnas"

    def _execute(self, sql: str, params: list | tuple | None = None):
        prepared_sql = self._prepare_sql(sql)
        with connections[self.db_alias].cursor() as cursor:
            cursor.execute(prepared_sql, params or [])

    def _fetchone(self, sql: str, params: list | tuple | None = None) -> tuple | None:
        prepared_sql = self._prepare_sql(sql)
        with connections[self.db_alias].cursor() as cursor:
            cursor.execute(prepared_sql, params or [])
            return cursor.fetchone()

    def _fetchall(self, sql: str, params: list | tuple | None = None) -> list[tuple]:
        prepared_sql = self._prepare_sql(sql)
        with connections[self.db_alias].cursor() as cursor:
            cursor.execute(prepared_sql, params or [])
            return cursor.fetchall()

    def _prepare_sql(self, sql: str) -> str:
        rendered = str(sql or "")
        if not self.system_schema:
            return rendered

        schema = str(self.system_schema)
        return self._ia_dev_table_pattern.sub(
            lambda match: f"`{schema}`.`{match.group(1)}`",
            rendered,
        )

    @classmethod
    def _resolve_table_name(cls, *, env_var: str, default: str) -> str:
        candidate = str(os.getenv(env_var, default) or default).strip()
        if not cls._is_safe_identifier(candidate):
            raise ValueError(f"Invalid {env_var} value")
        return candidate

    def _table_exists(self, *, table_name: str) -> bool:
        if not self._is_safe_identifier(table_name):
            return False
        row = self._fetchone(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = %s
              AND table_name = %s
            """,
            [self.system_schema, table_name],
        )
        return bool(int((row or [0])[0] or 0) > 0)

    def _table_rowcount(self, *, table_name: str) -> int:
        if not self._is_safe_identifier(table_name):
            return 0
        if not self._table_exists(table_name=table_name):
            return 0
        row = self._fetchone(f"SELECT COUNT(*) FROM {table_name}")
        return int((row or [0])[0] or 0)

    def _migrate_catalog_tables_from_legacy(self) -> None:
        # Copia datos legacy -> nuevo catalogo solo si el nuevo esta vacio.
        if (
            self.tabla_catalogo_dominios != self._tabla_legacy_dominios
            and self._table_exists(table_name=self._tabla_legacy_dominios)
            and self._table_exists(table_name=self.tabla_catalogo_dominios)
            and self._table_rowcount(table_name=self.tabla_catalogo_dominios) == 0
        ):
            self._execute(
                f"""
                INSERT INTO {self.tabla_catalogo_dominios} (
                    id,
                    codigo_dominio,
                    nombre_dominio,
                    objetivo_negocio,
                    entidad_principal,
                    estado_dominio,
                    nivel_madurez,
                    nivel_confianza_esquema,
                    source_of_truth,
                    source_ref,
                    flags_json,
                    contexto_semantico_json,
                    version,
                    created_at,
                    updated_at
                )
                SELECT
                    id,
                    codigo_dominio,
                    nombre_dominio,
                    objetivo_negocio,
                    entidad_principal,
                    estado_dominio,
                    nivel_madurez,
                    nivel_confianza_esquema,
                    source_of_truth,
                    source_ref,
                    flags_json,
                    contexto_semantico_json,
                    version,
                    created_at,
                    updated_at
                FROM {self._tabla_legacy_dominios}
                """
            )

        if (
            self.tabla_catalogo_tablas_dominio != self._tabla_legacy_tablas_dominio
            and self._table_exists(table_name=self._tabla_legacy_tablas_dominio)
            and self._table_exists(table_name=self.tabla_catalogo_tablas_dominio)
            and self._table_rowcount(table_name=self.tabla_catalogo_tablas_dominio) == 0
        ):
            self._execute(
                f"""
                INSERT INTO {self.tabla_catalogo_tablas_dominio} (
                    id,
                    dominio_id,
                    schema_name,
                    table_name,
                    table_fqn,
                    nombre_tabla_logico,
                    rol_tabla,
                    es_principal,
                    source_of_truth,
                    source_ref,
                    estado,
                    metadata_json,
                    created_at,
                    updated_at
                )
                SELECT
                    id,
                    dominio_id,
                    schema_name,
                    table_name,
                    table_fqn,
                    nombre_tabla_logico,
                    rol_tabla,
                    es_principal,
                    source_of_truth,
                    source_ref,
                    estado,
                    metadata_json,
                    created_at,
                    updated_at
                FROM {self._tabla_legacy_tablas_dominio}
                """
            )

    def _drop_unused_columns_table(self) -> None:
        # ia_dev_columnas ya no participa en runtime semantico actual.
        if not self._table_exists(table_name=self._tabla_legacy_columnas):
            return
        self._execute(f"DROP TABLE IF EXISTS {self._tabla_legacy_columnas}")

    def _drop_legacy_catalog_tables(self) -> None:
        # Ya no se usan en runtime: se reemplazaron por tablas catalogo en espanol.
        for legacy in (
            self._tabla_legacy_tablas_dominio,
            self._tabla_legacy_dominios,
        ):
            if not self._is_safe_identifier(legacy):
                continue
            if legacy in {self.tabla_catalogo_dominios, self.tabla_catalogo_tablas_dominio}:
                continue
            if self._table_exists(table_name=legacy):
                self._execute(f"DROP TABLE IF EXISTS {legacy}")

    @staticmethod
    def _to_text(value: Any) -> str:
        return str(value or "").strip()

    @classmethod
    def _safe_json_list(cls, value: Any) -> list[Any]:
        parsed = value
        if isinstance(value, str):
            parsed = cls._from_json(value, [])
        elif value is None:
            parsed = []
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, tuple):
            return list(parsed)
        if isinstance(parsed, dict):
            return [parsed]
        return []

    @staticmethod
    def _normalize_company_domain_code(value: Any) -> str:
        raw = str(value or "").strip().lower()
        if not raw:
            return ""
        normalized = re.sub(r"[^a-z0-9_]+", "", raw)
        if any(token in normalized for token in ("ausent", "asistencia")):
            return "ausentismo"
        if any(token in normalized for token in ("rrhh", "emplead", "personal", "humano")):
            return "empleados"
        if "transport" in normalized or "vehicul" in normalized or "movilidad" in normalized:
            return "transporte"
        if "viatic" in normalized:
            return "viaticos"
        if "nomina" in normalized or "payroll" in normalized:
            return "nomina"
        if "compr" in normalized:
            return "compras"
        if "agenda" in normalized:
            return "agenda"
        return normalized

    @staticmethod
    def _canonical_business_domain_name(domain_code: str) -> str:
        normalized = str(domain_code or "").strip().lower()
        if normalized == "ausentismo":
            return "Ausentismos"
        if normalized == "empleados":
            return "Empleados"
        return normalized.title() if normalized else ""

    def get_contexto_compania(self, *, codigo_compania: str = "CINCO") -> dict[str, Any]:
        schema = str(self.system_schema or "ai_dictionary")
        table_name = "dd_contexto_compania"
        company_code = str(codigo_compania or "CINCO").strip().upper() or "CINCO"
        defaults: dict[str, Any] = {
            "codigo_compania": company_code,
            "nombre_compania": "",
            "nombre_comercial": "",
            "aliases_compania": [],
            "sector": "",
            "descripcion_negocio": "",
            "objetivo_orquestador": "",
            "areas_activas": [],
            "procesos_clave": [],
            "dominios_oficiales": [],
            "lenguaje_interno": [],
            "sistemas_fuente": [],
            "politicas_globales": [],
            "agentes_oficiales": [],
            "restricciones_operativas": [],
            "indicadores_clave": [],
            "estado": "unknown",
            "version": 0,
            "dominios_operativos": [],
            "origen": f"{schema}.{table_name}",
        }
        if not self._is_safe_identifier(schema):
            return defaults
        if not self._table_exists(table_name=table_name):
            return defaults

        row = self._fetchone(
            f"""
            SELECT
                codigo_compania,
                nombre_compania,
                nombre_comercial,
                aliases_compania_json,
                sector,
                descripcion_negocio,
                objetivo_orquestador,
                areas_activas_json,
                procesos_clave_json,
                dominios_oficiales_json,
                lenguaje_interno_json,
                sistemas_fuente_json,
                politicas_globales_json,
                agentes_oficiales_json,
                restricciones_operativas_json,
                indicadores_clave_json,
                estado,
                version
            FROM {schema}.{table_name}
            WHERE UPPER(codigo_compania) = UPPER(%s)
              AND LOWER(COALESCE(estado, 'active')) = 'active'
            ORDER BY version DESC, id DESC
            LIMIT 1
            """,
            [company_code],
        )
        if not row:
            row = self._fetchone(
                f"""
                SELECT
                    codigo_compania,
                    nombre_compania,
                    nombre_comercial,
                    aliases_compania_json,
                    sector,
                    descripcion_negocio,
                    objetivo_orquestador,
                    areas_activas_json,
                    procesos_clave_json,
                    dominios_oficiales_json,
                    lenguaje_interno_json,
                    sistemas_fuente_json,
                    politicas_globales_json,
                    agentes_oficiales_json,
                    restricciones_operativas_json,
                    indicadores_clave_json,
                    estado,
                    version
                FROM {schema}.{table_name}
                WHERE LOWER(COALESCE(estado, 'active')) = 'active'
                ORDER BY version DESC, id DESC
                LIMIT 1
                """
            )
        if not row:
            return defaults

        payload = {
            "codigo_compania": self._to_text(row[0]).upper() or company_code,
            "nombre_compania": self._to_text(row[1]),
            "nombre_comercial": self._to_text(row[2]),
            "aliases_compania": self._safe_json_list(row[3]),
            "sector": self._to_text(row[4]),
            "descripcion_negocio": self._to_text(row[5]),
            "objetivo_orquestador": self._to_text(row[6]),
            "areas_activas": self._safe_json_list(row[7]),
            "procesos_clave": self._safe_json_list(row[8]),
            "dominios_oficiales": self._safe_json_list(row[9]),
            "lenguaje_interno": self._safe_json_list(row[10]),
            "sistemas_fuente": self._safe_json_list(row[11]),
            "politicas_globales": self._safe_json_list(row[12]),
            "agentes_oficiales": self._safe_json_list(row[13]),
            "restricciones_operativas": self._safe_json_list(row[14]),
            "indicadores_clave": self._safe_json_list(row[15]),
            "estado": self._to_text(row[16]).lower() or "active",
            "version": int(row[17] or 0),
            "origen": f"{schema}.{table_name}",
        }

        operational_raw = self._fetchall(
            f"""
            SELECT DISTINCT COALESCE(d.codigo, d.nombre, '')
            FROM {schema}.dd_tablas AS t
            JOIN {schema}.dd_dominios AS d ON d.id = t.dominio_id
            WHERE COALESCE(t.activo, 1) = 1
              AND COALESCE(d.activo, 1) = 1
            """
        )
        operational_domains: list[str] = []
        for item in operational_raw:
            value = self._normalize_company_domain_code(item[0] if item else "")
            if value:
                operational_domains.append(value)
        payload["dominios_operativos"] = sorted({item for item in operational_domains if item})
        return {**defaults, **payload}

    @staticmethod
    def _now() -> int:
        return int(time.time())

    def ensure_tables(self):
        init_key = f"{self.db_alias}:{self.system_schema or '_default_'}"
        if init_key in self._initialized_by_alias:
            return
        with self._init_lock:
            if init_key in self._initialized_by_alias:
                return

            self._execute(
                """
                CREATE TABLE IF NOT EXISTS ia_dev_session_memory (
                    session_id VARCHAR(64) PRIMARY KEY,
                    messages_json LONGTEXT NOT NULL,
                    context_json LONGTEXT NOT NULL,
                    trim_events INT NOT NULL DEFAULT 0,
                    updated_at BIGINT NOT NULL
                )
                """
            )
            self._execute(
                """
                CREATE TABLE IF NOT EXISTS ia_dev_tickets (
                    ticket_id VARCHAR(32) PRIMARY KEY,
                    category VARCHAR(64) NOT NULL,
                    title VARCHAR(255) NOT NULL,
                    description TEXT NOT NULL,
                    session_id VARCHAR(64) NULL,
                    created_at BIGINT NOT NULL
                )
                """
            )
            self._execute(
                """
                CREATE TABLE IF NOT EXISTS ia_dev_knowledge_proposals (
                    proposal_id VARCHAR(32) PRIMARY KEY,
                    status VARCHAR(32) NOT NULL,
                    mode VARCHAR(16) NOT NULL,
                    proposal_type VARCHAR(32) NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    description TEXT NOT NULL,
                    domain_code VARCHAR(64) NOT NULL,
                    condition_sql TEXT NOT NULL,
                    result_text TEXT NOT NULL,
                    tables_related TEXT NOT NULL,
                    priority INT NOT NULL,
                    target_rule_id INT NULL,
                    session_id VARCHAR(64) NULL,
                    requested_by VARCHAR(64) NOT NULL,
                    similar_rules_json LONGTEXT NOT NULL,
                    persistence_json LONGTEXT NULL,
                    error TEXT NULL,
                    version INT NOT NULL DEFAULT 1,
                    last_idempotency_key VARCHAR(120) NULL,
                    created_at BIGINT NOT NULL,
                    updated_at BIGINT NOT NULL
                )
                """
            )
            self._execute(
                """
                CREATE TABLE IF NOT EXISTS ia_dev_async_jobs (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    job_id VARCHAR(40) NOT NULL UNIQUE,
                    job_type VARCHAR(64) NOT NULL,
                    status VARCHAR(24) NOT NULL,
                    payload_json LONGTEXT NOT NULL,
                    result_json LONGTEXT NULL,
                    error TEXT NULL,
                    idempotency_key VARCHAR(120) NULL UNIQUE,
                    created_at BIGINT NOT NULL,
                    updated_at BIGINT NOT NULL,
                    run_after BIGINT NOT NULL DEFAULT 0
                )
                """
            )
            self._execute(
                """
                CREATE TABLE IF NOT EXISTS ia_dev_observability_events (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    event_type VARCHAR(80) NOT NULL,
                    source VARCHAR(80) NOT NULL,
                    duration_ms INT NULL,
                    tokens_in INT NULL,
                    tokens_out INT NULL,
                    cost_usd DECIMAL(14,8) NULL,
                    meta_json LONGTEXT NULL,
                    created_at BIGINT NOT NULL
                )
                """
            )
            self._execute(
                """
                CREATE TABLE IF NOT EXISTS ia_dev_user_memory (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    user_key VARCHAR(128) NOT NULL,
                    memory_key VARCHAR(120) NOT NULL,
                    memory_value_json LONGTEXT NOT NULL,
                    sensitivity VARCHAR(16) NOT NULL DEFAULT 'medium',
                    source VARCHAR(40) NOT NULL DEFAULT 'api',
                    confidence DECIMAL(6,5) NOT NULL DEFAULT 1.00000,
                    expires_at BIGINT NULL,
                    created_at BIGINT NOT NULL,
                    updated_at BIGINT NOT NULL,
                    UNIQUE KEY uq_ia_dev_user_memory (user_key, memory_key),
                    KEY idx_ia_dev_user_memory_user (user_key),
                    KEY idx_ia_dev_user_memory_updated (updated_at)
                )
                """
            )
            self._execute(
                """
                CREATE TABLE IF NOT EXISTS ia_dev_business_memory (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    domain_code VARCHAR(64) NOT NULL,
                    capability_id VARCHAR(120) NOT NULL,
                    memory_key VARCHAR(120) NOT NULL,
                    memory_value_json LONGTEXT NOT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'active',
                    source_type VARCHAR(40) NOT NULL DEFAULT 'manual',
                    version INT NOT NULL DEFAULT 1,
                    approved_by VARCHAR(64) NULL,
                    approved_at BIGINT NULL,
                    created_at BIGINT NOT NULL,
                    updated_at BIGINT NOT NULL,
                    UNIQUE KEY uq_ia_dev_business_memory (domain_code, capability_id, memory_key),
                    KEY idx_ia_dev_business_memory_domain (domain_code),
                    KEY idx_ia_dev_business_memory_capability (capability_id),
                    KEY idx_ia_dev_business_memory_status (status)
                )
                """
            )
            self._execute(
                """
                CREATE TABLE IF NOT EXISTS ia_dev_learned_memory_proposals (
                    proposal_id VARCHAR(40) PRIMARY KEY,
                    scope VARCHAR(20) NOT NULL,
                    status VARCHAR(24) NOT NULL,
                    proposer_user_key VARCHAR(128) NOT NULL,
                    source_run_id VARCHAR(64) NULL,
                    candidate_key VARCHAR(120) NOT NULL,
                    candidate_value_json LONGTEXT NOT NULL,
                    reason TEXT NULL,
                    sensitivity VARCHAR(16) NOT NULL DEFAULT 'medium',
                    domain_code VARCHAR(64) NULL,
                    capability_id VARCHAR(120) NULL,
                    policy_action VARCHAR(24) NULL,
                    policy_id VARCHAR(80) NULL,
                    idempotency_key VARCHAR(120) NULL UNIQUE,
                    error TEXT NULL,
                    version INT NOT NULL DEFAULT 1,
                    created_at BIGINT NOT NULL,
                    updated_at BIGINT NOT NULL,
                    KEY idx_ia_dev_lmp_status (status),
                    KEY idx_ia_dev_lmp_scope (scope),
                    KEY idx_ia_dev_lmp_created (created_at)
                )
                """
            )
            self._execute(
                """
                CREATE TABLE IF NOT EXISTS ia_dev_learned_memory_approvals (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    proposal_id VARCHAR(40) NOT NULL,
                    action VARCHAR(16) NOT NULL,
                    actor_user_key VARCHAR(128) NOT NULL,
                    actor_role VARCHAR(64) NOT NULL,
                    comment TEXT NULL,
                    created_at BIGINT NOT NULL,
                    KEY idx_ia_dev_lma_proposal (proposal_id),
                    KEY idx_ia_dev_lma_created (created_at)
                )
                """
            )
            self._execute(
                """
                CREATE TABLE IF NOT EXISTS ia_dev_workflow_state (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    workflow_type VARCHAR(64) NOT NULL,
                    workflow_key VARCHAR(120) NOT NULL UNIQUE,
                    status VARCHAR(24) NOT NULL,
                    state_json LONGTEXT NOT NULL,
                    retry_count INT NOT NULL DEFAULT 0,
                    lock_version INT NOT NULL DEFAULT 1,
                    next_retry_at BIGINT NULL,
                    last_error TEXT NULL,
                    created_at BIGINT NOT NULL,
                    updated_at BIGINT NOT NULL,
                    KEY idx_ia_dev_workflow_type (workflow_type),
                    KEY idx_ia_dev_workflow_status (status)
                )
                """
            )
            self._execute(
                """
                CREATE TABLE IF NOT EXISTS ia_dev_memory_audit_trail (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    event_type VARCHAR(64) NOT NULL,
                    memory_scope VARCHAR(20) NOT NULL,
                    entity_key VARCHAR(140) NOT NULL,
                    action VARCHAR(24) NOT NULL,
                    actor_type VARCHAR(24) NOT NULL,
                    actor_key VARCHAR(128) NOT NULL,
                    run_id VARCHAR(64) NULL,
                    trace_id VARCHAR(64) NULL,
                    before_json LONGTEXT NULL,
                    after_json LONGTEXT NULL,
                    meta_json LONGTEXT NULL,
                    created_at BIGINT NOT NULL,
                    KEY idx_ia_dev_mat_scope (memory_scope),
                    KEY idx_ia_dev_mat_entity (entity_key),
                    KEY idx_ia_dev_mat_run (run_id),
                    KEY idx_ia_dev_mat_trace (trace_id),
                    KEY idx_ia_dev_mat_created (created_at)
                )
                """
            )
            self._execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.tabla_catalogo_dominios} (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    codigo_dominio VARCHAR(80) NOT NULL UNIQUE,
                    nombre_dominio VARCHAR(120) NOT NULL,
                    objetivo_negocio TEXT NULL,
                    entidad_principal VARCHAR(80) NULL,
                    estado_dominio VARCHAR(24) NOT NULL DEFAULT 'planned',
                    nivel_madurez VARCHAR(24) NOT NULL DEFAULT 'initial',
                    nivel_confianza_esquema DECIMAL(6,5) NOT NULL DEFAULT 0.00000,
                    source_of_truth VARCHAR(24) NOT NULL DEFAULT 'db',
                    source_ref VARCHAR(255) NULL,
                    flags_json LONGTEXT NULL,
                    contexto_semantico_json LONGTEXT NULL,
                    version INT NOT NULL DEFAULT 1,
                    created_at BIGINT NOT NULL,
                    updated_at BIGINT NOT NULL,
                    KEY idx_ia_dev_dominios_estado (estado_dominio),
                    KEY idx_ia_dev_dominios_madurez (nivel_madurez),
                    KEY idx_ia_dev_dominios_updated (updated_at)
                )
                """
            )
            self._execute(
                """
                CREATE TABLE IF NOT EXISTS ia_dev_estado_dominio (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    dominio_id BIGINT NOT NULL,
                    estado_origen VARCHAR(24) NULL,
                    estado_destino VARCHAR(24) NOT NULL,
                    actor VARCHAR(120) NULL,
                    motivo TEXT NULL,
                    source VARCHAR(40) NOT NULL DEFAULT 'system',
                    run_id VARCHAR(64) NULL,
                    trace_id VARCHAR(64) NULL,
                    created_at BIGINT NOT NULL,
                    KEY idx_ia_dev_estado_dominio_dominio (dominio_id),
                    KEY idx_ia_dev_estado_dominio_destino (estado_destino),
                    KEY idx_ia_dev_estado_dominio_created (created_at)
                )
                """
            )
            self._execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.tabla_catalogo_tablas_dominio} (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    dominio_id BIGINT NOT NULL,
                    schema_name VARCHAR(120) NULL,
                    table_name VARCHAR(120) NOT NULL,
                    table_fqn VARCHAR(260) NOT NULL,
                    nombre_tabla_logico VARCHAR(120) NULL,
                    rol_tabla VARCHAR(40) NULL,
                    es_principal TINYINT(1) NOT NULL DEFAULT 0,
                    source_of_truth VARCHAR(24) NOT NULL DEFAULT 'db',
                    source_ref VARCHAR(255) NULL,
                    estado VARCHAR(24) NOT NULL DEFAULT 'active',
                    metadata_json LONGTEXT NULL,
                    created_at BIGINT NOT NULL,
                    updated_at BIGINT NOT NULL,
                    UNIQUE KEY uq_ia_dev_tablas_dominio (dominio_id, table_fqn),
                    KEY idx_ia_dev_tablas_dominio_dominio (dominio_id),
                    KEY idx_ia_dev_tablas_dominio_estado (estado)
                )
                """
            )
            self._execute(
                """
                CREATE TABLE IF NOT EXISTS ia_dev_relaciones (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    dominio_id BIGINT NOT NULL,
                    tabla_origen_id BIGINT NOT NULL,
                    tabla_destino_id BIGINT NOT NULL,
                    nombre_relacion VARCHAR(160) NOT NULL,
                    tipo_join VARCHAR(24) NOT NULL DEFAULT 'inner',
                    condicion_join_sql TEXT NOT NULL,
                    cardinalidad VARCHAR(40) NULL,
                    es_interdominio TINYINT(1) NOT NULL DEFAULT 0,
                    nivel_confianza DECIMAL(6,5) NOT NULL DEFAULT 0.00000,
                    source_of_truth VARCHAR(24) NOT NULL DEFAULT 'db',
                    estado VARCHAR(24) NOT NULL DEFAULT 'active',
                    created_at BIGINT NOT NULL,
                    updated_at BIGINT NOT NULL,
                    KEY idx_ia_dev_relaciones_dominio (dominio_id),
                    KEY idx_ia_dev_relaciones_origen (tabla_origen_id),
                    KEY idx_ia_dev_relaciones_destino (tabla_destino_id),
                    KEY idx_ia_dev_relaciones_estado (estado)
                )
                """
            )
            self._execute(
                """
                CREATE TABLE IF NOT EXISTS ia_dev_capacidades (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    dominio_id BIGINT NOT NULL,
                    capability_id VARCHAR(160) NOT NULL UNIQUE,
                    capability_key VARCHAR(120) NOT NULL,
                    tipo_tarea VARCHAR(80) NOT NULL,
                    contrato_input_json LONGTEXT NULL,
                    contrato_output_json LONGTEXT NULL,
                    filtros_soportados_json LONGTEXT NULL,
                    group_by_soportados_json LONGTEXT NULL,
                    metricas_soportadas_json LONGTEXT NULL,
                    policy_tags_json LONGTEXT NULL,
                    rollout_flag VARCHAR(120) NULL,
                    handler_class VARCHAR(160) NULL,
                    estado VARCHAR(24) NOT NULL DEFAULT 'planned',
                    version INT NOT NULL DEFAULT 1,
                    created_at BIGINT NOT NULL,
                    updated_at BIGINT NOT NULL,
                    KEY idx_ia_dev_capacidades_dominio (dominio_id),
                    KEY idx_ia_dev_capacidades_estado (estado),
                    KEY idx_ia_dev_capacidades_updated (updated_at)
                )
                """
            )
            self._execute(
                """
                CREATE TABLE IF NOT EXISTS ia_dev_skills (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    dominio_id BIGINT NOT NULL,
                    skill_code VARCHAR(120) NOT NULL,
                    skill_type VARCHAR(80) NOT NULL,
                    metadata_json LONGTEXT NULL,
                    prompt_template TEXT NULL,
                    estado VARCHAR(24) NOT NULL DEFAULT 'active',
                    version INT NOT NULL DEFAULT 1,
                    created_at BIGINT NOT NULL,
                    updated_at BIGINT NOT NULL,
                    UNIQUE KEY uq_ia_dev_skills (dominio_id, skill_code),
                    KEY idx_ia_dev_skills_dominio (dominio_id),
                    KEY idx_ia_dev_skills_estado (estado)
                )
                """
            )
            self._execute(
                """
                CREATE TABLE IF NOT EXISTS ia_dev_auditoria_semantica (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    entity_type VARCHAR(64) NOT NULL,
                    entity_id VARCHAR(120) NOT NULL,
                    change_type VARCHAR(32) NOT NULL,
                    change_source VARCHAR(40) NOT NULL,
                    before_json LONGTEXT NULL,
                    after_json LONGTEXT NULL,
                    version_from INT NULL,
                    version_to INT NULL,
                    actor VARCHAR(120) NULL,
                    run_id VARCHAR(64) NULL,
                    trace_id VARCHAR(64) NULL,
                    created_at BIGINT NOT NULL,
                    KEY idx_ia_dev_auditoria_entidad (entity_type, entity_id),
                    KEY idx_ia_dev_auditoria_created (created_at),
                    KEY idx_ia_dev_auditoria_run (run_id)
                )
                """
            )
            self._migrate_catalog_tables_from_legacy()
            self._drop_unused_columns_table()
            self._drop_legacy_catalog_tables()
            self._initialized_by_alias.add(init_key)

    @staticmethod
    def _to_json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False)

    @staticmethod
    def _from_json(raw: str | None, default: Any):
        if not raw:
            return default
        try:
            return json.loads(raw)
        except Exception:
            return default

    # Catalogo semantico de dominios
    def list_dominios(self, *, status: str | None = None, limit: int = 200) -> list[dict]:
        self.ensure_tables()
        safe_limit = max(1, min(int(limit), 1000))
        where = ""
        params: list[Any] = []
        if status:
            where = "WHERE estado_dominio = %s"
            params.append(str(status).strip().lower())
        rows = self._fetchall(
            f"""
            SELECT
                id,
                codigo_dominio,
                nombre_dominio,
                objetivo_negocio,
                entidad_principal,
                estado_dominio,
                nivel_madurez,
                nivel_confianza_esquema,
                source_of_truth,
                source_ref,
                flags_json,
                contexto_semantico_json,
                version,
                created_at,
                updated_at
            FROM {self.tabla_catalogo_dominios}
            {where}
            ORDER BY codigo_dominio
            LIMIT %s
            """,
            [*params, safe_limit],
        )
        payload: list[dict] = []
        for row in rows:
            payload.append(
                {
                    "id": int(row[0]),
                    "codigo_dominio": str(row[1] or ""),
                    "nombre_dominio": str(row[2] or ""),
                    "objetivo_negocio": str(row[3] or ""),
                    "entidad_principal": str(row[4] or ""),
                    "estado_dominio": str(row[5] or ""),
                    "nivel_madurez": str(row[6] or ""),
                    "nivel_confianza_esquema": float(row[7] or 0.0),
                    "source_of_truth": str(row[8] or ""),
                    "source_ref": str(row[9] or ""),
                    "flags_json": self._from_json(row[10], {}),
                    "contexto_semantico_json": self._from_json(row[11], {}),
                    "version": int(row[12] or 1),
                    "created_at": int(row[13] or 0),
                    "updated_at": int(row[14] or 0),
                }
            )
        return payload

    def get_dominio(self, *, codigo_dominio: str) -> dict | None:
        self.ensure_tables()
        code = str(codigo_dominio or "").strip().lower()
        if not code:
            return None
        row = self._fetchone(
            f"""
            SELECT
                id,
                codigo_dominio,
                nombre_dominio,
                objetivo_negocio,
                entidad_principal,
                estado_dominio,
                nivel_madurez,
                nivel_confianza_esquema,
                source_of_truth,
                source_ref,
                flags_json,
                contexto_semantico_json,
                version,
                created_at,
                updated_at
            FROM {self.tabla_catalogo_dominios}
            WHERE codigo_dominio = %s
            LIMIT 1
            """,
            [code],
        )
        if not row:
            return None
        return {
            "id": int(row[0]),
            "codigo_dominio": str(row[1] or ""),
            "nombre_dominio": str(row[2] or ""),
            "objetivo_negocio": str(row[3] or ""),
            "entidad_principal": str(row[4] or ""),
            "estado_dominio": str(row[5] or ""),
            "nivel_madurez": str(row[6] or ""),
            "nivel_confianza_esquema": float(row[7] or 0.0),
            "source_of_truth": str(row[8] or ""),
            "source_ref": str(row[9] or ""),
            "flags_json": self._from_json(row[10], {}),
            "contexto_semantico_json": self._from_json(row[11], {}),
            "version": int(row[12] or 1),
            "created_at": int(row[13] or 0),
            "updated_at": int(row[14] or 0),
        }

    def upsert_dominio(
        self,
        *,
        codigo_dominio: str,
        nombre_dominio: str,
        objetivo_negocio: str = "",
        entidad_principal: str = "",
        estado_dominio: str = "planned",
        nivel_madurez: str = "initial",
        nivel_confianza_esquema: float = 0.0,
        source_of_truth: str = "db",
        source_ref: str | None = None,
        flags: dict | None = None,
        contexto_semantico: dict | None = None,
    ) -> dict:
        self.ensure_tables()
        ts = self._now()
        code = str(codigo_dominio or "").strip().lower()
        if not code:
            raise ValueError("codigo_dominio is required")
        existing = self.get_dominio(codigo_dominio=code)
        if existing:
            new_version = int(existing.get("version") or 1) + 1
            self._execute(
                f"""
                UPDATE {self.tabla_catalogo_dominios}
                SET nombre_dominio = %s,
                    objetivo_negocio = %s,
                    entidad_principal = %s,
                    estado_dominio = %s,
                    nivel_madurez = %s,
                    nivel_confianza_esquema = %s,
                    source_of_truth = %s,
                    source_ref = %s,
                    flags_json = %s,
                    contexto_semantico_json = %s,
                    version = %s,
                    updated_at = %s
                WHERE codigo_dominio = %s
                """,
                [
                    str(nombre_dominio or code),
                    str(objetivo_negocio or ""),
                    str(entidad_principal or ""),
                    str(estado_dominio or "planned").strip().lower(),
                    str(nivel_madurez or "initial").strip().lower(),
                    float(nivel_confianza_esquema or 0.0),
                    str(source_of_truth or "db"),
                    str(source_ref or ""),
                    self._to_json(flags or {}),
                    self._to_json(contexto_semantico or {}),
                    new_version,
                    ts,
                    code,
                ],
            )
            return self.get_dominio(codigo_dominio=code) or {}

        self._execute(
            f"""
            INSERT INTO {self.tabla_catalogo_dominios} (
                codigo_dominio,
                nombre_dominio,
                objetivo_negocio,
                entidad_principal,
                estado_dominio,
                nivel_madurez,
                nivel_confianza_esquema,
                source_of_truth,
                source_ref,
                flags_json,
                contexto_semantico_json,
                version,
                created_at,
                updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                code,
                str(nombre_dominio or code),
                str(objetivo_negocio or ""),
                str(entidad_principal or ""),
                str(estado_dominio or "planned").strip().lower(),
                str(nivel_madurez or "initial").strip().lower(),
                float(nivel_confianza_esquema or 0.0),
                str(source_of_truth or "db"),
                str(source_ref or ""),
                self._to_json(flags or {}),
                self._to_json(contexto_semantico or {}),
                1,
                ts,
                ts,
            ],
        )
        return self.get_dominio(codigo_dominio=code) or {}

    def upsert_tabla_dominio(
        self,
        *,
        dominio_id: int,
        schema_name: str | None,
        table_name: str,
        table_fqn: str,
        nombre_tabla_logico: str | None = None,
        rol_tabla: str | None = None,
        es_principal: bool = False,
        source_of_truth: str = "db",
        source_ref: str | None = None,
        estado: str = "active",
        metadata: dict | None = None,
    ) -> dict:
        self.ensure_tables()
        ts = self._now()
        did = int(dominio_id)
        fqn = str(table_fqn or "").strip().lower()
        existing = self._fetchone(
            f"""
            SELECT id
            FROM {self.tabla_catalogo_tablas_dominio}
            WHERE dominio_id = %s
              AND table_fqn = %s
            LIMIT 1
            """,
            [did, fqn],
        )
        if existing:
            self._execute(
                f"""
                UPDATE {self.tabla_catalogo_tablas_dominio}
                SET schema_name = %s,
                    table_name = %s,
                    nombre_tabla_logico = %s,
                    rol_tabla = %s,
                    es_principal = %s,
                    source_of_truth = %s,
                    source_ref = %s,
                    estado = %s,
                    metadata_json = %s,
                    updated_at = %s
                WHERE id = %s
                """,
                [
                    str(schema_name or ""),
                    str(table_name or ""),
                    str(nombre_tabla_logico or ""),
                    str(rol_tabla or ""),
                    1 if es_principal else 0,
                    str(source_of_truth or "db"),
                    str(source_ref or ""),
                    str(estado or "active").strip().lower(),
                    self._to_json(metadata or {}),
                    ts,
                    int(existing[0]),
                ],
            )
        else:
            self._execute(
                f"""
                INSERT INTO {self.tabla_catalogo_tablas_dominio} (
                    dominio_id,
                    schema_name,
                    table_name,
                    table_fqn,
                    nombre_tabla_logico,
                    rol_tabla,
                    es_principal,
                    source_of_truth,
                    source_ref,
                    estado,
                    metadata_json,
                    created_at,
                    updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    did,
                    str(schema_name or ""),
                    str(table_name or ""),
                    fqn,
                    str(nombre_tabla_logico or ""),
                    str(rol_tabla or ""),
                    1 if es_principal else 0,
                    str(source_of_truth or "db"),
                    str(source_ref or ""),
                    str(estado or "active").strip().lower(),
                    self._to_json(metadata or {}),
                    ts,
                    ts,
                ],
            )

        row = self._fetchone(
            f"""
            SELECT
                id,
                dominio_id,
                schema_name,
                table_name,
                table_fqn,
                nombre_tabla_logico,
                rol_tabla,
                es_principal,
                source_of_truth,
                source_ref,
                estado,
                metadata_json
            FROM {self.tabla_catalogo_tablas_dominio}
            WHERE dominio_id = %s
              AND table_fqn = %s
            LIMIT 1
            """,
            [did, fqn],
        )
        if not row:
            return {}
        return {
            "id": int(row[0]),
            "dominio_id": int(row[1]),
            "schema_name": str(row[2] or ""),
            "table_name": str(row[3] or ""),
            "table_fqn": str(row[4] or ""),
            "nombre_tabla_logico": str(row[5] or ""),
            "rol_tabla": str(row[6] or ""),
            "es_principal": bool(row[7]),
            "source_of_truth": str(row[8] or ""),
            "source_ref": str(row[9] or ""),
            "estado": str(row[10] or ""),
            "metadata": self._from_json(row[11], {}),
        }

    def transition_estado_dominio(
        self,
        *,
        codigo_dominio: str,
        estado_destino: str,
        actor: str = "system",
        motivo: str = "",
        run_id: str | None = None,
        trace_id: str | None = None,
        source: str = "workflow",
    ) -> dict:
        self.ensure_tables()
        code = str(codigo_dominio or "").strip().lower()
        target = str(estado_destino or "").strip().lower()
        valid_states = {"planned", "partial", "active", "deprecated"}
        if target not in valid_states:
            return {"ok": False, "error": "invalid_target_status"}

        domain = self.get_dominio(codigo_dominio=code)
        if not domain:
            return {"ok": False, "error": "domain_not_found"}

        current = str(domain.get("estado_dominio") or "").strip().lower() or "planned"
        valid_transitions = {
            "planned": {"partial", "active", "deprecated"},
            "partial": {"active", "deprecated"},
            "active": {"partial", "deprecated"},
            "deprecated": {"planned"},
        }
        if current == target:
            return {"ok": True, "idempotent": True, "domain": domain}
        if target not in valid_transitions.get(current, set()):
            return {"ok": False, "error": "invalid_status_transition", "from_status": current, "to_status": target}

        ts = self._now()
        self._execute(
            f"""
            UPDATE {self.tabla_catalogo_dominios}
            SET estado_dominio = %s,
                version = version + 1,
                updated_at = %s
            WHERE codigo_dominio = %s
            """,
            [target, ts, code],
        )
        self._execute(
            """
            INSERT INTO ia_dev_estado_dominio (
                dominio_id,
                estado_origen,
                estado_destino,
                actor,
                motivo,
                source,
                run_id,
                trace_id,
                created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                int(domain.get("id") or 0),
                current,
                target,
                str(actor or "system"),
                str(motivo or ""),
                str(source or "workflow"),
                str(run_id or ""),
                str(trace_id or ""),
                ts,
            ],
        )
        self._execute(
            """
            INSERT INTO ia_dev_auditoria_semantica (
                entity_type,
                entity_id,
                change_type,
                change_source,
                before_json,
                after_json,
                version_from,
                version_to,
                actor,
                run_id,
                trace_id,
                created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                "dominio",
                str(domain.get("id") or ""),
                "status_transition",
                str(source or "workflow"),
                self._to_json({"estado_dominio": current}),
                self._to_json({"estado_dominio": target}),
                int(domain.get("version") or 1),
                int(domain.get("version") or 1) + 1,
                str(actor or "system"),
                str(run_id or ""),
                str(trace_id or ""),
                ts,
            ],
        )
        return {
            "ok": True,
            "idempotent": False,
            "from_status": current,
            "to_status": target,
            "domain": self.get_dominio(codigo_dominio=code),
        }

    def list_estado_dominio(
        self,
        *,
        codigo_dominio: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        self.ensure_tables()
        where = ""
        params: list[Any] = []
        if codigo_dominio:
            domain = self.get_dominio(codigo_dominio=str(codigo_dominio))
            if not domain:
                return []
            where = "WHERE e.dominio_id = %s"
            params.append(int(domain.get("id") or 0))
        rows = self._fetchall(
            f"""
            SELECT
                e.id,
                e.dominio_id,
                d.codigo_dominio,
                e.estado_origen,
                e.estado_destino,
                e.actor,
                e.motivo,
                e.source,
                e.run_id,
                e.trace_id,
                e.created_at
            FROM ia_dev_estado_dominio AS e
            JOIN {self.tabla_catalogo_dominios} AS d ON d.id = e.dominio_id
            {where}
            ORDER BY e.id DESC
            LIMIT %s
            """,
            [*params, max(1, min(int(limit), 1000))],
        )
        payload: list[dict] = []
        for row in rows:
            payload.append(
                {
                    "id": int(row[0]),
                    "dominio_id": int(row[1]),
                    "codigo_dominio": str(row[2] or ""),
                    "estado_origen": str(row[3] or ""),
                    "estado_destino": str(row[4] or ""),
                    "actor": str(row[5] or ""),
                    "motivo": str(row[6] or ""),
                    "source": str(row[7] or ""),
                    "run_id": str(row[8] or ""),
                    "trace_id": str(row[9] or ""),
                    "created_at": int(row[10] or 0),
                }
            )
        return payload

    def list_tablas_dominio(self, *, dominio_id: int, status: str | None = None, limit: int = 200) -> list[dict]:
        self.ensure_tables()
        where = "WHERE dominio_id = %s"
        params: list[Any] = [int(dominio_id)]
        if status:
            where += " AND estado = %s"
            params.append(str(status).strip().lower())
        rows = self._fetchall(
            f"""
            SELECT
                id,
                dominio_id,
                schema_name,
                table_name,
                table_fqn,
                nombre_tabla_logico,
                rol_tabla,
                es_principal,
                source_of_truth,
                source_ref,
                estado,
                metadata_json
            FROM {self.tabla_catalogo_tablas_dominio}
            {where}
            ORDER BY table_fqn
            LIMIT %s
            """,
            [*params, max(1, min(int(limit), 1000))],
        )
        payload: list[dict] = []
        for row in rows:
            payload.append(
                {
                    "id": int(row[0]),
                    "dominio_id": int(row[1]),
                    "schema_name": str(row[2] or ""),
                    "table_name": str(row[3] or ""),
                    "table_fqn": str(row[4] or ""),
                    "nombre_tabla_logico": str(row[5] or ""),
                    "rol_tabla": str(row[6] or ""),
                    "es_principal": bool(row[7]),
                    "source_of_truth": str(row[8] or ""),
                    "source_ref": str(row[9] or ""),
                    "estado": str(row[10] or ""),
                    "metadata": self._from_json(row[11], {}),
                }
            )
        return payload

    def list_columnas_dominio(self, *, dominio_id: int, status: str | None = None, limit: int = 500) -> list[dict]:
        # Tabla retirada: las columnas se resuelven desde ai_dictionary.dd_campos.
        return []

    def list_relaciones_dominio(self, *, dominio_id: int, status: str | None = None, limit: int = 500) -> list[dict]:
        self.ensure_tables()
        where = "WHERE r.dominio_id = %s"
        params: list[Any] = [int(dominio_id)]
        if status:
            where += " AND r.estado = %s"
            params.append(str(status).strip().lower())
        rows = self._fetchall(
            f"""
            SELECT
                r.id,
                r.dominio_id,
                r.tabla_origen_id,
                r.tabla_destino_id,
                tor.table_fqn,
                tde.table_fqn,
                r.nombre_relacion,
                r.tipo_join,
                r.condicion_join_sql,
                r.cardinalidad,
                r.es_interdominio,
                r.nivel_confianza,
                r.source_of_truth,
                r.estado
            FROM ia_dev_relaciones AS r
            LEFT JOIN {self.tabla_catalogo_tablas_dominio} AS tor ON tor.id = r.tabla_origen_id
            LEFT JOIN {self.tabla_catalogo_tablas_dominio} AS tde ON tde.id = r.tabla_destino_id
            {where}
            ORDER BY r.id
            LIMIT %s
            """,
            [*params, max(1, min(int(limit), 3000))],
        )
        payload: list[dict] = []
        for row in rows:
            payload.append(
                {
                    "id": int(row[0]),
                    "dominio_id": int(row[1]),
                    "tabla_origen_id": int(row[2]),
                    "tabla_destino_id": int(row[3]),
                    "tabla_origen_fqn": str(row[4] or ""),
                    "tabla_destino_fqn": str(row[5] or ""),
                    "nombre_relacion": str(row[6] or ""),
                    "tipo_join": str(row[7] or ""),
                    "condicion_join_sql": str(row[8] or ""),
                    "cardinalidad": str(row[9] or ""),
                    "es_interdominio": bool(row[10]),
                    "nivel_confianza": float(row[11] or 0.0),
                    "source_of_truth": str(row[12] or ""),
                    "estado": str(row[13] or ""),
                }
            )
        return payload

    def list_capacidades_dominio(self, *, dominio_id: int, status: str | None = None, limit: int = 200) -> list[dict]:
        self.ensure_tables()
        where = "WHERE dominio_id = %s"
        params: list[Any] = [int(dominio_id)]
        if status:
            where += " AND estado = %s"
            params.append(str(status).strip().lower())
        rows = self._fetchall(
            f"""
            SELECT
                id,
                dominio_id,
                capability_id,
                capability_key,
                tipo_tarea,
                filtros_soportados_json,
                group_by_soportados_json,
                metricas_soportadas_json,
                policy_tags_json,
                rollout_flag,
                handler_class,
                estado,
                version
            FROM ia_dev_capacidades
            {where}
            ORDER BY capability_id
            LIMIT %s
            """,
            [*params, max(1, min(int(limit), 1000))],
        )
        payload: list[dict] = []
        for row in rows:
            payload.append(
                {
                    "id": int(row[0]),
                    "dominio_id": int(row[1]),
                    "capability_id": str(row[2] or ""),
                    "capability_key": str(row[3] or ""),
                    "tipo_tarea": str(row[4] or ""),
                    "filtros_soportados": self._from_json(row[5], []),
                    "group_by_soportados": self._from_json(row[6], []),
                    "metricas_soportadas": self._from_json(row[7], []),
                    "policy_tags": self._from_json(row[8], []),
                    "rollout_flag": str(row[9] or ""),
                    "handler_class": str(row[10] or ""),
                    "estado": str(row[11] or ""),
                    "version": int(row[12] or 1),
                }
            )
        return payload

    def list_skills_dominio(self, *, dominio_id: int, status: str | None = None, limit: int = 200) -> list[dict]:
        self.ensure_tables()
        where = "WHERE dominio_id = %s"
        params: list[Any] = [int(dominio_id)]
        if status:
            where += " AND estado = %s"
            params.append(str(status).strip().lower())
        rows = self._fetchall(
            f"""
            SELECT
                id,
                dominio_id,
                skill_code,
                skill_type,
                metadata_json,
                prompt_template,
                estado,
                version
            FROM ia_dev_skills
            {where}
            ORDER BY skill_code
            LIMIT %s
            """,
            [*params, max(1, min(int(limit), 1000))],
        )
        payload: list[dict] = []
        for row in rows:
            payload.append(
                {
                    "id": int(row[0]),
                    "dominio_id": int(row[1]),
                    "skill_code": str(row[2] or ""),
                    "skill_type": str(row[3] or ""),
                    "metadata": self._from_json(row[4], {}),
                    "prompt_template": str(row[5] or ""),
                    "estado": str(row[6] or ""),
                    "version": int(row[7] or 1),
                }
            )
        return payload

    def sync_dominios_desde_ai_dictionary(self, *, limit: int = 500) -> dict:
        self.ensure_tables()
        dictionary_table = str(os.getenv("IA_DEV_DICTIONARY_TABLE", "ai_dictionary.dd_dominios") or "").strip()
        if "." in dictionary_table:
            dictionary_schema = dictionary_table.split(".", 1)[0]
        else:
            dictionary_schema = "ai_dictionary"
        if not self._is_safe_identifier(dictionary_schema):
            return {"ok": False, "error": "invalid_dictionary_schema"}

        domain_rows = self._fetchall(
            f"""
            SELECT id, codigo, nombre, descripcion
            FROM {dictionary_schema}.dd_dominios
            WHERE activo = 1
            ORDER BY id
            LIMIT %s
            """,
            [max(1, min(int(limit), 2000))],
        )

        synced_domains = 0
        synced_tables = 0
        for row in domain_rows:
            dd_domain_id = int(row[0] or 0)
            codigo = self._normalize_company_domain_code(row[1])
            if codigo not in {"empleados", "ausentismo"}:
                continue
            nombre = self._canonical_business_domain_name(codigo)
            descripcion = str(row[3] or "")
            if not codigo:
                continue
            local_domain = self.upsert_dominio(
                codigo_dominio=codigo,
                nombre_dominio=nombre,
                objetivo_negocio=descripcion,
                entidad_principal="empresa",
                estado_dominio="planned",
                nivel_madurez="initial",
                nivel_confianza_esquema=0.60,
                source_of_truth="ai_dictionary",
                source_ref=f"{dictionary_schema}.dd_dominios:{dd_domain_id}",
            )
            local_domain_id = int(local_domain.get("id") or 0)
            if local_domain_id <= 0:
                continue
            synced_domains += 1
            self._execute(
                """
                INSERT INTO ia_dev_auditoria_semantica (
                    entity_type,
                    entity_id,
                    change_type,
                    change_source,
                    before_json,
                    after_json,
                    version_from,
                    version_to,
                    actor,
                    run_id,
                    trace_id,
                    created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    "dominio",
                    str(local_domain_id),
                    "sync",
                    "ai_dictionary",
                    self._to_json({}),
                    self._to_json({"codigo_dominio": codigo, "nombre_dominio": nombre}),
                    0,
                    int(local_domain.get("version") or 1),
                    "system_sync",
                    "",
                    "",
                    self._now(),
                ],
            )

            table_rows = self._fetchall(
                f"""
                SELECT
                    id,
                    schema_name,
                    table_name,
                    alias_negocio,
                    descripcion
                FROM {dictionary_schema}.dd_tablas
                WHERE activo = 1
                  AND dominio_id = %s
                ORDER BY id
                LIMIT %s
                """,
                [dd_domain_id, 2000],
            )
            for trow in table_rows:
                schema_name = str(trow[1] or "").strip()
                table_name = str(trow[2] or "").strip()
                if not table_name:
                    continue
                table_fqn = f"{schema_name}.{table_name}".strip(".").lower()
                self.upsert_tabla_dominio(
                    dominio_id=local_domain_id,
                    schema_name=schema_name,
                    table_name=table_name,
                    table_fqn=table_fqn,
                    nombre_tabla_logico=str(trow[3] or ""),
                    rol_tabla="dataset",
                    es_principal=False,
                    source_of_truth="ai_dictionary",
                    source_ref=f"{dictionary_schema}.dd_tablas:{int(trow[0] or 0)}",
                    estado="active",
                    metadata={"descripcion": str(trow[4] or "")},
                )
                synced_tables += 1

        return {
            "ok": True,
            "dictionary_schema": dictionary_schema,
            "synced_domains": synced_domains,
            "synced_tables": synced_tables,
        }

    def _resolve_dictionary_schema(self) -> str | None:
        dictionary_table = str(os.getenv("IA_DEV_DICTIONARY_TABLE", "ai_dictionary.dd_dominios") or "").strip()
        dictionary_schema = dictionary_table.split(".", 1)[0] if "." in dictionary_table else "ai_dictionary"
        if not self._is_safe_identifier(dictionary_schema):
            return None
        return dictionary_schema

    def _dictionary_column_type(self, *, schema: str, table_name: str, column_name: str) -> str | None:
        if not self._is_safe_identifier(schema):
            return None
        if not self._is_safe_identifier(table_name):
            return None
        if not self._is_safe_identifier(column_name):
            return None
        row = self._fetchone(
            """
            SELECT COLUMN_TYPE
            FROM information_schema.columns
            WHERE table_schema = %s
              AND table_name = %s
              AND column_name = %s
            LIMIT 1
            """,
            [schema, table_name, column_name],
        )
        if not row or not row[0]:
            return None
        column_type = str(row[0] or "").strip().lower()
        if not re.match(r"^[a-z0-9(),\s]+$", column_type):
            return None
        return column_type

    def ensure_ia_dev_capacidades_columna_table(self) -> dict:
        """
        Crea la tabla canonica de capacidades funcionales por columna
        y su relacion (FK) con dd_campos.
        """
        dictionary_schema = self._resolve_dictionary_schema()
        if not dictionary_schema:
            return {"ok": False, "error": "invalid_dictionary_schema"}
        campo_id_type = self._dictionary_column_type(
            schema=dictionary_schema,
            table_name="dd_campos",
            column_name="id",
        ) or "bigint"

        self._execute(
            f"""
            CREATE TABLE IF NOT EXISTS {dictionary_schema}.ia_dev_capacidades_columna (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                campo_id {campo_id_type} NOT NULL,
                supports_filter TINYINT(1) NOT NULL DEFAULT 0,
                supports_group_by TINYINT(1) NOT NULL DEFAULT 0,
                supports_metric TINYINT(1) NOT NULL DEFAULT 0,
                supports_dimension TINYINT(1) NOT NULL DEFAULT 0,
                is_date TINYINT(1) NOT NULL DEFAULT 0,
                is_identifier TINYINT(1) NOT NULL DEFAULT 0,
                is_chart_dimension TINYINT(1) NOT NULL DEFAULT 0,
                is_chart_measure TINYINT(1) NOT NULL DEFAULT 0,
                allowed_operators_json LONGTEXT NULL,
                allowed_aggregations_json LONGTEXT NULL,
                normalization_strategy VARCHAR(120) NULL,
                priority INT NOT NULL DEFAULT 0,
                active TINYINT(1) NOT NULL DEFAULT 1,
                created_at BIGINT NOT NULL,
                updated_at BIGINT NOT NULL,
                UNIQUE KEY uq_ia_dev_capacidades_columna_campo (campo_id),
                KEY idx_ia_dev_capacidades_columna_active (active),
                CONSTRAINT fk_ia_dev_capacidades_columna_dd_campos
                    FOREIGN KEY (campo_id) REFERENCES {dictionary_schema}.dd_campos (id)
                    ON UPDATE CASCADE
                    ON DELETE CASCADE
            )
            """
        )
        view_created = False
        try:
            # Alias compatible solicitado por negocio.
            self._execute(
                f"""
                CREATE OR REPLACE VIEW {dictionary_schema}.dd_capacidades_campo AS
                SELECT
                    id,
                    campo_id,
                    supports_filter,
                    supports_group_by,
                    supports_metric,
                    supports_dimension,
                    is_date,
                    is_identifier,
                    is_chart_dimension,
                    is_chart_measure,
                    allowed_operators_json,
                    allowed_aggregations_json,
                    normalization_strategy,
                    priority,
                    active,
                    created_at,
                    updated_at
                FROM {dictionary_schema}.ia_dev_capacidades_columna
                """
            )
            view_created = True
        except Exception:
            view_created = False
        return {
            "ok": True,
            "dictionary_schema": dictionary_schema,
            "table_name": "ia_dev_capacidades_columna",
            "compat_view_created": bool(view_created),
        }

    def consolidate_column_capability_tables(
        self,
        *,
        drop_legacy_table: bool = True,
    ) -> dict:
        """
        Consolida metadata funcional de columnas en la tabla canónica:
        - destino: ia_dev_capacidades_columna
        - legacy: dd_campos_semantic_profile (si existe)
        """
        ensure = self.ensure_ia_dev_capacidades_columna_table()
        if not ensure.get("ok"):
            return ensure

        dictionary_schema = str(ensure.get("dictionary_schema") or "ai_dictionary")
        legacy_table = "dd_campos_semantic_profile"
        target_table = "ia_dev_capacidades_columna"

        legacy_meta = self._fetchone(
            """
            SELECT table_type
            FROM information_schema.tables
            WHERE table_schema = %s
              AND table_name = %s
            LIMIT 1
            """,
            [dictionary_schema, legacy_table],
        )
        if not legacy_meta:
            return {
                "ok": True,
                "dictionary_schema": dictionary_schema,
                "target_table": target_table,
                "legacy_table": legacy_table,
                "legacy_exists": False,
                "migrated_rows": 0,
                "dropped_legacy_table": False,
            }
        if str(legacy_meta[0] or "").upper() != "BASE TABLE":
            return {
                "ok": True,
                "dictionary_schema": dictionary_schema,
                "target_table": target_table,
                "legacy_table": legacy_table,
                "legacy_exists": True,
                "legacy_type": str(legacy_meta[0] or ""),
                "migrated_rows": 0,
                "dropped_legacy_table": False,
                "reason": "legacy_not_base_table",
            }

        rows = self._fetchall(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = %s
              AND table_name = %s
            """,
            [dictionary_schema, legacy_table],
        )
        legacy_columns = {
            str(item[0] or "").strip().lower()
            for item in rows
            if item and item[0]
        }

        def expr(*names: str, default: str = "NULL") -> str:
            for name in names:
                clean = str(name or "").strip().lower()
                if clean and clean in legacy_columns:
                    return f"l.{clean}"
            return default

        target_before = self._fetchone(
            f"SELECT COUNT(*) FROM {dictionary_schema}.{target_table}",
            [],
        )
        target_before_count = int((target_before or [0])[0] or 0)
        legacy_count_row = self._fetchone(
            f"SELECT COUNT(*) FROM {dictionary_schema}.{legacy_table}",
            [],
        )
        legacy_count = int((legacy_count_row or [0])[0] or 0)

        insert_sql = f"""
            INSERT INTO {dictionary_schema}.{target_table} (
                campo_id, supports_filter, supports_group_by, supports_metric, supports_dimension,
                is_date, is_identifier, is_chart_dimension, is_chart_measure,
                allowed_operators_json, allowed_aggregations_json, normalization_strategy,
                priority, active, created_at, updated_at
            )
            SELECT
                {expr("campo_id", "id_campo", default="NULL")} AS campo_id,
                COALESCE({expr("supports_filter", "soporta_filtro", "es_filtro", default="NULL")}, 0),
                COALESCE({expr("supports_group_by", "soporta_group_by", "es_group_by", default="NULL")}, 0),
                COALESCE({expr("supports_metric", "soporta_metrica", "es_metrica", default="NULL")}, 0),
                COALESCE({expr("supports_dimension", "soporta_dimension", default="NULL")}, 0),
                COALESCE({expr("is_date", "es_fecha", default="NULL")}, 0),
                COALESCE({expr("is_identifier", "es_identificador", default="NULL")}, 0),
                COALESCE({expr("is_chart_dimension", "es_chart_dimension", default="NULL")}, 0),
                COALESCE({expr("is_chart_measure", "es_chart_measure", default="NULL")}, 0),
                {expr("allowed_operators_json", "operadores_permitidos_json", default="NULL")},
                {expr("allowed_aggregations_json", "agregaciones_permitidas_json", default="NULL")},
                {expr("normalization_strategy", "estrategia_normalizacion", default="NULL")},
                COALESCE({expr("priority", "prioridad", default="NULL")}, 0),
                COALESCE({expr("active", "activo", default="NULL")}, 1),
                COALESCE({expr("created_at", "creado_en", default="NULL")}, {self._now()}),
                COALESCE({expr("updated_at", "actualizado_en", default="NULL")}, {self._now()})
            FROM {dictionary_schema}.{legacy_table} AS l
            WHERE {expr("campo_id", "id_campo", default="NULL")} IS NOT NULL
            ON DUPLICATE KEY UPDATE
                supports_filter = VALUES(supports_filter),
                supports_group_by = VALUES(supports_group_by),
                supports_metric = VALUES(supports_metric),
                supports_dimension = VALUES(supports_dimension),
                is_date = VALUES(is_date),
                is_identifier = VALUES(is_identifier),
                is_chart_dimension = VALUES(is_chart_dimension),
                is_chart_measure = VALUES(is_chart_measure),
                allowed_operators_json = VALUES(allowed_operators_json),
                allowed_aggregations_json = VALUES(allowed_aggregations_json),
                normalization_strategy = VALUES(normalization_strategy),
                priority = VALUES(priority),
                active = VALUES(active),
                updated_at = VALUES(updated_at)
        """
        self._execute(insert_sql)

        target_after = self._fetchone(
            f"SELECT COUNT(*) FROM {dictionary_schema}.{target_table}",
            [],
        )
        target_after_count = int((target_after or [0])[0] or 0)

        dropped_legacy = False
        if drop_legacy_table:
            self._execute(f"DROP TABLE IF EXISTS {dictionary_schema}.{legacy_table}")
            dropped_legacy = True

        # Reafirma vista de compatibilidad en caso de drop/create.
        self.ensure_ia_dev_capacidades_columna_table()

        return {
            "ok": True,
            "dictionary_schema": dictionary_schema,
            "target_table": target_table,
            "legacy_table": legacy_table,
            "legacy_exists": True,
            "legacy_rows": legacy_count,
            "target_rows_before": target_before_count,
            "target_rows_after": target_after_count,
            "migrated_rows": max(target_after_count - target_before_count, 0),
            "dropped_legacy_table": dropped_legacy,
        }

    def backfill_ia_dev_capacidades_columna_from_dd_campos(self) -> dict:
        """
        Pobla capacidades por columna tomando metadata base de dd_campos
        cuando no exista aún fila en la tabla canónica.
        """
        ensure = self.ensure_ia_dev_capacidades_columna_table()
        if not ensure.get("ok"):
            return ensure

        dictionary_schema = str(ensure.get("dictionary_schema") or "ai_dictionary")
        rows = self._fetchall(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = %s
              AND table_name = 'dd_campos'
            """,
            [dictionary_schema],
        )
        dd_cols = {
            str(item[0] or "").strip().lower()
            for item in rows
            if item and item[0]
        }
        if "id" not in dd_cols:
            return {
                "ok": False,
                "dictionary_schema": dictionary_schema,
                "error": "dd_campos_missing_id",
            }

        def cexpr(name: str, default: str = "NULL") -> str:
            clean = str(name or "").strip().lower()
            if clean in dd_cols:
                return f"c.{clean}"
            return default

        count_before = int((self._fetchone(
            f"SELECT COUNT(*) FROM {dictionary_schema}.ia_dev_capacidades_columna",
            [],
        ) or [0])[0] or 0)

        now = self._now()
        insert_sql = f"""
            INSERT INTO {dictionary_schema}.ia_dev_capacidades_columna (
                campo_id, supports_filter, supports_group_by, supports_metric, supports_dimension,
                is_date, is_identifier, is_chart_dimension, is_chart_measure,
                allowed_operators_json, allowed_aggregations_json, normalization_strategy,
                priority, active, created_at, updated_at
            )
            SELECT
                c.id,
                COALESCE({cexpr("es_filtro", default="0")}, 0),
                COALESCE({cexpr("es_group_by", default="0")}, 0),
                COALESCE({cexpr("es_metrica", default="0")}, 0),
                COALESCE({cexpr("es_group_by", default="0")}, 0),
                CASE
                    WHEN LOWER(COALESCE({cexpr("tipo_dato_tecnico", default="''")}, '')) REGEXP 'date|time'
                      OR LOWER(COALESCE({cexpr("column_name", default="''")}, '')) LIKE 'fecha%%'
                      OR LOWER(COALESCE({cexpr("campo_logico", default="''")}, '')) LIKE 'fecha%%'
                    THEN 1 ELSE 0
                END,
                CASE
                    WHEN LOWER(COALESCE({cexpr("column_name", default="''")}, '')) REGEXP 'cedula|ident|documento|id_empleado'
                      OR LOWER(COALESCE({cexpr("campo_logico", default="''")}, '')) REGEXP 'cedula|ident|documento|id_empleado'
                    THEN 1 ELSE 0
                END,
                COALESCE({cexpr("es_group_by", default="0")}, 0),
                COALESCE({cexpr("es_metrica", default="0")}, 0),
                NULL,
                NULL,
                'dd_campos_bootstrap',
                0,
                COALESCE({cexpr("activo", default="1")}, 1),
                COALESCE(UNIX_TIMESTAMP({cexpr("creado_en", default="NULL")}), {now}),
                {now}
            FROM {dictionary_schema}.dd_campos AS c
            WHERE c.id IS NOT NULL
            ON DUPLICATE KEY UPDATE
                campo_id = ia_dev_capacidades_columna.campo_id
        """
        self._execute(insert_sql)

        count_after = int((self._fetchone(
            f"SELECT COUNT(*) FROM {dictionary_schema}.ia_dev_capacidades_columna",
            [],
        ) or [0])[0] or 0)

        return {
            "ok": True,
            "dictionary_schema": dictionary_schema,
            "table_name": "ia_dev_capacidades_columna",
            "rows_before": count_before,
            "rows_after": count_after,
            "rows_inserted": max(count_after - count_before, 0),
        }

    def ensure_dd_campos_semantic_profile_table(self) -> dict:
        """
        Alias legacy: mantiene compatibilidad llamando a la tabla canonica.
        """
        return self.ensure_ia_dev_capacidades_columna_table()

    def upsert_ia_dev_capacidades_columna(
        self,
        *,
        campo_id: int,
        supports_filter: bool = False,
        supports_group_by: bool = False,
        supports_metric: bool = False,
        supports_dimension: bool = False,
        is_date: bool = False,
        is_identifier: bool = False,
        is_chart_dimension: bool = False,
        is_chart_measure: bool = False,
        allowed_operators: list[str] | None = None,
        allowed_aggregations: list[str] | None = None,
        normalization_strategy: str | None = None,
        priority: int = 0,
        active: bool = True,
    ) -> dict:
        ensure = self.ensure_ia_dev_capacidades_columna_table()
        if not ensure.get("ok"):
            return ensure
        dictionary_schema = str(ensure.get("dictionary_schema") or "ai_dictionary")
        now = self._now()
        self._execute(
            f"""
            INSERT INTO {dictionary_schema}.ia_dev_capacidades_columna (
                campo_id, supports_filter, supports_group_by, supports_metric, supports_dimension,
                is_date, is_identifier, is_chart_dimension, is_chart_measure,
                allowed_operators_json, allowed_aggregations_json, normalization_strategy,
                priority, active, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                supports_filter = VALUES(supports_filter),
                supports_group_by = VALUES(supports_group_by),
                supports_metric = VALUES(supports_metric),
                supports_dimension = VALUES(supports_dimension),
                is_date = VALUES(is_date),
                is_identifier = VALUES(is_identifier),
                is_chart_dimension = VALUES(is_chart_dimension),
                is_chart_measure = VALUES(is_chart_measure),
                allowed_operators_json = VALUES(allowed_operators_json),
                allowed_aggregations_json = VALUES(allowed_aggregations_json),
                normalization_strategy = VALUES(normalization_strategy),
                priority = VALUES(priority),
                active = VALUES(active),
                updated_at = VALUES(updated_at)
            """,
            [
                int(campo_id),
                1 if supports_filter else 0,
                1 if supports_group_by else 0,
                1 if supports_metric else 0,
                1 if supports_dimension else 0,
                1 if is_date else 0,
                1 if is_identifier else 0,
                1 if is_chart_dimension else 0,
                1 if is_chart_measure else 0,
                self._to_json(list(allowed_operators or [])),
                self._to_json(list(allowed_aggregations or [])),
                str(normalization_strategy or "") or None,
                int(priority),
                1 if active else 0,
                now,
                now,
            ],
        )
        return {
            "ok": True,
            "campo_id": int(campo_id),
            "dictionary_schema": dictionary_schema,
            "table_name": "ia_dev_capacidades_columna",
        }

    def upsert_dd_campos_semantic_profile(
        self,
        *,
        campo_id: int,
        supports_filter: bool = False,
        supports_group_by: bool = False,
        supports_metric: bool = False,
        supports_dimension: bool = False,
        is_date: bool = False,
        is_identifier: bool = False,
        is_chart_dimension: bool = False,
        is_chart_measure: bool = False,
        allowed_operators: list[str] | None = None,
        allowed_aggregations: list[str] | None = None,
        normalization_strategy: str | None = None,
        priority: int = 0,
        active: bool = True,
    ) -> dict:
        # Alias legacy: ahora escribe en la tabla canonica.
        return self.upsert_ia_dev_capacidades_columna(
            campo_id=campo_id,
            supports_filter=supports_filter,
            supports_group_by=supports_group_by,
            supports_metric=supports_metric,
            supports_dimension=supports_dimension,
            is_date=is_date,
            is_identifier=is_identifier,
            is_chart_dimension=is_chart_dimension,
            is_chart_measure=is_chart_measure,
            allowed_operators=allowed_operators,
            allowed_aggregations=allowed_aggregations,
            normalization_strategy=normalization_strategy,
            priority=priority,
            active=active,
        )

    @staticmethod
    def _is_safe_identifier(value: str) -> bool:
        return bool(re.match(r"^[A-Za-z0-9_]+$", str(value or "")))

    # Session memory
    def upsert_session_memory(
        self,
        *,
        session_id: str,
        messages: list[dict],
        context: dict,
        trim_events: int,
        updated_at: int | None = None,
    ):
        self.ensure_tables()
        ts = int(updated_at or self._now())
        existing = self._fetchone(
            "SELECT session_id FROM ia_dev_session_memory WHERE session_id = %s LIMIT 1",
            [session_id],
        )
        if existing:
            self._execute(
                """
                UPDATE ia_dev_session_memory
                SET messages_json = %s,
                    context_json = %s,
                    trim_events = %s,
                    updated_at = %s
                WHERE session_id = %s
                """,
                [
                    self._to_json(messages),
                    self._to_json(context),
                    int(trim_events),
                    ts,
                    session_id,
                ],
            )
            return

        self._execute(
            """
            INSERT INTO ia_dev_session_memory
                (session_id, messages_json, context_json, trim_events, updated_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            [
                session_id,
                self._to_json(messages),
                self._to_json(context),
                int(trim_events),
                ts,
            ],
        )

    def get_session_memory(self, session_id: str) -> dict | None:
        self.ensure_tables()
        row = self._fetchone(
            """
            SELECT session_id, messages_json, context_json, trim_events, updated_at
            FROM ia_dev_session_memory
            WHERE session_id = %s
            LIMIT 1
            """,
            [session_id],
        )
        if not row:
            return None
        return {
            "session_id": str(row[0]),
            "messages": self._from_json(row[1], []),
            "context": self._from_json(row[2], {}),
            "trim_events": int(row[3] or 0),
            "updated_at": int(row[4] or 0),
        }

    # User memory
    def upsert_user_memory(
        self,
        *,
        user_key: str,
        memory_key: str,
        memory_value: Any,
        sensitivity: str = "medium",
        source: str = "api",
        confidence: float = 1.0,
        expires_at: int | None = None,
    ):
        self.ensure_tables()
        now = self._now()
        existing = self._fetchone(
            """
            SELECT id
            FROM ia_dev_user_memory
            WHERE user_key = %s
              AND memory_key = %s
            LIMIT 1
            """,
            [user_key, memory_key],
        )
        if existing:
            self._execute(
                """
                UPDATE ia_dev_user_memory
                SET memory_value_json = %s,
                    sensitivity = %s,
                    source = %s,
                    confidence = %s,
                    expires_at = %s,
                    updated_at = %s
                WHERE user_key = %s
                  AND memory_key = %s
                """,
                [
                    self._to_json(memory_value),
                    sensitivity[:16],
                    source[:40],
                    max(0.0, min(float(confidence), 1.0)),
                    expires_at,
                    now,
                    user_key,
                    memory_key,
                ],
            )
            return

        self._execute(
            """
            INSERT INTO ia_dev_user_memory
                (user_key, memory_key, memory_value_json, sensitivity, source, confidence, expires_at, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                user_key,
                memory_key,
                self._to_json(memory_value),
                sensitivity[:16],
                source[:40],
                max(0.0, min(float(confidence), 1.0)),
                expires_at,
                now,
                now,
            ],
        )

    def get_user_memory_entry(self, *, user_key: str, memory_key: str) -> dict | None:
        self.ensure_tables()
        row = self._fetchone(
            """
            SELECT id, user_key, memory_key, memory_value_json, sensitivity, source, confidence, expires_at, created_at, updated_at
            FROM ia_dev_user_memory
            WHERE user_key = %s
              AND memory_key = %s
            LIMIT 1
            """,
            [user_key, memory_key],
        )
        if not row:
            return None
        return {
            "id": int(row[0]),
            "user_key": str(row[1] or ""),
            "memory_key": str(row[2] or ""),
            "memory_value": self._from_json(row[3], None),
            "sensitivity": str(row[4] or "medium"),
            "source": str(row[5] or "api"),
            "confidence": float(row[6] or 0.0),
            "expires_at": int(row[7]) if row[7] is not None else None,
            "created_at": int(row[8] or 0),
            "updated_at": int(row[9] or 0),
        }

    def list_user_memory(self, *, user_key: str, limit: int = 100) -> list[dict]:
        self.ensure_tables()
        safe_limit = max(1, min(int(limit), 500))
        now = self._now()
        rows = self._fetchall(
            """
            SELECT id, user_key, memory_key, memory_value_json, sensitivity, source, confidence, expires_at, created_at, updated_at
            FROM ia_dev_user_memory
            WHERE user_key = %s
              AND (expires_at IS NULL OR expires_at >= %s)
            ORDER BY updated_at DESC
            LIMIT %s
            """,
            [user_key, now, safe_limit],
        )
        return [
            {
                "id": int(row[0]),
                "user_key": str(row[1] or ""),
                "memory_key": str(row[2] or ""),
                "memory_value": self._from_json(row[3], None),
                "sensitivity": str(row[4] or "medium"),
                "source": str(row[5] or "api"),
                "confidence": float(row[6] or 0.0),
                "expires_at": int(row[7]) if row[7] is not None else None,
                "created_at": int(row[8] or 0),
                "updated_at": int(row[9] or 0),
            }
            for row in rows
        ]

    # Business memory
    def upsert_business_memory(
        self,
        *,
        domain_code: str,
        capability_id: str,
        memory_key: str,
        memory_value: Any,
        status: str = "active",
        source_type: str = "manual",
        approved_by: str | None = None,
        approved_at: int | None = None,
    ):
        self.ensure_tables()
        now = self._now()
        existing = self._fetchone(
            """
            SELECT id, version
            FROM ia_dev_business_memory
            WHERE domain_code = %s
              AND capability_id = %s
              AND memory_key = %s
            LIMIT 1
            """,
            [domain_code, capability_id, memory_key],
        )
        if existing:
            next_version = int(existing[1] or 1) + 1
            self._execute(
                """
                UPDATE ia_dev_business_memory
                SET memory_value_json = %s,
                    status = %s,
                    source_type = %s,
                    version = %s,
                    approved_by = %s,
                    approved_at = %s,
                    updated_at = %s
                WHERE id = %s
                """,
                [
                    self._to_json(memory_value),
                    status[:20],
                    source_type[:40],
                    next_version,
                    approved_by,
                    approved_at,
                    now,
                    int(existing[0]),
                ],
            )
            return

        self._execute(
            """
            INSERT INTO ia_dev_business_memory
                (domain_code, capability_id, memory_key, memory_value_json, status, source_type, version, approved_by, approved_at, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, 1, %s, %s, %s, %s)
            """,
            [
                domain_code[:64],
                capability_id[:120],
                memory_key[:120],
                self._to_json(memory_value),
                status[:20],
                source_type[:40],
                approved_by,
                approved_at,
                now,
                now,
            ],
        )

    def get_business_memory_entry(
        self,
        *,
        domain_code: str,
        capability_id: str,
        memory_key: str,
    ) -> dict | None:
        self.ensure_tables()
        row = self._fetchone(
            """
            SELECT id, domain_code, capability_id, memory_key, memory_value_json, status, source_type, version, approved_by, approved_at, created_at, updated_at
            FROM ia_dev_business_memory
            WHERE domain_code = %s
              AND capability_id = %s
              AND memory_key = %s
            LIMIT 1
            """,
            [domain_code, capability_id, memory_key],
        )
        if not row:
            return None
        return {
            "id": int(row[0]),
            "domain_code": str(row[1] or ""),
            "capability_id": str(row[2] or ""),
            "memory_key": str(row[3] or ""),
            "memory_value": self._from_json(row[4], None),
            "status": str(row[5] or ""),
            "source_type": str(row[6] or ""),
            "version": int(row[7] or 1),
            "approved_by": str(row[8]) if row[8] else None,
            "approved_at": int(row[9]) if row[9] is not None else None,
            "created_at": int(row[10] or 0),
            "updated_at": int(row[11] or 0),
        }

    def list_business_memory(
        self,
        *,
        domain_code: str | None = None,
        capability_id: str | None = None,
        memory_key_prefix: str | None = None,
        status: str | None = "active",
        limit: int = 100,
    ) -> list[dict]:
        self.ensure_tables()
        safe_limit = max(1, min(int(limit), 500))
        where: list[str] = ["1 = 1"]
        params: list[Any] = []
        if domain_code:
            where.append("domain_code = %s")
            params.append(domain_code)
        if capability_id:
            where.append("capability_id = %s")
            params.append(capability_id)
        if memory_key_prefix:
            where.append("memory_key LIKE %s")
            params.append(f"{memory_key_prefix}%")
        if status:
            where.append("status = %s")
            params.append(status)
        params.append(safe_limit)
        rows = self._fetchall(
            f"""
            SELECT id, domain_code, capability_id, memory_key, memory_value_json, status, source_type, version, approved_by, approved_at, created_at, updated_at
            FROM ia_dev_business_memory
            WHERE {" AND ".join(where)}
            ORDER BY updated_at DESC
            LIMIT %s
            """,
            params,
        )
        return [
            {
                "id": int(row[0]),
                "domain_code": str(row[1] or ""),
                "capability_id": str(row[2] or ""),
                "memory_key": str(row[3] or ""),
                "memory_value": self._from_json(row[4], None),
                "status": str(row[5] or ""),
                "source_type": str(row[6] or ""),
                "version": int(row[7] or 1),
                "approved_by": str(row[8]) if row[8] else None,
                "approved_at": int(row[9]) if row[9] is not None else None,
                "created_at": int(row[10] or 0),
                "updated_at": int(row[11] or 0),
            }
            for row in rows
        ]

    # Learned memory proposals
    def insert_learned_memory_proposal(self, proposal: dict):
        self.ensure_tables()
        self._execute(
            """
            INSERT INTO ia_dev_learned_memory_proposals
                (proposal_id, scope, status, proposer_user_key, source_run_id, candidate_key, candidate_value_json, reason,
                 sensitivity, domain_code, capability_id, policy_action, policy_id, idempotency_key, error, version, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                proposal["proposal_id"],
                proposal["scope"],
                proposal.get("status", "pending"),
                proposal.get("proposer_user_key"),
                proposal.get("source_run_id"),
                proposal.get("candidate_key"),
                self._to_json(proposal.get("candidate_value")),
                proposal.get("reason"),
                proposal.get("sensitivity", "medium"),
                proposal.get("domain_code"),
                proposal.get("capability_id"),
                proposal.get("policy_action"),
                proposal.get("policy_id"),
                proposal.get("idempotency_key"),
                proposal.get("error"),
                int(proposal.get("version") or 1),
                int(proposal.get("created_at") or self._now()),
                int(proposal.get("updated_at") or self._now()),
            ],
        )

    def get_learned_memory_proposal(self, proposal_id: str, *, for_update: bool = False) -> dict | None:
        self.ensure_tables()
        query = (
            """
            SELECT proposal_id, scope, status, proposer_user_key, source_run_id, candidate_key, candidate_value_json, reason,
                   sensitivity, domain_code, capability_id, policy_action, policy_id, idempotency_key, error, version, created_at, updated_at
            FROM ia_dev_learned_memory_proposals
            WHERE proposal_id = %s
            LIMIT 1
            """
            + (" FOR UPDATE" if for_update else "")
        )
        row = self._fetchone(query, [proposal_id])
        if not row:
            return None
        return {
            "proposal_id": str(row[0] or ""),
            "scope": str(row[1] or ""),
            "status": str(row[2] or ""),
            "proposer_user_key": str(row[3] or ""),
            "source_run_id": str(row[4]) if row[4] else None,
            "candidate_key": str(row[5] or ""),
            "candidate_value": self._from_json(row[6], None),
            "reason": str(row[7]) if row[7] else "",
            "sensitivity": str(row[8] or "medium"),
            "domain_code": str(row[9]) if row[9] else None,
            "capability_id": str(row[10]) if row[10] else None,
            "policy_action": str(row[11]) if row[11] else None,
            "policy_id": str(row[12]) if row[12] else None,
            "idempotency_key": str(row[13]) if row[13] else None,
            "error": str(row[14]) if row[14] else None,
            "version": int(row[15] or 1),
            "created_at": int(row[16] or 0),
            "updated_at": int(row[17] or 0),
        }

    def get_learned_memory_proposal_by_idempotency(self, idempotency_key: str) -> dict | None:
        self.ensure_tables()
        if not str(idempotency_key or "").strip():
            return None
        row = self._fetchone(
            """
            SELECT proposal_id
            FROM ia_dev_learned_memory_proposals
            WHERE idempotency_key = %s
            LIMIT 1
            """,
            [idempotency_key],
        )
        if not row:
            return None
        return self.get_learned_memory_proposal(str(row[0] or ""))

    def list_learned_memory_proposals(
        self,
        *,
        status: str | None = None,
        scope: str | None = None,
        proposer_user_key: str | None = None,
        limit: int = 30,
    ) -> list[dict]:
        self.ensure_tables()
        safe_limit = max(1, min(int(limit), 200))
        where: list[str] = ["1 = 1"]
        params: list[Any] = []
        if status:
            where.append("status = %s")
            params.append(status)
        if scope:
            where.append("scope = %s")
            params.append(scope)
        if proposer_user_key:
            where.append("proposer_user_key = %s")
            params.append(proposer_user_key)
        params.append(safe_limit)
        rows = self._fetchall(
            f"""
            SELECT proposal_id
            FROM ia_dev_learned_memory_proposals
            WHERE {" AND ".join(where)}
            ORDER BY created_at DESC
            LIMIT %s
            """,
            params,
        )
        result: list[dict] = []
        for row in rows:
            proposal = self.get_learned_memory_proposal(str(row[0]))
            if proposal:
                result.append(proposal)
        return result

    def update_learned_memory_proposal(self, proposal_id: str, updates: dict):
        self.ensure_tables()
        allowed = {
            "scope",
            "status",
            "reason",
            "sensitivity",
            "domain_code",
            "capability_id",
            "policy_action",
            "policy_id",
            "error",
            "version",
            "updated_at",
            "candidate_value",
        }
        sets: list[str] = []
        params: list[Any] = []
        for key, value in updates.items():
            if key not in allowed:
                continue
            if key == "candidate_value":
                sets.append("candidate_value_json = %s")
                params.append(self._to_json(value))
            else:
                sets.append(f"{key} = %s")
                params.append(value)
        if not sets:
            return
        params.append(proposal_id)
        self._execute(
            f"""
            UPDATE ia_dev_learned_memory_proposals
            SET {", ".join(sets)}
            WHERE proposal_id = %s
            """,
            params,
        )

    def insert_learned_memory_approval(self, approval: dict):
        self.ensure_tables()
        self._execute(
            """
            INSERT INTO ia_dev_learned_memory_approvals
                (proposal_id, action, actor_user_key, actor_role, comment, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            [
                approval.get("proposal_id"),
                approval.get("action"),
                approval.get("actor_user_key"),
                approval.get("actor_role"),
                approval.get("comment"),
                int(approval.get("created_at") or self._now()),
            ],
        )

    def list_learned_memory_approvals(self, *, proposal_id: str, limit: int = 20) -> list[dict]:
        self.ensure_tables()
        safe_limit = max(1, min(int(limit), 200))
        rows = self._fetchall(
            """
            SELECT id, proposal_id, action, actor_user_key, actor_role, comment, created_at
            FROM ia_dev_learned_memory_approvals
            WHERE proposal_id = %s
            ORDER BY id DESC
            LIMIT %s
            """,
            [proposal_id, safe_limit],
        )
        return [
            {
                "id": int(row[0]),
                "proposal_id": str(row[1] or ""),
                "action": str(row[2] or ""),
                "actor_user_key": str(row[3] or ""),
                "actor_role": str(row[4] or ""),
                "comment": str(row[5]) if row[5] else "",
                "created_at": int(row[6] or 0),
            }
            for row in rows
        ]

    # Workflow state
    def upsert_workflow_state(
        self,
        *,
        workflow_type: str,
        workflow_key: str,
        status: str,
        state: dict,
        retry_count: int = 0,
        lock_version: int = 1,
        next_retry_at: int | None = None,
        last_error: str | None = None,
    ):
        self.ensure_tables()
        now = self._now()
        existing = self._fetchone(
            """
            SELECT id
            FROM ia_dev_workflow_state
            WHERE workflow_key = %s
            LIMIT 1
            """,
            [workflow_key],
        )
        if existing:
            self._execute(
                """
                UPDATE ia_dev_workflow_state
                SET workflow_type = %s,
                    status = %s,
                    state_json = %s,
                    retry_count = %s,
                    lock_version = %s,
                    next_retry_at = %s,
                    last_error = %s,
                    updated_at = %s
                WHERE workflow_key = %s
                """,
                [
                    workflow_type,
                    status,
                    self._to_json(state),
                    int(retry_count),
                    int(lock_version),
                    next_retry_at,
                    last_error,
                    now,
                    workflow_key,
                ],
            )
            return
        self._execute(
            """
            INSERT INTO ia_dev_workflow_state
                (workflow_type, workflow_key, status, state_json, retry_count, lock_version, next_retry_at, last_error, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                workflow_type,
                workflow_key,
                status,
                self._to_json(state),
                int(retry_count),
                int(lock_version),
                next_retry_at,
                last_error,
                now,
                now,
            ],
        )

    def get_workflow_state(self, workflow_key: str, *, for_update: bool = False) -> dict | None:
        self.ensure_tables()
        query = (
            """
            SELECT id, workflow_type, workflow_key, status, state_json, retry_count, lock_version, next_retry_at, last_error, created_at, updated_at
            FROM ia_dev_workflow_state
            WHERE workflow_key = %s
            LIMIT 1
            """
            + (" FOR UPDATE" if for_update else "")
        )
        row = self._fetchone(query, [workflow_key])
        if not row:
            return None
        return {
            "id": int(row[0]),
            "workflow_type": str(row[1] or ""),
            "workflow_key": str(row[2] or ""),
            "status": str(row[3] or ""),
            "state": self._from_json(row[4], {}),
            "retry_count": int(row[5] or 0),
            "lock_version": int(row[6] or 1),
            "next_retry_at": int(row[7]) if row[7] is not None else None,
            "last_error": str(row[8]) if row[8] else None,
            "created_at": int(row[9] or 0),
            "updated_at": int(row[10] or 0),
        }

    def list_workflow_states(
        self,
        *,
        workflow_type: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        self.ensure_tables()
        safe_limit = max(1, min(int(limit), 500))
        where: list[str] = ["1 = 1"]
        params: list[Any] = []
        if workflow_type:
            where.append("workflow_type = %s")
            params.append(str(workflow_type))
        if status:
            where.append("status = %s")
            params.append(str(status))
        params.append(safe_limit)
        rows = self._fetchall(
            f"""
            SELECT id, workflow_type, workflow_key, status, state_json, retry_count, lock_version, next_retry_at, last_error, created_at, updated_at
            FROM ia_dev_workflow_state
            WHERE {" AND ".join(where)}
            ORDER BY updated_at DESC
            LIMIT %s
            """,
            params,
        )
        return [
            {
                "id": int(row[0]),
                "workflow_type": str(row[1] or ""),
                "workflow_key": str(row[2] or ""),
                "status": str(row[3] or ""),
                "state": self._from_json(row[4], {}),
                "retry_count": int(row[5] or 0),
                "lock_version": int(row[6] or 1),
                "next_retry_at": int(row[7]) if row[7] is not None else None,
                "last_error": str(row[8]) if row[8] else None,
                "created_at": int(row[9] or 0),
                "updated_at": int(row[10] or 0),
            }
            for row in rows
        ]

    # Memory audit
    def insert_memory_audit_event(
        self,
        *,
        event_type: str,
        memory_scope: str,
        entity_key: str,
        action: str,
        actor_type: str,
        actor_key: str,
        run_id: str | None = None,
        trace_id: str | None = None,
        before: Any = None,
        after: Any = None,
        meta: dict | None = None,
    ):
        self.ensure_tables()
        self._execute(
            """
            INSERT INTO ia_dev_memory_audit_trail
                (event_type, memory_scope, entity_key, action, actor_type, actor_key, run_id, trace_id, before_json, after_json, meta_json, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (event_type or "")[:64],
                (memory_scope or "")[:20],
                (entity_key or "")[:140],
                (action or "")[:24],
                (actor_type or "")[:24],
                (actor_key or "")[:128],
                (run_id or "")[:64] or None,
                (trace_id or "")[:64] or None,
                self._to_json(before) if before is not None else None,
                self._to_json(after) if after is not None else None,
                self._to_json(meta or {}),
                self._now(),
            ],
        )

    def list_memory_audit_events(
        self,
        *,
        memory_scope: str | None = None,
        entity_key: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        self.ensure_tables()
        safe_limit = max(1, min(int(limit), 1000))
        where: list[str] = ["1 = 1"]
        params: list[Any] = []
        if memory_scope:
            where.append("memory_scope = %s")
            params.append(memory_scope)
        if entity_key:
            where.append("entity_key = %s")
            params.append(entity_key)
        params.append(safe_limit)
        rows = self._fetchall(
            f"""
            SELECT id, event_type, memory_scope, entity_key, action, actor_type, actor_key, run_id, trace_id, before_json, after_json, meta_json, created_at
            FROM ia_dev_memory_audit_trail
            WHERE {" AND ".join(where)}
            ORDER BY id DESC
            LIMIT %s
            """,
            params,
        )
        return [
            {
                "id": int(row[0]),
                "event_type": str(row[1] or ""),
                "memory_scope": str(row[2] or ""),
                "entity_key": str(row[3] or ""),
                "action": str(row[4] or ""),
                "actor_type": str(row[5] or ""),
                "actor_key": str(row[6] or ""),
                "run_id": str(row[7]) if row[7] else None,
                "trace_id": str(row[8]) if row[8] else None,
                "before": self._from_json(row[9], None),
                "after": self._from_json(row[10], None),
                "meta": self._from_json(row[11], {}),
                "created_at": int(row[12] or 0),
            }
            for row in rows
        ]

    # Tickets
    def insert_ticket(
        self,
        *,
        ticket_id: str,
        category: str,
        title: str,
        description: str,
        session_id: str | None,
        created_at: int,
    ):
        self.ensure_tables()
        self._execute(
            """
            INSERT INTO ia_dev_tickets
                (ticket_id, category, title, description, session_id, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            [ticket_id, category, title, description, session_id, int(created_at)],
        )

    def get_ticket(self, ticket_id: str) -> dict | None:
        self.ensure_tables()
        row = self._fetchone(
            """
            SELECT ticket_id, category, title, description, session_id, created_at
            FROM ia_dev_tickets
            WHERE ticket_id = %s
            LIMIT 1
            """,
            [ticket_id],
        )
        if not row:
            return None
        return {
            "ticket_id": str(row[0]),
            "category": str(row[1] or ""),
            "title": str(row[2] or ""),
            "description": str(row[3] or ""),
            "session_id": str(row[4]) if row[4] else None,
            "created_at": int(row[5] or 0),
        }

    # Knowledge proposals
    def insert_knowledge_proposal(self, proposal: dict):
        self.ensure_tables()
        self._execute(
            """
            INSERT INTO ia_dev_knowledge_proposals (
                proposal_id, status, mode, proposal_type, name, description, domain_code,
                condition_sql, result_text, tables_related, priority, target_rule_id,
                session_id, requested_by, similar_rules_json, persistence_json, error,
                version, last_idempotency_key, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                proposal["proposal_id"],
                proposal["status"],
                proposal["mode"],
                proposal["proposal_type"],
                proposal["name"],
                proposal["description"],
                proposal["domain_code"],
                proposal["condition_sql"],
                proposal["result_text"],
                proposal["tables_related"],
                int(proposal["priority"]),
                proposal.get("target_rule_id"),
                proposal.get("session_id"),
                proposal["requested_by"],
                self._to_json(proposal.get("similar_rules") or []),
                self._to_json(proposal.get("persistence")) if proposal.get("persistence") is not None else None,
                proposal.get("error"),
                int(proposal.get("version") or 1),
                proposal.get("last_idempotency_key"),
                int(proposal["created_at"]),
                int(proposal["updated_at"]),
            ],
        )

    def get_knowledge_proposal(self, proposal_id: str, *, for_update: bool = False) -> dict | None:
        self.ensure_tables()
        query = (
            """
            SELECT proposal_id, status, mode, proposal_type, name, description, domain_code,
                   condition_sql, result_text, tables_related, priority, target_rule_id,
                   session_id, requested_by, similar_rules_json, persistence_json, error,
                   version, last_idempotency_key, created_at, updated_at
            FROM ia_dev_knowledge_proposals
            WHERE proposal_id = %s
            LIMIT 1
            """
            + (" FOR UPDATE" if for_update else "")
        )
        row = self._fetchone(query, [proposal_id])
        if not row:
            return None
        return {
            "proposal_id": str(row[0]),
            "status": str(row[1] or ""),
            "mode": str(row[2] or ""),
            "proposal_type": str(row[3] or ""),
            "name": str(row[4] or ""),
            "description": str(row[5] or ""),
            "domain_code": str(row[6] or ""),
            "condition_sql": str(row[7] or ""),
            "result_text": str(row[8] or ""),
            "tables_related": str(row[9] or ""),
            "priority": int(row[10] or 0),
            "target_rule_id": int(row[11]) if row[11] is not None else None,
            "session_id": str(row[12]) if row[12] else None,
            "requested_by": str(row[13] or ""),
            "similar_rules": self._from_json(row[14], []),
            "persistence": self._from_json(row[15], None),
            "error": str(row[16]) if row[16] else None,
            "version": int(row[17] or 1),
            "last_idempotency_key": str(row[18]) if row[18] else None,
            "created_at": int(row[19] or 0),
            "updated_at": int(row[20] or 0),
        }

    def list_knowledge_proposals(self, *, status: str | None = None, limit: int = 30) -> list[dict]:
        self.ensure_tables()
        safe_limit = max(1, min(int(limit), 100))
        if status:
            rows = self._fetchall(
                """
                SELECT proposal_id
                FROM ia_dev_knowledge_proposals
                WHERE status = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                [status, safe_limit],
            )
        else:
            rows = self._fetchall(
                """
                SELECT proposal_id
                FROM ia_dev_knowledge_proposals
                ORDER BY created_at DESC
                LIMIT %s
                """,
                [safe_limit],
            )
        result: list[dict] = []
        for row in rows:
            item = self.get_knowledge_proposal(str(row[0]))
            if item:
                result.append(item)
        return result

    def update_knowledge_proposal(self, proposal_id: str, updates: dict):
        self.ensure_tables()
        allowed = {
            "status",
            "condition_sql",
            "result_text",
            "tables_related",
            "priority",
            "target_rule_id",
            "similar_rules",
            "persistence",
            "error",
            "version",
            "last_idempotency_key",
            "updated_at",
        }
        sets: list[str] = []
        params: list = []
        for key, value in updates.items():
            if key not in allowed:
                continue
            if key == "similar_rules":
                sets.append("similar_rules_json = %s")
                params.append(self._to_json(value or []))
            elif key == "persistence":
                sets.append("persistence_json = %s")
                params.append(self._to_json(value) if value is not None else None)
            else:
                sets.append(f"{key} = %s")
                params.append(value)
        if not sets:
            return
        params.append(proposal_id)
        self._execute(
            f"""
            UPDATE ia_dev_knowledge_proposals
            SET {", ".join(sets)}
            WHERE proposal_id = %s
            """,
            params,
        )

    # Async jobs
    def insert_async_job(
        self,
        *,
        job_id: str,
        job_type: str,
        payload: dict,
        status: str,
        idempotency_key: str | None,
        run_after: int,
    ):
        self.ensure_tables()
        now = self._now()
        self._execute(
            """
            INSERT INTO ia_dev_async_jobs
                (job_id, job_type, status, payload_json, result_json, error, idempotency_key, created_at, updated_at, run_after)
            VALUES (%s, %s, %s, %s, NULL, NULL, %s, %s, %s, %s)
            """,
            [
                job_id,
                job_type,
                status,
                self._to_json(payload),
                idempotency_key,
                now,
                now,
                int(run_after),
            ],
        )

    def get_async_job_by_idempotency(self, idempotency_key: str) -> dict | None:
        self.ensure_tables()
        row = self._fetchone(
            """
            SELECT job_id, job_type, status, payload_json, result_json, error, idempotency_key, created_at, updated_at, run_after
            FROM ia_dev_async_jobs
            WHERE idempotency_key = %s
            LIMIT 1
            """,
            [idempotency_key],
        )
        return self._map_async_job(row)

    def list_pending_async_jobs(self, *, limit: int = 20) -> list[dict]:
        self.ensure_tables()
        now = self._now()
        rows = self._fetchall(
            """
            SELECT job_id, job_type, status, payload_json, result_json, error, idempotency_key, created_at, updated_at, run_after
            FROM ia_dev_async_jobs
            WHERE status = 'pending'
              AND run_after <= %s
            ORDER BY created_at ASC
            LIMIT %s
            """,
            [now, max(1, min(int(limit), 200))],
        )
        return [item for item in (self._map_async_job(row) for row in rows) if item]

    def claim_pending_async_jobs(self, *, limit: int = 20) -> list[dict]:
        self.ensure_tables()
        now = self._now()
        rows = self._fetchall(
            """
            SELECT job_id
            FROM ia_dev_async_jobs
            WHERE status = 'pending'
              AND run_after <= %s
            ORDER BY created_at ASC
            LIMIT %s
            """,
            [now, max(1, min(int(limit), 200))],
        )
        claimed: list[dict] = []
        for row in rows:
            job_id = str(row[0] or "").strip()
            if not job_id:
                continue
            with connections[self.db_alias].cursor() as cursor:
                cursor.execute(
                    self._prepare_sql(
                        """
                    UPDATE ia_dev_async_jobs
                    SET status = 'running',
                        updated_at = %s
                    WHERE job_id = %s
                      AND status = 'pending'
                    """
                    ),
                    [self._now(), job_id],
                )
                if int(cursor.rowcount or 0) != 1:
                    continue
            item = self.get_async_job(job_id)
            if item:
                claimed.append(item)
        return claimed

    def get_async_job(self, job_id: str) -> dict | None:
        self.ensure_tables()
        row = self._fetchone(
            """
            SELECT job_id, job_type, status, payload_json, result_json, error, idempotency_key, created_at, updated_at, run_after
            FROM ia_dev_async_jobs
            WHERE job_id = %s
            LIMIT 1
            """,
            [job_id],
        )
        return self._map_async_job(row)

    def update_async_job(
        self,
        *,
        job_id: str,
        status: str,
        result: dict | None = None,
        error: str | None = None,
    ):
        self.ensure_tables()
        now = self._now()
        self._execute(
            """
            UPDATE ia_dev_async_jobs
            SET status = %s,
                result_json = %s,
                error = %s,
                updated_at = %s
            WHERE job_id = %s
            """,
            [
                status,
                self._to_json(result) if result is not None else None,
                error,
                now,
                job_id,
            ],
        )

    def _map_async_job(self, row: tuple | None) -> dict | None:
        if not row:
            return None
        return {
            "job_id": str(row[0]),
            "job_type": str(row[1] or ""),
            "status": str(row[2] or ""),
            "payload": self._from_json(row[3], {}),
            "result": self._from_json(row[4], None),
            "error": str(row[5]) if row[5] else None,
            "idempotency_key": str(row[6]) if row[6] else None,
            "created_at": int(row[7] or 0),
            "updated_at": int(row[8] or 0),
            "run_after": int(row[9] or 0),
        }

    # Observability
    def insert_observability_event(
        self,
        *,
        event_type: str,
        source: str,
        duration_ms: int | None = None,
        tokens_in: int | None = None,
        tokens_out: int | None = None,
        cost_usd: float | None = None,
        meta: dict | None = None,
    ):
        self.ensure_tables()
        self._execute(
            """
            INSERT INTO ia_dev_observability_events
                (event_type, source, duration_ms, tokens_in, tokens_out, cost_usd, meta_json, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (event_type or "event")[:80],
                (source or "ia_dev")[:80],
                duration_ms,
                tokens_in,
                tokens_out,
                cost_usd,
                self._to_json(meta or {}),
                self._now(),
            ],
        )

    def get_observability_summary(
        self,
        *,
        window_seconds: int = 3600,
        limit: int = 2000,
        domain_code: str | None = None,
        generator: str | None = None,
        fallback_reason: str | None = None,
    ) -> dict:
        self.ensure_tables()
        safe_window = max(60, min(int(window_seconds), 604800))
        safe_limit = max(10, min(int(limit), 5000))
        since = self._now() - safe_window
        normalized_domain = str(domain_code or "").strip().lower()
        normalized_generator = str(generator or "").strip().lower()
        normalized_fallback_reason = str(fallback_reason or "").strip().lower()
        has_cause_filters = bool(normalized_domain or normalized_generator or normalized_fallback_reason)
        rows = self._fetchall(
            """
            SELECT event_type, source, duration_ms, tokens_in, tokens_out, cost_usd, created_at, meta_json
            FROM ia_dev_observability_events
            WHERE created_at >= %s
            ORDER BY id DESC
            LIMIT %s
            """,
            [since, safe_limit],
        )

        by_source: dict[str, dict] = defaultdict(
            lambda: {
                "events": 0,
                "durations_ms": [],
                "tokens_in": 0,
                "tokens_out": 0,
                "cost_usd": 0.0,
            }
        )
        by_event_type: dict[str, int] = defaultdict(int)

        total_events = 0
        total_tokens_in = 0
        total_tokens_out = 0
        total_cost_usd = 0.0
        all_durations: list[int] = []
        cause_events = 0
        cause_by_generator: dict[str, int] = defaultdict(int)
        cause_by_domain: dict[str, int] = defaultdict(int)
        cause_by_fallback_reason: dict[str, int] = defaultdict(int)
        cause_by_policy_reason: dict[str, int] = defaultdict(int)
        cause_confidences: list[float] = []
        cause_confidence_by_domain: dict[str, list[float]] = defaultdict(list)

        for row in rows:
            event_type = str(row[0] or "event")
            source = str(row[1] or "ia_dev")
            duration_ms = int(row[2]) if row[2] is not None else None
            tokens_in = int(row[3] or 0)
            tokens_out = int(row[4] or 0)
            cost_usd = float(row[5] or 0.0)
            meta = self._from_json(row[7], {}) if len(row) > 7 else {}
            is_cause_event = event_type == "cause_diagnostics_result"

            if has_cause_filters:
                if not is_cause_event:
                    continue
                meta_domain = str((meta or {}).get("domain_code") or "").strip().lower()
                meta_generator = str((meta or {}).get("generator") or "").strip().lower()
                meta_fallback_reason = str((meta or {}).get("fallback_reason") or "").strip().lower()
                if normalized_domain and meta_domain != normalized_domain:
                    continue
                if normalized_generator and meta_generator != normalized_generator:
                    continue
                if normalized_fallback_reason and meta_fallback_reason != normalized_fallback_reason:
                    continue

            total_events += 1
            total_tokens_in += tokens_in
            total_tokens_out += tokens_out
            total_cost_usd += cost_usd
            by_event_type[event_type] += 1

            bucket = by_source[source]
            bucket["events"] += 1
            bucket["tokens_in"] += tokens_in
            bucket["tokens_out"] += tokens_out
            bucket["cost_usd"] += cost_usd
            if duration_ms is not None:
                bucket["durations_ms"].append(duration_ms)
                all_durations.append(duration_ms)

            if is_cause_event:
                cause_events += 1
                generator_bucket = str((meta or {}).get("generator") or "unknown").strip().lower() or "unknown"
                domain_bucket = str((meta or {}).get("domain_code") or "unknown").strip().lower() or "unknown"
                fallback_bucket = str((meta or {}).get("fallback_reason") or "").strip()
                policy_bucket = str((meta or {}).get("policy_reason") or "").strip()
                confidence = None
                try:
                    confidence = float((meta or {}).get("confidence") or 0.0)
                except Exception:
                    confidence = None

                cause_by_generator[generator_bucket] += 1
                cause_by_domain[domain_bucket] += 1
                if fallback_bucket:
                    cause_by_fallback_reason[fallback_bucket] += 1
                if policy_bucket:
                    cause_by_policy_reason[policy_bucket] += 1
                if confidence is not None:
                    cause_confidences.append(confidence)
                    cause_confidence_by_domain[domain_bucket].append(confidence)

        def _duration_stats(values: list[int]) -> dict:
            if not values:
                return {"count": 0, "avg_ms": 0, "p95_ms": 0, "max_ms": 0}
            ordered = sorted(values)
            p95_idx = min(len(ordered) - 1, int(len(ordered) * 0.95))
            return {
                "count": len(ordered),
                "avg_ms": int(sum(ordered) / len(ordered)),
                "p95_ms": int(ordered[p95_idx]),
                "max_ms": int(ordered[-1]),
            }

        def _float_stats(values: list[float]) -> dict[str, Any]:
            if not values:
                return {"count": 0, "avg": 0.0, "p95": 0.0, "min": 0.0, "max": 0.0}
            ordered = sorted(float(item) for item in values)
            p95_idx = min(len(ordered) - 1, int(len(ordered) * 0.95))
            return {
                "count": len(ordered),
                "avg": round(float(sum(ordered) / len(ordered)), 5),
                "p95": round(float(ordered[p95_idx]), 5),
                "min": round(float(ordered[0]), 5),
                "max": round(float(ordered[-1]), 5),
            }

        sources: dict[str, dict] = {}
        for source, bucket in by_source.items():
            durations = list(bucket.pop("durations_ms", []))
            sources[source] = {
                **bucket,
                "cost_usd": round(float(bucket["cost_usd"]), 8),
                "latency": _duration_stats(durations),
            }

        return {
            "window_seconds": safe_window,
            "sample_size": total_events,
            "event_types": dict(by_event_type),
            "totals": {
                "events": total_events,
                "tokens_in": total_tokens_in,
                "tokens_out": total_tokens_out,
                "cost_usd": round(total_cost_usd, 8),
                "latency": _duration_stats(all_durations),
            },
            "cause_diagnostics": {
                "events": cause_events,
                "by_generator": dict(cause_by_generator),
                "by_domain": dict(cause_by_domain),
                "by_fallback_reason": dict(cause_by_fallback_reason),
                "by_policy_reason": dict(cause_by_policy_reason),
                "confidence": _float_stats(cause_confidences),
                "confidence_by_domain": {
                    str(domain or ""): _float_stats(values)
                    for domain, values in cause_confidence_by_domain.items()
                },
            },
            "sources": sources,
        }
