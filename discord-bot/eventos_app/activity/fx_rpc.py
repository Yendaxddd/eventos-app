"""The effects tab of the game-master panel (`gm.fx`, `gm.fx_set`, `gm.fx_clear`, `gm.fx_defaults`, `gm.fx_preview`).

Mixed into `ActivityBridge`; every handler first asks `_gm`, and what changes is signed in the panel's history. It relies on `self.fx`
(an FxDirector), `self.audio` and `self.gm.log`."""
from __future__ import annotations

import logging

from .audio import EVENTS
from .fx import BINDABLE, DEFAULT_BY_TYPE, PRESET_IDS, FxBook, power_key
from .hub import Conn, RpcError

log = logging.getLogger("eventos_app.activity")

MAX_POWERS_LISTED = 300


class FxRpc:
    def _fx_state(self) -> dict:
        book = self.fx.book
        powers = []
        for character, slots in list((getattr(self.app, "character_powers", None) or {}).items())[:MAX_POWERS_LISTED]:
            for slot in (1, 2):
                power = (slots or {}).get(f"power{slot}") if isinstance(slots, dict) else None
                if isinstance(power, dict) and power.get("name"):
                    key = power_key(character, slot)
                    powers.append({"character": str(character), "slot": slot, "name": str(power.get("name"))[:60], "type": str(power.get("type") or ""),
                                   "binding": book.powers.get(key)})
        return {"events": [{"id": e, "label": EVENTS[e][0], "scope": EVENTS[e][1], "binding": book.events.get(e)} for e in BINDABLE],
                "powers": powers, "defaults": book.defaults, "defaultByType": DEFAULT_BY_TYPE, "presets": list(PRESET_IDS),
                "sounds": [{"id": s["id"], "name": s["name"], "kind": s["kind"]} for s in self.audio.library.public()]}

    async def rpc_gm_fx(self, conn: Conn, args: dict):
        await self._gm(conn)
        return self._fx_state()

    async def rpc_gm_fx_set(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        what, sounds = args.get("for"), self.audio.library.get
        if what == "event":
            event = str(args.get("event"))
            self.fx.book.set_event(event, args.get("binding"), sounds)
            self.gm.log.add(actor, f"Puso un efecto a «{EVENTS[event][0]}»")
        elif what == "power":
            self.fx.book.set_power(args.get("character"), args.get("slot"), args.get("binding"), sounds)
            self.gm.log.add(actor, f"Puso un efecto al poder {args.get('slot')} de «{str(args.get('character'))[:40]}»")
        else:
            raise RpcError("No sé a qué poner ese efecto.")
        return self._fx_state()

    async def rpc_gm_fx_clear(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        what = args.get("for")
        if what == "event":
            self.fx.book.clear_event(args.get("event"))
            self.gm.log.add(actor, f"Quitó el efecto de «{EVENTS.get(str(args.get('event')), ('?',))[0]}»")
        elif what == "power":
            self.fx.book.clear_power(args.get("character"), args.get("slot"))
            self.gm.log.add(actor, f"Quitó el efecto del poder {args.get('slot')} de «{str(args.get('character'))[:40]}»")
        else:
            raise RpcError("No sé de qué quitar ese efecto.")
        return self._fx_state()

    async def rpc_gm_fx_defaults(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        on = bool(args.get("on"))
        self.fx.book.set_defaults(on)
        self.gm.log.add(actor, "Activó los efectos por defecto de los poderes" if on else "Apagó los efectos por defecto de los poderes")
        return self._fx_state()

    async def rpc_gm_fx_preview(self, conn: Conn, args: dict):
        """See (and hear) an effect that is not saved yet, only on the screen of whoever asks."""
        await self._gm(conn)
        binding = FxBook._checked(args.get("binding"), self.audio.library.get)
        await self.fx.show(binding, {"name": str(args.get("name") or "Poder de prueba")[:60], "event": "preview"}, {conn.user_id})
        return {"ok": True}
