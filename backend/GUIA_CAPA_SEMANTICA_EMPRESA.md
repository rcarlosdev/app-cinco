# Guia De Capa Semantica Empresarial

## Recomendacion Arquitectonica

La practica recomendada para empresas con multiples tablas, procesos y agentes no es
usar solo base de datos ni solo texto libre. La opcion mas estable es una capa semantica
hibrida:

- `ai_dictionary`: catalogo estructurado y gobernado.
- Archivos YAML versionados: contexto operativo corto, reglas de negocio y ejemplos.
- Planner deterministico: selecciona dominio, tablas, columnas y joins candidatos.
- LLM: desambiguacion y normalizacion final, no descubrimiento libre de negocio.

## Estructura Recomendada Por Dominio

Para cada dominio de negocio, mantener en `backend/apps/ia_dev/domains/<dominio>/`:

- `dominio.yaml`
- `contexto.yaml`
- `reglas.yaml`
- `ejemplos.yaml`

El directorio `backend/apps/ia_dev/domains/registry/` queda reservado para compatibilidad
incremental y definiciones legacy de transicion.

## Rol De Cada Archivo

### `dominio.yaml`

Define el contrato base del dominio solo como referencia de dominio y no como fuente
estructural principal del runtime:

- nombre del dominio
- objetivo de negocio
- entidad principal
- tablas asociadas solo si siguen existiendo por compatibilidad
- columnas clave solo si siguen existiendo por compatibilidad
- joins conocidos solo si siguen existiendo por compatibilidad
- filtros soportados
- group by soportados
- metricas soportadas

Regla practica:

- la fuente oficial estructural debe ser `ai_dictionary`
- no usar `dominio.yaml` para inventar tablas, columnas, joins o reglas que no existan en `dd_*`
- si hay conflicto entre YAML y `ai_dictionary`, manda `ai_dictionary`

### `contexto.yaml`

Explica al agente como debe pensar el dominio desde negocio y narrativa:

- descripcion del dominio
- enfoque de respuesta
- tono
- vocabulario interno
- ambiguedades frecuentes
- defaults de negocio narrativos

No debe cargar estructura tecnica:

- no meter tablas fisicas
- no meter columnas fisicas
- no meter joins
- no meter SQL
- no meter reglas estructurales de planner
- no repetir metadata que ya vive en `dd_tablas`, `dd_campos`, `dd_relaciones` o capacidades

### `reglas.yaml`

Expone reglas concretas y gobernables:

- mapeos implicitos
- defaults
- restricciones
- criterios de prioridad
- equivalencias de lenguaje

### `ejemplos.yaml`

Sirve como entrenamiento operativo controlado:

- consulta ejemplo
- interpretacion esperada
- capacidad esperada
- filtros o agrupaciones esperadas

## Distribucion Profesional De Responsabilidades

### En `ai_dictionary`

Guardar:

- dominios
- tablas
- columnas
- sinonimos
- capacidades por columna
- valores permitidos
- joins permitidos
- reglas simples y reutilizables
- metadata semantica por campo
- fallbacks controlados
- privacidad por campo
- multiples vistas semanticas sobre una misma columna fisica cuando aplique

## BusinessQuerySemanticPlan

La capa semantica empresarial debe producir un plan estructurado antes del planner SQL seguro.

Contrato recomendado y ya aplicado en inventario:

- `domain`
- `intent`
- `entity`
- `governed_physical_field`
- `grouping_dimension`
- `inventory_family`
- `scope`
- `output`
- `candidate_capability`
- `normalized_filters`
- `requires_enrichment`
- `applicable_business_rules`
- `possible_alerts`
- `known_limitations`
- `execution`

Regla:

- este plan organiza la consulta de negocio
- no reemplaza `ai_dictionary`
- no reemplaza el planner
- no autoriza SQL libre
- no autoriza `execute=True`

## Matriz Semantica General

La estrategia correcta no es agregar fixes por frase. La estrategia correcta es modelar familias de consulta.

Familias base ya modeladas para `inventario_logistica`:

1. `saldo + empleado/tecnico + cedula`
2. `saldo + movil/cuadrilla + valor alfanumerico`
3. `kardex|movimientos|entradas y salidas + empleado/tecnico + cedula`
4. `kardex|movimientos + codigo`
5. `inventario generico + movil/cuadrilla`
6. `material claro|material de claro`
7. `ferretero|material ferretero`
8. `material generico`
9. `equipos|seriales|CPE`
10. `materiales criticos + bodega|empleado|movil`
11. `consumo vs facturacion + OT`
12. `SAP|actas|documentos` como limitacion declarada, no como dato inventado
13. `archivo externo de proveedor|contratante + seriales|CPE + validacion|cruce contra inventario propio`

Cada familia debe terminar en:

- entidad normalizada
- filtros normalizados
- capability candidata
- reglas de negocio aplicables
- limitaciones conocidas
- salida esperada

Para la familia `validacion de seriales externos` la regla estable es:

- la columna de serial se detecta por semantica y validacion de valores, no por nombre fijo
- no se hardcodea nombre exacto de archivo
- no se hardcodea solo `Numero de serie`
- `sn` o `mac` solo cuentan como serial si la evidencia del encabezado y los valores lo soporta
- la consulta no nace de SQL libre de GPT
- la existencia de tablas historicas se valida primero en metadata gobernada operativa
- la consolidacion prioriza base actual sobre historica
- `MOVIL` solo aplica si el estado realmente contiene esa cadena
- responsable solo se enriquece cuando existe estado `MOVIL` y evidencia cruzable

### Regla estable 2026-05-18: `inventory_provider_serial_validation`

- para validacion de seriales de proveedor:
  - `cedula_original` y `edit_original` deben conservarse como evidencia separada
  - `responsable_candidate_source` solo puede ser:
    - `cedula`
    - `edit`
    - `historial`
    - `no_resuelto`
- para estados que contienen `MOVIL`:
  - primero intentar `cedula` actual si parece identificador de persona y cruza con personal
  - luego intentar `edit` actual
  - despues usar `historial` solo si aporta match real
- para estados `ASOCIADO MOVIL`, `MOVIL ASOCIADO` o equivalentes:
  - no asumir que `cedula` actual es persona
  - revisar explicitamente `edit` como posible cedula real
  - si `cedula` actual es tecnica y `edit` cruza con personal, la fuente semantica estable es `edit`
- `responsable_enriched=true` exige match real contra `bd_c3nc4s1s.cinco_base_de_personal`
- si solo existe identificador tecnico o no hay match real, la salida debe declarar limitacion y no afirmar responsable enriquecido

## Rol De GPT/OpenAI En La Capa Semantica

GPT/OpenAI puede intervenir solo como apoyo controlado en la capa semantica.

### En que componentes interviene

- interpretacion semantica previa
- deteccion de ambiguedad
- organizacion de filtros de negocio
- sugerencia de capability
- resumen empresarial posterior a la ejecucion
- alertas y sugerencias sobre resultados ya ejecutados

### Que informacion recibe

- consulta original
- snapshot de `ai_dictionary` ya gobernado
- sinonimos, reglas y relaciones declaradas
- memoria confirmada de negocio
- plan semantico parcial o ambiguo
- resultados ya ejecutados cuando deba resumir o alertar

