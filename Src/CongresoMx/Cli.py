import logging

import typer

from CongresoMx.Config import GetSettings

App = typer.Typer(
    name="CongresoMx",
    help="ETL del Congreso de la Union de Mexico.",
    no_args_is_help=True,
)

ScrapeApp = typer.Typer(
    name="Scrape",
    help="Comandos de scraping de portales del Congreso.",
    no_args_is_help=True,
)
App.add_typer(ScrapeApp, name="Scrape")

Logger = logging.getLogger(__name__)


# Comando de smoke test: imprime saludo y carga la config para validar wiring.
@App.command(name="Hello")
def Hello(Name: str = typer.Option("Mundo", help="Nombre a saludar.")) -> None:
    Config = GetSettings()
    typer.echo(f"Hola, {Name}.")
    typer.echo(f"EnvName={Config.EnvName} LogLevel={Config.LogLevel}")


# Levanta uvicorn apuntando a CongresoMx.Api.Main:App.
# Toma host y puerto del .env si no se pasan flags.
@App.command(name="Serve")
def Serve(
    Host: str = typer.Option("", help="Host. Vacio = lee ApiHost del .env."),
    Port: int = typer.Option(0, help="Puerto. 0 = lee ApiPort del .env."),
    Reload: bool = typer.Option(False, help="Auto-reload en cambios (solo dev)."),
) -> None:
    import uvicorn

    Config = GetSettings()
    uvicorn.run(
        "CongresoMx.Api.Main:App",
        host=Host or Config.ApiHost,
        port=Port or Config.ApiPort,
        reload=Reload,
    )


# Corre el scheduler en foreground. Bloquea hasta SIGINT/SIGTERM.
@App.command(name="Scheduler")
def Scheduler() -> None:
    from CongresoMx.Scheduler.Main import Main as RunScheduler

    RunScheduler()


# Scrapea los legisladores de una camara/legislatura y los persiste.
# Limit > 0 para validacion rapida en dev. Soporta Diputados y Senado.
@ScrapeApp.command(name="Legisladores")
def ScrapeLegisladores(
    Camara: str = typer.Option("Diputados", help="Camara: Diputados o Senado."),
    Legislatura: str = typer.Option("LXVI", help="Legislatura: LXVI."),
    Limit: int = typer.Option(0, help="0 = todos; N > 0 = solo los primeros N."),
) -> None:
    import asyncio

    if Camara not in ("Diputados", "Senado"):
        raise typer.BadParameter(f"--Camara {Camara!r} no soportada (Diputados o Senado)")
    if Legislatura != "LXVI":
        raise typer.BadParameter(
            f"--Legislatura {Legislatura!r} aun no implementada (solo LXVI)"
        )

    from CongresoMx.Database import DisposeEngine, GetSessionMaker
    from CongresoMx.Services.Legisladores import GuardarBatch

    async def Run() -> None:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        if Camara == "Diputados":
            from CongresoMx.Scrapers.Diputados.Legisladores import (
                ScraperDiputadosLegisladores,
            )
            async with ScraperDiputadosLegisladores(Legislatura=Legislatura) as Scraper:
                Mergeados = await Scraper.ScrapearLegislatura(
                    Limit=Limit if Limit > 0 else None
                )
        else:
            from CongresoMx.Scrapers.Senado.Legisladores import (
                ScraperSenadoLegisladores,
            )
            async with ScraperSenadoLegisladores(Legislatura=Legislatura) as Scraper:
                Mergeados = await Scraper.ScrapearLegislatura(
                    Limit=Limit if Limit > 0 else None
                )

        SessionMaker = GetSessionMaker()
        async with SessionMaker() as Session:
            Stats = await GuardarBatch(
                Session, Mergeados, NumeroLegislatura=Legislatura, Camara=Camara
            )
            await Session.commit()

        typer.echo("")
        typer.echo(f"Camara:                   {Camara}")
        typer.echo(f"Mergeados scrapeados:     {len(Mergeados)}")
        typer.echo(f"Nuevos en DB:             {Stats.Nuevos}")
        typer.echo(f"Actualizados en DB:       {Stats.Actualizados}")
        typer.echo(f"Sin partido resuelto:     {Stats.SinPartido}")
        typer.echo(f"Sin estado resuelto:      {Stats.SinEstado}")
        typer.echo(f"Errores de upsert:        {Stats.Errores}")
        await DisposeEngine()

    asyncio.run(Run())


