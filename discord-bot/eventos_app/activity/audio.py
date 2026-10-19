"""Sound for the event: a library of sounds and music the game masters upload, the automatic cues (a sound for «Black Flash», for «the boss
falls»...) and the music that plays for everybody at once.

The server decides what plays and when; each player's screen only plays it (with their own volume). Music is started at a moment of the
server's clock, so somebody who comes in late hears the same point of the same track as the rest.
"""
from __future__ import annotations

import json
import logging
import re
import secrets
from pathlib import Path
from typing import Any, Callable

from .hub import Conn, Hub, RpcError
from .media import AUDIO, MediaError, MediaStore

log = logging.getLogger("eventos_app.activity")

KINDS = {"sfx": "Efecto", "music": "Música", "voice": "Voz"}
MAX_NAME = 60
MAX_SOUNDS = 400
SCOPES = ("all", "target")

# event id -> (what the game masters read, who hears it unless they choose otherwise)
EVENTS: dict[str, tuple[str, str]] = {
    "qte_start": ("Empieza un QTE (cualquiera)", "target"),
    "qte_easy": ("QTE fácil", "target"), "qte_medium": ("QTE medio", "target"), "qte_hard": ("QTE difícil", "target"),
    "qte_impossible": ("QTE imposible", "target"),
    "qte_group": ("QTE grupal", "all"), "qte_combo": ("QTE combo", "target"), "qte_direction": ("QTE de dirección", "target"),
    "qte_bf_chain": ("Cadena de Black Flash (la ventana)", "target"), "qte_fake": ("QTE falso", "target"),
    "black_flash": ("¡Black Flash!", "all"), "chain_max": ("Cadena máxima de Black Flash", "all"), "combo_done": ("Combo completado", "target"),
    "fake_fail": ("Alguien cae en un QTE falso", "all"), "group_done": ("Termina un QTE grupal", "all"),
    "domain_cast": ("Alguien empieza una expansión de dominio", "all"), "domain": ("Expansión de dominio completada", "all"),
    "boss_domain": ("El jefe despliega su dominio", "all"), "boss_spawn": ("Aparece un jefe", "all"), "boss_defeated": ("El jefe cae", "all"),
    "fight_start": ("Empieza el combate", "all"), "fight_end": ("Termina el combate", "all"), "player_down": ("Cae un jugador", "all"),
    "checkpoint": ("Checkpoint (curación de todos)", "all"),
    # what happens to each player in a fight: the answers, the blows and the powers
    "evade_ok": ("Esquive logrado", "target"), "parry_ok": ("Parry logrado", "target"), "counter": ("Contraataque", "target"),
    "rescue_ok": ("Rescate logrado", "target"), "qte_fail": ("Fallas un QTE (tarde o a destiempo)", "target"),
    "combo_step": ("Paso de combo acertado", "target"),
    "player_hit": ("Un jugador recibe daño", "target"), "low_hp": ("Vida baja (queda un cuarto)", "target"), "heal": ("Un jugador se cura", "target"),
    "boss_hit": ("El jefe recibe daño", "all"),
    "power_used": ("Alguien usa un poder (cualquiera)", "all"), "power_1": ("Se usa un Poder 1", "all"), "power_2": ("Se usa un Poder 2", "all"),
}
PHASE_EVENTS = ("fight_start", "boss_spawn", "boss_domain", "boss_defeated", "fight_end")      # the moments of a fight that can change the music by themselves
PHASE_MODES = ("music", "stop")
QTE_FALLBACK = ("qte_start",)          # a QTE with no cue of its own uses this one


