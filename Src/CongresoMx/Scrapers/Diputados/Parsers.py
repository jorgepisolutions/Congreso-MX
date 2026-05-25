import logging
import re
from dataclasses import dataclass
from datetime import date

from selectolax.parser import HTMLParser, Node

from CongresoMx.Utils.Texto import ParseFechaEspanol

Logger = logging.getLogger(__name__)


# Datos crudos de un diputado tal como aparecen en listado_diputados_gpnp.php.
# Es el feed primario: nos da la lista completa con partido por bloque.
@dataclass(frozen=True)
class LegisladorListadoCrudo:
    IdExterno: str
    NumeroLista: int
    NombreCompletoListado: str
    PartidoSiglas: str | None
    Estado: str
    TipoEleccion: str
    Distrito: int | None
    Circunscripcion: int | None


# Datos crudos del detalle (curricula.php?dipt=X). Es el feed secundario:
# enriquece con foto, contacto, fecha nacimiento, suplente.
@dataclass(frozen=True)
class CurriculaCruda:
    IdExterno: str
    NombreCompleto: str
    TipoEleccion: str | None
    Distrito: int | None
    Circunscripcion: int | None
    Curul: str | None
    Telefono: str | None
    Email: str | None
    FechaNacimiento: date | None
    FotoUrl: str | None
    SuplenteNombre: str | None
    PartidoSiglasLogo: str | None


# Keywords ordenadas por especificidad (mas larga gana). Mapean substring
# del path del logo a las siglas canonicas. Se aplican en orden.
PARTIDO_LOGO_KEYWORDS: list[tuple[str, str]] = [
    ("morena", "MORENA"),
    ("movimiento_ciudadano", "MC"),
    ("accion_nacional", "PAN"),
    ("revolucionario_institucional", "PRI"),
    ("revolucion_democratica", "PRD"),
    ("verde_ecologista", "PVEM"),
    ("ecologista", "PVEM"),
    ("logvrd", "PVEM"),
    ("verde", "PVEM"),
    ("/pan", "PAN"),
    ("/pri", "PRI"),
    ("/prd", "PRD"),
    ("/pt", "PT"),
    ("/mc", "MC"),
    ("logopan", "PAN"),
    ("logopri", "PRI"),
    ("logoprd", "PRD"),
    ("logopt", "PT"),
    ("logomc", "MC"),
]

# Archivos a ignorar cuando aparecen en separadores: assets decorativos
# que no representan un partido.
LOGO_NO_PARTIDO_TOKENS: tuple[str, ...] = (
    "logo_lxvi", "lxvi.webp", "background", "ig_gdap", "favicon",
)

TIPO_ELECCION_MAP: dict[str, str] = {
    "mayoria relativa": "MayoriaRelativa",
    "representacion proporcional": "RepresentacionProporcional",
    "primera minoria": "PrimeraMinoria",
}


# Reconoce el partido a partir del src del logo. Aplica keywords en orden;
# la mas especifica gana. Devuelve None si el src es un asset no-partido
# o el partido no esta en el mapeo (caller deberia loggear).
def _ExtraerSiglasDeLogo(SrcAttr: str) -> str | None:
    if not SrcAttr:
        return None
    Lower = SrcAttr.lower()
    if any(Token in Lower for Token in LOGO_NO_PARTIDO_TOKENS):
        return None
    for Keyword, Siglas in PARTIDO_LOGO_KEYWORDS:
        if Keyword in Lower:
            return Siglas
    return None


# Convierte el texto del td 3 del listado (ej. "Dtto. 5", "Circ. 3") a tipo
# de eleccion + numero de distrito o circunscripcion.
def _ClasificarDistritoCircunscripcion(
    Texto: str,
) -> tuple[str, int | None, int | None]:
    Lower = Texto.lower().strip()
    Match = re.search(r"(\d+)", Texto)
    Numero = int(Match.group(1)) if Match else None
    if "circ" in Lower:
        return "RepresentacionProporcional", None, Numero
    return "MayoriaRelativa", Numero, None