### Que JSON o plan produce

- produce o complementa un `BusinessQuerySemanticPlan`
- nunca produce SQL ejecutable como autoridad final
- nunca reemplaza `QueryExecutionPlanner`

### Que decisiones no puede tomar

- no generar SQL libre
- no inventar tablas
- no inventar columnas
- no inventar KPIs
- no decidir `execute=True`
- no saltarse `ai_dictionary`
- no relajar validadores
- no ocultar saldos cero o negativos
- no activar `legacy` o `fallback` como implementacion
- no decidir renderizado final sin validacion

### Como usa `ai_dictionary` y memorias

- `ai_dictionary` manda como autoridad estructural
- `ia_dev_business_memory` conserva reglas empresariales ya confirmadas
- `ia_dev_user_memory` y `ia_dev_session_memory` solo complementan contexto
- `dd_reglas`, `dd_sinonimos`, `dd_relaciones`, `dd_campos`, `dd_tablas`, `dd_capacidades_campo` e `ia_dev_capacidades_columna` gobiernan lo estructural

### Como ayuda a generar alertas y sugerencias

- explica saldos cero o negativos
- resalta criticidad
- explica faltantes o limitaciones declaradas
- propone siguiente accion empresarial sobre resultados ya ejecutados

### Como se controla que no invente SQL ni columnas

- el plan semantico queda trazado y auditable
- `QueryExecutionPlanner` sigue siendo autoridad unica de SQL
- `result_satisfaction_validator` y `response_assembler` controlan salida y seguridad
- el trace final registra reglas aplicadas, fuentes consultadas, capability y filtros finales

### Puntos de refuerzo futuros

- reforzar scoring de ambiguedad antes de invocar apoyo LLM
- ampliar la matriz semantica a otras familias de logistica
- sincronizar mas reglas confirmadas a `dd_reglas` cuando exista ruta gobernada de escritura

## Regla Arquitectonica Persistida 2026-05-18: dashboard empresarial gobernado por patrones

El dashboard empresarial no debe generalizarse mediante heuristicas visuales sueltas, prompts por consulta ni renderizado libre decidido por GPT.

Regla estable:

- la expansion de dashboards empresariales debe hacerse ampliando gradualmente `dashboard_composition patterns` gobernados por evidencia
- el crecimiento debe ser incremental por patron semantico validado, no por frase puntual del usuario
- el backend semantico y el `DashboardCompositionPlanner` gobiernan la composicion
- el frontend solo renderiza composicion validada
- GPT/OpenAI puede interpretar intencion, priorizar informacion, narrar resultados y explicar decisiones
- GPT/OpenAI no gobierna datos, no inventa KPIs, no inventa columnas, no genera SQL libre, no decide renderizado final sin validacion y no reemplaza el `DashboardCompositionPlanner`

Contrato minimo obligatorio de cada nuevo `dashboard_composition pattern`:

- `domain`
- intencion semantica soportada
- tipo de evidencia
- metrica principal
- dimensiones validas
- KPIs permitidos
- rankings utiles
- graficos recomendados
- tablas `drill-down`
- contrato de evidencia
- condiciones de validacion
- fallback `legacy` si no aplica

Patron estable agregado:

- `inventory.serial.validation.provider_file`
- dominio: `inventario_logistica`
- intencion: validacion de seriales de proveedor
- evidencia: archivo externo + bases actuales + backups historicos + enriquecimiento personal controlado
- metrica principal: seriales validados
- dimensiones validas: `estado`, `fuente`, `anio`, `familia`, `material`, `movil`, `responsable`, `encontrado`

Regla critica:

- un pattern nuevo no debe nacer desde un prompt aislado ni desde heuristicas visuales no gobernadas
- la composicion final debe quedar soportada por evidencia, validacion y contrato explicito

### En Archivos YAML

Guardar:

- contexto del agente
- reglas de negocio compuestas
- defaults semanticos
- ejemplos reales de consulta
- ambiguedades frecuentes
- vocabulario interno de la empresa

## Como Alimentar La Contextualizacion

La implementacion correcta debe alimentar tres capas distintas y complementarias:

### 1. Contextualizacion Del Agente

Se alimenta en `contexto.yaml`.

Objetivo:

- explicarle al agente de que trata el dominio
- como debe responder
- como nombran el negocio las cosas
- que alertas o inconsistencias debe verbalizar

Debe incluir:

- descripcion de negocio corta
- tono de respuesta
- vocabulario real del usuario
- ejemplos de ambiguedad
- defaults narrativos

No debe incluir:

- nombres de columnas fisicas
- joins
- paths JSON tecnicos
- reglas de SQL
- tablas de base de datos como contrato principal

### 2. Contextualizacion De Dominio Y Tabla

Se alimenta principalmente en:

- `ai_dictionary.dd_dominios`
- `ai_dictionary.dd_tablas`
- `ai_dictionary.dd_relaciones`

Objetivo:

- declarar cual es el dominio oficial
- declarar cual es la tabla fuente de verdad
- declarar relaciones seguras entre tablas

Debe modelar:

- dominio canonico
- tabla principal oficial
- tablas auxiliares si existen
- alias de negocio de la tabla
- clave de negocio
- joins declarados y cardinalidad

Regla:

- no crear estructura nueva si una tabla existente ya es la fuente oficial
- no duplicar la misma semantica en otra tabla si solo es enriquecimiento

### 3. Contextualizacion De Campos

Se alimenta principalmente en:

- `ai_dictionary.dd_campos`
- `ai_dictionary.dd_sinonimos`
- `ai_dictionary.dd_reglas`
- `ai_dictionary.ia_dev_capacidades_columna`

Objetivo:

- convertir columnas fisicas en conceptos de negocio gobernados

Cada campo debe modelarse como concepto, no como frase pegada.

Debe incluir cuando aplique:

- `campo_logico` canonico
- definicion de negocio
- sinonimos reales del usuario
- valores permitidos
- si sirve para filtro
- si sirve para group by
- si sirve para metrica
- si es fecha
- si es identificador
- si tiene fallback
- si tiene sensibilidad o privacidad
- si representa una vista semantica derivada de JSON

## Regla Operativa Para Campos

Cuando una columna fisica soporte varios conceptos de negocio:

- no eliminar semantica util
- declarar multiples vistas semanticas sobre la misma columna
- distinguirlas por `campo_logico`, definicion y tags semanticos
- documentar `json_path`, tipo de entidad, fallback y concepto derivado

Ejemplos tipicos:

- una columna `datos` que contiene certificados, tallas, contrato o birthday
- una misma fecha usada como emision, vencimiento derivado o estado de vigencia

## Regla De Oro Para El Programador

Cuando implemente o actualice un dominio:

1. primero confirme la fuente oficial de negocio
2. luego modele dominio y tabla en `ai_dictionary`
3. despues modele campos, sinonimos, reglas y capacidades
4. deje `contexto.yaml` solo narrativo
5. use `ejemplos.yaml` para preguntas reales del negocio
6. no hardcodee frases completas si debe modelar conceptos

## Checklist Minimo De Implementacion

