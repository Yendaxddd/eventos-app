"""Mini enemies: small foes the game masters send in beside (or instead of) the boss.

* The game masters keep a **bestiary** (templates: name, life, picture, how often and how hard it attacks, what it gives when it falls)
  in `data/activity_mobs.json`, and spawn copies of them during the event.
* A live enemy **attacks** on its own clock: it picks somebody who is playing from the Activity and throws a QTE at them (one of the
  Activity's own -- swipe, drag, tap -- or a normal evade from the bot). Failing it hurts as any QTE does; answering it well hits back.
* Players **hit** an enemy by tapping it (one hit every couple of seconds), with their damage boosts and weapon. When it falls, whoever
  finished it gets power charge, and the game hears `mob_down` (and `mobs_cleared` when none is left), so sounds, effects and
  cinematics can follow.

Everything here is the Activity's: the bot only lends its QTEs, its damage to players, its damage boosts and its power charges."""
from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import secrets
import time
from pathlib import Path
from typing import Any

from .arena import MODES as ARENA_MODES
from .hub import RpcError

log = logging.getLogger("eventos_app.activity")

ATTACKS = ("random", "flick", "drag", "mash", "single")      # what a mini enemy throws at people
DIFFICULTIES = ("easy", "medium", "hard", "impossible")
MAX_TEMPLATES, MAX_LIVE, MAX_SPAWN = 60, 12, 6
HIT_BASE = 10                      # a player's tap, before their boosts
HIT_COOLDOWN = 2.0                 # seconds between two taps of the same player
COUNTER_HIT = 15                   # what answering an enemy's QTE well does back to it
TICK = 0.5
_IMAGE = re.compile(r"^(files/images/[0-9a-f]{24}\.(png|jpg|gif|webp)|https://\S{8,500})$")
_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def _int(value: Any, what: str, lo: int, hi: int) -> int:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        raise RpcError(f"{what}: escribe un número.") from None
    if number < lo or number > hi:
        raise RpcError(f"{what}: debe estar entre {lo} y {hi}.")
    return number


def clean_template(raw: Any, known_id: str = "") -> dict:
    if not isinstance(raw, dict):
        raise RpcError("El enemigo no es válido.")
    name = re.sub(r"\s+", " ", str(raw.get("name") or "")).strip()[:40]
    if not name:
        raise RpcError("El enemigo necesita un nombre.")
    image = str(raw.get("image") or "").strip()
    if image and not _IMAGE.match(image):
        raise RpcError("La imagen debe ser de la biblioteca o un enlace https.")
    color = str(raw.get("color") or "#fb7185")
    return {
        "id": known_id or str(raw.get("id") or "") or secrets.token_hex(4), "name": name, "image": image or None,
        "color": color.lower() if _COLOR.match(color) else "#fb7185",
        "hp": _int(raw.get("hp", 120), "Vida", 1, 100000),
        "every": _int(raw.get("every", 12), "Ataca cada (segundos)", 4, 600),
        "attack": raw.get("attack") if raw.get("attack") in ATTACKS else "random",
        "difficulty": raw.get("difficulty") if raw.get("difficulty") in DIFFICULTIES else "medium",
        "damage": _int(raw.get("damage"), "Daño", 1, 1000) if raw.get("damage") not in (None, "", 0) else None,
        "charge": _int(raw.get("charge", 10), "Carga al derrotarlo", 0, 100),
    }


