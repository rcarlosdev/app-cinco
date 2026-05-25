# Operacion Runtime Multiagente

## Objetivo

Guia operativa corta para correr el runtime task-first en modo enterprise sin alterar su autoridad base.

Principios vigentes:

- GPT coordina.
- El runtime valida.
- Las tools ejecutan.
- Approvals gobiernan.
- Evidence-first.
- `QueryExecutionPlanner`, `ai_dictionary`, `Tool Registry`, `OpenAI Gateway`, `Agents Runtime`, `Approval Runtime` y `Background Runtime` mantienen su autoridad vigente.

## Validaciones de arranque

Verificar antes de despliegue:

- `OPENAI_API_KEY` o `IA_DEV_OPENAI_API_KEY` presente si el entorno usa OpenAI.
- `IA_DEV_OPENAI_TIMEOUT_SECONDS` y `IA_DEV_OPENAI_RETRIES` alineados con SLOs del entorno.
- `IA_DEV_MAX_TOOL_LOOP_ROUNDS`
- `IA_DEV_MAX_TOOL_CALLS_PER_RUN`
- `IA_DEV_MAX_REPEAT_TOOL_CALLS`
- `IA_DEV_MAX_BACKGROUND_RETRIES`
- `IA_DEV_MAX_BACKGROUND_DURATION_SECONDS`
- `IA_DEV_MAX_APPROVAL_WAIT_SECONDS`
- `IA_DEV_OBSERVABILITY_ENABLED`

## Health checks operativos

Revisar como minimo:

- `task_state.state.runtime_metrics`
- `task_state.state.governance`
- `task_state.state.background`
- `task_state.state.approvals`
- `task_state.state.dead_letter`
- `observability` summary por dominio
- `RuntimeGovernanceService.build_monitor_summary(...)`
- `RuntimeGovernanceService.build_pilot_report(...)` cuando aplique
- `RuntimeGovernanceService.build_runtime_operations_summary(...)`
- `RuntimeGovernanceService.build_task_trace_explorer(...)`

Endpoints operativos vigentes:

- `GET /ia-dev/observability/summary/`
- `GET /ia-dev/runtime/operations/summary/`
- `GET/POST /ia-dev/runtime/semantic-gaps/`
- `GET /ia-dev/runtime/tasks/explorer/?run_id=<run_id>`
- `GET /ia-dev/runtime/tasks/explorer/?resume_token=<resume_token>`
- `GET /ia-dev/runtime/tasks/explorer/?background_run_id=<background_run_id>`
- `GET /ia-dev/runtime/governance/health/?domain=<dominio>&days=<n>`

## Alertas recomendadas

Abrir incidente si aparece cualquiera de estas condiciones:

- `dead_letter.dead_lettered = true`
- `background.run_status` en `failed` o `expired`
- `approval_status = awaiting_approval` por encima del limite de espera
- `tool_loop_repeat_detected`
- `tool_loop_call_limit_exceeded`
- `runtime_only_fallback_count` creciente en monitoreo
- `satisfaction_review_failed_count` creciente en monitoreo

## Troubleshooting

1. Validar `correlation_id`, `run_id` y `trace_id` en `task_state.state.correlation`.
2. Revisar `tool_execution_trace`, `agent_trace`, `handoff_trace`, `approval_trace` y `background_trace`.
3. Usar `runtime/tasks/explorer` para ver la corrida con:
   - `trace_counts`
   - `history_tail`
   - `runtime_metrics`
   - `governance`
   - trazas saneadas
4. Confirmar si el fallo fue por:
   - limite de loop
   - approval expirado
   - timeout de background
   - dead-letter por retries agotados
5. Si hay datos sensibles en evidencia, revisar la version saneada persistida y no reconstruir payloads crudos desde logs.

## Rollback y degradacion

- Si falla el runtime endurecido, mantener la misma arquitectura y degradar por policy existente, no por bypass manual.
- No desactivar approvals para “recuperar” operacion.
- No habilitar SQL libre.
- No reactivar flows destructivos.

## Modo mantenimiento

Recomendacion operativa:

- detener corridas largas nuevas
- dejar polling y lectura de estado habilitados
- permitir cancelacion segura
- evitar resumes masivos hasta validar aprobaciones pendientes y deadlines

## Checklist de produccion

- Limites de loop activos
- Redaccion de datos sensibles activa
- Correlation IDs persistidos
- Approval wait con expiracion activa
- Background retries con dead-letter activo
- Runtime metrics persistidas en `task_state`
- Observabilidad y reportes de governance disponibles
- `runtime/operations/summary` disponible para backlog operativo
- `runtime/tasks/explorer` disponible para trazabilidad y soporte
- `runtime/governance/health` disponible para health enterprise por dominio

## Superficie saneada para soporte

En `/ia-dev/chat/` el runtime ya puede exponer `task.current_run.semantic_explanation`.

Capacidad operativa adicional estable:

- `/ia-dev/chat/` acepta `attachments` cuando una capability gobernada requiere evidencia tabular externa
- los adjuntos viajan como metadata saneada del runtime y no deben reconstruirse manualmente desde logs
- la validacion de seriales externos de proveedor usa esta ruta, sigue siendo read-only y ahora debe pasar a `Background Runtime` cuando el adjunto supera el umbral operativo de archivo grande

Uso operativo recomendado:

- usar este bloque para soporte funcional y explicacion al usuario final
- preferirlo frente a reconstrucciones manuales desde logs o traces crudos
- validar desde ahi:
  - dominio
  - intencion
  - filtros
  - capability y tool
  - validacion
  - evidencia
  - limitaciones
  - approvals
  - background
  - timeline saneado

Regla:

- si `semantic_explanation` contradice una traza cruda, manda el estado gobernado persistido y saneado
- no exponer prompts, chain-of-thought ni SQL sensible para soporte de primer nivel

Runbook corto para `inventory_provider_serial_validation`:

1. Confirmar en `semantic_explanation` o `evidence`:
   - `candidate_capability = inventory_provider_serial_validation`
   - `planner_route_hint = inventory.serial.validation.provider_file`
2. Revisar en la respuesta:
   - `tablas_consultadas`
   - `tablas_historicas_no_existian`
   - `historical_tables_missing`
3. Si no hubo exito, validar primero limitaciones declaradas:
   - `attachment_required`
   - `provider_file_empty`
   - `serial_column_not_detected`
   - `attachment_too_large`
4. Si el usuario reporta responsables inventados, revisar que el serial realmente haya quedado en estado que contiene `MOVIL`.
5. Si el adjunto del proveedor supera aproximadamente `1_000_000` bytes decodificados:
   - esperar `background_execution_queued:inventory_provider_serial_validation`
   - revisar `task.current_run.background`
   - usar `background_run_id` o `task_id` para progreso y reanudacion
   - mientras `run_status` este en `queued`, `running` o `resumed`, `GET /ia-dev/chat/task-status/` devolvera solo progreso liviano
   - validar en `task.current_run.evidence.background_progress`:
     - `rows_processed`
     - `total_estimated`
     - `percentage`
     - `phase`
     - `current_chunk`
     - `total_chunks`
     - `found_so_far`
     - `not_found_so_far`
     - `movil_so_far`
     - `enriched_responsible_so_far`
     - `attachment_name`
     - `artifact_id`
     - `updated_at`
   - no esperar `response_snapshot` completo ni tablas pesadas durante ejecucion activa
   - si aparece `artifact_id` antes del cierre, corresponde a un artifact parcial real y descargable
6. Para validacion operativa progresiva con archivo real usar:
   - `python manage.py validate_provider_serial_file --attachment-path "<ruta>" --output "<salida.json>"`

Estrategia runtime vigente para performance:

- primero consultar tablas actuales para todos los seriales
- despues consultar historicos solo para seriales todavia no resueltos
- enrichment de personal solo para coincidencias cuyo estado contiene `MOVIL`
- el lookup ahora intenta primero igualdad directa por lote
- la normalizacion costosa `UPPER(TRIM(CAST(... AS CHAR)))` queda solo como fallback para faltantes del lote exacto
- el checkpoint evita recomputar KPIs globales completos por chunk
- la acumulacion completa se reserva para artifact parcial/final y snapshot terminal

## Refuerzo operativo P7: Capability Packs en superficie saneada

Cuando un dominio use `Capability Pack`, la operacion debe verificar en `task.current_run.evidence` y `task.current_run.semantic_explanation`:

- `paquete_capacidad_usado`
- `version_paquete`
- `capacidades_declaradas`
- `reglas_declaradas`
- `perfiles_respuesta`
- `evaluaciones_asociadas`

Uso operativo recomendado:

- confirmar desde esta metadata que el dominio corrio con el pack esperado
- diferenciar un binding gobernado del pack frente a fallback sombreado
- revisar primero esta superficie antes de abrir trazas crudas del runtime

Regla:

- si falta `paquete_capacidad_usado` en un dominio que ya fue migrado a pack, tratarlo como desalineacion operativa
- el pack no cambia autoridad de ejecucion; solo mejora gobierno, continuidad y soporte

## Continuous Runtime Learning operativo

Nueva superficie operativa:

- `ia_dictionary.registro_brechas_semanticas`
- `RuntimeGovernanceService.build_runtime_operations_summary(...)` ahora incluye `continuous_runtime_learning`

Uso operativo recomendado:

- revisar primero:
  - `brechas_nuevas`
  - `brechas_por_categoria`
  - `brechas_por_dominio`
  - `brechas_por_capacidad`
  - `brechas_frecuentes`
  - `brechas_resueltas`
  - `brechas_con_sugerencia_metadata`
- usar esta superficie para backlog accionable de mejora
- no mezclarla con observability cruda:
  - observability = eventos
  - `registro_brechas_semanticas` = gaps accionables gobernados

Cuando debe aparecer una brecha:

- `blocked`
- aclaracion estructural requerida
- limitacion declarada
- capability sin resolver
- tool faltante
- evidencia insuficiente
- planner bloqueado
- fallback sombreado excesivo
- error tecnico controlado
- fallo P5 registrado explicitamente

Regla critica:

- `Continuous Runtime Learning` no corrige solo
- no escribe automaticamente en `dd_*`
- no modifica automaticamente `ai_dictionary`
- no crea automaticamente tools ni agentes
- solo registra, clasifica y propone mejora gobernada

## Operacion V1 de revision de brechas semanticas

Uso operativo recomendado del endpoint `runtime/semantic-gaps`:

- `GET`:
  - listar brechas pendientes
  - agrupar por categoria
  - ver brechas frecuentes
  - inspeccionar la propuesta asociada cuando exista
- `POST` con `action`:
  - `marcar_en_revision`
  - `marcar_descartada`
  - `marcar_resuelta`
  - `crear_propuesta`
  - `aprobar_propuesta`
  - `aplicar_propuesta`
  - `vincular_eval`

Reglas operativas:

- no aplicar propuestas sensibles si `estado_aprobacion != aprobada`
- usar `vincular_eval` para dejar:
  - `eval` nuevo
  - `eval` actualizado
  - caso real reproducible
- una brecha equivalente abierta no debe duplicarse en backlog
- soporte debe revisar primero:
  - `estado_revision`
  - `propuesta_mejora`
  - `evaluaciones_vinculadas`
  - `casos_reales_reproducibles`
  - `historial`
