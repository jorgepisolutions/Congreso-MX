from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from CongresoMx.Models.Base import DEFAULT_TABLE_KWARGS, Base


# API key para autenticar consumidores de la API. KeyHash es SHA-256 del
# token (nunca guardamos el token en plano). RateLimitPerMin es opcional;
# si NULL usa el default del middleware (60/min).
class ApiKey(Base):
    __tablename__ = "ApiKeys"
    __table_args__ = DEFAULT_TABLE_KWARGS

    Id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    KeyHash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    Nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    Activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    RateLimitPerMin: Mapped[int | None] = mapped_column(Integer, nullable=True)
    CreatedAt: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )
    LastUsedAt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ExpiresAt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
