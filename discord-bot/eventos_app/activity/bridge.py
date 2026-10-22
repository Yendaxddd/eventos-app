"""Connects the bot to the Activity: the event channel's messages go out, what the players do comes in, and the
bot decides who may be there at all."""

from __future__ import annotations

import asyncio
import logging
import re
import json
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable

import discord

from .auth import AuthError
from .hub import Conn, Hub, RpcError
from ..lang.discord_hooks import untranslated
from .gm import GmLog, GmPanel
from .gm_rpc import GmRpc
from .panel_rpc import PanelRpc, is_storage_message
from .media import MediaStore
from .tupper_rpc import TupperRpc
from .audio import AudioDirector, AudioLibrary
from .audio_rpc import AudioRpc
from .cinema import CinemaBook, CinemaDirector
from .cinema_rpc import CinemaRpc
from .fx import FxBook, FxDirector
from .arena import ArenaQtes
from .fx_rpc import FxRpc
from .quick_rpc import QuickRpc
from .latency import CAP_MS, LatencyBook, compensation
from .prefs import PrefsStore
from .qte import COMMANDS, TIMED, ActivityInput, describe, response_seconds

log = logging.getLogger("eventos_app.activity")

MAX_TEXT = 4000
MAX_SAY = 2000
SAY_INTERVAL = 0.4          # seconds between two messages of the same person
MAX_EMBEDS = 3
MAX_PRESSES = 3             # button presses accepted per person and QTE (the engine ignores repeats anyway)
MAX_COMBO_PRESSES = 8       # a combo is a chain of answers to one QTE
BACKLOG_FETCH = 40
STATE_INTERVAL = 1.0         # seconds between looks at the game state (HP, boss, charges); only changes are sent
MAX_PLAYERS_SHOWN = 30
AVATAR_MEMORY = 200
_TYPED_TIMED = re.compile(r"\*(evade|parry)\*", re.IGNORECASE)


def _color(value: Any) -> str:
    rgb = getattr(value, "value", value) or 0
    return f"#{int(rgb):06x}" if rgb else ""


def _media(asset: Any) -> str:
    """An embed picture/video through Discord's own proxy (media.discordapp.net), which the Activity may load."""
    return getattr(asset, "proxy_url", None) or getattr(asset, "url", None) or ""


def _emoji(emoji: Any) -> dict:
    if isinstance(emoji, str):
        return {"name": emoji}
    return {"name": getattr(emoji, "name", "") or "", "id": str(emoji.id) if getattr(emoji, "id", None) else "",
            "animated": bool(getattr(emoji, "animated", False))}


def _embed(e: Any) -> dict:
    author, footer = getattr(e, "author", None), getattr(e, "footer", None)
    return {
        "title": (getattr(e, "title", "") or "")[:256], "description": (getattr(e, "description", "") or "")[:1000],
        "color": _color(getattr(e, "color", None)), "url": getattr(e, "url", "") or "",
        "image": _media(getattr(e, "image", None)), "thumb": _media(getattr(e, "thumbnail", None)),
        "video": _media(getattr(e, "video", None)),
        "author": (getattr(author, "name", "") or "")[:256], "footer": (getattr(footer, "text", "") or "")[:256],
        "fields": [{"name": (f.name or "")[:256], "value": (f.value or "")[:300], "inline": bool(getattr(f, "inline", False))}
                   for f in list(getattr(e, "fields", []) or [])[:6]],
    }


def _reply(message: Any) -> dict | None:
    ref = getattr(message, "reference", None)
    target = getattr(ref, "resolved", None) if ref is not None else None
    if target is None:
        return None
    author = getattr(target, "author", None)
    if author is None:                      # a deleted message
        return {"author": "", "text": "Mensaje original eliminado"}
    return {"author": getattr(author, "display_name", None) or author.name,
            "text": ((getattr(target, "clean_content", "") or "")[:120])}


