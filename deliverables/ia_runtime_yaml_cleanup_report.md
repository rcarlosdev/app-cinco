# Reporte Onda 3: YAML Estructural -> ai_dictionary First

## Causa Raiz De Las Fugas YAML Estructurales

- `DomainContextLoader` promovia desde YAML a runtime:
  - `tablas_asociadas`
  - `columnas_clave`
  - `joins_conocidos`
  - `capacidades`
  - `filtros_soportados`
  - `group_by_soportados`
  - `metricas_soportadas`
- `SemanticBusinessResolver` tomaba esa estructura desde `domain.raw_context` y la mezclaba con `DictionaryToolService`.
- En la practica, YAML podia seguir definiendo:
  - tablas
  - columnas
  - joins
  - dimensiones
  - metricas
  - filtros
- Eso ocultaba metadata incompleta en `ai_dictionary` y permitia que tests o flujos locales pasaran por fuga estructural en vez de por contrato real `dd_*`.

## Campos YAML Estructurales Encontrados

- En `backend/apps/ia_dev/domains/ausentismo/dominio.yaml` y `backend/apps/ia_dev/domains/empleados/dominio.yaml`:
  - `tablas_asociadas`
  - `columnas_clave`
  - `joins_conocidos`
  - `filtros_soportados`
  - `group_by_soportados`
  - `metricas_soportadas`
  - `capacidades`
- En runtime code:
  - [backend/apps/ia_dev/application/delegation/domain_context_loader.py](/c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/delegation/domain_context_loader.py:12)
  - [backend/apps/ia_dev/application/semantic/semantic_business_resolver.py](/c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/semantic/semantic_business_resolver.py:56)
  - [backend/apps/ia_dev/services/runtime_governance_service.py](/c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/services/runtime_governance_service.py:306)
- Dependencias residuales fuera del runtime principal:
  - [backend/apps/ia_dev/application/delegation/domain_registry.py](/c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/delegation/domain_registry.py:42)
  - [backend/apps/ia_dev/application/delegation/delegation_coordinator.py](/c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/delegation/delegation_coordinator.py:637)
  - `ai_dictionary_remediation_service.py` aun usa YAML estructural como insumo de compatibilidad, por eso no se borraron campos fisicos del YAML en esta onda.

## Clasificacion

- `mover a ai_dictionary`:
  - tablas
  - columnas
  - relaciones
  - joins
  - aliases fisicos
  - filtros soportados
  - group by soportados
  - metricas soportadas
  - capacidades tecnicas
- `mantener narrativo`:
  - `contexto_agente`
  - `reglas_negocio`
  - `ejemplos_consulta`
  - `vocabulario_negocio`
  - `tablas_prioritarias`
  - `columnas_prioritarias`
  - metadata descriptiva de dominio: nombre, objetivo, entidad principal, madurez, flags no estructurales
- `compatibilidad temporal`:
  - `legacy_capabilities` en carga de archivo
  - YAML fisico estructural retenido mientras existan servicios de remediacion y flujos legacy que todavia lo consumen fuera del runtime principal
- `eliminar del runtime`:
  - promocion top-level de estructura YAML en `DomainContextLoader`
  - fusion estructura YAML + diccionario en `SemanticBusinessResolver`

## Cambios Aplicados

- `DomainContextLoader` ahora:
  - conserva YAML como narrativa
  - registra inventario estructural en `yaml_structural_inventory`
  - marca `yaml_fields_ignored` y `yaml_fields_removed`
  - deja de promocionar estructura YAML a `tables/columns/relationships` del contexto por archivo
- `SemanticBusinessResolver` ahora:
  - construye `tables`, `columns`, `relationships`, `allowed_tables`, `allowed_columns`, aliases y `query_hints` solo desde `DictionaryToolService`
  - no usa YAML como fallback estructural
  - registra:
    - `structural_source=ai_dictionary`
    - `yaml_role=narrative_only`
    - `yaml_structural_ignored=true/false`
    - `missing_dictionary_metadata`
- `RuntimeGovernanceService` y `ia_dictionary_audit` ahora detectan:
  - `yaml_structural_leaks`
  - `yaml_fields_ignored`
  - `yaml_fields_removed`
  - `missing_dictionary_metadata`
- `ChatApplicationService` expone metadata nueva de source-of-truth en respuesta y eventos de runtime.

## Campos Eliminados

- Eliminados del runtime por archivo:
  - `tables`
  - `columns`
  - `relationships`
  - `capabilities`
  - `filtros_soportados`
  - `group_by_soportados`
  - `metricas_soportadas`
- Eliminacion fisica en YAML:
  - no aplicada en esta onda
  - motivo: hay consumidores de compatibilidad fuera del runtime principal, especialmente `ai_dictionary_remediation_service.py`

## Que Quedo Como YAML Narrativo

- `contexto_agente`
- `reglas_negocio`
- `ejemplos_consulta`
- `vocabulario_negocio`
- `tablas_prioritarias`
- `columnas_prioritarias`
- metadata descriptiva y de presentacion del dominio

## Que Quedo Gobernado Por ai_dictionary

- dominios
- tablas
- columnas
- relaciones
- joins
- sinonimos
- metrica/dimension/filter capability
- aliases logico->fisico usados por runtime
- validacion de SQL seguro via `allowed_tables` y `allowed_columns`

## Estado De Auditoria Y Metadata

- `ia_dictionary_audit --domain ausentismo --with-empleados`:
  - `missing_columns=0`
  - `missing_metrics=0`
  - `missing_relations=0`
  - `missing_synonyms=0`
  - `missing_rules=0`
  - `yaml_structural_leaks=0`
  - `yaml_fields_ignored=14`
  - `yaml_fields_removed=14`
  - `missing_dictionary_metadata=0`

