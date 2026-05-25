# Inventario de reglas semanticas hardcodeadas

## 1. Resumen ejecutivo

Este diagnostico documenta la primera superficie de migracion anti-hardcode revisada en runtime semantico Python, con foco en intencion, dominio, capability, routing, planner, response assembly y agentes.

Alcance leido:

- `apps/ia_dev/application/orchestration/chat_application_service.py`
- `apps/ia_dev/application/semantic/query_intent_resolver.py`
- `apps/ia_dev/application/semantic/semantic_orchestrator_service.py`
- `apps/ia_dev/services/intent_arbitration_service.py`
- `apps/ia_dev/application/semantic/semantic_capability_registry.py`
- `apps/ia_dev/application/semantic/query_execution_planner.py`
- `apps/ia_dev/application/delegation/domain_registry.py`
- `apps/ia_dev/domains/inventario_logistica/`
- `apps/ia_dev/domains/empleados/`
- `apps/ia_dev/domains/ausentismo/`
- contratos YAML y Capability Pack relevantes

Resultado de la lectura focalizada:

- La capa mas madura es `inventario_logistica`: ya tiene `reglas_semanticas.yaml`, `paquete_capacidades.yaml`, contrato de agente y `SemanticCapabilityRegistry`, pero aun conserva mirrors Python y fallbacks legacy.
- `empleados` y `ausentismo` tienen contratos y reglas YAML, pero siguen dependiendo de regex, keywords, mappings y decisiones semanticas duras en Python.
- `QueryExecutionPlanner` concentra varios guardrails tecnicos que no deben migrarse a metadata.
- El principal riesgo actual no es un `if` aislado, sino la coexistencia de metadata gobernada con duplicados Python que todavia pueden decidir dominio, intent o template.

Conteo del inventario documentado en este archivo:

- `authoritative_layer`: 4
- `assistive_heuristic`: 5
- `shadow_fallback`: 4
- `compatibility_layer`: 7
- `technical_guardrail`: 6

## Estado 2026-05-24 Fase 2

Estado posterior a la implementacion:

- `SemanticCapabilityRegistry` ya prioriza seleccion declarativa de `template_id` desde `paquete_capacidades.yaml -> semantic_bindings -> selection_rules`.
- La seleccion declarativa ya usa `intent_ids`, `entity_fields`, `families`, `output_profiles`, `normalized_filters`, `group_by`, `business_concepts`, `stock_scopes`, `requires_attachment` y reglas declarativas del pack.
- `_resolve_inventory_template_legacy` se conserva solo como `shadow_fallback` trazado.
- La traza estable ahora diferencia:
  - `source = capability_pack`
  - `source = legacy_shadow_fallback`
  - `fallback_used`
  - `legacy_mapping_used`
  - `migration_pending`

Templates ya migrados al pack para seleccion:

- `inventory_material_stock_mobile`
- `inventory_material_stock_grouped_dimension`
- `inventory_serial_stock_by_family_grouped_dimension`
- `inventory_material_stock_by_warehouse`
- `inventory_material_stock_balance`
- `inventory_material_critical_by_employee`
- `inventory_kardex_by_employee`
- `inventory_kardex_consolidated`
- `inventory_serial_by_operational_holder`
- `inventory_document_generation_pending`
- `inventory_transfer_destination_not_available`
- `inventory_traceability_by_serial`
- `inventory_transfer_warehouse`
- `inventory_transfer_other_ally`
- `inventory_provider_serial_validation`

Templates que siguen en legacy shadow fallback confirmado:

- no queda un template focal confirmado en pruebas dentro de esta fase
- `_resolve_inventory_template_legacy` se conserva como compatibilidad temporal para cualquier template legacy de inventario que aun no tenga `selection_rules` declarados en el pack

## Estado 2026-05-24 Fase 2.1 verificacion anti-hardcode de cierre

Se agrego una verificacion automatica en el loader del `Capability Pack` para medir cobertura declarativa real de templates activos usados por pruebas/evals focales.

Trace nueva publicada:

