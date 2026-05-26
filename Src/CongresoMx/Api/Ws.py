import asyncio
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from CongresoMx.Api.Deps import HashearKey
from CongresoMx.Database import GetSessionMaker
from CongresoMx.Models import ApiKey as ApiKeyModel
from CongresoMx.Services.RedisPubSub import GetClient
from sqlalchemy import select

Logger = logging.getLogger(__name__)

Router = APIRouter(prefix="/Ws", tags=["WebSocket"])

PATRON_CANAL = "Asistencias:*"


# Valida API key pasada como query param ?apikey=X. WebSocket no expone
# headers tan facilmente desde browser, asi que aceptamos query param.
async def _ValidarApiKeyWs(ApiKeyToken: str | None) -> bool:
    if not ApiKeyToken:
        return False
    KeyHash = HashearKey(ApiKeyToken)
    SessionMaker = GetSessionMaker()
    async with SessionMaker() as Session_:
        Row = (
            await Session_.execute(
                select(ApiKeyModel).where(
                    ApiKeyModel.KeyHash == KeyHash,
                    ApiKeyModel.Activo.is_(True),
                )
            )
        ).scalar_one_or_none()
    return Row is not None


# WebSocket que se suscribe a Redis pattern Asistencias:* y reenvia
# cada mensaje al cliente. Si el cliente cierra, cancelamos la suscripcion.
@Router.websocket("/Asistencias")
async def AsistenciasLive(
    Ws: WebSocket,
    apikey: str = Query(..., description="API key de autenticacion"),
) -> None:
    if not await _ValidarApiKeyWs(apikey):
        await Ws.close(code=status.WS_1008_POLICY_VIOLATION, reason="API key invalida")
        return

    await Ws.accept()
    Logger.info("WebSocket Asistencias conectado: %s", Ws.client)

    Client = await GetClient()
    Pubsub = Client.pubsub()
    await Pubsub.psubscribe(PATRON_CANAL)

    try:
        # Mensaje de bienvenida para confirmar conexion al cliente.
        await Ws.send_json({"Tipo": "Conectado", "Patron": PATRON_CANAL})

        async for Msg in Pubsub.listen():
            if Msg is None:
                continue
            MsgType = Msg.get("type")
            if MsgType not in ("pmessage", "message"):
                continue
            Channel = Msg.get("channel")
            Data = Msg.get("data")
            if isinstance(Channel, bytes):
                Channel = Channel.decode("utf-8", errors="replace")
            if isinstance(Data, bytes):
                Data = Data.decode("utf-8", errors="replace")
            await Ws.send_json({"Canal": Channel, "Mensaje": Data})

    except WebSocketDisconnect:
        Logger.info("WebSocket desconectado: %s", Ws.client)
    except asyncio.CancelledError:
        pass
    except Exception as Exc:
        Logger.error("WebSocket error: %s", Exc, exc_info=True)
    finally:
        try:
            await Pubsub.punsubscribe(PATRON_CANAL)
            await Pubsub.aclose()
        except Exception:
            pass
