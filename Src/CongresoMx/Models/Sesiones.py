from datetime import date, datetime, time

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from CongresoMx.Models.Base import DEFAULT_TABLE_KWARGS, Base


# Sesion del pleno de una camara. Estado refleja si esta en curso,
# concluida, suspendida, etc. Numero puede ser texto ("Extra 3").
class Sesion(Base):
    __tablename__ = "Sesiones"
    __table_args__ = (
        UniqueConstraint(
            "Camara",
            "LegislaturaId",
            "Fecha",
            "Numero",
            name="UkSesionCamaraLegislaturaFechaNumero",
        ),
        Index("IdxSesionFecha", "Fecha"),
        Index("IdxSesionEstadoFecha", "Estado", "Fecha"),
        DEFAULT_TABLE_KWARGS,
    )

    Id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    LegislaturaId: Mapped[int] = mapped_column(
        ForeignKey("Legislaturas.Id"), nullable=False
    )
    PeriodoId: Mapped[int] = mapped_column(ForeignKey("Periodos.Id"), nullable=False)
    Camara: Mapped[str] = mapped_column(
        Enum("Diputados", "Senado", name="SesionCamaraEnum"),
        nullable=False,
    )
    Numero: Mapped[str | None] = mapped_column(String(20), nullable=True)
    Tipo: Mapped[str] = mapped_column(
        Enum(
            "Ordinaria",
            "Extraordinaria",
            "Solemne",
            "Permanente",
            "Comision",
            name="SesionTipoEnum",
        ),
        nullable=False,
    )
    Fecha: Mapped[date] = mapped_column(Date, nullable=False)
    HoraInicio: Mapped[time | None] = mapped_column(Time, nullable=True)
    HoraFin: Mapped[time | None] = mapped_column(Time, nullable=True)
    QuorumInicial: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    QuorumFinal: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    Estado: Mapped[str] = mapped_column(
        Enum(
            "Programada",
            "EnCurso",
            "Concluida",
            "Suspendida",
            "Cancelada",
            name="SesionEstadoEnum",
        ),
        nullable=False,
    )
    UrlGaceta: Mapped[str | None] = mapped_column(String(500), nullable=True)
    UrlActa: Mapped[str | None] = mapped_column(String(500), nullable=True)
    UrlVideo: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ScrapedAt: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
        nullable=False,
    )
