"""The local web server behind the Activity: static client, token exchange and the WebSocket.

Discord's proxy forwards the Activity's requests here through a public tunnel (see `tunnel`), under the
magic prefix `/.proxy` (which Discord strips before forwarding, and which is accepted here too just in case).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import mimetypes
import re
import shutil
import tempfile
import time
import zlib
from pathlib import Path
from typing import Awaitable, Callable
from urllib.parse import urlsplit

import aiohttp
from aiohttp import web
from yarl import URL

from .auth import AuthError, DiscordAuth
from .hub import Conn, Hub

log = logging.getLogger("eventos_app.activity")

DEFAULT_PORT = 8765
HELLO_TIMEOUT = 10.0
MAX_FRAME = 64 * 1024
# Pictures and clips the mirror shows come through this server (no URL Mappings needed in the Developer Portal),
# and only from Discord's own hosts.
MEDIA_HOSTS = re.compile(r"^(cdn\.discordapp\.com|media\.discordapp\.net|images-ext-\d+\.discordapp\.net)$")
MAX_MEDIA = 25 * 1024 * 1024
MEDIA_CACHE_LIMIT = 200 * 1024 * 1024
MEDIA_REDIRECTS = 3
_EXTENSIONS = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp", "video/mp4": ".mp4", "video/webm": ".webm"}
Fetch = Callable[[str], Awaitable[tuple[str, bytes]]]   # url -> (content type, body); raises ValueError / OSError
Authorize = Callable[[int], Awaitable[dict]]   # user id -> {"name": ..., "avatar": ...}; raises AuthError

_FALLBACK = ("<!doctype html><meta charset=utf-8><title>Eventos App</title><body style='font:16px sans-serif;"
             "padding:2rem'><h1>La Actividad todavía no está construida</h1><p>Falta la carpeta "
             "<code>eventos_app/activity/web</code> (se genera con <code>npm run build</code> en "
             "<code>activity_client/</code>; el instalador ya la incluye).</p>")


def is_local_request(request: web.Request) -> bool:
    """True only for a browser on this very PC. A request that came through the public tunnel never is."""
    headers = request.headers
    if any(headers.get(h) for h in ("CF-Connecting-IP", "Cf-Ray", "X-Forwarded-For", "Forwarded", "X-Real-IP")):
        return False
    host = request.host.rsplit(":", 1)[0].strip("[]")
    return request.remote in ("127.0.0.1", "::1") and host in ("127.0.0.1", "localhost", "::1")


class ActivityServer:
    def __init__(self, hub: Hub, *, auth: DiscordAuth, authorize: Authorize, web_dir: Path, client_id: int,
                 host: str = "127.0.0.1", port: int = DEFAULT_PORT, allow_dev: bool = True, actions=None,
                 media_dir: Path | None = None, media_fetch: Fetch | None = None) -> None:
        self.hub, self.auth, self.authorize = hub, auth, authorize
        self.actions = actions     # what the players can do (write, press a QTE button): see ActivityBridge.say / press
        self.web_dir = Path(web_dir)
        self.client_id = client_id
        self.host, self.port = host, port
        self.allow_dev = allow_dev
        self._runner: web.AppRunner | None = None
        self.media_dir = Path(media_dir) if media_dir else None
        self._media_fetch = media_fetch or self._download
        self._media_locks: dict[str, asyncio.Lock] = {}
        self._media_session: aiohttp.ClientSession | None = None
        self._media_writes = 0

    # ---- lifecycle ----------------------------------------------------------------------------
    def _app(self) -> web.Application:
        app = web.Application(client_max_size=MAX_FRAME)
        for prefix in ("", "/.proxy"):
            app.router.add_get(f"{prefix}/api/config", self._config)
            app.router.add_post(f"{prefix}/api/token", self._token)
            app.router.add_get(f"{prefix}/ws", self._ws)
            app.router.add_get(f"{prefix}/healthz", self._health)
            app.router.add_get(f"{prefix}/media", self._media)
            app.router.add_get(f"{prefix}/", self._index)
        for prefix in ("/.proxy/", "/"):
            if self.web_dir.is_dir():
                app.router.add_static(prefix, self.web_dir, follow_symlinks=False)
        return app

    async def start(self) -> int:
        """Listen on the first free port from `port` on (a second copy of the app must not break the first)."""
        runner = web.AppRunner(self._app(), access_log=None)
        await runner.setup()
        last: Exception | None = None
        for candidate in range(self.port, self.port + 20):
            try:
                await web.TCPSite(runner, self.host, candidate).start()
            except OSError as exc:
                last = exc
                continue
            self._runner = runner
            self.port = runner.addresses[0][1]          # the real one when asked for port 0
            return self.port
        await runner.cleanup()
        raise OSError(f"no hay un puerto libre desde el {self.port}: {last}")

    async def stop(self) -> None:
        for conn in list(self.hub.conns.values()):
            try:
                await conn.ws.close(code=1001, message=b"server stopping")
            except Exception:  # noqa: BLE001
                pass
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
        if self._media_session is not None:
            await self._media_session.close()
            self._media_session = None

    # ---- plain endpoints ---------------------------------------------------------------------------
    async def _health(self, request: web.Request) -> web.Response:
        return web.json_response({"ok": True, "users": len(self.hub.participants())})

    async def _config(self, request: web.Request) -> web.Response:
        return web.json_response({"clientId": str(self.client_id), "channel": self.hub.channel_name,
                                  "dev": self.allow_dev and is_local_request(request)})

    # ---- pictures from Discord's CDN ---------------------------------------------------------------------
    @staticmethod
    def _media_allowed(url: str) -> bool:
        parts = urlsplit(url)
        return parts.scheme == "https" and bool(parts.hostname) and bool(MEDIA_HOSTS.match(parts.hostname)) and not parts.username

    async def _download(self, url: str) -> tuple[str, bytes]:
        if self._media_session is None:
            self._media_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20))
        for _ in range(MEDIA_REDIRECTS + 1):
            if not self._media_allowed(url):
                raise ValueError("host")
            async with self._media_session.get(url, allow_redirects=False) as response:
                if response.status in (301, 302, 303, 307, 308) and response.headers.get("Location"):
                    url = str(response.url.join(URL(response.headers["Location"])))
                    continue
                if response.status != 200:
                    raise OSError(f"HTTP {response.status}")
                kind = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
                if not kind.startswith(("image/", "video/")):
                    raise ValueError("type")
                body = bytearray()
                async for chunk in response.content.iter_chunked(1 << 16):
                    body += chunk
                    if len(body) > MAX_MEDIA:
                        raise ValueError("size")
                return kind, bytes(body)
        raise OSError("too many redirects")

    def _media_path(self, key: str) -> Path | None:
        if self.media_dir is None:
            self.media_dir = Path(tempfile.mkdtemp(prefix="eventos-media-"))
        self.media_dir.mkdir(parents=True, exist_ok=True)
        found = next((f for f in self.media_dir.glob(key + ".*") if f.suffix != ".part"), None)
        return found

    def _media_prune(self) -> None:
        files = sorted((f for f in self.media_dir.iterdir() if f.is_file()), key=lambda f: f.stat().st_mtime)
        total = sum(f.stat().st_size for f in files)
        for old in files:
            if total <= MEDIA_CACHE_LIMIT:
                break
            total -= old.stat().st_size
            old.unlink(missing_ok=True)

    async def _media(self, request: web.Request) -> web.StreamResponse:
        url = request.query.get("u", "")
        if not url.startswith("https://"):
            return web.Response(status=400, text="falta la dirección https")
        if not self._media_allowed(url):
            return web.Response(status=403, text="solo imágenes de Discord")
        key = hashlib.sha256(url.encode()).hexdigest()[:40]
        path = self._media_path(key)
        if path is None:
            async with self._media_locks.setdefault(key, asyncio.Lock()):
                path = self._media_path(key)          # another request may have fetched it while we waited
                if path is None:
                    try:
                        kind, body = await self._media_fetch(url)
                    except ValueError as exc:
                        return web.Response(status=415 if str(exc) == "type" else 413 if str(exc) == "size" else 403, text="no permitido")
                    except (OSError, aiohttp.ClientError, asyncio.TimeoutError):
                        return web.Response(status=502, text="Discord no respondió")
                    ext = _EXTENSIONS.get(kind) or mimetypes.guess_extension(kind) or (".mp4" if kind.startswith("video/") else ".png")
                    path = self.media_dir / f"{key}{ext}"
                    partial = path.with_suffix(".part")
                    partial.write_bytes(body)
                    partial.replace(path)
                    self._media_writes += 1
                    if self._media_writes % 20 == 0:
                        self._media_prune()
            self._media_locks.pop(key, None)
        else:
            path.touch()
        return web.FileResponse(path, headers={"Cache-Control": "public, max-age=86400"})

    async def _index(self, request: web.Request) -> web.StreamResponse:
        index = self.web_dir / "index.html"
        if index.is_file():
            return web.FileResponse(index, headers={"Cache-Control": "no-cache"})
        return web.Response(text=_FALLBACK, content_type="text/html", status=503)

    async def _token(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
            code = str(body["code"])
        except (ValueError, KeyError, TypeError):
            return web.json_response({"error": "falta el código"}, status=400)
        try:
            return web.json_response({"access_token": await self.auth.exchange_code(code)})
        except AuthError as exc:
            return web.json_response({"error": str(exc)}, status=400)

    # ---- the WebSocket ---------------------------------------------------------------------------------
    async def _identify(self, hello: dict, request: web.Request) -> tuple[int, str, str, bool]:
        """(user id, name, avatar, dev) of whoever said hello, or AuthError."""
        if hello.get("t") != "hello":
            raise AuthError("protocolo incorrecto")
        dev_name = hello.get("dev")
        if dev_name:
            if not (self.allow_dev and is_local_request(request)):
                raise AuthError("el modo de prueba solo funciona abriendo la página desde este mismo PC")
            name = str(dev_name).strip()[:32] or "Prueba"
            return -(1000 + zlib.crc32(name.encode()) % 1_000_000), f"{name} (prueba local)", "", True
        identity = await self.auth.identify(str(hello.get("token", "")))
        info = await self.authorize(identity.user_id)
        return identity.user_id, info.get("name") or identity.name, info.get("avatar") or identity.avatar, False

    async def _ws(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=20.0, max_msg_size=MAX_FRAME)
        await ws.prepare(request)
        conn: Conn | None = None
        try:
            try:
                hello = json.loads((await asyncio.wait_for(ws.receive(), HELLO_TIMEOUT)).data)
                user_id, name, avatar, dev = await self._identify(hello, request)
            except AuthError as exc:
                await ws.send_json({"t": "error", "code": "auth", "reason": str(exc)})
                return ws
            except (asyncio.TimeoutError, ValueError, TypeError, AttributeError):
                await ws.send_json({"t": "error", "code": "auth", "reason": "no llegó el saludo inicial"})
                return ws
            conn = Conn(self.hub.new_id(), user_id, name, avatar, ws, dev=dev)
            backlog = await self.hub.load_backlog()
            if self.actions is not None and hasattr(self.actions, "push_state"):
                await self.actions.push_state()                  # so the welcome carries the game as it is right now
            users = self.hub.participants()
            if not any(u["id"] == str(user_id) for u in users):
                users.append(conn.public())          # you are in the list you are first shown
            characters = self.actions.characters_of(user_id) if self.actions is not None else []
            await ws.send_json({"t": "welcome", "you": conn.public(), "serverTime": self.hub.now_ms(),
                                "channel": self.hub.channel_name, "users": users, "backlog": backlog,
                                "characters": characters, "qtes": list(self.hub.qtes.values()), "state": self.hub.state,
                                "me": self.actions.me_of(user_id) if self.actions is not None and not dev else {},
                                "canWrite": self.actions is not None})
            await self.hub.add(conn)
            async for message in ws:
                if message.type != aiohttp.WSMsgType.TEXT:
                    continue
                try:
                    frame = json.loads(message.data)
                except ValueError:
                    continue
                if not isinstance(frame, dict):
                    continue
                if not conn.allow():
                    await ws.send_json({"t": "slow"})
                    continue
                await self._frame(conn, frame)
        finally:
            if conn is not None:
                await self.hub.remove(conn)
        return ws

    async def _frame(self, conn: Conn, frame: dict) -> None:
        kind = frame.get("t")
        if kind == "ping":                    # clock sync: echo the client's stamp with the server's clock
            await conn.ws.send_json({"t": "pong", "c": frame.get("c"), "s": self.hub.now_ms()})
        elif kind == "sync":                  # what the client concluded from its pings
            try:
                conn.rtt_ms = max(0.0, min(float(frame["rtt"]), 60_000.0))
                conn.offset_ms = max(-1e12, min(float(frame["offset"]), 1e12))
            except (KeyError, TypeError, ValueError):
                return
            self.hub._changed()
        elif kind in ("say", "press"):
            if self.actions is None:
                await conn.ws.send_json({"t": "error", "code": "readonly", "reason": "Esta Actividad es de solo lectura."})
                return
            try:
                reason = await (self.actions.say if kind == "say" else self.actions.press)(conn, frame)
            except Exception:  # noqa: BLE001 - one bad frame must not close the connection
                log.exception("could not handle a %r frame", kind)
                reason = "Algo falló al procesarlo; inténtalo otra vez."
            if reason:
                await conn.ws.send_json({"t": "error", "code": kind, "reason": reason, "id": frame.get("id")})
