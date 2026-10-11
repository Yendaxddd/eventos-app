"""Spread the bot's outgoing messages and reactions over several Discord bot accounts and remove the
waiting discord.py adds on its own, so a burst of QTE traffic goes out with as little delay as possible.

How it works
------------
Discord rate-limits per bot token (and per channel): about 5 messages / 5 s in a channel for each bot,
and about 4 reactions / second. The bot code sends with `channel.send(...)` in ~160 places, so instead
of touching them all we swap a few methods of the primary bot's `HTTPClient` (`send_message`,
`edit_message`, `delete_message`, `add_reaction`). Everything in discord.py goes through those.

* Helper bots only log in over HTTP (no gateway, no privileged intents). They must be members of the
  server and may write in the event channel.
* A send (or reaction) goes to the sender with the most room left in that channel's rate-limit window; the
  slot is reserved immediately so a burst of 10 messages is spread from the first one. If every sender is
  full, the call waits for the first free slot instead of being refused.
* Edits and deletes go to the sender that wrote the message (Discord only lets a bot edit its own).
  For sticky channels (the HP bar thread) that knowledge survives restarts.
* If a helper can't write there (not in the server, no permission), the message goes out through another
  sender and that helper is skipped for that channel for a while.
* Messages with buttons always go through the primary: clicks are delivered only to the bot that is
  connected to the gateway.

Why the rate limit objects are replaced
---------------------------------------
discord.py serialises requests per bucket and, when a request finishes, computes
`remaining - still_in_flight`; if that is <= 0 it makes the call wait for the whole window to reset (the
message is already posted, but `await send()` doesn't return). With three or four sends in flight on
one bot that happens although plenty of quota is left, and the code awaiting the send (QTE timers!) is
stalled for seconds. The pool already does the pacing, so for the message, reaction and ping routes it
hands discord.py an "open" bucket that never blocks. Real 429s are still handled by discord.py's own
retry loop. If a future discord.py no longer exposes `get_ratelimit`, the pool falls back to sending one
message at a time per bot and channel, which avoids the stall the slow way.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, NamedTuple

import aiohttp
import discord

log = logging.getLogger("eventos_app.multibot")

CHANNEL_LIMIT = 5          # messages per window per channel per bot (Discord: 5 / 5 s)
WINDOW_SECONDS = 5.3       # a little more than 5 s: network jitter can squeeze requests together
REACTION_SPACING = 0.27    # Discord: 1 reaction per 250 ms per channel per bot
SLOW_SEND_SECONDS = 1.5    # a send slower than this was probably held back by a rate limit
PENALTY_SECONDS = 4.0      # how long a sender that was just held back is deprioritised
BLOCK_SECONDS = 600.0      # skip a helper in a channel it can't write to for this long
OWNER_MEMORY = 20000       # message -> author sender, for edits/deletes
STICKY_MEMORY = 500        # authors remembered across restarts (HP bar messages)
WARM_INTERVAL = 8.0        # seconds between keep-alive rounds (aiohttp closes idle connections at 15 s)
WARM_CONNECTIONS = 3       # connections kept ready per sender for a burst

SEND_ROUTE = "POST /channels/{channel_id}/messages"
REACT_ROUTE = "PUT /channels/{channel_id}/messages/{message_id}/reactions/{emoji}/@me"
PING_ROUTE = "GET /gateway"
OPEN_ROUTES = (SEND_ROUTE, REACT_ROUTE, PING_ROUTE)

INVITE_PERMISSIONS = discord.Permissions(
    view_channel=True, send_messages=True, send_messages_in_threads=True, embed_links=True,
    attach_files=True, read_message_history=True, add_reactions=True, use_external_emojis=True,
)


class Endpoints(NamedTuple):
    send_message: Callable[..., Any]
    edit_message: Callable[..., Any]
    delete_message: Callable[..., Any]
    add_reaction: Callable[..., Any]
    ping: Callable[..., Any]


def endpoints_of(http) -> Endpoints:
    async def ping():
        return await http.request(discord.http.Route("GET", "/gateway"))

    return Endpoints(http.send_message, http.edit_message, http.delete_message, http.add_reaction, ping)


class OpenBucket:
    """Stands in for discord.py's `Ratelimit`: never blocks (the pool does the pacing)."""

    limit = remaining = 1_000_000
    outgoing = 0
    reset_after = 0.0
    expires = None
    dirty = True

    async def __aenter__(self) -> "OpenBucket":
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    def update(self, response, *, use_clock: bool = False) -> None:
        return None

    def reset(self) -> None:
        return None

    def is_expired(self) -> bool:
        return False

    def is_inactive(self) -> bool:
        return True


