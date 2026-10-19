"""The requests the dashboards make (see panel.py), as the bridge answers them: `panel.profile`, `panel.skills`, `panel.learn`...

Mixed into `ActivityBridge`; it relies on `self.app`, `self.hub`, `self.avatars`, `self.panel`, `self.is_gm`, `self.characters_of`
and `self.char_avatars`. Every handler works for the player the connection belongs to, whatever the page says.
"""
from __future__ import annotations

import asyncio
import io
import logging
import re
import time

import discord

from .hub import Conn, RpcError
from .media import sniff_image  # noqa: F401 - the pictures' check lives in media.py; kept importable from here
from .panel import LEADERBOARD_ROWS, PlayerPanel

log = logging.getLogger("eventos_app.activity")

NAME_CACHE_SECONDS = 600
NAME_CACHE_SIZE = 500
UPLOAD_MAX = 8 * 1024 * 1024
UPLOAD_PER_MINUTE = 6
STORAGE_NOTE = "📁 (Almacén de imágenes de la Actividad: ignorar)"
_STORAGE_MARKS = ("📁 (Image storage", "📁 (Almacén de imágenes")

def is_storage_message(message) -> bool:
    """The messages the bot (and the Activity) post only to get a lasting address for a picture."""
    return str(getattr(message, "content", "") or "").startswith(_STORAGE_MARKS)


