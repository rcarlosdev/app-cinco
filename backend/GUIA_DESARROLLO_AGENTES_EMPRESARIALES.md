# Guia De Desarrollo De Agentes Empresariales

## 1. Proposito Del Documento

Esta es la guia oficial para construir, mantener y extender agentes empresariales del sistema multiagente actual.

Su objetivo es que Codex/VSC, nuevos chats, nuevas ramas y el equipo de programacion puedan continuar trabajo sin reabrir discovery completo y sin introducir hardcodes, SQL libre ni duplicacion de reglas.

## 2. Contexto Persistido Oficial

Leer siempre al inicio:

- `backend/MICRO_RESUMEN_SISTEMA_MULTIAGENTES.md`
- `backend/GUIA_CAPA_SEMANTICA_EMPRESA.md`
- `backend/OPERACION_RUNTIME_MULTIAGENTE.md`
- `backend/GUIA_DESARROLLO_AGENTES_EMPRESARIALES.md`

Aplicar tambien la seccion `USO, MANEJO, ACTUALIZACION Y PERSISTENCIA DEL CONTEXTO` del micro-resumen antes de modificar codigo o documentacion.

## 3. Modelo Mental Correcto

No entrenamos consultas.

Ensenamos el negocio al sistema para que GPT razone sobre tareas nuevas con metadata gobernada, capacidades declaradas, herramientas seguras y evidencia real.

Eso significa:

- no hardcodear frases como autoridad
- no entrenar respuestas cerradas por caso
- no hacer fine-tuning para reemplazar modelado semantico
- no dejar reglas clave solo en `if`, regex o texto libre

La meta es que el sistema entienda procesos, entidades, relaciones, reglas y capacidades para resolver consultas nuevas de forma gobernada.

## 4. Flujo Operativo Oficial

Flujo vigente:

`usuario -> task envelope -> semantic layer -> BusinessQuerySemanticPlan -> SemanticCapabilityRegistry -> ToolRegistryService -> QueryExecutionPlanner / handler seguro -> agents runtime -> approvals/background si aplica -> evidence-first response -> semantic_explanation -> continuous runtime learning`

Lectura operativa:

1. El usuario pide una tarea.
2. El runtime crea una tarea ejecutable y trazable.
3. La capa semantica normaliza dominio, intencion, entidad, filtros y capacidad candidata.
4. El binding semantico resuelve la ruta permitida.
5. La tool declarada se valida contra gobierno runtime.
6. El planner o handler seguro ejecuta.
7. La respuesta se construye sobre evidencia y no sobre texto inventado.
8. La corrida deja `semantic_explanation`, trazas saneadas y, si hay brecha, registro en aprendizaje continuo.

## 5. Autoridades Del Sistema

- `ai_dictionary`: autoridad estructural.
- `dd_tablas`, `dd_campos`, `dd_relaciones`: estructura de datos.
- `dd_sinonimos`, `dd_reglas`: lenguaje y reglas de negocio.
- `ia_dev_capacidades_columna`: capacidades por columna y afinidad de binding.
- `SemanticCapabilityRegistry`: binding semantico.
- `ToolRegistryService`: `capability -> tool`.
- `QueryExecutionPlanner`: SQL seguro.
- `Agents Runtime`: coordinacion.
- `Approval Runtime`: gobierno.
- `Background Runtime`: tareas largas.
- `Capability Packs`: empaquetado gobernado por dominio.
- `Continuous Runtime Learning`: registro de brechas, propuestas y mejora controlada.

Regla critica:

- GPT/OpenAI coordina y ayuda a razonar.
- El runtime valida.
- Las tools ejecutan.
- La evidencia manda.
- Ninguna de estas capas puede quitar autoridad a `ai_dictionary`, `ToolRegistryService` o `QueryExecutionPlanner`.

## 6. Como Crear Un Nuevo Dominio O Agente

Checklist oficial:

1. Identificar el proceso operativo real.
2. Identificar tablas oficiales y su fuente de verdad.
3. Registrar campos relevantes.
4. Registrar relaciones seguras.
5. Registrar sinonimos del lenguaje real del negocio.
6. Registrar reglas de negocio reutilizables.
7. Registrar capacidades por columna y binding esperado.
8. Crear capability y tool segura.
9. Crear response profile evidence-first.
10. Crear evals.
11. Crear `semantic_explanation` saneada.
12. Crear Capability Pack.
13. Registrar brechas esperadas, limitaciones y aclaraciones.

