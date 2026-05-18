Micro resumen actualizado

No reauditar arquitectura ni contratos. No tocar `fallback_policy`. No reabrir discovery del dominio. Continuar desde el estado actual de `inventario_logistica`.

## USO, MANEJO, ACTUALIZACION Y PERSISTENCIA DEL CONTEXTO

Esta seccion es la autoridad operativa de continuidad para futuros chats, trabajo en equipo, Codex/VSC, implementaciones incrementales, auditorias parciales y migraciones futuras.

### Como usar estos documentos

- Leer siempre al inicio:
  - `backend/MICRO_RESUMEN_SISTEMA_MULTIAGENTES.md`
  - `backend/GUIA_CAPA_SEMANTICA_EMPRESA.md`
  - `backend/OPERACION_RUNTIME_MULTIAGENTE.md`
  - `backend/GUIA_DESARROLLO_AGENTES_EMPRESARIALES.md`
- Usar `MICRO_RESUMEN_SISTEMA_MULTIAGENTES.md` como fuente oficial de continuidad operativa:
  - estado runtime vigente
  - fases completadas
  - contratos activos
  - archivos y rutas oficiales relevantes
  - pruebas relevantes ya ejecutadas
  - decisiones y flujos runtime ya aprobados
- Usar `GUIA_CAPA_SEMANTICA_EMPRESA.md` como fuente oficial de gobierno semantico y arquitectura conceptual estable:
  - reglas estructurales
  - responsabilidades de GPT/planner/tools/agents
  - limites de autoridad
  - lineamientos estables de modelado semantico
- Usar `OPERACION_RUNTIME_MULTIAGENTE.md` como fuente oficial de operacion productiva del runtime:
  - health checks
  - alertas
  - troubleshooting
  - mantenimiento
  - checklist de produccion
  - endpoints y comandos operativos vigentes
- Usar `GUIA_DESARROLLO_AGENTES_EMPRESARIALES.md` como fuente oficial para construccion, extension, entrenamiento y validacion de dominios/agentes empresariales:
  - como opera el sistema multiagente actual
  - como crear nuevos dominios, agentes y procesos
  - como crear Capability Packs
  - como validar sin hardcodes
  - como documentar y actualizar contexto persistido
- Si estos documentos ya confirman un hecho, asumirlo como valido sin reabrir discovery salvo que exista un sintoma nuevo, concreto y verificable.

### Que asumir sin revalidar

- La arquitectura ya confirmada y los contratos ya persistidos.
- El runtime actual y sus fases ya aplicadas.
- El stack OpenAI vigente ya documentado en estos archivos.
- La autoridad del planner.
- La gobernanza de `ai_dictionary`.
- El `task envelope` vigente.
- El `tool registry` vigente.
- El gateway unificado vigente.
- El `agents runtime` vigente.
- Las fases ya completadas, sus limites y compatibilidades.
- Las rutas, archivos oficiales, flujos runtime y reglas ya confirmadas en estos documentos.

### Que NO hacer

- No hacer reauditorias masivas de arquitectura, runtime o contratos ya persistidos.
- No redescubrir archivos, rutas, entrypoints, planners, gateways, tools ni reglas ya confirmadas.
- No revalidar hechos ya persistidos salvo por sintoma nuevo y especifico.
- No persistir ruido tecnico temporal, hallazgos efimeros o debugging pasajero.
- No duplicar informacion ya documentada si basta con referenciarla o ampliarla en el lugar correcto.
- No reescribir modulos, contratos o secciones documentales que ya estan alineados con el estado vigente.

### Cuando actualizar cada documento

Actualizar `MICRO_RESUMEN_SISTEMA_MULTIAGENTES.md` cuando cambie o se confirme de forma relevante:

- continuidad operativa
- estado runtime
- fases
- contratos
- archivos o rutas oficiales de trabajo
- pruebas relevantes
- decisiones implementadas
- runtime flows
- limitaciones vigentes
- handoffs, approvals o tracing relevantes
- endpoints operativos nuevos o metadata operativa reutilizable

Actualizar `GUIA_CAPA_SEMANTICA_EMPRESA.md` solo cuando cambie o se confirme de forma conceptual y estable:

- gobierno semantico
- reglas estructurales
- responsabilidades entre GPT, planner, tools y agents
- limites de autoridad
- arquitectura conceptual de largo plazo

Actualizar `OPERACION_RUNTIME_MULTIAGENTE.md` cuando cambie o se confirme de forma estable:

- operacion productiva diaria
- health checks
- dashboards o endpoints operativos
- alertas y troubleshooting
- runbooks
- checklist de produccion
- degradacion, rollback y mantenimiento

Actualizar `GUIA_DESARROLLO_AGENTES_EMPRESARIALES.md` cuando cambie o se confirme de forma estable:

- forma oficial de crear nuevos dominios o agentes
- checklist de entrenamiento de tablas, relaciones, reglas y capacidades
- estructura oficial de Capability Packs
- criterios oficiales de validacion y pruebas focalizadas
- diagnostico persistido de dominios empresariales

Regla:

- si el cambio es operativo, incremental o de continuidad, va al `MICRO_RESUMEN`
- si el cambio redefine gobierno semantico o arquitectura conceptual estable, va a la `GUIA_CAPA_SEMANTICA`
- si el cambio es runbook, monitoreo, soporte o troubleshooting operativo, va a `OPERACION_RUNTIME_MULTIAGENTE.md`
- si el cambio redefine la forma oficial de construir, validar, empaquetar o migrar dominios/agentes empresariales, va a `GUIA_DESARROLLO_AGENTES_EMPRESARIALES.md`

### Que debe persistirse

- decisiones arquitectonicas confirmadas
- contratos vigentes
- fases implementadas o cerradas
- runtime flows oficiales
- reglas semanticas confirmadas
- pruebas relevantes para futuras continuidades
- limitaciones vigentes y sus alcances
- rutas oficiales y archivos de referencia
- metadata importante para tracing y continuidad
- handoffs, approvals y tracing relevantes
- reglas utiles para evitar retrabajo en futuras sesiones

### Que NO debe persistirse

- logs temporales
- errores efimeros sin valor de continuidad
- debugging temporal
- resultados triviales o facilmente reproducibles
- ruido operacional sin impacto arquitectonico, semantico o contractual

### Regla para futuros prompts

Los futuros prompts pueden ser minimos y referenciar esta seccion en lugar de repetir bloques largos. Plantilla oficial:

```md
Contexto persistido oficial:
- MICRO_RESUMEN_SISTEMA_MULTIAGENTES.md
- GUIA_CAPA_SEMANTICA_EMPRESA.md
- OPERACION_RUNTIME_MULTIAGENTE.md
- GUIA_DESARROLLO_AGENTES_EMPRESARIALES.md

Antes de modificar codigo:
1. Lee los cuatro documentos.
2. Aplica la seccion:
   "USO, MANEJO, ACTUALIZACION Y PERSISTENCIA DEL CONTEXTO".
3. Trabaja solo sobre la tarea solicitada.
```

### Regla de continuidad

Si durante una implementacion aparece una regla util para futuros chats, coordinacion de equipo, continuidad arquitectonica o evitar retrabajo, debe persistirse en el documento correcto:

- `MICRO_RESUMEN_SISTEMA_MULTIAGENTES.md` si la regla es operativa, incremental o runtime
- `GUIA_CAPA_SEMANTICA_EMPRESA.md` si la regla es estructural, semantica o conceptual estable
- `OPERACION_RUNTIME_MULTIAGENTE.md` si la regla es operativa de soporte, monitoreo o produccion
- `GUIA_DESARROLLO_AGENTES_EMPRESARIALES.md` si la regla define como construir, migrar, validar o empaquetar dominios/agentes empresariales

Persistir solo informacion reusable y con valor de continuidad futura.

### Diferencia oficial entre ambos documentos

`MICRO_RESUMEN_SISTEMA_MULTIAGENTES.md`:

- continuidad operativa
- estado runtime
- fases
- contratos
- archivos relevantes
- pruebas
- decisiones
- runtime flows
- continuidad de trabajo

`GUIA_CAPA_SEMANTICA_EMPRESA.md`:

- gobierno semantico
- reglas estructurales
- responsabilidades GPT/planner/tools/agents
- limites de autoridad
- arquitectura conceptual estable

`OPERACION_RUNTIME_MULTIAGENTE.md`:

- health checks
- monitoreo
- alertas
- troubleshooting
- soporte y mantenimiento
- checklist de produccion
- endpoints operativos y runbooks

`GUIA_DESARROLLO_AGENTES_EMPRESARIALES.md`:

- guia oficial de construccion de agentes empresariales
- entrenamiento de tablas, relaciones, reglas y capacidades
- estructura de Capability Packs
- validacion y pruebas anti-hardcode
- diagnostico persistido de dominios actuales

### Regla final de uso

- Antes de modificar codigo o documentacion, leer los cuatro documentos y aplicar esta seccion.
- Trabajar solo sobre la tarea solicitada.
- No convertir cada sesion en una nueva auditoria total.
- Cuando esta seccion cubra la instruccion, referenciarla en el prompt en vez de repetir bloques largos.

## Capa semantica empresarial vigente

- Antes de `QueryExecutionPlanner`, `InventorySemanticResolver` produce `BusinessQuerySemanticPlan`.
- El plan semantico es la capa oficial para ordenar:
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
- El plan semantico se publica en:
  - `semantic_context.business_query_semantic_plan`
  - `semantic_context.inventory_semantic_plan`
  - `semantic_context.resolved_semantic.business_query_semantic_plan`
- `QueryExecutionPlanner` sigue siendo la unica autoridad para:
  - seleccionar SQL seguro,
  - decidir estrategia,
  - decidir ejecucion,
  - bloquear faltantes o rutas inseguras.
- El planner ahora adjunta `metadata.semantic_trace` con:
  - consulta original
  - plan semantico
  - reglas aplicadas
  - fuentes consultadas
  - memorias consultadas
  - capability candidata
  - filtros finales
  - razones de bloqueo si aplica

## Matriz semantica de inventario activa

- `saldo + empleado/tecnico + cedula`
  - `intent: stock_balance`
  - `capability: inventory_stock_balance_by_mobile`
  - `entity.field: cedula`
  - `output.grain: saldo_por_codigo`
- `saldo + movil/cuadrilla + valor alfanumerico`
  - `intent: stock_balance`
  - `capability: inventory_stock_balance_by_mobile`
  - `entity.field: movil`
  - `scope.include_serialized: true` para inventario generico por movil/cuadrilla
- `kardex|movimientos|entradas y salidas + empleado/tecnico + cedula`
  - `intent: movement_history`
  - `capability: inventory_kardex_by_employee`
  - `entity.field: cedula`
- `kardex|movimientos + codigo`
  - `intent: movement_history`
  - `capability: inventory_kardex_consolidated`
  - `entity.field: codigo`
- `serial|seriales|equipos|cpe`
  - `intent: serial_holder_query` o trazabilidad serializada segun alcance
  - `familia: serializados`
  - `regla: conteo, no cantidad`

## Memoria persistida requerida

- Las reglas confirmadas de esta capa se siembran en `ai_dictionary.ia_dev_business_memory`.
- Prefijo oficial de memoria: `inventory.semantic.*`
- Reglas persistidas:
  - `material_claro`
  - `ferretero`
  - `material_generico`
  - `saldo_inventario`
  - `kardex`
  - `kardex_empleado`
  - `movil_cuadrilla`
  - `inventario_generico`
  - `enrichment_historico`
  - `serializados`
  - `gpt_semantiza_planner_ejecuta`
- Toda siembra deja rastro en `ia_dev_memory_audit_trail`.

## Hechos confirmados, no revalidar

### Arquitectura/runtime

- No reauditar arquitectura ni contratos.
- El runtime ya usa `agent_contract` fases 1-2.
- `SemanticOrchestratorService` y `BusinessResponseComposer` ya estan integrados.
- `ChatApplicationService` es el orquestador principal.
- `QueryExecutionPlanner` es autoridad de SQL.
- GPT/OpenAI solo semantiza intencion, filtros, rutas, cruces y respuesta empresarial.
- GPT/OpenAI no genera SQL libre ni decide `execute=True`.
- No tocar `fallback_policy`.
- No activar SAP, actas ni documentos.
- No usar `legacy` ni `runtime_only_fallback` como implementacion.

### Ruta operativa conocida

- Ruta base del proyecto:
  `c:\dev\agente_cinco\app-cinco\backend`
- Comando de validacion solo si es necesario:
  `python manage.py simulate_ia_dev_chat --mode service --raw --message "<consulta>" --session-id "<id>" --reset-memory`
- No volver a buscar el entrypoint si no hay error de ruta.
- No volver a redescubrir `response_envelope` si no cambio el runtime.

### Archivos conocidos

- `semantic_inventory_resolver.py`: resolucion semantica de inventario.
- `query_execution_planner.py`: construccion SQL segura.
- `response_assembler.py`: respuesta especifica del dominio `inventario_logistica`.
- `business_response_composer_service.py`: composicion empresarial transversal.
- `query_intent_resolver.py`: intencion y rescates semanticos.
- `intent_arbitration_service.py`: arbitraje entre dominios/intenciones.
- `result_satisfaction_validator.py`: validacion de satisfaccion del resultado.
- `MICRO_RESUMEN_LOGISTICA_EMPLEADOS_ACTUALIZADO.md`: fuente persistida de contexto operativo.

No leer estos archivos de nuevo salvo que la tarea indique modificar o depurar uno de ellos.

### Tablas confirmadas

Personal:

- `bd_c3nc4s1s.cinco_base_de_personal`
- Columnas: `cedula, nombre, apellido, movil, area, carpeta, cargo, tipo_labor, estado, codigo_sap`.

Materiales/Ferretero:

- `logistica_cinco.logistica_movimientos_entrega`
- `logistica_cinco.logistica_movimientos_devolucion`
- `logistica_cinco.logistica_movimientos_consumo`
- `logistica_cinco.logistica_movimientos_cobro`
- `logistica_cinco.base_codigos`
- `base_codigos` contiene: `codigo, descripcion, tipo, medida, codigo_ant, fecha_edit`.

Serializados/Equipos/CPE:

- `logistica_cinco.logistica_base_seriales`
- `logistica_cinco.logistica_seriales_asociados`
- `logistica_cinco.base_codigo_seriales`
- `base_codigo_seriales` contiene: `codigo, descripcion, familia, tipo, codigo_anterior, valorizacion, fecha_edit`.

### Reglas de identificacion confirmadas

- Si el identificador es numerico, priorizar `cedula`.
- Si el identificador es alfanumerico tipo `TIRAN224` o `TIRAN314`, priorizar `movil`.
- Si el usuario dice movil/cuadrilla, buscar primero en `cinco_base_de_personal.movil` y obtener todas las `cedulas`.
- Para logistica, usar `cedula IN (...)` cuando la movil tenga varios empleados.
- No usar `responsable`.
- No usar `asignacion`.
- No usar `movimiento` en `logistica_base_seriales`.
- No excluir empleados por `estado = 'ACTIVO'` en inventario historico, salvo que el usuario lo pida explicitamente.
- Mostrar columna `estado_empleado` cuando se enriquezca con personal.

### Reglas de salida confirmadas

Materiales/Ferretero siempre debe conservar codigo:

- `Codigo | Descripcion | Tipo | Cedula | Empleado | Movil | Estado Empleado | Entregas | Devoluciones | Consumos | Cobros | Saldo`

Formula materiales:

- `saldo = entregas - devoluciones - consumos - cobros`

Serializados/Equipos siempre debe conservar serial/codigo:

- `Serial | Codigo | Descripcion | Familia | Estado | Cedula | Empleado | Movil | Estado Empleado | En Movil | En Base | Cobros | Saldo`

Regla serializados:

- No usar `cantidad`.
- Todo es conteo.
- `En Movil = estado contiene MOVIL`.
- `En Base = estado contiene BASE o BODEGA`.
- `Cobros = estado contiene COBRO`.
- `Saldo = En Movil + En Base - Cobros`.

### Regla de inventario generico

Si el usuario consulta inventario o saldo sin especificar `materiales`, `ferretero`, `serializados`, `equipos` o `CPE`:

- Debe responder ambos bloques cuando aplique:
  1. `Materiales/Ferretero`
  2. `Serializados/Equipos/CPE`
- No asumir solo materiales.
- No asumir solo serializados.

### Que comandos ejecutar

Ejecutar comandos solo cuando:

1. Se modifique codigo.
2. Se necesite reproducir una falla especifica.
3. Se necesite confirmar `rowcount` o SQL de una consulta puntual.
4. Se valide una correccion ya aplicada.
5. Haya error de entorno, ruta o conexion.

No ejecutar comandos para:

- redescubrir arquitectura,
- listar archivos conocidos,
- buscar tablas ya confirmadas,
- revalidar reglas ya confirmadas,
- inspeccionar runtime ya conocido,
- volver a leer todo el proyecto sin una falla concreta.

### Formato obligatorio al final de cada intervencion

Siempre entregar:

1. Que se asumio desde el micro-resumen sin revalidar.
2. Que si se ejecuto y por que era necesario.
3. Que hechos nuevos quedaron confirmados.
4. Que archivos se modificaron, si aplica.
5. Que pruebas se corrieron, si aplica.
6. Micro resumen completo actualizado para futuros chats.

Regla:

- Si el cambio es solo semantico o de documentacion, no ejecutar pruebas pesadas. Usar pruebas focalizadas o ninguna, explicando por que.

Estado vigente confirmado

- Ya quedo validado en runtime que las consultas genericas de inventario/saldo sin familia explicita pueden devolver dos bloques:
  - materiales/ferretero
  - serializados/equipos
- La salida de materiales con alcance operativo ahora conserva detalle por `codigo + cedula + movil`.
- El enrichment de empleados ya incluye `estado_empleado`.
- Para enrichment historico de inventario no se excluyen empleados por `estado = 'ACTIVO'`.
- Los saldos de inventario nunca deben filtrar solo positivos ni excluir ceros o negativos.
- Las consultas explicitamente de `material claro` o `material de claro` filtran solo `tipo = 'material'`.
- Las consultas explicitamente de `ferretero` o `material ferretero` filtran solo `tipo = 'ferretero'`.
- Las consultas de `material` generico deben incluir `tipo IN ('material', 'ferretero')` dentro de la misma tabla operativa.
- Las consultas explicitamente seriales/equipos/CPE seguiran usando su ruta serializada dedicada.

Regla obligatoria persistida

Si el usuario consulta `inventario`, `saldo`, `inventario por cuadrilla`, `inventario de movil`, `inventario del tecnico` o equivalentes sin especificar `materiales`, `ferretero`, `seriales`, `equipos` o `CPE`, responder con ambos bloques cuando aplique:

1. Materiales/Ferretero
2. Serializados/Equipos/CPE

Bloque A obligatorio: materiales/ferretero

Regla semantica vigente para `tipo` en inventario operativo:

- `material claro` y `material de claro` significan solo registros catalogados con `tipo = 'material'`.
- `ferretero` y `material ferretero` significan solo registros catalogados con `tipo = 'ferretero'`.
- `material` sin apellido significa `material claro + ferretero` en la misma tabla.
- La columna `tipo` se mantiene.
- Cuando haya que distinguir frente a ferretero, el lenguaje empresarial debe decir `material claro` y no solo `material`.

Columnas de salida operativa:

- `codigo`
- `descripcion`
- `tipo`
- `cedula`
- `nombre`
- `empleado`
- `movil`
- `estado_empleado`
- `entregas`
- `devoluciones`
- `consumos`
- `cobros`
- `saldo`

Formula obligatoria:

- `saldo = entregas - devoluciones - consumos - cobros`
- No usar `HAVING saldo > 0`, `WHERE saldo > 0` ni `HAVING saldo <> 0` en consultas de saldo operativo por empleado, tecnico, movil, cuadrilla, bodega o codigo.
- En inventario, los saldos `0` y negativos son informacion operacional critica.

Bloque B obligatorio: serializados/equipos

Columnas de salida operativa:

- `serial`
- `codigo`
- `descripcion`
- `familia`
- `estado`
- `cedula`
- `nombre`
- `empleado`
- `movil`
- `estado_empleado`
- `en_movil`
- `en_base`
- `cobros`
- `saldo`

Reglas serializados:

