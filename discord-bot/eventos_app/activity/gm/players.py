"""The players, one by one: HP, charges, cooldowns, skill points, achievements, objects and their adaptation, as the GM commands do."""
from __future__ import annotations

from ..hub import RpcError
from ..panel import PlayerPanel
from .common import DIFFICULTIES, finite, number, text

MAX_ROWS = 400


def _object_error(message: str) -> RpcError:
    """The special-objects manager answers in English: its refusals, in Spanish."""
    lowered = str(message).lower()
    for needle, spanish in (("not found", "Ese objeto no existe."), ("already owned", "Ese objeto único ya lo tiene otra persona."),
                            ("already has", "Ya tiene ese objeto."), ("not enough slots", "No tiene espacios suficientes en el inventario."),
                            ("doesn't have", "No tiene ese objeto."), ("has no objects", "No tiene objetos."), ("not tradeable", "Ese objeto no se puede intercambiar.")):
        if needle in lowered:
            return RpcError(spanish)
    return RpcError("No se pudo hacer el cambio con el objeto.")


class PlayerOps:
    # ---- who is there ---------------------------------------------------------------------------------------------------
    def player_ids(self) -> list[int]:
        app = self.app
        found: set[int] = set()
        for table in (getattr(app, "player_hp", {}), getattr(app, "power_charges", {}), getattr(app, "user_characters", {})):
            found.update(k for k in (table or {}) if isinstance(k, int))
        for table in (getattr(app, "player_skills", {}), getattr(app, "player_achievements", {})):
            for key in (table or {}):
                if isinstance(key, str) and key.isdigit():
                    found.add(int(key))
        for uid, stats in (getattr(app, "player_stats", {}) or {}).items():
            if isinstance(uid, int) and isinstance(stats, dict) and stats.get("total_attempts"):
                found.add(uid)
        found.update(m.id for m in (getattr(app, "qte_players", []) or []) if hasattr(m, "id"))
        manager = getattr(app, "special_objects_manager", None)
        if manager is not None:
            found.update(k for k in manager.player_inventory if isinstance(k, int))
        found.update(getattr(app, "afk_users", set()) or set())
        return sorted(i for i in found if i > 0)[:MAX_ROWS]

    def _row(self, uid: int, who: tuple[str, str | None], online: bool) -> dict:
        app = self.app
        hp = (getattr(app, "player_hp", {}) or {}).get(uid)
        charges = (getattr(app, "power_charges", {}) or {}).get(uid, {})
        stats = (getattr(app, "player_stats", {}) or {}).get(uid) or {}
        attempts = int(finite(stats.get("total_attempts")))
        return {
            "id": str(uid), "name": who[0], "avatar": who[1], "online": online,
            "hp": None if not hp else {"current": int(finite(hp.get("current"))), "max": int(finite(hp.get("max"))), "alive": bool(hp.get("alive", True)), "revenge": bool(hp.get("revenge_mode"))},
            "charges": [round(finite(charges.get("power1")), 1), round(finite(charges.get("power2")), 1)],
            "points": int(finite((getattr(app, "player_skills", {}) or {}).get(str(uid), {}).get("skill_points"))),
            "afk": uid in (getattr(app, "afk_users", set()) or set()),
            "characters": len((getattr(app, "user_characters", {}) or {}).get(uid, [])),
            "attempts": attempts, "rate": round(finite(stats.get("successful")) / attempts * 100, 1) if attempts else 0.0,
        }

    def rows(self, people: dict[int, tuple[str, str | None]], online: set[int]) -> list[dict]:
        return [self._row(uid, people.get(uid, (f"Jugador …{str(uid)[-4:]}", None)), uid in online) for uid in self.player_ids()]

    def player(self, uid: int, who: tuple[str, str | None], online: bool = False) -> dict:
        app = self.app
        panel = PlayerPanel(app)
        config = getattr(app, "achievements_config", None) or {}
        mine = (getattr(app, "player_achievements", {}) or {}).get(str(uid)) or {}
        achievements = [{"id": a, "name": text((config.get("achievements", {}).get(a) or {}).get("name", a), 80), "date": text((v or {}).get("date"), 32) if isinstance(v, dict) else None}
                        for a, v in mine.items() if a in (config.get("achievements") or {})]
        skills = (getattr(app, "player_skills", {}) or {}).get(str(uid), {}) or {}
        manager = getattr(app, "special_objects_manager", None)
        catalog_objects = []
        if manager is not None:
            owners = getattr(manager, "unique_object_owners", {}) or {}
            catalog_objects = [{"id": oid, "name": text(o.get("name", oid), 80), "unique": bool(o.get("unique")), "owner": str(owners[oid]) if oid in owners else None}
                               for oid, o in sorted(manager.objects.items())]
        return {
            "row": self._row(uid, who, online), "inventory": panel.inventory(uid), "profile": panel.profile(uid),
            "achievements": achievements, "titles": [t for t in (mine.get("titles") or []) if isinstance(t, str)],
            "skills": {k: int(finite(v)) for k, v in (skills.get("skills") or {}).items() if finite(v) > 0},
            "catalog": {"achievements": [{"id": a, "name": text(d.get("name", a), 80), "icon": text(d.get("icon", "🏆"), 8), "hidden": bool(d.get("hidden"))}
                                         for a, d in (config.get("achievements") or {}).items()], "objects": catalog_objects},
        }

    # ---- HP, charges, cooldowns ---------------------------------------------------------------------------------------------
    async def set_hp(self, actor: str, uid: int, label: str, current=None, maximum=None) -> None:
        app = self.app
        if current is None and maximum is None:
            raise RpcError("Indica la vida o la vida máxima.")
        if uid not in app.player_hp:
            await app.initialize_player_hp(uid)
        hp = app.player_hp[uid]
        new_max = int(number(maximum, "Vida máxima", 1, 9999, integer=True)) if maximum is not None else int(finite(hp.get("max"), 100))
        new_current = int(number(current, "Vida", 1, new_max, integer=True)) if current is not None else min(int(finite(hp.get("current"))), new_max)
        hp["max"], hp["current"] = new_max, new_current                                                 # both checked first: a refusal changes nothing
        if current is not None:
            hp["alive"] = True
        await app.update_hp_bar_display(uid)
        self.log.add(actor, f"Puso la vida de {label} en {hp['current']}/{hp['max']}")

    async def reset_hp(self, actor: str, uid: int | None, label: str = "") -> int:
        """/resethp: everyone (and the Faith system) or one player back to full health."""
        app = self.app
        targets = [uid] if uid is not None else list(app.player_hp.keys())
        if uid is not None and uid not in app.player_hp:
            raise RpcError("Esa persona todavía no tiene vida registrada.")
        for target in targets:
            app.player_hp[target] = {"current": app.max_hp, "max": app.max_hp, "alive": True, "revenge_mode": False}
            await app.update_hp_bar_display(target)
        if uid is None:
            app.reset_faith_system()
        self.log.add(actor, f"Restauró la vida de {label}" if uid is not None else f"Restauró la vida de {len(targets)} jugadores")
        return len(targets)

    def set_charges(self, actor: str, uid: int, label: str, power1, power2) -> None:
        app = self.app
        top = max(100.0, finite(getattr(app, "ultimate_cost", 100), 100))
        first = round(float(number(power1, "Carga del poder 1", 0, top)), 1)
        second = round(float(number(power2, "Carga del poder 2", 0, top)), 1)
        app.power_charges[uid] = {**app.power_charges.get(uid, {}), "power1": first, "power2": second}
        app.save_all_data(force=True)
        self.log.add(actor, f"Puso las cargas de {label} en {first:g} % y {second:g} %".replace(".", ","))

    def reset_cooldowns(self, actor: str, uid: int, label: str) -> None:
        app = self.app
        for table in ("power_cooldowns", "ultimate_fight_cooldowns", "domain_cooldowns"):
            (getattr(app, table, {}) or {}).pop(uid, None)
        self.log.add(actor, f"Reinició las recargas de {label}")

    def set_afk(self, actor: str, uid: int, label: str, afk) -> None:
        app = self.app
        if afk:
            app.afk_users.add(uid)
        else:
            app.afk_users.discard(uid)
        self.log.add(actor, f"{label} {'queda fuera de los QTE' if afk else 'vuelve a los QTE'}")

    # ---- skill points and achievements --------------------------------------------------------------------------------------
    def give_points(self, actor: str, uid: int, label: str, amount) -> None:
        app = self.app
        change = int(number(amount, "Puntos", -9999, 9999, integer=True))
        if change == 0:
            raise RpcError("Indica cuántos puntos dar o quitar.")
        mine = app.player_skills.setdefault(str(uid), {"skill_points": 0, "skills": {}})
        total = int(finite(mine.get("skill_points"))) + change
        if total < 0:
            raise RpcError("No tiene tantos puntos como quieres quitar.")
        mine["skill_points"] = total
        app.save_all_data(force=True)
        self.log.add(actor, f"{'Dio' if change > 0 else 'Quitó'} {abs(change)} puntos de habilidad a {label} (ahora {total})")

    def reset_skills(self, actor: str, uid: int, label: str) -> int:
        """Forget every learned skill and give the points back (what each rank cost)."""
        app = self.app
        mine = app.player_skills.get(str(uid)) or {}
        ranks = {k: int(finite(v)) for k, v in (mine.get("skills") or {}).items() if finite(v) > 0}
        if not ranks:
            raise RpcError("No tiene habilidades aprendidas.")
        costs = {s.get("id"): int(finite(s.get("cost"), 1)) for tree in (app.skill_tree_config or {}).values()
                 for branch in (tree.get("branches") or {}).values() for s in (branch.get("skills") or [])}
        refund = sum(costs.get(sid, 1) * rank for sid, rank in ranks.items())
        mine["skills"] = {}
        mine["skill_points"] = int(finite(mine.get("skill_points"))) + refund
        app.save_all_data(force=True)
        self.log.add(actor, f"Reinició las habilidades de {label} y le devolvió {refund} puntos")
        return refund

    async def grant_achievement(self, actor: str, uid: int, label: str, achievement_id) -> None:
        app = self.app
        achievement_id = str(achievement_id or "")
        config = getattr(app, "achievements_config", None) or {}
        data = (config.get("achievements") or {}).get(achievement_id)
        if data is None:
            raise RpcError("Ese logro no existe.")
        if achievement_id in ((getattr(app, "player_achievements", {}) or {}).get(str(uid)) or {}):
            raise RpcError("Ya tiene ese logro.")
        if not await app.award_achievement(uid, achievement_id):
            raise RpcError("No se pudo dar el logro.")
        self.log.add(actor, f"Dio el logro «{data.get('name', achievement_id)}» a {label}")

    def remove_achievement(self, actor: str, uid: int, label: str, achievement_id) -> None:
        """/removeachievement: the achievement goes, and so do its title and domain (the points stay: they may be spent)."""
        app = self.app
        achievement_id = str(achievement_id or "")
        mine = (getattr(app, "player_achievements", {}) or {}).get(str(uid))
        if not mine or achievement_id not in mine:
            raise RpcError("No tiene ese logro.")
        data = ((getattr(app, "achievements_config", None) or {}).get("achievements") or {}).get(achievement_id, {})
        reward = data.get("reward", {}) or {}
        del mine[achievement_id]
        title = reward.get("title")
        if title and title in (mine.get("titles") or []):
            mine["titles"].remove(title)
            if mine.get("active_title") == title:
                mine.pop("active_title", None)
                if mine["titles"]:
                    mine["active_title"] = mine["titles"][0]
        domain = reward.get("domain")
        if domain and domain in (mine.get("domains") or []):
            mine["domains"].remove(domain)
            if mine.get("active_domain") == domain:
                mine.pop("active_domain", None)
                if mine["domains"]:
                    mine["active_domain"] = mine["domains"][0]
        app.save_all_data(force=True)
        self.log.add(actor, f"Quitó el logro «{data.get('name', achievement_id)}» a {label}")

    # ---- special objects ----------------------------------------------------------------------------------------------------
    def _manager(self):
        manager = getattr(self.app, "special_objects_manager", None)
        if manager is None:
            raise RpcError("Los objetos especiales no están disponibles.")
        return manager

    def _owned(self, uid: int, object_id: str) -> dict:
        manager = self._manager()
        obj = manager.objects.get(object_id)
        if obj is None:
            raise RpcError("Ese objeto no existe.")
        if object_id not in manager.player_inventory.get(uid, []) and manager.unique_object_owners.get(object_id) != uid:
            raise RpcError("No tiene ese objeto.")
        return obj

    def give_object(self, actor: str, uid: int, label: str, object_id) -> None:
        ok, message = self._manager().give_object(uid, str(object_id or ""))
        if not ok:
            raise _object_error(message)
        self.log.add(actor, f"Dio el objeto «{object_id}» a {label}")

    def take_object(self, actor: str, uid: int, label: str, object_id) -> None:
        ok, message = self._manager().take_object(uid, str(object_id or ""))
        if not ok:
            raise _object_error(message)
        self.log.add(actor, f"Quitó el objeto «{object_id}» a {label}")

    def set_spins(self, actor: str, uid: int, label: str, object_id, values) -> None:
        object_id = str(object_id or "")
        obj = self._owned(uid, object_id)
        manager = self._manager()
        tracking = obj.get("tracking") or {}
        kind = tracking.get("type", "per_difficulty") if isinstance(tracking, dict) else "per_difficulty"
        keys = ("total",) if kind == "total" else DIFFICULTIES
        if not isinstance(values, dict) or not values:
            raise RpcError("Indica las vueltas.")
        clean = {}
        for key, value in values.items():
            if key not in keys:
                raise RpcError("Esa clase de vuelta no existe en este objeto.")
            clean[key] = int(number(value, f"Vueltas ({key})", 0, 99999, integer=True))
        for key, value in clean.items():
            manager.set_tracking(uid, object_id, key, value)
        manager.save_tracking()
        self.log.add(actor, f"Cambió las vueltas de «{object_id}» de {label}")

    def reset_spins(self, actor: str, uid: int, label: str, object_id) -> None:
        object_id = str(object_id or "")
        obj = self._owned(uid, object_id)
        manager = self._manager()
        tracking = obj.get("tracking") or {}
        kind = tracking.get("type", "per_difficulty") if isinstance(tracking, dict) else "per_difficulty"
        for key in (("total",) if kind == "total" else DIFFICULTIES):
            manager.set_tracking(uid, object_id, key, 0)
        warned = (getattr(self.app, "max_adaptation_warned", {}) or {}).get(uid)
        if warned:
            warned.pop(object_id, None)
        manager.save_tracking()
        self.log.add(actor, f"Reinició las vueltas de «{object_id}» de {label}")

    def set_slots(self, actor: str, uid: int, label: str, slots) -> None:
        count = int(number(slots, "Espacios", 1, 99, integer=True))
        self._manager().set_player_max_slots(uid, count)
        self.log.add(actor, f"Puso los espacios de inventario de {label} en {count}")