- dominio oficial identificado
- tabla oficial identificada
- `dd_tablas` alineado a fuente real
- `dd_campos` con conceptos de negocio y no solo nombres fisicos
- `dd_sinonimos` con lenguaje real del usuario
- `dd_reglas` con reglas simples y reutilizables
- capacidades por columna registradas
- `contexto.yaml` narrativo y no estructural
- `ejemplos.yaml` con preguntas reales de negocio

## Regla De Nombres

Todo artefacto de negocio debe seguir [REGLA_NOMENCLATURA_EMPRESA.md](./REGLA_NOMENCLATURA_EMPRESA.md).

## Estrategia De Migracion Recomendada

1. Mantener el runtime tecnico actual.
2. No renombrar el legado masivamente.
3. Empezar a crear todo lo nuevo en espanol.
4. Versionar contexto, reglas y ejemplos por dominio.
5. Hacer migracion gradual del legado cuando haya pruebas.

## Dominios Iniciales Ya Preparados

- `empleados`
- `ausentismo`

Cada uno ya tiene archivos de:

- contexto
- reglas
- ejemplos

## Regla Semantica Confirmada De Inventario

Cuando el negocio consulte `saldo` o `inventario` por empleado, tecnico, movil, cuadrilla, bodega o codigo:

- nunca filtrar solo saldos positivos
- incluir saldos positivos, cero y negativos
- no usar `HAVING saldo > 0`
- no usar `WHERE saldo > 0`
- no usar `HAVING saldo <> 0` si eso excluye saldos en cero

Motivo empresarial:

- los saldos en cero y negativos son informacion operacional critica
- permiten detectar faltantes, descuadres, cobros, consumos, deuda operativa e inventario insuficiente

Regla narrativa para el agente:

- si la consulta es generica de inventario o saldo y no especifica familia, responder materiales/ferretero y serializados/equipos cuando ambos apliquen
- si aparece un identificador numerico como `5098747`, priorizar su lectura como `cedula` en inventario operativo
- GPT puede ayudar a interpretar la intencion y el alcance, pero no debe inventar SQL ni filtrar semantica de saldo que oculte ceros o negativos

## Regla Semantica Vigente Para Material Claro Y Ferretero

Aplicar solo sobre inventario operativo de materiales:

- `material claro` o `material de claro` => filtrar solo `tipo = 'material'`
- `ferretero` o `material ferretero` => filtrar solo `tipo = 'ferretero'`
- `material` generico => incluir `tipo IN ('material', 'ferretero')` en la misma tabla
- mantener la columna `tipo`
- no separar por ahora en dos tablas

Regla de lenguaje empresarial:

- cuando el resultado distinga frente a ferretero, lo que antes se nombraba solo como `material` debe comunicarse como `material claro`
- el runtime puede seguir mostrando el valor tecnico de la columna `tipo`, pero el mensaje ejecutivo debe decir `material claro` cuando aplique

## Regla Semantica Confirmada De Kardex Por Empleado

Cuando el usuario diga:

- `kardex del tecnico {cedula}`
- `kardex del empleado {cedula}`
- `kardex de la cedula {cedula}`

debe interpretarse como:

- dominio: `inventario_logistica`
- filtro principal: `cedula`
- tipo de consulta: kardex operativo por empleado/tecnico
- capability esperada: `inventory_kardex_by_employee` o, en su defecto semantico, una variante consolidada con filtro por `cedula`

Regla de negocio:

- Kardex = movimientos dia a dia, entradas y salidas, y saldo por codigo
- Kardex por empleado/tecnico se resuelve por cedula usando movimientos de materiales/ferretero, conservando fecha, tipo de movimiento, codigo, descripcion, tipo, cantidad y efecto sobre saldo.
- Si la consulta combina `codigo + empleado/tecnico + cedula`, se mantiene la familia `kardex por empleado` y se agrega filtro por `codigo`; no debe degradarse a un kardex consolidado generico por codigo.
- En dashboard, ese resultado debe mostrarse como tabla operativa de kardex. No se debe reconstruir un chart sintetico desde filas transaccionales salvo que el backend entregue una grafica explicita.

Fuentes operativas minimas:

- `logistica_movimientos_entrega`
- `logistica_movimientos_devolucion`
- `logistica_movimientos_consumo`
- `logistica_movimientos_cobro`

Enriquecimiento requerido:

- `bd_c3nc4s1s.cinco_base_de_personal`
- no excluir empleados inactivos en enrichment historico

Catalogo requerido:

- `base_codigos`

Columnas minimas esperadas:

- `fecha`
- `tipo_movimiento`
- `codigo`
- `descripcion`
- `tipo`
- `cedula`
- `empleado`
- `movil`
- `estado_empleado`
- `bodega`
- `orden_trabajo`
- `ticket` cuando exista trazabilidad gobernada
- `entrada`
- `salida`
- `cantidad`
- `efecto`
- `saldo_movimiento`

Reglas de saldo:

- `entrega` suma como `entrada`; no debe invertirse como `salida`
- `devolucion` resta como `salida` mientras la formula vigente siga siendo descuento al saldo del empleado
- `consumo` resta
- `cobro` resta
- el saldo acumulado debe calcularse en orden cronologico ascendente por `fecha, movimiento_id`
- la visualizacion puede ordenarse descendente, pero no debe recalcular el saldo sobre el subconjunto visible
- no filtrar solo positivos
- incluir positivos, cero y negativos cuando apliquen

Regla documentada:

- `Kardex materiales/ferretero: entrega suma como entrada; consumo, cobro y devolucion restan como salida. El saldo acumulado debe calcularse en orden cronologico y no debe invertir el signo de entregas.`

Regla de familia:

- si no especifica tipo, incluir `material` y `ferretero`
- si dice `material claro`, filtrar solo `tipo = 'material'`
- si dice `ferretero`, filtrar solo `tipo = 'ferretero'`

Regla sobre serializados:

- si el usuario pide solo kardex generico, evaluar si existe trazabilidad suficiente para serializados/equipos
- si no existe trazabilidad cronologica confiable por cedula para serializados, responder materiales/ferretero y aclarar esa limitacion concreta
- no bloquear toda la consulta por la ausencia de esa trazabilidad serializada

## Regla Semantica Persistida 2026-05-17: familia serializada por coincidencia parcial gobernada

Cuando el usuario consulte una familia serializada por texto parcial, la resolucion correcta no es exigir igualdad exacta sobre `base_codigo_seriales.familia`.

Regla estable:

1. validar la familia contra `logistica_cinco.base_codigo_seriales.familia`
2. usar coincidencia parcial gobernada
   - `match_mode: contains`
   - normalizacion: `upper/trim`
3. si hay coincidencia de catalogo, mantener el filtro semantico como familia serializada
4. luego dejar que el planner seguro resuelva:
   - catalogo -> codigos
   - seriales -> estado operativo
   - enrichment de personal cuando aplique

Ejemplos validos:

- `Deco` puede cubrir `DECO`, `DECO HD`, `CPE DECO`, `TARJETA DECO`
- `ONT` puede cubrir variantes catalogadas como `ONT GPON`
- `Router` puede cubrir variantes catalogadas como `ROUTER WIFI`
- `CPE residencial` puede cubrir variantes catalogadas equivalentes del catalogo serializado

Regla critica:

