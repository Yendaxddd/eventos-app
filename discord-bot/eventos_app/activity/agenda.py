"""The agenda: when people can play, so the game masters know when an event works best.

Three things live here:
- each player's week: 168 hours (Monday 00:00 UTC first), each «no», «maybe» or «yes». The screen converts to and from the
  player's own clock, so everybody sees the week in their local time.
- each player's calendar: concrete dates (in their own calendar, «2026-11-15») that override the week for that day: yes / maybe /
  no, an optional range of hours in their clock and a short note («where»: «en el móvil», «desde el tren»). With their time zone
  (IANA name and the offset in minutes it had when they saved) everybody else's screen converts those hours to its own clock.
- date polls the game masters open (box «Agenda»): a few concrete dates, everybody answers yes / maybe / no, and a game
  master picks the winner, which every screen then shows as the next event.

Ops: `agenda.get`, `agenda.week`, `agenda.day`, `agenda.zone`, `agenda.vote` for everybody; `gm.schedule_propose`, `gm.schedule_close`,
`gm.schedule_delete` for the box. Every change sends `{"t": "agenda"}` so open screens fetch it again."""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import date, timedelta
import uuid
from pathlib import Path
from typing import Any

from .hub import Conn, RpcError

log = logging.getLogger("eventos_app.activity")

HOURS = 168
ANSWERS = ("yes", "maybe", "no")
MAX_OPTIONS = 8
MAX_POLLS = 12
DAY_MS = 86_400_000
MAX_DAYS = 120                  # concrete dates a player can have marked at once
DAY_NOTE = 120
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def clean_week(raw: Any) -> str:
    """168 characters, each 0 (no), 1 (maybe) or 2 (yes); anything else is «no»."""
    if isinstance(raw, list):
        raw = "".join(str(x) for x in raw[:HOURS])
    text = str(raw or "")[:HOURS]
    return "".join(c if c in "012" else "0" for c in text).ljust(HOURS, "0")


def _text(raw: Any, limit: int) -> str:
    return " ".join(str(raw or "").split())[:limit]


def clean_date(raw: Any) -> str:
    text = str(raw or "")
    if not _DATE.match(text):
        raise RpcError("Esa fecha no es válida.")
    try:
        date.fromisoformat(text)
    except ValueError:
        raise RpcError("Esa fecha no es válida.") from None
    return text


def clean_time(raw: Any) -> str:
    """«HH:MM» or "" (no hour given); «24:00» means the end of the day."""
    text = str(raw or "").strip()
    if text == "24:00":
        return text
    return text if _TIME.match(text) else ""


def clean_offset(raw: Any) -> int:
    """Minutes ahead of UTC (Madrid in summer: 120), within what the world uses."""
    try:
        return max(-14 * 60, min(14 * 60, int(raw)))
    except (TypeError, ValueError):
        return 0


def clean_day(raw: Any) -> dict:
    if not isinstance(raw, dict) or raw.get("a") not in ANSWERS:
        raise RpcError("Di si puedes, quizá o no.")
    start, end = clean_time(raw.get("from")), clean_time(raw.get("to"))
    if start and end and end <= start:
        raise RpcError("La hora de fin tiene que ir después de la de inicio.")
    if raw["a"] == "no":
        start = end = ""
    return {"a": raw["a"], "from": start, "to": end, "note": _text(raw.get("note"), DAY_NOTE)}


