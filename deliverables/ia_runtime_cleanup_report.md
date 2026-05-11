# Reporte De Limpieza Segura

## Estado Actual

- Gate estructural/runtime confirmado en verde para `ausentismo + empleados`:
  - `missing_columns=0`
  - `missing_metrics=0`
  - `missing_relations=0`
  - `missing_synonyms=0`
  - `missing_rules=0`
  - `yaml_structural_leaks=0`
  - `ia_runtime_diagnose --domain ausentismo --with-empleados --real-data`:
    - `passed=10`
    - `failed=0`
    - `legacy_count=0`
    - `errores_sql=0`

## Encapsulacion Legacy Analytics

- Phase 7 real aplicada:
  - El router de analytics ahora deja decision explicita en metadata:
    - `analytics_router_decision=join_aware_sql`
    - `analytics_router_decision=handler_modern`
    - `analytics_router_decision=runtime_only_fallback`
    - `analytics_router_decision=legacy` solo fuera del analytics cubierto o no migrado
  - `legacy_analytics_isolated=true` queda marcado para analytics cubierto y handlers modernos de `empleados`.
  - Cuando `IA_DEV_DISABLE_LEGACY_ANALYTICS_FALLBACK=1`, analytics cubierto de `ausentismo + empleados` ya no puede caer a:
    - `tool_ausentismo_service`
    - `run_legacy`
  - Si join-aware SQL falla en compilacion, ejecucion o validacion, la respuesta queda en `runtime_only_fallback` con razon gobernada.

## Compatibilidad Conservada

- Sigue vivo:
  - `backend/apps/ia_dev/services/orchestrator_service.py`
  - `backend/apps/ia_dev/services/orchestrator_service.py::run_legacy`
  - `backend/apps/ia_dev/services/tool_ausentismo_service.py`
  - YAML narrativo/compatibilidad
- Cambio de alcance:
  - `tool_ausentismo_service` queda como compatibilidad para rutas no migradas.
  - `run_legacy` queda como fallback global para rutas no analytics o no migradas.

## Observabilidad Confirmada

- Metadata activa en task-state, respuesta runtime y eventos:
  - `analytics_router_decision`
  - `legacy_analytics_isolated`
  - `blocked_tool_ausentismo_service`
  - `blocked_run_legacy_for_analytics`
  - `fallback_reason`
  - `cleanup_phase=phase_7`

## Riesgos Pendientes

- `tool_ausentismo_service` y `run_legacy` aun deben mantenerse mientras existan rutas no migradas.
- Conviene observar si aparecen `runtime_only_fallback` en trafico real antes de retirar compatibilidad.

## Phase 8 Deduplicacion De Metadata

- Baseline confirmada antes de modificar:
  - `ia_dictionary_audit --domain ausentismo --with-empleados`
    - `duplicated_definitions=36`
    - `missing_columns=0`
    - `missing_metrics=0`
    - `missing_relations=0`
    - `missing_synonyms=0`
    - `missing_rules=0`
    - `yaml_structural_leaks=0`
  - `ia_runtime_diagnose --domain ausentismo --with-empleados --real-data`
    - `passed=10`
    - `failed=0`
    - `legacy_count=0`
    - `errores_sql=0`

- Diagnostico real de `duplicated_definitions=36`:
  - `35` eran falsos positivos del auditor legacy:
    - causa=`self_duplicate_signal`
    - origen: el auditor contaba dos veces el mismo registro cuando `column_name == campo_logico` o `column_name == nombre_columna_logico`
  - `1` era repeticion de token en distinto scope:
    - causa=`multi_record_same_token`
    - `cedula` aparecia en tablas distintas dentro del contexto extendido de `ausentismo`

- Nuevo diagnostico de deduplicacion segura:
  - `legacy_duplicate_signals=36`
  - `total_duplicates=11`
  - `conflicts=0`
  - `auto_merge_candidates=0`
  - `manual_review_required=11`
  - breakdown:
    - `tables=1`
    - `fields=10`
    - `domains=0`
    - `synonyms=0`
    - `rules=0`
    - `relations=0`

