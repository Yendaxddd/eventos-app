"""Players' cinematics for their own powers and actions: a player writes a short cinematic (with the same editor the game masters use,
minus sound and channel messages), ties it to one of their powers or actions (a Black Flash, a domain, a counter...) and sends it.
A game master with the box «Solicitudes» approves it (or sends it back with a note); from then on it plays for everybody each time
that player does that, with a cooldown so it does not tire.

Only the player and the game masters who review requests ever see what is inside: for everybody else it is a surprise.

Ops (everybody): `creq.state`, `creq.save`, `creq.send`, `creq.delete`. Box «Solicitudes»: `gm.requests`, `gm.request_decide`."""
from __future__ import annotations

import logging
import time

from .audio import EVENTS
from .cinema import PLAYER_EVENTS
from .hub import Conn, RpcError

log = logging.getLogger("eventos_app.activity")

MAX_REQUESTS_EACH = 10
MAX_REQUEST_SECONDS = 20.0
PLAYER_STEPS = ("text", "title", "image", "scene", "effect", "vfx", "weather")     # no sounds from the GM library, no channel messages
UPLOADS_PER_HOUR = 15
EVENT_LABELS = {
    "power_used": "Cuando uso un poder", "black_flash": "Cuando hago un Black Flash", "domain": "Cuando completo mi expansión de dominio",
    "domain_cast": "Cuando empiezo mi expansión de dominio", "counter": "Cuando contraataco", "parry_ok": "Cuando hago un parry",
    "rescue_ok": "Cuando rescato a alguien", "mirror_invoke": "Cuando invoco el espejo", "chain_max": "Cuando llego a la cadena máxima de Black Flash",
    "combo_done": "Cuando completo un combo",
}


def bind_label(bind: dict) -> str:
    text = EVENT_LABELS.get(bind.get("event"), EVENTS.get(bind.get("event"), (bind.get("event"),))[0])
    if bind.get("event") == "power_used":
        who = bind.get("character") or "cualquier personaje"
        text = f"Cuando {who} usa {'el Poder ' + bind['slot'] if bind.get('slot') else 'un poder'}"
    elif bind.get("character"):
        text += f" (como {bind['character']})"
    return text


