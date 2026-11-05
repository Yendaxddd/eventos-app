"""Spread the bot's outgoing messages and reactions over several senders and remove the waiting discord.py
adds on its own, so a burst of QTE traffic goes out with as little delay as possible.

Modules
-------
* `ratelimit`   -- the "open" buckets that stop discord.py from blocking (see there for why).
* `sender`      -- `Sender` (one bot account or one webhook and what it has used) and its HTTP `Endpoints`.
* `webhooks`    -- registering one webhook per bot in the event channel (the extra "lanes").
* `diagnostics` -- request tracing, 429 explanations, event-loop lag.
* `multibot`    -- this file: `SenderPool`, the routing between all of them.

How it works
------------
Discord rate-limits per bot token (and per channel): about 5 messages / 5 s in a channel for each bot,
and about 4 reactions / second. The bot code sends with `channel.send(...)` in ~160 places, so instead
of touching them all we swap a few methods of the primary bot's `HTTPClient` (`send_message`,
`edit_message`, `delete_message`, `add_reaction`). Everything in discord.py goes through those.

* Helper bots only log in over HTTP (no gateway, no privileged intents). They must be members of the
  server and may write in the event channel.
* A send (or reaction) goes to the sender with the most room left in that channel's rate-limit window; the
  slot is reserved immediately so a burst of 10 messages is spread from the first one. If every sender is
  full, the call waits for the first free slot instead of being refused.
* Webhook lanes (one per bot, registered in the event channel) are extra senders for plain messages: bots are
  preferred, the lanes take what the bots have no room for. Replies, buttons and stickers always use a bot.
* Edits and deletes go to the sender that wrote the message (Discord only lets a bot edit its own).
  For sticky channels (the HP bar thread) that knowledge survives restarts.
* If a sender can't write there (not in the server, no permission), the message goes out through another
  sender and that one is skipped for that channel for a while.
* Messages with buttons always go through the primary: clicks are delivered only to the bot that is
  connected to the gateway.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, NamedTuple

import aiohttp
import discord

from . import webhooks
from .diagnostics import LoopMonitor, RequestTracer, install_log_redaction
from .ratelimit import (  # noqa: F401 - re-exported: the rest of the app and the tests import them from here
    _OPEN, OPEN_ROUTES, PING_ROUTE, REACT_ROUTE, SEND_ROUTE, WEBHOOK_SEND_ROUTE, OpenBucket, can_open_buckets,
    open_buckets)
from .sender import (  # noqa: F401
    CHANNEL_LIMIT, WARM_CONNECTIONS, WINDOW_SECONDS, Endpoints, Sender, SenderStats, endpoints_of,
    webhook_endpoints_of)

log = logging.getLogger("eventos_app.multibot")

REACTION_SPACING = 0.30    # Discord: 1 reaction per 250 ms (confirmed by its headers); the rest is margin for network jitter
MAX_REACTION_SPACING = 0.8 # the most a bot is slowed down after repeated 429s on reactions
REACT_RETRIES = 4          # extra tries (on top of discord.py's own 5) before a reaction is given up
SLOW_SEND_SECONDS = 1.5    # a send slower than this was probably held back by a rate limit
PENALTY_SECONDS = 4.0      # how long a sender that was just held back is deprioritised
BLOCK_SECONDS = 600.0      # skip a helper in a channel it can't write to for this long
OWNER_MEMORY = 20000       # message -> author sender, for edits/deletes
STICKY_MEMORY = 500        # authors remembered across restarts (HP bar messages)
WARM_INTERVAL = 8.0        # seconds between keep-alive rounds (aiohttp closes idle connections at 15 s)
BULK_DELETE_MAX = 100      # Discord: bulk delete takes 2 to 100 messages younger than two weeks
DELETE_PARALLEL = 4        # deletes in flight per sender when they have to go one by one
WAIT_MEMORY = 2000         # admission waits kept for the performance test
WEBHOOK_LIMIT = 5          # messages per window for ALL the webhooks of a channel (Discord: ~5 / 2 s, scope "shared")
WEBHOOK_WINDOW = 2.5       # a little more than the 2 s Discord documents; learned from its headers
SEND_RETRIES = 3           # extra tries (on top of discord.py's own 5) before a rate-limited message is given up

INVITE_PERMISSIONS = discord.Permissions(
    view_channel=True, send_messages=True, send_messages_in_threads=True, embed_links=True,
    attach_files=True, read_message_history=True, add_reactions=True, use_external_emojis=True,
    manage_webhooks=True,   # lets the bot register its own webhook lane in the event channel
)


def _reset_files(params) -> None:
    """Rewind attachments so the same message can be sent again through another sender."""
    for file in (getattr(params, "files", None) or ()):
        try:
            file.reset()
        except Exception:  # noqa: BLE001
            pass


def _payload(params) -> dict:
    payload = getattr(params, "payload", None)
    if payload is None:
        for part in getattr(params, "multipart", None) or ():
            if part.get("name") == "payload_json":
                try:
                    payload = json.loads(part["value"])
                except (ValueError, TypeError):
                    payload = None
                break
    return payload or {}


def has_components(params) -> bool:
    return bool(_payload(params).get("components"))


def needs_a_bot(params) -> bool:
    """Replies, stickers and polls cannot be sent by a webhook; buttons need the bot that receives the clicks."""
    payload = _payload(params)
    return any(payload.get(key) for key in ("components", "message_reference", "sticker_ids", "poll"))


_UNREACHABLE = (aiohttp.ClientError, asyncio.TimeoutError, OSError)
_METHODS = ("send_message", "edit_message", "delete_message", "add_reaction")


class SenderPool:
    def __init__(self, *, limit: int = CHANNEL_LIMIT, window: float = WINDOW_SECONDS,
                 reaction_spacing: float = REACTION_SPACING, on_change: Callable[[], None] | None = None) -> None:
        self.limits = {"send": (limit, window), "react": (1, reaction_spacing)}
        self.on_change = on_change
        self.primary: Sender | None = None
        self.helpers: list[Sender] = []
        self.sticky_channels: set[int] = set()
        self.owners_file: Path | None = None
        self._owners: OrderedDict[int, Sender] = OrderedDict()
        self._sticky: OrderedDict[int, int] = OrderedDict()   # message id -> author user id
        self._sticky_dirty = False
        self._http = None
        self._open = False
        self._task: asyncio.Task | None = None
        self.admitted = 0                                  # how many sends/reactions went through `_admit`
        self.waits: deque[float] = deque(maxlen=WAIT_MEMORY)   # seconds each one waited for its turn
        self._no_bulk: set[int] = set()                    # users that may not bulk delete in this server
        self.lanes: list[Sender] = []                      # webhook lanes in the event channel (see `ensure_lanes`)
        self.lane_ids: set[int] = set()                    # their webhook ids: the bot must not take them for players
        # Discord limits the webhooks of a channel TOGETHER (429 scope "shared"): every lane uses this one ledger
        self._lane_slots: dict = {}
        self._lane_shifted: dict = {}
        self.lane_channel = 0
        self.webhooks_enabled = True
        self.lane_store = webhooks.LaneStore()
        self.primary_identity: Callable[[], Any] | None = None   # async () -> (display name, avatar bytes | None)
        self.trace_file: Path | None = None                # where every request is logged (set before `install`)
        self.tracer = RequestTracer()
        self.tracer.context = self._context
        self.tracer.listeners.append(self._learn)
        self.monitor = LoopMonitor(on_warning=lambda lag: self.on_lag(lag) if self.on_lag else None)
        self.on_lag: Callable[[float], None] | None = None

    # ---- setup -----------------------------------------------------------------
    def install(self, primary_http, primary_name: str = "Principal", primary_user_id: int = 0) -> None:
        """Start routing the primary bot's sends/edits/deletes/reactions through the pool."""
        if self._http is not None:
            return
        self._http = primary_http
        install_log_redaction()
        self._open = can_open_buckets(primary_http)
        if self._open:
            open_buckets(primary_http)
        else:
            log.warning("discord.py has no get_ratelimit(): sending one message at a time per bot and channel")
        self.primary = Sender(primary_name, endpoints_of(primary_http), primary=True, user_id=primary_user_id)
        if not self.tracer.attach(primary_http, lambda: self.primary.name if self.primary else primary_name):
            log.warning("could not watch the main bot's requests; the rate-limit diagnostics will only cover helpers")
        if self.trace_file is not None:
            self.tracer.log_to(self.trace_file)
        primary_http.send_message = self._route_send
        primary_http.edit_message = self._route_edit
        primary_http.delete_message = self._route_delete
        primary_http.add_reaction = self._route_react
        self.load_owners()
        self._changed()

    def uninstall(self) -> None:
        """Restore the primary's own methods (instance attributes shadow the class methods)."""
        if self._http is not None:
            for name in (*_METHODS, "get_ratelimit"):
                self._http.__dict__.pop(name, None)
            self._http = None

    def start_background(self) -> None:
        """Keep connections warm and persist author memory. Needs a running loop."""
        if self._task is None:
            self._task = asyncio.get_running_loop().create_task(self._background())
            self.monitor.start()

    async def _background(self) -> None:
        while True:
            await asyncio.sleep(WARM_INTERVAL)
            try:
                await asyncio.gather(*(s.warm() for s in self._all()), return_exceptions=True)
                self.save_owners()
            except Exception:  # noqa: BLE001
                log.exception("pool background round failed")

    async def add_helper(self, token: str) -> Sender:
        """Log a helper bot in (HTTP only) and add it to the pool."""
        label = {"name": "auxiliar"}
        client = discord.Client(intents=discord.Intents.none(), http_trace=self.tracer.config(lambda: label["name"]))
        try:
            await client.login(token.strip())
            user = client.user
            label["name"] = str(user)
            known = {self.primary.user_id} if self.primary and self.primary.user_id else set()
            known |= {h.user_id for h in self.helpers}
            if user.id in known:
                raise ValueError(f"{user} ya está en uso (es el bot principal o un auxiliar repetido).")
        except BaseException:
            await client.close()
            raise
        if can_open_buckets(client.http):
            open_buckets(client.http)
        sender = Sender(str(user), endpoints_of(client.http), client=client, user_id=user.id)
        self.helpers.append(sender)
        self._changed()
        return sender

    async def check_access(self, channel_id: int) -> None:
        """Ask Discord whether each helper can see the channel; helpers that can't are skipped there.

        Only proves the helper is in the server and can view the channel, not that it may write
        (use `test_send` for that). Spares the first burst from discovering it the hard way.
        """
        for sender in self.helpers:
            if sender.client is None:
                continue
            try:
                await sender.client.http.get_channel(channel_id)
            except (discord.Forbidden, discord.NotFound):
                sender.access = "no"
                sender.block(channel_id, time.monotonic(), BLOCK_SECONDS)
            except _UNREACHABLE:
                sender.access = "?"
            else:
                sender.access = "ok"
                sender.unblock(channel_id)
        self._changed()

    async def remove_helper(self, sender: Sender) -> None:
        if sender in self.helpers:
            self.helpers.remove(sender)
        sender.ready = False
        for lane in [l for l in self.lanes if l.owner is sender]:
            self._drop_lane(lane)
        for message_id in [m for m, s in self._owners.items() if s is sender]:
            del self._owners[message_id]
        if sender.client is not None:
            await sender.client.close()
        self._changed()

    async def close(self) -> None:
        self.monitor.stop()
        self.tracer.stop_logging()
        if self._task is not None:
            self._task.cancel()
            self._task = None
        self.save_owners()
        self.uninstall()
        self.lanes.clear()
        self.lane_ids.clear()
        for sender in list(self.helpers):
            await self.remove_helper(sender)

    # ---- webhook lanes -------------------------------------------------------------
    def _http_of(self, owner: Sender):
        return self._http if owner.primary else owner.client.http

    async def _identity(self, owner: Sender) -> tuple[str, bytes | None]:
        """The name and picture a bot's webhook shows: the bot's own."""
        try:
            if owner.primary:
                if self.primary_identity is not None:
                    return await self.primary_identity()
                return owner.name.rsplit("#", 1)[0], None
            user = owner.client.user
            try:
                return user.display_name, await user.display_avatar.replace(size=128, format="png").read()
            except Exception:  # noqa: BLE001 - no picture is better than no lane
                return user.display_name, None
        except Exception:  # noqa: BLE001
            return owner.name.rsplit("#", 1)[0], None

    async def add_lane(self, owner: Sender, channel_id: int) -> dict:
        """Register (or find) the one webhook of `owner` in `channel_id` and start using it. Never raises."""
        existing = next((l for l in self.lanes if l.owner is owner and l.channel == channel_id), None)
        if existing is not None:
            return {"bot": owner.name, "ok": True, "reason": ""}
        try:
            name, avatar = await self._identity(owner)
            info = await webhooks.register(self._http_of(owner), channel_id=channel_id, user_id=owner.user_id,
                                           display_name=name, avatar=avatar, store=self.lane_store)
        except webhooks.LaneError as exc:
            owner.lane_note = str(exc)
        except Exception as exc:  # noqa: BLE001 - a lane is a bonus: its failure must never hurt the bot
            log.exception("could not register a webhook for %s", owner.name)
            owner.lane_note = f"{type(exc).__name__}: {exc}"
        else:
            lane = Sender(f"{owner.name} · webhook", webhook_endpoints_of(self._http_of(owner), info.webhook_id, info.token),
                          user_id=info.webhook_id)
            lane.lane, lane.channel, lane.webhook_id, lane.owner = True, channel_id, info.webhook_id, owner
            lane.can_react = False
            lane._slots, lane._shifted = self._lane_slots, self._lane_shifted     # one limit for all of them
            peer = next((l for l in self.lanes), None)                           # what the others already learned
            lane.send_limit = peer.send_limit if peer else WEBHOOK_LIMIT
            lane.send_window = peer.send_window if peer else WEBHOOK_WINDOW
            self.lanes.append(lane)
            self.lane_ids.add(info.webhook_id)
            owner.lane_note = "ok" if not info.created else "ok (webhook creado)"
            self._changed()
            return {"bot": owner.name, "ok": True, "reason": "", "created": info.created}
        self._changed()
        return {"bot": owner.name, "ok": False, "reason": owner.lane_note}

    async def ensure_lanes(self, channel_id: int) -> list[dict]:
        """Webhook lanes for this channel: one per bot (never more: a channel holds 15 webhooks in total).

        Call it whenever the event channel changes. The webhooks of the previous channel are left where they are
        (they are found again if you come back); only this pool stops using them.
        """
        channel_id = int(channel_id or 0)
        self.drop_lanes()
        self.lane_channel = channel_id
        if not self.webhooks_enabled or not channel_id:
            for bot in self._bots():
                bot.lane_note = ""
            self._changed()
            return []
        owners = [b for b in self._bots() if b.ready and b.access != "no"]
        for bot in self._bots():
            if bot not in owners:
                bot.lane_note = "no ve el canal"
        return list(await asyncio.gather(*(self.add_lane(o, channel_id) for o in owners)))

    def drop_lanes(self) -> None:
        for lane in list(self.lanes):
            self._drop_lane(lane)

    def _drop_lane(self, lane: Sender) -> None:
        lane.ready = False
        if lane in self.lanes:
            self.lanes.remove(lane)
        self.lane_ids.discard(lane.webhook_id)
        self._changed()

    def _lane_gone(self, lane: Sender) -> None:
        """Discord says this webhook does not exist (deleted by hand): forget it and register again next time."""
        lane.error = "el webhook ya no existe"
        if lane.owner is not None:
            lane.owner.lane_note = "el webhook fue borrado: se registrará de nuevo al cambiar de canal"
            self.lane_store.forget(lane.channel, lane.owner.user_id)
        self._drop_lane(lane)

    # ---- routing -----------------------------------------------------------------
    def _bots(self) -> list[Sender]:
        return ([self.primary] if self.primary else []) + self.helpers

    def _all(self) -> list[Sender]:
        return self._bots() + self.lanes

    def _limits_for(self, sender: Sender, kind: str) -> tuple[int, float]:
        limit, window = self.limits[kind]
        if kind == "send":    # a webhook lane has limits of its own
            limit, window = sender.send_limit or limit, sender.send_window or window
        if kind == "react":   # a bot that got 429s on reactions is spaced out more (see `_learn`)
            window = max(window, sender.react_spacing)
        return limit, window

    def _pick(self, kind: str, channel_id: int, now: float, exclude: set[Sender]) -> Sender | None:
        best, best_key = None, None
        for sender in self._all():
            if sender in exclude or not sender.ready or sender.blocked(kind, channel_id, now):
                continue
            if (sender.channel and sender.channel != channel_id) or (kind == "react" and not sender.can_react):
                continue
            limit, window = self._limits_for(sender, kind)
            wait = round(sender.wait_for(kind, channel_id, now, limit, window), 3)
            # soonest first; on a tie bots before lanes, then the least used, helpers before the main bot
            key = (wait, sender.lane, sender.load(now, self.limits["send"][1]), sender.last_used, sender.primary)
            if best_key is None or key < best_key:
                best, best_key = sender, key
        return best

    async def _admit(self, sender: Sender, kind: str, channel_id: int) -> None:
        """Reserve the sender's next slot and, if it isn't free yet, wait for it."""
        limit, window = self._limits_for(sender, kind)
        now = time.monotonic()
        wait = sender.wait_for(kind, channel_id, now, limit, window)
        at = now + wait
        sender.reserve(kind, channel_id, at)
        self.admitted += 1
        self.waits.append(wait)
        shifted = sender.shifted(kind, channel_id)
        while True:   # a 429 may push the planned time back while we sleep (Sender.push_back)
            remaining = at + (sender.shifted(kind, channel_id) - shifted) - time.monotonic()
            if remaining <= 0:
                break
            await asyncio.sleep(remaining)

    def _context(self, bot: str, kind: str, channel_id: int) -> dict:
        """What this program had planned for a bot when Discord answered 429 (for the diagnostics)."""
        if kind == "wsend":     # `channel_id` is the webhook's id for these
            sender = next((l for l in self.lanes if l.webhook_id == channel_id), None)
            if sender is None:
                return {}
            kind, channel_id, window = "send", sender.channel, self._limits_for(sender, "send")[1]
        else:
            sender = next((s for s in self._bots() if s.name == bot), None)
            if sender is None or kind not in ("send", "react"):
                return {}
            window = self.limits["send"][1] if kind == "send" else 1.0
        now = time.monotonic()
        slots = sender._slots.get((kind, channel_id), ())
        return {"reservas": sum(1 for t in slots if now - window < t <= now), "ventana_s": window}

    def _learn(self, event: dict) -> None:
        """React to what Discord answers: after a 429 move the pending requests out of the way, and adapt the
        spacing of reactions (wider after an episode of 429s, narrower after many clean reactions)."""
        if event["kind"] == "wsend":
            self._learn_lane(event)
            return
        if event["kind"] not in ("react", "send"):
            return
        sender = next((s for s in self._bots() if s.name == event["bot"]), None)
        if sender is None:
            return
        now = time.monotonic()
        base = self.limits["react"][1]
        current = max(base, sender.react_spacing)
        if event["status"] == 429:
            wait = event.get("reset_after") or (0.25 if event["kind"] == "react" else 1.0)
            if event["kind"] == "react":
                # discord.py resends this one after `wait`; the next planned reaction must come a full spacing later
                sender.push_back("react", event["channel"], now, now + wait + current)
                if now - sender.react_429_at > 1.0:     # one step per episode, not per 429 of the same episode
                    sender.react_spacing = min(MAX_REACTION_SPACING, current + 0.05)
                sender.react_429_at = now
                sender.react_clean = 0
            else:
                sender.push_back("send", event["channel"], now, now + wait + 0.05)
        elif event["kind"] == "react" and 200 <= event["status"] < 300:
            sender.react_clean += 1
            reset = event.get("reset_after")
            if reset and reset + 0.03 > current:
                sender.react_spacing = min(MAX_REACTION_SPACING, reset + 0.03)   # Discord said so itself
            elif sender.react_clean >= 20 and sender.react_spacing > base:
                sender.react_spacing = max(base, sender.react_spacing * 0.92)
                sender.react_clean = 0

    def _learn_lane(self, event: dict) -> None:
        """A webhook's limits are not the bots': take them from what Discord says about this very webhook."""
        lane = next((l for l in self.lanes if l.webhook_id == event.get("webhook")), None)
        if lane is None:
            return
        now = time.monotonic()
        if event["status"] == 429:
            wait = event.get("reset_after") or 1.0
            lane.push_back("send", lane.channel, now, now + wait + 0.05)     # the ledger is shared: moves for every lane
            if now - lane.send_429_at > 1.0:      # one widening per episode of 429s
                for peer in self.lanes:
                    peer.send_window = min(WINDOW_SECONDS, (lane.send_window or WEBHOOK_WINDOW) * 1.25)
            for peer in self.lanes:
                peer.send_429_at = now
        elif 200 <= event["status"] < 300 and event.get("limit"):
            remaining, reset = event.get("remaining"), event.get("reset_after")
            for peer in self.lanes:
                peer.send_limit = max(1, int(event["limit"]))
                if remaining is not None and reset and event["limit"] - remaining <= 1:   # first message of a window
                    peer.send_window = min(WINDOW_SECONDS, max(1.0, reset + 0.2))

    def _remember(self, message_id: int, channel_id: int, sender: Sender) -> None:
        self._owners[message_id] = sender
        self._owners.move_to_end(message_id)
        while len(self._owners) > OWNER_MEMORY:
            self._owners.popitem(last=False)
        if channel_id in self.sticky_channels and sender.user_id:
            self._sticky[message_id] = sender.user_id
            self._sticky.move_to_end(message_id)
            while len(self._sticky) > STICKY_MEMORY:
                self._sticky.popitem(last=False)
            self._sticky_dirty = True

    async def _route_send(self, channel_id, *, params):
        channel_id = int(channel_id)
        if has_components(params):
            await self._admit(self.primary, "send", channel_id)
            return await self._send_via(self.primary, channel_id, params)

        tried: set[Sender] = set(self.lanes) if needs_a_bot(params) else set()
        last_error: BaseException | None = None
        redone: set[Sender] = set()
        gave_up = 0
        while True:
            sender = self._pick("send", channel_id, time.monotonic(), tried)
            if sender is None:
                if last_error is not None:
                    raise last_error
                sender = self.primary
            await self._admit(sender, "send", channel_id)
            try:
                if self._open:
                    return await self._send_via(sender, channel_id, params)
                async with sender.channel_lock(channel_id):
                    return await self._send_via(sender, channel_id, params)
            except aiohttp.ServerDisconnectedError as exc:
                # a keep-alive connection that died while idle: the next try opens a fresh one
                if sender in redone:
                    if sender.primary:
                        raise
                    last_error = exc
                else:
                    redone.add(sender)
                    _reset_files(params)
                    continue
            except discord.HTTPException as exc:
                if exc.status == 429 and gave_up < SEND_RETRIES:
                    # discord.py gave up after 5 rate-limited tries: the message is NOT lost, plan it again (the
                    # tracer already moved what was planned behind the 429). The lanes share one limit: skip them all.
                    gave_up += 1
                    sender.stats.failed += 1
                    if sender.lane:
                        tried.update(self.lanes)
                    _reset_files(params)
                    continue
                # a sender that cannot write here is skipped; a webhook that Discord refuses (deleted, bad request)
                # is skipped too. Anything else (e.g. discord.py giving up on a 429) is the caller's to handle.
                refused = isinstance(exc, (discord.Forbidden, discord.NotFound)) or (sender.lane and exc.status in (400, 401))
                if sender.primary or not refused:
                    raise
                if exc.status != 400:
                    sender.block(channel_id, time.monotonic(), BLOCK_SECONDS)
                if sender.lane and exc.status in (401, 404):
                    self._lane_gone(sender)
                log.warning("%s cannot write in channel %s (%s); skipping it there",
                            "webhook of " + sender.owner.name if sender.lane and sender.owner else "helper " + sender.name,
                            channel_id, exc.status)
                last_error = exc
            except _UNREACHABLE as exc:
                if sender.primary:
                    raise
                log.warning("helper %s unreachable (%s)", sender.name, exc)
                last_error = exc
            sender.stats.failed += 1
            tried.add(sender)
            _reset_files(params)

    async def _send_via(self, sender: Sender, channel_id: int, params):
        started = time.monotonic()
        data = await sender.endpoints.send_message(channel_id, params=params)
        elapsed = time.monotonic() - started
        sender.stats.sent += 1
        sender.last_used = time.monotonic()
        if not getattr(params, "files", None):
            sender.latencies.append(elapsed)
            if elapsed > SLOW_SEND_SECONDS:
                sender.stats.held_back += 1
                sender.penalty_until = time.monotonic() + PENALTY_SECONDS
        if isinstance(data, dict) and data.get("id"):
            self._remember(int(data["id"]), channel_id, sender)
        return data

    async def send_as(self, channel_id, *, content: str, username: str, avatar_url: str | None = None):
        """Post as `username` (with that picture) through a webhook lane; nobody is pinged.

        Returns the message data, or None when there is no lane that can do it (no webhooks, or all refused),
        so the caller can fall back to writing it as the bot.
        """
        channel_id = int(channel_id)
        payload = {"content": content, "username": webhooks.lane_name(username)[:80] or "Jugador",
                   "allowed_mentions": {"parse": []}}
        if avatar_url:
            payload["avatar_url"] = avatar_url
        params = SimpleNamespace(payload=payload, files=None, multipart=None)
        tried: set[Sender] = set(self._bots())
        for _ in range(SEND_RETRIES + 1):
            lane = self._pick("send", channel_id, time.monotonic(), tried)
            if lane is None:
                return None
            await self._admit(lane, "send", channel_id)
            try:
                return await self._send_via(lane, channel_id, params)
            except discord.HTTPException as exc:
                lane.stats.failed += 1
                if exc.status == 429:
                    continue                      # the tracer moved the plan back: ask again
                if exc.status in (401, 404):
                    self._lane_gone(lane)
                tried.add(lane)
            except _UNREACHABLE:
                tried.add(lane)
        return None

    async def _route_react(self, channel_id, message_id, emoji):
        channel_id = int(channel_id)
        tried: set[Sender] = set()
        last_error: BaseException | None = None
        gave_up = 0
        while True:
            sender = self._pick("react", channel_id, time.monotonic(), tried)
            if sender is None:
                if last_error is not None:
                    raise last_error
                sender = self.primary
            await self._admit(sender, "react", channel_id)
            try:
                result = await sender.endpoints.add_reaction(channel_id, message_id, emoji)
            except (discord.Forbidden, discord.NotFound) as exc:
                # the message may simply be gone; only a helper is worth retrying elsewhere
                if sender.primary:
                    raise
                sender.block(channel_id, time.monotonic(), BLOCK_SECONDS, kinds=("react",))
                last_error = exc
            except _UNREACHABLE as exc:
                if sender.primary:
                    raise
                last_error = exc
            except discord.HTTPException as exc:
                # discord.py gave up after 5 rate-limited tries. The tracer already widened this bot's spacing:
                # go through admission again instead of losing the player's reaction.
                if exc.status != 429 or gave_up >= REACT_RETRIES:
                    raise
                gave_up += 1
                sender.stats.failed += 1
                continue
            else:
                sender.stats.reactions += 1
                sender.last_used = time.monotonic()
                return result
            sender.stats.failed += 1
            tried.add(sender)

    # ---- who wrote a message -------------------------------------------------------
    def _by_user_id(self, user_id: int) -> Sender | None:
        return next((s for s in self._all() if s.user_id == user_id), None)

    def _order_for(self, message_id: int) -> list[Sender]:
        message_id = int(message_id)
        owner = self._owners.get(message_id)
        if owner is None and message_id in self._sticky:
            owner = self._by_user_id(self._sticky[message_id])
        rest = [s for s in self._all() if s.ready and s is not owner]
        rest.sort(key=lambda s: s.lane)          # bots first: a lane only knows its own messages
        return ([owner] if owner and owner.ready else []) + rest

    async def _route_edit(self, channel_id, message_id, *, params):
        last: BaseException | None = None
        for sender in self._order_for(message_id):
            try:
                data = await sender.endpoints.edit_message(channel_id, message_id, params=params)
            except (discord.Forbidden, discord.NotFound) as exc:
                if isinstance(exc, discord.NotFound) and not sender.lane:
                    raise                           # the message itself is gone
                last = exc                          # not the author (a lane answers 404 for foreign messages): next
                _reset_files(params)
                continue
            sender.stats.edited += 1
            self._remember(int(message_id), int(channel_id), sender)
            return data
        raise last or RuntimeError("no sender available")

    async def _route_delete(self, channel_id, message_id, *, reason=None):
        last: BaseException | None = None
        for sender in self._order_for(message_id):
            try:
                result = await sender.endpoints.delete_message(channel_id, message_id, reason=reason)
            except (discord.Forbidden, discord.NotFound) as exc:
                if isinstance(exc, discord.NotFound) and not sender.lane:
                    raise
                last = exc
                continue
            sender.stats.deleted += 1
            self._owners.pop(int(message_id), None)
            self._sticky.pop(int(message_id), None)
            return result
        raise last or RuntimeError("no sender available")

    def _forget(self, message_id: int) -> None:
        self._owners.pop(message_id, None)
        self._sticky.pop(message_id, None)

    async def delete_many(self, channel_id: int, message_ids) -> dict:
        """Delete many messages as fast as Discord allows. Returns {"requested", "deleted", "bulk", "failed", "seconds"}.

        First tries bulk delete (100 per call) with the main bot, which is the one whose owner usually gave it
        Manage Messages (helpers are invited without it); whatever is left is deleted one by one, every bot
        taking care of its own messages at the same time.
        """
        started = time.monotonic()
        channel_id = int(channel_id)
        pending = list(dict.fromkeys(int(m) for m in message_ids))
        result = {"requested": len(pending), "deleted": 0, "bulk": 0, "failed": 0, "seconds": 0.0}

        for sender in [self.primary] if self.primary else []:
            if sender.endpoints.bulk_delete is None or sender.user_id in self._no_bulk:
                continue
            while len(pending) >= 2:
                chunk, rest = pending[:BULK_DELETE_MAX], pending[BULK_DELETE_MAX:]
                try:
                    await sender.endpoints.bulk_delete(channel_id, chunk)
                except discord.Forbidden:
                    self._no_bulk.add(sender.user_id)   # no Manage Messages: don't ask again
                    break
                except (discord.HTTPException, *_UNREACHABLE):
                    break                               # e.g. messages older than two weeks: go one by one
                for mid in chunk:
                    self._forget(mid)
                sender.stats.deleted += len(chunk)
                result["deleted"] += len(chunk)
                result["bulk"] += len(chunk)
                pending = rest

        groups: dict[Sender, list[int]] = {}
        for mid in pending:
            owner = self._order_for(mid)[:1]
            groups.setdefault(owner[0] if owner else self.primary, []).append(mid)

        async def drain(sender: Sender, mids: list[int]) -> None:
            gate = asyncio.Semaphore(DELETE_PARALLEL)

            async def one(mid: int) -> None:
                async with gate:
                    try:
                        await self._route_delete(channel_id, mid)
                    except discord.NotFound:
                        result["deleted"] += 1            # already gone is as good as deleted
                    except Exception:  # noqa: BLE001
                        result["failed"] += 1
                    else:
                        result["deleted"] += 1

            await asyncio.gather(*(one(m) for m in mids))

        await asyncio.gather(*(drain(s, m) for s, m in groups.items()))
        result["seconds"] = round(time.monotonic() - started, 2)
        return result

    # ---- persistence of who wrote the sticky messages ----------------------------------
    def load_owners(self) -> None:
        if self.owners_file is None or not self.owners_file.exists():
            return
        try:
            raw = json.loads(self.owners_file.read_text(encoding="utf-8"))
            self._sticky = OrderedDict((int(m), int(u)) for m, u in raw.items())
        except (OSError, ValueError):
            log.warning("could not read %s; starting without it", self.owners_file)

    def save_owners(self) -> None:
        if self.owners_file is None or not self._sticky_dirty:
            return
        try:
            tmp = self.owners_file.with_suffix(".tmp")
            tmp.write_text(json.dumps({str(m): u for m, u in self._sticky.items()}), encoding="utf-8")
            tmp.replace(self.owners_file)
            self._sticky_dirty = False
        except OSError:
            log.warning("could not save %s", self.owners_file)

    # ---- information for the UI ----------------------------------------------------
    def snapshot(self) -> list[dict]:
        return [s.snapshot() for s in self._all()]

    def ready_count(self) -> int:
        return sum(1 for s in self._bots() if s.ready)

    def _changed(self) -> None:
        if self.on_change is not None:
            try:
                self.on_change()
            except Exception:  # noqa: BLE001
                log.exception("on_change failed")

    # Same routes the bot's own calls take; the performance test uses them.
    async def send_text(self, channel_id: int, text: str):
        return await self._route_send(channel_id, params=_plain_params(text))

    async def add_reaction(self, channel_id: int, message_id: int, emoji: str):
        return await self._route_react(channel_id, message_id, emoji)

    async def delete_message(self, channel_id: int, message_id: int):
        return await self._route_delete(channel_id, message_id)

    async def test_send(self, sender: Sender, channel_id: int) -> str:
        """Send (and delete) a short message with one sender. Returns '' on success or a message."""
        try:
            data = await sender.endpoints.send_message(
                channel_id, params=_plain_params(f"🔧 Prueba de **{sender.name}**: este mensaje se borra solo."))
            await asyncio.sleep(2.5)
            await sender.endpoints.delete_message(channel_id, int(data["id"]), reason="test")
            return ""
        except discord.Forbidden:
            return "No tiene permiso para escribir en ese canal (o no está en el servidor)."
        except discord.NotFound:
            return "No ve ese canal: ¿está invitado a ese servidor?"
        except Exception as exc:  # noqa: BLE001
            return f"{type(exc).__name__}: {exc}"


def _plain_params(content: str):
    from discord.http import MultipartParameters
    return MultipartParameters(payload={"content": content}, multipart=None, files=None)


def invite_url(client_id: int) -> str:
    return discord.utils.oauth_url(client_id, permissions=INVITE_PERMISSIONS, scopes=("bot",))


@dataclass
class TokenInfo:
    user_id: int
    name: str
    invite: str = field(default="")


async def inspect_token(token: str) -> TokenInfo:
    """Log in briefly to learn who a token belongs to (raises discord.LoginFailure etc.)."""
    client = discord.Client(intents=discord.Intents.none())
    try:
        await client.login(token.strip())
        return TokenInfo(client.user.id, str(client.user), invite_url(client.user.id))
    finally:
        await client.close()
