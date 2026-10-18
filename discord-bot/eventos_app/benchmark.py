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
from .diagnostics import KIND_NAMES, explain_429, short_name
from .multibot import SenderPool, _plain_params

log = logging.getLogger(__name__)

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
        self.count = 0      # 429 on anything but reactions: the pool should never cause these
        self.reactions = 0  # 429 on reactions: spacing of 250 ms is tight, jitter makes a few unavoidable (retried at once)
        self.webhooks = 0   # 429 on webhooks: they share one limit per channel and "shared" 429s are harmless, retried

    def emit(self, record: logging.LogRecord) -> None:
        text = record.getMessage()
        if "rate limited" in text.lower():
            if "/reactions/" in text:
                self.reactions += 1
            elif "/webhooks/" in text:
                self.webhooks += 1
            else:
                self.count += 1


def _ms(seconds: float) -> int:
    return round(seconds * 1000)


def _spread(samples: list[float]) -> dict:
    if not samples:
        return {"first_ms": 0, "median_ms": 0, "p95_ms": 0, "last_ms": 0}
    ordered = sorted(samples)
    return {"first_ms": _ms(ordered[0]), "median_ms": _ms(statistics.median(ordered)),
            "p95_ms": _ms(ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))]), "last_ms": _ms(ordered[-1])}


async def _settle(pool: SenderPool, senders, channel_id: int, say: Callable[[str], None], kind: str = "send") -> None:
    """Wait until every sender has all its slots back, so a phase isn't slowed by what the previous one used."""
    now = time.monotonic()
    wait = max((s.quiet_in(kind, channel_id, now, pool._limits_for(s, kind)[1]) for s in senders
                if kind == "send" or s.can_react), default=0.0)
    if wait > 0.4:
        say(f"   esperando {wait:.1f} s a que Discord libere los turnos de todos los bots…")
    if wait > 0:
        await asyncio.sleep(wait + 0.05)


def _failure(exc: BaseException) -> str:
    if isinstance(exc, discord.HTTPException):
        return f"Discord respondió {exc.status} ({exc.text or type(exc).__name__})"
    return f"{type(exc).__name__}: {exc}"


