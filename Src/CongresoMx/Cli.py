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


# Scrapea las asistencias. Diputados: iterar por diputado (--Diputado o
# --Backfill). Senado: iterar por sesion (--Backfill solo).
@ScrapeApp.command(name="Asistencias")
def ScrapeAsistencias(
    Camara: str = typer.Option("Diputados", help="Camara: Diputados o Senado."),
    Legislatura: str = typer.Option("LXVI", help="Legislatura: LXVI."),
    Diputado: str = typer.Option("", help="Solo Diputados: IdExterno del diputado."),
    Backfill: bool = typer.Option(False, help="Recorre TODOS los registros."),
) -> None:
    import asyncio

    if Camara not in ("Diputados", "Senado"):
        raise typer.BadParameter("--Camara: Diputados o Senado")
    if Legislatura != "LXVI":
        raise typer.BadParameter("--Legislatura solo LXVI")
    if Camara == "Senado" and Diputado:
        raise typer.BadParameter("--Diputado no aplica a Senado; usa --Backfill")
    if Camara == "Senado" and not Backfill:
        raise typer.BadParameter("Senado requiere --Backfill")
    if Camara == "Diputados" and not Diputado and not Backfill:
        raise typer.BadParameter(
            "Pasa --Diputado <Id> O --Backfill (no podemos correr sin saber a quien)"
        )
    if Camara == "Diputados" and Diputado and Backfill:
        raise typer.BadParameter("--Diputado y --Backfill son mutuamente exclusivos")

    from sqlalchemy import select

    from CongresoMx.Database import DisposeEngine, GetSessionMaker
    from CongresoMx.Models import LegisladorPeriodo, Legislatura as LegMod, Sesion
    from CongresoMx.Services.Asistencias import (
        FinalizarScrapingRun,
        IniciarScrapingRun,
        StatsAsistencias,
    )

    Fuente = f"SITL_{Legislatura}" if Camara == "Diputados" else f"SENADO_{Legislatura}"

    async def RunDiputados(SessionMaker, LegislaturaId: int) -> StatsAsistencias:
        from CongresoMx.Scrapers.Diputados.Asistencias import ScraperDiputadosAsistencias
        from CongresoMx.Services.Asistencias import (
            CargarMapaSesiones,
            GuardarAsistenciasDiputado,
            ResolverLegisladorPeriodoId,
        )

        async with SessionMaker() as Sess:
            MapaSesiones = await CargarMapaSesiones(Sess, LegislaturaId)
            if not MapaSesiones:
                raise RuntimeError("No hay Sesiones; corre Scrape Sesiones primero")
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
            Run = await IniciarScrapingRun(
                Sess, Tipo="Asistencias",
                Parametros={"Legislatura": Legislatura, "Camara": "Diputados", "Total": len(IdsExternos)},
            )
            await Sess.commit()
            RunId = Run.Id

        async with ScraperDiputadosAsistencias(Legislatura=Legislatura) as Scraper:
            for Index, IdExterno in enumerate(IdsExternos, start=1):
                Asistencias = await Scraper.ScrapearDiputado(IdExterno)
                async with SessionMaker() as Sess2:
                    LegPerId = await ResolverLegisladorPeriodoId(
                        Sess2, IdExterno, LegislaturaId, Fuente, Camara="Diputados"
                    )
                    if LegPerId is None:
                        Stats.LegPeriodoNoEncontrado += 1
                        continue
                    await GuardarAsistenciasDiputado(
                        Sess2, LegisladorPeriodoId=LegPerId,
                        Asistencias=Asistencias, MapaSesiones=MapaSesiones,
                        Fuente=Fuente, Stats=Stats,
                    )
                    await Sess2.commit()
                if Index % 25 == 0 or Index == len(IdsExternos):
                    logging.getLogger("CongresoMx.Cli").info(
                        "Progreso: %d/%d diputados (nuevas=%d errores=%d)",
                        Index, len(IdsExternos), Stats.Nuevas, Stats.Errores,
                    )
        async with SessionMaker() as Sess3:
            from CongresoMx.Models import ScrapingRun
            RunReload = (await Sess3.execute(
                select(ScrapingRun).where(ScrapingRun.Id == RunId)
            )).scalar_one()
            FinalizarScrapingRun(RunReload, Stats,
                "Success" if Stats.Errores == 0 else "Partial")
            await Sess3.commit()
        return Stats

    async def RunSenado(SessionMaker, LegislaturaId: int) -> StatsAsistencias:
        from collections import defaultdict

        from CongresoMx.Scrapers.Senado.Asistencias import ScraperSenadoAsistencias
        from CongresoMx.Services.Asistencias import (
            CargarMapaLegisladorPeriodoSenado,
            GuardarAsistenciasSesionSenado,
        )

        async with SessionMaker() as Sess:
            MapaLegPer = await CargarMapaLegisladorPeriodoSenado(
                Sess, LegislaturaId, Fuente
            )
            if not MapaLegPer:
                raise RuntimeError(
                    "No hay LegisladorPeriodo Senado; corre Scrape Legisladores --Camara Senado primero"
                )
            # Carga Sesiones del Senado en DB, agrupadas por fecha y ordenadas
            # por Numero. Permite el match por orden secuencial dentro del dia.
            SesionesRows = (
                await Sess.execute(
                    select(Sesion.Id, Sesion.Fecha, Sesion.Numero).where(
                        Sesion.LegislaturaId == LegislaturaId,
                        Sesion.Camara == "Senado",
                        Sesion.Numero.is_not(None),
                    ).order_by(Sesion.Fecha, Sesion.Numero)
                )
            ).all()
            DbPorFecha: dict = defaultdict(list)
            for Sid, Fecha, _Num in SesionesRows:
                DbPorFecha[Fecha].append(Sid)

        async with ScraperSenadoAsistencias(Legislatura=Legislatura) as Scraper:
            # Descubre sesiones con asistencias publicadas (anio 1 y 2)
            Pairs: list[tuple] = []
            for Anio in (1, 2):
                Pairs.extend(await Scraper.ScrapearListadoPorAnio(Anio))
            # Agrupar y ordenar por numero ascendente dentro de cada fecha
            PorFecha: dict = defaultdict(list)
            for Fecha, Num in Pairs:
                PorFecha[Fecha].append(Num)
            for Fecha in PorFecha:
                PorFecha[Fecha].sort(key=lambda N: int(N))
            # Reconstruir lista ordenada por fecha asc + numero asc
            PairsOrdered: list[tuple] = []
            for Fecha in sorted(PorFecha):
                for Num in PorFecha[Fecha]:
                    PairsOrdered.append((Fecha, Num))

            typer.echo(f"Sesiones Senado con asistencias publicadas: {len(PairsOrdered)}")

            async with SessionMaker() as Sess:
                Stats = StatsAsistencias()
                Run = await IniciarScrapingRun(
                    Sess, Tipo="Asistencias",
                    Parametros={
                        "Legislatura": Legislatura,
                        "Camara": "Senado",
                        "Total": len(PairsOrdered),
                    },
                )
                await Sess.commit()
                RunId = Run.Id

            # Indice usado dentro de cada fecha para resolver SesionId
            IndicePorFecha: dict = defaultdict(int)
            for Index, (Fecha, Num) in enumerate(PairsOrdered, start=1):
                DbSids = DbPorFecha.get(Fecha, [])
                Idx = IndicePorFecha[Fecha]
                IndicePorFecha[Fecha] += 1
                if Idx >= len(DbSids):
                    logging.getLogger("CongresoMx.Cli").warning(
                        "Sesion (%s, num=%s) sin Sesion correspondiente en DB; skip",
                        Fecha, Num,
                    )
                    Stats.SesionNoEncontrada += 1
                    continue
                SesionId = DbSids[Idx]
                try:
                    Crudas = await Scraper.ScrapearSesion(Fecha, Num)
                except Exception as Exc:
                    logging.getLogger("CongresoMx.Cli").error(
                        "Error scrape sesion %s/%s: %s", Fecha, Num, Exc,
                    )
                    Stats.Errores += 1
                    continue
                async with SessionMaker() as Sess2:
                    await GuardarAsistenciasSesionSenado(
                        Sess2, SesionId=SesionId,
                        AsistenciasCrudas=Crudas, MapaLegisladorPeriodo=MapaLegPer,
                        Fuente=Fuente, Stats=Stats,
                    )
                    await Sess2.commit()
                if Index % 25 == 0 or Index == len(PairsOrdered):
                    logging.getLogger("CongresoMx.Cli").info(
                        "Progreso: %d/%d sesiones (nuevas=%d errores=%d)",
                        Index, len(PairsOrdered), Stats.Nuevas, Stats.Errores,
                    )

        async with SessionMaker() as Sess3:
            from CongresoMx.Models import ScrapingRun
            RunReload = (await Sess3.execute(
                select(ScrapingRun).where(ScrapingRun.Id == RunId)
            )).scalar_one()
            FinalizarScrapingRun(RunReload, Stats,
                "Success" if Stats.Errores == 0 else "Partial")
            await Sess3.commit()
        return Stats

    async def Run() -> None:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        SessionMaker = GetSessionMaker()
        async with SessionMaker() as Sess0:
            LegRow = (
                await Sess0.execute(select(LegMod).where(LegMod.Numero == Legislatura))
            ).scalar_one_or_none()
            if LegRow is None:
                raise RuntimeError(f"Legislatura {Legislatura} no esta en DB")
            LegislaturaId = LegRow.Id

        if Camara == "Diputados":
            Stats = await RunDiputados(SessionMaker, LegislaturaId)
        else:
            Stats = await RunSenado(SessionMaker, LegislaturaId)

        typer.echo("")
        typer.echo(f"Camara:                       {Camara}")
        typer.echo(f"Asistencias nuevas:           {Stats.Nuevas}")
        typer.echo(f"Asistencias actualizadas:     {Stats.Actualizadas}")
        typer.echo(f"Cambios de estado detectados: {Stats.Cambios}")
        typer.echo(f"Codigos desconocidos:         {Stats.CodigosDesconocidos}")
        typer.echo(f"Sesion no encontrada:         {Stats.SesionNoEncontrada}")
        typer.echo(f"LegPeriodo no encontrado:     {Stats.LegPeriodoNoEncontrado}")
        typer.echo(f"Errores:                      {Stats.Errores}")
        await DisposeEngine()

    asyncio.run(Run())


