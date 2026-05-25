# Diagnostico P3-A: Gobierno De Reglas Duras En `inventario_logistica`

## Alcance y supuestos

- Alcance exclusivo: `inventario_logistica`.
- Se asume valido sin reauditar:
  - P1 completado.
  - P2-A completado.
  - P2-B completado.
  - `SemanticCapabilityRegistry` ya existe para `inventario_logistica`.
  - `patterns` quedan como fallback sombreado.
- No se modifica:
  - `QueryExecutionPlanner` como autoridad SQL.
  - `fallback_policy`.
  - `ToolRegistryService`.
  - `OpenAI Gateway`.
  - `Agents Runtime`.
  - approvals.
  - background.
  - frontend.

## Resumen ejecutivo

P3-A confirma que la arquitectura ya esta encaminada a `metadata/capability-first`, pero `inventario_logistica` todavia mantiene deuda semantica importante en Python:

- sinonimia hardcodeada
- regex de identificadores y entidades
- reglas de negocio compuestas mezcladas con extraccion
- `template_id -> capability -> planner_route_hint -> response_profile` todavia materializado en mapas Python
- heuristicas narrativas en `response_assembler`
- ejemplos de tests que hoy validan comportamiento correcto, pero tambien congelan logica heredada

El riesgo principal no esta en el SQL. El riesgo principal esta en que la misma regla de negocio vive duplicada en:

- `matcher_semantico_gobernado_inventario.py`
- `semantic_inventory_resolver.py`
- `semantic_capability_registry.py`
- `business_query_semantic_plan.py`
- `query_intent_resolver.py`
- `semantic_orchestrator_service.py`
- `query_execution_planner.py`
- `response_assembler.py`

La meta de P3-B no debe ser una migracion masiva ciega. Debe ser una extraccion gobernada por capas:

1. vocabulario y alias a `dd_sinonimos`
2. reglas semanticas reutilizables a `dd_reglas`
3. conceptos y vistas logicas a `dd_campos`
4. bindings `intent/entity/filter/output -> capability` a `ia_dev_capacidades_columna`
5. dependencias de enrichment y cobertura a `dd_relaciones`
6. validaciones tecnicas y regex de saneamiento se quedan en codigo

## 1. Mapa actual de reglas duras

### `backend/apps/ia_dev/domains/inventario_logistica/matcher_semantico_gobernado_inventario.py`

Reglas duras detectadas:

- sinonimos base hardcodeados:
  - `inventario|stock|saldo|existencia|que tiene`
  - `movil|cuadrilla|brigada`
  - `kardex|movimientos|entradas y salidas`
  - `material claro|material de claro`
  - `ferretero|ferreteria|material ferretero`
  - `serial|seriales|serializado|equipos|cpe`
  - `tecnico|empleado|cedula`
  - `sap|acta|actas`
- lista `_PALABRAS_NO_CODIGO` para bloquear falsos positivos de `codigo`
- regla `identificador numerico => cedula`
- regla `identificador alfanumerico => movil`
- regla `material claro => tipo=material`
- regla `ferretero => tipo=ferretero`
- regla `material generico => tipo in (material, ferretero)`
- regla `kardex + cedula => inventory_kardex_by_employee`
- regla `kardex + codigo => inventory_kardex_consolidated`
- regla `actas/SAP + portador => limitacion declarada`
- regla `inventario generico por movil/cuadrilla => inventory_material_stock_mobile`
- regla `serializados explicitados => inventory_serial_by_operational_holder`
- regla `inventario generico sin familia explicita + movil => incluye serializados`
- regex y heuristicas de extraccion:
  - cedula
  - movil
  - codigo
  - nombre probable

Referencias clave:

- `matcher_semantico_gobernado_inventario.py:11`
- `matcher_semantico_gobernado_inventario.py:24`
- `matcher_semantico_gobernado_inventario.py:87`
- `matcher_semantico_gobernado_inventario.py:91`
- `matcher_semantico_gobernado_inventario.py:99`
- `matcher_semantico_gobernado_inventario.py:102`
- `matcher_semantico_gobernado_inventario.py:105`
- `matcher_semantico_gobernado_inventario.py:124`
- `matcher_semantico_gobernado_inventario.py:258`
- `matcher_semantico_gobernado_inventario.py:303`

### `backend/apps/ia_dev/domains/inventario_logistica/semantic_inventory_resolver.py`

Reglas duras detectadas:

