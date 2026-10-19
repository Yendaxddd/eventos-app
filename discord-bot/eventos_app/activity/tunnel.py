"""A public https address that leads to the local server.

Discord's proxy downloads the Activity from the internet, so the PC needs a public address.

* `Tunnel`: a free Cloudflare "quick tunnel". Needs no account but gets a NEW address every time it starts: it has
  to be pasted in the Developer Portal (URL Mappings, root `/`) at the start of each event. cloudflared is downloaded
  once, from Cloudflare's own GitHub releases, into `<app home>/tools`.
* `NgrokTunnel`: the free static domain of an ngrok account. The address never changes, so it is pasted in the
  Portal once. Needs the account's authtoken and domain (both free).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import sys
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Callable, Sequence

import aiohttp

log = logging.getLogger("eventos_app.activity")

URL_RE = re.compile(r"https://[a-z0-9][a-z0-9-]*\.trycloudflare\.com")
DOWNLOAD_URL = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
URL_WAIT_SECONDS = 25.0
NGROK_DOWNLOADS = ("https://bin.ngrok.com/c/bNyj1mQVY4c/ngrok-v3-stable-windows-amd64.zip",
                   "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-windows-amd64.zip")


class TunnelError(Exception):
    pass


class Tunnel:
    """States: idle -> downloading -> starting -> up (or error). `url` is set when up."""

    def __init__(self, port: int, *, tools_dir: Path | None = None, on_change: Callable[[], None] | None = None,
                 command: Callable[[Path, int, str], Sequence[str]] | None = None) -> None:
        self.port = port
        self.tools_dir = tools_dir
        self.on_change = on_change
        self._command = command or self._default_command
        self.last_error = ""
        self.state = "idle"
        self.detail = ""
        self.url = ""
        self._proc: asyncio.subprocess.Process | None = None
        self._reader: asyncio.Task | None = None
        self._stopping = False

    # ---- state -----------------------------------------------------------------------------------
    def _set(self, state: str, detail: str = "") -> None:
        self.state, self.detail = state, detail
        if self.on_change is not None:
            try:
                self.on_change()
            except Exception:  # noqa: BLE001
                log.exception("tunnel.on_change failed")

    program = "cloudflared"
    attempts: tuple[str, ...] = ("quic", "http2")       # some networks block one protocol: try the other
    fixed = False                                        # True when the address is the same on every start

    def _default_command(self, binary: Path, port: int, protocol: str) -> list[str]:
        return [str(binary), "tunnel", "--no-autoupdate", "--protocol", protocol, "--url", f"http://127.0.0.1:{port}"]

    def _url_in(self, line: str) -> str:
        """The public address mentioned in one line of the program's output ('' when none)."""
        match = URL_RE.search(line)
        return match.group(0) if match else ""

    def _failure(self) -> str:
        return "El túnel no devolvió ninguna dirección. ¿Hay internet? ¿Un firewall bloquea cloudflared?"

    # ---- the program --------------------------------------------------------------------------------
    def find_binary(self) -> Path | None:
        if self.tools_dir is not None:
            for name in (f"{self.program}.exe", self.program):
                candidate = self.tools_dir / name
                if candidate.is_file():
                    return candidate
        found = shutil.which(self.program)
        return Path(found) if found else None

    async def ensure_binary(self) -> Path:
        binary = self.find_binary()
        if binary is not None:
            return binary
        if sys.platform != "win32" or self.tools_dir is None:
            raise TunnelError("Instala cloudflared (https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) "
                              "y vuelve a intentarlo.")
        self.tools_dir.mkdir(parents=True, exist_ok=True)
        target, partial = self.tools_dir / "cloudflared.exe", self.tools_dir / "cloudflared.exe.part"
        self._set("downloading", "Descargando cloudflared (una sola vez)…")
        try:
            timeout = aiohttp.ClientTimeout(total=300)
            async with aiohttp.ClientSession(timeout=timeout) as session, session.get(DOWNLOAD_URL) as response:
                if response.status != 200:
                    raise TunnelError(f"No se pudo descargar cloudflared (HTTP {response.status}).")
                total, done = int(response.headers.get("Content-Length") or 0), 0
                with partial.open("wb") as out:
                    async for chunk in response.content.iter_chunked(1 << 16):
                        out.write(chunk)
                        done += len(chunk)
                        if total:
                            self._set("downloading", f"Descargando cloudflared… {done * 100 // total} %")
            os.replace(partial, target)
        except (aiohttp.ClientError, OSError, asyncio.TimeoutError) as exc:
            partial.unlink(missing_ok=True)
            raise TunnelError(f"No se pudo descargar cloudflared: {exc}") from exc
        return target

    # ---- running it -------------------------------------------------------------------------------------
    async def start(self) -> str:
        """Open the tunnel and return its public address. Raises TunnelError."""
        await self.stop()
        try:
            binary = await self.ensure_binary()
            for protocol in self.attempts:
                self._set("starting", "Abriendo el túnel…")
                url = await self._launch(binary, protocol)
                if url:
                    self.url = url
                    self._set("up", url)
                    return url
                await self._kill()
            raise TunnelError(self._failure())
        except TunnelError as exc:
            self.url = ""
            self._set("error", str(exc))
            raise
        except OSError as exc:
            self.url = ""
            self._set("error", f"No se pudo ejecutar {self.program}: {exc}")
            raise TunnelError(str(exc)) from exc

    async def _launch(self, binary: Path, protocol: str) -> str:
        flags = getattr(__import__("subprocess"), "CREATE_NO_WINDOW", 0)
        self._stopping = False
        self.last_error = ""
        self._proc = await asyncio.create_subprocess_exec(
            *self._command(binary, self.port, protocol), stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT, creationflags=flags)
        found: asyncio.Future[str] = asyncio.get_running_loop().create_future()

        async def read() -> None:
            assert self._proc is not None and self._proc.stdout is not None
            async for raw in self._proc.stdout:
                line = raw.decode("utf-8", "replace")
                url = self._url_in(line)
                if url and not found.done():
                    found.set_result(url)
            if not found.done():
                found.set_result("")
            if self.state == "up" and not self._stopping:   # it ended by itself: say so
                self.url = ""
                self._set("error", "El túnel se cerró. Reinicia la Actividad para abrir otro.")

        self._reader = asyncio.get_running_loop().create_task(read())
        try:
            return await asyncio.wait_for(asyncio.shield(found), URL_WAIT_SECONDS)
        except asyncio.TimeoutError:
            return ""

    async def _kill(self) -> None:
        self._stopping = True
        proc, self._proc = self._proc, None
        if proc is not None and proc.returncode is None:
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), 5)
            except (ProcessLookupError, asyncio.TimeoutError):
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
        if self._reader is not None:
            self._reader.cancel()
            self._reader = None

    async def stop(self) -> None:
        was_up = self.state != "idle"
        self.url = ""
        await self._kill()
        if was_up:
            self._set("idle")