class AgendaBook:
    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.people: dict[str, dict] = {}
        self.polls: list[dict] = []
        if path is not None and path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                self.people = {str(k): v for k, v in (raw.get("people") or {}).items() if isinstance(v, dict)}
                self.polls = [p for p in (raw.get("polls") or []) if isinstance(p, dict) and p.get("id")]
            except (OSError, ValueError, AttributeError):
                log.warning("could not read %s", path)

    def save(self) -> None:
        if self.path is None:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"people": self.people, "polls": self.polls}, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            log.warning("could not save %s", self.path)

    # ---- one person ------------------------------------------------------------------------------------
    def _entry(self, user_id: int, name: str) -> dict:
        old = self.people.get(str(user_id)) or {}
        return {"name": _text(name, 60) or old.get("name") or "Alguien", "week": old.get("week") or "0" * HOURS,
                "note": old.get("note", ""), "tz": old.get("tz", ""), "offset": old.get("offset", 0),
                "tzManual": bool(old.get("tzManual")), "days": dict(old.get("days") or {}), "updated": int(time.time() * 1000)}

    def _keep(self, user_id: int, entry: dict, today: str | None = None) -> dict:
        try:
            base = date.fromisoformat(str(today)) if today else date.today()
        except ValueError:
            base = date.today()
        cutoff = (base - timedelta(days=2)).isoformat()
        entry["days"] = {k: v for k, v in sorted(entry["days"].items()) if k >= cutoff}     # the past goes
        if entry["week"] == "0" * HOURS and not entry["note"] and not entry["days"] and not entry["tzManual"]:
            self.people.pop(str(user_id), None)                          # nothing marked: forget the person
        else:
            self.people[str(user_id)] = entry
        self.save()
        return entry

    # ---- the week ---------------------------------------------------------------------------------------
    def set_week(self, user_id: int, name: str, week: Any, note: Any = "", tz: Any = "", offset: Any = None) -> dict:
        entry = self._entry(user_id, name)
        entry["week"], entry["note"] = clean_week(week), _text(note, 200)
        self._device(entry, tz, offset)
        return self._keep(user_id, entry)

    @staticmethod
    def _device(entry: dict, tz: Any, offset: Any) -> None:
        """The browser's zone, unless they chose one by hand."""
        if tz and not entry["tzManual"]:
            entry["tz"] = _text(tz, 60)
            if offset is not None:
                entry["offset"] = clean_offset(offset)

    def set_zone(self, user_id: int, name: str, tz: Any, offset: Any, manual: Any = True) -> dict:
        """The time zone the player picked by hand (manual) or the browser's again (not manual)."""
        entry = self._entry(user_id, name)
        entry["tz"], entry["offset"], entry["tzManual"] = _text(tz, 60), clean_offset(offset), bool(manual)
        return self._keep(user_id, entry)

    # ---- the calendar ------------------------------------------------------------------------------------
    def set_day(self, user_id: int, name: str, day: Any, value: Any, today: str | None = None, tz: Any = "", offset: Any = None) -> dict:
        """Mark one concrete date (in the player's own calendar), or clear it with `value` None."""
        key = clean_date(day)
        entry = self._entry(user_id, name)
        self._device(entry, tz, offset)
        if value is None:
            entry["days"].pop(key, None)
        else:
            if key not in entry["days"] and len(entry["days"]) >= MAX_DAYS:
                raise RpcError(f"Puedes marcar hasta {MAX_DAYS} días: quita alguno.")
            entry["days"][key] = clean_day(value)
        return self._keep(user_id, entry, today)

    # ---- polls --------------------------------------------------------------------------------------------
    def poll(self, poll_id: str) -> dict:
        for p in self.polls:
            if p["id"] == poll_id:
                return p
        raise RpcError("Esa votación ya no existe.")

    def propose(self, by: str, title: Any, options: Any, minutes: Any = 120, note: Any = "", now_ms: int | None = None) -> dict:
        now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
        if not isinstance(options, list):
            raise RpcError("Faltan las fechas.")
        stamps = sorted({int(x) for x in options if isinstance(x, (int, float)) and now_ms - DAY_MS < int(x) < now_ms + 400 * DAY_MS})
        if not stamps:
            raise RpcError("Pon al menos una fecha (de hoy en adelante).")
        if len(stamps) > MAX_OPTIONS:
            raise RpcError(f"Como mucho {MAX_OPTIONS} fechas por votación.")
        try:
            minutes = max(15, min(12 * 60, int(minutes)))
        except (TypeError, ValueError):
            minutes = 120
        poll = {"id": uuid.uuid4().hex[:10], "title": _text(title, 80) or "Próximo evento", "note": _text(note, 300),
                "minutes": minutes, "options": [{"id": uuid.uuid4().hex[:8], "at": at} for at in stamps],
                "votes": {}, "names": {}, "open": True, "chosen": None, "by": _text(by, 60), "created": now_ms}
        self.polls.insert(0, poll)
        del self.polls[MAX_POLLS:]
        self.save()
        return poll

    def vote(self, poll_id: str, user_id: int, name: str, answers: Any) -> dict:
        poll = self.poll(poll_id)
        if not poll.get("open"):
            raise RpcError("Esa votación ya está cerrada.")
        if not isinstance(answers, dict):
            raise RpcError("Respuesta inválida.")
        ids = {o["id"] for o in poll["options"]}
        mine = {k: v for k, v in answers.items() if k in ids and v in ANSWERS}
        if mine:
            poll["votes"][str(user_id)] = mine
            poll["names"][str(user_id)] = _text(name, 60) or "Alguien"
        else:
            poll["votes"].pop(str(user_id), None)
            poll["names"].pop(str(user_id), None)
        self.save()
        return poll

    def close(self, poll_id: str, option_id: Any) -> dict:
        """Pick the winning date (or None to reopen the poll)."""
        poll = self.poll(poll_id)
        if option_id is None:
            poll["open"], poll["chosen"] = True, None
        else:
            if option_id not in {o["id"] for o in poll["options"]}:
                raise RpcError("Esa fecha no está en la votación.")
            poll["open"], poll["chosen"] = False, option_id
        self.save()
        return poll

    def delete(self, poll_id: str) -> None:
        self.poll(poll_id)
        self.polls = [p for p in self.polls if p["id"] != poll_id]
        self.save()

    def next_event(self, now_ms: int | None = None) -> dict | None:
        """The soonest chosen date that has not ended yet."""
        now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
        best = None
        for p in self.polls:
            if not p.get("chosen"):
                continue
            at = next((o["at"] for o in p["options"] if o["id"] == p["chosen"]), None)
            if at is not None and at + p.get("minutes", 120) * 60_000 > now_ms and (best is None or at < best["at"]):
                best = {"poll": p["id"], "title": p["title"], "at": at, "minutes": p.get("minutes", 120)}
        return best

    def public(self, me: int) -> dict:
        return {
            "people": [{"id": k, **v} for k, v in sorted(self.people.items(), key=lambda kv: kv[1].get("name", "").lower())],
            "polls": self.polls,
            "me": str(me),
            "next": self.next_event(),
        }


