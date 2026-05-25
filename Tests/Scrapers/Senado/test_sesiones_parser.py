from collections import Counter
from datetime import date
from pathlib import Path

from CongresoMx.Scrapers.Senado.ParsersSesiones import ParsearSesionesSenado

FIXTURES = Path(__file__).resolve().parents[2] / "Fixtures" / "Senado"


# Listado de sesiones plenarias de LXVI tiene 182 sesiones publicadas.
def test_parsear_sesiones_total():
    Html = (FIXTURES / "SesionesPlenarias.html").read_text(encoding="utf-8")
    Result = ParsearSesionesSenado(Html)
    assert len(Result) == 182


# Distribucion por Tipo coincide con conteo manual sobre el HTML.
def test_distribucion_tipos():
    Html = (FIXTURES / "SesionesPlenarias.html").read_text(encoding="utf-8")
    Result = ParsearSesionesSenado(Html)
    Cnt = Counter(S.Tipo for S in Result)
    assert Cnt["Ordinaria"] == 138
    assert Cnt["Permanente"] == 21
    assert Cnt["Solemne"] == 15
    assert Cnt["Extraordinaria"] == 8


# La primera sesion (No. 1) fue 29-ago-2024 (junta previa de la LXVI).
def test_primera_sesion():
    Html = (FIXTURES / "SesionesPlenarias.html").read_text(encoding="utf-8")
    Result = ParsearSesionesSenado(Html)
    Sesion1 = next((S for S in Result if S.Numero == "1"), None)
    assert Sesion1 is not None
    assert Sesion1.Fecha == date(2024, 8, 29)


# Numeros son strings unicos (no duplicados).
def test_numeros_unicos():
    Html = (FIXTURES / "SesionesPlenarias.html").read_text(encoding="utf-8")
    Result = ParsearSesionesSenado(Html)
    Numeros = [S.Numero for S in Result]
    assert len(Numeros) == len(set(Numeros))


# La mayoria de sesiones tiene URL de Gaceta.
def test_la_mayoria_tiene_gaceta():
    Html = (FIXTURES / "SesionesPlenarias.html").read_text(encoding="utf-8")
    Result = ParsearSesionesSenado(Html)
    ConGaceta = sum(1 for S in Result if S.UrlGaceta)
    assert ConGaceta > len(Result) * 0.8


# Fechas estan dentro del rango esperado para LXVI.
def test_rango_fechas_lxvi():
    Html = (FIXTURES / "SesionesPlenarias.html").read_text(encoding="utf-8")
    Result = ParsearSesionesSenado(Html)
    Fechas = [S.Fecha for S in Result]
    assert min(Fechas) >= date(2024, 8, 1)
    assert max(Fechas) <= date(2027, 8, 31)