# Helper: corre seed catalogos. Reusa Scripts/SeedCatalogos.Run() (async).
# Scripts/ no esta en el paquete instalado; lo agregamos a sys.path al vuelo.
async def _BackfillSeed() -> dict:
    import sys
    from pathlib import Path
    ProjectRoot = Path(__file__).resolve().parents[2]
    if str(ProjectRoot) not in sys.path:
        sys.path.insert(0, str(ProjectRoot))
    from Scripts.SeedCatalogos import Run as SeedRun
    await SeedRun()
    return {"status": "OK"}


# Helper: corre el scrape de Legisladores para una camara.
async def _BackfillLegisladores(Camara: str, Legislatura: str) -> dict:
    from CongresoMx.Database import GetSessionMaker
    from CongresoMx.Services.Legisladores import GuardarBatch

    if Camara == "Diputados":
        from CongresoMx.Scrapers.Diputados.Legisladores import (
            ScraperDiputadosLegisladores,
        )
        async with ScraperDiputadosLegisladores(Legislatura=Legislatura) as Scraper:
            Mergeados = await Scraper.ScrapearLegislatura(Limit=None)
    else:
        from CongresoMx.Scrapers.Senado.Legisladores import ScraperSenadoLegisladores
        async with ScraperSenadoLegisladores(Legislatura=Legislatura) as Scraper:
            Mergeados = await Scraper.ScrapearLegislatura(Limit=None)

    SM = GetSessionMaker()
    async with SM() as Sess:
        Stats = await GuardarBatch(
            Sess, Mergeados, NumeroLegislatura=Legislatura, Camara=Camara
        )
        await Sess.commit()
    return {
        "Total": len(Mergeados),
        "Nuevos": Stats.Nuevos,
        "Actualizados": Stats.Actualizados,
        "Errores": Stats.Errores,
    }


