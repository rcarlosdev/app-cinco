# Diagnóstico del sistema multiagente IA

Fecha: 2026-05-24  
Repositorio analizado: `c:\dev\agente_cinco\app-cinco`  
Alcance: backend IA, agentes, semántica, `ai_dictionary`, planner SQL, validadores, trazabilidad, memoria, background jobs y dominios ERP/CRM detectables en código.

## 1. Resumen ejecutivo

El sistema ya tiene una base seria para una plataforma IA empresarial: API autenticada de chat, orquestador central, gobierno semántico con `ai_dictionary`, contratos YAML por agente, planner SQL asistido, validadores de consulta, trazabilidad, memoria conversacional, background jobs y handlers especializados.

Sin embargo, hoy no es todavía un ERP/CRM inteligente completo. Su madurez real está concentrada en:

- RRHH/empleados: parcialmente operativo.
- Ausentismo/asistencia: operativo en consultas y analítica.
- Inventario/logística: parcialmente operativo en consultas SQL asistidas, kardex, saldos, movimientos y validación de seriales de proveedor.
- Transporte: capacidad limitada y condicionada a fuente configurada.
- CRM: no existe como dominio implementado.
- ERP transaccional: no existe como operación completa. Hay lectura, reportes y validaciones, pero no ciclos empresariales completos de compras, bodega, facturación, documentos, conciliaciones o alertas proactivas.

El diseño respeta en buena parte el principio del proyecto: GPT no genera SQL libre. GPT aparece como intérprete, árbitro y orquestador semántico, mientras que el código valida, planifica y ejecuta. La debilidad principal es que todavía conviven muchas heurísticas por tokens/frases con el gobierno semántico, y el runtime multiagente todavía funciona más como enrutamiento y trazabilidad que como coordinación autónoma real entre agentes.

Conclusión: el sistema está cerca de ser una capa inteligente de consultas empresariales gobernadas para algunos dominios. Todavía está lejos de ser un ERP/CRM operativo completo. El siguiente paso no debe ser "más prompts", sino estabilizar el gobierno semántico, endurecer SQL, activar coordinación multiagente real y crear dominios ERP/CRM con modelos, contratos, capabilities, validadores y pruebas.

## 2. Arquitectura actual detectada

### Backend y rutas principales

- Proyecto Django: `backend/config/urls.py:32-36`.
- App IA principal: `backend/apps/ia_dev`.
- Endpoints IA: `backend/apps/ia_dev/urls.py:27-52`.
  - `ia-dev/chat/`
  - `ia-dev/chat/task-status/`
  - `ia-dev/attendance/period/resolve/`
  - endpoints de memoria, salud, tickets, knowledge proposals, async jobs, observabilidad, runtime operations, semantic gaps, task explorer y governance health.
- Vista de chat: `backend/apps/ia_dev/views/chat_view.py`.
  - `IADevChatView.post`: `backend/apps/ia_dev/views/chat_view.py:155-231`.
  - Usa autenticación: `IsAuthenticatedUser` en `backend/apps/ia_dev/views/chat_view.py:156`.
  - Crea/usa singleton de `ChatApplicationService`: `backend/apps/ia_dev/views/chat_view.py:38-42`.

### Orquestador central

Archivo principal: `backend/apps/ia_dev/application/orchestration/chat_application_service.py`.

Responsabilidades detectadas:

- Bootstrap de clasificación.
- Carga de memoria conversacional.
- Resolución de intención.
- Arbitraje semántico.
- Orquestación de agentes.
- Construcción de contexto semántico.
- Planificación SQL.
- Ejecución SQL asistida.
- Ejecución de capabilities/handlers.
- Fallback controlado.
- Persistencia de estado de tarea.
- Observabilidad.
- Scheduling de background jobs.
- Ensamblado de respuesta.

Evidencias:

- Constructor con servicios de capabilities, tools, policy guard, response assembler, memoria, planners, validadores, agentes y background runtime: `backend/apps/ia_dev/application/orchestration/chat_application_service.py:103-186`.
- Método principal `run`: `backend/apps/ia_dev/application/orchestration/chat_application_service.py:611-1288`.
- Clasificación semántica y planner: `backend/apps/ia_dev/application/orchestration/chat_application_service.py:1740-2248`.
- Ejecución primaria de handler/capability o fallback: `backend/apps/ia_dev/application/orchestration/chat_application_service.py:4404-4654`.
- Bootstrap por reglas/tokens: `backend/apps/ia_dev/application/orchestration/chat_application_service.py:5672-5806`.

### Capas semánticas

- `QueryIntentResolver`: `backend/apps/ia_dev/application/semantic/query_intent_resolver.py`.
  - Reglas primero, GPT opcional después.
  - Prompt OpenAI devuelve JSON y no SQL.
- `IntentArbitrationService`: `backend/apps/ia_dev/application/semantic/intent_arbitration_service.py`.
  - Arbitra dominio, intención, uso de SQL/handler y política de fallback.
- `SemanticOrchestratorService`: `backend/apps/ia_dev/application/semantic/semantic_orchestrator_service.py`.
  - Combina determinismo, GPT opcional, validación y risk flags.
  - Prompt indica no generar SQL.
- `SemanticBusinessResolver`: `backend/apps/ia_dev/application/semantic/semantic_business_resolver.py`.
  - Usa `ai_dictionary.dd_*` como fuente estructural.
  - Documentado explícitamente como semántica estructural desde diccionario: `backend/apps/ia_dev/application/semantic/semantic_business_resolver.py:49-53`.
- `ContextBuilder`: `backend/apps/ia_dev/application/semantic/context_builder.py`.
  - Crea snapshot semántico reutilizable y auditable.

### Gobierno semántico y diccionario

- Store SQL: `backend/apps/ia_dev/services/sql_store.py`.
  - Fuerza schema `ai_dictionary`: `backend/apps/ia_dev/services/sql_store.py:19-29`.
  - Prepara nombres `ia_dev_*` bajo `ai_dictionary`: `backend/apps/ia_dev/services/sql_store.py:61-70`.
- Servicio de diccionario: `backend/apps/ia_dev/services/dictionary_tool_service.py`.
  - Tabla default `ai_dictionary.dd_dominios`: `backend/apps/ia_dev/services/dictionary_tool_service.py:19-30`.
  - Validación de identificadores seguros: `backend/apps/ia_dev/services/dictionary_tool_service.py:32-41`.
  - Snapshot de dominios/tablas/campos/reglas/relaciones/sinónimos: `backend/apps/ia_dev/services/dictionary_tool_service.py:220-260`.
- Remediación y sincronización:
  - `backend/apps/ia_dev/services/ai_dictionary_remediation_service.py`.
  - `backend/apps/ia_dev/services/ai_dictionary_deduplication_service.py`.
  - `backend/apps/ia_dev/services/inventory_dictionary_sync.py`.

### Agentes