- No usar `cantidad`.
- Todo es conteo.
- `en_movil = estado contiene MOVIL`
- `en_base = estado contiene BASE o BODEGA`
- `cobros = estado contiene COBRO`
- `saldo = en_movil + en_base - cobros`
- No usar `HAVING saldo > 0`, `WHERE saldo > 0` ni `HAVING saldo <> 0`.

Reglas de empleados persistidas

- Tabla oficial: `bd_c3nc4s1s.cinco_base_de_personal`
- Campos relevantes: `cedula, nombre, apellido, movil, area, carpeta, cargo, tipo_labor, estado, codigo_sap`
- No filtrar solo `ACTIVO` al enriquecer inventario historico.
- Mostrar empleados inactivos o fuera de operacion si aparecen por `cedula` o `movil`.
- Incluir `estado_empleado` en la salida.
- No usar `responsable`.
- No usar `asignacion`.
- No usar `movimiento` en `logistica_base_seriales`.

Mapa de rutas confirmado

1. Resolucion semantica

- Archivo: `backend/apps/ia_dev/domains/inventario_logistica/semantic_inventory_resolver.py`
- `template_id` principal para inventario operativo por tecnico/cuadrilla/movil: `inventory_material_stock_mobile`
- `template_id` para materiales criticos: `inventory_material_critical_by_employee`
- `template_id` serial dedicado por holder explicito: `inventory_serial_by_operational_holder`

2. Planeacion SQL

- Archivo: `backend/apps/ia_dev/application/semantic/query_execution_planner.py`
- Ruta materiales con detalle operativo:
  - `_build_inventory_material_stock_sql(...)`
  - `_inventory_should_group_balance_by_employee(...)`
  - `_build_inventory_mobile_employee_balance_sql(...)`
- Ruta serial suplementaria para inventario generico:
  - `_inventory_requires_dual_inventory_blocks(...)`
  - `_inventory_build_unspecified_family_supplemental_queries(...)`
  - `_build_inventory_serial_employee_balance_sql(...)`
- Ejecucion multi-bloque en runtime:
  - `execute_sql_assisted(...)`
  - `_execute_supplemental_inventory_queries(...)`
  - el SQL principal sigue siendo materiales
  - el bloque serializado viaja en `data.extra_tables`
  - metadata tecnica adicional en `data_sources.query_intelligence.supplemental_queries`

3. Respuesta de negocio

- Archivo: `backend/apps/ia_dev/domains/inventario_logistica/response_assembler.py`
- Archivo: `backend/apps/ia_dev/application/semantic/query_execution_planner.py`
- Cuando existe bloque suplementario serializado, el mensaje final debe hablar explicitamente de ambos bloques.

Flujo operativo ya aprobado

1. Detectar si la consulta es inventario/saldo con alcance operativo por `movil`, `cuadrilla`, `cedula` o agrupacion por cuadrilla/tecnico.
2. Si el usuario no explicita familia:
   - construir SQL de materiales como bloque principal
   - construir SQL serializado como bloque suplementario
   - responder con ambos
3. Si el usuario explicita `materiales` o `ferretero`:
   - responder solo materiales
4. Si el usuario explicita `seriales`, `equipos` o `CPE`:
   - responder solo serializados
5. En todos los cruces con personal:
   - incluir `estado_empleado`
   - no excluir `INACTIVO`

Patron SQL vigente: materiales con detalle de empleado

```sql
SELECT
  mov.codigo AS codigo,
  COALESCE(MAX(cat.descripcion), '') AS descripcion,
  COALESCE(MAX(cat.tipo), '') AS tipo,
  mov.cedula AS cedula,
  COALESCE(MAX(emp.nombre), '') AS nombre,
  TRIM(CONCAT(...)) AS empleado,
  COALESCE(MAX(emp.movil), '') AS movil,
  COALESCE(MAX(emp.estado_empleado), '') AS estado_empleado,
  SUM(mov.entregas) AS entregas,
  SUM(mov.devoluciones) AS devoluciones,
  SUM(mov.consumos) AS consumos,
  SUM(mov.cobros) AS cobros,
  SUM(mov.entregas - mov.devoluciones - mov.consumos - mov.cobros) AS saldo
FROM (... movimientos entrega/consumo/cobro/devolucion ...) AS mov
LEFT JOIN (
  SELECT
    p.cedula AS cedula,
    COALESCE(MAX(p.movil), '') AS movil,
    COALESCE(MAX(p.nombre), '') AS nombre,
    COALESCE(MAX(p.apellido), '') AS apellido,
    COALESCE(MAX(p.estado), '') AS estado_empleado
  FROM bd_c3nc4s1s.cinco_base_de_personal AS p
  GROUP BY p.cedula
) AS emp ON emp.cedula = mov.cedula
LEFT JOIN base_codigos AS cat ON cat.codigo = mov.codigo
GROUP BY mov.codigo, mov.cedula, COALESCE(emp.movil, '')
ORDER BY movil ASC, mov.cedula ASC, mov.codigo ASC
LIMIT 500
```

Patron SQL vigente: serializados con detalle de empleado

```sql
SELECT
  s.numero_serial AS serial,
  s.codigo AS codigo,
  COALESCE(MAX(cat.descripcion), '') AS descripcion,
  COALESCE(MAX(cat.familia), '') AS familia,
  COALESCE(MAX(s.estado), '') AS estado,
  s.cedula AS cedula,
  COALESCE(MAX(emp.nombre), '') AS nombre,
  TRIM(CONCAT(...)) AS empleado,
  COALESCE(MAX(emp.movil), '') AS movil,
  COALESCE(MAX(emp.estado_empleado), '') AS estado_empleado,
  SUM(CASE WHEN UPPER(COALESCE(s.estado, '')) LIKE '%MOVIL%' THEN 1 ELSE 0 END) AS en_movil,
  SUM(CASE WHEN UPPER(COALESCE(s.estado, '')) LIKE '%BASE%' OR UPPER(COALESCE(s.estado, '')) LIKE '%BODEGA%' THEN 1 ELSE 0 END) AS en_base,
  SUM(CASE WHEN UPPER(COALESCE(s.estado, '')) LIKE '%COBRO%' THEN 1 ELSE 0 END) AS cobros,
  SUM(
    CASE WHEN UPPER(COALESCE(s.estado, '')) LIKE '%MOVIL%' THEN 1 ELSE 0 END
    + CASE WHEN UPPER(COALESCE(s.estado, '')) LIKE '%BASE%' OR UPPER(COALESCE(s.estado, '')) LIKE '%BODEGA%' THEN 1 ELSE 0 END
    - CASE WHEN UPPER(COALESCE(s.estado, '')) LIKE '%COBRO%' THEN 1 ELSE 0 END
  ) AS saldo
FROM logistica_cinco.logistica_base_seriales AS s
LEFT JOIN (
  SELECT
    p.cedula AS cedula,
    COALESCE(MAX(p.movil), '') AS movil,
    COALESCE(MAX(p.nombre), '') AS nombre,
    COALESCE(MAX(p.apellido), '') AS apellido,
    COALESCE(MAX(p.estado), '') AS estado_empleado
  FROM bd_c3nc4s1s.cinco_base_de_personal AS p
  GROUP BY p.cedula
) AS emp ON emp.cedula = s.cedula
LEFT JOIN logistica_cinco.base_codigo_seriales AS cat ON cat.codigo = s.codigo
GROUP BY s.numero_serial, s.codigo, s.cedula, COALESCE(emp.movil, '')
ORDER BY movil ASC, cedula ASC, codigo ASC, serial ASC
LIMIT 500
```

Validacion de consultas objetivo

Q1. `inventario de la cuadrilla TIRAN224 con datos del empleado`

- Devuelve materiales/ferretero: si
- Devuelve serializados/equipos: si
- Motivo: consulta generica de inventario sin familia explicita y con alcance operativo por `movil`
- SQL materiales generado: exacto en `backend/tmp_stage2e_q1.json`
- SQL serializados generado: exacto en `backend/tmp_stage2e_q1.json`
- Patron de filtros:
  - materiales: bridge por `EXISTS (...) cinco_base_de_personal ... p.movil = 'TIRAN224'`
  - serializados: `WHERE EXISTS (...) p.movil = 'TIRAN224'`
- Columnas finales materiales:
  - `codigo, descripcion, tipo, cedula, nombre, empleado, movil, estado_empleado, entregas, devoluciones, consumos, cobros, saldo`
- Columnas finales serializados:
  - `serial, codigo, descripcion, familia, estado, cedula, nombre, empleado, movil, estado_empleado, en_movil, en_base, cobros, saldo`
- Rowcount materiales: `500`
- Rowcount serializados: `23`
- `estado_empleado` incluido: si
- Mensaje exacto al usuario:
  - `Se consolidaron 500 registros de materiales/ferretero y 23 registros de serializados/equipos para el alcance consultado`

Q2. `inventario por cuadrilla mostrando movil, cedula del empleado, nombre y saldo total`

- Devuelve materiales/ferretero: si
- Devuelve serializados/equipos: si
- Motivo: consulta generica de inventario por cuadrilla sin familia explicita
- SQL materiales generado: exacto en `backend/tmp_stage2e_q2.json`
- SQL serializados generado: exacto en `backend/tmp_stage2e_q2.json`
- Columnas finales materiales:
  - `codigo, descripcion, tipo, cedula, nombre, empleado, movil, estado_empleado, entregas, devoluciones, consumos, cobros, saldo`
- Columnas finales serializados:
  - `serial, codigo, descripcion, familia, estado, cedula, nombre, empleado, movil, estado_empleado, en_movil, en_base, cobros, saldo`
- Rowcount materiales: `500`
- Rowcount serializados: `500`
- `estado_empleado` incluido: si
- Mensaje exacto al usuario:
  - `Se consolidaron 500 registros de materiales/ferretero y 500 registros de serializados/equipos para el alcance consultado`

Q3. `saldo por tecnico en operacion_hfc mostrando cedula, nombre, movil y total de materiales`

- Devuelve materiales/ferretero: si
- Devuelve serializados/equipos: no
- Motivo: el usuario explicita `materiales`, por regla no se agrega bloque serializado
- SQL materiales generado: exacto en `backend/tmp_stage2e_q3.json`
- SQL serializados generado: no aplica
- Columnas finales materiales:
  - `codigo, descripcion, tipo, cedula, nombre, empleado, movil, estado_empleado, entregas, devoluciones, consumos, cobros, saldo`
- Rowcount materiales: `500`
- Rowcount serializados: `0`
- `estado_empleado` incluido: si
- Mensaje exacto al usuario:
  - `Se consolidaron 500 saldos de materiales por tecnico y codigo en operacion_hfc. El resultado conserva el detalle por cedula y codigo`

Q4. `materiales criticos por empleado en operacion_hfc cruzando saldo, cedula, movil y datos del empleado`

- Devuelve materiales/ferretero: si
- Devuelve serializados/equipos: no
- Motivo: la intencion es explicitamente `materiales criticos`, no inventario generico
- SQL materiales generado: exacto en `backend/tmp_stage2e_q4.json`
- SQL serializados generado: no aplica
- Columnas finales materiales:
  - `cedula, movil, nombre, apellido, estado_empleado, empleado, codigo, descripcion, tipo, consumo_ultimos_8_dias, promedio_dia, saldo_actual, umbral_3_dias, estado_critico`
- Rowcount materiales: `500`
- Rowcount serializados: `0`
- `estado_empleado` incluido: si
- Mensaje exacto al usuario:
  - `Se identificaron 500 materiales criticos por empleado en operacion_hfc. La criticidad se calculo con consumo de los ultimos 8 dias y cobertura estimada de 3 dias`

Artefactos de validacion vigentes

- `backend/tmp_stage2e_q1.json`
- `backend/tmp_stage2e_q2.json`
- `backend/tmp_stage2e_q3.json`
- `backend/tmp_stage2e_q4.json`

Pruebas que blindan este estado

- `apps.ia_dev.tests.test_inventario_semantic_resolver`
- `apps.ia_dev.tests.test_inventario_runtime_sql_alignment`
- `apps.ia_dev.tests.test_inventory_response_assembler`
- `apps.ia_dev.tests.test_query_intelligence_layer`

Comando de verificacion usado

```bash
backend/.venv/Scripts/python.exe backend/manage.py test apps.ia_dev.tests.test_inventario_semantic_resolver apps.ia_dev.tests.test_inventario_runtime_sql_alignment apps.ia_dev.tests.test_inventory_response_assembler
backend/.venv/Scripts/python.exe backend/manage.py simulate_ia_dev_chat --message "inventario de la cuadrilla TIRAN224 con datos del empleado" --session-id stage2e-q1 --reset-memory --raw > backend/tmp_stage2e_q1.json
backend/.venv/Scripts/python.exe backend/manage.py simulate_ia_dev_chat --message "inventario por cuadrilla mostrando movil, cedula del empleado, nombre y saldo total" --session-id stage2e-q2 --reset-memory --raw > backend/tmp_stage2e_q2.json
backend/.venv/Scripts/python.exe backend/manage.py simulate_ia_dev_chat --message "saldo por tecnico en operacion_hfc mostrando cedula, nombre, movil y total de materiales" --session-id stage2e-q3 --reset-memory --raw > backend/tmp_stage2e_q3.json
backend/.venv/Scripts/python.exe backend/manage.py simulate_ia_dev_chat --message "materiales criticos por empleado en operacion_hfc cruzando saldo, cedula, movil y datos del empleado" --session-id stage2e-q4 --reset-memory --raw > backend/tmp_stage2e_q4.json
```

Regla final para futuros chats

Si el usuario pide inventario o saldo con alcance de tecnico, empleado, movil o cuadrilla sin especificar familia, resolver directo con:

1. bloque materiales/ferretero
2. bloque serializados/equipos

Ambos con enrichment de `cinco_base_de_personal`, incluyendo `estado_empleado`, y sin excluir empleados inactivos.

## Estado validado 2026-05-11

- Consultas reproducidas:
  - `kardex del tecnico 5098747`
  - `kardex del empleado 5098747`
- Regla semantica nueva confirmada:
  - `kardex del tecnico {cedula}`
  - `kardex del empleado {cedula}`
  - `kardex de la cedula {cedula}`
  - se interpreta como `inventario_logistica` con filtro principal `cedula`
- Ruta correcta:
  - `template_id = inventory_kardex_by_employee`
  - `capability = inventory_kardex_by_employee`
  - SQL seguro sobre:
    - `logistica_movimientos_entrega`
    - `logistica_movimientos_devolucion`
    - `logistica_movimientos_consumo`
    - `logistica_movimientos_cobro`
  - enrichment historico con `bd_c3nc4s1s.cinco_base_de_personal`
  - catalogo con `base_codigos`
- Causa exacta del bloqueo anterior:
  - el resolver solo reconocia `kardex` cuando habia `codigo`
  - `kardex del tecnico/empleado 5098747` caia por descarte en `inventory_movement_detail`
  - esa ruta intentaba usar un SQL viejo sobre `a_promedios_consumo`
  - al no ser una ruta valida para este caso, terminaba bloqueada como `missing_dictionary_column`
- Regla operativa persistida:
  - Kardex por empleado/tecnico se resuelve por cedula usando movimientos de materiales/ferretero, conservando fecha, tipo de movimiento, codigo, descripcion, tipo, cantidad y efecto sobre saldo.
  - `entrega` suma como `entrada` y no debe invertirse como `salida`
  - `devolucion` resta como `salida`
  - `consumo` resta
  - `cobro` resta
  - el saldo acumulado se calcula en orden cronologico ascendente por `fecha, movimiento_id`, aunque la vista pueda ordenarse descendente
  - no recalcular saldo sobre solo el subconjunto visible cuando exista historico anterior
  - no filtrar solo saldos positivos
  - incluir positivos, cero y negativos cuando aplique
  - no excluir empleados inactivos en enrichment historico
- Columnas devueltas validadas en runtime:
  - `fecha, tipo_movimiento, codigo, descripcion, tipo, cedula, empleado, movil, estado_empleado, bodega, orden_trabajo, entrada, salida, cantidad, efecto, saldo_movimiento`
- Estado runtime validado:
  - `final_domain = inventario_logistica`
  - `planner_called = true`
  - `execute = true`
  - `legacy_used = false`
  - `fallback_reason = ''`
  - `rowcount = 500` en ambos casos reproducidos
- Limitacion explicitada:
  - no bloquear toda la consulta por serializados
  - si el usuario pide kardex generico por empleado, responder materiales/ferretero
  - aclarar que no hay trazabilidad cronologica confiable por cedula para serializados con las tablas hoy auditadas

## Estado validado 2026-05-11 kardex codigo + empleado

- Consulta reproducida: `kardex del codigo 1025507 para el empleado 5098747`
- Causa exacta corregida:
  - la combinacion `codigo + empleado` estaba cayendo en `inventory_kardex_consolidated`
  - esa ruta ignoraba el filtro de `cedula` y mostraba kardex global del codigo
  - en `_inventory_kardex_subqueries(...)` la tabla `logistica_movimientos_entrega` estaba mapeada como `salida`
  - la tabla `logistica_movimientos_devolucion` estaba mapeada como `entrada`, contradiciendo la formula vigente del saldo por empleado
  - por eso aparecian filas como `movimiento=entrega, entrada=0, salida=100` y el saldo acumulado quedaba invertido
- Regla documentada:
  - `Kardex materiales/ferretero: entrega suma como entrada; consumo, cobro y devolucion restan como salida. El saldo acumulado debe calcularse en orden cronologico y no debe invertir el signo de entregas.`

## Regla nueva confirmada

- Los saldos de inventario nunca deben filtrar solo positivos.
- En consultas por empleado, tecnico, movil, cuadrilla, bodega o codigo se deben devolver saldos positivos, cero y negativos.

## Estado validado 2026-05-11 dashboard kardex codigo + empleado

- Consulta reproducida: `kardex del codigo 1025507 para el empleado 1037659267`
- Estado backend validado:
  - `final_domain = inventario_logistica`
  - `capability = inventory_kardex_by_employee`
  - `response_flow = sql_assisted`
  - reply esperado: `Se consolido el kardex del codigo 1025507 para el empleado 1037659267`
  - salida estructurada: `table` transaccional con columnas de kardex operativo
- Regla de dashboard confirmada:
  - si la tabla contiene `fecha, tipo_movimiento, codigo, cedula, cantidad, efecto, saldo_movimiento`
  - tratar la vista como `Kardex Operativo`
  - no reconstruir chart sintetico desde la tabla en frontend
  - privilegiar tabla + insights sobre grafica automatica
- `HAVING saldo <> 0` tambien es incorrecto cuando excluye saldos en cero.
- Si la consulta es generica de inventario o saldo sin familia explicita, mantener ambos bloques cuando apliquen:
  - materiales/ferretero
  - serializados/equipos

## Estado validado 2026-05-10

- Consulta reproducida: `SALDO DEL EMPLEADO 5098747`
- Interpretacion confirmada:
  - `5098747` se interpreta como `cedula`
  - `final_domain = inventario_logistica`
  - `capability = inventory_stock_balance_by_mobile`
- Falla confirmada antes de la correccion:
  - SQL principal tenia `HAVING saldo <> 0 OR registros_cantidad_invalida > 0`
  - SQL suplementario serializado tenia `HAVING saldo <> 0`
  - por eso el runtime excluia saldos en cero
- Correccion aplicada:
  - se removio el filtro por saldo en materiales
  - se removio el filtro por saldo en serializados
  - el validador ahora rechaza planes SQL de inventario que vuelvan a filtrar `saldo <> 0`, `saldo > 0` o equivalentes

## Frontend architecture validada

- Vista conversacional final del usuario: `frontend/src/app/(private)/agente-ia/page.tsx`
- Modulo raiz: `frontend/src/modules/agente-ia/AgenteIAModule.tsx`
- El chat conversacional final ya no reutiliza la UI interna de IA DEV como workspace completo.
- La pantalla final del usuario ahora usa split-view persistente:
  1. izquierda = chat conversacional
  2. derecha = dashboard estructurado
- El transporte sigue reutilizando:
  - `frontend/src/modules/programacion/ia-dev/chat/hooks/useIADevChatTransport.ts`
  - `frontend/src/modules/programacion/ia-dev/chat/utils/mergeStreamingResponse.ts`
  - `frontend/src/modules/programacion/ia-dev/chat/utils/normalizeChatPayload.ts`
- La memoria local de conversaciones sigue en:
  - `frontend/src/modules/agente-ia/persistence/chatSessionStorage.ts`
- La persistencia nueva del split-view vive en:
  - `frontend/src/modules/agente-ia/persistence/splitViewStorage.ts`

