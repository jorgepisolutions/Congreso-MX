from collections import Counter
from datetime import date
from pathlib import Path

from CongresoMx.Scrapers.Diputados.Parsers import (
    ParsearCurricula,
    ParsearListadoDiputados,
)
from CongresoMx.Utils.Texto import (
    NombreHashSha256,
    NormalizarParaHash,
    ParseFechaEspanol,
    PartirNombreHispano,
)

FIXTURES = Path(__file__).resolve().parents[2] / "Fixtures" / "Diputados"


# Lee el listado completo (~500 filas) y verifica cantidades agregadas.
def test_parsear_listado_devuelve_500_diputados():
    Html = (FIXTURES / "ListadoLxvi.html").read_text(encoding="utf-8")
    Result = ParsearListadoDiputados(Html)
    assert len(Result) == 500


# Verifica que la distribucion de tipos de eleccion match LXVI (300 MR + 200 RP).
def test_listado_distribucion_tipo_eleccion():
    Html = (FIXTURES / "ListadoLxvi.html").read_text(encoding="utf-8")
    Result = ParsearListadoDiputados(Html)
    Cnt = Counter(D.TipoEleccion for D in Result)
    assert Cnt["MayoriaRelativa"] == 300
    assert Cnt["RepresentacionProporcional"] == 200


# Verifica que los 7 partidos relevantes aparezcan + 1 sin partido (independiente).
def test_listado_distribucion_por_partido():
    Html = (FIXTURES / "ListadoLxvi.html").read_text(encoding="utf-8")
    Result = ParsearListadoDiputados(Html)
    Cnt = Counter(D.PartidoSiglas for D in Result)
    Esperados = {"MORENA", "PAN", "PVEM", "PT", "PRI", "MC"}
    assert Esperados <= set(Cnt.keys())
    SinPartido = Cnt.get(None, 0)
    assert SinPartido >= 1, "Esperamos al menos un independiente en LXVI"


# Primer diputado tiene los campos esperados.
def test_listado_primer_diputado_completo():
    Html = (FIXTURES / "ListadoLxvi.html").read_text(encoding="utf-8")
    Result = ParsearListadoDiputados(Html)
    First = Result[0]
    assert First.IdExterno == "391"
    assert First.PartidoSiglas == "MORENA"
    assert First.Estado == "Campeche"
    assert First.TipoEleccion == "RepresentacionProporcional"
    assert First.Circunscripcion == 3
    assert First.Distrito is None
    assert "Abreu" in First.NombreCompletoListado


# Parsea la curricula de muestra y valida campos esperados.
def test_parsear_curricula_completa():
    Html = (FIXTURES / "Curricula391.html").read_text(encoding="utf-8")
    C = ParsearCurricula(Html, "391")
    assert C.IdExterno == "391"
    assert "Abreu" in C.NombreCompleto
    assert C.TipoEleccion == "RepresentacionProporcional"
    assert C.Circunscripcion == 3
    assert C.Curul == "H-265"
    assert C.Telefono == "61625"
    assert C.Email == "rocio.abreu@diputados.gob.mx"
    assert C.FechaNacimiento == date(1974, 5, 29)
    assert C.FotoUrl is not None
    assert "Rodríguez" in (C.SuplenteNombre or "")
    assert C.PartidoSiglasLogo == "MORENA"


# El prefijo "Dip." debe ser removido del nombre completo.
def test_parsear_curricula_remueve_prefijo_dip():
    Html = (FIXTURES / "Curricula391.html").read_text(encoding="utf-8")
    C = ParsearCurricula(Html, "391")
    assert not C.NombreCompleto.lower().startswith("dip")


# Fechas en formato espanol del SITL.
def test_parse_fecha_espanol_formato_sitl():
    assert ParseFechaEspanol("29-mayo - 1974") == date(1974, 5, 29)
    assert ParseFechaEspanol("1-enero-2000") == date(2000, 1, 1)
    assert ParseFechaEspanol("15 de febrero de 1980") is None  # no soportado
    assert ParseFechaEspanol("") is None
    assert ParseFechaEspanol("no es una fecha") is None


# Hash es determinista y normaliza acentos + espacios + case.
def test_nombre_hash_determinista_y_normalizado():
    HashA = NombreHashSha256("Rocío Adriana Abreu Artiñano")
    HashB = NombreHashSha256("ROCIO ADRIANA ABREU ARTINANO")
    HashC = NombreHashSha256("rocio adriana abreu artinano")
    HashD = NombreHashSha256("Rocio  Adriana  Abreu  Artinano")
    assert HashA == HashB == HashC == HashD
    assert len(HashA) == 64


def test_partir_nombre_hispano_3_partes():
    Nombre, ApP, ApM = PartirNombreHispano("Abreu Artiñano Rocío Adriana")
    assert ApP == "Abreu"
    assert ApM == "Artiñano"
    assert Nombre == "Rocío Adriana"


def test_partir_nombre_hispano_2_palabras():
    Nombre, ApP, ApM = PartirNombreHispano("Pérez Juan")
    assert ApP == "Pérez"
    assert Nombre == "Juan"
    assert ApM is None


def test_normalizar_para_hash_quita_acentos():
    assert NormalizarParaHash("Ciudad de México") == "ciudad de mexico"
    assert NormalizarParaHash("Querétaro") == "queretaro"
    assert NormalizarParaHash("  multiple   espacios  ") == "multiple espacios"