# Scrapea el calendario de sesiones de una camara. Diputados via SITL
# (7 perts ~10 seg); Senado via /66/sesiones (1 request ~3 seg).
@ScrapeApp.command(name="Sesiones")
def ScrapeSesiones(
    Camara: str = typer.Option("Diputados", help="Camara: Diputados o Senado."),
    Legislatura: str = typer.Option("LXVI", help="Legislatura: LXVI."),
) -> None:
    import asyncio

    if Camara not in ("Diputados", "Senado"):
        raise typer.BadParameter(f"--Camara {Camara!r} no soportada")
    if Legislatura != "LXVI":
        raise typer.BadParameter(f"--Legislatura {Legislatura!r} aun no implementada")

    from CongresoMx.Database import DisposeEngine, GetSessionMaker

    async def Run() -> None:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        if Camara == "Diputados":
            from CongresoMx.Scrapers.Diputados.Sesiones import ScraperDiputadosSesiones
            from CongresoMx.Services.Sesiones import GuardarBatchSesiones
            async with ScraperDiputadosSesiones(Legislatura=Legislatura) as Scraper:
                Sesiones = await Scraper.ScrapearCalendarioCompleto()
            SessionMaker = GetSessionMaker()
            async with SessionMaker() as Session:
                Stats = await GuardarBatchSesiones(
                    Session, Sesiones, NumeroLegislatura=Legislatura
                )
                await Session.commit()
        else:
            from CongresoMx.Scrapers.Senado.Sesiones import ScraperSenadoSesiones
            from CongresoMx.Services.Sesiones import GuardarBatchSesionesSenado
            async with ScraperSenadoSesiones(Legislatura=Legislatura) as Scraper:
                Sesiones = await Scraper.ScrapearSesiones()
            SessionMaker = GetSessionMaker()
            async with SessionMaker() as Session:
                Stats = await GuardarBatchSesionesSenado(
                    Session, Sesiones, NumeroLegislatura=Legislatura
                )
                await Session.commit()

        typer.echo("")
        typer.echo(f"Camara:                   {Camara}")
        typer.echo(f"Sesiones detectadas:      {len(Sesiones)}")
        typer.echo(f"Nuevas en DB:             {Stats.Nuevas}")
        typer.echo(f"Actualizadas en DB:       {Stats.Actualizadas}")
        typer.echo(f"Sin periodo:              {Stats.SinPeriodo}")
        typer.echo(f"Errores:                  {Stats.Errores}")
        await DisposeEngine()

    asyncio.run(Run())


