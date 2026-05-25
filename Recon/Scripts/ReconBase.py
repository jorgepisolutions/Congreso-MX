import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from selectolax.parser import HTMLParser

Logger = logging.getLogger(__name__)

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
}

RATE_LIMIT_SEC = 1.0
HTTP_TIMEOUT = 30.0
HTML_MIN_BYTES = 2048

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = PROJECT_ROOT / "Recon" / "Output"


# Resultado de la descarga de una URL. Lo que cualquier reporte necesita.
# Si Error != None, el resto de campos puede estar vacio.
@dataclass
class ReconResult:
    Url: str
    FinalUrl: str
    Status: int
    Bytes: int
    EncodingHeader: str
    EncodingApplied: str
    SavedPath: Path | None
    Title: str
    TagCounts: dict[str, int]
    TopClasses: list[tuple[str, int]]
    TopIds: list[tuple[str, int]]
    Notes: list[str] = field(default_factory=list)
    Error: str | None = None


# Cliente HTTP async con headers de navegador y rate limit por host.
# Sleep adaptativo: si el ultimo request fue hace menos de RateLimitSec,
# espera la diferencia antes del siguiente. Verify=False para sitios con
# CAs intermedias mal configuradas (comun en portales del gobierno MX).
class ReconClient:
    def __init__(self, RateLimitSec: float = RATE_LIMIT_SEC, Verify: bool = True):
        self._RateLimitSec = RateLimitSec
        self._Verify = Verify
        self._LastRequestAt = 0.0
        self._Client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "ReconClient":
        self._Client = httpx.AsyncClient(
            headers=BROWSER_HEADERS,
            timeout=HTTP_TIMEOUT,
            follow_redirects=True,
            verify=self._Verify,
        )
        return self

    async def __aexit__(self, *Exc: Any) -> None:
        if self._Client is not None:
            await self._Client.aclose()

    # Ejecuta GET respetando el rate limit. Devuelve la respuesta cruda.
    async def Get(self, Url: str) -> httpx.Response:
        Now = time.monotonic()
        Sleep = self._RateLimitSec - (Now - self._LastRequestAt)
        if Sleep > 0:
            await asyncio.sleep(Sleep)
        assert self._Client is not None, "ReconClient debe usarse como async with"
        Logger.info("GET %s", Url)
        Response = await self._Client.get(Url)
        self._LastRequestAt = time.monotonic()
        return Response


# Decodifica bytes a string. Usa charset del header si existe; si no,
# asume iso-8859-1 (default SITL). Cae a 'replace' si todo falla.
def DecodeBody(Response: httpx.Response) -> tuple[str, str]:
    Body = Response.content
    Declared = Response.charset_encoding or "iso-8859-1"
    try:
        return Body.decode(Declared), Declared
    except UnicodeDecodeError:
        return Body.decode("iso-8859-1", errors="replace"), f"{Declared} (replace)"


# Extrae senales utiles del HTML para que el humano decida selectores:
# titulo, conteo de tags, top clases y top ids.
def AnalyzeHtml(Html: str) -> dict[str, Any]:
    Tree = HTMLParser(Html)
    TagsOfInterest = ["table", "form", "a", "script", "iframe", "tr", "td", "div", "ul", "li"]
    TagCounts = {Tag: len(Tree.css(Tag)) for Tag in TagsOfInterest}

    TitleNode = Tree.css_first("title")
    Title = TitleNode.text(strip=True) if TitleNode else ""

    ClassFreq: dict[str, int] = {}
    IdFreq: dict[str, int] = {}
    for Node in Tree.css("*"):
        ClsAttr = Node.attributes.get("class")
        if ClsAttr:
            for Cls in ClsAttr.split():
                ClassFreq[Cls] = ClassFreq.get(Cls, 0) + 1
        IidAttr = Node.attributes.get("id")
        if IidAttr:
            IdFreq[IidAttr] = IdFreq.get(IidAttr, 0) + 1

    TopClasses = sorted(ClassFreq.items(), key=lambda X: -X[1])[:10]
    TopIds = sorted(IdFreq.items(), key=lambda X: -X[1])[:10]

    return {
        "Title": Title,
        "TagCounts": TagCounts,
        "TopClasses": TopClasses,
        "TopIds": TopIds,
    }