def serialize_message(message: Any, own_webhooks: set[int] | frozenset[int] = frozenset()) -> dict:
    """A Discord message as the Activity wants it (plain data; the client escapes everything it shows)."""
    author = message.author
    attachments = [{"url": a.url, "name": a.filename, "image": str(a.content_type or "").startswith("image/")}
                   for a in message.attachments][:6]
    embeds = [_embed(e) for e in list(message.embeds)[:MAX_EMBEDS]]
    top_role = getattr(author, "color", None)
    return {
        "id": str(message.id),
        "ts": int(message.created_at.timestamp() * 1000),
        "edited": bool(getattr(message, "edited_at", None)),
        "author": {"id": str(author.id), "name": getattr(author, "display_name", None) or author.name,
                   "avatar": str(author.display_avatar.url) if getattr(author, "display_avatar", None) else "",
                   "bot": bool(getattr(author, "bot", False)), "webhook": bool(message.webhook_id),
                   "ours": bool(message.webhook_id and message.webhook_id in own_webhooks),
                   "color": _color(top_role)},
        "text": (message.clean_content or "")[:MAX_TEXT],
        "attachments": attachments,
        "embeds": embeds,
        "stickers": [{"name": s.name, "url": str(s.url)} for s in list(getattr(message, "stickers", []) or [])[:3]],
        "reactions": [{"emoji": _emoji(r.emoji), "count": r.count} for r in list(getattr(message, "reactions", []) or [])[:20]],
        "reply": _reply(message),
    }


