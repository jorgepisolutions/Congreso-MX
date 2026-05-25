import logging
import re
from dataclasses import dataclass
from datetime import date

from selectolax.parser import HTMLParser

from CongresoMx.Utils.Texto import NormalizarParaHash

Logger = logging.getLogger(__name__)

MESES: dict[str, int] = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

# Mapeo del texto de la columna "Sesion" al ENUM Sesion.Tipo.
TIPO_SESION_MAP: dict[str, str] = {
    "ordinaria": "Ordinaria",
    "ordinaria vespertina": "Ordinaria",
    "ordinaria nocturna": "Ordinaria",
    "ordinario": "Ordinaria",
    "junta previa": "Ordinaria",
    "extraordinaria": "Extraordinaria",
    "solemne": "Solemne",
    "comision permanente": "Permanente",
    "comisión permanente": "Permanente",
}


# Datos crudos de una sesion del Senado. Incluye Numero (el Senado lo
# expone, a diferencia de Diputados que queda NULL).
@dataclass(frozen=True)
class SesionSenadoCruda:
    Numero: str
    Fecha: date
    Tipo: str
    UrlGaceta: str | None
    UrlActa: str | None
    UrlVideo: str | None


# Parsea "Miércoles 06 de mayo de 2026" en date(2026, 5, 6). Tolerante a
# que el dia de la semana este presente o ausente. Devuelve None si no parsea.
def _ParsearFechaEspanolLarga(Texto: str) -> date | None:
    Limpio = " ".join(Texto.strip().split())
    Match = re.search(
        r"(\d{1,2})\s+de\s+([A-Za-zÀ-ſ]+)\s+de\s+(\d{4})", Limpio
    )
    if not Match:
        return None
    Dia = int(Match.group(1))
    MesNombre = NormalizarParaHash(Match.group(2))
    Anio = int(Match.group(3))
    Mes = MESES.get(MesNombre)
    if Mes is None:
        return None
    try:
        return date(Anio, Mes, Dia)
    except ValueError:
        return None


# Mapea el texto de "Sesion" al enum. Devuelve "Ordinaria" como default
# si el texto no esta en TIPO_SESION_MAP (logueamos warning afuera).
def _MapearTipoSesion(Texto: str) -> tuple[str, bool]:
    Key = NormalizarParaHash(Texto)
    Tipo = TIPO_SESION_MAP.get(Key)
    if Tipo is None:
        return "Ordinaria", True
    return Tipo, False


# Encuentra el primer <a> de los documentos cuyo texto contenga keyword.
# Devuelve el href o None. Insensitive a mayusculas.
def _BuscarUrlPorTexto(Fila, Keyword: str) -> str | None:
    KeyLow = Keyword.lower()
    for A in Fila.css("a"):
        Texto = (A.text(strip=True) or "").lower()
        Href = A.attributes.get("href")
        if KeyLow in Texto and Href:
            return Href
    return None


# Parsea la tabla principal de /66/sesiones y devuelve una entrada por
# sesion (sin contar las subfilas internas de documentos).
def ParsearSesionesSenado(Html: str) -> list[SesionSenadoCruda]:
    Tree = HTMLParser(Html)
    Tabla = Tree.css_first("table.table-striped.table-bordered")
    if Tabla is None:
        return []

    Resultados: list[SesionSenadoCruda] = []
    for Fila in Tabla.css("tbody tr"):
        Tds = Fila.css("td")
        # Estructura esperada: <td>No</td><td>Fecha</td><td>Tipo</td><td><table>docs</table></td>
        if len(Tds) < 4:
            continue
        Numero = Tds[0].text(strip=True)
        if not Numero or not Numero[0].isdigit():
            continue
        Fecha = _ParsearFechaEspanolLarga(Tds[1].text(strip=True))
        if Fecha is None:
            continue
        TipoCrudo = Tds[2].text(strip=True)
        Tipo, Desconocido = _MapearTipoSesion(TipoCrudo)
        if Desconocido:
            Logger.warning(
                "Tipo de sesion no mapeado: %r (fecha %s)", TipoCrudo, Fecha
            )

        UrlGaceta = _BuscarUrlPorTexto(Tds[3], "Gaceta")
        UrlActa = _BuscarUrlPorTexto(Tds[3], "Acta") or _BuscarUrlPorTexto(
            Tds[3], "Estenografica"
        )
        UrlVideo = _BuscarUrlPorTexto(Tds[3], "Video") or _BuscarUrlPorTexto(
            Tds[3], "Multimedia"
        )

        Resultados.append(SesionSenadoCruda(
            Numero=Numero,
            Fecha=Fecha,
            Tipo=Tipo,
            UrlGaceta=UrlGaceta,
            UrlActa=UrlActa,
            UrlVideo=UrlVideo,
        ))

    return Resultados
