import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from CongresoMx.Api.Deps import Limiter_
from CongresoMx.Api.Routers import Asistencias, Legisladores, Sesiones, Stats, Votaciones
from CongresoMx.Api.Ws import Router as WsRouter
from CongresoMx.Config import GetSettings

Logger = logging.getLogger(__name__)


# Handler 429 cuando se excede el rate limit. Devuelve JSON con detalle
# en lugar del HTML por defecto.
def _RateLimitHandler(_Request: Request, Exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": f"Rate limit excedido: {Exc.detail}"},
    )


# App de FastAPI. Wirea routers REST + WebSocket + middleware de rate limit.
# Auth via X-Api-Key se aplica como dependencia a nivel de cada Router.
App = FastAPI(
    title="CongresoMx",
    description="API REST + WebSocket del Congreso de la Union de Mexico.",
    version="0.1.0",
)

App.state.limiter = Limiter_
App.add_exception_handler(RateLimitExceeded, _RateLimitHandler)
App.add_middleware(SlowAPIMiddleware)

# CORS abierto para que cualquier cliente externo pueda consumir.
# En produccion deberias restringir allow_origins.
App.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

App.include_router(Legisladores.Router)
App.include_router(Sesiones.Router)
App.include_router(Asistencias.Router)
App.include_router(Stats.Router)
App.include_router(Votaciones.Router)
App.include_router(WsRouter)


# Healthcheck publico (sin auth). Usado por docker compose healthcheck.
@App.get("/health", tags=["Meta"])
async def Health() -> dict[str, str]:
    Config = GetSettings()
    return {
        "Status": "ok",
        "Env": Config.EnvName,
        "Version": "0.1.0",
    }


# Endpoint raiz publico.
@App.get("/", tags=["Meta"])
async def Root() -> dict[str, str]:
    return {
        "Message": "CongresoMx API. Ver /docs.",
        "Auth": "Endpoints (excepto /health y /docs) requieren header X-Api-Key.",
    }
