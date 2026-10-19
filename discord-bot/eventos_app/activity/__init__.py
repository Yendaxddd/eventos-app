"""Discord Activity: a web app that runs inside Discord and mirrors the event channel (phase 0: read only).

* `hub`      -- who is connected, broadcasting, clock-sync statistics, the recent-messages backlog.
* `auth`     -- OAuth2 code exchange and "who is this token" checks against Discord.
* `server`   -- the local aiohttp server: static client, `/api/token`, `/ws`.
* `bridge`   -- connects the bot (messages of the event channel, who may join) to the hub.
* `tunnel`   -- a free Cloudflare quick tunnel so Discord's proxy can reach the local server.
"""

from .auth import AuthError, DiscordAuth, Identity
from .bridge import ActivityBridge, serialize_message
from .hub import Conn, Hub
from .server import ActivityServer
from .tunnel import Tunnel

__all__ = ["ActivityBridge", "ActivityServer", "AuthError", "Conn", "DiscordAuth", "Hub", "Identity", "Tunnel",
           "serialize_message"]
