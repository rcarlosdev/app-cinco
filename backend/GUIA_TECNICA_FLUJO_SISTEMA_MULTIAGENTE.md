# Guia Tecnica Del Flujo Del Sistema Multiagente

## Objetivo

Esta guia describe el flujo tecnico real del sistema multiagente empresarial del proyecto,
desde que entra una consulta hasta que se genera la respuesta, se guarda memoria y se
retroalimenta el runtime.

Esta guia no es funcional o de negocio. Es una guia de arquitectura y ejecucion.

Sirve para:

- entender el flujo end-to-end
- depurar problemas
- incorporar nuevos dominios/agentes
- extender planner, memoria, policy o capabilities

## Vista General

El sistema actual no es un chatbot monolitico. Es una orquestacion por capas:

1. entrada y bootstrap
2. memoria previa
3. query intelligence
4. planner y routing
5. ejecucion capability-first o delegacion
6. validacion de satisfaccion
7. memoria posterior
8. ensamblado final de respuesta

La arquitectura favorece:

- dominio semantico gobernado
- uso de `ai_dictionary + YAML`
- joins controlados
- fallback seguro
- memoria de patrones satisfactorios
- observabilidad por evento

## Componente De Entrada

Punto de entrada principal:

- [chat_application_service.py](</c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/orchestration/chat_application_service.py>)

Clase principal:

- `ChatApplicationService`

Metodo principal:

- `ChatApplicationService.run()`

Comportamiento:

- ejecuta el flujo capability-first, query intelligence y handlers modernos
- si un caller HTTP necesita contingencia, el fallback legacy queda aislado en `RuntimeFallbackService`

Ruta actual recomendada:

- `ChatApplicationService.run()`

## Nucleo De Orquestacion

Archivo principal:

- [chat_application_service.py](</c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/orchestration/chat_application_service.py>)

Clase:

- `ChatApplicationService`

Metodo central:

- `run()`

Ese metodo es el corazon del sistema.

## Flujo End-To-End

## Paso 1. Crear `RunContext`

Archivo:

- [chat_application_service.py](</c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/orchestration/chat_application_service.py>)

Metodo:

- `ChatApplicationService.run()`

Accion:

- crea `RunContext`
- recupera `session_context`
- resuelve `user_key`

Contrato:

- `run_id`
- `trace_id`
- `session_id`
- `routing_mode`
- `metadata`

## Paso 2. Bootstrap De Clasificacion

Metodo:

- `_bootstrap_classification()`

Objetivo:

- inferir una clasificacion inicial rapida sin depender aun de query intelligence completo

Salida tipica:

- `intent`
- `domain`
- `selected_agent`
- `needs_database`
- `output_mode`

Esto es un bootstrap. No es aun la resolucion final.

## Paso 3. Cargar Memoria Previa Temprana

Servicio:

- [chat_memory_runtime_service.py](</c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/memory/chat_memory_runtime_service.py>)

Metodo:

- `load_context_for_chat()`

Objetivo:

- traer memoria de usuario
- traer memoria de negocio
- traer patrones reutilizables

Importancia:

Esta carga ocurre antes de `query_intelligence`, para que el sistema pueda usar:

- preferencias de salida
- filtros recurrentes
- patrones satisfactorios
- fast-path semantico

## Paso 4. Resolver Query Intelligence

Metodo:

- `_resolve_query_intelligence()`

Este paso contiene varias subcapas.

### 4.1 Construir contexto semantico

Servicio:

- [semantic_business_resolver.py](</c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/semantic/semantic_business_resolver.py>)

Metodo relevante:

- `build_semantic_context()`

Fuente de datos:

- `ai_dictionary`
- YAML del dominio
- relaciones conocidas
- columnas y sinonimos

Resultado:

- tablas
- columnas
- relationships
- aliases
- reglas
- ejemplos
- `query_hints`

### 4.2 Context Builder

Servicio:

- [context_builder.py](</c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/semantic/context_builder.py>)

Objetivo:

- enriquecer o comparar contexto legacy vs contexto activo

### 4.3 Semantic Normalization

Servicio:

- [semantic_normalization_service.py](</c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/semantic/semantic_normalization_service.py>)

Objetivo:

- normalizar dominio, filtros, periodos, dimensiones, hints

Puede usar:

- reglas
- memoria
- OpenAI

### 4.4 Canonical Resolution

Servicio:

- [canonical_resolution_service.py](</c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/semantic/canonical_resolution_service.py>)

Objetivo:

- construir una lectura canonica de la consulta
- comparar version semantica vs version operativa

### 4.5 Query Intent Resolver

Servicio:

- [query_intent_resolver.py](</c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/semantic/query_intent_resolver.py>)

Metodo clave:

- `resolve()`

Capas internas:

- reglas deterministicas
- match de memoria de patrones
- fast-path
- OpenAI como refinador

Si hay patron satisfactorio exacto:

- `match_query_pattern()`
- `query_pattern_fastpath_hit`

En ese caso, el sistema evita la parte OpenAI de esa fase.

### 4.6 Semantic Business Resolve Query

Servicio:

- [semantic_business_resolver.py](</c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/semantic/semantic_business_resolver.py>)

Metodo:

- `resolve_query()`

Objetivo:

- producir `ResolvedQuerySpec`

Ese contrato ya incluye:

- intent estructurado
- filtros normalizados
- periodo normalizado
- columnas mapeadas
- `semantic_context`

### 4.7 Query Execution Planner

Servicio:

- [query_execution_planner.py](</c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/semantic/query_execution_planner.py>)

Metodo:

- `plan()`

Produce:

- `QueryExecutionPlan`

Decide:

- strategy
- capability
- constraints
- requires_context
- sql_assisted si aplica

## Paso 5. Clasificacion Override

Metodo:

- `_build_query_intelligence_classification_override()`

Objetivo:

- dejar que query intelligence refine bootstrap legacy

Ejemplo:

- una consulta arrancó como `general`
- query intelligence la convierte a `empleados`

## Paso 6. Planner De Capacidades

Servicios:

- [capability_planner.py](</c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/routing/capability_planner.py>)
- [intent_to_capability_bridge.py](</c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/routing/intent_to_capability_bridge.py>)
- [capability_catalog.py](</c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/routing/capability_catalog.py>)

Objetivo:

- transformar clasificacion e intent en una o varias capacidades candidatas

Entradas:

- clasificacion bootstrap
- query intelligence
- memoria
- workflow hints

Resultado:

- `candidate_plans`

## Paso 7. Delegacion Multiagente

Servicio:

- [delegation_coordinator.py](</c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/delegation/delegation_coordinator.py>)

Metodo:

- `plan_and_maybe_execute()`

Importante:

El sistema soporta multiagente, pero no todo join o cruce de tablas debe activar varios agentes.

Buena practica en esta arquitectura:

- si la relacion entre tablas es conocida y deterministica, usar planner multi-tabla
- usar multiagente real cuando hay subproblemas independientes o dominios distintos

Ejemplo donde NO hace falta dos agentes:

- `ausentismos por cargo`

Ejemplo donde SI podria aplicar:

- una consulta compuesta con varios procesos, varias fuentes y varios criterios operativos distintos

## Paso 8. Policy Guard

Servicio:

- [policy_guard.py](</c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/policies/policy_guard.py>)

Metodo:

- `evaluate()`

Objetivo:

- permitir o bloquear la capability
- forzar fallback legacy si hay restriccion

Ejemplos:

- capability deshabilitada
- join con personal restringido
- memory hints restringidos

## Paso 9. Capability Router

Archivo:

- [capability_router.py](</c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/routing/capability_router.py>)

Metodos:

- `route()`
- `execute()`

Responsabilidad:

- decidir si la capability se ejecuta o si va a legacy
- despachar al handler del dominio correcto

