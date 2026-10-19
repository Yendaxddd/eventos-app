"""Discord Activity: a web app that runs inside Discord, mirrors the event channel, lets the players write and
answer QTEs with buttons timed on their own screen.

* `hub`      -- who is connected, broadcasting, round-trip measurements, the recent-messages backlog, running QTEs.
* `prefs`    -- each player's display settings (theme, text size, size and place of the QTE buttons...).
* `latency`  -- each player's latency adjustment: network delay added, device lag taken off, with a cap.
* `qte`      -- `QteBook` (the bot's active QTEs, announcing starts/ends) and the button press dressed as a message.
* `auth`     -- OAuth2 code exchange and "who is this token" checks against Discord.
* `server`   -- the local aiohttp server: static client, `/api/token`, `/ws`.
* `bridge`   -- connects the bot (messages of the event channel, who may join) to the hub.
* `tunnel`   -- a free Cloudflare quick tunnel so Discord's proxy can reach the local server.
"""

from .auth import AuthError, DiscordAuth, Identity
from .bridge import ActivityBridge, serialize_message
from .hub import Conn, Hub, RpcError
from .latency import LatencyBook
from .prefs import PrefsStore
from .server import ActivityServer
from .tunnel import TailscaleTunnel, Tunnel

__all__ = ["ActivityBridge", "ActivityServer", "AuthError", "Conn", "DiscordAuth", "Hub", "Identity", "LatencyBook", "PrefsStore", "RpcError",
           "TailscaleTunnel", "Tunnel", "serialize_message"]
