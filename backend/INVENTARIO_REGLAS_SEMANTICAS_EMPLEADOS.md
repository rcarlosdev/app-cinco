# Reglas semanticas hardcodeadas de empleados

## Resumen

Lectura focal actualizada para la migracion anti-hardcode de `empleados` sin tocar `QueryExecutionPlanner`, `fallback_policy`, SQL ni runtime general.

Superficies revisadas:

- `backend/apps/ia_dev/domains/empleados/handler.py`
- `backend/apps/ia_dev/application/semantic/query_intent_resolver.py`
- `backend/apps/ia_dev/application/semantic/semantic_business_resolver.py`
- `backend/apps/ia_dev/application/semantic/semantic_normalization_service.py`
- `backend/apps/ia_dev/application/contracts/agent_contracts/empleados_agent.yaml`
- `backend/apps/ia_dev/services/ai_dictionary_remediation_service.py`
- tests focales de `empleados`, `query_intelligence` y `chat runtime metadata`

## Diagnostico por regla

| Regla actual | Donde vive hoy | Clasificacion | Observacion |
| --- | --- | --- | --- |
| Regex de cedula, nombre, movil y keywords `info/detalle/ficha` | `domains/empleados/handler.py::_extraer_filtros_desde_texto` | `compatibility_layer` | Sigue como rescate acotado, pero el binding principal de detalle ya queda gobernado por `Capability Pack`. |
| Keywords de estado activo/inactivo, egreso, retiro, baja, rotacion | `handler.py::_resolve_target_status`, `semantic_normalization_service.py`, `query_intent_resolver.py` | `assistive_heuristic` | Deben quedar gobernadas por sinonimia/reglas y no repartidas entre capas. |
| Alias `personal`, `colaboradores`, `personas`, `rrhh` | `semantic_normalization_service.py`, `DomainRegistry`, `AIDictionaryRemediationService` | `compatibility_layer` | Ya existe base en `ai_dictionary`, pero aun hay duplicados Python. |
| Canonizacion `labor -> tipo_labor` | `handler.py`, `reglas.yaml`, normalizacion semantica | `assistive_heuristic` | Buena candidata a regla declarativa unica. |
| Cumpleanos por `fnacimiento_month` y `birth_month` | `Capability Pack`, `SemanticCapabilityRegistry`, `handler`, planner | `authoritative_layer` + `shadow_fallback` acotado | Ya quedan gobernados por pack para mes, `este mes`, `por mes` y agrupaciones seguras. Legacy solo queda para `hoy`, `proximos`, campo fecha no gobernado o metadata insuficiente. |
| Rotacion y ventana temporal por defecto | `query_intent_resolver.py`, `semantic_business_resolver.py`, handler | `compatibility_layer` | Sigue mezclando negocio y heuristica temporal. |
| Personal activo/inactivo por defecto | `reglas.yaml`, `semantic_business_resolver.py`, handler | `authoritative_layer` | Regla ya estable y de bajo riesgo para migrar primero al pack. |
| Agrupaciones por area, cargo, sede, carpeta, supervisor, movil | `Capability Pack`, `SemanticCapabilityRegistry`, `handler` | `authoritative_layer` | Ya quedan gobernadas por `selection_rules` del pack; legacy solo rescata dimensiones no declaradas, ambiguedad o gaps de metadata. |
| Detalle por cedula, movil, nombre y filtros organizacionales declarados | `Capability Pack`, `SemanticCapabilityRegistry`, `handler` | `authoritative_layer` | Ya queda gobernado por `selection_rules` del pack con fallback legacy solo para entidad no verificable, filtro no declarado, ambiguedad o metadata insuficiente. |
| Mappings `intent -> capability` de empleados | `query_execution_planner.py`, `semantic_orchestrator_service.py`, contrato del agente | `compatibility_layer` | Siguen repartidos entre planner, orchestrator y contrato. |
| Response profiles de empleados | `Capability Pack`, handler y response assembly | `authoritative_layer` | El detalle seguro ya publica solo columnas gobernadas y saneadas desde el pack. |
| Certificados de alturas proximos a vencer/vencidos | planner SQL assist, diccionario, tests | `compatibility_layer` | Ruta moderna vigente y estable; se deja trazada como pendiente del pack para no romperla. |
| Missingness y filtros de campos incompletos | `query_intent_resolver.py`, `semantic_business_resolver.py` | `technical_guardrail` | Debe seguir protegido por normalizacion tecnica hasta modelar mejor sus operadores. |
| Ocultamiento de fotos y telefonos personales | handler y perfiles actuales implicitos | `technical_guardrail` | No se deben exponer por defecto; se formaliza como limitacion declarada del pack. |

