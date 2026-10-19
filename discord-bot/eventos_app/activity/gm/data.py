"""The game's content files (achievements, skill trees, special objects, translations): listed, checked before they are saved,
backed up first and loaded again into the running bot, so the team can add and change them without touching files."""
from __future__ import annotations

import json
import logging
import re
import shutil
import time
from pathlib import Path

from ..hub import RpcError
from .common import finite, text

log = logging.getLogger("eventos_app.activity")

BACKUPS_KEPT = 20
MAX_TEXT = 400_000
ID = re.compile(r"^[a-z0-9_]{2,40}$")
TRIGGER = re.compile(r"^[a-z0-9_]+:\d+(\|[a-z0-9_]+:\d+)*$", re.I)
MANUAL = "manual"                      # what the bot assumes for an achievement without a trigger: only a game master gives it


def _json(raw: str, what: str):
    if len(raw) > MAX_TEXT:
        raise RpcError("El archivo es demasiado grande.")
    try:
        return json.loads(raw)
    except ValueError as exc:
        raise RpcError(f"{what}: el JSON no es válido ({exc}).") from None


OBJECT_TYPES = ("adaptation", "passive", "triggered", "consumable")
OBJECT_RARITIES = ("common", "uncommon", "rare", "epic", "legendary", "mythic")
TRIGGER_WINDOWS = ("parry", "counter", "evade", "any", "passive")


