"""The audio side of the game-master panel: the library, the music, the soundboard and the cues (`gm.audio*`, `gm.music*`, `gm.cue*`).

Mixed into `ActivityBridge`; every handler first asks `_gm` (see gm_rpc.py), and what changes is signed in the panel's history. It relies on
`self.audio` (an AudioDirector) and `self.gm.log`."""
from __future__ import annotations

import logging

from .audio import EVENTS, KINDS
from .hub import Conn, RpcError
from .media import AUDIO

log = logging.getLogger("eventos_app.activity")


class AudioRpc:
    def _audio_state(self) -> dict:
        files, size = self.audio.library.store.usage(AUDIO) if self.audio.library.store is not None else (0, 0)
        return {"library": self.audio.library.public(), "cues": {e: dict(c) for e, c in self.audio.library.cues.items()},
                "events": [{"id": e, "label": label, "scope": scope} for e, (label, scope) in EVENTS.items()],
                "kinds": [{"id": k, "label": label} for k, label in KINDS.items()], "music": self.audio.music_frame(),
                "usage": {"files": files, "bytes": size}, "canStore": self.audio.library.store is not None}

    async def rpc_gm_audio(self, conn: Conn, args: dict):
        await self._gm(conn)
        return self._audio_state()

    async def rpc_gm_audio_update(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        sound = self.audio.library.update(args.get("id"), {k: v for k, v in args.items() if k in ("name", "kind", "volume", "loop")})
        self.gm.log.add(actor, f"Cambió el sonido «{sound['name']}» de la biblioteca")
        await self.audio.announce_library()
        return self._audio_state()

    async def rpc_gm_audio_delete(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        sound = self.audio.library.delete(args.get("id"))
        self.fx.book.forget_sound(sound["id"])
        if self.audio.music is not None and self.audio.music["sound"]["id"] == sound["id"]:
            await self.audio.stop_music()
        self.gm.log.add(actor, f"Borró el sonido «{sound['name']}» de la biblioteca")
        await self.audio.announce_library()
        return self._audio_state()

    async def rpc_gm_audio_play(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        sound = await self.audio.play(args.get("id"), args.get("volume", 100))
        self.gm.log.add(actor, f"Hizo sonar «{sound['name']}» para todos")
        return {"ok": True}

    async def rpc_gm_audio_stop(self, conn: Conn, args: dict):
        await self._gm(conn)
        await self.audio.stop_all()
        return {"ok": True}

    async def rpc_gm_music_play(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        music = await self.audio.start_music(args.get("id"), args.get("volume", 100), args.get("loop"))
        self.gm.log.add(actor, f"Puso la música «{music['sound']['name']}»")
        return self._audio_state()

    async def rpc_gm_music_stop(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        if self.audio.music is not None:
            self.gm.log.add(actor, f"Paró la música «{self.audio.music['sound']['name']}»")
        await self.audio.stop_music()
        return self._audio_state()

    async def rpc_gm_music_volume(self, conn: Conn, args: dict):
        await self._gm(conn)
        await self.audio.set_music_volume(args.get("volume"))
        return self._audio_state()

    async def rpc_gm_cue_set(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        cue = self.audio.library.set_cue(args.get("event"), args.get("sound"), args.get("volume", 100), args.get("scope"), args.get("enabled", True))
        sound = self.audio.library.get(cue["sound"])
        self.gm.log.add(actor, f"Ligó el sonido «{sound['name']}» a «{EVENTS[str(args.get('event'))][0]}»")
        return self._audio_state()

    async def rpc_gm_cue_clear(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        event = str(args.get("event"))
        if event not in EVENTS:
            raise RpcError("Ese aviso no existe.")
        self.audio.library.clear_cue(event)
        self.gm.log.add(actor, f"Quitó el sonido de «{EVENTS[event][0]}»")
        return self._audio_state()

    async def rpc_gm_cue_test(self, conn: Conn, args: dict):
        """Hear a cue as the players would, but only on the screen of whoever asks."""
        await self._gm(conn)
        event = str(args.get("event"))
        if event not in EVENTS:
            raise RpcError("Ese aviso no existe.")
        found = self.audio.library.cue_for(event, {})
        if found is None:
            raise RpcError("Ese aviso todavía no tiene sonido.")
        sound = self.audio.library.get(found[1]["sound"])
        await self.audio.play(sound["id"], found[1]["volume"], user_ids={conn.user_id})
        return {"ok": True}

    # ---- the uploads (the page sends the file over HTTP) -------------------------------------------------------------------
    async def store_audio(self, user_id: int, filename: str, kind: str, data: bytes, dev_gm: bool = False) -> dict:
        if not await self.gm_user(user_id, dev_gm):
            raise RpcError("Esto es solo para el equipo de GM.")
        sound = self.audio.library.add(filename, data, kind)
        who = (await self.who_is(user_id, fetch=False))[0]
        self.gm.log.add(who, f"Subió el sonido «{sound['name']}» a la biblioteca")
        await self.audio.announce_library()
        return sound
