"""What every part of the game-master panel shares: the change log, number checking and fire-and-forget tasks."""
from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import time
from collections import deque
from pathlib import Path
from typing import Any

from ..hub import RpcError

log = logging.getLogger("eventos_app.activity")

DIFFICULTIES = ("easy", "medium", "hard", "impossible")
DIFFICULTY_ES = {"easy": "fácil", "medium": "media", "hard": "difícil", "impossible": "imposible"}
LOG_KEEP = 300


def number(value: Any, name: str, lo: float, hi: float, *, integer: bool = False) -> float | int:
    """A number typed by a game master, forced to be one and inside its limits. Raises RpcError saying which one is wrong."""
    if isinstance(value, bool):
        raise RpcError(f"«{name}» debe ser un número.")
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise RpcError(f"«{name}» debe ser un número.") from None
    if not math.isfinite(parsed):
        raise RpcError(f"«{name}» debe ser un número.")
    if integer:
        if parsed != int(parsed):
            raise RpcError(f"«{name}» debe ser un número entero.")
        parsed = int(parsed)
    if not lo <= parsed <= hi:
        shown = (lambda v: f"{v:g}".replace(".", ","))
        raise RpcError(f"«{name}» va de {shown(lo)} a {shown(hi)}.")
    return parsed


def https_url(value: Any, *, required: bool = False) -> str | None:
    """A picture's address: https only (it ends up in Discord embeds and in the players' screens)."""
    raw = str(value or "").strip()
    if not raw:
        if required:
            raise RpcError("Falta el enlace de la imagen.")
        return None
    if len(raw) > 600 or not re.fullmatch(r"https://[^\s<>\"']+", raw):
        raise RpcError("La imagen debe ser un enlace https válido.")
    return raw


def finite(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def text(value: Any, limit: int) -> str:
    return "" if value is None else str(value)[:limit]


def spawn(coro, what: str) -> asyncio.Task | None:
    """Start something the bot does at its own pace (sending messages can wait for Discord's limits): the panel answers at once."""
    async def guarded():
        try:
            await coro
        except Exception:  # noqa: BLE001 - the bot's log is where the details go
            log.exception("could not %s", what)
    try:
        return asyncio.get_running_loop().create_task(guarded())
    except RuntimeError:
        coro.close()
        return None


class GmLog:
    """Who changed what, newest last: kept in memory and in a file, so the team can see what happened during an event."""

    def __init__(self, path: Path | None = None, keep: int = LOG_KEEP) -> None:
        self.path = path
        self.entries: deque[dict] = deque(maxlen=keep)
        if path is not None and path.exists():
            try:
                for line in path.read_text(encoding="utf-8").splitlines()[-keep:]:
                    try:
                        entry = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(entry, dict) and "action" in entry:
                        self.entries.append(entry)
            except OSError:
                log.warning("could not read %s", path)

    def add(self, who: str, action: str) -> dict:
        entry = {"ts": int(time.time() * 1000), "who": text(who, 60), "action": text(action, 300)}
        self.entries.append(entry)
        log.info("GM %s: %s", entry["who"], entry["action"])
        if self.path is not None:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
            except OSError:
                log.warning("could not write %s", self.path)
        return entry

    def recent(self, count: int = 100) -> list[dict]:
        return list(self.entries)[-count:][::-1]