- `capability_pack_coverage`
- `templates_pack_driven_count`
- `templates_legacy_allowed_count`
- `templates_missing_selection_rules`

Cobertura declarativa actual en pruebas/evals focales:

- `16` templates activos detectados
- `11` templates activos ya gobernados por `semantic_bindings.selection_rules`
- `1` template activo con `legacy_allowed` explicito en evals
- cobertura observable del pack: `0.6875`

Templates activos pendientes de migracion declarativa:

- `inventory_consumption_billing_operacion_hfc`
- `inventory_consumption_top`
- `inventory_movement_detail`
- `inventory_risk_consumo_movil_sin_validar`
- `inventory_serial_stock_by_dimension`

Politica de validacion nueva:

- falla si un template activo usado por evals no tiene binding declarativo y no esta marcado como `legacy_allowed`
- falla si un `semantic_binding` apunta a capability inexistente
- falla si un `semantic_binding` apunta a `response_profile` inexistente
- falla si un `semantic_binding` no declara `planner_route_hint`
- falla si un caso cubierto cae a legacy sin permiso explicito

Conclusion operativa de esta fase:

- aun no es seguro retirar el primer bloque legacy
- `_resolve_inventory_template_legacy` debe mantenerse acotado hasta migrar los cinco templates activos pendientes

## Estado 2026-05-24 Fase 2.2 cierre declarativo de templates activos

Estado posterior a la migracion focal:

- los 5 templates activos pendientes ya quedaron declarados en `paquete_capacidades.yaml`
- `SemanticCapabilityRegistry` ya los resuelve desde `semantic_bindings.selection_rules`
- el binding observable conserva `candidate_capability`, `planner_route_hint` y `response_profile`
- `_resolve_inventory_template_legacy` sigue vivo solo como `shadow_fallback`

Templates migrados en esta fase:

- `inventory_consumption_billing_operacion_hfc`
- `inventory_consumption_top`
- `inventory_movement_detail`
- `inventory_risk_consumo_movil_sin_validar`
- `inventory_serial_stock_by_dimension`

Cobertura declarativa activa medida por loader/evals:

- `16` templates activos detectados
- `16` templates activos ya gobernados por `selection_rules`
- `0` templates activos con `legacy_allowed` por falta de binding declarativo
- cobertura observable del pack: `1.0`
- `templates_missing_selection_rules = []`

Reglas declarativas nuevas agregadas:

- `inventario.route.serial_stock_dimension`
- `inventario.route.risk_consumo_movil_sin_validar`
- `inventario.route.consumption_top`
- `inventario.route.movement_detail`
- `inventario.route.reconciliation_operacion_hfc`

Perfiles de respuesta nuevos agregados:

- `inventory.serial.dimension.summary`
- `inventory.risk.serial.detail`
- `inventory.consumption.top.summary`
- `inventory.movement.detail`
- `inventory.reconciliation.operacion_hfc`

Evals anti-hardcode ampliadas con variaciones semanticas:

- `ingreso del codigo 1025507`
- `equipos por estado`
- `equipos serializados en consumo movil sin validar`
- `top de consumos de materiales en mayo`
- `comparativo de consumo tecnico contra facturacion hfc`

Conclusion operativa actualizada:

- ya es seguro retirar un primer bloque legacy puntual para estos 5 templates activos si se hace de forma acotada y con esta misma suite como guardrail
- aun no es seguro retirar `_resolve_inventory_template_legacy` completo
- deben mantenerse cubiertos los casos ambiguos no declarativos y los templates legacy no activos que siguen fuera del pack

## Estado 2026-05-24 Fase 2.3 retiro acotado de legacy shadow fallback

Estado posterior al recorte focal:

- se retiraron de `_resolve_inventory_template_legacy` las ramas especificas de:
  - `inventory_consumption_billing_operacion_hfc`
  - `inventory_consumption_top`
  - `inventory_movement_detail`
  - `inventory_risk_consumo_movil_sin_validar`
  - `inventory_serial_stock_by_dimension`
- esos 5 templates deben resolverse solo por `semantic_bindings.selection_rules`
- la suite ahora falla si alguno vuelve a resolverse por legacy shadow fallback

