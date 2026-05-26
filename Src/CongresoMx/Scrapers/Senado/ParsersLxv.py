import logging
import re
from dataclasses import dataclass
from datetime import date

from selectolax.parser import HTMLParser

Logger = logging.getLogger(__name__)


# Datos crudos de un senador en LXV desde el listado combinado LXIV_LXV.
# Estado y Partido vienen del texto inline "Campeche | morena".
@dataclass(frozen=True)
class SenadorLxvListadoCrudo:
    IdExterno: str
    NombreCompleto: str  # ya en forma "Nombre Apellidos"
    PartidoSiglas: str | None
    Estado: str
    FotoUrl: str | None


# Detalle: TipoEleccion (MayoriaRelativa | PrimeraMinoria | ListaNacional).
@dataclass(frozen=True)
class SenadorLxvDetalleCrudo:
    IdExterno: str
    TipoEleccion: str | None


# Fecha + numero de una sesion publicada en el calendario AJAX.
@dataclass(frozen=True)
class SesionLxvCruda:
    Fecha: date
    Numero: str


# Una fila de la tabla inline de asistencias por sesion: id senador + estado.
# Los nombres de campo replican los de la version LXVI (IdSenadorExterno,
# RegistroCrudo) para que el service GuardarAsistenciasSesionSenado funcione
# sin distincion entre legislaturas.
@dataclass(frozen=True)
class AsistenciaLxvCruda:
    IdSenadorExterno: str
    NombreVisible: str
    PartidoTexto: str | None
    RegistroCrudo: str


PARTIDO_NORMALIZACION: dict[str, str] = {
    "morena": "MORENA",
    "pan": "PAN",
    "pri": "PRI",
    "prd": "PRD",
    "pt": "PT",
    "pvem": "PVEM",
    "mc": "MC",
    "pes": "PES",
    "sg": "SG",
    "ng": "SG",
    "independiente": "SG",
}

TIPO_ELECCION_KEYWORDS: list[tuple[str, str]] = [
    ("primera minoria", "PrimeraMinoria"),
    ("primera minoría", "PrimeraMinoria"),
    ("lista nacional", "ListaNacional"),
    ("representacion proporcional", "ListaNacional"),
    ("representación proporcional", "ListaNacional"),
    ("mayoria relativa", "MayoriaRelativa"),
    ("mayoría relativa", "MayoriaRelativa"),
]

# Mapeo de texto-estado a codigo Asistencia lo hace el Service via
# REGISTRO_SENADO_A_ESTADO (compartido con LXVI Senado).


# Normaliza "Apellidos, Nombres" a "Nombres Apellidos". Si no hay coma,
# devuelve el texto tal cual.
def _FlipNombre(Texto: str) -> str:
    Limpio = " ".join(Texto.strip().split())
    if "," not in Limpio:
        return Limpio
    Partes = Limpio.split(",", maxsplit=1)
    Apellidos = Partes[0].strip()
    Nombres = Partes[1].strip()
    if not Apellidos or not Nombres:
        return Limpio
    return f"{Nombres} {Apellidos}"


# Quita el prefijo "Sen. " o "Senador " del nombre. Reduce espacios.
def _LimpiarPrefijoSen(Texto: str) -> str:
    Limpio = re.sub(r"^\s*Sen(?:ador|adora)?\.?\s+", "", Texto.strip(), flags=re.IGNORECASE)
    return " ".join(Limpio.split())


# Normaliza siglas de partido (case-insensitive + alias). Devuelve None para
# SG / Independiente.
def _NormalizarPartido(Texto: str) -> str | None:
    if not Texto:
        return None
    Clave = Texto.strip().lower()
    Mapeado = PARTIDO_NORMALIZACION.get(Clave, Texto.strip().upper())
    if Mapeado in {"SG", "INDEPENDIENTE", ""}:
        return None
    return Mapeado


# Mapea texto del detalle del senador a uno de los 3 tipos. Devuelve None
# si no se reconoce.
def _MapearTipoEleccion(Texto: str) -> str | None:
    if not Texto:
        return None
    Lower = Texto.lower()
    for Keyword, Valor in TIPO_ELECCION_KEYWORDS:
        if Keyword in Lower:
            return Valor
    return None