- `_resolve_inventory_type_filter(...)`
- `_resolve_material_family(...)`
- `_resolve_group_by(...)`
- `_extract_serial(...)`
- `_extract_operational_identifier(...)`
- `_extract_code(...)`
- `_extract_cedula(...)`
- `_extract_warehouse(...)`
- `MATERIAL_CODE_STOPWORDS`
- gran arbol `if/elif` de intents y `business_concept`
- rutas heredadas para:
  - `document_generation`
  - `external_reconciliation_query`
  - `reconciliation_query`
  - `notification_query`
  - `report_generation`
  - `assignment_distribution_query`
  - `alert_query`
  - `movement_history`
  - `risk_detection`
  - `traceability_query`
  - `stock_balance`
  - `serial_holder_query`
  - `consumption_query`
  - `return_query`
- heuristica `operacion_hfc => bodega`
- reglas de limitacion:
  - `missing_physical_column:bodega_destino`
  - `serializados_employee_kardex_not_available`
  - `document_generation_pending`
  - `external_source_pending:sap`

Referencias clave:

- `semantic_inventory_resolver.py:50`
- `semantic_inventory_resolver.py:101`
- `semantic_inventory_resolver.py:114`
- `semantic_inventory_resolver.py:127`
- `semantic_inventory_resolver.py:139`
- `semantic_inventory_resolver.py:148`
- `semantic_inventory_resolver.py:164`
- `semantic_inventory_resolver.py:174`
- `semantic_inventory_resolver.py:183`
- `semantic_inventory_resolver.py:315`
- `semantic_inventory_resolver.py:332`
- `semantic_inventory_resolver.py:536`
- `semantic_inventory_resolver.py:613`

### `backend/apps/ia_dev/application/semantic/semantic_capability_registry.py`

Reglas duras detectadas:

- `INVENTORY_TEMPLATE_BINDINGS`
- `INVENTORY_INTENT_IDS_BY_TEMPLATE`
- `_resolve_inventory_template(...)`
- `_resolve_inventory_template_legacy(...)`
- `_build_output_profile(...)`
- `_resolve_response_profile(...)`
- bindings hardcodeados:
  - `template_id -> candidate_capability`
  - `template_id -> planner_route_hint`
  - `template_id -> response_profile`
  - `template_id -> expected_output`
  - `template_id -> grain`
  - `template_id -> columns`
- regla `inventory_material_stock_mobile + include_serialized + no tipo => response_profile dual_block`
- fallback heredado `legacy_inventory_template_map`

Referencias clave:

- `semantic_capability_registry.py:26`
- `semantic_capability_registry.py:293`
- `semantic_capability_registry.py:451`
- `semantic_capability_registry.py:471`
- `semantic_capability_registry.py:611`
- `semantic_capability_registry.py:709`
- `semantic_capability_registry.py:756`
- `semantic_capability_registry.py:781`

### `backend/apps/ia_dev/domains/inventario_logistica/business_query_semantic_plan.py`

Reglas duras detectadas:

- `INVENTORY_SEMANTIC_MATRIX`
- `CONFIRMED_INVENTORY_MEMORY_RULES`
- `_resolve_capability(...)`
- `_resolve_scope_families(...)`
- `_should_include_serialized(...)`
- `_resolve_output_profile(...)`
- `_expected_output_for_capability(...)`
- `_applicable_rules(...)`
- `_possible_alerts(...)`

La mayoria ya son reglas formalizadas, pero siguen persistidas como listas Python y no como metadata auditable en `dd_*`.

Referencias clave:

- `business_query_semantic_plan.py:19`
- `business_query_semantic_plan.py:92`
- `business_query_semantic_plan.py:304`
- `business_query_semantic_plan.py:385`
- `business_query_semantic_plan.py:438`
- `business_query_semantic_plan.py:458`
- `business_query_semantic_plan.py:478`
- `business_query_semantic_plan.py:572`

### `backend/apps/ia_dev/application/semantic/query_intent_resolver.py`

Reglas duras detectadas:

- regex de dominio inventario `_INVENTORY_DOMAIN_SIGNAL_RE`
- regex `saldo empleado <cedula>` `_INVENTORY_EMPLOYEE_STOCK_RE`
- `natural_inventory_stock`
- `_resolve_template_id(...)` con mapping inventario por texto
- `_extract_entity(...)`
- `_extract_filters(...)`
- `_extract_group_by(...)`
- `_is_inventory_operational_cross_query(...)`
- override:
  - `registry_binding.template_id`
  - luego `match_gobernado.template_id`