# Helper: corre el scrape de Sesiones para una camara.
async def _BackfillSesiones(Camara: str, Legislatura: str) -> dict:
    from CongresoMx.Database import GetSessionMaker

    SM = GetSessionMaker()
    if Camara == "Diputados":
        from CongresoMx.Scrapers.Diputados.Sesiones import ScraperDiputadosSesiones
        from CongresoMx.Services.Sesiones import GuardarBatchSesiones
        async with ScraperDiputadosSesiones(Legislatura=Legislatura) as Scraper:
            Sesiones = await Scraper.ScrapearCalendarioCompleto()
        async with SM() as Sess:
            Stats = await GuardarBatchSesiones(
                Sess, Sesiones, NumeroLegislatura=Legislatura
            )
            await Sess.commit()
    else:
        from CongresoMx.Scrapers.Senado.Sesiones import ScraperSenadoSesiones
        from CongresoMx.Services.Sesiones import GuardarBatchSesionesSenado
        async with ScraperSenadoSesiones(Legislatura=Legislatura) as Scraper:
            Sesiones = await Scraper.ScrapearSesiones()
        async with SM() as Sess:
            Stats = await GuardarBatchSesionesSenado(
                Sess, Sesiones, NumeroLegislatura=Legislatura
            )
            await Sess.commit()
    return {
        "Total": len(Sesiones),
        "Nuevas": Stats.Nuevas,
        "Actualizadas": Stats.Actualizadas,
        "Errores": Stats.Errores,
    }


