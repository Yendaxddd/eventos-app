"""The live event: launching QTEs (what the F9-F12 hotkeys and /targetqte do), the batch queue, checkpoints, the fight and the mode of the QTEs."""
from __future__ import annotations

import random
import time

from ..hub import RpcError
from .common import DIFFICULTIES, DIFFICULTY_ES, finite, number, spawn, text

MODES = ("single", "group", "combo", "direction", "fake")
MODE_ES = {"single": "individual", "group": "grupal", "combo": "combo", "direction": "de dirección", "fake": "falso"}
QTE_MODES = ("standard", "combo", "direction", "random")
QTE_MODE_ES = {"standard": "normal", "combo": "combo", "direction": "dirección", "random": "al azar"}
MAX_BATCH = 30


class EventOps:
    # ---- what is happening ---------------------------------------------------------------------------------------
    def _member(self, user_id: int):
        guild = self.app.resolve_event_guild()
        return guild.get_member(user_id) if guild is not None else None

    def _name(self, member) -> str:
        return text(getattr(member, "display_name", None) or getattr(member, "name", None) or "?", 60)

    def stunned_left(self) -> float:
        app = self.app
        end = getattr(app, "stun_end_time", None)
        if getattr(app, "enemy_stunned", False) and end:
            return max(0.0, end - time.time())
        return 0.0

    def state(self) -> dict:
        app = self.app
        boss = getattr(app, "active_boss", None)
        weights = {k: int(v.get("weight", 0)) for k, v in (getattr(app, "qte_variations", {}) or {}).items()}
        qtes = []
        for key, data in list((getattr(app, "active_qtes", {}) or {}).items())[:30]:
            target = data.get("target")
            qtes.append({"id": str(key), "mode": text(data.get("mode"), 20), "difficulty": text(data.get("difficulty"), 20),
                         "target": self._name(target) if target is not None else None})
        stats = getattr(app, "session_stats", {}) or {}
        return {
            "fight": bool(getattr(app, "fight_active", False)),
            "boss": None if not boss else {"name": text(boss.get("name"), 80), "hp": finite(boss.get("hp_current")), "max": finite(boss.get("hp_max")),
                                           "image": boss.get("gif_url") if isinstance(boss.get("gif_url"), str) else None,
                                           "tupper": bool(boss.get("tupperbox_controlled"))},
            "bossMode": bool(getattr(app, "tupperbox_boss_mode", False)),
            "qtes": qtes,
            "batch": {"active": bool(getattr(app, "batch_mode_active", False)), "pending": [text(p.get("difficulty"), 20) for p in (getattr(app, "pending_qte_batch", []) or [])]},
            "stunLeft": round(self.stunned_left(), 1),
            "qteMode": getattr(app, "current_qte_mode", "standard"), "weights": weights,
            "players": {"eligible": len(getattr(app, "qte_players", []) or []), "afk": len(getattr(app, "afk_users", set()) or set()),
                        "withHp": len(getattr(app, "player_hp", {}) or {})},
            "session": {"qtes": int(stats.get("qtes_triggered", 0) or 0), "blackFlashes": int(stats.get("black_flashes_today", 0) or 0)},
            "checkpoints": len(getattr(app, "regen_checkpoints", []) or []), "regen": int(getattr(app, "regen_amount", 0) or 0),
        }

    # ---- launching QTEs ---------------------------------------------------------------------------------------------
    async def _random_member(self):
        app = self.app
        should = getattr(app, "should_update_cache", None)
        if callable(should) and should():
            await app.update_qte_player_cache()
        players = list(getattr(app, "qte_players", []) or [])
        if not players:
            raise RpcError("No hay jugadores disponibles para el QTE.")
        return random.choice(players)

    async def launch(self, actor: str, mode: str, difficulty: str, target_id=None) -> dict:
        app = self.app
        if difficulty not in DIFFICULTIES:
            raise RpcError("La dificultad no es válida.")
        if mode not in MODES:
            raise RpcError("Ese tipo de QTE no existe.")
        if self.stunned_left() > 0:
            raise RpcError(f"El enemigo está aturdido ({self.stunned_left():.0f} s). Espera a que termine.")
        if app.bot.get_channel(app.qte_channel_id) is None:
            raise RpcError("El evento todavía no tiene canal.")
        member = None
        if target_id not in (None, "", 0):
            try:
                member = self._member(int(target_id))
            except (TypeError, ValueError):
                member = None
            if member is None:
                raise RpcError("Ese jugador no está en el servidor.")
        who = "a todo el grupo"
        if mode == "group":
            spawn(app.trigger_group_qte(difficulty), "launch a group QTE")
        elif mode == "single":
            spawn(app.trigger_single_qte(difficulty, target_member=member, is_targeted=member is not None), "launch a QTE")
            who = f"a {self._name(member)}" if member is not None else "a alguien al azar"
        else:
            chosen = member is not None
            member = member or await self._random_member()
            spawn(getattr(app, f"trigger_{mode}_qte")(difficulty, member, chosen), f"launch a {mode} QTE")
            who = f"a {self._name(member)}"
        self.log.add(actor, f"Lanzó un QTE {MODE_ES[mode]} ({DIFFICULTY_ES[difficulty]}) {who}")
        return {"ok": True}

    # ---- the batch queue (Alt+F9 and F9-F12 in the app) ------------------------------------------------------------------
    def batch(self, actor: str, action: str, difficulty: str | None = None) -> dict:
        app = self.app
        if action == "start":
            app.batch_mode_active, app.pending_qte_batch = True, []
            self.log.add(actor, "Empezó una tanda de QTE")
        elif action == "add":
            if not app.batch_mode_active:
                raise RpcError("Primero empieza una tanda.")
            if difficulty not in DIFFICULTIES:
                raise RpcError("La dificultad no es válida.")
            if len(app.pending_qte_batch) >= MAX_BATCH:
                raise RpcError(f"Una tanda admite hasta {MAX_BATCH} QTE.")
            app.pending_qte_batch.append({"difficulty": difficulty})
        elif action == "undo":
            if app.pending_qte_batch:
                app.pending_qte_batch.pop()
        elif action == "cancel":
            app.batch_mode_active, app.pending_qte_batch = False, []
            self.log.add(actor, "Canceló la tanda de QTE")
        elif action == "send":
            if not app.batch_mode_active or not app.pending_qte_batch:
                raise RpcError("No hay QTE en la tanda.")
            count = len(app.pending_qte_batch)
            spawn(app.process_batch_qtes(), "send the batch of QTEs")
            self.log.add(actor, f"Envió una tanda de {count} QTE")
        else:
            raise RpcError("Esa acción no existe.")
        return self.state()["batch"]

    # ---- checkpoint, fight, QTE mode -------------------------------------------------------------------------------------
    async def checkpoint(self, actor: str) -> dict:
        app = self.app
        name = f"Checkpoint {len(app.regen_checkpoints) + 1}"
        app.regen_checkpoints.append(name)
        spawn(app.trigger_checkpoint_heal(name), "heal at a checkpoint")
        self.log.add(actor, f"Lanzó el {name} (+{app.regen_amount} HP a todos)")
        return {"name": name}

    def fight(self, actor: str, action: str) -> dict:
        app = self.app
        if action == "start":
            if app.fight_active:
                raise RpcError("Ya hay un combate en curso.")
            app.fight_active, app.fight_start_time = True, time.time()
            for stats in app.player_stats.values():
                if isinstance(stats, dict):
                    stats["damage_taken_this_fight"] = 0
                    stats["critical_counters_this_fight"] = 0
            app._resume_ultimate_cooldowns()
            self.log.add(actor, "Empezó el combate (los poderes vuelven a recargarse)")
        elif action == "end":
            if not app.fight_active:
                raise RpcError("No hay un combate en curso.")
            app._pause_ultimate_cooldowns()
            app.fight_active, app.fight_start_time = False, None
            self.log.add(actor, "Terminó el combate (las recargas se pausan)")
        else:
            raise RpcError("Esa acción no existe.")
        return self.state()

    def set_qte_mode(self, actor: str, mode: str, weights=None) -> dict:
        app = self.app
        if mode not in QTE_MODES:
            raise RpcError("Ese modo de QTE no existe.")
        if weights is not None:
            if not isinstance(weights, dict):
                raise RpcError("Las probabilidades no son válidas.")
            clean = {}
            for key in app.qte_variations:
                if key in weights:
                    clean[key] = int(number(weights[key], f"Probabilidad de {key}", 0, 100, integer=True))
            merged = {key: clean.get(key, int(value.get("weight", 0))) for key, value in app.qte_variations.items()}
            if not any(merged.values()):
                raise RpcError("Alguna probabilidad debe ser mayor que 0.")
            for key, value in merged.items():
                app.qte_variations[key]["weight"] = value
        app.current_qte_mode = mode
        self.persist_all()
        self.log.add(actor, f"Modo de QTE: {QTE_MODE_ES[mode]}")
        return self.state()

    def sync_commands(self, actor: str) -> dict:
        spawn(self.app.force_sync_commands(), "sync the slash commands")
        self.log.add(actor, "Sincronizó los comandos de barra")
        return {"ok": True}