Esto confirma que `query_intent_resolver` todavia no esta limpio de routing semantico inventario.

Referencias clave:

- `query_intent_resolver.py:56`
- `query_intent_resolver.py:64`
- `query_intent_resolver.py:178`
- `query_intent_resolver.py:268`
- `query_intent_resolver.py:658`
- `query_intent_resolver.py:719`
- `query_intent_resolver.py:732`
- `query_intent_resolver.py:1468`

### `backend/apps/ia_dev/application/semantic/semantic_orchestrator_service.py`

Reglas duras detectadas:

- regex duplicados de inventario:
  - `INVENTORY_EMPLOYEE_STOCK_RE`
  - `INVENTORY_DOMAIN_SIGNAL_RE`
- `_extract_filters(...)`
- `_extract_entities(...)`
- `_extract_dimensions(...)`
- `_extract_metrics(...)`
- `_resolve_intent_and_capability(...)`
- `_mapear_intencion_inventario(...)`
- `_resolve_scope(...)`
- `_looks_external_pending(...)`
- `_missing_filter_question(...)`

El orquestador sigue redecidiendo semantica que ya deberia venir gobernada desde registry.

Referencias clave:

- `semantic_orchestrator_service.py:44`
- `semantic_orchestrator_service.py:47`
- `semantic_orchestrator_service.py:178`
- `semantic_orchestrator_service.py:284`
- `semantic_orchestrator_service.py:491`
- `semantic_orchestrator_service.py:606`
- `semantic_orchestrator_service.py:629`
- `semantic_orchestrator_service.py:647`
- `semantic_orchestrator_service.py:665`
- `semantic_orchestrator_service.py:1092`

### `backend/apps/ia_dev/application/semantic/query_execution_planner.py`

Reglas duras detectadas:

- `_resolve_capability_id(...)` mantiene mapeo heredado por `template_id`
- `_build_inventory_material_stock_sql(...)`
- `_inventory_should_group_balance_by_employee(...)`
- `_inventory_requires_dual_inventory_blocks(...)`
- `_inventory_build_unspecified_family_supplemental_queries(...)`
- `_inventory_tipo_filter_sql(...)`
- `INVENTORY_QUANTITY_NUMERIC_RE`
- `serializados_employee_kardex_not_available`
- `operacion_hfc` hardcodeado en reconciliacion de consumo/facturacion

Importante:

- formulas SQL
- casteo numerico
- estructura de supplemental queries
- guardrails de seguridad

deben permanecer en codigo. Eso no es deuda semantica pura; es compilacion segura.

Referencias clave:

- `query_execution_planner.py:33`
- `query_execution_planner.py:841`
- `query_execution_planner.py:1722`
- `query_execution_planner.py:1872`
- `query_execution_planner.py:1924`
- `query_execution_planner.py:1948`
- `query_execution_planner.py:2574`
- `query_execution_planner.py:2638`
- `query_execution_planner.py:3550`
- `query_execution_planner.py:5367`

### `backend/apps/ia_dev/application/runtime/runtime_capability_adapter.py`

Estado:

- para inventario ya consume `semantic_capability_registry` primero
- no vuelve a inventar capability si el binding semantico existe

Deuda residual:

- mantiene puente heredado para otros dominios
- todavia materializa `capability_id/tool_id` como plan runtime, pero no es el foco de P3-A inventario

Referencias:

- `runtime_capability_adapter.py:578`
- `runtime_capability_adapter.py:622`
- `runtime_capability_adapter.py:637`

### `backend/apps/ia_dev/domains/inventario_logistica/response_assembler.py`

Reglas duras detectadas:

- `_inventory_type_scope_label(...)`
- narrativa condicionada por `row_keys`
- narrativa especial para:
  - materiales criticos
  - kardex empleado
  - stock por tecnico/cuadrilla
  - saldo por movil
  - stock bodega
- lectura directa de:
  - `template_id`
  - `candidate_capability`
  - `planner_route_hint`
  - `response_profile`
- mensaje hardcodeado de limitacion `serializados_employee_kardex_not_available`

Esto no debe migrarse completo a metadata ahora, pero si debe dejar de ser autoridad semantica primaria.

Referencias clave:

- `response_assembler.py:6`
- `response_assembler.py:85`
- `response_assembler.py:125`
- `response_assembler.py:145`
- `response_assembler.py:161`
- `response_assembler.py:218`

