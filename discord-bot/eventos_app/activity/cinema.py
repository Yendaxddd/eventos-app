"""Cinematics: a script of texts, sounds and pictures that happen at set moments, played on every player's screen at once.

A cinematic is a list of steps, each at a second of the timeline:

    text    a caption (who says it, what, for how long, how it appears)
    audio   a library sound (once), music that starts, or «stop the music»
    image   a picture on screen for a while
    scene   the background (a colour, a picture, or nothing) from then on
    effect  a flash, a shake or a fade to black
    post    a message the bot writes in the event channel

The game masters write them in the panel, play them by hand or bind them to what happens in the game («when the boss appears»). The server
only keeps the scripts, starts and stops them (and writes the `post` steps in the channel at their moment); each screen plays the rest by
its own clock, started at a moment of the server's, so they stay together.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import secrets
from pathlib import Path
from typing import Any, Awaitable, Callable

from .audio import EVENTS, AudioLibrary
from .fx import sanitize as fx_sanitize
from .hub import Hub, RpcError

log = logging.getLogger("eventos_app.activity")

MAX_CINEMAS = 80
MAX_STEPS = 200
MAX_TIME = 3600.0                      # an hour of timeline is already far more than anybody writes
MAX_DURATION = 600.0
MAX_TEXT = 600
STEP_TYPES = ("text", "audio", "image", "scene", "effect", "vfx", "post")
TEXT_EFFECTS = ("type", "fade", "shake")
AUDIO_MODES = ("play", "music", "stop_music")
EFFECTS = ("flash", "shake", "blackout")
SIZES = ("normal", "big")
_NOISY = {"evade_ok", "parry_ok", "counter", "rescue_ok", "combo_step", "player_hit", "heal", "boss_hit", "power_1", "power_2", "mob_attack", "mob_hit"}
TRIGGER_EVENTS = tuple(e for e in EVENTS if not e.startswith("qte_") and e not in _NOISY)        # cinematics start on what happens, not on every QTE or blow
BOSS_EVENTS = ("boss_spawn", "boss_defeated", "boss_domain")           # the events that say which boss they are about
_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
_IMAGE = re.compile(r"^files/images/[0-9a-f]{24}\.(png|jpg|gif|webp)$")


def _line(value: Any, limit: int) -> str:
    return re.sub(r"[ \t]+", " ", str(value or "").replace("\x00", "")).strip()[:limit]


def _body(value: Any, limit: int = MAX_TEXT) -> str:
    return str(value or "").replace("\x00", "").replace("\r\n", "\n").strip()[:limit]


def _seconds(value: Any, what: str, lo: float, hi: float, default: float | None = None) -> float:
    if value in (None, "") and default is not None:
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise RpcError(f"{what}: escribe un número de segundos.") from None
    if number != number or number < lo or number > hi:
        raise RpcError(f"{what}: debe estar entre {lo:g} y {hi:g} segundos.")
    return round(number, 2)


def _color(value: Any, what: str, default: str | None = None) -> str | None:
    if value in (None, ""):
        return default
    if not _COLOR.match(str(value)):
        raise RpcError(f"{what}: el color debe ser como #ff8800.")
    return str(value).lower()


def _image(value: Any, what: str) -> str | None:
    if value in (None, ""):
        return None
    if not _IMAGE.match(str(value)):
        raise RpcError(f"{what}: esa imagen no es de la biblioteca (súbela desde el editor).")
    return str(value)


def _percent(value: Any, default: int = 100) -> int:
    try:
        return max(0, min(100, int(round(float(value)))))
    except (TypeError, ValueError):
        return default


def text_duration(text: str) -> float:
    """How long a caption stays when its writer did not say: time to read it."""
    return round(max(2.0, min(20.0, len(text) / 14.0 + 1.0)), 2)


def clean_step(raw: Any, number: int, library: AudioLibrary | None) -> dict:
    """One step, checked. Raises RpcError saying which step and what is wrong."""
    where = f"Paso {number}"
    if not isinstance(raw, dict):
        raise RpcError(f"{where}: no es un paso válido.")
    kind = raw.get("type")
    if kind not in STEP_TYPES:
        raise RpcError(f"{where}: el tipo «{kind}» no existe.")
    step: dict = {"type": kind, "at": _seconds(raw.get("at"), f"{where}, momento", 0, MAX_TIME, 0.0)}
    if kind == "text":
        text = _body(raw.get("text"))
        if not text:
            raise RpcError(f"{where}: el texto está vacío.")
        step.update(text=text, speaker=_line(raw.get("speaker"), 60), avatar=_image(raw.get("avatar"), f"{where}, retrato"),
                    duration=_seconds(raw.get("duration"), f"{where}, duración", 0.5, MAX_DURATION, text_duration(text)),
                    effect=raw.get("effect") if raw.get("effect") in TEXT_EFFECTS else "type", color=_color(raw.get("color"), f"{where}, color"),
                    size=raw.get("size") if raw.get("size") in SIZES else "normal")
    elif kind == "audio":
        mode = raw.get("mode") if raw.get("mode") in AUDIO_MODES else "play"
        step["mode"] = mode
        if mode != "stop_music":
            sound = str(raw.get("sound") or "")
            if not sound:
                raise RpcError(f"{where}: elige un sonido de la biblioteca.")
            if library is not None and library.get(sound) is None:
                raise RpcError(f"{where}: ese sonido ya no está en la biblioteca.")
            step.update(sound=sound, volume=_percent(raw.get("volume")))
    elif kind == "image":
        image = _image(raw.get("image"), f"{where}, imagen")
        if image is None:
            raise RpcError(f"{where}: elige una imagen.")
        step.update(image=image, duration=_seconds(raw.get("duration"), f"{where}, duración", 0.5, MAX_DURATION, 4.0),
                    position=raw.get("position") if raw.get("position") in ("center", "left", "right") else "center")
    elif kind == "scene":
        step.update(color=_color(raw.get("color"), f"{where}, color", "#000000"), image=_image(raw.get("image"), f"{where}, imagen"),
                    dim=_percent(raw.get("dim"), 40))
    elif kind == "effect":
        step.update(effect=raw.get("effect") if raw.get("effect") in EFFECTS else "flash", color=_color(raw.get("color"), f"{where}, color", "#ffffff"),
                    duration=_seconds(raw.get("duration"), f"{where}, duración", 0.1, 30.0, 0.6))
    elif kind == "vfx":                      # a visual effect of the powers' kind (fx.py): a preset with its colour, strength and speed, and an optional banner
        look = fx_sanitize({k: raw.get(k) for k in ("preset", "color", "intensity", "speed", "banner")})
        step.update(preset=look["preset"], color=look["color"], intensity=look["intensity"], speed=look["speed"], banner=look["banner"],
                    duration=_seconds(raw.get("duration"), f"{where}, duración", 0.1, 30.0, 1.5))
    else:                                    # post
        text = _body(raw.get("text"), 1500)
        if not text:
            raise RpcError(f"{where}: el mensaje está vacío.")
        step["text"] = text
    return step


def clean_cinema(raw: Any, library: AudioLibrary | None, known_id: str | None = None) -> dict:
    """A whole cinematic, checked: its steps are put in time order and its length worked out. Raises RpcError saying what is wrong."""
    if not isinstance(raw, dict):
        raise RpcError("La cinemática no es válida.")
    name = _line(raw.get("name"), 80)
    if not name:
        raise RpcError("La cinemática necesita un nombre.")
    steps_raw = raw.get("steps")
    if not isinstance(steps_raw, list) or not steps_raw:
        raise RpcError("Añade al menos un paso a la cinemática.")
    if len(steps_raw) > MAX_STEPS:
        raise RpcError(f"Una cinemática puede tener hasta {MAX_STEPS} pasos.")
    steps = [clean_step(step, i, library) for i, step in enumerate(steps_raw, start=1)]
    steps.sort(key=lambda s: s["at"])
    triggers = []
    for event in raw.get("triggers") or []:
        if event in TRIGGER_EVENTS and event not in triggers:
            triggers.append(event)
    length = max(s["at"] + (s.get("duration") or 0) for s in steps)
    return {"id": known_id or str(raw.get("id") or "") or secrets.token_hex(4), "name": name, "steps": steps, "triggers": triggers,
            "boss": _line(raw.get("boss"), 80), "bg": _color(raw.get("bg"), "Fondo", "#000000"), "bars": bool(raw.get("bars", True)), "skippable": bool(raw.get("skippable", True)),
            "duration": round(length + 1.0, 2)}


class CinemaBook:
    """The scripts, in one JSON file."""

    def __init__(self, path: Path | None, library: AudioLibrary | None = None) -> None:
        self.path = path
        self.library = library
        self.items: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if self.path is None or not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            log.warning("could not read %s", self.path)
            return
        for item in (raw.get("cinemas") if isinstance(raw, dict) else None) or []:
            try:
                cinema = clean_cinema(item, None, known_id=str(item.get("id") or ""))
            except (RpcError, AttributeError):
                continue                       # a script edited by hand that no longer makes sense is left out, not fatal
            if re.fullmatch(r"[0-9a-f]{8}", cinema["id"]):
                self.items[cinema["id"]] = cinema

    def save(self) -> None:
        if self.path is None:
            return
        try:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"cinemas": list(self.items.values())}, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            log.warning("could not save %s", self.path)

    def listing(self) -> list[dict]:
        return [dict(c) for c in self.items.values()]

    def get(self, cinema_id: Any) -> dict | None:
        return self.items.get(str(cinema_id))

    def put(self, raw: Any) -> dict:
        known = str(raw.get("id") or "") if isinstance(raw, dict) else ""
        if known not in self.items:
            known = ""                        # an id this book never gave: it becomes a new one
            if isinstance(raw, dict):
                raw = {**raw, "id": ""}
        if not known and len(self.items) >= MAX_CINEMAS:
            raise RpcError(f"Ya hay {MAX_CINEMAS} cinemáticas: borra las que no uses.")
        cinema = clean_cinema(raw, self.library, known_id=known or None)
        while not known and cinema["id"] in self.items:
            cinema["id"] = secrets.token_hex(4)
        self.items[cinema["id"]] = cinema
        self.save()
        return dict(cinema)

    def duplicate(self, cinema_id: Any) -> dict:
        original = self.get(cinema_id)
        if original is None:
            raise RpcError("Esa cinemática ya no existe.")
        return self.put({**original, "id": "", "name": f"{original['name']} (copia)"[:80]})

    def delete(self, cinema_id: Any) -> dict:
        cinema = self.items.pop(str(cinema_id), None)
        if cinema is None:
            raise RpcError("Esa cinemática ya no existe.")
        self.save()
        return cinema


class CinemaDirector:
    """Starts and stops a cinematic for everybody, writes its `post` steps in the channel at their moment, and starts the ones bound to events."""

    def __init__(self, hub: Hub, book: CinemaBook, post: Callable[[str], Awaitable[Any]] | None = None) -> None:
        self.hub, self.book, self.post = hub, book, post
        self.run: dict | None = None                    # {"id", "cinema", "startedAt"}
        self._tasks: list[asyncio.Task] = []
        self.on_event_enabled = True

    def current(self) -> dict | None:
        """What a player coming in now needs to join the running cinematic, or None."""
        if self.run is None:
            return None
        if self.hub.now_ms() - self.run["startedAt"] > self.run["cinema"]["duration"] * 1000:
            self.run = None
            return None
        return {**self.run, "now": self.hub.now_ms()}

    async def play(self, cinema_id: Any) -> dict:
        cinema = self.book.get(cinema_id)
        if cinema is None:
            raise RpcError("Esa cinemática ya no existe.")
        await self.stop(announce=False)
        self.run = {"id": cinema["id"], "cinema": cinema, "startedAt": self.hub.now_ms()}
        await self.hub.broadcast({"t": "cine", "op": "start", "run": self.current()})
        for step in cinema["steps"]:
            if step["type"] == "post" and self.post is not None:
                self._tasks.append(asyncio.get_running_loop().create_task(self._post_at(step["at"], step["text"], cinema["id"])))
        self._tasks.append(asyncio.get_running_loop().create_task(self._finish_at(cinema["duration"], cinema["id"])))
        return cinema

    async def _post_at(self, at: float, text: str, cinema_id: str) -> None:
        try:
            await asyncio.sleep(at)
            if self.run is not None and self.run["id"] == cinema_id and self.post is not None:
                await self.post(text)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - a message that cannot be sent must not stop the cinematic
            log.exception("could not write a cinematic's message in the channel")

    async def _finish_at(self, seconds: float, cinema_id: str) -> None:
        try:
            await asyncio.sleep(seconds)
        except asyncio.CancelledError:
            return
        if self.run is not None and self.run["id"] == cinema_id:
            self.run = None

    async def stop(self, announce: bool = True) -> bool:
        for task in self._tasks:
            task.cancel()
        self._tasks = []
        was = self.run is not None
        self.run = None
        if announce and was:
            await self.hub.broadcast({"t": "cine", "op": "stop"})
        return was

    async def on_event(self, event: str, data: dict | None = None) -> bool:
        """Something happened in the game: start the first cinematic bound to it (unless one is already playing)."""
        if not self.on_event_enabled or self.current() is not None:
            return False
        who = str((data or {}).get("name") or "").strip().casefold()
        candidates = [c for c in self.book.items.values() if event in c["triggers"]]
        # one made for this boss wins over one for any boss
        candidates.sort(key=lambda c: 0 if c.get("boss") and event in BOSS_EVENTS else 1)
        for cinema in candidates:
            wanted = str(cinema.get("boss") or "").strip().casefold()
            if wanted and event in BOSS_EVENTS and wanted != who:
                continue
            await self.play(cinema["id"])
            return True
        return False