- Duplicados equivalentes detectados:
  - `1` tabla fisica compartida entre dominios:
    - `cincosas_cincosas.cinco_base_de_personal`
  - `10` campos fisicos compartidos entre `empleados` y `ausentismo`:
    - `cedula`
    - `nombre`
    - `apellido`
    - `supervisor`
    - `area`
    - `cargo`
    - `carpeta`
    - `movil`
    - `tipo`
    - `zona_nodo`

- Duplicados conflictivos detectados:
  - `0`

- Cambios aplicados en phase 8:
  - Se creo `ia_dictionary_deduplicate` con:
    - `--dry-run`
    - `--apply-safe`
  - Se reemplazo la deteccion de duplicados del auditor por una evaluacion por registro y scope compuesto.
  - No se eliminaron ni desactivaron registros porque:
    - no hubo `auto_merge_candidates`
    - todos los casos activos son equivalentes cross-domain y sostienen el scoping actual del runtime

- Resultado de `ia_dictionary_deduplicate --domain ausentismo --with-empleados --apply-safe`:
  - `applied_merge_count=0`
  - `skipped_merge_count=11`

- Estado final despues de phase 8:
  - `ia_dictionary_audit --domain ausentismo --with-empleados`
    - `duplicated_definitions=0`
    - `missing_columns=0`
    - `missing_metrics=0`
    - `missing_relations=0`
    - `missing_synonyms=0`
    - `missing_rules=0`
    - `yaml_structural_leaks=0`
  - `ia_runtime_diagnose --domain ausentismo --with-empleados --real-data`
    - `passed=10`
    - `failed=0`
    - `legacy_count=0`
    - `errores_sql=0`

- Rollback recomendado:
  - Revertir el codigo de `ia_dictionary_deduplicate` y la nueva logica del auditor si se quiere volver temporalmente al conteo legacy.
  - No hace falta rollback de DB en phase 8 porque `--apply-safe` no aplico merges sobre datos reales.

## Condicion Para Phase 8

- Listo para phase 8 solo para deduplicacion metadata, no para poda legacy completa.
- Condicion futura para borrar `tool_ausentismo_service`:
  - 7 dias de monitor con:
    - `legacy_count=0`
    - `blocked_run_legacy_for_analytics=0`
    - `runtime_only_fallback_count=0`
    - diagnostico `--real-data` limpio

## Phase 9 Rollout Controlado

- Phase 9 iniciada para trafico real controlado en `ausentismo + empleados`.
- Flag de piloto productivo:
  - `IA_DEV_ATTENDANCE_EMPLOYEES_PILOT_ENABLED=1`
- Alcance:
  - Aplica solo a `ausentismo` y `empleados`.
  - Mantiene el aislamiento de analytics con `IA_DEV_DISABLE_LEGACY_ANALYTICS_FALLBACK=1` para analytics cubierto de `ausentismo`.
  - No elimina legacy ni metadata; solo agrega control, auditoria y salud operativa.

## Criterio Para Mantener Piloto Activo

- Mantener el piloto activo mientras:
  - `legacy_count=0`
  - `runtime_only_fallback_count=0`
  - `blocked_legacy_count=0`
  - `errores_sql=0`
  - `satisfaction_review_failed_count=0`
  - `insight_poor_count=0`
- Validar diariamente con:
  - `python manage.py ia_runtime_pilot_health --domain ausentismo --days 1`
  - `python manage.py ia_runtime_pilot_report --domain ausentismo --days 7`

## Criterio Para Rollback

- Marcar rollback inmediato del piloto si cualquiera de estas señales aparece en ventana de 24 horas:
  - `legacy_count > 0`
  - `runtime_only_fallback_count > 0`
  - `blocked_legacy_count > 0`
  - `errores_sql > 0`
  - `satisfaction_review_failed_count > 0`
  - `insight_poor_count > 0`
- Accion recomendada:
  - conservar codigo y metadata actual
  - apagar `IA_DEV_ATTENDANCE_EMPLOYEES_PILOT_ENABLED`
  - revisar `ia_runtime_pilot_report` antes de reabrir trafico