- no hardcodear una familia concreta como excepcion
- no degradar la familia serializada a descripcion de materiales solo por no existir igualdad exacta
- la metadata debe gobernar la coincidencia parcial; el planner sigue siendo autoridad unica de SQL seguro

## Regla De Diagnostico Persistida Para Fallbacks Falsos En Empleados

Cuando una consulta de `empleados`, `rrhh` o un rescate hacia `inventario_logistica`:

- termine en `general.answer.v1`
- caiga en `legacy_fallback`
- o muestre la respuesta generica `Puedo ayudarte con empleados...`

no asumir de entrada que:

- el dominio no esta habilitado
- el planner no soporta la consulta
- el agente hibrido de inventario es la causa

Secuencia minima obligatoria de validacion:

1. revisar si `query_intelligence` produjo `error`
2. revisar si `execution_plan` quedo vacio
3. revisar si el `fallback_reason` visible es solo consecuencia de ese error interno

Hecho confirmado y persistido:

- existio un incidente real donde `query_intelligence` fallaba con `name 'AIDictionaryRemediationService' is not defined`
- la causa era un import faltante en `SemanticBusinessResolver`
- el efecto visible fue degradacion a:
  - `general.answer.v1`
  - `legacy_fallback`
  - razon `capability_mode_domain_not_enabled_yet`

Implicacion arquitectonica:

- un `fallback_reason` de routing no siempre refleja la causa raiz
- primero se debe descartar excepcion interna en la capa semantica moderna antes de diagnosticar contratos, rollout o YAML hibrido

Caso ya validado y no reabrir sin sintoma nuevo:

- `certificados de altura proximos a vencer`

Estado confirmado:

- el incidente no fue causado por `inventario_logistica` hibrido
- despues de corregir el import faltante, la consulta volvio a resolver por `sql_assisted`

## Refuerzo Operativo 2026-05-11

Reglas confirmadas en esta sesion:

- La consulta `certificados de altura proximos a vencer` debe seguir resolviendo en el dominio `empleados`.
- Para este caso, la salida moderna esperada es:
  - `query_intelligence` activo
  - `execution_plan.strategy = sql_assisted`
  - `metadata.metric_used = certificado_alturas_vigencia`
- No diagnosticar esta consulta como falla del hibrido `inventario_logistica` salvo que exista un sintoma nuevo y especifico de ese dominio.

Regla de observabilidad para `empleados`:

- Si `query_intelligence` falla dentro del pipeline moderno de `empleados`, el error no debe perderse.
- Debe quedar visible como minimo en:
  - `run_context.metadata.query_intelligence.error`
  - evento de observabilidad `query_intelligence_error`

Regla de integridad semantica para YAML/metadata versionada:

- Toda relacion declarada en el YAML hibrido debe apuntar a columnas explicitamente declaradas en `tables.<tabla>.columns`.
- Si una relacion usa una columna opcional o incompleta en metadata real, declararla igual con `missing_metadata_allowed: true` cuando corresponda.
- Caso confirmado:
  - `devolucion_movil_to_personal` requeria declarar `logistica_movimientos_devolucion.movil`

Implicacion practica:

- No todo sintoma de runtime proviene del planner o del fallback.
- Tambien deben vigilarse inconsistencias de metadata versionada:
  - relaciones con columnas no declaradas
  - campos usados por joins semanticos pero ausentes en el YAML

## Regla Arquitectonica Validada 2026-05-16: consulta -> tarea ejecutable

La capa semantica ya no debe pensarse como un mecanismo para redactar respuestas de chat.
Debe pensarse como compilador de tareas empresariales ejecutables.

### Contrato objetivo

Toda consulta debe intentar producir un artefacto de este tipo antes de redactar texto:

- `task_id`
- `run_id`
- `domain`
- `intent`
- `candidate_capability`
- `input_entities`
- `normalized_filters`
- `execution_mode`
- `required_tools`
- `required_approvals`
- `validation_plan`
- `evidence_plan`
- `final_state`

Regla:
 
- si no existe tarea ejecutable segura, el sistema debe responder bloqueo o aclaracion
- si existe tarea ejecutable segura, el texto final solo resume lo que la tarea ya ejecuto

### Fase 1 ya aplicada sobre `/ia-dev/chat/`

Sin migrar todavia a `Agents SDK`, el contrato HTTP actual ya debe exponer un sobre minimo de tarea compatible con el chat existente:

- `task.task_id`
- `task.current_run.run_id`
- `task.current_run.status`
- `task.current_run.domain`
- `task.current_run.intent`
- `task.current_run.plan`
- `task.current_run.required_tools`
- `task.current_run.validation`
- `task.current_run.evidence`
- `task.current_run.final_state`
- `task.current_run.reply`

Reglas de esta fase:

- `reply` top-level se conserva por compatibilidad con frontend.
- `task.current_run.reply` debe espejar el `reply` final.
- `task_id` puede alinearse temporalmente con el `workflow_key` persistido.
- `QueryExecutionPlanner` no cambia.
- `ai_dictionary` no cambia.
- el sobre `task` reutiliza la traza ya existente del runtime y no reemplaza `BusinessQuerySemanticPlan`.

### Fase 2 ya aplicada: Declarative Tool Registry

La ejecucion ya no debe depender de resolver handlers ad hoc desde la capa de chat.
Debe existir un registry declarativo unico de herramientas ejecutables.

Componentes agregados:

- `tool_id`
- `tool_definition`
- `input_schema`
- `output_schema`
- `execution_policy`
- `approval_policy`
- `audit_metadata`
- `tool_execution_trace`

Reglas de esta fase:

- los handlers productivos actuales se registran como tools declarativas
- `QueryExecutionPlanner` sigue siendo autoridad unica para SQL y se expone solo como tool declarativa interna `query_execution_planner.sql_assisted`
- el registry no reemplaza `BusinessQuerySemanticPlan`
- el registry no reemplaza `ai_dictionary`
- el registry separa:
  - reasoning
  - planning
  - execution
- la respuesta compatible sigue entregando `reply`, pero la corrida debe dejar tambien metadata y traza de tool persistida en `task_state`

Flujo vigente GPT / planner / tools:

1. GPT/OpenAI ayuda a semantizar y desambiguar
2. la capa semantica produce `BusinessQuerySemanticPlan`
3. el planner o el runtime selecciona la tool declarativa aplicable
4. la ejecucion deja:
   - tool seleccionada
   - policy aplicada
   - evidencia
   - trace persistida
5. el texto final resume una ejecucion real ya trazada

### Reparto de responsabilidades aprobado

1. Capa semantica

- interpreta negocio
- normaliza entidad, filtros, capacidad y alcance
- produce `BusinessQuerySemanticPlan`
- declara si falta contexto
- no ejecuta SQL
- no inventa tools

2. Planner / runtime de tarea

- traduce el plan semantico a tarea ejecutable
- decide herramienta o ruta
- ejecuta SQL o servicio
- adjunta evidencia
- persiste estado y trazabilidad

3. LLM / OpenAI

- ayuda a desambiguar
- ayuda a sugerir capability
- ayuda a revisar satisfaccion
- ayuda a redactar resumen ejecutivo sobre evidencia ya producida
- no debe ser el owner de la respuesta final si no existe ejecucion real

