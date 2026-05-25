# START HERE CODEX

## Proposito del archivo

Este es el primer archivo que Codex debe leer antes de modificar codigo, documentacion, agentes, planner, runtime, SQL, frontend o contratos IA del sistema multiagente empresarial.

Su funcion es forzar continuidad operativa, evitar redescubrimiento innecesario y mantener la autoridad del sistema en metadata gobernada, capabilities seguras y evidencia real.

Regla:

- leer este archivo primero
- luego leer `backend/MICRO_RESUMEN_SISTEMA_MULTIAGENTES.md` y los documentos oficiales referenciados aqui
- trabajar solo sobre la tarea solicitada
- no hacer discovery masivo salvo sintoma nuevo, concreto y verificable
- asumir validos los hechos persistidos salvo sintoma nuevo verificable
- inspeccionar solo archivos directamente relacionados con la tarea

## Documentos oficiales de continuidad

Leer siempre estos cuatro documentos:

- `backend/MICRO_RESUMEN_SISTEMA_MULTIAGENTES.md`
  - autoridad de continuidad operativa, estado runtime vigente, fases, contratos activos, rutas, pruebas relevantes y decisiones ya confirmadas
- `backend/GUIA_CAPA_SEMANTICA_EMPRESA.md`
  - autoridad de gobierno semantico, responsabilidades entre GPT, planner, tools y agents, limites de autoridad y reglas estructurales estables
- `backend/OPERACION_RUNTIME_MULTIAGENTE.md`
  - autoridad operativa del runtime productivo: health checks, alertas, troubleshooting, soporte, background, approvals y runbooks
- `backend/GUIA_DESARROLLO_AGENTES_EMPRESARIALES.md`
  - autoridad para construir, extender, validar y migrar dominios, agentes, Capability Packs y evals anti-hardcode

Si estos documentos ya confirman un hecho, asumirlo como vigente sin reauditar la arquitectura completa.

## Principio rector del proyecto

“No entrenamos consultas. Enseñamos el negocio al sistema para que GPT/OpenAI razone sobre tareas nuevas con metadata gobernada, capabilities, tools seguras y evidencia real.”

Implicaciones obligatorias:

- no hardcodear frases como autoridad de negocio
- no convertir examples, regex o fastpaths en gobierno principal
- no usar GPT/OpenAI para inventar tablas, columnas, SQL, KPIs o ejecucion
- no responder exito sin evidencia

## Autoridades del sistema

Las autoridades del sistema deben entenderse asi:

- `ai_dictionary` manda en estructura semantica
- `dd_tablas`, `dd_campos`, `dd_relaciones`, `dd_sinonimos`, `dd_reglas` gobiernan metadata
- `BusinessQuerySemanticPlan` organiza intencion, entidad, filtros, reglas y capability candidata
- `SemanticCapabilityRegistry` debe ser autoridad de binding semantico
- `ToolRegistryService` debe ser autoridad `capability -> tool`
- `QueryExecutionPlanner` debe ser autoridad unica de SQL seguro
- `ResponseAssembler` y `BusinessResponseComposer` deben responder sobre evidencia
- GPT/OpenAI razona y coordina, pero no inventa tablas, columnas, SQL, KPIs ni ejecucion

## Clasificacion obligatoria de logica existente

Cualquier regla, `if`, regex, keyword, fastpath o pattern existente o nuevo debe clasificarse explicitamente en una de estas categorias:

### A. `authoritative_layer`

Reglas gobernadas y oficiales:

- `ai_dictionary`
- `dd_*`
- `BusinessQuerySemanticPlan`
- `SemanticCapabilityRegistry`
- Capability Packs
- `ToolRegistryService`
- `QueryExecutionPlanner`

### B. `assistive_heuristic`

Heuristica permitida solo para sugerir, inferir o acelerar:

- deteccion inicial
- scoring
- normalizacion
- inferencia de encabezados
- familias candidatas
- deteccion de ambiguedad

### C. `shadow_fallback`

Fallback temporal y trazado:

- compatibilidad legacy
- rescate cuando falta metadata
- fallback sombreado
- nunca debe ser autoridad principal

