import logging
from dataclasses import dataclass
from datetime import date

from CongresoMx.Scrapers.Diputados.CalendarioBase import ExtraerCeldasGrises

Logger = logging.getLogger(__name__)


# Fecha de una sesion detectada en el calendario, con el pert que la origino.
# El pert se usa luego para mapear a PeriodoId via PERT_TO_PERIODO_KEY.
@dataclass(frozen=True)
class SesionCruda:
    Fecha: date
    Pert: int
    EsSesionDoble: bool


# Recorre los calendarios mensuales del HTML y devuelve las fechas de sesion
# del periodo. Una sesion doble (codigo "A/A") cuenta como una sola fecha
# con EsSesionDoble=True.
def ParsearCalendarioCompleto(Html: str, Pert: int) -> list[SesionCruda]:
    Celdas = ExtraerCeldasGrises(Html)
    PorFecha: dict[date, bool] = {}
    for C in Celdas:
        EsDoble = "/" in C.CodigoRaw
        PorFecha[C.Fecha] = PorFecha.get(C.Fecha, False) or EsDoble
    return [
        SesionCruda(Fecha=F, Pert=Pert, EsSesionDoble=D)
        for F, D in sorted(PorFecha.items())
    ]