## Criterio Futuro Para Retirar `tool_ausentismo_service`

- No retirar todavia.
- Solo considerar retiro cuando existan al menos `7` dias consecutivos de piloto real con:
  - `legacy_count=0`
  - `runtime_only_fallback_count=0`
  - `blocked_legacy_count=0`
  - `errores_sql=0`
  - `satisfaction_review_failed_count=0`
  - `insight_poor_count=0`
  - reporte de piloto sin recomendaciones criticas abiertas para `ai_dictionary`
- Hasta entonces, `tool_ausentismo_service` sigue como compatibilidad controlada fuera del alcance cubierto del piloto.

## Cierre Formal De Phase 9

- `phase_9` queda cerrada como `stable` para `ausentismo + empleados`.
- Evidencia operacional consolidada:
  - `ia_runtime_pilot_health --domain ausentismo --since-fix`: `healthy`
  - `ia_runtime_pilot_report --domain ausentismo --since-fix`:
    - `sql_assisted_count=6`
    - `runtime_only_fallback_count=0`
    - `legacy_count=0`
    - `blocked_legacy_count=0`
    - `errores_sql=0`
    - `insight_poor_count=0`
  - `ia_runtime_diagnose --domain ausentismo --with-empleados --real-data`:
    - `passed=10`
    - `failed=0`
    - `fallback_count=0`
    - `sql_assisted_count=9`
    - `handler_count=1`
    - `legacy_count=0`
- Decision de arquitectura:
  - El patron `dictionary-first + intent arbitration + task state + monitor/audit/diagnose + SQL assisted seguro` queda validado para un dominio cross-table real.
  - `ausentismo + empleados` se mantiene como baseline de referencia para replicacion.
  - No se autoriza aun borrado de legacy; solo se confirma estabilidad de la ruta moderna dentro del alcance cubierto.

## Discovery Para Phase 10

- Criterios usados:
  - alto valor empresarial
  - tablas fisicas localizables
  - posibilidad de declarar relaciones en `ai_dictionary`
  - preguntas analytics claras
  - bajo riesgo tecnico
- Estado real del `ai_dictionary`:
  - `dd_dominios=2`
  - dominios activos cargados hoy:
    - `EMPLEADOS`
    - `AUSENTISMOS`
- Lectura de candidatos:
  - `transporte`:
    - a favor: existe runtime parcial, policy flags, capability catalog y tablas reales candidatas
    - en contra: `get_domain_context('transporte')` aun retorna vacio y `ia_dictionary_audit --domain transporte` muestra `yaml_column_not_in_dd_campos=fecha_salida`
  - `horas_extras`, `comisiones`, `facturacion`, `viaticos`:
    - existen en registry, pero hoy no tienen soporte estructural real en `ai_dictionary`
    - no tienen slice capability-first comparable a `ausentismo + empleados`
    - riesgo tecnico mayor para una replicacion controlada
- Recomendacion:
  - elegir `transporte`
  - acotar el primer slice a `programacion de rutas`
  - tabla fact inicial recomendada: `cincosas_cincosas.nokia_base_ruta_programacion`
  - dimension reutilizable recomendada: `cincosas_cincosas.cinco_base_de_personal`
  - razon: ya existe `cedula`, tiene cobertura de join suficiente para una primera ola y permite preguntas analytics concretas sin generalizar el sistema

## Phase 10 Propuesta: Transporte / Programacion De Rutas

### 1. Audit De `ai_dictionary`

- Estado actual del dominio elegido:
  - `python manage.py ia_dictionary_audit --domain transporte --as-json`
  - resultado:
    - `missing_columns=0`
    - `missing_metrics=0`
    - `missing_relations=0`
    - `missing_synonyms=0`
    - `missing_rules=0`
    - `duplicated_definitions=0`
    - `yaml_structural_leaks=1`
      - `yaml_column_not_in_dd_campos: fecha_salida`
- Interpretacion:
  - el auditor no encuentra faltantes porque aun no existe una bateria funcional exigente para `transporte`
  - pero el `ai_dictionary` real no tiene dominio estructural cargado para `transporte`
  - por lo tanto, `transporte` no esta listo para runtime empresarial hasta bootstrap de metadata

