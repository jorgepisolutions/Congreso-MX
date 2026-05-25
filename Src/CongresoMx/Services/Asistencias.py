import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from CongresoMx.Models import (
    Asistencia,
    LegisladorPeriodo,
    Legislatura,
    ScrapingRun,
    Sesion,
)
from CongresoMx.Scrapers.Diputados.ParsersAsistencias import AsistenciaCruda
from CongresoMx.Scrapers.Diputados.Sesiones import SCRAPER_FUENTE

Logger = logging.getLogger(__name__)

CAMARA_DIPUTADOS = "Diputados"
CAMARA_SENADO = "Senado"

# Mapeo de codigos del SITL Diputados a Asistencia.Estado.
# Codigos: A (sistema), AC (cedula), AO (comision oficial), PM (permiso mesa),
# IJ (inasistencia justificada), I (inasistencia), IV (inasistencia votaciones).
CODIGO_A_ESTADO: dict[str, str] = {
    "A":  "Presente",
    "AC": "Presente",
    "AO": "ComisionOficial",
    "PM": "Licencia",
    "IJ": "Justificado",
    "I":  "Ausente",
    "IV": "Ausente",
}

# Mapeo de la columna "Registro" del Senado a Asistencia.Estado.
# Senado usa textos descriptivos en mayusculas, no codigos cortos.
REGISTRO_SENADO_A_ESTADO: dict[str, str] = {
    "asistencia": "Presente",
    "ausente": "Ausente",
    "ausencia": "Ausente",
    "inasistencia": "Ausente",
    "inasistencia justificada": "Justificado",
    "justificacion": "Justificado",
    "comision oficial": "ComisionOficial",
    "licencia": "Licencia",
}


# Mapea el texto de la columna Registro del Senado a Asistencia.Estado.
# Devuelve (Estado, EsDesconocido). Normaliza sin acentos antes de mapear.
def MapearRegistroSenadoAEstado(Registro: str) -> tuple[str, bool]:
    from CongresoMx.Utils.Texto import NormalizarParaHash
    Key = NormalizarParaHash(Registro)
    Estado = REGISTRO_SENADO_A_ESTADO.get(Key)
    if Estado is None:
        return "Desconocido", True
    return Estado, False


# Estadisticas de upsert para reporting + ScrapingRun.
@dataclass
class StatsAsistencias:
    Nuevas: int = 0
    Actualizadas: int = 0
    Cambios: int = 0
    CodigosDesconocidos: int = 0
    SesionNoEncontrada: int = 0
    LegPeriodoNoEncontrado: int = 0
    Errores: int = 0


# Traduce codigo SITL al enum Estado. Si no esta mapeado: "Desconocido".
def MapearCodigoAEstado(Codigo: str) -> tuple[str, bool]:
    Estado = CODIGO_A_ESTADO.get(Codigo)
    if Estado is None:
        return "Desconocido", True
    return Estado, False


# Upsert idempotente de Asistencia por (Sesion, LegisladorPeriodo, TipoPaseLista).
# Si la fila existia y el Estado cambio, loggea WARNING y devuelve diff=True.
async def UpsertAsistencia(
    Session: AsyncSession,
    SesionId: int,
    LegisladorPeriodoId: int,
    Estado: str,
    TipoPaseLista: str | None,
    Fuente: str,
) -> tuple[Asistencia, bool, bool]:
    Existing = (
        await Session.execute(
            select(Asistencia).where(
                Asistencia.SesionId == SesionId,
                Asistencia.LegisladorPeriodoId == LegisladorPeriodoId,
                Asistencia.TipoPaseLista == TipoPaseLista if TipoPaseLista is not None
                else Asistencia.TipoPaseLista.is_(None),
            )
        )
    ).scalar_one_or_none()

    if Existing is not None:
        EstadoCambio = Existing.Estado != Estado
        if EstadoCambio:
            Logger.warning(
                "Cambio asistencia Sesion=%d Leg=%d: %s -> %s",
                SesionId, LegisladorPeriodoId, Existing.Estado, Estado,
            )
            Existing.Estado = Estado
            Existing.Fuente = Fuente
        return Existing, False, EstadoCambio

    Nueva = Asistencia(
        SesionId=SesionId,
        LegisladorPeriodoId=LegisladorPeriodoId,
        Estado=Estado,
        TipoPaseLista=TipoPaseLista,
        Fuente=Fuente,
    )
    Session.add(Nueva)
    await Session.flush()
    return Nueva, True, False


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
    Run: ScrapingRun, Stats: StatsAsistencias, Status: str
) -> None:
    Run.Status = Status
    Run.FinishedAt = datetime.now(timezone.utc).replace(tzinfo=None)
    Run.RegistrosNuevos = Stats.Nuevas
    Run.RegistrosActualizados = Stats.Actualizadas
    Run.Errores = Stats.Errores