### Tests de inventario

Los tests hoy cumplen dos funciones:

- validan comportamiento correcto
- congelan reglas hardcodeadas

Casos canonizados activos:

- `TIRAN224`
- `5098747`
- `material claro`
- `ferretero`
- `actas SAP`
- `bodega destino`
- `operacion_hfc`
- `inventory_material_stock_mobile`
- `inventory_kardex_by_employee`
- `inventory_document_generation_pending`
- `inventory_transfer_destination_not_available`

Referencias:

- `test_semantic_capability_registry.py`
- `test_semantic_orchestrator_service.py`
- `test_inventory_response_assembler.py`
- `test_inventory_business_query_semantic_plan.py`
- `test_inventario_semantic_resolver.py`

## 2. Clasificacion de reglas

### 1. Debe migrar a `dd_sinonimos`

- alias de `inventario|stock|saldo|existencia`
- alias de `movil|cuadrilla|brigada`
- alias de `kardex|movimientos|entradas y salidas`
- alias de `material claro|material de claro`
- alias de `ferretero|ferreteria|material ferretero`
- alias de `serial|seriales|serializados|equipos|cpe`
- alias de `tecnico|empleado|cedula` cuando actuan como lenguaje de negocio
- alias de `sap|acta|actas|documentos` para limitacion documental

### 2. Debe migrar a `dd_reglas`

- `identificador numerico => cedula`
- `identificador alfanumerico operativo => movil`
- `material claro => tipo=material`
- `ferretero => tipo=ferretero`
- `material generico => tipo in (material, ferretero)`
- `inventario generico => dual block materiales + serializados`
- `serializados => conteo, no cantidad`
- `saldo de inventario incluye positivos, cero y negativos`
- `kardex por empleado si hay cedula`
- `kardex consolidado si hay codigo y no cedula`
- `kardex entrega suma; devolucion/consumo/cobro restan`
- `actas SAP/documentos => capability pending + external_pending`
- `traslados por bodega destino => blocked por metadata faltante`
- `consumo vs facturacion solo productivo con bodega=operacion_hfc`

### 3. Debe migrar a `dd_relaciones`

- regla de enrichment `movil -> cedulas` via `cinco_base_de_personal`
- cobertura de `cedula -> personal historico` sin filtrar solo `ACTIVO`
- dependencia `movimientos materiales -> base_codigos`
- dependencia `serializados -> base_codigo_seriales`
- dependencia `serializados por portador -> personal`
- dependencia `kardex empleado -> personal + catalogo`

### 4. Debe migrar a `ia_dev_capacidades_columna`

- `stock_balance + entity=cedula/movil -> inventory_stock_balance_by_mobile`
- `stock_balance + scope=bodega -> inventory_stock_balance_by_warehouse`
- `movement_history + cedula -> inventory_kardex_by_employee`
- `movement_history + codigo -> inventory_kardex_consolidated`
- `serial_holder_query + serial/cedula/movil -> inventory_serial_by_operational_holder`
- `traceability_query + serial -> inventory_traceability_by_serial`
- `risk_detection + serializados -> inventory_risk_consumo_movil_sin_validar`
- `consumption_query -> inventory_consumption_top|inventory_consumption_by_dimension`

### 5. Debe permanecer en codigo por ser validacion tecnica

- regex de saneamiento de SQL-safe identifiers
- regex numerico de cantidad `INVENTORY_QUANTITY_NUMERIC_RE`
- casteo numerico y proteccion ante cantidad invalida
- armado SQL seguro
- joins efectivos de compilacion
- `HAVING`, `ORDER BY`, `LIMIT`, supplemental query execution
- deduccion tecnica de `row_keys` para redactar respuesta mientras no exista perfil estructurado completo
- deteccion de nombre probable solo como guardrail de aclaracion
- stopwords tecnicas para no confundir `codigo`

### 6. Puede quedar como fallback sombreado temporal

- `_resolve_inventory_template_legacy(...)`
- `_resolve_capability(...)` heredado en `business_query_semantic_plan.py`
- `_resolve_template_id(...)` heredado en `query_intent_resolver.py`
- `_resolve_intent_and_capability(...)` heredado en `semantic_orchestrator_service.py`
- heuristicas de `response_assembler` por `row_keys`

Condicion:

- deben emitir traza de `legacy_mapping_used`, `fallback_used` o razon equivalente
- no deben ser autoridad cuando exista binding gobernado