def _clean_name(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\x00", "")).strip()[:MAX_NAME]


def _percent(value: Any, default: int = 100) -> int:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return default
    return max(0, min(100, number))


def _people(data: dict) -> set[int] | None:
    """The players an event is about: `user`, or `users`; None when it does not say."""
    found: set[int] = set()
    one = data.get("user")
    if isinstance(one, int) and not isinstance(one, bool):
        found.add(one)
    many = data.get("users")
    if isinstance(many, (list, tuple, set)):
        found.update(int(u) for u in many if isinstance(u, int) and not isinstance(u, bool))
    return found or None


class AudioLibrary:
    """The sounds, the cues bound to events, and what is playing as music. Kept in one JSON file; the audio itself lives in the MediaStore."""

    def __init__(self, store: MediaStore | None, path: Path | None = None) -> None:
        self.store = store
        self.path = path
        self.sounds: dict[str, dict] = {}
        self.cues: dict[str, dict] = {}
        self.phases: dict[str, dict] = {}          # event -> {"mode": "music" | "stop", "sound", "volume"}: the music follows the fight
        self._load()

    # ---- keeping ----------------------------------------------------------------------------------------------------------
    def _load(self) -> None:
        if self.path is None or not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            log.warning("could not read %s", self.path)
            return
        if not isinstance(raw, dict):
            return
        for item in raw.get("sounds") or []:
            sound = self._sound_from(item)
            if sound is not None:
                self.sounds[sound["id"]] = sound
        for event, cue in (raw.get("cues") or {}).items():
            clean = self._cue_from(event, cue)
            if clean is not None:
                self.cues[event] = clean
        for event, phase in (raw.get("phases") or {}).items():
            clean = self._phase_from(event, phase)
            if clean is not None:
                self.phases[event] = clean

    def save(self) -> None:
        if self.path is None:
            return
        try:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"sounds": list(self.sounds.values()), "cues": self.cues, "phases": self.phases}, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            log.warning("could not save %s", self.path)

    def _sound_from(self, item: Any) -> dict | None:
        if not isinstance(item, dict):
            return None
        sid, file = str(item.get("id") or ""), str(item.get("file") or "")
        parts = file.split("/")
        if not re.fullmatch(r"[0-9a-f]{8}", sid) or len(parts) != 3 or parts[:2] != ["files", AUDIO]:
            return None
        return {"id": sid, "name": _clean_name(item.get("name")) or "Sin nombre", "kind": item.get("kind") if item.get("kind") in KINDS else "sfx",
                "file": file, "volume": _percent(item.get("volume")), "loop": bool(item.get("loop")), "size": int(item.get("size") or 0)}

    def _cue_from(self, event: str, cue: Any) -> dict | None:
        if event not in EVENTS or not isinstance(cue, dict) or str(cue.get("sound") or "") not in self.sounds:
            return None
        return {"sound": str(cue["sound"]), "volume": _percent(cue.get("volume")),
                "scope": cue.get("scope") if cue.get("scope") in SCOPES else EVENTS[event][1], "enabled": bool(cue.get("enabled", True))}

    def _phase_from(self, event: str, phase: Any) -> dict | None:
        if event not in PHASE_EVENTS or not isinstance(phase, dict) or phase.get("mode") not in PHASE_MODES:
            return None
        if phase["mode"] == "music" and str(phase.get("sound") or "") not in self.sounds:
            return None
        return {"mode": phase["mode"], "sound": str(phase.get("sound") or "") if phase["mode"] == "music" else "", "volume": _percent(phase.get("volume"))}

    # ---- the sounds -------------------------------------------------------------------------------------------------------
    def public(self) -> list[dict]:
        return [dict(s) for s in self.sounds.values()]

    def get(self, sound_id: Any) -> dict | None:
        return self.sounds.get(str(sound_id))

    def add(self, filename: str, data: bytes, kind: str = "sfx") -> dict:
        if self.store is None:
            raise RpcError("Esta Actividad no puede guardar archivos en este PC.")
        if len(self.sounds) >= MAX_SOUNDS:
            raise RpcError(f"La biblioteca ya tiene {MAX_SOUNDS} sonidos: borra los que no uses.")
        if kind not in KINDS:
            kind = "music" if len(data) > 1_500_000 else "sfx"
        try:
            stored = self.store.save(AUDIO, data)
        except MediaError as exc:
            raise RpcError(str(exc)) from exc
        stem = _clean_name(re.sub(r"\.[A-Za-z0-9]{2,5}$", "", filename or "")) or "Sonido"
        sound = {"id": secrets.token_hex(4), "name": stem, "kind": kind, "file": stored.path, "volume": 100, "loop": kind == "music", "size": stored.size}
        self.sounds[sound["id"]] = sound
        self.save()
        return dict(sound)

    def update(self, sound_id: Any, fields: dict) -> dict:
        sound = self.get(sound_id)
        if sound is None:
            raise RpcError("Ese sonido ya no está en la biblioteca.")
        if "name" in fields:
            name = _clean_name(fields["name"])
            if not name:
                raise RpcError("El sonido necesita un nombre.")
            sound["name"] = name
        if "kind" in fields:
            if fields["kind"] not in KINDS:
                raise RpcError("Ese tipo de sonido no existe.")
            sound["kind"] = fields["kind"]
        if "volume" in fields:
            sound["volume"] = _percent(fields["volume"], sound["volume"])
        if "loop" in fields:
            sound["loop"] = bool(fields["loop"])
        self.save()
        return dict(sound)

    def delete(self, sound_id: Any) -> dict:
        sound = self.sounds.pop(str(sound_id), None)
        if sound is None:
            raise RpcError("Ese sonido ya no está en la biblioteca.")
        for event in [e for e, cue in self.cues.items() if cue["sound"] == sound["id"]]:
            del self.cues[event]
        for event in [e for e, phase in self.phases.items() if phase["sound"] == sound["id"]]:
            del self.phases[event]
        if self.store is not None and not any(s["file"] == sound["file"] for s in self.sounds.values()):
            _, name = sound["file"].rsplit("/", 1)
            self.store.delete(AUDIO, name)
        self.save()
        return sound

    # ---- the cues ---------------------------------------------------------------------------------------------------------
    def set_cue(self, event: Any, sound_id: Any, volume: Any = 100, scope: Any = None, enabled: Any = True) -> dict:
        event = str(event)
        if event not in EVENTS:
            raise RpcError("Ese aviso no existe.")
        if self.get(sound_id) is None:
            raise RpcError("Elige un sonido de la biblioteca.")
        cue = self._cue_from(event, {"sound": str(sound_id), "volume": volume, "scope": scope, "enabled": enabled})
        self.cues[event] = cue
        self.save()
        return dict(cue)

    def clear_cue(self, event: Any) -> None:
        if str(event) in self.cues:
            del self.cues[str(event)]
            self.save()

    # ---- the music of a fight ----------------------------------------------------------------------------------------------
    def set_phase(self, event: Any, mode: Any, sound_id: Any = None, volume: Any = 100) -> dict:
        event = str(event)
        if event not in PHASE_EVENTS:
            raise RpcError("Ese momento no puede cambiar la música.")
        if mode == "music" and self.get(sound_id) is None:
            raise RpcError("Elige una pista de la biblioteca.")
        phase = self._phase_from(event, {"mode": mode, "sound": sound_id, "volume": volume})
        if phase is None:
            raise RpcError("Esa acción no existe.")
        self.phases[event] = phase
        self.save()
        return dict(phase)

    def clear_phase(self, event: Any) -> None:
        if self.phases.pop(str(event), None) is not None:
            self.save()

    def cue_for(self, event: str, data: dict) -> tuple[str, dict] | None:
        """(event whose cue plays, the cue) for something that happened: a QTE looks for its own mode and difficulty first."""
        chain = [event]
        if event == "power_used":                      # the slot's own cue first, then «any power»
            chain = [f"power_{data.get('slot')}", "power_used"]
        if event == "qte":
            chain = [f"qte_{data.get('mode')}", f"qte_{data.get('difficulty')}", *QTE_FALLBACK]
        for name in chain:
            cue = self.cues.get(name)
            if cue is not None and cue["enabled"]:
                return name, cue
        return None


