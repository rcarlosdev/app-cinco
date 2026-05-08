# Onda 4: Runtime Compatibility Cleanup Report

## Estado

Onda 4 queda verde para el piloto `ausentismo + empleados`.

Flujo core confirmado:

`HTTP/CLI -> ChatApplicationService -> IntentArbitrationService -> SemanticBusinessResolver(ai_dictionary) -> QueryExecutionPlanner -> sql_assisted | handler moderno | runtime_only_fallback -> TaskStateService -> respuesta empresarial`

## Rutas `compatibility_only`

- `DelegationCoordinator`
  - Sigue vivo solo como compatibilidad explícita.
  - Ahora devuelve `compatibility_only`, `delegation_compat_used` y `delegation_compat_reason`.
  - La validación SQL residual ya no usa `domain.raw_context["tables"]`; usa `DictionaryToolService` y `ai_dictionary`.

- `CapabilityPlanner / CapabilityRouter / IntentToCapabilityBridge`
  - Ya no se presentan como autoridad cuando `QueryExecutionPlanner` decide.
  - Cuando participan, quedan marcados como ruta post-planner o fallback explícito.
  - Metadata nueva:
    - `compatibility_router_used`
    - `compatibility_router_reason`
    - `planner_was_authority`

- `ProactiveLoop / LoopController`
  - Con `IA_DEV_PROACTIVE_LOOP_ENABLED=0` ya no se ejecuta el loop.
  - Se hace un solo pase compatible y queda marcado con `proactive_compat_only`.
  - No reemplaza respuestas ya resueltas por `sql_assisted` ni por handler moderno.

- `LegacyResponseAssembler`
  - Queda reducido al contrato frontend y a diagnósticos útiles.
  - Las trazas de planner/router/divergence ya no se inyectan como autoridad.
  - Solo expone detalle ampliado cuando realmente hubo compatibilidad activa.

## Rutas eliminadas o aisladas del flujo principal

- Validación estructural residual de delegación basada en `domain.raw_context["tables"]`.
- Ejecución residual del proactive loop cuando el flag está apagado.
- Trazas legacy ruidosas de `capability_planner`, `policy_guard`, `capability_router` y `capability_divergence` como si fueran autoridad principal.

## Imports muertos removidos

- No se hizo poda agresiva de imports en esta onda.
- La limpieza fue conservadora para no mezclar aislamiento de flujo con refactors amplios sobre un worktree ya activo.

## Módulos que siguen vivos y por qué

- `backend/apps/ia_dev/application/orchestration/chat_application_service.py`
  - Sigue siendo el entrypoint real del runtime.

- `backend/apps/ia_dev/application/delegation/delegation_coordinator.py`
  - Sigue vivo para compatibilidad explícita y medición antes de poda.

- `backend/apps/ia_dev/application/routing/capability_planner.py`
  - Sigue vivo para selección compatible de capability cuando el planner no resuelve de forma precomputada.

- `backend/apps/ia_dev/application/routing/capability_router.py`
  - Sigue vivo para ejecutar handlers modernos como fallback explícito post-planner.

- `backend/apps/ia_dev/application/routing/intent_to_capability_bridge.py`
  - Sigue vivo para traducir clasificación legacy a capacidades mientras existan imports y tests activos.

- `backend/apps/ia_dev/application/orchestration/loop_controller.py`
  - Sigue vivo, pero ya encapsulado detrás del flag y fuera del flujo cuando el loop está apagado.

- `backend/apps/ia_dev/application/orchestration/response_assembler.py`
  - Sigue vivo por compatibilidad de contrato frontend y resumen empresarial.

- `backend/apps/ia_dev/services/orchestrator_service.py`
  - No se tocó ni se borró en esta onda por restricción explícita.

## Candidatos claros para Onda 5

- `DelegationCoordinator` activo, si la telemetría confirma uso nulo o irrelevante.
- `CapabilityPlanner / CapabilityRouter / IntentToCapabilityBridge`, si `QueryExecutionPlanner` absorbe el último fallback productivo.
- `LoopController`, si el rollout sigue apagado y no hay dependencia real.
- Bloques de `capability_shadow` y metadata de compatibilidad en `LegacyResponseAssembler`, si frontend ya no los requiere.
- `orchestrator_service.py`, solo después de confirmar cero dependencia productiva y de tests.

## Líneas removidas estimadas

- Remoción directa visible en esta onda: ~80 líneas.
- Aislamiento adicional sin borrado agresivo: varias rutas quedaron encapsuladas y listas para poda posterior.
- Se privilegió reducir autoridad legacy antes de borrar archivos completos.

## Riesgos pendientes

- `ChatApplicationService` sigue siendo muy grande; la separación entre core y compatibilidad todavía comparte archivo.
- `CapabilityPlanner/Router/Bridge` siguen importados y testeados, así que la poda total requiere una Onda 5 dedicada.
- `LegacyResponseAssembler` aún conserva responsabilidades mixtas: contrato frontend, presentación y diagnósticos.
- Hay un worktree con cambios previos amplios; por eso la limpieza de código muerto se hizo solo en zonas seguras.

## Validación ejecutada

- `python backend/manage.py test apps.ia_dev.tests.test_chat_runtime_metadata apps.ia_dev.tests.test_chat_runtime_sql_alignment apps.ia_dev.tests.test_regression_endpoints apps.ia_dev.tests.test_simulate_ia_dev_chat_command`
  - `OK`

- `python backend/manage.py ia_dictionary_audit --domain ausentismo --with-empleados`
  - `missing_columns=0`
  - `missing_metrics=0`
  - `missing_relations=0`
  - `yaml_structural_leaks=0`

- `python backend/manage.py ia_runtime_diagnose --domain ausentismo --with-empleados --real-data`
  - `passed=10`
  - `sql_assisted_count=9`
  - `handler_count=1`
  - `legacy_count=0`

- `python backend/manage.py ia_runtime_pilot_health --domain ausentismo --days 1 --since-fix`
  - `status=healthy`
  - `legacy_count=0`
  - `runtime_only_fallback_count=0`

- `python backend/manage.py ia_runtime_pilot_report --domain ausentismo --days 1 --since-fix`
  - `total_consultas_reales=0`
  - Sin regresiones detectadas en la ventana consultada.