# Parsea el listado /informacion/senadores/LXIV_LXV. Cada perfil viene en una
# tabla 2x con: foto, <a href="...LXIV_LXV/{Id}"><b>Apellidos, Nombres</b><br>Estado | partido</a>.
def ParsearListadoLxv(Html: str) -> list[SenadorLxvListadoCrudo]:
    Tree = HTMLParser(Html)
    Resultados: list[SenadorLxvListadoCrudo] = []
    Vistos: set[str] = set()

    for Anchor in Tree.css('a[href^="/informacion/senadores/LXIV_LXV/"]'):
        Href = Anchor.attributes.get("href") or ""
        Match = re.match(r"^/informacion/senadores/LXIV_LXV/(\d+)/?$", Href)
        if not Match:
            continue
        IdExterno = Match.group(1)
        if IdExterno in Vistos:
            continue

        Bold = Anchor.css_first("b")
        if Bold is None:
            continue
        NombreRaw = Bold.text(strip=True)
        NombreCompleto = _FlipNombre(NombreRaw)
        if not NombreCompleto:
            continue

        # El texto despues del <br> tiene "Estado | partido"
        TextoCompleto = Anchor.text(strip=True)
        Resto = TextoCompleto.replace(NombreRaw, "", 1).strip()
        Estado = ""
        Partido: str | None = None
        if "|" in Resto:
            Estado, PartidoRaw = (P.strip() for P in Resto.split("|", maxsplit=1))
            Partido = _NormalizarPartido(PartidoRaw)
        else:
            Estado = Resto

        # Buscar foto en la fila padre (anchor img de la fila)
        FotoUrl: str | None = None
        Padre = Anchor.parent
        for _ in range(3):  # subimos hasta encontrar <tr>
            if Padre is None or Padre.tag == "tr":
                break
            Padre = Padre.parent
        if Padre is not None and Padre.tag == "tr":
            Img = Padre.css_first("img")
            if Img is not None:
                Src = (Img.attributes.get("src") or "").strip()
                if Src.startswith("http"):
                    FotoUrl = Src

        Resultados.append(SenadorLxvListadoCrudo(
            IdExterno=IdExterno,
            NombreCompleto=NombreCompleto,
            PartidoSiglas=Partido,
            Estado=Estado,
            FotoUrl=FotoUrl,
        ))
        Vistos.add(IdExterno)

    return Resultados


# Parsea el detalle de senador LXV. Busca TipoEleccion en el contenido textual.
def ParsearDetalleLxv(Html: str, IdExterno: str) -> SenadorLxvDetalleCrudo:
    Texto = HTMLParser(Html).body.text() if HTMLParser(Html).body else Html
    Tipo = _MapearTipoEleccion(Texto)
    return SenadorLxvDetalleCrudo(IdExterno=IdExterno, TipoEleccion=Tipo)


# Parsea el HTML del calendario AJAX. Cada celda con sesion tiene un
# <a href="/informacion/asistencias/fecha/YYYY_MM_DD/N">.
def ParsearCalendarioLxv(Html: str) -> list[SesionLxvCruda]:
    Tree = HTMLParser(Html)
    Sesiones: list[SesionLxvCruda] = []
    Vistos: set[str] = set()
    for A in Tree.css('a[href^="/informacion/asistencias/fecha/"]'):
        Href = A.attributes.get("href") or ""
        Match = re.match(
            r"^/informacion/asistencias/fecha/(\d{4})_(\d{2})_(\d{2})/(\d+)$",
            Href,
        )
        if not Match:
            continue
        if Href in Vistos:
            continue
        Vistos.add(Href)
        Anio, Mes, Dia, Num = Match.groups()
        try:
            Fecha = date(int(Anio), int(Mes), int(Dia))
        except ValueError:
            Logger.warning("Fecha invalida en calendario: %s", Href)
            continue
        Sesiones.append(SesionLxvCruda(Fecha=Fecha, Numero=Num))
    return Sesiones


# Parsea la tabla inline de asistencias de UNA sesion. Cada fila:
# <tr><td><a href="...LXIV_LXV/{Id}/Asistencias">Sen. Nombre</a></td>
#     <td>PARTIDO</td><td>ESTADO</td></tr>.
def ParsearAsistenciasSesionLxv(Html: str) -> list[AsistenciaLxvCruda]:
    Tree = HTMLParser(Html)
    Filas: list[AsistenciaLxvCruda] = []
    for Tr in Tree.css("tr"):
        Tds = Tr.css("td")
        if len(Tds) < 3:
            continue
        AnchorSen = Tds[0].css_first('a[href*="/informacion/senadores/LXIV_LXV/"]')
        if AnchorSen is None:
            continue
        Href = AnchorSen.attributes.get("href") or ""
        Match = re.search(r"/informacion/senadores/LXIV_LXV/(\d+)/Asistencias", Href)
        if not Match:
            continue
        IdExterno = Match.group(1)
        NombreVisible = _LimpiarPrefijoSen(AnchorSen.text(strip=True))
        PartidoRaw = Tds[1].text(strip=True)
        EstadoTextoRaw = Tds[2].text(strip=True)
        Partido = _NormalizarPartido(PartidoRaw)
        EstadoTexto = " ".join(EstadoTextoRaw.upper().split())
        Filas.append(AsistenciaLxvCruda(
            IdSenadorExterno=IdExterno,
            NombreVisible=NombreVisible,
            PartidoTexto=Partido,
            RegistroCrudo=EstadoTexto,
        ))
    return Filas