# Helper: corre el backfill de Asistencias para una camara.
# Internamente reusa la logica RunDiputados/RunSenado del comando Scrape.
async def _BackfillAsistencias(Camara: str, Legislatura: str) -> dict:
    from sqlalchemy import select

    from CongresoMx.Database import GetSessionMaker
    from CongresoMx.Models import Legislatura as LegMod

    SM = GetSessionMaker()
    async with SM() as Sess0:
        LegRow = (
            await Sess0.execute(select(LegMod).where(LegMod.Numero == Legislatura))
        ).scalar_one_or_none()
        if LegRow is None:
            raise RuntimeError(f"Legislatura {Legislatura} no esta en DB")
        LegislaturaId = LegRow.Id

    # Reutilizamos las closures del comando ScrapeAsistencias via importacion
    # del estado: en esta version delegamos a subprocess via congresomx CLI.
    # Mas simple: replicamos la logica minima aqui sin closures.
    Fuente = (
        f"SITL_{Legislatura}" if Camara == "Diputados" else f"SENADO_{Legislatura}"
    )
    from CongresoMx.Services.Asistencias import (
        FinalizarScrapingRun,
        IniciarScrapingRun,
        StatsAsistencias,
    )

    if Camara == "Diputados":
        from CongresoMx.Models import LegisladorPeriodo, ScrapingRun
        from CongresoMx.Scrapers.Diputados.Asistencias import (
            ScraperDiputadosAsistencias,
        )
        from CongresoMx.Services.Asistencias import (
            CargarMapaSesiones,
            GuardarAsistenciasDiputado,
            ResolverLegisladorPeriodoId,
        )

        async with SM() as Sess:
            MapaSesiones = await CargarMapaSesiones(Sess, LegislaturaId)
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
            Stats = StatsAsistencias()
            Run = await IniciarScrapingRun(
                Sess, Tipo="Asistencias",
                Parametros={"Legislatura": Legislatura, "Camara": "Diputados", "Total": len(IdsExternos)},
            )
            await Sess.commit()
            RunId = Run.Id

        async with ScraperDiputadosAsistencias(Legislatura=Legislatura) as Scraper:
            for Index, IdExterno in enumerate(IdsExternos, start=1):
                Asistencias = await Scraper.ScrapearDiputado(IdExterno)
                async with SM() as Sess2:
                    LegPerId = await ResolverLegisladorPeriodoId(
                        Sess2, IdExterno, LegislaturaId, Fuente, Camara="Diputados"
                    )
                    if LegPerId is None:
                        Stats.LegPeriodoNoEncontrado += 1
                        continue
                    await GuardarAsistenciasDiputado(
                        Sess2, LegisladorPeriodoId=LegPerId,
                        Asistencias=Asistencias, MapaSesiones=MapaSesiones,
                        Fuente=Fuente, Stats=Stats,
                    )
                    await Sess2.commit()
                if Index % 50 == 0 or Index == len(IdsExternos):
                    logging.getLogger("CongresoMx.Backfill").info(
                        "Asistencias Diputados: %d/%d (nuevas=%d errores=%d)",
                        Index, len(IdsExternos), Stats.Nuevas, Stats.Errores,
                    )

        async with SM() as Sess3:
            RunReload = (
                await Sess3.execute(select(ScrapingRun).where(ScrapingRun.Id == RunId))
            ).scalar_one()
            FinalizarScrapingRun(
                RunReload, Stats, "Success" if Stats.Errores == 0 else "Partial"
            )
            await Sess3.commit()
    else:
        from collections import defaultdict

        from CongresoMx.Models import ScrapingRun, Sesion
        from CongresoMx.Scrapers.Senado.Asistencias import ScraperSenadoAsistencias
        from CongresoMx.Services.Asistencias import (
            CargarMapaLegisladorPeriodoSenado,
            GuardarAsistenciasSesionSenado,
        )

        async with SM() as Sess:
            MapaLegPer = await CargarMapaLegisladorPeriodoSenado(
                Sess, LegislaturaId, Fuente
            )
            SesionesRows = (
                await Sess.execute(
                    select(Sesion.Id, Sesion.Fecha, Sesion.Numero).where(
                        Sesion.LegislaturaId == LegislaturaId,
                        Sesion.Camara == "Senado",
                        Sesion.Numero.is_not(None),
                    ).order_by(Sesion.Fecha, Sesion.Numero)
                )
            ).all()
            DbPorFecha: dict = defaultdict(list)
            for Sid, Fecha, _Num in SesionesRows:
                DbPorFecha[Fecha].append(Sid)

        async with ScraperSenadoAsistencias(Legislatura=Legislatura) as Scraper:
            Pairs: list[tuple] = []
            for Anio in (1, 2):
                Pairs.extend(await Scraper.ScrapearListadoPorAnio(Anio))
            PorFecha: dict = defaultdict(list)
            for Fecha, Num in Pairs:
                PorFecha[Fecha].append(Num)
            for Fecha in PorFecha:
                PorFecha[Fecha].sort(key=lambda N: int(N))
            PairsOrdered: list[tuple] = []
            for Fecha in sorted(PorFecha):
                for Num in PorFecha[Fecha]:
                    PairsOrdered.append((Fecha, Num))

            async with SM() as Sess:
                Stats = StatsAsistencias()
                Run = await IniciarScrapingRun(
                    Sess, Tipo="Asistencias",
                    Parametros={"Legislatura": Legislatura, "Camara": "Senado", "Total": len(PairsOrdered)},
                )
                await Sess.commit()
                RunId = Run.Id

            IndicePorFecha: dict = defaultdict(int)
            for Index, (Fecha, Num) in enumerate(PairsOrdered, start=1):
                DbSids = DbPorFecha.get(Fecha, [])
                Idx = IndicePorFecha[Fecha]
                IndicePorFecha[Fecha] += 1
                if Idx >= len(DbSids):
                    Stats.SesionNoEncontrada += 1
                    continue
                SesionId = DbSids[Idx]
                try:
                    Crudas = await Scraper.ScrapearSesion(Fecha, Num)
                except Exception:
                    Stats.Errores += 1
                    continue
                async with SM() as Sess2:
                    await GuardarAsistenciasSesionSenado(
                        Sess2, SesionId=SesionId,
                        AsistenciasCrudas=Crudas, MapaLegisladorPeriodo=MapaLegPer,
                        Fuente=Fuente, Stats=Stats,
                    )
                    await Sess2.commit()
                if Index % 25 == 0 or Index == len(PairsOrdered):
                    logging.getLogger("CongresoMx.Backfill").info(
                        "Asistencias Senado: %d/%d (nuevas=%d errores=%d)",
                        Index, len(PairsOrdered), Stats.Nuevas, Stats.Errores,
                    )

        async with SM() as Sess3:
            RunReload = (
                await Sess3.execute(select(ScrapingRun).where(ScrapingRun.Id == RunId))
            ).scalar_one()
            FinalizarScrapingRun(
                RunReload, Stats, "Success" if Stats.Errores == 0 else "Partial"
            )
            await Sess3.commit()

    return {
        "Nuevas": Stats.Nuevas,
        "Actualizadas": Stats.Actualizadas,
        "CodigosDesconocidos": Stats.CodigosDesconocidos,
        "Errores": Stats.Errores,
    }


