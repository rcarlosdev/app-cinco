# Onda 10: adapter publico eliminado

## Resumen

- `ChatApplicationService` queda como runtime publico unico.
- `IADevOrchestratorService` fue retirado del flujo productivo y borrado.
- `chat_view.py` ahora usa `ChatApplicationService` en camino sano y `RuntimeFallbackService` como contingencia explicita.
- `LegacyOrchestratorRuntime` sigue vivo solo como runtime legacy encapsulado detras de `RuntimeFallbackService`.
- `simulate_ia_dev_chat.py`, analytics cubierto y KPRO siguen fuera del adapter eliminado.

## Cambios aplicados

### Runtime publico

- `backend/apps/ia_dev/views/chat_view.py`
  - elimina import y singleton de `IADevOrchestratorService`
  - camino sano: `ChatApplicationService.run(...)`
  - fallback explicito: `RuntimeFallbackService.run(...)`
  - metadata HTTP actualizada:
    - `data_sources.runtime.legacy_adapter_removed=true`
    - `data_sources.runtime.legacy_runtime_fallback_used=true|false`
    - `data_sources.runtime.legacy_runtime_fallback_reason`

### Fallback legacy restante

- `backend/apps/ia_dev/services/runtime_fallback_service.py`
  - nuevo servicio explicito de contingencia
  - encapsula `LegacyOrchestratorRuntime`
  - conserva guard para analytics cubierto y bloqueo de fallback legacy cuando aplica

### Runtime legacy

- `backend/apps/ia_dev/services/orchestrator_legacy_runtime.py`
  - sigue disponible
  - observabilidad renombrada para reportar `LegacyOrchestratorRuntime` en lugar del adapter historico

## Adapter eliminado

- archivo borrado:
  - `backend/apps/ia_dev/services/orchestrator_service.py`

- imports eliminados:
  - `backend/apps/ia_dev/views/chat_view.py`
  - `backend/apps/ia_dev/tests/test_regression_endpoints.py`
  - `backend/apps/ia_dev/tests/test_orchestrator_legacy_semantics.py`

## Tests migrados

- `test_regression_endpoints.py`
  - valida camino sano directo por `ChatApplicationService`
  - valida fallback via `RuntimeFallbackService`
  - migra checks de bootstrap al helper/runtime fallback
- `test_orchestrator_legacy_semantics.py`
  - ya no prueba el adapter
  - prueba semantica del fallback legacy explicito
- `test_phase5_legacy_cleanup.py`
  - agrega guard para que `chat_view.py` no reimporte `orchestrator_service.py`

## Flujo unico real

- si: el runtime publico unico ya es `ChatApplicationService`
- el runtime legacy restante no es publico; queda solo como contingencia encapsulada

## Riesgos

- `RuntimeFallbackService` sigue dependiendo de `LegacyOrchestratorRuntime`, asi que la deuda legacy aun existe aunque ya no sea entrypoint publico.
- `tool_ausentismo_service.py` sigue vivo dentro del runtime legacy y deberia limpiarse en una onda posterior separada.
- pueden quedar menciones historicas de `IADevOrchestratorService` en documentacion amplia o snapshots viejos; no deben existir imports/callers activos.

## Validacion ejecutada

### Tests pedidos

- `python backend/manage.py test apps.ia_dev.tests.test_chat_runtime_metadata apps.ia_dev.tests.test_chat_runtime_sql_alignment apps.ia_dev.tests.test_regression_endpoints apps.ia_dev.tests.test_simulate_ia_dev_chat_command apps.ia_dev.tests.test_phase5_legacy_cleanup apps.ia_dev.tests.test_orchestrator_legacy_semantics`
- resultado:
  - `54 tests`
  - `OK`

### Auditoria de diccionario

- `python backend/manage.py ia_dictionary_audit --domain ausentismo --with-empleados`
- resultado clave:
  - `missing_columns=0`
  - `missing_metrics=0`
  - `missing_relations=0`
  - `missing_synonyms=0`
  - `missing_rules=0`
  - `duplicated_definitions=0`
  - `missing_dictionary_metadata=0`
  - nota: persisten `yaml_fields_ignored=14` y `yaml_fields_removed=14` como hallazgo conocido, no introducido por Onda 10

### Diagnostico runtime real-data

- `python backend/manage.py ia_runtime_diagnose --domain ausentismo --with-empleados --real-data`
- resultado:
  - `passed=10`
  - `failed=0`
  - `fallback_count=0`
  - `sql_assisted_count=9`
  - `handler_count=1`
  - `legacy_count=0`

### Salud del piloto

- `python backend/manage.py ia_runtime_pilot_health --domain ausentismo --days 1 --since-fix`
- resultado:
  - `status=healthy`
  - `legacy_count=0`
  - `runtime_only_fallback_count=0`
  - `blocked_legacy_count=0`

## Archivos modificados

- `backend/apps/ia_dev/services/runtime_fallback_service.py`
- `backend/apps/ia_dev/services/orchestrator_legacy_runtime.py`
- `backend/apps/ia_dev/views/chat_view.py`
- `backend/apps/ia_dev/tests/test_regression_endpoints.py`
- `backend/apps/ia_dev/tests/test_orchestrator_legacy_semantics.py`
- `backend/apps/ia_dev/tests/test_phase5_legacy_cleanup.py`
- `backend/apps/ia_dev/tests/test_observability_summary_cause_diagnostics.py`
- `backend/GUIA_TECNICA_FLUJO_SISTEMA_MULTIAGENTE.md`
- `deliverables/ia_runtime_pruning_report.md`

## Archivos borrados

- `backend/apps/ia_dev/services/orchestrator_service.py`

## Referencias restantes esperadas

- `LegacyOrchestratorRuntime` como implementacion legacy encapsulada
- `tool_ausentismo_service.py` aun consumido por el runtime legacy
- menciones historicas no ejecutables en deliverables/planes anteriores
