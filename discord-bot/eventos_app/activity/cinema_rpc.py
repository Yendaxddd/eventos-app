"""The cinematics tab of the game-master panel (`gm.cinemas`, `gm.cinema_save`, `gm.cinema_play`...).

Mixed into `ActivityBridge`; every handler first asks `_gm`, and what changes is signed in the panel's history. It relies on `self.cinema`
(a CinemaDirector), `self.audio` and `self.gm.log`."""
from __future__ import annotations

import logging

import discord

from .audio import EVENTS
from .cinema import TRIGGER_EVENTS
from .hub import Conn, RpcError
from .media import IMAGES, MediaError

log = logging.getLogger("eventos_app.activity")


class CinemaRpc:
    def _cinema_state(self) -> dict:
        run = self.cinema.current()
        files, size = self.audio.library.store.usage(IMAGES) if self.audio.library.store is not None else (0, 0)
        return {"cinemas": self.cinema.book.listing(), "running": run["id"] if run else None,
                "events": [{"id": e, "label": EVENTS[e][0]} for e in TRIGGER_EVENTS],
                "sounds": [{"id": s["id"], "name": s["name"], "kind": s["kind"]} for s in self.audio.library.public()],
                "images": {"files": files, "bytes": size}, "canStore": self.audio.library.store is not None,
                "autoplay": self.cinema.on_event_enabled}

    async def rpc_gm_cinemas(self, conn: Conn, args: dict):
        await self._gm(conn)
        return self._cinema_state()

    async def rpc_gm_cinema_save(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        raw = args.get("cinema")
        cinema = self.cinema.book.put(raw)
        self.gm.log.add(actor, f"Guardó la cinemática «{cinema['name']}» ({len(cinema['steps'])} pasos)")
        return {**self._cinema_state(), "saved": cinema}

    async def rpc_gm_cinema_delete(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        cinema = self.cinema.book.delete(args.get("id"))
        if self.cinema.run is not None and self.cinema.run["id"] == cinema["id"]:
            await self.cinema.stop()
        self.gm.log.add(actor, f"Borró la cinemática «{cinema['name']}»")
        return self._cinema_state()

    async def rpc_gm_cinema_duplicate(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        cinema = self.cinema.book.duplicate(args.get("id"))
        self.gm.log.add(actor, f"Duplicó una cinemática como «{cinema['name']}»")
        return {**self._cinema_state(), "saved": cinema}

    async def rpc_gm_cinema_play(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        cinema = await self.cinema.play(args.get("id"))
        self.gm.log.add(actor, f"Puso la cinemática «{cinema['name']}» para todos")
        return self._cinema_state()

    async def rpc_gm_cinema_stop(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        if await self.cinema.stop():
            self.gm.log.add(actor, "Paró la cinemática")
        return self._cinema_state()

    async def rpc_gm_cinema_auto(self, conn: Conn, args: dict):
        """Switch off (or on) the cinematics that start by themselves when something happens."""
        actor = await self._gm(conn)
        self.cinema.on_event_enabled = bool(args.get("enabled"))
        self.gm.log.add(actor, "Activó las cinemáticas automáticas" if self.cinema.on_event_enabled else "Desactivó las cinemáticas automáticas")
        return self._cinema_state()

    # ---- the channel messages of a cinematic -----------------------------------------------------------------------------------
    async def _cinema_post(self, text: str) -> None:
        channel = self.channel()
        if channel is not None:
            await channel.send(text, allowed_mentions=discord.AllowedMentions.none())

    # ---- a picture for a cinematic (a game master uploads it over HTTP; it stays on this PC) ----------------------------------------
    async def store_cinema_image(self, user_id: int, filename: str, data: bytes, dev_gm: bool = False) -> dict:
        if not await self.gm_user(user_id, dev_gm):
            raise RpcError("Esto es solo para el equipo de GM.")
        store = self.audio.library.store
        if store is None:
            raise RpcError("Esta Actividad no puede guardar archivos en este PC.")
        try:
            stored = store.save(IMAGES, data)
        except MediaError as exc:
            raise RpcError(str(exc)) from exc
        return {"path": stored.path, "size": stored.size}