class CinemaRequestRpc:
    """Mixed into ActivityBridge; relies on `self.cinema` (CinemaDirector), `self.audio`, `self.hub`, `self._gm`, `self.gm.log`,
    `self.conn_access`, `self.characters_of`."""

    _creq_uploads: dict[int, list[float]]

    def creq_can_upload(self, user_id: int) -> bool:
        """A player may add pictures for their requests, a few an hour (they stay on the host's PC)."""
        if not hasattr(self, "_creq_uploads"):
            self._creq_uploads = {}
        now = time.time()
        recent = [t for t in self._creq_uploads.get(user_id, []) if now - t < 3600]
        if len(recent) >= UPLOADS_PER_HOUR:
            return False
        self._creq_uploads[user_id] = recent + [now]
        return True

    def _creq_mine(self, conn: Conn) -> list[dict]:
        me = str(conn.user_id)
        return [c for c in self.cinema.book.listing() if c.get("kind") == "request" and (c.get("owner") or {}).get("id") == me]

    def _creq_own(self, conn: Conn, cid) -> dict:
        c = self.cinema.book.get(cid)
        if c is None or c.get("kind") != "request" or (c.get("owner") or {}).get("id") != str(conn.user_id):
            raise RpcError("Esa solicitud no es tuya o ya no existe.")
        return c

    def _creq_powers(self, character: str) -> list[dict]:
        powers = (getattr(self.app, "character_powers", None) or {}).get(character) or {}
        out = []
        for slot in ("1", "2"):
            p = powers.get(f"power{slot}") if isinstance(powers, dict) else None
            if isinstance(p, dict):
                out.append({"slot": slot, "name": str(p.get("name") or f"Poder {slot}")[:60]})
        return out

    async def _creq_state(self, conn: Conn) -> dict:
        chars = self.characters_of(conn.user_id)
        images = getattr(self, "char_images", {}) or {}
        return {
            "mine": [{**c, "bindLabel": bind_label(c.get("bind") or {})} for c in self._creq_mine(conn)],
            "characters": [{"name": n, "powers": self._creq_powers(n)} for n in chars],
            "events": [{"id": e, "label": EVENT_LABELS[e]} for e in PLAYER_EVENTS],
            "limit": MAX_REQUESTS_EACH, "maxSeconds": MAX_REQUEST_SECONDS, "steps": list(PLAYER_STEPS),
            # what the shared editor needs (as the game masters' «d»)
            "d": {"me": str(conn.user_id), "sounds": [], "events": [], "bosses": [], "canStore": self.audio.library.store is not None,
                  "images": {"files": 0, "bytes": 0}, "cast": [{"name": n, "image": images[n]} for n in chars if n in images]},
        }

    async def rpc_creq_state(self, conn: Conn, args: dict):
        return await self._creq_state(conn)

    async def rpc_creq_save(self, conn: Conn, args: dict):
        raw = args.get("cinema")
        if not isinstance(raw, dict):
            raise RpcError("Falta la cinemática.")
        cid = str(raw.get("id") or "")
        before = self._creq_own(conn, cid) if cid else None
        if before is None and len(self._creq_mine(conn)) >= MAX_REQUESTS_EACH:
            raise RpcError(f"Puedes tener hasta {MAX_REQUESTS_EACH} solicitudes: borra alguna.")
        steps = [s for s in (raw.get("steps") or []) if isinstance(s, dict)]
        if any(s.get("type") not in PLAYER_STEPS for s in steps):
            raise RpcError("Las cinemáticas de jugador no llevan sonidos de la biblioteca ni mensajes en el canal.")
        bind = raw.get("bind") if isinstance(raw.get("bind"), dict) else {}
        character = str(bind.get("character") or "")
        if character and character not in self.characters_of(conn.user_id):
            raise RpcError("Ese personaje no es tuyo.")
        status = before["status"] if before is not None else "draft"
        if status in ("approved", "rejected"):
            status = "draft"                          # changed after a decision: it needs to be sent (and approved) again
        clean = {**raw, "kind": "request", "status": status, "share": "private", "editors": [], "triggers": [], "boss": "",
                 "bind": {**bind, "user": str(conn.user_id)}, "review": before.get("review", "") if before else ""}
        cinema = self.cinema.book.put(clean, author={"id": str(conn.user_id), "name": conn.name})
        if cinema["duration"] - 1 > MAX_REQUEST_SECONDS:
            self.cinema.book.put({**cinema, "status": "draft"})
            raise RpcError(f"Las cinemáticas de jugador duran como mucho {int(MAX_REQUEST_SECONDS)} s (la tuya, {int(cinema['duration'] - 1)} s). Está guardada como borrador.")
        return {**await self._creq_state(conn), "saved": {"id": cinema["id"], "status": cinema["status"]}}

    async def rpc_creq_send(self, conn: Conn, args: dict):
        c = self._creq_own(conn, args.get("id"))
        c["status"] = "pending"
        self.cinema.book.save()
        await self._creq_tell_reviewers(f"{conn.name} pide una cinemática: «{c['name']}» ({bind_label(c.get('bind') or {}).lower()}).")
        return await self._creq_state(conn)

    async def rpc_creq_delete(self, conn: Conn, args: dict):
        c = self._creq_own(conn, args.get("id"))
        self.cinema.book.delete(c["id"])
        return await self._creq_state(conn)

    async def _creq_tell_reviewers(self, text: str) -> None:
        for other in list(self.hub.conns.values()):
            try:
                perms, _host = await self.conn_access(other)
            except Exception:  # noqa: BLE001
                continue
            if "requests" in perms:
                await self.hub.send(other, {"t": "toast", "text": text, "kind": "info"})
        await self.hub.broadcast({"t": "creq"})

    # ---- the game masters ------------------------------------------------------------------------------------------------
    def _creq_queue(self) -> dict:
        items = [c for c in self.cinema.book.listing() if c.get("kind") == "request" and c.get("status") != "draft"]
        order = {"pending": 0, "approved": 1, "rejected": 2}
        items.sort(key=lambda c: order.get(c.get("status"), 3))
        return {"requests": [{**c, "bindLabel": bind_label(c.get("bind") or {})} for c in items]}

    async def rpc_gm_requests(self, conn: Conn, args: dict):
        await self._gm(conn)
        return self._creq_queue()

    async def rpc_gm_request_decide(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        c = self.cinema.book.get(args.get("id"))
        if c is None or c.get("kind") != "request":
            raise RpcError("Esa solicitud ya no existe.")
        status = args.get("status")
        if status not in ("approved", "rejected", "pending"):
            raise RpcError("Decide «aprobar» o «rechazar».")
        c["status"] = status
        c["review"] = " ".join(str(args.get("review") or "").split())[:300]
        self.cinema.book.save()
        owner = int((c.get("owner") or {}).get("id") or 0)
        word = {"approved": "aprobó", "rejected": "devolvió", "pending": "dejó pendiente"}[status]
        text = f"El equipo de GM {word} tu cinemática «{c['name']}»" + (f": {c['review']}" if c["review"] else ".")
        for other in list(self.hub.conns.values()):
            if other.user_id == owner:
                await self.hub.send(other, {"t": "toast", "text": text, "kind": "ok" if status == "approved" else "info"})
        await self.hub.broadcast({"t": "creq"})
        self.gm.log.add(actor, f"{word.capitalize()} la cinemática de {(c.get('owner') or {}).get('name', '?')} «{c['name']}»")
        return self._creq_queue()
