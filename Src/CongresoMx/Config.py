from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ProjectRoot = Path(__file__).resolve().parents[2]
EnvFile = ProjectRoot / ".env"


# Carga la configuracion del proyecto desde variables de entorno y .env.
# Entrada principal: instancia Settings() o usar GetSettings() cacheado.
# Lee de Path raiz del repo / .env. Campos en PascalCase por convencion.
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=EnvFile,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    EnvName: str = Field(default="Local")
    LogLevel: str = Field(default="INFO")
    Timezone: str = Field(default="America/Mexico_City")

    DatabaseUrl: str
    DatabaseEcho: bool = Field(default=False)

    RedisUrl: str = Field(default="redis://127.0.0.1:6379/0")

    ApiKey: str = Field(default="ChangeMeApiKey")
    ApiHost: str = Field(default="0.0.0.0")
    ApiPort: int = Field(default=8000)

    UserAgent: str = Field(
        default=(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )
    )
    RateLimitPerHostPerSec: int = Field(default=1)
    HttpTimeoutSec: int = Field(default=30)
    HttpMaxRetries: int = Field(default=3)


# Devuelve la instancia unica de Settings.
# Pydantic-settings ya cachea pero exponer un accessor evita imports circulares.
def GetSettings() -> Settings:
    return Settings()  # type: ignore[call-arg]