### 7. Es hardcode critico a eliminar

- `INVENTORY_TEMPLATE_BINDINGS` como unica autoridad de negocio
- `INVENTORY_INTENT_IDS_BY_TEMPLATE`
- duplicacion de regex de dominio inventario en `query_intent_resolver` y `semantic_orchestrator_service`
- duplicacion de `template_id -> capability` en planner
- duplicacion de `intent/entity/filter -> template` en resolver, intent resolver, registry y orchestrator

## 3. Tabla de migracion regla -> destino `dd_*`

| Regla actual | Origen actual | Clasificacion | Destino propuesto | Clave canonica | Ejemplo de registro |
| --- | --- | --- | --- | --- | --- |
| `cuadrilla`, `brigada` => `movil` | matcher | 1 | `dd_sinonimos.alias` | `inventario.entity.movil` | `alias=cuadrilla`, `canonico=movil`, `dominio=inventario_logistica` |
| `kardex`, `movimientos`, `entradas y salidas` | matcher | 1 | `dd_sinonimos.alias` | `inventario.intent.movement_history` | `alias=entradas y salidas`, `canonico=movement_history` |
| `material claro`, `material de claro` | matcher/resolver | 1 | `dd_sinonimos.alias` | `inventario.family.material_claro` | `alias=material de claro`, `canonico=material_claro` |
| `ferretero`, `ferreteria`, `material ferretero` | matcher/resolver | 1 | `dd_sinonimos.alias` | `inventario.family.ferretero` | `alias=ferreteria`, `canonico=ferretero` |
| `serial`, `seriales`, `equipos`, `cpe` | matcher/resolver | 1 | `dd_sinonimos.alias` | `inventario.family.serializados` | `alias=equipos`, `canonico=serializados` |
| numerico operativo => `cedula` | matcher/resolver | 2 | `dd_reglas` | `inventario.identifier.numeric_to_cedula` | `condicion={"value_kind":"numeric","min_len":5}`, `resultado={"field":"cedula"}` |
| alfanumerico operativo => `movil` | matcher/resolver | 2 | `dd_reglas` | `inventario.identifier.alphanumeric_to_movil` | `condicion={"value_kind":"alphanumeric","must_have_letters":true,"must_have_digits":true}`, `resultado={"field":"movil"}` |
| `material claro` => `tipo=material` | matcher/resolver | 2 | `dd_reglas` | `inventario.filter.material_claro` | `entrada={"family":"material_claro"}, salida={"tipo":"material"}` |
| `ferretero` => `tipo=ferretero` | matcher/resolver | 2 | `dd_reglas` | `inventario.filter.ferretero` | `entrada={"family":"ferretero"}, salida={"tipo":"ferretero"}` |
| `material` generico => ambos tipos | matcher/resolver | 2 | `dd_reglas` | `inventario.filter.material_generico` | `salida={"tipo":["material","ferretero"]}` |
| inventario generico => dual block | matcher/plan/planner | 2 | `dd_reglas` | `inventario.scope.dual_block_unspecified_family` | `condicion={"intent":"stock_balance","tipo_absent":true,"holder_scope":true}, salida={"include_serialized":true}` |
| serializados usan conteo | matcher/plan | 2 | `dd_reglas` | `inventario.metric.serial_count_only` | `salida={"quantity_mode":"count"}` |
| saldo incluye cero y negativo | matcher/plan | 2 | `dd_reglas` | `inventario.metric.stock_include_zero_negative` | `salida={"allow_zero":true,"allow_negative":true}` |
| kardex empleado por cedula | matcher/registry | 2 | `dd_reglas` + `ia_dev_capacidades_columna` | `inventario.route.kardex_employee` | `condicion={"intent":"movement_history","field":"cedula"}, salida={"template_id":"inventory_kardex_by_employee"}` |
| kardex codigo consolidado | matcher/registry | 2 | `dd_reglas` + `ia_dev_capacidades_columna` | `inventario.route.kardex_codigo` | `condicion={"intent":"movement_history","field":"codigo"}, salida={"template_id":"inventory_kardex_consolidated"}` |
| `movil -> cedulas` | planner/resolver | 3 | `dd_relaciones` | `inventario.rel.movil_to_personal` | `tabla_origen=cinco_base_de_personal`, `campo_origen=movil`, `campo_destino=cedula` |
| materiales + personal historico | planner | 3 | `dd_relaciones` | `inventario.rel.movimientos_to_personal_historico` | `allow_inactive=true` |
| campo logico `movil` | varios | 4 | `dd_campos` | `inventario.campo.movil` | `campo_logico=movil`, `es_identificador=true`, `supports_filter=true` |
| binding `stock_balance + movil/cedula -> inventory_stock_balance_by_mobile` | registry | 4 | `ia_dev_capacidades_columna` | `inventario.cap.stock_balance.holder` | `intent=stock_balance`, `entity_field=movil|cedula`, `capability=inventory_stock_balance_by_mobile` |
| binding `stock_balance + bodega -> inventory_stock_balance_by_warehouse` | registry | 4 | `ia_dev_capacidades_columna` | `inventario.cap.stock_balance.bodega` | `intent=stock_balance`, `entity_field=bodega`, `capability=inventory_stock_balance_by_warehouse` |
| response profile `inventory.stock.mobile.dual_block` | registry | 4 | `ia_dev_capacidades_columna` | `inventario.cap.stock_balance.mobile.response` | `response_profile=inventory.stock.mobile.dual_block`, `planner_route_hint=inventory.material_stock.mobile` |
| actas/SAP como limitacion | matcher/resolver/registry | 2 | `dd_reglas` | `inventario.limit.document_generation_pending` | `condicion={"intent":"document_generation"}, salida={"capability":"inventory_document_generation_pending","availability":"blocked"}` |
| `bodega destino` faltante | resolver/registry | 2 | `dd_reglas` | `inventario.limit.transfer_destination_missing_metadata` | `salida={"template_id":"inventory_transfer_destination_not_available"}` |
| `operacion_hfc` como filtro especial | resolver/planner | 2 y 5 | `dd_sinonimos` + codigo tecnico | `inventario.filter.operacion_hfc` | alias semantico en metadata; enforcement SQL queda en codigo |