## Dependencias Rotas O Eliminadas

- Eliminadas del runtime principal:
  - dependencia directa de `SemanticBusinessResolver` en estructura YAML
  - dependencia de `DomainContextLoader.load_from_files()` para tablas/columnas/joins del runtime principal
- No eliminadas todavia:
  - `DomainRegistry`
  - `CapabilityRouter/Planner`
  - `orchestrator_service.py`
  - `tool_ausentismo_service.py`

## Archivos Tocados

- [backend/apps/ia_dev/application/delegation/domain_context_loader.py](/c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/delegation/domain_context_loader.py:1)
- [backend/apps/ia_dev/application/semantic/semantic_business_resolver.py](/c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/semantic/semantic_business_resolver.py:1)
- [backend/apps/ia_dev/services/runtime_governance_service.py](/c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/services/runtime_governance_service.py:1)
- [backend/apps/ia_dev/management/commands/ia_dictionary_audit.py](/c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/management/commands/ia_dictionary_audit.py:1)
- [backend/apps/ia_dev/application/orchestration/chat_application_service.py](/c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/application/orchestration/chat_application_service.py:1)
- [backend/apps/ia_dev/tests/test_query_semantic_resolvers.py](/c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/tests/test_query_semantic_resolvers.py:1)
- [backend/apps/ia_dev/tests/test_phase6_runtime_governance.py](/c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/tests/test_phase6_runtime_governance.py:1)
- [backend/apps/ia_dev/tests/test_chat_runtime_metadata.py](/c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/tests/test_chat_runtime_metadata.py:1)
- [backend/apps/ia_dev/tests/test_chat_runtime_sql_alignment.py](/c:/dev/agente_cinco/app-cinco/backend/apps/ia_dev/tests/test_chat_runtime_sql_alignment.py:1)

## Lineas Removidas Estimadas

- Remocion directa atribuible a esta onda:
  - ~58 lineas de lectura/promocion estructural legacy retiradas o neutralizadas
- Nota:
  - `chat_application_service.py` ya tenia cambios previos en el worktree; solo se agrego metadata puntual, por lo que no se uso ese archivo para estimacion de poda.

## Validacion Ejecutada

- `python backend/manage.py test apps.ia_dev.tests.test_chat_runtime_metadata apps.ia_dev.tests.test_chat_runtime_sql_alignment apps.ia_dev.tests.test_regression_endpoints apps.ia_dev.tests.test_simulate_ia_dev_chat_command`
  - `OK`
- `python backend/manage.py ia_dictionary_audit --domain ausentismo --with-empleados`
  - `yaml_structural_leaks=0`
  - `missing_dictionary_metadata=0`
- `python backend/manage.py ia_runtime_diagnose --domain ausentismo --with-empleados --real-data`
  - `passed=10`
  - `failed=0`
  - `sql_assisted_count=9`
  - `handler_count=1`
  - `legacy_count=0`
- `python backend/manage.py ia_runtime_pilot_health --domain ausentismo --days 1 --since-fix`
  - `status=healthy`
- `python backend/manage.py ia_runtime_pilot_report --domain ausentismo --days 1 --since-fix`
  - `sql_assisted_count=6`
  - `runtime_only_fallback_count=0`
  - `legacy_count=0`
  - `blocked_legacy_count=0`
  - `errores_sql=0`

## Flujos Validados Como No Usados O Conflictivos

- `legacy_count=0` en diagnose y pilot report:
  - el fallback legacy no se uso en el alcance validado de `ausentismo + empleados`
  - candidato fuerte para poda futura: ramas legacy analytics alrededor de router/planner una vez se cierre la siguiente onda
- `runtime_only_fallback_count=0`:
  - no hay evidencia de necesidad operativa del fallback runtime-only en los casos auditados actuales
  - mantener por seguridad, pero no ampliar complejidad alrededor de esa ruta
- `handler_count=1` en diagnose:
  - corresponde al caso moderno de cumpleanos en empleados
  - no es candidato de eliminacion
- `default_sql_builder` sigue activo en parte del diagnostico real:
  - no eliminar
  - convive sano con `join_aware_pilot`
- dependencia residual conflictiva a limpiar despues:
  - `DelegationCoordinator` validando SQL con `domain.raw_context["tables"]`
  - `DomainRegistry` reteniendo `capabilities` legacy por compatibilidad

## Riesgos Pendientes

- YAML estructural sigue existiendo fisicamente en archivos de dominio.
- `ai_dictionary_remediation_service.py` todavia depende de ese YAML estructural como insumo operativo de compatibilidad.
- `DelegationCoordinator` conserva una validacion basada en `domain.raw_context["tables"]`; hoy ya no afecta el flujo principal validado, pero es ruido tecnico.
- `CapabilityRouter/Planner` y `orchestrator_service.py` siguen como deuda de encapsulacion, aunque no hayan aparecido en el piloto validado.

## Siguiente Onda Recomendada

- Onda 4: encapsular compatibilidad y podar residuos no usados del piloto cubierto.
- Orden recomendado:
  1. sacar validacion estructural YAML residual de `DelegationCoordinator`
  2. mover consumidores no-runtime de YAML estructural a `ai_dictionary` o a snapshots derivados
  3. marcar `CapabilityRouter/Planner` y wrapper legacy como compatibilidad explicita para posterior borrado
  4. solo despues evaluar borrado fisico de campos estructurales en YAML