Cobertura declarativa final confirmada:

- `capability_pack_coverage = 1.0`
- `templates_pack_driven_count = 16`
- `templates_legacy_allowed_count = 0`
- `templates_missing_selection_rules = []`
- conteo derivado `templates_missing_selection_rules = 0`

Trazabilidad obligatoria preservada para templates migrados:

- `source = capability_pack`
- `legacy_mapping_used = false`
- `fallback_used = false`

Legacy retenido y motivo documentado:

- `legacy_retained_reason = requiere aclaracion estructural`
  - aplica a ambiguedades no declarativas como nombres propios sin identificador verificable
- `legacy_retained_reason = compatibilidad temporal fuera del alcance activo`
  - aplica a templates futuros o no activos que aun no tienen `selection_rules`
- `legacy_retained_reason = rescate controlado ante pack incompleto`
  - aplica a rutas no retiradas en esta fase para mantener seguridad operativa

## Estado 2026-05-24 Fase 2.4 validacion ampliada de cierre

Estado posterior a la ampliacion de evals anti-hardcode:

- la suite focal ya no valida solo cobertura general
- ahora publica una matriz explicita con los `12` casos minimos de cierre operativo
- todos los casos pack-driven exigidos deben dejar:
  - `source = capability_pack`
  - `legacy_mapping_used = false`
  - `fallback_used = false`
- la ambiguedad permitida `que tiene Juan Perez` queda trazada como:
  - `source = aclaracion_controlada`
  - `legacy_retained_reason = requiere_aclaracion_estructural_por_portador_no_verificable`

Matriz minima ya validada:

- `inventario_generico_por_movil_cuadrilla`
- `inventario_por_cedula`
- `kardex_por_empleado`
- `kardex_codigo_mas_empleado`
- `seriales_equipos_por_familia`
- `consumo_vs_facturacion_operacion_hfc`
- `top_consumos`
- `movement_detail`
- `riesgo_consumo_movil_sin_validar`
- `serial_stock_por_dimension`
- `materiales_criticos`
- `consulta_ambigua_rescate_permitido`

Cobertura declarativa observada por loader + tests + evals despues de esta ampliacion:

- `capability_pack_coverage = 1.0`
- `templates_pack_driven_count = 17`
- `templates_legacy_allowed_count = 0`
- `templates_missing_selection_rules = []`
- `templates_used_by_legacy = []`

Regresion adicional cerrada dentro del mismo dominio:

- se detecto una desviacion en consultas de consumo operativo por movil/mes
- se formalizo en el pack la ruta `inventory_consumption_by_dimension`
- esto evita recaer a plantilla generica y mantiene la resolucion gobernada sin tocar planner ni SQL libre

Conclusiones operativas:

- ya no queda legacy activo en la superficie cubierta por la matriz minima
- el legacy shadow fallback permanece solo para:
  - aclaraciones estructurales controladas
  - compatibilidad temporal fuera del alcance activo cubierto
  - rescate de seguridad si apareciera una superficie no declarativa futura

## 2. Criterios de clasificacion usados

### A. `authoritative_layer`

- La regla ya opera como autoridad vigente porque esta alineada con contrato, registry, planner o Capability Pack.
- Puede seguir en codigo si su rol es interpretar metadata gobernada y no inventar negocio.

### B. `assistive_heuristic`

- Ayuda a inferir, normalizar o pedir aclaracion.
- No debe ser la ultima autoridad de ejecucion.
- Debe poder perder contra `dd_*`, `SemanticCapabilityRegistry`, contrato o planner.

### C. `shadow_fallback`

- Se activa para rescatar ruta, copy o clasificacion cuando falta metadata o la cobertura aun no es total.
- Debe quedar trazado y con plan explicito de retiro.

### D. `compatibility_layer`

- Duplicado legacy o puente temporal entre metadata gobernada y runtime actual.
- No deberia crecer con nuevas reglas de negocio.

### E. `technical_guardrail`

