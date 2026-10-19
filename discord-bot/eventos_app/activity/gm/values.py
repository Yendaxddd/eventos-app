"""The game's numbers (what /editvalues, /editqte and /config change), with the limits those commands use, and a file that keeps them
between sessions (the bot itself forgets what /editvalues changes when it restarts)."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import NamedTuple

from ..hub import RpcError
from .common import DIFFICULTIES, DIFFICULTY_ES, finite, number

log = logging.getLogger("eventos_app.activity")


class Spec(NamedTuple):
    key: str
    group: str
    label: str
    hint: str
    kind: str            # int | float | percent (stored as a fraction) | bool
    lo: float
    hi: float
    step: float
    persist: str         # "live" (the bot keeps it in live_config.json) | "file" (this panel's file)
    unit: str = ""


GROUPS = [
    ("players", "Jugadores"), ("bf", "Black Flash"), ("power", "Poderes y cargas"), ("combat", "Combate"),
]

SPECS: list[Spec] = [
    Spec("max_hp", "players", "Vida máxima", "Vida de todos los jugadores. Al cambiarla, la vida actual de cada uno se ajusta en proporción.", "int", 1, 9999, 5, "file", "HP"),
    Spec("regen_amount", "players", "Curación por checkpoint", "HP que recupera cada jugador vivo en cada checkpoint.", "int", 0, 9999, 5, "file", "HP"),
    Spec("save_limit", "players", "Rescates por ventana", "Cuántos compañeros puede rescatar alguien en la ventana de tiempo de abajo.", "int", 0, 20, 1, "file"),
    Spec("save_time_window", "players", "Ventana de rescates", "Segundos que cuentan los rescates ya hechos.", "int", 5, 600, 5, "file", "s"),
    Spec("black_flash_base_chance", "bf", "Probabilidad base de Black Flash", "Con la que empieza cada jugador.", "percent", 0, 100, 1, "file", "%"),
    Spec("black_flash_increment", "bf", "Sube por acierto", "Lo que sube la probabilidad cada vez que alguien acierta sin conseguirlo.", "percent", 0, 100, 1, "file", "%"),
    Spec("black_flash_cap", "bf", "Probabilidad máxima", "Tope de la probabilidad de Black Flash.", "percent", 0, 100, 1, "file", "%"),
    Spec("bf_timing_window", "bf", "Margen del primer Black Flash", "Segundos de margen alrededor del parry perfecto.", "float", 0.05, 1.0, 0.05, "live", "s"),
    Spec("bf_chain_timing_window", "bf", "Margen de la cadena", "Margen de los Black Flash siguientes de una cadena (más justo).", "float", 0.05, 1.0, 0.05, "file", "s"),
    Spec("charge_per_damage_dealt", "power", "Carga por daño hecho", "% de carga cada 10 puntos de daño que haces.", "float", 0, 20, 0.5, "live", "%"),
    Spec("charge_per_damage_taken", "power", "Carga por daño recibido", "% de carga cada 5 puntos de daño que recibes.", "float", 0, 20, 0.5, "file", "%"),
    Spec("charge_per_counter", "power", "Carga por contraataque", "% de carga por cada contraataque.", "float", 0, 20, 0.5, "file", "%"),
    Spec("ultimate_cost", "power", "Carga necesaria", "% de carga para poder usar un poder. La carga de un poder nunca pasa del 100 %, así que más no se podría alcanzar.", "float", 1, 100, 5, "file", "%"),
    Spec("ultimate_base_cooldown", "power", "Recarga base de los poderes", "Segundos (solo cuentan durante el combate).", "int", 0, 86400, 30, "live", "s"),
    Spec("ultimate_cooldown_per_damage", "power", "Recarga extra por daño", "Segundos de recarga por cada punto de daño del poder.", "float", 0, 5, 0.1, "file", "s"),
    Spec("ultimate_max_damage", "power", "Daño máximo de un poder", "Tope del daño de cualquier poder.", "int", 0, 99999, 50, "live"),
    Spec("ultimate_self_recharge", "power", "El poder se recarga a sí mismo", "Si el daño del propio poder da carga.", "bool", 0, 1, 1, "file"),
    Spec("counter_window", "combat", "Ventana de contraataque", "Segundos para contraatacar tras un esquive.", "float", 0.5, 5, 0.1, "file", "s"),
    Spec("revenge_threshold", "combat", "Modo venganza desde", "Al bajar de este % de vida, el jugador entra en modo venganza.", "percent", 0, 100, 1, "live", "%"),
    Spec("revenge_damage_multiplier", "combat", "Daño en venganza", "Multiplicador de daño en modo venganza.", "float", 1, 10, 0.1, "live", "×"),
    Spec("revenge_bf_bonus", "combat", "Black Flash extra en venganza", "% extra de probabilidad en modo venganza.", "percent", 0, 100, 1, "live", "%"),
    Spec("latency_offset", "combat", "Tolerancia de latencia del bot", "Segundos de gracia por los retrasos de Discord e internet.", "float", 0, 1, 0.05, "file", "s"),
]
BY_KEY = {spec.key: spec for spec in SPECS}
LIVE_KEYS = ("revenge_threshold", "revenge_damage_multiplier", "revenge_bf_bonus", "bf_timing_window", "ultimate_base_cooldown", "charge_per_damage_dealt", "ultimate_max_damage")


def _read(app, spec: Spec):
    raw = getattr(app, spec.key, 0)
    if spec.kind == "bool":
        return bool(raw)
    value = finite(raw)
    return round(value * 100, 2) if spec.kind == "percent" else (int(value) if spec.kind == "int" else round(value, 3))


def _parse(spec: Spec, value):
    """The value as the bot stores it, or RpcError saying what is wrong."""
    if spec.kind == "bool":
        if not isinstance(value, bool):
            raise RpcError(f"«{spec.label}» es sí o no.")
        return value
    parsed = number(value, spec.label, spec.lo, spec.hi, integer=spec.kind == "int")
    return parsed / 100.0 if spec.kind == "percent" else parsed


class ValueOps:
    values_file: Path | None = None

    # ---- reading ------------------------------------------------------------------------------------------------------------
    def values(self) -> dict:
        app = self.app
        groups = []
        for gid, title in GROUPS:
            items = [{"key": s.key, "label": s.label, "hint": s.hint, "kind": s.kind, "value": _read(app, s), "min": s.lo, "max": s.hi, "step": s.step, "unit": s.unit}
                     for s in SPECS if s.group == gid]
            groups.append({"id": gid, "title": title, "items": items})
        times, timeouts, damage = app.qte_times, getattr(app, "qte_timeout_durations", {}) or {}, app.damage_ranges
        qte = {}
        for diff in DIFFICULTIES:
            t = times.get(diff, {})
            window = t.get("parry_window") or (0, 0)
            low, high = (damage.get(diff) or (0, 0))[:2] if isinstance(damage.get(diff), (tuple, list)) else (0, 0)
            qte[diff] = {"evade": finite(t.get("evade_window")), "parryStart": finite(window[0]), "parryEnd": finite(window[1]), "perfect": finite(t.get("perfect_parry")),
                         "timeout": finite(timeouts.get(diff)), "damageMin": int(finite(low)), "damageMax": int(finite(high))}
        return {"groups": groups, "qte": qte, "difficulties": [[d, DIFFICULTY_ES[d]] for d in DIFFICULTIES]}

    # ---- changing -----------------------------------------------------------------------------------------------------------
    async def set_value(self, actor: str, key: str, value) -> dict:
        app = self.app
        spec = BY_KEY.get(key)
        if spec is None:
            raise RpcError("Ese valor no existe.")
        new = _parse(spec, value)
        old = getattr(app, key, None)
        if key == "max_hp":
            await self._rescale_hp(int(old or 100), int(new))
        setattr(app, key, new)
        self._persist(spec)
        self.log.add(actor, f"{spec.label}: {self._shown(spec, old)} → {self._shown(spec, new)}")
        return self.values()

    @staticmethod
    def _shown(spec: Spec, raw) -> str:
        if spec.kind == "bool":
            return "sí" if raw else "no"
        value = finite(raw) * (100 if spec.kind == "percent" else 1)
        return f"{value:g}".replace(".", ",") + (f" {spec.unit}" if spec.unit else "")

    async def _rescale_hp(self, old: int, new: int) -> None:
        """/editvalues player_hp: everybody's maximum changes and their current HP follows in proportion."""
        app = self.app
        for uid, hp in list(app.player_hp.items()):
            before = max(1, int(finite(hp.get("max"), old)))
            hp["max"] = new
            hp["current"] = max(1, min(new, int(finite(hp.get("current")) / before * new))) if hp.get("alive", True) else hp.get("current", 0)
            await app.update_hp_bar_display(uid)

    def set_qte(self, actor: str, difficulty: str, data: dict) -> dict:
        """/editqte, for one difficulty: the windows (seconds) and the damage."""
        app = self.app
        if difficulty not in DIFFICULTIES:
            raise RpcError("La dificultad no es válida.")
        evade = float(number(data.get("evade"), "Ventana de esquive", 0.1, 30))
        start = float(number(data.get("parryStart"), "Inicio del parry", 0, 30))
        end = float(number(data.get("parryEnd"), "Fin del parry", 0.1, 30))
        if start >= end:
            raise RpcError("El parry debe empezar antes de acabar.")
        perfect = float(number(data.get("perfect"), "Parry perfecto", 0, 30))
        if not start <= perfect <= end:
            raise RpcError("El parry perfecto debe estar dentro de la ventana del parry.")
        timeout = float(number(data.get("timeout"), "Tiempo límite", 0.5, 60))
        if timeout < end:
            raise RpcError("El tiempo límite no puede ser menor que el final del parry.")
        low = int(number(data.get("damageMin"), "Daño mínimo", 0, 9999, integer=True))
        high = int(number(data.get("damageMax"), "Daño máximo", 0, 9999, integer=True))
        if low > high:
            raise RpcError("El daño mínimo no puede ser mayor que el máximo.")
        app.qte_times[difficulty].update({"evade_window": evade, "parry_window": (start, end), "perfect_parry": perfect})
        app.damage_ranges[difficulty] = (low, high)
        if getattr(app, "qte_timeout_durations", None) is not None:
            app.qte_timeout_durations[difficulty] = timeout
        app.save_qte_settings()
        self._persist_file()
        self.log.add(actor, f"Cambió los tiempos y el daño de los QTE {DIFFICULTY_ES[difficulty]}s")
        return self.values()

    # ---- keeping them -------------------------------------------------------------------------------------------------------
    def _persist(self, spec: Spec) -> None:
        if spec.persist == "live" and callable(getattr(self.app, "save_live_config", None)):
            self.app.save_live_config()
        self._persist_file()

    def _snapshot(self) -> dict:
        snapshot = {spec.key: _read(self.app, spec) for spec in SPECS if spec.persist == "file"}
        timeouts = getattr(self.app, "qte_timeout_durations", None)
        if timeouts:
            snapshot["qte_timeout_durations"] = {d: finite(v) for d, v in timeouts.items()}
        snapshot["qte_variations"] = {k: int(v.get("weight", 0)) for k, v in (getattr(self.app, "qte_variations", {}) or {}).items()}
        snapshot["current_qte_mode"] = getattr(self.app, "current_qte_mode", "standard")
        return snapshot

    def _persist_file(self) -> None:
        if self.values_file is None:
            return
        try:
            self.values_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.values_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._snapshot(), ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.values_file)
        except OSError:
            log.warning("could not save %s", self.values_file)

    def persist_all(self) -> None:
        """Called when the QTE mode or its weights change (they have no spec of their own)."""
        self._persist_file()

    def apply_saved(self) -> int:
        """At start: the values this panel kept, checked again, back into the bot. Returns how many were applied."""
        if self.values_file is None or not self.values_file.exists():
            return 0
        try:
            saved = json.loads(self.values_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            log.warning("could not read %s", self.values_file)
            return 0
        if not isinstance(saved, dict):
            return 0
        applied = 0
        for key, value in saved.items():
            spec = BY_KEY.get(key)
            try:
                if spec is not None and spec.persist == "file":
                    setattr(self.app, key, _parse(spec, value))
                    applied += 1
                elif key == "qte_timeout_durations" and isinstance(value, dict):
                    for diff, seconds in value.items():
                        if diff in DIFFICULTIES:
                            self.app.qte_timeout_durations[diff] = float(number(seconds, "Tiempo límite", 0.5, 60))
                            applied += 1
                elif key == "qte_variations" and isinstance(value, dict):
                    for name, weight in value.items():
                        if name in self.app.qte_variations:
                            self.app.qte_variations[name]["weight"] = int(number(weight, "Probabilidad", 0, 100, integer=True))
                            applied += 1
                elif key == "current_qte_mode" and value in ("standard", "combo", "direction", "random"):
                    self.app.current_qte_mode = value
                    applied += 1
            except (RpcError, AttributeError, TypeError):
                log.warning("saved value %r ignored", key)
        return applied
