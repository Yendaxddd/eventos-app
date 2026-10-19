"""The requests of the game-master panel, as the bridge answers them (`gm.state`, `gm.launch`, `gm.boss.hp`...).

Mixed into `ActivityBridge`. Every handler first asks `_gm`: the bot decides by role, at that very moment, who may do this
(a game master who loses the role loses the panel at once), and the change is signed in the log with their name."""
from __future__ import annotations

import asyncio
import logging

from .gm import GmPanel
from .hub import Conn, RpcError

log = logging.getLogger("eventos_app.activity")


class GmRpc:
    gm: GmPanel

    async def _gm(self, conn: Conn) -> str:
        if not await self.is_gm(conn):
            raise RpcError("Esto es solo para el equipo de GM.")
        return conn.name

    @staticmethod
    def _uid(args: dict) -> int:
        try:
            uid = int(str(args.get("id")))
        except (TypeError, ValueError):
            raise RpcError("Falta elegir a la persona.") from None
        if uid <= 0:
            raise RpcError("Esa persona no es válida.")
        return uid

    async def _who(self, args: dict) -> tuple[int, str]:
        uid = self._uid(args)
        return uid, (await self.who_is(uid, fetch=False))[0]

    async def _player_view(self, uid: int) -> dict:
        who = await self.who_is(uid, fetch=False)
        return self.gm.player(uid, who, uid in {c.user_id for c in self.hub.conns.values()})

    # ---- the event ---------------------------------------------------------------------------------------------------------
    async def rpc_gm_state(self, conn: Conn, args: dict):
        await self._gm(conn)
        return self.gm.state()

    async def rpc_gm_launch(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        await self.gm.launch(actor, str(args.get("mode")), str(args.get("difficulty")), args.get("target"))
        return self.gm.state()

    async def rpc_gm_batch(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        return self.gm.batch(actor, str(args.get("action")), args.get("difficulty"))

    async def rpc_gm_checkpoint(self, conn: Conn, args: dict):
        return await self.gm.checkpoint(await self._gm(conn))

    async def rpc_gm_fight(self, conn: Conn, args: dict):
        return self.gm.fight(await self._gm(conn), str(args.get("action")))

    async def rpc_gm_qte_mode(self, conn: Conn, args: dict):
        return self.gm.set_qte_mode(await self._gm(conn), str(args.get("mode")), args.get("weights"))

    async def rpc_gm_sync(self, conn: Conn, args: dict):
        return self.gm.sync_commands(await self._gm(conn))

    async def rpc_gm_history(self, conn: Conn, args: dict):
        await self._gm(conn)
        return {"entries": self.gm.log.recent(120)}

    # ---- the boss ----------------------------------------------------------------------------------------------------------
    async def rpc_gm_boss(self, conn: Conn, args: dict):
        await self._gm(conn)
        return self.gm.boss()

    async def rpc_gm_boss_register(self, conn: Conn, args: dict):
        return await self.gm.boss_register(await self._gm(conn), args.get("name"), args.get("hp"), args.get("image"))

    async def rpc_gm_boss_spawn(self, conn: Conn, args: dict):
        return await self.gm.boss_spawn(await self._gm(conn))

    async def rpc_gm_boss_mode(self, conn: Conn, args: dict):
        return self.gm.boss_mode(await self._gm(conn), bool(args.get("on")))

    async def rpc_gm_boss_hp(self, conn: Conn, args: dict):
        return await self.gm.boss_hp(await self._gm(conn), str(args.get("action")), args.get("amount"))

    async def rpc_gm_boss_remove(self, conn: Conn, args: dict):
        return self.gm.boss_remove(await self._gm(conn))

    async def rpc_gm_boss_config(self, conn: Conn, args: dict):
        return self.gm.boss_config(await self._gm(conn), args)

    async def rpc_gm_ability_save(self, conn: Conn, args: dict):
        return self.gm.ability_save(await self._gm(conn), args)

    async def rpc_gm_ability_remove(self, conn: Conn, args: dict):
        return self.gm.ability_remove(await self._gm(conn), args.get("name"))

    async def rpc_gm_ability_use(self, conn: Conn, args: dict):
        return await self.gm.ability_use(await self._gm(conn), args.get("name"))

    async def rpc_gm_gif_add(self, conn: Conn, args: dict):
        return self.gm.gif_add(await self._gm(conn), str(args.get("kind")), args.get("url"))

    async def rpc_gm_gif_remove(self, conn: Conn, args: dict):
        return self.gm.gif_remove(await self._gm(conn), str(args.get("kind")), args.get("index"))

    async def rpc_gm_domain_save(self, conn: Conn, args: dict):
        return self.gm.domain_save(await self._gm(conn), args)

    async def rpc_gm_domain_clear(self, conn: Conn, args: dict):
        return self.gm.domain_clear(await self._gm(conn))

    async def rpc_gm_domain_expand(self, conn: Conn, args: dict):
        return await self.gm.domain_expand(await self._gm(conn))

    # ---- the players ----------------------------------------------------------------------------------------------------------
    async def rpc_gm_players(self, conn: Conn, args: dict):
        await self._gm(conn)
        ids = self.gm.player_ids()
        people = dict(zip(ids, await asyncio.gather(*(self.who_is(i, fetch=False) for i in ids))))
        return {"players": self.gm.rows(people, {c.user_id for c in self.hub.conns.values()})}

    async def rpc_gm_player(self, conn: Conn, args: dict):
        await self._gm(conn)
        return await self._player_view(self._uid(args))

    async def rpc_gm_hp(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        uid, label = await self._who(args)
        await self.gm.set_hp(actor, uid, label, args.get("current"), args.get("max"))
        return await self._player_view(uid)

    async def rpc_gm_hp_reset(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        if args.get("id") in (None, "", "all"):
            return {"count": await self.gm.reset_hp(actor, None)}
        uid, label = await self._who(args)
        await self.gm.reset_hp(actor, uid, label)
        return await self._player_view(uid)

    async def rpc_gm_charges(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        uid, label = await self._who(args)
        self.gm.set_charges(actor, uid, label, args.get("power1"), args.get("power2"))
        return await self._player_view(uid)

    async def rpc_gm_cooldowns(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        uid, label = await self._who(args)
        self.gm.reset_cooldowns(actor, uid, label)
        return await self._player_view(uid)

    async def rpc_gm_afk(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        uid, label = await self._who(args)
        self.gm.set_afk(actor, uid, label, bool(args.get("afk")))
        return await self._player_view(uid)

    async def rpc_gm_points(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        uid, label = await self._who(args)
        self.gm.give_points(actor, uid, label, args.get("amount"))
        return await self._player_view(uid)

    async def rpc_gm_skills_reset(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        uid, label = await self._who(args)
        self.gm.reset_skills(actor, uid, label)
        return await self._player_view(uid)

    async def rpc_gm_ach_give(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        uid, label = await self._who(args)
        await self.gm.grant_achievement(actor, uid, label, args.get("achievement"))
        return await self._player_view(uid)

    async def rpc_gm_ach_remove(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        uid, label = await self._who(args)
        self.gm.remove_achievement(actor, uid, label, args.get("achievement"))
        return await self._player_view(uid)

    async def rpc_gm_obj_give(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        uid, label = await self._who(args)
        self.gm.give_object(actor, uid, label, args.get("object"))
        return await self._player_view(uid)

    async def rpc_gm_obj_take(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        uid, label = await self._who(args)
        self.gm.take_object(actor, uid, label, args.get("object"))
        return await self._player_view(uid)

    async def rpc_gm_obj_spins(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        uid, label = await self._who(args)
        if args.get("reset"):
            self.gm.reset_spins(actor, uid, label, args.get("object"))
        else:
            self.gm.set_spins(actor, uid, label, args.get("object"), args.get("values"))
        return await self._player_view(uid)

    async def rpc_gm_slots(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        uid, label = await self._who(args)
        self.gm.set_slots(actor, uid, label, args.get("slots"))
        return await self._player_view(uid)

    # ---- values -------------------------------------------------------------------------------------------------------------
    async def rpc_gm_values(self, conn: Conn, args: dict):
        await self._gm(conn)
        return self.gm.values()

    async def rpc_gm_value_set(self, conn: Conn, args: dict):
        return await self.gm.set_value(await self._gm(conn), str(args.get("key")), args.get("value"))

    async def rpc_gm_qte_set(self, conn: Conn, args: dict):
        return self.gm.set_qte(await self._gm(conn), str(args.get("difficulty")), args)

    # ---- content ------------------------------------------------------------------------------------------------------------
    async def rpc_gm_data(self, conn: Conn, args: dict):
        await self._gm(conn)
        return {"files": self.gm.files(), "templates": self.gm.templates()}

    async def rpc_gm_file_get(self, conn: Conn, args: dict):
        await self._gm(conn)
        return {**self.gm.file_get(str(args.get("key"))), "backups": self.gm.backups(str(args.get("key")))}

    async def rpc_gm_file_save(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        out = self.gm.file_save(actor, str(args.get("key")), args.get("text"))
        return {**out, "backups": self.gm.backups(str(args.get("key")))}

    async def rpc_gm_file_create(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        out = self.gm.file_create(actor, str(args.get("kind")), args.get("name"), args.get("text"))
        return {**out, "files": self.gm.files()}

    async def rpc_gm_file_delete(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        self.gm.file_delete(actor, str(args.get("key")))
        return {"files": self.gm.files()}

    async def rpc_gm_file_restore(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        out = self.gm.file_restore(actor, str(args.get("key")), str(args.get("name")))
        return {**out, "backups": self.gm.backups(str(args.get("key")))}

    async def rpc_gm_achievements(self, conn: Conn, args: dict):
        await self._gm(conn)
        return self.gm.achievements()

    async def rpc_gm_ach_save(self, conn: Conn, args: dict):
        return self.gm.achievement_save(await self._gm(conn), args)

    async def rpc_gm_ach_delete(self, conn: Conn, args: dict):
        return self.gm.achievement_delete(await self._gm(conn), args.get("id"))

    async def rpc_gm_objects(self, conn: Conn, args: dict):
        await self._gm(conn)
        return self.gm.objects()

    async def rpc_gm_obj_approve(self, conn: Conn, args: dict):
        return self.gm.object_approve(await self._gm(conn), str(args.get("file")))

    async def rpc_gm_obj_reject(self, conn: Conn, args: dict):
        return self.gm.object_reject(await self._gm(conn), str(args.get("file")), str(args.get("reason") or ""))

    async def rpc_gm_obj_reload(self, conn: Conn, args: dict):
        return self.gm.object_reload(await self._gm(conn))
