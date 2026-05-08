# Guia De Capa Semantica Empresarial

## Recomendacion Arquitectonica

La practica recomendada para empresas con multiples tablas, procesos y agentes no es
usar solo base de datos ni solo texto libre. La opcion mas estable es una capa semantica
hibrida:

- `ai_dictionary`: catalogo estructurado y gobernado.
- Archivos YAML versionados: contexto operativo corto, reglas de negocio y ejemplos.
- Planner deterministico: selecciona dominio, tablas, columnas y joins candidatos.
- LLM: desambiguacion y normalizacion final, no descubrimiento libre de negocio.

## Estructura Recomendada Por Dominio

Para cada dominio de negocio, mantener en `backend/apps/ia_dev/domains/<dominio>/`:

- `dominio.yaml`
- `contexto.yaml`
- `reglas.yaml`
- `ejemplos.yaml`

El directorio `backend/apps/ia_dev/domains/registry/` queda reservado para compatibilidad
incremental y definiciones legacy de transicion.

## Rol De Cada Archivo

### `dominio.yaml`

Define el contrato base del dominio solo como referencia de dominio y no como fuente
estructural principal del runtime:

- nombre del dominio
- objetivo de negocio
- entidad principal
- tablas asociadas solo si siguen existiendo por compatibilidad
- columnas clave solo si siguen existiendo por compatibilidad
- joins conocidos solo si siguen existiendo por compatibilidad
- filtros soportados
- group by soportados
- metricas soportadas

Regla practica:

- la fuente oficial estructural debe ser `ai_dictionary`
- no usar `dominio.yaml` para inventar tablas, columnas, joins o reglas que no existan en `dd_*`
- si hay conflicto entre YAML y `ai_dictionary`, manda `ai_dictionary`

### `contexto.yaml`

Explica al agente como debe pensar el dominio desde negocio y narrativa:

- descripcion del dominio
- enfoque de respuesta
- tono
- vocabulario interno
- ambiguedades frecuentes
- defaults de negocio narrativos

No debe cargar estructura tecnica:

- no meter tablas fisicas
- no meter columnas fisicas
- no meter joins
- no meter SQL
- no meter reglas estructurales de planner
- no repetir metadata que ya vive en `dd_tablas`, `dd_campos`, `dd_relaciones` o capacidades

### `reglas.yaml`

Expone reglas concretas y gobernables:

- mapeos implicitos
- defaults
- restricciones
- criterios de prioridad
- equivalencias de lenguaje

### `ejemplos.yaml`

Sirve como entrenamiento operativo controlado:

- consulta ejemplo
- interpretacion esperada
- capacidad esperada
- filtros o agrupaciones esperadas

## Distribucion Profesional De Responsabilidades

### En `ai_dictionary`

Guardar:

- dominios
- tablas
- columnas
- sinonimos
- capacidades por columna
- valores permitidos
- joins permitidos
- reglas simples y reutilizables
- metadata semantica por campo
- fallbacks controlados
- privacidad por campo
- multiples vistas semanticas sobre una misma columna fisica cuando aplique

### En Archivos YAML

Guardar:

- contexto del agente
- reglas de negocio compuestas
- defaults semanticos
- ejemplos reales de consulta
- ambiguedades frecuentes
- vocabulario interno de la empresa

## Como Alimentar La Contextualizacion

La implementacion correcta debe alimentar tres capas distintas y complementarias:

### 1. Contextualizacion Del Agente

Se alimenta en `contexto.yaml`.

Objetivo:

- explicarle al agente de que trata el dominio
- como debe responder
- como nombran el negocio las cosas
- que alertas o inconsistencias debe verbalizar

Debe incluir:

- descripcion de negocio corta
- tono de respuesta
- vocabulario real del usuario
- ejemplos de ambiguedad
- defaults narrativos

No debe incluir:

- nombres de columnas fisicas
- joins
- paths JSON tecnicos
- reglas de SQL
- tablas de base de datos como contrato principal

### 2. Contextualizacion De Dominio Y Tabla

Se alimenta principalmente en:

- `ai_dictionary.dd_dominios`
- `ai_dictionary.dd_tablas`
- `ai_dictionary.dd_relaciones`

Objetivo:

- declarar cual es el dominio oficial
- declarar cual es la tabla fuente de verdad
- declarar relaciones seguras entre tablas

Debe modelar:

- dominio canonico
- tabla principal oficial
- tablas auxiliares si existen
- alias de negocio de la tabla
- clave de negocio
- joins declarados y cardinalidad

Regla:

- no crear estructura nueva si una tabla existente ya es la fuente oficial
- no duplicar la misma semantica en otra tabla si solo es enriquecimiento

### 3. Contextualizacion De Campos

Se alimenta principalmente en:

- `ai_dictionary.dd_campos`
- `ai_dictionary.dd_sinonimos`
- `ai_dictionary.dd_reglas`
- `ai_dictionary.ia_dev_capacidades_columna`

Objetivo:

- convertir columnas fisicas en conceptos de negocio gobernados

Cada campo debe modelarse como concepto, no como frase pegada.

Debe incluir cuando aplique:

- `campo_logico` canonico
- definicion de negocio
- sinonimos reales del usuario
- valores permitidos
- si sirve para filtro
- si sirve para group by
- si sirve para metrica
- si es fecha
- si es identificador
- si tiene fallback
- si tiene sensibilidad o privacidad
- si representa una vista semantica derivada de JSON

## Regla Operativa Para Campos

Cuando una columna fisica soporte varios conceptos de negocio:

- no eliminar semantica util
- declarar multiples vistas semanticas sobre la misma columna
- distinguirlas por `campo_logico`, definicion y tags semanticos
- documentar `json_path`, tipo de entidad, fallback y concepto derivado

Ejemplos tipicos:

- una columna `datos` que contiene certificados, tallas, contrato o birthday
- una misma fecha usada como emision, vencimiento derivado o estado de vigencia

## Regla De Oro Para El Programador

Cuando implemente o actualice un dominio:

1. primero confirme la fuente oficial de negocio
2. luego modele dominio y tabla en `ai_dictionary`
3. despues modele campos, sinonimos, reglas y capacidades
4. deje `contexto.yaml` solo narrativo
5. use `ejemplos.yaml` para preguntas reales del negocio
6. no hardcodee frases completas si debe modelar conceptos

## Checklist Minimo De Implementacion

- dominio oficial identificado
- tabla oficial identificada
- `dd_tablas` alineado a fuente real
- `dd_campos` con conceptos de negocio y no solo nombres fisicos
- `dd_sinonimos` con lenguaje real del usuario
- `dd_reglas` con reglas simples y reutilizables
- capacidades por columna registradas
- `contexto.yaml` narrativo y no estructural
- `ejemplos.yaml` con preguntas reales de negocio

## Regla De Nombres

Todo artefacto de negocio debe seguir [REGLA_NOMENCLATURA_EMPRESA.md](./REGLA_NOMENCLATURA_EMPRESA.md).

## Estrategia De Migracion Recomendada

1. Mantener el runtime tecnico actual.
2. No renombrar el legado masivamente.
3. Empezar a crear todo lo nuevo en espanol.
4. Versionar contexto, reglas y ejemplos por dominio.
5. Hacer migracion gradual del legado cuando haya pruebas.

## Dominios Iniciales Ya Preparados

- `empleados`
- `ausentismo`

Cada uno ya tiene archivos de:

- contexto
- reglas
- ejemplos
