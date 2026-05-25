import asyncio
import logging

from sqlalchemy.dialects.mysql import insert as MysqlInsert
from sqlalchemy.ext.asyncio import AsyncSession

from CongresoMx.Database import DisposeEngine, GetSessionMaker
from CongresoMx.Models import Estado, Partido

Logger = logging.getLogger(__name__)

# Estados de Mexico con clave numerica del INE (1-32) y abreviatura comun.
# Lista canonica usada por el INE para distritos y resultados electorales.
ESTADOS: list[tuple[int, str, str]] = [
    (1, "AGS", "Aguascalientes"),
    (2, "BC", "Baja California"),
    (3, "BCS", "Baja California Sur"),
    (4, "CAM", "Campeche"),
    (5, "COA", "Coahuila"),
    (6, "COL", "Colima"),
    (7, "CHIS", "Chiapas"),
    (8, "CHIH", "Chihuahua"),
    (9, "CDMX", "Ciudad de Mexico"),
    (10, "DGO", "Durango"),
    (11, "GTO", "Guanajuato"),
    (12, "GRO", "Guerrero"),
    (13, "HGO", "Hidalgo"),
    (14, "JAL", "Jalisco"),
    (15, "MEX", "Mexico"),
    (16, "MICH", "Michoacan"),
    (17, "MOR", "Morelos"),
    (18, "NAY", "Nayarit"),
    (19, "NL", "Nuevo Leon"),
    (20, "OAX", "Oaxaca"),
    (21, "PUE", "Puebla"),
    (22, "QRO", "Queretaro"),
    (23, "QROO", "Quintana Roo"),
    (24, "SLP", "San Luis Potosi"),
    (25, "SIN", "Sinaloa"),
    (26, "SON", "Sonora"),
    (27, "TAB", "Tabasco"),
    (28, "TAMS", "Tamaulipas"),
    (29, "TLAX", "Tlaxcala"),
    (30, "VER", "Veracruz"),
    (31, "YUC", "Yucatan"),
    (32, "ZAC", "Zacatecas"),
]

# Partidos politicos con representacion vigente en LXVI. Colores aproximados
# segun branding oficial. Si aparece otro, se agrega y se reusa por Siglas.
PARTIDOS: list[tuple[str, str, str]] = [
    ("PAN", "Partido Accion Nacional", "#0061C7"),
    ("PRI", "Partido Revolucionario Institucional", "#C00000"),
    ("PRD", "Partido de la Revolucion Democratica", "#FFCC00"),
    ("MORENA", "Movimiento Regeneracion Nacional", "#8B1A1A"),
    ("PT", "Partido del Trabajo", "#C8102E"),
    ("PVEM", "Partido Verde Ecologista de Mexico", "#00B14F"),
    ("MC", "Movimiento Ciudadano", "#FF8800"),
]


# Inserta o actualiza los 32 estados via ON DUPLICATE KEY UPDATE.
# Idempotente: re-correr no duplica, solo refresca nombres si cambiaron.
async def UpsertEstados(Session: AsyncSession) -> int:
    for IdRow, Clave, Nombre in ESTADOS:
        Stmt = MysqlInsert(Estado).values(Id=IdRow, Clave=Clave, Nombre=Nombre)
        Stmt = Stmt.on_duplicate_key_update(
            Clave=Stmt.inserted.Clave,
            Nombre=Stmt.inserted.Nombre,
        )
        await Session.execute(Stmt)
    return len(ESTADOS)


# Inserta o actualiza los partidos de la lista PARTIDOS. Activo=True por default.
# Si un partido futuro deja de ser activo, se actualiza manualmente.
async def UpsertPartidos(Session: AsyncSession) -> int:
    for Siglas, Nombre, ColorHex in PARTIDOS:
        Stmt = MysqlInsert(Partido).values(
            Siglas=Siglas,
            Nombre=Nombre,
            ColorHex=ColorHex,
            Activo=True,
        )
        Stmt = Stmt.on_duplicate_key_update(
            Nombre=Stmt.inserted.Nombre,
            ColorHex=Stmt.inserted.ColorHex,
        )
        await Session.execute(Stmt)
    return len(PARTIDOS)


# Orquesta el seed: abre sesion async, ejecuta los upserts, commit, dispose.
async def Run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    Logger.info("Iniciando seed de catalogos...")
    SessionMaker = GetSessionMaker()
    try:
        async with SessionMaker() as Session:
            NumEstados = await UpsertEstados(Session)
            NumPartidos = await UpsertPartidos(Session)
            await Session.commit()
        Logger.info("Seed completo: %d Estados, %d Partidos", NumEstados, NumPartidos)
    finally:
        await DisposeEngine()


if __name__ == "__main__":
    asyncio.run(Run())
