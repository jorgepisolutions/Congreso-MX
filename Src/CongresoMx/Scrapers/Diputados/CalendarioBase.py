import logging
import re
from dataclasses import dataclass
from datetime import date

from selectolax.parser import HTMLParser

from CongresoMx.Utils.Texto import NormalizarParaHash

Logger = logging.getLogger(__name__)

# Color de fondo que el SITL usa para marcar dias con sesion en el calendario.
COLOR_DIA_SESION = "#D6E2E2"
BGCOLOR_VARIANTS: tuple[str, ...] = (COLOR_DIA_SESION.lower(), COLOR_DIA_SESION.upper())

# Patron para extraer dia + codigo desde el texto de la celda. Tras strip
# de tags, el texto queda como "24A" o "1A/A" o "14A/I".
CELDA_PATTERN = re.compile(r"^\s*(\d{1,2})\s*([A-Za-z/]+)\s*$")

MESES: dict[str, int] = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}


# Representa una celda gris del calendario: fecha + codigo crudo.
# El codigo puede ser unico ("A") o doble ("A/A", "I/A", etc.) para
# dias con dos sesiones.
@dataclass(frozen=True)
class CeldaCalendario:
    Fecha: date
    CodigoRaw: str


# Convierte "Septiembre 2024" en (9, 2024). Devuelve (None, None) si no parsea.
def ParsearMesAnio(Texto: str) -> tuple[int | None, int | None]:
    Limpio = " ".join(Texto.strip().split())
    Match = re.match(r"^([A-Za-zÀ-ſ]+)\s+(\d{4})$", Limpio)
    if not Match:
        return None, None
    MesNombre = NormalizarParaHash(Match.group(1))
    Anio = int(Match.group(2))
    return MESES.get(MesNombre), Anio


# Recorre todos los <table class="estadistico"> del HTML, identifica celdas
# con bgcolor gris y extrae (fecha, codigo). Skipea celdas vacias o mal formadas.
def ExtraerCeldasGrises(Html: str) -> list[CeldaCalendario]:
    Tree = HTMLParser(Html)
    Celdas: list[CeldaCalendario] = []

    for Tabla in Tree.css("table.estadistico"):
        TituloNode = Tabla.css_first("span.linkTitulo1")
        if TituloNode is None:
            continue
        Mes, Anio = ParsearMesAnio(TituloNode.text(strip=True))
        if Mes is None or Anio is None:
            continue

        for Celda in Tabla.css("td"):
            BgAttr = Celda.attributes.get("bgcolor") or ""
            if BgAttr not in BGCOLOR_VARIANTS:
                continue
            Texto = Celda.text(strip=True)
            Match = CELDA_PATTERN.match(Texto)
            if Match is None:
                continue
            Dia = int(Match.group(1))
            CodigoRaw = Match.group(2)
            try:
                Fecha = date(Anio, Mes, Dia)
            except ValueError:
                Logger.warning("Fecha invalida: %d-%d-%d", Anio, Mes, Dia)
                continue
            Celdas.append(CeldaCalendario(Fecha=Fecha, CodigoRaw=CodigoRaw))

    return Celdas
