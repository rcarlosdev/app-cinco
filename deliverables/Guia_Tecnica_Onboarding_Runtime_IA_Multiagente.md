# Guia Tecnica De Onboarding Del Runtime IA Multiagente

## Objetivo

Este documento explica el flujo real del sistema actual y deja una forma correcta de extenderlo sin romper la arquitectura. Esta guia esta pensada para developers que necesitan:

- entender por donde entra una consulta y como se resuelve
- agregar nuevos dominios, tablas o joins
- decidir cuando crear handler y cuando no
- evitar hardcode, rutas paralelas y metadata mal ubicada

La regla principal es esta: el sistema ya esta diseñado para razonar. Nuestro trabajo no es meterle mas heuristicas manuales, sino darle buen contexto estructural en `ai_dictionary` y dejar que el runtime decida.

## Flujo Actual Del Sistema

Flujo unico vigente:

`HTTP/CLI -> ChatApplicationService -> IntentArbitrationService -> SemanticBusinessResolver -> QueryExecutionPlanner -> sql_assisted | handler moderno | runtime_fallback -> respuesta empresarial`

Ese es el camino que debemos proteger. Todo cambio nuevo tiene que entrar por esa ruta, no por una alternativa paralela.

### 1. HTTP / CLI

Las entradas principales hoy son el endpoint HTTP y el comando de simulacion. Ambos deben terminar resolviendo por el mismo runtime. El endpoint real esta en [chat_view.py](/c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/views/chat_view.py:1) y el comando operativo en `simulate_ia_dev_chat`.

La idea es simple: no debe existir una logica para frontend y otra diferente para pruebas. La simulacion tiene que reproducir el comportamiento del runtime real para que los diagnosticos sean confiables.

### 2. `ChatApplicationService`

Archivo principal: [chat_application_service.py](/c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/orchestration/chat_application_service.py:1)

Este es el entrypoint real del runtime. Construye el `RunContext`, carga memoria temprana, coordina query intelligence, ejecuta planner, arma la respuesta final y registra metadata operativa. Si alguien pregunta “quien manda de verdad en el flujo”, la respuesta es `ChatApplicationService`.

No es un simple wrapper. Es la pieza que mantiene coherencia entre arbitraje, contexto semantico, ejecucion y observabilidad. Si cambias aca una decision de flujo, el impacto casi siempre es sistémico.

### 3. `IntentArbitrationService`

Archivo: [intent_arbitration_service.py](/c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/services/intent_arbitration_service.py:1)

Esta capa decide semanticamente que quiere hacer el usuario. No se queda en “detectar palabras”: arbitra si la solicitud es una consulta analitica, una accion, una pregunta operativa o una peticion de cambio de conocimiento. Cuando hay OpenAI disponible, GPT actua como arbitro principal; si no, existe fallback deterministico.

La salida importante no es solo `final_intent`, sino banderas operativas como `should_use_sql_assisted`, `should_use_handler` y `should_fallback`. Esa decision ya viene con contexto de dominio, capacidades candidatas y metadata del diccionario.

### 4. `SemanticBusinessResolver`

Archivo: [semantic_business_resolver.py](/c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/semantic/semantic_business_resolver.py:1)

Esta pieza convierte una intencion estructurada en una especificacion operativa usando `ai_dictionary.dd_*` como fuente estructural. El propio archivo lo dice de forma explicita: `ai_dictionary` manda; YAML queda como narrativa.

Aqui se resuelven tablas, columnas, relaciones, sinonimos, columnas permitidas, joins permitidos y contexto del dominio. Tambien se marcan huecos de metadata y se construye el inventario que despues usa el planner. Si falta estructura en `ai_dictionary`, este servicio no deberia “inventarla” leyendo YAML como si fuera catalogo productivo.

### 5. `QueryExecutionPlanner`

Archivo: [query_execution_planner.py](/c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/semantic/query_execution_planner.py:1)

Este es el componente que decide como ejecutar la consulta ya resuelta. Evalua politica, determina si aplica `sql_assisted`, si debe ir por una capacidad con handler moderno, si falta contexto o si toca fallback. En el flujo sano, el planner es la autoridad sobre la estrategia de ejecucion.

Tambien es quien valida SQL seguro: tablas permitidas, columnas permitidas, joins declarados y limites. No deberia haber SQL “por fuera” de esta capa para casos de analytics cubiertos.

