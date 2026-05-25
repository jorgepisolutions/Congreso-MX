from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from CongresoMx.Models.Base import DEFAULT_TABLE_KWARGS, Base


# La persona fisica. NombreHash permite dedupe entre legislaturas cuando
# la misma persona reaparece (potencialmente con distinto partido o cargo).
class Legislador(Base):
    __tablename__ = "Legisladores"
    __table_args__ = (
        Index("IdxLegisladoresNombreHash", "NombreHash"),
        Index("IdxLegisladoresNombreCompleto", "NombreCompleto"),
        DEFAULT_TABLE_KWARGS,
    )

    Id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    NombreCompleto: Mapped[str] = mapped_column(String(300), nullable=False)
    Nombre: Mapped[str | None] = mapped_column(String(150), nullable=True)
    ApellidoPaterno: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ApellidoMaterno: Mapped[str | None] = mapped_column(String(100), nullable=True)
    Genero: Mapped[str | None] = mapped_column(
        Enum("M", "F", "X", name="LegisladorGeneroEnum"),
        nullable=True,
    )
    FechaNacimiento: Mapped[date | None] = mapped_column(Date, nullable=True)
    FotoUrl: Mapped[str | None] = mapped_column(String(500), nullable=True)
    NombreHash: Mapped[str] = mapped_column(String(64), nullable=False)
    CreatedAt: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
        nullable=False,
    )
    UpdatedAt: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        nullable=False,
    )


# El cargo: persona en una legislatura especifica con partido, distrito,
# y tipo de eleccion. Una persona puede tener varios LegisladorPeriodo
# si repite en multiples legislaturas.
class LegisladorPeriodo(Base):
    __tablename__ = "LegisladorPeriodo"
    __table_args__ = (
        UniqueConstraint(
            "LegisladorId",
            "LegislaturaId",
            "Camara",
            "FechaAlta",
            name="UkLegisladorPeriodoLegisladorLegislatura",
        ),
        Index("IdxLegisladorPeriodoIdExterno", "IdExterno", "Fuente"),
        Index("IdxLegisladorPeriodoLegislaturaCamara", "LegislaturaId", "Camara"),
        DEFAULT_TABLE_KWARGS,
    )

    Id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    LegisladorId: Mapped[int] = mapped_column(
        ForeignKey("Legisladores.Id"), nullable=False
    )
    LegislaturaId: Mapped[int] = mapped_column(
        ForeignKey("Legislaturas.Id"), nullable=False
    )
    Camara: Mapped[str] = mapped_column(
        Enum("Diputados", "Senado", name="LegisladorPeriodoCamaraEnum"),
        nullable=False,
    )
    PartidoId: Mapped[int | None] = mapped_column(
        ForeignKey("Partidos.Id"), nullable=True
    )
    EstadoId: Mapped[int | None] = mapped_column(
        SmallInteger, ForeignKey("Estados.Id"), nullable=True
    )
    Distrito: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    TipoEleccion: Mapped[str] = mapped_column(
        Enum(
            "MayoriaRelativa",
            "RepresentacionProporcional",
            "PrimeraMinoria",
            name="LegisladorPeriodoTipoEleccionEnum",
        ),
        nullable=False,
    )
    Curul: Mapped[str | None] = mapped_column(String(20), nullable=True)
    EsSuplente: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    SuplenteDeId: Mapped[int | None] = mapped_column(
        ForeignKey("LegisladorPeriodo.Id"), nullable=True
    )
    FechaAlta: Mapped[date | None] = mapped_column(Date, nullable=True)
    FechaBaja: Mapped[date | None] = mapped_column(Date, nullable=True)
    MotivoBaja: Mapped[str | None] = mapped_column(String(200), nullable=True)
    IdExterno: Mapped[str | None] = mapped_column(String(50), nullable=True)
    Fuente: Mapped[str | None] = mapped_column(String(50), nullable=True)