async def run(pool: SenderPool, channel_id: int, *, profile: str = "rapida", say: Callable[[str], None] = print,
              stop: asyncio.Event | None = None, max_rate_limits: int = 12,
              on_report: Callable[[dict], None] | None = None, **overrides) -> dict:
    """Run the test and return a report dict (see `format_report`). `overrides` replace profile values.

    The report is complete (and handed to `on_report`) before the test messages are deleted, so a slow or
    failing cleanup never hides the results. Whatever goes wrong in a phase is recorded in `report["errors"]`.
    """
    cfg = {**PROFILES[profile], **overrides}
    senders = [s for s in pool._all() if s.ready]
    lanes = sum(1 for s in senders if s.lane)
    bots = len(senders) - lanes
    limit, window = pool.limits["send"]
    counter = _RateLimitCounter()
    logging.getLogger("discord.http").addHandler(counter)
    created: list[int] = []
    report: dict = {"profile": profile, "channel_id": channel_id, "bots": bots, "lanes": lanes, "senders": [], "bursts": [],
                    "reactions": None, "sustained": None, "aborted": "", "errors": [], "cleanup": None}
    usable: list[dict] = []
    tracer = pool.tracer
    seq0 = tracer.seq
    pool.monitor.start()
    pool.monitor.take_max()

    def phase(name: str) -> None:
        tracer.phase = name
        pool.monitor.take_max()

    def should_stop() -> bool:
        if stop is not None and stop.is_set():
            report["aborted"] = "cancelada"
            return True
        if counter.count > max_rate_limits:
            report["aborted"] = f"demasiados límites de Discord ({counter.count}); se detuvo para no insistir"
            return True
        return False

    async def measure() -> None:
        # 1. each bot on its own: how long does one message / one reaction take when nothing else is going on?
        phase("latencia")
        say(f"1/4 Latencia de cada emisor ({bots} bots" + (f" + {lanes} webhooks" if lanes else "") + ")…")
        for sender in senders:
            entry = {"name": sender.name, "lane": sender.lane, "rtt_ms": 0, "reaction_ms": 0, "error": ""}
            ids, times = [], []
            try:
                for i in range(cfg["rtt_samples"]):
                    started = time.perf_counter()
                    data = await sender.endpoints.send_message(
                        channel_id, params=_plain_params(f"🧪 latencia {sender.name} {i + 1} (se borra sola)"))
                    times.append(time.perf_counter() - started)
                    sender.reserve("send", channel_id, time.monotonic())  # direct call: tell the pool the slot is used
                    ids.append(int(data["id"]))
                    pool._remember(ids[-1], channel_id, sender)           # so it can be deleted by its author
                if sender.can_react:
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
            say(f"   {sender.name}: " + (_sender_line(entry) if not entry["error"] else entry["error"]))
            if should_stop():
                return
        usable.extend(e for e in report["senders"] if not e["error"])
        if not usable:
            report["aborted"] = "ningún bot puede escribir en el canal"
            return

        # 2. bursts: everyone answers at once (each starts with every bot's window completely free)
        working = [s for s, e in zip(senders, report["senders"]) if not e["error"]]
        # messages that fit in one turn: every bot has its own limit, but all the webhooks together have ONE
        slots = sum(pool._limits_for(s, "send")[0] for s in working if not s.lane)
        slots += max((pool._limits_for(s, "send")[0] for s in working if s.lane), default=0)
        sizes = [min(MAX_MESSAGES // 2, slots),
                 min(MAX_MESSAGES // 2, slots + len(working) * cfg["overflow_per_bot"])]
        burst_ids: list[int] = []
        for number, size in enumerate(sizes, start=1):
            await _settle(pool, senders, channel_id, say)
            phase(f"ráfaga {number}")
            fits = "caben en un turno" if size <= slots else "más de los que caben en un turno"
            say(f"2/4 Ráfaga {number}: {size} mensajes a la vez ({fits})…")
            started = time.perf_counter()
            waits_before = pool.admitted
            done: list[float] = []
            failures: list[str] = []

            async def one(i: int, size=size, started=started) -> None:
                try:
                    data = await pool.send_text(channel_id, f"🧪 ráfaga {number}.{i + 1}/{size} (se borra sola)")
                except Exception as exc:  # noqa: BLE001
                    failures.append(_failure(exc))
                    return
                done.append(time.perf_counter() - started)
                created.append(int(data["id"]))
                burst_ids.append(int(data["id"]))

            await asyncio.gather(*(one(i) for i in range(size)))
            waited = list(pool.waits)[-(pool.admitted - waits_before):] if pool.admitted > waits_before else []
            spread = {"size": size, "failed": len(failures), "max_wait_ms": _ms(max(waited, default=0.0)),
                      "loop_lag_ms": _ms(pool.monitor.take_max()), **_spread(done)}
            report["bursts"].append(spread)
            report["errors"].extend(failures[:3])
            say(f"   primero {spread['first_ms']} ms · mediana {spread['median_ms']} ms · último {spread['last_ms']} ms"
                f" (esperando turno hasta {spread['max_wait_ms']} ms)")
            if should_stop():
                return
        if not burst_ids:
            report["errors"].append("ninguna ráfaga llegó a enviarse")
            return

        # 3. reactions (✅/❌ under every reply)
        await _settle(pool, senders, channel_id, say, "react")
        phase("reacciones")
        reactors = sum(1 for s in working if s.can_react)
        count = min(60, reactors * cfg["reactions_per_bot"], len(burst_ids) * len(EMOJIS))
        say(f"3/4 {count} reacciones a la vez…")
        started = time.perf_counter()
        done = []
        failures = []

        async def react(i: int) -> None:
            try:
                await pool.add_reaction(channel_id, burst_ids[i % len(burst_ids)], EMOJIS[(i // len(burst_ids)) % len(EMOJIS)])
            except Exception as exc:  # noqa: BLE001
                failures.append(_failure(exc))
                return
            done.append(time.perf_counter() - started)

        await asyncio.gather(*(react(i) for i in range(count)))
        report["reactions"] = {"count": count, "failed": len(failures), "loop_lag_ms": _ms(pool.monitor.take_max()),
                               **_spread(done)}
        report["errors"].extend(failures[:3])
        say(f"   mediana {report['reactions']['median_ms']} ms · última {report['reactions']['last_ms']} ms"
            + (f" · {len(failures)} fallaron" if failures else ""))
        if should_stop():
            return

        # 4. sustained: the most the channel takes minute after minute
        seconds = cfg["sustained_seconds"]
        if seconds:
            await _settle(pool, senders, channel_id, say)
            phase("sostenido")
            say(f"4/4 Ritmo sostenido durante {seconds:g} s…")
            end = time.perf_counter() + seconds
            stamps: list[float] = []
            begin = time.perf_counter()

            async def worker() -> None:
                while time.perf_counter() < end and not should_stop() and len(created) < MAX_MESSAGES * 2:
                    try:
                        data = await pool.send_text(channel_id, "🧪 ritmo sostenido (se borra sola)")
                    except Exception as exc:  # noqa: BLE001
                        report["errors"].append(_failure(exc))
                        return
                    created.append(int(data["id"]))
                    stamps.append(time.perf_counter() - begin)

            await asyncio.gather(*(worker() for _ in range(max(2, len(usable) * 2))))
            steady = [t for t in stamps if t >= window]  # after the first window, whose burst doesn't repeat
            span = max(1e-6, (stamps[-1] if stamps else seconds) - window)
            per_minute = len(steady) / span * 60 if steady and span > 1 else len(stamps) / seconds * 60
            report["sustained"] = {"seconds": seconds, "messages": len(stamps), "per_minute": round(per_minute),
                                   "per_bot_per_minute": round(per_minute / len(usable))}   # per sender (bot or webhook)
            say(f"   {len(stamps)} mensajes · ritmo estable ≈ {round(per_minute)} por minuto")

    try:
        await measure()
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - keep what was measured, and say what went wrong
        log.exception("performance test failed")
        report["errors"].append(_failure(exc))
        report["aborted"] = report["aborted"] or f"falló: {_failure(exc)}"
    finally:
        logging.getLogger("discord.http").removeHandler(counter)
        tracer.phase = ""

    # the report first: cleanup can take a while and must never hide the results
    report["rate_limits"] = counter.count
    report["reaction_retries"] = counter.reactions
    report["webhook_retries"] = counter.webhooks
    report["held_back"] = sum(s["held_back"] for s in pool.snapshot())
    base_spacing = pool.limits["react"][1]
    spacing = statistics.mean(max(base_spacing, s.react_spacing) for s in senders) if senders else base_spacing
    lane_senders = [s for s in senders if s.lane]
    lane_limit = round(statistics.mean(pool._limits_for(s, "send")[0] for s in lane_senders)) if lane_senders else 0
    lane_window = statistics.mean(pool._limits_for(s, "send")[1] for s in lane_senders) if lane_senders else 0.0
    report["planned"] = {"send_limit": limit, "send_window_ms": _ms(window), "react_spacing_ms": _ms(spacing),
                         "lane_limit": lane_limit, "lane_window_ms": _ms(lane_window)}
    report["trace"] = tracer.summary(seq0)
    report["loop_lag_ms"] = _ms(pool.monitor.worst)
    if usable:
        rtt = statistics.median([e["rtt_ms"] for e in usable]) / 1000 or 0.12
        usable_bots = sum(1 for e in usable if not e.get("lane"))
        usable_lanes = len(usable) - usable_bots
        model = dict(lanes=usable_lanes, lane_limit=lane_limit or 5, lane_window=lane_window or 2.5, rtt=rtt,
                     limit=limit, window=window, spacing=spacing)
        report["capacity_inputs"] = {**model, "bots": usable_bots}
        report["capacity"] = {f"{d:g}": capacity_model.capacity(usable_bots, deadline=d, **model).as_dict()
                              for d in (2.0, 3.0, 5.0)}
    if on_report is not None:
        try:
            on_report(report)
        except Exception:  # noqa: BLE001
            log.exception("could not show the report")

    if created:
        say(f"Borrando {len(created)} mensajes de prueba…")
        try:
            report["cleanup"] = await asyncio.shield(pool.delete_many(channel_id, created))
        except Exception as exc:  # noqa: BLE001
            report["cleanup"] = {"requested": len(created), "deleted": 0, "bulk": 0, "failed": len(created),
                                 "seconds": 0.0, "error": _failure(exc)}
        c = report["cleanup"]
        say(f"   borrados {c['deleted']} de {c['requested']} en {c['seconds']} s"
            + (" (en bloque)" if c["bulk"] == c["deleted"] and c["bulk"] else "")
            + (f" · {c['failed']} no se pudieron borrar: bórralos a mano" if c["failed"] else ""))
    return report


def _diagnosis_lines(report: dict) -> list[str]:
    """What Discord answered: real limits, slow kinds of request, every 429 with its cause."""
    trace, planned = report.get("trace"), report.get("planned") or {}
    if not trace or not trace.get("requests"):
        return []
    lines = [f"  DIAGNÓSTICO · {trace['requests']} peticiones a Discord (detalle de cada una en logs\\requests.jsonl)"]
    for kind, row in trace["kinds"].items():
        statuses = ", ".join(f"{count}× {status}" for status, count in sorted(row["status"].items()))
        lines.append(f"    {KIND_NAMES.get(kind, kind)}: {row['n']} ({statuses}) · respuesta mediana {row['p50_ms']} ms, "
                     f"p95 {row['p95_ms']} ms, máx {row['max_ms']} ms")
    for kind, row in trace["observed"].items():
        plan = (f"la app planea {planned.get('send_limit')} cada {planned.get('send_window_ms')} ms" if kind == "send"
                else f"la app espacia {planned.get('react_spacing_ms')} ms" if kind == "react"
                else f"la app planea {planned.get('lane_limit')} cada {planned.get('lane_window_ms')} ms" if kind == "wsend"
                else "")
        low, high = row["reset_after_ms"]
        lines.append(f"    Discord dice ({KIND_NAMES.get(kind, kind)}): límite {'/'.join(map(str, row['limit'])) or '?'}, "
                     f"reinicio {low}–{high} ms" + (f" · {plan}" if plan else ""))
    conns = trace.get("connections") or {}
    if conns.get("new") or conns.get("reused"):
        where = ", ".join(f"{count} en {phase_name}" for phase_name, count in conns["new_by_phase"].items())
        lines.append(f"    Conexiones: {conns['new']} nuevas" + (f" ({where})" if where else "") +
                     f", {conns['reused']} reutilizadas · la nueva más lenta tardó {conns['connect_ms_max']} ms en abrirse")
    slow = [r for r in trace.get("slowest", []) if r["ms"] >= 1000]
    if slow:
        lines.append("    Peticiones de más de 1 s (en una red sana no deberían pasar):")
        for r in slow[:3]:
            how = ("conexión nueva" + (f", {r['connect_ms']} ms solo en conectar" if r.get("connect_ms") else "")
                   if r["conn"] == "new" else "conexión ya abierta" if r["conn"] == "reused" else "")
            lines.append(f"      {KIND_NAMES.get(r['kind'], r['kind'])} de {short_name(r['bot'])} [{r['phase'] or '-'}]: "
                         f"{r['ms']} ms (estado {r['status']}" + (f", {how}" if how else "") + ")")
    if trace["limited_total"]:
        lines.append(f"    {trace['limited_total']} respuestas 429 (ninguna petición se pierde: se reintenta). Las primeras:")
        for item in trace["limited"][:8]:
            lines.append(f"      +{item['at_ms']} ms [{item['phase'] or '-'}] " + explain_429(item, limit=planned.get("send_limit", 5)))
    elif trace["requests"]:
        lines.append("    Ningún 429: Discord no limitó nada.")
    if report.get("loop_lag_ms") is not None:
        lag = report["loop_lag_ms"]
        lines.append(f"    Carga del bot: el peor retraso al atender fue {lag} ms"
                     + (" (alto: el propio bot iba justo de CPU/red)" if lag > 250 else " (bien)"))
    return lines


def _sender_line(entry: dict, sep: str = ",") -> str:
    if entry.get("lane"):
        return f"mensaje {entry['rtt_ms']} ms (webhook)"
    return f"mensaje {entry['rtt_ms']} ms{sep} reacción {entry['reaction_ms']} ms"


def format_report(report: dict) -> list[str]:
    """Spanish lines for the log panel / a text file."""
    lanes = report.get("lanes", 0)
    lines = [f"PRUEBA DE RENDIMIENTO · {report['bots']} bot{'s' if report['bots'] != 1 else ''}"
             + (f" + {lanes} webhook{'s' if lanes != 1 else ''}" if lanes else "") + f" · prueba {report['profile']}"]
    if report.get("aborted"):
        lines.append(f"⚠ Se detuvo: {report['aborted']}")
    for entry in report["senders"]:
        lines.append(f"  {entry['name']}: " + (_sender_line(entry, " ·") if not entry["error"] else f"✗ {entry['error']}"))
    for burst in report["bursts"]:
        lines.append(f"  Ráfaga de {burst['size']} mensajes: primero {burst['first_ms']} ms, mediana "
                     f"{burst['median_ms']} ms, último {burst['last_ms']} ms"
                     + (f" (de eso, hasta {burst['max_wait_ms']} ms esperando turno para no pasar el límite)"
                        if burst.get("max_wait_ms", 0) > 300 else "")
                     + (f" · {burst['failed']} fallaron" if burst.get("failed") else ""))
    if report.get("reactions"):
        r = report["reactions"]
        lines.append(f"  {r['count']} reacciones a la vez: mediana {r['median_ms']} ms, última {r['last_ms']} ms"
                     + (f" · {r['failed']} fallaron" if r.get("failed") else ""))
    if report.get("sustained"):
        s = report["sustained"]
        lines.append(f"  Ritmo sostenido: ≈ {s['per_minute']} mensajes por minuto en total "
                     f"(≈ {s['per_bot_per_minute']} por " + ("emisor, bot o webhook)" if lanes else "bot)"))
    lines.extend(_diagnosis_lines(report))
    for error in dict.fromkeys(report.get("errors") or []):
        lines.append(f"  ✗ {error}")
    if "rate_limits" in report:
        lines.append(f"  Límites de Discord (429) encontrados: {report['rate_limits']} · envíos frenados: {report['held_back']}"
                     + (f" · reacciones reintentadas por milisegundos de diferencia: {report['reaction_retries']}"
                        if report.get("reaction_retries") else "")
                     + (f" · webhooks reintentados: {report['webhook_retries']}" if report.get("webhook_retries") else ""))
    cleanup = report.get("cleanup")
    if cleanup:
        lines.append(f"  Mensajes de prueba borrados: {cleanup['deleted']} de {cleanup['requested']} en {cleanup['seconds']} s")
    if report.get("capacity"):
        c3 = report["capacity"]["3"]
        lines.append("  Capacidad estimada (jugadores respondiendo a la vez y viendo todo su resultado a tiempo):")
        for deadline, c in report["capacity"].items():
            lines.append(f"    en {deadline} s: ≈ {c['players']} jugadores (límite: {c['limiting']})")
        lines.append(f"  Ritmo máximo: ≈ {round(c3['messages_per_minute'])} mensajes y ≈ {round(c3['reactions_per_minute'])} "
                     f"reacciones por minuto en el canal.")
        inputs = report.get("capacity_inputs") or {}
        base = {k: v for k, v in inputs.items() if k not in ("bots", "lanes")}
        base.update(deadline=3.0, rtt=c3["rtt"])
        with_one = capacity_model.capacity(max(1, inputs.get("bots", 1)) + 1, lanes=inputs.get("lanes", 0), **base).players
        without = capacity_model.capacity(max(1, inputs.get("bots", 1)), lanes=inputs.get("lanes", 0), **base).players
        lines.append(f"  Cada bot auxiliar que agregues suma ≈ {with_one - without} jugadores simultáneos.")
        if lanes:
            planned = report.get("planned") or {}
            lines.append(f"  Los webhooks de un canal comparten UN solo límite (≈ {planned.get('lane_limit')} mensajes cada "
                         f"{planned.get('lane_window_ms', 0) / 1000:.1f} s en total, sean los que sean) y no mandan reacciones: "
                         f"las reacciones siguen necesitando un bot.")
    return lines
