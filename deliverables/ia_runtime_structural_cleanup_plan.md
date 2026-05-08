# Plan De Limpieza Estructural Del Runtime IA

## Objetivo Arquitectonico Final

- Runtime objetivo unico:
  - `ChatApplicationService`
  - `IntentArbitrationService`
  - `QueryExecutionPlanner`
  - ejecucion: `sql_assisted | handler | fallback`
  - `ai_dictionary.dd_*` como source of truth estructural
- Todo lo que no entre en ese flujo debe quedar clasificado como:
  - eliminable
  - deprecable
  - fallback de compatibilidad

## Hallazgos Clave

- La entrada HTTP principal aun no entra directo al runtime final:
  - [backend/apps/ia_dev/views/chat_view.py](/c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/views/chat_view.py:9)
  - importa e instancia `IADevOrchestratorService`
- El wrapper legacy sigue siendo una segunda ruta completa:
  - [backend/apps/ia_dev/services/orchestrator_service.py](/c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/services/orchestrator_service.py:35)
  - `run()` intenta `ChatApplicationService` pero conserva fallback total a `run_legacy`
- `ChatApplicationService` ya es el runtime correcto, pero aun arrastra puentes transicionales:
  - [backend/apps/ia_dev/application/orchestration/chat_application_service.py](/c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/orchestration/chat_application_service.py:106)
  - sigue construyendo `IntentToCapabilityBridge`, `CapabilityPlanner`, `CapabilityRouter`, `LegacyResponseAssembler`, `DelegationCoordinator`, `ContextBuilder`, `SemanticBusinessResolver`, `LoopController`
- El contexto estructural aun mezcla YAML con `ai_dictionary`:
  - [backend/apps/ia_dev/application/semantic/semantic_business_resolver.py](/c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/semantic/semantic_business_resolver.py:21)
  - el docstring dice explicitamente: `YAML + catalogo DB + ai_dictionary`
- La gobernanza runtime aun depende de loaders estructurales por archivo:
  - [backend/apps/ia_dev/services/runtime_governance_service.py](/c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/services/runtime_governance_service.py:7)
  - usa `DomainContextLoader`
- La respuesta publica aun incluye trazas transicionales y ruido de observabilidad:
  - [backend/apps/ia_dev/application/orchestration/response_assembler.py](/c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/orchestration/response_assembler.py:14)
  - inyecta `capability_shadow`, `reasoning`, `query_intelligence`, `cause_diagnostics`, `proactive_loop`

## Duplicidades Identificadas

### 1. Resolucion De Intencion

- Ruta correcta:
  - `IntentArbitrationService`
- Rutas duplicadas:
  - `IntentClassifierService`
  - `_bootstrap_classification()` dentro de `ChatApplicationService`
  - alineacion posterior via `_apply_legacy_bridge_canonical_alignment()`
- Source of truth:
  - `IntentArbitrationService`
- Decision:
  - deprecar `IntentClassifierService`
  - eliminar uso productivo de `_bootstrap_classification()` como decision primaria
  - dejar cualquier heuristica residual solo como señal auxiliar, no como router

### 2. Resolucion De Dominio

- Ruta correcta:
  - dominio candidato + arbitraje final dentro de `IntentArbitrationService`
- Rutas duplicadas:
  - `IntentClassifierService`
  - `IntentToCapabilityBridge`
  - `CapabilityPlanner.plan_from_legacy()`
- Source of truth:
  - `IntentArbitrationService`
- Decision:
  - deprecar bridge y planner legacy-driven

### 3. Ruteo De Ejecucion

- Ruta correcta:
  - `QueryExecutionPlanner.plan()`
  - `sql_assisted | handler | fallback`
- Rutas duplicadas:
  - `CapabilityRouter`
  - ramas `legacy_runner`
  - `tool_*_service.py` usados como via principal desde wrapper
- Source of truth:
  - `QueryExecutionPlanner`
- Decision:
  - deprecar `CapabilityRouter`
  - encapsular `legacy_runner` como fallback aislado y no como ruta de primer nivel

### 4. Contexto Estructural

- Ruta correcta:
  - `DictionaryToolService` leyendo `ai_dictionary.dd_*`
- Rutas duplicadas:
  - `DomainContextLoader`
  - `DomainRegistry`
  - parte estructural de `SemanticBusinessResolver`
  - auditorias que comparan o cargan estructura desde YAML
- Source of truth:
  - `ai_dictionary.dd_*`
- Decision:
  - mover YAML a rol narrativo solamente
  - deprecar loaders estructurales de runtime

