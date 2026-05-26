import json
import logging
from typing import Any

import redis.asyncio as RedisAsyncIO

from CongresoMx.Config import GetSettings

Logger = logging.getLogger(__name__)

_Client: RedisAsyncIO.Redis | None = None


# Devuelve un cliente Redis async cacheado. La conexion se reusa entre
# llamadas. URL viene del .env (RedisUrl).
async def GetClient() -> RedisAsyncIO.Redis:
    global _Client
    if _Client is None:
        Config = GetSettings()
        _Client = RedisAsyncIO.from_url(
            Config.RedisUrl,
            encoding="utf-8",
            decode_responses=False,
        )
    return _Client


# Cierra el cliente Redis y resetea el singleton.
async def CloseClient() -> None:
    global _Client
    if _Client is not None:
        await _Client.aclose()
        _Client = None


# Publica un payload JSON en el canal especificado. No bloquea; si nadie
# esta suscrito, el mensaje se descarta (semantica fire-and-forget).
async def Publicar(Canal: str, Payload: dict[str, Any]) -> int:
    Client = await GetClient()
    Body = json.dumps(Payload, default=str, ensure_ascii=False).encode("utf-8")
    try:
        Suscriptores = await Client.publish(Canal, Body)
        Logger.info(
            "Publicado en Redis canal=%s suscriptores=%d bytes=%d",
            Canal, Suscriptores, len(Body),
        )
        return Suscriptores
    except Exception as Exc:
        Logger.error("Error publicando a Redis canal=%s: %s", Canal, Exc)
        return 0
