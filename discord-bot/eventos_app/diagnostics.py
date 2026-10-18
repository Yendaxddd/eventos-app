"""Tools to see *what Discord actually answers* and *when the bot itself is slow*.

* `RequestTracer` watches every HTTP request every bot makes (through aiohttp's trace hooks, so it also sees
  the 429s that discord.py retries on its own): which bot, what kind (message, reaction, edit, delete), how
  long it took, and Discord's own rate-limit headers. It keeps the latest events in memory (for the
  performance test report), writes every one to `logs/requests.jsonl` (rotating) and tells listeners about
  each 429 so the app can explain it live.
* `LoopMonitor` measures how late the bot's event loop wakes up. If it is late, the bot itself (not Discord)
  is the bottleneck: too much work at once.
"""

from __future__ import annotations

import asyncio
import json
import logging
import logging.handlers
import queue
import re
import statistics
import time
from collections import deque
from pathlib import Path
from typing import Callable

import aiohttp
from yarl import URL

log = logging.getLogger("eventos_app.diagnostics")

_WEBHOOK_ROUTES = (
    (re.compile(r"^/webhooks/(\d+)/[^/]+$"), {"POST": "wsend"}),
    (re.compile(r"^/webhooks/(\d+)/[^/]+/messages/\d+$"), {"PATCH": "wedit", "DELETE": "wdelete"}),
)
_ROUTES = (
    (re.compile(r"^/channels/(\d+)/messages/bulk-delete$"), {"POST": "bulk"}),
    (re.compile(r"^/channels/(\d+)/messages/\d+/reactions/.+/@me$"), {"PUT": "react"}),
    (re.compile(r"^/channels/(\d+)/messages/\d+$"), {"PATCH": "edit", "DELETE": "delete"}),
    (re.compile(r"^/channels/(\d+)/messages$"), {"POST": "send"}),
)
KIND_NAMES = {"send": "mensaje", "react": "reacción", "edit": "edición", "delete": "borrado", "bulk": "borrado en bloque",
              "wsend": "mensaje por webhook", "wedit": "edición por webhook", "wdelete": "borrado por webhook",
              "other": "otra petición"}
_TOKEN_IN_URL = re.compile(r"(/webhooks/\d+/)[\w-]+")


def classify(method: str, url: str) -> tuple[str, int]:
    """('send' | 'react' | 'edit' | 'delete' | 'bulk' | 'wsend' | 'wedit' | 'wdelete' | 'ping' | 'other', id).

    The id is the channel's, or the webhook's for the 'w…' kinds (a webhook's token is never kept anywhere).
    """
    path = re.sub(r"^/api/v\d+", "", URL(url).raw_path)
    if path == "/gateway":
        return "ping", 0
    for pattern, kinds in _WEBHOOK_ROUTES:
        match = pattern.match(path)
        if match and method in kinds:
            return kinds[method], int(match.group(1))
    for pattern, kinds in _ROUTES:
        match = pattern.match(path)
        if match and method in kinds:
            return kinds[method], int(match.group(1))
    return "other", 0


def _float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _ms(seconds: float | None) -> int | None:
    return None if seconds is None else round(seconds * 1000)


def short_name(name: str) -> str:
    return name.split("#")[-2][-24:] + "#" + name.split("#")[-1] if "#" in name else name[-28:]