class Bestiary:
    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.items: dict[str, dict] = {}
        if path is not None and path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                for item in (raw if isinstance(raw, list) else [])[:MAX_TEMPLATES]:
                    try:
                        t = clean_template(item, str(item.get("id") or "") if isinstance(item, dict) else "")
                        self.items[t["id"]] = t
                    except RpcError:
                        continue
            except (OSError, ValueError):
                log.warning("could not read %s", path)

    def save(self) -> None:
        if self.path is None:
            return
        try:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(list(self.items.values()), ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            log.warning("could not save %s", self.path)

    def put(self, raw: Any) -> dict:
        known = str(raw.get("id") or "") if isinstance(raw, dict) else ""
        if known and known not in self.items:
            known = ""
        if not known and len(self.items) >= MAX_TEMPLATES:
            raise RpcError(f"El bestiario admite hasta {MAX_TEMPLATES} enemigos.")
        t = clean_template(raw, known)
        self.items[t["id"]] = t
        self.save()
        return t

    def delete(self, tid: Any) -> dict:
        t = self.items.pop(str(tid), None)
        if t is None:
            raise RpcError("Ese enemigo ya no está en el bestiario.")
        self.save()
        return t


class Mobs:
    def __init__(self, bridge, path: Path | None = None) -> None:
        self.b = bridge
        self.bestiary = Bestiary(path)
        self.live: dict[str, dict] = {}
        self.paused = False
        self.serial = 0
        self.last_hit: dict[int, float] = {}
        self.task: asyncio.Task | None = None

    # ---- what the players see ------------------------------------------------------------------------------------------
    def public(self) -> dict:
        now = time.monotonic()
        return {"paused": self.paused, "list": [{"id": m["id"], "name": m["name"], "image": m["image"], "color": m["color"], "hp": m["hp"], "max": m["max"],
                                                 "next": None if self.paused else max(0.0, round(m["next"] - now, 1)), "every": m["every"],
                                                 "attacking": m.get("attacking")} for m in self.live.values()]}

    async def announce(self) -> None:
        await self.b.hub.broadcast({"t": "mobs", **self.public()})

    # ---- the game masters ------------------------------------------------------------------------------------------------
    async def spawn(self, tid: Any, count: Any = 1) -> list[dict]:
        t = self.bestiary.items.get(str(tid))
        if t is None:
            raise RpcError("Ese enemigo ya no está en el bestiario.")
        n = _int(count, "Cuántos", 1, MAX_SPAWN)
        if len(self.live) + n > MAX_LIVE:
            raise RpcError(f"Puede haber hasta {MAX_LIVE} enemigos a la vez.")
        now = time.monotonic()
        made = []
        same = sum(1 for m in self.live.values() if m["template"] == t["id"])
        for i in range(n):
            self.serial += 1
            label = t["name"] if n == 1 and same == 0 else f"{t['name']} {same + i + 1}"
            mob = {"id": f"m{self.serial}", "template": t["id"], "name": label, "image": t["image"], "color": t["color"], "hp": t["hp"], "max": t["hp"],
                   "every": t["every"], "attack": t["attack"], "difficulty": t["difficulty"], "damage": t["damage"], "charge": t["charge"],
                   "next": now + t["every"] * random.uniform(0.6, 1.0) + i * 1.5, "attacking": None, "hitters": {}}
            self.live[mob["id"]] = mob
            made.append(mob)
        self._ensure_task()
        self.b.on_event("mob_spawn", {"name": t["name"], "count": n})
        await self.announce()
        return made

    def _need(self, mid: Any) -> dict:
        mob = self.live.get(str(mid))
        if mob is None:
            raise RpcError("Ese enemigo ya no está.")
        return mob

    async def set_hp(self, mid: Any, action: str, amount: Any = None) -> dict:
        mob = self._need(mid)
        if action == "kill":
            await self._damage(mob, mob["hp"], None)
            return mob
        value = _int(amount, "Cantidad", 1, 100000)
        if action == "damage":
            await self._damage(mob, value, None)
        elif action == "heal":
            mob["hp"] = min(mob["max"], mob["hp"] + value)
            await self.announce()
        else:
            raise RpcError("Esa acción no existe.")
        return mob

    async def remove(self, mid: Any = None) -> None:
        if mid in (None, "", "all"):
            self.live.clear()
        else:
            self.live.pop(str(self._need(mid)["id"]), None)
        await self.announce()

    async def set_paused(self, paused: bool) -> None:
        self.paused = bool(paused)
        now = time.monotonic()
        for mob in self.live.values():                  # after a pause nobody is attacked the very next instant
            mob["next"] = max(mob["next"], now + mob["every"] * 0.5)
        await self.announce()

    async def damage_all(self, amount: int, user: Any = None) -> int:
        """A power that hits every enemy on the field (`damage_all`). Says how many it hit."""
        if amount <= 0 or not self.live:
            return 0
        who = None
        if user is not None:
            conn = next((c for c in list(self.b.hub.conns.values()) if c.user_id == int(user)), None)
            who = (int(user), conn.name if conn else "?")
        hit = 0
        for mob in list(self.live.values()):
            await self._damage(mob, amount, who)
            hit += 1
        return hit

    async def stun(self, seconds: float) -> None:
        """The boss was stunned: the mini enemies wait too (their next attack comes `seconds` later)."""
        if seconds <= 0 or not self.live:
            return
        later = time.monotonic() + seconds
        for mob in self.live.values():
            mob["next"] = max(mob["next"], later)
        await self.announce()

    # ---- the players hit -----------------------------------------------------------------------------------------------
    def damage_of(self, uid: int, base: int) -> int:
        app = self.b.app
        amount = float(base)
        try:
            weapon = getattr(app, "get_weapon_damage_multiplier", None)
            if weapon is not None:
                amount *= float(weapon(uid) or 1.0)
            boost = getattr(app, "apply_damage_buff", None)
            if boost is not None:
                amount = float(boost(uid, int(round(amount))))
        except Exception:  # noqa: BLE001 - the boosts are the bot's: a failure there leaves the plain hit
            pass
        return max(1, int(round(amount)))

    async def hit(self, uid: int, name: str, mid: Any) -> dict:
        mob = self._need(mid)
        now = time.monotonic()
        wait = HIT_COOLDOWN - (now - self.last_hit.get(uid, -999))
        if wait > 0:
            raise RpcError(f"Espera {wait:.1f} s para volver a golpear.")
        self.last_hit[uid] = now
        dealt = await self._damage(mob, self.damage_of(uid, HIT_BASE), (uid, name))
        return {"dealt": dealt, "hp": mob["hp"], "down": mob["hp"] <= 0, "cooldown": HIT_COOLDOWN}

    async def _damage(self, mob: dict, amount: int, who: tuple[int, str] | None) -> int:
        """Takes `amount` off the enemy (never more than it has left) and says how much that was."""
        if mob["id"] not in self.live:
            return 0
        dealt = min(mob["hp"], max(0, int(amount)))
        mob["hp"] -= dealt
        if who is not None:
            mob["hitters"][who[0]] = mob["hitters"].get(who[0], 0) + dealt
        self.b.on_event("mob_hit", {"name": mob["name"], "amount": dealt, "user": who[0] if who else None})
        await self.b.hub.broadcast({"t": "mob_hit", "id": mob["id"], "amount": dealt, "by": who[1] if who else None})
        if mob["hp"] <= 0:
            await self._fall(mob, who)
        else:
            await self.announce()
        return dealt

    async def _fall(self, mob: dict, who: tuple[int, str] | None) -> None:
        self.live.pop(mob["id"], None)
        if who is not None and mob["charge"]:
            self._give_charge(who[0], mob["charge"])
            self.b.notify(who[0], "mob_down", {"name": mob["name"], "charge": mob["charge"]})
        self.b.on_event("mob_down", {"name": mob["name"], "user": who[0] if who else None})
        if not self.live:
            self.b.on_event("mobs_cleared", {})
        await self.announce()

    def _give_charge(self, uid: int, percent: int) -> None:
        charges = getattr(self.b.app, "power_charges", None)
        if not isinstance(charges, dict):
            return
        mine = charges.setdefault(uid, {"power1": 0, "power2": 0})
        for slot in ("power1", "power2"):
            mine[slot] = min(100, float(mine.get(slot, 0) or 0) + percent)

    # ---- the enemies attack -----------------------------------------------------------------------------------------------
    def _ensure_task(self) -> None:
        if self.task is None or self.task.done():
            self.task = asyncio.get_running_loop().create_task(self._loop())

    async def _loop(self) -> None:
        try:
            while self.live:
                await asyncio.sleep(TICK)
                if self.paused:
                    continue
                now = time.monotonic()
                for mob in list(self.live.values()):
                    if mob["next"] <= now and not mob.get("attacking"):
                        mob["next"] = now + mob["every"]
                        try:
                            await self._attack(mob)
                        except Exception:  # noqa: BLE001 - one bad attack must not stop the others
                            log.exception("a mini enemy could not attack")
        except asyncio.CancelledError:
            pass

    def _targets(self) -> list:
        inside = {c.user_id: c for c in list(self.b.hub.conns.values()) if not c.hidden}
        players = {m.id: m for m in list(getattr(self.b.app, "qte_players", []) or [])}
        pool = [players[u] for u in inside if u in players]
        if not pool:
            from .arena import _Somebody
            pool = [_Somebody(u, c.name) for u, c in inside.items() if u < 0]          # test windows on this PC
        return pool

    async def _attack(self, mob: dict) -> None:
        pool = self._targets()
        if not pool:
            return
        target = random.choice(pool)
        kind = mob["attack"]
        if kind == "random":
            kind = random.choice(("flick", "drag", "mash", "single"))
        mob["attacking"] = getattr(target, "display_name", None) or getattr(target, "name", "?")
        await self.announce()
        self.b.on_event("mob_attack", {"name": mob["name"], "user": target.id})

        async def after(uid: int, ok: bool, mob_id=mob["id"]) -> None:
            live = self.live.get(mob_id)
            if live is None:
                return
            live["attacking"] = None
            if ok:
                await self._damage(live, self.damage_of(uid, COUNTER_HIT), (uid, mob["attacking"] or "?"))
            else:
                await self.announce()

        if kind in ARENA_MODES:
            await self.b.arena.launch(kind, mob["difficulty"], [target], damage=mob["damage"], on_done=after, source=mob["name"])
        else:
            trigger = getattr(self.b.app, "trigger_single_qte", None)
            if trigger is None or target.id < 0:
                await self.b.arena.launch("flick", mob["difficulty"], [target], damage=mob["damage"], on_done=after, source=mob["name"])
                return
            await trigger(mob["difficulty"], target_member=target, is_targeted=True)
            mob["attacking"] = None
            await self.announce()

    def stop(self) -> None:
        if self.task is not None:
            self.task.cancel()
            self.task = None