### Componentes frontend nuevos confirmados

- `frontend/src/modules/agente-ia/components/SplitLayout.tsx`
- `frontend/src/modules/agente-ia/components/ChatPanel.tsx`
- `frontend/src/modules/agente-ia/components/MessageList.tsx`
- `frontend/src/modules/agente-ia/components/MessageInput.tsx`
- `frontend/src/modules/agente-ia/components/DashboardPanel.tsx`
- `frontend/src/modules/agente-ia/components/DashboardRenderer.tsx`
- `frontend/src/modules/agente-ia/components/KPIGrid.tsx`
- `frontend/src/modules/agente-ia/components/DataTable.tsx`
- `frontend/src/modules/agente-ia/components/ChartRenderer.tsx`
- `frontend/src/modules/agente-ia/components/InsightCards.tsx`
- `frontend/src/modules/agente-ia/components/BasicMarkdown.tsx`
- `frontend/src/modules/agente-ia/utils/buildDashboardSnapshot.ts`
- `frontend/src/modules/agente-ia/mock/mockAnalyticsResponse.ts`

## Dashboard flow confirmado

1. El usuario escribe en el panel izquierdo.
2. `AgenteIAModule` crea mensaje user + placeholder assistant `streaming`.
3. `useIADevChatTransport` mantiene el flujo websocket/http fallback ya vigente.
4. `onProgress` fusiona parciales en `message.response` usando `mergeStreamingResponse(...)`.
5. `onChunk` mantiene streaming textual solo en el chat izquierdo.
6. Al finalizar, `normalizeChatPayload(...)` produce payload estructurado para UI.
7. `buildDashboardSnapshot(...)` inspecciona los mensajes assistant del chat activo.
8. El dashboard toma el ultimo mensaje assistant con `hasStructuredContent = true`.
9. Si hay una respuesta nueva en streaming sin estructura todavia:
   - el panel derecho conserva el ultimo dashboard estructurado valido
   - y muestra estado `Actualizando dashboard`
10. Si no existe estructura:
   - el panel derecho muestra empty state elegante
   - con opcion de demo local

## Renderer registry confirmado

- El registry dinamico vive en `frontend/src/modules/agente-ia/components/DashboardRenderer.tsx`
- Patron vigente:

```ts
const widgetRegistry = {
  kpi: KPIWidget,
  chart: ChartWidget,
  table: TableWidget,
  insights: InsightWidget,
};
```

- El builder de widgets vive en `frontend/src/modules/agente-ia/utils/buildDashboardSnapshot.ts`
- El core no depende de hardcode por dominio; depende del payload normalizado.

## UI contracts confirmados

### Contrato frontend esperado desde backend

El frontend final ya consume este sobre:

```json
{
  "reply": "texto conversacional",
  "orchestrator": {
    "intent": "analytics_query",
    "domain": "inventario_logistica",
    "selected_agent": "inventory_analyst"
  },
  "data": {
    "kpis": {},
    "insights": [],
    "table": {
      "columns": [],
      "rows": [],
      "rowcount": 0
    },
    "extra_tables": [],
    "chart": {},
    "charts": [],
    "series": [],
    "labels": [],
    "meta": {}
  }
}
```

### Contratos UI normalizados confirmados

- `normalizeChatPayload(...)` ya soporta:
  - `data.kpis`
  - `data.insights`
  - `data.table`
  - `data.extra_tables`
  - `data.chart`
  - `data.charts`
  - `data.labels`
  - `data.series`
- `NormalizedAssistantPayload` ahora incluye:
  - `table`
  - `extraTables`
  - `charts`
  - `kpis`
  - `insights`
  - `summary`
  - `hasStructuredContent`

## Split-view behavior confirmado

### Desktop

- Layout persistente 2 paneles.
- Ratio inicial persistido: `42/58` aprox.
- Rango permitido del resize:
  - minimo chat: `34%`
  - maximo chat: `62%`
- Handle de resize visible solo en `lg+`.

### Tablet

- `SplitLayout.tsx` cambia a tabs:
  1. `Chat`
  2. `Dashboard`
- El tab activo se persiste en localStorage.
- Al enviar una consulta nueva, tablet cambia automaticamente a `Dashboard`.

### Mobile

- Stack vertical:
  1. bloque chat
  2. bloque dashboard

## Response rendering rules confirmadas

- El chat izquierdo muestra solo conversacion humana.
- El bubble assistant en `MessageList.tsx` renderiza:
  - `message.normalized.summary` si existe estructura
  - `message.content` si es texto puro o streaming
- El chat izquierdo no vuelve a renderizar:
  - tablas
  - charts
  - KPIs
  - JSON crudo
- El panel derecho no duplica el texto conversacional completo.
- El panel derecho usa:
  - badges de `intent`
  - badges de `domain`
  - badge de `selected_agent`
  - summary corta como contexto

## Widgets soportados confirmados

1. KPI cards
2. charts multiples
3. tabla principal
4. `extra_tables` como tabs
5. insight cards
6. badges contextuales intent/domain/agent
7. empty state elegante
8. loading state persistente mientras llega nueva estructura

## Regla UI persistida para tabs operativos

- El frontend debe nombrar tabs operativos por tipo empresarial inferido, no por posicion tecnica `Principal` o `Adicional`.
- Si una tabla contiene `codigo, descripcion, tipo, entregas, devoluciones, consumos, cobros, saldo`, el tab debe mostrarse como `Materiales / Ferretero`.
- Si una tabla contiene `serial, codigo, descripcion, familia, estado, en_movil, en_base, cobros, saldo`, el tab debe mostrarse como `Serializados / Equipos`.
- Si no se puede inferir el tipo empresarial:
  - usar `Tabla principal`
  - usar `Tabla adicional {n}`
- Si en el futuro `data.extra_tables` envia `name`, `title` o `key`, el frontend debe preferir ese nombre para la tab adicional.
- En esta fase no separar `Materiales` y `Ferretero` en tabs distintas; ambos siguen compartiendo la misma tabla y se distinguen por la columna `tipo`.

## Historial y UX confirmados

- El historial de chats persiste en localStorage.
- El listado de conversaciones ya no consume una columna fija permanente.
- El historial abre como drawer/overlay desde el panel izquierdo mediante boton `Chats`.
- El input inferior sigue fijo/sticky.
- Se mantiene:
  - auto scroll
  - boton `scroll to bottom`
  - prompt history con flechas arriba/abajo
  - undo/redo del input

## Demo/mock operativa confirmada

- Existe demo local funcional en:
  - `frontend/src/modules/agente-ia/mock/mockAnalyticsResponse.ts`
- Se puede cargar desde:
  - empty state del chat
  - empty state del dashboard
- La demo inyecta una respuesta analitica con:
  - KPIs
  - charts
  - tabla principal
  - `extra_tables`
  - insights

## Estado operacional validado

- `frontend/src/modules/agente-ia/AgenteIAModule.tsx` compila y enlaza con el transporte real existente.
- `frontend/src/services/ia-dev.service.ts` ya reconoce `data.extra_tables`.
- El renderer derecho queda desacoplado del bubble assistant.
- El split-view del usuario final queda separado del workspace interno de IA DEV.
- Validaciones corridas sobre frontend:
  - `npm run typecheck`
  - `npm run lint`
- Estado vigente:
  - compilacion TypeScript: OK
  - lint: OK

## Incidente persistido: certificados de alturas e impacto cruzado en empleados

No reabrir esta investigacion desde cero salvo que aparezca un sintoma nuevo distinto.

Hallazgo confirmado:

- La falla reportada en `certificados de altura proximos a vencer` no fue causada por el agente hibrido `inventario_logistica`.
- La causa raiz fue un `NameError` en `SemanticBusinessResolver` por uso de `AIDictionaryRemediationService` sin import activo.
- Ese error hacia que `query_intelligence` entrara en `except`, dejara `execution_plan` vacio y degradara la consulta a:
  - `general.answer.v1`
  - `legacy_fallback`
  - razon visible: `capability_mode_domain_not_enabled_yet`

Archivo causal corregido:

- `backend/apps/ia_dev/application/semantic/semantic_business_resolver.py`

Impacto confirmado antes del fix:

- consultas de `empleados`
- consultas de `rrhh`
- rescates que arrancaban clasificados como `empleados` aunque terminaran en otro dominio
- caso confirmado:
  - `certificados de altura proximos a vencer`
  - `personal activo hoy`
  - `stock por movil TIRAN224`

Estado confirmado despues del fix:

- `certificados de altura proximos a vencer` vuelve a resolver por `sql_assisted`
- `personal activo hoy` vuelve a resolver por `sql_assisted`
- `stock por movil TIRAN224` vuelve a resolver por `inventario_logistica` con `sql_assisted`

Regla operativa persistida:

- Si vuelve a aparecer el mensaje generico `Consulta recibida. Puedo ayudarte con empleados...` en una consulta moderna de `empleados` o en un rescate hacia `inventario_logistica`, primero validar:
  - si `query_intelligence` trae `error`
  - si `execution_plan` llega vacio
  - si la ruta cae en `legacy_fallback`
- Antes de culpar al hibrido YAML-DB de inventario, revisar primero errores internos del pipeline moderno de `empleados`.

Regla para futuros chats:

- No repetir la auditoria completa del agente hibrido `inventario_logistica` para este incidente.
- Reusar como hecho confirmado que la causa raiz historica fue el import faltante de `AIDictionaryRemediationService`.

## Sesion 2026-05-11: validacion focalizada empleados, ausentismo e inventario_logistica

Alcance ejecutado en esta sesion:

- validacion focalizada de `query_intelligence`, planner y respuesta final para `empleados`
- validacion focalizada de respuesta de negocio en `ausentismo`
- validacion focalizada de integridad semantica/YAML en `inventario_logistica`
- sin reauditar arquitectura ni tocar `fallback_policy`

Hechos nuevos confirmados:

- El caso `certificados de altura proximos a vencer` quedo blindado con prueba de servicio sobre `ChatApplicationService._resolve_query_intelligence`.
- La regresion historica no se reabrio: la consulta sigue resolviendo en `empleados` con `execution_plan.strategy = sql_assisted` y `metric_used = certificado_alturas_vigencia`.
- Se agrego cobertura para que un fallo interno de `query_intelligence` en `empleados` quede expuesto en:
  - `run_context.metadata.query_intelligence.error`
  - evento de observabilidad `query_intelligence_error`
- Esto evita que una excepcion vuelva a degradarse silenciosamente sin rastro diagnostico util.

Hallazgo nuevo corregido:

- `inventario_logistica` tenia una inconsistencia real en el YAML hibrido:
  - existia la relacion `devolucion_movil_to_personal`
  - pero `logistica_movimientos_devolucion` no declaraba la columna `movil`
- El problema no estaba en runtime SQL del caso de certificados; era una falla de integridad de metadata versionada.
- Se corrigio agregando la columna `movil` como `mobile_unit` con `missing_metadata_allowed: true` en `logistica_movimientos_devolucion`.

Impacto validado por agente:

- `empleados`
  - sin falla nueva confirmada
  - `query_intelligence` mantiene ruta moderna para certificados de alturas
  - el error path queda trazable y testeado
- `ausentismo`
  - sin falla nueva confirmada en este barrido
  - las respuestas de resumen siguen diferenciando foco `all` vs `unjustified`
- `inventario_logistica`
  - se descarta reabrir la causa de certificados contra el hibrido
  - se confirma y corrige una falla distinta: integridad YAML de devoluciones por movil

Pruebas focalizadas corridas en esta sesion:

- `python manage.py test apps.ia_dev.tests.test_chat_runtime_metadata apps.ia_dev.tests.test_inventario_yaml_agent`
- `python manage.py test apps.ia_dev.tests.test_query_intelligence_layer apps.ia_dev.tests.test_empleados_handler apps.ia_dev.tests.test_ausentismo_handler_summary_focus apps.ia_dev.tests.test_inventario_yaml_agent apps.ia_dev.tests.test_simulate_ia_dev_chat_command apps.ia_dev.tests.test_chat_runtime_metadata`

Resultado:

- 22 tests: OK
- 114 tests: OK

Regla operativa persistida:

- Si reaparece un sintoma parecido en `empleados`, no basta con mirar el fallback visible.
- Confirmar siempre si existe:
  - error en `query_intelligence`
  - metadata de error en `run_context`
  - evento `query_intelligence_error` en observabilidad
- Si el rojo viene de `inventario_logistica`, distinguir entre:
  - fallo de runtime/planner
  - inconsistencia de metadata/YAML como relaciones con columnas no declaradas

## Estado arquitectonico validado 2026-05-16

No volver a reauditar el stack base de `backend/apps/ia_dev` salvo que cambien estos archivos:

- `backend/apps/ia_dev/views/chat_view.py`
- `backend/apps/ia_dev/application/orchestration/chat_application_service.py`
- `backend/apps/ia_dev/application/runtime/runtime_capability_adapter.py`
- `backend/apps/ia_dev/application/semantic/query_execution_planner.py`
- `backend/apps/ia_dev/services/dictionary_tool_service.py`
- `backend/apps/ia_dev/services/observability_service.py`
- `backend/apps/ia_dev/application/memory/*`
- `backend/apps/ia_dev/application/workflow/*`

### Mapa oficial actual

1. Entrada frontend

- Vista final: `frontend/src/app/(private)/agente-ia/page.tsx`
- Modulo raiz: `frontend/src/modules/agente-ia/AgenteIAModule.tsx`
- Transporte: `frontend/src/modules/programacion/ia-dev/chat/hooks/useIADevChatTransport.ts`
- Servicio HTTP final: `frontend/src/services/ia-dev.service.ts`
- Endpoint principal: `POST /ia-dev/chat/`

2. Runtime backend

- Entry point HTTP: `backend/apps/ia_dev/views/chat_view.py`
- Orquestador principal: `ChatApplicationService.run(...)`
- Secuencia oficial:
  1. bootstrap classification
  2. carga de memoria
  3. query intelligence
  4. semantic normalization / canonical resolution / semantic orchestrator
  5. planner SQL o capability handler
  6. validacion de satisfaccion
  7. persistencia de task state, memoria y observabilidad
  8. ensamblado del `chat_response` para frontend

3. Donde se ejecuta trabajo real

- SQL asistido y consultas de inventario: `QueryExecutionPlanner.execute_sql_assisted(...)`
- Ejecucion por capability no-SQL planner: `RuntimeCapabilityAdapter.execute(...)`
- Handlers productivos actuales:
  - `backend/apps/ia_dev/domains/empleados/handler.py`
  - `backend/apps/ia_dev/domains/ausentismo/handler.py`
  - `backend/apps/ia_dev/domains/transport/handler.py`
- Inventario/logistica hoy ejecuta principalmente por planner deterministico y SQL seguro, no por tool call de OpenAI.

4. Base de datos y fuentes

- Multi DB Django:
  - `default`: principal MySQL
  - `azul`: personal/common
  - `logistica_cinco`: logistica
- Router:
  - `common -> azul`
  - `empleados -> azul`
  - `authentication/security/operaciones -> default`
- `ai_dictionary` sigue siendo la fuente estructural oficial.

### OpenAI API realmente usada hoy

- El proyecto ya usa `Responses API` en productivo.
- No hay uso productivo confirmado de `Chat Completions`.
- No hay uso productivo confirmado de `Assistants API`.
- No hay integracion actual con `Agents SDK`.

Servicios confirmados con `client.responses.create(...)`:

- `query_intent_resolver.py`
- `semantic_orchestrator_service.py`
- `semantic_normalization_service.py`
- `satisfaction_review_gate.py`
- `cause_diagnostics_service.py`
- `attendance_period_resolver_service.py`
- `intent_service.py`
- `intent_arbitration_service.py`
- `orchestrator_legacy_runtime.py`

Regla confirmada:

- OpenAI hoy actua como clasificador, normalizador, arbitro semantico, reviewer y redactor.
- OpenAI hoy NO gobierna un loop unico de tools.
- OpenAI hoy NO recibe un registry operativo de function tools del negocio.

### Tools / function calls actuales

- No se encontro uso productivo de `tools=` ni `tool_choice` en llamadas a `Responses API`.
- No se encontro loop de `function_call` / `function_call_output` controlado por el modelo como superficie principal del runtime.
- Los `used_tools` actuales son etiquetas internas de ejecucion, no OpenAI function tools nativas.

Herramientas reales actuales:

- planner SQL seguro
- handlers de dominio
- servicios Python internos (`tool_ausentismo_service`, `tool_transport_service`, consultas de empleados, dictionary, memoria, tickets)
- propuestas de memoria / conocimiento

Conclusion oficial:

- El sistema ya es parcialmente agentic en arquitectura interna, pero todavia no es un runtime de tareas unificado model-driven con `Responses API tools` + `Agents SDK`.

### Semantic layer y memoria confirmadas

- Snapshot y contexto por dominio salen de `DictionaryToolService`.
- Tablas estructurales oficiales:
  - `ai_dictionary.dd_dominios`
  - `ai_dictionary.dd_tablas`
  - `ai_dictionary.dd_campos`
  - `ai_dictionary.dd_reglas`
  - `ai_dictionary.dd_relaciones`
  - `ai_dictionary.dd_sinonimos`
  - `ai_dictionary.ia_dev_capacidades_columna`
- Memoria persistente confirmada:
  - `ia_dev_business_memory`
  - `ia_dev_learned_memory_proposals`
  - `ia_dev_learned_memory_approvals`
  - `ia_dev_memory_audit_trail`
  - `ia_dev_workflow_state`

### Validadores y guardrails confirmados

- `PolicyGuard`
- `ResultSatisfactionValidator`
- `SatisfactionReviewGate`
- `agent_contract` + `fallback_policy`
- `ApprovalPolicyService` para memoria
- `TaskStateService` para estado persistido de ejecucion

Regla confirmada:

- Antes de ejecutar, el runtime puede bloquear por contrato, seguridad SQL, contexto faltante, arbitraje de intencion o satisfaccion insuficiente.
- `QueryExecutionPlanner` sigue siendo autoridad unica para SQL seguro cuando la ruta es `sql_assisted`.

### Trazabilidad y evidencia confirmadas

- `RunContext` genera `run_id` y `trace_id`.
- `ObservabilityService.record_event(...)` persiste eventos.
- `TaskStateService.save(...)` guarda:
  - pregunta original
  - dominio detectado
  - plan
  - `executed_query`
  - validacion
  - fallback usado
  - recomendaciones
- `ReasoningLedgerService` arma `working_updates`.
- `trace` viaja en el response contract.
- `semantic_trace` queda en metadata del planner.
- auditoria de memoria vive en `ia_dev_memory_audit_trail`.

### Hallazgos criticos ya resueltos para futuros chats

No volver a cuestionar estos hechos salvo cambio de codigo:

- El endpoint oficial sigue siendo `/ia-dev/chat/`.
- `ChatApplicationService` es la autoridad de orquestacion actual.
- El runtime ya usa `Responses API`, pero de forma distribuida y sin function tools nativas.
- El proyecto no esta sobre `Assistants API`.
- El proyecto no usa `Agents SDK` hoy.
- La ejecucion real ocurre en planner SQL y handlers Python, no en el modelo.
- Existe semantic layer gobernada con `ai_dictionary`.
- Existen validadores previos y posteriores a la ejecucion.
- Existe task state persistido, auditoria de memoria y observabilidad.
- El frontend puede intentar websocket, pero el path canonico comprobado en repo sigue siendo HTTP `/ia-dev/chat/`; el fallback sintetiza progreso local cuando no hay stream backend.

### Brechas criticas ya confirmadas

1. La consulta del usuario aun entra por superficie de `chat response`, no por un contrato explicito de `task / run / action`.
2. Las tools de negocio no estan expuestas al modelo como function tools o MCP tools unificadas.
3. No hay `Agents SDK` para handoffs, specialist-as-tool, tracing nativo ni guardrails del SDK.
4. Las llamadas OpenAI estan dispersas en varios servicios y no pasan por un solo gateway/model policy runtime.
5. No se esta usando `previous_response_id`, `store`, `background` ni un estado nativo de Responses para corridas largas.
6. El frontend consume `reply + dashboard`, pero no una maquina de estados de tarea con `planned/executing/awaiting_approval/completed/failed`.

### Modulos que SI se conservan en una migracion

