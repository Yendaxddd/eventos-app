"""The boss: what the /bossdashboard buttons, /registerboss and /bossdefeatgif do."""
from __future__ import annotations

import time

import discord

from ..hub import RpcError
from .common import finite, https_url, number, spawn, text

DOMAIN_TYPES = ("simple", "dps", "stun")
MAX_GIFS = 30
MAX_ABILITIES = 25
MAX_HP = 9_999_999
GIF_KINDS = ("evade", "counter", "defeat")
GIF_KIND_ES = {"evade": "de esquive", "counter": "de contraataque", "defeat": "de derrota"}


class BossOps:
    def _boss_config(self) -> dict:
        return self.app.tupperbox_boss_config

    def _need_boss(self) -> dict:
        boss = getattr(self.app, "active_boss", None)
        if not boss:
            raise RpcError("No hay un jefe en combate.")
        return boss

    def _channel(self):
        channel = self.app.bot.get_channel(self.app.qte_channel_id)
        if channel is None:
            raise RpcError("El evento todavía no tiene canal.")
        return channel

    # ---- reading -------------------------------------------------------------------------------------------------------
    def boss(self) -> dict:
        app, config = self.app, self._boss_config()
        inflict = config.get("status_inflict", {}) or {}
        abilities = []
        for name, data in list((config.get("abilities", {}) or {}).items())[:MAX_ABILITIES]:
            status = inflict.get(name)
            abilities.append({"name": text(name, 50), "damage": int(finite((data or {}).get("damage"))), "gif": (data or {}).get("gif") if isinstance((data or {}).get("gif"), str) else None,
                              "status": {"type": text(status.get("status"), 30), "chance": int(finite(status.get("chance"), 100)), "duration": int(finite(status.get("duration"), 60))}
                              if isinstance(status, dict) else None})
        domain = config.get("domain")
        return {
            "active": self.state()["boss"], "mode": bool(getattr(app, "tupperbox_boss_mode", False)),
            "config": {
                "character": text(config.get("character_name"), 100) or None, "hp": int(finite(config.get("boss_hp"), 1000)),
                "evade": round(finite(config.get("evade_chance"), 0.15) * 100), "counter": round(finite(config.get("counter_chance"), 0.20) * 100),
                "counterDamage": int(finite(config.get("counter_damage"), 15)), "abilities": abilities,
                "evadeGifs": [g for g in (config.get("evade_gifs") or []) if isinstance(g, str)][:MAX_GIFS],
                "counterGifs": [g for g in (config.get("counter_gifs") or []) if isinstance(g, str)][:MAX_GIFS],
                "domain": None if not isinstance(domain, dict) else {
                    "name": text(domain.get("name"), 100), "type": text(domain.get("type", "simple"), 20), "duration": int(finite(domain.get("duration"), 30)),
                    "effect": int(finite(domain.get("effect_value"), 10)), "gif": domain.get("gif") if isinstance(domain.get("gif"), str) else None},
            },
            "defeatGifs": [g for g in (getattr(app, "boss_defeat_gifs", []) or []) if isinstance(g, str)][:MAX_GIFS],
            "statusTypes": sorted((getattr(app, "status_effect_types", {}) or {}).keys()),
        }

    # ---- the fight ------------------------------------------------------------------------------------------------------
    def _start_fight(self) -> None:
        app = self.app
        app.fight_active, app.fight_start_time = True, time.time()
        for stats in app.player_stats.values():
            if isinstance(stats, dict):
                stats["damage_taken_this_fight"] = 0
                stats["critical_counters_this_fight"] = 0
        app._resume_ultimate_cooldowns()

    async def boss_register(self, actor: str, name, hp, image=None) -> dict:
        """/registerboss: a boss with a picture, and the fight begins."""
        app = self.app
        clean = text(name, 80).strip()
        if not clean:
            raise RpcError("El jefe necesita un nombre.")
        health = int(number(hp, "Vida del jefe", 1, MAX_HP, integer=True))
        picture = https_url(image)
        channel = self._channel()
        app.active_boss = {"name": clean, "hp_current": health, "hp_max": health, "gif_url": picture, "participants": set()}
        self._start_fight()
        embed = discord.Embed(title=f"⚔️ BOSS FIGHT STARTED: {clean}",
                              description=f"**HP**: {health}\n**Status**: ⚔️ **FIGHT IN PROGRESS!**\n\n🔥 Ultimate cooldowns are now active!", color=discord.Color.dark_red())
        if picture:
            embed.set_image(url=picture)
        embed.set_footer(text="Use QTE commands to engage the boss!")
        spawn(channel.send(embed=embed), "announce the boss")
        spawn(app.update_hp_bar_display(clean, is_boss=True), "draw the boss HP bar")
        self.log.add(actor, f"Registró al jefe «{clean}» con {health} HP")
        return self.boss()

    async def boss_spawn(self, actor: str) -> dict:
        """The «Spawn Boss» button: the Tupperbox character becomes the boss."""
        app, config = self.app, self._boss_config()
        name = text(config.get("character_name"), 100).strip()
        if not name:
            raise RpcError("Primero elige el personaje de Tupperbox que hace de jefe (en «Ajustes del jefe»).")
        health = int(finite(config.get("boss_hp"), 1000)) or 1000
        channel = self._channel()
        app.active_boss = {"name": name, "hp_current": health, "hp_max": health, "participants": set(), "tupperbox_controlled": True}
        app.tupperbox_boss_mode = True
        app.fight_active, app.fight_start_time = True, time.time()
        app._resume_ultimate_cooldowns()
        embed = discord.Embed(title="👹 BOSS APPEARS!", description=f"**{name}** has entered the battlefield!\n\n❤️ **HP:** {health}\n⚔️ *The fight begins!*",
                              color=discord.Color.dark_red())
        spawn(channel.send(embed=embed), "announce the boss")
        spawn(app.update_hp_bar_display(name, is_boss=True), "draw the boss HP bar")
        self.log.add(actor, f"Hizo aparecer al jefe «{name}» con {health} HP")
        return self.boss()

    def boss_mode(self, actor: str, on) -> dict:
        self.app.tupperbox_boss_mode = bool(on)
        self.log.add(actor, "Activó el modo jefe de Tupperbox" if on else "Desactivó el modo jefe de Tupperbox")
        return self.boss()

    async def boss_hp(self, actor: str, action: str, amount=None) -> dict:
        app = self.app
        boss = self._need_boss()
        name, current, maximum = boss["name"], int(finite(boss.get("hp_current"))), int(finite(boss.get("hp_max")))
        if action == "defeat":
            await app.damage_boss(name, current)
            self.log.add(actor, f"Derrotó al jefe «{name}»")
            return self.boss()
        value = int(number(amount, "Cantidad", 0 if action == "set" else 1, MAX_HP, integer=True))
        if action == "damage":
            await app.damage_boss(name, value)
            self.log.add(actor, f"Hizo {value} de daño al jefe «{name}»")
        elif action == "heal":
            boss["hp_current"] = min(maximum, current + value)
            await app.update_hp_bar_display(name, is_boss=True)
            self.log.add(actor, f"Curó {value} HP al jefe «{name}»")
        elif action == "set":
            if value > maximum:
                raise RpcError(f"La vida del jefe no puede pasar de su máximo ({maximum}).")
            if value == 0:
                await app.damage_boss(name, current)
            else:
                boss["hp_current"] = value
                await app.update_hp_bar_display(name, is_boss=True)
            self.log.add(actor, f"Puso la vida del jefe «{name}» en {value}")
        else:
            raise RpcError("Esa acción no existe.")
        return self.boss()

    def boss_remove(self, actor: str) -> dict:
        """Take the boss away without a victory (a mistake, a rest): the fight ends quietly."""
        app = self.app
        boss = self._need_boss()
        if app.fight_active:
            app._pause_ultimate_cooldowns()
            app.fight_active, app.fight_start_time = False, None
        app.active_boss = None
        app.tupperbox_boss_mode = False
        self.log.add(actor, f"Retiró al jefe «{boss['name']}» sin derrotarlo")
        return self.boss()

    # ---- the Tupperbox boss's settings ----------------------------------------------------------------------------------------
    def boss_config(self, actor: str, data: dict) -> dict:
        config = self._boss_config()
        character = text(data.get("character"), 100).strip()
        hp = int(number(data.get("hp"), "Vida del jefe", 1, MAX_HP, integer=True))                       # everything is checked before anything changes
        evade = number(data.get("evade"), "Probabilidad de esquivar", 0, 100, integer=True) / 100
        counter = number(data.get("counter"), "Probabilidad de contraatacar", 0, 100, integer=True) / 100
        counter_damage = int(number(data.get("counterDamage"), "Daño del contraataque", 0, 9999, integer=True))
        config.update({"character_name": character or None, "boss_hp": hp, "evade_chance": evade, "counter_chance": counter, "counter_damage": counter_damage})
        self.app.save_tupperbox_boss_config()
        self.log.add(actor, "Cambió los ajustes del jefe")
        return self.boss()

    def ability_save(self, actor: str, data: dict) -> dict:
        config = self._boss_config()
        name = text(data.get("name"), 50).strip()
        if not name:
            raise RpcError("La habilidad necesita un nombre.")
        abilities = config.setdefault("abilities", {})
        if name not in abilities and len(abilities) >= MAX_ABILITIES:
            raise RpcError(f"El jefe puede tener hasta {MAX_ABILITIES} habilidades.")
        ability = {"damage": int(number(data.get("damage"), "Daño", 0, 9999, integer=True)), "gif": https_url(data.get("gif"))}
        status = text(data.get("statusType"), 30).strip()
        inflicted = None
        if status:
            known = getattr(self.app, "status_effect_types", None)
            if known and status not in known:
                raise RpcError("Ese estado alterado no existe.")
            inflicted = {"status": status, "chance": int(number(data.get("statusChance", 100), "Probabilidad del estado", 0, 100, integer=True)),
                         "duration": int(number(data.get("statusDuration", 60), "Duración del estado", 1, 3600, integer=True))}
        abilities[name] = ability                                                                          # only now does anything change
        inflict = config.setdefault("status_inflict", {})
        if inflicted:
            inflict[name] = inflicted
        else:
            inflict.pop(name, None)
        self.app.save_tupperbox_boss_config()
        self.log.add(actor, f"Guardó la habilidad «{name}» del jefe")
        return self.boss()

    def ability_remove(self, actor: str, name) -> dict:
        config = self._boss_config()
        name = str(name or "")
        if name not in (config.get("abilities") or {}):
            raise RpcError("Esa habilidad ya no existe.")
        del config["abilities"][name]
        (config.get("status_inflict") or {}).pop(name, None)
        self.app.save_tupperbox_boss_config()
        self.log.add(actor, f"Quitó la habilidad «{name}» del jefe")
        return self.boss()

    async def ability_use(self, actor: str, name) -> dict:
        app = self.app
        name = str(name or "")
        if name not in (self._boss_config().get("abilities") or {}):
            raise RpcError("Esa habilidad no existe.")
        targets = list((getattr(app, "player_hp", {}) or {}).keys())
        if not targets:
            raise RpcError("No hay jugadores a los que atacar.")
        channel = self._channel()
        result = await app.boss_use_ability(name, targets)
        if not result.get("success"):
            raise RpcError("No se pudo usar la habilidad.")
        embed = discord.Embed(title=f"👹💥 Boss uses **{name}**!", description=f"Damage: **{result['damage']}**\nTargets hit: **{len(result['targets_hit'])}**",
                              color=discord.Color.dark_red())
        if result.get("gif"):
            embed.set_image(url=result["gif"])
        spawn(channel.send(embed=embed), "announce the boss ability")
        self.log.add(actor, f"El jefe usó «{name}» ({result['damage']} de daño a {len(result['targets_hit'])} jugadores)")
        return {"damage": result["damage"], "hit": len(result["targets_hit"])}

    # ---- GIFs ---------------------------------------------------------------------------------------------------------------
    def _gif_list(self, kind: str) -> list:
        if kind not in GIF_KINDS:
            raise RpcError("Ese tipo de GIF no existe.")
        if kind == "defeat":
            return self.app.boss_defeat_gifs
        return self._boss_config().setdefault(f"{kind}_gifs", [])

    def _gifs_saved(self, kind: str) -> None:
        if kind == "defeat":
            self.app.save_all_data(force=True)
        else:
            self.app.save_tupperbox_boss_config()

    def gif_add(self, actor: str, kind: str, url) -> dict:
        address = https_url(url, required=True)
        gifs = self._gif_list(kind)
        if address in gifs:
            raise RpcError("Esa imagen ya está en la lista.")
        if len(gifs) >= MAX_GIFS:
            raise RpcError(f"Puede haber hasta {MAX_GIFS} imágenes en la lista.")
        gifs.append(address)
        self._gifs_saved(kind)
        self.log.add(actor, f"Añadió un GIF {GIF_KIND_ES[kind]} del jefe")
        return self.boss()

    def gif_remove(self, actor: str, kind: str, index) -> dict:
        gifs = self._gif_list(kind)
        position = int(number(index, "Posición", 0, 10_000, integer=True))
        if position >= len(gifs):
            raise RpcError("Esa imagen ya no está.")
        gifs.pop(position)
        self._gifs_saved(kind)
        self.log.add(actor, f"Quitó un GIF {GIF_KIND_ES[kind]} del jefe")
        return self.boss()

    # ---- the boss's domain ----------------------------------------------------------------------------------------------------
    def domain_save(self, actor: str, data: dict) -> dict:
        name = text(data.get("name"), 100).strip()
        if not name:
            raise RpcError("El dominio necesita un nombre.")
        kind = text(data.get("type"), 20).lower()
        if kind not in DOMAIN_TYPES:
            raise RpcError("El tipo de dominio no es válido (simple, dps o stun).")
        self._boss_config()["domain"] = {
            "name": name, "type": kind, "duration": int(number(data.get("duration"), "Duración", 1, 3600, integer=True)),
            "effect_value": int(number(data.get("effect"), "Efecto", 0, 9999, integer=True)), "gif": https_url(data.get("gif"))}
        self.app.save_tupperbox_boss_config()
        self.log.add(actor, f"Guardó el dominio «{name}» del jefe")
        return self.boss()

    def domain_clear(self, actor: str) -> dict:
        self._boss_config()["domain"] = None
        self.app.save_tupperbox_boss_config()
        self.log.add(actor, "Quitó el dominio del jefe")
        return self.boss()

    async def domain_expand(self, actor: str) -> dict:
        domain = self._boss_config().get("domain")
        if not domain:
            raise RpcError("El jefe no tiene dominio.")
        channel = self._channel()
        spawn(self.app.trigger_boss_domain(channel, domain), "expand the boss's domain")
        self.log.add(actor, f"El jefe expandió su dominio «{domain.get('name')}»")
        return {"ok": True}