- Protege SQL, archivos, volumen, approvals, isolation, background, limitacion controlada o sanitizacion.
- Debe permanecer en codigo, aunque algunos mensajes o parametros puedan declararse tambien en metadata.

## 3. Hallazgos por categoria

| ID | Archivo | Funcion/clase | Regla actual | Categoria | Dominio | Riesgo | Puede migrarse a metadata | Destino sugerido | Prioridad | Criterio de aceptacion para migrarla |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| H01 | `apps/ia_dev/application/semantic/semantic_capability_registry.py` | `INVENTORY_TEMPLATE_BINDINGS` | Registry central con `template_id -> capability/route/response_profile/columns` para inventario. | `authoritative_layer` | `inventario_logistica` | medio | parcial | `Capability Pack`, `SemanticCapabilityRegistry` | media | El pack debe exponer el mismo binding y el registry solo leerlo, sin perder `template_id`, `route_hint` ni `response_profile`. |
| H02 | `apps/ia_dev/application/semantic/semantic_capability_registry.py` | `_governed_rule_matches` | Evalua condiciones gobernadas (`intent`, `field_any_of`, `group_by_any_of`, `holder_scope_required`, familia, etc.). | `authoritative_layer` | `inventario_logistica` | medio | no completa | mantener en `SemanticCapabilityRegistry` | media | La logica puede quedarse si solo interpreta `dd_reglas` y no agrega nuevas ramas de negocio fuera de metadata. |
| H03 | `apps/ia_dev/application/semantic/semantic_orchestrator_service.py` | `ROUTE_BY_STRATEGY` | Traduce `strategy` declarada en contrato a `recommended_route`. | `authoritative_layer` | transversal | bajo | parcial | `SemanticCapabilityRegistry`, `Capability Pack` | baja | La tabla de estrategias debe salir de contrato/pack o permanecer minima y sin reglas de negocio nuevas. |
| H04 | `apps/ia_dev/services/intent_arbitration_service.py` | `SUPPORTED_INTENTS` | Taxonomia cerrada de intenciones finales del runtime. | `authoritative_layer` | transversal | bajo | no prioritaria | mantener en codigo como policy | baja | Solo cambiar si existe politica versionada del runtime con coverage de contratos y evaluaciones. |
| H05 | `apps/ia_dev/application/semantic/query_intent_resolver.py` | `_EMPLOYEE_*`, `_TEMPORAL_REFERENCE_RE`, `_MISSINGNESS_OPERATOR_RE` | Regex para detectar estado activo/inactivo, temporalidad y faltantes de dato. | `assistive_heuristic` | `empleados`, `ausentismo` | medio | si | `dd_sinonimos`, `dd_reglas`, `eval anti-hardcode` | alta | Debe existir sinonimia y regla gobernada equivalente; la heuristica solo puede quedar como apoyo con traza. |
| H06 | `apps/ia_dev/application/semantic/query_intent_resolver.py` | `_INVENTORY_DOMAIN_SIGNAL_RE`, `_INVENTORY_EMPLOYEE_STOCK_RE`, `_resolve_domain` | Detecta lenguaje fuerte de inventario y cruces inventario-empleado para orientar dominio. | `assistive_heuristic` | `inventario_logistica`, `empleados` | medio | si | `dd_sinonimos`, `dd_reglas`, `Capability Pack` | alta | La decision principal debe salir de metadata/registry; la regex puede quedar solo como scorer inicial. |
| H07 | `apps/ia_dev/application/semantic/query_intent_resolver.py` | `_apply_common_business_typos` | Normaliza typos de negocio como `empelados`, `cantididad`, `vacasiones`. | `assistive_heuristic` | transversal | bajo | si | `dd_sinonimos` | media | Los alias corregidos deben existir en sinonimia gobernada y el normalizador no debe crecer por archivo Python. |
| H08 | `apps/ia_dev/application/semantic/semantic_orchestrator_service.py` | `_is_real_ambiguity`, `_missing_filter_question` | Detecta una ambiguedad puntual y redacta aclaraciones especificas por capability. | `assistive_heuristic` | `inventario_logistica`, transversal | bajo | si | `Capability Pack`, `dd_reglas` | media | Las preguntas de aclaracion deben salir de perfil o regla declarada por capability. |
| H09 | `apps/ia_dev/services/intent_arbitration_service.py` | `_resolve_temporal_filter` | Mapea meses en texto (`enero`, `febrero`, `este mes`) a filtro temporal util. | `assistive_heuristic` | `empleados`, `ausentismo` | bajo | si | `dd_sinonimos`, `dd_reglas` | media | Debe haber cobertura de sinonimos temporales y tests anti-hardcode equivalentes. |
| H10 | `apps/ia_dev/domains/inventario_logistica/validador_seriales_proveedor.py` | `LectorArchivoTabularProveedor`, `_detect_provider_columns`, `_serial_value_confidence` | Heuristica contextual para detectar columna serial, encabezados variantes y serial valido en archivo de proveedor. | `assistive_heuristic` | `inventario_logistica` | bajo | parcial | `Capability Pack`, `eval anti-hardcode` | media | Puede quedarse como heuristica contextual siempre que no invente evidencia, conserve serial original y deje trazabilidad. |
| H11 | `apps/ia_dev/application/semantic/query_intent_resolver.py` | `_resolve_rules` | Si la consulta de rotacion no trae referencia temporal y el periodo queda en `hoy`, fuerza ventana de 30 dias. | `shadow_fallback` | `empleados` | alto | si | `dd_reglas` | alta | La regla de ventana por defecto debe declararse en metadata y quedar evidenciada en el plan semantico. |
| H12 | `apps/ia_dev/application/semantic/semantic_orchestrator_service.py` | `_looks_external_pending` | Tokens `sap`, `spa`, `acta`, `compras` fuerzan `external_pending` en inventario. | `shadow_fallback` | `inventario_logistica` | medio | si | `dd_reglas`, `Capability Pack` | alta | Debe existir regla gobernada que explique por que se bloquea ejecucion y que capability pendiente aplica. |
| H13 | `apps/ia_dev/services/intent_arbitration_service.py` | `_apply_minimal_policy`, `_is_inventory_employee_stock_query` | Caso especial que fuerza `analytics_query + inventario_logistica` para frases tipo saldo del empleado/tecnico con identificador. | `shadow_fallback` | `inventario_logistica`, `empleados` | alto | si | `SemanticCapabilityRegistry`, `dd_reglas`, `eval anti-hardcode` | alta | El runtime debe llegar a la misma decision por metadata gobernada sin el bypass especial. |
| H14 | `apps/ia_dev/application/orchestration/chat_application_service.py` | `_runtime_only_fallback_copy` | Copy de limitacion para `unsupported_metric`, `unsupported_dimension`, `missing_dictionary_*`, `unsafe_sql_plan`. | `shadow_fallback` | transversal | medio | parcial | `Capability Pack`, mantener copy critica en codigo | media | El motivo tecnico debe seguir en codigo; el texto de negocio puede declararse por policy/pack. |
| H15 | `apps/ia_dev/application/delegation/domain_registry.py` | `DOMAIN_ALIASES` | Alias de dominio como `rrhh -> empleados`, `inventario -> inventario_logistica`, `attendance -> ausentismo`. | `compatibility_layer` | transversal | alto | si | `dd_sinonimos` | alta | La resolucion canonica debe salir de sinonimia gobernada y no solo de un dict Python. |
| H16 | `apps/ia_dev/application/delegation/domain_registry.py` | `DOMAIN_KEYWORDS`, `resolve_domain`, `resolve_domains_for_message` | Keywords para inferir dominio cuando no alcanza classification o capability. | `compatibility_layer` | transversal | medio | si | `dd_sinonimos`, `Capability Pack` | alta | El ranking de dominios debe apoyarse en sinonimia/metadata por dominio y no en listas manuales. |
| H17 | `apps/ia_dev/application/semantic/semantic_orchestrator_service.py` | `_mapear_intencion_inventario` | Traduce salida de matcher gobernado a `intent_id` internos legacy. | `compatibility_layer` | `inventario_logistica` | alto | si | `SemanticCapabilityRegistry`, `Capability Pack` | alta | El matcher o registry deben devolver el `intent_id` canonico final sin tabla de conversion manual. |
| H18 | `apps/ia_dev/application/semantic/semantic_capability_registry.py` | `_resolve_inventory_template` | Ladder de `if` que asigna template por intent, filtros, familia, `group_by`, concepto y stock scope. | `compatibility_layer` | `inventario_logistica` | alto | si | `dd_reglas`, `Capability Pack`, `SemanticCapabilityRegistry` | alta | Debe resolverse por reglas gobernadas leidas por registry; el `if` solo deberia interpretar condiciones declaradas. |
| H19 | `apps/ia_dev/application/semantic/semantic_capability_registry.py` | `_resolve_inventory_template_legacy` | Mapa legacy de templates de inventario para asegurar compatibilidad. | `compatibility_layer` | `inventario_logistica` | alto | si | `Capability Pack`, `eval anti-hardcode` | alta | Solo retirarlo cuando exista paridad demostrada por evals y cobertura de `dd_reglas`/pack. |
| H20 | `apps/ia_dev/services/intent_arbitration_service.py` | `_concept_aliases_from_dictionary` | Lista fija de conceptos soportados (`birthday`, `tenure`, `turnover`) para enlazar campos de empleados. | `compatibility_layer` | `empleados` | alto | si | `dd_campos`, `dd_sinonimos`, `dd_relaciones` | alta | Los conceptos y aliases deben poder salir enteramente del diccionario gobernado sin whitelist Python. |
| H21 | `apps/ia_dev/application/semantic/query_intent_resolver.py` | `_ATTENDANCE_REASON_SIGNALS` | Mapea tokens de justificacion (`vacaciones`, `incapacidad`, `licencia`, `permiso`, `calamidad`) a canonicos. | `compatibility_layer` | `ausentismo` | medio | si | `dd_sinonimos`, `dd_reglas` | alta | Debe leerse desde metadata del dominio y coincidir con `ausentismo_tipo_por_justificacion`. |
| H22 | `apps/ia_dev/application/contracts/agent_contracts/*.yaml` | `routing_rules.deterministic_patterns` | Contratos de agentes conservan patrones deterministicos por dominio para enrutar. | `compatibility_layer` | `inventario_logistica`, `empleados`, `ausentismo` | medio | si | `Capability Pack`, `dd_sinonimos` | media | Los patrones deben ser declarativos, trazables y consumidos por una sola capa de routing. |
| H23 | `apps/ia_dev/application/semantic/query_execution_planner.py` | `SAFE_IDENTIFIER_RE`, `TRAILING_LIMIT_RE`, `_is_safe_identifier`, `_inventory_tipo_filter_sql`, `INVENTORY_QUANTITY_NUMERIC_RE` | Sanitizacion de identificadores, control de `LIMIT`, casting seguro y armado de filtro SQL de tipo. | `technical_guardrail` | transversal, `inventario_logistica` | bajo | no | mantener en codigo como guardrail | alta | Debe seguir en codigo y toda migracion futura debe preservar validacion y escaping equivalentes. |
| H24 | `apps/ia_dev/application/semantic/query_execution_planner.py` | `_cleanup_blocks_legacy_analytics_fallback`, `_productive_pilot_enabled_for_domain` | Bloquea recaidas silenciosas al legacy segun flags de rollout y cobertura analitica. | `technical_guardrail` | transversal | medio | no | mantener en codigo como guardrail | alta | Solo tocar con pruebas de rollout y evidencia de no regresion operacional. |
| H25 | `apps/ia_dev/application/semantic/query_execution_planner.py` | `_should_prefer_capability_strategy` | Si hay adjunto y `template_id=inventory_provider_serial_validation`, obliga handler gobernado antes de SQL. | `technical_guardrail` | `inventario_logistica` | bajo | no | mantener en codigo como guardrail | alta | Debe seguir protegiendo la ruta segura basada en archivo y background. |
| H26 | `apps/ia_dev/application/orchestration/chat_application_service.py` | `_apply_memory_policy` | `domain_guarded_keys` y bloqueo de hints cross-domain para no contaminar memoria entre dominios. | `technical_guardrail` | transversal | medio | no | mantener en codigo como guardrail | alta | La memoria cruzada debe seguir bloqueada salvo handoff explicito y trazado. |
| H27 | `apps/ia_dev/domains/inventario_logistica/validador_seriales_proveedor.py` | `_DB_LOOKUP_CHUNK_SIZE`, `_safe_union_chunk_size`, `_execute_serial_lookup` | Chunking, fallback normalizado controlado y lookup seguro para archivos grandes. | `technical_guardrail` | `inventario_logistica` | bajo | no | mantener en codigo como guardrail | alta | Debe conservar procesamiento en background, chunking y trazabilidad por chunk. |
| H28 | `apps/ia_dev/application/orchestration/chat_application_service.py` | `_planner_block_reason_to_business_text` | Convierte `block_reason` tecnicos a copy segura y no filtrante para usuario. | `technical_guardrail` | transversal | bajo | parcial | mantener en codigo como guardrail | media | La politica user-safe debe permanecer; el wording puede externalizarse sin exponer debug tecnico. |