- `ChatApplicationService` como punto de integracion temporal
- `QueryExecutionPlanner`
- `DictionaryToolService`
- `ResultSatisfactionValidator`
- `SatisfactionReviewGate`
- `PolicyGuard`
- `ChatMemoryRuntimeService`
- `MemoryGovernanceService`
- `TaskStateService`
- `ObservabilityService`
- `ResponseAssembler` / `BusinessResponseComposerService`
- handlers de dominio y servicios SQL ya auditados

### Modulos que deben refactorizarse para target task-first

- `chat_view.py` para aceptar y devolver `task envelope`
- `ChatApplicationService` para separar `chat UX` de `task runtime`
- llamadas OpenAI dispersas para centralizarlas en un gateway unico
- surface frontend `AgenteIAModule` para mostrar estado de tarea y evidencia, no solo reply
- flujo de tools para convertir servicios/handlers en registry declarativo de herramientas

### Target oficial de migracion

Objetivo aprobado para futuros chats:

- cada consulta del usuario debe compilarse a una tarea ejecutable
- el texto conversacional debe ser la capa de explicacion, no el producto principal
- `Responses API` debe quedar como superficie unica de modelos
- `Agents SDK` debe gobernar orquestacion, tools, handoffs, approvals y tracing
- `ai_dictionary` + memoria de negocio deben seguir como autoridad estructural y contextual

## Instruccion persistida para futuros chats

Cuando la solicitud sea arquitectonica sobre IA Dev:

1. asumir este estado como confirmado
2. no reejecutar discovery masivo del repo
3. revisar solo archivos si la tarea pide cambio puntual
4. no volver a validar si usa `Responses API`: ya esta confirmado que si
5. no volver a validar si usa `Agents SDK`: ya esta confirmado que no
6. enfocar el trabajo en migracion task-first, registry de tools, approvals, evidencia y traces

## Sesion 2026-05-16: Fase 1 TaskEnvelope + TaskRun

Que se asumio sin revalidar:

- `/ia-dev/chat/` sigue siendo el endpoint canonico.
- `ChatApplicationService` sigue siendo el orquestador principal.
- `QueryExecutionPlanner` no se toca y sigue siendo autoridad unica de SQL seguro.
- `ai_dictionary` no cambia en esta fase.
- el frontend actual sigue consumiendo `reply + data` y no debe romperse.

Que se modifico:

- `backend/apps/ia_dev/application/contracts/chat_contracts.py`
  - el contrato HTTP ahora siempre incluye `task`.
  - `task.current_run` expone:
    - `run_id`
    - `status`
    - `domain`
    - `intent`
    - `plan`
    - `required_tools`
    - `validation`
    - `evidence`
    - `final_state`
    - `reply`
- `backend/apps/ia_dev/application/orchestration/chat_application_service.py`
  - `_attach_runtime_metadata(...)` ahora construye el `TaskEnvelope` desde:
    - `run_context`
    - `task_state`
    - `query_intelligence`
    - metadata runtime existente
  - no se cambio `QueryExecutionPlanner`.
- `backend/apps/ia_dev/application/workflow/task_state_service.py`
  - persiste `task_id` como alias estable de `workflow_key`.
  - persiste tambien `status` plano y rastro de `task_id/run_id` en `history`.
- `backend/apps/ia_dev/views/chat_view.py`
  - asegura compatibilidad final sincronizando `task.current_run.reply` con el `reply` definitivo ya compuesto.
- `frontend/src/services/ia-dev.service.ts`
  - tipado del nuevo contrato `task`.
- `frontend/src/modules/agente-ia/AgenteIAModule.tsx`
  - mantiene compatibilidad usando `result.reply` y, si viniera vacio, cae a `result.task.current_run.reply`.

Que quedo validado:

- el backend sigue devolviendo `reply` top-level para la UI actual.
- cada respuesta moderna ahora sale con `task_id` y `current_run`.
- `required_tools` informa `query_execution_planner.sql_assisted` cuando la corrida fue planner SQL.
- `validation`, `evidence` y `final_state` se rellenan desde la traza ya existente, sin crear un runtime nuevo.
- no hubo migracion a `Agents SDK`.
- no se tocaron `ai_dictionary` ni `QueryExecutionPlanner`.

Que comandos/pruebas se ejecutaron:

- `python manage.py test apps.ia_dev.tests.test_chat_response_contracts apps.ia_dev.tests.test_task_state_service apps.ia_dev.tests.test_chat_runtime_metadata`
- `npm run typecheck`

Resultado:

- `22 tests`: OK
- `TypeScript typecheck`: OK

Estado vigente para futuros chats:

- Fase 1 de `task-first` ya existe sobre `/ia-dev/chat/` sin romper el contrato anterior.
- El producto visible para frontend sigue siendo `reply`, pero ya viaja un contrato paralelo `task`.
- El `task_id` vigente en esta fase se alinea con `task_state.workflow_key` (`task_runtime:<run_id>`).
- `task.current_run.reply` debe considerarse espejo del `reply` final, no una fuente narrativa distinta.
- La siguiente fase puede profundizar en estados/approvals/evidencia sin rehacer esta base.

## Sesion 2026-05-16: Fase 2 Tool Registry

Que se asumio sin revalidar:

- `ai_dictionary` sigue siendo autoridad estructural y no se modifica.
- `BusinessQuerySemanticPlan` sigue siendo la salida oficial de la capa semantica.
- `QueryExecutionPlanner` sigue siendo autoridad unica de SQL seguro.
- `fallback_policy` no se toca.
- el sobre `task` de Fase 1 y el `reply` top-level deben seguir siendo compatibles.

Que se modifico:

- `backend/apps/ia_dev/application/contracts/tool_contracts.py`
  - nuevos contratos tipados para:
    - `ToolDefinition`
    - `ToolExecutionPolicy`
    - `ToolApprovalPolicy`
    - `ToolExecutionTrace`
- `backend/apps/ia_dev/application/runtime/tool_registry_service.py`
  - nuevo registry declarativo unico.
  - registra:
    - tools de handlers por `capability_id`
    - tool planner `query_execution_planner.sql_assisted`
  - expone:
    - `tool_id`
    - `tool_definition`
    - `input_schema`
    - `output_schema`
    - `execution_policy`
    - `approval_policy`
    - `audit_metadata`
  - centraliza el mapeo `capability -> tool`.
- `backend/apps/ia_dev/application/runtime/runtime_capability_adapter.py`
  - deja de resolver solo por prefijo de handler y ahora adjunta metadata declarativa de tool.
  - cada capability plan ahora publica `tool_id` y `tool_definition`.
  - la ejecucion de handler devuelve tambien:
    - `tool_id`
    - `tool_definition`
    - `tool_trace`
- `backend/apps/ia_dev/application/orchestration/chat_application_service.py`
  - construye `tool_execution` y `tool_execution_trace` para la corrida final.
  - persiste esa traza dentro de `task_state`.
  - publica la metadata de tools en:
    - `task.current_run.tool_execution`
    - `data_sources.runtime.tool_execution`
- `backend/apps/ia_dev/application/contracts/chat_contracts.py`
  - el contrato de `task.current_run` ahora tolera `tool_execution` sin romper compatibilidad.
- `backend/apps/ia_dev/application/workflow/task_state_service.py`
  - persiste:
    - `tool_execution`
    - `tool_execution_trace`
  - agrega a `history`:
    - `selected_tool_id`
    - `tool_trace_count`

Que quedo validado:

- reasoning, planning y execution quedaron mas separados:
  - razonamiento/semantica siguen en sus capas actuales
  - el planner sigue decidiendo SQL
  - la ejecucion de tools ahora tiene registry declarativo propio
- los handlers productivos actuales quedaron registrados como tools declarativas.
- `query_execution_planner.sql_assisted` ya existe como tool declarativa de planner.
- la corrida final ahora deja traza persistida de tool con:
  - definicion
  - policy de ejecucion
  - policy de aprobacion
  - metadata de auditoria
  - input/output resumido
- no se migro todavia a `Agents SDK`.
- no se rompio `reply` compatible.

Que comandos/pruebas se ejecutaron:

- `python manage.py test apps.ia_dev.tests.test_tool_registry_service apps.ia_dev.tests.test_task_state_service apps.ia_dev.tests.test_chat_response_contracts apps.ia_dev.tests.test_chat_runtime_metadata`

Resultado:

- `27 tests`: OK

Estado vigente para futuros chats:

- Fase 1 `Task Envelope` sigue vigente y estable.
- Fase 2 `Tool Registry` ya existe en backend con registry declarativo y traza persistida.
- la lista `required_tools` sigue siendo compatible y el detalle rico vive en `tool_execution`.
- el planner SQL sigue fuera del control del modelo y solo se expone como tool declarativa de runtime interno.
- la siguiente fase debe atacar la unificacion de llamadas OpenAI en un gateway comun, sin rehacer el registry.

## Hoja de ruta vigente

- Fase 1 -> Task Envelope ✅ (OK - 2025-05-16 03:27)
- Fase 2 -> Tool Registry ✅
- Fase 3 -> Unified OpenAI Gateway
- Fase 4 -> Responses API tools
- Fase 5 -> Agents SDK
- Fase 6 -> Handoffs + approvals
- Fase 7 -> Background runs

## Sesion 2026-05-16: V1 flujo gobernado de revision de brechas semanticas

Que se asumio sin revalidar:

- P1-P7 siguen vigentes segun este micro-resumen.
- `Continuous Runtime Learning V1` ya existe y registra en `ia_dictionary.registro_brechas_semanticas`.
- `semantic_gap_registry_service.py` sigue registrando brechas sin autocorregir.
- `RuntimeGovernanceService` ya exponia `continuous_runtime_learning`.
- no se reauditan `QueryExecutionPlanner`, `ToolRegistryService`, `SemanticCapabilityRegistry`, `fallback_policy`, `OpenAI Gateway`, `Agents Runtime`, approvals base, background ni frontend.

Que quedo implementado:

- nueva capa operativa de revision:
  - `backend/apps/ia_dev/application/runtime/semantic_gap_review_service.py`
- estados de revision V1 en espanol:
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
- las propuestas gobernadas ahora quedan trazadas en metadata de la brecha con:
  - `tipo_propuesta`
  - `descripcion`
  - `destino_sugerido`
  - `valor_sugerido`
  - `evidencia`
  - `riesgo`
  - `requiere_aprobacion`
  - `estado_aprobacion`
  - `aplicado_en`
  - `validado_por_eval`
- integracion con approvals:
  - propuestas sensibles de metadata/capability/tool/agente generan `approval_runtime`
  - la aplicacion gobernada queda bloqueada si no existe approval aprobada
- integracion con evals P5:
  - cada brecha puede vincular `evaluaciones_vinculadas`
  - cada brecha puede vincular `casos_reales_reproducibles`
  - la resolucion puede dejar `prueba_validacion`
- deduplicacion:
  - el registro evita duplicar brechas equivalentes abiertas aunque cambie `run_id`

Superficie operativa nueva:

- endpoint interno:
  - `GET/POST /ia-dev/runtime/semantic-gaps/`
- operaciones minimas:
  - listar brechas pendientes
  - agrupar por categoria
  - ver brechas frecuentes
  - marcar en revision
  - marcar descartada
  - marcar resuelta
  - crear propuesta
  - aprobar propuesta
  - aplicar propuesta gobernada
  - vincular eval
- `RuntimeGovernanceService.build_runtime_operations_summary(...)` ahora incluye tambien:
  - `gestion_brechas_semanticas`

Trazabilidad nueva persistida por brecha:

- `metadata.flujo_revision.estado_actual`
- `metadata.flujo_revision.historial`
- `metadata.flujo_revision.ultimo_revisor`
- `metadata.flujo_revision.ultima_decision`
- `metadata.flujo_revision.propuesta_mejora`
- `metadata.flujo_revision.evaluaciones_vinculadas`
- `metadata.flujo_revision.casos_reales_reproducibles`
- referencias de aplicacion:
  - `referencia_metadata_creada`
  - `referencia_capacidad_creada`
  - `referencia_agente_creado`

Archivos modificados:

- `backend/apps/ia_dev/application/runtime/semantic_gap_registry_service.py`
- `backend/apps/ia_dev/application/runtime/semantic_gap_review_service.py`
- `backend/apps/ia_dev/application/memory/repositories.py`
- `backend/apps/ia_dev/services/sql_store.py`
- `backend/apps/ia_dev/services/runtime_governance_service.py`
- `backend/apps/ia_dev/views/chat_view.py`
- `backend/apps/ia_dev/views/__init__.py`
- `backend/apps/ia_dev/urls.py`
- tests focalizados de brechas, metadata y endpoints

Pruebas focalizadas ejecutadas:

- `python manage.py test apps.ia_dev.tests.test_semantic_gap_registry_service apps.ia_dev.tests.test_semantic_gap_review_service apps.ia_dev.tests.test_phase6_runtime_governance.Phase6GovernanceServiceTests.test_runtime_operations_summary_aggregates_task_runtime_state apps.ia_dev.tests.test_regression_endpoints.IADevRegressionEndpointsTests.test_semantic_gap_operations_endpoint_returns_operational_payload apps.ia_dev.tests.test_regression_endpoints.IADevRegressionEndpointsTests.test_semantic_gap_operations_endpoint_aprueba_propuesta apps.ia_dev.tests.test_chat_runtime_metadata.ChatRuntimeMetadataTests.test_attach_semantic_gap_learning_enriches_response_and_task_state`

Resultado:

- `21 tests`: OK

Regla critica persistida:

- el sistema puede registrar, clasificar, revisar y proponer mejoras sobre brechas reales
- la aplicacion a metadata, capabilities, tools o agentes sigue siendo gobernada
- no se escribe en `dd_*` ni se autocorrige ninguna autoridad estructural sin approval

## Sesion 2026-05-16: Continuous Runtime Learning iniciado

Que se asumio sin revalidar:

- P1 completado.
- P2 completado.
- P3-B parcial estable.
- P4 parcial estable alto.
- P5 implementado.
- P6 implementado.
- P7 implementado para `inventario_logistica`.
- `Capability Pack` de `inventario_logistica` activo.
- `SemanticCapabilityRegistry` activo.
- `evidence-first` activo.
- `semantic_explanation` activo.
- `QueryExecutionPlanner` sigue siendo autoridad unica de SQL seguro.
- `ToolRegistryService` sigue siendo autoridad unica de `capability -> tool`.
- `ai_dictionary` sigue siendo autoridad estructural.
- no se toca `fallback_policy`, `OpenAI Gateway`, `Agents Runtime`, approvals ni background.

Que quedo implementado:

- Primera version de `Continuous Runtime Learning` como capacidad transversal post P1-P7.
- Nueva tabla gobernada:
  - `ia_dictionary.registro_brechas_semanticas`
- Nuevo servicio tecnico:
  - `backend/apps/ia_dev/application/runtime/semantic_gap_registry_service.py`
- Integracion al cierre de `ChatApplicationService`:
  - registra brechas accionables reales
  - deja traza minima en:
    - `task_state.state.continuous_runtime_learning`
    - `task.current_run.evidence.continuous_runtime_learning`
    - `task.current_run.semantic_explanation.continuous_runtime_learning`
    - `data_sources.runtime.continuous_runtime_learning`
- Integracion con P5:
  - `inventario_runtime_eval_suite.py` ya puede registrar fallos P5 gobernados cuando se le pida explicitamente
  - no autocorrige nada

Categorias iniciales activas:

- `falta_sinonimo`
- `falta_regla`
- `falta_relacion`
- `falta_campo`
- `falta_tabla`
- `falta_capacidad`
- `falta_tool`
- `falta_agente`
- `consulta_ambigua`
- `fuera_de_alcance`
- `evidencia_insuficiente`
- `bloqueo_correcto`
- `error_tecnico`
- `fallback_excesivo`
- `degradacion_semantica`

Cuando se registra:

- estado final `blocked`
- aclaracion estructural requerida
- limitacion declarada
- capability sin resolver
- tool faltante
- evidencia insuficiente
- planner bloqueado
- fallback sombreado usado como senal de degradacion
- error tecnico controlado
- fallo P5 cuando se registra explicitamente desde la suite

Consultas operativas minimas ya expuestas:

- `brechas_nuevas`
- `brechas_por_categoria`
- `brechas_por_dominio`
- `brechas_por_capacidad`
- `brechas_frecuentes`
- `brechas_resueltas`
- `brechas_con_sugerencia_metadata`

Como se revisa:

- `RuntimeGovernanceService.build_runtime_operations_summary(...)` ahora incluye:
  - `continuous_runtime_learning`
- el backlog operativo puede revisarse desde esa superficie sin mezclarlo con observability cruda

Que NO se aplica automaticamente:

- nuevos sinonimos
- nuevas reglas
- nuevas relaciones
- nuevas capabilities
- nuevos tools
- nuevos agentes
- escrituras a `dd_*`
- cambios a `ai_dictionary`
- aprobaciones ni ejecuciones sensibles

Regla persistida:

- `Continuous Runtime Learning` no corrige solo.
- registra, clasifica y propone mejoras gobernadas.

Archivos relevantes nuevos/modificados:

- `backend/apps/ia_dev/application/runtime/semantic_gap_registry_service.py`
- `backend/apps/ia_dev/services/sql_store.py`
- `backend/apps/ia_dev/application/memory/repositories.py`
- `backend/apps/ia_dev/application/orchestration/chat_application_service.py`
- `backend/apps/ia_dev/application/runtime/inventario_runtime_eval_suite.py`
- `backend/apps/ia_dev/services/runtime_governance_service.py`

Pruebas focalizadas validadas:

- `python manage.py test apps.ia_dev.tests.test_semantic_gap_registry_service apps.ia_dev.tests.test_chat_runtime_metadata.ChatRuntimeMetadataTests.test_attach_semantic_gap_learning_enriches_response_and_task_state apps.ia_dev.tests.test_phase6_runtime_governance.Phase6GovernanceServiceTests.test_runtime_operations_summary_aggregates_task_runtime_state apps.ia_dev.tests.test_inventario_runtime_eval_suite`
- resultado:
  - `15 tests`: OK

Incidencia heredada detectada fuera de este alcance:

- `apps.ia_dev.tests.test_phase6_runtime_governance.Phase6RealDataDiagnoseTests.test_real_data_mode_reports_success_empty_and_critical_nulls`
- causa:
  - una expectativa heredada invoca `_build_sql_response(...)` con firma vieja sin `export_rows`
- no pertenece a `Continuous Runtime Learning`

## Sesion 2026-05-16: P7 Capability Packs / Agent Skills empresariales

Que se asumio sin revalidar:

- P1 completado.
- P2 completado.
- P3-B parcial estable.
- P4 parcial estable alto.
- P5 implementado.
- P6 implementado.
- `SemanticCapabilityRegistry` activo.
- `metadata_gobernada_inventario.py` activo.
- explicacion semantica saneada activa en backend y frontend.
- `QueryExecutionPlanner`, `fallback_policy`, `ToolRegistryService`, `OpenAI Gateway`, `Agents Runtime`, approvals, background y contratos de respuesta no se reescriben.

Que quedo implementado:

- `inventario_logistica` ya tiene un `Capability Pack` empresarial gobernado y versionado.
- artefactos nuevos del dominio:
  - `backend/apps/ia_dev/domains/inventario_logistica/paquete_capacidades.yaml`
  - `backend/apps/ia_dev/domains/inventario_logistica/reglas_semanticas.yaml`
  - `backend/apps/ia_dev/domains/inventario_logistica/perfiles_respuesta.yaml`
  - `backend/apps/ia_dev/domains/inventario_logistica/politicas_aprobacion.yaml`
  - `backend/apps/ia_dev/domains/inventario_logistica/evaluaciones.yaml`
  - `backend/apps/ia_dev/domains/inventario_logistica/README_OPERATIVO.md`
- loader/validator nuevo:
  - `backend/apps/ia_dev/domains/inventario_logistica/paquete_capacidades_loader.py`
- el pack valida:
  - dominio
  - version
  - capabilities declaradas
  - tools existentes
  - response profiles existentes
  - reglas vinculadas a metadata gobernada
  - evaluaciones asociadas
  - limitaciones declaradas
  - ausencia de SQL libre
  - ausencia de prompts internos inseguros

Integraciones activas:

- `SemanticCapabilityRegistry`
  - valida el `template_id`/`capability`/`response_profile` contra el pack
  - publica en binding trace:
    - `paquete_capacidad_usado`
    - `version_paquete`
    - `capacidades_declaradas`
    - `reglas_declaradas`
    - `perfiles_respuesta`
    - `evaluaciones_asociadas`
