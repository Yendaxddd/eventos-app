"""Results: what each player did in a round (a fight, a run of QTEs, a chapter), and the screens the game masters show about it.

- `RoundTracker` listens to the game's events (the same ones that play sounds and cinematics: a Black Flash, a parry, a rescue,
  damage taken, a power...) and adds them up per player. A round starts with a fight (or when a game master starts one) and keeps
  counting until another starts.
- A results screen is a title and a list of blocks the game masters edit freely, even while it is on everybody's screen: a podium,
  awards («fastest parry», «guardian»...), the stats table, free text (a decision, what comes next) and lists (rewards, loot...).
  `build_screen` fills one from the round; when the boss falls, one is made by itself (and shown, if «automatic» is on).

Ops (box «Resultados»): `gm.results`, `gm.results_save`, `gm.results_build`, `gm.results_show`, `gm.results_hide`,
`gm.results_delete`, `gm.results_auto`, `gm.results_reset`. Everybody: `results.get` (what is showing, or was shown last)."""
from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from .hub import Conn, RpcError

log = logging.getLogger("eventos_app.activity")

# What each event adds to the player it names: [stat, how much (a number, or the data field to add)]
COUNTS: dict[str, list[tuple[str, Any]]] = {
    "black_flash": [("bf", 1), ("damage", "damage")],
    "parry_ok": [("parries", 1)],
    "evade_ok": [("evades", 1)],
    "rescue_ok": [("saves", 1)],
    "qte_fail": [("fails", 1)],
    "combo_done": [("combos", 1)],
    "group_done": [("groups", 1)],
    "counter": [("counters", 1), ("damage", "damage")],
    "mirror_invoke": [("damage", "damage")],
    "power_used": [("powers", 1)],
    "power_effect": [("damage", "damage"), ("healed", "healed")],
    "power_aoe": [("damage", "amount")],
    "domain": [("domains", 1)],
    "player_hit": [("taken", "amount"), ("hits", 1)],
    "heal": [("healed_self", "amount")],
    "player_down": [("downs", 1)],
}
FAST = {"parry_ok": "best_parry", "evade_ok": "best_evade", "rescue_ok": "best_save", "black_flash": "best_bf"}   # fastest reaction (ms)

STATS = [  # [key, label] in the order the table shows them
    ("score", "Puntos"), ("damage", "Daño"), ("bf", "Black Flash"), ("parries", "Parries"), ("evades", "Esquivas"), ("saves", "Rescates"),
    ("combos", "Combos"), ("counters", "Contraataques"), ("powers", "Poderes"), ("taken", "Daño recibido"), ("fails", "Fallos"), ("downs", "Caídas"),
]
WEIGHTS = {"damage": 1, "bf": 15, "parries": 8, "evades": 4, "saves": 12, "combos": 10, "groups": 4, "counters": 6, "powers": 3,
           "domains": 8, "healed": 0.5, "fails": -3, "downs": -10}

# [id, title, icon, stat, best is "max" or "min", how the value reads]
AWARDS = [
    ("mvp", "MVP de la ronda", "crown", "score", "max", "{v} punto{s}"),
    ("damage", "Más daño", "swords", "damage", "max", "{v} de daño"),
    ("bf", "Maestro del Black Flash", "zap", "bf", "max", "{v} Black Flash"),
    ("parry", "Parry más rápido", "shield", "best_parry", "min", "{v} ms"),
    ("guardian", "Guardián", "heart-handshake", "saves", "max", "{v} rescate{s}"),
    ("dodger", "Inalcanzable", "wind", "evades", "max", "{v} esquiva{s}"),
    ("reflex", "Reflejos de acero", "timer", "best_evade", "min", "{v} ms"),
    ("combo", "Rey del combo", "flame", "combos", "max", "{v} combo{s}"),
    ("tank", "Aguante", "mountain", "taken", "max", "{v} de daño aguantado"),
    ("caster", "Lluvia de poderes", "sparkles", "powers", "max", "{v} poder{es}"),
]
BLOCK_TYPES = ("podium", "awards", "stats", "text", "list")
MAX_SCREENS = 30
MAX_BLOCKS = 16


def score_of(s: dict) -> int:
    return int(round(sum(s.get(k, 0) * w for k, w in WEIGHTS.items())))


