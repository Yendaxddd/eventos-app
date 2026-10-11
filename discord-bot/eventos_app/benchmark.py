"""Performance test for the event channel, meant to be run from the app with the real bots.

It posts short test messages (and reactions) in the event channel, times them, and deletes everything at
the end. It goes through the same routes the bot uses during an event, so what it measures is what the
players get. Nothing here needs a window: the app shows the report.
"""

from __future__ import annotations

import asyncio
import logging
import statistics
import time
from typing import Callable

import discord

from . import capacity as capacity_model
from .multibot import SenderPool, _plain_params

EMOJIS = ["✅", "❌", "⭐", "❗", "🔥", "⚡", "🎯", "🛡️", "💚", "🔒"]

PROFILES = {
    # name: (rtt samples per bot, extra messages per bot beyond one window, reactions per bot, sustained seconds)
    "rapida": {"rtt_samples": 3, "overflow_per_bot": 2, "reactions_per_bot": 8, "sustained_seconds": 0.0},
    "completa": {"rtt_samples": 5, "overflow_per_bot": 3, "reactions_per_bot": 12, "sustained_seconds": 25.0},
}
MAX_MESSAGES = 150  # never flood the channel, whatever the number of bots


class _RateLimitCounter(logging.Handler):
    """discord.py logs a warning each time Discord answers 429."""

    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.count = 0

    def emit(self, record: logging.LogRecord) -> None:
        if "rate limited" in record.getMessage().lower():
            self.count += 1


def _ms(seconds: float) -> int:
    return round(seconds * 1000)


def _spread(samples: list[float]) -> dict:
    if not samples:
        return {"first_ms": 0, "median_ms": 0, "p95_ms": 0, "last_ms": 0}
    ordered = sorted(samples)
    return {"first_ms": _ms(ordered[0]), "median_ms": _ms(statistics.median(ordered)),
            "p95_ms": _ms(ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))]), "last_ms": _ms(ordered[-1])}