- `ToolRegistryService`
  - el pack valida tools declaradas contra el registry vigente
  - la autoridad `capability -> tool` sigue en `ToolRegistryService`
- `metadata_gobernada_inventario.py`
  - el pack no la reemplaza
  - sus reglas y campos siguen siendo la referencia estructural para validacion
- `response_assembler`
  - conserva `response_profile` evidence-first
  - ahora arrastra metadata del pack en `metadata`, `evidence_summary` y `semantic_trace`
- `semantic_explanation`
  - ahora expone un bloque `capability_pack` saneado al usuario/runtime trace
- eval suite P5
  - ahora exige traza del pack y no solo metadata semantica

Regla estable P7:

- el `Capability Pack` organiza, declara, valida y documenta capacidades del dominio
- no reemplaza `ai_dictionary`
- no reemplaza `QueryExecutionPlanner`
- no reemplaza `ToolRegistryService`
- no autoriza SQL
- no inventa tablas o columnas

Como crear nuevos packs despues de P7:

1. crear `paquete_capacidades.yaml`
2. declarar `reglas_semanticas.yaml`
3. declarar `perfiles_respuesta.yaml`
4. declarar `politicas_aprobacion.yaml`
5. declarar `evaluaciones.yaml`
6. vincular reglas a metadata gobernada real
7. validar tools y perfiles existentes
8. publicar traza del pack en binding, evidencia y `semantic_explanation`

Estado P1-P7:

- P1 metadata/capability-first inicial âœ…
- P2 centralizacion intent/capability/tool/planner âœ…
- P3 migracion parcial de reglas duras a metadata gobernada â— estable parcial
- P4 response assembly evidence-first â— estable alto
- P5 pruebas reales + evals anti-hardcode âœ…
- P6 UI/UX de explicacion semantica âœ…
- P7 Capability Packs / Agent Skills empresariales âœ… para `inventario_logistica`

Nota oficial de roadmap:

- despues de P7 inicia `Continuous Runtime Learning`
- no implementar en P7:
  - tabla de fallos
  - aprendizaje operacional
  - propuestas de metadata
  - gaps
  - metricas reales

Pruebas ejecutadas:

- `python manage.py test apps.ia_dev.tests.test_inventory_capability_pack_loader apps.ia_dev.tests.test_semantic_capability_registry apps.ia_dev.tests.test_inventory_response_assembler apps.ia_dev.tests.test_inventario_runtime_eval_suite apps.ia_dev.tests.test_chat_runtime_metadata`
- `python manage.py test apps.ia_dev.tests.test_inventario_semantic_resolver apps.ia_dev.tests.test_inventario_runtime_sql_alignment apps.ia_dev.tests.test_semantic_capability_registry apps.ia_dev.tests.test_inventory_response_assembler apps.ia_dev.tests.test_inventario_runtime_eval_suite apps.ia_dev.tests.test_chat_response_contracts apps.ia_dev.tests.test_chat_runtime_metadata`

Resultado:

- `44 tests`: OK
- `117 tests`: OK

## Sesion 2026-05-16: P6 UI/UX de explicacion semantica

Que se asumio sin revalidar:

- P1 y P2 completados.
- P3-B parcial estable.
- P4 parcial estable alto.
- P5 implementado con evals anti-hardcode.
- `inventario_runtime_eval_suite.py` existe.
- `inventario_logistica` ya responde evidence-first.
- `SemanticCapabilityRegistry` y `metadata_gobernada_inventario.py` siguen activos.
- No se reaudita arquitectura completa ni se tocan `QueryExecutionPlanner`, `fallback_policy`, `ToolRegistryService`, `OpenAI Gateway`, `Agents Runtime`, approvals, background, SQL builders, `ai_dictionary` ni contratos base.

Que se implemento:

- El backend ahora publica `task.current_run.semantic_explanation` como bloque saneado y derivado de metadata ya existente.
- La explicacion se arma desde:
  - `BusinessQuerySemanticPlan`
  - `semantic_trace`
  - `semantic_context`
  - `response_profile`
  - `evidence_summary`
  - `task.current_run`
  - `tool_execution`
  - `validation`
  - metadata de approvals y background
- El frontend ahora muestra una UX dedicada para explicar:
  - que entendio el sistema
  - dominio e intencion
  - entidad y filtros aplicados
  - capability, herramienta y ruta usada
  - validacion
  - evidencia y limitaciones
  - timeline de tarea
  - indicadores de metadata gobernada, fallback sombreado, approvals y background
- La vista mantiene compatibilidad con:
  - `reply` top-level
  - dashboard actual
  - `data.table`
  - `extra_tables`
  - mobile y tablet

Metadata expuesta al usuario:

- `user_question`
- `understood_as`
- `domain`
- `intent`
- `entity`
- `normalized_filters`
- `selected_capability`
- `selected_tool`
- `planner_route_hint`
- `validation_status`
- `evidence_summary`
- `limitations`
- `clarification_needed`
- `metadata_used`
- `fallback_used`
- `agents_involved`
- `approvals_status`
- `background_status`
- `final_state`
- `timeline`

Que se oculta por seguridad:

- prompts internos
- chain-of-thought
- traces crudos
- SQL crudo sensible
- secretos
- payloads internos no saneados

Archivos modificados:

- `backend/apps/ia_dev/application/contracts/chat_contracts.py`
- `backend/apps/ia_dev/application/orchestration/chat_application_service.py`
- `backend/apps/ia_dev/tests/test_chat_response_contracts.py`
- `backend/apps/ia_dev/tests/test_chat_runtime_metadata.py`
- `frontend/src/services/ia-dev.service.ts`
- `frontend/src/modules/programacion/ia-dev/chat/types.ts`
- `frontend/src/modules/programacion/ia-dev/chat/utils/normalizeChatPayload.ts`
- `frontend/src/modules/agente-ia/types.ts`
- `frontend/src/modules/agente-ia/utils/buildDashboardSnapshot.ts`
- `frontend/src/modules/agente-ia/components/DashboardRenderer.tsx`
- `frontend/src/modules/agente-ia/components/SemanticExplanationPanel.tsx`
- `frontend/src/modules/agente-ia/components/TaskTimeline.tsx`
- `frontend/src/modules/agente-ia/components/EvidenceSummaryPanel.tsx`
- `frontend/src/modules/agente-ia/components/ValidationStatusPanel.tsx`

Pruebas ejecutadas:

- `python manage.py test apps.ia_dev.tests.test_chat_response_contracts apps.ia_dev.tests.test_chat_runtime_metadata apps.ia_dev.tests.test_business_response_composer_service`
- `npm run typecheck`

Resultado:

- `28 tests`: OK
- frontend `typecheck`: OK

Avance oficial P1-P7:

- P1 âœ…
- P2 âœ…
- P3-B parcial estable
- P4 parcial estable alto
- P5 âœ…
- P6 âœ… `UI/UX de explicacion semantica`
- P7 pendiente `Capability Packs / Agent Skills empresariales`

Siguiente paso:

- P7 debe empaquetar capabilities y skills empresariales reutilizables sobre esta base.
- No implementar todavia `Continuous Runtime Learning` dentro de P6.

## Sesion 2026-05-16: P5 evals reales y anti-hardcode en inventario

Que se asumio sin revalidar:

- P1 completado.
- P2-A completado.
- P2-B completado.
- P3-A completado.
- P3-B parcial estable.
- P4 parcial estable alto.
- `SemanticCapabilityRegistry` activo.
- `metadata_gobernada_inventario.py` activo.
- `inventario_logistica` evidence-first activo.
- `patterns/legacy` siguen solo como fallback sombreado.
- no se toca `QueryExecutionPlanner` como autoridad SQL, `fallback_policy`, `ToolRegistryService`, `OpenAI Gateway`, `Agents Runtime`, approvals, background, frontend ni contratos `reply/task/data/evidence/status`.

Que quedo implementado:

- nueva suite focalizada de P5 en:
  - `backend/apps/ia_dev/application/runtime/inventario_runtime_eval_suite.py`
  - dataset versionado `p5_inventario_runtime_eval_v1`
- la suite evalua el flujo real:
  - `InventorySemanticResolver`
  - `SemanticCapabilityRegistry`
  - `QueryExecutionPlanner`
  - `build_inventory_business_response(...)`
- evaluadores simples incorporados:
  - `semantic correctness`
  - `capability correctness`
  - `planner route correctness`
  - `evidence correctness`
  - `clarification correctness`
  - `limitation correctness`
  - `anti-hardcode validation`
- traza minima por caso:
  - `eval_result`
  - `eval_reason`
  - `semantic_confidence`
  - `fallback_detected`
  - `metadata_used`
  - `suspected_hardcode`
- casos reales cubiertos con variaciones semanticas:
  - cuadrilla / movil / brigada `TIRAN224`
  - tecnico / empleado / cedula `5098747`
  - `ferreteria`
  - `movimientos`
  - `entradas y salidas`
  - `historial del codigo 1025507 para 5098747`
  - `actas SAP`
  - nombre propio ambiguo
  - resultado vacio
  - ruido textual adicional

Ajuste anti-hardcode incorporado en runtime:

- `backend/apps/ia_dev/domains/inventario_logistica/semantic_inventory_resolver.py`
  - ahora reconoce `codigo` y `código`
  - ahora reconoce cedula operacional en frases tipo `historial ... para 5098747`
  - esto elimina dependencia innecesaria de wording exacto para una familia real de consultas de kardex por empleado

Metricas P5 obtenidas con dataset versionado:

- `13` preguntas evaluadas
- `12` casos pasaron
- `1` caso fallo de forma controlada
- clasificacion:
  - `10` `correcto`
  - `1` `aclaracion_valida`
  - `1` `limitacion_valida`
  - `1` `capability_incorrecta`
- `metadata_usage_count = 13`
- `metadata_usage_ratio = 1.0`
- `evidence_coverage_count = 13`
- `evidence_coverage_ratio = 1.0`
- `fallback_usage_count = 2`
- `fallback_usage_ratio = 0.1538`
- `clarification_ratio = 0.0769`
- `limitation_ratio = 0.0769`
- `suspected_hardcode_count = 0`

Fallbacks y gaps detectados:

- caso controlado `fallback_sombreado_controlado`:
  - al forzar metadata gobernada vacia, la ruta cae en `legacy` sombreado
  - queda trazado con:
    - `fallback_sombreado_usado = true`
    - `regla_legacy_detectada = true`
  - el legado degrada de `inventory_kardex_by_employee` a `inventory_kardex_consolidated`
  - el evaluador lo clasifica como `capability_incorrecta`
- esto deja validado que P5 ya detecta:
  - dependencia excesiva de metadata ausente
  - divergencia capability/route
  - respuestas exitosas con evidencia pero semantica degradada

Pruebas ejecutadas y estado:

- `python manage.py test apps.ia_dev.tests.test_inventario_runtime_eval_suite apps.ia_dev.tests.test_inventario_semantic_resolver apps.ia_dev.tests.test_inventory_response_assembler apps.ia_dev.tests.test_semantic_capability_registry`
- resultado:
  - `58 tests`: OK
- `python manage.py test apps.ia_dev.tests.test_chat_response_contracts apps.ia_dev.tests.test_chat_runtime_metadata`
- resultado:
  - `25 tests`: OK
- comprobacion ampliada:
  - `python manage.py test apps.ia_dev.tests.test_inventory_response_assembler apps.ia_dev.tests.test_inventario_semantic_resolver apps.ia_dev.tests.test_inventario_runtime_sql_alignment apps.ia_dev.tests.test_semantic_capability_registry apps.ia_dev.tests.test_chat_response_contracts apps.ia_dev.tests.test_chat_runtime_metadata`
- resultado:
  - reaparecen solo los `2` fallos heredados ya persistidos antes de P5:
    - `test_planner_builds_transfer_warehouse_without_destination_column`
    - `test_planner_builds_transfer_other_ally`
  - ambos siguen fuera del alcance funcional de P5 y no fueron introducidos por esta iteracion

Readiness para `Continuous Runtime Learning`:

- P5 no implementa tablas ni runtime learning.
- si deja listo el shape minimo reusable para una futura persistencia transversal:
  - `pregunta_original`
  - `grupo_semantico`
  - `clasificacion`
  - `eval_reason`
  - `template_id`
  - `candidate_capability`
  - `planner_reason`
  - `response_status`
  - `semantic_confidence`
  - `fallback_detected`
  - `metadata_used`
  - `suspected_hardcode`

Estado P5:

- P5 🟡 parcial estable alto
- la capa de eval ya existe, detecta degradacion real y valida evidencia/governance
- queda un gap controlado visible cuando desaparece metadata gobernada y el fallback legacy cambia la capability de kardex

Avance global P1-P7:

- P1 ✅ inventario metadata/capability-first inicial
- P2 ✅ centralizar mapping intent/capability/tool/planner
- P3 🟡 migrar reglas duras a `ai_dictionary` y `dd_*` parcial estable
- P4 🟡 evidence-first response assembly parcial estable alto
- P5 🟡 pruebas reales + evals anti-hardcode parcial estable alto
- P6 siguiente paso: UI/UX de explicacion semantica
- P7 pendiente: Capability Packs / Agent Skills empresariales

## Sesion 2026-05-16: P4 evidence-first response assembly en inventario

Que se asumio sin revalidar:

- P1 completado.
- P2-A completado.
- P2-B completado.
- P3-A completado.
- P3-B parcial estable.
- `SemanticCapabilityRegistry` ya existe para `inventario_logistica`.
- `metadata_gobernada_inventario.py` ya existe.
- `patterns` y `legacy` siguen solo como fallback sombreado.
- `QueryExecutionPlanner` sigue siendo la unica autoridad de SQL seguro.
- no se toca `fallback_policy`, `ToolRegistryService`, `OpenAI Gateway`, `Agents Runtime`, approvals, background ni frontend.

Que quedo implementado:

- `backend/apps/ia_dev/domains/inventario_logistica/response_assembler.py`
  - la respuesta de inventario ahora se arma primero desde:
    - `BusinessQuerySemanticPlan`
    - `semantic_context`
    - `semantic_capability_registry`
    - `response_profile`
    - `result_set`
    - `extra_tables`
    - `limitations`
  - ya no depende principalmente de frases del usuario ni de `reply` previo para cerrar exito, vacio, aclaracion o limitacion.
  - agrega:
    - `response_profile` estructurado
    - `evidence_summary` estructurado
    - metadata de traza:
      - `response_profile_usado`
      - `evidence_sources_used`
      - `semantic_context_used`
      - `fallback_narrativo_usado`
      - `missing_evidence_reason`
      - `semantic_trace`
  - estados evidence-first manejados:
    - `success`
    - `clarification_required`
    - `limitation_declared`
    - `empty_result`

- `backend/apps/ia_dev/application/semantic/query_execution_planner.py`
  - para `inventario_logistica`, el planner ahora entrega al assembler:
    - `result_set`
    - `supplemental_tables`
    - `execution_metadata`
  - se redujo el armado narrativo hardcodeado posterior para doble bloque; la autoridad de cierre pasa al assembler del dominio.

- `backend/apps/ia_dev/application/orchestration/business_response_composer_service.py`
  - si existe `data.business_response`, el `reply` final pasa a derivarse de ese bloque estructurado y no del texto tecnico previo.
  - el composer enriquece la salida con evidencia runtime:
    - validacion
    - tool execution
    - runtime trace

- `backend/apps/ia_dev/application/orchestration/chat_application_service.py`
  - `task.current_run.evidence` ahora expone tambien:
    - `response_profile_usado`
    - `evidence_sources_used`
    - `semantic_context_used`
    - `fallback_narrativo_usado`
    - `missing_evidence_reason`

Que respuestas ya quedaron evidence-first:

- inventario operativo por movil/cuadrilla/empleado
- inventario generico dual block materiales + serializados cuando aplica
- kardex por empleado/codigo
- aclaracion estructural por portador ambiguo
- limitacion declarada para SAP o documentacion no habilitada
- resultado vacio explicado desde `result_set` y filtros ejecutados

Fallback narrativo que aun queda:

- perfiles no modelados especificamente en `inventario_logistica` caen en resumen generico evidence-first del dominio
- otros dominios fuera de `inventario_logistica` siguen usando parte del composer transversal heredado
- `response_assembler` transversal legacy sigue existiendo para rutas no migradas a P4

Pruebas focalizadas ejecutadas:

- `python manage.py test apps.ia_dev.tests.test_inventory_response_assembler apps.ia_dev.tests.test_business_response_composer_service apps.ia_dev.tests.test_chat_response_contracts apps.ia_dev.tests.test_chat_runtime_metadata apps.ia_dev.tests.test_semantic_capability_registry`

Resultado:

- `39 tests`: OK

Prueba ampliada relevante:

- `python manage.py test apps.ia_dev.tests.test_inventario_semantic_resolver apps.ia_dev.tests.test_inventario_runtime_sql_alignment apps.ia_dev.tests.test_inventory_business_query_semantic_plan apps.ia_dev.tests.test_inventory_response_assembler apps.ia_dev.tests.test_semantic_capability_registry`

Resultado:

- la parte nueva de P4 quedo estable
- aparecieron 2 fallos existentes o fuera del alcance P4 en `test_inventario_runtime_sql_alignment`:
  - `test_planner_builds_transfer_warehouse_without_destination_column`
  - `test_planner_builds_transfer_other_ally`
- ambos fallan por `plan.reason` de rutas `transfer_*`, no por response assembly evidence-first

Estado P4:

- `inventario_logistica`: parcial estable alto
- transversal: ajuste pequeno y seguro en composer/task evidence

Avance global P1-P7:

- P1 ✅ inventario metadata/capability-first inicial
- P2 ✅ centralizar mapping intent/capability/tool/planner
- P3 🟡 migrar reglas duras a `ai_dictionary` y `dd_*` parcial estable
- P4 🟡 evidence-first response assembly parcial estable
- P5 siguiente paso: pruebas reales + evals anti-hardcode
- P6 pendiente: UI/UX de explicacion semantica
- P7 pendiente: Capability Packs / Agent Skills empresariales

Nota de roadmap:

- P1-P7 siguen siendo la arquitectura funcional
- despues de P7 viene la linea transversal `Continuous Runtime Learning`
- ahi entran tabla de fallos, aprendizaje operacional, propuestas de metadata, gaps y metricas reales
- P4 no implementa `Continuous Runtime Learning`; solo deja trazabilidad util para futuras fases

## Sesion 2026-05-16: P3-B gobierno metadata-first de reglas duras en inventario

Que se asumio sin revalidar:

- P1 completado.
- P2-A completado.
- P2-B completado.
- `SemanticCapabilityRegistry` sigue siendo la autoridad unica de binding semantico.
- `ToolRegistryService` sigue siendo la autoridad unica de `capability -> tool_id`.
- `QueryExecutionPlanner` sigue siendo la autoridad unica de SQL seguro.
- no se toca `fallback_policy`, approvals, background, agents runtime, OpenAI gateway, frontend ni contratos `reply/task/data/evidence/status`.

Que quedo implementado en P3-B:

- se agrego metadata gobernada reutilizable para `inventario_logistica` en:
  - `dd_sinonimos`
  - `dd_reglas`
  - `ia_dev_capacidades_columna`
- `InventoryDictionarySyncService.build_preview(...)` y `sync(...)` ya incluyen:
  - `dd_reglas_preview_count`
  - `ia_dev_capacidades_columna_preview_count`
  - upsert controlado de `ia_dev_capacidades_columna`
- `SemanticCapabilityRegistry` ya prioriza metadata gobernada para resolver:
  - `template_id`
  - `candidate_capability`
  - `planner_route_hint`
  - `response_profile`
  - `output_profile`
- `MatcherSemanticoGobernadoInventario` ya consume metadata gobernada para sinonimia y reglas P3-B prioritarias.
- el legado queda como fallback sombreado y no como autoridad primaria.

Reglas migradas a metadata gobernada:

- `dd_sinonimos`
  - `material claro`
  - `material de claro`
  - `ferretero`
  - `material ferretero`
  - `material`
  - `cuadrilla`
  - `brigada`
  - `movil`
  - `móvil`
  - `tecnico`
  - `técnico`
  - `empleado`
  - `cedula`
  - `cédula`
  - `kardex`
  - `movimientos`
  - `entradas y salidas`
  - `serial`
  - `seriales`
  - `equipo`
  - `equipos`
  - `CPE`
  - `bodega`
  - `operacion_hfc`
