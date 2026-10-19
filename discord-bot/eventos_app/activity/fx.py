"""Visual effects for powers and game events: a *binding* says which preset plays on every screen, in what colour, how strong, how fast and
how late, with an optional banner and sound. The game masters bind them in the panel's Effects tab; the Activity draws them (the presets
themselves live in the client: activity_client/src/fx-model.js, and test/fx-cases.json keeps both sides agreeing on what a binding means).

Kept in one JSON file: `{"events": {event: binding}, "powers": {"Character|1": binding}, "defaults": true}`. A power with no binding of its own
uses the one of its slot's event, then of «any power», then (when `defaults` is on) a look by its type."""
from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any

from .audio import EVENTS, AudioDirector
from .hub import Hub, RpcError

log = logging.getLogger("eventos_app.activity")

PRESET_IDS = ("slash", "explosion", "rayo", "curacion", "escudo", "carga", "dominio", "impacto", "pulso", "ninguno")
DEFAULT_BY_TYPE = {"destructive": "explosion", "support": "curacion", "defend": "escudo", "build": "carga", "control": "rayo"}
DEFAULT_BINDING = {"preset": "impacto", "color": "", "intensity": 100, "speed": 100, "delay": 0, "banner": "", "name": False, "sound": "", "scope": "all"}
RANGES = {"intensity": (25, 200), "speed": (50, 200), "delay": (0, 5000)}
BINDABLE = tuple(e for e in EVENTS if not e.startswith("qte_"))        # a QTE has its own look; the rest of what happens can be given one
MAX_BINDINGS = 400
_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
_SOUND = re.compile(r"^[0-9a-f]{1,32}$")


def sanitize(raw: Any) -> dict:
    """A binding as the client sends it, every field forced into range (the same rules as the client's `sanitizeBinding`)."""
    out = dict(DEFAULT_BINDING)
    if not isinstance(raw, dict):
        return out
    if raw.get("preset") in PRESET_IDS:
        out["preset"] = raw["preset"]
    if isinstance(raw.get("color"), str) and _COLOR.match(raw["color"]):
        out["color"] = raw["color"].lower()
    for key, (low, high) in RANGES.items():
        value = raw.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value == value and abs(value) != float("inf"):
            out[key] = int(round(min(high, max(low, value))))
    if isinstance(raw.get("banner"), str):
        out["banner"] = re.sub(r"[\x00-\x1f]", "", raw["banner"]).strip()[:40]
    if isinstance(raw.get("name"), bool):
        out["name"] = raw["name"]
    if isinstance(raw.get("sound"), str) and _SOUND.match(raw["sound"]):
        out["sound"] = raw["sound"]
    if raw.get("scope") in ("all", "target"):
        out["scope"] = raw["scope"]
    return out


def is_empty(binding: dict) -> bool:
    return binding["preset"] == "ninguno" and not binding["banner"] and not binding["name"] and not binding["sound"]


def power_key(character: Any, slot: Any) -> str:
    return f"{str(character)[:80]}|{int(slot) if str(slot).isdigit() else 0}"


