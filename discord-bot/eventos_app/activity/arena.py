"""QTEs that only exist in the Activity: they need a finger or a mouse, so the channel cannot have them.

* **flick** (deslizar): swipe the way the arrow points (or press that arrow key), before the time runs out.
* **drag** (arrastrar): drag the token onto the mark (or move it with the arrow keys and press Enter).
* **mash** (machacar): tap the button (or the space bar) as many times as it asks.

They are sent to the players like the bot's QTEs (a `qte` frame, ids starting with "a") and judged here: the time by the same rules as
a button press (the player's own stopwatch, adjusted for their connection and screen), the gesture by what the screen measured. A
failure (or no answer) hurts the player through the bot's own `damage_player`, a success counts as an evade in their stats. The game
masters launch them from the panel; the mini enemies use them to attack (mobs.py)."""
from __future__ import annotations

import asyncio
import logging
import math
import random
from typing import Any, Callable

from .hub import Conn, RpcError
from .qte import response_seconds

log = logging.getLogger("eventos_app.activity")

MODES = {"flick": "deslizar", "drag": "arrastrar", "mash": "machacar"}
DIFFICULTIES = ("easy", "medium", "hard", "impossible")
TIMEOUT = {"flick": {"easy": 2.6, "medium": 1.9, "hard": 1.4, "impossible": 1.0},
           "drag": {"easy": 4.0, "medium": 3.0, "hard": 2.3, "impossible": 1.7},
           "mash": {"easy": 3.2, "medium": 3.2, "hard": 3.4, "impossible": 3.6}}
MASH_COUNT = {"easy": 8, "medium": 12, "hard": 16, "impossible": 22}
DRAG_TOLERANCE = {"easy": 0.16, "medium": 0.12, "hard": 0.09, "impossible": 0.07}     # of the pad's size
FLICK_DIRS = ("up", "down", "left", "right")
MAX_TAP_RATE = 16.0                 # taps per second a person can really do: more is a script
GRACE_S = 0.35                      # past the deadline, for the answer still on its way
MAX_LIVE = 60


def params_for(mode: str, difficulty: str, rng=random) -> dict:
    if mode == "flick":
        return {"dir": rng.choice(FLICK_DIRS)}
    if mode == "drag":
        start = (round(rng.uniform(0.12, 0.3), 3), round(rng.uniform(0.2, 0.8), 3))
        goal = (round(rng.uniform(0.7, 0.88), 3), round(rng.uniform(0.2, 0.8), 3))
        if rng.random() < 0.5:                             # sometimes right to left
            start, goal = (1 - start[0], start[1]), (1 - goal[0], goal[1])
        return {"from": list(start), "to": list(goal), "tolerance": DRAG_TOLERANCE[difficulty]}
    return {"count": MASH_COUNT[difficulty]}


def judge(mode: str, params: dict, data: Any, seconds: float, timeout: float) -> tuple[bool, str]:
    """(passed, why not). `data` is what the player's screen measured."""
    if seconds > timeout + GRACE_S:
        return False, "late"
    data = data if isinstance(data, dict) else {}
    if mode == "flick":
        return (True, "") if data.get("dir") == params["dir"] else (False, "wrong_dir")
    if mode == "drag":
        try:
            x, y = float(data.get("x")), float(data.get("y"))
        except (TypeError, ValueError):
            return False, "missed"
        if not (math.isfinite(x) and math.isfinite(y)):
            return False, "missed"
        gx, gy = params["to"]
        return (True, "") if math.hypot(x - gx, y - gy) <= params["tolerance"] else (False, "missed")
    try:
        count = int(data.get("count"))
    except (TypeError, ValueError):
        return False, "short"
    need = params["count"]
    if count < need:
        return False, "short"
    if seconds <= 0 or count / max(seconds, 0.05) > MAX_TAP_RATE:
        return False, "short"
    return True, ""


