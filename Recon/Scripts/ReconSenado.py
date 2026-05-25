import asyncio
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

from ReconBase import (
    OUTPUT_ROOT,
    PrintConsoleSummary,
    Recon,
    ReconClient,
    ReconResult,
    SetupLogging,
    WriteSummary,
)

LEGISLATURA_NUM = "66"
BASE_URL = f"https://www.senado.gob.mx/{LEGISLATURA_NUM}/"
PORTAL = "Senado"
OUTPUT_DIR = OUTPUT_ROOT / PORTAL

# Rutas candidatas a probar despues del home. Estas son hipotesis; el
# recon reporta cuales son 200 y cuales no. PROJECT.md dice "mapear con
# reconnaissance" porque no tenemos rutas oficiales.
CANDIDATE_PATHS = [
    "senadores/",
    "senadores/listado",
    "legisladores/",
    "asistencias/",
    "asistencia/",
    "gaceta/",
    "sesiones/",
    "votaciones/",
    "comisiones/",
]


# Extrae paths internos del home extrayendo todos los <a href> y filtrando
# los que comparten host con BASE_URL.
def ExtractInternalLinks(HtmlPath: Path, BaseUrl: str, MaxLinks: int = 30) -> list[str]:
    if not HtmlPath.exists():
        return []
    Html = HtmlPath.read_text(encoding="utf-8")
    BaseHost = urlparse(BaseUrl).netloc
    Hrefs = re.findall(r'href=["\']([^"\']+)["\']', Html)
    Seen: set[str] = set()
    Out: list[str] = []
    for Raw in Hrefs:
        Absolute = urljoin(BaseUrl, Raw)
        Parsed = urlparse(Absolute)
        if Parsed.netloc != BaseHost:
            continue
        if Parsed.scheme not in ("http", "https"):
            continue
        if Absolute in Seen:
            continue
        Seen.add(Absolute)
        Out.append(Absolute)
        if len(Out) >= MaxLinks:
            break
    return Out


# Genera nombre de archivo seguro a partir de una URL.
def UrlToFilename(Url: str) -> str:
    Parsed = urlparse(Url)
    Path_ = Parsed.path.strip("/").replace("/", "_") or "index"
    Path_ = re.sub(r"[^A-Za-z0-9._-]", "_", Path_)
    return f"{Path_}.html"


# Recon Senado: descarga home, atacca paths candidatos, descubre internos
# desde el home y se queda con los primeros 5 que aun no haya tocado.
async def Main() -> None:
    SetupLogging()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    Results: list[ReconResult] = []
    TouchedUrls: set[str] = set()

    async with ReconClient() as Client:
        # Home
        HomeUrl = BASE_URL
        HomePath = OUTPUT_DIR / f"Home{LEGISLATURA_NUM}.html"
        Results.append(await Recon(Client, HomeUrl, HomePath))
        TouchedUrls.add(HomeUrl)

        # Paths candidatos hardcodeados
        for SubPath in CANDIDATE_PATHS:
            Url = urljoin(BASE_URL, SubPath)
            if Url in TouchedUrls:
                continue
            OutPath = OUTPUT_DIR / UrlToFilename(Url)
            Results.append(await Recon(Client, Url, OutPath))
            TouchedUrls.add(Url)

        # Descubre hasta 5 enlaces internos del home no tocados aun
        InternalLinks = ExtractInternalLinks(HomePath, BASE_URL, MaxLinks=30)
        DiscoveryCount = 0
        for Url in InternalLinks:
            if Url in TouchedUrls:
                continue
            OutPath = OUTPUT_DIR / f"Discovered_{UrlToFilename(Url)}"
            Results.append(await Recon(Client, Url, OutPath))
            TouchedUrls.add(Url)
            DiscoveryCount += 1
            if DiscoveryCount >= 5:
                break

    WriteSummary(Results, OUTPUT_DIR, PORTAL)
    PrintConsoleSummary(Results, PORTAL)


if __name__ == "__main__":
    asyncio.run(Main())
