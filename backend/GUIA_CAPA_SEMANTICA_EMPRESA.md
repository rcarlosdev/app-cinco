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

Cada familia debe terminar en:

- entidad normalizada
- filtros normalizados
- capability candidata
- reglas de negocio aplicables
- limitaciones conocidas
- salida esperada

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
- no decidir `execute=True`
- no saltarse `ai_dictionary`
- no relajar validadores
- no ocultar saldos cero o negativos
- no activar `legacy` o `fallback` como implementacion

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
