# Capability Pack Empleados

## Estado

Fase ampliada de migracion anti-hardcode de `empleados` con detalle y cumpleanos gobernados.

Cobertura activa del pack en esta fase:

- `count_entities_by_status` sin identificador puntual
- `aggregate_by_group_and_period` para `area`, `cargo`, `sede`, `carpeta`, `supervisor` y `movil`
- `detail_by_entity_and_period` por `cedula`, `movil`, `nombre`, `area`, `cargo`, `supervisor`, `carpeta`, `sede`, `tipo_labor` y `estado`
- `count_records_by_period` para cumpleanos por mes y `este mes`
- agrupaciones de cumpleanos por `area`, `sede`, `cargo`, `carpeta`, `supervisor`, `movil` y `birth_month`
- capabilities efectivas:
  - `empleados.count.active.v1`
  - `empleados.detail.v1`
- sin cambios en planner, `fallback_policy`, SQL ni runtime general

Superficies diagnosticadas pero aun no migradas:

- ruta moderna `sql_assisted` de certificados de alturas
- rotacion de personal
- missingness y filtros sensibles

## Trazabilidad esperada

Pack-driven:

- `source = capability_pack`
- `legacy_mapping_used = false`
- `fallback_used = false`

Compatibilidad o rescate permitido:

- `source = legacy_shadow_fallback`
- `legacy_retained_reason` con limitacion declarada
- solo para:
  - dimension agrupada no declarada
  - consulta agrupada ambigua sin dimension
  - gap de metadata gobernada
  - entidad de detalle no verificable
  - filtro de detalle no declarado
  - consulta de detalle ambigua
  - metadata insuficiente para detalle
  - cumpleanos con periodo ambiguo no resoluble como `hoy` o `proximos`
  - cumpleanos con campo fecha no gobernado
  - cumpleanos con metadata insuficiente
  - certificados, rotacion o missingness aun no migrados

## Campos que no deben salir por defecto

- `foto_empleado`
- `imagen_empleado`
- `link_foto`
- `password`
- `codigo_sap`
- `celular_personal`
- `celular_alterno`
- cualquier otro campo sensible no incluido en `perfiles_respuesta.yaml`