- Registry: `backend/apps/ia_dev/application/agents/agents_registry.py`.
- Runtime: `backend/apps/ia_dev/application/agents/agents_runtime_service.py`.
- Especialistas:
  - `backend/apps/ia_dev/application/agents/specialists/inventory_agent.py`.
  - `backend/apps/ia_dev/application/agents/specialists/empleados_agent.py`.
  - `backend/apps/ia_dev/application/agents/specialists/ausentismo_agent.py`.
  - `backend/apps/ia_dev/application/agents/specialists/semantic_resolution_agent.py`.
  - `backend/apps/ia_dev/application/agents/specialists/manager_agent.py`.
- Contratos:
  - `backend/apps/ia_dev/application/contracts/agent_contracts/inventario_logistica_agent.yaml`.
  - `backend/apps/ia_dev/application/contracts/agent_contracts/ausentismo_agent.yaml`.
  - `backend/apps/ia_dev/application/contracts/agent_contracts/empleados_agent.yaml`.
  - `backend/apps/ia_dev/application/contracts/agent_contracts/transport_agent.yaml`.
  - `backend/apps/ia_dev/application/contracts/agent_contracts/knowledge_agent.yaml`.
  - `backend/apps/ia_dev/application/contracts/agent_contracts/analista_agent.yaml`.

### Planner SQL, políticas y ejecución

- Planner: `backend/apps/ia_dev/application/semantic/query_execution_planner.py`.
- Política SQL: `backend/apps/ia_dev/application/policies/query_execution_policy.py`.
- SQL join-aware: `backend/apps/ia_dev/application/semantic/join_aware_sql_service.py`.

Evidencias clave:

- SQL assisted solo para dominios cubiertos y piloto: `backend/apps/ia_dev/application/semantic/query_execution_planner.py:24-33`.
- Validación de SQL antes de plan aprobado: `backend/apps/ia_dev/application/semantic/query_execution_planner.py:130-142`.
- Ejecución SQL asistida con trazabilidad: `backend/apps/ia_dev/application/semantic/query_execution_planner.py:548-671`.
- SELECT obligatorio, tokens prohibidos, LIMIT obligatorio y allowlist de tablas/columnas/relaciones: `backend/apps/ia_dev/application/policies/query_execution_policy.py:127-212`.

### Runtime de capabilities y handlers

- Catálogo: `backend/apps/ia_dev/application/capabilities/capability_catalog.py`.
- Tool registry: `backend/apps/ia_dev/application/tools/tool_registry_service.py`.
- Runtime adapter: `backend/apps/ia_dev/application/runtime/runtime_capability_adapter.py`.
- Handlers:
  - Inventario/logística: `backend/apps/ia_dev/application/operational/inventario_logistica/handler.py`.
  - Empleados: `backend/apps/ia_dev/application/operational/empleados/handler.py`.
  - Ausentismo: `backend/apps/ia_dev/application/operational/ausentismo/handler.py`.
  - Transporte: `backend/apps/ia_dev/application/operational/transport/handler.py`.

### Memoria, trazabilidad y background

- Memoria conversacional: `backend/apps/ia_dev/application/memory/chat_memory_runtime_service.py`.
- Estado de tareas: `backend/apps/ia_dev/application/task_state_service.py`.
- Observabilidad: `backend/apps/ia_dev/application/observability/observability_service.py`.
- Background runtime: `backend/apps/ia_dev/application/runtime/background_runtime_service.py`.
- Ensamblado de respuesta:
  - `backend/apps/ia_dev/application/response/response_assembler.py`.
  - `backend/apps/ia_dev/application/response/business_response_composer_service.py`.

## 3. Flujo actual de pregunta → intención → planificación → SQL → respuesta

Flujo observado:

1. El usuario envía `message`, `session_id`, adjuntos y flags a `IADevChatView.post`: `backend/apps/ia_dev/views/chat_view.py:155-189`.
2. La vista llama `ChatApplicationService.run`.
3. Se crea `RunContext`, se almacenan adjuntos y se precarga memoria de sesión: `backend/apps/ia_dev/application/orchestration/chat_application_service.py:623-638`.
4. Se inicia ledger/traza de razonamiento: `backend/apps/ia_dev/application/orchestration/chat_application_service.py:641-646`.
5. Se ejecuta bootstrap de clasificación por reglas/tokens: `backend/apps/ia_dev/application/orchestration/chat_application_service.py:648-651` y `5672-5806`.
6. Se resuelve intención con reglas y GPT opcional en `QueryIntentResolver`.
7. Se arbitra intención/dominio con `IntentArbitrationService`: `backend/apps/ia_dev/application/orchestration/chat_application_service.py:1741-1757`.
8. Se ejecuta `SemanticOrchestratorService` para decisión semántica validada: `backend/apps/ia_dev/application/orchestration/chat_application_service.py:1774-1818`.
9. Se ejecuta `AgentsRuntimeService`, que selecciona manager + un especialista: `backend/apps/ia_dev/application/orchestration/chat_application_service.py:1820-1847`.
10. Se construye contexto de negocio con `SemanticBusinessResolver`: `backend/apps/ia_dev/application/orchestration/chat_application_service.py:1954-1966`.
11. Se planifica ejecución con `QueryExecutionPlanner`: `backend/apps/ia_dev/application/orchestration/chat_application_service.py:1996-1999`.
12. Si aplica `sql_assisted`, se ejecuta `execute_sql_assisted`: `backend/apps/ia_dev/application/orchestration/chat_application_service.py:2119-2139`.
13. Se valida satisfacción del resultado: `backend/apps/ia_dev/application/orchestration/chat_application_service.py:2140-2147`.
14. Si no hay SQL assisted, se intenta capability/handler o fallback controlado: `backend/apps/ia_dev/application/orchestration/chat_application_service.py:4404-4654`.
15. Se ensamblan respuesta, memoria, estado de tarea, trazas y metadata HTTP.

Dónde interviene OpenAI-GPT:

- `QueryIntentResolver`: interpreta intención y entidades en JSON, sin SQL.
- `IntentArbitrationService`: arbitra dominio/intención/uso de herramientas.
- `SemanticOrchestratorService`: interpreta semántica, valida con determinismo y no genera SQL.
- `AgentsRuntimeService`: manager con tool loop, sin SQL libre.

Dónde intervienen reglas/código:

- Bootstrap de dominio/intención.
- Pre-router de inventario.
- Diccionario `ai_dictionary`.
- Validación de dominio/tablas/columnas/relaciones.
- Planner SQL.
- Handlers por capability.
- Policy guard.
- Response assembler.
- Task state y observabilidad.

## 4. Agentes existentes y capacidades

### Manager agent

- Nombre: `manager_agent`.
- Archivo: `backend/apps/ia_dev/application/agents/specialists/manager_agent.py`.
- Dominio: coordinación general.
- Responsabilidad: seleccionar especialista y mantener trazabilidad de handoff.
- Entradas: contexto semántico, intención, dominio, capabilities candidatas.
- Herramientas: `AgentsRuntimeService._run_manager_tool_loop`: `backend/apps/ia_dev/application/agents/agents_runtime_service.py:243-354`.
- Tablas/fuentes: no consulta datos directamente.
- Puede resolver: selección de un especialista y explicación de enrutamiento.
- Limitaciones: no ejecuta varios agentes, no consolida resultados multiagente, no hace validación cruzada.
- Riesgo: parecer una orquestación multiagente más avanzada de lo que realmente es.
- Mejora: convertirlo en coordinador real con plan de tareas, dependencias, ejecución secuencial/paralela y agregación.

