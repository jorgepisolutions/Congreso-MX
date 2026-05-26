import asyncio
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from CongresoMx.Config import GetSettings
from CongresoMx.Scheduler.Jobs import (
    DetectorSesionSenado,
    ReconciliacionDiaria,
    TZ_CDMX,
)

Logger = logging.getLogger(__name__)


# Heartbeat: loguea cada 5 min que el scheduler sigue vivo. Util para
# monitoreo basico (no usamos uptime/healthcheck externos en el VPS).
def Heartbeat() -> None:
    Logger.info("Scheduler vivo: %s", datetime.now(timezone.utc).isoformat())


# Bootstrap del scheduler: registra los 3 jobs y se queda bloqueado.
# - ReconciliacionDiaria: cron 06:00 CDMX cada dia
# - DetectorSesionSenado: cada 5 min (filtra horario internamente)
# - Heartbeat: cada 5 min para que docker logs muestre actividad
async def Run() -> None:
    Config = GetSettings()
    logging.basicConfig(
        level=Config.LogLevel,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    Logger.info(
        "Iniciando scheduler en EnvName=%s TZ=%s", Config.EnvName, Config.Timezone
    )

    Scheduler = AsyncIOScheduler(timezone=TZ_CDMX)

    Scheduler.add_job(
        ReconciliacionDiaria,
        trigger=CronTrigger(hour=6, minute=0, timezone=TZ_CDMX),
        id="ReconciliacionDiaria",
        max_instances=1,
        coalesce=True,
    )

    Scheduler.add_job(
        DetectorSesionSenado,
        trigger="interval",
        minutes=5,
        id="DetectorSesionSenado",
        max_instances=1,
        coalesce=True,
        kwargs={"Scheduler": Scheduler},
    )

    Scheduler.add_job(
        Heartbeat,
        trigger="interval",
        minutes=5,
        id="Heartbeat",
    )

    Scheduler.start()
    Heartbeat()
    Logger.info(
        "Scheduler arrancado con jobs: %s",
        [J.id for J in Scheduler.get_jobs()],
    )

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
