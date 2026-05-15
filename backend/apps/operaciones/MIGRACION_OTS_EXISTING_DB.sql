-- Actualiza una base existente para soportar OTs como registros independientes
-- con auditoria basica (quien la agrego y cuando) y unicidad global por OT.
-- Pensado para MySQL/MariaDB.

SET @schema_name = DATABASE();

SELECT INDEX_NAME
INTO @ot_unique_index
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = @schema_name
  AND TABLE_NAME = 'operaciones_actividades'
  AND COLUMN_NAME = 'ot'
  AND NON_UNIQUE = 0
LIMIT 1;

SET @drop_index_sql = IF(
  @ot_unique_index IS NULL,
  'SELECT 1',
  CONCAT(
    'ALTER TABLE operaciones_actividades DROP INDEX `',
    @ot_unique_index,
    '`'
  )
);

PREPARE stmt_drop_index FROM @drop_index_sql;
EXECUTE stmt_drop_index;
DEALLOCATE PREPARE stmt_drop_index;

SET @add_ots_column_sql = IF(
  EXISTS(
    SELECT 1
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = @schema_name
      AND TABLE_NAME = 'operaciones_actividades'
      AND COLUMN_NAME = 'ots'
  ),
  'SELECT 1',
  'ALTER TABLE operaciones_actividades ADD COLUMN ots LONGTEXT NOT NULL DEFAULT '''''' AFTER ot'
);

PREPARE stmt_add_ots FROM @add_ots_column_sql;
EXECUTE stmt_add_ots;
DEALLOCATE PREPARE stmt_add_ots;

ALTER TABLE operaciones_actividades
  MODIFY COLUMN ot VARCHAR(100) NOT NULL DEFAULT '';

UPDATE operaciones_actividades
SET ots = TRIM(COALESCE(ot, ''))
WHERE TRIM(COALESCE(ots, '')) = '';

CREATE TABLE IF NOT EXISTS operaciones_actividad_ots (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  actividad_id BIGINT NOT NULL,
  ot VARCHAR(100) NOT NULL,
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  created_by INT NULL,
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  updated_by INT NULL,
  CONSTRAINT fk_operaciones_actividad_ots_actividad
    FOREIGN KEY (actividad_id) REFERENCES operaciones_actividades(id)
    ON DELETE CASCADE,
  INDEX idx_operaciones_actividad_ots_ot (ot),
  INDEX idx_operaciones_actividad_ots_ot_active (ot, is_active)
);

INSERT INTO operaciones_actividad_ots (
  actividad_id,
  ot,
  is_active,
  created_at,
  created_by,
  updated_at,
  updated_by
)
SELECT
  actividad.id,
  TRIM(SUBSTRING_INDEX(SUBSTRING_INDEX(tokens.tokenized_ots, '\n', numbers.n), '\n', -1)) AS ot,
  1,
  actividad.created_at,
  actividad.created_by,
  actividad.updated_at,
  actividad.updated_by
FROM operaciones_actividades actividad
JOIN (
  SELECT 1 AS n UNION ALL SELECT 2 UNION ALL SELECT 3 UNION ALL SELECT 4 UNION ALL SELECT 5
  UNION ALL SELECT 6 UNION ALL SELECT 7 UNION ALL SELECT 8 UNION ALL SELECT 9 UNION ALL SELECT 10
  UNION ALL SELECT 11 UNION ALL SELECT 12 UNION ALL SELECT 13 UNION ALL SELECT 14 UNION ALL SELECT 15
  UNION ALL SELECT 16 UNION ALL SELECT 17 UNION ALL SELECT 18 UNION ALL SELECT 19 UNION ALL SELECT 20
) numbers
JOIN (
  SELECT
    id,
    REPLACE(REPLACE(TRIM(COALESCE(ots, ot, '')), ',', '\n'), '\r', '') AS tokenized_ots
  FROM operaciones_actividades
) tokens ON tokens.id = actividad.id
WHERE numbers.n <= 1 + LENGTH(tokens.tokenized_ots) - LENGTH(REPLACE(tokens.tokenized_ots, '\n', ''))
  AND TRIM(SUBSTRING_INDEX(SUBSTRING_INDEX(tokens.tokenized_ots, '\n', numbers.n), '\n', -1)) <> ''
  AND NOT EXISTS (
    SELECT 1
    FROM operaciones_actividad_ots existing_ot
    WHERE existing_ot.ot = TRIM(SUBSTRING_INDEX(SUBSTRING_INDEX(tokens.tokenized_ots, '\n', numbers.n), '\n', -1))
  );

SET @drop_ots_column_sql = IF(
  EXISTS(
    SELECT 1
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = @schema_name
      AND TABLE_NAME = 'operaciones_actividades'
      AND COLUMN_NAME = 'ots'
  ),
  'ALTER TABLE operaciones_actividades DROP COLUMN ots',
  'SELECT 1'
);

PREPARE stmt_drop_ots FROM @drop_ots_column_sql;
EXECUTE stmt_drop_ots;
DEALLOCATE PREPARE stmt_drop_ots;
