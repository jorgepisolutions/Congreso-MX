import logging

import typer

from CongresoMx.Config import GetSettings

App = typer.Typer(
    name="CongresoMx",
    help="ETL del Congreso de la Union de Mexico.",
    no_args_is_help=True,
)

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


# Entrypoint para `python -m CongresoMx.Cli` o el script `congresomx`.
def Main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    App()


if __name__ == "__main__":
    Main()
