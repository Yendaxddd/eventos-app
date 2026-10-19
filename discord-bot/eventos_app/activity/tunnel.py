"""A free Cloudflare "quick tunnel": a public https address that leads to the local server.

Discord's proxy downloads the Activity from the internet, so the PC needs a public address. A quick tunnel
needs no account but gets a NEW address every time it starts: it has to be pasted in the Developer Portal
(URL Mappings, root `/`) at the start of each event. cloudflared is downloaded once, from Cloudflare's own
GitHub releases, into `<app home>/tools`.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Callable, Sequence

import aiohttp

log = logging.getLogger("eventos_app.activity")

URL_RE = re.compile(r"https://[a-z0-9][a-z0-9-]*\.trycloudflare\.com")
DOWNLOAD_URL = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
URL_WAIT_SECONDS = 25.0


class TunnelError(Exception):
    pass


class Tunnel:
    """States: idle -> downloading -> starting -> up (or error). `url` is set when up."""

    def __init__(self, port: int, *, tools_dir: Path | None = None, on_change: Callable[[], None] | None = None,
                 command: Callable[[Path, int, str], Sequence[str]] | None = None) -> None:
        self.port = port
        self.tools_dir = tools_dir
        self.on_change = on_change
        self._command = command or self._cloudflared_command
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

    @staticmethod
    def _cloudflared_command(binary: Path, port: int, protocol: str) -> list[str]:
        return [str(binary), "tunnel", "--no-autoupdate", "--protocol", protocol, "--url", f"http://127.0.0.1:{port}"]

    # ---- the program --------------------------------------------------------------------------------
    def find_binary(self) -> Path | None:
        if self.tools_dir is not None:
            for name in ("cloudflared.exe", "cloudflared"):
                candidate = self.tools_dir / name
                if candidate.is_file():
                    return candidate
        found = shutil.which("cloudflared")
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
            for protocol in ("quic", "http2"):     # some networks block one of them: try the other
                self._set("starting", "Abriendo el túnel…")
                url = await self._launch(binary, protocol)
                if url:
                    self.url = url
                    self._set("up", url)
                    return url
                await self._kill()
            raise TunnelError("El túnel no devolvió ninguna dirección. ¿Hay internet? ¿Un firewall bloquea cloudflared?")
        except TunnelError as exc:
            self.url = ""
            self._set("error", str(exc))
            raise
        except OSError as exc:
            self.url = ""
            self._set("error", f"No se pudo ejecutar cloudflared: {exc}")
            raise TunnelError(str(exc)) from exc

    async def _launch(self, binary: Path, protocol: str) -> str:
        flags = getattr(__import__("subprocess"), "CREATE_NO_WINDOW", 0)
        self._stopping = False
        self._proc = await asyncio.create_subprocess_exec(
            *self._command(binary, self.port, protocol), stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT, creationflags=flags)
        found: asyncio.Future[str] = asyncio.get_running_loop().create_future()

        async def read() -> None:
            assert self._proc is not None and self._proc.stdout is not None
            async for raw in self._proc.stdout:
                match = URL_RE.search(raw.decode("utf-8", "replace"))
                if match and not found.done():
                    found.set_result(match.group(0))
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
