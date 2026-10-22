"""Saving a little later: a file that may change many times a second (each player's settings, a latency result) is written once
things calm down, not on every change. Outside a running event loop (a script, a test) it is written at once."""
from __future__ import annotations

import asyncio

SAVE_DELAY = 1.0


class SavesLater:
    _pending: asyncio.TimerHandle | None = None

    def _save(self) -> None:  # pragma: no cover - each store writes its own file
        raise NotImplementedError

    def _save_soon(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self._save()
            return
        if self._pending is None:
            self._pending = loop.call_later(SAVE_DELAY, self.flush)

    def flush(self) -> None:
        """Write now whatever is waiting (on shutdown)."""
        if self._pending is not None:
            self._pending.cancel()
            self._pending = None
            self._save()
