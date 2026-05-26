import logging
from dataclasses import dataclass
from datetime import date

from CongresoMx.Scrapers.Base import BaseScraper
from CongresoMx.Scrapers.Senado.ParsersLxv import (
    ParsearCalendarioLxv,
    SesionLxvCruda,
)

Logger = logging.getLogger(__name__)

CAL_URL = "https://www.senado.gob.mx/informacion/app/asistencias/functions/calendarioMes.php"

# Rango de la legislatura LXV: 2021-09-01 a 2024-08-31.
RANGO_LXV: tuple[date, date] = (date(2021, 9, 1), date(2024, 8, 31))


# Sesion del Senado LXV, en forma compatible con UpsertSesion (Camara=Senado,
# Numero del calendario, Tipo deducido por fecha, FechaInicio del periodo).
@dataclass(frozen=True)
class SesionSenadoLxvCruda:
    Fecha: date
    Numero: str
    Tipo: str  # "Ordinaria" | "Extraordinaria" | "Permanente"
    UrlGaceta: str | None = None
    UrlActa: str | None = None
    UrlVideo: str | None = None


# Genera lista de (anio, mes) tuples entre dos fechas inclusive.
def _IterMeses(Desde: date, Hasta: date) -> list[tuple[int, int]]:
    Resultado: list[tuple[int, int]] = []
    Anio, Mes = Desde.year, Desde.month
    while (Anio, Mes) <= (Hasta.year, Hasta.month):
        Resultado.append((Anio, Mes))
        Mes += 1
        if Mes > 12:
            Mes = 1
            Anio += 1
    return Resultado


# Heuristica de tipo de sesion por fecha: para LXV usamos el mismo modelo que
# Diputados — entre 1-sep y 15-dic, y 1-feb y 30-abr son Ordinarias; el resto
# son Extraordinarias o Comision Permanente. Resolver Periodo definitivo lo
# hace el Service comparando con la tabla Periodos.
def _DeducirTipoPorFecha(Fecha: date) -> str:
    Mes, Dia = Fecha.month, Fecha.day
    EsOrdSep = (Mes, Dia) >= (9, 1) and (Mes, Dia) <= (12, 15)
    EsOrdFeb = (Mes, Dia) >= (2, 1) and (Mes, Dia) <= (4, 30)
    if EsOrdSep or EsOrdFeb:
        return "Ordinaria"
    # Diciembre 16 - enero 31: Comision Permanente.
    if (Mes == 12 and Dia >= 16) or Mes == 1:
        return "Permanente"
    # Mayo - agosto: Permanente o Extraordinaria. Marcamos como Permanente
    # por defecto y dejamos que el service lo resuelva via Periodos.Tipo.
    if 5 <= Mes <= 8:
        return "Permanente"
    return "Ordinaria"


# Scraper del calendario LXV. Itera mes a mes y agrupa todas las sesiones.
class ScraperSenadoSesionesLxv(BaseScraper):
    def __init__(self, Legislatura: str = "LXV") -> None:
        super().__init__()
        if Legislatura != "LXV":
            raise ValueError(
                "ScraperSenadoSesionesLxv solo soporta LXV"
            )
        self._Legislatura = Legislatura

    # Descarga el calendario de un mes via AJAX. Devuelve las sesiones del mes.
    async def ScrapearMes(self, Anio: int, Mes: int) -> list[SesionLxvCruda]:
        Url = f"{CAL_URL}?action=ajax&anio={Anio}&mes={Mes}"
        Html = await self.GetHtml(Url)
        Sesiones = ParsearCalendarioLxv(Html)
        Logger.info(
            "Calendario %04d-%02d: %d sesiones", Anio, Mes, len(Sesiones)
        )
        return Sesiones

    # Orquesta: itera Sep 2021 → Aug 2024 y combina todas las sesiones.
    async def ScrapearSesiones(self) -> list[SesionSenadoLxvCruda]:
        Desde, Hasta = RANGO_LXV
        Combinadas: list[SesionSenadoLxvCruda] = []
        for Anio, Mes in _IterMeses(Desde, Hasta):
            Crudas = await self.ScrapearMes(Anio, Mes)
            for SC in Crudas:
                Combinadas.append(SesionSenadoLxvCruda(
                    Fecha=SC.Fecha,
                    Numero=SC.Numero,
                    Tipo=_DeducirTipoPorFecha(SC.Fecha),
                ))
        return sorted(Combinadas, key=lambda S: (S.Fecha, int(S.Numero)))