### Inventory agent

- Nombre en código: `inventory_agent`.
- Contrato de negocio relacionado: `inventario_logistica_agent`.
- Archivos:
  - `backend/apps/ia_dev/application/agents/specialists/inventory_agent.py`.
  - `backend/apps/ia_dev/application/contracts/agent_contracts/inventario_logistica_agent.yaml`.
- Dominio: `inventario_logistica`.
- Responsabilidad: saldos, kardex, movimientos, seriales, consumo vs facturación, validación de seriales proveedor.
- Entradas que entiende: `inventory_query`, `stock_balance`, `movement_history`, `serial_holder_query`.
- Herramientas: `query_execution_planner.sql_assisted`, `inventory_provider_serial_validation`.
- Fuentes: tablas gobernadas por `ai_dictionary`; contrato menciona capacidades SQL assisted para stock, móvil, bodega, seriales, kardex y consumo/facturación.
- Tareas actuales:
  - Consulta de saldos y movimientos mediante SQL assisted.
  - Trazabilidad por serial si el diccionario y planner lo soportan.
  - Validación de seriales de proveedor por handler dedicado.
- Evidencia:
  - Intents de inventario: `backend/apps/ia_dev/application/contracts/agent_contracts/inventario_logistica_agent.yaml:18-99`.
  - Capabilities: `backend/apps/ia_dev/application/contracts/agent_contracts/inventario_logistica_agent.yaml:100-280`.
  - Handler solo soporta `inventory_provider_serial_validation`: `backend/apps/ia_dev/application/operational/inventario_logistica/handler.py:28`.
- Limitaciones:
  - Muchas capacidades son SQL/reporting, no transacciones ERP.
  - Documentos y generación SAP están marcados como pendientes.
  - Facturación y compras aparecen como semántica o planeación, no como proceso implementado.
  - Hay inconsistencia nominal entre `inventory_agent` y `inventario_logistica_agent`.
- Riesgos:
  - Respuestas de inventario pueden depender de compilers y mapeos frágiles si `ai_dictionary` está incompleto.
  - Capacidades en contrato pueden ser interpretadas como más maduras que su ejecución real.
- Mejoras:
  - Normalizar nombres de agente.
  - Separar capabilities de consulta, validación, conciliación, documento y transacción.
  - Añadir pruebas por cada intent de inventario con datos controlados.

### Empleados agent

- Nombre: `empleados_agent`.
- Archivos:
  - `backend/apps/ia_dev/application/agents/specialists/empleados_agent.py`.
  - `backend/apps/ia_dev/application/operational/empleados/handler.py`.
  - `backend/apps/empleados/models/empleado_model.py`.
- Dominio: `empleados`, `rrhh`.
- Responsabilidad: conteos, detalle, analítica de empleados.
- Entradas: `employee_count`, `employee_detail`, `employee_analytics`, `rrhh_query`.
- Herramientas: `empleados.count.active.v1`, `empleados.detail.v1`.
- Fuente principal: tabla unmanaged `cinco_base_de_personal`: `backend/apps/empleados/models/empleado_model.py:88-90`.
- Campos relevantes: cédula, nombre, área, carpeta, sede, móvil, cargo, supervisor, estado, correo, ingreso/egreso: `backend/apps/empleados/models/empleado_model.py:22-86`.
- Tareas actuales:
  - Conteos por estado/agrupación.
  - Detalle de empleados.
  - Algunas respuestas analíticas.
- Limitaciones:
  - No es un módulo RRHH completo de nómina, desempeño, permisos, contratación o documentos.
  - Riesgo de exponer PII si no hay política fina de columnas sensibles.
- Riesgos:
  - El modelo contiene campo `password`: `backend/apps/empleados/models/empleado_model.py:51`.
  - Debe existir una allowlist estricta de salida para evitar exposición accidental.
- Mejoras:
  - Política de clasificación PII por campo.
  - Capabilities separadas para conteo, detalle autorizado, organigrama, rotación y ausentismo cruzado.

### Ausentismo agent

- Nombre: `ausentismo_agent`.
- Archivos:
  - `backend/apps/ia_dev/application/agents/specialists/ausentismo_agent.py`.
  - `backend/apps/ia_dev/application/contracts/agent_contracts/ausentismo_agent.yaml`.
  - `backend/apps/ia_dev/application/operational/ausentismo/handler.py`.
- Dominio: `ausentismo`, `attendance`.
- Responsabilidad: resumen, detalle, recurrencia, agregados, tendencias y resolución de periodos.
- Entradas: `ausentismo_query`, `attendance_summary`, `attendance_detail`, `attendance_trend`, `attendance_aggregate`.
- Herramientas: `attendance.period.resolve.v1`, `attendance.summary.v1`, `attendance.detail.v1`, `attendance.recurrence.v1`, `attendance.aggregate.v1`, `attendance.trend.v1`.
- Fuentes: tablas y relaciones gobernadas por diccionario, más business tool de ausentismo.
- Tareas actuales:
  - Resumen por periodo.
  - Detalle de ausencias.
  - Reincidencias.
  - Agregados y tendencias.
- Evidencia:
  - Intents/capabilities: `backend/apps/ia_dev/application/contracts/agent_contracts/ausentismo_agent.yaml:19-193`.
  - Join-aware SQL solo para attendance/ausentismo: `backend/apps/ia_dev/application/semantic/join_aware_sql_service.py:10-12`.
- Limitaciones:
  - Handoffs a empleados están declarados, pero no hay colaboración multiagente real.
  - Dependencia de tablas/relaciones correctas en diccionario.
- Riesgos:
  - Si el periodo o relación no se resuelve, puede caer a fallback o pedir aclaración.
- Mejoras:
  - Activar validación cruzada con empleados para filtros de empleado, área, sede o supervisor.

### Semantic resolution agent

- Nombre: `semantic_resolution_agent`.
- Archivo: `backend/apps/ia_dev/application/agents/specialists/semantic_resolution_agent.py`.
- Dominio: `general`, `shared`, `semantic`.
- Responsabilidad: resolver intención, dominio y contexto cuando no hay especialista claro.
- Entradas: consultas ambiguas o generales.
- Herramientas: `semantic_context.resolve`, `semantic_gap.register`, `dictionary.lookup`.
- Fuentes: `ai_dictionary`, memoria y gaps semánticos.
- Tareas actuales:
  - Recomendar herramientas semánticas.
  - Registrar faltantes o ambigüedad.
- Limitaciones:
  - No ejecuta consultas de negocio.
  - No sustituye dominios faltantes.
- Mejora:
  - Convertirlo en agente de gobernanza semántica con propuestas estructuradas para `ai_dictionary`.

### Transport agent

- Nombre contractual: `transport_agent`.
- Archivos:
  - `backend/apps/ia_dev/application/contracts/agent_contracts/transport_agent.yaml`.
  - `backend/apps/ia_dev/application/operational/transport/handler.py`.
