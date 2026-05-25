import asyncio

from ReconBase import (
    OUTPUT_ROOT,
    PrintConsoleSummary,
    Recon,
    ReconClient,
    ReconResult,
    SetupLogging,
    WriteSummary,
)

BASE_URL = "https://www.sil.gobernacion.gob.mx/portal/"
PORTAL = "Sil"
OUTPUT_DIR = OUTPUT_ROOT / PORTAL

# URLs candidatas para SIL. Las dos primeras son las que PROJECT.md menciona.
# El index del portal puede revelar la estructura real si las rutas planas
# devuelven 404 o redirect a un menu.
URLS_TO_PROBE = [
    (BASE_URL, "PortalIndex.html"),
    (f"{BASE_URL}ReporteSesion/diputados", "ReporteSesionDiputados.html"),
    (f"{BASE_URL}ReporteSesion/senadores", "ReporteSesionSenadores.html"),
]


# Recon SIL: probar las URLs definidas en URLS_TO_PROBE y reportar.
async def Main() -> None:
    SetupLogging()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    Results: list[ReconResult] = []

    # Verify=False: el portal SIL usa CAs intermedias que no se validan
    # contra el trust store estandar. Para recon de HTML publico es aceptable.
    async with ReconClient(Verify=False) as Client:
        for Url, Filename in URLS_TO_PROBE:
            Results.append(await Recon(Client, Url, OUTPUT_DIR / Filename))

    WriteSummary(Results, OUTPUT_DIR, PORTAL)
    PrintConsoleSummary(Results, PORTAL)


if __name__ == "__main__":
    asyncio.run(Main())