_OPEN = OpenBucket()


def can_open_buckets(http) -> bool:
    return callable(getattr(http, "get_ratelimit", None)) and hasattr(discord.http, "Ratelimit")


def open_buckets(http) -> None:
    """Make the message / reaction / ping routes of this HTTP client non-blocking."""
    original = http.get_ratelimit

    def get_ratelimit(key: str):
        head = key.rpartition(":")[0]  # "<route or bucket hash>:<major parameters>"
        if head in OPEN_ROUTES or head in {http._bucket_hashes.get(r) for r in OPEN_ROUTES}:
            return _OPEN
        return original(key)

    http.get_ratelimit = get_ratelimit


@dataclass
class SenderStats:
    sent: int = 0
    reactions: int = 0
    edited: int = 0
    deleted: int = 0
    held_back: int = 0   # sends that were slowed down by a rate limit
    failed: int = 0      # calls that had to be redone through another sender
    pings: int = 0


class Sender:
    """One bot account used for outgoing traffic."""

    def __init__(self, name: str, endpoints: Endpoints, *, primary: bool = False,
                 client: discord.Client | None = None, user_id: int = 0) -> None:
        self.name = name
        self.endpoints = endpoints
        self.primary = primary
        self.client = client
        self.user_id = user_id
        self.access = ""  # result of the last check on the event channel: "ok", "no" or "?"
        self.ready = True
        self.error = ""
        self.stats = SenderStats()
        self.penalty_until = 0.0
        self.last_used = 0.0
        self.latencies: deque[float] = deque(maxlen=200)   # seconds per successful send
        self._slots: dict[tuple[str, int], deque[float]] = {}
        self._blocked: dict[tuple[str, int], float] = {}
        self._locks: dict[int, asyncio.Lock] = {}

    # -- scheduling -----------------------------------------------------------
    def channel_lock(self, channel_id: int) -> asyncio.Lock:
        """Only used when discord.py's buckets can't be opened (see the module docstring)."""
        lock = self._locks.get(channel_id)
        if lock is None:
            lock = self._locks[channel_id] = asyncio.Lock()
        return lock

    def wait_for(self, kind: str, channel_id: int, now: float, limit: int, window: float) -> float:
        """Seconds until this sender has a free slot of `kind` in the channel (0 = right now)."""
        slots = self._slots.setdefault((kind, channel_id), deque())
        while slots and now - slots[0] >= window:
            slots.popleft()
        wait = 0.0 if len(slots) < limit else slots[len(slots) - limit] + window - now
        return max(wait, self.penalty_until - now, 0.0)

    def reserve(self, kind: str, channel_id: int, at: float) -> None:
        self._slots.setdefault((kind, channel_id), deque()).append(at)

    def load(self, now: float, window: float) -> int:
        return sum(1 for (kind, _), slots in self._slots.items() if kind == "send" for t in slots if now - t < window)

    def blocked(self, kind: str, channel_id: int, now: float) -> bool:
        until = self._blocked.get((kind, channel_id))
        if until is None:
            return False
        if now >= until:
            del self._blocked[(kind, channel_id)]
            return False
        return True

    def block(self, channel_id: int, now: float, seconds: float, kinds: tuple[str, ...] = ("send", "react")) -> None:
        for kind in kinds:
            self._blocked[(kind, channel_id)] = now + seconds

    def unblock(self, channel_id: int) -> None:
        for kind in ("send", "react"):
            self._blocked.pop((kind, channel_id), None)

    # -- measuring ------------------------------------------------------------
    def percentile(self, p: float) -> float:
        if not self.latencies:
            return 0.0
        ordered = sorted(self.latencies)
        return ordered[min(len(ordered) - 1, int(p * len(ordered)))]

    async def warm(self) -> None:
        """Keep a few HTTPS connections open so the next burst doesn't pay for TCP + TLS handshakes."""
        if not self.ready or time.monotonic() - self.last_used < 3.0:
            return
        results = await asyncio.gather(*(self.endpoints.ping() for _ in range(WARM_CONNECTIONS)), return_exceptions=True)
        self.stats.pings += sum(1 for r in results if not isinstance(r, BaseException))

    def snapshot(self) -> dict:
        return {
            "name": self.name, "primary": self.primary, "ready": self.ready, "error": self.error,
            "user_id": self.user_id, "sent": self.stats.sent, "reactions": self.stats.reactions,
            "edited": self.stats.edited, "held_back": self.stats.held_back, "failed": self.stats.failed,
            "pings": self.stats.pings, "blocked_channels": len({c for (_, c) in self._blocked}),
            "access": self.access,
            "p50_ms": round(self.percentile(0.5) * 1000), "p95_ms": round(self.percentile(0.95) * 1000),
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
_METHODS = ("send_message", "edit_message", "delete_message", "add_reaction")


class SenderPool:
    def __init__(self, *, limit: int = CHANNEL_LIMIT, window: float = WINDOW_SECONDS,
                 reaction_spacing: float = REACTION_SPACING, on_change: Callable[[], None] | None = None) -> None:
        self.limits = {"send": (limit, window), "react": (1, reaction_spacing)}
        self.on_change = on_change
        self.primary: Sender | None = None
        self.helpers: list[Sender] = []
        self.sticky_channels: set[int] = set()
        self.owners_file: Path | None = None
        self._owners: OrderedDict[int, Sender] = OrderedDict()
        self._sticky: OrderedDict[int, int] = OrderedDict()   # message id -> author user id
        self._sticky_dirty = False
        self._http = None
        self._open = False
        self._task: asyncio.Task | None = None

    # ---- setup -----------------------------------------------------------------
    def install(self, primary_http, primary_name: str = "Principal", primary_user_id: int = 0) -> None:
        """Start routing the primary bot's sends/edits/deletes/reactions through the pool."""
        if self._http is not None:
            return
        self._http = primary_http
        self._open = can_open_buckets(primary_http)
        if self._open:
            open_buckets(primary_http)
        else:
            log.warning("discord.py has no get_ratelimit(): sending one message at a time per bot and channel")
        self.primary = Sender(primary_name, endpoints_of(primary_http), primary=True, user_id=primary_user_id)
        primary_http.send_message = self._route_send
        primary_http.edit_message = self._route_edit
        primary_http.delete_message = self._route_delete
        primary_http.add_reaction = self._route_react
        self.load_owners()
        self._changed()

    def uninstall(self) -> None:
        """Restore the primary's own methods (instance attributes shadow the class methods)."""
        if self._http is not None:
            for name in (*_METHODS, "get_ratelimit"):
                self._http.__dict__.pop(name, None)
            self._http = None

    def start_background(self) -> None:
        """Keep connections warm and persist author memory. Needs a running loop."""
        if self._task is None:
            self._task = asyncio.get_running_loop().create_task(self._background())

    async def _background(self) -> None:
        while True:
            await asyncio.sleep(WARM_INTERVAL)
            try:
                await asyncio.gather(*(s.warm() for s in self._all()), return_exceptions=True)
                self.save_owners()
            except Exception:  # noqa: BLE001
                log.exception("pool background round failed")

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
        if can_open_buckets(client.http):
            open_buckets(client.http)
        sender = Sender(str(user), endpoints_of(client.http), client=client, user_id=user.id)
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
                sender.unblock(channel_id)
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
        if self._task is not None:
            self._task.cancel()
            self._task = None
        self.save_owners()
        self.uninstall()
        for sender in list(self.helpers):
            await self.remove_helper(sender)

    # ---- routing -----------------------------------------------------------------
    def _all(self) -> list[Sender]:
        return ([self.primary] if self.primary else []) + self.helpers

    def _pick(self, kind: str, channel_id: int, now: float, exclude: set[Sender]) -> Sender | None:
        limit, window = self.limits[kind]
        best, best_key = None, None
        for sender in self._all():
            if sender in exclude or not sender.ready or sender.blocked(kind, channel_id, now):
                continue
            wait = round(sender.wait_for(kind, channel_id, now, limit, window), 3)
            key = (wait, sender.load(now, self.limits["send"][1]), sender.last_used, sender.primary)
            if best_key is None or key < best_key:
                best, best_key = sender, key
        return best

    async def _admit(self, sender: Sender, kind: str, channel_id: int) -> None:
        """Reserve the sender's next slot and, if it isn't free yet, wait for it."""
        limit, window = self.limits[kind]
        now = time.monotonic()
        wait = sender.wait_for(kind, channel_id, now, limit, window)
        sender.reserve(kind, channel_id, now + wait)
        if wait > 0:
            await asyncio.sleep(wait)

    def _remember(self, message_id: int, channel_id: int, sender: Sender) -> None:
        self._owners[message_id] = sender
        self._owners.move_to_end(message_id)
        while len(self._owners) > OWNER_MEMORY:
            self._owners.popitem(last=False)
        if channel_id in self.sticky_channels and sender.user_id:
            self._sticky[message_id] = sender.user_id
            self._sticky.move_to_end(message_id)
            while len(self._sticky) > STICKY_MEMORY:
                self._sticky.popitem(last=False)
            self._sticky_dirty = True

    async def _route_send(self, channel_id, *, params):
        channel_id = int(channel_id)
        if has_components(params):
            await self._admit(self.primary, "send", channel_id)
            return await self._send_via(self.primary, channel_id, params)

        tried: set[Sender] = set()
        last_error: BaseException | None = None
        redone: set[Sender] = set()
        while True:
            sender = self._pick("send", channel_id, time.monotonic(), tried)
            if sender is None:
                if last_error is not None:
                    raise last_error
                sender = self.primary
            await self._admit(sender, "send", channel_id)
            try:
                if self._open:
                    return await self._send_via(sender, channel_id, params)
                async with sender.channel_lock(channel_id):
                    return await self._send_via(sender, channel_id, params)
            except aiohttp.ServerDisconnectedError as exc:
                # a keep-alive connection that died while idle: the next try opens a fresh one
                if sender in redone:
                    if sender.primary:
                        raise
                    last_error = exc
                else:
                    redone.add(sender)
                    _reset_files(params)
                    continue
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
        if not getattr(params, "files", None):
            sender.latencies.append(elapsed)
            if elapsed > SLOW_SEND_SECONDS:
                sender.stats.held_back += 1
                sender.penalty_until = time.monotonic() + PENALTY_SECONDS
        if isinstance(data, dict) and data.get("id"):
            self._remember(int(data["id"]), channel_id, sender)
        return data

    async def _route_react(self, channel_id, message_id, emoji):
        channel_id = int(channel_id)
        tried: set[Sender] = set()
        last_error: BaseException | None = None
        while True:
            sender = self._pick("react", channel_id, time.monotonic(), tried)
            if sender is None:
                if last_error is not None:
                    raise last_error
                sender = self.primary
            await self._admit(sender, "react", channel_id)
            try:
                result = await sender.endpoints.add_reaction(channel_id, message_id, emoji)
            except (discord.Forbidden, discord.NotFound) as exc:
                # the message may simply be gone; only a helper is worth retrying elsewhere
                if sender.primary:
                    raise
                sender.block(channel_id, time.monotonic(), BLOCK_SECONDS, kinds=("react",))
                last_error = exc
            except _UNREACHABLE as exc:
                if sender.primary:
                    raise
                last_error = exc
            else:
                sender.stats.reactions += 1
                sender.last_used = time.monotonic()
                return result
            sender.stats.failed += 1
            tried.add(sender)

    # ---- who wrote a message -------------------------------------------------------
    def _by_user_id(self, user_id: int) -> Sender | None:
        return next((s for s in self._all() if s.user_id == user_id), None)

    def _order_for(self, message_id: int) -> list[Sender]:
        message_id = int(message_id)
        owner = self._owners.get(message_id)
        if owner is None and message_id in self._sticky:
            owner = self._by_user_id(self._sticky[message_id])
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
            self._remember(int(message_id), int(channel_id), sender)
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
            self._sticky.pop(int(message_id), None)
            return result
        raise last or RuntimeError("no sender available")

    # ---- persistence of who wrote the sticky messages ----------------------------------
    def load_owners(self) -> None:
        if self.owners_file is None or not self.owners_file.exists():
            return
        try:
            raw = json.loads(self.owners_file.read_text(encoding="utf-8"))
            self._sticky = OrderedDict((int(m), int(u)) for m, u in raw.items())
        except (OSError, ValueError):
            log.warning("could not read %s; starting without it", self.owners_file)

    def save_owners(self) -> None:
        if self.owners_file is None or not self._sticky_dirty:
            return
        try:
            tmp = self.owners_file.with_suffix(".tmp")
            tmp.write_text(json.dumps({str(m): u for m, u in self._sticky.items()}), encoding="utf-8")
            tmp.replace(self.owners_file)
            self._sticky_dirty = False
        except OSError:
            log.warning("could not save %s", self.owners_file)

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

    # Same routes the bot's own calls take; the performance test uses them.
    async def send_text(self, channel_id: int, text: str):
        return await self._route_send(channel_id, params=_plain_params(text))

    async def add_reaction(self, channel_id: int, message_id: int, emoji: str):
        return await self._route_react(channel_id, message_id, emoji)

    async def delete_message(self, channel_id: int, message_id: int):
        return await self._route_delete(channel_id, message_id)

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
