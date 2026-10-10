"""Spread the bot's outgoing messages over several Discord bot accounts, so that one account's
rate limits don't throttle a burst of QTEs.

How it works
------------
Discord rate-limits per bot token (and per channel): about 5 messages / 5 s in one channel for each
bot. The bot code sends with `channel.send(...)` in ~160 places, so instead of touching them all we
swap three methods of the primary bot's `HTTPClient` (`send_message`, `edit_message`,
`delete_message`). Every send, edit and delete in discord.py goes through those.

* Helper bots only log in over HTTP (no gateway, no privileged intents). They must be members of the
  server and may write in the event channel.
* A send goes to the sender (primary or helper) with the most room left in that channel's rate-limit
  window; the slot is reserved immediately so a burst of 10 messages is spread from the first one.
  Each sender sends one message at a time per channel (see CHANNEL_LIMIT for why).
* Edits and deletes go to the sender that wrote the message (Discord only lets a bot edit its own).
* If a helper can't write there (not in the server, no permission), the message goes out through another
  sender and that helper is skipped for that channel for a while.
* Messages with buttons always go through the primary: clicks are delivered only to the bot that is
  connected to the gateway.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from typing import Any, Callable, NamedTuple

import aiohttp
import discord

log = logging.getLogger("eventos_app.multibot")

# Discord allows ~5 messages / 5 s per channel per bot. We plan for 4 and send one at a time per bot
# and channel. Why: when a request finishes, discord.py computes `remaining - still_in_flight` and, if
# that is <= 0, makes the call wait for the whole window to reset (the message is already posted, but
# `await send()` doesn't return). That happens whenever 3+ sends run in parallel on one bot, or the 5th
# in a window finishes, and it would stall the QTE code that awaits the send (timers start late).
# With one request in flight and at most 4 per window that wait can't happen.
CHANNEL_LIMIT = 4
WINDOW_SECONDS = 5.0
SLOW_SEND_SECONDS = 1.5  # a send slower than this was probably held back by a rate limit
PENALTY_SECONDS = 4.0    # how long a sender that was just held back is deprioritised
BLOCK_SECONDS = 600.0    # skip a helper in a channel it can't write to for this long
OWNER_MEMORY = 20000     # message -> author sender, for edits/deletes

INVITE_PERMISSIONS = discord.Permissions(
    view_channel=True, send_messages=True, send_messages_in_threads=True, embed_links=True,
    attach_files=True, read_message_history=True, add_reactions=True, use_external_emojis=True,
)


class Endpoints(NamedTuple):
    send_message: Callable[..., Any]
    edit_message: Callable[..., Any]
    delete_message: Callable[..., Any]


@dataclass
class SenderStats:
    sent: int = 0
    edited: int = 0
    deleted: int = 0
    held_back: int = 0   # sends that were slowed down by a rate limit
    failed: int = 0      # sends that had to be redone through another sender


class Sender:
    """One bot account used for outgoing messages."""

    def __init__(self, name: str, endpoints: Endpoints, *, primary: bool = False,
                 client: discord.Client | None = None, user_id: int = 0) -> None:
        self.name = name
        self.endpoints = endpoints
        self.access = ""  # result of the last check on the event channel: "ok", "no" or "?"
        self.primary = primary
        self.client = client
        self.user_id = user_id
        self.ready = True
        self.error = ""
        self.stats = SenderStats()
        self.penalty_until = 0.0
        self.last_used = 0.0
        self._slots: dict[int, deque[float]] = {}
        self._blocked: dict[int, float] = {}
        self._locks: dict[int, asyncio.Lock] = {}

    def channel_lock(self, channel_id: int) -> asyncio.Lock:
        """Serialises this sender's sends to one channel (see CHANNEL_LIMIT)."""
        lock = self._locks.get(channel_id)
        if lock is None:
            lock = self._locks[channel_id] = asyncio.Lock()
        return lock

    # -- scheduling -----------------------------------------------------------
    def wait_for(self, channel_id: int, now: float, limit: int, window: float) -> float:
        """Seconds until this sender has a free slot in the channel (0 = right now)."""
        slots = self._slots.setdefault(channel_id, deque())
        while slots and now - slots[0] >= window:
            slots.popleft()
        wait = 0.0 if len(slots) < limit else slots[len(slots) - limit] + window - now
        return max(wait, self.penalty_until - now, 0.0)

    def reserve(self, channel_id: int, at: float) -> None:
        self._slots.setdefault(channel_id, deque()).append(at)

    def load(self, now: float, window: float) -> int:
        return sum(1 for slots in self._slots.values() for t in slots if now - t < window)

    def blocked(self, channel_id: int, now: float) -> bool:
        until = self._blocked.get(channel_id)
        if until is None:
            return False
        if now >= until:
            del self._blocked[channel_id]
            return False
        return True

    def block(self, channel_id: int, now: float, seconds: float) -> None:
        self._blocked[channel_id] = now + seconds

    def snapshot(self) -> dict:
        return {
            "name": self.name, "primary": self.primary, "ready": self.ready, "error": self.error,
            "user_id": self.user_id, "sent": self.stats.sent, "edited": self.stats.edited,
            "held_back": self.stats.held_back, "failed": self.stats.failed,
            "blocked_channels": len(self._blocked), "access": self.access,
        }