Dominios capability-first actuales:

- `attendance`
- `transport`
- `empleados`

## Paso 10. Proactive Loop

Metodo:

- `_execute_with_proactive_loop()`

Objetivo:

- intentar capacidades candidatas
- evaluar satisfaccion
- replanificar si el resultado no cumple

Este loop permite:

- detectar resultados insuficientes
- reintentar con otra capability
- cortar si se satisface la consulta

## Paso 11. Ejecucion Del Handler De Dominio

Ejemplos:

- [domains/empleados/handler.py](</c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/domains/empleados/handler.py>)
- [domains/attendance/handler.py](</c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/domains/attendance/handler.py>)
- [domains/transport/handler.py](</c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/domains/transport/handler.py>)

Cada handler:

1. recibe capability + `ResolvedQuerySpec` + `QueryExecutionPlan`
2. resuelve filtros runtime
3. resuelve dimensiones
4. ejecuta el service o tool del dominio
5. construye `reply`, `data`, `trace`, `data_sources`

## Paso 12. Services O Tools De Negocio

Ejemplos:

- [empleado_service.py](</c:/dev/agente_cinco/app-cinco/backend/apps/empleados/services/empleado_service.py>)
- [tool_attendance_service.py](</c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/services/tool_attendance_service.py>)

Aqui vive la logica operativa de datos:

- queryset
- joins controlados
- agregaciones
- detalle
- tablas de salida

## Paso 13. Validacion De Satisfaccion

Servicios:

- [result_satisfaction_validator.py](</c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/semantic/result_satisfaction_validator.py>)
- [satisfaction_review_gate.py](</c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/semantic/satisfaction_review_gate.py>)
- [loop_controller.py](</c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/orchestration/loop_controller.py>)

Objetivo:

- verificar si el resultado cumple con la consulta
- decidir si se aprueba o si se replanifica

Ejemplos de chequeos:

- pidió `por supervisor` pero no vino agrupado
- pidió `cedula` concreta y la tabla no la aplicó
- pidió grafica y no hay payload suficiente

## Paso 14. Memoria Posterior

Servicios:

- [chat_memory_runtime_service.py](</c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/memory/chat_memory_runtime_service.py>)
- [query_pattern_memory_service.py](</c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/semantic/query_pattern_memory_service.py>)

Memoria de preferencias:

- `detect_candidates()`
- `persist_candidates()`

Memoria de patrones satisfactorios:

- `_record_query_pattern_memory()`
- `record_success()`

Se guarda:

- shape de consulta
- semantic pattern
- execution pattern
- satisfaction score
- response signature

Si el patron es de bajo riesgo:

- puede autoaplicarse
- puede quedar en scope de usuario
- puede quedar en scope de negocio

## Paso 15. Observabilidad

Servicios:

- `ObservabilityService`
- eventos en `ChatApplicationService`
- traza del simulador en [simulate_ia_dev_chat.py](</c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/management/commands/simulate_ia_dev_chat.py>)

Eventos importantes:

- `query_intelligence_resolved`
- `query_pattern_candidates_loaded`
- `query_pattern_fastpath_hit`
- `query_pattern_fastpath_miss`
- `policy_runtime_decision`
- `proactive_loop_iteration`
- `empleados_handler_executed`
- `query_pattern_memory_recorded`

## Paso 16. Ensamblado Final

Archivo:

- [response_assembler.py](</c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/orchestration/response_assembler.py>)

Clase:

- `LegacyResponseAssembler`

Metodo:

- `assemble()`

Responsabilidad:

- consolidar respuesta final
- anexar `capability_shadow`
- anexar `query_intelligence`
- anexar `memory_candidates`
- anexar `pending_proposals`
- completar `trace`

## Contratos Principales Del Flujo

Archivo:

- [query_intelligence_contracts.py](</c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/contracts/query_intelligence_contracts.py>)

Contratos clave:

