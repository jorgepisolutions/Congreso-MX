from datetime import date
from pathlib import Path

from CongresoMx.Scrapers.Diputados.ParsersSesiones import ParsearCalendarioCompleto

FIXTURES = Path(__file__).resolve().parents[2] / "Fixtures" / "Diputados"


# Pert=1 corresponde al primer periodo ordinario LXVI (sep-dic 2024).
def test_parse_calendario_pert1_devuelve_sesiones():
    Html = (FIXTURES / "AsistenciasPorPeriodoPert1.html").read_text(encoding="utf-8")
    Sesiones = ParsearCalendarioCompleto(Html, 1)
    assert len(Sesiones) > 0
    # Periodo 1 cubre sep 2024 a dic 2024
    Fechas = [S.Fecha for S in Sesiones]
    assert min(Fechas) >= date(2024, 9, 1)
    assert max(Fechas) <= date(2024, 12, 31)


# La primera sesion de LXVI fue la instalacion el 1-sep-2024 (doble).
def test_parse_calendario_pert1_primera_sesion_es_instalacion():
    Html = (FIXTURES / "AsistenciasPorPeriodoPert1.html").read_text(encoding="utf-8")
    Sesiones = ParsearCalendarioCompleto(Html, 1)
    Primera = Sesiones[0]
    assert Primera.Fecha == date(2024, 9, 1)
    assert Primera.EsSesionDoble is True
    assert Primera.Pert == 1


# Cada SesionCruda lleva el pert correcto.
def test_parse_calendario_setea_pert():
    Html = (FIXTURES / "AsistenciasPorPeriodoPert1.html").read_text(encoding="utf-8")
    Sesiones = ParsearCalendarioCompleto(Html, 1)
    assert all(S.Pert == 1 for S in Sesiones)


# Las sesiones se devuelven ordenadas por fecha.
def test_parse_calendario_ordenado_por_fecha():
    Html = (FIXTURES / "AsistenciasPorPeriodoPert1.html").read_text(encoding="utf-8")
    Sesiones = ParsearCalendarioCompleto(Html, 1)
    Fechas = [S.Fecha for S in Sesiones]
    assert Fechas == sorted(Fechas)


# Detectamos sesiones dobles (con "A/A" o codigo separado por /).
def test_parse_calendario_detecta_sesiones_dobles():
    Html = (FIXTURES / "AsistenciasPorPeriodoPert1.html").read_text(encoding="utf-8")
    Sesiones = ParsearCalendarioCompleto(Html, 1)
    Dobles = [S for S in Sesiones if S.EsSesionDoble]
    assert len(Dobles) > 0, "Esperamos al menos una sesion doble en pert=1"


# Sin duplicados por fecha (un dia con dos sesiones cuenta como una sola).
def test_parse_calendario_sin_duplicados_por_fecha():
    Html = (FIXTURES / "AsistenciasPorPeriodoPert1.html").read_text(encoding="utf-8")
    Sesiones = ParsearCalendarioCompleto(Html, 1)
    Fechas = [S.Fecha for S in Sesiones]
    assert len(Fechas) == len(set(Fechas))
