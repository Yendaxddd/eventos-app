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
from .hub import Conn, Hub
from .qte import COMMANDS, ActivityInput, describe, response_seconds

log = logging.getLogger("eventos_app.activity")

MAX_TEXT = 4000
MAX_SAY = 2000
SAY_INTERVAL = 0.4          # seconds between two messages of the same person
MAX_EMBEDS = 3
MAX_PRESSES = 3             # button presses accepted per person and QTE (the engine ignores repeats anyway)
BACKLOG_FETCH = 40
STATE_INTERVAL = 1.0         # seconds between looks at the game state (HP, boss, charges); only changes are sent
MAX_PLAYERS_SHOWN = 30
AVATAR_MEMORY = 200
TIMED_COMMANDS = ("evade", "parry")                  # answered against the clock of the QTE
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


class ActivityBridge:
    def __init__(self, hub: Hub, app: Any, pool: Callable[[], Any] | None = None, avatar_file: Path | None = None) -> None:
        self.hub, self.app = hub, app        # app: the AdvancedQTEBot instance
        self.pool = pool or (lambda: None)   # the SenderPool, for webhook sends
        self._listeners: list[tuple[Any, str]] = []
        self.avatar_file = avatar_file
        self.avatars: OrderedDict[str, str] = OrderedDict()   # the picture each character was last seen with
        self._load_avatars()
        self._warned_no_lane = False
        self._state_task = None

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
        self.hub.loader = self.load_backlog
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
        book = getattr(self.app, "active_qtes", None)
        if hasattr(book, "on_start"):
            book.on_start = book.on_end = None
        self.hub.loader = None

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
        return bool(self.app.qte_channel_id) and message.channel.id == self.app.qte_channel_id

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
        frames = [self._frame(m) async for m in channel.history(limit=BACKLOG_FETCH, oldest_first=False)]
        return list(reversed(frames))

    def _qte_started(self, qte_id, data) -> None:
        app = self.app
        frame = describe(qte_id, data, app.qte_times, self.hub.now_ms(), timeouts=getattr(app, "qte_timeout_durations", None),
                         bf_window=getattr(app, "bf_timing_window", 0.0), adjust=getattr(app, "get_adjusted_parry_window", None))
        self._spawn(self.hub.qte_start(frame))

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
        """What only this player sees: their charges and streak."""
        app = self.app
        if user_id <= 0:
            return {}
        charges = (getattr(app, "power_charges", {}) or {}).get(user_id, {})
        stats = (getattr(app, "player_stats", {}) or {}).get(user_id, {})
        return {"charges": {"power1": self._num(charges.get("power1", 0)), "power2": self._num(charges.get("power2", 0))},
                "cost": self._num(getattr(app, "ultimate_cost", 100), 0), "streak": int(stats.get("evade_streak", 0) or 0)}

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
                await self.hub.send(conn, {"t": "me", "me": me})

    async def _state_loop(self) -> None:
        while True:
            await asyncio.sleep(STATE_INTERVAL)
            if not self.hub.conns:
                continue
            try:
                await self.push_state()
            except Exception:  # noqa: BLE001 - a bad value in the game data must not stop the loop
                log.exception("could not read the game state for the Activity")

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
        avatar = conn.avatar if as_name == "me" else (self.avatars.get(as_name) or conn.avatar)
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
                seconds = None if started is None else max(0.0, self.hub.now_ms() - started - (conn.rtt_ms or 0) / 2) / 1000.0
                await self.app.handle_qte_response(message, measured=seconds)
            else:
                await self.app.bot.on_message(message)
        except Exception:  # noqa: BLE001 - the message is already in the channel; a handler failing is the bot's log
            log.exception("the bot failed to handle a message written from the Activity")

    async def press(self, conn: Conn, frame: dict) -> str | None:
        """A QTE button. The player's screen measured `dt` (ms between seeing the QTE and pressing)."""
        command = str(frame.get("command", ""))
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

        if command not in TIMED_COMMANDS:       # adapt / attack: the bot's normal handler, no clock involved
            await self.app.bot.on_message(message)
            await self._verdict(conn, str(frame.get("id") or ""), message, None)
            return None

        qte_id = str(frame.get("id", ""))
        entry = self.hub.qtes.get(qte_id)
        if entry is None:
            return "Ese QTE ya terminó."
        if conn.presses.get(qte_id, 0) >= MAX_PRESSES:
            return None
        conn.presses[qte_id] = conn.presses.get(qte_id, 0) + 1
        try:
            dt = float(frame.get("dt"))
        except (TypeError, ValueError):
            return "Tiempo inválido."
        elapsed = self.hub.now_ms() - entry["tGo"]
        seconds = response_seconds(dt, conn.rtt_ms or 0.0, elapsed)
        if seconds is None:
            return "Esa pulsación no es creíble."
        data = next((v for k, v in self.app.active_qtes.items() if str(k) == qte_id), None)
        message.mirror_to = data.get("message") if data else None
        await self.app.handle_qte_response(message, measured=seconds)
        await self._verdict(conn, qte_id, message, seconds)
        return None

    async def _verdict(self, conn: Conn, qte_id: str, message: ActivityInput, seconds: float | None) -> None:
        ok = True if "✅" in message.reactions else False if "❌" in message.reactions else None
        await self.hub.send(conn, {"t": "qte_result", "id": qte_id, "ok": ok,
                                   "ms": None if seconds is None else round(seconds * 1000),
                                   "reactions": message.reactions})