### Mapeo objetivo a OpenAI Responses API + Agents SDK

1. `Responses API`

- superficie unica de modelos
- gateway interno unico para:
  - model policy
  - timeout/retries
  - metadata y trace metadata
  - logging comun
  - normalizacion de errores
- function tools o MCP tools para las capacidades ejecutables
- uso de `store` y continuidad cuando convenga
- uso de `background` para tareas largas
- evitar llamadas aisladas y dispersas por servicio

### Fase 3 aplicada: Unified OpenAI Gateway

Regla vigente:

- toda llamada interna a `Responses API` debe pasar por un gateway comun
- los servicios de negocio no deben instanciar `OpenAI()` ni llamar `client.responses.create(...)` directamente
- el gateway no decide dominio, intencion, planner ni ejecucion
- el gateway solo estandariza la invocacion del modelo y deja metadata uniforme para trazabilidad

Metadata minima uniforme del gateway:

- `component`
- `model`
- `model_source`
- `response_id`
- `timeout_seconds`
- `retries`
- `trace_metadata`
- `request_metadata`
- `usage`

2. `Agents SDK`

- manager agent para intake y routing
- specialist agents por dominio
- tools locales para:
  - planner SQL seguro
  - ejecucion de handlers
  - memoria
  - tickets
  - propuestas de conocimiento
- guardrails/human review para aprobaciones y escrituras sensibles
- tracing nativo para model calls, tool calls, handoffs y validaciones

### Lo que NO debe cambiar

- `ai_dictionary` sigue mandando en lo estructural
- `BusinessQuerySemanticPlan` sigue existiendo
- `QueryExecutionPlanner` sigue siendo autoridad unica de SQL seguro
- memorias de negocio siguen siendo persistidas y auditables
- validadores de satisfaccion siguen antes de presentar resultado como exitoso

### Lo que SI debe cambiar

- dejar de tratar `reply` como producto principal
- dejar de mezclar orquestacion de tarea con superficie de chat
- convertir handlers y servicios internos en registry declarativo de tools
- unificar las invocaciones OpenAI en un gateway comun
- hacer que cada corrida deje:
  - estado
  - evidencia
  - validacion
  - aprobaciones requeridas
  - resultado final

### Regla persistida para futuros cambios

Cuando se implemente una nueva capacidad:

1. primero modelar semantica en `ai_dictionary` y memoria gobernada
2. luego definir el contrato de tarea ejecutable
3. despues exponer la ejecucion como tool o ruta deterministica auditable
4. por ultimo redactar la respuesta humana sobre evidencia ya producida

No volver a aceptar como estado final una respuesta que solo "suena correcta" si no deja:

- ruta ejecutada
- evidencia
- validacion
- trazabilidad

## Fase 4 Aplicada: Responses API Native Tools Sobre Runtime Existente

Regla vigente:

- OpenAI ya puede usar native tools del `Responses API`, pero solo sobre tools declarativas gobernadas por el runtime.
- El runtime sigue siendo autoridad de ejecucion.
- `QueryExecutionPlanner` sigue siendo la unica autoridad de SQL seguro.
- el modelo puede:
  - seleccionar tool
  - pedir ejecucion
  - recibir `function_call_output`
  - continuar reasoning
- el modelo no puede:
  - ejecutar SQL arbitrario
  - saltarse validadores
  - modificar `ai_dictionary`
  - escribir memoria gobernada

Contrato de gobierno de tools:

1. `Tool Registry` declara la tool.
2. el gateway la convierte a schema OpenAI `tools=[]`.
3. el modelo solo propone `function_call`.
4. el runtime ejecuta la tool declarativa permitida.
5. el runtime devuelve output estructurado y evidencia.
6. la traza de tool queda persistida en `task_state` y observabilidad.

Primera exposicion segura ya aplicada:

- tools semanticas de contexto gobernado
- handlers deterministas auto-aprobados
- planner `sql_assisted` solo como tool declarativa auditada del runtime

Regla critica:

- esta fase agrega native tools sobre el runtime deterministico actual
- no reemplaza el runtime actual
- no introduce todavia `Agents SDK`, handoffs ni background runs

## Fase 5 Aplicada: Agents SDK Orchestration Layer Sobre Runtime Existente

Regla vigente:

- `Agents SDK` ya existe como capa oficial de coordinacion multiagente sobre el runtime actual.
- el runtime deterministico sigue siendo autoridad de ejecucion.
- `QueryExecutionPlanner` sigue siendo la unica autoridad de SQL seguro.
- `ai_dictionary` sigue siendo autoridad estructural.
- los agentes coordinan, delegan, resumen y dejan tracing; no reemplazan planner, validadores ni handlers.

Arquitectura vigente:

1. usuario
2. `manager_agent`
3. specialist agent
4. tools declarativas existentes
5. runtime actual
6. planner/handlers/SQL seguro
7. `task envelope` + evidencia

Agentes iniciales:

- `manager_agent`
- `inventory_agent`
- `empleados_agent`
- `ausentismo_agent`
- `semantic_resolution_agent`

Reglas de coordinacion:

- el manager decide especialista usando dominio/intencion/capability ya gobernados por el runtime.
- la delegacion se expone como `agents-as-tools` desde un registry dedicado.
- los especialistas trabajan con contexto semantico gobernado y tools declarativas existentes.
- ninguna decision del manager o del especialista puede:
  - generar SQL libre
  - duplicar planners dentro del prompt
  - alterar `fallback_policy`
  - alterar `ai_dictionary`
  - saltarse validadores

Responsabilidades por capa:

1. `manager_agent`

- intake
- routing
- delegacion a especialista
- consolidacion
- no ejecuta SQL libre
- no reemplaza logica de negocio

2. specialist agents

- resuelven intencion del dominio
- enriquecen contexto
- recomiendan tools declarativas del runtime
- dejan trace auditable

3. runtime deterministico

- sigue validando
- sigue ejecutando
- sigue siendo owner de seguridad, planner y evidencia

Persistencia/tracing vigente:

- `task.current_run.agents`
- `task.current_run.handoffs`
- `task_state.state.agents`
- `task_state.state.handoffs`
- `task_state.state.agent_trace`
- `data_sources.runtime.agents`
- `data_sources.runtime.handoffs`
- `data_sources.runtime.agent_trace`

Limitacion vigente:

- si el paquete oficial del Agents SDK no esta instalado, la capa usa implementacion compatible sobre `OpenAIGatewayService` + function tool loop.
- esta fase prepara handoffs y approvals, pero no activa todavia approvals humanas completas ni background runs productivos.

## Fase 6 Aplicada: Handoffs Gobernados + Approvals Sobre Runtime Existente

Regla vigente:

- OpenAI coordina.
- el runtime valida.
- las tools ejecutan.
- las acciones sensibles requieren approval.
- ningun agente puede saltarse policy, validadores ni approvals.

Gobierno aprobado:

1. handoffs

- el manager puede delegar a specialist agents, pero cada handoff queda trazado y gobernado.
- el handoff no mueve autoridad de negocio al modelo.
- el handoff solo coordina:
  - especialista destino
  - tool objetivo sugerida
  - evidencia previa

2. approvals