class RoundTracker:
    def __init__(self) -> None:
        self.reset("")

    def reset(self, title: str = "") -> None:
        self.title = title or "Ronda"
        self.started = int(time.time() * 1000)
        self.players: dict[int, dict] = {}
        self.boss: dict | None = None             # {"name", "damage", "defeated"}
        self.events = 0

    def _player(self, uid: int) -> dict:
        return self.players.setdefault(uid, {})

    def track(self, event: str, data: dict) -> None:
        if event == "fight_start":
            self.reset("Combate")
            return
        if event == "boss_spawn":
            self.boss = {"name": str(data.get("name") or "Jefe"), "damage": 0, "defeated": False}
            if self.title in ("Ronda", "Combate"):
                self.title = f"Combate contra {self.boss['name']}"
            return
        if event == "boss_hit" and self.boss is not None:
            self.boss["damage"] += int(data.get("amount") or 0)
            return
        if event == "boss_defeated" and self.boss is not None:
            self.boss["defeated"] = True
            return
        rules = COUNTS.get(event)
        user = data.get("user")
        if rules is None or user is None:
            return
        try:
            uid = int(user)
        except (TypeError, ValueError):
            return
        p = self._player(uid)
        self.events += 1
        for stat, how in rules:
            amount = how if isinstance(how, (int, float)) else data.get(how)
            try:
                amount = float(amount or 0)
            except (TypeError, ValueError):
                amount = 0.0
            if amount:
                p[stat] = p.get(stat, 0) + (int(amount) if float(amount).is_integer() else round(amount, 1))
        if event in FAST and isinstance(data.get("ms"), (int, float)) and data["ms"] > 0:
            key = FAST[event]
            p[key] = min(p.get(key, 10**9), int(data["ms"]))

    def table(self, name_of: Callable[[int], str]) -> list[dict]:
        rows = []
        for uid, s in self.players.items():
            row = {"id": str(uid), "name": name_of(uid), **s}
            row["score"] = score_of(s)
            rows.append(row)
        rows.sort(key=lambda r: (-r["score"], r["name"].lower()))
        return rows

    def public(self, name_of: Callable[[int], str]) -> dict:
        return {"title": self.title, "started": self.started, "boss": self.boss, "rows": self.table(name_of), "events": self.events,
                "stats": [list(s) for s in STATS]}


MAX_AWARDS_EACH = 3        # so the prizes go round: after three, the next best player gets it


def awards_of(rows: list[dict]) -> list[dict]:
    out = []
    won: dict[str, int] = {}
    for aid, title, icon, stat, best, fmt in AWARDS:
        have = [r for r in rows if r.get(stat)]
        if aid == "mvp":
            have = [r for r in rows if r.get("score", 0) > 0]
        if not have:
            continue
        ranked = sorted(have, key=lambda r: r.get(stat, 0), reverse=best != "min")
        pick = next((r for r in ranked if won.get(r["id"], 0) < MAX_AWARDS_EACH), None)
        if pick is None:
            continue
        won[pick["id"]] = won.get(pick["id"], 0) + 1
        v = pick.get(stat, 0)
        out.append({"id": aid, "icon": icon, "title": title, "name": pick["name"], "value": fmt.format(v=v, s="" if v == 1 else "s", es="" if v == 1 else "es")})
    return out


def build_screen(round_state: dict, by: str = "") -> dict:
    """A results screen filled from a round: podium, awards and the table. The game masters edit it from there."""
    rows = round_state["rows"]
    boss = round_state.get("boss")
    subtitle = ""
    if boss:
        subtitle = f"{boss['name']} {'derrotado' if boss.get('defeated') else 'sigue en pie'} · {boss.get('damage', 0)} de daño en total"
    blocks: list[dict] = []
    if rows:
        blocks.append({"type": "podium", "title": "Podio", "entries": [{"name": r["name"], "value": f"{r['score']} pts"} for r in rows[:3]]})
        awards = awards_of(rows)
        if awards:
            blocks.append({"type": "awards", "title": "Premios", "items": awards})
        keys = [k for k, _ in STATS if any(r.get(k) for r in rows)]
        labels = dict(STATS)
        blocks.append({"type": "stats", "title": "Estadísticas", "columns": [[k, labels[k]] for k in keys],
                       "rows": [{"name": r["name"], "values": [r.get(k, 0) for k in keys]} for r in rows]})
    else:
        blocks.append({"type": "text", "title": "Sin datos todavía", "body": "Nadie ha hecho nada en esta ronda (o el juego no lo contó)."})
    return clean_screen({"title": round_state.get("title") or "Resultados", "subtitle": subtitle, "blocks": blocks, "by": by})