- Dominio: transporte/logística.
- Responsabilidad actual: resumen de salidas.
- Herramienta: `transport.departures.summary.v1`.
- Limitación central: depende de fuente configurada, por ejemplo `IA_DEV_TRANSPORT_TABLE`.
- Evidencia: handler soporta solo `transport.departures.summary.v1`: `backend/apps/ia_dev/application/operational/transport/handler.py:101-107`.
- Estado: parcial y frágil.

## 5. Capacidades ERP actuales

| Proceso ERP | Estado | Evidencia | Tablas/fuentes necesarias | Gaps técnicos |
|---|---:|---|---|---|
| Inventario | Parcial | Contrato inventario con stock, dimensiones, seriales y movimientos: `inventario_logistica_agent.yaml:18-63` | Tablas de inventario gobernadas por `ai_dictionary` | Falta operación transaccional, reservas, ajustes, conteos físicos, políticas de bodega |
| Kardex | Parcial | Capability `inventory_kardex_consolidated`: `inventario_logistica_agent.yaml:55-63` y `231-240` | Movimientos, saldos, seriales, productos, bodegas | Falta motor contable/operativo completo y reconciliación formal |
| Compras | No soportado operativo | Referencias semánticas en YAML de inventario, sin handler ni dominio activo | Proveedores, órdenes, recepciones, facturas, productos | Crear dominio, modelos, contracts, lifecycle y validadores |
| Logística | Parcial | Dominio `inventario_logistica`, transport handler limitado | Movimientos, bodegas, móviles, transporte | Falta WMS/TMS completo, rutas, despachos, recepción, picking |
| Bodega | Parcial | Stock por bodega y dimensiones en contrato | Bodegas, productos, saldos, movimientos | Falta operación de transferencia, inventario físico, ajustes, auditoría operacional |
| Técnicos móviles | Parcial | Empleado tiene `movil`; inventario soporta stock por móvil | Empleados, móviles, inventario asignado, actividades | Falta agente de operación en campo, órdenes, consumo, evidencia y cierre |
| Facturación | Planeado/no operativo | `facturacion.domain.yaml` está planificado sin tablas/capabilities; consumo vs facturación en inventario | Clientes, facturas, items, consumos, contratos | Crear dominio facturación real y conciliador |
| Consumos | Parcial | Capacidades de movimientos/consumo en inventario | Movimientos, seriales, productos, responsables | Falta registro transaccional seguro y flujo de aprobación |
| Conciliaciones | Parcial conceptual | Capability consumo vs facturación en inventario | Facturación + consumos + contratos | Falta motor de conciliación, reglas y reportes de diferencias |
| Reportes operativos | Parcial | SQL assisted, tablas, charts y response assembler | Cualquier dominio gobernado | Falta catálogo formal de reportes, programación y exportación robusta |
| Alertas | No soportado como operación | Existen observabilidad/background, no motor de alertas de negocio | Reglas, umbrales, scheduler, destinatarios | Crear alert engine y canales |
| Documentos | Pendiente | Document generation marcado `external_pending`: `inventario_logistica_agent.yaml:82-90` | Plantillas, datos, firmas, adjuntos | Crear generador documental gobernado |
| Trazabilidad movimientos | Parcial | Seriales, kardex, movimientos y provider serial validation | Seriales, movimientos, productos, bodegas | Falta trazabilidad transaccional integral y auditoría de ciclo completo |

Diagnóstico ERP: el sistema funciona hoy como capa inteligente de consulta y validación para partes de RRHH, ausentismo e inventario. No es aún un ERP, porque no administra procesos de negocio de punta a punta con estados, aprobaciones, documentos, transacciones, conciliación y auditoría operacional completa.

## 6. Capacidades CRM actuales

No se encontró un módulo CRM backend implementado. No hay app `crm`, modelos de leads, oportunidades, cuentas, contactos, actividades comerciales, campañas, historial de interacción o pipeline.

| Capacidad CRM | Estado | Evidencia | Qué habría que crear |
|---|---:|---|---|
| Clientes/cuentas | No soportado | Solo aparece `cliente` como filtro planeado en `facturacion.domain.yaml` | Modelos `Cliente`, `Cuenta`, fuentes externas, contrato CRM |
| Leads | No soportado | Sin modelos, handlers ni contracts | Dominio `crm`, modelos lead, lifecycle, scoring |
| Oportunidades | No soportado | Sin código detectado | Pipeline, etapas, probabilidad, forecast |
| Seguimiento comercial | No soportado | Sin tareas comerciales persistentes | Actividades, tareas, responsables, SLA |
| Historial de interacción | No soportado | Memoria conversacional es de IA, no CRM | Timeline CRM con emails, llamadas, notas y soporte |
| Soporte | No soportado CRM | Existen tickets IA/gobernanza, no soporte cliente | Casos, SLA, priorización |
| Campañas | No soportado | Sin entidades ni agentes | Segmentos, campañas, plantillas, resultados |
| Priorización de clientes | No soportado | Sin datos de clientes | Scoring, RFM, riesgo, valor |
| Riesgo de pérdida | No soportado | Sin historial comercial | Modelos de churn y señales |
| Generación de correos | Parcial genérico | GPT podría redactar texto, pero sin CRM ni trazabilidad | Tool de redacción con datos CRM y aprobación |
| Tareas comerciales | No soportado | Sin módulo comercial | Task engine CRM integrado con agentes |

Diagnóstico CRM: hoy no hay CRM empresarial. Hay infraestructura IA reutilizable para crearlo, pero faltan dominios, datos, modelos, contratos, capabilities, seguridad y workflows.

## 7. Evaluación de consultas a base de datos

### Selección de tablas

La selección se apoya en:

- `ai_dictionary` a través de `DictionaryToolService`.
- Contexto construido por `SemanticBusinessResolver`.
- Contratos YAML de agente.
- Compilers específicos del planner.

Fortalezas:

- El diccionario es la fuente estructural principal.
- El planner valida tablas declaradas contra allowlists.
- Hay separación entre GPT y SQL.

Debilidades:

- Si `allowed_tables` llega vacío o incompleto, la validación puede perder fuerza porque depende de `declared_tables and allowed_table_set`.
- Algunos dominios están planeados en YAML/registry sin tablas reales.

### Selección de columnas

Fortalezas:

- `QueryExecutionPolicy.validate_sql_query` valida columnas cuando recibe `allowed_columns` y `declared_columns`: `backend/apps/ia_dev/application/policies/query_execution_policy.py:169-182`.
- El contexto semántico construye columnas desde diccionario.

Debilidades:

- La extracción de columnas usa regex y depende de columnas declaradas por el planner.
- No hay evidencia de una política PII transversal por campo para impedir exposición de columnas sensibles.

### Filtros

Fortalezas:

- El resolver extrae entidades, filtros y periodos.
- Join-aware SQL para ausentismo compila filtros de periodo y justificación desde contexto controlado.

Debilidades:

- Muchos filtros nacen de heurísticas de texto.
- La validación de filtros es más sintáctica que semántica. Ejemplo: puede validar que una columna exista, pero no necesariamente que el filtro tenga sentido empresarial.

### SQL libre peligroso

Control existente:

