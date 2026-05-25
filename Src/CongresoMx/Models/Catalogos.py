from datetime import date

from sqlalchemy import (
    Boolean,
    Date,
    Enum,
    ForeignKey,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from CongresoMx.Models.Base import DEFAULT_TABLE_KWARGS, Base


# Legislatura: bloque de 3 años en una camara. Ej. LXV (2021-2024), LXVI (2024-2027).
class Legislatura(Base):
    __tablename__ = "Legislaturas"
    __table_args__ = DEFAULT_TABLE_KWARGS

    Id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    Numero: Mapped[str] = mapped_column(String(10), nullable=False, unique=True)
    NumeroArabigo: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    FechaInicio: Mapped[date] = mapped_column(Date, nullable=False)
    FechaFin: Mapped[date] = mapped_column(Date, nullable=False)


# Periodo legislativo dentro de una legislatura. Cada anio tiene 2 periodos
# ordinarios + extraordinarios eventuales.
class Periodo(Base):
    __tablename__ = "Periodos"
    __table_args__ = (
        UniqueConstraint(
            "LegislaturaId",
            "AnioLegislativo",
            "Numero",
            "Tipo",
            name="UkPeriodosLegislaturaAnioNumeroTipo",
        ),
        DEFAULT_TABLE_KWARGS,
    )

    Id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    LegislaturaId: Mapped[int] = mapped_column(
        ForeignKey("Legislaturas.Id"), nullable=False
    )
    AnioLegislativo: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    Numero: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    Tipo: Mapped[str] = mapped_column(
        Enum("Ordinario", "Extraordinario", "Permanente", name="PeriodoTipoEnum"),
        nullable=False,
    )
    FechaInicio: Mapped[date] = mapped_column(Date, nullable=False)
    FechaFin: Mapped[date] = mapped_column(Date, nullable=False)


# Partido politico con representacion en el Congreso. Activo=False para
# partidos historicos que ya no existen (ej. Nueva Alianza).
class Partido(Base):
    __tablename__ = "Partidos"
    __table_args__ = DEFAULT_TABLE_KWARGS

    Id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    Siglas: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    Nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    ColorHex: Mapped[str | None] = mapped_column(String(7), nullable=True)
    Activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


# Estado mexicano. Id = clave INE 1-32. Clave = abreviatura comun (AGS, CDMX).
class Estado(Base):
    __tablename__ = "Estados"
    __table_args__ = DEFAULT_TABLE_KWARGS

    Id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    Clave: Mapped[str] = mapped_column(String(5), nullable=False, unique=True)
    Nombre: Mapped[str] = mapped_column(String(100), nullable=False)
