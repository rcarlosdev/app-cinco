# Plan De Deprecacion Controlada

## Phase 7: Encapsular Legacy Analytics

- Aislado efectivamente en esta fase:
  - Analytics cubierto de `ausentismo + empleados` entra por `join_aware_sql`.
  - Casos especificos no SQL de `empleados` siguen por handler moderno.
  - Casos inseguros del analytics cubierto responden `runtime_only_fallback`.
  - Legacy queda reservado para rutas no analytics o no migradas.

- Reglas activas con `IA_DEV_DISABLE_LEGACY_ANALYTICS_FALLBACK=1`:
  - `tool_ausentismo_service` no debe ejecutarse para analytics cubierto por join-aware SQL.
  - Si join-aware falla, no se permite caer a `run_legacy`.
  - La telemetria deja evidencia con:
    - `analytics_router_decision`
    - `legacy_analytics_isolated=true`
    - `blocked_tool_ausentismo_service`
    - `blocked_run_legacy_for_analytics`
    - `fallback_reason`
    - `cleanup_phase=phase_7`

## Wrappers Que Siguen Vivos

- `backend/apps/ia_dev/services/orchestrator_service.py`
  - Sigue como wrapper de compatibilidad.
- `backend/apps/ia_dev/services/orchestrator_service.py::run_legacy`
  - Sigue vivo solo como fallback global no analytics.
- `backend/apps/ia_dev/services/tool_ausentismo_service.py`
  - Sigue vivo solo como compatibilidad para rutas no migradas.
- YAML
  - Sigue vivo para narrativa, tono, ejemplos y compatibilidad general.

## No Tocar Aun

- No borrar archivos legacy.
- No borrar tablas.
- No eliminar `IADevOrchestratorService`.
- No eliminar `run_legacy`.
- No eliminar `tool_ausentismo_service`.
- No deduplicar aun `duplicated_definitions=36`.

## Condicion Futura Para Borrar `tool_ausentismo_service`

- Esperar 7 dias de monitor estable con:
  - `legacy_count=0`
  - `blocked_run_legacy_for_analytics=0`
  - `runtime_only_fallback_count=0`
  - `python backend/manage.py ia_runtime_diagnose --domain ausentismo --with-empleados --real-data` limpio

## Phase 8 Sugerida

- Siguiente paso recomendado:
  - deduplicar metadata estructural y narrativa sin alterar runtime
- Alcance de phase 8:
  - atacar `duplicated_definitions=36`
  - mantener unchanged el router encapsulado de phase 7