- `StructuredQueryIntent`
- `ResolvedQuerySpec`
- `QueryExecutionPlan`
- `SatisfactionValidation`
- `QueryPatternMemory`

Estos contratos son el idioma interno del runtime.

## Fuentes De Verdad Del Sistema

## 1. `ai_dictionary`

Estructura:

- `dd_dominios`
- `dd_tablas`
- `dd_campos`
- `dd_sinonimos`
- `dd_relaciones`
- `ia_dev_capacidades_columna`

Uso:

- definir tablas candidatas
- definir columnas candidatas
- definir sinonimos
- definir joins permitidos
- definir capacidades por columna

## 2. YAML Por Dominio

Ruta:

- `backend/apps/ia_dev/domains/<dominio>/`

Archivos:

- `dominio.yaml`
- `contexto.yaml`
- `reglas.yaml`
- `ejemplos.yaml`

Uso:

- contexto corto y claro para el runtime
- defaults de negocio
- ambiguedades
- ejemplos operativos

## 3. Memoria

Tipos:

- memoria de usuario
- memoria de negocio
- patrones satisfactorios

Uso:

- acelerar consultas repetidas
- aplicar fast-path
- reusar estrategias satisfactorias

## Como Se Relacionan Los Dominios

El sistema puede relacionar dominios de dos maneras:

### A. Planner Multi-Tabla

Recomendado cuando:

- la relacion es conocida
- el join esta gobernado
- la consulta puede resolverse en un solo flujo

Ejemplo:

- `ausentismos por cargo`

Flujo:

- dominio base `attendance`
- join a `empleados`
- dimension `cargo`

### B. Delegacion Multiagente

Recomendado cuando:

- los subproblemas son independientes
- hay varias fuentes o varios pasos no triviales
- conviene dividir analisis y resolucion

## Diagrama Mental Simplificado

```text
Usuario
  -> ChatApplicationService.run
      -> bootstrap classification
      -> preload memory
      -> query intelligence
        -> semantic context
        -> normalization
        -> canonical resolution
        -> intent resolver
        -> semantic business resolve
        -> execution planner
      -> capability planning
      -> delegation optional
      -> policy guard
      -> capability router
      -> handler de dominio
      -> satisfaction validation
      -> memory writeback
      -> response assembler
      -> respuesta final
```

## Donde Se Ganan Tiempo Y Calidad

## Calidad

Mejora con:

- mejor `ai_dictionary`
- mejor YAML por dominio
- joins claros
- reglas explicitas
- pruebas de consultas reales

## Tiempo

Mejora con:

- `query_pattern_fastpath`
- menor dependencia de OpenAI en consultas repetidas
- mejores patrones de dominio
- menos ambiguedad en tablas y columnas candidatas

## Donde Depurar Segun El Problema

### El dominio sale mal

Revisar:

- `_bootstrap_classification()`
- `query_intent_resolver.py`
- `semantic_normalization_service.py`
- `canonical_resolution_service.py`

### Escoge mal la capability

Revisar:

- `intent_to_capability_bridge.py`
- `capability_planner.py`
- `query_execution_planner.py`

### Ejecuta bien pero responde mal

Revisar:

- handler del dominio
- service/tool del dominio
- `response_assembler.py`

### No aprende consultas repetidas

Revisar:

- `query_pattern_memory_service.py`
- `chat_memory_runtime_service.py`
- flags de memoria
- eventos `query_pattern_fastpath_*`

### Un join con empleados no funciona

Revisar:

- `dd_relaciones`
- `dominio.yaml` del dominio base
- `semantic_business_resolver.py`
- service/tool que hace el join

## Inferencia Semantica De Conceptos De Negocio A Campos Estructurales

Esta capa existe para que el usuario no tenga que nombrar columnas fisicas ni logicas.

