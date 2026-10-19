"""Everyone connected to the Activity, and what the server tells them."""

from __future__ import annotations

import asyncio
import itertools
import logging
import statistics
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger("eventos_app.activity")

BACKLOG = 60                 # messages kept to show to whoever joins
RATE_PER_SECOND = 30.0       # frames a single connection may send per second (bursts of 2x)
PING_EVERY = 2.0             # seconds between the server's own round-trip measurements of each player
RTT_SAMPLES = 15             # how many of them are remembered


class RpcError(Exception):
    """A request the player can be told why it was refused (its message is shown as is)."""


@dataclass
class Conn:
    """One open WebSocket."""
    id: int
    user_id: int
    name: str
    avatar: str
    ws: Any                              # aiohttp WebSocketResponse (anything with `send_json` / `close`)
    dev: bool = False                    # opened from a browser on this PC, not from Discord
    rtt_ms: float | None = None          # last round trip measured by the client
    offset_ms: float | None = None       # server clock minus client clock, as estimated by the client
    joined: float = field(default_factory=time.time)
    last_say: float = 0.0                # monotonic time of the last message written from the Activity
    last_me: dict | None = None          # the private state this connection was last sent (see the bridge's state loop)
    presses: dict = field(default_factory=dict)   # QTE id -> how many times this connection pressed a button for it
    rtts: deque = field(default_factory=lambda: deque(maxlen=RTT_SAMPLES))   # round trips (ms) measured by the server itself
    sp_sent: dict = field(default_factory=dict)   # server ping number -> when it was sent (monotonic)
    comp_sent: dict | None = None                 # the latency adjustment this connection was last told
    gm: bool = False                              # may use the game-master panel (checked again on every action)
    hidden: bool = False                          # the host's own window (the desktop app): it is not listed among the people in the Activity
    _tokens: float = 2 * RATE_PER_SECOND
    _refilled: float = field(default_factory=time.monotonic)

    def allow(self) -> bool:
        """Token bucket: a connection that floods the server is told to slow down."""
        now = time.monotonic()
        self._tokens = min(2 * RATE_PER_SECOND, self._tokens + (now - self._refilled) * RATE_PER_SECOND)
        self._refilled = now
        if self._tokens < 1:
            return False
        self._tokens -= 1
        return True

    def public(self) -> dict:
        return {"id": str(self.user_id), "name": self.name, "avatar": self.avatar, "dev": self.dev}

    @property
    def net_ms(self) -> float:
        """How long a frame takes to reach this player: half the typical round trip. What the server measured itself, until it
        has enough of that, what the client reported."""
        if len(self.rtts) >= 3:
            return statistics.median(self.rtts) / 2.0
        return (self.rtt_ms or 0.0) / 2.0

    @property
    def jitter_ms(self) -> float | None:
        if len(self.rtts) < 3:
            return None
        middle = statistics.median(self.rtts)
        return sum(abs(r - middle) for r in self.rtts) / len(self.rtts)

    def stats(self) -> dict:
        return {**self.public(), "hidden": self.hidden, "rtt_ms": self.rtt_ms, "offset_ms": self.offset_ms,
                "net_ms": round(self.net_ms, 1), "jitter_ms": None if self.jitter_ms is None else round(self.jitter_ms, 1),
                "seconds": round(time.time() - self.joined)}


