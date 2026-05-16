# Diagnostico P2-A: Semantic Capability Registry

## Alcance

- Tarea focalizada solo en P2-A.
- Sin refactor grande.
- Sin cambiar `ai_dictionary`.
- Sin mover la autoridad SQL fuera de `QueryExecutionPlanner`.
- Sin tocar `fallback_policy`, `task envelope`, `tool registry base`, `gateway`, `agents runtime`, approvals, background ni frontend.

## Pregunta central

Donde se decide hoy cada cosa y donde deberia decidirse una sola vez para el flujo:

- `intent`
- `entity`
- `filters`
- `output profile`
- `candidate_capability`
- `template_id`
- `tool_id`
- `planner_route`
- `execution_mode`
- `response_profile`

Objetivo de destino:

`intent + entity + filters + output -> candidate_capability -> tool_id -> planner_route -> response_profile`

## 1. Mapa de duplicaciones actuales

### Intent

- `matcher_semantico_gobernado_inventario.py`
  - decide `intencion` gobernada para P1 inventario.
- `semantic_inventory_resolver.py`
  - vuelve a inferir `intent` en `infer_for_arbitration(...)`.
- `query_intent_resolver.py`
  - decide `operation`, `entity`, `filters` y `template_id`.
- `semantic_orchestrator_service.py`
  - vuelve a decidir `intent` y `capability`.

Diagnostico:

- autoridad correcta hoy: `QueryIntentResolver` para `StructuredQueryIntent`, con apoyo del matcher gobernado en inventario.
- deuda: el orquestador no deberia redescubrir `intent`.

### Entity

- `matcher_semantico_gobernado_inventario.py`
  - extrae `cedula`, `movil`, `codigo`.
- `semantic_inventory_resolver.py`
  - vuelve a extraer y fusionar filtros y entidades.
- `query_intent_resolver.py`
  - `_extract_entity(...)` y merge con `match_gobernado`.
- `business_query_semantic_plan.py`
  - `_build_entity(...)` reconstruye entidad desde filtros.
- `semantic_orchestrator_service.py`
  - `_extract_entities(...)` lo vuelve a hacer para routing.

Diagnostico:

- autoridad correcta hoy: `BusinessQuerySemanticPlan.main_entity`.
- deuda: la extraccion repetida en resolver, intent resolver y orchestrator.

### Filters

- `matcher_semantico_gobernado_inventario.py`
  - normaliza `tipo`, `stock_scope`, `cedula`, `movil`, `codigo`.
- `semantic_inventory_resolver.py`
  - agrega filtros heredados y calcula `template_map`.
- `query_intent_resolver.py`
  - `_extract_filters(...)` y merge con `match_gobernado`.
- `semantic_orchestrator_service.py`
  - `_extract_filters(...)` otra vez para routing.
- `query_execution_planner.py`
  - interpreta filtros para decidir subruta SQL.

Diagnostico:

- autoridad correcta hoy: `resolved_query.normalized_filters` enriquecido por `business_query_semantic_plan`.
- duplicacion tolerable temporal: planner usando filtros ya normalizados para construir SQL.
- deuda: orchestrator y resolver duplican normalizacion.

### Output profile / response profile

- `business_query_semantic_plan.py`
  - `_resolve_output_profile(...)`
  - `_expected_output_for_capability(...)`
- `response_assembler.py`
  - vuelve a decidir narrativa y alcance por `row_keys`, `filters`, `template_id`, `business_concept`.
- `query_execution_planner.py`
  - decide `output_mode` tecnico y bloques suplementarios.
- `capability_catalog.py`
  - expone `response_shape`, pero hoy no gobierna inventario.

Diagnostico:

- autoridad correcta hoy: `BusinessQuerySemanticPlan.output` para el perfil de negocio esperado.
- duplicacion tolerable temporal: `QueryExecutionPlanner` define shape tecnico real del resultado.
- deuda: `response_assembler` sigue mezclando perfil narrativo con heuristicas por columnas devueltas.

### Candidate capability

- `matcher_semantico_gobernado_inventario.py`
  - devuelve `capacidad_candidata`.
- `semantic_inventory_resolver.py`
  - `template_map` induce capability indirectamente.
- `business_query_semantic_plan.py`
  - `_resolve_capability(...)`.
- `semantic_orchestrator_service.py`
  - `_resolve_intent_and_capability(...)`.
- `runtime_capability_adapter.py`
  - `_resolve_primary_capability_id(...)`
  - `_resolve_capability_from_resolved_query(...)`
