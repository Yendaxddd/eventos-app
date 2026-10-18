"""Rate-limit plumbing shared by every sender: which routes discord.py must not block on.

discord.py serialises requests per bucket and, when a request finishes, computes
`remaining - still_in_flight`; if that is <= 0 it makes the call wait for the whole window to reset (the
message is already posted, but `await send()` doesn't return). With three or four sends in flight on
one bot that happens although plenty of quota is left, and the code awaiting the send (QTE timers!) is
stalled for seconds. The pool already does the pacing, so for the message, reaction, webhook and ping
routes it hands discord.py an "open" bucket that never blocks. Real 429s are still handled by discord.py's
own retry loop. If a future discord.py no longer exposes `get_ratelimit`, the pool falls back to sending
one message at a time per bot and channel (see `Sender.channel_lock`), which avoids the stall the slow way.
"""

from __future__ import annotations

import discord

SEND_ROUTE = "POST /channels/{channel_id}/messages"
REACT_ROUTE = "PUT /channels/{channel_id}/messages/{message_id}/reactions/{emoji}/@me"
PING_ROUTE = "GET /gateway"
WEBHOOK_SEND_ROUTE = "POST /webhooks/{webhook_id}/{webhook_token}"
OPEN_ROUTES = (SEND_ROUTE, REACT_ROUTE, PING_ROUTE, WEBHOOK_SEND_ROUTE)


class OpenBucket:
    """Stands in for discord.py's `Ratelimit`: never blocks (the pool does the pacing)."""

    limit = remaining = 1_000_000
    outgoing = 0
    reset_after = 0.0
    expires = None
    dirty = True

    async def __aenter__(self) -> "OpenBucket":
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    def update(self, response, *, use_clock: bool = False) -> None:
        return None

    def reset(self) -> None:
        return None

    def is_expired(self) -> bool:
        return False

    def is_inactive(self) -> bool:
        return True


_OPEN = OpenBucket()


def can_open_buckets(http) -> bool:
    return callable(getattr(http, "get_ratelimit", None)) and hasattr(discord.http, "Ratelimit")


def open_buckets(http) -> None:
    """Make the message / reaction / ping routes of this HTTP client non-blocking."""
    original = http.get_ratelimit

    def get_ratelimit(key: str):
        head = key.rpartition(":")[0]  # "<route or bucket hash>:<major parameters>"
        if head in OPEN_ROUTES or head in {http._bucket_hashes.get(r) for r in OPEN_ROUTES}:
            return _OPEN
        return original(key)

    http.get_ratelimit = get_ratelimit
