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


# Scrapea los legisladores de Diputados de una legislatura y los persiste.
# Limit > 0 para validacion rapida en dev.
@ScrapeApp.command(name="Legisladores")
def ScrapeLegisladores(
    Camara: str = typer.Option("Diputados", help="Camara: Diputados (Senado pendiente)."),
    Legislatura: str = typer.Option("LXVI", help="Legislatura: LXVI."),
    Limit: int = typer.Option(0, help="0 = todos; N > 0 = solo los primeros N."),
) -> None:
    import asyncio

    if Camara != "Diputados":
        raise typer.BadParameter(
            f"--Camara {Camara!r} aun no implementada (solo Diputados en Fase 3)"
        )
    if Legislatura != "LXVI":
        raise typer.BadParameter(
            f"--Legislatura {Legislatura!r} aun no implementada (solo LXVI en Fase 3)"
        )

    from CongresoMx.Database import DisposeEngine, GetSessionMaker
    from CongresoMx.Scrapers.Diputados.Legisladores import ScraperDiputadosLegisladores
    from CongresoMx.Services.Legisladores import GuardarBatch

    async def Run() -> None:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        async with ScraperDiputadosLegisladores(Legislatura=Legislatura) as Scraper:
            Mergeados = await Scraper.ScrapearLegislatura(
                Limit=Limit if Limit > 0 else None
            )

        SessionMaker = GetSessionMaker()
        async with SessionMaker() as Session:
            Stats = await GuardarBatch(Session, Mergeados, NumeroLegislatura=Legislatura)
            await Session.commit()

        typer.echo("")
        typer.echo(f"Mergeados scrapeados:     {len(Mergeados)}")
        typer.echo(f"Nuevos en DB:             {Stats.Nuevos}")
        typer.echo(f"Actualizados en DB:       {Stats.Actualizados}")
        typer.echo(f"Sin partido resuelto:     {Stats.SinPartido}")
        typer.echo(f"Sin estado resuelto:      {Stats.SinEstado}")
        typer.echo(f"Errores de upsert:        {Stats.Errores}")
        await DisposeEngine()

    asyncio.run(Run())


# Scrapea el calendario de sesiones de Diputados via SITL.
# Una corrida cubre todos los perts conocidos (~10 seg).
@ScrapeApp.command(name="Sesiones")
def ScrapeSesiones(
    Camara: str = typer.Option("Diputados", help="Camara: Diputados (Senado pendiente)."),
    Legislatura: str = typer.Option("LXVI", help="Legislatura: LXVI."),
) -> None:
    import asyncio

    if Camara != "Diputados":
        raise typer.BadParameter(
            f"--Camara {Camara!r} aun no implementada (solo Diputados en Fase 4)"
        )
    if Legislatura != "LXVI":
        raise typer.BadParameter(
            f"--Legislatura {Legislatura!r} aun no implementada (solo LXVI en Fase 4)"
        )

    from CongresoMx.Database import DisposeEngine, GetSessionMaker
    from CongresoMx.Scrapers.Diputados.Sesiones import ScraperDiputadosSesiones
    from CongresoMx.Services.Sesiones import GuardarBatchSesiones

    async def Run() -> None:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        async with ScraperDiputadosSesiones(Legislatura=Legislatura) as Scraper:
            Sesiones = await Scraper.ScrapearCalendarioCompleto()

        SessionMaker = GetSessionMaker()
        async with SessionMaker() as Session:
            Stats = await GuardarBatchSesiones(
                Session, Sesiones, NumeroLegislatura=Legislatura
            )
            await Session.commit()

        typer.echo("")
        typer.echo(f"Sesiones detectadas:      {len(Sesiones)}")
        typer.echo(f"Nuevas en DB:             {Stats.Nuevas}")
        typer.echo(f"Actualizadas en DB:       {Stats.Actualizadas}")
        typer.echo(f"Sin periodo:              {Stats.SinPeriodo}")
        typer.echo(f"Errores:                  {Stats.Errores}")
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
