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
CAMARA_SENADO = "Senado"

# Prioridad de Periodo.Tipo cuando una fecha cae en varios periodos
# (ej. Ordinario y Extraordinario solapados). Permanente gana para
# las sesiones que el Senado etiqueta como Comision Permanente.
PRIORIDAD_PERIODO_PARA_SESION_PERMANENTE = ["Permanente", "Extraordinario", "Ordinario"]
PRIORIDAD_PERIODO_PARA_SESION_REGULAR = ["Ordinario", "Extraordinario", "Permanente"]


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


# Upsert idempotente de Sesion. Match por (Camara, LegislaturaId, Fecha, Numero).
# Para Senado, Numero viene del portal. Para Diputados, queda None.
async def UpsertSesion(
    Session: AsyncSession,
    LegislaturaId: int,
    PeriodoId: int,
    Fecha: date,
    Tipo: str,
    Estado: str,
    Camara: str = CAMARA_DIPUTADOS,
    Numero: str | None = None,
    UrlGaceta: str | None = None,
    UrlActa: str | None = None,
    UrlVideo: str | None = None,
) -> tuple[Sesion, bool]:
    NumeroCond = (
        Sesion.Numero.is_(None) if Numero is None else Sesion.Numero == Numero
    )
    Existing = (
        await Session.execute(
            select(Sesion).where(
                Sesion.Camara == Camara,
                Sesion.LegislaturaId == LegislaturaId,
                Sesion.Fecha == Fecha,
                NumeroCond,
            )
        )
    ).scalar_one_or_none()

    if Existing is not None:
        Existing.PeriodoId = PeriodoId
        Existing.Tipo = Tipo
        Existing.Estado = Estado
        if UrlGaceta:
            Existing.UrlGaceta = UrlGaceta
        if UrlActa:
            Existing.UrlActa = UrlActa
        if UrlVideo:
            Existing.UrlVideo = UrlVideo
        return Existing, False

    Nueva = Sesion(
        LegislaturaId=LegislaturaId,
        PeriodoId=PeriodoId,
        Camara=Camara,
        Numero=Numero,
        Tipo=Tipo,
        Fecha=Fecha,
        Estado=Estado,
        UrlGaceta=UrlGaceta,
        UrlActa=UrlActa,
        UrlVideo=UrlVideo,
    )
    Session.add(Nueva)
    await Session.flush()
    return Nueva, True


# Carga periodos como lista de tuplas (Tipo, FechaInicio, FechaFin, PeriodoId)
# para resolver por fecha en O(N) (N=11 periodos LXVI, despreciable).
async def CargarPeriodosPorFecha(
    Session: AsyncSession, LegislaturaId: int
) -> list[tuple[str, date, date, int]]:
    from CongresoMx.Models import Periodo
    Rows = (
        await Session.execute(
            select(Periodo.Tipo, Periodo.FechaInicio, Periodo.FechaFin, Periodo.Id).where(
                Periodo.LegislaturaId == LegislaturaId
            )
        )
    ).all()
    return [(Tipo, FechaIni, FechaFin, Id_) for Tipo, FechaIni, FechaFin, Id_ in Rows]


# Resuelve PeriodoId para una fecha dada. Si la fecha cae en mas de un
# periodo (Ordinario y Extraordinario solapados), aplica Prioridad.
# Devuelve None si la fecha no cae en ningun periodo.
def ResolverPeriodoIdPorFecha(
    Periodos: list[tuple[str, date, date, int]],
    Fecha: date,
    Prioridad: list[str],
) -> int | None:
    Candidatos = [
        (Tipo, Id_)
        for Tipo, FechaIni, FechaFin, Id_ in Periodos
        if FechaIni <= Fecha <= FechaFin
    ]
    if not Candidatos:
        return None
    Candidatos.sort(key=lambda X: Prioridad.index(X[0]) if X[0] in Prioridad else 999)
    return Candidatos[0][1]


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


# Procesa sesiones del Senado: upsert por (Camara, LegislaturaId, Fecha, Numero).
# Resuelve PeriodoId por fecha con prioridad segun Tipo de sesion.
async def GuardarBatchSesionesSenado(
    Session: AsyncSession,
    Sesiones: list,
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

    Periodos = await CargarPeriodosPorFecha(Session, Leg.Id)
    if not Periodos:
        raise RuntimeError(
            f"No hay Periodos para legislatura {NumeroLegislatura}. Corre el seed."
        )
    Hoy = datetime.now(timezone.utc).date()
    Stats = StatsSesiones()

    Run = await IniciarScrapingRun(
        Session,
        Tipo="Sesiones",
        Parametros={
            "Legislatura": NumeroLegislatura,
            "Camara": CAMARA_SENADO,
            "Total": len(Sesiones),
        },
    )

    try:
        for SCruda in Sesiones:
            # Sesiones Permanente priorizan Periodo.Tipo='Permanente' para
            # asignacion; las demas priorizan Ordinario.
            Prioridad = (
                PRIORIDAD_PERIODO_PARA_SESION_PERMANENTE
                if SCruda.Tipo == "Permanente"
                else PRIORIDAD_PERIODO_PARA_SESION_REGULAR
            )
            PeriodoId = ResolverPeriodoIdPorFecha(Periodos, SCruda.Fecha, Prioridad)
            if PeriodoId is None:
                Logger.warning(
                    "Sesion %s (%s) no cae en ningun Periodo; skip",
                    SCruda.Numero, SCruda.Fecha,
                )
                Stats.SinPeriodo += 1
                continue

            Estado = _EstadoSesionPorFecha(SCruda.Fecha, Hoy)
            try:
                _, EsNueva = await UpsertSesion(
                    Session,
                    LegislaturaId=Leg.Id,
                    PeriodoId=PeriodoId,
                    Fecha=SCruda.Fecha,
                    Tipo=SCruda.Tipo,
                    Estado=Estado,
                    Camara=CAMARA_SENADO,
                    Numero=SCruda.Numero,
                    UrlGaceta=SCruda.UrlGaceta,
                    UrlActa=SCruda.UrlActa,
                    UrlVideo=SCruda.UrlVideo,
                )
            except Exception as Exc:
                Logger.error("Error upsert sesion %s: %s", SCruda.Fecha, Exc, exc_info=True)
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