- GPT no debe generar SQL.
- SQL debe iniciar con `SELECT`.
- Hay tokens prohibidos: insert, update, delete, alter, drop, create, truncate, merge, grant, revoke: `backend/apps/ia_dev/application/policies/query_execution_policy.py:20-32`.
- LIMIT obligatorio y acotado: `backend/apps/ia_dev/application/policies/query_execution_policy.py:146-155`.
- Validación de tablas, columnas y relaciones.

Riesgos:

- La ejecución usa `cursor.execute(sql_query)` para SQL generado por planner: `backend/apps/ia_dev/application/semantic/query_execution_planner.py:567-570`.
- Es aceptable si el planner es cerrado y validado, pero conviene reforzar con AST/parser SQL y conexión DB de solo lectura real.
- Queries suplementarias de inventario se ejecutan luego desde metadata: `backend/apps/ia_dev/application/semantic/query_execution_planner.py:717-762`; deben revalidarse una por una justo antes de ejecutarse.

### LIMIT y conteos reales

Fortalezas:

- LIMIT obligatorio.
- Conteo total para list/detail cuando aplica: `backend/apps/ia_dev/application/semantic/query_execution_planner.py:764-805`.
- Export rows query sin LIMIT para metadata/export controlado: `backend/apps/ia_dev/application/semantic/query_execution_planner.py:833-838`.

Riesgos:

- Export sin controles adicionales podría crecer demasiado si no hay topes por proceso/background.

### Joins

Fortalezas:

- Valida relaciones declaradas contra allowlist: `backend/apps/ia_dev/application/policies/query_execution_policy.py:184-201`.
- Join-aware SQL usa `dd_relaciones` para ausentismo: `backend/apps/ia_dev/application/semantic/join_aware_sql_service.py:52-92`.

Debilidades:

- Join-aware está limitado a `ausentismo`/`attendance`.
- Inventario parece depender de compilers específicos.

### Explicación y trazas

Fortalezas:

- Observabilidad registra eventos.
- Task state guarda plan, query, validación, fallback y recomendaciones.
- SQL assisted registra query, rowcount, total_records, returned_records, truncated y limit: `backend/apps/ia_dev/application/semantic/query_execution_planner.py:616-643`.

Debilidad:

- La respuesta de negocio oculta términos técnicos por diseño, lo cual mejora UX, pero puede dificultar auditoría para usuarios avanzados si no hay modo explicativo.

## 8. Evaluación de validaciones y seguridad

### Antes de ejecutar

- Autenticación en la vista.
- Bootstrap semántico.
- Arbitraje de intención.
- Policy guard.
- Capability catalog.
- Validación SQL por tipo, tablas, columnas, relaciones y LIMIT.
- Contratos de agentes.
- `ai_dictionary` como allowlist semántica.

### Durante la ejecución

- Uso de alias DB configurable: `IA_DEV_DB_READONLY_ALIAS` o `IA_DEV_DB_ALIAS`: `backend/apps/ia_dev/application/semantic/query_execution_planner.py:560-564`.
- Captura de errores SQL y evento `query_sql_assisted_error`: `backend/apps/ia_dev/application/semantic/query_execution_planner.py:645-671`.
- Background runtime para tareas largas.

### Después de ejecutar

- `ResultSatisfactionValidator`.
- Response assembler.
- Task state final.
- Observability events.
- Memoria candidata.

### Riesgos de seguridad

- La seguridad de solo lectura depende de alias/configuración. Debe existir rol DB read-only real.
- Validación SQL basada en regex puede ser insuficiente ante SQL complejo.
- Posible exposición PII en empleados si no hay política por campo.
- Fallback legacy puede saltar parte de la gobernanza si no está completamente controlado.
- Adjuntos para validaciones necesitan límites de tamaño, tipo, sanitización y auditoría.

## 9. Evaluación de orquestación multiagente

Estado actual: parcial.

Lo que existe:

- `AgentsRegistry` registra cuatro especialistas: `backend/apps/ia_dev/application/agents/agents_registry.py:17-23`.
- Selección de primer especialista compatible: `backend/apps/ia_dev/application/agents/agents_registry.py:35-49`.
- Runtime manager + especialista: `backend/apps/ia_dev/application/agents/agents_runtime_service.py:58-241`.
- Tool loop opcional con OpenAI, sin generación de SQL: `backend/apps/ia_dev/application/agents/agents_runtime_service.py:243-354`.
- Handoff trace y metadata de agentes.

Lo que no existe todavía:

- Delegación real a varios agentes.
- Ejecución paralela.
- Plan multi-step entre dominios.
- Agregación de resultados de varios agentes.
- Validación cruzada entre agentes.
- Escalamiento formal cuando falta información más allá de fallback/clarificación.

Evidencia crítica:

- En `ChatApplicationService.run`, la delegación queda forzada a apagada/pruned:
  - `mode: "off"`.
  - `should_delegate: False`.
  - `plan_reason: "delegation_pruned_wave_5"`.
  - `tasks: []`.
  - Archivo: `backend/apps/ia_dev/application/orchestration/chat_application_service.py:908-920`.

Conclusión: hoy hay arquitectura para multiagente, pero el comportamiento productivo es mono-especialista con trazabilidad.

## 10. Riesgos técnicos actuales

1. Sobrepromesa funcional: contratos YAML describen capacidades futuras o parciales que pueden parecer disponibles.
2. Hardcodes semánticos: bootstrap, domain keywords y resolvers tienen muchos tokens/frases.
3. SQL regex-based: protege bastante, pero no es tan robusto como parser/AST + permisos DB.
4. Delegación inactiva: el nombre multiagente puede no reflejar la ejecución real.
5. CRM inexistente: cualquier respuesta CRM sería genérica o inventada si no se bloquea.
6. ERP no transaccional: el sistema consulta y valida, pero no gobierna ciclos completos.
7. PII: empleados incluye datos sensibles y requiere política fina.
8. Fallback legacy: puede introducir comportamientos no gobernados si se usa fuera de dominios controlados.
9. Nombres divergentes: `inventory_agent` vs `inventario_logistica_agent`.
10. Dependencia fuerte de calidad de `ai_dictionary`: si faltan campos, relaciones o sinónimos, baja precisión.

## 11. Hardcodes o fragilidad detectada

Ejemplos principales:

- Bootstrap por tokens en `ChatApplicationService._bootstrap_classification`: `backend/apps/ia_dev/application/orchestration/chat_application_service.py:5672-5806`.
- Pre-router de inventario: `backend/apps/ia_dev/application/orchestration/chat_application_service.py:5681-5693`.
- Señales de ausentismo, inventario, RRHH y knowledge en el bootstrap: `backend/apps/ia_dev/application/orchestration/chat_application_service.py:5726-5796`.
- Regex y tokens en `QueryIntentResolver`: `backend/apps/ia_dev/application/semantic/query_intent_resolver.py:34-66` y `145-260`.
- Keywords de dominio en `DomainRegistry`: `backend/apps/ia_dev/application/delegation/domain_registry.py:54-87`.
- Roles semánticos por nombre de campo en `DictionaryToolService._semantic_role_for_field`: `backend/apps/ia_dev/services/dictionary_tool_service.py:77-97`.
- Patrones determinísticos de routing dentro de contratos YAML, por ejemplo inventario: `backend/apps/ia_dev/application/contracts/agent_contracts/inventario_logistica_agent.yaml:281-285`.