class AudioDirector:
    """Sends the sounds to the players' screens: cues when the game says something happened, and what the game masters play by hand."""

    def __init__(self, hub: Hub, library: AudioLibrary) -> None:
        self.hub, self.library = hub, library
        self.music: dict | None = None       # {"sound": {...}, "startedAt": server ms, "volume": 0-100, "loop": bool}
        self.send_to: Callable = hub.send

    # ---- what a player gets when they come in -----------------------------------------------------------------------------
    def welcome(self) -> dict:
        return {"library": self.library.public(), "music": self.music_frame()}

    def music_frame(self) -> dict | None:
        return None if self.music is None else {**self.music, "now": self.hub.now_ms()}

    # ---- playing ---------------------------------------------------------------------------------------------------------
    def _play_frame(self, sound: dict, volume: int = 100) -> dict:
        return {"t": "audio", "op": "play", "sound": sound, "volume": max(0, min(100, round(volume * sound["volume"] / 100))), "at": self.hub.now_ms()}

    async def play(self, sound_id: Any, volume: int = 100, user_ids: set[int] | None = None) -> dict:
        """One sound, now, for everybody (or for the given people)."""
        sound = self.library.get(sound_id)
        if sound is None:
            raise RpcError("Ese sonido ya no está en la biblioteca.")
        await self._send(self._play_frame(sound, _percent(volume)), user_ids)
        return sound

    async def _send(self, frame: dict, user_ids: set[int] | None = None) -> int:
        sent = 0
        for conn in list(self.hub.conns.values()):
            if user_ids is not None and conn.user_id not in user_ids:
                continue
            if await self.send_to(conn, frame):
                sent += 1
        return sent

    async def stop_all(self) -> None:
        await self.hub.broadcast({"t": "audio", "op": "stop"})

    async def start_music(self, sound_id: Any, volume: int = 100, loop: bool | None = None) -> dict:
        sound = self.library.get(sound_id)
        if sound is None:
            raise RpcError("Ese sonido ya no está en la biblioteca.")
        self.music = {"sound": sound, "startedAt": self.hub.now_ms(), "volume": _percent(volume), "loop": sound["loop"] if loop is None else bool(loop)}
        await self.hub.broadcast({"t": "audio", "op": "music", "music": self.music_frame()})
        return self.music

    async def stop_music(self) -> None:
        self.music = None
        await self.hub.broadcast({"t": "audio", "op": "music", "music": None})

    async def set_music_volume(self, volume: Any) -> None:
        if self.music is None:
            raise RpcError("No hay música sonando.")
        self.music["volume"] = _percent(volume)
        await self.hub.broadcast({"t": "audio", "op": "music", "music": self.music_frame(), "keep": True})      # same track, new volume

    async def announce_library(self) -> None:
        await self.hub.broadcast({"t": "audio", "op": "library", "sounds": self.library.public()})

    # ---- cues ------------------------------------------------------------------------------------------------------------
    async def dispatch(self, event: str, data: dict | None = None) -> bool:
        """Something happened in the game: play the cue bound to it, if there is one. `data["user"]` is who it is about."""
        data = data or {}
        phase = self.library.phases.get(event)
        if phase is not None:                                         # the music follows the fight
            try:
                if phase["mode"] == "stop":
                    if self.music is not None:
                        await self.stop_music()
                else:
                    await self.start_music(phase["sound"], phase["volume"])
            except RpcError:
                pass
        found = self.library.cue_for(event, data)
        if found is None:
            return bool(phase)
        _, cue = found
        sound = self.library.get(cue["sound"])
        if sound is None:
            return False
        who = _people(data) if cue["scope"] == "target" else None          # nobody known (a fake QTE has no target): everybody hears it
        await self._send(self._play_frame(sound, cue["volume"]), who)
        return True