## Capability map actual

- `empleados.count.active.v1`
  - cubre hoy: conteo simple, agrupaciones, parte de rotacion y rescates de rutas modernas
  - ruta actual: `handler` y `sql_assisted`
- `empleados.detail.v1`
  - cubre hoy: detalle seguro por cedula, movil, nombre y filtros organizacionales declarados
  - ruta actual: `handler`

## Templates/intents candidatos

- `count_entities_by_status`
  - fase actual: migrado
  - capability objetivo: `empleados.count.active.v1`
- `aggregate_by_group_and_period`
  - fase actual: migrado al pack
  - capability objetivo: `empleados.count.active.v1`
- `detail_by_entity_and_period`
  - fase actual: migrado al pack
  - capability objetivo: `empleados.detail.v1`
- `count_records_by_period`
  - fase actual: migrado al pack
  - capability objetivo: `empleados.count.active.v1`
  - caso principal: cumpleanos por mes
- `heights_certificate_summary`
  - fase actual: candidato pendiente
  - caso principal: certificados de alturas proximos a vencer

## Response profiles candidatos

- `empleados.count.active.summary`
- `empleados.count.grouped.summary`
- `empleados.detail.safe_table`
- `empleados.birthday.summary`
- `empleados.certificados_alturas.summary`

## Selection rules vigentes

- `count_entities_by_status`
  - requiere `estado in {ACTIVO, INACTIVO}`
  - no permite identificador puntual
  - no permite `group_by`
  - excluye `birthday`, `turnover`, `heights_certificate_validity` y `missingness`
- `aggregate_by_group_and_period`
  - estado valido + `group_by` en `area/cargo/sede/carpeta/supervisor/movil`
  - sin identificador puntual
  - excluye `birthday`, `turnover`, `heights_certificate_validity` y `missingness`
  - deja fallback solo para dimension no declarada, ambiguedad o metadata gap
- `detail_by_entity_and_period`
  - identificadores/filtros gobernados: `cedula|movil|nombre|area|cargo|supervisor|carpeta|sede|tipo_labor|estado`
  - deja fallback solo para entidad no verificable, filtro no declarado, ambiguedad o metadata insuficiente
- `count_records_by_period`
  - `required_business_concepts = birthday`
  - `period_fields = fnacimiento_month`
  - `date_semantics = birthday_month`
  - deja fallback solo para periodo ambiguo, campo fecha no gobernado o metadata insuficiente
- `heights_certificate_summary`
  - proxima fase: `field_match=certificado_alturas_*` + `estado_empleado=ACTIVO` + `tipo_labor=OPERATIVO`

## Evals minimos vigentes

- `personal activo hoy` -> `source=capability_pack`
- `cantidad empleados inactivos` -> `source=capability_pack`
- `empleados por area` -> `source=capability_pack`
- `cuantos empleados hay por cargo` -> `source=capability_pack`
- `agrupa empleados activos por sede` -> `source=capability_pack`
- `distribucion de personal por carpeta` -> `source=capability_pack`
- `empleados por supervisor` -> `source=capability_pack`
- `tecnicos por movil` -> `source=capability_pack`
- `detalle del empleado 123456` -> `source=capability_pack`
- `datos del tecnico 123456` -> `source=capability_pack`
- `empleados del movil TIRAN224` -> `source=capability_pack`
- `mostrar personal de la sede norte` -> `source=capability_pack`
- `mostrar personal por supervisor` -> `source=capability_pack`
- `listar empleados inactivos` -> `source=capability_pack`
- `distribucion de personal` -> `source=legacy_shadow_fallback`, `legacy_retained_reason=empleados.limit.grouped_population_ambiguous_request`
- `informacion del empleado por cedula` -> `source=legacy_shadow_fallback`, `legacy_retained_reason=empleados.limit.detail_ambiguous_request`
- `cumpleanos de mayo` -> `source=capability_pack`
- `empleados que cumplen anos este mes` -> `source=capability_pack`
- `cumpleanos por mes` -> `source=capability_pack`
- `cumpleanos de mayo por area` -> `source=capability_pack`
- `cumpleanos de hoy` -> `source=legacy_shadow_fallback`, `legacy_retained_reason=empleados.limit.birthday_ambiguous_period`
- `proximos cumpleanos de empleados activos` -> `source=legacy_shadow_fallback`, `legacy_retained_reason=empleados.limit.birthday_ambiguous_period`
- `certificados de altura proximos a vencer del personal activo operativo` -> mantener ruta moderna y traza pending pack
- detalle gobernado -> sin exponer `link_foto`, `imagen_empleado`, `password`, `codigo_sap`, `celular_personal`, `celular_alterno`