- `query_execution_planner.py`
  - `_resolve_capability_id(...)`

Diagnostico:

- autoridad correcta hoy: ninguna unica. Es la duplicacion principal de P2-A.

### Template id

- `matcher_semantico_gobernado_inventario.py`
  - ya entrega `template_id`.
- `query_intent_resolver.py`
  - `_resolve_template_id(...)`.
- `semantic_inventory_resolver.py`
  - `template_map`.

Diagnostico:

- autoridad correcta hoy: `StructuredQueryIntent.template_id`.
- deuda: matcher, resolver y query intent resolver mantienen logica paralela.

### Tool id

- `tool_registry_service.py`
  - `get_tool_for_capability(...)`
  - `map_capability_to_tool(...)`
  - `resolve_tool_for_runtime(...)`
- `runtime_capability_adapter.py`
  - consume `tool_registry_service`, no inventa tool nueva.

Diagnostico:

- autoridad correcta hoy: `ToolRegistryService`.
- duplicacion tolerable temporal: adapter adjunta `tool_id` al plan runtime, pero no redefine el binding.

### Planner route / execution mode

- `semantic_orchestrator_service.py`
  - `ROUTE_BY_STRATEGY` y `recommended_route`.
- `query_execution_planner.py`
  - decide `strategy` real: `sql_assisted`, `capability`, `ask_context`, `fallback`.
- `runtime_capability_adapter.py`
  - `build_route(...)` decide `execute_capability` vs `use_legacy`.
- `tool_registry_service.py`
  - `execution_policy.mode` por tool.

Diagnostico:

- autoridad correcta hoy:
  - `QueryExecutionPlanner` para estrategia de ejecucion concreta.
  - `ToolRegistryService` para `execution_mode` por tool.
- deuda: el orquestador no deberia decidir una ruta final distinta a la del planner; solo deberia sugerir o validar un `planner_route_hint`.

## 2. Archivos y metodos donde hoy se decide capability/template/tool/planner route

### `backend/apps/ia_dev/domains/inventario_logistica/matcher_semantico_gobernado_inventario.py`

- `resolver(...)`
  - decide `intencion`, `capacidad_candidata`, `template_id`, `filtros`, `familias`, `incluye_serializados`.

### `backend/apps/ia_dev/domains/inventario_logistica/semantic_inventory_resolver.py`

- `infer_for_arbitration(...)`
  - decide `intent`, `filters`, `business_concept`, `candidate_tables`, `candidate_fields`, `expected_runtime_flow`.
- `resolve_query(...)`
  - decide `resolved_template_id` via `template_map`.

### `backend/apps/ia_dev/application/semantic/query_intent_resolver.py`

- `_resolve_rules(...)`
  - decide `domain`, `operation`, `entity`, `filters`, `group_by`, `template_id`.
- `_resolve_template_id(...)`
  - decide `template_id`.

### `backend/apps/ia_dev/domains/inventario_logistica/business_query_semantic_plan.py`

- `build_plan(...)`
  - consolida `candidate_capability`, `main_entity`, `normalized_filters`, `scope`, `output`.
- `_resolve_capability(...)`
  - decide `candidate_capability` desde `template_id`.
- `_resolve_output_profile(...)`
  - decide columnas y grano esperados.
- `_expected_output_for_capability(...)`
  - decide clase de salida esperada.

### `backend/apps/ia_dev/application/semantic/semantic_orchestrator_service.py`

- `_deterministic_output(...)`
  - decide `domain`, `intent`, `capability`, `recommended_route`.
- `_resolve_intent_and_capability(...)`
  - decide `intent` y `capability`.

### `backend/apps/ia_dev/application/runtime/runtime_capability_adapter.py`

- `_resolve_primary_capability_id(...)`
  - decide capability bootstrap desde `classification`, `execution_plan` o `resolved_query`.
- `_resolve_capability_from_resolved_query(...)`
  - decide capability para empleados/ausentismo desde `template_id` y `operation`.
- `_build_plan(...)`
  - materializa `tool_id` usando `ToolRegistryService`.
- `build_route(...)`
  - decide `execute_capability` vs `use_legacy`.

### `backend/apps/ia_dev/application/runtime/tool_registry_service.py`

- `get_tool_for_capability(...)`
  - binding capability -> tool.
- `map_capability_to_tool(...)`
  - binding capability -> tool id.
- `resolve_tool_for_runtime(...)`
  - seleccion final de tool segun flow/capability.

### `backend/apps/ia_dev/application/semantic/query_execution_planner.py`

- `plan(...)`
  - decide `strategy`.
