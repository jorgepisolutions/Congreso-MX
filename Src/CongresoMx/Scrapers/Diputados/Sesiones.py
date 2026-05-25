import logging

from CongresoMx.Scrapers.Base import BaseScraper
from CongresoMx.Scrapers.Diputados.ParsersSesiones import (
    ParsearCalendarioCompleto,
    SesionCruda,
)

Logger = logging.getLogger(__name__)

BASE_URL_TEMPLATE = "https://sitl.diputados.gob.mx/{Legislatura}_leg/"
SCRAPER_FUENTE = "SITL"

# Perts conocidos para LXVI con contenido. 2, 7 y 10 estan vacios; los omitimos.
# Cada uno corresponde a un (AnioLegislativo, NumeroPeriodo, Tipo) en el seed.
PERTS_LXVI: list[int] = [1, 3, 4, 5, 6, 8, 9]

# Mapeo pert -> (AnioLegislativo, NumeroPeriodo, Tipo) para resolver
# PeriodoId en el service. Tipo aqui es el de Periodos.Tipo (Ordinario|Extraordinario).
PERT_TO_PERIODO_KEY: dict[int, tuple[int, int, str]] = {
    1: (1, 1, "Ordinario"),
    3: (1, 2, "Ordinario"),
    4: (1, 1, "Extraordinario"),
    5: (1, 2, "Extraordinario"),
    6: (2, 1, "Ordinario"),
    8: (2, 2, "Ordinario"),
    9: (2, 1, "Extraordinario"),
}

# Diputado de muestra: el SITL marca las fechas en gris independientemente
# del diputado, asi que cualquier ID valido sirve.
DIPUTADO_SAMPLE_ID = "391"


# Scraper que extrae las fechas de sesiones de Diputados desde el calendario
# de asistencias_por_pernplxvi.php. Solo descarga + parsea.
class ScraperDiputadosSesiones(BaseScraper):
    def __init__(self, Legislatura: str = "LXVI") -> None:
        super().__init__()
        self._Legislatura = Legislatura
        self._BaseUrl = BASE_URL_TEMPLATE.format(Legislatura=Legislatura)

    # Descarga el calendario del periodo Pert para el diputado muestra.
    # Devuelve las fechas de sesion del periodo.
    async def ScrapearPert(self, Pert: int) -> list[SesionCruda]:
        Url = (
            f"{self._BaseUrl}asistencias_por_pernplxvi.php"
            f"?iddipt={DIPUTADO_SAMPLE_ID}&pert={Pert}"
        )
        Html = await self.GetHtml(Url)
        Sesiones = ParsearCalendarioCompleto(Html, Pert)
        Logger.info("Pert=%d: %d sesiones detectadas", Pert, len(Sesiones))
        return Sesiones

    # Orquesta: descarga cada pert relevante y combina las fechas.
    # Dedupe por fecha (un dia no puede pertenecer a dos perts).
    async def ScrapearCalendarioCompleto(
        self, Perts: list[int] | None = None
    ) -> list[SesionCruda]:
        PertsAUsar = Perts if Perts else PERTS_LXVI
        Todas: dict[tuple[int, ...], SesionCruda] = {}
        for P in PertsAUsar:
            for S in await self.ScrapearPert(P):
                Key = (S.Fecha.toordinal(),)
                if Key in Todas:
                    Logger.warning(
                        "Fecha %s aparece en multiples perts; usando primer pert=%d",
                        S.Fecha, Todas[Key].Pert,
                    )
                    continue
                Todas[Key] = S
        return sorted(Todas.values(), key=lambda S: S.Fecha)
