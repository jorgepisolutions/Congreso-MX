# Plan de Fases

Cada fase es un prompt independiente para Claude Code. Respetan el workflow definido en `CLAUDE.md`:

1. Lee archivos relevantes
2. Produce un plan (todos, asunciones, tradeoffs, criterios de exito)
3. **Espera tu aprobacion**
4. Implementa marcando los todos
5. Resume cambios sin code dumps
6. Verifica contra criterios

Marca progreso editando este archivo:

- [ ] Fase 0: Setup inicial
- [ ] Fase 1: Reconnaissance de portales
- [ ] Fase 2: Modelos SQLAlchemy + migraciones
- [ ] Fase 3: Scraper de legisladores Diputados
- [ ] Fase 4: Scraper de sesiones Diputados
- [ ] Fase 5: Scraper de asistencias Diputados
- [ ] Fase 6: Scrapers del Senado
- [ ] Fase 7: Backfill historico LXV + LXVI
- [ ] Fase 8: Scheduler incremental
- [ ] Fase 9: API REST + WebSocket
- [ ] Fase 10: Docker + deploy a VPS

---

## Fase 0 — Setup inicial

```
Lee CLAUDE.md y PROJECT.md. Tambien lee docs/Architecture.md.

Tu tarea: armar el scaffold del proyecto Congreso MX.

NO escribas codigo aun. Primero produce un plan que incluya:

- Lista concreta de archivos a crear con su proposito
- Asunciones que estes haciendo (version de Python, ubicacion del .env, etc.)
- Tradeoffs considerados (ej: si usar uv vs pip, src layout vs flat)
- Criterios de exito: como sabremos que el setup esta correcto

Espera mi aprobacion del plan antes de crear archivos.

Contenido esperado del scaffold:

1. pyproject.toml usando uv como package manager con dependencias:
   - Runtime: httpx, selectolax, sqlalchemy[asyncio], alembic, asyncmy,
     fastapi, uvicorn[standard], apscheduler, redis, typer,
     python-dotenv, tenacity, pydantic-settings
   - Dev: pytest, pytest-asyncio, respx, ruff, mypy, ipython

2. Estructura de carpetas en PascalCase segun PROJECT.md (Src/CongresoMx/...).

3. Configuracion base:
   - .env.example con todas las variables necesarias
   - .gitignore (Python + .env + Recon/Output/)
   - .editorconfig
   - ruff.toml con reglas razonables (recordar que no usamos snake_case)
   - .pre-commit-config.yaml con ruff y mypy

4. docker/DockerCompose.yml con servicios mariadb:11 y redis:7-alpine
   para desarrollo local. MariaDB con charset utf8mb4 e init script que
   cree la base de datos CongresoMx.

5. Src/CongresoMx/Config.py con Pydantic Settings que lea del .env.

6. Src/CongresoMx/__init__.py vacio (este nombre es forzado por Python).

7. Src/CongresoMx/Cli.py con stub de Typer (comando Hello por ahora).

Una vez aprobado el plan: implementa, no instales nada todavia, muestrame
el arbol final y los comandos para arrancar.
```

---

## Fase 1 — Reconnaissance de portales

Antes de cualquier scraper, hay que mapear el HTML real. Los portales del Congreso cambian sin aviso.