## 4. Hallazgos por dominio

### `inventario_logistica`

- Mayor avance metadata-first, pero todavia conviven tres capas: metadata gobernada, binding Python de registry y fallback legacy.
- Criticos: `H12`, `H13`, `H17`, `H18`, `H19`.
- Regla especial aceptable: `H10` y `H27` para `inventory_provider_serial_validation`. La deteccion heuristica de columnas/seriales no se clasifica como hardcode malo mientras no invente evidencia, valide contra datos y mantenga chunking/background seguro.

### `empleados`

- Tiene contrato de agente y reglas YAML, pero mantiene bastante semantica operacional en regex y listas duras.
- Criticos: `H05`, `H11`, `H15`, `H20`.
- Principal brecha: falta que sinonimia, conceptos y defaults temporales/organizacionales salgan de `dd_*` o un pack equivalente.

### `ausentismo`

- Tiene contrato y reglas declaradas, pero sigue dependiendo de mapeos Python para justificaciones y de heuristicas compartidas con empleados.
- Criticos: `H05`, `H21`, `H22`.
- Principal brecha: las reglas de justificacion y dimension deberian centralizarse y dejar de vivir duplicadas entre YAML y Python.

### Transversal

- Criticos: `H14`, `H15`, `H16`, `H23`, `H24`, `H26`, `H28`.
- La migracion no debe tocar guardrails de planner, memoria, limitaciones controladas ni rollout.

