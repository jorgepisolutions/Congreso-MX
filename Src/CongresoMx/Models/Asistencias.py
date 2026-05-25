from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from CongresoMx.Models.Base import DEFAULT_TABLE_KWARGS, Base


# Asistencia de un legislador a un pase de lista de una sesion.
# TipoPaseLista distingue Inicial/Intermedio/Final dentro de la misma sesion.
class Asistencia(Base):
    __tablename__ = "Asistencias"
    __table_args__ = (
        UniqueConstraint(
            "SesionId",
            "LegisladorPeriodoId",
            "TipoPaseLista",
            name="UkAsistenciaSesionLegisladorTipo",
        ),
        Index("IdxAsistenciaSesion", "SesionId"),
        Index("IdxAsistenciaLegislador", "LegisladorPeriodoId"),
        DEFAULT_TABLE_KWARGS,
    )

    Id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    SesionId: Mapped[int] = mapped_column(ForeignKey("Sesiones.Id"), nullable=False)
    LegisladorPeriodoId: Mapped[int] = mapped_column(
        ForeignKey("LegisladorPeriodo.Id"), nullable=False
    )
    Estado: Mapped[str] = mapped_column(
        Enum(
            "Presente",
            "Ausente",
            "Justificado",
            "ComisionOficial",
            "Licencia",
            "Desconocido",
            name="AsistenciaEstadoEnum",
        ),
        nullable=False,
    )
    HoraRegistro: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    TipoPaseLista: Mapped[str | None] = mapped_column(
        Enum(
            "Inicial",
            "Intermedio",
            "Final",
            "VotacionNominal",
            name="AsistenciaTipoPaseListaEnum",
        ),
        nullable=True,
    )
    Fuente: Mapped[str] = mapped_column(String(50), nullable=False)
    ScrapedAt: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
        nullable=False,
    )