```
Lee CLAUDE.md, PROJECT.md y docs/Recon.md.

Tu tarea: implementar scripts de reconnaissance para los 3 portales fuente.

Produce primero un plan con:
- URLs concretas a probar (sacalas de PROJECT.md y agrega variantes si crees que son necesarias)
- Como manejaras encoding (ISO-8859-1 vs UTF-8)
- Como guardaras los resultados en Recon/Output/
- Que reportaras al final (status codes, tamanos, primeras etiquetas distintivas)
- Criterios de exito: cuando consideramos que el recon esta completo

Espera mi aprobacion.

Implementa Recon/Scripts/ReconDiputados.py, ReconSenado.py y ReconSil.py
usando httpx async. Cada uno:

1. Lista de URLs a descargar (con variantes si la principal devuelve 404)
2. Headers de navegador real
3. Timeout de 30s
4. Detecta encoding y normaliza a UTF-8 al guardar
5. Guarda HTML en Recon/Output/[Portal]/[NombreDescriptivo].html
6. Reporta por URL: status code, tamano, encoding detectado, primeras 5
   tags <table>/<form>/<a> distintivas

Despues de correrlos, muestrame el resumen para que yo (humano) revise
los HTML descargados y decida los selectores correctos.
```

---

## Fase 2 — Modelos SQLAlchemy + migraciones

```
Lee CLAUDE.md, PROJECT.md y docs/Architecture.md.

Tu tarea: implementar los modelos SQLAlchemy 2.0 (async, declarative)
basados en el esquema SQL de docs/Architecture.md, y configurar Alembic.

Recuerda: nombres en PascalCase (tanto Python como SQL), comentarios # de
max 3 lineas arriba de cada clase, sin docstrings, logging estandar.

Produce primero un plan:
- Lista de archivos a crear bajo Src/CongresoMx/Models/
- Como organizaras Base (metadata, naming convention para constraints)
- Como manejaras los tipos especificos de MariaDB (ENUM, JSON)
- Como configuraras Alembic para async
- Asunciones (version de MariaDB, etc.)
- Criterios de exito: que tablas deben existir tras alembic upgrade head

Espera mi aprobacion.

Implementa:

- Src/CongresoMx/Models/Base.py (Base con naming convention)
- Src/CongresoMx/Models/Catalogos.py (Legislaturas, Periodos, Partidos, Estados)
- Src/CongresoMx/Models/Legisladores.py (Legisladores, LegisladorPeriodo)
- Src/CongresoMx/Models/Sesiones.py
- Src/CongresoMx/Models/Asistencias.py
- Src/CongresoMx/Models/Votaciones.py (Votaciones, Votos)
- Src/CongresoMx/Models/Auditoria.py (ScrapingRuns)
- Alembic/ configurado para async, con env.py adaptado
- Migracion inicial generada con alembic revision --autogenerate

Scripts/SeedCatalogos.py que pueble Estados (32) y Partidos basicos
(PRI, PAN, PRD, MORENA, PT, PVEM, MC, minimo).

Al final corre alembic upgrade head, ejecuta SeedCatalogos y muestrame
SHOW TABLES y DESCRIBE Legisladores.

Importante: yo soy principiante en async. Cuando introduzcas el patron
async engine + AsyncSession, explicalo en 3-5 lineas en el resumen final
(no en code comments).
```

---

## Fase 3 — Scraper de legisladores Diputados

