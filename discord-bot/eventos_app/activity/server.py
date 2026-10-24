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
from urllib.parse import unquote, urlsplit

import aiohttp
from aiohttp import web
from yarl import URL

from .. import __version__
from .auth import AuthError, DiscordAuth
from .hub import MAX_PER_USER, Conn, Hub, RpcError
from .media import AUDIO, CONTENT_TYPES, IMAGES, LIMITS, MediaStore

log = logging.getLogger("eventos_app.activity")

DEFAULT_PORT = 8765
HELLO_TIMEOUT = 10.0
RPC_TIMEOUT = 15.0
MAX_FRAME = 64 * 1024
UPLOAD_LIMIT = 9 * 1024 * 1024        # a little above what the bridge accepts, so it is the one that explains why
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


def _log_late_failure(task: asyncio.Future) -> None:
    if not task.cancelled() and task.exception() is not None and not isinstance(task.exception(), RpcError):
        log.error("a slow request failed in the end", exc_info=task.exception())


def dev_identity(name: str) -> tuple[int, str]:
    """The (made-up, negative) id and name of a test window opened on this PC."""
    clean = str(name).strip()[:32] or "Prueba"
    return -(1000 + zlib.crc32(clean.encode()) % 1_000_000), f"{clean} (prueba local)"


def is_local_request(request: web.Request) -> bool:
    """True only for a browser on this very PC. A request that came through the public tunnel never is."""
    headers = request.headers
    if any(headers.get(h) for h in ("CF-Connecting-IP", "Cf-Ray", "X-Forwarded-For", "Forwarded", "X-Real-IP")):
        return False
    host = request.host.rsplit(":", 1)[0].strip("[]")
    if not (request.remote in ("127.0.0.1", "::1") and host in ("127.0.0.1", "localhost", "::1")):
        return False
    # Any web page the host opens can also reach 127.0.0.1 (a WebSocket has no CORS check): the browser says which page asks, in Origin.
    origin = headers.get("Origin")
    return origin is None or bool(_LOCAL_ORIGIN.match(origin))


_LOCAL_ORIGIN = re.compile(r"^https?://(127\.0\.0\.1|localhost|\[::1\])(:\d{1,5})?$")