### D. `compatibility_layer`

Codigo heredado que se conserva temporalmente por compatibilidad:

- debe tener traza
- debe tener plan de migracion
- no debe crecer con nuevas reglas de negocio

### E. `technical_guardrail`

Validaciones tecnicas que si pueden vivir en codigo:

- seguridad SQL
- limites de tamano
- chunking
- validacion de archivos
- sanitizacion
- control de permisos
- timeouts
- approvals
- background limits

## Regla sobre hardcodes

No eliminar todos los `if`, regex o patterns de golpe.

Eso seria riesgoso.

Primero se debe:

1. centralizar binding semantico
2. completar `SemanticCapabilityRegistry`
3. migrar dominios a Capability Packs
4. fortalecer `dd_*`
5. fortalecer evals anti-hardcode
6. marcar cada heuristica como temporal, fallback, compatibility layer o autoridad real

## Regla critica anti-hardcode

Una heuristica puede sugerir dominio, intent, filtro o capability, pero nunca puede:

- ejecutar SQL
- reemplazar `ai_dictionary`
- reemplazar `SemanticCapabilityRegistry`
- reemplazar `QueryExecutionPlanner`
- inventar tablas
- inventar columnas
- inventar KPIs
- responder exito sin evidencia

## Caso especial: validacion de seriales de proveedor

Capabilities basadas en archivos externos, como `inventory_provider_serial_validation`, si pueden usar heuristica contextual para:

- detectar columnas de serial
- analizar encabezados variables
- validar valores
- normalizar seriales
- detectar duplicados
- procesar archivos grandes en background

Regla critica:

- esa heuristica solo ayuda a inferir y validar
- no es autoridad de negocio
- no puede inventar evidencia
- no puede saltarse `QueryExecutionPlanner.execute_governed_select(...)` o la ruta segura equivalente

## Orden correcto de mejora

Secuencia obligatoria de trabajo:

1. No agregar nuevos hardcodes.
2. Identificar la regla actual.
3. Clasificarla.
4. Buscar si ya existe en `ai_dictionary` o Capability Pack.
5. Si no existe, proponer migracion a `dd_sinonimos`, `dd_reglas`, `ia_dev_capacidades_columna` o Capability Pack.
6. Mantener fallback sombreado solo si hay tests.
7. Agregar o actualizar eval anti-hardcode.
8. Actualizar el documento persistido correcto.

## Instruccion para futuros chats Codex

Plantilla corta obligatoria:

“Lee primero `backend/START_HERE_CODEX.md`. Luego lee los documentos oficiales que este archivo referencia. Trabaja solo sobre la tarea solicitada. No hagas discovery masivo salvo sintoma nuevo verificable. No introduzcas SQL libre ni hardcodes de negocio como autoridad.”

Regla de arranque explicita para futuros chats:

“Lee primero `backend/START_HERE_CODEX.md`, luego `backend/MICRO_RESUMEN_SISTEMA_MULTIAGENTES.md` y los documentos oficiales referenciados. No hagas rediscovery masivo del repo. Asume válidos los hechos persistidos salvo síntoma nuevo verificable. Inspecciona solo archivos directamente relacionados con la tarea.”

## Criterio de autoridad diaria

Antes de agregar una regla nueva en codigo, confirmar:

- si pertenece a metadata gobernada, debe migrar a `dd_*`, `ia_dev_capacidades_columna` o Capability Pack
- si es heuristica, debe quedar trazada como `assistive_heuristic`, `shadow_fallback` o `compatibility_layer`
- si es validacion tecnica, puede quedar como `technical_guardrail`
- si compite con una autoridad ya existente, debe perder contra la autoridad oficial

## Criterios de aceptacion de este punto de arranque

Este archivo existe para que futuras tareas mantengan estas condiciones:

- no reabrir discovery global si la documentacion oficial ya confirma el estado vigente
- no promover eliminacion masiva e insegura de `if`
- definir migracion gradual de hardcodes hacia metadata gobernada
- diferenciar heuristica asistiva vs autoridad semantica
- mantener el caso especial de seriales externos dentro de una ruta segura y evidence-first
