from collections import Counter
from pathlib import Path

from CongresoMx.Scrapers.Senado.Parsers import (
    ParsearDetalleSenador,
    ParsearListadoSenadores,
)

FIXTURES = Path(__file__).resolve().parents[2] / "Fixtures" / "Senado"


# La pagina por_grupo_parlamentario tiene exactamente 128 senadores (LXVI).
def test_parsear_listado_devuelve_128():
    Html = (FIXTURES / "SenadoresPorGrupo.html").read_text(encoding="utf-8")
    Result = ParsearListadoSenadores(Html)
    assert len(Result) == 128


# Distribucion por partido coincide con la composicion oficial de LXVI.
def test_listado_distribucion_partidos():
    Html = (FIXTURES / "SenadoresPorGrupo.html").read_text(encoding="utf-8")
    Result = ParsearListadoSenadores(Html)
    Cnt = Counter(D.PartidoSiglas for D in Result)
    assert Cnt["MORENA"] == 67
    assert Cnt["PAN"] == 21
    assert Cnt["PVEM"] == 14
    assert Cnt["PRI"] == 13
    assert Cnt["MC"] == 6
    assert Cnt["PT"] == 6
    assert Cnt.get(None, 0) == 1  # 1 independiente (SG)


# El primer senador (Aguilar Castillo) esta en licencia segun el HTML.
def test_detectar_senador_en_licencia():
    Html = (FIXTURES / "SenadoresPorGrupo.html").read_text(encoding="utf-8")
    Result = ParsearListadoSenadores(Html)
    Aguilar = next((R for R in Result if R.IdExterno == "1579"), None)
    assert Aguilar is not None
    assert Aguilar.EnLicencia is True
    assert "Aguilar Castillo" in Aguilar.NombreCompleto


# El prefijo "Sen." debe ser removido del nombre completo.
def test_nombre_sin_prefijo_sen():
    Html = (FIXTURES / "SenadoresPorGrupo.html").read_text(encoding="utf-8")
    Result = ParsearListadoSenadores(Html)
    for R in Result:
        assert not R.NombreCompleto.lower().startswith("sen")


# Email y telefono se extraen correctamente.
def test_email_y_telefono_se_extraen():
    Html = (FIXTURES / "SenadoresPorGrupo.html").read_text(encoding="utf-8")
    Result = ParsearListadoSenadores(Html)
    Aguilar = next(R for R in Result if R.IdExterno == "1579")
    assert Aguilar.Email and "@senado.gob.mx" in Aguilar.Email
    assert Aguilar.Telefono is not None


# El detalle individual identifica TipoEleccion canonico.
def test_parsear_detalle_tipo_eleccion():
    Html = (FIXTURES / "Senador1579.html").read_text(encoding="utf-8")
    Det = ParsearDetalleSenador(Html, "1579")
    assert Det.TipoEleccion == "MayoriaRelativa"
    assert Det.EstadoDetalle == "Sonora"
