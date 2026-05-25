# PROJECT.md

Contexto específico del proyecto Congreso MX. Complementa `CLAUDE.md` sin reemplazarlo.

Si hay conflicto entre este archivo y `CLAUDE.md`, **prevalece `CLAUDE.md`**.

---

## Project Overview

Sistema ETL en Python para extraer, almacenar y servir datos del Congreso de la Unión de México (Cámara de Diputados y Senado de la República).

**Alcance funcional**
- Legisladores (diputados y senadores)
- Sesiones del pleno
- Asistencias (foco principal del proyecto)
- Votaciones nominales

**Alcance temporal**
- Legislatura LXV (sept 2021 – ago 2024)
- Legislatura LXVI (sept 2024 – ago 2027, en curso)

**Modos de operación**
- Backfill histórico: corrida única para cargar datos pasados
- Incremental: scheduler que actualiza durante días de sesión
- Casi tiempo real: polling 2–5 min de asistencias mientras hay sesión activa

**Despliegue objetivo**
- VPS Linux (Hetzner CX22 recomendado, Ubuntu 24.04)
- Docker Compose para servicios (MariaDB, Redis, app, scheduler)

---

## Stack Técnico

- Python 3.11+
- MariaDB 11 con charset `utf8mb4`
- SQLAlchemy 2.0 (async) + Alembic para migraciones
- httpx (cliente HTTP async) + selectolax (parsing HTML)
- APScheduler para crons
- FastAPI + WebSockets para la API
- Redis para caché y pub/sub
- `logging` estándar (no structlog)
- `uv` para gestión de dependencias

---

## Fuentes de Datos

No existe API oficial. Todo es scraping de portales HTML del gobierno.

### Cámara de Diputados — SITL

Base: `http://sitl.diputados.gob.mx/{LEG}_leg/` donde `{LEG}` es `LXV` o `LXVI`.

Rutas conocidas (validar con reconnaissance antes de cada scraper):
- `listado_diputados_gpnp.php` — lista por grupo parlamentario
- `listado_diputados_edomexp.php` — lista por estado
- `curricula.php?dipt={id}` — detalle del diputado
- `asistencias_diputado_OL.php?iddip={id}` — asistencias acumuladas
- `asistencias_sesion.php?fecha={YYYY-MM-DD}` — asistencias por sesión
- `votaciones.php` — votaciones nominales

### Senado de la República

Base: `https://www.senado.gob.mx/{N}/` donde `{N}` es `65` o `66`.

Estructura más moderna (MVC). Mapear con reconnaissance.

### SIL (validación cruzada)

Base: `https://www.sil.gobernacion.gob.mx/portal/`
- `ReporteSesion/diputados`
- `ReporteSesion/senadores`

Sirve para validar datos contra una segunda fuente.

---

## Cuidados con los Portales

- **Encoding**: a veces ISO-8859-1 o windows-1252. Detectar y normalizar a UTF-8.
- **Sin CORS**: scraping server-side obligatorio.
- **Rate limiting propio**: max 1 request/seg por host, retry con backoff exponencial.
- **HTML inconsistente**: selectores defensivos, validación de cantidad mínima de elementos esperados.
- **Cambios sin aviso**: asumir que la estructura puede romperse en cualquier momento.
- **User-Agent**: usar uno real de navegador.

---

## Modelo de Datos

Ver `docs/Architecture.md` para el esquema SQL completo.

Resumen de tablas:
- `Legislaturas`, `Periodos`, `Partidos`, `Estados` (catálogos)
- `Legisladores` (la persona, dedupe por hash de nombre normalizado)
- `LegisladorPeriodo` (el cargo: persona en una legislatura específica)
- `Sesiones`, `Asistencias`
- `Votaciones`, `Votos`
- `ScrapingRuns` (auditoría de cada corrida)

### Decisiones de diseño relevantes

1. **Separación persona/cargo**: una persona puede repetir legislaturas con distinto partido o distrito. La tabla `Legisladores` guarda la persona; `LegisladorPeriodo` guarda el cargo.

