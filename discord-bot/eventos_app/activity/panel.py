"""The player's own dashboards for the Activity: what `/dashboard`, `/mystats`, `/achievements`, `/skills`, `/inventory`,
`/leaderboard`, `/mycharacters`, `/registerpower` and `/setcountergif` show and do, as data the screen can draw.

Everything reads and writes the bot's own tables and follows the rules of the slash commands, so the screen is another way
of doing what the commands already allow, never more. Whoever asks is always the player the connection belongs to (the
server knows it from Discord), never an id sent by the page.
"""
from __future__ import annotations

import math
import re
import time
from typing import Any

from ..i18n import describe_object_effect, describe_skill_effect, tr
from .hub import RpcError
from .. import powers as power_rules

MAX_CHARACTER_NAME = 80
MAX_CHARACTERS = 25                 # per player: far more than anyone plays, and the «jugar como» list stays usable
MAX_POWER_NAME, MAX_POWER_TEXT, MAX_EFFECT, MAX_TRIGGER = 50, 900, 160, 100
MAX_COOLDOWN = 86_400
MAX_URL = 600
MAX_COUNTER_IMAGES = 20
RECENT_TIMES = 40                   # response times drawn in the stats chart
LEADERBOARD_ROWS = 10

CATEGORIES = ("success_rate", "black_flashes", "parry_streak", "total_attempts", "best_time", "saves")
PROGRESS_STATS = {                  # achievement trigger -> the player's stat that counts toward it
    "evade_count": "evades", "evade_streak": "best_evade_streak", "parry_count": "parries", "black_flash_count": "black_flashes",
}
POWER_SHOW = ("all", "self", "off")       # who sees the power's picture fill the screen in the Activity
DIFFICULTIES = ("easy", "medium", "hard", "impossible")


_TR = []


def spanish(text: str) -> str:
    """A message of the bot, in Spanish and without Discord's bold marks (the panel shows it as plain text)."""
    if not _TR:
        try:
            from ..lang.translator import load
            _TR.append(load())
        except Exception:  # noqa: BLE001 - no catalogue: the English text
            _TR.append(None)
    out = _TR[0].text(text) if _TR[0] is not None else text
    return out.replace("**", "").replace("\n", " ").strip()


def _text(value: Any, limit: int) -> str:
    return "" if value is None else str(value)[:limit]


