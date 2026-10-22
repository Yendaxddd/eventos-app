"""The mini enemies, as the screens ask for them (`mob.attack` for players; `gm.mobs*` for the game masters).

Mixed into `ActivityBridge`; every `gm.*` handler first asks `_gm`, and what changes is signed in the panel's history. It relies on
`self.mobs` (a Mobs, mobs.py)."""
from __future__ import annotations

from .hub import Conn, RpcError
from .mobs import ATTACKS, DIFFICULTIES, MAX_LIVE, MAX_SPAWN


class MobsRpc:
    def _mobs_state(self) -> dict:
        return {"bestiary": list(self.mobs.bestiary.items.values()), **self.mobs.public(), "attacks": list(ATTACKS),
                "difficulties": list(DIFFICULTIES), "maxLive": MAX_LIVE, "maxSpawn": MAX_SPAWN}

    async def rpc_mob_attack(self, conn: Conn, args: dict):
        if conn.hidden:
            raise RpcError("Desde esta ventana no se puede golpear.")
        return await self.mobs.hit(conn.user_id, conn.name, args.get("id"))

    async def rpc_gm_mobs(self, conn: Conn, args: dict):
        await self._gm(conn)
        return self._mobs_state()

    async def rpc_gm_mob_save(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        t = self.mobs.bestiary.put(args.get("mob"))
        self.gm.log.add(actor, f"Guardó el enemigo «{t['name']}» en el bestiario")
        return {**self._mobs_state(), "saved": t["id"]}

    async def rpc_gm_mob_delete(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        t = self.mobs.bestiary.delete(args.get("id"))
        self.gm.log.add(actor, f"Borró el enemigo «{t['name']}» del bestiario")
        return self._mobs_state()

    async def rpc_gm_mob_spawn(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        made = await self.mobs.spawn(args.get("id"), args.get("count", 1))
        self.gm.log.add(actor, f"Hizo aparecer {len(made)} × «{self.mobs.bestiary.items[made[0]['template']]['name']}»")
        return self._mobs_state()

    async def rpc_gm_mob_hp(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        action = str(args.get("action") or "")
        mob = await self.mobs.set_hp(args.get("id"), action, args.get("amount"))
        words = {"damage": "Dañó", "heal": "Curó", "kill": "Derrotó"}.get(action, action)
        self.gm.log.add(actor, f"{words} a «{mob['name']}»" + (f" ({args.get('amount')})" if action != "kill" else ""))
        return self._mobs_state()

    async def rpc_gm_mob_remove(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        await self.mobs.remove(args.get("id"))
        self.gm.log.add(actor, "Retiró a todos los enemigos" if args.get("id") in (None, "", "all") else "Retiró un enemigo")
        return self._mobs_state()

    async def rpc_gm_mob_pause(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        await self.mobs.set_paused(bool(args.get("paused")))
        self.gm.log.add(actor, "Pausó a los enemigos" if self.mobs.paused else "Reanudó a los enemigos")
        return self._mobs_state()
