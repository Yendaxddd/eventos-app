"""Connects the bot to the Activity: the event channel's messages go out, and the bot decides who may come in."""

from __future__ import annotations

import logging
from typing import Any

import discord

from .auth import AuthError
from .hub import Hub

log = logging.getLogger("eventos_app.activity")

MAX_TEXT = 4000
MAX_EMBEDS = 3
BACKLOG_FETCH = 40


def _color(value: Any) -> str:
    rgb = getattr(value, "value", value) or 0
    return f"#{int(rgb):06x}" if rgb else ""


def serialize_message(message: Any, own_webhooks: set[int] | frozenset[int] = frozenset()) -> dict:
    """A Discord message as the Activity wants it (plain data; the client escapes everything it shows)."""
    author = message.author
    attachments = [{"url": a.url, "name": a.filename, "image": str(a.content_type or "").startswith("image/")}
                   for a in message.attachments][:6]
    embeds = []
    for e in list(message.embeds)[:MAX_EMBEDS]:
        embeds.append({"title": (e.title or "")[:256], "description": (e.description or "")[:1000],
                       "image": getattr(getattr(e, "image", None), "url", "") or getattr(getattr(e, "thumbnail", None), "url", "") or "",
                       "color": _color(e.color)})
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
    }


class ActivityBridge:
    def __init__(self, hub: Hub, app: Any) -> None:
        self.hub, self.app = hub, app        # app: the AdvancedQTEBot instance
        self._listeners: list[tuple[Any, str]] = []

    # ---- wiring ---------------------------------------------------------------------------------
    def start(self) -> None:
        bot = self.app.bot
        for fn, name in ((self._on_message, "on_message"), (self._on_edit, "on_message_edit"),
                         (self._on_delete, "on_message_delete")):
            bot.add_listener(fn, name)        # alongside the bot's own handlers, which are not touched
            self._listeners.append((fn, name))
        self.hub.loader = self.load_backlog
        self.sync_channel()

    def stop(self) -> None:
        for fn, name in self._listeners:
            self.app.bot.remove_listener(fn, name)
        self._listeners.clear()
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

    def _frame(self, message) -> dict:
        return serialize_message(message, self.app.own_webhook_ids)

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

    async def load_backlog(self) -> list[dict]:
        channel = self.channel()
        if channel is None:
            return []
        frames = [self._frame(m) async for m in channel.history(limit=BACKLOG_FETCH, oldest_first=False)]
        return list(reversed(frames))

    # ---- who may come in -----------------------------------------------------------------------------
    async def authorize(self, user_id: int) -> dict:
        """Only people who can see the event channel get to see it mirrored. Raises AuthError otherwise."""
        guild = self.app.resolve_event_guild()
        channel = self.channel()
        if guild is None or channel is None:
            raise AuthError("El evento todavía no tiene canal: el administrador debe elegirlo en la app.")
        member = guild.get_member(user_id)
        if member is None:
            try:
                member = await guild.fetch_member(user_id)
            except (discord.NotFound, discord.HTTPException):
                member = None
        if member is None:
            raise AuthError("No eres miembro del servidor del evento.")
        perms = channel.permissions_for(member)
        if not (perms.view_channel and perms.read_message_history):
            raise AuthError("No tienes acceso al canal del evento.")
        return {"name": member.display_name, "avatar": str(member.display_avatar.url)}
