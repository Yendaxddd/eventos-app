"""A tiny fake of the Discord REST API, enough to exercise discord.py's real HTTP client:

* tokens identify bots (`Authorization: Bot <token>`)
* sending is rate limited per (bot, channel): `limit` messages per `window` seconds, with the same
  X-RateLimit-* headers Discord sends and a 429 when exceeded
* per-bot channel access (403 "Missing Access" when denied)
* messages remember their author: only the author may edit them (403 50005 otherwise)
"""

from __future__ import annotations

import asyncio
import itertools
import json
import time

import discord.http
from aiohttp import web


def _json(data, status: int = 200, headers: dict | None = None) -> web.Response:
    # discord.py only parses a body whose content-type is exactly "application/json" (no charset)
    return web.Response(body=json.dumps(data).encode(), status=status, headers=headers,
                        content_type="application/json")


class FakeDiscord:
    def __init__(self, *, limit: int = 5, window: float = 1.0, latency: float = 0.02,
                 reaction_window: float = 0.25) -> None:
        self.limit, self.window, self.latency = limit, window, latency
        self.reaction_window = reaction_window
        self.reactions: list[dict] = []        # every reaction attempt, including 429s
        self.gateway_hits: dict[str, int] = {}  # keep-alive pings per token
        self.connections: set[int] = set()      # client ports seen (= distinct TCP connections)
        self.edit_attempts: list[tuple[str, int]] = []  # (token, status)
        self._reaction_buckets: dict[tuple[str, int], float] = {}
        self.in_flight: dict[tuple[str, int], int] = {}
        self.max_in_flight: dict[tuple[str, int], int] = {}
        self.bots: dict[str, int] = {}        # token -> user id
        self.denied: set[tuple[str, int]] = set()  # (token, channel) without access
        self.messages: dict[int, dict] = {}
        self.requests: list[dict] = []        # every send attempt, including 429s
        self._buckets: dict[tuple[str, int], list] = {}  # (token, channel) -> [window_start, used]
        self._ids = itertools.count(1000)
        self._runner: web.AppRunner | None = None
        self._old_base: str | None = None
        self.port = 0

    def add_bot(self, token: str, user_id: int) -> None:
        self.bots[token] = user_id

    def add_message(self, channel_id: int, author_token: str, content: str = "") -> int:
        """A message that already exists (e.g. what a player typed)."""
        mid = next(self._ids)
        self.messages[mid] = {"id": mid, "channel": channel_id, "author_token": author_token, "content": content,
                              "files": [], "components": None}
        return mid

    def deny(self, token: str, channel_id: int) -> None:
        self.denied.add((token, channel_id))

    # ---- lifecycle --------------------------------------------------------------
    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/api/v10/users/@me", self._me)
        app.router.add_get("/api/v10/oauth2/applications/@me", self._application)
        app.router.add_get("/api/v10/gateway", self._gateway)
        app.router.add_put("/api/v10/channels/{cid}/messages/{mid}/reactions/{emoji}/@me", self._react)
        app.router.add_get("/api/v10/channels/{cid}", self._channel)
        app.router.add_post("/api/v10/channels/{cid}/messages", self._send)
        app.router.add_patch("/api/v10/channels/{cid}/messages/{mid}", self._edit)
        app.router.add_delete("/api/v10/channels/{cid}/messages/{mid}", self._delete)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", 0)
        await site.start()
        self.port = site._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
        self._old_base = discord.http.Route.BASE
        discord.http.Route.BASE = f"http://127.0.0.1:{self.port}/api/v10"

    async def stop(self) -> None:
        if self._old_base is not None:
            discord.http.Route.BASE = self._old_base
        if self._runner:
            await self._runner.cleanup()

    # ---- helpers ------------------------------------------------------------------
    def _token(self, request: web.Request) -> str | None:
        header = request.headers.get("Authorization", "")
        token = header.removeprefix("Bot ").strip()
        return token if token in self.bots else None

    @staticmethod
    def _error(status: int, code: int, message: str) -> web.Response:
        return _json({"code": code, "message": message}, status=status)

    def sent_by(self, token: str) -> list[dict]:
        return [m for m in self.messages.values() if m["author_token"] == token]

    # ---- endpoints ------------------------------------------------------------------
    async def _me(self, request: web.Request) -> web.Response:
        token = self._token(request)
        if token is None:
            return self._error(401, 0, "401: Unauthorized")
        uid = self.bots[token]
        return _json({"id": str(uid), "username": f"bot{uid}", "discriminator": "0",
                      "global_name": None, "avatar": None, "bot": True})

    async def _application(self, request: web.Request) -> web.Response:
        token = self._token(request)
        if token is None:
            return self._error(401, 0, "401: Unauthorized")
        uid = self.bots[token]
        return _json({"id": str(uid), "name": f"bot{uid}", "description": "", "icon": None, "verify_key": "00",
                      "flags": 0, "bot_public": True, "bot_require_code_grant": False,
                      "owner": {"id": "1", "username": "owner", "discriminator": "0", "avatar": None}})

    def _note_connection(self, request: web.Request) -> None:
        peer = request.transport.get_extra_info("peername") if request.transport else None
        if peer:
            self.connections.add(peer[1])

    async def _gateway(self, request: web.Request) -> web.Response:
        self._note_connection(request)
        token = self._token(request) or "?"
        self.gateway_hits[token] = self.gateway_hits.get(token, 0) + 1
        await asyncio.sleep(self.latency)
        return _json({"url": "wss://gateway.fake"})

    async def _react(self, request: web.Request) -> web.Response:
        """Reactions: 1 per `reaction_window` per (bot, channel), like Discord's ~250 ms bucket."""
        self._note_connection(request)
        token = self._token(request)
        if token is None:
            return self._error(401, 0, "401: Unauthorized")
        channel, mid = int(request.match_info["cid"]), int(request.match_info["mid"])
        await asyncio.sleep(self.latency)
        now = time.monotonic()
        entry = {"t": now, "token": token, "message": mid, "emoji": request.match_info["emoji"], "status": 204}
        self.reactions.append(entry)
        if (token, channel) in self.denied:
            entry["status"] = 403
            return self._error(403, 50001, "Missing Access")
        if mid not in self.messages:
            entry["status"] = 404
            return self._error(404, 10008, "Unknown Message")
        last = self._reaction_buckets.get((token, channel))
        headers = {"X-RateLimit-Limit": "1", "X-RateLimit-Bucket": f"react-{channel}-{token}"}
        if last is not None and now - last < self.reaction_window:
            retry = self.reaction_window - (now - last)
            entry["status"] = 429
            headers.update({"Retry-After": f"{retry:.3f}", "X-RateLimit-Remaining": "0", "Via": "1.1 fake-edge",
                            "X-RateLimit-Reset-After": f"{retry:.3f}", "X-RateLimit-Scope": "user"})
            return _json({"message": "You are being rate limited.", "retry_after": retry, "global": False},
                         status=429, headers=headers)
        self._reaction_buckets[(token, channel)] = now
        headers.update({"X-RateLimit-Remaining": "0", "X-RateLimit-Reset-After": f"{self.reaction_window:.3f}"})
        self.messages[mid].setdefault("reactions", []).append((token, entry["emoji"]))
        return web.Response(status=204, headers=headers)

    async def _channel(self, request: web.Request) -> web.Response:
        token = self._token(request)
        channel = int(request.match_info["cid"])
        if token is None:
            return self._error(401, 0, "401: Unauthorized")
        if (token, channel) in self.denied:
            return self._error(403, 50001, "Missing Access")
        return _json({"id": str(channel), "type": 0, "name": "qte", "guild_id": "1"})

    async def _send(self, request: web.Request) -> web.Response:
        token = self._token(request)
        if token is None:
            return self._error(401, 0, "401: Unauthorized")
        channel = int(request.match_info["cid"])
        self._note_connection(request)
        key = (token, channel)
        self.in_flight[key] = self.in_flight.get(key, 0) + 1
        self.max_in_flight[key] = max(self.max_in_flight.get(key, 0), self.in_flight[key])
        try:
            await asyncio.sleep(self.latency)  # a network round trip, so overlapping sends really overlap
            return await self._handle_send(request, token, channel)
        finally:
            self.in_flight[key] -= 1

    async def _handle_send(self, request: web.Request, token: str, channel: int) -> web.Response:
        # read the whole body first, like a real server, so the connection stays reusable on error answers
        content, files, payload = "", [], {}
        if request.content_type.startswith("multipart/"):
            reader = await request.multipart()
            async for part in reader:
                data = await part.read()
                if part.name == "payload_json":
                    payload = json.loads(data)
                    content = payload.get("content", "")
                else:
                    files.append({"name": part.filename, "size": len(data)})
        else:
            payload = await request.json()
            content = payload.get("content", "")
        now = time.monotonic()
        entry = {"t": now, "token": token, "channel": channel, "status": 200}
        self.requests.append(entry)
        if (token, channel) in self.denied:
            entry["status"] = 403
            return self._error(403, 50001, "Missing Access")

        bucket = self._buckets.get((token, channel))
        if bucket is None or now - bucket[0] >= self.window:
            bucket = self._buckets[(token, channel)] = [now, 0]
        headers = {"X-RateLimit-Limit": str(self.limit), "X-RateLimit-Bucket": f"send-{channel}-{token}"}
        if bucket[1] >= self.limit:
            retry = max(0.01, self.window - (now - bucket[0]))
            entry["status"] = 429
            headers.update({"Retry-After": f"{retry:.3f}", "X-RateLimit-Remaining": "0", "Via": "1.1 fake-edge",
                            "X-RateLimit-Reset-After": f"{retry:.3f}", "X-RateLimit-Scope": "user"})
            return _json({"message": "You are being rate limited.", "retry_after": retry, "global": False},
                         status=429, headers=headers)
        bucket[1] += 1
        remaining = self.limit - bucket[1]
        reset_after = self.window - (now - bucket[0])
        headers.update({"X-RateLimit-Remaining": str(remaining), "X-RateLimit-Reset-After": f"{reset_after:.3f}",
                        "X-RateLimit-Reset": f"{time.time() + reset_after:.3f}"})

        mid = next(self._ids)
        self.messages[mid] = {"id": mid, "channel": channel, "author_token": token, "content": content,
                              "files": files, "components": payload.get("components")}
        entry["message_id"] = mid
        return _json(self._message_json(mid), headers=headers)

    def _message_json(self, mid: int) -> dict:
        m = self.messages[mid]
        uid = self.bots[m["author_token"]]
        return {
            "id": str(mid), "channel_id": str(m["channel"]), "content": m["content"],
            "author": {"id": str(uid), "username": f"bot{uid}", "discriminator": "0", "avatar": None, "bot": True},
            "timestamp": "2026-01-01T00:00:00+00:00", "edited_timestamp": None, "tts": False,
            "mention_everyone": False, "mentions": [], "mention_roles": [], "attachments": [],
            "embeds": [], "pinned": False, "type": 0, "flags": 0,
        }

    async def _edit(self, request: web.Request) -> web.Response:
        token = self._token(request)
        mid = int(request.match_info["mid"])
        msg = self.messages.get(mid)
        if token is None:
            return self._error(401, 0, "401: Unauthorized")
        if msg is None:
            return self._error(404, 10008, "Unknown Message")
        if msg["author_token"] != token:
            self.edit_attempts.append((token, 403))
            return self._error(403, 50005, "Cannot edit a message authored by another user")
        self.edit_attempts.append((token, 200))
        payload = await request.json()
        msg["content"] = payload.get("content", msg["content"])
        msg["edited_by"] = token
        return _json(self._message_json(mid))

    async def _delete(self, request: web.Request) -> web.Response:
        token = self._token(request)
        mid = int(request.match_info["mid"])
        msg = self.messages.get(mid)
        if token is None:
            return self._error(401, 0, "401: Unauthorized")
        if msg is None:
            return self._error(404, 10008, "Unknown Message")
        if msg["author_token"] != token:
            return self._error(403, 50013, "Missing Permissions")
        del self.messages[mid]
        return web.Response(status=204)