```
Lee CLAUDE.md, PROJECT.md, docs/Recon.md, y los HTML en Recon/Output/Diputados/.

Tu tarea: implementar el scraper de legisladores de la Camara de Diputados
para legislatura LXVI.

Produce primero un plan que incluya:
- Selectores CSS que identificaste de los HTML reales (no asumas, leelos)
- Estructura de BaseScraper (clase base reutilizable para todos los scrapers)
- Como manejaras retry, rate limiting, encoding
- Como sera el flujo: listado -> detalle por curricula
- Que dataclasses crudos extraeras del HTML
- Como sera el upsert en DB (matching por IdExterno + Fuente)
- Criterios de exito: ej. 500 diputados insertados sin errores

Espera mi aprobacion.

Implementa:

1. Src/CongresoMx/Scrapers/Base.py con clase BaseScraper:
   - http client httpx async compartido (context manager)
   - Retry con tenacity (exponential backoff, max 3)
   - Rate limiting (max 1 req/seg por host)
   - Logging con modulo logging estandar
   - Deteccion y normalizacion de encoding
   - Metodo GetHtml(url) -> str

2. Src/CongresoMx/Scrapers/Diputados/Legisladores.py:
   - Clase ScraperDiputadosLegisladores(BaseScraper)
   - Metodo ScrapearListado(Legislatura: str) -> list[LegisladorCrudo]
   - Metodo ScrapearCurricula(IdExterno: str) -> CurriculaCruda

3. Src/CongresoMx/Services/Legisladores.py:
   - UpsertLegislador(Sesion, Crudo) -> Legislador
   - UpsertLegisladorPeriodo(Sesion, Legislador, Crudo, Legislatura, Camara)
   - NormalizarNombreParaHash() helper para dedupe entre legislaturas

4. CLI: agregar comando a Cli.py:
   congreso scrape legisladores --camara diputados --legislatura LXVI

5. Tests en Tests/Scrapers/TestDiputadosLegisladores.py:
   - respx para mockear HTTP
   - Fixtures con HTML real recortado de Recon/Output/
   - Test del parser, test del upsert (DB de tests separada)

En el resumen final, explicame brevemente:
- Que es y como funciona el http client compartido async
- Que es y como funciona el rate limiter
- Como interactua el async con el upsert en DB
```

---

## Fase 4 — Scraper de sesiones Diputados

```
Lee CLAUDE.md, PROJECT.md y Recon/Output/Diputados/.

Tarea: scraper de sesiones de Diputados LXVI.

Produce plan primero:
- De donde sacas el listado de sesiones (calendario? gaceta? derivado de
  asistencias?). Si no es claro del recon, proponeme alternativas con tradeoffs
- Como mapeas la sesion a su Periodo correcto
- Como calculas el Estado actual (Programada/EnCurso/Concluida) en base a
  fecha y hora actual en America/Mexico_City
- Criterios de exito

Espera aprobacion.

Implementa:

1. Src/CongresoMx/Scrapers/Diputados/Sesiones.py:
   - ScrapearCalendario(Legislatura, Periodo) -> list[SesionCruda]
   - ScrapearDetalleSesion(Fecha) -> SesionDetalle (quorum, hora, etc.)

2. Src/CongresoMx/Services/Sesiones.py:
   - UpsertSesion con mapeo correcto a Periodo
   - Calculo de Estado

3. CLI:
   congreso scrape sesiones --camara diputados --legislatura LXVI
   con flags --desde-fecha y --hasta-fecha opcionales.

4. Tests.
```

---

## Fase 5 — Scraper de asistencias Diputados (critico)

Este es el componente central del proyecto. Tomar mas tiempo en el plan.

```
Lee CLAUDE.md, PROJECT.md, Recon/Output/Diputados/, y los modelos en
Src/CongresoMx/Models/Asistencias.py.

Tarea: scraper de asistencias de Diputados. Es el componente mas
importante del proyecto.

Produce plan exhaustivo:

- Has revisado realmente los HTML de asistencias_sesion.php y
  asistencias_diputado_OL.php? Que estructura tienen?
- Pregunta: el portal publica pases de lista intermedios o solo el
  consolidado final? La granularidad de la tabla Asistencias
  (campo TipoPaseLista) depende de esto. Si no esta claro del recon,
  propon una hipotesis y planea como validarla con datos reales.
- Como detectas cambios entre corridas (alguien que paso de Ausente a
  Justificado por ejemplo)?
- Como manejas suplencias (un diputado de licencia y su suplente activo
  en la misma sesion)?
- Criterios de exito: que metricas validan que funciona?

Espera aprobacion del plan. Discute conmigo los puntos abiertos.

Implementa:

1. Src/CongresoMx/Scrapers/Diputados/Asistencias.py con dos modos:
   - ScrapearAsistenciasSesion(Fecha) -> list[AsistenciaCruda]
   - ScrapearAsistenciasDiputado(IdExterno) -> list[AsistenciaCruda]

2. Src/CongresoMx/Services/Asistencias.py:
   - UpsertAsistencias con diff detection
   - Si la asistencia ya existe pero cambio, actualizar y loggear el cambio
   - Si es nueva, insertar
   - Usar ScrapingRuns para auditoria

3. CLI:
   congreso scrape asistencias --camara diputados --fecha YYYY-MM-DD
   congreso scrape asistencias --camara diputados --diputado <id>
   congreso scrape asistencias --camara diputados --legislatura LXVI --backfill

4. Tests con HTML real recortado.
```