- `dd_reglas`
  - `identificador numerico => cedula`
  - `identificador alfanumerico operativo => movil`
  - `inventario generico sin familia explicita => dual block`
  - `material claro => tipo = material`
  - `ferretero => tipo = ferretero`
  - `material generico => tipo IN (material, ferretero)`
  - `serializados/equipos => conteo, no cantidad`
  - `saldos incluyen positivos, cero y negativos`
  - `kardex: entrega suma`
  - `kardex: devolucion, consumo y cobro restan`
  - `kardex: saldo acumulado cronologico`
  - `actas/SAP/documentos => limitacion declarada`
  - `bodega destino => limitacion declarada por metadata faltante`
- `ia_dev_capacidades_columna`
  - afinidad gobernada para:
    - `cedula`
    - `movil`
    - `codigo`
    - `serial`
    - `bodega`
    - `tipo`
    - `estado`
    - `fecha`
    - `orden_trabajo`
    - `familia`
    - `descripcion`

Trazabilidad nueva persistida:

- `regla_metadata_usada`
- `fuente_dd`
- `fallback_sombreado_usado`
- `regla_legacy_detectada`
- `regla_migrada`

Donde queda visible:

- `semantic_context.inventory_governed_match`
- `semantic_context.semantic_capability_registry`
- `semantic_context.resolved_semantic.semantic_capability_registry`
- `semantic_context.resolved_semantic.binding_trace`

Que quedo como fallback sombreado temporal:

- `INVENTORY_TEMPLATE_BINDINGS` en `semantic_capability_registry.py`
- `_resolve_inventory_template_legacy(...)`
- heuristicas heredadas no prioritarias fuera de las familias P3-B migradas
- parte del arbol legacy de `semantic_inventory_resolver.py` para intents no priorizados en esta sesion

Que no se elimino aun y por que:

- no se elimino el mapa legacy completo porque la equivalencia total de todas las rutas de inventario todavia no esta demostrada por tests anti-hardcode para cada intent heredado.
- no se movieron formulas SQL, joins efectivos ni guardrails de compilacion a metadata.
- no se ajusto `dd_relaciones` en esta sesion porque no aparecio una necesidad segura adicional validada por P3-A para los casos priorizados.

Estado P3-B:

- `P3-B`: parcial estable
- criterio cumplido:
  - metadata primero
  - lectura desde metadata
  - comparacion contra legacy
  - fallback sombreado
  - sin mover autoridad SQL ni tool binding

Pruebas ejecutadas:

- `python manage.py test apps.ia_dev.tests.test_inventario_dictionary_sync apps.ia_dev.tests.test_semantic_capability_registry apps.ia_dev.tests.test_semantic_orchestrator_service apps.ia_dev.tests.test_chat_runtime_metadata apps.ia_dev.tests.test_chat_response_contracts`
- `python manage.py test apps.ia_dev.tests.test_inventory_business_query_semantic_plan apps.ia_dev.tests.test_inventario_semantic_resolver apps.ia_dev.tests.test_query_intelligence_layer`

Resultado:

- `153 tests`: OK

Casos reales cubiertos en la sesion:

- `que tiene asignado la cuadrilla TIRAN224`
- `muestrame lo que tiene el movil TIRAN224`
- `movimientos del tecnico 5098747`
- `entradas y salidas de 5098747`
- `solo material de claro de TIRAN224`
- `ferreteria asignada al tecnico 5098747`
- `que tiene Juan Perez`
- `actas SAP del empleado 5098747`

Avance global P1-P7:

- P1 `inventario metadata/capability-first inicial` -> vigente
- P2 `centralizar mapping intent/capability/tool/planner` -> vigente
- P3 `migrar reglas duras a ai_dictionary/dd_*` -> en progreso; P3-B parcial estable
- P4 `evidence-first response assembly general` -> siguiente foco recomendado
- P5 `pruebas reales + evals anti-hardcode` -> pendiente de ampliar
- P6 `UI/UX de explicacion semantica` -> sin cambios
- P7 `Capability Packs / Agent Skills empresariales` -> sin cambios

Riesgos vigentes:

- el runtime todavia conserva mapas legacy de compatibilidad para rutas no cubiertas por las reglas P3-B priorizadas.
- `ia_dev_capacidades_columna` sigue siendo afinidad por campo; el binding semantico rico sigue apoyandose tambien en `dd_reglas`.
- falta ampliar tests anti-hardcode para demostrar cuando ya se puedan retirar mas listas legacy.

Proximos pasos recomendados para P4:

- hacer que `response_assembler` consuma preferentemente `response_profile`, `binding_trace` y `semantic_trace` en vez de heuristicas por texto o `row_keys`.
- ampliar casos reales obligatorios faltantes:
  - `inventario operativo de TIRAN224 con empleados`
  - `que saldo tiene 5098747`
  - `revisa inventario del tecnico 5098747`
  - `historial del codigo 1025507 para 5098747`
  - `materiales del movil TIRAN224`
- agregar evals anti-hardcode para demostrar cuando ya se puedan retirar mas listas legacy.

## Sesion 2026-05-16: P3-A diagnostico de migracion de reglas duras a gobierno metadata

Que se asumio sin revalidar:

- P1 completado.
- P2-A completado.
- P2-B completado.
- `SemanticCapabilityRegistry` ya existe para `inventario_logistica`.
- `patterns` quedan como fallback sombreado.
- `QueryExecutionPlanner` sigue siendo la unica autoridad SQL.
- no se toca `fallback_policy`, `ToolRegistryService`, `OpenAI Gateway`, `Agents Runtime`, approvals, background ni frontend.

Que quedo confirmado:

- La deuda principal de `inventario_logistica` ya no esta en SQL sino en reglas semanticas duplicadas entre:
  - `matcher_semantico_gobernado_inventario.py`
  - `semantic_inventory_resolver.py`
  - `semantic_capability_registry.py`
  - `business_query_semantic_plan.py`
  - `query_intent_resolver.py`
  - `semantic_orchestrator_service.py`
  - `query_execution_planner.py`
  - `response_assembler.py`
- Los hardcodes detectados se concentran en:
  - sinonimos
  - regex de identificadores
  - reglas de negocio compuestas
  - `template_id -> capability -> planner_route_hint -> response_profile`
  - heuristicas narrativas por `row_keys`
- `runtime_capability_adapter` ya respeta primero `semantic_capability_registry` para inventario y no es el cuello principal de P3.

Reglas detectadas y clasificadas:

- Deben migrar a `dd_sinonimos`:
  - `inventario|stock|saldo|existencia`
  - `movil|cuadrilla|brigada`
  - `kardex|movimientos|entradas y salidas`
  - `material claro|material de claro`
  - `ferretero|ferreteria|material ferretero`
  - `serial|seriales|equipos|cpe`
  - `sap|acta|actas`
- Deben migrar a `dd_reglas`:
  - numerico => `cedula`
  - alfanumerico operativo => `movil`
  - `material claro => tipo=material`
  - `ferretero => tipo=ferretero`
  - `material generico => tipo in (material, ferretero)`
  - inventario generico => doble bloque materiales + serializados
  - serializados => conteo
  - saldo incluye positivos, cero y negativos
  - kardex por empleado/codigo
  - limitaciones `SAP/actas/documentos`
  - `bodega destino` como bloqueo por metadata faltante
- Deben migrar a `dd_relaciones`:
  - `movil -> cedulas`
  - enrichment historico con personal
  - dependencias con catalogos de materiales y serializados
- Deben migrar a `dd_campos`:
  - `cedula`, `movil`, `codigo`, `serial`, `bodega`
- Deben migrar a `ia_dev_capacidades_columna`:
  - binding `intent/entity/filter/output -> template_id/capability/planner_route_hint/response_profile`
- Deben quedarse en codigo:
  - formulas SQL
  - casteos numericos
  - guardrails de compilacion
  - joins efectivos
  - validaciones de seguridad
- Pueden quedar como fallback sombreado temporal:
  - `_resolve_inventory_template_legacy(...)`
  - `_resolve_template_id(...)` heredado
  - `_resolve_capability(...)` heredado
  - heuristicas de `response_assembler`
- Hardcode critico a eliminar:
  - `INVENTORY_TEMPLATE_BINDINGS`
  - `INVENTORY_INTENT_IDS_BY_TEMPLATE`
  - duplicaciones de regex/routing entre resolver, intent resolver, orchestrator y planner

Plan P3-B priorizado:

1. mover alias y conceptos base a `dd_sinonimos` y `dd_campos`
2. mover reglas P1 core a `dd_reglas`
3. sacar `template_id/capability/route/response_profile` de mapas Python hacia `ia_dev_capacidades_columna`
4. gobernar limitaciones declaradas y bloqueos conocidos en metadata
5. dejar los hardcodes viejos solo como fallback sombreado con traza
6. eliminar hardcode cuando exista cobertura de tests anti-hardcode

Riesgos persistidos:

- divergencia temporal entre metadata nueva y fallback heredado
- planner ocultando inconsistencias si sigue remapeando capability por `template_id`
- `response_assembler` contradiciendo `response_profile` por heuristicas de `row_keys`
- aliases demasiado amplios capturando consultas de otros dominios
- seriales numericos colisionando con la regla `numerico => cedula` si no se condiciona por intent/familia

Pruebas necesarias para P3-B:

- no regresion de casos P1:
  - `que tiene asignado la cuadrilla TIRAN224`
  - `muestrame lo que tiene el movil TIRAN224`
  - `movimientos del tecnico 5098747`
  - `entradas y salidas de 5098747`
  - `solo material de claro de TIRAN224`
  - `ferreteria asignada al tecnico 5098747`
  - `actas SAP del empleado 5098747`
- tests anti-hardcode:
  - registry resolviendo desde `dd_sinonimos`
  - binding resolviendo desde `ia_dev_capacidades_columna`
  - `legacy_mapping_used` trazado solo cuando falte metadata
- tests de planner:
  - no cambia autoridad SQL
  - `dual_block` sigue gobernado
  - limitaciones siguen declaradas
- tests de respuesta:
  - `response_assembler` prioriza `response_profile` y `semantic_trace`

Documento oficial generado:

- `backend/DIAGNOSTICO_P3A_GOBIERNO_REGLAS_DURAS_INVENTARIO.md`

Avance oficial P1-P7:

- P1 `Inventario metadata/capability-first inicial` âœ…
- P2 `Centralizar mapping intent/capability/tool/planner` âœ…
- P3-A `Diagnostico y plan seguro de migracion de reglas duras a dd_*` âœ…
- P3-B pendiente: extraccion controlada a metadata gobernada
- P4 pendiente: evidence-first response assembly general
- P5 pendiente: pruebas reales + evals anti-hardcode
- P6 pendiente: UI/UX de explicacion semantica
- P7 pendiente: capability packs / agent skills empresariales

## Sesion 2026-05-16: P2-B Semantic Capability Registry read-only para inventario_logistica

Que se asumio sin revalidar:

- P1 de inventario ya estaba completado y validado.
- P2-A ya habia dejado definido el corte de autoridad.
- `QueryExecutionPlanner` sigue siendo la unica autoridad de estrategia final y SQL seguro.
- `ToolRegistryService` sigue siendo la unica autoridad de `capability -> tool_id`.
- no se tocan `fallback_policy`, empleados, ausentismo ni transport en esta iteracion.

Que quedo implementado:

- nuevo `SemanticCapabilityRegistry` en:
  - `backend/apps/ia_dev/application/semantic/semantic_capability_registry.py`
- el registry ahora centraliza para `inventario_logistica`:
  - `intent + entity + filters + output -> template_id`
  - `template_id -> candidate_capability`
  - `candidate_capability -> planner_route_hint`
  - `candidate_capability/template -> response_profile`
  - `candidate_capability -> tool_id` consumiendo `ToolRegistryService`
- el registry deja trace read-only con:
  - `source`
  - `matched_rules`
  - `consulted_metadata`
  - `confidence`
  - `fallback_used`
  - `unresolved_reason`
  - `legacy_mapping_used`
  - `legacy_reason`
  - `migration_target`

Integracion gradual aplicada:

- `semantic_inventory_resolver.py`
  - ya resuelve `binding_decision` desde el registry
  - el viejo `template_map` deja de ser autoridad principal
  - el trace queda publicado en:
    - `semantic_context.semantic_capability_registry`
    - `semantic_context.resolved_semantic.semantic_capability_registry`
    - `semantic_context.resolved_semantic.binding_trace`
- `business_query_semantic_plan.py`
  - consume el binding del registry para poblar:
    - `candidate_capability`
    - `output`
    - metadata de `template_id/planner_route_hint/response_profile/tool_id`
  - los mappings heredados quedan como fallback sombreado
- `query_intent_resolver.py`
  - para inventario ya puede pedir `template_id` al registry antes de caer al mapping heredado
- `semantic_orchestrator_service.py`
  - para inventario prioriza el registry para decidir `capability` semantica candidata
  - sus heuristicas previas quedan como sombra de compatibilidad
- `runtime_capability_adapter.py`
  - ya puede leer `candidate_capability` desde el binding persistido en `resolved_query.semantic_context`
- `query_execution_planner.py`
  - ya prioriza `candidate_capability` proveniente del registry/semantic context antes del remapeo legacy por `template_id`
  - `metadata.semantic_trace` ahora incluye `semantic_binding`
- `response_assembler.py`
  - ya recibe y expone en metadata:
    - `template_id`
    - `candidate_capability`
    - `planner_route_hint`
    - `response_profile`
    - `tool_id`

Estado P2 actualizado:

- P1 âœ… Inventario metadata/capability-first inicial
- P2 âœ… Centralizar mapping intent/capability/tool/planner
- P2-B âœ… `SemanticCapabilityRegistry` read-only implementado para `inventario_logistica`
- P3 pendiente -> migrar mas reglas duras a `ai_dictionary/dd_*`
- P4 pendiente -> evidence-first response assembly general
- P5 pendiente -> pruebas reales + evals anti-hardcode
- P6 pendiente -> UI/UX de explicacion semantica

Duplicaciones que aun quedan como fallback sombreado:

- heuristicas heredadas en `semantic_orchestrator_service.py` para inventario
- remapeos legacy por `template_id` en `query_execution_planner.py`
- helpers heredados de output/capability en `business_query_semantic_plan.py`
- matcher/patrones siguen proponiendo familia e intencion, pero ya no deben ser la autoridad final cuando existe binding del registry

Siguiente paso confirmado para P3:

- mover mas reglas de inventario desde heuristicas Python a `dd_reglas`, `dd_sinonimos` e `ia_dev_capacidades_columna`
- reducir los fallbacks legacy del planner y del orchestrator hasta dejar el registry como unica autoridad semantica efectiva de inventario
- ampliar el mismo patron despues a otros dominios, pero no antes de cerrar la deuda restante de inventario

Pruebas ejecutadas:

- `python manage.py test apps.ia_dev.tests.test_semantic_capability_registry apps.ia_dev.tests.test_inventario_semantic_resolver apps.ia_dev.tests.test_inventory_business_query_semantic_plan apps.ia_dev.tests.test_semantic_orchestrator_service`
- `python manage.py test apps.ia_dev.tests.test_inventario_runtime_sql_alignment apps.ia_dev.tests.test_semantic_orchestrator_service apps.ia_dev.tests.test_chat_response_contracts apps.ia_dev.tests.test_chat_runtime_metadata apps.ia_dev.tests.test_tool_registry_service`

Resultado:

- `135 tests`: OK

## Sesion 2026-05-16: P2-A centralizacion de mappings intent/capability/tool/planner

Que se asumio sin revalidar:

- existe `matcher_semantico_gobernado_inventario.py`
- los patterns quedan como fallback sombreado y no como autoridad
- `response_assembler` debe preferir plan/contexto y no la frase del usuario
- `QueryExecutionPlanner` sigue siendo la unica autoridad SQL
- no se tocan `ai_dictionary`, `fallback_policy`, `task envelope`, `tool registry` base, gateway, agents runtime, approvals, background ni frontend

Que se hizo:

- diagnostico focalizado de duplicaciones actuales entre:
  - `semantic_inventory_resolver.py`
  - `matcher_semantico_gobernado_inventario.py`
  - `semantic_orchestrator_service.py`
  - `query_intent_resolver.py`
  - `runtime_capability_adapter.py`
  - `business_query_semantic_plan.py`
  - `tool_registry_service.py`
  - `query_execution_planner.py`
- se documento el diseno propuesto en:
  - `backend/DIAGNOSTICO_P2A_SEMANTIC_CAPABILITY_REGISTRY.md`

Hallazgo principal:

- hoy el binding `intent/entity/filter/output -> capability/template/route/response` esta repartido entre matcher, resolver, intent resolver, orchestrator, adapter y planner
- la duplicacion mas critica esta en:
  - `candidate_capability`
  - `template_id`
  - `planner route`
  - `response profile`
- `tool_id` ya esta razonablemente centralizado en `ToolRegistryService`

Diseno propuesto:

- crear `SemanticCapabilityRegistry` como autoridad unica de binding semantico para:
  - `intent`
  - `entity`
  - `normalized_filters`
  - `output profile`
  - `candidate_capability`
  - `template_id`
  - `planner_route_hint`
  - `response_profile`
- mantener la separacion:
  - `SemanticCapabilityRegistry` => binding semantico
  - `ToolRegistryService` => `capability -> tool_id`
  - `QueryExecutionPlanner` => estrategia y SQL seguro

Que no se toco:

- `ai_dictionary`
- `QueryExecutionPlanner` como autoridad SQL
- `fallback_policy`
- `task envelope`
- `tool registry` base
- `gateway`
- `agents runtime`
- approvals
- background
- frontend

Estado de la fase:

- P2-A completado
- diseno propuesto y persistido
- sin refactor grande implementado aun

Que queda para P2-B:

1. crear `SemanticCapabilityRegistry` read-only para inventario
2. mover al registry los mappings de `template_id/candidate_capability/response_profile`
3. hacer que `semantic_inventory_resolver` y `business_query_semantic_plan` consuman ese registry
4. dejar `semantic_orchestrator_service` en modo consumidor y no autoridad paralela
5. reducir el remapeo de capability en `query_execution_planner` a compatibilidad temporal auditada

Pruebas:

- no se corrieron pruebas runtime en P2-A porque no hubo cambio de codigo productivo
- la sesion fue solo de diagnostico, diseno y persistencia documental

## Sesion 2026-05-16: Endurecimiento y operacion enterprise sobre runtime task-first

Que se asumio sin revalidar:

- `ai_dictionary`, `BusinessQuerySemanticPlan`, `QueryExecutionPlanner`, `fallback_policy`, `task envelope`, `tool registry`, `unified gateway`, `agents runtime`, `approvals runtime` y `background runtime` mantienen su autoridad vigente.
- no se agregan capas arquitectonicas mayores ni se reemplaza el runtime actual.
- la prioridad de esta etapa es estabilidad, governance, trazabilidad y operacion real.

Que se modifico:

- `backend/apps/ia_dev/application/runtime/runtime_hardening_service.py`
  - policy central ligera para:
    - limites de tool loop
    - limites de tool calls por corrida
    - deteccion de loops repetidos
    - limites de retries/background duration/approval wait
    - redaccion de datos sensibles
    - correlation metadata
    - idempotency key
    - runtime metrics derivadas
- `backend/apps/ia_dev/application/runtime/approval_runtime_service.py`
  - approvals ahora persisten:
    - `expires_at`
    - `approval_role_matrix`
    - `correlation`
  - la evidencia sensible queda saneada antes de persistirse.
- `backend/apps/ia_dev/application/runtime/background_runtime_service.py`
  - cola background idempotente para la misma tool activa.
  - timeout efectivo acotado por policy runtime.
  - approval expirado bloquea resume seguro.
  - retries agotados generan `dead_letter`.
  - se agrega enforcement reutilizable de expiracion.
- `backend/apps/ia_dev/application/workflow/task_state_service.py`
  - persiste:
    - `correlation`
    - `governance`
    - `runtime_metrics`
    - `dead_letter`
  - el estado calcula metricas operativas resumidas por corrida.
- `backend/apps/ia_dev/infrastructure/ai/openai_gateway_service.py`
  - agrega correlation uniforme en metadata.
  - endurece el function tool loop con:
    - max rounds efectivos
    - max tool calls por corrida
    - bloqueo de repeated tool loops
  - sanea argumentos/evidence/output de traces nativas antes de persistirlas.
- `backend/apps/ia_dev/application/runtime/runtime_capability_adapter.py`
  - expone `correlation` e `idempotency_key` en metadata runtime.
