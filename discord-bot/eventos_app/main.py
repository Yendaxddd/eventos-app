"""Entry point of the desktop app (`EventosApp.exe` / `python -m eventos_app`)."""

from __future__ import annotations

import argparse
import json
import logging
import logging.handlers
import os
import sys
import time

from . import APP_NAME, __version__, paths


def _fix_stdio() -> None:
    """A windowed (no console) build has sys.stdout/sys.stderr == None; anything
    that prints or writes there would crash. Point them at a log file instead."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    stream = open(paths.logs_dir() / "stdio.log", "a", encoding="utf-8", buffering=1)
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream


def _setup_logging() -> None:
    handler = logging.handlers.RotatingFileHandler(
        paths.logs_dir() / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"))
    log = logging.getLogger("eventos_app")
    log.setLevel(logging.INFO)
    log.addHandler(handler)

    def excepthook(exc_type, exc, tb):
        log.critical("unhandled exception", exc_info=(exc_type, exc, tb))

    sys.excepthook = excepthook


def activity_check() -> dict:
    """The Activity inside the build: the web client is bundled and the local server really serves it."""
    import asyncio
    import urllib.request

    from . import activity

    web = paths.resource_path("eventos_app", "activity", "web")
    result = {"activity_client_bundled": all((web / name).is_file() for name in ("index.html", "app.js", "app.css"))}

    async def serve() -> bool:
        server = activity.ActivityServer(activity.Hub(), auth=activity.DiscordAuth(client_id=1, client_secret=""),
                                         authorize=None, web_dir=web, client_id=1, port=0)
        port = await server.start()
        try:
            def fetch() -> tuple[bool, bool]:
                base = f"http://127.0.0.1:{port}"
                with urllib.request.urlopen(f"{base}/healthz", timeout=5) as health, \
                        urllib.request.urlopen(f"{base}/app.js", timeout=5) as script:
                    return b'"ok"' in health.read(), len(script.read()) > 10_000
            health, script = await asyncio.get_running_loop().run_in_executor(None, fetch)
            return health and script
        finally:
            await server.stop()

    result["activity_server"] = asyncio.run(serve())
    return result


def _smoke_test(out_path: str | None) -> int:
    """Open the window, import the whole bot and try a (bad-token) login, then exit.

    Used by CI to prove that a freshly built .exe really starts: all modules and
    resources are bundled, and the bot can be created and run. Result goes to a
    JSON file because a windowed build has no console to print to.
    """
    from .runner import State
    from .settings import Settings
    from .ui import App

    report: dict = {"app": APP_NAME, "version": __version__, "frozen": paths.is_frozen(),
                    "home": str(paths.app_home()), "checks": {}}
    checks = report["checks"]
    try:
        app = App()
        app.update()
        checks["window"] = bool(app.winfo_exists())
        checks["icon"] = paths.resource_path("eventos_app", "resources", "icon.png").exists()
        checks["assets"] = any(paths.assets_dir().glob("*.gif"))
        checks["data"] = any(paths.data_dir().glob("*.json"))

        picker = app.config_page.player_picker  # the searchable dropdown used for servers, channels and roles
        picker.set_enabled(True)
        picker.set_items([(1, "@Jugadores", ""), (2, "@Staff", "")])
        picker.open()
        app.update()
        picker._query.set("sta")
        app.update()
        checks["picker_popup"] = [row[1] for row in picker._visible] == ["@Staff"]
        picker.close()
        app.update()
        checks.update(activity_check())

        # Starts the bot with an invalid token: it must get as far as talking to Discord
        # and be refused (or fail to connect), not crash while loading its own code.
        runner = app.runner
        runner.start(Settings(discord_token="smoke-test-invalid-token", hotkeys_enabled=False))
        deadline = time.time() + 60
        while runner.state in (State.STARTING, State.CONNECTED) and time.time() < deadline:
            app.update()
            time.sleep(0.05)
        report["bot_result"] = runner.error
        checks["bot_login_attempt"] = runner.state is State.ERROR and (
            "token" in runner.error.lower() or "conectar" in runner.error.lower())
        app.update()
        app.destroy()
    except Exception as exc:  # noqa: BLE001
        logging.getLogger("eventos_app").exception("smoke test failed")
        report["exception"] = f"{type(exc).__name__}: {exc}"
    report["ok"] = bool(report["checks"]) and all(report["checks"].values()) and "exception" not in report

    target = out_path or str(paths.logs_dir() / "smoke_test.json")
    with open(target, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    return 0 if report["ok"] else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=APP_NAME)
    parser.add_argument("--version", action="store_true", help="print the version and exit")
    parser.add_argument("--smoke-test", action="store_true", help="start, self-check and exit (used by CI)")
    parser.add_argument("--smoke-out", help="where --smoke-test writes its JSON report")
    args = parser.parse_args(argv)

    os.chdir(paths.app_home())  # the bot uses a few paths relative to the working directory
    _fix_stdio()
    if args.version:
        print(f"{APP_NAME} {__version__}")
        return 0
    paths.seed_defaults()
    _setup_logging()
    logging.getLogger("eventos_app").info("%s %s starting (home=%s)", APP_NAME, __version__, paths.app_home())

    if args.smoke_test:
        return _smoke_test(args.smoke_out)

    from .ui import App

    App().mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
