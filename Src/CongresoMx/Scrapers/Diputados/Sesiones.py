import logging

from CongresoMx.Scrapers.Base import BaseScraper
from CongresoMx.Scrapers.Diputados.ParsersSesiones import (
    ParsearCalendarioCompleto,
    SesionCruda,
)

Logger = logging.getLogger(__name__)

BASE_URL_TEMPLATE = "https://sitl.diputados.gob.mx/{Legislatura}_leg/"
SCRAPER_FUENTE = "SITL"

# Endpoint del calendario por legislatura. El archivo PHP cambia su nombre
# segun la legislatura: asistencias_por_pernp<lower>.php.
URL_CALENDARIO_PATH = "asistencias_por_pernp{LegLower}.php"

# Perts por legislatura. Los perts sin contenido (tipicamente Permanentes,
# que Diputados no agenda en pleno) se omiten.
PERTS_POR_LEGISLATURA: dict[str, list[int]] = {
    "LXVI": [1, 3, 4, 5, 6, 8, 9],
    "LXV":  [1, 3, 4, 5, 7, 8, 9, 11, 12],
}

# Mapeo pert -> (AnioLegislativo, NumeroPeriodo, TipoPeriodo) por legislatura.
# Tipo aqui es el de Periodos.Tipo (Ordinario|Extraordinario). Service usa
# este mapa para resolver PeriodoId al guardar la sesion.
PERT_TO_PERIODO_KEY_POR_LEGISLATURA: dict[str, dict[int, tuple[int, int, str]]] = {
    "LXVI": {
        1: (1, 1, "Ordinario"),
        3: (1, 2, "Ordinario"),
        4: (1, 1, "Extraordinario"),
        5: (1, 2, "Extraordinario"),
        6: (2, 1, "Ordinario"),
        8: (2, 2, "Ordinario"),
        9: (2, 1, "Extraordinario"),
    },
    "LXV": {
        1: (1, 1, "Ordinario"),
        3: (1, 2, "Ordinario"),
        4: (1, 1, "Extraordinario"),
        5: (2, 1, "Ordinario"),
        7: (2, 2, "Ordinario"),
        8: (2, 1, "Extraordinario"),
        9: (3, 1, "Ordinario"),
        11: (3, 2, "Ordinario"),
        12: (3, 1, "Extraordinario"),
    },
}

# Diputado de muestra para descargar el calendario: el SITL marca las fechas
# en gris para todos los diputados por igual, asi que cualquier ID valido sirve.
DIPUTADO_SAMPLE_ID_POR_LEGISLATURA: dict[str, str] = {
    "LXVI": "391",
    "LXV": "1",
}


# Devuelve la lista de perts conocidos con contenido para una legislatura.
# Lanza KeyError si la legislatura no esta soportada.
def PertsDeLegislatura(Legislatura: str) -> list[int]:
    return PERTS_POR_LEGISLATURA[Legislatura]


# Devuelve el mapa pert -> (AnioLegislativo, NumeroPeriodo, TipoPeriodo)
# para la legislatura indicada.
def PertToPeriodoKeyDeLegislatura(
    Legislatura: str,
) -> dict[int, tuple[int, int, str]]:
    return PERT_TO_PERIODO_KEY_POR_LEGISLATURA[Legislatura]


# Scraper que extrae las fechas de sesiones de Diputados desde el calendario
# de asistencias_por_pernp<leg>.php. Solo descarga + parsea.
class ScraperDiputadosSesiones(BaseScraper):
    def __init__(self, Legislatura: str = "LXVI") -> None:
        super().__init__()
        if Legislatura not in PERTS_POR_LEGISLATURA:
            raise ValueError(
                f"Legislatura {Legislatura!r} no soportada (LXV, LXVI)"
            )
        self._Legislatura = Legislatura
        self._BaseUrl = BASE_URL_TEMPLATE.format(Legislatura=Legislatura)
        self._UrlPath = URL_CALENDARIO_PATH.format(LegLower=Legislatura.lower())
        self._DiputadoMuestra = DIPUTADO_SAMPLE_ID_POR_LEGISLATURA[Legislatura]

    # Descarga el calendario del periodo Pert para el diputado muestra.
    # Devuelve las fechas de sesion del periodo.
    async def ScrapearPert(self, Pert: int) -> list[SesionCruda]:
        Url = (
            f"{self._BaseUrl}{self._UrlPath}"
            f"?iddipt={self._DiputadoMuestra}&pert={Pert}"
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
        PertsAUsar = Perts if Perts else PERTS_POR_LEGISLATURA[self._Legislatura]
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
