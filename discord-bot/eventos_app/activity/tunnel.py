"""A public https address that leads to the local server.

Discord's proxy downloads the Activity from the internet, so the PC needs a public address.

* `Tunnel`: a free Cloudflare "quick tunnel". Needs no account but gets a NEW address every time it starts: it has
  to be pasted in the Developer Portal (URL Mappings, root `/`) at the start of each event. cloudflared is downloaded
  once, from Cloudflare's own GitHub releases, into `<app home>/tools`.
* `TailscaleTunnel`: Tailscale Funnel. The address never changes, so it is pasted in the Portal once, and there is no
  warning page in front (ngrok's free plan has one, which leaves the Activity blank inside Discord).
"""

from __future__ import annotations

import asyncio
import json
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



_FUNNEL_LINK = re.compile(r"https://login\.tailscale\.com/\S+")
_TAILSCALE_PATHS = (r"C:\Program Files\Tailscale\tailscale.exe", r"C:\Program Files (x86)\Tailscale\tailscale.exe")
TAILSCALE_DOWNLOAD = "https://tailscale.com/download"
CLI_TIMEOUT = 25.0


def find_tailscale() -> Path | None:
    found = shutil.which("tailscale")
    if found:
        return Path(found)
    return next((Path(p) for p in _TAILSCALE_PATHS if Path(p).is_file()), None)


def read_status(output: str) -> tuple[str, str]:
    """(address, problem) from the JSON of `tailscale status --json`: the machine's public name, or what is wrong."""
    try:
        data = json.loads(output)
    except ValueError:
        return "", f"Tailscale no respondió como se esperaba: {output.strip()[:200] or 'sin salida'}"
    state = data.get("BackendState")
    if state == "NeedsLogin":
        return "", "Tailscale no tiene la sesión iniciada: ábrelo (icono de la bandeja) e inicia sesión."
    if state == "Stopped":
        return "", "Tailscale está desconectado: actívalo desde el icono de la bandeja (Connect)."
    if state != "Running":
        return "", f"Tailscale no está listo (estado: {state or 'desconocido'}). Ábrelo y espera a que conecte."
    name = str((data.get("Self") or {}).get("DNSName", "")).rstrip(".")
    if not name:
        return "", ("Tu Tailscale no tiene nombre público: activa «MagicDNS» y «HTTPS Certificates» en "
                    "https://login.tailscale.com/admin/dns y vuelve a intentarlo.")
    return name, ""


class TailscaleTunnel(Tunnel):
    """Tailscale Funnel: a fixed public https address (`equipo.tailXXXX.ts.net`) with no warning page in front.

    Needs Tailscale installed and signed in, with MagicDNS + HTTPS certificates on and Funnel allowed once. Nothing is
    downloaded: Tailscale is a Windows service with its own installer. The Funnel is switched off again on `stop`."""

    program = "tailscale"
    fixed = True

    def __init__(self, port: int, *, command: Callable[[Path, list[str]], Sequence[str]] | None = None, **options) -> None:
        super().__init__(port, **options)
        self._cli = command or (lambda binary, args: [str(binary), *args])
        self._exposed = False

    def find_binary(self) -> Path | None:
        return find_tailscale()

    async def _run(self, binary: Path, args: list[str]) -> tuple[int, str]:
        flags = getattr(__import__("subprocess"), "CREATE_NO_WINDOW", 0)
        proc = await asyncio.create_subprocess_exec(*self._cli(binary, args), stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.STDOUT, creationflags=flags)
        chunks: list[bytes] = []

        async def pump() -> None:                # kept as it arrives: a command that hangs still leaves what it said
            assert proc.stdout is not None
            async for chunk in proc.stdout:
                chunks.append(chunk)

        reader = asyncio.get_running_loop().create_task(pump())
        timed_out = False
        try:
            await asyncio.wait_for(proc.wait(), CLI_TIMEOUT)       # e.g. `funnel` waiting for approval in the browser
        except asyncio.TimeoutError:
            timed_out = True
            proc.kill()
            await proc.wait()
        try:
            await asyncio.wait_for(reader, 2.0)
        except asyncio.TimeoutError:
            reader.cancel()
        text = b"".join(chunks).decode("utf-8", "replace")
        return (-1 if timed_out else (proc.returncode or 0)), text

    def _fail(self, message: str) -> TunnelError:
        self.url = ""
        self._set("error", message)
        return TunnelError(message)

    async def start(self) -> str:
        await self.stop()
        self._set("starting", "Comprobando Tailscale…")
        binary = self.find_binary()
        if binary is None:
            raise self._fail(f"Tailscale no está instalado. Descárgalo en {TAILSCALE_DOWNLOAD}, inicia sesión y vuelve a intentarlo.")
        try:
            code, out = await self._run(binary, ["status", "--json"])
            address, problem = read_status(out)
            if problem:
                raise self._fail(problem)
            self._set("starting", "Activando el Funnel…")
            code, out = await self._run(binary, ["funnel", "--bg", "--https=443", f"http://127.0.0.1:{self.port}"])
            link = _FUNNEL_LINK.search(out)
            if link and (code != 0 or "not enabled" in out.lower() or "enable" in out.lower()):
                raise self._fail(f"Funnel todavía no está permitido en tu Tailscale: abre {link.group(0)} una vez y apruébalo; "
                                 f"luego reinicia la Actividad.")
            timed_out = code == -1
            if code != 0 and not timed_out:
                raise self._fail(f"Tailscale no pudo activar el Funnel: {out.strip()[:300] or 'sin mensaje'}")
            self._exposed = True
            said = out.strip()[:300]
            code, out = await self._run(binary, ["funnel", "status"])      # it may already be on (set by hand, or slow to answer)
            if timed_out and address not in out:
                raise self._fail("Tailscale tardó demasiado en activar el Funnel" + (f" y dijo: {said}" if said else "") +
                                 f". Abre PowerShell y ejecuta «tailscale funnel --bg {self.port}» para ver qué pide "
                                 "(casi siempre aprobar Funnel en el navegador).")
            if address not in out:
                raise self._fail("Tailscale no confirmó el Funnel. Ejecuta «tailscale funnel status» para ver qué pasa.")
        except OSError as exc:
            raise self._fail(f"No se pudo ejecutar Tailscale: {exc}") from exc
        self.url = f"https://{address}"
        self._set("up", self.url)
        return self.url

    async def stop(self) -> None:
        was_up = self.state != "idle"
        self.url = ""
        if self._exposed:
            self._exposed = False
            binary = self.find_binary()
            if binary is not None:
                try:
                    await self._run(binary, ["funnel", "--https=443", "off"])     # nothing stays public with the bot off
                except OSError:
                    pass
        if was_up:
            self._set("idle")


def check_tailscale() -> tuple[bool, str]:
    """Blocking check for the settings window (call it from a thread): is Tailscale ready, and what would the address be?"""
    import subprocess

    binary = find_tailscale()
    if binary is None:
        return False, f"Tailscale no está instalado. Descárgalo en {TAILSCALE_DOWNLOAD}."
    try:
        done = subprocess.run([str(binary), "status", "--json"], capture_output=True, text=True, timeout=CLI_TIMEOUT,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"No se pudo ejecutar Tailscale: {exc}"
    address, problem = read_status(done.stdout or done.stderr)
    return (False, problem) if problem else (True, f"Tailscale listo. Tu dirección será https://{address}")
