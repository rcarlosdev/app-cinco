from __future__ import annotations

from typing import Any

from apps.ia_dev.services.sql_store import IADevSqlStore


class MemoryRepository:
    def __init__(self):
        self.store = IADevSqlStore()

    def set_user_memory(
        self,
        *,
        user_key: str,
        memory_key: str,
        memory_value: Any,
        sensitivity: str = "medium",
        source: str = "api",
        confidence: float = 1.0,
        expires_at: int | None = None,
    ) -> dict:
        self.store.upsert_user_memory(
            user_key=user_key,
            memory_key=memory_key,
            memory_value=memory_value,
            sensitivity=sensitivity,
            source=source,
            confidence=confidence,
            expires_at=expires_at,
        )
        return self.store.get_user_memory_entry(user_key=user_key, memory_key=memory_key) or {}

    def get_user_memory(self, *, user_key: str, limit: int = 100) -> list[dict]:
        return self.store.list_user_memory(user_key=user_key, limit=limit)

    def get_business_memory(
        self,
        *,
        domain_code: str | None = None,
        capability_id: str | None = None,
        memory_key_prefix: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        return self.store.list_business_memory(
            domain_code=domain_code,
            capability_id=capability_id,
            memory_key_prefix=memory_key_prefix,
            status="active",
            limit=limit,
        )

    def create_learning_proposal(self, proposal: dict) -> dict:
        self.store.insert_learned_memory_proposal(proposal)
        return self.store.get_learned_memory_proposal(str(proposal.get("proposal_id") or "")) or {}

    def get_learning_proposal_by_idempotency(self, idempotency_key: str) -> dict | None:
        return self.store.get_learned_memory_proposal_by_idempotency(idempotency_key)

    def list_learning_proposals(
        self,
        *,
        status: str | None = None,
        scope: str | None = None,
        proposer_user_key: str | None = None,
        limit: int = 30,
    ) -> list[dict]:
        return self.store.list_learned_memory_proposals(
            status=status,
            scope=scope,
            proposer_user_key=proposer_user_key,
            limit=limit,
        )

    def get_learning_proposal(self, proposal_id: str, *, for_update: bool = False) -> dict | None:
        return self.store.get_learned_memory_proposal(proposal_id, for_update=for_update)

    def update_learning_proposal(self, proposal_id: str, updates: dict):
        self.store.update_learned_memory_proposal(proposal_id, updates)

    def add_learning_approval(self, approval: dict):
        self.store.insert_learned_memory_approval(approval)

    def set_business_memory(
        self,
        *,
        domain_code: str,
        capability_id: str,
        memory_key: str,
        memory_value: Any,
        source_type: str,
        approved_by: str | None = None,
        approved_at: int | None = None,
    ) -> dict:
        self.store.upsert_business_memory(
            domain_code=domain_code,
            capability_id=capability_id,
            memory_key=memory_key,
            memory_value=memory_value,
            status="active",
            source_type=source_type,
            approved_by=approved_by,
            approved_at=approved_at,
        )
        return self.store.get_business_memory_entry(
            domain_code=domain_code,
            capability_id=capability_id,
            memory_key=memory_key,
        ) or {}

    def add_audit_event(
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
        self.store.insert_memory_audit_event(
            event_type=event_type,
            memory_scope=memory_scope,
            entity_key=entity_key,
            action=action,
            actor_type=actor_type,
            actor_key=actor_key,
            run_id=run_id,
            trace_id=trace_id,
            before=before,
            after=after,
            meta=meta or {},
        )

    def list_audit_events(
        self,
        *,
        memory_scope: str | None = None,
        entity_key: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        return self.store.list_memory_audit_events(
            memory_scope=memory_scope,
            entity_key=entity_key,
            limit=limit,
        )

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
    ) -> None:
        self.store.upsert_workflow_state(
            workflow_type=workflow_type,
            workflow_key=workflow_key,
            status=status,
            state=state,
            retry_count=retry_count,
            lock_version=lock_version,
            next_retry_at=next_retry_at,
            last_error=last_error,
        )

    def get_workflow_state(self, workflow_key: str, *, for_update: bool = False) -> dict | None:
        return self.store.get_workflow_state(workflow_key, for_update=for_update)

    def list_workflow_states(
        self,
        *,
        workflow_type: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        return self.store.list_workflow_states(
            workflow_type=workflow_type,
            status=status,
            limit=limit,
        )

    # Continuous runtime learning
    def get_gap_record_by_idempotency(self, idempotency_key: str) -> dict | None:
        return self.store.get_registro_brecha_semantica_por_clave(idempotency_key)

    def create_gap_record(self, payload: dict) -> dict:
        return self.store.insert_registro_brecha_semantica(payload)

    def get_gap_record(self, registro_id: int) -> dict | None:
        return self.store.get_registro_brecha_semantica(registro_id)

    def update_gap_record(self, registro_id: int, updates: dict) -> dict | None:
        return self.store.update_registro_brecha_semantica(registro_id, updates)

    def find_equivalent_open_gap_record(self, payload: dict) -> dict | None:
        return self.store.find_equivalent_open_gap_record(payload)

    def list_gap_records(
        self,
        *,
        estado_revision: str | None = None,
        categoria_brecha: str | None = None,
        dominio_detectado: str | None = None,
        capacidad_candidata: str | None = None,
        solo_con_sugerencia_metadata: bool = False,
        limit: int = 100,
    ) -> list[dict]:
        return self.store.list_registro_brechas_semanticas(
            estado_revision=estado_revision,
            categoria_brecha=categoria_brecha,
            dominio_detectado=dominio_detectado,
            capacidad_candidata=capacidad_candidata,
            solo_con_sugerencia_metadata=solo_con_sugerencia_metadata,
            limit=limit,
        )

    def summarize_gap_records(self, *, limit: int = 10) -> dict:
        return self.store.summarize_registro_brechas_semanticas(limit=limit)
