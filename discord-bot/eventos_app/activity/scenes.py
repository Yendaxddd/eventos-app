"""Scenes: which QTEs come up on their own, for the kind of moment the event is in. A boss fight wants parries, Black Flashes and
counter-attacks; a chase wants dodging, swiping and mashing, and a parry there makes no sense.

A scene is a name, a weight for each kind of QTE and whether a good evade still earns a counter-attack. The game masters keep a few
(the four presets to start with) and switch the active one in the middle of the event. While one is active, every QTE that is not
of a chosen type (the bot's random ones, F9-F12, the batch, a boss ability, a mini enemy's «random» attack, the panel's «individual»)
is drawn from it. With none active, the classic «QTE mode» of the panel decides, as it always did.

The bot reads `app.qte_scene` (the active scene, or None) and calls `app.launch_gesture(kind, difficulty, member)` for the swipe,
drag and tap QTEs, which exist only in the Activity: somebody who is not in it gets the closest QTE of the channel instead.

Ops (box «Evento»): `gm.scenes`, `gm.scene_save`, `gm.scene_delete`, `gm.scene_use`, `gm.scene_presets`. Everybody hears
`{"t": "scene"}` with the name of the active one (and whether parry and counter-attack are on), so nobody parries a chase."""
from __future__ import annotations

import json
import logging
import random
import re
import uuid
from pathlib import Path
from typing import Any

from .hub import Conn, RpcError

log = logging.getLogger("eventos_app.activity")

KINDS = {
    "standard": "Esquivar o parry",      # the bot's normal QTE: evade, or parry for a Black Flash
    "evade": "Solo esquivar",            # the same QTE without the parry (no Black Flash)
    "combo": "Combo",
    "direction": "Dirección",
    "fake": "Trampa",
    "flick": "Deslizar",                 # the Activity's own
    "drag": "Arrastrar",
    "mash": "Machacar",
}
GESTURES = ("flick", "drag", "mash")
MAX_SCENES = 24
PRESETS = [
    {"id": "boss", "name": "Jefe", "color": "#ef4444", "counter": True,
     "note": "Combate contra el jefe: parry, Black Flash y contraataques.",
     "weights": {"standard": 60, "combo": 15, "direction": 15, "fake": 10}},
    {"id": "combat", "name": "Combate", "color": "#f97316", "counter": True,
     "note": "Pelea contra enemigos: de todo un poco.",
     "weights": {"standard": 45, "combo": 5, "direction": 15, "flick": 15, "drag": 10, "mash": 10}},
    {"id": "escape", "name": "Huida", "color": "#22c55e", "counter": False,
     "note": "Escapar: esquivar, deslizar y machacar. Sin parry ni contraataque.",
     "weights": {"evade": 25, "direction": 25, "flick": 25, "mash": 25}},
    {"id": "dodge", "name": "Esquivar", "color": "#38bdf8", "counter": False,
     "note": "Sobrevivir a lo que cae: solo esquivas.",
     "weights": {"evade": 50, "direction": 25, "flick": 25}},
]
_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def clean_scene(raw: Any, sid: str | None = None) -> dict:
    if not isinstance(raw, dict):
        raise RpcError("Esa escena no es válida.")
    name = " ".join(str(raw.get("name") or "").split())[:40]
    if not name:
        raise RpcError("Ponle un nombre a la escena.")
    weights = {}
    src = raw.get("weights") if isinstance(raw.get("weights"), dict) else {}
    for kind in KINDS:
        try:
            value = int(round(float(src.get(kind, 0) or 0)))
        except (TypeError, ValueError):
            value = 0
        weights[kind] = max(0, min(100, value))
    if not any(weights.values()):
        raise RpcError("La escena necesita al menos un tipo de QTE con probabilidad.")
    color = str(raw.get("color") or "")
    return {"id": sid or str(raw.get("id") or "") or uuid.uuid4().hex[:8], "name": name,
            "color": color if _COLOR.match(color) else "#a78bfa", "counter": bool(raw.get("counter", True)),
            "note": " ".join(str(raw.get("note") or "").split())[:160], "weights": weights}


def parry_on(scene: dict | None) -> bool:
    """Can a parry (and so a Black Flash) come up in this scene?"""
    return scene is None or scene["weights"].get("standard", 0) > 0 or scene["weights"].get("combo", 0) > 0


def pick_kind(scene: dict, rng=random) -> str:
    kinds = [k for k, w in scene["weights"].items() if w > 0]
    return rng.choices(kinds, weights=[scene["weights"][k] for k in kinds])[0]


def fallback_kind(scene: dict) -> str:
    """For somebody who is not in the Activity, instead of a swipe, drag or tap: the closest QTE of the channel."""
    w = scene["weights"]
    if w.get("direction", 0) > 0:
        return "direction"
    return "evade" if w.get("evade", 0) > 0 or w.get("standard", 0) == 0 else "standard"