class ActivityServer:
    def __init__(self, hub: Hub, *, auth: DiscordAuth, authorize: Authorize, web_dir: Path, client_id: int,
                 host: str = "127.0.0.1", port: int = DEFAULT_PORT, allow_dev: bool = True, actions=None,
                 media_dir: Path | None = None, media_fetch: Fetch | None = None, files: MediaStore | None = None,
                 on_event: Callable[[str], None] | None = None) -> None:
        self.hub, self.auth, self.authorize = hub, auth, authorize
        self.actions = actions     # what the players can do (write, press a QTE button): see ActivityBridge.say / press
        self.web_dir = Path(web_dir)
        self.client_id = client_id
        self.host, self.port = host, port
        self.allow_dev = allow_dev
        self._runner: web.AppRunner | None = None
        self.on_event = on_event       # one line of text per thing worth telling the person running the app (see `_note`)
        self._reports = 0
        self._reports_reset = 0.0
        self.files = files        # the host's own library of pictures and audio, handed out at /files/<kind>/<name>
        self.media_dir = Path(media_dir) if media_dir else None
        self._media_fetch = media_fetch or self._download
        self._media_locks: dict[str, asyncio.Lock] = {}
        self._media_session: aiohttp.ClientSession | None = None
        self._media_writes = 0

    # ---- lifecycle ----------------------------------------------------------------------------
    def _note(self, text: str) -> None:
        if self.on_event is not None:
            try:
                self.on_event(text)
            except Exception:  # noqa: BLE001
                log.exception("on_event failed")

    @web.middleware
    async def _watch(self, request: web.Request, handler):
        """Say in the app's log when somebody (Discord, above all) asks for the page: it shows whether Discord reaches us."""
        path = request.path.removeprefix("/.proxy") or "/"
        shown = path in ("/", "/index.html", "/api/config", "/api/token", "/ws", "/healthz")
        try:
            response = await handler(request)
        except web.HTTPException as exc:
            if shown:
                self._note(f"{request.method} {path} → {exc.status} ({self._who(request)})")
            raise
        if shown:
            self._note(f"{request.method} {path} → {response.status} ({self._who(request)})")
        return response

    @web.middleware
    async def _fresh(self, request: web.Request, handler):
        """Files of the client are always re-checked (a cheap 304 when unchanged), so an update is seen at once."""
        response = await handler(request)
        if isinstance(response, web.FileResponse) and "Cache-Control" not in response.headers and not request.path.endswith("/media"):
            if "/files/" in request.path:             # named by their content: they never change under their name
                response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
                return response
            # fonts have a fingerprint in their name, so they never change under it: keep them; everything else is re-checked
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable" if "/fonts/" in request.path else "no-cache"
        return response

    @staticmethod
    def _who(request: web.Request) -> str:
        agent = request.headers.get("User-Agent", "sin User-Agent")
        via = "por el túnel" if not is_local_request(request) else "desde este PC"
        return f"{via}, {agent[:60]}"

    async def _report(self, request: web.Request) -> web.Response:
        """The page tells how far it got (and any error), so a blank Activity can be diagnosed from the app's log."""
        now = time.monotonic()
        if now - self._reports_reset > 60:
            self._reports, self._reports_reset = 0, now
        self._reports += 1
        if self._reports > 200:                               # a whole server opening the Activity at once still gets heard
            return web.json_response({"ok": False}, status=429)
        try:
            body = await request.json()
            stage, detail = str(body.get("stage", ""))[:40], str(body.get("detail", ""))[:300]
        except (ValueError, TypeError, AttributeError):
            return web.json_response({"ok": False}, status=400)
        self._note(f"la página dice: {stage}{' — ' + detail if detail else ''}")
        return web.json_response({"ok": True})

    def _app(self) -> web.Application:
        app = web.Application(client_max_size=MAX_FRAME, middlewares=[self._watch, self._fresh])
        for prefix in ("", "/.proxy"):
            app.router.add_post(f"{prefix}/api/report", self._report)
            app.router.add_post(f"{prefix}/api/upload", self._upload)
            app.router.add_post(f"{prefix}/api/audio", self._upload_audio)
            app.router.add_post(f"{prefix}/api/image", self._upload_cinema_image)
            app.router.add_get(f"{prefix}/api/config", self._config)
            app.router.add_post(f"{prefix}/api/token", self._token)
            app.router.add_get(f"{prefix}/ws", self._ws)
            app.router.add_get(f"{prefix}/healthz", self._health)
            app.router.add_get(f"{prefix}/media", self._media)
            app.router.add_get(f"{prefix}/files/{{kind}}/{{name}}", self._file)
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
        await self.hub.close()
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

    # ---- the host's own library -----------------------------------------------------------------------------
    async def _file(self, request: web.Request) -> web.StreamResponse:
        path = self.files.path_of(request.match_info["kind"], request.match_info["name"]) if self.files is not None else None
        if path is None:
            raise web.HTTPNotFound()
        return web.FileResponse(path, headers={"Content-Type": CONTENT_TYPES.get(path.suffix, "application/octet-stream"),
                                               "X-Content-Type-Options": "nosniff"})

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
            try:
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
                        if self._media_writes % 5 == 0:
                            self._media_prune()
            finally:
                self._media_locks.pop(key, None)          # also when it failed: an address that never worked leaves nothing behind
        else:
            path.touch()
        return web.FileResponse(path, headers={"Cache-Control": "public, max-age=86400"})

    def _versioned(self, text: str) -> str:
        """`app.js` and `app.css` get a version in their address: Discord's browser keeps files it has seen for a
        while, and an old script with a new page (or the other way round) leaves buttons missing."""
        for name in ("app.js", "app.css", "style.css"):
            path = self.web_dir / name
            if path.is_file():
                version = hashlib.sha1(path.read_bytes()).hexdigest()[:10]
                text = text.replace(f'"./{name}"', f'"./{name}?v={version}"')
        return text

    async def _index(self, request: web.Request) -> web.StreamResponse:
        index = self.web_dir / "index.html"
        if index.is_file():
            return web.Response(text=self._versioned(index.read_text(encoding="utf-8")), content_type="text/html",
                                headers={"Cache-Control": "no-cache"})
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

    # ---- pictures a player sends from their device ---------------------------------------------------------------
    async def _http_user(self, request: web.Request) -> int:
        """Who sends this request: the Discord token in `Authorization`, or a test window on this PC (`X-Dev`)."""
        dev = request.headers.get("X-Dev")
        if dev:
            if not (self.allow_dev and is_local_request(request)):
                raise AuthError("el modo de prueba solo funciona abriendo la página desde este mismo PC")
            return dev_identity(dev)[0]
        token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        identity = await self.auth.identify(token)
        await self.authorize(identity.user_id)
        return identity.user_id

    async def _upload(self, request: web.Request) -> web.Response:
        """The body is the picture itself. The bridge checks it is a real picture, keeps it on Discord and answers its address."""
        if self.actions is None or not hasattr(self.actions, "store_image"):
            return web.json_response({"error": "Esta Actividad es de solo lectura."}, status=403)
        try:
            user_id = await self._http_user(request)
        except AuthError as exc:
            return web.json_response({"error": str(exc)}, status=401)
        if request.content_length is not None and request.content_length > UPLOAD_LIMIT:
            return web.json_response({"error": "La imagen pesa demasiado."}, status=413)
        body = bytearray()
        async for chunk in request.content.iter_chunked(1 << 16):
            body += chunk
            if len(body) > UPLOAD_LIMIT:
                return web.json_response({"error": "La imagen pesa demasiado."}, status=413)
        name = unquote(request.headers.get("X-Filename", "imagen"))[:120]         # sent URL-encoded: headers are plain ASCII
        try:
            url = await asyncio.wait_for(self.actions.store_image(user_id, name, bytes(body)), RPC_TIMEOUT * 2)
        except RpcError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except asyncio.TimeoutError:
            return web.json_response({"error": "Discord tardó demasiado en guardar la imagen."}, status=504)
        except Exception:  # noqa: BLE001
            log.exception("could not store an uploaded picture")
            return web.json_response({"error": "No se pudo guardar la imagen."}, status=500)
        return web.json_response({"url": url})

    async def _upload_audio(self, request: web.Request) -> web.Response:
        """A sound for the library: only the game masters may add one. The body is the file itself."""
        if self.actions is None or not hasattr(self.actions, "store_audio"):
            return web.json_response({"error": "Esta Actividad es de solo lectura."}, status=403)
        try:
            user_id = await self._http_user(request)
        except AuthError as exc:
            return web.json_response({"error": str(exc)}, status=401)
        limit = LIMITS[AUDIO]
        if request.content_length is not None and request.content_length > limit:
            return web.json_response({"error": f"El archivo pesa demasiado: el máximo es {limit // (1024 * 1024)} MB."}, status=413)
        body = bytearray()
        async for chunk in request.content.iter_chunked(1 << 18):
            body += chunk
            if len(body) > limit:
                return web.json_response({"error": f"El archivo pesa demasiado: el máximo es {limit // (1024 * 1024)} MB."}, status=413)
        name = unquote(request.headers.get("X-Filename", "sonido"))[:120]
        dev_gm = bool(request.headers.get("X-Dev")) and request.headers.get("X-Gm") == "1"      # a test window on this PC that asked for the panel
        try:
            sound = await asyncio.wait_for(self.actions.store_audio(user_id, name, request.headers.get("X-Kind", ""), bytes(body), dev_gm), RPC_TIMEOUT * 2)
        except RpcError as exc:
            return web.json_response({"error": str(exc)}, status=403 if "equipo de GM" in str(exc) else 400)
        except asyncio.TimeoutError:
            return web.json_response({"error": "Tardó demasiado en guardar el sonido."}, status=504)
        except Exception:  # noqa: BLE001
            log.exception("could not store an uploaded sound")
            return web.json_response({"error": "No se pudo guardar el sonido."}, status=500)
        return web.json_response({"sound": sound})

    async def _upload_cinema_image(self, request: web.Request) -> web.Response:
        """A picture for a cinematic (kept on this PC): only the game masters may add one. The body is the file itself."""
        if self.actions is None or not hasattr(self.actions, "store_cinema_image"):
            return web.json_response({"error": "Esta Actividad es de solo lectura."}, status=403)
        try:
            user_id = await self._http_user(request)
        except AuthError as exc:
            return web.json_response({"error": str(exc)}, status=401)
        limit = LIMITS[IMAGES]
        body = bytearray()
        async for chunk in request.content.iter_chunked(1 << 16):
            body += chunk
            if len(body) > limit:
                return web.json_response({"error": f"La imagen pesa demasiado: el máximo es {limit // (1024 * 1024)} MB."}, status=413)
        name = unquote(request.headers.get("X-Filename", "imagen"))[:120]
        dev_gm = bool(request.headers.get("X-Dev")) and request.headers.get("X-Gm") == "1"
        try:
            out = await asyncio.wait_for(self.actions.store_cinema_image(user_id, name, bytes(body), dev_gm), RPC_TIMEOUT * 2)
        except RpcError as exc:
            return web.json_response({"error": str(exc)}, status=403 if "equipo de GM" in str(exc) else 400)
        except Exception:  # noqa: BLE001
            log.exception("could not store a cinematic picture")
            return web.json_response({"error": "No se pudo guardar la imagen."}, status=500)
        return web.json_response(out)

    # ---- the WebSocket ---------------------------------------------------------------------------------
    async def _identify(self, hello: dict, request: web.Request) -> tuple[int, str, str, bool]:
        """(user id, name, avatar, dev) of whoever said hello, or AuthError."""
        if hello.get("t") != "hello":
            raise AuthError("protocolo incorrecto")
        dev_name = hello.get("dev")
        if dev_name:
            if not (self.allow_dev and is_local_request(request)):
                raise AuthError("el modo de prueba solo funciona abriendo la página desde este mismo PC")
            user_id, name = dev_identity(dev_name)
            return user_id, name, "", True
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
                self._note(f"entrada rechazada: {exc}")
                await ws.send_json({"t": "error", "code": "auth", "reason": str(exc)})
                return ws
            except (asyncio.TimeoutError, ValueError, TypeError, AttributeError):
                await ws.send_json({"t": "error", "code": "auth", "reason": "no llegó el saludo inicial"})
                return ws
            conn = Conn(self.hub.new_id(), user_id, name, avatar, ws, dev=dev)
            same = sorted((c for c in self.hub.conns.values() if c.user_id == user_id), key=lambda c: c.id)
            for old in same[:max(0, len(same) - MAX_PER_USER + 1)]:          # one person, a handful of windows at most: the oldest goes
                asyncio.get_running_loop().create_task(old.ws.close())
            conn.gm = bool(dev and hello.get("gm"))           # a test window on this PC may ask for the GM panel; Discord users never do
            conn.hidden = bool(dev and hello.get("host"))     # ...and, being the host's own window (the desktop app), not to be listed among the players
            backlog = await self.hub.load_backlog()
            if self.actions is not None and hasattr(self.actions, "push_state"):
                await self.actions.push_state()                  # so the welcome carries the game as it is right now
            users = self.hub.participants()
            if not conn.hidden and not any(u["id"] == str(user_id) for u in users):
                users.append(conn.public())          # you are in the list you are first shown
            characters = self.actions.characters_of(user_id) if self.actions is not None else []
            extras = {}
            if self.actions is not None and hasattr(self.actions, "welcome_extras"):
                extras = await self.actions.welcome_extras(conn)         # perms, settings, latency, rules, pictures of the characters
            await ws.send_json({"t": "welcome", "you": conn.public(), "serverTime": self.hub.now_ms(), "version": __version__,
                                "channel": self.hub.channel_name, "users": users, "backlog": backlog,
                                "characters": characters, "qtes": list(self.hub.qtes.values()), "state": self.hub.state,
                                "me": self.actions.me_of(user_id) if self.actions is not None else {},
                                "canWrite": self.actions is not None, **extras})
            await self.hub.add(conn)
            self._note(f"{name} entró a la Actividad")
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
        elif kind == "sq":                    # the answer to one of the server's own pings
            self.hub.note_sq(conn, frame.get("n"))
        elif kind == "prefs" and self.actions is not None and hasattr(self.actions, "save_prefs"):
            await self.actions.save_prefs(conn, frame.get("prefs"))
        elif kind == "latency" and self.actions is not None and hasattr(self.actions, "save_latency"):
            try:
                calib, comp = await self.actions.save_latency(conn, frame.get("result"))
            except Exception:  # noqa: BLE001
                log.exception("could not save a latency test")
                return
            await conn.ws.send_json({"t": "calib", "calib": calib})
            await conn.ws.send_json({"t": "comp", "comp": comp})
        elif kind == "rpc" and self.actions is not None and hasattr(self.actions, "rpc"):
            call_id = str(frame.get("id", ""))[:32]
            # the work itself is never cut halfway (an import that already saved half its pictures, a boss already at 0 HP): past the
            # timeout the person is told it goes on, and it finishes by itself
            work = asyncio.ensure_future(self.actions.rpc(conn, str(frame.get("op", "")), frame.get("args") or {}))
            try:
                data = await asyncio.wait_for(asyncio.shield(work), RPC_TIMEOUT)
                await conn.ws.send_json({"t": "rpc_ok", "id": call_id, "data": data})
            except RpcError as exc:
                await conn.ws.send_json({"t": "rpc_err", "id": call_id, "reason": str(exc)})
            except asyncio.TimeoutError:
                work.add_done_callback(_log_late_failure)
                await conn.ws.send_json({"t": "rpc_err", "id": call_id, "reason": "Está tardando: sigue en marcha y terminará por su cuenta. Vuelve a mirar en un momento."})
            except Exception:  # noqa: BLE001 - one bad request must not close the connection
                log.exception("rpc %r failed", frame.get("op"))
                await conn.ws.send_json({"t": "rpc_err", "id": call_id, "reason": "Algo falló al procesarlo; inténtalo otra vez."})
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
