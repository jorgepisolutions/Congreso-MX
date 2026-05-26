from typing import Annotated

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
    CargoDetalle,
    LegisladorDetalle,
    LegisladorResumen,
    PaginatedResponse,
)
from CongresoMx.Models import (
    Asistencia,
    Estado,
    Legislador,
    LegisladorPeriodo,
    Legislatura,
    Partido,
    Sesion,
)

Router = APIRouter(
    prefix="/Legisladores",
    tags=["Legisladores"],
    dependencies=[Depends(RequireApiKey)],
)


# Lista paginada de legisladores con filtros opcionales.
@Router.get("", response_model=PaginatedResponse[LegisladorResumen])
@Limiter_.limit(LimitParaKey, key_func=ApiKeyOrIp)
async def ListarLegisladores(
    request: Request,
    Session_: SessionDep,
    Camara: str | None = Query(None, description="Diputados o Senado"),
    Partido_: str | None = Query(None, alias="Partido", description="Siglas del partido (MORENA, PAN, etc.)"),
    Estado_: str | None = Query(None, alias="Estado", description="Nombre o clave del estado"),
    Legislatura_: str | None = Query("LXVI", alias="Legislatura"),
    Limit: int = Query(50, ge=1, le=500),
    Offset: int = Query(0, ge=0),
) -> PaginatedResponse[LegisladorResumen]:
    Stmt = (
        select(
            Legislador.Id,
            Legislador.NombreCompleto,
            LegisladorPeriodo.Camara,
            Partido.Siglas,
            Estado.Nombre,
            LegisladorPeriodo.TipoEleccion,
        )
        .join(LegisladorPeriodo, LegisladorPeriodo.LegisladorId == Legislador.Id)
        .outerjoin(Partido, Partido.Id == LegisladorPeriodo.PartidoId)
        .outerjoin(Estado, Estado.Id == LegisladorPeriodo.EstadoId)
        .join(Legislatura, Legislatura.Id == LegisladorPeriodo.LegislaturaId)
    )
    Cond = []
    if Camara:
        Cond.append(LegisladorPeriodo.Camara == Camara)
    if Partido_:
        Cond.append(Partido.Siglas == Partido_)
    if Estado_:
        Cond.append((Estado.Nombre == Estado_) | (Estado.Clave == Estado_))
    if Legislatura_:
        Cond.append(Legislatura.Numero == Legislatura_)
    if Cond:
        Stmt = Stmt.where(and_(*Cond))

    # Total sin paginar
    CountStmt = select(func.count()).select_from(Stmt.order_by(None).subquery())
    Total = (await Session_.execute(CountStmt)).scalar_one()

    Rows = (
        await Session_.execute(
            Stmt.order_by(Legislador.NombreCompleto).limit(Limit).offset(Offset)
        )
    ).all()
    Items = [
        LegisladorResumen(
            Id=Id_, NombreCompleto=Nombre, Camara=Camara_, Partido=Partido_Sig,
            Estado=Estado_Nom, TipoEleccion=Tipo,
        )
        for Id_, Nombre, Camara_, Partido_Sig, Estado_Nom, Tipo in Rows
    ]
    return PaginatedResponse(Items=Items, Total=Total, Limit=Limit, Offset=Offset)


# Detalle de un legislador con todos sus cargos (LegisladorPeriodo).
@Router.get("/{LegisladorId}", response_model=LegisladorDetalle)
@Limiter_.limit(LimitParaKey, key_func=ApiKeyOrIp)
async def DetalleLegislador(
    request: Request,
    LegisladorId: int,
    Session_: SessionDep,
) -> LegisladorDetalle:
    Persona = (
        await Session_.execute(
            select(Legislador).where(Legislador.Id == LegisladorId)
        )
    ).scalar_one_or_none()
    if Persona is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Legislador no encontrado")

    Rows = (
        await Session_.execute(
            select(
                LegisladorPeriodo.Id,
                LegisladorPeriodo.Camara,
                Legislatura.Numero,
                Partido.Siglas,
                Estado.Nombre,
                LegisladorPeriodo.TipoEleccion,
                LegisladorPeriodo.Distrito,
                LegisladorPeriodo.Curul,
                LegisladorPeriodo.EsSuplente,
                LegisladorPeriodo.Fuente,
                LegisladorPeriodo.IdExterno,
            )
            .join(Legislatura, Legislatura.Id == LegisladorPeriodo.LegislaturaId)
            .outerjoin(Partido, Partido.Id == LegisladorPeriodo.PartidoId)
            .outerjoin(Estado, Estado.Id == LegisladorPeriodo.EstadoId)
            .where(LegisladorPeriodo.LegisladorId == LegisladorId)
        )
    ).all()
    Cargos = [
        CargoDetalle(
            Id=Id_, Camara=Cam, LegislaturaNumero=LegNum, Partido=Pt, Estado=Es,
            TipoEleccion=Tipo, Distrito=Dist, Curul=Cur, EsSuplente=Suplt,
            Fuente=Fu, IdExterno=IdExt,
        )
        for Id_, Cam, LegNum, Pt, Es, Tipo, Dist, Cur, Suplt, Fu, IdExt in Rows
    ]
    return LegisladorDetalle(
        Id=Persona.Id,
        NombreCompleto=Persona.NombreCompleto,
        Nombre=Persona.Nombre,
        ApellidoPaterno=Persona.ApellidoPaterno,
        ApellidoMaterno=Persona.ApellidoMaterno,
        Genero=Persona.Genero,
        FechaNacimiento=Persona.FechaNacimiento,
        FotoUrl=Persona.FotoUrl,
        Cargos=Cargos,
    )


# Lista de asistencias del legislador, con filtros opcionales.
@Router.get(
    "/{LegisladorId}/Asistencias",
    response_model=PaginatedResponse[AsistenciaEntry],
)
@Limiter_.limit(LimitParaKey, key_func=ApiKeyOrIp)
async def AsistenciasDelLegislador(
    request: Request,
    LegisladorId: int,
    Session_: SessionDep,
    Estado_: str | None = Query(None, alias="Estado"),
    Desde: str | None = Query(None, description="YYYY-MM-DD"),
    Hasta: str | None = Query(None, description="YYYY-MM-DD"),
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
        .where(Legislador.Id == LegisladorId)
    )
    if Estado_:
        Stmt = Stmt.where(Asistencia.Estado == Estado_)
    if Desde:
        Stmt = Stmt.where(Sesion.Fecha >= Desde)
    if Hasta:
        Stmt = Stmt.where(Sesion.Fecha <= Hasta)

    CountStmt = select(func.count()).select_from(Stmt.order_by(None).subquery())
    Total = (await Session_.execute(CountStmt)).scalar_one()

    Rows = (
        await Session_.execute(
            Stmt.order_by(Sesion.Fecha, Asistencia.TipoPaseLista)
            .limit(Limit).offset(Offset)
        )
    ).all()
    Items = [
        AsistenciaEntry(
            Id=Aid, SesionId=Sid, Fecha=Fecha, Camara=Cam, NumeroSesion=Num,
            TipoSesion=TS, LegisladorId=Lid, NombreCompleto=Nom, Partido=Pt,
            Estado=Est, TipoPaseLista=TPL, Fuente=Fu,
        )
        for Aid, Sid, Fecha, Cam, Num, TS, Lid, Nom, Pt, Est, TPL, Fu in Rows
    ]
    return PaginatedResponse(Items=Items, Total=Total, Limit=Limit, Offset=Offset)