Artefactos minimos recomendados:

- `dominio.yaml`
- `contexto.yaml`
- `reglas.yaml`
- `ejemplos.yaml`
- contrato de agente
- capabilities declaradas
- tests focalizados
- documentacion operativa si el dominio entra en uso productivo

## 7. Como Entrenar Tablas Y Procesos

Aqui, `entrenar` significa:

- modelar metadata
- declarar relaciones
- declarar reglas
- declarar capacidades
- declarar ejemplos y evals

No significa:

- fine-tuning
- hardcodear frases
- guardar SQL libre en prompts
- resolver negocio por regex como autoridad final

Orden correcto:

1. `dd_tablas`
2. `dd_campos`
3. `dd_relaciones`
4. `dd_sinonimos`
5. `dd_reglas`
6. `ia_dev_capacidades_columna`
7. `SemanticCapabilityRegistry`
8. `ToolRegistryService`
9. `QueryExecutionPlanner` o handler seguro
10. evals anti-hardcode

## 8. Que No Hacer

- No hardcodear frases como fuente principal de verdad.
- No crear SQL libre desde GPT.
- No duplicar reglas fuera de `ai_dictionary` si ya deben vivir en `dd_*`.
- No saltar `QueryExecutionPlanner` cuando la ruta es SQL.
- No crear agentes que respondan sin tools, metadata y evidencia.
- No responder exito sin evidencia.
- No autocorregir metadata sin approval.
- No convertir fastpaths, examples o regex en autoridad final.

## 9. Como Crear Capability Packs

Estructura oficial usada por `inventario_logistica`:

- `paquete_capacidades.yaml`
- `reglas_semanticas.yaml`
- `perfiles_respuesta.yaml`
- `politicas_aprobacion.yaml`
- `evaluaciones.yaml`
- `README_OPERATIVO.md`

Responsabilidad del pack:

- organizar capacidades del dominio
- declarar cobertura operacional
- documentar limitaciones
- validar consistencia entre capability, tool y response profile
- publicar traza saneada reutilizable

El pack no reemplaza:

- `ai_dictionary`
- `SemanticCapabilityRegistry`
- `ToolRegistryService`
- `QueryExecutionPlanner`

## 10. Como Validar Un Dominio Nuevo

Checklist de pruebas:

1. Intencion.
2. Metadata.
3. Capability.
4. Tool.
5. Planner o handler seguro.
6. Evidence-first.
7. `semantic_explanation`.
8. Fallback.
9. Limitation.
10. Clarification.
11. Evals anti-hardcode.
12. Registro de brechas.

Validacion minima esperada:

- el dominio resuelve dominio e intencion correctos
- aplica filtros correctos
- usa tablas y relaciones permitidas
- deja rastro de capability y tool
- produce evidencia suficiente o una limitacion declarada
- expone explicacion semantica saneada
- registra brecha cuando no puede cerrar bien

## 11. Como Usar Continuous Runtime Learning

Flujo oficial:

`registro_brechas_semanticas -> revision -> propuesta gobernada -> approvals si aplica -> eval asociado -> cierre trazable`

Reglas:

- registrar brecha no equivale a corregir
- observability no reemplaza backlog accionable
- una propuesta sensible no se aplica sin approval
- toda correccion relevante debe quedar ligada a eval o caso reproducible

Campos utiles a vigilar:

- categoria
- dominio
- capacidad
- estado_revision
- propuesta_mejora
- evaluaciones_vinculadas
- historial

## 12. Reglas De Nomenclatura

Aplicar `backend/REGLA_NOMENCLATURA_EMPRESA.md`.

Regla vigente:

- negocio y empresa en espanol
- infraestructura, runtime y artefactos tecnicos pueden seguir en ingles

Ejemplos:

- dominio, reglas, ejemplos, sinonimos y procesos de negocio en espanol
- `runtime`, `planner`, `gateway`, `background`, `approval`, `tool loop` pueden mantenerse en ingles

## 13. Diagnostico De Dominios Actuales

### Estado De Dominios O Agentes Actuales

