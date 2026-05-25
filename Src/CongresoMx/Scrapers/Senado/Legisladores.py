import logging

from CongresoMx.Scrapers.Base import BaseScraper
from CongresoMx.Scrapers.Diputados.Legisladores import LegisladorMergeado
from CongresoMx.Scrapers.Senado.Parsers import (
    ParsearDetalleSenador,
    ParsearListadoSenadores,
    SenadorListadoCrudo,
)
from CongresoMx.Utils.Texto import NombreHashSha256, PartirNombreHispano

Logger = logging.getLogger(__name__)

BASE_URL_TEMPLATE = "https://www.senado.gob.mx/{LegNumero}/"
DETALLE_URL_TEMPLATE = "https://www.senado.gob.mx/{LegNumero}/senador/{IdExterno}"
LISTADO_PATH = "senadores/por_grupo_parlamentario"
LEG_NUMERO_POR_NOMBRE: dict[str, str] = {"LXVI": "66", "LXV": "65"}
SCRAPER_FUENTE = "SENADO"


# Combina listado + detalle en un LegisladorMergeado reusable por Services.
# Distrito y Circunscripcion quedan None (no aplican en Senado).
def Mergear(
    Listado: SenadorListadoCrudo, TipoEleccion: str | None
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
        Telefono=Listado.Telefono,
        Email=Listado.Email,
        FechaNacimiento=None,
        FotoUrl=Listado.FotoUrl,
        SuplenteNombre=None,
    )


# Scraper para senadores de la Camara de Senado. Reusa BaseScraper.
# El listado canonico es por_grupo_parlamentario (no /senadores/ a secas).
class ScraperSenadoLegisladores(BaseScraper):
    def __init__(self, Legislatura: str = "LXVI") -> None:
        super().__init__()
        LegNumero = LEG_NUMERO_POR_NOMBRE.get(Legislatura)
        if LegNumero is None:
            raise ValueError(f"Legislatura {Legislatura!r} no mapeada a numero del Senado")
        self._Legislatura = Legislatura
        self._LegNumero = LegNumero
        self._BaseUrl = BASE_URL_TEMPLATE.format(LegNumero=LegNumero)

    # Descarga el listado completo y devuelve los 128 senadores. Lanza si
    # el listado tiene menos de 120 (proteccion contra cambio estructural).
    async def ScrapearListado(self) -> list[SenadorListadoCrudo]:
        Url = f"{self._BaseUrl}{LISTADO_PATH}"
        Html = await self.GetHtml(Url)
        Resultados = ParsearListadoSenadores(Html)
        if len(Resultados) < 120:
            raise RuntimeError(
                f"Listado Senado devolvio {len(Resultados)} perfiles "
                "(esperado >=120); estructura puede haber cambiado"
            )
        Logger.info(
            "Listado Senado parseado: %d senadores en %s",
            len(Resultados), self._Legislatura,
        )
        return Resultados

    # Descarga la pagina de detalle de un senador y extrae TipoEleccion.
    async def ScrapearDetalle(self, IdExterno: str) -> str | None:
        Url = DETALLE_URL_TEMPLATE.format(
            LegNumero=self._LegNumero, IdExterno=IdExterno
        )
        Html = await self.GetHtml(Url)
        Detalle = ParsearDetalleSenador(Html, IdExterno)
        return Detalle.TipoEleccion

    # Orquesta: listado + detalle por cada senador, devolviendo LegisladorMergeado.
    # Limit > 0 trunca despues del listado pero antes de los detalles.
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
                Logger.info("Progreso: %d/%d senadores", Index, len(Listado))

        return Mergeados