## 4. Modelo de datos destino propuesto

### `dd_sinonimos`

Uso:

- vocabulario de usuario
- sinonimia de intents
- sinonimia de familias
- sinonimia de entidades
- sinonimia de limitaciones declaradas

Campos sugeridos:

- `dominio`
- `scope_tipo`
- `scope_clave`
- `alias`
- `canonico`
- `activo`
- `prioridad`
- `source`
- `trace_tag`

Ejemplo:

```json
{
  "dominio": "inventario_logistica",
  "scope_tipo": "entity",
  "scope_clave": "movil",
  "alias": "cuadrilla",
  "canonico": "movil",
  "activo": true,
  "prioridad": 100,
  "trace_tag": "dd_sinonimos:inventario.entity.movil"
}
```

Lectura:

- `SemanticCapabilityRegistry` arma `synonym_index`
- `BusinessQuerySemanticPlan` ya no infiere familias desde texto si el registry ya normalizo

### `dd_reglas`

Uso:

- heuristicas semanticas reutilizables
- bindings compuestos no tecnicos
- limitaciones declaradas
- reglas de salida semantica

Campos sugeridos:

- `dominio`
- `rule_id`
- `rule_kind`
- `intent`
- `entity_field`
- `condition_json`
- `result_json`
- `priority`
- `is_fallback`
- `migration_status`
- `trace_tag`

Ejemplo:

```json
{
  "dominio": "inventario_logistica",
  "rule_id": "inventario.scope.dual_block_unspecified_family",
  "rule_kind": "scope_resolution",
  "intent": "stock_balance",
  "condition_json": {
    "holder_scope_required": true,
    "tipo_absent": true,
    "exclude_tokens": ["kardex", "movimientos"]
  },
  "result_json": {
    "include_serialized": true,
    "response_profile_override": "inventory.stock.mobile.dual_block"
  },
  "priority": 90,
  "is_fallback": false,
  "migration_status": "governed"
}
```

Lectura:

- `SemanticCapabilityRegistry` evalua reglas por prioridad
- `BusinessQuerySemanticPlan` consume `result_json` ya resuelto en `scope`, `applicable_business_rules`, `known_limitations`

### `dd_relaciones`

Uso:

- enrichment
- cruces seguros
- cobertura historica de personal
- dependencia de catalogos

Campos sugeridos:

- `dominio`
- `relation_id`
- `source_table`
- `source_field`
- `target_table`
- `target_field`
- `relation_type`
- `business_purpose`
- `enrichment_policy_json`
- `trace_tag`