### 5. Ensamblado De Respuesta Y Observabilidad

- Ruta correcta:
  - metadata minima del runtime
- Rutas duplicadas o ruidosas:
  - `LegacyResponseAssembler`
  - `capability_shadow`
  - `reasoning_diagnostics`
  - `context_builder_resolved`
  - `runtime_wrapper_resolved`
- Source of truth:
  - metadata emitida por `ChatApplicationService` al final de la ejecucion
- Decision:
  - deprecar ensamblado legacy de trazas extendidas

## Clasificacion De Servicios Y Archivos

### Core

- [backend/apps/ia_dev/application/orchestration/chat_application_service.py](/c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/orchestration/chat_application_service.py:1)
- [backend/apps/ia_dev/services/intent_arbitration_service.py](/c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/services/intent_arbitration_service.py:1)
- [backend/apps/ia_dev/application/semantic/query_execution_planner.py](/c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/semantic/query_execution_planner.py:1)
- [backend/apps/ia_dev/services/dictionary_tool_service.py](/c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/services/dictionary_tool_service.py:1)
- [backend/apps/ia_dev/application/policies/query_execution_policy.py](/c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/policies/query_execution_policy.py:1)
- `join_aware_sql_service` y handlers modernos solo donde ya son parte del flujo del planner

### Deprecar

- [backend/apps/ia_dev/services/orchestrator_service.py](/c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/services/orchestrator_service.py:1)
- [backend/apps/ia_dev/services/intent_service.py](/c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/services/intent_service.py:1)
- [backend/apps/ia_dev/application/routing/capability_planner.py](/c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/routing/capability_planner.py:1)
- [backend/apps/ia_dev/application/routing/intent_to_capability_bridge.py](/c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/routing/intent_to_capability_bridge.py:1)
- [backend/apps/ia_dev/application/routing/capability_router.py](/c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/routing/capability_router.py:1)
- [backend/apps/ia_dev/application/orchestration/response_assembler.py](/c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/orchestration/response_assembler.py:1)
- [backend/apps/ia_dev/application/orchestration/loop_controller.py](/c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/orchestration/loop_controller.py:1)
- [backend/apps/ia_dev/application/delegation/delegation_coordinator.py](/c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/delegation/delegation_coordinator.py:1)
- [backend/apps/ia_dev/application/semantic/context_builder.py](/c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/semantic/context_builder.py:1)
- [backend/apps/ia_dev/application/delegation/domain_context_loader.py](/c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/delegation/domain_context_loader.py:1)
- [backend/apps/ia_dev/application/delegation/domain_registry.py](/c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/delegation/domain_registry.py:1)

### Mantener Solo Como Fallback O Compatibilidad

- `run_legacy` dentro de `orchestrator_service.py`
- [backend/apps/ia_dev/services/tool_ausentismo_service.py](/c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/services/tool_ausentismo_service.py:1)
- [backend/apps/ia_dev/services/tool_transport_service.py](/c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/services/tool_transport_service.py:1)
- YAML de dominio solo para:
  - narrativa
  - ejemplos
  - tono
  - presentacion

### Eliminables En Olas Posteriores

- [backend/apps/ia_dev/services/tool_attendance_service.py](/c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/services/tool_attendance_service.py:1)
- pruebas enfocadas en `capability_shadow`, `legacy bridge`, `intent_service` y `router` una vez se complete el cutover

## Flujo Principal Que Debe Quedar

```text
Request
  -> IADevChatView
  -> ChatApplicationService
  -> IntentArbitrationService
  -> QueryExecutionPlanner
  -> sql_assisted | handler | fallback
  -> response metadata minima
```

## Flujo Que Hoy Sigue Sobrando

```text
Request
  -> IADevChatView
  -> IADevOrchestratorService
  -> ChatApplicationService
  -> bridges / planner / router / assembler / delegation / loop
  -> legacy_runner posible
  -> run_legacy posible
```

## YAML Vs AI_Dictionary

- Regla final:
  - `ai_dictionary.dd_dominios`
  - `ai_dictionary.dd_tablas`
  - `ai_dictionary.dd_campos`
  - `ai_dictionary.dd_relaciones`
  - `ai_dictionary.dd_sinonimos`
  - `ai_dictionary.dd_reglas`
  - son la unica fuente estructural
- YAML solo debe conservar:
  - narrativa del dominio
  - ejemplos de preguntas
  - instrucciones de presentacion
  - vocabulario no estructural
- Implicacion:
  - cualquier tabla, columna, join o regla de compilacion tomada desde YAML debe considerarse deuda tecnica

