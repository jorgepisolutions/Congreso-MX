import logging

from CongresoMx.Scrapers.Base import BaseScraper
from CongresoMx.Scrapers.Senado.ParsersSesiones import (
    ParsearSesionesSenado,
    SesionSenadoCruda,
)

Logger = logging.getLogger(__name__)

BASE_URL_TEMPLATE = "https://www.senado.gob.mx/{LegNumero}/"
LEG_NUMERO_POR_NOMBRE: dict[str, str] = {"LXVI": "66", "LXV": "65"}
MIN_SESIONES_ESPERADAS = 100


# Scraper para el listado de sesiones plenarias del Senado.
# Una sola URL devuelve toda la historia de la legislatura (~393 KB).
class ScraperSenadoSesiones(BaseScraper):
    def __init__(self, Legislatura: str = "LXVI") -> None:
        super().__init__()
        LegNumero = LEG_NUMERO_POR_NOMBRE.get(Legislatura)
        if LegNumero is None:
            raise ValueError(f"Legislatura {Legislatura!r} no mapeada")
        self._Legislatura = Legislatura
        self._BaseUrl = BASE_URL_TEMPLATE.format(LegNumero=LegNumero)

    # Descarga y parsea el listado completo de sesiones.
    async def ScrapearSesiones(self) -> list[SesionSenadoCruda]:
        Url = f"{self._BaseUrl}sesiones"
        Html = await self.GetHtml(Url)
        Resultados = ParsearSesionesSenado(Html)
        if len(Resultados) < MIN_SESIONES_ESPERADAS:
            raise RuntimeError(
                f"Listado de sesiones Senado devolvio {len(Resultados)} "
                f"(esperado >={MIN_SESIONES_ESPERADAS}); estructura puede haber cambiado"
            )
        Logger.info(
            "Listado de sesiones Senado parseado: %d sesiones en %s",
            len(Resultados), self._Legislatura,
        )
        return Resultados
