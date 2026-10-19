"""The QTE side of the Activity: tell the clients when a QTE starts and ends, and turn their button presses into
what the bot's chat handlers expect (a message), so the damage / HP logic stays exactly where it is."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable

log = logging.getLogger("eventos_app.activity")

COMMANDS = ("evade", "parry", "adapt", "attack")      # the buttons of this version
HUMAN_MIN_MS = 80.0                                    # nobody reacts faster than this: a smaller `dt` is a script
GRACE_MS = 150.0                                       # how far a claimed `dt` may exceed the real elapsed time


class QteBook(dict):
    """`active_qtes` of the bot, but it says when a QTE appears and when it disappears.

    The bot keeps using it as a plain dict (`book[id] = {...}`, `book.pop(id, None)`); nothing in its logic changes.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.on_start: Callable[[Any, dict], None] | None = None
        self.on_end: Callable[[Any, dict], None] | None = None

    def _fire(self, callback, key, data) -> None:
        if callback is not None:
            try:
                callback(key, data)
            except Exception:  # noqa: BLE001 - the Activity must never break the game
                log.exception("QTE listener failed")

    def __setitem__(self, key, value) -> None:
        fresh = key not in self
        super().__setitem__(key, value)
        if fresh:
            self._fire(self.on_start, key, value)

    def pop(self, key, *default):
        present = key in self
        value = super().pop(key, *default)
        if present:
            self._fire(self.on_end, key, value)
        return value

    def __delitem__(self, key) -> None:
        value = self[key]
        super().__delitem__(key)
        self._fire(self.on_end, key, value)


class CharacterAuthor:
    """The player's Member, but called by the name of the character they are playing as.

    The bot resolves who acts (powers, characters, Tupperbox) from `message.author.display_name` looked up in its
    character registry, so with this as the author a button or a typed command acts as that character."""

    def __init__(self, member, name: str) -> None:
        self._member = member
        self.display_name = name

    def __getattr__(self, attr):
        return getattr(self._member, attr)

    def __eq__(self, other):
        return other == self._member or other is self

    def __hash__(self):
        return hash(self._member)


class ActivityInput:
    """A button press dressed as the Discord message the bot's handlers know how to read.

    Only what they use: who wrote it, where, what, when, and a way to react to it (the reaction is kept so the
    Activity can show the verdict, and is put on the QTE message in the channel for those playing from the chat).
    """

    id = 0
    webhook_id = None
    attachments: tuple = ()
    embeds: tuple = ()
    mentions: tuple = ()
    reference = None
    stickers: tuple = ()
    pinned = False
    tts = False

    def __init__(self, member, channel, content: str, *, user_id: int, character: str | None = None,
                 created_at: datetime | None = None) -> None:
        self.author = CharacterAuthor(member, character) if character else member
        self.channel = channel
        self.guild = getattr(channel, "guild", None)
        self.content = content
        self.clean_content = content
        self.activity_user_id = user_id
        self.created_at = created_at or datetime.now(timezone.utc)
        self.reactions: list[str] = []
        self.mirror_to: Any = None           # the QTE message in the channel, to echo the verdict on it

    async def add_reaction(self, emoji) -> None:
        self.reactions.append(str(emoji))
        if self.mirror_to is not None:
            try:
                await self.mirror_to.add_reaction(emoji)
            except Exception:  # noqa: BLE001 - a missing reaction is only cosmetic
                pass

    async def reply(self, content=None, **kwargs):
        return await self.channel.send(content, **{k: v for k, v in kwargs.items() if k != "mention_author"})


def describe(qte_id, data: dict, times: dict, now_ms: float, *, timeouts: dict | None = None, bf_window: float = 0.0,
             adjust: Callable[[str, int], tuple[float, float]] | None = None) -> dict:
    """What a client needs to draw a QTE: who it is for, for how long, and the windows of the timing bar.

    `times`: the bot's `qte_times`; `timeouts`: its `qte_timeout_durations`; `bf_window`: its Black Flash tolerance;
    `adjust(difficulty, user_id)`: the parry window of a player (REVENGE mode moves and narrows it)."""
    difficulty = data.get("difficulty")
    timing = times.get(difficulty, {})
    target = None if data.get("mode") == "fake" else data.get("target")    # a fake QTE does not say who it is for
    evade = float(timing.get("evade_window", 5.0))
    parry = tuple(timing.get("parry_window") or (0.0, 0.0))
    if target is not None and adjust is not None:
        try:
            parry = tuple(adjust(difficulty, target.id))
        except Exception:  # noqa: BLE001 - the base window is a fine answer
            pass
    center = (parry[0] + parry[1]) / 2
    timeout = float((timeouts or {}).get(difficulty) or max(evade, parry[1]))
    windows = {"evade": [0.0, evade], "parry": [round(parry[0], 3), round(parry[1], 3)],
               "bf": [round(max(0.0, center - bf_window), 3), round(center + bf_window, 3)] if bf_window else None}
    return {
        "id": str(qte_id), "mode": data.get("mode", "single"), "difficulty": difficulty or "",
        "target": {"id": str(target.id), "name": getattr(target, "display_name", None) or target.name} if target else None,
        "participants": [str(p) for p in (data.get("participants") or {})],
        "tGo": now_ms, "timeout": timeout, "windows": windows if data.get("mode") in ("single", "group") else None,
        "commands": [c for c in COMMANDS if c != "attack"],
    }


def response_seconds(dt_ms: float, rtt_ms: float, elapsed_ms: float) -> float | None:
    """Seconds since the QTE started, from what the client measured. None when the claim is not credible.

    `dt_ms`: client clock between seeing the stimulus and pressing. The stimulus reached the client about
    `rtt/2` after the server sent it, so that is added back (a slow connection must not cost the player the QTE).
    A claim above the real elapsed time is trimmed to it, one below what a human can do is refused.
    """
    if dt_ms != dt_ms or dt_ms < HUMAN_MIN_MS or dt_ms > 120_000:       # NaN, a script, or nonsense
        return None
    rtt = max(0.0, min(rtt_ms, 5_000.0))
    claimed = dt_ms + rtt / 2.0
    return min(claimed, elapsed_ms + GRACE_MS) / 1000.0


