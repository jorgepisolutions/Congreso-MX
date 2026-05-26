from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select

from CongresoMx.Api.Deps import (
    ApiKeyOrIp,
    LimitParaKey,
    Limiter_,
    RequireApiKey,
    SessionDep,
)
from CongresoMx.Api.Schemas import PaginatedResponse, VotacionEntry
from CongresoMx.Models import Sesion, Votacion

Router = APIRouter(
    prefix="/Votaciones",
    tags=["Votaciones"],
    dependencies=[Depends(RequireApiKey)],
)


# Lista de votaciones. La tabla esta vacia hoy (Fase 5 scrappeó solo
# asistencias, no votos). Cuando scrapeemos votaciones, este endpoint
# las exposera sin cambios de codigo.
@Router.get("", response_model=PaginatedResponse[VotacionEntry])
@Limiter_.limit(LimitParaKey, key_func=ApiKeyOrIp)
async def ListarVotaciones(
    request: Request,
    Session_: SessionDep,
    Camara: str | None = Query(None),
    SesionId: int | None = Query(None),
    Limit: int = Query(50, ge=1, le=500),
    Offset: int = Query(0, ge=0),
) -> PaginatedResponse[VotacionEntry]:
    Stmt = (
        select(
            Votacion.Id, Votacion.SesionId, Votacion.Numero, Votacion.Asunto,
            Votacion.Tipo, Votacion.Resultado,
        )
        .join(Sesion, Sesion.Id == Votacion.SesionId)
    )
    if Camara:
        Stmt = Stmt.where(Sesion.Camara == Camara)
    if SesionId:
        Stmt = Stmt.where(Votacion.SesionId == SesionId)

    CountStmt = select(func.count()).select_from(Stmt.order_by(None).subquery())
    Total = (await Session_.execute(CountStmt)).scalar_one()

    Rows = (
        await Session_.execute(
            Stmt.order_by(Votacion.SesionId.desc(), Votacion.Numero)
            .limit(Limit).offset(Offset)
        )
    ).all()
    Items = [
        VotacionEntry(Id=I, SesionId=Sid, Numero=Num, Asunto=As, Tipo=T, Resultado=Res)
        for I, Sid, Num, As, T, Res in Rows
    ]
    return PaginatedResponse(Items=Items, Total=Total, Limit=Limit, Offset=Offset)
