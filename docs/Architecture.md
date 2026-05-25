# Architecture

## Diagrama general

```
[FUENTES HTML]
  - sitl.diputados.gob.mx/LXV_leg + LXVI_leg
  - senado.gob.mx/65 + senado.gob.mx/66
  - sil.gobernacion.gob.mx (validacion cruzada)
        |
        v
[BACKFILL CLI]   [SCHEDULER APScheduler]
        \\           /
         v         v
        [Scrapers httpx]  <---> [Redis cache]
                |
                v
        [Services: dedupe, diff, validation]
                |
                v
        [MariaDB via SQLAlchemy async]
                |
                v
        [FastAPI + WebSocket]
```

---

## Modelo de Datos

Nombres de columnas en PascalCase (siguiendo `CLAUDE.md`). Charset `utf8mb4` en todas las tablas. Motor InnoDB.

### Catalogos

```sql
CREATE TABLE Legislaturas (
  Id INT PRIMARY KEY AUTO_INCREMENT,
  Numero VARCHAR(10) NOT NULL,
  NumeroArabigo SMALLINT NOT NULL,
  FechaInicio DATE NOT NULL,
  FechaFin DATE NOT NULL,
  UNIQUE KEY UkNumero (Numero)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE Periodos (
  Id INT PRIMARY KEY AUTO_INCREMENT,
  LegislaturaId INT NOT NULL,
  AnioLegislativo TINYINT NOT NULL,
  Numero TINYINT NOT NULL,
  Tipo ENUM('Ordinario','Extraordinario') NOT NULL,
  FechaInicio DATE NOT NULL,
  FechaFin DATE NOT NULL,
  FOREIGN KEY (LegislaturaId) REFERENCES Legislaturas(Id),
  UNIQUE KEY UkPeriodo (LegislaturaId, AnioLegislativo, Numero, Tipo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE Partidos (
  Id INT PRIMARY KEY AUTO_INCREMENT,
  Siglas VARCHAR(20) NOT NULL,
  Nombre VARCHAR(200) NOT NULL,
  ColorHex VARCHAR(7),
  Activo BOOLEAN DEFAULT TRUE,
  UNIQUE KEY UkSiglas (Siglas)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE Estados (
  Id TINYINT PRIMARY KEY,
  Clave VARCHAR(5) NOT NULL,
  Nombre VARCHAR(100) NOT NULL,
  UNIQUE KEY UkClave (Clave)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### Legisladores y cargos

```sql
-- La persona. Dedupe entre legislaturas via NombreHash.
CREATE TABLE Legisladores (
  Id INT PRIMARY KEY AUTO_INCREMENT,
  NombreCompleto VARCHAR(300) NOT NULL,
  Nombre VARCHAR(150),
  ApellidoPaterno VARCHAR(100),
  ApellidoMaterno VARCHAR(100),
  Genero ENUM('M','F','X'),
  FechaNacimiento DATE,
  FotoUrl VARCHAR(500),
  NombreHash CHAR(64) NOT NULL,
  CreatedAt DATETIME DEFAULT CURRENT_TIMESTAMP,
  UpdatedAt DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX IdxNombreHash (NombreHash),
  INDEX IdxNombre (NombreCompleto)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- El cargo: la persona en una legislatura especifica con partido, distrito, etc.
CREATE TABLE LegisladorPeriodo (
  Id INT PRIMARY KEY AUTO_INCREMENT,
  LegisladorId INT NOT NULL,
  LegislaturaId INT NOT NULL,
  Camara ENUM('Diputados','Senado') NOT NULL,
  PartidoId INT,
  EstadoId TINYINT,
  Distrito SMALLINT,
  TipoEleccion ENUM(
    'MayoriaRelativa',
    'RepresentacionProporcional',
    'PrimeraMinoria'
  ) NOT NULL,
  Curul VARCHAR(20),
  EsSuplente BOOLEAN DEFAULT FALSE,
  SuplenteDeId INT,
  FechaAlta DATE,
  FechaBaja DATE,
  MotivoBaja VARCHAR(200),
  IdExterno VARCHAR(50),
  Fuente VARCHAR(50),
  FOREIGN KEY (LegisladorId) REFERENCES Legisladores(Id),
  FOREIGN KEY (LegislaturaId) REFERENCES Legislaturas(Id),
  FOREIGN KEY (PartidoId) REFERENCES Partidos(Id),
  FOREIGN KEY (EstadoId) REFERENCES Estados(Id),
  FOREIGN KEY (SuplenteDeId) REFERENCES LegisladorPeriodo(Id),
  UNIQUE KEY UkLegisladorLegislatura (LegisladorId, LegislaturaId, Camara, FechaAlta),
  INDEX IdxIdExterno (IdExterno, Fuente),
  INDEX IdxLegislaturaCamara (LegislaturaId, Camara)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### Sesiones y asistencias

```sql
CREATE TABLE Sesiones (
  Id INT PRIMARY KEY AUTO_INCREMENT,
  LegislaturaId INT NOT NULL,
  PeriodoId INT NOT NULL,
  Camara ENUM('Diputados','Senado') NOT NULL,
  Numero VARCHAR(20),
  Tipo ENUM('Ordinaria','Extraordinaria','Solemne','Permanente','Comision') NOT NULL,
  Fecha DATE NOT NULL,
  HoraInicio TIME,
  HoraFin TIME,
  QuorumInicial SMALLINT,
  QuorumFinal SMALLINT,
  Estado ENUM('Programada','EnCurso','Concluida','Suspendida','Cancelada') NOT NULL,
  UrlGaceta VARCHAR(500),
  UrlActa VARCHAR(500),
  UrlVideo VARCHAR(500),
  ScrapedAt DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (LegislaturaId) REFERENCES Legislaturas(Id),
  FOREIGN KEY (PeriodoId) REFERENCES Periodos(Id),
  UNIQUE KEY UkSesion (Camara, LegislaturaId, Fecha, Numero),
  INDEX IdxFecha (Fecha),
  INDEX IdxEstado (Estado, Fecha)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE Asistencias (
  Id BIGINT PRIMARY KEY AUTO_INCREMENT,
  SesionId INT NOT NULL,
  LegisladorPeriodoId INT NOT NULL,
  Estado ENUM(
    'Presente',
    'Ausente',
    'Justificado',
    'ComisionOficial',
    'Licencia',
    'Desconocido'
  ) NOT NULL,
  HoraRegistro DATETIME,
  TipoPaseLista ENUM('Inicial','Intermedio','Final','VotacionNominal'),
  Fuente VARCHAR(50) NOT NULL,
  ScrapedAt DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (SesionId) REFERENCES Sesiones(Id),
  FOREIGN KEY (LegisladorPeriodoId) REFERENCES LegisladorPeriodo(Id),
  UNIQUE KEY UkAsistencia (SesionId, LegisladorPeriodoId, TipoPaseLista),
  INDEX IdxSesion (SesionId),
  INDEX IdxLegislador (LegisladorPeriodoId)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### Votaciones

```sql
CREATE TABLE Votaciones (
  Id INT PRIMARY KEY AUTO_INCREMENT,
  SesionId INT NOT NULL,
  Numero SMALLINT NOT NULL,
  Asunto TEXT NOT NULL,
  Tipo ENUM('Nominal','Economica','Cedula') NOT NULL,
  Resultado ENUM('Aprobado','Rechazado','Empate','Retirado'),
  TotalFavor SMALLINT,
  TotalContra SMALLINT,
  TotalAbstencion SMALLINT,
  TotalAusente SMALLINT,
  Hora TIME,
  UrlDetalle VARCHAR(500),
  FOREIGN KEY (SesionId) REFERENCES Sesiones(Id),
  UNIQUE KEY UkVotacion (SesionId, Numero)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE Votos (
  Id BIGINT PRIMARY KEY AUTO_INCREMENT,
  VotacionId INT NOT NULL,
  LegisladorPeriodoId INT NOT NULL,
  Sentido ENUM('Favor','Contra','Abstencion','Ausente','Quorum') NOT NULL,
  FOREIGN KEY (VotacionId) REFERENCES Votaciones(Id),
  FOREIGN KEY (LegisladorPeriodoId) REFERENCES LegisladorPeriodo(Id),
  UNIQUE KEY UkVoto (VotacionId, LegisladorPeriodoId)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### Auditoria

```sql
CREATE TABLE ScrapingRuns (
  Id BIGINT PRIMARY KEY AUTO_INCREMENT,
  Fuente VARCHAR(50) NOT NULL,
  Tipo VARCHAR(50) NOT NULL,
  Parametros JSON,
  StartedAt DATETIME NOT NULL,
  FinishedAt DATETIME,
  Status ENUM('Running','Success','Partial','Failed') NOT NULL,
  RegistrosNuevos INT DEFAULT 0,
  RegistrosActualizados INT DEFAULT 0,
  Errores INT DEFAULT 0,
  ErrorDetalle TEXT,
  INDEX IdxStatusStarted (Status, StartedAt),
  INDEX IdxFuenteTipo (Fuente, Tipo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

## Estrategia de Polling Casi Tiempo Real

Pseudocodigo del scheduler:

```python
# Detector de sesion activa
# Corre cada 5 min en horario habil.
# Marca en Redis si hay sesion en curso.
async def DetectarSesionActiva():
    if not EsDiaHabilSesion():
        return
    if not EnHorarioSesion():
        return
    for Camara in ['Diputados', 'Senado']:
        Sesion = await ChequearEstadoSesion(Camara)
        if Sesion.Estado == 'EnCurso':
            await DispararPollingVivo(Camara, Sesion.Id)

# Polling activo durante una sesion en curso
# Hace diff contra DB y publica eventos en Redis pub/sub.
async def PollingVivo(Camara, SesionId):
    while True:
        Asistencias = await ScrapearAsistenciasActuales(Camara, SesionId)
        NuevasOCambios = await UpsertConDiff(Asistencias)
        if NuevasOCambios:
            await Redis.publish(f'Asistencias:{Camara}', NuevasOCambios)
        Sesion = await RefrescarSesion(SesionId)
        if Sesion.Estado != 'EnCurso':
            break
        await asyncio.sleep(150)
```

Notas operativas:
- Dias de sesion tipicos: martes y jueves (configurable, varia por periodo)
- Horario: 9am–11pm America/Mexico_City
- Frecuencia de polling: 150 segundos (2.5 min) durante sesion en curso
- Frecuencia del detector: 300 segundos (5 min)
- Reconciliacion nocturna a las 4am contra SIL

---

## Cuidados Especificos con MariaDB

- `utf8mb4` en todas las tablas; URL de conexion con `?charset=utf8mb4`
- Collation `utf8mb4_unicode_ci` para case-insensitive en nombres
- `JSON` nativo desde MariaDB 10.2; queries distintas a Postgres
- Upsert: `INSERT ... ON DUPLICATE KEY UPDATE`; en SQLAlchemy usar `mysql.insert(...).on_duplicate_key_update(...)`
- InnoDB obligatorio para foreign keys (default en MariaDB 11)
- Timezone del servidor: UTC. Conversion a `America/Mexico_City` en la aplicacion.

---

## Despliegue en VPS

- VPS recomendado: Hetzner CX22 (4 GB RAM, 2 vCPU)
- OS: Ubuntu 24.04 LTS
- Containers via Docker Compose:
  - `mariadb:11`
  - `redis:7-alpine`
  - `app-api` (Python + uvicorn)
  - `app-scheduler` (mismo image, comando distinto)
- Reverse proxy: Caddy con HTTPS automatico
- Backups: dump diario de MariaDB comprimido, retencion 30 dias, upload a object storage (Backblaze B2 o Cloudflare R2)
- Monitoreo basico: Uptime Kuma con health checks

## Seguridad

- API detras de auth (API key simple en header `X-Api-Key`)
- Rate limiting con `slowapi`
- Secretos en `.env`, nunca en git
- MariaDB no expuesta al exterior, solo accesible dentro de la red Docker
