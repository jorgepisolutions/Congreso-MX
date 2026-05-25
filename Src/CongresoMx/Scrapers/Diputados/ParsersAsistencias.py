import logging
from dataclasses import dataclass
from datetime import date

from CongresoMx.Scrapers.Diputados.CalendarioBase import ExtraerCeldasGrises

Logger = logging.getLogger(__name__)


# Asistencia cruda de UN diputado en UNA fecha. Si la sesion del dia es
# doble, CodigoFinal queda con el segundo codigo; si no, queda None.
@dataclass(frozen=True)
class AsistenciaCruda:
    Fecha: date
    Pert: int
    CodigoInicial: str
    CodigoFinal: str | None


# Parsea el HTML del calendario de un diputado y devuelve sus asistencias.
# El parser maneja codigos simples ("A", "I", "IJ") y dobles ("A/A", "I/A").
def ParsearAsistenciasCompletas(Html: str, Pert: int) -> list[AsistenciaCruda]:
    Celdas = ExtraerCeldasGrises(Html)
    Resultados: list[AsistenciaCruda] = []
    for C in Celdas:
        if "/" in C.CodigoRaw:
            Partes = C.CodigoRaw.split("/", maxsplit=1)
            CodigoInicial = Partes[0].strip() or "Desconocido"
            CodigoFinal = Partes[1].strip() if len(Partes) > 1 else None
            if CodigoFinal == "":
                CodigoFinal = None
        else:
            CodigoInicial = C.CodigoRaw.strip()
            CodigoFinal = None
        Resultados.append(AsistenciaCruda(
            Fecha=C.Fecha,
            Pert=Pert,
            CodigoInicial=CodigoInicial,
            CodigoFinal=CodigoFinal,
        ))
    return sorted(Resultados, key=lambda A: A.Fecha)
