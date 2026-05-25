-- Garantiza que la base CongresoMx exista con el charset y collation correctos.
-- El contenedor crea la DB via MARIADB_DATABASE, pero esto fuerza el collation exacto.

CREATE DATABASE IF NOT EXISTS CongresoMx
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

ALTER DATABASE CongresoMx
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
