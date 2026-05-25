import asyncio
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from CongresoMx.Config import GetSettings

Logger = logging.getLogger(__name__)


# Heartbeat: loguea cada 60s para validar que el contenedor del scheduler
# sigue vivo. Reemplazar por jobs reales (DetectarSesionActiva, etc.)
# en fases siguientes.
def Heartbeat() -> None:
    Logger.info("Scheduler vivo: %s", datetime.now(timezone.utc).isoformat())


# Bootstrap del scheduler. Configura logging, instancia APScheduler,
# registra el heartbeat y mantiene el proceso vivo hasta SIGINT/SIGTERM.
async def Run() -> None:
    Config = GetSettings()
    logging.basicConfig(
        level=Config.LogLevel,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    Logger.info("Iniciando scheduler en EnvName=%s TZ=%s", Config.EnvName, Config.Timezone)

    Scheduler = AsyncIOScheduler(timezone="UTC")
    Scheduler.add_job(Heartbeat, "interval", seconds=60, id="Heartbeat")
    Scheduler.start()
    Heartbeat()

    Stop = asyncio.Event()
    try:
        await Stop.wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        Logger.info("Recibida senial de apagado, cerrando scheduler...")
    finally:
        Scheduler.shutdown(wait=True)


# Entrypoint sincronico para invocar desde el CLI o como modulo.
def Main() -> None:
    asyncio.run(Run())


if __name__ == "__main__":
    Main()
