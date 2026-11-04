"""The «Equipo de GM» page (`gm.staff`, `gm.staff_set`, `gm.staff_remove`, `gm.staff_admins`): who is a game master and with which boxes.

Mixed into `ActivityBridge`; relies on `self.staff` (staff.StaffBook), `self._gm`, `self.who_is`, `self.gm` and `self.push_perms`.
Nobody can give a box they do not have, and only a host can name another host."""
from __future__ import annotations

import asyncio

from .hub import Conn, RpcError
from .staff import PERMS, preset_of

LABELS = {p[0]: p[1] for p in PERMS}


class StaffRpc:
    def _guild_roles(self) -> list[dict]:
        guild = self.app.resolve_event_guild()
        out = []
        for role in list(getattr(guild, "roles", None) or [])[:250]:
            if getattr(role, "is_default", lambda: False)():
                continue                                  # @everyone
            colour = getattr(getattr(role, "colour", None), "value", 0) or 0
            out.append({"id": str(role.id), "name": str(getattr(role, "name", role.id)), "color": f"#{colour:06x}" if colour else ""})
        return out

    async def _staff_state(self, conn: Conn) -> dict:
        ids = self.gm.player_ids()
        for c in self.hub.conns.values():
            if c.user_id > 0 and c.user_id not in ids:
                ids.append(c.user_id)
        names = dict(zip(ids, await asyncio.gather(*(self.who_is(i, fetch=False) for i in ids))))
        perms, host = await self.conn_access(conn)
        return {**self.staff.public(), "roles_available": self._guild_roles(),
                "people_available": [{"id": str(i), "name": names[i][0], "avatar": names[i][1]} for i in ids],
                "me": {"id": str(conn.user_id), "perms": perms, "host": host}}

    async def rpc_gm_staff(self, conn: Conn, args: dict):
        await self._gm(conn)
        return await self._staff_state(conn)

    async def rpc_gm_staff_set(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        mine, host = await self.conn_access(conn)
        kind = str(args.get("kind") or "")
        if kind == "host" and not host:
            raise RpcError("Solo un anfitrión puede nombrar a otro anfitrión.")
        wanted = [p for p in (args.get("perms") or []) if isinstance(p, str)]
        missing = [p for p in wanted if p not in mine]
        if missing:
            raise RpcError(f"No puedes dar un permiso que no tienes: {LABELS.get(missing[0], missing[0])}.")
        if kind == "person" and str(args.get("id")) == str(conn.user_id) and not host:
            raise RpcError("No puedes cambiar tus propios permisos: pídeselo a otro miembro del equipo.")
        entry = self.staff.set_entry(kind, args.get("id"), args.get("name"), wanted)
        what = {"host": "anfitrión", "person": "persona", "role": "rol"}[kind]
        preset = preset_of(entry["perms"])
        self.gm.log.add(actor, f"Equipo de GM: {args.get('name') or entry['id']} ({what}) → "
                               + ("anfitrión" if kind == "host" else (", ".join(LABELS[p] for p in entry["perms"]) or "sin permisos") + (f" [{preset}]" if preset != "custom" else "")))
        await self.push_perms()
        return await self._staff_state(conn)

    async def rpc_gm_staff_remove(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        _mine, host = await self.conn_access(conn)
        kind = str(args.get("kind") or "")
        if kind == "host" and not host:
            raise RpcError("Solo un anfitrión puede quitar a otro anfitrión.")
        self.staff.remove(kind, args.get("id"))
        self.gm.log.add(actor, f"Equipo de GM: quitó a {args.get('name') or args.get('id')} ({kind})")
        await self.push_perms()
        return await self._staff_state(conn)

    async def rpc_gm_staff_admins(self, conn: Conn, args: dict):
        """What the bot's admin role gives by itself (to whoever has no entry of their own)."""
        actor = await self._gm(conn)
        mine, _host = await self.conn_access(conn)
        wanted = [p for p in (args.get("perms") or []) if isinstance(p, str)]
        missing = [p for p in wanted if p not in mine]
        if missing:
            raise RpcError(f"No puedes dar un permiso que no tienes: {LABELS.get(missing[0], missing[0])}.")
        boxes = self.staff.set_admins(wanted)
        self.gm.log.add(actor, "Equipo de GM: el rol de administrador da → " + (", ".join(LABELS[p] for p in boxes) or "nada"))
        await self.push_perms()
        return await self._staff_state(conn)