def public(scene: dict | None) -> dict | None:
    if scene is None:
        return None
    return {"id": scene["id"], "name": scene["name"], "color": scene["color"], "note": scene["note"],
            "parry": parry_on(scene), "counter": scene["counter"]}


class SceneBook:
    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.items: dict[str, dict] = {}
        self.active = ""
        loaded = False
        if path is not None and path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                for item in raw.get("scenes", []):
                    try:
                        scene = clean_scene(item)
                        self.items[scene["id"]] = scene
                    except RpcError:
                        continue
                self.active = str(raw.get("active") or "")
                loaded = True
            except (OSError, ValueError, AttributeError):
                log.warning("could not read %s", path)
        if not loaded:
            self.restore_presets(save=False)
        if self.active not in self.items:
            self.active = ""

    def save(self) -> None:
        if self.path is None:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"scenes": list(self.items.values()), "active": self.active}, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            log.warning("could not save %s", self.path)

    def restore_presets(self, save: bool = True) -> None:
        for preset in PRESETS:
            self.items[preset["id"]] = clean_scene(preset)
        if save:
            self.save()

    def current(self) -> dict | None:
        return self.items.get(self.active) if self.active else None

    def put(self, raw: Any) -> dict:
        sid = str((raw or {}).get("id") or "") if isinstance(raw, dict) else ""
        if sid and sid not in self.items:
            sid = ""
        if not sid and len(self.items) >= MAX_SCENES:
            raise RpcError(f"Puedes tener hasta {MAX_SCENES} escenas: borra alguna.")
        scene = clean_scene(raw, sid or uuid.uuid4().hex[:8])
        self.items[scene["id"]] = scene
        self.save()
        return scene

    def delete(self, sid: Any) -> dict:
        scene = self.items.pop(str(sid), None)
        if scene is None:
            raise RpcError("Esa escena ya no existe.")
        if self.active == scene["id"]:
            self.active = ""
        self.save()
        return scene

    def use(self, sid: Any) -> dict | None:
        sid = str(sid or "")
        if sid and sid not in self.items:
            raise RpcError("Esa escena ya no existe.")
        self.active = sid
        self.save()
        return self.current()

    def state(self) -> dict:
        return {"scenes": list(self.items.values()), "active": self.active, "kinds": [{"id": k, "label": v} for k, v in KINDS.items()]}


class SceneRpc:
    """Mixed into ActivityBridge; relies on `self.scenes` (SceneBook), `self.arena`, `self.hub`, `self.app`, `self._gm` and `self.gm.log`."""

    def apply_scene(self) -> None:
        """What the bot reads when it draws a QTE (and the hook for the Activity's own QTEs)."""
        self.app.qte_scene = self.scenes.current()
        self.app.launch_gesture = self.launch_gesture

    async def launch_gesture(self, kind: str, difficulty: str, member) -> bool:
        """A swipe, drag or tap QTE for `member` if they have the Activity open (True), else nothing (False)."""
        if kind not in GESTURES or int(getattr(member, "id", 0)) not in self.arena.in_activity():
            return False
        try:
            await self.arena.launch(kind, difficulty, [member], source="scene")
        except RpcError:
            return False
        return True

    async def _scene_changed(self) -> None:
        self.apply_scene()
        await self.hub.broadcast({"t": "scene", "scene": public(self.scenes.current())})

    async def rpc_gm_scenes(self, conn: Conn, args: dict):
        await self._gm(conn)
        return self.scenes.state()

    async def rpc_gm_scene_save(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        scene = self.scenes.put(args.get("scene"))
        if scene["id"] == self.scenes.active:
            await self._scene_changed()
        self.gm.log.add(actor, f"Guardó la escena «{scene['name']}»")
        return {**self.scenes.state(), "saved": scene["id"]}

    async def rpc_gm_scene_delete(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        was = self.scenes.active
        scene = self.scenes.delete(args.get("id"))
        if was == scene["id"]:
            await self._scene_changed()
        self.gm.log.add(actor, f"Borró la escena «{scene['name']}»")
        return self.scenes.state()

    async def rpc_gm_scene_use(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        scene = self.scenes.use(args.get("id"))
        await self._scene_changed()
        self.gm.log.add(actor, f"Escena: {scene['name']}" if scene else "Sin escena (QTE en modo clásico)")
        return self.scenes.state()

    async def rpc_gm_scene_presets(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        self.scenes.restore_presets()
        if self.scenes.active in {p["id"] for p in PRESETS}:
            await self._scene_changed()
        self.gm.log.add(actor, "Restauró las escenas de serie")
        return self.scenes.state()