# Normaliza string para matching de tipo eleccion: lowercase, sin acentos.
def _NormalizarParaMatch(Texto: str) -> str:
    import unicodedata
    SinAcentos = "".join(
        Char for Char in unicodedata.normalize("NFD", Texto)
        if unicodedata.category(Char) != "Mn"
    )
    return " ".join(SinAcentos.lower().split())


# Parsea el HTML completo del listado y devuelve un crudo por diputado.
# El partido se trackea con un puntero (PartidoActual) que cambia cada
# vez que aparece un logo nuevo en una fila separadora.
def ParsearListadoDiputados(Html: str) -> list[LegisladorListadoCrudo]:
    Tree = HTMLParser(Html)
    Resultados: list[LegisladorListadoCrudo] = []
    PartidoActual: str | None = None
    NumeroSecuencial = 0

    for Fila in Tree.css("tr"):
        # Caso 1: fila separadora con colspan=3 y un <img> de logo de partido.
        # Estructura: <tr><td colspan=3>...<img src="..."></td></tr>
        TdSpan = Fila.css_first("td[colspan]")
        if TdSpan is not None and TdSpan.css_first("a[href^=\"curricula.php\"]") is None:
            Img = TdSpan.css_first("img")
            if Img is not None:
                Src = Img.attributes.get("src") or ""
                Siglas = _ExtraerSiglasDeLogo(Src)
                if Siglas is not None:
                    PartidoActual = Siglas
                else:
                    LowerSrc = Src.lower()
                    if not any(Token in LowerSrc for Token in LOGO_NO_PARTIDO_TOKENS):
                        Logger.warning("Logo no mapeado: src=%s", Src)
                        PartidoActual = None
            continue

        # Caso 2: fila de diputado: tres <td> con link curricula en el primero
        Tds = Fila.css("td")
        if len(Tds) != 3:
            continue
        Link = Tds[0].css_first('a[href^="curricula.php?dipt="]')
        if Link is None:
            continue

        Href = Link.attributes.get("href") or ""
        Match = re.search(r"dipt=(\d+)", Href)
        if Match is None:
            continue
        IdExterno = Match.group(1)
        NumeroSecuencial += 1
        TextoLink = Link.text(strip=True)
        # Quita prefijo "{Numero} " del texto
        NombreSinNumero = re.sub(r"^\d+\s+", "", TextoLink).strip()
        Estado = Tds[1].text(strip=True)
        TextoDistrito = Tds[2].text(strip=True)
        Tipo, Distrito, Circunscripcion = _ClasificarDistritoCircunscripcion(TextoDistrito)

        Resultados.append(LegisladorListadoCrudo(
            IdExterno=IdExterno,
            NumeroLista=NumeroSecuencial,
            NombreCompletoListado=NombreSinNumero,
            PartidoSiglas=PartidoActual,
            Estado=Estado,
            TipoEleccion=Tipo,
            Distrito=Distrito,
            Circunscripcion=Circunscripcion,
        ))

    return Resultados


# Extrae el primer <b> dentro de un <p>. Devuelve None si no existe.
def _TextoBoldDePagina(Node_: Node) -> str | None:
    Bold = Node_.css_first("b")
    if Bold is None:
        return None
    Texto = Bold.text(strip=True)
    return Texto or None


