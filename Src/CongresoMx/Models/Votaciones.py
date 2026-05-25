from datetime import time

from sqlalchemy import (
    BigInteger,
    Enum,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from CongresoMx.Models.Base import DEFAULT_TABLE_KWARGS, Base


# Votacion nominal/economica de un asunto en una sesion. Resultado nullable
# porque puede no estar definido aun (en curso, retirado antes de votar).
class Votacion(Base):
    __tablename__ = "Votaciones"
    __table_args__ = (
        UniqueConstraint("SesionId", "Numero", name="UkVotacionSesionNumero"),
        DEFAULT_TABLE_KWARGS,
    )

    Id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    SesionId: Mapped[int] = mapped_column(ForeignKey("Sesiones.Id"), nullable=False)
    Numero: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    Asunto: Mapped[str] = mapped_column(Text, nullable=False)
    Tipo: Mapped[str] = mapped_column(
        Enum("Nominal", "Economica", "Cedula", name="VotacionTipoEnum"),
        nullable=False,
    )
    Resultado: Mapped[str | None] = mapped_column(
        Enum("Aprobado", "Rechazado", "Empate", "Retirado", name="VotacionResultadoEnum"),
        nullable=True,
    )
    TotalFavor: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    TotalContra: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    TotalAbstencion: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    TotalAusente: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    Hora: Mapped[time | None] = mapped_column(Time, nullable=True)
    UrlDetalle: Mapped[str | None] = mapped_column(String(500), nullable=True)


# Voto individual de un legislador en una votacion. "Quorum" se usa
# cuando el legislador registro presencia pero no emitio voto.
class Voto(Base):
    __tablename__ = "Votos"
    __table_args__ = (
        UniqueConstraint(
            "VotacionId", "LegisladorPeriodoId", name="UkVotoVotacionLegislador"
        ),
        DEFAULT_TABLE_KWARGS,
    )

    Id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    VotacionId: Mapped[int] = mapped_column(ForeignKey("Votaciones.Id"), nullable=False)
    LegisladorPeriodoId: Mapped[int] = mapped_column(
        ForeignKey("LegisladorPeriodo.Id"), nullable=False
    )
    Sentido: Mapped[str] = mapped_column(
        Enum(
            "Favor",
            "Contra",
            "Abstencion",
            "Ausente",
            "Quorum",
            name="VotoSentidoEnum",
        ),
        nullable=False,
    )
