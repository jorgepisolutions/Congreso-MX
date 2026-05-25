import asyncio
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from ReconBase import (
    OUTPUT_ROOT,
    PrintConsoleSummary,
    Recon,
    ReconClient,
    ReconResult,
    SetupLogging,
    WriteSummary,
)

LEGISLATURA = "LXVI"
BASE_URL = f"http://sitl.diputados.gob.mx/{LEGISLATURA}_leg/"
PORTAL = "Diputados"
OUTPUT_DIR = OUTPUT_ROOT / PORTAL
TIMEZONE_MX = ZoneInfo("America/Mexico_City")
DAYS_TO_PROBE = 14
HTML_MIN_BYTES_SESSION = 5000


# Extrae el primer ID de diputado encontrado en un listado HTML guardado.
# Busca el patron curricula.php?dipt=NNN. Devuelve None si no aparece.
def ExtractFirstDiputadoId(HtmlPath: Path) -> str | None:
    if not HtmlPath.exists():
        return None
    Html = HtmlPath.read_text(encoding="utf-8")
    Match = re.search(r"curricula\.php\?dipt=(\d+)", Html)
    return Match.group(1) if Match else None


# Itera dias hacia atras desde hoy hasta encontrar una fecha cuya pagina
# de asistencias tenga HTML real (>5KB). Borra los archivos de prueba que
# fueron muy chicos. Devuelve (Fecha, ReconResult) o (None, None).
async def FindRecentValidSession(
    Client: ReconClient,
) -> tuple[str | None, ReconResult | None]:
    Today = datetime.now(TIMEZONE_MX).date()
    for OffsetDays in range(0, DAYS_TO_PROBE):
        Fecha = Today - timedelta(days=OffsetDays)
        FechaIso = Fecha.strftime("%Y-%m-%d")
        Url = f"{BASE_URL}asistencias_sesion.php?fecha={FechaIso}"
        OutPath = OUTPUT_DIR / f"AsistenciasSesion-{Fecha.strftime('%Y%m%d')}.html"
        Result = await Recon(Client, Url, OutPath)
        if Result.Status == 200 and Result.Bytes > HTML_MIN_BYTES_SESSION:
            return FechaIso, Result
        # Pagina vacia o 404: borramos el archivo y seguimos
        if Result.SavedPath and Result.SavedPath.exists():
            Result.SavedPath.unlink()
    return None, None


# Orquesta el recon de Diputados: listados primero (para sacar Id muestra),
# luego curricula/asistencias de ese Id, votaciones, y busqueda de sesion.
async def Main() -> None:
    SetupLogging()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    Results: list[ReconResult] = []

    async with ReconClient() as Client:
        # Listados (no requieren parametros)
        Results.append(await Recon(
            Client,
            f"{BASE_URL}listado_diputados_gpnp.php",
            OUTPUT_DIR / f"ListadoGpnp{LEGISLATURA.title()}.html",
        ))
        Results.append(await Recon(
            Client,
            f"{BASE_URL}listado_diputados_edomexp.php",
            OUTPUT_DIR / f"ListadoEdomexp{LEGISLATURA.title()}.html",
        ))

        # Sample ID extraido del listado por grupo parlamentario
        IdSample = ExtractFirstDiputadoId(
            OUTPUT_DIR / f"ListadoGpnp{LEGISLATURA.title()}.html"
        )
        if IdSample:
            Results.append(await Recon(
                Client,
                f"{BASE_URL}curricula.php?dipt={IdSample}",
                OUTPUT_DIR / f"CurriculaSample{LEGISLATURA.title()}.html",
            ))
            # Rutas reales descubiertas inspeccionando curricula.php (las de
            # PROJECT.md como asistencias_diputado_OL.php devolvian 404).
            Results.append(await Recon(
                Client,
                f"{BASE_URL}asistencias_diputados_xperiodonp{LEGISLATURA.lower()}.php?dipt={IdSample}",
                OUTPUT_DIR / "AsistenciasDiputadoSample.html",
            ))
            Results.append(await Recon(
                Client,
                f"{BASE_URL}votaciones_diputados_xperiodonp{LEGISLATURA.lower()}.php?dipt={IdSample}",
                OUTPUT_DIR / "VotacionesDiputadoSample.html",
            ))
            Results.append(await Recon(
                Client,
                f"{BASE_URL}iniciativas_diputados_xperiodonp{LEGISLATURA.lower()}.php?dipt={IdSample}",
                OUTPUT_DIR / "IniciativasDiputadoSample.html",
            ))
        else:
            print("WARN: no se encontro IdExterno en el listado; saltando paginas por diputado")

        # Asistencias de sesion: buscar fecha real con HTML no vacio
        FechaValida, ResultadoSesion = await FindRecentValidSession(Client)
        if ResultadoSesion:
            Results.append(ResultadoSesion)
            print(f"INFO: sesion valida encontrada en fecha {FechaValida}")
        else:
            print(f"WARN: ninguna fecha en los ultimos {DAYS_TO_PROBE} dias devolvio HTML > {HTML_MIN_BYTES_SESSION}B")

    WriteSummary(Results, OUTPUT_DIR, PORTAL)
    PrintConsoleSummary(Results, PORTAL)


if __name__ == "__main__":
    asyncio.run(Main())
