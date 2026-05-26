import logging

from CongresoMx.Scrapers.Base import BaseScraper
from CongresoMx.Scrapers.Diputados.Legisladores import LegisladorMergeado
from CongresoMx.Scrapers.Senado.ParsersLxv import (
    ParsearDetalleLxv,
    ParsearListadoLxv,
    SenadorLxvListadoCrudo,
)
from CongresoMx.Utils.Texto import NombreHashSha256, PartirNombreHispano

Logger = logging.getLogger(__name__)

LISTADO_URL = "https://www.senado.gob.mx/informacion/senadores/LXIV_LXV"
DETALLE_URL_TEMPLATE = "https://www.senado.gob.mx/informacion/senadores/LXIV_LXV/{IdExterno}"
SCRAPER_FUENTE = "SENADO_LXV"


# Combina un listado-crudo + tipo eleccion en un LegisladorMergeado reusable.
# Distrito y Circunscripcion quedan None (no aplican en Senado).
def Mergear(
    Listado: SenadorLxvListadoCrudo, TipoEleccion: str | None
) -> LegisladorMergeado:
    Nombre, ApPaterno, ApMaterno = PartirNombreHispano(Listado.NombreCompleto)
    return LegisladorMergeado(
        IdExterno=Listado.IdExterno,
        NombreCompleto=Listado.NombreCompleto,
        Nombre=Nombre,
        ApellidoPaterno=ApPaterno,
        ApellidoMaterno=ApMaterno,
        NombreHash=NombreHashSha256(Listado.NombreCompleto),
        PartidoSiglas=Listado.PartidoSiglas,
        Estado=Listado.Estado,
        TipoEleccion=TipoEleccion or "MayoriaRelativa",
        Distrito=None,
        Circunscripcion=None,
        Curul=None,
        Telefono=None,
        Email=None,
        FechaNacimiento=None,
        FotoUrl=Listado.FotoUrl,
        SuplenteNombre=None,
    )


# Scraper para senadores de LXV (y LXIV combinado, pero filtramos a los
# 128 activos en LXV via las sesiones de LXV).
class ScraperSenadoLegisladoresLxv(BaseScraper):
    def __init__(self, Legislatura: str = "LXV") -> None:
        super().__init__()
        if Legislatura != "LXV":
            raise ValueError(
                "ScraperSenadoLegisladoresLxv solo soporta LXV; usa "
                "ScraperSenadoLegisladores para LXVI"
            )
        self._Legislatura = Legislatura

    # Descarga el listado combinado y devuelve >= 128 perfiles.
    async def ScrapearListado(self) -> list[SenadorLxvListadoCrudo]:
        Html = await self.GetHtml(LISTADO_URL)
        Resultados = ParsearListadoLxv(Html)
        if len(Resultados) < 120:
            raise RuntimeError(
                f"Listado LXIV_LXV devolvio {len(Resultados)} perfiles "
                "(esperado >= 120); estructura puede haber cambiado"
            )
        Logger.info("Listado LXV parseado: %d perfiles", len(Resultados))
        return Resultados

    # Descarga el detalle de un senador y extrae TipoEleccion.
    async def ScrapearDetalle(self, IdExterno: str) -> str | None:
        Url = DETALLE_URL_TEMPLATE.format(IdExterno=IdExterno)
        Html = await self.GetHtml(Url)
        Detalle = ParsearDetalleLxv(Html, IdExterno)
        return Detalle.TipoEleccion

    # Orquesta listado + detalle. Limit recorta despues del listado.
    async def ScrapearLegislatura(
        self, Limit: int | None = None
    ) -> list[LegisladorMergeado]:
        Listado = await self.ScrapearListado()
        if Limit is not None and Limit > 0:
            Listado = Listado[:Limit]
            Logger.info("Aplicando --limit %d", Limit)

        Mergeados: list[LegisladorMergeado] = []
        for Index, Crudo in enumerate(Listado, start=1):
            try:
                Tipo = await self.ScrapearDetalle(Crudo.IdExterno)
            except Exception as Exc:
                Logger.error(
                    "Error detalle Senador Id=%s (%d/%d): %s",
                    Crudo.IdExterno, Index, len(Listado), Exc,
                )
                Tipo = None
            Mergeados.append(Mergear(Crudo, Tipo))
            if Index % 25 == 0 or Index == len(Listado):
                Logger.info("Progreso LXV senadores: %d/%d", Index, len(Listado))

        return Mergeados