| Dominio | Estado | Que cumple | Que falta | Prioridad | Proximos pasos sugeridos |
| --- | --- | --- | --- | --- | --- |
| `inventario_logistica` | Completo | `BusinessQuerySemanticPlan`, `SemanticCapabilityRegistry`, `ToolRegistryService`, `QueryExecutionPlanner`, response evidence-first, `semantic_explanation`, Capability Pack, evals anti-hardcode, aprendizaje continuo, documentacion operativa | ampliar cobertura de migracion metadata-first donde aun quede fallback sombreado legacy | Media | cerrar deuda puntual restante por familias no migradas, mantener evals y revisar brechas reales |
| `empleados` | Parcialmente alineado | dominio y reglas versionadas, contrato de agente, capabilities declaradas, handler seguro, integracion con runtime y `ToolRegistryService`, respuesta con evidencia de tabla/KPI, uso parcial de `ResolvedQuerySpec` + `QueryExecutionPlan` como plan operativo | no hay `BusinessQuerySemanticPlan` propio ni binding gobernado por registry, no usa `SemanticCapabilityRegistry`, no hay Capability Pack, no hay evals anti-hardcode del dominio, no hay documentacion operativa del dominio, no se evidencian `dd_*` completos ni trazabilidad de brechas por dominio | Alta | migrar binding semantico a metadata gobernada, crear pack, crear evals, publicar explicacion semantica por evidencia y registrar brechas |
| `ausentismo` | Parcialmente alineado | dominio y reglas versionadas, contrato de agente, varias capabilities declaradas, business tool seguro, referencias a `dd_tablas`, integracion con runtime y `ToolRegistryService`, uso parcial de `ResolvedQuerySpec` + `QueryExecutionPlan` como plan operativo | no hay `BusinessQuerySemanticPlan` propio ni binding por `SemanticCapabilityRegistry`, no hay Capability Pack, no hay evals anti-hardcode del dominio, no hay documentacion operativa del dominio, metadata gobernada parcial frente al modelo completo, sin trazabilidad de brechas semanticas por dominio en artefactos propios | Alta | migrar binding semantico y perfiles de respuesta a metadata gobernada, crear pack, crear evals, documentar operacion y cerrar brechas |

### Detalle Del Diagnostico

Base usada para este diagnostico focalizado:

- `backend/apps/ia_dev/application/semantic/semantic_capability_registry.py`
- `backend/apps/ia_dev/application/runtime/tool_registry_service.py`
- `backend/apps/ia_dev/application/runtime/runtime_capability_adapter.py`
- `backend/apps/ia_dev/application/routing/capability_catalog.py`
- contratos de agente de `empleados` y `ausentismo`
- handlers y tests focalizados de los tres dominios
- pack y documentacion de `inventario_logistica`

#### `inventario_logistica`

Cumple:

- metadata gobernada en `metadata_gobernada_inventario.py`
- `BusinessQuerySemanticPlan`
- `SemanticCapabilityRegistry` activo para el dominio
- `ToolRegistryService` integrado
- `QueryExecutionPlanner` como autoridad SQL
- response evidence-first
- `semantic_explanation` saneada
- evals anti-hardcode en `evaluaciones.yaml` y suite Python
- Capability Pack completo
- approvals y background por runtime global y politicas del pack
- registro de brechas via `Continuous Runtime Learning`
- `README_OPERATIVO.md`

Observacion:

- sigue existiendo compatibilidad temporal con fallback sombreado legacy en algunas rutas, pero ya no es la autoridad principal del dominio.

#### `empleados`

Cumple:

- dominio narrativo y reglas versionadas
- contrato de agente y capabilities declaradas
- handler seguro y controlado por runtime
- integracion con `ToolRegistryService`
- consumo de `ResolvedQuerySpec` y `QueryExecutionPlan` como plan operativo parcial
- respuesta con tabla o KPI y trazas operativas
- `semantic_explanation` global del runtime disponible al final de la corrida

Falta o no queda evidenciado como completo:

- metadata gobernada completa en `ai_dictionary` para `dd_tablas`, `dd_campos`, `dd_relaciones`, `dd_sinonimos`, `dd_reglas`, `ia_dev_capacidades_columna`
- `BusinessQuerySemanticPlan` propio del dominio
- binding por `SemanticCapabilityRegistry`
- Capability Pack
- evals anti-hardcode del dominio
- documentacion operativa propia
- evidencia explicita de registro de brechas semanticas del dominio

Clasificacion:

- `Parcialmente alineado`

#### `ausentismo`

Cumple:

