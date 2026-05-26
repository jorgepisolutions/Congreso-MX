import logging
from datetime import date

from CongresoMx.Scrapers.Base import BaseScraper
from CongresoMx.Scrapers.Senado.ParsersLxv import (
    AsistenciaLxvCruda,
    ParsearAsistenciasSesionLxv,
)

Logger = logging.getLogger(__name__)

SESION_URL_TEMPLATE = "https://www.senado.gob.mx/informacion/asistencias/fecha/{AnioMesDia}/{Numero}"


# Scraper de asistencias por sesion LXV. Devuelve todas las filas inline
# (senador + partido visible + estado-texto) para que el service mapee.
class ScraperSenadoAsistenciasLxv(BaseScraper):
    def __init__(self, Legislatura: str = "LXV") -> None:
        super().__init__()
        if Legislatura != "LXV":
            raise ValueError(
                "ScraperSenadoAsistenciasLxv solo soporta LXV"
            )
        self._Legislatura = Legislatura

    # Descarga la pagina de UNA sesion y extrae las filas de asistencias.
    async def ScrapearSesion(
        self, Fecha: date, Numero: str
    ) -> list[AsistenciaLxvCruda]:
        AnioMesDia = Fecha.strftime("%Y_%m_%d")
        Url = SESION_URL_TEMPLATE.format(AnioMesDia=AnioMesDia, Numero=Numero)
        Html = await self.GetHtml(Url)
        Filas = ParsearAsistenciasSesionLxv(Html)
        Logger.info(
            "Sesion %s/%s: %d filas de asistencia", Fecha, Numero, len(Filas)
        )
        return Filas
