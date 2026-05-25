import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from CongresoMx.Models import Legislatura, Periodo, ScrapingRun, Sesion
from CongresoMx.Scrapers.Diputados.Sesiones import (
    PERT_TO_PERIODO_KEY,
    SCRAPER_FUENTE,
    SesionCruda,
)

Logger = logging.getLogger(__name__)

CAMARA_DIPUTADOS = "Diputados"


# Estadisticas de upsert de sesiones, devuelta al CLI para reportes.
@dataclass
class StatsSesiones:
    Nuevas: int = 0
    Actualizadas: int = 0
    SinPeriodo: int = 0
    Errores: int = 0


# Mapeo (AnioLegislativo, NumeroPeriodo, TipoPeriodo) -> PeriodoId,
# cargado una sola vez al inicio del batch.
async def _CargarPeriodos(
    Session: AsyncSession, LegislaturaId: int
) -> dict[tuple[int, int, str], int]:
    Rows = (
        await Session.execute(
            select(
                Periodo.AnioLegislativo,
                Periodo.Numero,
                Periodo.Tipo,
                Periodo.Id,
            ).where(Periodo.LegislaturaId == LegislaturaId)
        )
    ).all()
    return {(Anio, Num, Tipo): Id_ for Anio, Num, Tipo, Id_ in Rows}


# Mapea el tipo del Periodo (Ordinario|Extraordinario) al tipo de la Sesion
# (Ordinaria|Extraordinaria). Conversion 1:1 en feminino.
def _TipoSesionDesdePeriodoTipo(TipoPeriodo: str) -> str:
    return "Ordinaria" if TipoPeriodo == "Ordinario" else "Extraordinaria"


# Devuelve el Estado de la sesion segun la fecha actual.
# Concluida si la fecha es <= hoy; Programada si es futura.
def _EstadoSesionPorFecha(Fecha: date, Hoy: date) -> str:
    return "Concluida" if Fecha <= Hoy else "Programada"


# Busca por (Camara, LegislaturaId, Fecha, Numero=NULL) y actualiza, o crea.
# Devuelve (Sesion, EsNueva).
async def UpsertSesion(
    Session: AsyncSession,
    LegislaturaId: int,
    PeriodoId: int,
    Fecha: date,
    Tipo: str,
    Estado: str,
) -> tuple[Sesion, bool]:
    Existing = (
        await Session.execute(
            select(Sesion).where(
                Sesion.Camara == CAMARA_DIPUTADOS,
                Sesion.LegislaturaId == LegislaturaId,
                Sesion.Fecha == Fecha,
                Sesion.Numero.is_(None),
            )
        )
    ).scalar_one_or_none()

    if Existing is not None:
        Existing.PeriodoId = PeriodoId
        Existing.Tipo = Tipo
        Existing.Estado = Estado
        return Existing, False

    Nueva = Sesion(
        LegislaturaId=LegislaturaId,
        PeriodoId=PeriodoId,
        Camara=CAMARA_DIPUTADOS,
        Numero=None,
        Tipo=Tipo,
        Fecha=Fecha,
        Estado=Estado,
    )
    Session.add(Nueva)
    await Session.flush()
    return Nueva, True


# Crea fila ScrapingRun con Status=Running y devuelve la instancia.
async def IniciarScrapingRun(
    Session: AsyncSession, Tipo: str, Parametros: dict[str, Any]
) -> ScrapingRun:
    Run = ScrapingRun(
        Fuente=SCRAPER_FUENTE,
        Tipo=Tipo,
        Parametros=Parametros,
        StartedAt=datetime.now(timezone.utc).replace(tzinfo=None),
        Status="Running",
    )
    Session.add(Run)
    await Session.flush()
    return Run


# Cierra la ScrapingRun con los contadores finales.
def FinalizarScrapingRun(
    Run: ScrapingRun, Stats: StatsSesiones, Status: str
) -> None:
    Run.Status = Status
    Run.FinishedAt = datetime.now(timezone.utc).replace(tzinfo=None)
    Run.RegistrosNuevos = Stats.Nuevas
    Run.RegistrosActualizados = Stats.Actualizadas
    Run.Errores = Stats.Errores


# Procesa las sesiones crudas: resuelve PeriodoId via PERT_TO_PERIODO_KEY,
# upsert por fecha, audita en ScrapingRuns. Caller hace commit.
async def GuardarBatchSesiones(
    Session: AsyncSession,
    Sesiones: list[SesionCruda],
    NumeroLegislatura: str,
) -> StatsSesiones:
    Leg = (
        await Session.execute(
            select(Legislatura).where(Legislatura.Numero == NumeroLegislatura)
        )
    ).scalar_one_or_none()
    if Leg is None:
        raise RuntimeError(
            f"Legislatura '{NumeroLegislatura}' no esta en DB. Corre el seed."
        )

    PeriodoMap = await _CargarPeriodos(Session, Leg.Id)
    Hoy = datetime.now(timezone.utc).date()
    Stats = StatsSesiones()

    Run = await IniciarScrapingRun(
        Session,
        Tipo="Sesiones",
        Parametros={"Legislatura": NumeroLegislatura, "Total": len(Sesiones)},
    )

    try:
        for SCruda in Sesiones:
            Key = PERT_TO_PERIODO_KEY.get(SCruda.Pert)
            if Key is None:
                Logger.warning(
                    "Pert %d no mapeado a Periodo; skip sesion %s",
                    SCruda.Pert, SCruda.Fecha,
                )
                Stats.SinPeriodo += 1
                continue
            PeriodoId = PeriodoMap.get(Key)
            if PeriodoId is None:
                Logger.warning(
                    "Periodo %s no esta en DB; corre Scripts/SeedCatalogos.py. Skip %s",
                    Key, SCruda.Fecha,
                )
                Stats.SinPeriodo += 1
                continue

            Tipo = _TipoSesionDesdePeriodoTipo(Key[2])
            Estado = _EstadoSesionPorFecha(SCruda.Fecha, Hoy)
            try:
                _, EsNueva = await UpsertSesion(
                    Session,
                    LegislaturaId=Leg.Id,
                    PeriodoId=PeriodoId,
                    Fecha=SCruda.Fecha,
                    Tipo=Tipo,
                    Estado=Estado,
                )
            except Exception as Exc:
                Logger.error(
                    "Error upsert sesion %s: %s", SCruda.Fecha, Exc, exc_info=True
                )
                Stats.Errores += 1
                continue

            if EsNueva:
                Stats.Nuevas += 1
            else:
                Stats.Actualizadas += 1

        FinalStatus = "Success" if Stats.Errores == 0 else "Partial"
        FinalizarScrapingRun(Run, Stats, FinalStatus)
    except Exception:
        FinalizarScrapingRun(Run, Stats, "Failed")
        raise

    return Stats