### 6. `sql_assisted`

Cuando una consulta es analitica y el dominio tiene metadata suficiente, el planner genera SQL seguro y lo ejecuta por la ruta moderna. Esta es la salida preferida para preguntas agregables y basadas en datos tabulares reales.

El estado saludable hoy se ve asi: la consulta entra, el planner elige `sql_assisted`, el compilador genera SQL valido, no se usa fallback y la respuesta queda marcada con `runtime_flow=sql_assisted`.

### 7. `handler` moderno

El handler moderno es la salida correcta solo cuando la consulta no encaja bien como SQL assisted. Un ejemplo tipico es una logica de negocio especial, una resolucion de entidad o un calculo que no conviene expresar como SQL generico.

Un handler no debe existir porque “era mas rapido programarlo a mano”. Debe existir porque el caso realmente lo necesita.

### 8. `runtime_fallback`

Archivo: [runtime_fallback_service.py](/c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/services/runtime_fallback_service.py:1)

El fallback existe como contingencia encapsulada. No es una ruta normal de implementacion. Sirve para mantener compatibilidad mientras quedan partes legacy vivas, y en analytics cubierto incluso puede bloquear el paso al legacy para no contaminar el piloto moderno.

Si una consulta nueva llega consistentemente al fallback, eso no significa que “funciona”. Significa que falta metadata, falta cobertura moderna o se rompio el flujo actual.

## Reglas Clave Del Sistema

### No hacer

- No usar reglas del tipo “si contiene X palabra, ejecutar Y”.
- No meter logica estructural en YAML.
- No crear agentes por tabla.
- No duplicar logica de negocio fuera del runtime.
- No escribir SQL manual fuera del planner para analytics cubierto.
- No reintroducir routing legacy como autoridad principal.

### Si hacer

- Usar `ai_dictionary` como fuente estructural unica.
- Dejar que GPT arbitre la intencion cuando corresponde.
- Dejar que el planner decida la estrategia de ejecucion.
- Usar YAML solo como apoyo narrativo, ejemplos y contexto no autoritativo.
- Modelar bien tablas, campos, relaciones y sinonimos antes de tocar codigo.

## Que Significa “No Meter Logica Estructural En YAML”

YAML puede seguir existiendo para:

- contexto del dominio
- vocabulario narrativo
- ejemplos de consultas
- reglas descriptivas de negocio

YAML no debe definir la verdad estructural de:

- tablas reales
- columnas reales
- joins reales
- columnas autorizadas para compilar SQL
- sinonimos productivos si no estan tambien en `ai_dictionary`

Si el runtime necesita una columna para compilar una consulta, esa columna debe existir en `ai_dictionary`, no solo en `dominio.yaml`.

## Como Agregar Una Nueva Tabla O Dominio Correctamente

La secuencia correcta es metadata primero, runtime despues.

### Paso 1. Decidir si es dominio nuevo o extension de uno existente

Antes de crear codigo, responde:

- esto es un nuevo proceso de negocio o solo otra tabla del mismo dominio
- comparte dimensiones con `empleados` u otro dominio existente
- necesita una capacidad nueva o solo habilitar nuevas preguntas sobre el mismo dominio

No crees un agente nuevo solo porque aparecio una tabla nueva. Primero piensa en el proceso de negocio, no en el storage.

### Paso 2. Registrar estructura en `ai_dictionary`

Registra al menos:

- dominio en `dd_dominios` si aplica
- tabla en `dd_tablas`
- columnas en `dd_campos`
- perfiles/capacidades de columna donde aplique
- sinonimos en `dd_sinonimos`
- relaciones en `dd_relaciones`

Si la tabla se cruza con `empleados`, no dupliques `area`, `cargo`, `supervisor` y otros atributos si ya viven correctamente en `cinco_base_de_personal`. Declara el join y reutiliza la dimension compartida.

### Paso 3. Validar metadata

Ejecuta:

```powershell
python manage.py ia_dictionary_audit --domain <dominio> --as-json
```

Si el dominio cruza con empleados o con otro dominio activo, usa una validacion ampliada cuando exista soporte, por ejemplo:

```powershell
python manage.py ia_dictionary_audit --domain ausentismo --with-empleados
```

No avances si aparecen:

- `missing_columns`
- `missing_relations`
- `missing_synonyms`
- `yaml_structural_leaks`

