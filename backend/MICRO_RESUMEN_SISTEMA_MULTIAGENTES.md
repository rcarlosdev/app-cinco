Micro resumen actualizado

No reauditar arquitectura ni contratos. No tocar `fallback_policy`. No reabrir discovery del dominio. Continuar desde el estado actual de `inventario_logistica`.

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