- las tools read-only seguras y `query_execution_planner.sql_assisted` siguen auto-aprobadas.
- las tools con policy sensible o `requires_approval` no se ejecutan sin approval explicito.
- si falta approval:
  - no ejecutar
  - dejar la tarea en `awaiting_approval`
  - responder con evidencia previa
  - emitir `resume_token`

Estados esperados del runtime:

- `planned`
- `executing`
- `awaiting_approval`
- `approved`
- `rejected`
- `blocked`
- `completed`
- `failed`

Persistencia requerida de esta fase:

- `task.current_run.approvals`
- `task.current_run.handoffs`
- `task.current_run.status`
- `task_state.approval_trace`
- `task_state.handoff_trace`
- eventos de observabilidad de approvals y handoffs

Regla critica:

- Fase 6 agrega gobierno y approvals sobre el runtime actual.
- no reemplaza `QueryExecutionPlanner`, `ai_dictionary`, `Tool Registry`, `OpenAI Gateway` ni `Agents Runtime`.
- la evidencia manda sobre el texto tambien en flujos pausados por approval.

## Fase 7 Aplicada: Background Runs Sobre Runtime Existente

Regla vigente:

- los `background runs` agregan duracion, estado, polling, checkpoints y resume.
- los `background runs` no agregan autoridad de negocio nueva.
- OpenAI coordina.
- el runtime valida y gobierna estado.
- las tools ejecutan.
- approvals siguen gobernando acciones sensibles.

Que cambia conceptualmente:

1. el sistema ya no solo puede responder `sync`.

- ahora una tarea puede quedar:
  - `queued`
  - `running`
  - `awaiting_approval`
  - `paused`
  - `resumed`
  - `completed`
  - `failed`
  - `cancelled`
  - `expired`

2. el `task-first contract` ahora tambien debe soportar ejecucion larga.

Metadata minima esperada:

- `background_run_id`
- `job_id`
- `queue_status`
- `run_status`
- `polling`
- `resume_token`
- `checkpoint`
- `partial_evidence`
- `final_evidence`
- `cancellation`
- `failure_reason`
- `retry`
- `timeout`

Contrato operativo adicional para `inventory_provider_serial_validation`:

- cuando el runtime quede en `queued`, `running` o `resumed`, la respuesta de polling debe ser ligera
- la semantica visible para UI debe salir de:
  - `task.current_run.evidence.background_progress`
  - `task.current_run.semantic_explanation.background_status`
  - `data.meta.background_job`
- esa superficie debe contener solo evidencia persistida y real:
  - `background_run_id`
  - `status`
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
- si el estado ya es terminal, el runtime puede volver a exponer el snapshot completo

3. el resume no es autoridad nueva.

- reanudar una corrida solo permite continuar una tarea ya gobernada.
- no habilita SQL libre.
- no habilita tools fuera de policy.
- no relaja validadores.

Regla arquitectonica critica:

- si una corrida larga necesita approval, debe pasar a `awaiting_approval`.
- al aprobar, puede pasar a `resumed`.
- la evidencia previa y posterior debe quedar trazada.
- `agent_trace`, `tool_execution_trace`, `approval_trace` y `handoff_trace` no deben perder continuidad por el resume.

Politica vigente:

1. consultas rapidas read-only:

- siguen sync

2. SQL seguro normal:

- sigue sync mientras no exista policy de background

3. tareas largas:

- pueden pasar a background por:
  - declaracion de tool
  - policy runtime
  - approval pendiente

4. cancelacion o falla:

- no deben borrar evidencia previa
- deben dejar estado final claro

Regla final:

- Fase 7 administra duracion y estado.
- no cambia la autoridad de `ai_dictionary`.
- no cambia la autoridad de `QueryExecutionPlanner`.
- no cambia la autoridad del `Tool Registry`.
- no cambia la autoridad del `OpenAI Gateway`.
- no cambia la autoridad del `Agents Runtime`.
- no cambia la autoridad del `Approval Runtime`.

## Regla Enterprise Persistida 2026-05-16: hardening central sin mover autoridad

El endurecimiento enterprise del runtime debe hacerse como enforcement central de limites y governance, no como nueva autoridad semantica.

Responsabilidades estables:

1. GPT/OpenAI

- coordina
- razona dentro de limites
- no supera limites de tool loop
- no persiste evidencia sensible en claro por decision propia

2. Runtime endurecido

- aplica limites de loop, retries, background duration y approval wait
- redacciona evidencia sensible antes de persistir traces operativas
- persiste correlation IDs, lineage y runtime metrics
- puede bloquear resumes expirados y corridas en loop

3. Tools y planners

- siguen ejecutando bajo contratos existentes
- no cambian autoridad por el endurecimiento

Regla critica:

- el hardening central refuerza seguridad, trazabilidad y operacion
- no autoriza al modelo a saltarse `QueryExecutionPlanner`, `ai_dictionary`, approvals ni validadores
- endpoints operativos, health checks o trace explorers solo exponen estado persistido y saneado; no crean una autoridad semantica nueva

## Regla Arquitectonica Persistida 2026-05-16: pattern-first solo como acelerador, no como autoridad

Los patrones, examples, query fastpaths y detectores deterministas pueden ayudar a acelerar interpretacion, pero no deben gobernar la resolucion final.

Orden correcto:

1. pregunta del usuario
2. interpretacion inicial o familia candidata
3. validacion contra `ai_dictionary`, `dd_tablas`, `dd_campos`, `dd_relaciones`, `dd_sinonimos`, `dd_reglas`, `ia_dev_capacidades_columna`
4. construccion de `BusinessQuerySemanticPlan`
5. seleccion y validacion de capability/tool
6. `QueryExecutionPlanner` o runtime deterministico como autoridad final de ejecucion
7. respuesta sobre evidencia

Reglas estables:

- un `query_pattern`, example o regex puede sugerir:
  - dominio
  - intent
  - capability
  - filtros probables
- un `query_pattern`, example o regex no puede:
  - reemplazar metadata estructural
  - reemplazar sinonimia gobernada
  - disparar SQL o respuesta final por si solo
  - ocultar faltantes reales de metadata
  - inventar tablas, columnas o reglas

Regla sobre familias semanticas:

- las familias validas si pueden seguir existiendo
- pero deben expresarse como semantica gobernada y reutilizable, no como frase cerrada
- los ejemplos entrenan interpretacion
- `ai_dictionary` gobierna

Regla sobre respuesta final:

- la capa de respuesta no debe inferir negocio principalmente desde texto ya redactado
- debe preferir:
  - `semantic_trace`
  - `execution metadata`
  - `kpis`
  - `result_set`
  - reglas gobernadas

Implicacion de implementacion:

- si una regla de negocio solo vive en `if`, `elif`, regex o keywords Python y no puede trazarse a metadata/capabilities, debe tratarse como deuda tecnica o hardcode segun su impacto

## Regla Semantica Persistida 2026-05-16: matcher gobernado inventory capability-first

Para las familias P1 de `inventario_logistica`, la resolucion correcta ya no debe depender principalmente de frases exactas ni regex como autoridad.

Orden correcto para estas familias:

1. pregunta del usuario
2. sinonimia y reglas gobernadas
   - `dd_sinonimos`
   - `dd_reglas`
   - `ia_dev_capacidades_columna`
   - memoria confirmada `inventory.semantic.*`