class AgendaRpc:
    """Mixed into ActivityBridge; relies on `self.agenda` (AgendaBook), `self.hub`, `self._gm`, `self.gm.log`, `self.conn_access`."""

    async def _agenda_changed(self) -> None:
        await self.hub.broadcast({"t": "agenda", "next": self.agenda.next_event()})

    async def _agenda_state(self, conn: Conn) -> dict:
        state = self.agenda.public(conn.user_id)
        perms, _host = await self.conn_access(conn)
        state["canEdit"] = "schedule" in perms
        return state

    async def rpc_agenda_get(self, conn: Conn, args: dict):
        return await self._agenda_state(conn)

    async def rpc_agenda_week(self, conn: Conn, args: dict):
        self.agenda.set_week(conn.user_id, conn.name, args.get("week"), args.get("note"), args.get("tz"), args.get("offset"))
        await self._agenda_changed()
        return await self._agenda_state(conn)

    async def rpc_agenda_day(self, conn: Conn, args: dict):
        self.agenda.set_day(conn.user_id, conn.name, args.get("date"), args.get("day"), args.get("today"),
                             args.get("tz"), args.get("offset"))
        await self._agenda_changed()
        return await self._agenda_state(conn)

    async def rpc_agenda_zone(self, conn: Conn, args: dict):
        self.agenda.set_zone(conn.user_id, conn.name, args.get("tz"), args.get("offset"), args.get("manual", True))
        await self._agenda_changed()
        return await self._agenda_state(conn)

    async def rpc_agenda_vote(self, conn: Conn, args: dict):
        self.agenda.vote(str(args.get("poll") or ""), conn.user_id, conn.name, args.get("answers"))
        await self._agenda_changed()
        return await self._agenda_state(conn)

    async def rpc_gm_schedule_propose(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        poll = self.agenda.propose(conn.name, args.get("title"), args.get("options"), args.get("minutes", 120), args.get("note"))
        self.gm.log.add(actor, f"Abrió la votación de fechas «{poll['title']}» ({len(poll['options'])} fechas)")
        await self._agenda_changed()
        return await self._agenda_state(conn)

    async def rpc_gm_schedule_close(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        poll = self.agenda.close(str(args.get("poll") or ""), args.get("option"))
        self.gm.log.add(actor, f"Eligió la fecha de «{poll['title']}»" if poll["chosen"] else f"Reabrió la votación «{poll['title']}»")
        await self._agenda_changed()
        return await self._agenda_state(conn)

    async def rpc_gm_schedule_delete(self, conn: Conn, args: dict):
        actor = await self._gm(conn)
        poll = self.agenda.poll(str(args.get("poll") or ""))
        self.agenda.delete(poll["id"])
        self.gm.log.add(actor, f"Borró la votación de fechas «{poll['title']}»")
        await self._agenda_changed()
        return await self._agenda_state(conn)