- `_resolve_capability_id(...)`
  - remapea `template_id` a capability.
- `_build_inventory_sql_query(...)`
  - decide planner subroute por `template_id`.
- `_should_route_kardex_codigo_employee_to_employee(...)`
  - override especial de ruta.

### `backend/apps/ia_dev/domains/inventario_logistica/response_assembler.py`

- `_inventory_type_scope_label(...)`
  - decide etiqueta narrativa de familia.
- `build_inventory_business_response(...)`
  - decide perfil de narrativa final segun `row_keys`, `filters`, `template_id`, `business_concept`.

## 3. Clasificacion

### Autoridad correcta

- `ToolRegistryService`
  - binding capability -> tool.
- `QueryExecutionPlanner`
  - estrategia y autoridad de ejecucion SQL.
- `BusinessQuerySemanticPlan`
  - semantica estructurada de negocio previa al planner.

### Duplicacion tolerable temporal

- `matcher_semantico_gobernado_inventario.py`
  - puede seguir proponiendo `intent/entity/filters/candidate_capability` en P2 mientras exista fallback sombreado.
- `response_assembler.py`
  - puede seguir usando metadata de resultados mientras se migra a response profile estructurado.
- `runtime_capability_adapter.py`
  - puede seguir resolviendo capabilities no inventario en empleados/ausentismo como puente.

### Deuda tecnica

- `semantic_inventory_resolver.py`
  - `template_map` grande y especifico del dominio.
- `semantic_orchestrator_service.py`
  - redescubre `intent/capability/route` que ya deberian venir resueltos.
- `query_execution_planner.py`
  - remapea capability desde `template_id`; deberia consumir binding ya resuelto y solo validar si necesita overrides tecnicos.

### Hardcode a migrar

- regex de dominio inventario repetidos en `query_intent_resolver.py` y `semantic_orchestrator_service.py`
- `_resolve_template_id(...)` de inventario en `query_intent_resolver.py`
- `template_map` de `semantic_inventory_resolver.py`
- `_resolve_capability(...)` de `business_query_semantic_plan.py`
- rama inventario de `_resolve_capability_id(...)` en `query_execution_planner.py`
- rama inventario de `_resolve_intent_and_capability(...)` en `semantic_orchestrator_service.py`

## 4. Diseno propuesto: Semantic Capability Registry

Nombre sugerido:

- `SemanticCapabilityRegistry`

Ubicacion sugerida:

- `backend/apps/ia_dev/application/semantic/semantic_capability_registry.py`

Objetivo:

- ser la unica autoridad semantica de binding para:
  - `intent`
  - `entity`
  - `normalized_filters`
  - `output_profile`
  - `candidate_capability`
  - `template_id`
  - `planner_route_hint`
  - `response_profile`

No debe decidir:

- SQL
- `execute=True`
- fallback policy
- approval policy
- tool execution real

### Contratos sugeridos

#### Entrada principal

`SemanticBindingRequest`

- `domain`
- `message`
- `intent`
- `entity`
- `normalized_filters`
- `group_by`
- `semantic_context`
- `business_query_semantic_plan` opcional
- `source_hints`
  - `governed_match`
  - `classification`
  - `query_intent`

#### Salida principal

`SemanticBindingDecision`

- `domain`
- `intent`
- `entity`
- `normalized_filters`
- `output_profile`
  - `grain`
  - `columns`
  - `expected_output`
- `candidate_capability`
- `template_id`
- `planner_route_hint`
  - por ejemplo `inventory.material_stock.mobile`
- `response_profile`
  - por ejemplo `inventory.stock.mobile.detail`
- `evidence`
  - reglas usadas
  - sinonimos usados
  - memory keys usadas
  - fuente de verdad usada
- `warnings`
- `known_limitations`

### Fuentes de verdad

Orden de autoridad:

1. `ai_dictionary`
   - `dd_sinonimos`
   - `dd_reglas`
   - `dd_campos`
   - `dd_relaciones`
   - `dd_tablas`
   - `dd_capacidades_campo`
   - `ia_dev_capacidades_columna`
2. memoria confirmada `inventory.semantic.*`
3. matriz/metadata gobernada del dominio
4. patterns solo como `source_hint`, nunca como autoridad

### Como consulta ai_dictionary/capabilities

- lee sinonimia gobernada para normalizar `intent/entity/filter`
- lee capacidades declaradas para validar que la capability exista y a que dominio pertenece
- lee reglas simples para elegir `template_id`, `planner_route_hint` y `response_profile`
- si falta metadata para una capability, devuelve `known_limitations` y no inventa ruta