Cómo reemplazarlos:

- Mover sinónimos, aliases, entidades, métricas y filtros a `ai_dictionary`.
- Usar reglas gobernadas versionadas en `dd_reglas` o equivalente.
- Mantener heurísticas solo como fallback auditable con `source=heuristic_fallback`.
- Añadir evaluaciones semánticas por dominio para medir regresiones.
- Prohibir que nuevas capacidades dependan de `if "frase exacta" in message`.

## 12. Matriz de madurez

| Área | Estado actual | Nivel 1-5 | Evidencia en código | Riesgo actual | Mejora recomendada | Prioridad |
|---|---|---:|---|---|---|---|
| Intención | Híbrida: reglas + GPT opcional + arbitraje | 3 | `query_intent_resolver.py`, `intent_arbitration_service.py` | Heurísticas rígidas | Gobernar aliases/intents en `ai_dictionary` y pruebas semánticas | Alta |
| Agentes | Manager + un especialista con trazas | 2 | `agents_runtime_service.py:58-241` | No son agentes autónomos reales | Activar ejecución multiagente planificada | Alta |
| Orquestación | Runtime central robusto, delegación apagada | 2 | `chat_application_service.py:908-920` | Preguntas multi-dominio quedan limitadas | Task planner + aggregator productivos | Alta |
| ai_dictionary | Fuerte como fuente estructural | 4 | `sql_store.py:19-29`, `dictionary_tool_service.py:220-260` | Dominios incompletos | Completar ERP/CRM y versionar reglas | Alta |
| SQL planner | SQL assisted gobernado por dominio | 3 | `query_execution_planner.py:46-240` | Compilers específicos y cobertura parcial | AST SQL, más dominios, pruebas golden | Alta |
| Validación SQL | SELECT/LIMIT/allowlist | 3 | `query_execution_policy.py:127-212` | Regex insuficiente para SQL complejo | Parser SQL + DB read-only + validación suplementaria | Alta |
| Trazabilidad | Buena observabilidad y task state | 4 | `task_state_service.py`, `observability_service.py` | Trazas dispersas para auditoría ejecutiva | Consola de auditoría por run/correlation | Media |
| Reportes | Tablas/charts/respuestas, sin catálogo formal | 3 | response assembler + SQL assisted | Reportes no versionados | Catálogo de reportes y export background | Media |
| ERP | Parcial en inventario/RRHH/asistencia | 2 | contratos inventario/ausentismo/empleados | No hay procesos punta a punta | Dominios transaccionales y workflows | Alta |
| CRM | Ausente | 1 | sin app/modelos/contracts CRM | Respuestas sin respaldo si se intentan | Crear dominio CRM desde cero | Alta |
| Seguridad | Autenticación + policy SQL | 3 | `chat_view.py:156`, `query_execution_policy.py` | PII y rol DB | Field-level security, roles, auditoría | Alta |
| UX | Respuesta de negocio cuidada | 3 | `business_response_composer_service.py` | Puede ocultar evidencia técnica | Modo auditor/explicativo | Media |
| Background tasks | Existe runtime, útil para tareas largas | 3 | `background_runtime_service.py` | No es scheduler empresarial | Queue durable, retries, alertas, cancelación UI | Media |
| Memoria conversacional | Memoria de sesión y candidatos | 3 | `chat_memory_runtime_service.py` | Heurística y posible contaminación | Memoria gobernada por tipo/confianza/caducidad | Media |

## 13. Brechas para operar como ERP/CRM inteligente

Brechas ERP:

- Falta núcleo transaccional: órdenes, estados, aprobaciones, auditoría de cambios.
- Falta catálogo de procesos: compras, recepción, despacho, consumo, facturación, conciliación, documentos.
- Falta motor de reglas de negocio gobernadas.
- Falta seguridad por rol, campo y acción.
- Falta separación explícita entre consulta, recomendación y ejecución operacional.
- Falta scheduler de alertas y reportes recurrentes.
- Falta lifecycle documental.

Brechas CRM:

- Falta dominio `crm`.
- Faltan modelos de cliente, contacto, lead, oportunidad, actividad, campaña, interacción y caso.
- Falta contrato de agente CRM.
- Faltan capabilities comerciales.
- Falta memoria CRM persistente distinta de memoria conversacional IA.
- Falta scoring, pipeline y forecast.
- Falta integración de correo/calendario o herramientas comerciales.

Brechas IA/gobernanza:

- Mover más decisión semántica a `ai_dictionary`.
- Reducir hardcodes.
- Activar multiagente real.
- Crear evaluaciones automáticas de intención, dominio, SQL y respuesta.
- Registrar evidencia de cada dato usado.

## 14. Roadmap recomendado

### Fase 1: estabilización

Objetivo: hacer confiable lo que ya existe y evitar falsas capacidades.

Archivos a modificar:

- `backend/apps/ia_dev/application/orchestration/chat_application_service.py`.
- `backend/apps/ia_dev/application/semantic/query_execution_planner.py`.
- `backend/apps/ia_dev/application/policies/query_execution_policy.py`.
- `backend/apps/ia_dev/application/agents/agents_runtime_service.py`.
- contratos YAML en `backend/apps/ia_dev/application/contracts/agent_contracts/`.

Nuevas clases/servicios sugeridos:

- `SqlAstValidationService`.
- `CapabilityAvailabilityValidator`.
- `AgentNameNormalizer`.
- `SensitiveFieldPolicyService`.

Pruebas necesarias:

- Tests de SQL blocked/allowed.
- Tests de no exposición PII.
- Tests de capabilities declaradas vs ejecutables.
- Golden tests de intención para inventario, empleados y ausentismo.

Criterios de aceptación:

- Ninguna capability se presenta como ejecutable si no tiene planner/handler real.
- Toda query suplementaria se valida antes de ejecutarse.
- DB usa rol read-only verificable.
- Respuestas CRM deben declarar "no soportado" si no hay dominio.

### Fase 2: gobierno semántico ERP/CRM

Objetivo: convertir `ai_dictionary` en gobierno semántico completo de dominios, entidades, métricas, filtros, sinónimos y relaciones.

Archivos a modificar:

- `backend/apps/ia_dev/services/dictionary_tool_service.py`.
- `backend/apps/ia_dev/services/sql_store.py`.
- `backend/apps/ia_dev/application/semantic/semantic_business_resolver.py`.
- `backend/apps/ia_dev/application/semantic/query_intent_resolver.py`.
- `backend/apps/ia_dev/application/delegation/domain_registry.py`.

Nuevas clases/servicios sugeridos:

- `SemanticGovernanceService`.
- `DomainSemanticProfileService`.
- `SemanticEvaluationSuite`.
- `DictionaryRuleVersioningService`.

Pruebas necesarias:

- Resolución de sinónimos.
- Selección de dominio sin hardcodes.
- Validación de métricas/filtros.
- Regression tests por dominio.

Criterios de aceptación:

- Nuevos términos de negocio se agregan sin tocar código.
- Hardcodes de dominio quedan como fallback auditable, no camino principal.
- Cada dominio activo tiene tablas, columnas, relaciones, métricas y filtros mínimos.

