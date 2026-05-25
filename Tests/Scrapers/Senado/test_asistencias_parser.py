from collections import Counter
from pathlib import Path

from CongresoMx.Scrapers.Senado.ParsersAsistencias import (
    ParsearAsistenciasSesionSenado,
)
from CongresoMx.Services.Asistencias import MapearRegistroSenadoAEstado

FIXTURES = Path(__file__).resolve().parents[2] / "Fixtures" / "Senado"


# El fixture (sesion 25 del 22-abr-2026) tiene los 128 senadores.
def test_parsear_asistencias_128_senadores():
    Html = (FIXTURES / "AsistenciasSesion-2026_04_22-25.html").read_text(encoding="utf-8")
    R = ParsearAsistenciasSesionSenado(Html)
    assert len(R) == 128


# El primer registro debe ser un senador con IdExterno valido.
def test_primer_senador_tiene_id_y_registro():
    Html = (FIXTURES / "AsistenciasSesion-2026_04_22-25.html").read_text(encoding="utf-8")
    R = ParsearAsistenciasSesionSenado(Html)
    Primero = R[0]
    assert Primero.IdSenadorExterno.isdigit()
    assert Primero.RegistroCrudo  # no vacio
    assert Primero.GrupoParlamentario  # no vacio


# Distribucion por partido coincide con la composicion oficial.
def test_distribucion_grupos():
    Html = (FIXTURES / "AsistenciasSesion-2026_04_22-25.html").read_text(encoding="utf-8")
    R = ParsearAsistenciasSesionSenado(Html)
    Cnt = Counter(A.GrupoParlamentario for A in R)
    assert Cnt["MORENA"] == 67
    assert Cnt["PAN"] == 21


# Codigos del Senado se mapean correctamente a Asistencia.Estado.
def test_mapeo_codigos_senado_a_estado():
    assert MapearRegistroSenadoAEstado("ASISTENCIA") == ("Presente", False)
    assert MapearRegistroSenadoAEstado("AUSENTE") == ("Ausente", False)
    assert MapearRegistroSenadoAEstado("INASISTENCIA JUSTIFICADA") == ("Justificado", False)
    assert MapearRegistroSenadoAEstado("COMISION OFICIAL") == ("ComisionOficial", False)
    assert MapearRegistroSenadoAEstado("COMISIÓN OFICIAL") == ("ComisionOficial", False)
    assert MapearRegistroSenadoAEstado("LICENCIA") == ("Licencia", False)
    assert MapearRegistroSenadoAEstado("XYZ") == ("Desconocido", True)
