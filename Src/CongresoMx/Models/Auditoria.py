from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, Enum, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from CongresoMx.Models.Base import DEFAULT_TABLE_KWARGS, Base


# Registro de cada corrida de scraper. Util para diagnosticar regresiones
# y para reintentos. Parametros guarda kwargs/filtros como JSON.
class ScrapingRun(Base):
    __tablename__ = "ScrapingRuns"
    __table_args__ = (
        Index("IdxScrapingRunsStatusStarted", "Status", "StartedAt"),
        Index("IdxScrapingRunsFuenteTipo", "Fuente", "Tipo"),
        DEFAULT_TABLE_KWARGS,
    )

    Id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    Fuente: Mapped[str] = mapped_column(String(50), nullable=False)
    Tipo: Mapped[str] = mapped_column(String(50), nullable=False)
    Parametros: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    StartedAt: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    FinishedAt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    Status: Mapped[str] = mapped_column(
        Enum("Running", "Success", "Partial", "Failed", name="ScrapingRunStatusEnum"),
        nullable=False,
    )
    RegistrosNuevos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    RegistrosActualizados: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    Errores: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ErrorDetalle: Mapped[str | None] = mapped_column(Text, nullable=True)