## 5. Hallazgos criticos

- `H18`: `_resolve_inventory_template` sigue decidiendo negocio de inventario con ladder Python aunque ya existe metadata gobernada del dominio.
- `H19`: `_resolve_inventory_template_legacy` conserva el mapa legacy mas sensible del binding inventario.
- `H13`: el caso especial de arbitraje para saldo por empleado/tecnico sigue bypassando parcialmente la autoridad de metadata.
- `H15` y `H16`: `DomainRegistry` aun puede decidir dominio por alias/keywords fuera de metadata gobernada.
- `H20` y `H21`: empleados y ausentismo siguen con conceptos y canonicos relevantes embebidos en Python.

## 6. Reglas que NO deben eliminarse porque son guardrails tecnicos

- `H23`: sanitizacion SQL, control de `LIMIT`, regex de identificadores y casting seguro.
- `H24`: bloqueo de fallback legacy segun rollout y cobertura.
- `H25`: ruta obligatoria a handler seguro para `inventory_provider_serial_validation` con adjuntos.
- `H26`: aislamiento de memoria entre dominios.
- `H27`: chunking, fallback normalizado controlado y procesamiento robusto de archivos grandes.
- `H28`: traduccion de errores tecnicos a mensajes seguros para usuario final.

## 7. Reglas que pueden migrarse a `dd_sinonimos`

