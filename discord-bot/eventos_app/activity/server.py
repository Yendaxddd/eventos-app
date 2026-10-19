"""The local web server behind the Activity: static client, token exchange and the WebSocket.

Discord's proxy forwards the Activity's requests here through a public tunnel (see `tunnel`), under the
magic prefix `/.proxy` (which Discord strips before forwarding, and which is accepted here too just in case).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import zlib
from pathlib import Path
from typing import Awaitable, Callable

import aiohttp
from aiohttp import web

from .auth import AuthError, DiscordAuth
from .hub import Conn, Hub

log = logging.getLogger("eventos_app.activity")

DEFAULT_PORT = 8765
HELLO_TIMEOUT = 10.0
MAX_FRAME = 64 * 1024
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
                 host: str = "127.0.0.1", port: int = DEFAULT_PORT, allow_dev: bool = True) -> None:
        self.hub, self.auth, self.authorize = hub, auth, authorize
        self.web_dir = Path(web_dir)
        self.client_id = client_id
        self.host, self.port = host, port
        self.allow_dev = allow_dev
        self._runner: web.AppRunner | None = None

    # ---- lifecycle ----------------------------------------------------------------------------
    def _app(self) -> web.Application:
        app = web.Application(client_max_size=MAX_FRAME)
        for prefix in ("", "/.proxy"):
            app.router.add_get(f"{prefix}/api/config", self._config)
            app.router.add_post(f"{prefix}/api/token", self._token)
            app.router.add_get(f"{prefix}/ws", self._ws)
            app.router.add_get(f"{prefix}/healthz", self._health)
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

    # ---- plain endpoints ---------------------------------------------------------------------------
    async def _health(self, request: web.Request) -> web.Response:
        return web.json_response({"ok": True, "users": len(self.hub.participants())})

    async def _config(self, request: web.Request) -> web.Response:
        return web.json_response({"clientId": str(self.client_id), "channel": self.hub.channel_name,
                                  "dev": self.allow_dev and is_local_request(request)})

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
            users = self.hub.participants()
            if not any(u["id"] == str(user_id) for u in users):
                users.append(conn.public())          # you are in the list you are first shown
            await ws.send_json({"t": "welcome", "you": conn.public(), "serverTime": self.hub.now_ms(),
                                "channel": self.hub.channel_name, "users": users, "backlog": backlog})
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
        elif kind == "chat":
            await conn.ws.send_json({"t": "error", "code": "readonly",
                                     "reason": "Por ahora el espejo es de solo lectura: escribe en el chat de Discord."})