def _reset_files(params) -> None:
    """Rewind attachments so the same message can be sent again through another sender."""
    for file in (getattr(params, "files", None) or ()):
        try:
            file.reset()
        except Exception:  # noqa: BLE001
            pass


def has_components(params) -> bool:
    payload = getattr(params, "payload", None)
    if payload is None:
        for part in getattr(params, "multipart", None) or ():
            if part.get("name") == "payload_json":
                try:
                    payload = json.loads(part["value"])
                except (ValueError, TypeError):
                    payload = None
                break
    return bool(payload and payload.get("components"))


_UNREACHABLE = (aiohttp.ClientError, asyncio.TimeoutError, OSError)


class SenderPool:
    def __init__(self, *, limit: int = CHANNEL_LIMIT, window: float = WINDOW_SECONDS,
                 on_change: Callable[[], None] | None = None) -> None:
        self.limit = limit
        self.window = window
        self.on_change = on_change
        self.primary: Sender | None = None
        self.helpers: list[Sender] = []
        self._owners: OrderedDict[int, Sender] = OrderedDict()
        self._http = None

    # ---- setup -----------------------------------------------------------------
    def install(self, primary_http, primary_name: str = "Principal", primary_user_id: int = 0) -> None:
        """Start routing the primary bot's sends/edits/deletes through the pool."""
        if self._http is not None:
            return
        self._http = primary_http
        self.primary = Sender(
            primary_name,
            Endpoints(primary_http.send_message, primary_http.edit_message, primary_http.delete_message),
            primary=True, user_id=primary_user_id,
        )
        primary_http.send_message = self._route_send
        primary_http.edit_message = self._route_edit
        primary_http.delete_message = self._route_delete
        self._changed()

    def uninstall(self) -> None:
        """Restore the primary's own methods (instance attributes shadow the class methods)."""
        if self._http is not None:
            for name in ("send_message", "edit_message", "delete_message"):
                self._http.__dict__.pop(name, None)
            self._http = None

    async def add_helper(self, token: str) -> Sender:
        """Log a helper bot in (HTTP only) and add it to the pool."""
        client = discord.Client(intents=discord.Intents.none())
        try:
            await client.login(token.strip())
            user = client.user
            known = {self.primary.user_id} if self.primary and self.primary.user_id else set()
            known |= {h.user_id for h in self.helpers}
            if user.id in known:
                raise ValueError(f"{user} ya está en uso (es el bot principal o un auxiliar repetido).")
        except BaseException:
            await client.close()
            raise
        http = client.http
        sender = Sender(str(user), Endpoints(http.send_message, http.edit_message, http.delete_message),
                        client=client, user_id=user.id)
        self.helpers.append(sender)
        self._changed()
        return sender

    async def check_access(self, channel_id: int) -> None:
        """Ask Discord whether each helper can see the channel; helpers that can't are skipped there.

        Only proves the helper is in the server and can view the channel, not that it may write
        (use `test_send` for that). Spares the first burst from discovering it the hard way.
        """
        for sender in self.helpers:
            if sender.client is None:
                continue
            try:
                await sender.client.http.get_channel(channel_id)
            except (discord.Forbidden, discord.NotFound):
                sender.access = "no"
                sender.block(channel_id, time.monotonic(), BLOCK_SECONDS)
            except _UNREACHABLE:
                sender.access = "?"
            else:
                sender.access = "ok"
                sender._blocked.pop(channel_id, None)
        self._changed()

    async def remove_helper(self, sender: Sender) -> None:
        if sender in self.helpers:
            self.helpers.remove(sender)
        sender.ready = False
        for message_id in [m for m, s in self._owners.items() if s is sender]:
            del self._owners[message_id]
        if sender.client is not None:
            await sender.client.close()
        self._changed()

    async def close(self) -> None:
        self.uninstall()
        for sender in list(self.helpers):
            await self.remove_helper(sender)

    # ---- routing -----------------------------------------------------------------
    def _all(self) -> list[Sender]:
        return ([self.primary] if self.primary else []) + self.helpers

    def _pick(self, channel_id: int, now: float, exclude: set[Sender]) -> Sender | None:
        best, best_key = None, None
        for sender in self._all():
            if sender in exclude or not sender.ready or sender.blocked(channel_id, now):
                continue
            wait = round(sender.wait_for(channel_id, now, self.limit, self.window), 3)
            key = (wait, sender.load(now, self.window), sender.last_used, sender.primary)
            if best_key is None or key < best_key:
                best, best_key = sender, key
        return best

    def _remember(self, message_id: int, sender: Sender) -> None:
        self._owners[message_id] = sender
        self._owners.move_to_end(message_id)
        while len(self._owners) > OWNER_MEMORY:
            self._owners.popitem(last=False)

    async def _route_send(self, channel_id, *, params):
        channel_id = int(channel_id)
        if has_components(params) or not any(h.ready for h in self.helpers):
            return await self._send_via(self.primary, channel_id, params)

        tried: set[Sender] = set()
        last_error: BaseException | None = None
        while True:
            now = time.monotonic()
            sender = self._pick(channel_id, now, tried)
            if sender is None:
                if last_error is not None:
                    raise last_error
                return await self._send_via(self.primary, channel_id, params)
            wait = sender.wait_for(channel_id, now, self.limit, self.window)
            sender.reserve(channel_id, now + wait)
            try:
                async with sender.channel_lock(channel_id):
                    return await self._send_via(sender, channel_id, params)
            except (discord.Forbidden, discord.NotFound) as exc:
                if sender.primary:
                    raise
                sender.block(channel_id, time.monotonic(), BLOCK_SECONDS)
                log.warning("helper %s cannot write in channel %s (%s); skipping it there", sender.name, channel_id, exc)
                last_error = exc
            except _UNREACHABLE as exc:
                if sender.primary:
                    raise
                log.warning("helper %s unreachable (%s)", sender.name, exc)
                last_error = exc
            sender.stats.failed += 1
            tried.add(sender)
            _reset_files(params)

    async def _send_via(self, sender: Sender, channel_id: int, params):
        started = time.monotonic()
        data = await sender.endpoints.send_message(channel_id, params=params)
        elapsed = time.monotonic() - started
        sender.stats.sent += 1
        sender.last_used = time.monotonic()
        if elapsed > SLOW_SEND_SECONDS and not getattr(params, "files", None):
            sender.stats.held_back += 1
            sender.penalty_until = time.monotonic() + PENALTY_SECONDS
        if isinstance(data, dict) and data.get("id"):
            self._remember(int(data["id"]), sender)
        return data

    def _order_for(self, message_id: int) -> list[Sender]:
        owner = self._owners.get(int(message_id))
        rest = [s for s in self._all() if s.ready and s is not owner]
        return ([owner] if owner and owner.ready else []) + rest

    async def _route_edit(self, channel_id, message_id, *, params):
        last: BaseException | None = None
        for sender in self._order_for(message_id):
            try:
                data = await sender.endpoints.edit_message(channel_id, message_id, params=params)
            except discord.Forbidden as exc:  # not the author: try the next sender
                last = exc
                _reset_files(params)
                continue
            sender.stats.edited += 1
            self._remember(int(message_id), sender)
            return data
        raise last or RuntimeError("no sender available")

    async def _route_delete(self, channel_id, message_id, *, reason=None):
        last: BaseException | None = None
        for sender in self._order_for(message_id):
            try:
                result = await sender.endpoints.delete_message(channel_id, message_id, reason=reason)
            except discord.Forbidden as exc:
                last = exc
                continue
            sender.stats.deleted += 1
            self._owners.pop(int(message_id), None)
            return result
        raise last or RuntimeError("no sender available")

    # ---- information for the UI ----------------------------------------------------
    def snapshot(self) -> list[dict]:
        return [s.snapshot() for s in self._all()]

    def ready_count(self) -> int:
        return sum(1 for s in self._all() if s.ready)

    def _changed(self) -> None:
        if self.on_change is not None:
            try:
                self.on_change()
            except Exception:  # noqa: BLE001
                log.exception("on_change failed")

    async def test_send(self, sender: Sender, channel_id: int) -> str:
        """Send (and delete) a short message with one sender. Returns '' on success or a message."""
        try:
            data = await sender.endpoints.send_message(
                channel_id, params=_plain_params(f"🔧 Prueba de **{sender.name}**: este mensaje se borra solo."))
            await asyncio.sleep(2.5)
            await sender.endpoints.delete_message(channel_id, int(data["id"]), reason="test")
            return ""
        except discord.Forbidden:
            return "No tiene permiso para escribir en ese canal (o no está en el servidor)."
        except discord.NotFound:
            return "No ve ese canal: ¿está invitado a ese servidor?"
        except Exception as exc:  # noqa: BLE001
            return f"{type(exc).__name__}: {exc}"


def _plain_params(content: str):
    from discord.http import MultipartParameters
    return MultipartParameters(payload={"content": content}, multipart=None, files=None)


def invite_url(client_id: int) -> str:
    return discord.utils.oauth_url(client_id, permissions=INVITE_PERMISSIONS, scopes=("bot",))


@dataclass
class TokenInfo:
    user_id: int
    name: str
    invite: str = field(default="")


async def inspect_token(token: str) -> TokenInfo:
    """Log in briefly to learn who a token belongs to (raises discord.LoginFailure etc.)."""
    client = discord.Client(intents=discord.Intents.none())
    try:
        await client.login(token.strip())
        return TokenInfo(client.user.id, str(client.user), invite_url(client.user.id))
    finally:
        await client.close()
