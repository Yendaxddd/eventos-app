"""The game masters' quick controls (`gm.quick`): everything the side panel needs in one request, so it can keep itself fresh without asking for
five things every few seconds. The actions themselves are the panel's usual ones (`gm.fight`, `gm.boss_spawn`, `gm.cinema_play`...).

Mixed into `ActivityBridge`; it relies on `self.gm`, `self.cinema`, `self.audio` and `self.fx`."""
from __future__ import annotations

from .audio import EVENTS
from .fx import PRESET_IDS
from .hub import Conn

LINKED_EVENTS = ("fight_start", "boss_spawn", "boss_domain", "boss_defeated", "fight_end")          # the moments of a fight that other systems hook onto


class QuickRpc:
    def _links(self) -> list[dict]:
        """For each moment of a fight, what is already bound to it: cinematics, music, an effect and a sound."""
        out = []
        library, fx = self.audio.library, self.fx.book
        for event in LINKED_EVENTS:
            cinemas = [{"id": c["id"], "name": c["name"], "boss": c.get("boss", "")} for c in self.cinema.book.items.values() if event in c["triggers"]]
            phase = library.phases.get(event)
            cue = library.cues.get(event)
            effect = fx.events.get(event)
            out.append({"event": event, "label": EVENTS[event][0], "cinemas": cinemas, "cinema": cinemas[0] if cinemas else None,
                        "phase": dict(phase) if phase else None, "effect": dict(effect) if effect else None, "cue": dict(cue) if cue else None})
        return out

    async def rpc_gm_quick(self, conn: Conn, args: dict):
        await self._gm(conn)
        state = self.gm.state()
        config = self.gm.boss()["config"]
        run = self.cinema.current()
        music = self.audio.music
        return {
            "state": state,
            "boss": {"active": state["boss"], "mode": state["bossMode"], "character": config["character"], "hp": config["hp"],
                     "abilities": [{"name": a["name"], "damage": a["damage"]} for a in config["abilities"][:12]], "domain": config["domain"]["name"] if config["domain"] else None},
            "cinemas": [{"id": c["id"], "name": c["name"], "seconds": max(1, round(c["duration"] - 1)), "triggers": c["triggers"]} for c in self.cinema.book.listing()],
            "running": run["id"] if run else None,
            "music": None if music is None else {"name": music["sound"]["name"], "volume": music["volume"]},
            "tracks": [{"id": s["id"], "name": s["name"]} for s in self.audio.library.public() if s["kind"] == "music"],
            "links": self._links(),
            "sounds": [{"id": s["id"], "name": s["name"], "kind": s["kind"]} for s in self.audio.library.public()],
            "presets": list(PRESET_IDS),
        }
