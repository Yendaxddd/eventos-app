"""How much traffic can the event channel take, and how many players is that?

Discord limits each bot separately, so every extra bot adds the same capacity. For one bot in one channel:

* messages: 5 per ~5 s window (we plan with a 5.3 s window for network jitter) -> ~57 per minute;
* reactions: Discord says 1 per 250 ms, but real runs got 429s at 270 ms; the app plans 350 ms and learns the
  spacing each bot really needs (the performance test feeds the learned value in) -> ~3 per second;
* edits of messages: the same 5 per window, shared by every message edited in that channel.

A *burst* (a group QTE where everybody answers within a couple of seconds) is limited by how many of those
slots fall inside the time you are willing to wait for the last answer ("deadline"). Beyond that, the
excess is queued, not lost, and shows up late. Pure functions: the performance test feeds in what it measured.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .multibot import CHANNEL_LIMIT, REACTION_SPACING, WINDOW_SECONDS


@dataclass
class Capacity:
    bots: int
    deadline: float
    rtt: float
    messages_in_deadline: int      # messages that can go out within the deadline, with no queueing
    reactions_in_deadline: int
    edits_in_deadline: int
    messages_per_minute: float     # sustained, whole channel
    reactions_per_minute: float
    players: int                   # simultaneous players that fit in the deadline
    limiting: str                  # what runs out first: "mensajes", "reacciones" or "ediciones"

    def as_dict(self) -> dict:
        return asdict(self)


def capacity(bots: int, *, deadline: float = 3.0, rtt: float = 0.12, messages_per_player: float = 1.0,
             reactions_per_player: float = 1.0, edits_per_player: float = 1.0, limit: int = CHANNEL_LIMIT,
             window: float = WINDOW_SECONDS, spacing: float = REACTION_SPACING) -> Capacity:
    """Simultaneous players that can each get `messages_per_player` messages, `reactions_per_player`
    reactions and `edits_per_player` HP-bar edits within `deadline` seconds, with `bots` bots in the pool.

    The defaults are deliberately pessimistic: in practice most replies need a reaction and only failures
    or counters need a message.
    """
    bots = max(1, bots)
    usable = max(0.0, deadline - rtt)
    messages = bots * limit * (1 + int(usable // window))
    reactions = bots * (1 + int(usable // spacing))
    edits = messages
    limits = {
        "mensajes": messages / messages_per_player if messages_per_player else float("inf"),
        "reacciones": reactions / reactions_per_player if reactions_per_player else float("inf"),
        "ediciones": edits / edits_per_player if edits_per_player else float("inf"),
    }
    limiting = min(limits, key=limits.get)
    return Capacity(
        bots=bots, deadline=deadline, rtt=rtt, messages_in_deadline=messages, reactions_in_deadline=reactions,
        edits_in_deadline=edits, messages_per_minute=bots * limit * 60.0 / window, reactions_per_minute=bots * 60.0 / spacing,
        players=int(limits[limiting]), limiting=limiting,
    )


def table(max_bots: int = 8, deadlines: tuple[float, ...] = (2.0, 3.0, 5.0), **kwargs) -> list[dict]:
    """Rows for the docs / the report: players per number of bots and deadline."""
    rows = []
    for bots in range(1, max_bots + 1):
        row = {"bots": bots}
        base = capacity(bots, **kwargs)
        row["messages_per_minute"] = round(base.messages_per_minute)
        for deadline in deadlines:
            row[f"players_{deadline:g}s"] = capacity(bots, deadline=deadline, **kwargs).players
        rows.append(row)
    return rows
