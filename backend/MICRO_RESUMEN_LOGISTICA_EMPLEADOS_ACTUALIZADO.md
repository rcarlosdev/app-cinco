Micro resumen actualizado

No reauditar arquitectura ni contratos. No tocar `fallback_policy`. No reabrir discovery del dominio. Continuar desde el estado actual de `inventario_logistica`.

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
- Las consultas explicitamente materiales siguen devolviendo solo materiales.
- Las consultas explicitamente seriales/equipos/CPE seguiran usando su ruta serializada dedicada.

Regla obligatoria persistida

Si el usuario consulta `inventario`, `saldo`, `inventario por cuadrilla`, `inventario de movil`, `inventario del tecnico` o equivalentes sin especificar `materiales`, `ferretero`, `seriales`, `equipos` o `CPE`, responder con ambos bloques cuando aplique:

1. Materiales/Ferretero
2. Serializados/Equipos/CPE

Bloque A obligatorio: materiales/ferretero

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
HAVING saldo <> 0
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
HAVING saldo <> 0
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