3. dominio candidato
4. campos candidatos
5. filtros normalizados
6. capability candidata
7. `BusinessQuerySemanticPlan`
8. planner/runtime deterministico

Familias P1 cubiertas:

- `cuadrilla | movil | brigada` => `movil`
- numerico operativo => `cedula`
- alfanumerico operativo => `movil`
- `kardex | movimientos | entradas y salidas` por empleado/tecnico => `inventory_kardex_by_employee`
- `material claro | material de claro` => `tipo = material`
- `ferretero | ferreteria | material ferretero` => `tipo = ferretero`
- inventario generico por movil/cuadrilla => doble bloque materiales + serializados cuando aplique
- serializados => conteo, no cantidad
- `actas SAP` => limitacion declarada, no respuesta inventada

Regla critica:

- los patterns, fastpaths y regex pueden quedar como fallback sombreado
- no pueden ser autoridad final si existe ruta gobernada para esa familia
- la capa de respuesta debe preferir `semantic_context`, `semantic_trace` y `BusinessQuerySemanticPlan` antes que inferir desde texto renderizado o desde la frase original del usuario

## Regla Arquitectonica Persistida 2026-05-16: Semantic Capability Registry como autoridad unica de binding

Cuando una consulta ya fue semantizada, el sistema no debe volver a decidir el binding de negocio en multiples capas.

Binding a centralizar en una sola autoridad:

- `intent`
- `entity`
- `normalized_filters`
- `output profile`
- `candidate_capability`
- `template_id`
- `planner_route_hint`
- `response_profile`

Distribucion estable de responsabilidades:

1. `SemanticCapabilityRegistry`

- interpreta binding semantico gobernado
- consolida `intent/entity/filter/output -> capability/template/planner_route_hint/response_profile`
- usa `ai_dictionary`, `dd_*`, `ia_dev_capacidades_columna` y memoria confirmada como autoridad
- no decide SQL
- no decide `execute=True`
- no ejecuta tools

2. `ToolRegistryService`

- sigue siendo la unica autoridad de `capability -> tool_id`
- no redefine semantica de negocio

3. `QueryExecutionPlanner`

- sigue siendo la unica autoridad de estrategia y SQL seguro
- consume binding ya resuelto
- solo puede aplicar overrides tecnicos o bloqueos seguros
- no debe convertirse en una segunda autoridad semantica de capability/template salvo compatibilidad temporal auditada

4. `response_assembler`

- debe preferir `response_profile`, `BusinessQuerySemanticPlan`, `semantic_trace` y metadata de ejecucion
- no debe reconstruir la semantica principal desde texto o heuristicas aisladas de columnas cuando ya exista binding gobernado

Regla critica:

- si el mismo mapping `intent/entity/filter/output -> capability/template/route/response` vive en matcher, resolver, orchestrator, adapter y planner, eso es deuda tecnica
- los patterns y fastpaths pueden proponer candidatos
- el registry semantico debe decidir una sola vez

## Regla Arquitectonica Persistida 2026-05-16: migracion de hardcodes semanticos a metadata gobernada

Cuando una regla de negocio de un dominio operativo aparezca en Python como:

- `if` o `elif` por frase
- regex de semantica de negocio
- lista de tokens o aliases
- `template map`
- `capability map`
- `response profile map`

debe clasificarse explicitamente antes de crecer:

1. `dd_sinonimos`
2. `dd_reglas`
3. `dd_relaciones`
4. `dd_campos`
5. `ia_dev_capacidades_columna`
6. validacion tecnica que se queda en codigo
7. fallback sombreado temporal

Regla estable:

- la metadata gobierna negocio
- el codigo gobierna validacion tecnica y compilacion segura

Distribucion correcta:

1. `dd_sinonimos`

- alias de usuario
- vocabulario real
- equivalencias de lenguaje

2. `dd_reglas`

- reglas semanticas reutilizables
- defaults
- restricciones
- limitaciones declaradas
- criterios de prioridad

3. `dd_relaciones`

- enrichment
- cobertura
- dependencias entre fuentes

4. `dd_campos`

- conceptos logicos
- identificadores
- soportes de filtro y agrupacion

5. `ia_dev_capacidades_columna`

- binding `intent/entity/filter/output -> template_id/capability/planner_route_hint/response_profile`

6. Codigo

- regex de saneamiento
- validaciones de formato
- compilacion SQL segura
- formulas y joins efectivos
- enforcement tecnico

Regla critica:

- una regex puede extraer un valor
- pero no debe ser la autoridad final de negocio si la misma semantica puede vivir en metadata

Regla de migracion segura:

1. primero sembrar la regla en metadata
2. luego hacer que `SemanticCapabilityRegistry` la lea desde metadata
3. despues dejar el hardcode viejo solo como fallback sombreado con traza
4. por ultimo eliminar el hardcode cuando exista cobertura de tests anti-hardcode

Regla de trazabilidad:

- toda decision de binding semantico debe poder decir:
  - `source_table`
  - `rule_id` o `binding_id`
  - `matched_rules`
  - `fallback_used`
  - `legacy_mapping_used`

Regla final:

- no mover formulas SQL ni autoridad de `QueryExecutionPlanner` al diccionario
- no usar metadata para reemplazar guardrails tecnicos
- si una regla mezcla negocio y compilacion, separar primero la parte semantica de la tecnica antes de migrar

## Regla Arquitectonica Persistida 2026-05-16: trazabilidad obligatoria en migracion metadata-first

Cuando una decision semantica de `inventario_logistica` se resuelva por metadata gobernada, la traza debe distinguir explicitamente metadata vs legacy.

Campos minimos de traza:

- `regla_metadata_usada`
- `fuente_dd`
- `fallback_sombreado_usado`
- `regla_legacy_detectada`
- `regla_migrada`

Regla estable:

- si la decision sale de `dd_sinonimos`, `dd_reglas` o `ia_dev_capacidades_columna`, debe quedar visible que regla gobernada participo.
- si la decision cae en mapa heredado o compatibilidad temporal, debe quedar visible como fallback sombreado y no como autoridad normal.
- la comparacion metadata vs legacy debe quedar en `semantic_trace`, `binding_trace` o metadata semantica equivalente, nunca oculta solo en logs efimeros.

Motivo:

- permite demostrar migracion real de negocio fuera de Python
- evita confundir compatibilidad temporal con gobierno definitivo
- habilita tests anti-hardcode y retiro seguro de reglas heredadas

## Regla Arquitectonica Persistida 2026-05-16: response assembly evidence-first

La respuesta final no debe construirse principalmente desde:

- frase literal del usuario
- `reply` previo redactado
- regex o keywords sobre texto final
- inferencias de riesgo desde narrativa ya escrita

La respuesta final debe construirse primero desde evidencia estructurada:

- `BusinessQuerySemanticPlan`
- `semantic_context`
- `semantic_capability_registry`
- `response_profile`
- `tool_execution`
- `validation`
- `query_execution_trace`
- `result_set`
- `extra_tables`
- `known_limitations`

Regla estable:

