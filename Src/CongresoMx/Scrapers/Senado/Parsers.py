import logging
import re
from dataclasses import dataclass

from selectolax.parser import HTMLParser

Logger = logging.getLogger(__name__)


# Datos crudos de un senador desde el listado por_grupo_parlamentario.
# Suficiente para detectar partido, estado, telefono, email, foto y licencia.
@dataclass(frozen=True)
class SenadorListadoCrudo:
    IdExterno: str
    NombreCompleto: str  # sin prefijo "Sen. "
    PartidoSiglas: str | None
    Estado: str
    FotoUrl: str | None
    Telefono: str | None
    Email: str | None
    Direccion: str | None
    EnLicencia: bool


# Datos crudos del detalle individual: tipo de eleccion (la fuente canonica
# para distinguir MR, RP, PM).
@dataclass(frozen=True)
class SenadorDetalleCrudo:
    IdExterno: str
    TipoEleccion: str | None
    EstadoDetalle: str | None


TIPO_ELECCION_KEYWORDS: list[tuple[str, str]] = [
    ("primera minoria", "PrimeraMinoria"),
    ("primera minoría", "PrimeraMinoria"),
    ("representacion proporcional", "RepresentacionProporcional"),
    ("representación proporcional", "RepresentacionProporcional"),
    ("mayoria relativa", "MayoriaRelativa"),
    ("mayoría relativa", "MayoriaRelativa"),
]


# Extrae siglas del nombre de clase 'border1XXX'. Devuelve None para 'SG'
# (Sin Grupo: independiente) o si no matchea.
def _ExtraerPartidoDeClase(ClasesAttr: str) -> str | None:
    Match = re.search(r"border1([A-Z]+)", ClasesAttr or "")
    if not Match:
        return None
    Siglas = Match.group(1).upper()
    if Siglas == "SG":
        return None
    return Siglas


# Quita el prefijo "Sen. " o "Senador " del nombre. Reduce espacios.
def _LimpiarNombre(Texto: str) -> str:
    Limpio = re.sub(r"^\s*Sen(?:ador)?\.?\s+", "", Texto.strip(), flags=re.IGNORECASE)
    return " ".join(Limpio.split())


# Mapea "Senador Electo por el Principio de Mayoria Relativa" a "MayoriaRelativa".
# Devuelve None si no se reconoce el texto.
def _MapearTipoEleccion(Texto: str) -> str | None:
    if not Texto:
        return None
    Lower = Texto.lower()
    for Keyword, Valor in TIPO_ELECCION_KEYWORDS:
        if Keyword in Lower:
            return Valor
    return None


# Parsea el HTML de /66/senadores/por_grupo_parlamentario y devuelve
# un crudo por senador. Validacion defensiva: si <120 senadores, fallar.
def ParsearListadoSenadores(Html: str) -> list[SenadorListadoCrudo]:
    Tree = HTMLParser(Html)
    Resultados: list[SenadorListadoCrudo] = []

    for Perfil in Tree.css("div.perfil-senador"):
        IdExterno = (Perfil.attributes.get("data_id-senador") or "").strip()
        if not IdExterno:
            continue
        ClasesAttr = Perfil.attributes.get("class") or ""
        Partido = _ExtraerPartidoDeClase(ClasesAttr)

        NombreNode = Perfil.css_first("h4.nombre-sen a")
        NombreCompleto = _LimpiarNombre(NombreNode.text(strip=True)) if NombreNode else ""

        FotoNode = Perfil.css_first("img.foto-sen")
        FotoUrl = (FotoNode.attributes.get("src") if FotoNode else None) or None

        EstadoNode = Perfil.css_first("span.estado")
        Estado = EstadoNode.text(strip=True) if EstadoNode else ""

        EnLicencia = Perfil.css_first("span.sen-licencia") is not None

        Telefono: str | None = None
        Email: str | None = None
        Direccion: str | None = None
        for P in Perfil.css("div.content p"):
            Texto = P.text(strip=True)
            if not Texto:
                continue
            EnlaceTel = P.css_first('a[href^="tel:"]')
            EnlaceMail = P.css_first('a[href^="mailto:"]')
            if EnlaceTel is not None:
                Telefono = EnlaceTel.text(strip=True)
            elif EnlaceMail is not None:
                Email = EnlaceMail.text(strip=True)
            else:
                # Primer <p> sin tel/mailto = direccion
                if Direccion is None:
                    Direccion = Texto

        Resultados.append(SenadorListadoCrudo(
            IdExterno=IdExterno,
            NombreCompleto=NombreCompleto,
            PartidoSiglas=Partido,
            Estado=Estado,
            FotoUrl=FotoUrl,
            Telefono=Telefono,
            Email=Email,
            Direccion=Direccion,
            EnLicencia=EnLicencia,
        ))

    if len(Resultados) < 120:
        Logger.warning(
            "Listado Senado devolvio %d perfiles (esperado >=120)",
            len(Resultados),
        )
    return Resultados


# Parsea /66/senador/{Id} y extrae TipoEleccion + Estado canonicos.
# El detalle tiene mucha info; nos quedamos solo con lo no presente en listado.
def ParsearDetalleSenador(Html: str, IdExterno: str) -> SenadorDetalleCrudo:
    Tree = HTMLParser(Html)
    TipoNode = Tree.css_first("h3.tipoEleccion")
    TipoEleccion = _MapearTipoEleccion(TipoNode.text(strip=True)) if TipoNode else None

    EstadoNode = Tree.css_first("h4.nEstadi")
    Estado = EstadoNode.text(strip=True) if EstadoNode else None

    return SenadorDetalleCrudo(
        IdExterno=IdExterno,
        TipoEleccion=TipoEleccion,
        EstadoDetalle=Estado,
    )