# Orquestador: corre seed + scrapers en orden. Tolera errores parciales
# (loguea y sigue). Idempotente: re-correr no duplica nada.
@App.command(name="Backfill")
def Backfill(
    Legislatura: str = typer.Option("LXVI", help="Legislatura: LXVI."),
    Camara: str = typer.Option("Ambas", help="Diputados | Senado | Ambas."),
    Hasta: str = typer.Option(
        "Asistencias", help="Seed | Legisladores | Sesiones | Asistencias."
    ),
) -> None:
    import asyncio
    import time

    if Legislatura != "LXVI":
        raise typer.BadParameter("Solo LXVI por ahora (LXV es trabajo pendiente)")
    if Camara not in ("Diputados", "Senado", "Ambas"):
        raise typer.BadParameter("--Camara: Diputados | Senado | Ambas")
    if Hasta not in ("Seed", "Legisladores", "Sesiones", "Asistencias"):
        raise typer.BadParameter("--Hasta: Seed | Legisladores | Sesiones | Asistencias")

    Camaras = ["Diputados", "Senado"] if Camara == "Ambas" else [Camara]
    Orden = ["Seed", "Legisladores", "Sesiones", "Asistencias"]
    Hasta_Idx = Orden.index(Hasta)
    Etapas = Orden[: Hasta_Idx + 1]

    Log = logging.getLogger("CongresoMx.Backfill")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    async def Run() -> None:
        from CongresoMx.Database import DisposeEngine, GetSessionMaker

        Inicio = time.monotonic()
        Resultados: dict[str, tuple[str, float, dict | str]] = {}

        # Seed
        if "Seed" in Etapas:
            Log.info("== Seed catalogos ==")
            T0 = time.monotonic()
            try:
                Res = await _BackfillSeed()
                Resultados["Seed"] = ("OK", time.monotonic() - T0, Res)
            except Exception as Exc:
                Log.error("Seed fallo: %s", Exc, exc_info=True)
                Resultados["Seed"] = ("FAIL", time.monotonic() - T0, str(Exc))

        # Legisladores / Sesiones / Asistencias por camara
        Helpers = {
            "Legisladores": _BackfillLegisladores,
            "Sesiones": _BackfillSesiones,
            "Asistencias": _BackfillAsistencias,
        }
        for Etapa in ("Legisladores", "Sesiones", "Asistencias"):
            if Etapa not in Etapas:
                continue
            for Cam in Camaras:
                Nombre = f"{Cam} {Etapa}"
                Log.info("== %s ==", Nombre)
                T0 = time.monotonic()
                try:
                    Res = await Helpers[Etapa](Cam, Legislatura)
                    Resultados[Nombre] = ("OK", time.monotonic() - T0, Res)
                except Exception as Exc:
                    Log.error("%s fallo: %s", Nombre, Exc, exc_info=True)
                    Resultados[Nombre] = ("FAIL", time.monotonic() - T0, str(Exc))

        Total = time.monotonic() - Inicio

        # Reporte
        typer.echo("")
        typer.echo("== Resumen Backfill ==")
        typer.echo(f"Tiempo total: {Total/60:.1f} min")
        typer.echo("")
        for Etapa, (Status, Dur, Info) in Resultados.items():
            Sufijo = f" {Info}" if isinstance(Info, dict) else ""
            typer.echo(f"  [{Status:<4}] {Dur:>6.1f}s  {Etapa}{Sufijo}")

        # Counts finales
        SM = GetSessionMaker()
        async with SM() as Sess:
            from sqlalchemy import func, select as sa_select

            from CongresoMx.Models import (
                Asistencia, Legislador, LegisladorPeriodo, Sesion,
            )

            CountLeg = (await Sess.execute(sa_select(func.count(Legislador.Id)))).scalar_one()
            CountLP = (await Sess.execute(sa_select(func.count(LegisladorPeriodo.Id)))).scalar_one()
            CountSes = (await Sess.execute(sa_select(func.count(Sesion.Id)))).scalar_one()
            CountAsi = (await Sess.execute(sa_select(func.count(Asistencia.Id)))).scalar_one()

        typer.echo("")
        typer.echo("== Counts finales en DB ==")
        typer.echo(f"  Legisladores:      {CountLeg:>7}")
        typer.echo(f"  LegisladorPeriodo: {CountLP:>7}")
        typer.echo(f"  Sesiones:          {CountSes:>7}")
        typer.echo(f"  Asistencias:       {CountAsi:>7}")

        # Query bonus: top 10 diputados con mas inasistencias en LXVI
        if "Asistencias" in Etapas:
            from sqlalchemy import text
            async with SM() as Sess:
                Rows = (
                    await Sess.execute(
                        text(
                            "SELECT l.NombreCompleto, p.Siglas AS Partido, "
                            "  e.Nombre AS Estado, COUNT(*) AS Ausencias "
                            "FROM Asistencias a "
                            "JOIN LegisladorPeriodo lp ON lp.Id=a.LegisladorPeriodoId "
                            "JOIN Legisladores l ON l.Id=lp.LegisladorId "
                            "LEFT JOIN Partidos p ON p.Id=lp.PartidoId "
                            "LEFT JOIN Estados e ON e.Id=lp.EstadoId "
                            "WHERE a.Estado='Ausente' AND lp.Camara='Diputados' "
                            "  AND lp.LegislaturaId=2 "
                            "GROUP BY l.Id ORDER BY Ausencias DESC LIMIT 10"
                        )
                    )
                ).all()
            typer.echo("")
            typer.echo("== Top 10 diputados con mas inasistencias (Ausente) en LXVI ==")
            for Nombre, Partido, Estado, N in Rows:
                typer.echo(f"  {N:>3}  {Partido or '-':<8}  {Estado or '-':<22}  {Nombre}")

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