async def run(pool: SenderPool, channel_id: int, *, profile: str = "rapida", say: Callable[[str], None] = print,
              stop: asyncio.Event | None = None, max_rate_limits: int = 12, **overrides) -> dict:
    """Run the test and return a report dict (see `format_report`). `overrides` replace profile values."""
    cfg = {**PROFILES[profile], **overrides}
    senders = [s for s in pool._all() if s.ready]
    bots = len(senders)
    limit, window = pool.limits["send"]
    counter = _RateLimitCounter()
    logging.getLogger("discord.http").addHandler(counter)
    created: list[int] = []
    report: dict = {"profile": profile, "channel_id": channel_id, "bots": bots, "senders": [], "bursts": [],
                    "reactions": None, "sustained": None, "aborted": ""}

    def should_stop() -> bool:
        if stop is not None and stop.is_set():
            report["aborted"] = "cancelada"
            return True
        if counter.count > max_rate_limits:
            report["aborted"] = f"demasiados límites de Discord ({counter.count}); se detuvo para no insistir"
            return True
        return False

    try:
        # 1. each bot on its own: how long does one message / one reaction take when nothing else is going on?
        say(f"1/4 Latencia de cada bot ({bots})…")
        for sender in senders:
            entry = {"name": sender.name, "rtt_ms": 0, "reaction_ms": 0, "error": ""}
            ids, times = [], []
            try:
                for i in range(cfg["rtt_samples"]):
                    started = time.perf_counter()
                    data = await sender.endpoints.send_message(
                        channel_id, params=_plain_params(f"🧪 latencia {sender.name} {i + 1} (se borra sola)"))
                    times.append(time.perf_counter() - started)
                    sender.reserve("send", channel_id, time.monotonic())  # direct call: tell the pool the slot is used
                    ids.append(int(data["id"]))
                started = time.perf_counter()
                await sender.endpoints.add_reaction(channel_id, ids[0], "⭐")
                entry["reaction_ms"] = _ms(time.perf_counter() - started)
                sender.reserve("react", channel_id, time.monotonic())
                entry["rtt_ms"] = _ms(statistics.median(times))
            except (discord.Forbidden, discord.NotFound):
                entry["error"] = "no puede escribir en el canal"
            except discord.HTTPException as exc:
                entry["error"] = f"Discord respondió {exc.status}"
            created.extend(ids)
            report["senders"].append(entry)
            say(f"   {sender.name}: " + (f"mensaje {entry['rtt_ms']} ms, reacción {entry['reaction_ms']} ms"
                                         if not entry["error"] else entry["error"]))
            if should_stop():
                return report
        usable = [e for e in report["senders"] if not e["error"]]
        if not usable:
            report["aborted"] = "ningún bot puede escribir en el canal"
            return report

        # 2. bursts: everyone answers at once
        sizes = [min(MAX_MESSAGES // 2, len(usable) * limit),
                 min(MAX_MESSAGES // 2, len(usable) * (limit + cfg["overflow_per_bot"]))]
        burst_ids: list[int] = []
        for number, size in enumerate(sizes, start=1):
            say(f"2/4 Ráfaga {number}: {size} mensajes a la vez…")
            started = time.perf_counter()
            done: list[float] = []

            async def one(i: int, size=size, started=started) -> None:
                data = await pool.send_text(channel_id, f"🧪 ráfaga {i + 1}/{size} (se borra sola)")
                done.append(time.perf_counter() - started)
                created.append(int(data["id"]))
                burst_ids.append(int(data["id"]))

            await asyncio.gather(*(one(i) for i in range(size)))
            spread = {"size": size, **_spread(done)}
            report["bursts"].append(spread)
            say(f"   primero {spread['first_ms']} ms · mediana {spread['median_ms']} ms · último {spread['last_ms']} ms")
            if should_stop():
                return report
            if number < len(sizes):
                await asyncio.sleep(window + 0.3)  # let every bot's window reset before the next burst

        # 3. reactions (✅/❌ under every reply)
        count = min(60, len(usable) * cfg["reactions_per_bot"], len(burst_ids) * len(EMOJIS))
        say(f"3/4 {count} reacciones a la vez…")
        started = time.perf_counter()
        done = []

        async def react(i: int) -> None:
            await pool.add_reaction(channel_id, burst_ids[i % len(burst_ids)], EMOJIS[(i // len(burst_ids)) % len(EMOJIS)])
            done.append(time.perf_counter() - started)

        await asyncio.gather(*(react(i) for i in range(count)))
        report["reactions"] = {"count": count, **_spread(done)}
        say(f"   mediana {report['reactions']['median_ms']} ms · última {report['reactions']['last_ms']} ms")
        if should_stop():
            return report

        # 4. sustained: the most the channel takes minute after minute
        seconds = cfg["sustained_seconds"]
        if seconds:
            say(f"4/4 Ritmo sostenido durante {seconds:g} s…")
            end = time.perf_counter() + seconds
            stamps: list[float] = []
            begin = time.perf_counter()

            async def worker() -> None:
                while time.perf_counter() < end and not should_stop() and len(created) < MAX_MESSAGES * 2:
                    data = await pool.send_text(channel_id, "🧪 ritmo sostenido (se borra sola)")
                    created.append(int(data["id"]))
                    stamps.append(time.perf_counter() - begin)

            await asyncio.gather(*(worker() for _ in range(max(2, len(usable) * 2))))
            steady = [t for t in stamps if t >= window]  # after the first window, whose burst doesn't repeat
            span = max(1e-6, (stamps[-1] if stamps else seconds) - window)
            per_minute = len(steady) / span * 60 if steady and span > 1 else len(stamps) / seconds * 60
            report["sustained"] = {"seconds": seconds, "messages": len(stamps), "per_minute": round(per_minute),
                                   "per_bot_per_minute": round(per_minute / len(usable))}
            say(f"   {len(stamps)} mensajes · ritmo estable ≈ {round(per_minute)} por minuto")
    finally:
        logging.getLogger("discord.http").removeHandler(counter)
        say("Borrando los mensajes de prueba…")
        gate = asyncio.Semaphore(6)

        async def remove(mid: int) -> None:
            async with gate:
                try:
                    await pool.delete_message(channel_id, mid)
                except Exception:  # noqa: BLE001 - already gone or not ours: nothing to clean
                    pass

        await asyncio.gather(*(remove(m) for m in created))

    report["rate_limits"] = counter.count
    report["held_back"] = sum(s["held_back"] for s in pool.snapshot())
    rtt = statistics.median([e["rtt_ms"] for e in usable]) / 1000 or 0.12
    report["capacity"] = {
        f"{d:g}": capacity_model.capacity(len(usable), deadline=d, rtt=rtt, limit=limit, window=window,
                                          spacing=pool.limits["react"][1]).as_dict() for d in (2.0, 3.0, 5.0)}
    return report


def format_report(report: dict) -> list[str]:
    """Spanish lines for the log panel / a text file."""
    lines = [f"PRUEBA DE RENDIMIENTO · {report['bots']} bot{'s' if report['bots'] != 1 else ''} "
             f"· prueba {report['profile']}"]
    if report.get("aborted"):
        lines.append(f"⚠ Se detuvo: {report['aborted']}")
    for entry in report["senders"]:
        lines.append(f"  {entry['name']}: " + (f"mensaje {entry['rtt_ms']} ms · reacción {entry['reaction_ms']} ms"
                                              if not entry["error"] else f"✗ {entry['error']}"))
    for burst in report["bursts"]:
        lines.append(f"  Ráfaga de {burst['size']} mensajes: primero {burst['first_ms']} ms, mediana "
                     f"{burst['median_ms']} ms, último {burst['last_ms']} ms")
    if report.get("reactions"):
        r = report["reactions"]
        lines.append(f"  {r['count']} reacciones a la vez: mediana {r['median_ms']} ms, última {r['last_ms']} ms")
    if report.get("sustained"):
        s = report["sustained"]
        lines.append(f"  Ritmo sostenido: ≈ {s['per_minute']} mensajes por minuto en total "
                     f"(≈ {s['per_bot_per_minute']} por bot)")
    if "rate_limits" in report:
        lines.append(f"  Límites de Discord (429) encontrados: {report['rate_limits']} · envíos frenados: {report['held_back']}")
    if report.get("capacity"):
        c3 = report["capacity"]["3"]
        lines.append("  Capacidad estimada (jugadores respondiendo a la vez y viendo todo su resultado a tiempo):")
        for deadline, c in report["capacity"].items():
            lines.append(f"    en {deadline} s: ≈ {c['players']} jugadores (límite: {c['limiting']})")
        lines.append(f"  Ritmo máximo: ≈ {round(c3['messages_per_minute'])} mensajes y ≈ {round(c3['reactions_per_minute'])} "
                     f"reacciones por minuto en el canal.")
        per_bot = capacity_model.capacity(1, deadline=3.0, rtt=c3["rtt"]).players
        lines.append(f"  Cada bot auxiliar que agregues suma ≈ {per_bot} jugadores simultáneos.")
    return lines
