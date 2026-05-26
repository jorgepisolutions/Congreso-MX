from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import case, func, select

from CongresoMx.Api.Deps import (

    LIMITE_DEFAULT,
    Limiter_,
    RequireApiKey,
    SessionDep,
)
from CongresoMx.Api.Schemas import StatInasistente, StatPorPartido
from CongresoMx.Models import (
    Asistencia,
    Estado,
    Legislador,
    LegisladorPeriodo,
    Legislatura,
    Partido,
)

Router = APIRouter(
    prefix="/Stats",
    tags=["Stats"],
    dependencies=[Depends(RequireApiKey)],
)


# Distribucion de asistencia por partido + camara para una legislatura.
@Router.get("/PorPartido", response_model=list[StatPorPartido])
@Limiter_.limit(LIMITE_DEFAULT)
async def StatsPorPartido(
    request: Request,
    Session_: SessionDep,
    Legislatura_: str = Query("LXVI", alias="Legislatura"),
) -> list[StatPorPartido]:
    EstadoCase = lambda E: func.sum(case((Asistencia.Estado == E, 1), else_=0))  # noqa: E731
    Stmt = (
        select(
            LegisladorPeriodo.Camara.label("Camara"),
            Partido.Siglas.label("Partido"),
            func.count().label("TotalRegistros"),
            EstadoCase("Presente").label("Presentes"),
            EstadoCase("Ausente").label("Ausentes"),
            EstadoCase("Justificado").label("Justificados"),
            EstadoCase("ComisionOficial").label("ComisionOficial"),
            EstadoCase("Licencia").label("Licencia"),
        )
        .join(LegisladorPeriodo, LegisladorPeriodo.Id == Asistencia.LegisladorPeriodoId)
        .join(Legislatura, Legislatura.Id == LegisladorPeriodo.LegislaturaId)
        .outerjoin(Partido, Partido.Id == LegisladorPeriodo.PartidoId)
        .where(Legislatura.Numero == Legislatura_)
        .group_by(LegisladorPeriodo.Camara, Partido.Siglas)
        .order_by(LegisladorPeriodo.Camara, Partido.Siglas)
    )
    Rows = (await Session_.execute(Stmt)).all()
    return [
        StatPorPartido(
            Camara=Cam, Partido=Pt or "(Independiente)", TotalRegistros=Tot,
            Presentes=Pres, Ausentes=Aus, Justificados=Just,
            ComisionOficial=CO, Licencia=Lic,
            PctPresencia=round(100 * Pres / Tot, 2) if Tot else 0.0,
        )
        for Cam, Pt, Tot, Pres, Aus, Just, CO, Lic in Rows
    ]


# Top N legisladores con mas inasistencias (Ausente + Justificado).
@Router.get("/TopInasistentes", response_model=list[StatInasistente])
@Limiter_.limit(LIMITE_DEFAULT)
async def TopInasistentes(
    request: Request,
    Session_: SessionDep,
    Legislatura_: str = Query("LXVI", alias="Legislatura"),
    Camara: str | None = Query(None),
    Top: int = Query(10, ge=1, le=100),
) -> list[StatInasistente]:
    EstadoCase = lambda E: func.sum(case((Asistencia.Estado == E, 1), else_=0))  # noqa: E731
    Stmt = (
        select(
            Legislador.Id.label("LegisladorId"),
            Legislador.NombreCompleto.label("NombreCompleto"),
            LegisladorPeriodo.Camara.label("Camara"),
            Partido.Siglas.label("Partido"),
            Estado.Nombre.label("Estado"),
            EstadoCase("Ausente").label("Ausencias"),
            EstadoCase("Justificado").label("Justificadas"),
        )
        .join(LegisladorPeriodo, LegisladorPeriodo.Id == Asistencia.LegisladorPeriodoId)
        .join(Legislador, Legislador.Id == LegisladorPeriodo.LegisladorId)
        .join(Legislatura, Legislatura.Id == LegisladorPeriodo.LegislaturaId)
        .outerjoin(Partido, Partido.Id == LegisladorPeriodo.PartidoId)
        .outerjoin(Estado, Estado.Id == LegisladorPeriodo.EstadoId)
        .where(Legislatura.Numero == Legislatura_)
    )
    if Camara:
        Stmt = Stmt.where(LegisladorPeriodo.Camara == Camara)
    Stmt = (
        Stmt.group_by(Legislador.Id, LegisladorPeriodo.Id, Partido.Siglas, Estado.Nombre)
        .having(EstadoCase("Ausente") > 0)
        .order_by(EstadoCase("Ausente").desc())
        .limit(Top)
    )
    Rows = (await Session_.execute(Stmt)).all()
    return [
        StatInasistente(
            LegisladorId=Lid, NombreCompleto=Nom, Camara=Cam,
            Partido=Pt, Estado=Es, Ausencias=Aus, Justificadas=Just,
        )
        for Lid, Nom, Cam, Pt, Es, Aus, Just in Rows
    ]
