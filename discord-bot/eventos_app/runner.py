"""Runs the Discord bot on a background thread with its own asyncio loop, so the
window stays responsive, and lets the UI start / stop / poke it safely.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import importlib
import json
import logging
import os
import threading
import time
import types
from enum import Enum
from typing import Awaitable, Callable

import discord

from rich.markup import escape as markup_escape

from . import activity, backups, benchmark, browser, console_bridge, diagnostics, i18n, multibot, paths, snapshot, webhooks
from .settings import Settings

log = logging.getLogger("eventos_app")

BOT_MODULE = "advanced_qte_hp_system_debug"
STOP_TIMEOUT_SECONDS = 15
# actions that need the event channel to be set up
NEEDS_CHANNEL = {"single_easy", "single_medium", "single_hard", "single_impossible", "group_easy",
                 "group_medium", "group_hard", "group_impossible", "checkpoint"}


class State(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    CONNECTED = "connected"  # logged in and ready
    STOPPING = "stopping"
    ERROR = "error"


def friendly_error(exc: BaseException) -> str:
    """Turn the usual discord.py failures into something a person can act on."""
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


def describe_discord_error(exc: BaseException) -> str:
    """Short Spanish text for errors while configuring the event."""
    if isinstance(exc, discord.Forbidden):
        return ("El bot no tiene permisos en ese canal. Necesita «Enviar mensajes» y «Gestionar hilos» "
                "(para crear el hilo de barras de HP).")
    if isinstance(exc, discord.NotFound):
        return "Ese canal o rol ya no existe."
    return f"{type(exc).__name__}: {exc}"


class BotRunner:
    def __init__(self, sink: console_bridge.Sink | None = None) -> None:
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._app = None  # AdvancedQTEBot
        self._pool: multibot.SenderPool | None = None
        self._bench_stop: asyncio.Event | None = None
        self._last_429: dict[tuple[str, str], float] = {}
        self._activity = None                      # the running Discord Activity (see eventos_app/activity)
        self._activity_task: asyncio.Task | None = None
        self._helper_errors: dict[str, str] = {}  # helper token -> why it could not be added
        self._base_interval = 0.15
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
            text = f"{app.bot.user} · {n} servidor{'es' if n != 1 else ''}"
            helpers = self.helpers_online()
            if helpers:
                text += f" · {helpers} bot{'s' if helpers != 1 else ''} auxiliar{'es' if helpers != 1 else ''}"
            return text
        except Exception:
            return ""

    def is_active(self) -> bool:
        return self.state in (State.STARTING, State.CONNECTED, State.STOPPING)

    def main_bot_id(self) -> int:
        app = self._app
        try:
            return app.bot.user.id if app is not None and app.bot.user else 0
        except Exception:
            return 0

    def event_ready(self) -> bool:
        """Is there an event channel the bot can see?"""
        app = self._app
        try:
            return bool(app is not None and self._is_ready() and app.qte_channel_id and app.bot.get_channel(app.qte_channel_id) is not None)
        except Exception:  # noqa: BLE001
            return False

    def event_line(self) -> str:
        """One line about the configured event for the panel ('' when not connected)."""
        app = self._app
        if app is None or not self._is_ready():
            return ""
        try:
            channel = app.bot.get_channel(app.qte_channel_id) if app.qte_channel_id else None
            if channel is not None:
                return f"Evento: {channel.guild.name} › #{channel.name}"
            return "⚠ Aún no hay un canal de evento: elígelo en Configuración."
        except Exception:
            return ""

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
        if name in NEEDS_CHANNEL and not app.bot.get_channel(app.qte_channel_id):
            console_bridge.console.print(
                "[yellow]⚠ Primero elige el servidor y el canal del evento en Configuración "
                "(o usa /setchannel en Discord).[/yellow]")
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

    # ---- talking to the bot's event loop ---------------------------------------
    def submit(self, make_coro: Callable[[], Awaitable]) -> concurrent.futures.Future:
        """Run a coroutine on the bot's loop; the result is read from the returned Future."""
        loop = self._loop
        if loop is None or loop.is_closed() or not self._is_ready():
            raise RuntimeError("El bot no está conectado.")
        return asyncio.run_coroutine_threadsafe(make_coro(), loop)

    async def _servers_snapshot(self) -> dict:
        """Servers, text channels and roles the bot can see, plus the current event configuration."""
        app = self._app
        guilds = []
        for guild in sorted(app.bot.guilds, key=lambda g: g.name.lower()):
            me = guild.me
            channels = []
            for channel in guild.text_channels:
                perms = channel.permissions_for(me) if me is not None else None
                if perms is None or (perms.view_channel and perms.send_messages):
                    channels.append({"id": channel.id, "name": channel.name,
                                     "group": channel.category.name if channel.category else ""})
            roles = [{"id": r.id, "name": r.name} for r in sorted(guild.roles, key=lambda r: -r.position)
                     if not r.is_default() and not r.managed]
            guilds.append({"id": guild.id, "name": guild.name, "channels": channels, "roles": roles})
        resolved = app.resolve_event_guild()
        return {
            "guilds": guilds,
            "current": {
                "guild_id": resolved.id if resolved else 0,
                "channel_id": app.qte_channel_id,
                "thread_id": app.hp_bar_thread_id,
                "player_role_id": app.qte_player_role_id,
                "admin_role_id": app.admin_role_id,
            },
        }

    def load_servers(self) -> concurrent.futures.Future:
        return self.submit(self._servers_snapshot)

    async def _apply_event(self, channel_id: int, player_role_id: int | None, admin_role_id: int | None) -> dict:
        app = self._app
        channel = app.bot.get_channel(channel_id)
        if channel is None:
            return {"ok": False, "error": "El bot ya no ve ese canal."}
        try:
            result = await app.configure_event(channel, player_role_id=player_role_id, admin_role_id=admin_role_id)
        except (discord.Forbidden, discord.NotFound, discord.HTTPException) as exc:
            return {"ok": False, "error": describe_discord_error(exc)}
        app.print_config_check()
        console_bridge.console.print(f"[green]✓ Evento configurado en #{channel.name} ({channel.guild.name})[/green]")
        if self._pool is not None:
            self._pool.sticky_channels = {app.hp_bar_thread_id} if app.hp_bar_thread_id else set()
            await self._pool.check_access(channel_id)
            await self._sync_lanes()          # a new channel: every bot registers its one webhook there
            if self._activity is not None:
                await self._activity.bridge.announce_channel()
        return {"ok": True, "thread": result["thread"].name, "created": result["created"]}

    def apply_event(self, channel_id: int, player_role_id: int | None = None,
                    admin_role_id: int | None = None) -> concurrent.futures.Future:
        """Point the event at a channel (creating the HP thread if needed) and set the roles."""
        return self.submit(lambda: self._apply_event(channel_id, player_role_id, admin_role_id))

    # ---- helper bots (several accounts sharing the sending load) ----------------
    def helpers_online(self) -> int:
        return len(self._pool.helpers) if self._pool else 0

    def helper_info(self, token: str) -> dict:
        """State of one configured helper: {'state': 'idle'|'ok'|'error', 'error': str, 'sender': dict|None}."""
        token = token.strip()
        if token in self._helper_errors:
            return {"state": "error", "error": self._helper_errors[token], "sender": None}
        pool = self._pool
        if pool is not None:
            for sender in pool.helpers:
                if sender.client is not None and sender.client.http.token == token:
                    return {"state": "ok", "error": "", "sender": sender.snapshot()}
        return {"state": "idle", "error": "", "sender": None}

    async def _add_helper(self, token: str) -> str:
        """Returns '' on success or an error message."""
        pool = self._pool
        if pool is None:
            return "El bot principal todavía no está listo."
        self._helper_errors.pop(token, None)
        try:
            sender = await pool.add_helper(token)
        except discord.LoginFailure:
            message = "Discord rechazó este token."
        except ValueError as exc:
            message = str(exc)
        except Exception as exc:  # noqa: BLE001 - one bad helper must never stop the main bot
            message = f"No se pudo conectar: {exc}"
        else:
            app = self._app
            if app.qte_channel_id:
                await pool.check_access(app.qte_channel_id)
                if pool.webhooks_enabled and sender.access != "no":
                    await pool.add_lane(sender, app.qte_channel_id)
            return ""
        self._helper_errors[token] = message
        console_bridge.console.print(f"[yellow]⚠ Bot auxiliar no disponible: {message}[/yellow]")
        return message

    async def _remove_helper(self, token: str) -> None:
        self._helper_errors.pop(token, None)
        pool = self._pool
        if pool is None:
            return
        for sender in list(pool.helpers):
            if sender.client is not None and sender.client.http.token == token:
                await pool.remove_helper(sender)

    def add_helper(self, token: str) -> concurrent.futures.Future:
        return self.submit(lambda: self._add_helper(token.strip()))

    def remove_helper(self, token: str) -> concurrent.futures.Future:
        return self.submit(lambda: self._remove_helper(token.strip()))

    async def _test_helper(self, token: str) -> str:
        pool, app = self._pool, self._app
        if pool is None or not app.qte_channel_id:
            return "Elige primero el canal del evento."
        for sender in pool.helpers:
            if sender.client is not None and sender.client.http.token == token.strip():
                return await pool.test_send(sender, app.qte_channel_id) or ""
        return "Ese bot auxiliar no está conectado."

    def test_helper(self, token: str) -> concurrent.futures.Future:
        return self.submit(lambda: self._test_helper(token))

    async def _run_benchmark(self, profile: str) -> dict:
        pool, app = self._pool, self._app
        if pool is None or not app.qte_channel_id:
            return {"ok": False, "error": "Elige primero el canal del evento (Configuración → Bot y evento)."}
        out = console_bridge.console
        self._bench_stop = asyncio.Event()
        out.print("[bold cyan]▶ Prueba de rendimiento: manda mensajes de prueba al canal del evento y los borra[/bold cyan]")
        path = paths.logs_dir() / f"rendimiento_{time.strftime('%Y%m%d_%H%M%S')}.txt"

        def save(report: dict) -> list[str]:
            lines = benchmark.format_report(report)
            path.write_text("\n".join(lines) + "\n\n" + json.dumps(report, indent=2, ensure_ascii=False),
                            encoding="utf-8")
            return lines

        def show(report: dict) -> None:  # right away: the cleanup that follows may take a few seconds
            for line in save(report):
                out.print(f"[bold white]{line}[/bold white]")
            out.print(f"[green]Informe guardado en {path}[/green]")

        try:
            report = await benchmark.run(pool, app.qte_channel_id, profile=profile, stop=self._bench_stop,
                                         say=lambda text: out.print(f"[cyan]{text}[/cyan]"), on_report=show)
        finally:
            self._bench_stop = None
        lines = save(report)  # again, now with the cleanup result
        return {"ok": not report.get("aborted"), "error": report.get("aborted", ""), "report": report,
                "lines": lines, "path": str(path)}

    def run_benchmark(self, profile: str = "rapida") -> concurrent.futures.Future:
        """Performance test with the real bots (see benchmark.py). Posts test messages and deletes them."""
        return self.submit(lambda: self._run_benchmark(profile))

    def cancel_benchmark(self) -> None:
        stop, loop = self._bench_stop, self._loop
        if stop is not None and loop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(stop.set)

    def pool_snapshot(self) -> list[dict]:
        return self._pool.snapshot() if self._pool else []

    async def _start_pool(self, settings: Settings) -> None:
        """Once the main bot is logged in: route its sends through the pool and log the helpers in."""
        app = self._app
        pool = multibot.SenderPool(on_change=self._rebalance_interval)
        self._pool = pool
        # who wrote the HP bar messages must survive restarts, or the first edit of each goes to the wrong bot
        pool.owners_file = paths.data_dir() / "sender_owners.json"
        pool.trace_file = paths.logs_dir() / "requests.jsonl"   # every request + Discord's rate-limit headers
        pool.tracer.listeners.append(self._on_trace)
        pool.on_lag = self._on_lag
        pool.sticky_channels = {app.hp_bar_thread_id} if app.hp_bar_thread_id else set()
        pool.webhooks_enabled = settings.use_webhooks
        pool.lane_store = webhooks.LaneStore(paths.data_dir() / "webhook_lanes.json")
        app.own_webhook_ids = pool.lane_ids      # the bot must not take its own webhooks for players or Tupperbox

        async def identity():
            user = app.bot.user
            try:
                avatar = await user.display_avatar.replace(size=128, format="png").read()
            except Exception:  # noqa: BLE001 - a webhook without a picture is fine
                avatar = None
            return user.display_name, avatar

        pool.primary_identity = identity
        pool.install(app.bot.http, str(app.bot.user), app.bot.user.id)
        pool.start_background()  # keeps HTTPS connections warm for the next burst
        for token in settings.helper_tokens():
            await self._add_helper(token)
        if pool.helpers:
            online = len(pool.helpers)
            console_bridge.console.print(
                f"[green]✓ {online} bot{'s' if online != 1 else ''} auxiliar{'es' if online != 1 else ''} "
                f"compartiendo el envío de mensajes[/green]")
        await self._sync_lanes()
        await self._start_activity(settings)

    def _backup_on_stop(self) -> None:
        """Everything is on disk now: keep a copy of it if anything changed since the last one."""
        try:
            home = paths.app_home()
            if backups.changed_since_last(home):
                made = backups.make_backup(home, label=backups.AUTOMATIC)
                console_bridge.console.print(f"[dim]💾 Copia de seguridad de los datos: {made.name}[/dim]")
        except Exception as exc:  # noqa: BLE001 - never stop the bot from closing over a copy
            log.warning("automatic backup failed", exc_info=True)
            console_bridge.console.print(f"[yellow]⚠ No se pudo hacer la copia de seguridad automática: {markup_escape(str(exc))}[/yellow]")

    # ---- what the window shows about the event, and the host's own window -----------------------------------
    def event_snapshot(self) -> dict:
        """The live state of the event for the Home page (read-only; {} until the bot is ready)."""
        app = self._app
        if app is None or not self._is_ready():
            return {}
        a = self._activity
        online = {c.user_id for c in list(a.hub.conns.values())} if a is not None else set()
        return snapshot.event_snapshot(app, online)

    def host_url(self, *, gm: bool = True) -> str:
        """Where this PC opens the Activity as the host («» while the Activity is not running)."""
        info = self.activity_info()
        return browser.host_url(info["port"], gm=gm) if info.get("running") else ""

    def flush_data(self, timeout: float = 20.0) -> None:
        """Make sure what the bot knows is on disk (before a copy). Blocks the caller, never the bot's own thread."""
        app, loop = self._app, self._loop
        if app is None or loop is None or loop.is_closed():
            return
        module = importlib.import_module(BOT_MODULE)

        async def save() -> None:
            app.save_all_data(force=True)
            await asyncio.get_running_loop().run_in_executor(None, module.flush_saves)

        asyncio.run_coroutine_threadsafe(save(), loop).result(timeout)

    # ---- Discord Activity (local server + free tunnel) --------------------------------
    async def _start_activity(self, settings: Settings) -> None:
        if not settings.activity_enabled or self._activity is not None:
            return
        app, out = self._app, console_bridge.console
        client_id = app.bot.application_id or app.bot.user.id
        i18n.configure(overrides=paths.data_dir() / "i18n_es.json")       # the game masters' own Spanish for names and descriptions
        files = activity.MediaStore(paths.app_home() / "activity_media")      # pictures and audio kept on this PC (not in the data copies: audio is big)
        hub = activity.Hub()
        auth = activity.DiscordAuth(client_id=client_id, client_secret=settings.activity_client_secret.strip())
        bridge = activity.ActivityBridge(hub, app, pool=lambda: self._pool,
                                         avatar_file=paths.data_dir() / "character_avatars.json",
                                         prefs_file=paths.data_dir() / "activity_prefs.json",
                                         latency_file=paths.data_dir() / "activity_latency.json",
                                         data_dir=self._bot_data_dir(app), gm_log_file=paths.data_dir() / "gm_log.jsonl",
                                         values_file=paths.data_dir() / "gm_values.json", files=files,
                                         char_images_file=paths.data_dir() / "character_images.json",
                                         audio_file=paths.data_dir() / "audio_library.json")
        server = activity.ActivityServer(hub, auth=auth, authorize=bridge.authorize, client_id=client_id,
                                         web_dir=paths.resource_path("eventos_app", "activity", "web"),
                                         actions=bridge, media_dir=paths.app_home() / "cache" / "media", files=files,
                                         on_event=lambda text: out.print(f"[dim]🌐 Actividad: {markup_escape(text)}[/dim]"))
        try:
            port = await server.start()
        except OSError as exc:
            out.print(f"[yellow]⚠ No se pudo abrir el servidor de la Actividad: {exc}[/yellow]")
            await auth.close()
            return
        bridge.start()
        tunnel = self._make_tunnel(settings, port)
        self._activity = types.SimpleNamespace(hub=hub, auth=auth, bridge=bridge, server=server, tunnel=tunnel)
        out.print(f"[green]✓ Servidor de la Actividad en el puerto {port}. Abriendo el túnel…[/green]")
        self._activity_task = asyncio.get_running_loop().create_task(self._open_tunnel())

    @staticmethod
    def _bot_data_dir(app):
        """The folder the bot itself reads and writes its game data in (it falls back to another folder if the usual one is read-only)."""
        module = importlib.import_module(type(app).__module__) if type(app).__module__ else None
        found = getattr(module, "DATA_DIR", None)
        return found if found is not None else paths.data_dir()

    @staticmethod
    def _make_tunnel(settings: Settings, port: int):
        """Tailscale Funnel (fixed address) when chosen, the free Cloudflare quick tunnel otherwise."""
        if settings.activity_tunnel == "tailscale":
            return activity.TailscaleTunnel(port)
        return activity.Tunnel(port, tools_dir=paths.app_home() / "tools")

    async def _open_tunnel(self) -> dict:
        a, out = self._activity, console_bridge.console
        if a is None:
            return {"ok": False, "error": "La Actividad no está activada."}
        try:
            url = await a.tunnel.start()
        except activity.tunnel.TunnelError as exc:
            out.print(f"[yellow]⚠ Túnel de la Actividad: {exc}[/yellow]")
            return {"ok": False, "error": str(exc)}
        out.print(f"[green]✓ Actividad lista. Pega esta dirección en el Developer Portal (Activities → URL Mappings → raíz «/»): "
                  f"{url.removeprefix('https://')}[/green]")
        out.print(f"[cyan]🔎 Para comprobar el mapping sin abrir Discord, abre en el navegador: "
                  f"https://{a.server.client_id}.discordsays.com/healthz  (debe mostrar {{\"ok\": true…}})[/cyan]")
        return {"ok": True, "url": url}

    async def _stop_activity(self) -> None:
        a, self._activity = self._activity, None
        task, self._activity_task = self._activity_task, None
        if task is not None:
            task.cancel()
        if a is None:
            return
        for step in (a.tunnel.stop, a.server.stop, a.auth.close):
            try:
                await step()
            except Exception:  # noqa: BLE001
                log.exception("could not stop part of the Activity")
        a.bridge.stop()

    def activity_info(self) -> dict:
        """What the window shows about the Activity (read from the UI thread)."""
        a = self._activity
        if a is None:
            return {"running": False}
        return {"running": True, "port": a.server.port, "tunnel": a.tunnel.state, "detail": a.tunnel.detail,
                "url": a.tunnel.url, "fixed": getattr(a.tunnel, "fixed", False), "users": a.hub.stats(),
                "secret_set": bool(a.auth.client_secret), "client_id": a.server.client_id}

    def reopen_tunnel(self) -> concurrent.futures.Future:
        """A fresh tunnel (and a fresh address) without restarting the bot."""
        return self.submit(self._open_tunnel)

    # ---- webhook lanes (one webhook per bot in the event channel) ---------------------
    async def _sync_lanes(self, enabled: bool | None = None) -> dict:
        """(Re)register the webhooks for the current event channel and say how it went."""
        pool, app = self._pool, self._app
        if pool is None or app is None:
            return {"ok": False, "error": "El bot principal todavía no está listo."}
        if enabled is not None:
            pool.webhooks_enabled = enabled
        if not pool.webhooks_enabled:
            await pool.ensure_lanes(0)
            return {"ok": True, "lanes": 0, "failed": [], "disabled": True}
        if not app.qte_channel_id:
            return {"ok": False, "error": "Elige primero el canal del evento (Configuración → Bot y evento)."}
        results = await pool.ensure_lanes(app.qte_channel_id)
        good = [r for r in results if r["ok"]]
        bad = [r for r in results if not r["ok"]]
        out = console_bridge.console
        if good:
            out.print(f"[green]✓ {len(good)} webhook{'s' if len(good) != 1 else ''} de envío listo"
                      f"{'s' if len(good) != 1 else ''} en el canal del evento (1 por bot)[/green]")
        for item in bad:
            out.print(f"[yellow]⚠ Sin webhook para {diagnostics.short_name(item['bot'])}: {item['reason']}[/yellow]")
        return {"ok": True, "lanes": len(good), "failed": bad}

    def refresh_lanes(self, enabled: bool | None = None) -> concurrent.futures.Future:
        """Register the webhooks again (e.g. after granting «Gestionar webhooks») or switch them on/off now."""
        return self.submit(lambda: self._sync_lanes(enabled))

    def _on_trace(self, event: dict) -> None:
        """Explain each 429 in the log (at most one line per bot and kind every 3 s; the file has them all)."""
        if event["status"] != 429 or self._bench_stop is not None:   # the performance test prints its own diagnosis
            return
        now = time.monotonic()
        key = (event["bot"], event["kind"])
        if now - self._last_429.get(key, 0.0) < 3.0:
            return
        self._last_429[key] = now
        pool = self._pool
        console_bridge.console.print(
            f"[yellow]⚠ 429 · {diagnostics.explain_429(event, limit=pool.limits['send'][0] if pool else 5)}[/yellow]")

    def _on_lag(self, lag: float) -> None:
        console_bridge.console.print(
            f"[yellow]⚠ El bot tardó {round(lag * 1000)} ms en atender: va muy cargado (no es un límite de Discord).[/yellow]")

    def _rebalance_interval(self) -> None:
        """safe_send() used to wait a minimum time between messages per channel. The sender pool paces every
        bot now (and waits for a free slot when all are busy), so that extra wait is only added latency."""
        app, pool = self._app, self._pool
        if app is not None and pool is not None:
            app._min_message_interval = 0.0

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
            self._base_interval = self._app._min_message_interval
            self._helper_errors.clear()
            loop.run_until_complete(self._serve(settings))
        except BaseException as exc:  # noqa: BLE001 - everything must reach the UI
            error = friendly_error(exc)
            log.exception("bot stopped with an error")
            console_bridge.console.print(f"[red]✗ {error}[/red]")
        finally:
            self._cleanup(loop, settings)
            self._app = None
            self._loop = None
            self._pool = None
            if error:
                self._set(State.ERROR, error)
            else:
                self._set(State.STOPPED)

    async def _serve(self, settings: Settings) -> None:
        bot = self._app.bot
        started = False

        async def on_ready_once():
            nonlocal started
            if not started:  # on_ready fires again after reconnects
                started = True
                await self._start_pool(settings)

        bot.add_listener(on_ready_once, "on_ready")
        try:
            async with bot:
                await bot.start(settings.discord_token.strip())
        finally:
            await self._stop_activity()
            if self._pool is not None:
                await self._pool.close()
            if not bot.is_closed():
                await bot.close()

    def _cleanup(self, loop: asyncio.AbstractEventLoop, settings: Settings | None = None) -> None:
        app = self._app
        if app is not None:
            module = importlib.import_module(BOT_MODULE)
            for step in (app.teardown_hotkeys, lambda: app.save_all_data(force=True), module.flush_saves):
                try:
                    step()
                except Exception:
                    log.exception("cleanup step failed")
            if settings is not None and settings.backup_on_stop:
                self._backup_on_stop()
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
