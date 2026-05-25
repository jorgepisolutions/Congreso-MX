import logging
from dataclasses import dataclass
from datetime import date

from CongresoMx.Scrapers.Base import BaseScraper
from CongresoMx.Scrapers.Diputados.Parsers import (
    CurriculaCruda,
    LegisladorListadoCrudo,
    ParsearCurricula,
    ParsearListadoDiputados,
)
from CongresoMx.Utils.Texto import NombreHashSha256, PartirNombreHispano

Logger = logging.getLogger(__name__)

BASE_URL_TEMPLATE = "https://sitl.diputados.gob.mx/{Legislatura}_leg/"
MIN_FILAS_ESPERADAS = 400
FUENTE = "SITL"


# Datos completos de un legislador tras mergear listado + curricula.
# Es lo que el service consume para hacer los upserts en DB.
@dataclass(frozen=True)
class LegisladorMergeado:
    IdExterno: str
    NombreCompleto: str
    Nombre: str | None
    ApellidoPaterno: str | None
    ApellidoMaterno: str | None
    NombreHash: str
    PartidoSiglas: str | None
    Estado: str
    TipoEleccion: str
    Distrito: int | None
    Circunscripcion: int | None
    Curul: str | None
    Telefono: str | None
    Email: str | None
    FechaNacimiento: date | None
    FotoUrl: str | None
    SuplenteNombre: str | None


# Combina LegisladorListadoCrudo (canonico para partido, estado, numero)
# con CurriculaCruda (canonico para nombre, contacto, fecha nacimiento).
# Si difieren en TipoEleccion o Distrito, prevalece la curricula.
def Mergear(
    Listado: LegisladorListadoCrudo,
    Curricula: CurriculaCruda,
) -> LegisladorMergeado:
    NombreCompleto = Curricula.NombreCompleto or Listado.NombreCompletoListado
    Nombre, ApPaterno, ApMaterno = PartirNombreHispano(Listado.NombreCompletoListado)
    TipoEleccion = Curricula.TipoEleccion or Listado.TipoEleccion
    Distrito = Curricula.Distrito if Curricula.Distrito is not None else Listado.Distrito
    Circuns = (
        Curricula.Circunscripcion
        if Curricula.Circunscripcion is not None
        else Listado.Circunscripcion
    )

    if (
        Curricula.PartidoSiglasLogo
        and Listado.PartidoSiglas
        and Curricula.PartidoSiglasLogo != Listado.PartidoSiglas
    ):
        Logger.warning(
            "Conflicto partido para Id=%s: listado=%s curricula=%s; gana listado",
            Listado.IdExterno,
            Listado.PartidoSiglas,
            Curricula.PartidoSiglasLogo,
        )

    return LegisladorMergeado(
        IdExterno=Listado.IdExterno,
        NombreCompleto=NombreCompleto,
        Nombre=Nombre,
        ApellidoPaterno=ApPaterno,
        ApellidoMaterno=ApMaterno,
        NombreHash=NombreHashSha256(NombreCompleto),
        PartidoSiglas=Listado.PartidoSiglas,
        Estado=Listado.Estado,
        TipoEleccion=TipoEleccion,
        Distrito=Distrito,
        Circunscripcion=Circuns,
        Curul=Curricula.Curul,
        Telefono=Curricula.Telefono,
        Email=Curricula.Email,
        FechaNacimiento=Curricula.FechaNacimiento,
        FotoUrl=Curricula.FotoUrl,
        SuplenteNombre=Curricula.SuplenteNombre,
    )


# Scraper para listado + curriculas de la Camara de Diputados SITL.
# Hereda BaseScraper (rate limit, retry, encoding, UA navegador).
# Solo descarga + parsea; persistencia esta en CongresoMx.Services.Legisladores.
class ScraperDiputadosLegisladores(BaseScraper):
    def __init__(self, Legislatura: str = "LXVI") -> None:
        super().__init__()
        self._Legislatura = Legislatura
        self._BaseUrl = BASE_URL_TEMPLATE.format(Legislatura=Legislatura)

    # Descarga y parsea el listado completo de la legislatura.
    # Valida cantidad minima de filas para detectar cambios estructurales.
    async def ScrapearListado(self) -> list[LegisladorListadoCrudo]:
        Url = f"{self._BaseUrl}listado_diputados_gpnp.php"
        Html = await self.GetHtml(Url)
        Resultados = ParsearListadoDiputados(Html)
        if len(Resultados) < MIN_FILAS_ESPERADAS:
            raise RuntimeError(
                f"Listado devolvio solo {len(Resultados)} filas (esperado >= "
                f"{MIN_FILAS_ESPERADAS}). La estructura del portal pudo haber cambiado."
            )
        Logger.info(
            "Listado parseado: %d diputados en %s",
            len(Resultados), self._Legislatura,
        )
        return Resultados

    # Descarga y parsea la curricula de un diputado por su IdExterno.
    async def ScrapearCurricula(self, IdExterno: str) -> CurriculaCruda:
        Url = f"{self._BaseUrl}curricula.php?dipt={IdExterno}"
        Html = await self.GetHtml(Url)
        return ParsearCurricula(Html, IdExterno)

    # Orquesta todo: listado, luego curricula por cada Id, merge final.
    # Limit es para dev: trunca la lista despues del listado pero antes de
    # las curriculas (~17 min vs ~20 s con --limit 10).
    async def ScrapearLegislatura(
        self, Limit: int | None = None
    ) -> list[LegisladorMergeado]:
        Listado = await self.ScrapearListado()
        if Limit is not None and Limit > 0:
            Listado = Listado[:Limit]
            Logger.info("Aplicando --limit %d", Limit)

        Mergeados: list[LegisladorMergeado] = []
        for Index, Item in enumerate(Listado, start=1):
            try:
                Curricula = await self.ScrapearCurricula(Item.IdExterno)
            except Exception as Exc:
                Logger.error(
                    "Error scrapeando curricula Id=%s (%d/%d): %s",
                    Item.IdExterno, Index, len(Listado), Exc,
                )
                continue
            Mergeados.append(Mergear(Item, Curricula))
            if Index % 25 == 0 or Index == len(Listado):
                Logger.info("Progreso: %d/%d curriculas", Index, len(Listado))

        return Mergeados
