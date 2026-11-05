"""What is happening in the event, as plain data for the desktop window: read from the bot's own tables (never changing them), from the
window's thread while the bot's thread keeps working."""

from __future__ import annotations

import logging
from typing import Any

from .activity.gm import GmPanel

log = logging.getLogger("eventos_app")

MAX_PLAYERS = 40


def _names(app: Any, ids: list[int]) -> dict[int, tuple[str, str | None]]:
    """The server's nickname of each person the bot can see right now (no questions asked to Discord)."""
    try:
        guild = app.resolve_event_guild()
    except Exception:  # noqa: BLE001 - not connected yet
        guild = None
    out: dict[int, tuple[str, str | None]] = {}
    for uid in ids:
        member = guild.get_member(uid) if guild is not None else None
        name = getattr(member, "display_name", None) or getattr(member, "name", None)
        out[uid] = (str(name) if name else f"Jugador …{str(uid)[-4:]}", None)
    return out


def event_snapshot(app: Any, online: set[int] | None = None) -> dict:
    """The live state of the event: the fight, the boss, the QTEs and every person with health, the most hurt first.
    `online` are the people inside the Activity right now. An empty dict when the bot has nothing to say yet."""
    if app is None:
        return {}
    panel = GmPanel(app)
    for _ in range(3):                                  # the bot's thread may change a table while it is being read: ask again
        try:
            state = panel.state()
            ids = [uid for uid in panel.player_ids() if uid in (getattr(app, "player_hp", {}) or {})]
            rows = panel.rows(_names(app, ids), online or set())
            break
        except RuntimeError:
            continue
        except Exception:  # noqa: BLE001 - a half-built bot or odd data must never break the window
            log.debug("could not read the event state", exc_info=True)
            return {}
    else:
        return {}
    players = [row for row in rows if row["hp"] is not None]
    players.sort(key=lambda r: ((r["hp"]["current"] / r["hp"]["max"]) if r["hp"]["max"] else 1.0, r["name"].lower()))
    state["players"] = [{"id": r["id"], "name": r["name"], "hp": r["hp"]["current"], "max": r["hp"]["max"], "alive": r["hp"]["alive"],
                         "revenge": r["hp"]["revenge"], "afk": r["afk"], "online": r["online"], "charges": r["charges"]}
                        for r in players[:MAX_PLAYERS]]
    state["playerCount"] = len(players)
    return state
