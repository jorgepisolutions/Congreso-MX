import logging
from dataclasses import dataclass

from CongresoMx.Scrapers.Base import BaseScraper
from CongresoMx.Scrapers.Diputados.ParsersAsistencias import (
    AsistenciaCruda,
    ParsearAsistenciasCompletas,
)
from CongresoMx.Scrapers.Diputados.Sesiones import (
    BASE_URL_TEMPLATE,
    DIPUTADO_SAMPLE_ID_POR_LEGISLATURA,
    PERTS_POR_LEGISLATURA,
    SCRAPER_FUENTE,
    URL_CALENDARIO_PATH,
)

Logger = logging.getLogger(__name__)

# Asistencias agrupadas por diputado: lo que el service consume para
# guardar en batch por diputado (1 commit por diputado).
@dataclass
class AsistenciasDeDiputado:
    IdExterno: str
    Asistencias: list[AsistenciaCruda]


# Scraper de asistencias por diputado. Reusa el endpoint que Fase 4
# usa para sesiones (asistencias_por_pernp<leg>.php), pero ahora lee
# los codigos de cada celda en vez de descartarlos.
class ScraperDiputadosAsistencias(BaseScraper):
    def __init__(self, Legislatura: str = "LXVI") -> None:
        super().__init__()
        if Legislatura not in PERTS_POR_LEGISLATURA:
            raise ValueError(
                f"Legislatura {Legislatura!r} no soportada (LXV, LXVI)"
            )
        self._Legislatura = Legislatura
        self._BaseUrl = BASE_URL_TEMPLATE.format(Legislatura=Legislatura)
        self._UrlPath = URL_CALENDARIO_PATH.format(LegLower=Legislatura.lower())

    # Descarga las asistencias de un diputado en UN pert. Devuelve [] si
    # el periodo esta vacio para ese diputado (esperado en perts futuros).
    async def ScrapearDiputadoPert(
        self, IdExterno: str, Pert: int
    ) -> list[AsistenciaCruda]:
        Url = (
            f"{self._BaseUrl}{self._UrlPath}"
            f"?iddipt={IdExterno}&pert={Pert}"
        )
        Html = await self.GetHtml(Url)
        return ParsearAsistenciasCompletas(Html, Pert)

    # Descarga las asistencias de un diputado en todos los perts conocidos
    # de su legislatura. Concatena los resultados.
    async def ScrapearDiputado(self, IdExterno: str) -> list[AsistenciaCruda]:
        Todas: list[AsistenciaCruda] = []
        for P in PERTS_POR_LEGISLATURA[self._Legislatura]:
            Asistencias = await self.ScrapearDiputadoPert(IdExterno, P)
            Todas.extend(Asistencias)
        return Todas