### Relacion con `BusinessQuerySemanticPlan`

- `BusinessQuerySemanticPlan` sigue existiendo.
- El registry se vuelve la autoridad interna para poblar:
  - `candidate_capability`
  - `output`
  - `scope` semantico derivado
  - `response_profile`
- `InventoryBusinessQueryPlanner` deja de mantener mappings propios y pasa a consumir el registry.

### Relacion con Tool Registry

- `ToolRegistryService` no cambia de autoridad.
- Sigue siendo el unico que decide capability -> tool.
- El `SemanticCapabilityRegistry` solo entrega `candidate_capability`.
- El `tool_id` se obtiene despues con:
  - `tool_registry_service.get_tool_for_capability(...)`

### Relacion con QueryExecutionPlanner

- `QueryExecutionPlanner` no cambia su autoridad SQL.
- Debe recibir un binding ya estabilizado:
  - `template_id`
  - `candidate_capability`
  - `planner_route_hint`
  - `response_profile`
- Puede mantener overrides tecnicos minimos:
  - bloqueo por metadata faltante
  - subruta SQL segura
  - ajuste tecnico de compilador
- No deberia remapear capability semantica salvo por compatibilidad temporal auditada.

### Reglas de separacion

- Registry semantico:
  - `intent/entity/filter/output -> capability/template/planner_route_hint/response_profile`
- Tool registry:
  - `capability -> tool_id + execution_policy + approval_policy`
- Planner:
  - `binding + semantic_context -> strategy + SQL seguro + evidence`
- Response assembler:
  - `response_profile + semantic_plan + execution metadata -> narrativa final`

## 5. Plan de implementacion P2-B por pasos pequenos

### P2-B1

- Crear `SemanticCapabilityRegistry` solo para inventario.
- Implementar API read-only.
- Sin cambiar aun planner ni adapter.

### P2-B2

- Mover al registry el mapping:
  - `intent + filters + output -> template_id`
  - `template_id -> candidate_capability`
  - `candidate_capability -> response_profile`
- Hacer que `InventoryBusinessQueryPlanner` lo consuma.

### P2-B3

- Hacer que `semantic_inventory_resolver.py` deje de usar `template_map`.
- Que pase a pedir `binding_decision` al registry.

### P2-B4

- Hacer que `query_intent_resolver.py` en inventario solo resuelva:
  - `domain`
  - `operation`
  - `entity`
  - `filters`
- y delegue `template_id` al registry.

### P2-B5

- Hacer que `semantic_orchestrator_service.py` consuma binding ya resuelto.
- Eliminar decision local de capability/ruta para inventario.

### P2-B6

- Hacer que `QueryExecutionPlanner` use `candidate_capability` y `planner_route_hint`.
- Mantener fallback de compatibilidad por una fase.

### P2-B7

- Reemplazar heuristicas de `response_assembler.py` por `response_profile`.

## 6. Riesgos y pruebas necesarias

### Riesgos

- divergencia temporal entre `template_id` viejo y `candidate_capability` nuevo
- romper rutas inventario no cubiertas por P1
- que el planner siga remapeando capability y esconda inconsistencias
- que `response_assembler` siga leyendo `row_keys` y produzca narrativas inconsistentes con el binding

### Pruebas minimas

- consultas P1 ya persistidas:
  - `que tiene asignado la cuadrilla TIRAN224`
  - `muestrame lo que tiene el movil TIRAN224`
  - `movimientos del tecnico 5098747`
  - `entradas y salidas de 5098747`
  - `solo material de claro de TIRAN224`
  - `ferreteria asignada al tecnico 5098747`
  - `actas SAP del empleado 5098747`
- assertion de binding:
  - `intent`
  - `entity`
  - `normalized_filters`
  - `candidate_capability`
  - `template_id`
  - `tool_id`
  - `planner_route_hint`
  - `response_profile`
- test anti-duplicacion:
  - una sola fuente gobierna capability/template/response profile para inventario
- test de compatibilidad:
  - `ToolRegistryService` y `QueryExecutionPlanner` siguen recibiendo datos esperados

## Decision arquitectonica propuesta

Queda propuesto y listo para P2-B:

- `SemanticCapabilityRegistry` como autoridad unica de binding semantico.
- `ToolRegistryService` como autoridad unica de tool binding.
- `QueryExecutionPlanner` como autoridad unica de estrategia y SQL seguro.

Estado P2-A:

- diagnostico completo
- diseno propuesto
- sin refactor grande implementado aun