class ArenaQtes:
    def __init__(self, bridge) -> None:
        self.b = bridge
        self.live: dict[str, dict] = {}
        self.counter = 0

    # ---- starting ---------------------------------------------------------------------------------------------------------
    def in_activity(self) -> set[int]:
        return {c.user_id for c in list(self.b.hub.conns.values()) if not c.hidden}

    async def launch(self, mode: str, difficulty: str, members: list, *, damage: Any = None, on_done: Callable | None = None,
                     source: str = "") -> list[dict]:
        """One QTE of `mode` for each member (a discord.Member or anything with .id and .display_name). Returns the frames."""
        if mode not in MODES:
            raise RpcError("Ese tipo de QTE no existe.")
        if difficulty not in DIFFICULTIES:
            raise RpcError("La dificultad no es válida.")
        if len(self.live) >= MAX_LIVE:
            raise RpcError("Hay demasiados QTE en marcha.")
        frames = []
        for member in members:
            self.counter += 1
            qid = f"a{self.counter}"
            timeout = TIMEOUT[mode][difficulty]
            frame = {"id": qid, "mode": mode, "difficulty": difficulty,
                     "target": {"id": str(member.id), "name": getattr(member, "display_name", None) or getattr(member, "name", "?")},
                     "participants": [], "tGo": self.b.hub.now_ms(), "timeout": timeout, "windows": {"evade": [0.0, timeout]},
                     "commands": ["gesture"], "arena": params_for(mode, difficulty), "source": source}
            entry = {"frame": frame, "user": int(member.id), "damage": damage, "on_done": on_done, "done": False}
            self.live[qid] = entry
            await self.b.hub.qte_start(frame)
            entry["task"] = asyncio.get_running_loop().create_task(self._expire(qid, timeout))
            frames.append(frame)
            self.b._spawn(self.b.audio.dispatch("qte", {"mode": mode, "difficulty": difficulty, "user": int(member.id)}))
        return frames

    async def _expire(self, qid: str, timeout: float) -> None:
        try:
            await asyncio.sleep(timeout + GRACE_S + self.b.answer_grace())      # a gesture made in time may still be on its way
            entry = self.live.get(qid)
            if entry is not None and not entry["done"]:
                await self._settle(entry, False, None, "timeout")
        except asyncio.CancelledError:
            pass

    # ---- answering ----------------------------------------------------------------------------------------------------------
    async def answer(self, conn: Conn, frame: dict) -> str | None:
        qid = str(frame.get("id") or "")
        entry = self.live.get(qid)
        if entry is None:
            return "Ese QTE ya terminó."
        if conn.user_id != entry["user"]:
            return "Ese QTE no es tuyo."
        if entry["done"]:
            return None
        try:
            dt = float(frame.get("dt"))
        except (TypeError, ValueError):
            return "Tiempo inválido."
        q = entry["frame"]
        elapsed = self.b.hub.now_ms() - q["tGo"]
        seconds = response_seconds(dt, conn.net_ms, elapsed, self.b.latency.device_ms(conn.user_id), self.b.cap_ms)
        if seconds is None:
            return "Esa respuesta no es creíble."
        ok, why = judge(q["mode"], q["arena"], frame.get("data"), seconds, q["timeout"])
        await self._settle(entry, ok, seconds, why)
        return None

    async def _settle(self, entry: dict, ok: bool, seconds: float | None, why: str = "") -> None:
        entry["done"] = True
        q = entry["frame"]
        task = entry.get("task")
        if task is not None and task is not asyncio.current_task():
            task.cancel()
        self.live.pop(q["id"], None)
        result = {"t": "qte_result", "id": q["id"], "ok": ok, "ms": None if seconds is None else round(seconds * 1000), "why": why, "reactions": []}
        for conn in list(self.b.hub.conns.values()):
            if conn.user_id == entry["user"]:
                await self.b.hub.send(conn, result)
        await self.b.hub.qte_end(q["id"])
        app, uid = self.b.app, entry["user"]
        try:
            if ok:
                self.b.on_event("evade_ok", {"user": uid, "mode": q["mode"]})
                stats = getattr(app, "update_player_stats", None)
                if stats is not None and seconds is not None:
                    await stats(uid, "evade", True, seconds)
            else:
                self.b.on_event("qte_fail", {"user": uid, "mode": q["mode"]})
                hurt = getattr(app, "damage_player", None)
                if hurt is not None:
                    await hurt(uid, entry["damage"] if entry["damage"] is not None else q["difficulty"])
                stats = getattr(app, "update_player_stats", None)
                if stats is not None:
                    await stats(uid, "evade", False, seconds or q["timeout"])
        except Exception:  # noqa: BLE001 - the verdict is already given; the bot's bookkeeping must not break the server
            log.exception("could not apply the result of an Activity QTE")
        if entry["on_done"] is not None:
            try:
                await entry["on_done"](uid, ok)
            except Exception:  # noqa: BLE001
                log.exception("a QTE's follow-up failed")

    async def gm_launch(self, actor: str, mode: str, difficulty: str, target_id=None) -> dict:
        """The panel's «Lanzar»: for one chosen person or somebody at random, among those who have the Activity open."""
        gm = self.b.gm
        if gm.stunned_left() > 0:
            raise RpcError(f"El enemigo está aturdido ({gm.stunned_left():.0f} s). Espera a que termine.")
        inside = self.in_activity()
        if target_id not in (None, "", 0):
            try:
                uid = int(target_id)
            except (TypeError, ValueError):
                raise RpcError("Ese jugador no está en el servidor.") from None
            if uid not in inside:
                raise RpcError("Ese jugador no tiene la Actividad abierta: este QTE solo se puede responder desde ella.")
            member = gm._member(uid) if uid > 0 else None
            members = [member or _Somebody(uid, self._name_of(uid))]
        else:
            players = {m.id: m for m in list(getattr(self.b.app, "qte_players", []) or [])}
            pool = [players[u] for u in inside if u in players] or [_Somebody(u, self._name_of(u)) for u in inside if u < 0]
            if not pool:
                raise RpcError("Nadie que pueda jugar tiene la Actividad abierta.")
            members = [random.choice(pool)]
        frames = await self.launch(mode, difficulty, members, source="gm")
        gm.log.add(actor, f"Lanzó un QTE de {MODES[mode]} ({difficulty}) a {frames[0]['target']['name']}")
        return {"ok": True}

    def _name_of(self, uid: int) -> str:
        for conn in self.b.hub.conns.values():
            if conn.user_id == uid:
                return conn.name
        return "?"

    def stop_all(self) -> None:
        for entry in list(self.live.values()):
            task = entry.get("task")
            if task is not None:
                task.cancel()
        self.live.clear()


class _Somebody:
    """A person known only by the Activity (a test window on this PC)."""

    def __init__(self, uid: int, name: str) -> None:
        self.id, self.display_name, self.name = uid, name, name