# Carga (Camara, LegislaturaId, Fecha) -> SesionId desde DB en un solo SELECT.
async def CargarMapaSesiones(
    Session: AsyncSession, LegislaturaId: int, Camara: str = CAMARA_DIPUTADOS
) -> dict[date, int]:
    Rows = (
        await Session.execute(
            select(Sesion.Fecha, Sesion.Id).where(
                Sesion.LegislaturaId == LegislaturaId,
                Sesion.Camara == Camara,
            )
        )
    ).all()
    return {Fecha: Id_ for Fecha, Id_ in Rows}


# Carga mapa (Fecha, NumeroSesion) -> SesionId para Senado, donde una
# fecha puede tener varias sesiones (matutina + vespertina).
async def CargarMapaSesionesSenado(
    Session: AsyncSession, LegislaturaId: int
) -> dict[tuple[date, str], int]:
    Rows = (
        await Session.execute(
            select(Sesion.Fecha, Sesion.Numero, Sesion.Id).where(
                Sesion.LegislaturaId == LegislaturaId,
                Sesion.Camara == CAMARA_SENADO,
            )
        )
    ).all()
    return {(Fecha, str(Numero)): Id_ for Fecha, Numero, Id_ in Rows if Numero}


# Resuelve LegisladorPeriodoId desde IdExterno + Fuente.
async def ResolverLegisladorPeriodoId(
    Session: AsyncSession,
    IdExterno: str,
    LegislaturaId: int,
    FuenteLeg: str,
    Camara: str = CAMARA_DIPUTADOS,
) -> int | None:
    Row = (
        await Session.execute(
            select(LegisladorPeriodo.Id).where(
                LegisladorPeriodo.IdExterno == IdExterno,
                LegisladorPeriodo.LegislaturaId == LegislaturaId,
                LegisladorPeriodo.Camara == Camara,
                LegisladorPeriodo.Fuente == FuenteLeg,
            )
        )
    ).scalar_one_or_none()
    return Row


# Carga TODOS los LegisladorPeriodoId de Senado de la legislatura en
# un dict IdExterno -> Id, evitando 128 SELECTs (1 por senador) por sesion.
async def CargarMapaLegisladorPeriodoSenado(
    Session: AsyncSession, LegislaturaId: int, Fuente: str
) -> dict[str, int]:
    Rows = (
        await Session.execute(
            select(LegisladorPeriodo.IdExterno, LegisladorPeriodo.Id).where(
                LegisladorPeriodo.LegislaturaId == LegislaturaId,
                LegisladorPeriodo.Camara == CAMARA_SENADO,
                LegisladorPeriodo.Fuente == Fuente,
            )
        )
    ).all()
    return {IdExterno: Id_ for IdExterno, Id_ in Rows if IdExterno}