- `backend/apps/ia_dev/application/runtime/tool_registry_service.py`
  - agrega metadata de sensibilidad y matriz de approval por tool.
- `backend/apps/ia_dev/services/runtime_governance_service.py`
  - agrega:
    - `build_runtime_operations_summary(...)`
    - `build_task_trace_explorer(...)`
  - consolida:
    - estados runtime
    - approval backlog
    - background failures
    - dead-letter
    - correlation y trace explorer saneado
- `backend/apps/ia_dev/views/chat_view.py`
  - expone endpoints operativos nuevos:
    - `GET /ia-dev/runtime/operations/summary/`
    - `GET /ia-dev/runtime/tasks/explorer/`
    - `GET /ia-dev/runtime/governance/health/`
- documentacion operativa:
  - `backend/OPERACION_RUNTIME_MULTIAGENTE.md`

Hardening y governance confirmados:

- loop agentic infinito mitigado por:
  - `IA_DEV_MAX_TOOL_LOOP_ROUNDS`
  - `IA_DEV_MAX_TOOL_CALLS_PER_RUN`
  - `IA_DEV_MAX_REPEAT_TOOL_CALLS`
- background endurecido con:
  - `IA_DEV_MAX_BACKGROUND_RETRIES`
  - `IA_DEV_MAX_BACKGROUND_DURATION_SECONDS`
  - `dead_letter`
  - `queue_run` idempotente
- approvals endurecidos con:
  - `IA_DEV_MAX_APPROVAL_WAIT_SECONDS`
  - expiracion de approval
  - role matrix persistida
- evidencia sensible saneada en approvals, traces nativas y background evidence.
- correlation y lineage operativo disponible por corrida.

Metricas operativas disponibles:

- `task_state.state.runtime_metrics`
- `task_state.state.governance`
- `task_state.state.correlation`
- `task_state.state.dead_letter`
- `task_state.state.background.retry`
- `task_state.state.approvals[*].expires_at`
- `observability` summary existente
- `RuntimeGovernanceService.build_monitor_summary(...)`
- `RuntimeGovernanceService.build_pilot_report(...)`
- `RuntimeGovernanceService.build_runtime_operations_summary(...)`
- `RuntimeGovernanceService.build_task_trace_explorer(...)`
- `GET /ia-dev/runtime/operations/summary/`
- `GET /ia-dev/runtime/tasks/explorer/`
- `GET /ia-dev/runtime/governance/health/`

Politicas y limites nuevos vigentes:

- no permitir mas tool loops repetidos identicos que el maximo configurado.
- no permitir resumes de approvals expirados.
- no permitir crecimiento indefinido de retries de background.
- no persistir evidencia sensible en claro en traces de runtime endurecido.

Riesgos/limitaciones vigentes:

- el circuit breaker distribuido e inmune a reinicios no queda implementado todavia; el endurecimiento actual cubre limites por corrida y loops repetidos en proceso.
- no se agrego endpoint nuevo de approvals ni dashboard frontend dedicado; se expusieron endpoints backend operativos y trazas saneadas para soporte.
- no se tocaron `semantic layer`, planner SQL, fallback base ni contratos de negocio.

Checklist operativo de produccion:

- verificar limites `IA_DEV_MAX_*`
- verificar observabilidad habilitada
- revisar `dead_letter` y `runtime_metrics`
- revisar approvals expirados o pendientes
- usar `runtime/operations/summary` para backlog operativo
- usar `runtime/tasks/explorer` para correlation, lineage y traces saneadas
- usar `runtime/governance/health` para health enterprise por dominio
- usar `correlation_id`, `run_id` y `trace_id` para troubleshooting
- no hacer bypass de approvals ni de planner

Que comandos/pruebas se ejecutaron:

- `python manage.py test apps.ia_dev.tests.test_task_state_service apps.ia_dev.tests.test_approval_runtime_service apps.ia_dev.tests.test_background_runtime_service apps.ia_dev.tests.test_tool_registry_service apps.ia_dev.tests.test_openai_gateway_service`
- `python manage.py test apps.ia_dev.tests.test_background_end_to_end_flows apps.ia_dev.tests.test_chat_runtime_metadata`
- `python manage.py test apps.ia_dev.tests.test_phase6_runtime_governance.Phase6GovernanceServiceTests.test_runtime_operations_summary_aggregates_task_runtime_state apps.ia_dev.tests.test_phase6_runtime_governance.Phase6GovernanceServiceTests.test_task_trace_explorer_returns_sanitized_operational_view apps.ia_dev.tests.test_regression_endpoints.IADevRegressionEndpointsTests.test_runtime_operations_summary_endpoint_returns_payload apps.ia_dev.tests.test_regression_endpoints.IADevRegressionEndpointsTests.test_runtime_task_explorer_endpoint_requires_lookup_identifier apps.ia_dev.tests.test_regression_endpoints.IADevRegressionEndpointsTests.test_runtime_task_explorer_endpoint_returns_not_found_when_missing apps.ia_dev.tests.test_regression_endpoints.IADevRegressionEndpointsTests.test_runtime_governance_health_endpoint_returns_monitor_and_pilot_health`

Resultado:

- `55 tests`: OK
- `6 tests` focalizados de operacion/governance: OK

Estado vigente para futuros chats:

- Fase 1 -> Task Envelope ✅
- Fase 2 -> Tool Registry ✅
- Fase 3 -> Unified OpenAI Gateway ✅
- Fase 4 -> Responses API tools ✅
- Fase 5 -> Agents SDK Orchestration ✅
- Fase 6 -> Handoffs + approvals ✅
- Fase 7 -> Background runs ✅
- etapa nueva activa:
  - endurecimiento operativo del runtime
  - governance reforzado
  - observabilidad y trazabilidad ampliadas
  - limites enterprise basicos ya persistidos
  - explorer operativo de tareas y trazas saneadas disponible por API

## Sesion 2026-05-16: Fase 7 Background Runs + validacion end-to-end

Que se asumio sin revalidar:

- `ai_dictionary` sigue siendo autoridad estructural.
- `BusinessQuerySemanticPlan` no cambia.
- `QueryExecutionPlanner` sigue siendo autoridad unica de SQL seguro.
- `fallback_policy`, semantic layer, SQL authority, tool registry base, gateway base, agents runtime base y approvals base no se reemplazan.
- `ChatApplicationService` sigue siendo el orquestador principal.

Que se modifico:

- nuevos contratos runtime:
  - `backend/apps/ia_dev/application/contracts/background_run_contracts.py`
  - soporta:
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
- nuevos servicios:
  - `backend/apps/ia_dev/application/runtime/background_runtime_service.py`
  - `backend/apps/ia_dev/application/runtime/checkpoint_service.py`
- `backend/apps/ia_dev/application/workflow/task_state_service.py`
  - nuevos estados soportados:
    - `queued`
    - `running`
    - `paused`
    - `resumed`
    - `cancelled`
    - `expired`
  - persiste:
    - `background`
    - `background_trace`
    - `checkpoints`
  - agrega helpers:
    - `update_state(...)`
    - `find_by_resume_token(...)`
    - `find_by_background_run_id(...)`
- `backend/apps/ia_dev/application/runtime/runtime_capability_adapter.py`
  - si una tool entra por policy de background:
    - no rompe el flujo sync existente
    - puede devolver `background_pending`
    - deja metadata para polling
  - si una tool requiere approval:
    - deja `awaiting_approval`
    - siembra `resume_token`
    - sincroniza background state con approval state
- `backend/apps/ia_dev/application/orchestration/chat_application_service.py`
  - ahora expone:
    - `task.current_run.background`
    - `data_sources.runtime.background`
    - `data_sources.runtime.background_trace`
    - `data_sources.runtime.checkpoints`
  - agrega helpers:
    - `poll_background_run(...)`
    - `resume_background_run(...)`
    - `cancel_background_run(...)`
  - mantiene compatibilidad con:
    - `reply` top-level
    - `task.current_run.reply`
    - dashboard y payload actual
- `backend/apps/ia_dev/application/contracts/chat_contracts.py`
  - `task.current_run` ahora soporta `background` sin romper el contrato actual.
- `backend/apps/ia_dev/application/runtime/tool_registry_service.py`
  - si una capability declara `policy_tags` como `supports_background` o `long_running`, la tool queda marcada con `supports_background=True`.

Estados runtime/background vigentes:

- `queued`
- `running`
- `awaiting_approval`
- `paused`
- `resumed`
- `completed`
- `failed`
- `cancelled`
- `expired`

Eventos de observabilidad ya soportados por esta fase:

- `background_run_queued`
- `background_run_started`
- `background_run_checkpoint`
- `background_run_awaiting_approval`
- `background_run_resumed`
- `background_run_completed`
- `background_run_failed`
- `background_run_cancelled`

Persistencia/tracing oficial desde esta fase:

- `task.current_run.background`
- `task.current_run.status`
- `task.current_run.evidence`
- `task_state.state.background`
- `task_state.state.background_trace`
- `task_state.state.checkpoints`
- `data_sources.runtime.background`
- `data_sources.runtime.background_trace`
- `data_sources.runtime.checkpoints`
- las trazas de:
  - `agent_trace`
  - `tool_execution_trace`
  - `approval_trace`
  - `handoff_trace`
  ya no se pierden al reanudar o cancelar.

Poll / resume / cancel oficial de esta fase:

- polling por:
  - `run_id`
  - `background_run_id`
  - `resume_token`
- resume gobernado por:
  - approval previa
  - `resume_token`
  - evidencia antes y despues de approval
- cancelacion:
  - deja `cancelled`
  - conserva evidencia parcial y trazas previas

Que quedo validado:

- Caso A: consulta normal sync mantiene `task envelope`, `tool registry`, gateway y respuesta compatible.
- Caso B: native tool call conserva `tool_execution_trace`.
- Caso C: multiagent handoff conserva `agent_trace` y `handoff_trace`.
- Caso D: approval required deja `awaiting_approval`, `approval_request` y `resume_token`.
- Caso E: resume after approval conserva trazas previas y posteriores y puede cerrar `completed`.
- Caso F: background long run deja `queued`, polling, checkpoints y completion controlada.
- Caso G: cancel/failure no pierden evidencia ni trazas previas.

Que comandos/pruebas se ejecutaron:

- `python manage.py test apps.ia_dev.tests.test_background_runtime_service apps.ia_dev.tests.test_background_end_to_end_flows apps.ia_dev.tests.test_task_state_service apps.ia_dev.tests.test_runtime_capability_adapter apps.ia_dev.tests.test_chat_response_contracts apps.ia_dev.tests.test_chat_runtime_metadata apps.ia_dev.tests.test_tool_registry_service apps.ia_dev.tests.test_openai_gateway_service`
- `python manage.py test apps.ia_dev.tests.test_approval_runtime_service apps.ia_dev.tests.test_agents_runtime_service`

Resultado:

- `56 tests`: OK

Limitaciones actuales:

- esta fase deja contratos, persistencia, polling, checkpoints, cancelacion y resume gobernado, pero todavia no publica endpoint productivo dedicado para polling/cancel/resume externo.
- no se implemento un worker productivo ni cola distribuida; la fase gobierna estado y duracion dentro del runtime actual.
- no se habilitaron escrituras autonomas destructivas.
- background no cambia autoridad:
  - `QueryExecutionPlanner` sigue mandando en SQL seguro
  - `ai_dictionary` sigue mandando en estructura
  - approvals siguen gobernando acciones sensibles
- el resume productivo hoy queda listo por contrato y servicio; la reanudacion automatica por infraestructura externa queda para una fase posterior.

Estado vigente para futuros chats:

- Fase 1 -> Task Envelope ✅
- Fase 2 -> Tool Registry ✅
- Fase 3 -> Unified OpenAI Gateway ✅
- Fase 4 -> Responses API tools ✅
- Fase 5 -> Agents SDK Orchestration ✅
- Fase 6 -> Handoffs + approvals ✅
- Fase 7 -> Background runs ✅

## Sesion 2026-05-16: Fase 6 Handoffs + approvals

Que se asumio sin revalidar:

- `ai_dictionary` sigue siendo autoridad estructural.
- `BusinessQuerySemanticPlan` no cambia.
- `QueryExecutionPlanner` sigue siendo autoridad unica de SQL seguro.
- `fallback_policy`, frontend, semantic layer, task envelope, tool registry, gateway unificado y runtime deterministico no se reemplazan.
- esta fase agrega gobierno de handoffs y approvals sobre el runtime actual; no habilita background runs productivos, escrituras autonomas ni bypass de validadores.

Que se modifico:

- nuevos contratos:
  - `backend/apps/ia_dev/application/contracts/runtime_governance_contracts.py`
  - contratos para:
    - `approval_request_id`
    - `approval_type`
    - `requested_by_agent`
    - `target_tool`
    - `target_action`
    - `risk_level`
    - `reason`
    - `required_role`
    - `approval_status`
    - `approved_by`
    - `approved_at`
    - `rejected_reason`
    - `resume_token`
    - `evidence_before_approval`
    - `evidence_after_approval`
- `backend/apps/ia_dev/application/contracts/tool_contracts.py`
  - `approval_policy` ahora expone:
    - `approval_type`
    - `required_role`
    - `risk_level`
- nuevos servicios:
  - `backend/apps/ia_dev/application/runtime/approval_runtime_service.py`
  - `backend/apps/ia_dev/application/runtime/handoff_trace_service.py`
- `backend/apps/ia_dev/application/runtime/tool_registry_service.py`
  - las tools read-only y `query_execution_planner.sql_assisted` quedan auto-aprobadas.
  - las capabilities con `policy_tag requires_approval` publican policy manual con:
    - `approval_type: human_review`
    - `required_role: governance`
    - `risk_level: high`
- `backend/apps/ia_dev/application/runtime/runtime_capability_adapter.py`
  - bloquea ejecucion de tools sensibles sin approval.
  - crea `approval_request` + `resume_token`.
  - persiste en `run_context.metadata.approval_runtime`:
    - `approvals`
    - `approval_trace`
    - `status`
  - emite evento `runtime_approval_requested`.
- `backend/apps/ia_dev/application/agents/agents_runtime_service.py`
  - los handoffs ahora se registran como handoff gobernado con `handoff_id`, `target_tool`, evidencia y traza dedicada.
  - expone:
    - `handoffs`
    - `handoff_trace`
  - emite evento `agents_runtime_handoff_trace_recorded`.
- `backend/apps/ia_dev/application/orchestration/chat_application_service.py`
  - si una tool requiere approval y aun no existe:
    - no ejecuta la accion
    - responde evidencia previa
    - deja la tarea en `awaiting_approval`
  - persiste y publica:
    - `task.current_run.approvals`
    - `task.current_run.handoffs`
    - `task.current_run.status`
    - `task_state.state.approvals`
    - `task_state.state.approval_trace`
    - `task_state.state.handoffs`
    - `task_state.state.handoff_trace`
    - `data_sources.runtime.approvals`
    - `data_sources.runtime.approval_trace`
    - `data_sources.runtime.handoff_trace`
- `backend/apps/ia_dev/application/workflow/task_state_service.py`
  - nuevos estados soportados:
    - `planned`
    - `executing`
    - `awaiting_approval`
    - `approved`
    - `rejected`
    - `blocked`
    - `completed`
    - `failed`
  - mantiene compatibilidad con estados previos ya persistidos.
- `backend/apps/ia_dev/application/contracts/chat_contracts.py`
  - `task.current_run` ahora soporta `approvals` sin romper `reply` top-level ni dashboard actual.

Politicas iniciales ya activas:

1. read-only seguro:
   - no requiere approval
2. SQL seguro validado por `QueryExecutionPlanner`:
   - no requiere approval
3. tools con `requires_approval`:
   - no ejecutan sin approval
   - dejan `awaiting_approval`
   - devuelven evidencia previa y `resume_token`
4. tools destructivas:
   - no se habilitaron todavia

Persistencia/tracing vigente desde esta fase:

- `task.current_run.approvals`
- `task.current_run.handoffs`
- `task.current_run.status`
- `task_state.state.approval_trace`
- `task_state.state.handoff_trace`
- eventos:
  - `runtime_approval_requested`
  - `agents_runtime_handoff`
  - `agents_runtime_handoff_trace_recorded`

Que quedo validado:

- Fase 6 agrega gobierno sobre el runtime actual y no reemplaza `QueryExecutionPlanner`, `ai_dictionary`, `Tool Registry`, `OpenAI Gateway` ni `Agents Runtime`.
- los handoffs manager -> specialist ya dejan `handoff_id`, `target_tool`, evidencia y traza persistible.
- las tools sensibles ya no pueden ejecutarse sin approval del runtime.
- la pausa/reanudacion queda preparada via `resume_token`.
- `reply` top-level, `task envelope`, dashboard y runtime deterministico siguen compatibles.

Que comandos/pruebas se ejecutaron:

- `python manage.py test apps.ia_dev.tests.test_approval_policy_service apps.ia_dev.tests.test_approval_runtime_service apps.ia_dev.tests.test_runtime_capability_adapter apps.ia_dev.tests.test_agents_runtime_service apps.ia_dev.tests.test_task_state_service apps.ia_dev.tests.test_chat_response_contracts apps.ia_dev.tests.test_chat_runtime_metadata`
- `python manage.py test apps.ia_dev.tests.test_tool_registry_service`

Resultado:

- `39 tests`: OK

Limitaciones actuales:

- esta fase deja contratos y runtime para pause/resume y human-in-the-loop, pero no publica todavia un endpoint productivo de aprobacion/reanudacion externa.
- no se habilitaron escrituras autonomas, background runs productivos ni tools destructivas.
- el approval actual se activa por policy declarativa de tool; no mueve autoridad de negocio al modelo.

Estado vigente para futuros chats:

- Fase 1 -> Task Envelope ✅
- Fase 2 -> Tool Registry ✅
- Fase 3 -> Unified OpenAI Gateway ✅
- Fase 4 -> Responses API tools ✅
- Fase 5 -> Agents SDK Orchestration ✅
- Fase 6 -> Handoffs + approvals ✅
- Fase 7 -> Background runs

## Sesion 2026-05-16: Fase 5 Agents SDK Orchestration Layer

Que se asumio sin revalidar:

- `ai_dictionary` sigue siendo autoridad estructural.
- `BusinessQuerySemanticPlan` no cambia.
- `QueryExecutionPlanner` sigue siendo autoridad unica de SQL seguro.
- `fallback_policy`, task envelope, frontend, semantic layer, runtime SQL authority y tool registry vigente no se reemplazan.
- `ChatApplicationService` sigue siendo el orquestador principal y esta fase solo lo envuelve con coordinacion multiagente.

Que se modifico:

- nueva capa `backend/apps/ia_dev/application/agents/`
  - `agents_runtime_service.py`
  - `agents_registry.py`
  - `manager_agent.py`
  - `specialists/`
    - `inventory_agent.py`
    - `empleados_agent.py`
    - `ausentismo_agent.py`
    - `semantic_resolution_agent.py`
- `backend/apps/ia_dev/application/orchestration/chat_application_service.py`
  - integra la capa de agents despues de `semantic_orchestrator`.
  - persiste `agents`, `handoffs`, `agent_trace` y bootstrap en `task_state`.
  - publica metadata de agentes en `task.current_run` y `data_sources.runtime`.
- `backend/apps/ia_dev/application/contracts/chat_contracts.py`
  - `task.current_run` ahora soporta:
    - `agents`
    - `handoffs`
- `backend/apps/ia_dev/application/workflow/task_state_service.py`
  - persiste:
    - `agents`
    - `handoffs`
    - `agent_trace`
    - `agents_runtime_bootstrap`
  - agrega a `history`:
    - `agent_count`
    - `handoff_count`
- `backend/apps/ia_dev/application/runtime/service_runtime_bootstrap.py`
  - nuevo flag default:
    - `IA_DEV_AGENTS_RUNTIME_ENABLED=1`

Agentes creados:

- `manager_agent`
- `inventory_agent`
- `empleados_agent`
- `ausentismo_agent`
- `semantic_resolution_agent`

Routing implementado:

- el manager agent usa la salida ya gobernada de:
  - `intent_arbitration`
  - `semantic_orchestrator`
  - `candidate_domain`
  - `candidate_intent`
  - `candidate_capability`
- delega especialistas como `agents-as-tools` via registry:
  - `agent.delegate.inventory_agent`
  - `agent.delegate.empleados_agent`
  - `agent.delegate.ausentismo_agent`
  - `agent.delegate.semantic_resolution_agent`
