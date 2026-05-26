from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import and_, func, select

from CongresoMx.Api.Deps import (
    ApiKeyOrIp,
    LimitParaKey,
    Limiter_,
    RequireApiKey,
    SessionDep,
)
from CongresoMx.Api.Schemas import (
    AsistenciaEntry,
    PaginatedResponse,
    SesionDetalle,
    SesionResumen,
)
from CongresoMx.Models import (
    Asistencia,
    Legislador,
    LegisladorPeriodo,
    Legislatura,
    Partido,
    Periodo,
    Sesion,
)

Router = APIRouter(
    prefix="/Sesiones",
    tags=["Sesiones"],
    dependencies=[Depends(RequireApiKey)],
)


# Lista paginada de sesiones con filtros opcionales.
@Router.get("", response_model=PaginatedResponse[SesionResumen])
@Limiter_.limit(LimitParaKey, key_func=ApiKeyOrIp)
async def ListarSesiones(
    request: Request,
    Session_: SessionDep,
    Camara: str | None = Query(None),
    Desde: date | None = Query(None),
    Hasta: date | None = Query(None),
    Tipo: str | None = Query(None),
    Limit: int = Query(50, ge=1, le=500),
    Offset: int = Query(0, ge=0),
) -> PaginatedResponse[SesionResumen]:
    Stmt = select(
        Sesion.Id, Sesion.Fecha, Sesion.Camara, Sesion.Tipo, Sesion.Estado, Sesion.Numero
    )
    Cond = []
    if Camara:
        Cond.append(Sesion.Camara == Camara)
    if Desde:
        Cond.append(Sesion.Fecha >= Desde)
    if Hasta:
        Cond.append(Sesion.Fecha <= Hasta)
    if Tipo:
        Cond.append(Sesion.Tipo == Tipo)
    if Cond:
        Stmt = Stmt.where(and_(*Cond))

    CountStmt = select(func.count()).select_from(Stmt.order_by(None).subquery())
    Total = (await Session_.execute(CountStmt)).scalar_one()

    Rows = (
        await Session_.execute(
            Stmt.order_by(Sesion.Fecha.desc(), Sesion.Camara, Sesion.Numero)
            .limit(Limit).offset(Offset)
        )
    ).all()
    Items = [
        SesionResumen(Id=I, Fecha=F, Camara=C, Tipo=T, Estado=E, Numero=N)
        for I, F, C, T, E, N in Rows
    ]
    return PaginatedResponse(Items=Items, Total=Total, Limit=Limit, Offset=Offset)


# Detalle de una sesion incluyendo metadata de Periodo y Legislatura.
@Router.get("/{SesionId}", response_model=SesionDetalle)
@Limiter_.limit(LimitParaKey, key_func=ApiKeyOrIp)
async def DetalleSesion(
    request: Request,
    SesionId: int,
    Session_: SessionDep,
) -> SesionDetalle:
    Row = (
        await Session_.execute(
            select(
                Sesion, Legislatura.Numero, Periodo.AnioLegislativo,
                Periodo.Numero, Periodo.Tipo,
            )
            .join(Legislatura, Legislatura.Id == Sesion.LegislaturaId)
            .outerjoin(Periodo, Periodo.Id == Sesion.PeriodoId)
            .where(Sesion.Id == SesionId)
        )
    ).first()
    if Row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Sesion no encontrada")
    Ses, LegNum, AnioP, NumP, TipoP = Row
    return SesionDetalle(
        Id=Ses.Id,
        Fecha=Ses.Fecha,
        Camara=Ses.Camara,
        Tipo=Ses.Tipo,
        Estado=Ses.Estado,
        Numero=Ses.Numero,
        LegislaturaNumero=LegNum,
        PeriodoAnio=AnioP,
        PeriodoNumero=NumP,
        PeriodoTipo=TipoP,
        HoraInicio=str(Ses.HoraInicio) if Ses.HoraInicio else None,
        HoraFin=str(Ses.HoraFin) if Ses.HoraFin else None,
        QuorumInicial=Ses.QuorumInicial,
        QuorumFinal=Ses.QuorumFinal,
        UrlGaceta=Ses.UrlGaceta,
        UrlActa=Ses.UrlActa,
        UrlVideo=Ses.UrlVideo,
    )


# Lista de asistencias de UNA sesion. Util para ver quien estuvo donde.
@Router.get(
    "/{SesionId}/Asistencias",
    response_model=PaginatedResponse[AsistenciaEntry],
)
@Limiter_.limit(LimitParaKey, key_func=ApiKeyOrIp)
async def AsistenciasDeSesion(
    request: Request,
    SesionId: int,
    Session_: SessionDep,
    Estado_: str | None = Query(None, alias="Estado"),
    Limit: int = Query(200, ge=1, le=500),
    Offset: int = Query(0, ge=0),
) -> PaginatedResponse[AsistenciaEntry]:
    Stmt = (
        select(
            Asistencia.Id, Asistencia.SesionId, Sesion.Fecha, Sesion.Camara,
            Sesion.Numero, Sesion.Tipo, Legislador.Id, Legislador.NombreCompleto,
            Partido.Siglas, Asistencia.Estado, Asistencia.TipoPaseLista, Asistencia.Fuente,
        )
        .join(LegisladorPeriodo, LegisladorPeriodo.Id == Asistencia.LegisladorPeriodoId)
        .join(Legislador, Legislador.Id == LegisladorPeriodo.LegisladorId)
        .join(Sesion, Sesion.Id == Asistencia.SesionId)
        .outerjoin(Partido, Partido.Id == LegisladorPeriodo.PartidoId)
        .where(Asistencia.SesionId == SesionId)
    )
    if Estado_:
        Stmt = Stmt.where(Asistencia.Estado == Estado_)

    CountStmt = select(func.count()).select_from(Stmt.order_by(None).subquery())
    Total = (await Session_.execute(CountStmt)).scalar_one()

    Rows = (
        await Session_.execute(
            Stmt.order_by(Legislador.NombreCompleto).limit(Limit).offset(Offset)
        )
    ).all()
    Items = [
        AsistenciaEntry(
            Id=Aid, SesionId=Sid, Fecha=F, Camara=C, NumeroSesion=N, TipoSesion=Ts,
            LegisladorId=Lid, NombreCompleto=Nom, Partido=Pt, Estado=Est,
            TipoPaseLista=Tpl, Fuente=Fu,
        )
        for Aid, Sid, F, C, N, Ts, Lid, Nom, Pt, Est, Tpl, Fu in Rows
    ]
    return PaginatedResponse(Items=Items, Total=Total, Limit=Limit, Offset=Offset)