class RequestTracer:
    def __init__(self, keep: int = 4000) -> None:
        self.events: deque[dict] = deque(maxlen=keep)
        self.seq = 0
        self.phase = ""                                  # set by the performance test: "ráfaga 1", "reacciones"…
        self.context: Callable[[str, str, int], dict] | None = None   # (bot, kind, channel) -> what the pool had planned
        self.listeners: list[Callable[[dict], None]] = []
        self.observed: dict[tuple[str, str], dict] = {}  # (bot, kind) -> last rate-limit headers of a successful call
        self._queue_listener: logging.handlers.QueueListener | None = None
        self._logger: logging.Logger | None = None

    # ---- hooking into aiohttp --------------------------------------------------------------
    def config(self, label: Callable[[], str]) -> aiohttp.TraceConfig:
        """A TraceConfig for one bot's HTTP session. `label()` gives the bot's name at the time of the request."""
        cfg = aiohttp.TraceConfig()

        async def start(session, ctx, params) -> None:
            ctx.started = time.perf_counter()

        async def end(session, ctx, params) -> None:
            self._finish(label(), params.method, str(params.url), ctx, response=params.response)

        async def failed(session, ctx, params) -> None:
            self._finish(label(), params.method, str(params.url), ctx, error=params.exception)

        async def connecting(session, ctx, params) -> None:       # no free connection: a new one is opened
            ctx.conn = "new"
            ctx.conn_started = time.perf_counter()

        async def connected(session, ctx, params) -> None:
            ctx.connect_ms = _ms(time.perf_counter() - getattr(ctx, "conn_started", time.perf_counter()))

        async def reused(session, ctx, params) -> None:
            ctx.conn = "reused"

        cfg.on_connection_create_start.append(connecting)
        cfg.on_connection_create_end.append(connected)
        cfg.on_connection_reuseconn.append(reused)
        cfg.on_request_start.append(start)
        cfg.on_request_end.append(end)
        cfg.on_request_exception.append(failed)
        cfg.freeze()
        return cfg

    def attach(self, http, label: Callable[[], str]) -> bool:
        """Add the hooks to a session that already exists (the main bot's). False if discord.py changed inside."""
        session = getattr(http, "_HTTPClient__session", None)
        traces = getattr(session, "_trace_configs", None)
        if not isinstance(traces, list) or getattr(session, "closed", True):
            return False
        traces.append(self.config(label))
        return True

    # ---- recording ---------------------------------------------------------------------------
    def _finish(self, bot: str, method: str, url: str, ctx, *, response=None, error: BaseException | None = None) -> None:
        try:
            kind, ident = classify(method, url)
            channel = 0 if kind.startswith("w") else ident
            elapsed = time.perf_counter() - getattr(ctx, "started", time.perf_counter())
            event = {"t": round(time.time(), 3), "mono": time.monotonic(), "bot": bot, "kind": kind, "channel": channel,
                     "phase": self.phase, "status": 0, "ms": _ms(elapsed), "conn": getattr(ctx, "conn", "")}
            if kind.startswith("w"):
                event["webhook"] = ident
            if getattr(ctx, "connect_ms", None) is not None:
                event["connect_ms"] = ctx.connect_ms
            if error is not None:
                event["error"] = type(error).__name__
            if response is not None:
                headers = response.headers
                event["status"] = response.status
                event["limit"] = _float(headers.get("X-RateLimit-Limit"))
                event["remaining"] = _float(headers.get("X-RateLimit-Remaining"))
                event["reset_after"] = _float(headers.get("X-RateLimit-Reset-After"))
                event["retry_after"] = _float(headers.get("Retry-After"))
                event["bucket"] = (headers.get("X-RateLimit-Bucket") or "")[:12]
                event["scope"] = headers.get("X-RateLimit-Scope") or ""
                event["global"] = headers.get("X-RateLimit-Global") == "true"
                event["via"] = bool(headers.get("Via"))
            if event["status"] == 429 and self.context is not None:
                event["ours"] = self.context(bot, kind, ident)
            if kind == "ping":
                return
            self.seq += 1
            event["seq"] = self.seq
            self.events.append(event)
            if 200 <= event["status"] < 300 and event.get("reset_after") is not None:
                self.observed[(bot, kind)] = {"limit": event.get("limit"), "reset_after": event["reset_after"],
                                              "remaining": event.get("remaining"), "bucket": event.get("bucket")}
            if self._logger is not None:
                self._logger.info(json.dumps({k: v for k, v in event.items() if k != "mono"}, ensure_ascii=False))
            for listener in list(self.listeners):
                try:
                    listener(event)
                except Exception:  # noqa: BLE001
                    log.exception("tracer listener failed")
        except Exception:  # noqa: BLE001 - tracing must never break a request
            log.exception("could not trace a request")

    # ---- the log file ----------------------------------------------------------------------------
    def log_to(self, path: Path, max_bytes: int = 3_000_000, backups: int = 3) -> None:
        self.stop_logging()
        try:
            handler = logging.handlers.RotatingFileHandler(path, maxBytes=max_bytes, backupCount=backups, encoding="utf-8")
        except OSError:
            log.warning("cannot write %s", path)
            return
        handler.setFormatter(logging.Formatter("%(message)s"))
        events: queue.SimpleQueue = queue.SimpleQueue()       # the file is written on another thread
        logger = logging.getLogger(f"eventos_app.requests.{id(self)}")
        logger.handlers.clear()
        logger.addHandler(logging.handlers.QueueHandler(events))
        logger.setLevel(logging.INFO)
        logger.propagate = False
        self._logger = logger
        self._queue_listener = logging.handlers.QueueListener(events, handler)
        self._queue_listener.start()

    def stop_logging(self) -> None:
        if self._queue_listener is not None:
            self._queue_listener.stop()
            for handler in self._queue_listener.handlers:
                handler.close()
            self._queue_listener = None
        self._logger = None

    # ---- reading it back ---------------------------------------------------------------------------
    def since(self, seq: int) -> list[dict]:
        return [e for e in self.events if e["seq"] > seq]

    def summary(self, since: int = 0) -> dict:
        """What the requests since `since` looked like, for the report."""
        events = self.since(since)
        origin = events[0]["mono"] if events else 0.0
        kinds: dict[str, dict] = {}
        for kind in sorted({e["kind"] for e in events}):
            mine = [e for e in events if e["kind"] == kind]
            times = sorted(e["ms"] for e in mine if e["status"] and 200 <= e["status"] < 300)
            statuses: dict[str, int] = {}
            for e in mine:
                key = str(e["status"] or e.get("error", "error"))
                statuses[key] = statuses.get(key, 0) + 1
            kinds[kind] = {"n": len(mine), "status": statuses,
                           "p50_ms": round(statistics.median(times)) if times else 0,
                           "p95_ms": times[min(len(times) - 1, int(0.95 * len(times)))] if times else 0,
                           "max_ms": times[-1] if times else 0}
        limited = [{"at_ms": round((e["mono"] - origin) * 1000), "phase": e["phase"], "bot": e["bot"], "kind": e["kind"],
                    "retry_after_ms": _ms(e.get("retry_after")), "reset_after_ms": _ms(e.get("reset_after")),
                    "scope": e.get("scope", ""), "global": e.get("global", False), "ours": e.get("ours", {})}
                   for e in events if e["status"] == 429]
        observed: dict[str, dict] = {}
        for e in events:
            if 200 <= e["status"] < 300 and e.get("reset_after") is not None:
                row = observed.setdefault(e["kind"], {"limit": set(), "reset_after_ms": [10 ** 9, 0], "bucket": set()})
                if e.get("limit") is not None:
                    row["limit"].add(int(e["limit"]))
                row["reset_after_ms"] = [min(row["reset_after_ms"][0], _ms(e["reset_after"])),
                                         max(row["reset_after_ms"][1], _ms(e["reset_after"]))]
                row["bucket"].add(e.get("bucket", ""))
        for row in observed.values():
            row["limit"] = sorted(row["limit"])
            row["buckets"] = len(row.pop("bucket"))
        phases: dict[str, dict] = {}
        for e in events:
            row = phases.setdefault(e["phase"] or "-", {"requests": 0, "429": 0, "errors": 0})
            row["requests"] += 1
            row["429"] += e["status"] == 429
            row["errors"] += e["status"] == 0 or e["status"] >= 500
        slowest = [{"at_ms": round((e["mono"] - origin) * 1000), "phase": e["phase"], "bot": e["bot"], "kind": e["kind"],
                    "ms": e["ms"], "status": e["status"], "conn": e.get("conn", ""), "connect_ms": e.get("connect_ms")}
                   for e in sorted(events, key=lambda e: e["ms"], reverse=True)[:5]]
        conns = {"new": sum(e.get("conn") == "new" for e in events), "reused": sum(e.get("conn") == "reused" for e in events),
                 "connect_ms_max": max((e.get("connect_ms") or 0 for e in events), default=0),
                 "new_by_phase": {}}
        for e in events:
            if e.get("conn") == "new":
                conns["new_by_phase"][e["phase"] or "-"] = conns["new_by_phase"].get(e["phase"] or "-", 0) + 1
        return {"requests": len(events), "kinds": kinds, "slowest": slowest, "connections": conns, "limited": limited[:15], "limited_total": len(limited),
                "observed": observed, "phases": phases}