# Procesa las asistencias crudas de UN diputado. Inserta o actualiza
# en DB las filas correspondientes. Devuelve stats para acumulacion.
# El caller hace commit afuera (para que sea por-diputado o por-batch).
async def GuardarAsistenciasDiputado(
    Session: AsyncSession,
    LegisladorPeriodoId: int,
    Asistencias: list[AsistenciaCruda],
    MapaSesiones: dict[date, int],
    Fuente: str,
    Stats: StatsAsistencias,
) -> None:
    for ACruda in Asistencias:
        SesionId = MapaSesiones.get(ACruda.Fecha)
        if SesionId is None:
            Logger.warning(
                "Sesion para %s no esta en DB; skip asistencia de LegPer=%d",
                ACruda.Fecha, LegisladorPeriodoId,
            )
            Stats.SesionNoEncontrada += 1
            continue

        if ACruda.CodigoFinal is None:
            # Dia simple: una sola Asistencia con TipoPaseLista=NULL
            Estado, Desconocido = MapearCodigoAEstado(ACruda.CodigoInicial)
            if Desconocido:
                Logger.warning(
                    "Codigo desconocido %r en %s LegPer=%d",
                    ACruda.CodigoInicial, ACruda.Fecha, LegisladorPeriodoId,
                )
                Stats.CodigosDesconocidos += 1
            try:
                _, EsNueva, Cambio = await UpsertAsistencia(
                    Session,
                    SesionId=SesionId,
                    LegisladorPeriodoId=LegisladorPeriodoId,
                    Estado=Estado,
                    TipoPaseLista=None,
                    Fuente=Fuente,
                )
            except Exception as Exc:
                Logger.error("Error upsert asistencia %s: %s", ACruda.Fecha, Exc)
                Stats.Errores += 1
                continue
            if EsNueva:
                Stats.Nuevas += 1
            else:
                Stats.Actualizadas += 1
            if Cambio:
                Stats.Cambios += 1
            continue

        # Dia doble: dos Asistencias con TipoPaseLista Inicial y Final
        for CodigoRaw, Tipo in (
            (ACruda.CodigoInicial, "Inicial"),
            (ACruda.CodigoFinal, "Final"),
        ):
            Estado, Desconocido = MapearCodigoAEstado(CodigoRaw)
            if Desconocido:
                Logger.warning(
                    "Codigo desconocido %r en %s LegPer=%d Tipo=%s",
                    CodigoRaw, ACruda.Fecha, LegisladorPeriodoId, Tipo,
                )
                Stats.CodigosDesconocidos += 1
            try:
                _, EsNueva, Cambio = await UpsertAsistencia(
                    Session,
                    SesionId=SesionId,
                    LegisladorPeriodoId=LegisladorPeriodoId,
                    Estado=Estado,
                    TipoPaseLista=Tipo,
                    Fuente=Fuente,
                )
            except Exception as Exc:
                Logger.error("Error upsert asistencia %s/%s: %s", ACruda.Fecha, Tipo, Exc)
                Stats.Errores += 1
                continue
            if EsNueva:
                Stats.Nuevas += 1
            else:
                Stats.Actualizadas += 1
            if Cambio:
                Stats.Cambios += 1


# Procesa todas las asistencias de UNA sesion del Senado.
# Una sola fila por (Sesion, Senador) con TipoPaseLista=NULL.
async def GuardarAsistenciasSesionSenado(
    Session: AsyncSession,
    SesionId: int,
    AsistenciasCrudas: list,
    MapaLegisladorPeriodo: dict[str, int],
    Fuente: str,
    Stats: StatsAsistencias,
) -> None:
    for ACruda in AsistenciasCrudas:
        LegPerId = MapaLegisladorPeriodo.get(ACruda.IdSenadorExterno)
        if LegPerId is None:
            Logger.warning(
                "Senador IdExterno=%s no esta en DB; skip asistencia sesion=%d",
                ACruda.IdSenadorExterno, SesionId,
            )
            Stats.LegPeriodoNoEncontrado += 1
            continue
        Estado, Desconocido = MapearRegistroSenadoAEstado(ACruda.RegistroCrudo)
        if Desconocido:
            Logger.warning(
                "Registro Senado no mapeado: %r (senador %s, sesion %d)",
                ACruda.RegistroCrudo, ACruda.IdSenadorExterno, SesionId,
            )
            Stats.CodigosDesconocidos += 1
        try:
            _, EsNueva, Cambio = await UpsertAsistencia(
                Session,
                SesionId=SesionId,
                LegisladorPeriodoId=LegPerId,
                Estado=Estado,
                TipoPaseLista=None,
                Fuente=Fuente,
            )
        except Exception as Exc:
            Logger.error(
                "Error upsert asistencia Senado sesion=%d senador=%s: %s",
                SesionId, ACruda.IdSenadorExterno, Exc,
            )
            Stats.Errores += 1
            continue
        if EsNueva:
            Stats.Nuevas += 1
        else:
            Stats.Actualizadas += 1
        if Cambio:
            Stats.Cambios += 1