class ActivityBridge(PanelRpc, GmRpc, TupperRpc, AudioRpc, CinemaRpc, FxRpc, QuickRpc):
    def __init__(self, hub: Hub, app: Any, pool: Callable[[], Any] | None = None, avatar_file: Path | None = None,
                 prefs_file: Path | None = None, latency_file: Path | None = None, data_dir: Path | None = None,
                 gm_log_file: Path | None = None, values_file: Path | None = None, files: MediaStore | None = None,
                 char_images_file: Path | None = None, audio_file: Path | None = None, cinema_file: Path | None = None,
                 fx_file: Path | None = None) -> None:
        self.hub, self.app = hub, app        # app: the AdvancedQTEBot instance
        self.pool = pool or (lambda: None)   # the SenderPool, for webhook sends
        self._listeners: list[tuple[Any, str]] = []
        self.avatar_file = avatar_file
        self.prefs = PrefsStore(prefs_file)          # display settings of each player
        self.latency = LatencyBook(latency_file)     # tap-test result (device lag) of each player
        self.cap_ms = CAP_MS                         # the most a latency adjustment may move an answer
        self.avatars: OrderedDict[str, str] = OrderedDict()   # the picture each character was last seen with
        self._load_avatars()
        self._warned_no_lane = False
        self.public_url = ""                         # where the outside world reaches the Activity's server (the tunnel); set by the runner
        self._state_task = None
        self._init_panel()                           # the player dashboards (panel_rpc.py)
        self._init_tupper(files, char_images_file)   # the pictures kept on this PC (tupper_rpc.py)
        self.audio = AudioDirector(hub, AudioLibrary(files, audio_file))      # the sounds, the music and the cues (audio.py)
        self.arena = ArenaQtes(self)                                          # swipe, drag and tap QTEs (arena.py)
        self.fx = FxDirector(hub, FxBook(fx_file), self.audio)                 # the looks of powers and events (fx.py)
        self.cinema = CinemaDirector(hub, CinemaBook(cinema_file, self.audio.library), post=self._cinema_post)     # the scripts and their playing (cinema.py)
        self.gm = GmPanel(app, GmLog(gm_log_file), data_dir, values_file)       # the game-master panel (gm/, gm_rpc.py)

    # ---- wiring ---------------------------------------------------------------------------------
    def start(self) -> None:
        bot = self.app.bot
        for fn, name in ((self._on_message, "on_message"), (self._on_edit, "on_message_edit"),
                         (self._on_delete, "on_message_delete"), (self._on_reaction, "on_reaction_add"),
                         (self._on_reaction, "on_reaction_remove"), (self._on_reactions_cleared, "on_reaction_clear")):
            bot.add_listener(fn, name)        # alongside the bot's own handlers, which are not touched
            self._listeners.append((fn, name))
        book = getattr(self.app, "active_qtes", None)
        if hasattr(book, "on_start"):
            book.on_start, book.on_end = self._qte_started, self._qte_ended
        self.app.activity_notify = self               # the bot tells answers to the player here instead of in the channel (see feedback)
        self.hub.loader = self.load_backlog
        self.hub.on_tick = self.push_comps
        self.gm.apply_saved()                        # the numbers the game masters changed in the panel come back after a restart
        self.sync_channel()
        try:
            self._state_task = asyncio.get_running_loop().create_task(self._state_loop())
        except RuntimeError:
            self._state_task = None

    def stop(self) -> None:
        if getattr(self, "_state_task", None) is not None:
            self._state_task.cancel()
            self._state_task = None
        for fn, name in self._listeners:
            self.app.bot.remove_listener(fn, name)
        self._listeners.clear()
        self.arena.stop_all()
        book = getattr(self.app, "active_qtes", None)
        if hasattr(book, "on_start"):
            book.on_start = book.on_end = None
        if getattr(self.app, "activity_notify", None) is self:
            self.app.activity_notify = None
        self.hub.loader = None
        self.hub.on_tick = None

    def channel(self):
        channel_id = self.app.qte_channel_id
        return self.app.bot.get_channel(channel_id) if channel_id else None

    def sync_channel(self) -> None:
        """The event channel changed (or is being set up): the mirror starts over with the new one."""
        channel = self.channel()
        self.hub.reset_channel(getattr(channel, "name", "") or "")

    async def announce_channel(self) -> None:
        """Tell the players already inside that the channel changed, with its recent messages."""
        self.sync_channel()
        if self.hub.conns:
            await self.hub.broadcast({"t": "reset", "channel": self.hub.channel_name,
                                      "backlog": await self.hub.load_backlog()})

    def _load_avatars(self) -> None:
        if self.avatar_file is not None and self.avatar_file.exists():
            try:
                data = json.loads(self.avatar_file.read_text(encoding="utf-8"))
                self.avatars.update({str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {})
            except (OSError, ValueError):
                log.warning("could not read %s", self.avatar_file)

    def _save_avatars(self) -> None:
        if self.avatar_file is None:
            return
        try:
            tmp = self.avatar_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.avatars, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.avatar_file)
        except OSError:
            log.warning("could not save %s", self.avatar_file)

    def _frame(self, message) -> dict:
        frame = serialize_message(message, self.app.own_webhook_ids)
        author = frame["author"]
        if author["webhook"] and not author["ours"] and author["avatar"]:    # Tupperbox & co: remember the picture
            if self.avatars.get(author["name"]) != author["avatar"]:
                self.avatars[author["name"]] = author["avatar"]
                while len(self.avatars) > AVATAR_MEMORY:
                    self.avatars.popitem(last=False)
                self._save_avatars()
            self.avatars.move_to_end(author["name"])
        return frame

    # ---- bot -> Activity ---------------------------------------------------------------------------
    def _mine(self, message) -> bool:
        return bool(self.app.qte_channel_id) and message.channel.id == self.app.qte_channel_id and not is_storage_message(message)

    async def _on_message(self, message) -> None:
        if self._mine(message):
            await self.hub.push_message(self._frame(message))

    async def _on_edit(self, before, after) -> None:
        if self._mine(after):
            await self.hub.edit_message(self._frame(after))

    async def _on_delete(self, message) -> None:
        if self._mine(message):
            await self.hub.delete_message(str(message.id))

    async def _on_reaction(self, reaction, user=None) -> None:
        if self._mine(reaction.message):
            await self.hub.edit_message(self._frame(reaction.message))

    async def _on_reactions_cleared(self, message, reactions=None) -> None:
        if self._mine(message):
            await self.hub.edit_message(self._frame(message))

    async def load_backlog(self) -> list[dict]:
        channel = self.channel()
        if channel is None:
            return []
        frames = [self._frame(m) async for m in channel.history(limit=BACKLOG_FETCH, oldest_first=False) if not is_storage_message(m)]
        return list(reversed(frames))

    def _qte_started(self, qte_id, data) -> None:
        self._spawn(self._announce(qte_id, data, self.hub.now_ms()))

    async def _announce(self, qte_id, data: dict, started_ms: float) -> None:
        await asyncio.sleep(0)       # the bot fills in the rest of the QTE (a combo's sequence) right after creating it
        app = self.app
        frame = describe(qte_id, data, app.qte_times, started_ms, timeouts=getattr(app, "qte_timeout_durations", None),
                         bf_window=getattr(app, "bf_timing_window", 0.0), adjust=getattr(app, "get_adjusted_parry_window", None),
                         chain_window=getattr(app, "bf_chain_timing_window", 0.0))
        if str(qte_id) in {str(k) for k in app.active_qtes}:       # it may have been answered already
            await self.hub.qte_start(frame)
            target = frame.get("target")
            await self.audio.dispatch("qte", {"mode": frame["mode"], "difficulty": frame["difficulty"],
                                              "user": int(target["id"]) if target else None, "users": [int(p) for p in frame.get("participants") or []]})

    def on_event(self, event: str, data: dict | None = None) -> None:
        """The game says something happened (a Black Flash, the boss falls...): the cues bound to it play."""
        self._spawn(self.audio.dispatch(event, data or {}))
        self._spawn(self.cinema.on_event(event, data or {}))
        self._spawn(self.fx.dispatch(event, data or {}))

    # ---- notifications: what an answer led to, told to the player inside their Activity ----------------
    def has_player(self, user_id) -> bool:
        """Is this person inside the Activity right now (the host's own window does not count)?"""
        return any(c.user_id == user_id and not c.hidden for c in list(self.hub.conns.values()))

    def notify(self, who, kind: str, data: dict | None = None) -> None:
        """A notice for one player, or for each of a list of them. `kind` says what happened and `data` its numbers; the screen words it."""
        ids = {who} if isinstance(who, int) else set(who or ())
        for conn in list(self.hub.conns.values()):
            if conn.user_id in ids and not conn.hidden:
                self._spawn(self.hub.send(conn, {"t": "notice", "kind": str(kind), "data": data or {}}))

    def _qte_ended(self, qte_id, data) -> None:
        self._spawn(self.hub.qte_end(str(qte_id)))

    @staticmethod
    def _spawn(coro) -> None:
        try:
            asyncio.get_running_loop().create_task(coro)
        except RuntimeError:                  # no loop (the bot is shutting down)
            coro.close()

    # ---- the game state: HP, boss, charges ---------------------------------------------------------------
    @staticmethod
    def _num(value, digits: int = 1):
        try:
            return round(float(value), digits)
        except (TypeError, ValueError):
            return 0

    def snapshot(self) -> dict:
        """What everybody sees: the boss and the HP of the players. Read straight from the bot's own data."""
        app = self.app
        boss = getattr(app, "active_boss", None)
        boss_frame = None
        if boss:
            boss_frame = {"name": str(boss.get("name", "Jefe")), "hp": self._num(boss.get("hp_current"), 0),
                          "max": self._num(boss.get("hp_max"), 0)}
        hp = getattr(app, "player_hp", {}) or {}
        players = []
        for member in list(getattr(app, "qte_players", []) or [])[:MAX_PLAYERS_SHOWN]:
            entry = hp.get(member.id)
            if entry:
                players.append({"id": str(member.id), "name": getattr(member, "display_name", None) or member.name,
                                "hp": self._num(entry.get("current"), 0), "max": self._num(entry.get("max"), 0),
                                "revenge": bool(entry.get("revenge_mode"))})
        return {"boss": boss_frame, "fight": bool(getattr(app, "fight_active", False)), "players": players}

    def me_of(self, user_id: int) -> dict:
        """What only this player sees: charges, streak, and every countdown (as moments on the server's clock)."""
        app = self.app
        if user_id <= 0:
            return {}
        now = time.time()
        ms = lambda t: int(t * 1000)       # noqa: E731
        charges = (getattr(app, "power_charges", {}) or {}).get(user_id, {})
        stats = (getattr(app, "player_stats", {}) or {}).get(user_id, {})
        window, limit = float(getattr(app, "save_time_window", 60)), int(getattr(app, "save_limit", 2))
        recent = sorted(t for t in (getattr(app, "save_timestamps", {}) or {}).get(user_id, []) if now - t < window)
        parry_until = (getattr(app, "player_parry_cooldown", {}) or {}).get(user_id, 0)
        counter_until = (getattr(app, "counter_deadlines", {}) or {}).get(user_id, 0) \
            if user_id in (getattr(app, "counter_enabled_players", {}) or {}) else 0
        fight = bool(getattr(app, "fight_active", False))
        cooldowns = (getattr(app, "power_cooldowns", {}) or {}).get(user_id, {})
        paused = (getattr(app, "ultimate_fight_cooldowns", {}) or {}).get(user_id, {})
        powers: dict = {}
        for name in self.characters_of(user_id):
            known = (getattr(app, "character_powers", {}) or {}).get(name, {})
            entry = {}
            for key in ("power1", "power2"):
                if key in known:
                    end, rest = cooldowns.get(key, 0), paused.get(key, 0)
                    entry[key] = {"name": str(known[key].get("name", key))[:40],
                                  "until": ms(end) if fight and end > now else None,     # counting down (a fight is on)
                                  "paused": round(rest) if not fight and rest > 0 else None}   # waiting for the next fight
            if entry:
                powers[name] = entry
        domains = ((getattr(app, "player_achievements", {}) or {}).get(str(user_id), {}) or {}).get("domains")
        return {"charges": {"power1": self._num(charges.get("power1", 0)), "power2": self._num(charges.get("power2", 0))},
                "cost": self._num(getattr(app, "ultimate_cost", 100), 0), "streak": int(stats.get("evade_streak", 0) or 0),
                "saves": {"left": max(0, limit - len(recent)), "limit": limit,
                          "until": ms(recent[0] + window) if len(recent) >= limit else None},
                "parryUntil": ms(parry_until) if parry_until > now else None,
                "counterUntil": ms(counter_until) if counter_until > now else None,
                "powers": powers, "domain": bool(domains)}

    async def push_state(self) -> None:
        """Send what changed since the last look (nothing at all when nothing did)."""
        snap = self.snapshot()
        if snap != self.hub.state:
            self.hub.state = snap
            await self.hub.broadcast({"t": "state", "s": snap})
        for conn in list(self.hub.conns.values()):
            me = self.me_of(conn.user_id)
            if me != conn.last_me:
                conn.last_me = me
                await self.hub.send(conn, {"t": "me", "me": me, "now": self.hub.now_ms()})

    async def _state_loop(self) -> None:
        while True:
            await asyncio.sleep(STATE_INTERVAL)
            if not self.hub.conns:
                continue
            try:
                await self.push_state()
            except Exception:  # noqa: BLE001 - a bad value in the game data must not stop the loop
                log.exception("could not read the game state for the Activity")

    # ---- settings, latency adjustment, permissions ---------------------------------------------------------
    def rules(self) -> dict:
        """The bot's QTE timings, so the tutorial's practice uses the real windows."""
        app = self.app
        times, timeouts = getattr(app, "qte_times", {}) or {}, getattr(app, "qte_timeout_durations", {}) or {}
        return {
            "times": {d: {"evade": t.get("evade_window"), "parry": list(t.get("parry_window") or (0, 0)), "perfect": t.get("perfect_parry"),
                          "timeout": timeouts.get(d)} for d, t in times.items()},
            "bfWindow": float(getattr(app, "bf_timing_window", 0.2)), "chainWindow": float(getattr(app, "bf_chain_timing_window", 0.15)),
            "counterWindow": 5.0, "saveLimit": int(getattr(app, "save_limit", 2)), "saveWindow": float(getattr(app, "save_time_window", 60)),
            "ultimateCost": float(getattr(app, "ultimate_cost", 100)),
        }

    def char_avatars(self, user_id: int) -> dict:
        """The picture of each of the player's characters: the one kept on this PC (imported), else the last one seen in the channel."""
        found = {}
        for name in self.characters_of(user_id):
            picture = self.char_image(name) or self.avatars.get(name)
            if picture:
                found[name] = picture
        return found

    def compensation_of(self, conn: Conn) -> dict:
        return compensation(conn.net_ms, self.latency.device_ms(conn.user_id), self.cap_ms)

    async def gm_user(self, user_id: int, dev_gm: bool = False) -> bool:
        """The same question as `is_gm`, for somebody who is not connected through the socket (a file upload over HTTP)."""
        if user_id < 0:                                  # a test window on this PC: only if it asked to be a game master
            return dev_gm
        member = await self.member_of(user_id)
        try:
            return bool(member is not None and self.app.is_admin(member))
        except Exception:  # noqa: BLE001
            return False

    async def is_gm(self, conn: Conn) -> bool:
        """May this connection use the game-master panel? The bot decides by role, every time it is asked."""
        if conn.dev:
            return conn.gm
        member = await self.member_of(conn.user_id)
        try:
            return bool(member is not None and self.app.is_admin(member))
        except Exception:  # noqa: BLE001
            return False

    async def welcome_extras(self, conn: Conn) -> dict:
        comp = self.compensation_of(conn)
        conn.comp_sent = comp
        # prefs is None when the server knows nothing about this person yet: the client then keeps (and sends) the ones it has
        return {"perms": {"gm": await self.is_gm(conn)}, "prefs": self.prefs.get(conn.user_id) if self.prefs.has(conn.user_id) else None,
                "calib": self.latency.get(conn.user_id),
                "comp": comp, "rules": self.rules(), "charAvatars": self.char_avatars(conn.user_id), "audio": self.audio.welcome(),
                "cine": self.cinema.current()}

    async def save_prefs(self, conn: Conn, raw) -> dict:
        return self.prefs.set(conn.user_id, raw)

    async def save_latency(self, conn: Conn, raw) -> tuple[dict | None, dict]:
        """The result of the player's latency test: kept, and the adjustment recomputed with it."""
        result = self.latency.set(conn.user_id, raw)
        comp = self.compensation_of(conn)
        conn.comp_sent = comp
        return result, comp

    async def push_comps(self) -> None:
        """Tell each player their adjustment again when the server's own measurement moved it by a few ms."""
        for conn in list(self.hub.conns.values()):
            comp = self.compensation_of(conn)
            old = conn.comp_sent
            if old is None or abs(comp["net"] - old["net"]) >= 3 or comp["device"] != old["device"] or comp["cap"] != old["cap"]:
                conn.comp_sent = comp
                await self.hub.send(conn, {"t": "comp", "comp": comp})

    async def rpc(self, conn: Conn, op: str, args: dict):
        """Requests from the player's screen that expect an answer (profile data, game-master actions...)."""
        if not isinstance(args, dict):
            raise RpcError("Petición inválida.")
        handler = getattr(self, "rpc_" + op.replace(".", "_"), None) if op.replace(".", "_").replace("_", "").isalnum() else None
        if handler is None:
            raise RpcError("Esa acción no existe.")
        return await handler(conn, args)

    async def rpc_ping(self, conn: Conn, args: dict):
        return {"pong": True, "serverTime": self.hub.now_ms()}

    # ---- who may come in -----------------------------------------------------------------------------
    async def member_of(self, user_id: int):
        guild = self.app.resolve_event_guild()
        if guild is None or user_id <= 0:
            return None
        member = guild.get_member(user_id)
        if member is None:
            try:
                member = await guild.fetch_member(user_id)
            except (discord.NotFound, discord.HTTPException):
                member = None
        return member

    async def authorize(self, user_id: int) -> dict:
        """Only people who can see the event channel get to see it mirrored. Raises AuthError otherwise."""
        guild = self.app.resolve_event_guild()
        channel = self.channel()
        if guild is None or channel is None:
            raise AuthError("El evento todavía no tiene canal: el administrador debe elegirlo en la app.")
        member = await self.member_of(user_id)
        if member is None:
            raise AuthError("No eres miembro del servidor del evento.")
        perms = channel.permissions_for(member)
        if not (perms.view_channel and perms.read_message_history):
            raise AuthError("No tienes acceso al canal del evento.")
        return {"name": member.display_name, "avatar": str(member.display_avatar.url)}

    # ---- Activity -> bot ---------------------------------------------------------------------------------
    def characters_of(self, user_id: int) -> list[str]:
        try:
            return sorted(self.app.get_user_characters(user_id))
        except Exception:  # noqa: BLE001
            return []

    def character_avatar_url(self, name: str) -> str | None:
        """A web address Discord can fetch for the picture kept on this PC for a character (it goes out through the tunnel), or None."""
        picture = self.char_image(name)
        base = (self.public_url or "").rstrip("/")
        return f"{base}/{picture}" if picture and base.startswith("https://") else None

    async def say(self, conn: Conn, frame: dict) -> str | None:
        """A message written in the Activity: it appears in the channel under the chosen name and the bot treats it
        like any chat message (so `*attack*`, trigger phrases... work from here). Returns why not, or None."""
        text = str(frame.get("text", "")).strip()
        if not text:
            return None
        if len(text) > MAX_SAY:
            return f"Máximo {MAX_SAY} caracteres."
        now = time.monotonic()
        if now - conn.last_say < SAY_INTERVAL:
            return "Vas demasiado rápido."
        conn.last_say = now
        channel = self.channel()
        if channel is None:
            return "El evento todavía no tiene canal."
        as_name = str(frame.get("as") or "me")
        if as_name != "me" and as_name not in self.characters_of(conn.user_id):
            return "Ese personaje no es tuyo."
        name = conn.name if as_name == "me" else as_name
        avatar = conn.avatar if as_name == "me" else (self.character_avatar_url(as_name) or self.avatars.get(as_name) or conn.avatar)
        member = await self.member_of(conn.user_id)
        if member is not None and as_name == "me":
            name = member.display_name

        pool = self.pool()
        sent = None
        if pool is not None:
            try:
                sent = await pool.send_as(channel.id, content=text, username=name, avatar_url=avatar or None)
            except Exception:  # noqa: BLE001
                log.exception("could not post through a webhook")
        if sent is None:      # no lane (no «Gestionar webhooks» or none registered): the bot says it for them
            if not self._warned_no_lane:
                self._warned_no_lane = True
                log.warning("Activity: no webhook lane in the event channel, so players' messages go out as the bot "
                            "(give a bot «Gestionar webhooks» there to show their own name and picture)")
            try:
                with untranslated():                   # what the player wrote goes out as they wrote it
                    await channel.send(f"**{name}:** {text}", allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException as exc:
                return f"Discord no dejó publicarlo ({exc.status})."
        if member is not None:
            await self._run_typed(conn, member, channel, text, None if as_name == "me" else as_name)
        return None

    async def _run_typed(self, conn: Conn, member, channel, text: str, character: str | None = None) -> None:
        """Hand a written message to the bot's own message handler, as if it had been typed in the channel."""
        message = ActivityInput(member, channel, text, user_id=conn.user_id, character=character)
        timed = _TYPED_TIMED.search(text)
        try:
            if timed and self.app.active_qtes:
                # typed answers have no button timing: measure from the QTE start, less the trip to the player
                started = min((q["tGo"] for q in self.hub.qtes.values()), default=None)
                seconds = None if started is None else max(0.0, self.hub.now_ms() - started - conn.net_ms) / 1000.0
                await self.app.handle_qte_response(message, measured=seconds)
            else:
                await self.app.bot.on_message(message)
        except Exception:  # noqa: BLE001 - the message is already in the channel; a handler failing is the bot's log
            log.exception("the bot failed to handle a message written from the Activity")

    async def press(self, conn: Conn, frame: dict) -> str | None:
        """A QTE button. The player's screen measured `dt` (ms between seeing the QTE and pressing)."""
        command = str(frame.get("command", ""))
        if str(frame.get("id") or "").startswith("a"):           # a QTE of the Activity's own (swipe, drag, tap)
            return await self.arena.answer(conn, frame)
        if command not in COMMANDS:
            return "Botón desconocido."
        member = await self.member_of(conn.user_id)
        channel = self.channel()
        if member is None or channel is None:
            return "No se pudo comprobar quién eres en el servidor del evento."
        character = str(frame.get("as") or "me")
        if character != "me" and character not in self.characters_of(conn.user_id):
            return "Ese personaje no es tuyo."
        message = ActivityInput(member, channel, f"*{command}*", user_id=conn.user_id,
                                character=None if character == "me" else character)

        if command not in TIMED:       # adapt, attack, powers, domain: the bot's normal handler, no clock involved
            await self.app.bot.on_message(message)
            await self._verdict(conn, str(frame.get("id") or ""), message, None)
            return None

        qte_id = str(frame.get("id", ""))
        entry = self.hub.qtes.get(qte_id)
        if entry is None:
            return "Ese QTE ya terminó."
        if command not in entry.get("commands", ()):
            return "Ese botón no sirve en este QTE."
        limit = MAX_COMBO_PRESSES if entry.get("mode") == "combo" else MAX_PRESSES
        if conn.presses.get(qte_id, 0) >= limit:
            return None
        conn.presses[qte_id] = conn.presses.get(qte_id, 0) + 1
        try:
            dt = float(frame.get("dt"))
        except (TypeError, ValueError):
            return "Tiempo inválido."
        elapsed = self.hub.now_ms() - entry["tGo"]
        seconds = response_seconds(dt, conn.net_ms, elapsed, self.latency.device_ms(conn.user_id), self.cap_ms)
        if seconds is None:
            return "Esa pulsación no es creíble."
        key, data = next(((k, v) for k, v in self.app.active_qtes.items() if str(k) == qte_id), (None, None))
        if key is None:
            return "Ese QTE ya terminó."
        quiet = getattr(self.app, "feedback_quiet", None)
        message.mirror_to = None if (quiet is not None and quiet(conn.user_id)) else (data.get("message") if data else None)
        await self.app.handle_qte_response(message, measured=seconds, only=key)         # this QTE, not the first that takes it
        if entry.get("mode") == "fake":                         # a fake QTE: whoever answers it falls for it
            message.reactions[:] = ["❌"]
        await self._verdict(conn, qte_id, message, seconds)
        if entry.get("mode") == "combo" and key in self.app.active_qtes:               # the next step is shown only to who earned it
            now = self.app.active_qtes[key]
            sequence, index = now.get("combo_sequence") or [], int(now.get("combo_index", 0))
            if index < len(sequence):
                await self.hub.send(conn, {"t": "qte_step", "id": qte_id, "index": index, "step": sequence[index]})
        return None

    async def _verdict(self, conn: Conn, qte_id: str, message: ActivityInput, seconds: float | None) -> None:
        ok = True if "✅" in message.reactions else False if "❌" in message.reactions else None
        await self.hub.send(conn, {"t": "qte_result", "id": qte_id, "ok": ok,
                                   "ms": None if seconds is None else round(seconds * 1000),
                                   "reactions": message.reactions})
