import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from CongresoMx.Models import (
    Estado,
    Legislador,
    LegisladorPeriodo,
    Legislatura,
    Partido,
    ScrapingRun,
)
from CongresoMx.Scrapers.Diputados.Legisladores import FUENTE, LegisladorMergeado
from CongresoMx.Utils.Texto import NormalizarParaHash

Logger = logging.getLogger(__name__)

CAMARA_DIPUTADOS = "Diputados"


# Estadisticas de una corrida de guardado. Util para reportes y para
# popular ScrapingRuns con valores precisos.
@dataclass
class StatsGuardado:
    Nuevos: int = 0
    Actualizados: int = 0
    SinPartido: int = 0
    SinEstado: int = 0
    Errores: int = 0


# Resuelve siglas/nombre de catalogos a IDs via diccionarios pre-cargados.
# Evita 1 SELECT por diputado.
@dataclass
class CatalogoCache:
    PartidoIdPorSiglas: dict[str, int]
    EstadoIdPorNombreNormalizado: dict[str, int]
    LegislaturaIdPorNumero: dict[str, int]


# Carga los 3 catalogos relevantes una sola vez para usar in-memory durante
# el batch. Si los catalogos cambian a media corrida, no se re-cargan.
async def CargarCatalogos(Session: AsyncSession) -> CatalogoCache:
    PartidoRows = (await Session.execute(select(Partido.Siglas, Partido.Id))).all()
    EstadoRows = (await Session.execute(select(Estado.Nombre, Estado.Id))).all()
    LegRows = (await Session.execute(select(Legislatura.Numero, Legislatura.Id))).all()
    return CatalogoCache(
        PartidoIdPorSiglas={Siglas: Id_ for Siglas, Id_ in PartidoRows},
        EstadoIdPorNombreNormalizado={
            NormalizarParaHash(Nombre): Id_ for Nombre, Id_ in EstadoRows
        },
        LegislaturaIdPorNumero={Numero: Id_ for Numero, Id_ in LegRows},
    )


# Busca un Legislador por NombreHash y actualiza sus campos; si no existe,
# lo crea. Devuelve la fila persistida (con Id) y un bool de "fue nuevo".
async def UpsertLegislador(
    Session: AsyncSession, Datos: LegisladorMergeado
) -> tuple[Legislador, bool]:
    Existing = (
        await Session.execute(
            select(Legislador).where(Legislador.NombreHash == Datos.NombreHash)
        )
    ).scalar_one_or_none()

    if Existing is not None:
        Existing.NombreCompleto = Datos.NombreCompleto
        Existing.Nombre = Datos.Nombre
        Existing.ApellidoPaterno = Datos.ApellidoPaterno
        Existing.ApellidoMaterno = Datos.ApellidoMaterno
        if Datos.FechaNacimiento is not None:
            Existing.FechaNacimiento = Datos.FechaNacimiento
        if Datos.FotoUrl is not None:
            Existing.FotoUrl = Datos.FotoUrl
        return Existing, False

    Nuevo = Legislador(
        NombreCompleto=Datos.NombreCompleto,
        Nombre=Datos.Nombre,
        ApellidoPaterno=Datos.ApellidoPaterno,
        ApellidoMaterno=Datos.ApellidoMaterno,
        NombreHash=Datos.NombreHash,
        FechaNacimiento=Datos.FechaNacimiento,
        FotoUrl=Datos.FotoUrl,
    )
    Session.add(Nuevo)
    await Session.flush()
    return Nuevo, True


# Busca un LegisladorPeriodo por (LegislaturaId, Camara, IdExterno, Fuente)
# y actualiza; si no existe, lo crea. Devuelve (fila, fue_nuevo).
async def UpsertLegisladorPeriodo(
    Session: AsyncSession,
    LegisladorId: int,
    LegislaturaId: int,
    Datos: LegisladorMergeado,
    PartidoId: int | None,
    EstadoId: int | None,
    Fuente: str,
) -> tuple[LegisladorPeriodo, bool]:
    Existing = (
        await Session.execute(
            select(LegisladorPeriodo).where(
                LegisladorPeriodo.LegislaturaId == LegislaturaId,
                LegisladorPeriodo.Camara == CAMARA_DIPUTADOS,
                LegisladorPeriodo.IdExterno == Datos.IdExterno,
                LegisladorPeriodo.Fuente == Fuente,
            )
        )
    ).scalar_one_or_none()

    if Existing is not None:
        Existing.LegisladorId = LegisladorId
        Existing.PartidoId = PartidoId
        Existing.EstadoId = EstadoId
        Existing.Distrito = Datos.Distrito
        Existing.TipoEleccion = Datos.TipoEleccion
        Existing.Curul = Datos.Curul
        return Existing, False

    Nuevo = LegisladorPeriodo(
        LegisladorId=LegisladorId,
        LegislaturaId=LegislaturaId,
        Camara=CAMARA_DIPUTADOS,
        PartidoId=PartidoId,
        EstadoId=EstadoId,
        Distrito=Datos.Distrito,
        TipoEleccion=Datos.TipoEleccion,
        Curul=Datos.Curul,
        EsSuplente=False,
        IdExterno=Datos.IdExterno,
        Fuente=Fuente,
    )
    Session.add(Nuevo)
    await Session.flush()
    return Nuevo, True