# Inspecciona un <p> y lo clasifica segun su contenido. Es posicional por
# clase de icono o por texto literal del label antes del <b>.
def _ParsearParrafoContacto(
    P: Node,
    Resultado: dict[str, str | None],
) -> None:
    if "correo" in (P.attributes.get("class") or ""):
        Resultado["Email"] = _TextoBoldDePagina(P)
        return
    Icono = P.css_first("i")
    Clase = (Icono.attributes.get("class") or "") if Icono is not None else ""
    TextoCompleto = P.text(strip=False)
    LowerTexto = _NormalizarParaMatch(TextoCompleto)

    if "phone-volume" in Clase:
        Resultado["Telefono"] = _TextoBoldDePagina(P)
    elif "calendar-days" in Clase:
        Bold = _TextoBoldDePagina(P)
        Resultado["FechaNacimientoRaw"] = Bold
    elif "user-group" in Clase or "suplente" in LowerTexto:
        Resultado["SuplenteNombre"] = _TextoBoldDePagina(P)
    elif "circunscripc" in LowerTexto:
        Bold = _TextoBoldDePagina(P)
        if Bold is not None:
            Match = re.search(r"(\d+)", Bold)
            if Match:
                Resultado["Circunscripcion"] = Match.group(1)
    elif "distrito" in LowerTexto:
        Bold = _TextoBoldDePagina(P)
        if Bold is not None:
            Match = re.search(r"(\d+)", Bold)
            if Match:
                Resultado["Distrito"] = Match.group(1)
    elif "curul" in LowerTexto:
        Resultado["Curul"] = _TextoBoldDePagina(P)


# Parsea el HTML de curricula.php?dipt={Id} y devuelve los campos extraibles.
# IdExterno se recibe explicito porque el HTML no siempre lo expone limpio.
def ParsearCurricula(Html: str, IdExterno: str) -> CurriculaCruda:
    Tree = HTMLParser(Html)

    NombreNode = Tree.css_first("h1.header-name")
    NombreCompleto = ""
    if NombreNode is not None:
        Bruto = NombreNode.text(strip=True)
        NombreCompleto = re.sub(r"^Dip\.\s*", "", Bruto, flags=re.IGNORECASE).strip()

    TipoNode = Tree.css_first("h4.header-job b")
    TipoEleccion: str | None = None
    if TipoNode is not None:
        TipoTexto = _NormalizarParaMatch(TipoNode.text(strip=True))
        TipoEleccion = TIPO_ELECCION_MAP.get(TipoTexto)

    FotoNode = Tree.css_first("img.header-image")
    FotoUrl: str | None = None
    if FotoNode is not None:
        SrcAttr = (FotoNode.attributes.get("src") or "").strip()
        if SrcAttr:
            FotoUrl = SrcAttr

    Acumulado: dict[str, str | None] = {
        "Curul": None,
        "Telefono": None,
        "Email": None,
        "FechaNacimientoRaw": None,
        "SuplenteNombre": None,
        "Distrito": None,
        "Circunscripcion": None,
    }
    Contacto = Tree.css_first("div.header-contact")
    Parrafos = Contacto.css("p") if Contacto is not None else Tree.css("p")
    for P in Parrafos:
        _ParsearParrafoContacto(P, Acumulado)

    FechaNacimiento = ParseFechaEspanol(Acumulado.get("FechaNacimientoRaw") or "")

    LogoPartidoNode = Tree.css_first("div.partidosbolitas img")
    PartidoSiglasLogo: str | None = None
    if LogoPartidoNode is not None:
        PartidoSiglasLogo = _ExtraerSiglasDeLogo(LogoPartidoNode.attributes.get("src") or "")

    DistritoNum = int(Acumulado["Distrito"]) if Acumulado.get("Distrito") else None
    CircuNum = int(Acumulado["Circunscripcion"]) if Acumulado.get("Circunscripcion") else None

    return CurriculaCruda(
        IdExterno=IdExterno,
        NombreCompleto=NombreCompleto,
        TipoEleccion=TipoEleccion,
        Distrito=DistritoNum,
        Circunscripcion=CircuNum,
        Curul=Acumulado.get("Curul"),
        Telefono=Acumulado.get("Telefono"),
        Email=Acumulado.get("Email"),
        FechaNacimiento=FechaNacimiento,
        FotoUrl=FotoUrl,
        SuplenteNombre=Acumulado.get("SuplenteNombre"),
        PartidoSiglasLogo=PartidoSiglasLogo,
    )
