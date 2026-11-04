"""Who is on the game-master team and what each of them may do.

Before this, being a game master was all or nothing: whoever had the bot's admin role could do everything. Now each permission is a
box (launch QTEs, run the boss, touch players, write cinematics, put up results...) and the host decides who has which:

    host        the one running the event: the guild's owner, whoever the host names as co-host, and the desktop app's own window.
                Always has every box, including `staff` (deciding the others' boxes).
    people      one person, by Discord id: their boxes replace anything their roles would give them (so one admin can be limited)
    roles       a Discord role: everybody with it gets those boxes (added together over all their roles)
    admins      what the bot's admin role gives when nobody wrote anything more precise (by default: everything but `staff`)

A preset is just a named set of boxes the panel offers to fill them in one click. The server checks the box on every request
(`gm_rpc._gm`), so a page that shows a button it should not is harmless.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from .hub import RpcError

log = logging.getLogger("eventos_app.activity")

# (id, label, what it allows) — the order is the order the panel shows them in
PERMS: tuple[tuple[str, str, str], ...] = (
    ("event", "Evento y QTE", "Lanzar QTE y tandas, empezar y terminar el combate, checkpoints, modo de los QTE automáticos."),
    ("boss", "Jefe", "Registrar, hacer aparecer y controlar al jefe: vida, habilidades, dominio e imágenes."),
    ("mobs", "Mini enemigos", "El bestiario y los enemigos en el campo."),
    ("players", "Jugadores", "Vida, cargas, puntos, logros, objetos y apoyo de cada jugador."),
    ("values", "Valores del juego", "Los números del juego y los tiempos y daño de cada dificultad."),
    ("content", "Contenido", "Logros, objetos, poderes, árboles de habilidades y traducciones."),
    ("cinema", "Crear cinemáticas", "Escribir sus propias cinemáticas (privadas hasta que las compartan)."),
    ("stage", "Dirigir en vivo", "Poner cinemáticas, música, sonidos y efectos para todos durante el evento."),
    ("media", "Biblioteca de audio y efectos", "Subir sonidos y música, y ajustar los avisos y efectos automáticos."),
    ("results", "Resultados", "Mostrar y editar la pantalla de resultados después de cada capítulo, jefe o decisión."),
    ("summary", "Resúmenes", "Crear resúmenes del evento (con IA) de un tramo de mensajes y publicarlos."),
    ("schedule", "Agenda", "Proponer fechas para el evento y ver la disponibilidad de todos."),
    ("requests", "Solicitudes", "Aprobar o rechazar las cinemáticas que los jugadores piden para sus poderes y acciones."),
    ("history", "Historial", "Ver quién hizo qué en el panel."),
    ("staff", "Equipo de GM", "Decidir quién es game master y qué puede hacer cada uno."),
)
PERM_IDS = tuple(p[0] for p in PERMS)
ALL_BUT_STAFF = tuple(p for p in PERM_IDS if p != "staff")

PRESETS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "full": ("GM total", "Todo menos decidir los permisos de los demás.", ALL_BUT_STAFF),
    "cohost": ("Coanfitrión", "Todo, también el equipo de GM.", PERM_IDS),
    "narrator": ("Narrador", "Cuenta la historia: cinemáticas, música, efectos, resultados y resúmenes.",
                 ("cinema", "stage", "media", "results", "summary", "requests", "history")),
    "combat": ("Ayudante de combate", "Lleva la pelea: QTE, jefe, enemigos y la vida de los jugadores.",
               ("event", "boss", "mobs", "players", "stage", "history")),
    "moderator": ("Moderador", "Cuida a la gente: jugadores, resultados, agenda y el historial.",
                  ("players", "results", "schedule", "summary", "history")),
    "none": ("Sin permisos", "No es game master.", ()),
}

# which box each request of the panel needs; a request that is not here needs only to be on the team (any box)
OP_PERMS: dict[str, str] = {}
for _perm, _ops in {
    "event": "launch batch fight checkpoint sync qte_mode",
    "boss": "boss boss_config boss_hp boss_mode boss_register boss_remove boss_spawn ability_remove ability_save ability_use "
            "domain_clear domain_expand domain_save gif_add gif_remove",
    "mobs": "mobs mob_delete mob_hp mob_pause mob_remove mob_save mob_spawn",
    "players": "players player hp hp_reset charges cooldowns points skills_reset support slots ach_give ach_remove obj_give obj_take obj_spins afk",
    "values": "values value_set qte_set",
    "content": "data file_create file_delete file_get file_restore file_save achievements ach_save ach_delete objects object object_save "
               "object_image obj_approve obj_reject obj_reload powers",
    "cinema": "cinemas cinema_save cinema_delete cinema_duplicate cinema_link cinema_auto",
    "stage": "cinema_play cinema_stop audio_play audio_stop music_play music_stop cue_test look look_set",
    "media": "audio audio_delete audio_update cue_set cue_clear phase_set phase_clear music_volume fx fx_set fx_clear fx_defaults fx_preview",
    "results": "results results_build results_show results_hide results_save results_delete results_auto results_reset",
    "summary": "summary summary_make summary_save summary_delete summary_post ai_get ai_set ai_test",
    "schedule": "schedule_propose schedule_close schedule_delete",
    "requests": "requests request_decide",
    "history": "history",
    "staff": "staff staff_set staff_remove staff_admins",
}.items():
    for _op in _ops.split():
        OP_PERMS["gm." + _op] = _perm
# the cinematics list is also what a director needs to play one: either box opens it (what is inside stays sealed, see cinema_rpc)
SHARED_OPS = {"gm.cinemas": ("cinema", "stage"), "gm.cinema_link": ("cinema", "stage")}

_ID = re.compile(r"^\d{1,20}$")


def clean_perms(raw: Any) -> list[str]:
    if not isinstance(raw, (list, tuple)):
        return []
    return [p for p in PERM_IDS if p in raw]


def preset_of(perms: list[str]) -> str:
    """The preset these boxes are exactly, or 'custom'."""
    have = set(perms)
    for key, (_label, _hint, boxes) in PRESETS.items():
        if have == set(boxes):
            return key
    return "custom"


class StaffBook:
    """The team, in one JSON file (data/gm_staff.json)."""

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.people: dict[str, dict] = {}       # id -> {"name", "perms"}
        self.roles: dict[str, dict] = {}        # role id -> {"name", "perms"}
        self.admins: list[str] = list(ALL_BUT_STAFF)
        self.hosts: dict[str, str] = {}         # co-hosts: id -> name
        self._load()

    def _load(self) -> None:
        if self.path is None or not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            log.warning("could not read %s", self.path)
            return
        if not isinstance(raw, dict):
            return
        for key, target in (("people", self.people), ("roles", self.roles)):
            for ident, entry in (raw.get(key) or {}).items():
                if _ID.match(str(ident)) and isinstance(entry, dict):
                    target[str(ident)] = {"name": str(entry.get("name") or "")[:80], "perms": clean_perms(entry.get("perms"))}
        if isinstance(raw.get("admins"), list):
            self.admins = clean_perms(raw["admins"])
        for ident, name in (raw.get("hosts") or {}).items():
            if _ID.match(str(ident)):
                self.hosts[str(ident)] = str(name or "")[:80]

    def save(self) -> None:
        if self.path is None:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"people": self.people, "roles": self.roles, "admins": self.admins, "hosts": self.hosts},
                                      ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            log.warning("could not save %s", self.path)

    # ---- deciding -------------------------------------------------------------------------------------------------------------
    def resolve(self, user_id: int, role_ids: list[int], is_admin: bool, is_host: bool) -> tuple[list[str], bool]:
        """(the boxes this person has, whether they are a host)."""
        host = is_host or str(user_id) in self.hosts
        if host:
            return list(PERM_IDS), True
        person = self.people.get(str(user_id))
        if person is not None:
            return list(person["perms"]), False
        have: set[str] = set()
        for role in role_ids:
            entry = self.roles.get(str(role))
            if entry is not None:
                have.update(entry["perms"])
        if is_admin:
            have.update(self.admins)
        return [p for p in PERM_IDS if p in have], False

    # ---- changing -------------------------------------------------------------------------------------------------------------
    def set_entry(self, kind: str, ident: Any, name: Any, perms: Any) -> dict:
        ident = str(ident or "").strip()
        if not _ID.match(ident):
            raise RpcError("Falta elegir a la persona o el rol.")
        boxes = clean_perms(perms)
        if kind == "host":
            self.hosts[ident] = str(name or "")[:80]
            self.people.pop(ident, None)
        elif kind == "person":
            self.people[ident] = {"name": str(name or "")[:80], "perms": boxes}
            self.hosts.pop(ident, None)
        elif kind == "role":
            self.roles[ident] = {"name": str(name or "")[:80], "perms": boxes}
        else:
            raise RpcError("Eso no se puede guardar en el equipo.")
        self.save()
        return {"id": ident, "perms": boxes}

    def remove(self, kind: str, ident: Any) -> bool:
        ident = str(ident or "")
        table = {"person": self.people, "role": self.roles, "host": self.hosts}.get(kind)
        if table is None or ident not in table:
            raise RpcError("Esa entrada ya no está en el equipo.")
        table.pop(ident)
        self.save()
        return True

    def set_admins(self, perms: Any) -> list[str]:
        self.admins = clean_perms(perms)
        self.save()
        return list(self.admins)

    def public(self) -> dict:
        return {"people": [{"id": k, **v, "preset": preset_of(v["perms"])} for k, v in self.people.items()],
                "roles": [{"id": k, **v, "preset": preset_of(v["perms"])} for k, v in self.roles.items()],
                "hosts": [{"id": k, "name": v} for k, v in self.hosts.items()],
                "admins": {"perms": list(self.admins), "preset": preset_of(self.admins)},
                "perms": [{"id": i, "label": label, "hint": hint} for i, label, hint in PERMS],
                "presets": [{"id": k, "label": label, "hint": hint, "perms": list(boxes)} for k, (label, hint, boxes) in PRESETS.items()]}
