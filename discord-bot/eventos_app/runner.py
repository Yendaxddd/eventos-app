"""Runs the Discord bot on a background thread with its own asyncio loop, so the
window stays responsive, and lets the UI start / stop / poke it safely.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import os
import threading
from enum import Enum

from . import console_bridge
from .settings import Settings

log = logging.getLogger("eventos_app")

BOT_MODULE = "advanced_qte_hp_system_debug"
STOP_TIMEOUT_SECONDS = 15


class State(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    CONNECTED = "connected"  # logged in and ready
    STOPPING = "stopping"
    ERROR = "error"


def friendly_error(exc: BaseException) -> str:
    """Turn the usual discord.py failures into something a person can act on."""
    import discord

    if isinstance(exc, discord.LoginFailure):
        return "Discord rechazó el token. Revisa que lo copiaste completo en Configuración."
    if isinstance(exc, discord.PrivilegedIntentsRequired):
        return (
            "Faltan permisos en el Developer Portal. Activa «Message Content Intent» y "
            "«Server Members Intent» en la pestaña Bot de tu aplicación y vuelve a iniciar."
        )
    if isinstance(exc, discord.ConnectionClosed):
        return f"Discord cerró la conexión ({exc})."
    if isinstance(exc, OSError):
        return f"No se pudo conectar a Discord. ¿Hay internet? ({exc})"
    return f"{type(exc).__name__}: {exc}"


class BotRunner:
    def __init__(self, sink: console_bridge.Sink | None = None) -> None:
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._app = None  # AdvancedQTEBot
        self._state = State.STOPPED
        self._error = ""
        self._lock = threading.Lock()
        if sink is not None:
            console_bridge.console.set_sink(sink)

    # ---- state the UI reads -------------------------------------------------
    @property
    def state(self) -> State:
        with self._lock:
            state = self._state
        if state is State.STARTING and self._is_ready():
            return State.CONNECTED
        return state

    @property
    def error(self) -> str:
        return self._error

    def _set(self, state: State, error: str = "") -> None:
        with self._lock:
            self._state = state
            self._error = error

    def _is_ready(self) -> bool:
        app = self._app
        try:
            return bool(app is not None and app.bot.is_ready())
        except Exception:
            return False

    def describe_connection(self) -> str:
        """e.g. 'EventBot#1234 · 3 servidores' once connected."""
        app = self._app
        if app is None or not self._is_ready():
            return ""
        try:
            n = len(app.bot.guilds)
            return f"{app.bot.user} · {n} servidor{'es' if n != 1 else ''}"
        except Exception:
            return ""

    def is_active(self) -> bool:
        return self.state in (State.STARTING, State.CONNECTED, State.STOPPING)

    # ---- actions ------------------------------------------------------------
    def start(self, settings: Settings) -> None:
        if self.is_active():
            return
        if not settings.discord_token.strip():
            self._set(State.ERROR, "Falta el token del bot. Pégalo en Configuración.")
            return
        self._set(State.STARTING)
        self._thread = threading.Thread(
            target=self._thread_main, args=(settings,), name="discord-bot", daemon=True
        )
        self._thread.start()

    def stop(self, wait: float = 0) -> None:
        """Ask the bot to close. With wait > 0, block up to that many seconds."""
        thread = self._thread
        if thread is None or not thread.is_alive():
            return
        self._set(State.STOPPING)
        loop, app = self._loop, self._app
        if loop is not None and app is not None and not loop.is_closed():
            asyncio.run_coroutine_threadsafe(app.bot.close(), loop)
        if wait:
            thread.join(wait)

    def run_action(self, name: str) -> bool:
        """Run one of the bot's quick actions (the same ones the hotkeys trigger)."""
        app = self._app
        if app is None or not self._is_ready():
            return False
        action = getattr(app, "quick_actions", {}).get(name)
        if action is None:
            return False
        try:
            action()
        except Exception as exc:
            console_bridge.console.print(f"[red]✗ No se pudo ejecutar «{name}»: {exc}[/red]")
            log.exception("quick action %s failed", name)
            return False
        return True

    def action_label(self, name: str) -> str:
        """Hotkey bound to an action, for button captions ('' if unknown)."""
        app = self._app
        return getattr(app, "keybinds", {}).get(name, "") if app else ""

    # ---- worker thread ------------------------------------------------------
    def _thread_main(self, settings: Settings) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        error = ""
        try:
            os.environ.update(settings.to_env())
            module = importlib.import_module(BOT_MODULE)
            self._app = module.AdvancedQTEBot()
            loop.run_until_complete(self._serve(settings.discord_token.strip()))
        except BaseException as exc:  # noqa: BLE001 - everything must reach the UI
            error = friendly_error(exc)
            log.exception("bot stopped with an error")
            console_bridge.console.print(f"[red]✗ {error}[/red]")
        finally:
            self._cleanup(loop)
            self._app = None
            self._loop = None
            if error:
                self._set(State.ERROR, error)
            else:
                self._set(State.STOPPED)

    async def _serve(self, token: str) -> None:
        bot = self._app.bot
        try:
            async with bot:
                await bot.start(token)
        finally:
            if not bot.is_closed():
                await bot.close()

    def _cleanup(self, loop: asyncio.AbstractEventLoop) -> None:
        app = self._app
        if app is not None:
            for step in (app.teardown_hotkeys, lambda: app.save_all_data(force=True)):
                try:
                    step()
                except Exception:
                    log.exception("cleanup step failed")
        try:
            pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            log.exception("loop cleanup failed")
        finally:
            loop.close()
            console_bridge.console.print("[yellow]Bot detenido.[/yellow]")
