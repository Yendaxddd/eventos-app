"""Everyone connected to the Activity, and what the server tells them."""

from __future__ import annotations

import asyncio
import itertools
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger("eventos_app.activity")

BACKLOG = 60                 # messages kept to show to whoever joins
RATE_PER_SECOND = 30.0       # frames a single connection may send per second (bursts of 2x)


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
    presses: dict = field(default_factory=dict)   # QTE id -> how many times this connection pressed a button for it
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

    def stats(self) -> dict:
        return {**self.public(), "rtt_ms": self.rtt_ms, "offset_ms": self.offset_ms,
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
        self.qtes: dict[str, dict] = {}                    # QTE id -> the frame the clients were shown (still running)

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
        await self.broadcast({"t": "users", "users": self.participants()})
        self._changed()

    async def remove(self, conn: Conn) -> None:
        if self.conns.pop(conn.id, None) is not None:
            await self.broadcast({"t": "users", "users": self.participants()})
            self._changed()

    def participants(self) -> list[dict]:
        seen: dict[int, dict] = {}
        for conn in self.conns.values():       # one entry per person, even with two windows open
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
        await self.broadcast({"t": "qte", "q": frame})

    async def qte_end(self, qte_id: str) -> None:
        if self.qtes.pop(qte_id, None) is not None:
            for conn in self.conns.values():
                conn.presses.pop(qte_id, None)
            await self.broadcast({"t": "qte_end", "id": qte_id})
