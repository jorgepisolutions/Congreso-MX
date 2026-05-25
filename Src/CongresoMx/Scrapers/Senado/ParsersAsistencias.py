import logging
import re
from dataclasses import dataclass

from selectolax.parser import HTMLParser

Logger = logging.getLogger(__name__)


# Asistencia cruda de un senador en una sesion del Senado.
# IdSenadorExterno = ID interno del Senado (1503..1729 aprox).
# RegistroCrudo = texto literal del Senado (ej. "ASISTENCIA", "AUSENTE",
# "INASISTENCIA JUSTIFICADA", etc.) que el service mapea a enum.
@dataclass(frozen=True)
class AsistenciaSenadoCruda:
    IdSenadorExterno: str
    GrupoParlamentario: str | None
    RegistroCrudo: str


# Parsea el HTML que devuelve el endpoint AJAX de /66/app/asistencias.
# Estructura: <tbody><tr><td>N</td><td><a href="/66/asistencias/{Id}#info">Sen. Nombre</a></td><td>Partido</td><td>Registro</td></tr>
def ParsearAsistenciasSesionSenado(Html: str) -> list[AsistenciaSenadoCruda]:
    Tree = HTMLParser(Html)
    Resultados: list[AsistenciaSenadoCruda] = []

    for Fila in Tree.css("tbody tr"):
        Tds = Fila.css("td")
        if len(Tds) < 4:
            continue
        # Td 1: senador. Extraemos IdExterno del href.
        Link = Tds[1].css_first("a[href]")
        if Link is None:
            continue
        Href = Link.attributes.get("href") or ""
        Match = re.search(r"/asistencias/(\d+)", Href)
        if Match is None:
            continue
        IdExterno = Match.group(1)
        Grupo = Tds[2].text(strip=True) or None
        Registro = Tds[3].text(strip=True)
        Resultados.append(AsistenciaSenadoCruda(
            IdSenadorExterno=IdExterno,
            GrupoParlamentario=Grupo,
            RegistroCrudo=Registro,
        ))
    return Resultados