- no hay hardcode por frases completas; la seleccion usa dominio/intencion/capability ya resueltos por el runtime.

Tracing agregado:

- persistencia en `task_state.state`:
  - `agents`
  - `handoffs`
  - `agent_trace`
  - `agents_runtime_bootstrap`
- exposicion en respuesta:
  - `task.current_run.agents`
  - `task.current_run.handoffs`
  - `data_sources.runtime.agents`
  - `data_sources.runtime.handoffs`
  - `data_sources.runtime.agent_trace`
- eventos nuevos:
  - `agents_runtime_manager_selected`
  - `agents_runtime_handoff`
  - `agents_runtime_specialist_completed`
  - `agents_runtime_resolved`

Metadata nueva:

- `task.current_run.evidence.agent_count`
- `task.current_run.evidence.handoff_count`
- `task.current_run.final_state.agents_sdk`
- `task_state.state.history[*].agent_count`
- `task_state.state.history[*].handoff_count`

Handoffs soportados:

- handoff manager -> specialist auditado
- origen y destino persistidos como:
  - `handoff_origin`
  - `handoff_target`
- esta fase deja la estructura lista para approvals futuras, pero no activa aprobaciones humanas completas.

Que quedo validado:

- `Agents SDK` queda integrado como capa oficial de coordinacion sobre el runtime actual.
- el bootstrap detecta si existe SDK nativo; si no, usa implementacion segura sobre `OpenAIGatewayService` + function tool loop.
- el manager coordina y delega; los especialistas no reemplazan planners, handlers ni validadores.
- `reply` top-level, `task envelope`, planner trace, tool trace, semantic trace y dashboard actual siguen compatibles.
- la autoridad de SQL sigue fuera del modelo.

Limitaciones actuales:

- el entorno actual no trae instalado el paquete oficial del Agents SDK; la capa corre en modo compatible `gateway_function_loop`.
- los especialistas actuales coordinan y recomiendan tools declarativas; no introducen escrituras autonomas, background runs productivos ni approvals humanas.
- no se habilitaron tools destructivas ni bypass de validadores.
- no se reemplazo `ChatApplicationService`.

Que comandos/pruebas se ejecutaron:

- `python manage.py test apps.ia_dev.tests.test_agents_runtime_service apps.ia_dev.tests.test_chat_response_contracts apps.ia_dev.tests.test_task_state_service apps.ia_dev.tests.test_chat_runtime_metadata apps.ia_dev.tests.test_openai_gateway_service apps.ia_dev.tests.test_tool_registry_service apps.ia_dev.tests.test_semantic_orchestrator_service`

Resultado:

- `48 tests`: OK

Estado vigente para futuros chats:

- Fase 1 `Task Envelope` vigente.
- Fase 2 `Tool Registry` vigente.
- Fase 3 `Unified OpenAI Gateway` vigente.
- Fase 4 `Responses API tools` vigente.
- Fase 5 `Agents SDK` ya existe como capa de coordinacion multiagente sobre el runtime actual.
- el manager agent no es autoridad de negocio ni de SQL.
- `QueryExecutionPlanner`, `ai_dictionary`, validadores y runtime deterministico siguen mandando.
- la siguiente fase debe profundizar approvals/handoffs/background sin rehacer esta base.

## Hoja de ruta vigente final

- Fase 1 -> Task Envelope ✅
- Fase 2 -> Tool Registry ✅
- Fase 3 -> Unified OpenAI Gateway ✅
- Fase 4 -> Responses API tools ✅
- Fase 5 -> Agents SDK ✅
- Fase 6 -> Handoffs + approvals
- Fase 7 -> Background runs

## Sesion 2026-05-16: Diagnostico focalizado pattern-first vs metadata-first

Que se asumio sin revalidar:

- `ai_dictionary` sigue siendo autoridad estructural.
- `BusinessQuerySemanticPlan` sigue siendo la capa oficial previa al planner.
- `QueryExecutionPlanner` sigue siendo autoridad unica de SQL seguro.
- `Tool Registry`, `Agents Runtime`, approvals, background y `fallback_policy` no se reauditan en esta tarea.

Hallazgos utiles para continuidad:

- La autoridad de ejecucion sigue bien gobernada en:
  - `semantic_business_resolver`
  - `tool_registry_service`
  - `query_execution_planner`
- Persisten rutas transicionales `pattern-first` en:
  - `semantic_inventory_resolver`
  - `query_intent_resolver`
  - `semantic_orchestrator_service`
  - `chat_application_service`
- Existen `fastpaths` y `pre-router` por patrones que hoy aceleran el runtime, pero todavia dependen de tokens, regex y frases de inventario.
- `response_assembler` conserva heuristicas por texto de respuesta como:
  - `empleados activos`
  - `proximos a vencer`
  - `rotacion`
  Eso debe migrar gradualmente a metadata estructurada de resultado y no a texto renderizado.
- `runtime_capability_adapter` aun resuelve capacidades base por dominio/intencion/template hardcodeados para empleados y ausentismo; es tolerable como puente, pero no es el objetivo final `metadata/capability-first`.
- Los `query_patterns`, examples y `deterministic_patterns` siguen siendo aceleradores utiles de transicion, pero no deben convertirse en autoridad semantica ni saltarse validacion por metadata/capabilities.

Prioridad de refactor confirmada:

1. mover familias, sinonimia y reglas de inventario desde regex Python hacia `dd_sinonimos`, `dd_reglas` e `ia_dev_capacidades_columna`
2. hacer que `query_pattern_fastpath` y `inventory_pre_router` solo propongan candidatos, nunca decisiones finales no revalidadas
3. reemplazar heuristicas de `response_assembler` basadas en texto por señales estructuradas en `result_set`, `kpis`, `semantic_trace` o `execution metadata`
4. reducir mapeos hardcodeados de capability en adapters cuando ya exista metadata suficiente en dictionary/catalog

Regla de continuidad nueva:

- Si aparece un nuevo fastpath, pattern o example:
  - puede sugerir dominio, intent o capability
  - no puede ser autoridad final
  - debe revalidarse contra `ai_dictionary`, `dd_*`, capacidades, planner y policy antes de ejecutar o cerrar respuesta

## Sesion 2026-05-16: P1 metadata/capability-first en inventario

Que se asumio sin revalidar:

- `QueryExecutionPlanner` sigue siendo la unica autoridad de SQL seguro.
- No se toca `fallback_policy`, approvals, background, agents runtime ni contratos HTTP del frontend.
- La regla de nomenclatura empresarial en espanol ya existe y sigue gobernada por `backend/REGLA_NOMENCLATURA_EMPRESA.md`.

Que quedo implementado:

- `inventario_logistica` ahora tiene un matcher semantico gobernado para familias P1 de inventario por portador:
  - cuadrilla/movil/brigada
  - tecnico/empleado/cedula
  - kardex/movimientos/entradas y salidas
  - material claro / material de claro
  - ferretero / ferreteria
  - actas SAP como limitacion declarada
- El orden operativo queda:
  1. pregunta
  2. matcher gobernado
  3. dominio/intencion/campos/filtros/capability candidata
  4. `BusinessQuerySemanticPlan`
  5. planner SQL seguro
- Los regex y fastpaths heredados quedan solo como fallback sombreado cuando no haya coincidencia gobernada para esa familia.
- `response_assembler` ya no infiere principalmente desde texto de la pregunta el alcance `material claro` vs `ferretero` ni el enfoque por cuadrilla; ahora prioriza `business_query_semantic_plan` y `semantic_context`.

Reglas semanticas P1 persistidas:

- `material claro` y `material de claro` => `tipo = material`
- `ferretero` y `ferreteria` => `tipo = ferretero`
- `cuadrilla`, `movil`, `brigada` => sinonimia gobernada de `movil`
- `kardex`, `movimientos`, `entradas y salidas` => familia de `movement_history`
- identificador numerico => `cedula`
- identificador alfanumerico operativo => `movil`
- inventario generico por `movil/cuadrilla` => doble bloque cuando aplique
- serializados => conteo, no cantidad
- saldo de inventario => incluir positivos, cero y negativos
- `actas SAP` del empleado/tecnico => limitacion declarada, no dato inventado

Pruebas focalizadas validadas:

- `que tiene asignado la cuadrilla TIRAN224`
- `muestrame lo que tiene el movil TIRAN224`
- `movimientos del tecnico 5098747`
- `entradas y salidas de 5098747`
- `solo material de claro de TIRAN224`
- `ferreteria asignada al tecnico 5098747`
- `que tiene Juan Perez` => aclaracion requerida
- `actas SAP del empleado 5098747` => limitacion declarada

Contrato frontend revalidado:

- `reply`
- `task`
- `data`
- `evidence`
- `status`

No se rompio compatibilidad contractual en las pruebas del chat runtime.

## Sesion 2026-05-16: Fase 4 Responses API Native Tools

Que se asumio sin revalidar:

- `ai_dictionary` sigue siendo autoridad estructural.
- `BusinessQuerySemanticPlan` no cambia.
- `QueryExecutionPlanner` sigue siendo autoridad unica de SQL seguro.
- `fallback_policy`, `task envelope`, frontend y semantic layer funcional no se reemplazan.
- esta fase agrega native tools sobre el runtime actual; no introduce `Agents SDK`, handoffs ni background runs operativos.

Que se modifico:

- `backend/apps/ia_dev/application/contracts/tool_contracts.py`
  - la traza de tool ahora soporta metadata nativa de `Responses API`:
    - `tool_call_id`
    - `tool_name`
    - `arguments`
    - `execution_status`
    - `validation_status`
    - `evidence_metadata`
    - `model_response_id`
    - `loop_iteration`
- `backend/apps/ia_dev/application/runtime/tool_registry_service.py`
  - el registry ahora convierte tools declarativas a schema nativo OpenAI `tools=[]`.
  - agrega tools seguras iniciales para reasoning semantico:
    - `semantic_orchestrator.dictionary_summary.v1`
    - `semantic_orchestrator.domain_context_summary.v1`
    - `semantic_orchestrator.memory_context.v1`
    - `semantic_orchestrator.deterministic_baseline.v1`
    - `semantic_orchestrator.route_debug_hints.v1`
  - mantiene `query_execution_planner.sql_assisted` como tool declarativa interna del runtime.
- `backend/apps/ia_dev/infrastructure/ai/openai_gateway_contracts.py`
  - el gateway ahora expone `output_items`, `function_calls` y resultado tipado del tool loop.
- `backend/apps/ia_dev/infrastructure/ai/openai_gateway_service.py`
  - implementa loop nativo:
    - `response`
    - `function_call`
    - ejecucion runtime
    - `function_call_output`
    - continuacion de reasoning
  - extrae `response.output` y normaliza function calls sin mover logica de negocio al modelo.
- `backend/apps/ia_dev/application/runtime/runtime_capability_adapter.py`
  - agrega `execute_registered_tool(...)` para enrutar tools declarativas hacia handlers o planner delegado, manteniendo aprobaciones y autoridad runtime.
- `backend/apps/ia_dev/application/semantic/semantic_orchestrator_service.py`
  - usa native tools del gateway en la fase de reasoning semantico.
  - el modelo solo puede pedir contexto gobernado ya preparado; no ejecuta SQL libre.
  - persiste en `run_context.metadata`:
    - `response_native_tool_trace`
    - `response_native_tool_loop`
- `backend/apps/ia_dev/application/orchestration/chat_application_service.py`
  - fusiona traza nativa de Responses API con la traza runtime ya existente.
  - persiste en `task_state` y publica en:
    - `task.current_run.tool_execution`
    - `task_state.tool_execution_trace`
    - `data_sources.runtime.tool_execution`
- tests actualizados:
  - `backend/apps/ia_dev/tests/test_openai_gateway_service.py`
  - `backend/apps/ia_dev/tests/test_tool_registry_service.py`
  - `backend/apps/ia_dev/tests/test_semantic_orchestrator_service.py`
  - `backend/apps/ia_dev/tests/test_chat_runtime_metadata.py`

Tools expuestas en esta fase:

- tools semanticas de contexto gobernado:
  - `semantic_orchestrator.dictionary_summary.v1`
  - `semantic_orchestrator.domain_context_summary.v1`
  - `semantic_orchestrator.memory_context.v1`
  - `semantic_orchestrator.deterministic_baseline.v1`
  - `semantic_orchestrator.route_debug_hints.v1`
- tools declarativas de runtime ya convertibles a schema nativo:
  - handlers seguros auto-aprobados del registry
  - `query_execution_planner.sql_assisted` como tool declarativa interna

Runtime loop implementado:

1. el gateway invoca `Responses API` con `tools` y `tool_choice`
2. si el modelo devuelve `function_call`, el runtime ejecuta la tool declarativa permitida
3. el runtime devuelve `function_call_output` estructurado
4. el gateway reanuda reasoning hasta obtener respuesta final o mas tool calls
5. la traza nativa se fusiona con la traza runtime y se persiste en `task_state`

Metadata nueva persistida:

- `task.current_run.tool_execution.native_tool_calls_count`
- `task.current_run.tool_execution.response_tool_loop`
- `task_state.state.tool_execution_trace[*].tool_call_id`
- `task_state.state.tool_execution_trace[*].tool_name`
- `task_state.state.tool_execution_trace[*].arguments`
- `task_state.state.tool_execution_trace[*].execution_status`
- `task_state.state.tool_execution_trace[*].validation_status`
- `task_state.state.tool_execution_trace[*].evidence_metadata`
- `task_state.state.tool_execution_trace[*].model_response_id`
- `task_state.state.tool_execution_trace[*].loop_iteration`

Observabilidad nueva:

- evento `response_native_tool_executed`

Que quedo validado:

- el gateway soporta `tools=[]`, `tool_choice`, parseo de `function_call` y continuidad con `function_call_output`.
- la autoridad de SQL sigue fuera del modelo.
- ninguna tool nativa salta validadores existentes.
- `reply` top-level y `task.current_run.reply` siguen compatibles.
- la traza nativa convive con el runtime deterministico actual y no lo reemplaza.

Que comandos/pruebas se ejecutaron:

- `python manage.py test apps.ia_dev.tests.test_openai_gateway_service apps.ia_dev.tests.test_tool_registry_service apps.ia_dev.tests.test_semantic_orchestrator_service apps.ia_dev.tests.test_chat_runtime_metadata apps.ia_dev.tests.test_task_state_service`
- `python manage.py test apps.ia_dev.tests.test_chat_response_contracts`

Resultado:

- `44 tests`: OK

Limitaciones actuales:

- el uso activo de native tools queda habilitado primero en `semantic_orchestrator_service` con tools seguras de contexto.
- `query_execution_planner.sql_assisted` ya es convertible a schema nativo, pero no se entrego ejecucion autonoma libre al modelo.
- no hay `Agents SDK`, handoffs, approvals humanas ni background runs en esta fase.
- el modelo sigue sin poder:
  - ejecutar SQL arbitrario
  - modificar `ai_dictionary`
  - escribir memoria gobernada
  - relajar validadores

Estado vigente para futuros chats:

- Fase 1 `Task Envelope` vigente.
- Fase 2 `Tool Registry` vigente.
- Fase 3 `Unified OpenAI Gateway` vigente.
- Fase 4 `Responses API Native Tools` ya existe sobre el runtime actual.
- la traza oficial de tools ahora puede mezclar:
  - tool calls nativas de Responses API
  - tool execution runtime final
- la siguiente fase debe construir `Agents SDK` sobre esta base, no reemplazarla.

## Sesion 2026-05-16: Fase 3 Unified OpenAI Gateway

Que se asumio sin revalidar:

- `ai_dictionary` sigue siendo autoridad estructural y no se modifica.
- `BusinessQuerySemanticPlan` sigue siendo la salida oficial de la capa semantica.
- `QueryExecutionPlanner` sigue siendo autoridad unica de SQL seguro.
- `fallback_policy`, task envelope y tool registry no se tocan funcionalmente.
- no se introduce `Agents SDK`, native tools ni cambios de frontend en esta fase.

Que se modifico:

- `backend/apps/ia_dev/infrastructure/ai/openai_gateway_contracts.py`
  - nuevo contrato tipado para request/response/error del gateway.
- `backend/apps/ia_dev/infrastructure/ai/model_policy.py`
  - nueva policy central para seleccion de modelo por route o modelo explicito.
- `backend/apps/ia_dev/infrastructure/ai/openai_gateway_service.py`
  - nuevo gateway unico para `Responses API`.
  - centraliza:
    - seleccion de modelo
    - api key
    - timeout
    - retries
    - metadata uniforme
    - trace metadata
    - logging comun
    - normalizacion de errores
    - passthrough preparado para `reasoning`, `text`, `store`, `background`, `previous_response_id`, `tools` y `tool_choice`
- servicios migrados desde llamadas directas a `client.responses.create(...)`:
  - `backend/apps/ia_dev/application/semantic/query_intent_resolver.py`
  - `backend/apps/ia_dev/application/semantic/semantic_orchestrator_service.py`
  - `backend/apps/ia_dev/application/semantic/semantic_normalization_service.py`
  - `backend/apps/ia_dev/application/semantic/satisfaction_review_gate.py`
  - `backend/apps/ia_dev/application/semantic/cause_diagnostics_service.py`
  - `backend/apps/ia_dev/services/attendance_period_resolver_service.py`
  - `backend/apps/ia_dev/services/intent_service.py`
  - `backend/apps/ia_dev/services/intent_arbitration_service.py`
  - `backend/apps/ia_dev/services/orchestrator_legacy_runtime.py`
- `backend/apps/ia_dev/tests/test_openai_gateway_service.py`
  - nueva cobertura focalizada del gateway.

Que quedo validado:

- no quedan llamadas directas a `client.responses.create(...)` fuera del gateway.
- el comportamiento funcional de fallback/rules/heuristics se conserva en los servicios.
- la metadata uniforme del gateway ya expone:
  - `component`
  - `model`
  - `model_source`
  - `response_id`
  - `timeout_seconds`
  - `retries`
  - `trace_metadata`
  - `request_metadata`
  - `usage`
- el gateway ya normaliza errores a codigos estables como:
  - `missing_api_key`
  - `timeout`
  - `rate_limit`
  - `authentication_error`
  - `api_error`
  - `openai_request_error`
- no se movio logica de negocio al gateway.
- no se altero SQL ni se introdujo control de tools nativas aun.
- servicios pendientes de migrar al gateway: ninguno de los que hoy usaban `Responses API` directo.

Que comandos/pruebas se ejecutaron:

- `python manage.py test apps.ia_dev.tests.test_openai_gateway_service apps.ia_dev.tests.test_intent_service apps.ia_dev.tests.test_intent_arbitration_service apps.ia_dev.tests.test_cause_diagnostics_service apps.ia_dev.tests.test_satisfaction_review_gate apps.ia_dev.tests.test_semantic_orchestrator_service apps.ia_dev.tests.test_semantic_normalization_service apps.ia_dev.tests.test_query_intelligence_layer`
- `python manage.py test apps.ia_dev.tests.test_openai_gateway_service apps.ia_dev.tests.test_intent_arbitration_service apps.ia_dev.tests.test_cause_diagnostics_service apps.ia_dev.tests.test_satisfaction_review_gate apps.ia_dev.tests.test_semantic_orchestrator_service apps.ia_dev.tests.test_semantic_normalization_service apps.ia_dev.tests.test_query_intelligence_layer apps.ia_dev.tests.test_chat_runtime_metadata`

Resultado:

- `129 tests`: OK
- `test_intent_service` mantiene una expectativa heredada `employee_query` que no coincide con el runtime vigente `empleados_query`; no se forzo ese cambio porque afectaria el contrato semantico actual y no pertenece a esta fase.

Estado vigente para futuros chats:

- Fase 1 `Task Envelope` sigue vigente y estable.
- Fase 2 `Tool Registry` sigue vigente y estable.
- Fase 3 `Unified OpenAI Gateway` ya existe y es la unica superficie interna para `Responses API`.
- los servicios siguen decidiendo negocio localmente; el gateway solo estandariza invocacion OpenAI.
- el runtime ya queda listo para Fase 4 sin tener que volver a dispersar configuracion de modelo/timeout/retries/metadata.

## Hoja de ruta vigente actualizada

- Fase 1 -> Task Envelope ✅
- Fase 2 -> Tool Registry ✅
- Fase 3 -> Unified OpenAI Gateway ✅
- Fase 4 -> Responses API tools
- Fase 5 -> Agents SDK
- Fase 6 -> Handoffs + approvals
- Fase 7 -> Background runs