1. primero se ejecuta o se bloquea la tarea gobernada
2. luego se resume el resultado humano sobre esa evidencia
3. si falta evidencia suficiente:
   - no presentar exito
   - responder aclaracion, bloqueo o limitacion declarada
4. si el resultado esta vacio:
   - explicar desde `result_set`, filtros y alcance ejecutado
   - no inventar causa

Campos minimos de traza para la capa de respuesta:

- `response_profile_usado`
- `evidence_sources_used`
- `semantic_context_used`
- `fallback_narrativo_usado`
- `missing_evidence_reason`

Regla critica:

- `reply` es superficie final de lectura humana
- no es la fuente de verdad semantica
- la fuente de verdad semantica y de cierre debe ser la evidencia ejecutada o la limitacion gobernada

## Regla Arquitectonica Persistida 2026-05-16: explicacion semantica saneada para UX de confianza

La UI no debe mostrar solo la respuesta final cuando ya existe metadata suficiente para explicar la tarea.

La explicacion visible al usuario debe derivarse de estado gobernado y saneado como:

- `BusinessQuerySemanticPlan`
- `semantic_context`
- `semantic_trace`
- `response_profile`
- `tool_execution`
- `validation`
- `evidence_summary`
- `approvals`
- `background`

La explicacion no debe derivarse de:

- `reply` libre como fuente principal
- prompts internos
- chain-of-thought
- traces crudos
- SQL sensible

Campos funcionales esperados para UX:

- que entendio el sistema
- dominio e intencion
- entidad y filtros normalizados
- capability y herramienta usadas
- validaciones
- evidencia encontrada
- limitaciones o aclaraciones
- estado actual de la tarea
- agentes o ruta participantes
- indicadores de metadata gobernada y fallback sombreado

Regla critica:

- esto no es debug visual
- es trazabilidad saneada para confianza, adopcion y soporte seguro

## Regla Arquitectonica Persistida 2026-05-16: Capability Pack empresarial como organizador y validador

Cuando un dominio operativo ya tiene metadata, capabilities, tools, perfiles y evals dispersos pero estables, debe poder formalizarse como un `Capability Pack` versionado.

Objetivo:

- organizar el dominio
- declarar su cobertura operacional
- validar consistencia
- documentar rutas, limitaciones y perfiles
- publicar traza saneada reutilizable

Contenido minimo del pack:

- metadata de dominio y version
- procesos operativos cubiertos
- entidades
- reglas semanticas
- capabilities
- tools declaradas
- response profiles
- approval policies
- evaluaciones
- limitaciones declaradas
- explicacion semantica esperada

Regla critica:

- el pack no reemplaza `ai_dictionary`
- el pack no reemplaza `QueryExecutionPlanner`
- el pack no reemplaza `ToolRegistryService`
- el pack no autoriza SQL
- el pack no inventa tablas ni columnas
- el pack organiza y valida el binding gobernado ya existente

Trazabilidad minima requerida del pack:

- `paquete_capacidad_usado`
- `version_paquete`
- `capacidades_declaradas`
- `reglas_declaradas`
- `perfiles_respuesta`
- `evaluaciones_asociadas`

Orden correcto:

1. metadata gobernada y sinonimia validan negocio
2. `SemanticCapabilityRegistry` resuelve binding
3. `Capability Pack` valida y documenta ese binding
4. `ToolRegistryService` resuelve tool
5. `QueryExecutionPlanner` decide estrategia y SQL seguro
6. la respuesta final y la UX exponen la traza saneada del pack

## Regla Arquitectonica Persistida 2026-05-16: Continuous Runtime Learning registra pero no autocorrige

`Continuous Runtime Learning` es una capacidad transversal posterior a P1-P7 para aprender desde uso real sin mover autoridades.

Objetivo:

- registrar consultas no resueltas
- clasificar brechas semanticas y operativas
- priorizar backlog de mejora
- proponer cambios gobernados

No puede:

- corregir metadata sola
- escribir automaticamente en `dd_*`
- modificar automaticamente `ai_dictionary`
- crear automaticamente capabilities, tools o agentes
- saltarse `QueryExecutionPlanner`, `ToolRegistryService`, `SemanticCapabilityRegistry` ni validadores

Regla critica:

- observability registra eventos
- `registro_brechas_semanticas` registra gaps accionables
- la mejora sigue siendo humana y gobernada

## Regla Arquitectonica Persistida 2026-05-16: revision gobernada de brechas semanticas

Registrar una brecha no equivale a corregirla.

Flujo estable:

- `registro_brechas_semanticas`
- revision
- propuesta
- aprobacion cuando aplique
- aplicacion gobernada
- validacion o eval
- cierre

Estados operativos de negocio permitidos:

- `nueva`
- `en_revision`
- `requiere_metadata`
- `requiere_sinonimo`
- `requiere_regla`
- `requiere_relacion`
- `requiere_capacidad`
- `requiere_tool`
- `requiere_agente`
- `requiere_aclaracion_usuario`
- `fuera_de_alcance`
- `resuelta`
- `descartada`

Regla critica:

- una propuesta puede sugerir:
  - metadata
  - sinonimia
  - reglas
  - relaciones
  - capabilities
  - tools
  - agentes
  - mejoras de respuesta o eval
- la sugerencia no autoriza aplicacion automatica
- toda aplicacion sobre metadata, capabilities, tools o agentes requiere gobierno y approval cuando la policy lo marque
- el cierre debe dejar trazabilidad de:
  - quien reviso
  - que decidio
  - que referencia se creo
  - que prueba o eval valido la resolucion


## Regla Semantica Persistida 2026-05-16: familia serializada catalogada por dimension operativa

Cuando una consulta de `inventario_logistica` pida `saldo`, `inventario`, `existencia` o equivalentes y ademas:

- mencione una familia gobernada del catalogo `logistica_cinco.base_codigo_seriales.familia`
- o un alias gobernado de esa familia dentro de serializados/equipos/CPE
- y pida agrupacion por `movil`, `cuadrilla`, `tecnico`, `empleado` o `bodega`

la resolucion correcta es:

1. validar primero la familia contra el catalogo gobernado de serializados
2. si existe, clasificar `inventory_family = serializados`
3. normalizar filtro `material_family = <familia_catalogada>`
4. resolver capability `inventory_serial_stock_by_family_grouped_dimension`
5. dejar al planner seguro construir SQL sobre:
   - `logistica_base_seriales`
   - `base_codigo_seriales`
   - `cinco_base_de_personal` cuando aplique enrichment por portador
6. responder sobre evidencia y conteo, no sobre cantidad

Reglas estables:

- una familia catalogada de `base_codigo_seriales.familia` no debe degradarse automaticamente a descripcion de `base_codigos`
- `en moviles` significa agrupacion por movil, no solicitud de un movil especifico faltante
- serializados usan conteo:
  - `en_movil = estado contiene MOVIL`
  - `en_base = estado contiene BASE o BODEGA`
  - `cobros = estado contiene COBRO`
  - `saldo = en_movil + en_base - cobros`
- si la familia existe en catalogo pero no hay seriales asociados al alcance, responder vacio con evidencia de catalogo
- si la familia no existe en catalogo y no hay sinonimia gobernada suficiente, responder limitacion o aclaracion; no inventar familia ni reinterpretar por texto libre como autoridad
