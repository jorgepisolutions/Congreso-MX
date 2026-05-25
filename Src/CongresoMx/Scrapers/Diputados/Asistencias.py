import logging
from dataclasses import dataclass

from CongresoMx.Scrapers.Base import BaseScraper
from CongresoMx.Scrapers.Diputados.ParsersAsistencias import (
    AsistenciaCruda,
    ParsearAsistenciasCompletas,
)
from CongresoMx.Scrapers.Diputados.Sesiones import (
    BASE_URL_TEMPLATE,
    PERTS_LXVI,
    SCRAPER_FUENTE,
)

Logger = logging.getLogger(__name__)

# Asistencias agrupadas por diputado: lo que el service consume para
# guardar en batch por diputado (1 commit por diputado).
@dataclass
class AsistenciasDeDiputado:
    IdExterno: str
    Asistencias: list[AsistenciaCruda]


# Scraper de asistencias por diputado. Reusa el endpoint que Fase 4
# usa para sesiones (asistencias_por_pernplxvi.php), pero ahora lee
# los codigos de cada celda en vez de descartarlos.
class ScraperDiputadosAsistencias(BaseScraper):
    def __init__(self, Legislatura: str = "LXVI") -> None:
        super().__init__()
        self._Legislatura = Legislatura
        self._BaseUrl = BASE_URL_TEMPLATE.format(Legislatura=Legislatura)

    # Descarga las asistencias de un diputado en UN pert. Devuelve [] si
    # el periodo esta vacio para ese diputado (esperado en perts futuros).
    async def ScrapearDiputadoPert(
        self, IdExterno: str, Pert: int
    ) -> list[AsistenciaCruda]:
        Url = (
            f"{self._BaseUrl}asistencias_por_pernplxvi.php"
            f"?iddipt={IdExterno}&pert={Pert}"
        )
        Html = await self.GetHtml(Url)
        return ParsearAsistenciasCompletas(Html, Pert)

    # Descarga las asistencias de un diputado en todos los perts conocidos.
    # Concatena los resultados.
    async def ScrapearDiputado(self, IdExterno: str) -> list[AsistenciaCruda]:
        Todas: list[AsistenciaCruda] = []
        for P in PERTS_LXVI:
            Asistencias = await self.ScrapearDiputadoPert(IdExterno, P)
            Todas.extend(Asistencias)
        return Todas
