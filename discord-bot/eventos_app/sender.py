"""One account (or one webhook) that can put messages in the event channel, and what it has used so far."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, NamedTuple

import discord

CHANNEL_LIMIT = 5          # messages per window per channel per bot (Discord: 5 / 5 s)
WINDOW_SECONDS = 5.3       # a little more than 5 s: network jitter can squeeze requests together
WARM_CONNECTIONS = CHANNEL_LIMIT  # connections kept ready per sender: a burst opens one per message


class Endpoints(NamedTuple):
    send_message: Callable[..., Any]
    edit_message: Callable[..., Any]
    delete_message: Callable[..., Any]
    add_reaction: Callable[..., Any]
    ping: Callable[..., Any] | None
    bulk_delete: Callable[..., Any] | None = None  # up to 100 messages in one call (needs Manage Messages)


def endpoints_of(http) -> Endpoints:
    async def ping():
        return await http.request(discord.http.Route("GET", "/gateway"))

    return Endpoints(http.send_message, http.edit_message, http.delete_message, http.add_reaction, ping,
                     getattr(http, "delete_messages", None))


def webhook_endpoints_of(http, webhook_id: int, token: str) -> Endpoints:
    """The same five calls for one webhook, sent over `http` (the session of the bot that registered it).

    The webhook's token is in the URL, so Discord does not look at who asks. Reactions are not possible.
    """
    def route(method: str, tail: str = "", **extra) -> discord.http.Route:
        return discord.http.Route(method, "/webhooks/{webhook_id}/{webhook_token}" + tail,
                                  webhook_id=webhook_id, webhook_token=token, **extra)

    async def send(channel_id, *, params):
        r, query = route("POST"), {"wait": "true"}
        if getattr(params, "files", None):
            return await http.request(r, files=params.files, form=params.multipart, params=query)
        return await http.request(r, json=params.payload, params=query)

    async def edit(channel_id, message_id, *, params):
        r = route("PATCH", "/messages/{message_id}", message_id=message_id)
        if getattr(params, "files", None):
            return await http.request(r, files=params.files, form=params.multipart)
        return await http.request(r, json=params.payload)

    async def delete(channel_id, message_id, *, reason=None):
        return await http.request(route("DELETE", "/messages/{message_id}", message_id=message_id))

    async def react(*args, **kwargs):
        raise RuntimeError("a webhook cannot add reactions")

    return Endpoints(send, edit, delete, react, None, None)


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
        # a webhook lane: sends only, in one channel, with its own (more generous) limits
        self.lane = False
        self.channel = 0                  # the only channel a lane can write to (0 = any)
        self.webhook_id = 0
        self.owner: "Sender | None" = None   # the bot that registered the lane
        self.can_react = True
        self.send_limit: int | None = None   # per-sender override of the pool's message limit
        self.send_window: float | None = None
        self.send_429_at = 0.0
        self.lane_note = ""               # on a bot: how registering its webhook went ("" = not tried, "ok" or why not)
        self.access = ""  # result of the last check on the event channel: "ok", "no" or "?"
        self.ready = True
        self.error = ""
        self.stats = SenderStats()
        self.penalty_until = 0.0
        self.react_spacing = 0.0     # learned from Discord's 429s / headers; 0 = use the pool's default
        self.react_clean = 0         # successful reactions since the last 429
        self.react_429_at = 0.0
        self.last_used = 0.0
        self.latencies: deque[float] = deque(maxlen=200)   # seconds per successful send
        self._slots: dict[tuple[str, int], deque[float]] = {}
        self._shifted: dict[tuple[str, int], float] = {}   # total seconds pending slots were pushed back (see push_back)
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

    def shifted(self, kind: str, channel_id: int) -> float:
        return self._shifted.get((kind, channel_id), 0.0)

    def push_back(self, kind: str, channel_id: int, now: float, earliest: float) -> float:
        """Delay every slot that has not come yet so the first of them is not before `earliest`.

        Used after a 429: discord.py retries that request on its own and the retry takes the next bit of quota;
        the requests planned behind it would collide with it one after another. Returns the seconds moved.
        """
        slots = self._slots.get((kind, channel_id))
        future = [t for t in slots if t > now] if slots else []
        if not future:
            return 0.0
        delta = earliest - min(future)
        if delta <= 0:
            return 0.0
        self._slots[(kind, channel_id)] = deque(t + delta if t > now else t for t in slots)
        self._shifted[(kind, channel_id)] = self.shifted(kind, channel_id) + delta
        return delta

    def quiet_in(self, kind: str, channel_id: int, now: float, window: float) -> float:
        """Seconds until every slot used so far has expired (0 = the sender is completely fresh)."""
        slots = self._slots.get((kind, channel_id))
        last = slots[-1] + window - now if slots else 0.0
        return max(last, self.penalty_until - now, 0.0)

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
        if not self.ready or self.endpoints.ping is None or time.monotonic() - self.last_used < 3.0:
            return
        results = await asyncio.gather(*(self.endpoints.ping() for _ in range(WARM_CONNECTIONS)), return_exceptions=True)
        self.stats.pings += sum(1 for r in results if not isinstance(r, BaseException))

    def snapshot(self) -> dict:
        return {
            "name": self.name, "primary": self.primary, "lane": self.lane, "lane_note": self.lane_note, "ready": self.ready, "error": self.error,
            "user_id": self.user_id, "sent": self.stats.sent, "reactions": self.stats.reactions,
            "edited": self.stats.edited, "held_back": self.stats.held_back, "failed": self.stats.failed,
            "pings": self.stats.pings, "blocked_channels": len({c for (_, c) in self._blocked}),
            "access": self.access, "react_spacing_ms": round(self.react_spacing * 1000),
            "p50_ms": round(self.percentile(0.5) * 1000), "p95_ms": round(self.percentile(0.95) * 1000),
        }
