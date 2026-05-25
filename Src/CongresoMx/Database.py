from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from CongresoMx.Config import GetSettings

_Engine: AsyncEngine | None = None
_SessionMaker: async_sessionmaker[AsyncSession] | None = None


# Crea (o devuelve cacheado) el AsyncEngine global apuntando a DatabaseUrl.
# pool_pre_ping=True descarta conexiones muertas antes de usarlas.
def GetEngine() -> AsyncEngine:
    global _Engine
    if _Engine is None:
        Config = GetSettings()
        _Engine = create_async_engine(
            Config.DatabaseUrl,
            echo=Config.DatabaseEcho,
            pool_pre_ping=True,
        )
    return _Engine


# Crea (o devuelve cacheado) el sessionmaker global.
# expire_on_commit=False permite usar objetos despues del commit.
def GetSessionMaker() -> async_sessionmaker[AsyncSession]:
    global _SessionMaker
    if _SessionMaker is None:
        _SessionMaker = async_sessionmaker(
            GetEngine(),
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _SessionMaker


# Cierra el engine y resetea los singletons. Util en tests y en shutdown.
async def DisposeEngine() -> None:
    global _Engine, _SessionMaker
    if _Engine is not None:
        await _Engine.dispose()
    _Engine = None
    _SessionMaker = None
