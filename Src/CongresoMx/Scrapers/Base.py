import asyncio
import logging
import time
from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    before_sleep_log,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from CongresoMx.Config import GetSettings
from CongresoMx.Utils.Encoding import DecodeHttpResponse

Logger = logging.getLogger(__name__)

BROWSER_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
}

RETRY_EXCEPTIONS = (
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.RemoteProtocolError,
    httpx.HTTPStatusError,
)


# BaseScraper async para todos los scrapers del proyecto.
# Provee httpx client con UA real, rate limit por host, retry exponencial,
# decode automatico de ISO-8859-1. Subclases solo agregan logica de portal.
class BaseScraper:
    def __init__(self, Verify: bool = True) -> None:
        Config = GetSettings()
        self._UserAgent = Config.UserAgent
        self._Timeout = float(Config.HttpTimeoutSec)
        self._MaxRetries = Config.HttpMaxRetries
        self._RateLimitSec = 1.0 / Config.RateLimitPerHostPerSec
        self._Verify = Verify
        self._LastRequestAt = 0.0
        self._Client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "BaseScraper":
        Headers = {**BROWSER_HEADERS, "User-Agent": self._UserAgent}
        self._Client = httpx.AsyncClient(
            headers=Headers,
            timeout=self._Timeout,
            follow_redirects=True,
            verify=self._Verify,
        )
        return self

    async def __aexit__(self, *Exc: Any) -> None:
        if self._Client is not None:
            await self._Client.aclose()

    # Espera lo necesario para mantener el rate limit (1 req/s default).
    async def _WaitRateLimit(self) -> None:
        Sleep = self._RateLimitSec - (time.monotonic() - self._LastRequestAt)
        if Sleep > 0:
            await asyncio.sleep(Sleep)

    # Una sola descarga sin retry; sirve de unidad para tenacity. Lanza
    # HTTPStatusError en 4xx/5xx para que tenacity decida si reintentar.
    async def _DoGetOnce(self, Url: str) -> httpx.Response:
        assert self._Client is not None, "BaseScraper debe usarse como async with"
        await self._WaitRateLimit()
        Logger.info("GET %s", Url)
        Response = await self._Client.get(Url)
        self._LastRequestAt = time.monotonic()
        if Response.status_code >= 500:
            raise httpx.HTTPStatusError(
                f"Server error {Response.status_code}",
                request=Response.request,
                response=Response,
            )
        return Response

    # Descarga con retry exponencial. Devuelve HTML como str ya decodificado.
    # 4xx no se reintentan (errores del cliente).
    async def GetHtml(self, Url: str) -> str:
        Retrying = AsyncRetrying(
            stop=stop_after_attempt(self._MaxRetries),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            retry=retry_if_exception_type(RETRY_EXCEPTIONS),
            before_sleep=before_sleep_log(Logger, logging.WARNING),
            reraise=True,
        )
        async for Attempt in Retrying:
            with Attempt:
                Response = await self._DoGetOnce(Url)
        Response.raise_for_status()
        Body, _ = DecodeHttpResponse(Response)
        return Body