- dominio narrativo y reglas versionadas
- contrato de agente y capabilities declaradas
- handler y business tool seguros
- referencias operativas a `dd_tablas` en tablas de ausentismo y personal
- integracion con `ToolRegistryService`
- consumo de `ResolvedQuerySpec` y `QueryExecutionPlan` como plan operativo parcial
- respuesta con evidencia tabular/KPI/grafica y trazas operativas
- `semantic_explanation` global del runtime disponible al final de la corrida

Falta o no queda evidenciado como completo:

- `BusinessQuerySemanticPlan` propio del dominio
- binding por `SemanticCapabilityRegistry`
- Capability Pack
- evals anti-hardcode del dominio
- documentacion operativa propia
- metadata gobernada completa y trazable en `dd_campos`, `dd_relaciones`, `dd_sinonimos`, `dd_reglas`, `ia_dev_capacidades_columna`
- registro de brechas semanticas aterrizado al dominio en artefactos propios

Clasificacion:

- `Parcialmente alineado`

## 14. Roadmap Recomendado

1. Completar `inventario_logistica` si queda deuda puntual de migracion metadata-first o fallback sombreado.
2. Migrar `empleados` a Capability Pack.
3. Migrar `ausentismo` a Capability Pack.
4. Crear evals anti-hardcode para `empleados`.
5. Crear evals anti-hardcode para `ausentismo`.
6. Conectar `semantic_explanation` de negocio mas rica para `empleados` y `ausentismo` sobre evidencia estructurada.
7. Registrar brechas reales por dominio en `registro_brechas_semanticas`.

## 15. Checklist Antes De Merge

- tests focalizados OK
- micro-resumen actualizado
- guia actualizada si aplica
- operacion actualizada si aplica
- sin duplicacion
- sin hardcodes nuevos
- sin SQL libre
- evidencia y trazabilidad presentes

## Regla Final De Trabajo

Para nuevas ramas, nuevos chats o nuevas tareas:

1. leer el contexto persistido oficial
2. no reauditar arquitectura completa
3. modelar primero el negocio y luego la ejecucion
4. usar metadata gobernada, capability, tool y evidencia
5. persistir reglas reutilizables en el documento correcto

## Regla UX Persistida 2026-05-16

Cuando el frontend exponga el sistema multiagente empresarial:

1. el chat debe seguir siendo conversacional y simple
2. el informe empresarial debe vivir en el panel derecho
3. historial, herramientas y caracteristicas deben quedar en una zona de soporte separada
4. la explicacion visible debe salir de `semantic_explanation`, evidencia y estado saneado
5. no mostrar JSON crudo, traces internos, prompts, chain-of-thought ni SQL sensible

Regla critica:

- la UX debe demostrar `task-first` y `evidence-first`
- no debe degradarse a panel de debugging
- no debe duplicar tablas o dashboard dentro del chat

## Regla UX Persistida 2026-05-17: dashboard historico desacoplado del chat

En el frontend del `Agente IA`:

1. cada respuesta del asistente debe poder abrir su propio dashboard asociado
2. la asociacion visible debe ser estable por `message_id`
3. el panel derecho no debe reemplazarse automaticamente por la ultima respuesta si el usuario esta inspeccionando una respuesta anterior
4. una nueva corrida puede mostrar estado runtime vivo sin borrar el dashboard historico seleccionado
5. la persistencia de seleccion del dashboard debe vivir como estado visual UI, separado del runtime y separado de la respuesta conversacional

Regla critica:

- `chat conversacional` != `panel operativo`
- `runtime state` != `UI state`
- el panel derecho debe comportarse como inspector reutilizable para dashboards, evidencia, explicacion y superficies futuras, no como render acoplado al ultimo mensaje textual

## Regla UX Persistida 2026-05-17: adjuntos honestos antes de transporte binario real

Cuando el frontend del chat permita adjuntar archivos:

1. la UI puede aceptar adjuntos locales por selector o drag & drop
2. los adjuntos pueden mostrarse en el compositor y en el mensaje del usuario
3. si el transporte actual no soporta binarios reales, la interfaz debe decirlo de forma explicita
4. no se debe insinuar que el sistema leyo el contenido del archivo si solo recibio su referencia nominal

Regla critica:

- la UX puede adelantarse al backend
- la semantica y la evidencia no
- si no hubo binario en runtime, no hay inspeccion real del archivo
