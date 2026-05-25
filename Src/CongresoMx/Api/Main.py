import logging

from fastapi import FastAPI

from CongresoMx.Config import GetSettings

Logger = logging.getLogger(__name__)


# App de FastAPI. Endpoints minimos para smoke tests en esta fase.
# Routers reales se agregaran bajo CongresoMx.Api.Routers.
App = FastAPI(
    title="CongresoMx",
    description="ETL del Congreso de la Union de Mexico.",
    version="0.1.0",
)


# Healthcheck: confirma que el proceso esta vivo y la config carga.
# Lo usan docker compose healthcheck y monitoreo externo.
@App.get("/health")
async def Health() -> dict[str, str]:
    Config = GetSettings()
    return {
        "Status": "ok",
        "Env": Config.EnvName,
        "Version": "0.1.0",
    }


# Endpoint raiz: mensaje simple para verificar conectividad sin tocar /docs.
@App.get("/")
async def Root() -> dict[str, str]:
    return {"Message": "CongresoMx API. Ver /docs para la API interactiva."}