def _number(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _int(value: Any, default: int = 0) -> int:
    return int(_number(value, default))


def _dec(value: float, digits: int = 1) -> str:
    """12.5 -> "12,5", 90.0 -> "90": the decimal comma, and no useless ",0"."""
    text = f"{value:.{digits}f}".rstrip("0").rstrip(".") if digits else f"{value:.0f}"
    return text.replace(".", ",")


def _clean_line(value: Any, limit: int) -> str:
    """One line of text typed by a player: no control characters, no line breaks, trimmed."""
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", str(value if value is not None else ""))
    return re.sub(r"\s{2,}", " ", text).strip()[:limit]


def _url(value: Any) -> str | None:
    """A picture's address: https only (the page shows it through the app's own media proxy)."""
    text = str(value or "").strip()
    if not text:
        return None
    if len(text) > MAX_URL or not re.fullmatch(r"https://[^\s<>\"']+", text):
        raise RpcError("La imagen debe ser un enlace https válido.")
    return text


class PlayerPanel:
    def __init__(self, app: Any) -> None:
        self.app = app

    # ---- small readers ----------------------------------------------------------------------------------------------
    def _stats(self, uid: int) -> dict:
        return (getattr(self.app, "player_stats", {}) or {}).get(uid) or {}

    def _ach_of(self, uid: int) -> dict:
        return (getattr(self.app, "player_achievements", {}) or {}).get(str(uid)) or {}

    def _config(self) -> dict:
        return getattr(self.app, "achievements_config", None) or {}

    def _skills_of(self, uid: int) -> dict:
        return (getattr(self.app, "player_skills", {}) or {}).get(str(uid)) or {}

    def _manager(self):
        return getattr(self.app, "special_objects_manager", None)

    def _characters(self, uid: int) -> list[str]:
        try:
            return sorted(self.app.get_user_characters(uid))
        except Exception:  # noqa: BLE001
            return []

    def _save(self) -> None:
        self.app.save_all_data(force=True)         # a change made here must not wait for the bot's save throttle

    # ---- profile ---------------------------------------------------------------------------------------------------
    @staticmethod
    def _rate(stats: dict) -> float:
        attempts = _int(stats.get("total_attempts"))
        return round(_int(stats.get("successful")) / attempts * 100, 1) if attempts > 0 else 0.0

    def _board_value(self, category: str, stats: dict):
        """(sortable value, text) of one player for a leaderboard category; None when there is nothing to rank."""
        if category == "success_rate":
            value = self._rate(stats)
            return value, f"{_dec(value)} %"
        if category == "best_time":
            best = _number(stats.get("best_time"), float("inf"))
            if not math.isfinite(best) or best <= 0 or best >= 999:
                return None
            return -best, f"{_dec(best, 2)} s"
        key = {"black_flashes": "black_flashes", "parry_streak": "best_parry_streak", "total_attempts": "total_attempts", "saves": "saves"}[category]
        value = _int(stats.get(key))
        return value, str(value)

    def ranking(self, category: str) -> list[dict]:
        """Everyone with stats, best first: [{id, value, text}] (names are added by whoever can look them up)."""
        if category not in CATEGORIES:
            raise RpcError("Esa clasificación no existe.")
        rows = []
        for uid, stats in (getattr(self.app, "player_stats", {}) or {}).items():
            if not isinstance(stats, dict) or not _int(stats.get("total_attempts")):
                continue
            scored = self._board_value(category, stats)
            if scored is not None:
                rows.append({"id": int(uid), "value": scored[0], "text": scored[1]})
        rows.sort(key=lambda r: (-r["value"], r["id"]))
        for place, row in enumerate(rows, 1):
            row["rank"] = place
        return rows

    def profile(self, uid: int) -> dict:
        app = self.app
        stats = self._stats(uid)
        ach, config = self._ach_of(uid), self._config()
        attempts = _int(stats.get("total_attempts"))
        streak = _int(stats.get("parry_streak"))
        best = _number(stats.get("best_time"), float("inf"))
        avg = _number(stats.get("avg_time"), 0.0)
        times = [round(t, 2) for t in (_number(x, -1) for x in list(stats.get("times") or [])[-RECENT_TIMES:]) if 0 < t < 60]
        cost = _number(getattr(app, "ultimate_cost", 100), 100) or 100
        charges = []
        for slot in (1, 2):
            pct = _number((getattr(app, "power_charges", {}) or {}).get(uid, {}).get(f"power{slot}"), 0.0)
            name, owner = f"Poder {slot}", None
            for char in self._characters(uid):
                power = (getattr(app, "character_powers", {}) or {}).get(char, {}).get(f"power{slot}")
                if power:
                    name, owner = _text(power.get("name"), MAX_POWER_NAME), char
                    break
            charges.append({"slot": slot, "name": name, "character": owner, "pct": round(pct, 1), "ready": pct >= cost})
        domains = config.get("domains", {}) or {}
        active_domain = ach.get("active_domain")
        achievements = config.get("achievements", {}) or {}
        learned = sum(1 for r in (self._skills_of(uid).get("skills") or {}).values() if _int(r) > 0)
        manager = self._manager()
        objects = slots_used = slots_max = 0
        if manager is not None:
            objects = len(self._owned_objects(uid))
            slots_used, slots_max = manager.get_used_slots(uid), manager.get_player_max_slots(uid)
        ranks = {}
        if attempts:
            for category in CATEGORIES:
                for row in self.ranking(category):
                    if row["id"] == uid:
                        ranks[category] = row["rank"]
        return {
            "stats": {
                "attempts": attempts, "ok": _int(stats.get("successful")), "failed": _int(stats.get("failed")), "rate": self._rate(stats),
                "evades": _int(stats.get("evades")), "parries": _int(stats.get("parries")), "saves": _int(stats.get("saves")),
                "adapts": _int(stats.get("adapts")), "best": round(best, 2) if math.isfinite(best) and 0 < best < 999 else None,
                "avg": round(avg, 2) if avg > 0 else None, "streak": _int(stats.get("current_streak")), "bestStreak": _int(stats.get("best_streak")),
                "parryStreak": streak, "bestParryStreak": _int(stats.get("best_parry_streak")), "multiplier": round(min(2.0, 1.0 + streak * 0.1), 1),
                "evadeStreak": _int(stats.get("evade_streak")), "bestEvadeStreak": _int(stats.get("best_evade_streak")),
                "bfChance": round(_number(stats.get("black_flash_chance"), 0.01) * 100, 1), "bf": _int(stats.get("black_flashes")),
                "times": times,
            },
            "charges": charges, "cost": round(cost),
            "points": _int(self._skills_of(uid).get("skill_points")),
            "title": ach.get("active_title") or None,
            "domain": ({"id": active_domain, "name": _text((domains.get(active_domain) or {}).get("name", active_domain), 60)}
                       if active_domain and active_domain in (ach.get("domains") or []) else None),
            "counts": {"achievements": [sum(1 for a in ach if a in achievements), len(achievements)], "characters": len(self._characters(uid)),
                       "skills": learned, "objects": objects, "slots": [slots_used, slots_max]},
            "ranks": ranks, "players": len([1 for s in (getattr(app, "player_stats", {}) or {}).values() if isinstance(s, dict) and _int(s.get("total_attempts"))]),
            "active": uid not in (getattr(app, "afk_users", set()) or set()),
        }

    def set_active(self, uid: int, active: bool) -> dict:
        """The `/qte` command: take part in the QTEs or stay out of them."""
        afk = getattr(self.app, "afk_users", None)
        if afk is None:
            raise RpcError("Esta opción no está disponible.")
        if active:
            afk.discard(uid)
        else:
            afk.add(uid)
        return {"active": uid not in afk}

    # ---- achievements, titles, domains -----------------------------------------------------------------------------
    def achievements(self, uid: int) -> dict:
        config, ach, stats = self._config(), self._ach_of(uid), self._stats(uid)
        domains_cfg = config.get("domains", {}) or {}
        categories = config.get("categories", {}) or {}
        listed = config.get("achievements", {}) or {}
        out_categories, unlocked = [], 0
        order = dict.fromkeys([*categories, *(a.get("category") for a in listed.values())])
        for cat_id in (c for c in order if c):
            cat = categories.get(cat_id, {})
            items = []
            for ach_id, data in listed.items():
                if data.get("category") != cat_id:
                    continue
                mine = ach.get(ach_id)
                have = bool(mine.get("unlocked", True)) if isinstance(mine, dict) else bool(mine)
                if have:
                    unlocked += 1
                if data.get("hidden") and not have:       # a secret stays one: nothing about it leaves the server
                    items.append({"id": ach_id, "secret": True, "unlocked": False, "icon": "❓", "name": "???", "description": "Logro secreto: se descubre al conseguirlo."})
                    continue
                reward = data.get("reward", {}) or {}
                domain = reward.get("domain")
                trigger = str(data.get("trigger", ""))
                kind, _, needed = trigger.partition(":")
                progress = None
                if kind in PROGRESS_STATS and needed.isdigit() and not have:
                    progress = {"have": min(_int(stats.get(PROGRESS_STATS[kind])), int(needed)), "need": int(needed)}
                items.append({
                    "id": ach_id, "unlocked": have, "secret": bool(data.get("hidden")), "icon": _text(data.get("icon", "🏆"), 8),
                    "name": tr(_text(data.get("name", ach_id), 80)), "description": tr(_text(data.get("description", ""), 300)),
                    "date": _text(mine.get("date"), 32) if isinstance(mine, dict) else None, "progress": progress,
                    "reward": {"points": _int(reward.get("skill_points")), "title": tr(_text(reward.get("title"), 60)) if reward.get("title") else None,
                               "domain": _text((domains_cfg.get(domain) or {}).get("name", domain), 60) if domain else None},
                })
            if items:
                out_categories.append({"id": cat_id, "name": tr(_text(cat.get("name", cat_id), 60)), "icon": _text(cat.get("icon", "📁"), 8),
                                       "color": _text(cat.get("color", "#888888"), 9), "items": items})
        titles = [t for t in (ach.get("titles") or []) if isinstance(t, str)]
        owned = [d for d in (ach.get("domains") or []) if isinstance(d, str)]
        now = time.time()
        used = (getattr(self.app, "domain_cooldowns", {}) or {}).get(uid, {})
        domains = []
        for d_id in owned:
            cfg = domains_cfg.get(d_id) or {}
            cooldown = _number(cfg.get("cooldown"), 600)
            left = max(0.0, cooldown - (now - _number(used.get(d_id), 0.0))) if d_id in used else 0.0
            domains.append({"id": d_id, "name": _text(cfg.get("name", d_id), 60), "japanese": _text(cfg.get("japanese_name"), 40), "type": _text(cfg.get("type", "simple"), 30),
                            "description": tr(_text(cfg.get("description", ""), 300)), "cast": _number(cfg.get("cast_time"), 5.0), "cooldown": round(cooldown),
                            "left": round(left), "active": d_id == ach.get("active_domain")})
        return {"categories": out_categories, "unlocked": unlocked, "total": len(listed),
                "titles": [{"id": t, "name": tr(_text(t, 60))} for t in titles], "activeTitle": ach.get("active_title") if ach.get("active_title") in titles else None,
                "domains": domains}

    def set_title(self, uid: int, title: str | None) -> dict:
        ach = self._ach_of(uid)
        if title in (None, "", "none"):
            ach.pop("active_title", None)
        else:
            if title not in (ach.get("titles") or []):
                raise RpcError("Todavía no tienes ese título.")
            self.app.player_achievements.setdefault(str(uid), ach)["active_title"] = title
        self._save()
        return {"activeTitle": ach.get("active_title")}

    def set_domain(self, uid: int, domain_id: str) -> dict:
        ach = self._ach_of(uid)
        if domain_id not in (ach.get("domains") or []):
            raise RpcError("Todavía no tienes ese dominio.")
        self.app.player_achievements.setdefault(str(uid), ach)["active_domain"] = domain_id
        self._save()
        return {"activeDomain": domain_id}

    # ---- characters and powers ---------------------------------------------------------------------------------------
    @staticmethod
    def _power(power: dict | None) -> dict | None:
        if not isinstance(power, dict):
            return None
        return {"name": _text(power.get("name"), MAX_POWER_NAME), "description": _text(power.get("description"), MAX_POWER_TEXT),
                "type": _text(power.get("type"), 20), "cooldown": _int(power.get("cooldown")), "effect": _text(power.get("effect"), MAX_EFFECT),
                "image": power.get("image_url") if isinstance(power.get("image_url"), str) else None,
                "trigger": _text(power.get("trigger_phrase"), MAX_TRIGGER) or None, "show": power.get("show") if power.get("show") in POWER_SHOW else "all"}

    def damage_multiplier(self, uid: int) -> float:
        """What this player's hits are worth now (weapon, damage boost, revenge): the power builder shows its numbers with it."""
        app = self.app
        try:
            weapon = float(app.get_weapon_damage_multiplier(uid)) if hasattr(app, "get_weapon_damage_multiplier") else 1.0
            boost = app.get_active_buff(uid, "damage_boost") if hasattr(app, "get_active_buff") else None
        except Exception:  # noqa: BLE001 - the bot's helpers: a failure there shows the plain numbers
            weapon, boost = 1.0, None
        revenge = bool(((getattr(app, "player_hp", {}) or {}).get(uid) or {}).get("revenge_mode"))
        return power_rules.damage_multiplier(weapon, float(boost["value"]) if boost else 0.0, revenge)

    def characters(self, uid: int, avatars: dict[str, str] | None = None, seen: list[str] | None = None) -> dict:
        powers = getattr(self.app, "character_powers", {}) or {}
        mine = self._characters(uid)
        known = set(getattr(self.app, "character_registry", {}) or {})
        return {
            "characters": [{"name": name, "avatar": (avatars or {}).get(name),
                            "powers": {key: self._power((powers.get(name) or {}).get(key)) for key in ("power1", "power2")}} for name in mine],
            "types": list(getattr(self.app, "power_types", []) or []), "max": MAX_CHARACTERS,
            "multiplier": round(self.damage_multiplier(uid), 3), "cap": int(getattr(self.app, "ultimate_max_damage", 500) or 500),
            "suggestions": [n for n in (seen or []) if n not in known][:12],     # names seen in the channel that nobody has registered
        }

    def register_character(self, uid: int, name: Any) -> dict:
        name = _clean_line(name, MAX_CHARACTER_NAME)
        if not name:
            raise RpcError("Escribe el nombre exacto del personaje, tal como sale en Tupperbox.")
        app = self.app
        if name in app.character_registry:
            raise RpcError(f"«{name}» ya está registrado.")
        if len(self._characters(uid)) >= MAX_CHARACTERS:
            raise RpcError(f"Puedes registrar hasta {MAX_CHARACTERS} personajes.")
        app.character_registry[name] = uid
        app.user_characters.setdefault(uid, []).append(name)
        self._save()
        return {"name": name}

    def unregister_character(self, uid: int, name: Any) -> dict:
        name = str(name or "")
        app = self.app
        if app.character_registry.get(name) != uid:
            raise RpcError("Ese personaje no está registrado a tu nombre.")
        del app.character_registry[name]
        if name in (app.user_characters.get(uid) or []):
            app.user_characters[uid].remove(name)
        self._save()
        return {"name": name}

    def save_power(self, uid: int, is_gm: bool, data: dict) -> dict:
        app = self.app
        name = str(data.get("character") or "")
        owner = app.character_registry.get(name)
        if owner is None:
            raise RpcError("Ese personaje no está registrado.")
        if owner != uid and not is_gm:
            raise RpcError("Ese personaje no es tuyo.")
        slot = _int(data.get("slot"))
        if slot not in (1, 2):
            raise RpcError("El poder va en la ranura 1 (poder de lore) o 2 (poder de historia).")
        power_name = _clean_line(data.get("name"), MAX_POWER_NAME)
        if not power_name:
            raise RpcError("El poder necesita un nombre.")
        description = str(data.get("description") or "").replace("\x00", "").strip()[:MAX_POWER_TEXT]
        if not description:
            raise RpcError("Cuenta en una frase qué hace el poder.")
        kind = str(data.get("type") or "")
        if kind not in app.power_types:
            raise RpcError("El tipo de poder no es válido.")
        cooldown = _int(data.get("cooldown"), -1)
        if not 0 <= cooldown <= MAX_COOLDOWN:
            raise RpcError("La recarga va de 0 a 86 400 segundos.")
        effect = _clean_line(data.get("effect"), MAX_EFFECT)
        if not effect:
            raise RpcError("Falta el efecto del poder.")
        try:
            effect = power_rules.validate(effect)
        except power_rules.PowerError as exc:
            raise RpcError(str(exc)) from None
        trigger = _clean_line(data.get("trigger"), MAX_TRIGGER).lower() or None
        image = _url(data.get("image"))
        app.character_powers.setdefault(name, {})[f"power{slot}"] = {
            "name": power_name, "description": description, "type": kind, "cooldown": cooldown, "effect": effect,
            "image_url": image, "trigger_phrase": trigger,
            "show": data.get("show") if data.get("show") in POWER_SHOW else "all",
        }
        self._save()
        return {"character": name, "slot": slot}

    def remove_power(self, uid: int, is_gm: bool, character: Any, slot: Any) -> dict:
        app = self.app
        name = str(character or "")
        owner = app.character_registry.get(name)
        if owner is None or (owner != uid and not is_gm):
            raise RpcError("Ese personaje no es tuyo.")
        key = f"power{_int(slot)}"
        powers = app.character_powers.get(name) or {}
        if key not in powers:
            raise RpcError("Ese poder no existe.")
        del powers[key]
        if not powers:
            app.character_powers.pop(name, None)
        self._save()
        return {"character": name}

    # ---- skill tree ---------------------------------------------------------------------------------------------------
    def _all_skills(self):
        for tree_id, tree in (getattr(self.app, "skill_tree_config", {}) or {}).items():
            for branch_id, branch in (tree.get("branches") or {}).items():
                for skill in branch.get("skills") or []:
                    yield tree_id, branch_id, skill

    def skills(self, uid: int) -> dict:
        mine = self._skills_of(uid)
        ranks = {k: _int(v) for k, v in (mine.get("skills") or {}).items()}
        points = _int(mine.get("skill_points"))
        names = {s.get("id"): s.get("name") for _, _, s in self._all_skills()}
        trees, learned, total = [], 0, 0
        for tree_id, tree in (getattr(self.app, "skill_tree_config", {}) or {}).items():
            branches = []
            for branch_id, branch in (tree.get("branches") or {}).items():
                skills = []
                for skill in branch.get("skills") or []:
                    sid = _text(skill.get("id"), 60)
                    maximum, cost = max(1, _int(skill.get("max_rank"), 1)), max(0, _int(skill.get("cost"), 1))
                    rank = min(ranks.get(sid, 0), maximum)
                    needs = [{"id": p, "name": tr(_text(names.get(p, p), 60)), "met": ranks.get(p, 0) > 0} for p in (skill.get("prerequisites") or [])]
                    state = "maxed" if rank >= maximum else "locked" if any(not n["met"] for n in needs) else "poor" if points < cost else "available"
                    learned += 1 if rank else 0
                    total += 1
                    effect = _text(skill.get("effect"), 80)
                    skills.append({"id": sid, "name": tr(_text(skill.get("name", sid), 60)), "description": describe_skill_effect(effect) or tr(_text(skill.get("description"), 200)),
                                   "tier": max(1, _int(skill.get("tier"), 1)), "cost": cost, "max": maximum, "rank": rank, "needs": needs, "state": state})
                branches.append({"id": branch_id, "name": tr(_text(branch.get("name", branch_id), 60)), "icon": _text(branch.get("icon", "📌"), 8),
                                 "color": _text(branch.get("color", "#8888ff"), 9), "description": tr(_text(branch.get("description"), 200)), "skills": skills})
            trees.append({"id": tree_id, "name": tr(_text(tree.get("name", tree_id), 80)), "description": tr(_text(tree.get("description"), 200)), "branches": branches})
        return {"points": points, "trees": trees, "learned": learned, "total": total}

    def learn_skill(self, uid: int, skill_id: Any) -> dict:
        skill_id = str(skill_id or "")
        found = next((s for _, _, s in self._all_skills() if s.get("id") == skill_id), None)
        if found is None:
            raise RpcError("Esa habilidad no existe.")
        app = self.app
        mine = app.player_skills.setdefault(str(uid), {"skill_points": 0, "skills": {}})
        mine.setdefault("skills", {})
        ranks, points = mine["skills"], _int(mine.get("skill_points"))
        missing = [p for p in (found.get("prerequisites") or []) if _int(ranks.get(p)) <= 0]
        if missing:
            names = {s.get("id"): s.get("name") for _, _, s in self._all_skills()}
            raise RpcError("Te falta: " + ", ".join(tr(_text(names.get(p, p), 60)) for p in missing) + ".")
        rank, maximum, cost = _int(ranks.get(skill_id)), max(1, _int(found.get("max_rank"), 1)), max(0, _int(found.get("cost"), 1))
        if rank >= maximum:
            raise RpcError("Esa habilidad ya está al máximo.")
        if points < cost:
            raise RpcError(f"Te faltan puntos de habilidad: cuesta {cost} y tienes {points}.")
        mine["skill_points"] = points - cost
        ranks[skill_id] = rank + 1
        self._save()
        return {"id": skill_id, "rank": rank + 1, "points": mine["skill_points"]}

    # ---- inventory ---------------------------------------------------------------------------------------------------
    def _owned_objects(self, uid: int) -> list[str]:
        manager = self._manager()
        if manager is None:
            return []
        owned = list(manager.player_inventory.get(uid, []))
        for obj_id, owner in (getattr(manager, "unique_object_owners", {}) or {}).items():
            if owner == uid and obj_id not in owned:
                owned.append(obj_id)
        return [o for o in owned if o in manager.objects]

    def inventory(self, uid: int) -> dict:
        manager = self._manager()
        if manager is None:
            return {"objects": [], "slots": [0, 0]}
        out = []
        for obj_id in self._owned_objects(uid):
            obj = manager.objects[obj_id]
            display = obj.get("display") or {}
            tracking = obj.get("tracking") or {}
            kind = tracking.get("type", "per_difficulty") if isinstance(tracking, dict) else "per_difficulty"
            thresholds = obj.get("thresholds") or []
            rows = []
            if obj.get("type") == "adaptation" or thresholds:
                keys = ["total"] if kind == "total" else list(DIFFICULTIES)
                for key in keys:
                    steps_raw = thresholds if kind == "total" and isinstance(thresholds, list) else (thresholds.get(key, []) if isinstance(thresholds, dict) else [])
                    spins = _int(manager.get_tracking(uid, obj_id, key))
                    steps = [{"spins": _int(t.get("spins")), "effects": [describe_object_effect(e) for e in (t.get("effects") or [])], "done": spins >= _int(t.get("spins"))}
                             for t in steps_raw if isinstance(t, dict)]
                    if not steps and not spins:
                        continue
                    pending = [s["spins"] for s in steps if not s["done"]]
                    rows.append({"key": key, "spins": spins, "next": min(pending) if pending else None, "max": max((s["spins"] for s in steps), default=None), "steps": steps})
            out.append({
                "id": obj_id, "name": tr(_text(obj.get("name", obj_id), 80)), "emoji": _text(display.get("emoji", "📦"), 8), "color": _text(display.get("color"), 9) or None,
                "rarity": _text(obj.get("rarity", "common"), 12), "type": _text(obj.get("type", "unknown"), 20), "slots": max(1, _int(obj.get("slots_required"), 1)),
                "tradeable": bool(obj.get("tradeable", True)), "unique": bool(obj.get("unique", False)),
                "description": tr(_text(obj.get("description"), 500)), "lore": tr(_text(obj.get("lore"), 400)) or None,
                "image": obj.get("image_url") if isinstance(obj.get("image_url"), str) else None,
                "tracking": {"kind": kind, "rows": rows},
                "use": self._use_of(uid, obj_id),
            })
        owners = getattr(manager, "unique_object_owners", {}) or {}
        catalog = [{"id": oid, "name": tr(_text(o.get("name", oid), 80)), "emoji": _text((o.get("display") or {}).get("emoji", "📦"), 8),
                    "rarity": _text(o.get("rarity", "common"), 12), "type": _text(o.get("type", "unknown"), 20),
                    "description": tr(_text(o.get("description"), 300)), "image": o.get("image_url") if isinstance(o.get("image_url"), str) else None,
                    "unique": bool(o.get("unique", False)), "taken": oid in owners, "mine": owners.get(oid) == uid}
                   for oid, o in list((manager.objects or {}).items())[:200]]
        return {"objects": out, "slots": [manager.get_used_slots(uid), manager.get_player_max_slots(uid)], "catalog": catalog}

    def _use_of(self, uid: int, obj_id: str) -> dict | None:
        """The button an object has in the inventory (today the Mirror Shard's invocation), and why it cannot be pressed yet."""
        if obj_id != "mirror_shard" or not hasattr(self.app, "mirror_invoke_problem"):
            return None
        problem = self.app.mirror_invoke_problem(uid)
        return {"id": "mirror", "label": "Invocar: refleja un QTE contra el jefe", "problem": spanish(problem) if problem else None}

    async def use_object(self, uid: int, name: str, use: str) -> dict:
        if use != "mirror" or not hasattr(self.app, "mirror_invoke"):
            raise RpcError("Ese objeto no se puede usar así.")
        problem = self.app.mirror_invoke_problem(uid)
        if problem:
            raise RpcError(spanish(problem))
        dealt = await self.app.mirror_invoke(uid, name)
        return {"damage": dealt, **self.inventory(uid)}

    # ---- counter images ----------------------------------------------------------------------------------------------
    def _images(self, uid: int) -> list[str]:
        raw = (getattr(self.app, "user_counter_gifs", {}) or {}).get(uid, [])
        return [raw] if isinstance(raw, str) else [u for u in raw if isinstance(u, str)]

    def counter_images(self, uid: int) -> dict:
        return {"images": self._images(uid), "max": MAX_COUNTER_IMAGES}

    def add_counter_image(self, uid: int, url: Any) -> dict:
        link = _url(url)
        if link is None:
            raise RpcError("Falta el enlace de la imagen.")
        images = self._images(uid)
        if len(images) >= MAX_COUNTER_IMAGES:
            raise RpcError(f"Puedes tener hasta {MAX_COUNTER_IMAGES} imágenes. Quita alguna antes de añadir otra.")
        self.app.user_counter_gifs[uid] = [*images, link]
        self._save()
        return self.counter_images(uid)

    def remove_counter_image(self, uid: int, index: Any) -> dict:
        images = self._images(uid)
        i = _int(index, -1)
        if not 0 <= i < len(images):
            raise RpcError("Esa imagen ya no está.")
        images.pop(i)
        if images:
            self.app.user_counter_gifs[uid] = images
        else:
            self.app.user_counter_gifs.pop(uid, None)
        self._save()
        return self.counter_images(uid)

    def clear_counter_images(self, uid: int) -> dict:
        self.app.user_counter_gifs.pop(uid, None)
        self._save()
        return self.counter_images(uid)