class PanelRpc:
    panel: PlayerPanel

    def _init_panel(self) -> None:
        self.panel = PlayerPanel(self.app)
        self._names: dict[int, tuple[float, str, str | None]] = {}
        self._uploads: dict[int, list[float]] = {}

    # ---- who is who ----------------------------------------------------------------------------------------------
    async def who_is(self, user_id: int, fetch: bool = True) -> tuple[str, str | None]:
        """(name, picture) of a player for a list: the server's nickname if the bot can see them, else their Discord name
        (`fetch=False` never asks Discord: long lists must not make hundreds of requests)."""
        cached = self._names.get(user_id)
        if cached and time.monotonic() - cached[0] < NAME_CACHE_SECONDS:
            return cached[1], cached[2]
        name = avatar = None
        guild = self.app.resolve_event_guild()
        member = guild.get_member(user_id) if guild is not None else None
        if member is None and fetch:
            try:
                member = await self.app.bot.fetch_user(user_id)
            except Exception:  # noqa: BLE001 - deleted account, no network...
                member = None
        if member is not None:
            name = getattr(member, "display_name", None) or getattr(member, "name", None)
            avatar = str(member.display_avatar.url) if getattr(member, "display_avatar", None) is not None else None
        name = name or f"Jugador …{str(user_id)[-4:]}"
        self._names[user_id] = (time.monotonic(), name, avatar)
        while len(self._names) > NAME_CACHE_SIZE:
            self._names.pop(next(iter(self._names)))
        return name, avatar

    # ---- reads -----------------------------------------------------------------------------------------------------
    async def rpc_panel_profile(self, conn: Conn, args: dict):
        return self.panel.profile(conn.user_id)

    async def rpc_panel_achievements(self, conn: Conn, args: dict):
        return self.panel.achievements(conn.user_id)

    async def rpc_panel_skills(self, conn: Conn, args: dict):
        return self.panel.skills(conn.user_id)

    async def rpc_panel_inventory(self, conn: Conn, args: dict):
        return self.panel.inventory(conn.user_id)

    async def rpc_panel_images(self, conn: Conn, args: dict):
        return self.panel.counter_images(conn.user_id)

    async def rpc_panel_board(self, conn: Conn, args: dict):
        category = str(args.get("category") or "success_rate")
        rows = self.panel.ranking(category)
        top = rows[:LEADERBOARD_ROWS]
        mine = next((r for r in rows if r["id"] == conn.user_id), None)
        shown = top + ([mine] if mine is not None and mine not in top else [])
        people = await asyncio.gather(*(self.who_is(r["id"]) for r in shown))

        def line(row, who):
            return {"rank": row["rank"], "id": str(row["id"]), "name": who[0], "avatar": who[1], "text": row["text"], "me": row["id"] == conn.user_id}
        lines = [line(r, w) for r, w in zip(shown, people)]
        return {"category": category, "rows": lines[:len(top)], "me": lines[len(top)] if mine is not None and mine not in top else None, "total": len(rows)}

    async def rpc_panel_characters(self, conn: Conn, args: dict):
        return self._characters_payload(conn)

    def _characters_payload(self, conn: Conn) -> dict:
        seen = [name for name in reversed(self.avatars) if name != conn.name][:40]       # the pictures of whoever spoke through a webhook
        return self.panel.characters(conn.user_id, avatars=self.char_avatars(conn.user_id), seen=seen)

    async def _characters_changed(self, conn: Conn) -> dict:
        """After a character is registered or dropped: every screen of that player learns the new list."""
        frame = {"t": "chars", "characters": self.characters_of(conn.user_id), "charAvatars": self.char_avatars(conn.user_id)}
        for other in list(self.hub.conns.values()):
            if other.user_id == conn.user_id:
                await self.hub.send(other, frame)
        return self._characters_payload(conn)

    # ---- changes ---------------------------------------------------------------------------------------------------
    async def rpc_panel_active(self, conn: Conn, args: dict):
        return self.panel.set_active(conn.user_id, bool(args.get("active")))

    async def rpc_panel_title(self, conn: Conn, args: dict):
        return self.panel.set_title(conn.user_id, args.get("title"))

    async def rpc_panel_domain(self, conn: Conn, args: dict):
        return self.panel.set_domain(conn.user_id, str(args.get("id") or ""))

    async def rpc_panel_learn(self, conn: Conn, args: dict):
        result = self.panel.learn_skill(conn.user_id, args.get("id"))
        log.info("%s aprendió la habilidad %s (rango %s)", conn.name, result["id"], result["rank"])
        return {**result, "skills": self.panel.skills(conn.user_id)}

    async def rpc_panel_register(self, conn: Conn, args: dict):
        done = self.panel.register_character(conn.user_id, args.get("name"))
        log.info("%s registró el personaje %s desde la Actividad", conn.name, done["name"])
        return await self._characters_changed(conn)

    async def rpc_panel_unregister(self, conn: Conn, args: dict):
        done = self.panel.unregister_character(conn.user_id, args.get("name"))
        log.info("%s quitó el personaje %s desde la Actividad", conn.name, done["name"])
        return await self._characters_changed(conn)

    async def rpc_panel_power(self, conn: Conn, args: dict):
        done = self.panel.save_power(conn.user_id, await self.is_gm(conn), args)
        log.info("%s guardó el poder %s de %s", conn.name, done["slot"], done["character"])
        return await self._characters_changed(conn)

    async def rpc_panel_unpower(self, conn: Conn, args: dict):
        self.panel.remove_power(conn.user_id, await self.is_gm(conn), args.get("character"), args.get("slot"))
        return await self._characters_changed(conn)

    async def rpc_panel_image_add(self, conn: Conn, args: dict):
        return self.panel.add_counter_image(conn.user_id, args.get("url"))

    async def rpc_panel_image_remove(self, conn: Conn, args: dict):
        return self.panel.remove_counter_image(conn.user_id, args.get("index"))

    async def rpc_panel_images_clear(self, conn: Conn, args: dict):
        return self.panel.clear_counter_images(conn.user_id)

    # ---- pictures a player uploads from their device ----------------------------------------------------------------
    async def store_image(self, user_id: int, filename: str, data: bytes) -> str:
        """Give a picture a lasting Discord address (like /setcountergif does): it is posted in the event channel as a
        storage message that the Activity itself hides. Returns the address. Raises RpcError with the reason."""
        if not data:
            raise RpcError("La imagen está vacía.")
        if len(data) > UPLOAD_MAX:
            raise RpcError(f"La imagen pesa demasiado: el máximo es {UPLOAD_MAX // (1024 * 1024)} MB.")
        kind = sniff_image(data)
        if kind is None:
            raise RpcError("Solo se aceptan imágenes PNG, JPG, GIF o WebP.")
        now = time.monotonic()
        recent = [t for t in self._uploads.get(user_id, []) if now - t < 60]
        if len(recent) >= UPLOAD_PER_MINUTE:
            raise RpcError("Estás subiendo imágenes muy rápido. Espera un minuto.")
        self._uploads[user_id] = [*recent, now]
        channel = self.channel()
        if channel is None:
            raise RpcError("El evento todavía no tiene canal donde guardar la imagen.")
        stem = re.sub(r"[^A-Za-z0-9_-]+", "_", str(filename).rsplit(".", 1)[0])[:40].strip("_") or "imagen"
        try:
            message = await channel.send(content=STORAGE_NOTE, file=discord.File(io.BytesIO(data), filename=f"{stem}{kind[1]}"),
                                         allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException as exc:
            log.warning("could not store an uploaded picture: %s", exc)
            raise RpcError("Discord no dejó guardar la imagen. Prueba con otra o con un enlace.") from exc
        if not message.attachments:
            raise RpcError("Discord no devolvió la dirección de la imagen.")
        return str(message.attachments[0].url)