Ejemplo:

```json
{
  "dominio": "inventario_logistica",
  "relation_id": "inventario.rel.movil_to_personal",
  "source_table": "bd_c3nc4s1s.cinco_base_de_personal",
  "source_field": "movil",
  "target_table": "bd_c3nc4s1s.cinco_base_de_personal",
  "target_field": "cedula",
  "relation_type": "holder_resolution",
  "business_purpose": "resolver movil a conjunto de cedulas",
  "enrichment_policy_json": {
    "allow_inactive": true,
    "emit_estado_empleado": true
  }
}
```

Lectura:

- `SemanticCapabilityRegistry` solo consulta existencia y politica
- `BusinessQuerySemanticPlan` marca `requires_enrichment`
- `QueryExecutionPlanner` mantiene la implementacion SQL segura

### `dd_campos`

Uso:

- conceptos logicos
- identificadores
- familias
- filtros soportados

Campos sugeridos:

- `dominio`
- `campo_logico`
- `tabla`
- `columna`
- `es_identificador`
- `supports_filter`
- `supports_group_by`
- `supports_metric`
- `semantic_tags`
- `trace_tag`

Ejemplo:

```json
{
  "dominio": "inventario_logistica",
  "campo_logico": "movil",
  "tabla": "bd_c3nc4s1s.cinco_base_de_personal",
  "columna": "movil",
  "es_identificador": true,
  "supports_filter": true,
  "supports_group_by": true,
  "semantic_tags": ["holder", "operativo", "alfanumerico"]
}
```

### `ia_dev_capacidades_columna`

Uso:

- binding `intent/entity/filter/output -> capability`
- `planner_route_hint`
- `response_profile`
- `template_id`

Campos sugeridos:

- `dominio`
- `capability_binding_id`
- `intent`
- `entity_field`
- `required_filters_json`
- `forbidden_filters_json`
- `template_id`
- `capability_id`
- `planner_route_hint`
- `response_profile`
- `output_grain`
- `priority`
- `trace_tag`

Ejemplo:

```json
{
  "dominio": "inventario_logistica",
  "capability_binding_id": "inventario.cap.stock_balance.mobile",
  "intent": "stock_balance",
  "entity_field": "movil",
  "required_filters_json": {
    "stock_scope": "movil"
  },
  "template_id": "inventory_material_stock_mobile",
  "capability_id": "inventory_stock_balance_by_mobile",
  "planner_route_hint": "inventory.material_stock.mobile",
  "response_profile": "inventory.stock.mobile.detail",
  "output_grain": "saldo_por_codigo",
  "priority": 100
}
```

Lectura:

- `SemanticCapabilityRegistry` se vuelve lector primario de esta tabla
- `BusinessQuerySemanticPlan` usa el binding ya resuelto para `candidate_capability`, `output`, `execution.capability`

## 5. Regla por regla: clasificacion recomendada

| Regla puntual | Clasificacion |
| --- | --- |
| sinonimos hardcodeados | 1 |
| regex de cedula como semantica de negocio | 2 |
| regex de movil como semantica de negocio | 2 |
| regex de codigo/serial/bodega como extraccion primaria | 5 |
| `numerico => cedula` | 2 |
| `alfanumerico => movil` | 2 |
| `material claro => tipo material` | 2 |
| `ferretero => tipo ferretero` | 2 |
| `inventario generico => dual block` | 2 |
| `serializados => conteo` | 2 |
| `saldo incluye cero/negativo` | 2 |
| `kardex entradas/salidas/signos` | 2 |
| `SAP/actas/documentos` como limitacion | 2 |
| `template_id -> capability` | 4 y 7 |
| `capability -> response_profile` | 4 y 7 |
| `planner_route_hint` hardcodeado | 4 y 7 |
| ejemplos canonizados que operan como logica | 6 si validan fallback, 7 si gobiernan semantica |
| formulas SQL y validaciones de compilacion | 5 |

## 6. Priorizacion propuesta para P3-B

### P3-B1. Vocabulario y normalizacion base

- mover a `dd_sinonimos`:
  - movil/cuadrilla/brigada
  - kardex/movimientos/entradas y salidas
  - material claro
  - ferretero
  - serializados/equipos/cpe
  - acta/sap/documento
- mover a `dd_campos`:
  - `cedula`
  - `movil`
  - `codigo`
  - `serial`
  - `bodega`

Impacto:

- bajo
- reduce duplicacion entre matcher, resolver, intent resolver y orchestrator