### Fase 3: agentes especializados

Objetivo: pasar de agentes que recomiendan herramientas a agentes que ejecutan capacidades seguras.

Archivos a modificar:

- `backend/apps/ia_dev/application/agents/specialists/base.py`.
- `backend/apps/ia_dev/application/agents/agents_registry.py`.
- `backend/apps/ia_dev/application/agents/agents_runtime_service.py`.
- `backend/apps/ia_dev/application/runtime/runtime_capability_adapter.py`.

Nuevas clases/servicios sugeridos:

- `AgentExecutionContract`.
- `AgentToolExecutor`.
- `AgentEvidenceCollector`.
- `AgentSafetyBoundary`.

Pruebas necesarias:

- Cada agente ejecuta solo herramientas permitidas.
- Cada respuesta incluye evidencia.
- Agente no inventa datos si faltan fuentes.

Criterios de aceptación:

- Inventory, empleados y ausentismo pueden ejecutar tareas propias sin fallback legacy.
- Cada agente declara entradas, salidas, herramientas y límites.
- El manager no puede saltarse policy/planner.

### Fase 4: orquestación multiagente

Objetivo: habilitar coordinación real entre agentes para preguntas multi-dominio.

Archivos a modificar:

- `backend/apps/ia_dev/application/delegation/task_planner.py`.
- `backend/apps/ia_dev/application/delegation/task_aggregator.py`.
- `backend/apps/ia_dev/application/orchestration/chat_application_service.py`.
- `backend/apps/ia_dev/application/agents/agents_runtime_service.py`.

Nuevas clases/servicios sugeridos:

- `MultiAgentPlanService`.
- `AgentDependencyGraph`.
- `CrossAgentValidationService`.
- `MultiAgentAnswerAggregator`.

Pruebas necesarias:

- Preguntas que combinan empleados + ausentismo.
- Preguntas que combinan inventario + facturación cuando facturación exista.
- Fallo parcial de un agente y consolidación segura.

Criterios de aceptación:

- Delegación deja de estar forzada a `off`.
- Se soporta ejecución secuencial y paralela cuando sea seguro.
- Respuesta final distingue datos confirmados, faltantes y supuestos.

### Fase 5: reportes, alertas y documentos

Objetivo: convertir respuestas en artefactos empresariales.

Archivos a modificar:

- `backend/apps/ia_dev/application/runtime/background_runtime_service.py`.
- `backend/apps/ia_dev/application/response/response_assembler.py`.
- `backend/apps/ia_dev/application/operational/inventario_logistica/handler.py`.
- nuevos módulos de reportes/documentos.

Nuevas clases/servicios sugeridos:

- `ReportCatalogService`.
- `ScheduledReportService`.
- `BusinessAlertEngine`.
- `DocumentGenerationService`.
- `ArtifactEvidenceService`.

Pruebas necesarias:

- Reportes grandes en background.
- Alertas por umbral.
- Documento con evidencia trazable.
- Cancelación/reintento de jobs.

Criterios de aceptación:

- Reporte programado y descargable.
- Alerta generada desde regla gobernada.
- Documento identifica fuente, fecha, filtros y responsable.

### Fase 6: operación empresarial tipo ERP/CRM

Objetivo: habilitar procesos empresariales completos con IA como copiloto seguro.

Archivos/módulos a crear:

- `backend/apps/crm/`.
- `backend/apps/erp/` o subapps por compras, facturación, bodega.
- Contratos `crm_agent.yaml`, `compras_agent.yaml`, `facturacion_agent.yaml`.
- Handlers transaccionales con aprobación.

Nuevas clases/servicios sugeridos:

- `WorkflowEngineService`.
- `ApprovalPolicyService`.
- `BusinessTransactionService`.
- `AuditTrailService`.
- `CrmPipelineService`.
- `CustomerInteractionTimelineService`.

Pruebas necesarias:

- Workflows de compra, recepción, consumo, factura, conciliación.
- Pipeline CRM de lead a oportunidad.
- Seguridad por rol y acción.
- Auditoría de cada cambio.

Criterios de aceptación:

- La IA puede consultar, sugerir y preparar acciones, pero las transacciones críticas requieren validación y aprobación.
- Cada operación deja auditoría.
- ERP/CRM pueden operar aunque GPT esté degradado, usando reglas y validadores.

## 15. Backlog priorizado

P0:

- Validar queries suplementarias antes de ejecución.
- Confirmar rol DB read-only real.
- Bloquear o etiquetar capacidades CRM/ERP no implementadas.
- Crear política PII por campo para empleados.
- Normalizar nombres de agentes y capabilities ejecutables.

P1:

- Migrar tokens críticos de bootstrap a `ai_dictionary`.
- Crear suite de evaluación semántica.
- Activar multiagent planner en modo controlado.
- Crear catálogo de reports gobernados.
- Crear dominio CRM mínimo con modelos y contrato.

P2:

- Motor de alertas.
- Generación documental.
- Workflows ERP transaccionales.
- Integración de correo/calendario para CRM.
- Panel de auditoría de runs.

## 16. Prompts de implementación para siguientes chats Codex

### Prompt 1: Endurecer validación SQL

Contexto: el sistema IA usa `QueryExecutionPlanner` y `QueryExecutionPolicy` para SQL assisted. GPT no debe generar SQL libre. Hay validación SELECT/LIMIT/allowlist, pero algunas queries suplementarias de inventario se ejecutan desde metadata.

Rutas:

- `backend/apps/ia_dev/application/semantic/query_execution_planner.py`
- `backend/apps/ia_dev/application/policies/query_execution_policy.py`
- tests existentes bajo `backend/apps/ia_dev/tests/` si existen.

Objetivo: revalidar toda query suplementaria justo antes de ejecutarla y preparar una capa AST/parser o servicio aislado para validación SQL.

Tareas:

- Localizar `_execute_supplemental_inventory_queries`.
- Aplicar `validate_sql_query` a cada query suplementaria con las mismas allowlists del plan.
- Registrar evento de rechazo si una query suplementaria falla.
- Añadir tests de query suplementaria válida, sin LIMIT, con tabla no permitida y con operación prohibida.

Criterios de aceptación:

- Ninguna query suplementaria se ejecuta sin validación.
- Los tests prueban rechazo y trazabilidad.
- No se permite SQL no SELECT.
- No se relaja la política actual.

### Prompt 2: Reducir hardcodes de intención y dominio

Contexto: hay bootstrap por tokens en `ChatApplicationService`, regex en `QueryIntentResolver` y keywords en `DomainRegistry`. El principio del proyecto es gobernar semántica desde `ai_dictionary`, no entrenar frases.

Rutas:

- `backend/apps/ia_dev/application/orchestration/chat_application_service.py`
- `backend/apps/ia_dev/application/semantic/query_intent_resolver.py`
- `backend/apps/ia_dev/application/delegation/domain_registry.py`
- `backend/apps/ia_dev/services/dictionary_tool_service.py`

Objetivo: introducir un `SemanticGovernanceService` que consulte aliases/sinónimos/reglas desde `ai_dictionary` y deje los hardcodes solo como fallback auditable.

Tareas:

