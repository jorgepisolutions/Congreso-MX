import logging
import re
from dataclasses import dataclass
from datetime import date

from selectolax.parser import HTMLParser

from CongresoMx.Utils.Texto import NormalizarParaHash

Logger = logging.getLogger(__name__)

# Color de fondo que marca dia con sesion en el calendario del SITL.
COLOR_DIA_SESION = "#D6E2E2"
BGCOLOR_VARIANTS = (COLOR_DIA_SESION.lower(), COLOR_DIA_SESION.upper())

MESES: dict[str, int] = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}


# Fecha de una sesion detectada en el calendario, con el pert que la origino.
# El pert se usa luego para mapear a PeriodoId via PERT_TO_PERIODO_KEY.
@dataclass(frozen=True)
class SesionCruda:
    Fecha: date
    Pert: int
    EsSesionDoble: bool


# Parsea "Septiembre 2024" a (9, 2024). Devuelve (None, None) si no parsea.
def _ParsearMesAnio(Texto: str) -> tuple[int | None, int | None]:
    Limpio = " ".join(Texto.strip().split())
    Match = re.match(r"^([A-Za-zÀ-ſ]+)\s+(\d{4})$", Limpio)
    if not Match:
        return None, None
    MesNombre = NormalizarParaHash(Match.group(1))
    Anio = int(Match.group(2))
    return MESES.get(MesNombre), Anio


# Una sesion doble en el calendario aparece como "DD<br>A/A" (codigos separados
# por /). Para esta fase la registramos como una sola sesion + flag.
def _ExtraerDiaYDoble(Texto: str) -> tuple[int | None, bool]:
    Match = re.search(r"(\d{1,2})", Texto)
    if Match is None:
        return None, False
    Dia = int(Match.group(1))
    EsDoble = "/" in Texto
    return Dia, EsDoble


# Recorre los calendarios mensuales del HTML y devuelve todas las fechas
# de sesion del periodo. Sin duplicar fechas (dia doble cuenta como una).
def ParsearCalendarioCompleto(Html: str, Pert: int) -> list[SesionCruda]:
    Tree = HTMLParser(Html)
    Resultados: dict[date, bool] = {}

    for Tabla in Tree.css("table.estadistico"):
        TituloNode = Tabla.css_first("span.linkTitulo1")
        if TituloNode is None:
            continue
        TituloTexto = TituloNode.text(strip=True)
        Mes, Anio = _ParsearMesAnio(TituloTexto)
        if Mes is None or Anio is None:
            continue

        for Celda in Tabla.css("td"):
            BgAttr = Celda.attributes.get("bgcolor") or ""
            if BgAttr not in BGCOLOR_VARIANTS:
                continue
            TextoCelda = Celda.text(strip=False)
            Dia, EsDoble = _ExtraerDiaYDoble(TextoCelda)
            if Dia is None:
                continue
            try:
                Fecha = date(Anio, Mes, Dia)
            except ValueError:
                Logger.warning("Fecha invalida: %d-%d-%d", Anio, Mes, Dia)
                continue
            Resultados[Fecha] = Resultados.get(Fecha, False) or EsDoble

    return [
        SesionCruda(Fecha=F, Pert=Pert, EsSesionDoble=D)
        for F, D in sorted(Resultados.items())
    ]
