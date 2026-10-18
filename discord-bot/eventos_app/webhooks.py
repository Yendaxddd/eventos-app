"""Webhook lanes: every bot registers ONE webhook in the event channel and the pool sends through it as well.

Why: Discord limits each bot to 5 messages per 5 s per channel, but a webhook has a limit of its own (about
5 per 2 s), so a webhook is a free extra "sender" that needs no new account. A channel can hold 15 webhooks
in total, therefore a bot never makes more than one: it first looks for the one it registered before (kept in
`webhook_lanes.json`, and by name as a fallback) and only creates one when there is none.

Needs the *Manage Webhooks* permission for that bot in the channel. Without it the bot simply has no lane
and keeps sending as itself; `register` explains why in Spanish so the app can show it.
"""

from __future__ import annotations

import base64
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import discord

log = logging.getLogger("eventos_app.webhooks")

MAX_WEBHOOKS_PER_CHANNEL = 15
_FORBIDDEN_WORDS = re.compile(r"clyde|discord", re.IGNORECASE)   # Discord refuses webhook names containing these


class LaneError(Exception):
    """A webhook could not be registered; the message is meant for the user."""


@dataclass
class LaneInfo:
    channel_id: int
    user_id: int          # the bot that registered it
    webhook_id: int
    token: str
    name: str
    created: bool = False


def lane_name(display_name: str) -> str:
    """The name the webhook shows: the bot's own, minus what Discord does not accept."""
    name = _FORBIDDEN_WORDS.sub("·", display_name).strip() or "Eventos"
    return name[:80]


def avatar_data(raw: bytes | None) -> str | None:
    if not raw:
        return None
    mime = "image/png"
    if raw[:3] == b"\xff\xd8\xff":
        mime = "image/jpeg"
    elif raw[:4] == b"GIF8":
        mime = "image/gif"
    elif raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        mime = "image/webp"
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


class LaneStore:
    """Which webhook each bot registered in which channel: `{"<channel>:<bot>": {"id": ..., "token": ...}}`."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self._data: dict[str, dict] = {}
        if path is not None and path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self._data = {k: v for k, v in raw.items() if isinstance(v, dict)}
            except (OSError, ValueError):
                log.warning("could not read %s; starting without it", path)

    @staticmethod
    def _key(channel_id: int, user_id: int) -> str:
        return f"{channel_id}:{user_id}"

    def get(self, channel_id: int, user_id: int) -> tuple[int, str] | None:
        entry = self._data.get(self._key(channel_id, user_id))
        if entry and str(entry.get("id", "")).isdigit() and entry.get("token"):
            return int(entry["id"]), str(entry["token"])
        return None

    def put(self, channel_id: int, user_id: int, webhook_id: int, token: str) -> None:
        self._data[self._key(channel_id, user_id)] = {"id": str(webhook_id), "token": token}
        self._save()

    def forget(self, channel_id: int, user_id: int) -> None:
        if self._data.pop(self._key(channel_id, user_id), None) is not None:
            self._save()

    def _save(self) -> None:
        if self.path is None:
            return
        try:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._data, indent=1), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            log.warning("could not save %s", self.path)


async def _still_there(http, webhook_id: int, token: str) -> bool:
    route = discord.http.Route("GET", "/webhooks/{webhook_id}/{webhook_token}", webhook_id=webhook_id, webhook_token=token)
    try:
        await http.request(route)
    except discord.HTTPException as exc:
        if exc.status in (401, 403, 404):
            return False
        raise
    return True


def _explain(exc: discord.HTTPException) -> str:
    if getattr(exc, "code", 0) == 30007 or "maximum number of webhooks" in str(exc).lower():
        return f"el canal ya tiene {MAX_WEBHOOKS_PER_CHANNEL} webhooks (el máximo): borra alguno que no uses"
    if isinstance(exc, discord.Forbidden):
        return "le falta el permiso «Gestionar webhooks» en ese canal"
    return f"Discord respondió {exc.status}: {exc.text or type(exc).__name__}"


async def register(http, *, channel_id: int, user_id: int, display_name: str, avatar: bytes | None,
                   store: LaneStore) -> LaneInfo:
    """Find (or create) the single webhook of this bot in this channel. Raises `LaneError`."""
    name = lane_name(display_name)
    known = store.get(channel_id, user_id)
    if known is not None:
        try:
            if await _still_there(http, *known):
                return LaneInfo(channel_id, user_id, known[0], known[1], name)
        except discord.HTTPException as exc:
            raise LaneError(_explain(exc)) from exc
        store.forget(channel_id, user_id)   # deleted by hand: register again below

    try:
        existing = await http.channel_webhooks(channel_id)
    except discord.HTTPException as exc:
        raise LaneError(_explain(exc)) from exc
    for hook in existing:
        creator = int((hook.get("user") or {}).get("id") or 0)
        if creator == user_id and hook.get("name") == name and hook.get("token"):
            store.put(channel_id, user_id, int(hook["id"]), hook["token"])
            return LaneInfo(channel_id, user_id, int(hook["id"]), hook["token"], name)
    if len(existing) >= MAX_WEBHOOKS_PER_CHANNEL:
        raise LaneError(f"el canal ya tiene {MAX_WEBHOOKS_PER_CHANNEL} webhooks (el máximo): borra alguno que no uses")

    try:
        data = await http.create_webhook(channel_id, name=name, avatar=avatar_data(avatar),
                                         reason="Eventos App: carril de envío extra")
    except discord.HTTPException as exc:
        raise LaneError(_explain(exc)) from exc
    if not data.get("token"):
        raise LaneError("Discord no devolvió el token del webhook")
    store.put(channel_id, user_id, int(data["id"]), data["token"])
    return LaneInfo(channel_id, user_id, int(data["id"]), data["token"], name, created=True)