### 2. 10 Preguntas Funcionales

- `Cuantas rutas programadas hubo por ciudad en un periodo dado`
- `Que proyectos concentran mas programaciones en el periodo`
- `Cuantas programaciones quedaron en estado EJECUCION vs RECEPCION`
- `Que tecnicos tuvieron mas programaciones por periodo`
- `Que supervisores concentran mas rutas programadas`
- `Que areas tienen mayor volumen de personal asignado a rutas`
- `Que vehiculos estan activos vs inactivos`
- `Que vehiculos tienen SOAT, CDA o licencia vencida`
- `Que conductores o propietarios tienen mas vehiculos asociados`
- `Que ciudades concentran mas vehiculos operativos`

### 3. Diagnostico Real-Data

- Baseline fisico encontrado:
  - `nokia_base_ruta_programacion`: `170` filas
  - `transportadores_vehiculos_org`: `1090` filas
  - `transportadores_dia_a_dia`: `5` filas
  - `Ubicacion_moviles`: `82261` filas
- Frescura observada:
  - `nokia_base_ruta_programacion.fecha_edit`: `2018-06-21` a `2018-08-13`
  - `transportadores_dia_a_dia.fecha_edit`: `2022-01-19` a `2023-09-29`
  - `transportadores_vehiculos_org.fecha_edit`: `2022-08-31` a `2024-06-18`
- Calidad y relacion con `empleados`:
  - `nokia_base_ruta_programacion.cedula -> cinco_base_de_personal.cedula`:
    - `matched=141/170` (`82.94%`)
    - `cedula_null=29`
  - `transportadores_vehiculos_org.cedual_conductor -> cinco_base_de_personal.cedula`:
    - `matched=308/1090` (`28.26%`)
  - `transportadores_vehiculos_org.cedula -> cinco_base_de_personal.cedula`:
    - `matched=172/1090` (`15.78%`)
- Calidad operacional util:
  - `nokia_base_ruta_programacion.estado`:
    - `EJECUCION=155`
    - `RECEPCION=15`
  - `transportadores_vehiculos_org.estado`:
    - `ACTIVO=522`
    - `INACTIVO=568`
  - vencimientos en `transportadores_vehiculos_org`:
    - `soat_vencido=1090`
    - `cda_vencido=1076`
    - `licencia_vencida=583`
    - `mantenimiento_vencido=1090`
- Diagnostico ejecutivo:
  - mejor primer slice: `nokia_base_ruta_programacion`
  - mejor segundo slice posterior: `transportadores_vehiculos_org`
  - no usar `transportadores_dia_a_dia` como fact principal inicial por volumen demasiado bajo
  - no usar `Ubicacion_moviles` en la primera ola por mayor complejidad temporal/geoespacial y sin join organizacional claro

### 4. Gaps De Metadata

- Falta crear `dd_dominios` para `TRANSPORTE`.
- Falta registrar `dd_tablas` para:
  - `cincosas_cincosas.nokia_base_ruta_programacion`
  - `cincosas_cincosas.transportadores_vehiculos_org`
  - `cincosas_cincosas.cinco_base_de_personal` como dimension compartida
- Falta registrar `dd_campos` minimos:
  - `cedula`
  - `fecha_edit`
  - `fprogramacion`
  - `estado`
  - `proyecto`
  - `region`
  - `ciudad`
  - `placa`
  - `nombre_conductor`
  - `movil_asignada`
  - `fecha_soat`
  - `fecha_cda`
  - `fecha_licencia`
  - `proximo_mantenimiento`
- Falta declarar relaciones:
  - `nokia_base_ruta_programacion.cedula = cinco_base_de_personal.cedula`
  - `transportadores_vehiculos_org.cedual_conductor = cinco_base_de_personal.cedula`
  - opcional despues: `transportadores_vehiculos_org.cedula = cinco_base_de_personal.cedula`
- Faltan sinonimos de negocio:
  - `ruta`, `programacion`, `tecnico`, `vehiculo`, `placa`, `conductor`, `mantenimiento`, `soat`, `cda`