class FxBook:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self.events: dict[str, dict] = {}
        self.powers: dict[str, dict] = {}
        self.defaults = True
        if path is not None and path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    for event, binding in (raw.get("events") or {}).items():
                        if event in BINDABLE:
                            self.events[event] = sanitize(binding)
                    for key, binding in list((raw.get("powers") or {}).items())[:MAX_BINDINGS]:
                        if isinstance(key, str) and re.fullmatch(r".{1,80}\|[12]", key):
                            self.powers[key] = sanitize(binding)
                    self.defaults = raw.get("defaults") is not False
            except (OSError, ValueError, AttributeError):
                log.warning("could not read %s", path)

    def save(self) -> None:
        if self.path is None:
            return
        try:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"events": self.events, "powers": self.powers, "defaults": self.defaults}, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            log.warning("could not save %s", self.path)

    # ---- changes (checked here; raise RpcError with the reason) ----------------------------------------------------------
    def set_event(self, event: Any, raw: Any, sounds=None) -> dict:
        if str(event) not in BINDABLE:
            raise RpcError("Ese suceso no existe.")
        binding = self._checked(raw, sounds)
        self.events[str(event)] = binding
        self.save()
        return binding

    def set_power(self, character: Any, slot: Any, raw: Any, sounds=None) -> dict:
        if str(slot) not in ("1", "2") or not str(character).strip():
            raise RpcError("Ese poder no existe.")
        if len(self.powers) >= MAX_BINDINGS and power_key(character, slot) not in self.powers:
            raise RpcError("Hay demasiados poderes con efecto propio: quita alguno.")
        binding = self._checked(raw, sounds)
        self.powers[power_key(character, slot)] = binding
        self.save()
        return binding

    def clear_event(self, event: Any) -> None:
        if self.events.pop(str(event), None) is not None:
            self.save()

    def clear_power(self, character: Any, slot: Any) -> None:
        if self.powers.pop(power_key(character, slot), None) is not None:
            self.save()

    def set_defaults(self, on: bool) -> None:
        self.defaults = bool(on)
        self.save()

    @staticmethod
    def _checked(raw: Any, sounds=None) -> dict:
        binding = sanitize(raw)
        if is_empty(binding):
            raise RpcError("Ese efecto no hace nada: elige un efecto visual, un rótulo o un sonido.")
        if binding["sound"] and sounds is not None and sounds(binding["sound"]) is None:
            raise RpcError("Ese sonido ya no está en la biblioteca.")
        return binding

    # ---- what plays for something that happened ------------------------------------------------------------------------
    def binding_for(self, event: str, data: dict) -> dict | None:
        if event == "power_used":
            own = self.powers.get(power_key(data.get("character", ""), data.get("slot", 0)))
            if own is not None:
                return own
            for name in (f"power_{data.get('slot')}", "power_used"):
                if name in self.events:
                    return self.events[name]
            if self.defaults:
                preset = DEFAULT_BY_TYPE.get(str(data.get("type")), "impacto")
                return {**DEFAULT_BINDING, "preset": preset, "name": True}
            return None
        return self.events.get(event)

    def forget_sound(self, sound_id: str) -> None:
        changed = False
        for binding in [*self.events.values(), *self.powers.values()]:
            if binding["sound"] == sound_id:
                binding["sound"] = ""
                changed = True
        if changed:
            self.save()


class FxDirector:
    """Sends the effects to the players' screens when the game says something happened, and plays the sound that goes with them."""

    def __init__(self, hub: Hub, book: FxBook, audio: AudioDirector) -> None:
        self.hub, self.book, self.audio = hub, book, audio

    def frame(self, binding: dict, ctx: dict | None = None) -> dict:
        return {"t": "fx", "fx": binding, "ctx": ctx or {}, "at": self.hub.now_ms()}

    async def dispatch(self, event: str, data: dict | None = None) -> bool:
        data = data or {}
        binding = self.book.binding_for(event, data)
        if binding is None:
            return False
        ctx = {"name": str(data.get("name") or EVENTS.get(event, ("",))[0])[:60], "event": event}
        who = None
        if binding["scope"] == "target" and data.get("user") is not None:
            who = {int(data["user"])}
        await self.show(binding, ctx, who)
        return True

    async def show(self, binding: dict, ctx: dict, user_ids: set[int] | None = None) -> None:
        """The effect on the screens of `user_ids` (everybody when None). The sound waits for the binding's delay, as the picture does."""
        frame = self.frame(binding, ctx)
        for conn in list(self.hub.conns.values()):
            if conn.hidden or (user_ids is not None and conn.user_id not in user_ids):
                continue
            try:
                await self.hub.send(conn, frame)
            except Exception:  # noqa: BLE001
                log.exception("could not send an effect")
        if binding["sound"]:
            asyncio.get_running_loop().create_task(self._sound(binding, user_ids))

    async def _sound(self, binding: dict, user_ids: set[int] | None) -> None:
        try:
            if binding["delay"]:
                await asyncio.sleep(binding["delay"] / 1000)
            await self.audio.play(binding["sound"], 100, user_ids)
        except RpcError:
            pass                                          # the sound left the library
        except Exception:  # noqa: BLE001
            log.exception("could not play the sound of an effect")