class DataOps:
    data_dir: Path | None = None

    # ---- where things are ----------------------------------------------------------------------------------------------------
    def _need_dir(self) -> Path:
        if self.data_dir is None:
            raise RpcError("No se conoce la carpeta de datos.")
        return self.data_dir

    def _paths(self) -> dict[str, Path]:
        base = self._need_dir()
        return {"achievements": base / "achievements" / "achievements_config.json", "trees": base / "skill_trees" / "templates", "i18n": base / "i18n_es.json"}

    def _manager(self):
        manager = getattr(self.app, "special_objects_manager", None)
        if manager is None:
            raise RpcError("Los objetos especiales no están disponibles.")
        return manager

    # ---- backups -------------------------------------------------------------------------------------------------------------
    def _backup(self, path: Path) -> None:
        if not path.exists():
            return
        folder = self._need_dir() / "backups"
        folder.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        taken = [int(m.group(1)) for f in folder.glob(f"{path.stem}.{stamp}.*.json") if (m := re.fullmatch(r".+\.(\d+)\.json", f.name))]
        target = folder / f"{path.stem}.{stamp}.{max(taken, default=0) + 1:04d}.json"      # the names sort in the order the copies were made, even within one second
        shutil.copy2(path, target)
        old = sorted(folder.glob(f"{path.stem}.*.json"))
        for stale in old[:-BACKUPS_KEPT]:
            stale.unlink(missing_ok=True)

    def _write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._backup(path)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(path)

    def backups(self, key: str) -> list[dict]:
        path = self._file_path(key)
        folder = self._need_dir() / "backups"
        if not folder.is_dir():
            return []
        found = sorted(folder.glob(f"{path.stem}.*.json"), reverse=True)[:BACKUPS_KEPT]
        return [{"name": f.name, "ts": int(f.stat().st_mtime * 1000), "size": f.stat().st_size} for f in found]

    # ---- the files that can be edited -------------------------------------------------------------------------------------------
    def files(self) -> list[dict]:
        paths = self._paths()
        out = [{"key": "achievements", "group": "Logros", "label": "Logros, categorías y dominios", "exists": paths["achievements"].exists()}]
        if paths["trees"].is_dir():
            for f in sorted(paths["trees"].glob("*.json")):
                if not f.name.startswith("_"):
                    out.append({"key": f"tree:{f.stem}", "group": "Árboles de habilidades", "label": f.stem, "exists": True})
        manager = self._manager()
        for f in sorted(manager.approved_path.glob("*.json")):
            out.append({"key": f"object:{f.stem}", "group": "Objetos especiales", "label": f.stem, "exists": True})
        for f in sorted(manager.pending_path.glob("*.json")):
            out.append({"key": f"pending:{f.stem}", "group": "Objetos pendientes", "label": f.stem, "exists": True})
        out.append({"key": "i18n", "group": "Traducciones", "label": "Textos en español (data/i18n_es.json)", "exists": paths["i18n"].exists()})
        return out

    def templates(self) -> list[dict]:
        manager = self._manager()
        found = []
        for f in sorted(manager.templates_path.glob("*.json")):
            found.append({"key": f"template:{f.stem}", "label": f"Objeto · {f.stem.replace('template_', '')}"})
        tree = self._paths()["trees"] / "skill_tree_template.json"
        if tree.exists():
            found.append({"key": "template:skill_tree_template", "label": "Árbol de habilidades"})
        return found

    def _file_path(self, key: str) -> Path:
        key = str(key or "")
        paths = self._paths()
        if key == "achievements":
            return paths["achievements"]
        if key == "i18n":
            return paths["i18n"]
        kind, _, name = key.partition(":")
        if not re.fullmatch(r"[A-Za-z0-9_\-]{1,80}", name or ""):
            raise RpcError("Ese archivo no existe.")
        if kind == "tree":
            return paths["trees"] / f"{name}.json"
        manager = self._manager()
        if kind == "object":
            return manager.approved_path / f"{name}.json"
        if kind == "pending":
            return manager.pending_path / f"{name}.json"
        if kind == "template":
            return (paths["trees"] if name == "skill_tree_template" else manager.templates_path) / f"{name}.json"
        raise RpcError("Ese archivo no existe.")

    def file_get(self, key: str) -> dict:
        path = self._file_path(key)
        if not path.exists():
            raise RpcError("Ese archivo todavía no existe.")
        try:
            return {"key": key, "text": path.read_text(encoding="utf-8")}
        except OSError:
            raise RpcError("No se pudo leer el archivo.") from None

    def file_save(self, actor: str, key: str, content: str) -> dict:
        """Check the file for its kind, keep a copy of the old one, write the new one and load it into the running bot."""
        content = str(content or "")
        kind = str(key).partition(":")[0] if ":" in str(key) else str(key)
        if kind == "template":
            raise RpcError("Las plantillas no se pueden cambiar: cópiala a un archivo nuevo.")
        path = self._file_path(key)
        warnings: list[str] = []
        if key == "achievements":
            warnings = self._check_achievements(_json(content, "Logros"))
        elif kind == "tree":
            warnings = self._check_tree(_json(content, "Árbol"), path.stem)
        elif kind in ("object", "pending"):
            self._check_object(content, path)
        elif key == "i18n":
            self._check_i18n(_json(content, "Traducciones"))
        else:
            raise RpcError("Ese archivo no se puede cambiar.")
        pretty = json.dumps(json.loads(content), ensure_ascii=False, indent=2) + "\n"
        self._write(path, pretty)
        self._reload(key, kind)
        self.log.add(actor, f"Guardó el archivo «{path.name}»")
        return {"ok": True, "warnings": warnings, "text": pretty}

    def file_restore(self, actor: str, key: str, name: str) -> dict:
        path = self._file_path(key)
        folder = self._need_dir() / "backups"
        source = folder / str(name or "")
        if source.parent != folder or not source.name.startswith(path.stem + ".") or not source.is_file():
            raise RpcError("Esa copia ya no existe.")
        out = self.file_save(actor, key, source.read_text(encoding="utf-8"))
        self.log.add(actor, f"Recuperó una copia de «{path.name}»")
        return out

    def file_create(self, actor: str, kind: str, name: str, content: str) -> dict:
        """A new tree or object: it must not overwrite anything."""
        name = str(name or "").strip().lower()
        if not ID.match(name):
            raise RpcError("El nombre debe tener entre 2 y 40 letras minúsculas, números o guiones bajos.")
        if kind not in ("tree", "object"):
            raise RpcError("Eso no se puede crear.")
        key = f"{kind}:{name}"
        if self._file_path(key).exists():
            raise RpcError("Ya existe uno con ese nombre.")
        return self.file_save(actor, key, content)

    def file_delete(self, actor: str, key: str) -> dict:
        kind = str(key).partition(":")[0]
        if kind not in ("tree", "object", "pending"):
            raise RpcError("Ese archivo no se puede borrar.")
        path = self._file_path(key)
        if not path.exists():
            raise RpcError("Ese archivo ya no existe.")
        self._backup(path)
        path.unlink()
        self._reload(key, kind)
        self.log.add(actor, f"Borró el archivo «{path.name}» (queda una copia)")
        return {"ok": True}

    def _reload(self, key: str, kind: str) -> None:
        app = self.app
        if key == "achievements":
            app.achievements_config = app.load_achievements_config()
        elif kind == "tree":
            app.skill_tree_config = app.load_skill_tree_config()
        elif kind in ("object", "pending"):
            self._manager().load_all()

    # ---- checks ----------------------------------------------------------------------------------------------------------------
    def _check_achievements(self, data) -> list[str]:
        if not isinstance(data, dict) or not isinstance(data.get("achievements"), dict):
            raise RpcError("Falta la sección «achievements».")
        categories, domains = data.get("categories") or {}, data.get("domains") or {}
        if not isinstance(categories, dict) or not isinstance(domains, dict):
            raise RpcError("«categories» y «domains» deben ser objetos.")
        warnings, problems = [], []
        for aid, a in data["achievements"].items():
            if not isinstance(a, dict) or not str(a.get("name", "")).strip():
                problems.append(f"«{aid}» necesita un nombre.")
                continue
            if a.get("category") not in categories:
                warnings.append(f"«{aid}»: la categoría «{a.get('category')}» no existe.")
            reward = a.get("reward") or {}
            if reward.get("domain") and reward["domain"] not in domains:
                problems.append(f"«{aid}» da el dominio «{reward['domain']}», que no existe.")
            trigger = str(a.get("trigger", ""))
            if trigger and trigger != MANUAL and not TRIGGER.match(trigger):
                warnings.append(f"«{aid}»: el disparador «{trigger}» no tiene el formato tipo:número.")
        if problems:
            raise RpcError(" ".join(problems[:5]))
        return warnings[:20]

    def _check_tree(self, data, stem: str) -> list[str]:
        if not isinstance(data, dict) or not isinstance(data.get("branches"), dict) or not data["branches"]:
            raise RpcError("Falta la sección «branches» con al menos una rama.")
        if not str(data.get("name", "")).strip():
            raise RpcError("El árbol necesita un nombre.")
        ids, problems, warnings = set(), [], []
        for bid, branch in data["branches"].items():
            if not isinstance(branch, dict) or not isinstance(branch.get("skills"), list):
                problems.append(f"La rama «{bid}» necesita una lista «skills».")
                continue
            for skill in branch["skills"]:
                sid = skill.get("id") if isinstance(skill, dict) else None
                if not sid or not isinstance(sid, str):
                    problems.append(f"Una habilidad de «{bid}» no tiene «id».")
                elif sid in ids:
                    problems.append(f"La habilidad «{sid}» está repetida.")
                else:
                    ids.add(sid)
        if problems:
            raise RpcError(" ".join(problems[:5]))
        for branch in data["branches"].values():
            for skill in branch["skills"]:
                if not str(skill.get("name", "")).strip():
                    problems.append(f"«{skill['id']}» necesita un nombre.")
                for field, low in (("cost", 0), ("max_rank", 1), ("tier", 1)):
                    value = skill.get(field, low if field != "cost" else 1)
                    if not isinstance(value, int) or isinstance(value, bool) or value < low:
                        problems.append(f"«{skill['id']}»: «{field}» debe ser un número entero de {low} en adelante.")
                for need in skill.get("prerequisites") or []:
                    if need not in ids:
                        problems.append(f"«{skill['id']}» necesita «{need}», que no existe.")
                    elif need == skill["id"]:
                        problems.append(f"«{skill['id']}» no puede necesitarse a sí misma.")
                if not skill.get("effect"):
                    warnings.append(f"«{skill['id']}» no tiene «effect»: no hará nada.")
        if problems:
            raise RpcError(" ".join(problems[:5]))
        return warnings[:20]

    def _object_problems(self, data) -> list[str]:
        """What is wrong with an object definition (the bot's own validator stops at objects with the newer flat list of thresholds)."""
        if not isinstance(data, dict):
            return ["El objeto debe ser un objeto JSON."]
        problems = [f"Falta el campo «{f}»." for f in ("id", "name", "type") if f not in data]
        if problems:
            return problems
        manager = self._manager()
        if not isinstance(data["id"], str) or not re.fullmatch(r"[a-z0-9_]+", data["id"]):
            problems.append("El «id» debe tener solo letras minúsculas, números y guiones bajos.")
        if data["type"] not in OBJECT_TYPES:
            problems.append(f"El tipo debe ser uno de: {', '.join(OBJECT_TYPES)}.")
        if data.get("rarity") and data["rarity"] not in OBJECT_RARITIES:
            problems.append(f"La rareza debe ser una de: {', '.join(OBJECT_RARITIES)}.")
        if "slots_required" in data and (not isinstance(data["slots_required"], int) or isinstance(data["slots_required"], bool) or data["slots_required"] < 1):
            problems.append("«slots_required» debe ser un entero positivo.")
        trigger = data.get("trigger") or {}
        if isinstance(trigger, dict) and trigger.get("window") and trigger["window"] not in TRIGGER_WINDOWS:
            problems.append(f"La ventana del disparador debe ser una de: {', '.join(TRIGGER_WINDOWS)}.")

        def steps(where: str, group) -> None:
            if not isinstance(group, list):
                problems.append(f"{where} debe ser una lista.")
                return
            for i, step in enumerate(group):
                if not isinstance(step, dict) or not isinstance(step.get("spins"), int) or isinstance(step.get("spins"), bool) or step["spins"] < 0:
                    problems.append(f"{where}[{i}] necesita «spins» (un entero).")
                    continue
                if not isinstance(step.get("effects"), list):
                    problems.append(f"{where}[{i}] necesita una lista «effects».")
                    continue
                for effect in step["effects"]:
                    if not isinstance(effect, str) or not manager._validate_effect(effect):
                        problems.append(f"Efecto no válido: «{effect}».")
        thresholds = data.get("thresholds") or []
        if isinstance(thresholds, dict):
            for difficulty, group in thresholds.items():
                steps(f"thresholds.{difficulty}", group)
        else:
            steps("thresholds", thresholds)
        for i, cond in enumerate(data.get("conditionals") or []):
            if not isinstance(cond, dict) or "if" not in cond or not isinstance(cond.get("then"), list):
                problems.append(f"conditionals[{i}] necesita «if» y una lista «then».")
            else:
                problems.extend(f"Efecto no válido en una condición: «{e}»." for e in cond["then"] if not isinstance(e, str) or not manager._validate_effect(e))
        return problems

    def _check_object(self, content: str, path: Path) -> None:
        data = _json(content, "Objeto")
        problems = self._object_problems(data)
        if problems:
            raise RpcError("El objeto no es válido: " + " ".join(problems[:5]))
        if data.get("id") != path.stem:
            raise RpcError(f"El «id» del objeto («{data.get('id')}») debe ser igual al nombre del archivo («{path.stem}»).")

    @staticmethod
    def _check_i18n(data) -> None:
        if not isinstance(data, dict):
            raise RpcError("Debe ser un objeto con «exact» y/o «patterns».")
        exact = data.get("exact", {})
        if not isinstance(exact, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in exact.items()):
            raise RpcError("«exact» debe ser un objeto de textos: {\"Original\": \"Traducción\"}.")
        patterns = data.get("patterns", [])
        if not isinstance(patterns, list):
            raise RpcError("«patterns» debe ser una lista de pares [expresión, reemplazo].")
        for pair in patterns:
            if not (isinstance(pair, list) and len(pair) == 2 and all(isinstance(x, str) for x in pair)):
                raise RpcError("Cada elemento de «patterns» debe ser [expresión, reemplazo].")
            try:
                re.compile(pair[0])
            except re.error as exc:
                raise RpcError(f"La expresión «{pair[0]}» no es válida: {exc}.") from None

    # ---- achievements, as a list ------------------------------------------------------------------------------------------------
    def achievements(self) -> dict:
        config = getattr(self.app, "achievements_config", None) or {}
        categories = [{"id": cid, "name": text(c.get("name", cid), 60), "icon": text(c.get("icon", "📁"), 8), "color": text(c.get("color", "#888888"), 9)}
                      for cid, c in (config.get("categories") or {}).items()]
        items = []
        for aid, a in (config.get("achievements") or {}).items():
            reward = a.get("reward") or {}
            items.append({"id": aid, "name": text(a.get("name", aid), 80), "description": text(a.get("description"), 300), "category": text(a.get("category"), 40),
                          "icon": text(a.get("icon", "🏆"), 8), "trigger": text(a.get("trigger"), 120), "hidden": bool(a.get("hidden")), "announce": bool(a.get("announce", True)),
                          "message": text(a.get("announcement_message"), 300),
                          "reward": {"points": int(finite(reward.get("skill_points"))), "title": text(reward.get("title"), 60) or None, "domain": text(reward.get("domain"), 40) or None}})
        domains = [{"id": did, "name": text(d.get("name", did), 80)} for did, d in (config.get("domains") or {}).items()]
        return {"categories": categories, "achievements": items, "domains": domains}

    def achievement_save(self, actor: str, data: dict) -> dict:
        """One achievement, from a form: it keeps whatever else the file says about it."""
        path = self._paths()["achievements"]
        config = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"_version": "1.0", "categories": {}, "achievements": {}, "domains": {}}
        aid = text(data.get("id"), 40).strip().lower()
        if not ID.match(aid):
            raise RpcError("El identificador debe tener entre 2 y 40 letras minúsculas, números o guiones bajos.")
        name = text(data.get("name"), 80).strip()
        if not name:
            raise RpcError("El logro necesita un nombre.")
        category = text(data.get("category"), 40)
        if category not in (config.get("categories") or {}):
            raise RpcError("Elige una categoría que exista.")
        trigger = text(data.get("trigger"), 120).strip()
        if trigger and trigger != MANUAL and not TRIGGER.match(trigger):
            raise RpcError("El disparador debe ser como «evade_count:100» (tipo:número; puedes unir varios con «|»), o «manual» si solo lo da el GM.")
        reward = data.get("reward") or {}
        points = int(finite(reward.get("points")))
        if not 0 <= points <= 999:
            raise RpcError("Los puntos de habilidad van de 0 a 999.")
        domain = text(reward.get("domain"), 40).strip() or None
        if domain and domain not in (config.get("domains") or {}):
            raise RpcError("Ese dominio no existe.")
        entry = dict((config["achievements"].get(aid) or {}))
        entry.update({"name": name, "description": text(data.get("description"), 300), "category": category, "icon": text(data.get("icon") or "🏆", 8),
                      "trigger": trigger or MANUAL, "hidden": bool(data.get("hidden")), "announce": bool(data.get("announce", True))})
        message = text(data.get("message"), 300).strip()
        if message:
            entry["announcement_message"] = message
        else:
            entry.pop("announcement_message", None)
        new_reward = {}
        if points:
            new_reward["skill_points"] = points
        title = text(reward.get("title"), 60).strip()
        if title:
            new_reward["title"] = title
        if domain:
            new_reward["domain"] = domain
        entry["reward"] = new_reward
        creating = aid not in config["achievements"]
        config["achievements"][aid] = entry
        self._write(path, json.dumps(config, ensure_ascii=False, indent=2) + "\n")
        self.app.achievements_config = self.app.load_achievements_config()
        self.log.add(actor, f"{'Creó' if creating else 'Cambió'} el logro «{name}»")
        return self.achievements()

    def achievement_delete(self, actor: str, achievement_id) -> dict:
        path = self._paths()["achievements"]
        config = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        aid = str(achievement_id or "")
        if aid not in (config.get("achievements") or {}):
            raise RpcError("Ese logro ya no existe.")
        name = config["achievements"][aid].get("name", aid)
        del config["achievements"][aid]
        self._write(path, json.dumps(config, ensure_ascii=False, indent=2) + "\n")
        self.app.achievements_config = self.app.load_achievements_config()
        self.log.add(actor, f"Borró el logro «{name}» (quien ya lo tenía lo conserva; queda una copia del archivo)")
        return self.achievements()

    # ---- objects waiting for approval --------------------------------------------------------------------------------------------
    def objects(self) -> dict:
        manager = self._manager()
        approved = [{"id": oid, "name": text(o.get("name", oid), 80), "rarity": text(o.get("rarity", "common"), 12), "type": text(o.get("type"), 20)}
                    for oid, o in sorted(manager.objects.items())]
        pending = []
        for f in sorted(manager.pending_path.glob("*.json")):
            name, errors = f.stem, []
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                name = data.get("name", f.stem) if isinstance(data, dict) else f.stem
                errors = self._object_problems(data)
            except (OSError, ValueError):
                errors = ["El archivo no es un JSON válido."]
            pending.append({"file": f.name, "name": text(name, 80), "ok": not errors, "errors": [text(e, 200) for e in errors[:5]]})
        return {"approved": approved, "pending": pending}

    def object_approve(self, actor: str, filename: str) -> dict:
        """Pending -> approved: checked first, an older object with the same id is archived, and the new one is loaded."""
        manager = self._manager()
        filename = str(filename or "")
        source = manager.pending_path / filename
        if not re.fullmatch(r"[A-Za-z0-9_\-]{1,80}\.json", filename) or not source.is_file():
            raise RpcError("No se pudo aprobar: ese archivo ya no está.")
        try:
            data = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise RpcError("No se pudo aprobar: el archivo no es un JSON válido.") from None
        problems = self._object_problems(data)
        if problems:
            raise RpcError("No se pudo aprobar: " + " ".join(problems[:4]))
        stamp = time.strftime("%Y%m%d_%H%M%S")
        for existing in manager.approved_path.glob("*.json"):
            try:
                same = json.loads(existing.read_text(encoding="utf-8")).get("id") == data["id"]
            except (OSError, ValueError, AttributeError):
                same = False
            if same:
                shutil.move(str(existing), str(manager.archive_path / f"{existing.stem}_{stamp}.json"))
        destination = manager.approved_path / filename
        shutil.move(str(source), str(destination))
        ok, error = manager._load_object(destination)
        if not ok:
            raise RpcError(f"El objeto se movió pero no se pudo cargar: {error}")
        self.log.add(actor, f"Aprobó el objeto «{filename}»")
        return self.objects()

    def object_reject(self, actor: str, filename: str, reason: str = "") -> dict:
        filename = str(filename or "")
        if not re.fullmatch(r"[A-Za-z0-9_\-]{1,80}\.json", filename):                # the bot's own method would follow «../» out of the pending folder
            raise RpcError("No se pudo rechazar: ese archivo ya no está.")
        ok, message = self._manager().reject_object(filename, text(reason, 200))
        if not ok:
            raise RpcError(f"No se pudo rechazar: {message}")
        self.log.add(actor, f"Rechazó el objeto «{filename}»")
        return self.objects()

    def object_reload(self, actor: str) -> dict:
        count, errors = self._manager().load_all()
        self.log.add(actor, f"Recargó los objetos ({count} cargados)")
        return {**self.objects(), "loaded": count, "errors": [text(e, 200) for e in errors[:10]]}
