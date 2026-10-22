"""What a character's power does in a fight: its effect string, read, checked, described and worked out.

A power's `effect` is one or more parts joined by ";" (at most MAX_PARTS), each `kind[:number[:number]]`:

    damage:N              N damage to the boss (the attacker's weapon and damage boosts count; capped by the game's maximum)
    damage_all:N          the same to the boss, and N to every mini enemy on the field
    heal:N                N HP to whoever uses it              heal_team:N   N HP to every player still standing
    shield:P:S            P % less damage taken for S seconds  shield_team:P:S  the same for everybody
    stun / stun:S         the boss is stunned for S seconds (3 by default; the GM's hotkeys and the mini enemies wait)
    buff:TYPE:P:S         +P % of damage_boost or bf_boost for S seconds (0 seconds: the next hit only)
    charge_team:P         P % of power charge to every other player
    cleanse / cleanse_team  bleeding, burning, poison, weakness, stun and curses are removed

The old forms keep working: `damage:50`, `heal:30`, `stun`, `buff:damage_boost:0.2:30` (a value of 1 or less is a fraction, 0.2 = 20 %).
Nothing here touches the bot: `plan()` says what to do with the numbers, the bot does it (apply_power_effect).
"""
from __future__ import annotations

import re
from typing import Any

MAX_PARTS = 4
MAX_AMOUNT = 100000
KINDS = ("damage", "damage_all", "heal", "heal_team", "shield", "shield_team", "stun", "buff", "charge_team", "cleanse", "cleanse_team")
BUFFS = ("damage_boost", "bf_boost")
_PART = re.compile(r"^([a-z_]{3,16})(?::([a-z_]{2,24}|\d{1,6}(?:\.\d{1,2})?))?(?::(\d{1,6}(?:\.\d{1,2})?))?(?::(\d{1,5}(?:\.\d{1,2})?))?$")


class PowerError(ValueError):
    """What is wrong with an effect, in words for the player (Spanish)."""


def _num(text: str | None, default: float) -> float:
    return default if text in (None, "") else float(text)


def parse(effect: Any) -> list[dict]:
    """The parts of an effect string, checked: [{kind, amount, seconds, buff}]. Raises PowerError."""
    raw = str(effect or "").strip().lower().replace(" ", "")
    if not raw:
        raise PowerError("Falta el efecto del poder.")
    pieces = [p for p in re.split(r"[;+]", raw) if p]
    if len(pieces) > MAX_PARTS:
        raise PowerError(f"Un poder puede tener hasta {MAX_PARTS} efectos.")
    out = []
    for piece in pieces:
        m = _PART.match(piece)
        if not m or m.group(1) not in KINDS:
            raise PowerError(f"«{piece}» no es un efecto válido.")
        kind, a, b, c = m.groups()
        if kind == "buff":
            if a not in BUFFS:
                raise PowerError("La mejora debe ser damage_boost (más daño) o bf_boost (más Black Flash).")
            value = _num(b, 10.0)
            percent = value * 100 if value <= 1 else value
            out.append({"kind": kind, "buff": a, "amount": min(percent, 300.0), "seconds": min(_num(c, 30.0), 600.0)})
            continue
        if a is not None and not re.fullmatch(r"\d+(\.\d+)?", a):
            raise PowerError(f"«{piece}»: el número del efecto no es válido.")
        if kind in ("cleanse", "cleanse_team"):
            out.append({"kind": kind, "amount": 0, "seconds": 0})
        elif kind == "stun":
            out.append({"kind": kind, "amount": 0, "seconds": max(0.5, min(_num(a, 3.0), 10.0))})
        elif kind in ("shield", "shield_team"):
            out.append({"kind": kind, "amount": max(1.0, min(_num(a, 30.0), 90.0)), "seconds": max(1.0, min(_num(b, 15.0), 300.0))})
        elif kind == "charge_team":
            out.append({"kind": kind, "amount": max(1.0, min(_num(a, 20.0), 100.0)), "seconds": 0})
        else:
            if a is None:
                raise PowerError(f"«{kind}» necesita una cantidad, por ejemplo {kind}:50.")
            out.append({"kind": kind, "amount": max(0.0, min(float(a), MAX_AMOUNT)), "seconds": 0})
    return out


def validate(effect: Any) -> str:
    """The effect written back in its tidy form (raises PowerError)."""
    return ";".join(compose(p) for p in parse(effect))


def compose(part: dict) -> str:
    n = lambda v: f"{v:g}"                       # noqa: E731 - 50.0 -> "50"
    kind = part["kind"]
    if kind == "buff":
        return f"buff:{part['buff']}:{n(part['amount'])}:{n(part['seconds'])}"
    if kind in ("cleanse", "cleanse_team"):
        return kind
    if kind == "stun":
        return f"stun:{n(part['seconds'])}"
    if kind in ("shield", "shield_team"):
        return f"shield{'_team' if kind.endswith('team') else ''}:{n(part['amount'])}:{n(part['seconds'])}"
    return f"{kind}:{n(part['amount'])}"


def damage_multiplier(weapon: float = 1.0, boost_percent: float = 0.0, revenge: bool = False) -> float:
    """What the attacker brings to a hit: their weapon, their damage boost, and revenge mode (+10 %)."""
    return max(0.0, float(weapon or 1.0)) * (1 + max(0.0, boost_percent) / 100.0) * (1.1 if revenge else 1.0)


def boss_damage(amount: float, multiplier: float, cap: float) -> int:
    return int(round(min(cap, max(0.0, amount) * multiplier)))


def describe(parts: list[dict], multiplier: float = 1.0, cap: float = 500) -> list[str]:
    """Each part in a short English sentence (the bot's language; the app translates it)."""
    lines = []
    for p in parts:
        k, a, s = p["kind"], p["amount"], p["seconds"]
        if k == "damage":
            lines.append(f"💥 {boss_damage(a, multiplier, cap)} damage to the boss")
        elif k == "damage_all":
            lines.append(f"💥 {boss_damage(a, multiplier, cap)} damage to the boss and {int(round(a * multiplier))} to every mini enemy")
        elif k == "heal":
            lines.append(f"💚 Heals {int(a)} HP")
        elif k == "heal_team":
            lines.append(f"💚 Heals {int(a)} HP to every player")
        elif k == "shield":
            lines.append(f"🛡️ {int(a)}% less damage for {int(s)} seconds")
        elif k == "shield_team":
            lines.append(f"🛡️ Everyone takes {int(a)}% less damage for {int(s)} seconds")
        elif k == "stun":
            lines.append(f"🌀 The boss is stunned for {s:g} seconds")
        elif k == "buff":
            what = "damage" if p["buff"] == "damage_boost" else "Black Flash chance"
            lines.append(f"✨ +{a:g}% {what} for {int(s)} seconds" if s else f"✨ +{a:g}% {what} on the next hit")
        elif k == "charge_team":
            lines.append(f"⚡ +{int(a)}% power charge to every other player")
        elif k == "cleanse":
            lines.append("🧼 Removes your harmful effects")
        elif k == "cleanse_team":
            lines.append("🧼 Removes everyone's harmful effects")
    return lines