---

## Fase 6 — Scrapers del Senado

```
Lee CLAUDE.md, PROJECT.md y Recon/Output/Senado/.

Tarea: replicar fases 3-5 para el Senado.

Produce plan que documente las diferencias estructurales encontradas en
el recon contra Diputados. Si hay diferencias significativas (ej.
asistencias por comision, manejo distinto de suplencias, JSON endpoints
internos), discutelas conmigo antes de implementar.

Espera aprobacion.

Implementa Src/CongresoMx/Scrapers/Senado/:
- Legisladores.py
- Sesiones.py
- Asistencias.py

Reutiliza al maximo BaseScraper y los services (anade parametros Camara
donde sea necesario).

Extiende CLI: mismos comandos con --camara senado.

Tests.
```

---

## Fase 7 — Backfill historico

```
Lee CLAUDE.md, PROJECT.md y el estado actual del proyecto.

Tarea: comando CLI que ejecute el backfill completo de LXV + LXVI en
ambas camaras.

Plan primero:
- Orden de ejecucion correcto (catalogos -> legisladores -> sesiones -> asistencias)
- Concurrency strategy (cuantos scrapers en paralelo por host)
- Como reportar progreso (rich? logging simple?)
- Manejo de errores parciales (continuar y reportar al final vs detener todo)
- Estimacion de tiempo
- Criterios de exito (counts finales esperados)

Espera aprobacion.

Implementa comando Cli.py:
   congreso backfill --legislatura LXV [--legislatura LXVI] [--camara X]

Idempotente. Imprime progreso. Maneja errores parciales sin abortar.
Al final reporta estadisticas via SELECT COUNT(*) por tabla.

Despues de correrlo, ejecuta un query interesante: top 10 diputados con
mas inasistencias en LXVI hasta hoy.
```

---

## Fase 8 — Scheduler incremental

```
Lee CLAUDE.md, PROJECT.md y la seccion "Estrategia de Polling" de
docs/Architecture.md.

Tarea: scheduler con APScheduler que mantiene los datos al dia y hace
polling casi tiempo real durante sesiones activas.

Plan primero:
- Como configuras APScheduler async
- Como manejas zona horaria (servidor UTC, logica en CDMX)
- Como creas jobs dinamicos (el polling solo cuando hay sesion activa)
- Como usas Redis pub/sub (que canales, que payload)
- Como detienes el job dinamico cuando la sesion termina
- Criterios de exito

Espera aprobacion.

Implementa Src/CongresoMx/Scheduler/Main.py:

1. Job DetectarSesionActiva cada 5 min:
   - Solo dias habiles de sesion (configurable)
   - Solo en horario 9am-11pm CDMX
   - Para cada camara verifica si hay sesion en curso
   - Si la hay, dispara PollingVivo

2. PollingVivo dinamico cada 2.5 min mientras la sesion este en curso:
   - Scrapea asistencias actuales
   - Diff con DB
   - Si hay cambios: upsert + publicar en Redis canal Asistencias:{Camara}:{SesionId}
   - Cuando estado != EnCurso, auto-detener

3. Job ReconciliacionNocturna cada dia a las 4am:
   - Re-scrapea sesiones del dia anterior contra SIL
   - Reporta discrepancias

4. CLI:
   congreso scheduler run

En el resumen, explicame Redis pub/sub (que es, como lo consumira la API
en la fase 9) y como APScheduler maneja jobs async.
```

