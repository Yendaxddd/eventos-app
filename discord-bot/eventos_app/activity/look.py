"""The event's look: a style the game masters choose for everybody (a theme, an accent, corners, a background, a typeface and a way of
drawing panels). Each player sees it while their setting «follow the event's style» is on, which it is until they pick their own look.

`gm.look` reads it, `gm.look_set` changes it (box «Dirigir en vivo»), and every screen hears `{"t": "look"}` at once."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .hub import Conn, RpcError
from .prefs import sanitize

log = logging.getLogger("eventos_app.activity")

LOOK_KEYS = ("theme", "accent", "accentColor", "baseColor", "corners", "bg", "font", "surface")


def clean_look(raw: Any) -> dict | None:
    """Only the look's own settings, each checked as a player's own would be; None (or an empty dict) means «no event style»."""
    if not isinstance(raw, dict) or not raw:
        return None
    full = sanitize({k: raw[k] for k in LOOK_KEYS if k in raw})
    return {k: full[k] for k in LOOK_KEYS}


class LookBook:
    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.value: dict | None = None
        self.name = ""
        if path is not None and path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                self.value = clean_look(raw.get("look")) if isinstance(raw, dict) else None
                self.name = str(raw.get("name") or "")[:60] if isinstance(raw, dict) else ""
            except (OSError, ValueError):
                log.warning("could not read %s", path)

    def set(self, raw: Any, name: Any = "") -> dict | None:
        self.value = clean_look(raw)
        self.name = str(name or "")[:60] if self.value else ""
        if self.path is not None:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.path.with_suffix(".tmp")
                tmp.write_text(json.dumps({"look": self.value, "name": self.name}, ensure_ascii=False), encoding="utf-8")
                tmp.replace(self.path)
            except OSError:
                log.warning("could not save %s", self.path)
        return self.value


class LookRpc:
    """Mixed into ActivityBridge; relies on `self.look` (LookBook), `self.hub`, `self._gm` and `self.gm.log`."""

    async def rpc_gm_look(self, conn: Conn, args: dict):
        await self._gm(conn)
        return {"look": self.look.value, "name": self.look.name}

    async def rpc_gm_look_set(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        look = args.get("look")
        if look is not None and not isinstance(look, dict):
            raise RpcError("Ese estilo no es válido.")
        value = self.look.set(look, args.get("name"))
        await self.hub.broadcast({"t": "look", "look": value})
        self.gm.log.add(actor, f"Estilo del evento: {self.look.name or 'personalizado'}" if value else "Quitó el estilo del evento (cada uno ve el suyo)")
        return {"look": value, "name": self.look.name}
