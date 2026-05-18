# Capability Pack `inventario_logistica`

## Objetivo

Formalizar el dominio `inventario_logistica` como un paquete gobernado y repetible para:

- metadata
- reglas
- sinonimos
- capabilities
- tools
- perfiles de respuesta
- politicas de aprobacion
- evaluaciones
- explicacion semantica

## Archivos del pack

- `paquete_capacidades.yaml`
- `reglas_semanticas.yaml`
- `perfiles_respuesta.yaml`
- `politicas_aprobacion.yaml`
- `evaluaciones.yaml`

## Autoridades que no cambia

- `QueryExecutionPlanner` sigue siendo autoridad unica de SQL.
- `ToolRegistryService` sigue siendo autoridad unica de `capability -> tool`.
- `ai_dictionary` y `metadata_gobernada_inventario.py` siguen gobernando semantica estructural.
- el pack no habilita SQL libre ni tools destructivas.

## Flujo operativo

1. La consulta se semantiza.
2. `SemanticCapabilityRegistry` resuelve template, capability, route y response profile.
3. El Capability Pack valida que esa ruta exista y este documentada.
4. `ToolRegistryService` confirma la tool declarada.
5. `QueryExecutionPlanner` decide estrategia y SQL seguro.
6. La respuesta y la explicacion semantica publican el pack usado y su version.

## Cobertura inicial

- inventario operativo por movil, cuadrilla, brigada, tecnico y empleado
- materiales y ferretero
- serializados, equipos y CPE
- kardex por empleado y por codigo
- limitaciones documentales SAP/actas
- aclaraciones estructurales y resultados vacios

## Regla de extension

Para crear un nuevo pack de negocio:

1. crear el `paquete_capacidades.yaml`
2. declarar reglas, perfiles, aprobaciones y evaluaciones
3. vincular cada regla a metadata gobernada real
4. validar tools y response profiles existentes
5. publicar traza saneada del pack en runtime

## Limitaciones declaradas

- `documentos_sap_y_actas_no_habilitados`
- `missing_physical_column:bodega_destino`
- `serializados_employee_kardex_not_available`
- `result_set_empty`
- `aclaracion_portador_requerida`
- `scope_required:operacion_hfc`