## Observabilidad Minima Recomendada

- Mantener:
  - `arbitrated_intent`
  - `final_intent`
  - `runtime_flow`
  - `compiler_used`
  - `fallback_reason`
- Deprecar o apagar gradualmente:
  - `capability_shadow`
  - `runtime_wrapper_resolved`
  - `context_builder_resolved`
  - `reasoning_diagnostics`
  - trazas duplicadas de `query_intelligence` y `proactive_loop`

## Plan De Limpieza Seguro

### Onda 0: Congelar Arquitectura

- No tocar logica del piloto `ausentismo + empleados`
- Marcar como target oficial el flujo unico
- Documentar `orchestrator_service.py` como wrapper de compatibilidad y no como runtime principal

### Onda 1: Cortar El Wrapper Como Entrada Principal

- Cambiar [backend/apps/ia_dev/views/chat_view.py](/c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/views/chat_view.py:9) para que use `ChatApplicationService` directo
- Mantener `IADevOrchestratorService` solo para compatibilidad de comandos y fallback controlado
- Resultado esperado:
  - una sola entrada productiva real

### Onda 2: Sacar Ruteo Transicional De `ChatApplicationService`

- Retirar dependencia operativa de:
  - `IntentToCapabilityBridge`
  - `CapabilityPlanner`
  - `CapabilityRouter`
  - `LegacyResponseAssembler`
  - `DelegationCoordinator`
  - `LoopController`
- Mover cualquier decision necesaria al binomio:
  - `IntentArbitrationService`
  - `QueryExecutionPlanner`

### Onda 3: Separar Estructura De Narrativa

- Hacer que `SemanticBusinessResolver` consuma estructura solo desde `DictionaryToolService`
- Dejar `DomainRegistry` y `DomainContextLoader` solo para contenido narrativo si siguen siendo utiles
- Quitar usos estructurales de YAML en auditoria y runtime

### Onda 4: Encapsular Compatibilidad

- Reducir `orchestrator_service.py` a un adapter pequeno
- Dejar `run_legacy` y `tool_ausentismo_service` fuera del camino principal
- Toda llamada a legacy debe quedar explicitamente etiquetada como fallback

### Onda 5: Poda Final

- Borrar archivos deprecados solo cuando:
  - no existan imports productivos
  - no existan tests de regresion que dependan del camino viejo
  - el piloto y el dominio siguiente funcionen por el flujo unico

## Estimacion De Codigo Removible

- Primera ola conservadora de simplificacion:
  - `intent_service.py`: `459`
  - `capability_planner.py`: `375`
  - `intent_to_capability_bridge.py`: `757`
  - `capability_router.py`: `267`
  - `response_assembler.py`: `766`
  - `loop_controller.py`: `92`
  - `delegation_coordinator.py`: `714`
  - `context_builder.py`: `224`
  - `tool_attendance_service.py`: `6`
  - `tool_transport_service.py`: `57`
  - total aproximado: `3,717` lineas
- Segunda ola posible:
  - `domain_context_loader.py`: `334`
  - `domain_registry.py`: `249`
  - subtotal acumulado: `4,300` lineas
- Ola final al retirar wrapper:
  - `orchestrator_service.py`: `2,634`
  - total acumulado posible: `6,934` lineas
- No se cuenta aqui la reduccion interna adicional que puede lograrse dentro de `ChatApplicationService`

## Riesgos

- `orchestrator_service.py` aun es usado por la vista principal y por comandos de simulacion; no se puede cortar sin adapter claro
- `SemanticBusinessResolver` mezcla responsabilidades semanticas validas con carga estructural legacy; conviene separar antes de podar
- Hay tests construidos alrededor de `capability_shadow`, `legacy bridge`, `intent_service` y `orchestrator`
- La observabilidad actual alimenta reportes existentes; hay que reducir ruido sin romper `monitor`, `audit`, `diagnose` ni `pilot_report`
- `tool_ausentismo_service` aun sirve como compatibilidad fuera del alcance cubierto; retirarlo antes de tiempo seria riesgoso

## Criterio De Listo Para Siguiente Dominio

- La senal correcta ya no es "mas inteligencia".
- La senal correcta es esta:
  - una pregunta entra
  - pasa por un solo camino
  - deja una sola decision de intencion
  - deja un solo planner de ejecucion
  - y responde sin ambiguedad de runtime
- Cuando eso quede cierto, el sistema si esta listo para seguir entrenando o configurar el siguiente dominio, por ejemplo `transporte`.
