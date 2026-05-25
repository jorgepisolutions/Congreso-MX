import logging
import re
from datetime import date

from CongresoMx.Scrapers.Base import BaseScraper
from CongresoMx.Scrapers.Senado.ParsersAsistencias import (
    AsistenciaSenadoCruda,
    ParsearAsistenciasSesionSenado,
)

Logger = logging.getLogger(__name__)

BASE_URL_TEMPLATE = "https://www.senado.gob.mx/{LegNumero}/"
AJAX_PATH = "app/asistencias/functions/viewTableAsist.php"
POR_ANIO_PATH = "asistencias/por_anio/{Legislatura}/{Anio}"
LEG_NUMERO_POR_NOMBRE: dict[str, str] = {"LXVI": "66", "LXV": "65"}

# Patron que el listado por_anio expone: /66/asistencias/{YYYY_MM_DD}/{NumPorAnio}
URL_SESION_PATTERN = re.compile(r"/asistencias/(\d{4})_(\d{2})_(\d{2})/(\d+)")


# Scraper para asistencias del Senado. El AJAX usa numero de sesion
# "por año legislativo" (1..N reseteandose cada anio), distinto del numero
# global del listado /66/sesiones. Por eso primero hay que descubrir las
# parejas (fecha, numero_por_anio) via /66/asistencias/por_anio/LXVI/{Anio}.
class ScraperSenadoAsistencias(BaseScraper):
    def __init__(self, Legislatura: str = "LXVI") -> None:
        super().__init__()
        LegNumero = LEG_NUMERO_POR_NOMBRE.get(Legislatura)
        if LegNumero is None:
            raise ValueError(f"Legislatura {Legislatura!r} no mapeada")
        self._Legislatura = Legislatura
        self._LegNumero = LegNumero
        self._BaseUrl = BASE_URL_TEMPLATE.format(LegNumero=LegNumero)

    # Descarga el listado por año y extrae todas las (Fecha, NumeroPorAnio)
    # con asistencias publicadas. Devuelve lista de tuples.
    async def ScrapearListadoPorAnio(
        self, AnioLegislativo: int
    ) -> list[tuple[date, str]]:
        Path = POR_ANIO_PATH.format(
            Legislatura=self._Legislatura, Anio=AnioLegislativo
        )
        Url = f"{self._BaseUrl}{Path}"
        Html = await self.GetHtml(Url)
        Resultados: list[tuple[date, str]] = []
        Vistos: set[tuple[date, str]] = set()
        for Match in URL_SESION_PATTERN.finditer(Html):
            Anio, Mes, Dia, Num = Match.groups()
            try:
                Fecha = date(int(Anio), int(Mes), int(Dia))
            except ValueError:
                continue
            Key = (Fecha, Num)
            if Key in Vistos:
                continue
            Vistos.add(Key)
            Resultados.append(Key)
        Logger.info(
            "Listado por_anio %s/%d: %d sesiones con asistencias",
            self._Legislatura, AnioLegislativo, len(Resultados),
        )
        return Resultados

    # Descarga las asistencias de UNA sesion del Senado via el endpoint
    # AJAX. NumeroPorAnio es el reset-por-año, NO el numero global.
    async def ScrapearSesion(
        self, Fecha: date, NumeroPorAnio: str
    ) -> list[AsistenciaSenadoCruda]:
        FechaStr = Fecha.strftime("%Y-%m-%d")
        Url = (
            f"{self._BaseUrl}{AJAX_PATH}"
            f"?action=ajax&cell=1&order=DESC&sesion={NumeroPorAnio}&fecha={FechaStr}&q="
        )
        Html = await self.GetHtml(Url)
        return ParsearAsistenciasSesionSenado(Html)