---

## Fase 9 — API REST + WebSocket

```
Lee CLAUDE.md, PROJECT.md y el estado actual del proyecto.

Recuerda: vanilla HTML/CSS si llega a haber frontend, decision postergada.
La API debe ser consumible por cualquier cliente externo.

Tarea: API FastAPI con endpoints REST + WebSocket para datos en vivo.

Plan primero:
- Estructura de routers
- Schemas Pydantic (input y output)
- Estrategia de auth (API key simple via header X-Api-Key)
- Rate limiting (slowapi, limites por tier)
- Como conecta el WebSocket con Redis pub/sub
- Criterios de exito

Espera aprobacion.

Implementa Src/CongresoMx/Api/:

Endpoints REST:
   GET /legisladores                     (filtros: legislatura, camara, partido, estado)
   GET /legisladores/{Id}
   GET /legisladores/{Id}/asistencias
   GET /legisladores/{Id}/votaciones
   GET /sesiones                         (filtros: camara, desde, hasta)
   GET /sesiones/{Id}
   GET /sesiones/{Id}/asistencias
   GET /asistencias                      (filtros: camara, fecha, estado)
   GET /stats/asistencias                (agregados, top inasistentes, % por partido)

WebSocket:
   /ws/asistencias/{Camara}
   Se suscribe a Redis pub/sub y envia updates JSON en tiempo real

Auth: API key en header. Generacion de keys via script CLI.
Rate limiting: 60 req/min por key.
Docs auto en /docs.

CLI:
   congreso serve [--host 0.0.0.0 --port 8000]
   congreso api genkey --nombre "..."

Tests de endpoints con TestClient de FastAPI.
```

---

## Fase 10 — Docker + deploy

```
Lee CLAUDE.md, PROJECT.md y el estado del proyecto.

Tarea: preparar el proyecto para deploy en VPS Linux.

Plan primero:
- Estructura del Dockerfile (multi-stage con uv)
- DockerComposeProd.yml con todos los servicios
- Estrategia de backups (frecuencia, retencion, destino)
- Reverse proxy (Caddy con HTTPS automatico)
- Monitoreo (health checks)
- Criterios de exito (servicio levantado, HTTPS funcionando, scheduler corriendo, backup ejecutado al menos una vez)

Espera aprobacion.

Implementa:

1. Docker/Dockerfile multi-stage (builder con uv, runtime slim)

2. Docker/DockerComposeProd.yml:
   - mariadb:11 (volumen persistente, healthcheck, restart policy)
   - redis:7-alpine (volumen persistente)
   - app-api (uvicorn)
   - app-scheduler (mismo image, comando distinto)
   - caddy (reverse proxy HTTPS automatico)

3. Caddyfile

4. Scripts/Backup.sh - dump diario, comprimido, retencion 30 dias, upload
   via rclone (placeholder de config)

5. Scripts/Deploy.sh - pull + migrate + restart

6. docs/Deploy.md con pasos paso a paso:
   - Provisionar Hetzner CX22 Ubuntu 24.04
   - Firewall ufw
   - Usuario no-root
   - Docker + Compose
   - Clonar repo, configurar .env produccion
   - DNS
   - Levantar y verificar

7. systemd unit opcional para auto-start

8. docs/Monitoring.md con Uptime Kuma + checks
```

---

## Notas

- Las fases son iterativas. Si en una fase descubres que un modelo esta mal, ajusta con migracion nueva (no edites la inicial).
- Al cerrar fase: marca checkbox arriba con `- [x]` y commit con Conventional Commits.
- Si Claude Code encuentra bloqueos (HTML cambio, endpoint caido), documentar en `docs/Issues.md` antes de improvisar.
- Si surge una decision tecnica no cubierta en CLAUDE.md ni PROJECT.md, preguntar antes de elegir.