def _t(raw: Any, limit: int) -> str:
    return str(raw if raw is not None else "").strip()[:limit]


def clean_block(raw: Any) -> dict | None:
    if not isinstance(raw, dict) or raw.get("type") not in BLOCK_TYPES:
        return None
    kind = raw["type"]
    block = {"id": _t(raw.get("id"), 16) or uuid.uuid4().hex[:8], "type": kind, "title": _t(raw.get("title"), 80)}
    if kind == "podium":
        block["entries"] = [{"name": _t(e.get("name"), 60), "value": _t(e.get("value"), 40)}
                            for e in (raw.get("entries") or [])[:3] if isinstance(e, dict)]
    elif kind == "awards":
        block["items"] = [{"icon": _t(i.get("icon"), 24) or "trophy", "title": _t(i.get("title"), 60), "name": _t(i.get("name"), 60),
                           "value": _t(i.get("value"), 60)} for i in (raw.get("items") or [])[:12] if isinstance(i, dict)]
    elif kind == "stats":
        cols = [[_t(c[0], 20), _t(c[1], 30)] for c in (raw.get("columns") or [])[:12] if isinstance(c, (list, tuple)) and len(c) == 2]
        block["columns"] = cols
        block["rows"] = [{"name": _t(r.get("name"), 60), "values": [v if isinstance(v, (int, float)) else _t(v, 20) for v in (r.get("values") or [])[:len(cols)]]}
                         for r in (raw.get("rows") or [])[:40] if isinstance(r, dict)]
    elif kind == "text":
        block["body"] = _t(raw.get("body"), 2000)
    elif kind == "list":
        block["items"] = [{"name": _t(i.get("name"), 60), "text": _t(i.get("text"), 200)} for i in (raw.get("items") or [])[:24] if isinstance(i, dict)]
    return block


def clean_screen(raw: Any) -> dict:
    if not isinstance(raw, dict):
        raise RpcError("Pantalla inválida.")
    now = int(time.time() * 1000)
    blocks = [b for b in (clean_block(x) for x in (raw.get("blocks") or [])[:MAX_BLOCKS]) if b]
    return {"id": _t(raw.get("id"), 16) or uuid.uuid4().hex[:10], "title": _t(raw.get("title"), 80) or "Resultados",
            "subtitle": _t(raw.get("subtitle"), 160), "accent": _t(raw.get("accent"), 16), "blocks": blocks,
            "by": _t(raw.get("by"), 60), "created": int(raw.get("created") or now) if str(raw.get("created") or "").isdigit() else now, "updated": now}


class ResultsBook:
    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.screens: list[dict] = []
        self.showing: str | None = None
        self.last: str | None = None              # the last one shown (players can open it again)
        self.auto = True
        if path is not None and path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                self.screens = [s for s in raw.get("screens", []) if isinstance(s, dict) and s.get("id")]
                self.last = raw.get("last")
                self.auto = bool(raw.get("auto", True))
            except (OSError, ValueError, AttributeError):
                log.warning("could not read %s", path)

    def save(self) -> None:
        if self.path is None:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"screens": self.screens, "last": self.last, "auto": self.auto}, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            log.warning("could not save %s", self.path)

    def get(self, sid: str | None) -> dict | None:
        return next((s for s in self.screens if s["id"] == sid), None) if sid else None

    def put(self, raw: Any) -> dict:
        screen = clean_screen(raw)
        old = self.get(screen["id"])
        if old is not None:
            screen["created"] = old["created"]
            self.screens[self.screens.index(old)] = screen
        else:
            self.screens.insert(0, screen)
            del self.screens[MAX_SCREENS:]
        self.save()
        return screen

    def delete(self, sid: str) -> None:
        if self.get(sid) is None:
            raise RpcError("Esa pantalla ya no existe.")
        self.screens = [s for s in self.screens if s["id"] != sid]
        if self.showing == sid:
            self.showing = None
        if self.last == sid:
            self.last = None
        self.save()

    def show(self, sid: str | None) -> dict | None:
        if sid is not None and self.get(sid) is None:
            raise RpcError("Esa pantalla ya no existe.")
        self.showing = sid
        if sid:
            self.last = sid
        self.save()
        return self.get(sid)