- `H05`: estado activo/inactivo, faltantes de dato, vocabulario temporal frecuente.
- `H06`: lenguaje fuerte de inventario y aliases de portador.
- `H07`: typos de negocio frecuentes.
- `H09`: meses y referencias temporales comunes.
- `H15`: alias de dominio.
- `H16`: keywords de dominio.
- `H20`: aliases de conceptos de empleados.
- `H21`: justificaciones de ausentismo.
- `H22`: patrones deterministicos contractuales, si se desea centralizar vocabulario por dominio.

## 8. Reglas que pueden migrarse a `dd_reglas`

- `H05`: reglas de inferencia de estado, agregacion y missingness.
- `H08`: aclaraciones por capability y ambiguedad recurrente.
- `H11`: default temporal de rotacion a 30 dias.
- `H12`: pending external por SAP/SPA/acta/compras.
- `H13`: regla especial saldo por empleado/tecnico.
- `H18`: resolucion de template por intent/filtros/familia/group_by.
- `H21`: mapeo de justificacion en ausentismo.

## 9. Reglas que pueden migrarse a `ia_dev_capacidades_columna`

- `H18`: condiciones basadas en `cedula`, `movil`, `bodega`, `serial`, `codigo`, `descripcion`, `tipo`.
- `H20`: conceptos empleados ligados a columnas semanticas concretas.
- Parte de `H05` y `H21` cuando el filtro final depende de columnas soportadas y no solo de sinonimia.