class _RedactWebhookTokens(logging.Filter):
    """discord.py logs the full URL of a rate-limited request; a webhook's token must not end up in a log file."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            text = record.getMessage()
        except Exception:  # noqa: BLE001
            return True
        if "/webhooks/" in text:
            record.msg, record.args = _TOKEN_IN_URL.sub(r"\1***", text), ()
        return True


def install_log_redaction() -> None:
    logger = logging.getLogger("discord.http")
    if not any(isinstance(f, _RedactWebhookTokens) for f in logger.filters):
        logger.addFilter(_RedactWebhookTokens())


def explain_429(event: dict, *, limit: int = 5) -> str:
    """One Spanish sentence about a 429: who got it, how long Discord asked to wait and whether we caused it."""
    kind = KIND_NAMES.get(event.get("kind", "other"), "petición")
    wait = event["reset_after_ms"] if "reset_after_ms" in event else _ms(event.get("reset_after"))   # exact, in ms
    if wait is None:  # Retry-After is rounded up to whole seconds, so it is only the fallback
        wait = event["retry_after_ms"] if "retry_after_ms" in event else _ms(event.get("retry_after"))
    ours = (event.get("ours") or {}).get("reservas")
    text = f"{kind} de {short_name(event['bot'])}: Discord pidió esperar {wait if wait is not None else '?'} ms"
    if event.get("global"):
        text += " (límite GLOBAL de la cuenta)"
    elif event.get("scope") and event["scope"] != "user":
        text += f" (ámbito: {event['scope']})"
    if ours is not None:
        window = (event.get("ours") or {}).get("ventana_s", 0)
        text += f" · este bot tenía {ours} reserva{'s' if ours != 1 else ''} en los últimos {window:g} s"
        if event.get("kind") == "send" and ours <= limit:
            text += " → no fue por exceso nuestro (¿otro programa usa este bot, o desfase de reloj?)"
        elif event.get("kind") == "react":
            text += " → Discord limita las reacciones más que lo planeado (la app ya espacia más)"
    return text


class LoopMonitor:
    """Samples how late the event loop wakes up. Big values mean the bot is overloaded, not rate limited."""

    INTERVAL = 0.05
    WARN = 0.25

    def __init__(self, on_warning: Callable[[float], None] | None = None) -> None:
        self.on_warning = on_warning
        self.max_lag = 0.0         # since the last `take_max()`
        self.worst = 0.0           # since the start
        self.samples = 0
        self._last_warning = 0.0
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.get_running_loop().create_task(self._run())

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None

    def take_max(self) -> float:
        value, self.max_lag = self.max_lag, 0.0
        return value

    async def _run(self) -> None:
        while True:
            before = time.monotonic()
            await asyncio.sleep(self.INTERVAL)
            lag = max(0.0, time.monotonic() - before - self.INTERVAL)
            self.samples += 1
            self.max_lag = max(self.max_lag, lag)
            self.worst = max(self.worst, lag)
            if lag > self.WARN and self.on_warning is not None and time.monotonic() - self._last_warning > 10:
                self._last_warning = time.monotonic()
                try:
                    self.on_warning(lag)
                except Exception:  # noqa: BLE001
                    log.exception("loop monitor callback failed")