def _ngrok_error(line: str) -> str:
    """What went wrong, in Spanish, from one JSON log line of ngrok (or '' when the line is not an error)."""
    try:
        data = json.loads(line)
    except ValueError:
        text = line.strip()
        return text if "ERR_NGROK" in text or "unknown flag" in text else ""
    if data.get("lvl") not in ("eror", "crit", "error"):
        return ""
    text = f"{data.get('err', '')} {data.get('msg', '')}"
    if "ERR_NGROK_105" in text or "ERR_NGROK_107" in text or "authentication failed" in text.lower():
        return "ngrok rechazó el authtoken: cópialo otra vez desde dashboard.ngrok.com → Your Authtoken."
    if "ERR_NGROK_334" in text or "already online" in text.lower():
        return "Ese dominio de ngrok ya está en uso (¿otro ngrok abierto en este PC u otro equipo?)."
    if "ERR_NGROK_314" in text or "ERR_NGROK_313" in text or "domain" in text.lower() and "not" in text.lower():
        return "ngrok no reconoce ese dominio: cópialo de dashboard.ngrok.com → Domains (debe ser el gratuito de tu cuenta)."
    return text.strip()[:300]


class NgrokTunnel(Tunnel):
    """The free static domain of an ngrok account: the address is known beforehand and never changes."""

    program = "ngrok"
    attempts = ("url", "domain")      # the flag is `--url` in current versions and `--domain` in older ones
    fixed = True

    def __init__(self, port: int, *, token: str, domain: str, **options) -> None:
        super().__init__(port, **options)
        self.token = token.strip()
        self.domain = re.sub(r"^https?://", "", domain.strip()).strip("/").lower()

    def _default_command(self, binary: Path, port: int, flag: str) -> list[str]:
        target = f"https://{self.domain}" if flag == "url" else self.domain
        return [str(binary), "http", str(port), f"--{flag}", target, "--authtoken", self.token,
                "--log", "stdout", "--log-format", "json"]

    def _url_in(self, line: str) -> str:
        error = _ngrok_error(line)
        if error:
            self.last_error = error
        try:
            data = json.loads(line)
        except ValueError:
            return ""
        if data.get("msg") == "started tunnel" or data.get("url", "").endswith(self.domain):
            return f"https://{self.domain}"
        return ""

    def _failure(self) -> str:
        return self.last_error or "ngrok no abrió el túnel. ¿Hay internet? ¿Un firewall lo bloquea?"

    async def start(self) -> str:
        if not self.token or not self.domain:
            self._set("error", "Faltan el authtoken o el dominio de ngrok en Configuración.")
            raise TunnelError(self.detail)
        return await super().start()

    async def ensure_binary(self) -> Path:
        binary = self.find_binary()
        if binary is not None:
            return binary
        if sys.platform != "win32" or self.tools_dir is None:
            raise TunnelError("Instala ngrok (https://ngrok.com/download) y vuelve a intentarlo.")
        self.tools_dir.mkdir(parents=True, exist_ok=True)
        self._set("downloading", "Descargando ngrok (una sola vez)…")
        problem = ""
        for url in NGROK_DOWNLOADS:
            try:
                timeout = aiohttp.ClientTimeout(total=300)
                async with aiohttp.ClientSession(timeout=timeout) as session, session.get(url) as response:
                    if response.status != 200:
                        problem = f"HTTP {response.status}"
                        continue
                    archive = zipfile.ZipFile(BytesIO(await response.read()))
                    name = next((n for n in archive.namelist() if n.lower().endswith("ngrok.exe")), None)
                    if name is None:
                        problem = "el archivo no contiene ngrok.exe"
                        continue
                    target = self.tools_dir / "ngrok.exe"
                    partial = self.tools_dir / "ngrok.exe.part"
                    partial.write_bytes(archive.read(name))
                    os.replace(partial, target)
                    return target
            except (aiohttp.ClientError, OSError, asyncio.TimeoutError, zipfile.BadZipFile) as exc:
                problem = str(exc)
        raise TunnelError(f"No se pudo descargar ngrok ({problem}). Descárgalo de https://ngrok.com/download y "
                          f"copia ngrok.exe en {self.tools_dir}.")
