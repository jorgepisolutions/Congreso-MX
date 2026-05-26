import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

import httpx

Logger = logging.getLogger(__name__)

URL_DATOS_MINUTO = (
    "https://pleno.senado.gob.mx/webservice/sesion_al_minuto/envivo/datosMinuto.php"
)
HTTP_TIMEOUT = 15.0
# El WAF del Senado bloquea con Accept: application/json, asi que mandamos
# headers de navegador estandar. El endpoint devuelve JSON en el body aunque
# diga Content-Type: text/html.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Referer": "https://www.senado.gob.mx/66/sesion_al_minuto",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
}

# Frases que indican que la sesion ya termino (no esta en curso).
# El portal del Senado las imprime en el campo "punto" cuando cierra sesion.
FRASES_SESION_TERMINADA: tuple[str, ...] = (
    "se levanta la sesion",
    "se levanta la sesión",
    "cita para la siguiente",
    "se da por concluida",
)


# Estado de la sesion del Senado en este instante segun el endpoint live.
@dataclass(frozen=True)
class EstadoSesionSenado:
    HayActiva: bool
    FechaPortal: date | None
    PuntoActual: str
    TramiteActual: str
    DatosRaw: dict[str, Any]


# Normaliza texto para deteccion por substring (sin acentos, lowercase).
def _Normalizar(Texto: str) -> str:
    import unicodedata
    SinAcentos = "".join(
        c for c in unicodedata.normalize("NFD", Texto)
        if unicodedata.category(c) != "Mn"
    )
    return SinAcentos.lower()


# Consulta el endpoint datosMinuto.php y devuelve si hay sesion activa.
# Heuristica: si "punto" contiene "se levanta", "cita para la siguiente",
# "concluida" o equivalente, esta sesion termino. Si la fecha del portal
# es distinta de hoy CDMX, tampoco hay sesion.
async def ConsultarEstadoSenado() -> EstadoSesionSenado:
    import json as _json
    async with httpx.AsyncClient(
        headers=BROWSER_HEADERS, timeout=HTTP_TIMEOUT, follow_redirects=True
    ) as Client:
        Resp = await Client.get(URL_DATOS_MINUTO)
        Resp.raise_for_status()
        # Content-Type a veces dice text/html pero el body es JSON. Parseamos
        # el text directamente con json.loads en vez de Resp.json().
        Body = Resp.text.strip()
        if not Body or not Body.startswith("{"):
            Logger.warning("datosMinuto.php no devolvio JSON: %r", Body[:200])
            return EstadoSesionSenado(
                HayActiva=False, FechaPortal=None, PuntoActual="",
                TramiteActual="", DatosRaw={},
            )
        Data = _json.loads(Body)

    PuntoRaw = (Data.get("punto") or "").strip()
    TramiteRaw = (Data.get("tramite") or "").strip()
    FechaStr = Data.get("fecha")
    FechaPortal: date | None = None
    if FechaStr:
        try:
            FechaPortal = datetime.strptime(FechaStr, "%Y-%m-%d").date()
        except ValueError:
            Logger.warning("Fecha del portal no parseable: %r", FechaStr)

    # Determinar si hay sesion activa
    PuntoNorm = _Normalizar(PuntoRaw)
    HayFraseTerminada = any(F in PuntoNorm for F in FRASES_SESION_TERMINADA)
    HayActiva = (
        FechaPortal is not None
        and PuntoRaw
        and not HayFraseTerminada
    )

    return EstadoSesionSenado(
        HayActiva=HayActiva,
        FechaPortal=FechaPortal,
        PuntoActual=PuntoRaw,
        TramiteActual=TramiteRaw,
        DatosRaw=Data,
    )