## 10. Reglas que deben moverse a Capability Packs

- `H01`: binding declarativo de template/capability/response profile.
- `H03`: estrategias y rutas si se quiere declararlas por dominio.
- `H08`: preguntas de aclaracion por capability.
- `H12`: limitaciones `external_pending`.
- `H17`: conversion final de intencion inventario a capability/intent canonico.
- `H18` y `H19`: mapping transitorio de templates.
- `H22`: patrones deterministicos hoy repetidos en contratos.

## 11. Reglas que requieren eval anti-hardcode antes de tocarse

- `H11`: rotacion a 30 dias por defecto.
- `H13`: arbitraje especial inventario-empleado.
- `H15` y `H16`: alias y keywords de dominio.
- `H18` y `H19`: binding de templates de inventario.
- `H20` y `H21`: conceptos de empleados y justificaciones de ausentismo.
- `H10`: heuristica aceptable de archivo proveedor, para asegurar que la migracion no degrade deteccion real.

## 12. Backlog priorizado de migracion

1. Sacar de Python la decision de template inventario hoy repartida entre `H17`, `H18` y `H19`, dejando al `SemanticCapabilityRegistry` como lector de metadata/pack.
2. Migrar alias y keywords de dominio de `H15` y `H16` a sinonimia gobernada con trazabilidad y evals.
3. Migrar conceptos de empleados y justificaciones de ausentismo de `H20` y `H21` a `dd_campos` + `dd_sinonimos` + `dd_reglas`.
4. Declarar en metadata las reglas de aclaracion y pending external de `H08`, `H11` y `H12`.
5. Consolidar patrones deterministicos duplicados en contratos y resolvers (`H22`) para que no crezcan en paralelo.

## 13. Recomendacion de primera fase de implementacion

Primera fase recomendada: inventario metadata-first sin tocar planner ni runtime base.

Secuencia sugerida:

1. Mover el contenido semantico de `H17`, `H18` y `H19` a una fuente declarativa unica del `Capability Pack` de `inventario_logistica`.
2. Hacer que `SemanticCapabilityRegistry` lea primero esa fuente y deje el mapa legacy solo como `shadow_fallback` trazado.
3. Agregar evals anti-hardcode que comparen `template_id`, `candidate_capability`, `planner_route_hint` y `response_profile` contra el comportamiento actual.
4. No tocar `QueryExecutionPlanner`, `fallback_policy`, ni guardrails de `inventory_provider_serial_validation`.

Condicion de salida de fase 1:

- Igualdad observable del binding inventario actual.
- Ningun cambio funcional de runtime.
- Legacy map aun presente, pero reducido a compatibilidad demostrada por evals.