2. **Idempotencia**: cada scraper debe poder re-correrse sin duplicar datos. Upsert con `ON DUPLICATE KEY UPDATE` o equivalente vía SQLAlchemy.

3. **Auditoría de scraping**: `ScrapingRuns` registra qué se scrapeó, cuándo, cuántos registros, y errores.

4. **Reconnaissance primero**: antes de escribir cualquier scraper nuevo, correr un script de recon que guarde el HTML real en `recon/output/`. Mirar el HTML, identificar selectores, validar, y solo entonces escribir el scraper.

---

## Adaptaciones a MariaDB

Diferencias relevantes frente a Postgres (por si Claude Code asume Postgres):
- `JSONB` no existe — usar `JSON`
- `TEXT[]` no existe — usar `JSON` o tabla relacional
- `ON CONFLICT` no existe — usar `ON DUPLICATE KEY UPDATE`
- Forzar `utf8mb4` en todas las tablas (acentos en nombres)
- Collation recomendada: `utf8mb4_unicode_ci`
- InnoDB obligatorio para foreign keys (default en MariaDB 11)
- Timezone del servidor en UTC, conversión a `America/Mexico_City` en la aplicación

---

## Convenciones Específicas de Este Proyecto

Las convenciones generales están en `CLAUDE.md`. Las que listo aquí son adiciones o aclaraciones específicas.

### Nombres de archivos y clases

Aplicar PascalCase de `CLAUDE.md` donde sea posible. Excepciones forzadas por librerías que NO se renombran:
- Decoradores de FastAPI usan parámetros snake_case (`status_code`, `response_model`)
- Atributos de httpx (`status_code`, `headers`, `content`)
- Pydantic v2 (`model_config`, `model_validate`, `model_dump`)
- SQLAlchemy (`mapped_column`, `primary_key`, `__tablename__`)
- Dunder methods (`__init__`, `__aenter__`, `__aexit__`)
- Tests de pytest (deben empezar con `test_`)

Para nombres de **columnas SQL** en MariaDB: usar PascalCase (`NombreCompleto`, `FechaNacimiento`). El estándar SQL universal es snake_case pero la regla de `CLAUDE.md` aplica.

### Estructura de carpetas

```
Src/CongresoMx/
├── Scrapers/
│   ├── Base.py                       # Clase base BaseScraper
│   ├── Diputados/
│   │   ├── Legisladores.py
│   │   ├── Sesiones.py
│   │   ├── Asistencias.py
│   │   └── Votaciones.py
│   ├── Senado/
│   └── Sil/
├── Models/
│   ├── Base.py
│   ├── Catalogos.py
│   ├── Legisladores.py
│   ├── Sesiones.py
│   ├── Asistencias.py
│   ├── Votaciones.py
│   └── Auditoria.py
├── Services/
├── Api/
│   ├── Main.py
│   ├── Deps.py
│   ├── Routers/
│   └── Schemas.py
├── Scheduler/
├── Utils/
└── Cli.py

Recon/
├── Scripts/
└── Output/                           # Gitignored

Tests/
Docker/
Alembic/
Docs/
Scripts/
```

### Comentarios

Por `CLAUDE.md`: bloques `#` de máx 3 líneas inmediatamente arriba de cada clase, método y función. Sin docstrings.

### Logging

Por `CLAUDE.md`: módulo `logging` estándar, no structlog. Formato con timestamp y nombre de módulo. Niveles `INFO`/`WARNING`/`ERROR`.

### Resource Management

Por `CLAUDE.md`: cerrar conexiones HTTP, DB, archivos vía `with` o `try/finally`. El cliente httpx de los scrapers usa `async with`. Las sesiones de SQLAlchemy también.

### Frontend (si llega a existir)

Por `CLAUDE.md`: vanilla HTML5 + CSS, sin React/Vue/Svelte. Decisión postergada hasta que sea relevante. La API y WebSocket funcionan independientemente con cualquier cliente.

---

## Estado del Proyecto

Ver `Docs/Phases.md` para el plan de fases y el progreso actual.