- Falta formalizar metricas soportadas:
  - `total_programaciones`
  - `total_vehiculos`
  - `total_activos`
  - `total_inactivos`
  - `documentos_vencidos`
- Falta extender `diagnose` con casos reales de `transporte`

### 5. Plan Incremental Estilo Ausentismo + Empleados

- `phase_10a`:
  - bootstrap de `ai_dictionary` solo para `transporte/programacion_de_rutas`
  - sin tocar legacy
  - sin generalizar otros dominios
- `phase_10b`:
  - cargar `dd_tablas`, `dd_campos`, `dd_relaciones`, `dd_sinonimos`, `dd_reglas`
  - reusar `cinco_base_de_personal` como dimension organizacional oficial
- `phase_10c`:
  - extender `IntentArbitrationService` para reconocer consultas analytics claras de `transporte`
  - mantener `TaskStateService`, monitor, audit y trazabilidad iguales a phase 9
- `phase_10d`:
  - habilitar SQL assisted seguro solo para agregaciones de `nokia_base_ruta_programacion`
  - dimensiones iniciales:
    - `estado`
    - `ciudad`
    - `region`
    - `proyecto`
    - `supervisor` via join con empleados
- `phase_10e`:
  - agregar segundo slice `transportadores_vehiculos_org` para estado documental y mantenimiento
  - mantener capacidades separadas por slice, no por tabla como agente independiente
- `phase_10f`:
  - activar piloto controlado de `transporte`
  - medir con los mismos indicadores de health/report usados en phase 9

### 6. Flags Recomendadas

- Reusar banderas existentes, sin introducir complejidad innecesaria:
  - `IA_DEV_DOMAIN_TRANSPORTE_ENABLED=1`
  - `IA_DEV_CAP_TRANSPORT_ENABLED=0` al inicio
  - `IA_DEV_CAP_TRANSPORT_SUMMARY_ENABLED=0` al inicio
  - `IA_DEV_POLICY_TRANSPORT_FORCE_LEGACY=0`
- Activacion sugerida:
  - dejar `IA_DEV_CAP_TRANSPORT_ENABLED=0` hasta completar bootstrap estructural
  - subir `IA_DEV_CAP_TRANSPORT_SUMMARY_ENABLED=1` solo para el slice `nokia_base_ruta_programacion`
  - mantener legacy disponible durante toda phase 10
- No aplicar aun una bandera equivalente a `IA_DEV_DISABLE_LEGACY_ANALYTICS_FALLBACK=1` para `transporte` hasta tener:
  - audit limpio
  - diagnose real-data verde
  - piloto baseline sin errores SQL

### 7. Tests Minimos

- `ia_dictionary_audit --domain transporte` debe fallar al inicio y quedar limpio al cerrar bootstrap.
- Agregar casos a `ia_runtime_diagnose` para `transporte`:
  - conteo por `estado`
  - agrupacion por `ciudad`
  - agrupacion por `proyecto`
  - cruce con `supervisor` usando `empleados`
- Tests unitarios minimos:
  - `IntentArbitrationService` enruta `transporte` a analytics cuando la pregunta es agregable
  - `TaskStateService` registra `analytics_router_decision` y `response_flow`
  - SQL assisted bloquea columnas/tablas fuera de `ai_dictionary`
  - fallback a legacy sigue disponible cuando falte metadata o falle compilacion
- Tests de integracion minimos:
  - pregunta simple de programaciones por ciudad
  - pregunta de vehiculos activos/inactivos
  - pregunta con join a supervisor
  - pregunta fuera de cobertura que confirme `legacy` intacto

## Decision Ejecutiva Para Phase 10

- Proceder con `transporte`, pero no como dominio amplio desde el dia 1.
- Replicar el patron solo sobre `programacion de rutas` primero.
- Mantener `legacy` completo durante toda la fase.
- No crear agentes por tabla.
- No generalizar el sistema antes de demostrar exito en este segundo dominio.
- `ai_dictionary` sigue siendo la unica source of truth estructural antes de habilitar SQL assisted productivo.