### P3-B2. Reglas semanticas core de P1

- mover a `dd_reglas`:
  - `numerico => cedula`
  - `alfanumerico => movil`
  - `material claro`
  - `ferretero`
  - `material generico`
  - `dual block`
  - `serializados conteo`
  - `saldo incluye cero/negativo`

Impacto:

- alto
- elimina la mayor parte del hardcode repetido de P1

### P3-B3. Binding capability-first

- extraer de `INVENTORY_TEMPLATE_BINDINGS` hacia `ia_dev_capacidades_columna`
- dejar `SemanticCapabilityRegistry` como lector de metadata y no como repositorio de mapas

Impacto:

- muy alto
- reduce duplicacion con planner, orchestrator y response assembler

### P3-B4. Limitaciones declaradas y rutas bloqueadas

- gobernar:
  - `inventory_document_generation_pending`
  - `inventory_transfer_destination_not_available`
  - `serializados_employee_kardex_not_available`
  - `consumo_vs_facturacion operacion_hfc`

Impacto:

- medio
- mejora trazabilidad de bloqueos y no mezcla negocio con código

### P3-B5. Desinflar fallbacks sombreados

- `query_intent_resolver`
- `semantic_orchestrator_service`
- `business_query_semantic_plan`

Meta:

- que solo sugieran, no gobiernen

## 7. Riesgos

- divergencia temporal entre metadata nueva y fallback heredado
- que `QueryExecutionPlanner` siga escondiendo inconsistencias al remapear capability desde `template_id`
- que `response_assembler` mantenga narrativa basada en `row_keys` y contradiga el `response_profile`
- que un alias de `dd_sinonimos` demasiado amplio capture consultas de otros dominios
- que la migracion de `dual_block` rompa consultas de `material claro` o `ferretero` explicitos
- que la regla `numerico => cedula` afecte seriales puramente numericos si no se condiciona por intent/familia

## 8. Tests necesarios para P3-B

### Tests de registry semantico

- debe resolver igual con `dd_sinonimos` sin depender de `_SINONIMOS_BASE`
- debe resolver `template_id/capability/route/response_profile` desde metadata y no desde mapas Python
- debe emitir `matched_rule_ids` y `metadata_sources`

### Tests de no regresion P1

- `que tiene asignado la cuadrilla TIRAN224`
- `muestrame lo que tiene el movil TIRAN224`
- `movimientos del tecnico 5098747`
- `entradas y salidas de 5098747`
- `solo material de claro de TIRAN224`
- `ferreteria asignada al tecnico 5098747`
- `actas SAP del empleado 5098747`

### Tests anti-hardcode

- remover alias de Python y comprobar que el caso pasa con `dd_sinonimos`
- remover mapa `template_id -> capability` de Python y comprobar que el binding sale desde metadata
- validar que el fallback sombreado se activa solo si falta metadata
- validar que `legacy_mapping_used` queda trazado

### Tests de planner sin mover autoridad

- `QueryExecutionPlanner` sigue compilando SQL igual con binding metadata-first
- `dual_block` sigue saliendo solo cuando lo ordena regla gobernada
- `serializados_employee_kardex_not_available` sigue como limitacion declarada

### Tests de respuesta evidence-first

- `response_assembler` prioriza `response_profile` y `semantic_trace`
- no reconstruye familia solo desde texto del usuario si el binding ya la resuelve

## 9. Decision operativa para P3-B

La migracion segura no es:

- borrar regex masivamente
- borrar `INVENTORY_TEMPLATE_BINDINGS` de una vez
- mover formulas SQL al diccionario

La migracion segura si es:

1. copiar primero la regla a metadata
2. hacer que `SemanticCapabilityRegistry` la lea desde metadata
3. dejar el hardcode viejo como fallback sombreado con traza
4. cubrir con tests anti-hardcode
5. eliminar el hardcode solo cuando el fallback ya no se use

## 10. Estado de salida P3-A

P3-A queda completo cuando ya esta claro:

- que reglas deben salir del codigo
- en que tabla metadata deben vivir
- cuales deben permanecer tecnicas
- cuales son fallback temporal
- cuales son hardcode critico a eliminar primero

Sin romper el flujo vigente:

`BusinessQuerySemanticPlan`
-> `SemanticCapabilityRegistry`
-> `ToolRegistryService`
-> `QueryExecutionPlanner`
-> `Evidence-first response`
