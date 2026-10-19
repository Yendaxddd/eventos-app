"""Download a picture from an address a player typed, without becoming a way into the host's own network.

The Activity's server runs on the game master's PC, so an address like `http://192.168.1.1/` or `http://127.0.0.1:8765/` must never be
fetched on a player's behalf. Every connection (and every redirect) goes through a resolver that refuses anything but public internet
addresses, only web addresses (`https`, or the odd old `http` one) are accepted, and the size is capped while it downloads.
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

import aiohttp
from aiohttp.abc import AbstractResolver

MAX_REDIRECTS = 3
USER_AGENT = "EventosApp/1.1 (+https://github.com/Yendaxddd/eventos-app)"


class FetchError(Exception):
    """A reason that can be told to the person in plain words."""


def is_public(address: str) -> bool:
    try:
        return ipaddress.ip_address(address.split("%")[0]).is_global
    except ValueError:
        return False


class PublicOnlyResolver(AbstractResolver):
    """The system's resolver, keeping only the public addresses it finds (so a name that points inside the house gets nowhere)."""

    def __init__(self) -> None:
        self._inner = aiohttp.resolver.DefaultResolver()

    async def resolve(self, host: str, port: int = 0, family: int = socket.AF_INET):
        found = await self._inner.resolve(host, port, family)
        allowed = [entry for entry in found if is_public(entry["host"])]
        if not allowed:
            raise OSError("esa dirección no es pública")
        return allowed

    async def close(self) -> None:
        await self._inner.close()


def check_url(url: str) -> str:
    """The address, or FetchError if it is not an http(s) address of a name on the public internet."""
    try:
        parts = urlsplit(str(url).strip())
    except ValueError as exc:
        raise FetchError("El enlace no es válido.") from exc
    if parts.scheme not in ("https", "http") or not parts.hostname:
        raise FetchError("El enlace debe empezar por https://")
    if parts.username or parts.password:
        raise FetchError("El enlace no puede llevar usuario ni contraseña.")
    try:
        literal = ipaddress.ip_address(parts.hostname)
    except ValueError:
        literal = None
    if literal is not None and not literal.is_global:
        raise FetchError("Ese enlace apunta a una dirección que no es pública.")
    return parts.geturl()


async def fetch_bytes(url: str, *, max_bytes: int, timeout: float = 15.0, allow_private: bool = False, session: aiohttp.ClientSession | None = None) -> bytes:
    """The body of `url` (at most `max_bytes`). `allow_private` is for the tests, which serve the picture from this very machine."""
    if not allow_private:
        url = check_url(url)
    own = session is None
    if own:
        connector = aiohttp.TCPConnector(resolver=None if allow_private else PublicOnlyResolver(), limit=4, force_close=True)
        session = aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=timeout), headers={"User-Agent": USER_AGENT})
    try:
        async with session.get(url, allow_redirects=True, max_redirects=MAX_REDIRECTS) as response:
            if response.status != 200:
                raise FetchError(f"El servidor de la imagen respondió {response.status}.")
            if response.content_length is not None and response.content_length > max_bytes:
                raise FetchError("La imagen pesa demasiado.")
            body = bytearray()
            async for chunk in response.content.iter_chunked(1 << 16):
                body += chunk
                if len(body) > max_bytes:
                    raise FetchError("La imagen pesa demasiado.")
            return bytes(body)
    except FetchError:
        raise
    except asyncio.TimeoutError as exc:
        raise FetchError("La imagen tardó demasiado en descargarse.") from exc
    except (aiohttp.ClientError, OSError) as exc:
        raise FetchError("No se pudo descargar la imagen.") from exc
    finally:
        if own:
            await session.close()
