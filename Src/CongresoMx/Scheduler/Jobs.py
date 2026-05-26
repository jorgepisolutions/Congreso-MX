import logging
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from CongresoMx.Scheduler.DetectorSenado import ConsultarEstadoSenado

Logger = logging.getLogger(__name__)

TZ_CDMX = ZoneInfo("America/Mexico_City")
DIAS_SESION = {0, 1, 2, 3}  # Lunes a Jueves (weekday() devuelve 0=Lun)
HORA_INICIO = 9   # 09:00 CDMX
HORA_FIN = 23     # 23:00 CDMX
CICLOS_SIN_CAMBIOS_PARA_DETENER = 3

CANAL_SENADO = "Asistencias:Senado"

# Estado en memoria del polling vivo del Senado. None si no hay polling activo.
# Lo gestiona el modulo para que el job dinamico se auto-detenga.
_EstadoPollingSenado: dict = {
    "Activo": False,
    "CiclosSinCambios": 0,
    "UltimaFecha": None,
    "JobId": "PollingVivoSenado",
}


# Devuelve True si AHORA en CDMX es dia y hora de sesion (Lun-Jue 9-23h).
def EstamosEnHorarioSesion(Ahora: datetime | None = None) -> bool:
    if Ahora is None:
        Ahora = datetime.now(TZ_CDMX)
    else:
        Ahora = Ahora.astimezone(TZ_CDMX)
    if Ahora.weekday() not in DIAS_SESION:
        return False
    if not (HORA_INICIO <= Ahora.hour < HORA_FIN):
        return False
    return True


# Job: corre cada dia a las 06:00 CDMX. Refresca todos los datos via
# el orquestador Backfill (reusa los helpers del Cli).
async def ReconciliacionDiaria() -> None:
    Logger.info("ReconciliacionDiaria: arrancando full Backfill LXVI...")
    from CongresoMx.Cli import (
        _BackfillAsistencias,
        _BackfillLegisladores,
        _BackfillSeed,
        _BackfillSesiones,
    )
    try:
        await _BackfillSeed()
        for Camara in ("Diputados", "Senado"):
            try:
                ResL = await _BackfillLegisladores(Camara, "LXVI")
                Logger.info("ReconciliacionDiaria %s Legisladores: %s", Camara, ResL)
            except Exception as Exc:
                Logger.error("Reconciliacion %s Legisladores fallo: %s", Camara, Exc)
            try:
                ResS = await _BackfillSesiones(Camara, "LXVI")
                Logger.info("ReconciliacionDiaria %s Sesiones: %s", Camara, ResS)
            except Exception as Exc:
                Logger.error("Reconciliacion %s Sesiones fallo: %s", Camara, Exc)
            try:
                ResA = await _BackfillAsistencias(Camara, "LXVI")
                Logger.info("ReconciliacionDiaria %s Asistencias: %s", Camara, ResA)
            except Exception as Exc:
                Logger.error("Reconciliacion %s Asistencias fallo: %s", Camara, Exc)
        Logger.info("ReconciliacionDiaria completada")
    finally:
        from CongresoMx.Database import DisposeEngine
        await DisposeEngine()


# Job: cada 5 min consulta el endpoint live del Senado. Si hay sesion
# activa y el polling no esta corriendo, agrega el job dinamico.
async def DetectorSesionSenado(Scheduler) -> None:
    if not EstamosEnHorarioSesion():
        return
    try:
        Estado = await ConsultarEstadoSenado()
    except Exception as Exc:
        Logger.error("DetectorSesionSenado fallo: %s", Exc)
        return

    if not Estado.HayActiva:
        if _EstadoPollingSenado["Activo"]:
            Logger.info(
                "Senado: sesion terminada (punto=%r); deteniendo polling",
                Estado.PuntoActual[:80],
            )
            try:
                Scheduler.remove_job(_EstadoPollingSenado["JobId"])
            except Exception:
                pass
            _EstadoPollingSenado["Activo"] = False
            _EstadoPollingSenado["CiclosSinCambios"] = 0
        return

    if _EstadoPollingSenado["Activo"]:
        return

    Logger.info(
        "Senado: SESION ACTIVA detectada (fecha=%s punto=%r); arrancando polling",
        Estado.FechaPortal, Estado.PuntoActual[:80],
    )
    _EstadoPollingSenado["Activo"] = True
    _EstadoPollingSenado["CiclosSinCambios"] = 0
    _EstadoPollingSenado["UltimaFecha"] = Estado.FechaPortal
    Scheduler.add_job(
        PollingVivoSenado,
        trigger="interval",
        seconds=150,
        id=_EstadoPollingSenado["JobId"],
        max_instances=1,
        coalesce=True,
        replace_existing=True,
        kwargs={"Scheduler": Scheduler},
    )