# Descarga, decodifica, analiza y guarda una URL en disco como UTF-8.
# Captura httpx.HTTPError en ReconResult.Error; no lanza excepciones.
async def Recon(Client: ReconClient, Url: str, OutPath: Path) -> ReconResult:
    try:
        Response = await Client.Get(Url)
    except httpx.HTTPError as Exc:
        Logger.warning("HTTPError en %s: %s", Url, Exc)
        return ReconResult(
            Url=Url, FinalUrl=Url, Status=0, Bytes=0,
            EncodingHeader="", EncodingApplied="",
            SavedPath=None, Title="",
            TagCounts={}, TopClasses=[], TopIds=[],
            Error=f"{type(Exc).__name__}: {Exc}",
        )

    Body, EncodingApplied = DecodeBody(Response)

    Notes: list[str] = []
    if len(Response.content) < HTML_MIN_BYTES:
        Notes.append(f"HTML pequeno (<{HTML_MIN_BYTES}B): posible 404 o pagina vacia")

    Analysis = AnalyzeHtml(Body)
    LowerTitle = Analysis["Title"].lower()
    if any(Bad in LowerTitle for Bad in ("404", "no encontrado", "not found", "error")):
        Notes.append(f"Titulo sospechoso: {Analysis['Title']!r}")

    OutPath.parent.mkdir(parents=True, exist_ok=True)
    OutPath.write_text(Body, encoding="utf-8")

    return ReconResult(
        Url=Url,
        FinalUrl=str(Response.url),
        Status=Response.status_code,
        Bytes=len(Response.content),
        EncodingHeader=Response.charset_encoding or "(none)",
        EncodingApplied=EncodingApplied,
        SavedPath=OutPath,
        Title=Analysis["Title"],
        TagCounts=Analysis["TagCounts"],
        TopClasses=Analysis["TopClasses"],
        TopIds=Analysis["TopIds"],
        Notes=Notes,
    )


# Genera ReconSummary.md dentro de OutDir. Tabla compacta + detalle por URL.
def WriteSummary(Results: list[ReconResult], OutDir: Path, Portal: str) -> Path:
    SummaryPath = OutDir / "ReconSummary.md"
    Lines: list[str] = []
    Lines.append(f"# Recon Summary: {Portal}")
    Lines.append("")
    Ok = sum(1 for R in Results if R.Error is None and R.Status == 200)
    Err = sum(1 for R in Results if R.Error)
    Lines.append(f"Total URLs probadas: {len(Results)}  |  200 OK: {Ok}  |  Errores: {Err}")
    Lines.append("")
    Lines.append("## Tabla resumen")
    Lines.append("")
    Lines.append("| Status | URL | Bytes | Enc | Archivo | Notas |")
    Lines.append("|---|---|---|---|---|---|")
    for R in Results:
        Status = R.Error or str(R.Status)
        Filename = R.SavedPath.name if R.SavedPath else "-"
        NoteStr = "; ".join(R.Notes) if R.Notes else ""
        Lines.append(
            f"| {Status} | `{R.Url}` | {R.Bytes} | {R.EncodingApplied} "
            f"| `{Filename}` | {NoteStr} |"
        )
    Lines.append("")
    Lines.append("## Detalle por URL")
    for R in Results:
        Lines.append("")
        Lines.append(f"### `{R.Url}`")
        if R.Error:
            Lines.append(f"- Error: `{R.Error}`")
            continue
        Lines.append(f"- Status: {R.Status}")
        Lines.append(f"- Final URL: `{R.FinalUrl}`")
        Lines.append(f"- Bytes: {R.Bytes}")
        Lines.append(
            f"- Encoding header: `{R.EncodingHeader}`  |  aplicado: `{R.EncodingApplied}`"
        )
        Lines.append(f"- Archivo: `{R.SavedPath}`")
        Lines.append(f"- Titulo: `{R.Title}`")
        Lines.append(f"- Tag counts: `{R.TagCounts}`")
        if R.TopClasses:
            Lines.append(f"- Top classes: `{R.TopClasses}`")
        if R.TopIds:
            Lines.append(f"- Top ids: `{R.TopIds}`")
        if R.Notes:
            Lines.append(f"- Notes: `{R.Notes}`")
    Lines.append("")
    SummaryPath.write_text("\n".join(Lines), encoding="utf-8")
    return SummaryPath


# Imprime resumen a stdout en una tabla legible.
def PrintConsoleSummary(Results: list[ReconResult], Portal: str) -> None:
    print()
    print(f"=== Recon {Portal} ===")
    for R in Results:
        Status = R.Error or str(R.Status)
        Filename = R.SavedPath.name if R.SavedPath else "-"
        NotesStr = f"  [{'; '.join(R.Notes)}]" if R.Notes else ""
        print(f"  [{Status:>6}] {R.Bytes:>7}B  {Filename:<40}  {R.Url}{NotesStr}")
    print()


# Configura logging consistente para los scripts de recon.
def SetupLogging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