class ResultsRpc:
    """Mixed into ActivityBridge; relies on `self.round` (RoundTracker), `self.results` (ResultsBook), `self.hub`, `self._gm`, `self.gm.log`."""

    def _player_name(self, uid: int) -> str:
        app = self.app
        for member in list(getattr(app, "qte_players", []) or []):
            if getattr(member, "id", None) == uid:
                return getattr(member, "display_name", None) or member.name
        guild = app.resolve_event_guild() if hasattr(app, "resolve_event_guild") else None
        member = guild.get_member(uid) if guild is not None else None
        if member is not None:
            return member.display_name
        for conn in list(self.hub.conns.values()):
            if conn.user_id == uid:
                return conn.name
        return f"Jugador {str(uid)[-4:]}"

    def track_results(self, event: str, data: dict) -> None:
        try:
            self.round.track(event, data)
            if event == "boss_defeated":
                self._spawn(self._auto_results())
        except Exception:  # noqa: BLE001 - counting must never break the game
            log.exception("results could not count %s", event)

    async def _auto_results(self) -> None:
        screen = self.results.put(build_screen(self.round.public(self._player_name), by="Automático"))
        if self.results.auto:
            self.results.show(screen["id"])
            await self.hub.broadcast({"t": "results", "screen": screen, "reopen": True})

    async def _results_state(self) -> dict:
        return {"round": self.round.public(self._player_name), "screens": self.results.screens, "showing": self.results.showing,
                "auto": self.results.auto}

    async def rpc_gm_results(self, conn: Conn, args: dict):
        await self._gm(conn)
        return await self._results_state()

    async def rpc_gm_results_build(self, conn: Conn, args: dict):
        await self._gm(conn)
        screen = self.results.put(build_screen(self.round.public(self._player_name), by=conn.name))
        return {**await self._results_state(), "made": screen["id"]}

    async def rpc_gm_results_save(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        raw = args.get("screen")
        if not isinstance(raw, dict):
            raise RpcError("Falta la pantalla.")
        if not raw.get("by"):
            raw = {**raw, "by": conn.name}
        screen = self.results.put(raw)
        if self.results.showing == screen["id"]:                 # edited live: everybody sees the change at once
            await self.hub.broadcast({"t": "results", "screen": screen})
        self.gm.log.add(actor, f"Guardó la pantalla de resultados «{screen['title']}»")
        return {**await self._results_state(), "made": screen["id"]}

    async def rpc_gm_results_show(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        screen = self.results.show(str(args.get("id") or ""))
        await self.hub.broadcast({"t": "results", "screen": screen, "reopen": True})
        self.gm.log.add(actor, f"Mostró los resultados «{screen['title']}» a todos")
        return await self._results_state()

    async def rpc_gm_results_hide(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        self.results.show(None)
        await self.hub.broadcast({"t": "results", "screen": None})
        self.gm.log.add(actor, "Quitó los resultados de las pantallas")
        return await self._results_state()

    async def rpc_gm_results_delete(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        sid = str(args.get("id") or "")
        screen = self.results.get(sid)
        was_showing = self.results.showing == sid
        self.results.delete(sid)
        if was_showing:
            await self.hub.broadcast({"t": "results", "screen": None})
        self.gm.log.add(actor, f"Borró la pantalla de resultados «{screen['title'] if screen else sid}»")
        return await self._results_state()

    async def rpc_gm_results_auto(self, conn: Conn, args: dict):
        await self._gm(conn)
        self.results.auto = bool(args.get("on"))
        self.results.save()
        return await self._results_state()

    async def rpc_gm_results_reset(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        self.round.reset(_t(args.get("title"), 80) or "Ronda")
        self.gm.log.add(actor, f"Empezó una ronda nueva de resultados: «{self.round.title}»")
        return await self._results_state()

    async def rpc_results_get(self, conn: Conn, args: dict):
        return {"screen": self.results.get(self.results.showing or self.results.last), "showing": self.results.showing is not None}