# Job dinamico: cada 2.5 min mientras hay sesion del Senado en vivo.
# Scrapea asistencias del dia, hace diff con DB, publica en Redis.
async def PollingVivoSenado(Scheduler) -> None:
    from collections import defaultdict

    from sqlalchemy import select

    from CongresoMx.Database import GetSessionMaker
    from CongresoMx.Models import Legislatura, ScrapingRun, Sesion
    from CongresoMx.Scrapers.Senado.Asistencias import ScraperSenadoAsistencias
    from CongresoMx.Services.Asistencias import (
        CargarMapaLegisladorPeriodoSenado,
        FinalizarScrapingRun,
        GuardarAsistenciasSesionSenado,
        IniciarScrapingRun,
        StatsAsistencias,
    )
    from CongresoMx.Services.RedisPubSub import Publicar

    # Re-chequea el estado antes de hacer el polling
    try:
        Estado = await ConsultarEstadoSenado()
    except Exception as Exc:
        Logger.error("PollingVivoSenado: estado fallo: %s", Exc)
        return

    if not Estado.HayActiva or Estado.FechaPortal is None:
        Logger.info("PollingVivoSenado: estado dejo de ser activo; deteniendo")
        try:
            Scheduler.remove_job(_EstadoPollingSenado["JobId"])
        except Exception:
            pass
        _EstadoPollingSenado["Activo"] = False
        return

    Hoy = Estado.FechaPortal
    Fuente = "SENADO_LXVI"

    SM = GetSessionMaker()
    async with SM() as Sess:
        Leg = (
            await Sess.execute(
                select(Legislatura).where(Legislatura.Numero == "LXVI")
            )
        ).scalar_one()
        LegislaturaId = Leg.Id
        MapaLegPer = await CargarMapaLegisladorPeriodoSenado(
            Sess, LegislaturaId, Fuente
        )
        # Buscar la sesion del Senado en DB para HOY (la primera por Numero)
        Rows = (
            await Sess.execute(
                select(Sesion.Id, Sesion.Numero).where(
                    Sesion.LegislaturaId == LegislaturaId,
                    Sesion.Camara == "Senado",
                    Sesion.Fecha == Hoy,
                ).order_by(Sesion.Numero)
            )
        ).all()
        if not Rows:
            Logger.warning(
                "PollingVivoSenado: no hay Sesion en DB para fecha=%s; "
                "se necesita Reconciliacion antes de poder scrapear asistencias",
                Hoy,
            )
            return
        SesionId, NumeroGlobal = Rows[0]

    # Heuristica: el AJAX usa NumeroPorAnio, pero hasta tener el listado
    # por_anio actualizado, intentamos con el NumeroGlobal y vemos si funciona.
    async with ScraperSenadoAsistencias(Legislatura="LXVI") as Scraper:
        try:
            Crudas = await Scraper.ScrapearSesion(Hoy, str(NumeroGlobal))
        except Exception as Exc:
            Logger.error(
                "PollingVivoSenado: ScrapearSesion fallo fecha=%s num=%s: %s",
                Hoy, NumeroGlobal, Exc,
            )
            return

    Logger.info(
        "PollingVivoSenado: scrape devolvio %d crudas para sesion=%d",
        len(Crudas), SesionId,
    )

    if not Crudas:
        _EstadoPollingSenado["CiclosSinCambios"] += 1
        if _EstadoPollingSenado["CiclosSinCambios"] >= CICLOS_SIN_CAMBIOS_PARA_DETENER:
            Logger.info(
                "PollingVivoSenado: %d ciclos sin datos; deteniendo",
                _EstadoPollingSenado["CiclosSinCambios"],
            )
            try:
                Scheduler.remove_job(_EstadoPollingSenado["JobId"])
            except Exception:
                pass
            _EstadoPollingSenado["Activo"] = False
        return

    # Hay datos: hacer upsert y publicar a Redis si hubo cambios reales
    async with SM() as Sess:
        Stats = StatsAsistencias()
        Run = await IniciarScrapingRun(
            Sess, Tipo="AsistenciasPollingVivo",
            Parametros={"Camara": "Senado", "SesionId": SesionId, "Fecha": str(Hoy)},
        )
        await Sess.commit()
        RunId = Run.Id

    async with SM() as Sess2:
        await GuardarAsistenciasSesionSenado(
            Sess2, SesionId=SesionId,
            AsistenciasCrudas=Crudas, MapaLegisladorPeriodo=MapaLegPer,
            Fuente=Fuente, Stats=Stats,
        )
        await Sess2.commit()

    async with SM() as Sess3:
        RunReload = (
            await Sess3.execute(select(ScrapingRun).where(ScrapingRun.Id == RunId))
        ).scalar_one()
        FinalizarScrapingRun(
            RunReload, Stats, "Success" if Stats.Errores == 0 else "Partial"
        )
        await Sess3.commit()

    if Stats.Cambios > 0 or Stats.Nuevas > 0:
        Payload = {
            "Camara": "Senado",
            "SesionId": SesionId,
            "Fecha": str(Hoy),
            "Nuevas": Stats.Nuevas,
            "Actualizadas": Stats.Actualizadas,
            "Cambios": Stats.Cambios,
            "Timestamp": datetime.now(timezone.utc).isoformat(),
            "PuntoActual": Estado.PuntoActual[:200],
        }
        await Publicar(f"{CANAL_SENADO}:{SesionId}", Payload)
        _EstadoPollingSenado["CiclosSinCambios"] = 0
    else:
        _EstadoPollingSenado["CiclosSinCambios"] += 1