class Hub:
    def __init__(self, backlog: int = BACKLOG) -> None:
        self.conns: dict[int, Conn] = {}
        self._ids = itertools.count(1)
        self.backlog: deque[dict] = deque(maxlen=backlog)
        self.channel_name = ""
        self.on_change: Callable[[], None] | None = None   # the app's window refreshes who is connected
        self.loader: Callable[[], Any] | None = None       # async () -> list of message frames, for the first joiner
        self._loaded = False
        self.state: dict = {}                               # boss / players, as last broadcast
        self.qtes: dict[str, dict] = {}                    # QTE id -> the frame the clients were shown (still running)
        self.on_tick: Callable[[], Any] | None = None       # async; called after each round of server pings (the bridge pushes latency changes)
        self._pinger: asyncio.Task | None = None
        self._ping_no = 0

    # ---- clock ---------------------------------------------------------------------------
    @staticmethod
    def now_ms() -> float:
        """The server clock the clients synchronise to (wall clock, milliseconds)."""
        return time.time() * 1000.0

    # ---- connections ----------------------------------------------------------------------
    def new_id(self) -> int:
        return next(self._ids)

    async def add(self, conn: Conn) -> None:
        self.conns[conn.id] = conn
        self._ensure_pinger()
        await self.broadcast({"t": "users", "users": self.participants()})
        self._changed()

    async def remove(self, conn: Conn) -> None:
        if self.conns.pop(conn.id, None) is not None:
            await self.broadcast({"t": "users", "users": self.participants()})
            self._changed()

    # ---- the server's own round-trip measurements -----------------------------------------------------
    def _ensure_pinger(self) -> None:
        if self._pinger is None or self._pinger.done():
            try:
                self._pinger = asyncio.get_running_loop().create_task(self._ping_loop())
            except RuntimeError:                   # no loop yet (a test building a hub by hand)
                self._pinger = None

    async def _ping_loop(self) -> None:
        while True:
            await asyncio.sleep(PING_EVERY)
            if not self.conns:
                continue
            self._ping_no += 1
            for conn in list(self.conns.values()):
                conn.sp_sent[self._ping_no] = time.monotonic()
                for old in [n for n in conn.sp_sent if n < self._ping_no - 6]:
                    conn.sp_sent.pop(old, None)
                await self.send(conn, {"t": "sp", "n": self._ping_no})
            if self.on_tick is not None:
                try:
                    await self.on_tick()
                except Exception:  # noqa: BLE001 - measuring must never stop
                    log.exception("hub.on_tick failed")

    def note_sq(self, conn: Conn, n) -> None:
        """The client answered a server ping: that is one round trip, measured on the server's own clock."""
        try:
            sent = conn.sp_sent.pop(int(n), None)
        except (TypeError, ValueError):
            return
        if sent is not None:
            conn.rtts.append((time.monotonic() - sent) * 1000.0)

    async def close(self) -> None:
        if self._pinger is not None:
            self._pinger.cancel()
            self._pinger = None

    def participants(self) -> list[dict]:
        seen: dict[int, dict] = {}
        for conn in self.conns.values():       # one entry per person, even with two windows open
            if not conn.hidden:
                seen.setdefault(conn.user_id, conn.public())
        return list(seen.values())

    def stats(self) -> list[dict]:
        return [c.stats() for c in self.conns.values()]

    def _changed(self) -> None:
        if self.on_change is not None:
            try:
                self.on_change()
            except Exception:  # noqa: BLE001
                log.exception("hub.on_change failed")

    # ---- sending --------------------------------------------------------------------------
    @staticmethod
    async def send(conn: Conn, frame: dict) -> bool:
        try:
            await conn.ws.send_json(frame)
            return True
        except Exception:  # noqa: BLE001 - a dead socket is cleaned up by its own handler
            return False

    async def broadcast(self, frame: dict) -> int:
        """Send to everybody at once; returns how many got it."""
        conns = list(self.conns.values())
        results = await asyncio.gather(*(self.send(c, frame) for c in conns))
        return sum(results)

    # ---- the mirrored channel ---------------------------------------------------------------
    async def load_backlog(self) -> list[dict]:
        """The recent messages (read from Discord once, then kept up to date by the live events)."""
        if not self._loaded and self.loader is not None:
            self._loaded = True
            try:
                for frame in await self.loader():
                    self.backlog.append(frame)
            except Exception:  # noqa: BLE001
                log.exception("could not read the channel history")
                self._loaded = False
        return list(self.backlog)

    def reset_channel(self, name: str = "") -> None:
        """The event moved to another channel: forget the old messages."""
        self.backlog.clear()
        self._loaded = False
        self.channel_name = name

    async def push_message(self, frame: dict) -> None:
        self.backlog.append(frame)
        await self.broadcast({"t": "msg", "m": frame})

    async def edit_message(self, frame: dict) -> None:
        for i, old in enumerate(self.backlog):
            if old["id"] == frame["id"]:
                self.backlog[i] = frame
        await self.broadcast({"t": "edit", "m": frame})

    async def delete_message(self, message_id: str) -> None:
        kept = [m for m in self.backlog if m["id"] != message_id]
        self.backlog.clear()
        self.backlog.extend(kept)
        await self.broadcast({"t": "del", "id": message_id})

    # ---- QTEs ---------------------------------------------------------------------------------
    async def qte_start(self, frame: dict) -> None:
        self.qtes[frame["id"]] = frame
        await self.broadcast({"t": "qte", "q": frame, "now": self.now_ms()})      # `now` lets a client tell how long ago it started

    async def qte_end(self, qte_id: str) -> None:
        if self.qtes.pop(qte_id, None) is not None:
            for conn in self.conns.values():
                conn.presses.pop(qte_id, None)
            await self.broadcast({"t": "qte_end", "id": qte_id})
