from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import and_, func, select

from CongresoMx.Api.Deps import (
    ApiKeyOrIp,
    LIMITE_DEFAULT,
    Limiter_,
    RequireApiKey,
    SessionDep,
)
from CongresoMx.Api.Schemas import AsistenciaEntry, PaginatedResponse
from CongresoMx.Models import (
    Asistencia,
    Legislador,
    LegisladorPeriodo,
    Partido,
    Sesion,
)

Router = APIRouter(
    prefix="/Asistencias",
    tags=["Asistencias"],
    dependencies=[Depends(RequireApiKey)],
)


# Lista global de asistencias con filtros. Por defecto limita a 50 para
# no devolver 78,000 filas por accidente.
@Router.get("", response_model=PaginatedResponse[AsistenciaEntry])
@Limiter_.limit(LIMITE_DEFAULT, key_func=ApiKeyOrIp)
async def ListarAsistencias(
    request: Request,
    Session_: SessionDep,
    Camara: str | None = Query(None),
    Fecha: date | None = Query(None),
    Estado_: str | None = Query(None, alias="Estado"),
    Desde: date | None = Query(None),
    Hasta: date | None = Query(None),
    Limit: int = Query(50, ge=1, le=500),
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
    )
    Cond = []
    if Camara:
        Cond.append(Sesion.Camara == Camara)
    if Fecha:
        Cond.append(Sesion.Fecha == Fecha)
    if Estado_:
        Cond.append(Asistencia.Estado == Estado_)
    if Desde:
        Cond.append(Sesion.Fecha >= Desde)
    if Hasta:
        Cond.append(Sesion.Fecha <= Hasta)
    if Cond:
        Stmt = Stmt.where(and_(*Cond))

    CountStmt = select(func.count()).select_from(Stmt.order_by(None).subquery())
    Total = (await Session_.execute(CountStmt)).scalar_one()

    Rows = (
        await Session_.execute(
            Stmt.order_by(Sesion.Fecha.desc(), Legislador.NombreCompleto)
            .limit(Limit).offset(Offset)
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