# Scrapea las asistencias de Diputados LXVI por diputado o backfill completo.
# Solo Diputados/LXVI por ahora. --Diputado X corre uno solo (smoke ~10s).
# --Backfill recorre los 500 diputados (~58 min).
@ScrapeApp.command(name="Asistencias")
def ScrapeAsistencias(
    Camara: str = typer.Option("Diputados", help="Camara: Diputados."),
    Legislatura: str = typer.Option("LXVI", help="Legislatura: LXVI."),
    Diputado: str = typer.Option("", help="IdExterno del diputado para corrida individual."),
    Backfill: bool = typer.Option(False, help="Recorre TODOS los diputados de LXVI."),
) -> None:
    import asyncio

    if Camara != "Diputados":
        raise typer.BadParameter("--Camara solo Diputados en Fase 5")
    if Legislatura != "LXVI":
        raise typer.BadParameter("--Legislatura solo LXVI en Fase 5")
    if not Diputado and not Backfill:
        raise typer.BadParameter(
            "Pasa --Diputado <Id> O --Backfill (no podemos correr sin saber a quien)"
        )
    if Diputado and Backfill:
        raise typer.BadParameter("--Diputado y --Backfill son mutuamente exclusivos")

    from sqlalchemy import select

    from CongresoMx.Database import DisposeEngine, GetSessionMaker
    from CongresoMx.Models import LegisladorPeriodo, Legislatura as LegMod
    from CongresoMx.Scrapers.Diputados.Asistencias import ScraperDiputadosAsistencias
    from CongresoMx.Services.Asistencias import (
        CargarMapaSesiones,
        FinalizarScrapingRun,
        GuardarAsistenciasDiputado,
        IniciarScrapingRun,
        ResolverLegisladorPeriodoId,
        StatsAsistencias,
    )

    Fuente = f"SITL_{Legislatura}"

    async def Run() -> None:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        SessionMaker = GetSessionMaker()

        async with SessionMaker() as Sess:
            LegRow = (
                await Sess.execute(select(LegMod).where(LegMod.Numero == Legislatura))
            ).scalar_one_or_none()
            if LegRow is None:
                raise RuntimeError(f"Legislatura {Legislatura} no esta en DB")
            LegislaturaId = LegRow.Id

            MapaSesiones = await CargarMapaSesiones(Sess, LegislaturaId)
            if not MapaSesiones:
                raise RuntimeError("No hay Sesiones en DB; corre Scrape Sesiones primero")

            if Diputado:
                IdsExternos = [Diputado]
            else:
                Rows = (
                    await Sess.execute(
                        select(LegisladorPeriodo.IdExterno).where(
                            LegisladorPeriodo.LegislaturaId == LegislaturaId,
                            LegisladorPeriodo.Camara == "Diputados",
                            LegisladorPeriodo.Fuente == Fuente,
                        )
                    )
                ).all()
                IdsExternos = [R[0] for R in Rows if R[0]]
            typer.echo(f"Diputados a procesar: {len(IdsExternos)}")

            Stats = StatsAsistencias()
            ScrapingRunRow = await IniciarScrapingRun(
                Sess,
                Tipo="Asistencias",
                Parametros={"Legislatura": Legislatura, "Total": len(IdsExternos)},
            )
            await Sess.commit()
            ScrapingRunId = ScrapingRunRow.Id

        async with ScraperDiputadosAsistencias(Legislatura=Legislatura) as Scraper:
            for Index, IdExterno in enumerate(IdsExternos, start=1):
                Asistencias = await Scraper.ScrapearDiputado(IdExterno)
                async with SessionMaker() as Sess2:
                    LegPerId = await ResolverLegisladorPeriodoId(
                        Sess2, IdExterno, LegislaturaId, Fuente
                    )
                    if LegPerId is None:
                        Stats.LegPeriodoNoEncontrado += 1
                        continue
                    await GuardarAsistenciasDiputado(
                        Sess2,
                        LegisladorPeriodoId=LegPerId,
                        Asistencias=Asistencias,
                        MapaSesiones=MapaSesiones,
                        Fuente=Fuente,
                        Stats=Stats,
                    )
                    await Sess2.commit()
                if Index % 25 == 0 or Index == len(IdsExternos):
                    logging.getLogger("CongresoMx.Cli").info(
                        "Progreso: %d/%d diputados (nuevas=%d cambios=%d errores=%d)",
                        Index, len(IdsExternos), Stats.Nuevas, Stats.Cambios, Stats.Errores,
                    )

        async with SessionMaker() as Sess3:
            from CongresoMx.Models import ScrapingRun
            RunReload = (
                await Sess3.execute(select(ScrapingRun).where(ScrapingRun.Id == ScrapingRunId))
            ).scalar_one()
            FinalStatus = "Success" if Stats.Errores == 0 else "Partial"
            FinalizarScrapingRun(RunReload, Stats, FinalStatus)
            await Sess3.commit()

        typer.echo("")
        typer.echo(f"Asistencias nuevas:           {Stats.Nuevas}")
        typer.echo(f"Asistencias actualizadas:     {Stats.Actualizadas}")
        typer.echo(f"Cambios de estado detectados: {Stats.Cambios}")
        typer.echo(f"Codigos desconocidos:         {Stats.CodigosDesconocidos}")
        typer.echo(f"Sesion no encontrada:         {Stats.SesionNoEncontrada}")
        typer.echo(f"LegPeriodo no encontrado:     {Stats.LegPeriodoNoEncontrado}")
        typer.echo(f"Errores:                      {Stats.Errores}")
        await DisposeEngine()

    asyncio.run(Run())


# Entrypoint para `python -m CongresoMx.Cli` o el script `congresomx`.
def Main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    App()


if __name__ == "__main__":
    Main()