- Diseñar servicio pequeño que devuelva candidatos de dominio/intención desde diccionario.
- Integrarlo antes de los tokens hardcoded.
- Registrar `source=ai_dictionary` o `source=heuristic_fallback`.
- Añadir tests con términos nuevos agregados al diccionario sin cambiar código.

Criterios de aceptación:

- Un alias del diccionario enruta correctamente.
- El fallback por tokens queda trazado.
- No se agregan nuevos if/else por frase exacta.

### Prompt 3: Activar multiagente controlado

Contexto: `AgentsRuntimeService` selecciona un especialista, pero `ChatApplicationService` fuerza delegación apagada en `delegation_pruned_wave_5`.

Rutas:

- `backend/apps/ia_dev/application/orchestration/chat_application_service.py`
- `backend/apps/ia_dev/application/delegation/task_planner.py`
- `backend/apps/ia_dev/application/delegation/task_aggregator.py`
- `backend/apps/ia_dev/application/agents/agents_runtime_service.py`

Objetivo: habilitar multiagente en modo piloto para consultas que requieran dos dominios, por ejemplo empleados + ausentismo.

Tareas:

- Revisar planner/aggregator existentes.
- Crear flag `IA_DEV_MULTIAGENT_DELEGATION_ENABLED`.
- Si está activo, permitir plan con tareas seguras.
- Ejecutar secuencialmente primero, no paralelo.
- Consolidar resultados con evidencia por agente.
- Mantener fallback seguro si un agente falla.

Criterios de aceptación:

- Consulta multi-dominio genera al menos dos tareas.
- Respuesta final muestra datos confirmados y faltantes.
- Si el flag está apagado, comportamiento actual se conserva.

### Prompt 4: Crear dominio CRM mínimo gobernado

Contexto: no hay CRM implementado. Se requiere crear base empresarial sin inventar respuestas.

Rutas sugeridas:

- `backend/apps/crm/`
- `backend/apps/ia_dev/application/contracts/agent_contracts/crm_agent.yaml`
- `backend/apps/ia_dev/domains/registry/crm.domain.yaml`
- `backend/apps/ia_dev/application/operational/crm/handler.py`

Objetivo: crear esqueleto CRM mínimo con clientes, contactos, leads, oportunidades, actividades e interacciones, más contrato IA en estado piloto.

Tareas:

- Crear modelos Django o adaptadores a tablas existentes si las hay.
- Crear contrato CRM con capabilities solo de consulta.
- Registrar dominio en diccionario/registry.
- Crear handler read-only para clientes/leads/oportunidades.
- Bloquear generación de acciones comerciales sin aprobación.

Criterios de aceptación:

- Consultas CRM sin datos responden "dominio no configurado" con claridad.
- Consultas con datos usan handler o SQL gobernado.
- No hay respuesta CRM fabricada.

### Prompt 5: Convertir inventario en módulo ERP operativo gradual

Contexto: inventario tiene buen soporte de consulta, kardex y validación de seriales, pero no operación ERP completa.

Rutas:

- `backend/apps/ia_dev/application/contracts/agent_contracts/inventario_logistica_agent.yaml`
- `backend/apps/ia_dev/application/operational/inventario_logistica/handler.py`
- `backend/apps/ia_dev/application/semantic/query_execution_planner.py`
- módulos nuevos bajo `backend/apps/operaciones/` o app ERP dedicada.

Objetivo: separar capabilities de lectura, validación, conciliación, documento y transacción, y crear un primer workflow seguro de ajuste/consumo con aprobación.

Tareas:

- Auditar capabilities inventario ejecutables vs declaradas.
- Marcar pending las que no tengan handler/planner.
- Crear workflow read-only primero para conciliación consumo vs facturación.
- Diseñar transacción con estado `draft`, `pending_approval`, `approved`, `executed`, `rejected`.

Criterios de aceptación:

- Ninguna transacción se ejecuta directo por GPT.
- Todo cambio requiere approval policy.
- Cada paso queda auditado.

### Prompt 6: Crear motor de reportes y alertas

Contexto: ya existen SQL assisted, response assembler, observability y background runtime, pero no un catálogo de reportes/alertas empresariales.

Rutas:

- `backend/apps/ia_dev/application/runtime/background_runtime_service.py`
- `backend/apps/ia_dev/application/response/response_assembler.py`
- nuevos servicios `ReportCatalogService`, `BusinessAlertEngine`

Objetivo: permitir reportes programables y alertas gobernadas por reglas de negocio.

Tareas:

- Crear catálogo de reportes con dominio, filtros, métricas, permisos y límites.
- Ejecutar reportes grandes en background.
- Crear reglas de alerta desde diccionario o tabla gobernada.
- Registrar evidencia y destinatarios.

Criterios de aceptación:

- Reporte programado genera artefacto trazable.
- Alerta se dispara solo desde regla gobernada.
- Hay pruebas de límite, permisos y job fallido.

## 17. Criterios de aceptación generales

- GPT no genera SQL libre.
- Toda consulta ejecutada está validada, limitada y trazada.
- Cada respuesta de datos indica fuente, filtros y límites en metadata.
- Las capacidades no implementadas se declaran como no disponibles o pendientes.
- Los dominios nuevos se agregan por `ai_dictionary` y contratos, no por frases hardcoded.
- Las transacciones empresariales requieren validación de código y aprobación.
- PII y campos sensibles están protegidos por política explícita.
- Multiagente significa varias tareas/agentes reales, no solo metadata de handoff.
- CRM no responde con datos si no existe fuente real.
- Background jobs son idempotentes, auditables y recuperables.

## 18. Pruebas recomendadas

Pruebas unitarias:

- `QueryExecutionPolicy`: SELECT válido, DELETE bloqueado, LIMIT ausente, LIMIT excesivo, tabla no permitida, columna no permitida, relación no permitida.
- `QueryExecutionPlanner`: generación de SQL por dominio, rechazo por contexto incompleto, conteo total, truncamiento.
- `DictionaryToolService`: carga de dominios, tablas, campos, reglas, relaciones y sinónimos.
- `QueryIntentResolver`: intención por diccionario, fallback heurístico trazado, OpenAI desactivado.
- Handlers: empleados, ausentismo, inventario provider serial validation, transporte sin fuente.

Pruebas de integración:

- Chat completo para ausentismo con periodo.
- Chat completo para conteo de empleados.
- Chat completo para inventario stock/kardex.
- Adjuntos de seriales proveedor con background.
- Fallo SQL controlado y respuesta segura.

Pruebas de seguridad:

- No exposición de `password` u otros campos sensibles.
- Usuario sin permisos no accede a chat o datos.
- SQL injection-like prompts no cambian política.
- Verificación de rol DB read-only.

Pruebas multiagente futuras:

- Pregunta empleados + ausentismo con dos tareas.
- Falla un agente y el agregador responde con parcialidad explícita.
- Pregunta de dominio no soportado registra semantic gap.

Pruebas ERP/CRM futuras:

- CRM sin configuración responde no disponible.
- Lead/oportunidad con datos reales responde con fuente.
- Conciliación inventario/facturación produce diferencias trazadas.
- Documento generado incluye filtros, fecha, fuente y responsable.