### Paso 4. Probar preguntas reales del negocio

No pruebes primero con preguntas tecnicas como:

- “haz select de tabla X”
- “trae column_name Y”

Prueba con lenguaje real de negocio:

- “que areas tienen mas ausentismo”
- “cuantos empleados activos hay por cargo”
- “que proyectos concentran mas rutas”

La arquitectura esta hecha para resolver intencion de negocio, no prompts de DBA.

### Paso 5. Ejecutar diagnostico del runtime

Ejecuta:

```powershell
python manage.py ia_runtime_diagnose --domain <dominio> --real-data
```

O la variante con dominios relacionados:

```powershell
python manage.py ia_runtime_diagnose --domain ausentismo --with-empleados --real-data
```

Lo que quieres ver:

- `passed > 0`
- `failed=0`
- `sql_assisted_count` creciendo para analytics
- `legacy_count=0`
- `fallback_count=0` o al menos controlado y explicado

### Paso 6. Verificar que entra por la ruta correcta

Para una consulta agregable, el flujo esperado es:

- arbitraje decide analytics
- `SemanticBusinessResolver` encuentra estructura valida en `ai_dictionary`
- `QueryExecutionPlanner` selecciona `sql_assisted`
- `compiler_used` refleja compilador moderno
- `runtime_flow=sql_assisted`
- `fallback_reason` vacio

Si no pasa eso, el problema casi nunca se arregla metiendo mas `if`. Normalmente falta metadata o hay una restriccion de policy/coverage.

## Cuándo Crear Un Handler

Crear handler solo cuando una consulta no deba resolverse como SQL assisted.

### Crear handler si

- no es realmente un query SQL
- requiere logica especifica de aplicacion
- necesita resolver entidades o transformaciones especiales
- el calculo no es razonable ni mantenible como SQL assisted

### No crear handler si

- la consulta es un conteo, agrupacion, top, distribucion, comparativo o resumen tabular
- la respuesta puede construirse con joins declarados y agregaciones normales
- el unico problema actual es que falta metadata en `ai_dictionary`

Regla simple: si se puede resolver con SQL seguro, no crees handler.

## Cómo Evitar Romper El Sistema

### 1. No tocar `ChatApplicationService` sin entender el impacto

Cambiar ahi implica tocar el flujo central. Antes de hacerlo, revisa como afecta:

- memoria temprana
- arbitraje
- planner
- metadata final
- observabilidad
- fallback

### 2. No reintroducir routing legacy

El runtime ya hizo trabajo de aislamiento para que la ruta moderna tenga autoridad. Si vuelves a meter planner/router legacy como decision principal, vas a contaminar diagnosticos y reabrir deuda tecnica ya cerrada.

### 3. No usar el orchestrator antiguo como solucion facil

`orchestrator_service.py` y partes legacy siguen vivos por compatibilidad, no como patron de extension. Si un dominio nuevo “solo funciona” entrando por ahi, entonces no esta integrado correctamente al runtime moderno.

### 4. No meter nueva logica dentro del fallback

El fallback debe quedarse como contingencia. No conviertas `RuntimeFallbackService` en una segunda plataforma de desarrollo. Si agregas comportamiento nuevo ahi, solo estas creando otra arquitectura paralela.

## Debugging Operativo

### `ia_runtime_diagnose`

Comando principal para validar comportamiento funcional del runtime.

```powershell
python manage.py ia_runtime_diagnose --domain <dominio> --real-data
```

Mirar especialmente:

- `runtime_flow`
- `compiler_used`
- `fallback_reason`
- `sql_assisted_count`
- `handler_count`
- `legacy_count`

Interpretacion rapida:

- `runtime_flow=sql_assisted`: ruta moderna ideal para analytics
- `runtime_flow=handler`: caso moderno pero no SQL
- `runtime_flow=runtime_only_fallback` o `legacy_fallback`: algo falta o algo se rompio

### `ia_runtime_pilot_health`

Sirve para revisar salud operativa del piloto controlado.

```powershell
python manage.py ia_runtime_pilot_health --domain ausentismo --days 1
```

Mirar:

- `status`
- `legacy_count`
- `runtime_only_fallback_count`
- `errores_sql`

Si esos valores dejan de estar en cero en un dominio ya cubierto, hay regresion o perdida de cobertura.

### `ia_runtime_pilot_report`

Sirve para ver el comportamiento agregado de una ventana de tiempo.

