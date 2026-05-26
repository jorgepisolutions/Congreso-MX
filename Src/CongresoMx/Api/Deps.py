import hashlib
import logging
from datetime import datetime, timezone
from typing import Annotated, AsyncGenerator

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi import Limiter
from slowapi.util import get_remote_address

from CongresoMx.Database import GetSessionMaker
from CongresoMx.Models import ApiKey

Logger = logging.getLogger(__name__)

# Limiter compartido a nivel de aplicacion. Se referencia desde Main.py.
# Default key_func usa la IP del cliente; los routers especificos usan
# la API key como key_func via override.
Limiter_ = Limiter(key_func=get_remote_address)


# Hashea un token con SHA-256 hex. Es lo que se guarda en ApiKeys.KeyHash.
def HashearKey(Token: str) -> str:
    return hashlib.sha256(Token.encode("utf-8")).hexdigest()


# Provee una AsyncSession para el ciclo de vida del request. Hace
# commit/rollback automatico al cerrar segun el resultado del handler.
async def GetSession() -> AsyncGenerator[AsyncSession, None]:
    SessionMaker = GetSessionMaker()
    async with SessionMaker() as Session_:
        yield Session_


# Valida el header X-Api-Key contra la tabla ApiKeys. Actualiza LastUsedAt.
# Devuelve el ApiKey row para que los endpoints puedan usar su RateLimitPerMin
# u otra metadata si la necesitan. Rechaza con 401 si no matchea.
async def RequireApiKey(
    Request_: Request,
    XApiKey: Annotated[str | None, Header(alias="X-Api-Key")] = None,
    Session_: AsyncSession = Depends(GetSession),
) -> ApiKey:
    if not XApiKey:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Header X-Api-Key requerido",
        )
    KeyHash = HashearKey(XApiKey)
    Row = (
        await Session_.execute(
            select(ApiKey).where(ApiKey.KeyHash == KeyHash, ApiKey.Activo.is_(True))
        )
    ).scalar_one_or_none()
    if Row is None:
        Logger.warning(
            "API key invalida desde %s (hash=%s...)",
            Request_.client.host if Request_.client else "?",
            KeyHash[:8],
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key invalida o inactiva",
        )
    # Verifica expiracion si esta seteada
    Ahora = datetime.now(timezone.utc).replace(tzinfo=None)
    if Row.ExpiresAt is not None and Row.ExpiresAt < Ahora:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key expirada",
        )
    # Update LastUsedAt sin commit explicito (la session lo cierra al final)
    await Session_.execute(
        update(ApiKey).where(ApiKey.Id == Row.Id).values(LastUsedAt=Ahora)
    )
    await Session_.commit()
    # Guardamos referencia en request.state para que slowapi use el key como rate limit bucket
    Request_.state.apikey_id = Row.Id
    Request_.state.apikey_nombre = Row.Nombre
    Request_.state.apikey_ratelimit = Row.RateLimitPerMin
    return Row


# Key function para slowapi: usa el Id de la ApiKey si esta autenticada,
# si no usa la IP. Permite rate limiting por key (cada cliente tiene su bucket).
def ApiKeyOrIp(Request_: Request) -> str:
    KeyId = getattr(Request_.state, "apikey_id", None)
    if KeyId is not None:
        return f"apikey:{KeyId}"
    return get_remote_address(Request_)


# Resuelve el limit dinamico segun la metadata de la ApiKey. Si tiene
# RateLimitPerMin custom, usa eso; si no, el default global (60/min).
def LimitParaKey(Request_: Request) -> str:
    Custom = getattr(Request_.state, "apikey_ratelimit", None)
    if Custom and Custom > 0:
        return f"{Custom}/minute"
    return "60/minute"


ApiKeyDep = Annotated[ApiKey, Depends(RequireApiKey)]
SessionDep = Annotated[AsyncSession, Depends(GetSession)]
