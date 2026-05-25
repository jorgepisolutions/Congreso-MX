# Congreso MX

Sistema ETL para datos del Congreso de la Union de Mexico (Camara de Diputados y Senado de la Republica).

Estado: en desarrollo. Ver `docs/Phases.md`.

## Quick Start

```bash
cp .env.example .env
docker compose -f Docker/DockerCompose.yml up -d
uv sync
alembic upgrade head

uv run congreso backfill --legislatura LXVI
uv run congreso serve
uv run congreso scheduler run
```

## Documentacion

- `CLAUDE.md`: convenciones generales (no editar)
- `PROJECT.md`: contexto especifico del proyecto Congreso MX
- `docs/Architecture.md`: arquitectura y modelo de datos
- `docs/Phases.md`: plan de desarrollo por fases
- `docs/Recon.md`: guia de reconnaissance de portales

## Stack

Python 3.11+, MariaDB 11, SQLAlchemy 2.0 async, FastAPI, Redis, Docker.

## Licencia

Privado.