```powershell
python manage.py ia_runtime_pilot_report --domain ausentismo --days 7
```

Mirar:

- `sql_assisted_count`
- `handler_count`
- `runtime_only_fallback_count`
- `legacy_count`
- `blocked_legacy_count`
- lista de consultas con `flow` y `fallback_reason`

Este comando es util para ver si un cambio “parece funcionar” en local pero degradó el trafico real.

## Qué Mirar En Metadata

### `runtime_flow`

Te dice por donde salio realmente la respuesta. Es el indicador mas importante para entender si el flujo sano se mantuvo.

### `compiler_used`

Te dice que compilador construyo la consulta. Para analytics cubierto deberias ver la ruta moderna, no una solucion lateral.

### `fallback_reason`

Es la pista mas util cuando algo no entro por la ruta esperada. No la tapes. No la reemplaces por mensajes genericos. Si aparece, hay que leerla y arreglar la causa real.

## Ejemplo Completo

Pregunta:

`Que areas tienen mas ausentismo?`

### 1. Arbitraje

`IntentArbitrationService` recibe la pregunta junto con dominio candidato, contexto del diccionario y capacidades. GPT interpreta que es una consulta analitica, no una accion ni una solicitud de cambio de conocimiento.

La salida esperada es algo equivalente a:

- `final_intent=analytics_query`
- `final_domain=ausentismo`
- `should_use_sql_assisted=true`

### 2. Resolucion semantica

`SemanticBusinessResolver` toma el dominio `ausentismo` y construye contexto desde `ai_dictionary`:

- tabla de ausentismo
- columnas relevantes
- relacion con `cinco_base_de_personal`
- sinonimos y aliases
- columnas permitidas
- joins permitidos

Si “area” no vive en la tabla de ausentismo sino en empleados, eso no se resuelve hardcodeando una union manual. Se resuelve porque la relacion ya esta declarada en `ai_dictionary`.

### 3. Plan de ejecucion

`QueryExecutionPlanner` evalua si la consulta puede resolverse por `sql_assisted`. Como es una agregacion clara y hay join permitido, construye el plan SQL seguro.

La salida esperada es:

- `strategy=sql_assisted`
- `runtime_flow=sql_assisted`
- `compiler_used` moderno
- `fallback_reason=""`

### 4. Ejecucion y respuesta

Se ejecuta el SQL validado, se obtienen filas reales y la respuesta empresarial devuelve resumen, tabla, insights o KPIs segun el contrato del frontend.

Lo importante aca es que la respuesta no sale de una heuristica “si preguntan por area usa esta query fija”. Sale de:

- arbitraje de intencion
- metadata estructural del diccionario
- planner de ejecucion

## Anti-Patrones

No hagas nada de esta lista:

- hardcode de reglas por palabra clave
- duplicar logica del dominio en varios archivos
- escribir SQL manual fuera del planner para analytics cubierto
- usar YAML como fuente estructural productiva
- crear un agente por cada tabla
- saltarte `ai_dictionary` porque “ya sabemos como se llama la columna”
- meter joins manuales en handlers si el caso es resolvible por SQL assisted
- agregar caminos paralelos al runtime para “salir del paso”
- usar fallback o legacy como lugar para desarrollar features nuevas

Si una solucion nueva depende de uno de esos patrones, probablemente esta mal diseñada para esta arquitectura.

## Checklist De Implementacion

- modelaste dominio, tabla, campos, sinonimos y relaciones en `ai_dictionary`
- corriste `ia_dictionary_audit`
- probaste preguntas reales del negocio
- corriste `ia_runtime_diagnose`
- verificaste `runtime_flow=sql_assisted` cuando aplica
- confirmaste que `fallback_reason` esta vacio en el camino sano
- evitaste crear handler si SQL assisted resolvia el caso
- no tocaste fallback ni legacy para meter cobertura nueva

## Conclusión

El sistema ya esta diseñado para razonar. La responsabilidad del desarrollador no es forzar la respuesta con mas condiciones manuales, sino alimentar bien la estructura del negocio y respetar el flujo moderno.

En esta arquitectura, el valor viene de `ai_dictionary`, del arbitraje semantico y del planner. Si esos tres estan bien alimentados, el runtime resuelve. Si faltan, no se arregla con mas hardcode: se arregla con mejor metadata y mejor cobertura estructural.
