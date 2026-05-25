import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from CongresoMx.Config import GetSettings
from CongresoMx.Models import Base

Config = context.config

if Config.config_file_name is not None:
    fileConfig(Config.config_file_name)

# Sobreescribe sqlalchemy.url con el valor real del .env. Esto evita
# guardar credenciales en alembic.ini.
Config.set_main_option("sqlalchemy.url", GetSettings().DatabaseUrl)

TargetMetadata = Base.metadata


# Ejecuta las migraciones dentro de una conexion sync (Alembic exige sync).
# Esto se llama desde do_run_migrations_async via connection.run_sync.
def DoRunMigrations(Connection_: Connection) -> None:
    context.configure(
        connection=Connection_,
        target_metadata=TargetMetadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# Crea el AsyncEngine y delega DoRunMigrations envuelto en run_sync.
# NullPool: no necesitamos pool para una corrida one-shot de migracion.
async def RunAsyncMigrations() -> None:
    Connectable = async_engine_from_config(
        Config.get_section(Config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with Connectable.connect() as Connection_:
        await Connection_.run_sync(DoRunMigrations)
    await Connectable.dispose()


# Entrypoint cuando alembic corre en modo online (con DB real).
# El modo offline no se soporta porque usamos async engine.
def RunMigrationsOnline() -> None:
    asyncio.run(RunAsyncMigrations())


if context.is_offline_mode():
    raise RuntimeError(
        "Modo offline no soportado: este proyecto usa AsyncEngine con MariaDB."
    )
else:
    RunMigrationsOnline()