- GPT puede inferir conceptos de negocio como `cumpleanos`, `edad`, `antiguedad` o `retiro`.
- Esa inferencia solo es valida cuando `ai_dictionary` confirma tabla, campo y operacion segura.
- El planner nunca debe inventar SQL fuera de lo declarado en `dd_tablas`, `dd_campos`, `dd_relaciones` y capacidades de columna.

Ejemplos canonicos:

- `cumpleanos -> empleados.fecha_nacimiento`
- `edad -> empleados.fecha_nacimiento`
- `antiguedad -> empleados.fecha_ingreso`
- `retiro -> empleados.fecha_egreso`

Reglas de gobierno:

1. si hay una sola columna candidata con alta confianza, `QueryExecutionPlanner` puede resolver por `sql_assisted`
2. si hay varias columnas candidatas, el sistema debe elegir por confianza o pedir aclaracion
3. si no hay columna declarada en `ai_dictionary`, la respuesta correcta es una limitacion de metadata, no SQL inventado
4. la memoria debe aprender la forma canonica `concepto + dominio + campo + operacion`, no una frase rigida puntual

Ejemplo operativo:

- `Cumpleaños de mayo` puede resolverse si `ai_dictionary` declara `cinco_base_de_personal.fnacimiento` como `fecha_nacimiento`, con sinonimos de negocio y soporte para `filter_by_month`
- `Cumpleaños por mes` puede resolverse si la columna fecha soporta `group_by_month`
- `Cuantos cumplen años en mayo` puede resolverse como `count` sobre `fecha_nacimiento`

## Dimensiones Agrupables Y Operador Semantico POR

El usuario no necesita escribir `GROUP BY`.

En lenguaje de negocio, expresiones como:

- `por area`
- `por cargo`
- `por sede`
- `por mes`

son senales de agrupacion.

Reglas tecnicas:

1. GPT o la capa deterministica pueden proponer la agrupacion desde el lenguaje natural
2. la ejecucion solo se permite si `ai_dictionary` confirma que la dimension existe y permite `group_by`
3. si la dimension vive en otra tabla, el runtime debe usar una relacion declarada en `dd_relaciones`
4. si no existe metadata estructural suficiente, la respuesta correcta es una limitacion estructural, no un fallback generico

Ejemplos:

- `cumpleanos de mayo por area` implica filtro por `fecha_nacimiento` y agrupacion por `area`
- `empleados activos por cargo` implica conteo agrupado por `cargo`
- `ausentismo por sede` implica agrupacion valida solo si la dimension esta declarada y el join esta gobernado

## Archivos Mas Importantes Del Sistema

- [chat_application_service.py](</c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/orchestration/chat_application_service.py>)
- [runtime_fallback_service.py](</c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/services/runtime_fallback_service.py>)
- [semantic_business_resolver.py](</c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/semantic/semantic_business_resolver.py>)
- [query_intent_resolver.py](</c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/semantic/query_intent_resolver.py>)
- [query_execution_planner.py](</c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/semantic/query_execution_planner.py>)
- [capability_planner.py](</c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/routing/capability_planner.py>)
- [capability_router.py](</c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/routing/capability_router.py>)
- [delegation_coordinator.py](</c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/delegation/delegation_coordinator.py>)
- [chat_memory_runtime_service.py](</c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/memory/chat_memory_runtime_service.py>)
- [query_pattern_memory_service.py](</c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/semantic/query_pattern_memory_service.py>)
- [response_assembler.py](</c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/orchestration/response_assembler.py>)

## Recomendacion Tecnica Final

Para extender este sistema sin degradarlo:

1. no metas logica de negocio compleja en prompts solamente
2. modela el dominio primero en `ai_dictionary`
3. explicalo corto en YAML
4. deja los joins gobernados
5. usa planner multi-tabla antes de intentar multiagente conversacional
6. guarda patrones satisfactorios
7. observa `fastpath hit rate`, `satisfaction` y `fallbacks`

Ese es el camino para que el sistema siga creciendo como plataforma empresarial y no
como una suma de prompts aislados.
