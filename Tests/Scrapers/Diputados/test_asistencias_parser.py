from collections import Counter
from datetime import date
from pathlib import Path

from CongresoMx.Scrapers.Diputados.ParsersAsistencias import ParsearAsistenciasCompletas
from CongresoMx.Services.Asistencias import MapearCodigoAEstado

FIXTURES = Path(__file__).resolve().parents[2] / "Fixtures" / "Diputados"


# Pert=1 (sep-dic 2024) tiene 31 fechas de sesion. Las asistencias del
# diputado 391 deben tener una entrada por sesion.
def test_parsear_asistencias_pert1_tiene_31():
    Html = (FIXTURES / "AsistenciasPorPeriodoPert1.html").read_text(encoding="utf-8")
    Result = ParsearAsistenciasCompletas(Html, 1)
    assert len(Result) == 31


# Pert correctamente seteado en cada AsistenciaCruda.
def test_parsear_asistencias_setea_pert():
    Html = (FIXTURES / "AsistenciasPorPeriodoPert1.html").read_text(encoding="utf-8")
    Result = ParsearAsistenciasCompletas(Html, 1)
    assert all(A.Pert == 1 for A in Result)


# La primera sesion del 1-sep-2024 es doble; debe tener CodigoFinal != None.
def test_parsear_asistencias_detecta_sesion_doble():
    Html = (FIXTURES / "AsistenciasPorPeriodoPert1.html").read_text(encoding="utf-8")
    Result = ParsearAsistenciasCompletas(Html, 1)
    Primera = Result[0]
    assert Primera.Fecha == date(2024, 9, 1)
    assert Primera.CodigoInicial == "A"
    assert Primera.CodigoFinal == "A"


# Diputado 391 en pert=1: 31 sesiones, mayoria "A" + algun "PM".
# Sin inasistencias en esta diputada para el periodo.
def test_distribucion_codigos_dip391_pert1():
    Html = (FIXTURES / "AsistenciasPorPeriodoPert1.html").read_text(encoding="utf-8")
    Result = ParsearAsistenciasCompletas(Html, 1)
    Cnt: Counter[str] = Counter()
    for A in Result:
        Cnt[A.CodigoInicial] += 1
        if A.CodigoFinal:
            Cnt[A.CodigoFinal] += 1
    assert Cnt["A"] >= 30
    assert Cnt.get("I", 0) == 0


# Mapeo codigo -> Estado: validar las equivalencias documentadas.
def test_mapeo_codigos_a_estado():
    assert MapearCodigoAEstado("A") == ("Presente", False)
    assert MapearCodigoAEstado("AC") == ("Presente", False)
    assert MapearCodigoAEstado("AO") == ("ComisionOficial", False)
    assert MapearCodigoAEstado("PM") == ("Licencia", False)
    assert MapearCodigoAEstado("IJ") == ("Justificado", False)
    assert MapearCodigoAEstado("I") == ("Ausente", False)
    assert MapearCodigoAEstado("IV") == ("Ausente", False)
    assert MapearCodigoAEstado("XX") == ("Desconocido", True)
    assert MapearCodigoAEstado("") == ("Desconocido", True)