# Crea una fila ScrapingRun con Status=Running y devuelve la instancia
# para que el caller le acumule contadores y la cierre al final.
async def IniciarScrapingRun(
    Session: AsyncSession, Tipo: str, Parametros: dict[str, Any]
) -> ScrapingRun:
    Run = ScrapingRun(
        Fuente=FUENTE,
        Tipo=Tipo,
        Parametros=Parametros,
        StartedAt=datetime.now(timezone.utc).replace(tzinfo=None),
        Status="Running",
    )
    Session.add(Run)
    await Session.flush()
    return Run


# Cierra la ScrapingRun con los contadores finales. Tira commit afuera.
def FinalizarScrapingRun(
    Run: ScrapingRun,
    Stats: StatsGuardado,
    Status: str,
    ErrorDetalle: str | None = None,
) -> None:
    Run.Status = Status
    Run.FinishedAt = datetime.now(timezone.utc).replace(tzinfo=None)
    Run.RegistrosNuevos = Stats.Nuevos
    Run.RegistrosActualizados = Stats.Actualizados
    Run.Errores = Stats.Errores
    Run.ErrorDetalle = ErrorDetalle


# Procesa la lista completa de LegisladorMergeado: resuelve catalogos,
# upsert Legislador, upsert LegisladorPeriodo, audita en ScrapingRuns.
# El caller hace commit cuando regresa.
async def GuardarBatch(
    Session: AsyncSession,
    Mergeados: list[LegisladorMergeado],
    NumeroLegislatura: str,
) -> StatsGuardado:
    Cache = await CargarCatalogos(Session)
    LegislaturaId = Cache.LegislaturaIdPorNumero.get(NumeroLegislatura)
    if LegislaturaId is None:
        raise RuntimeError(
            f"Legislatura '{NumeroLegislatura}' no esta en DB. "
            "Corre Scripts/SeedCatalogos.py primero."
        )

    Fuente = f"SITL_{NumeroLegislatura}"
    Stats = StatsGuardado()
    Run = await IniciarScrapingRun(
        Session,
        Tipo="Legisladores",
        Parametros={"Legislatura": NumeroLegislatura, "Total": len(Mergeados)},
    )

    try:
        for Datos in Mergeados:
            PartidoId = (
                Cache.PartidoIdPorSiglas.get(Datos.PartidoSiglas)
                if Datos.PartidoSiglas
                else None
            )
            if Datos.PartidoSiglas and PartidoId is None:
                Logger.warning(
                    "Partido '%s' no esta en catalogo Partidos (Id=%s)",
                    Datos.PartidoSiglas, Datos.IdExterno,
                )
                Stats.SinPartido += 1

            EstadoKey = NormalizarParaHash(Datos.Estado) if Datos.Estado else ""
            EstadoId = Cache.EstadoIdPorNombreNormalizado.get(EstadoKey)
            if Datos.Estado and EstadoId is None:
                Logger.warning(
                    "Estado '%s' no matchea catalogo Estados (Id=%s)",
                    Datos.Estado, Datos.IdExterno,
                )
                Stats.SinEstado += 1

            try:
                Pers, NuevoPers = await UpsertLegislador(Session, Datos)
                _, NuevoPer = await UpsertLegisladorPeriodo(
                    Session,
                    LegisladorId=Pers.Id,
                    LegislaturaId=LegislaturaId,
                    Datos=Datos,
                    PartidoId=PartidoId,
                    EstadoId=EstadoId,
                    Fuente=Fuente,
                )
            except Exception as Exc:
                Logger.error(
                    "Error upsert Id=%s: %s", Datos.IdExterno, Exc, exc_info=True
                )
                Stats.Errores += 1
                continue

            if NuevoPers or NuevoPer:
                Stats.Nuevos += 1
            else:
                Stats.Actualizados += 1

        Status = "Success" if Stats.Errores == 0 else "Partial"
        FinalizarScrapingRun(Run, Stats, Status=Status)
    except Exception as Exc:
        FinalizarScrapingRun(Run, Stats, Status="Failed", ErrorDetalle=str(Exc))
        raise

    return Stats
