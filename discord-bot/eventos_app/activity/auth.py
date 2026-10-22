"""Who is this? OAuth2 against Discord: the Activity gets a code, we trade it for a token and ask who owns it."""

from __future__ import annotations

import re
import time
from collections import OrderedDict, deque
from typing import NamedTuple

import aiohttp

API_BASE = "https://discord.com/api/v10"
TOKEN_CACHE_SECONDS = 300
CACHE_MAX = 4000                 # tokens remembered (good and bad): the oldest are forgotten first
BAD_TOKEN_SECONDS = 600          # a token Discord refused is refused here for this long, without asking again
# Discord bans an IP that sends 10 000 refused requests in 10 minutes, and that would take the bot down with it: at most this many
# unknown tokens are taken to Discord per minute when they keep failing (a flood of made-up tokens gets "try again in a moment").
FAILURES_PER_MINUTE = 40
_TOKEN = re.compile(r"^[A-Za-z0-9._~+/=-]{20,200}$")


class AuthError(Exception):
    """Something the player can be told: bad token, not in the server, no access to the channel."""


class Identity(NamedTuple):
    user_id: int
    name: str
    avatar: str


def default_avatar(user_id: int) -> str:
    return f"https://cdn.discordapp.com/embed/avatars/{(user_id >> 22) % 6}.png"


class DiscordAuth:
    def __init__(self, *, client_id: int, client_secret: str, session: aiohttp.ClientSession | None = None,
                 api_base: str = API_BASE) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.api_base = api_base.rstrip("/")
        self._session = session
        self._own_session = session is None
        self._cache: OrderedDict[str, tuple[float, Identity]] = OrderedDict()
        self._bad: OrderedDict[str, float] = OrderedDict()
        self._failures: deque[float] = deque()

    async def _http(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        return self._session

    async def close(self) -> None:
        if self._own_session and self._session is not None:
            await self._session.close()
            self._session = None

    async def exchange_code(self, code: str) -> str:
        """The Activity authorised itself and got a one-time `code`; Discord gives us the access token for it."""
        if not self.client_secret:
            raise AuthError("Falta el «Client Secret» de la aplicación (página Actividad → Ajustes de la Actividad).")
        session = await self._http()
        form = {"client_id": str(self.client_id), "client_secret": self.client_secret,
                "grant_type": "authorization_code", "code": code}
        try:
            async with session.post(f"{self.api_base}/oauth2/token", data=form) as response:
                data = await response.json(content_type=None)
                if response.status != 200 or "access_token" not in data:
                    raise AuthError("Discord no aceptó el código de la Actividad "
                                    f"({data.get('error_description') or data.get('error') or response.status}).")
                return data["access_token"]
        except aiohttp.ClientError as exc:
            raise AuthError(f"No se pudo hablar con Discord: {exc}") from exc

    def _refused(self, token: str, now: float) -> None:
        self._bad[token] = now
        self._bad.move_to_end(token)
        while len(self._bad) > CACHE_MAX:
            self._bad.popitem(last=False)
        self._failures.append(now)

    async def identify(self, access_token: str) -> Identity:
        now = time.monotonic()
        cached = self._cache.get(access_token)
        if cached and now - cached[0] < TOKEN_CACHE_SECONDS:
            return cached[1]
        if not _TOKEN.match(access_token or ""):
            raise AuthError("Discord no reconoce tu sesión: cierra y vuelve a abrir la Actividad.")
        refused_at = self._bad.get(access_token)
        if refused_at is not None and now - refused_at < BAD_TOKEN_SECONDS:
            raise AuthError("Discord no reconoce tu sesión: cierra y vuelve a abrir la Actividad.")
        while self._failures and now - self._failures[0] > 60:
            self._failures.popleft()
        if len(self._failures) >= FAILURES_PER_MINUTE:
            raise AuthError("Hay demasiados intentos de entrar ahora mismo: espera un momento y vuelve a abrir la Actividad.")
        session = await self._http()
        try:
            async with session.get(f"{self.api_base}/users/@me",
                                   headers={"Authorization": f"Bearer {access_token}"}) as response:
                if response.status != 200:
                    self._refused(access_token, now)
                    raise AuthError("Discord no reconoce tu sesión: cierra y vuelve a abrir la Actividad.")
                data = await response.json(content_type=None)
        except aiohttp.ClientError as exc:
            raise AuthError(f"No se pudo hablar con Discord: {exc}") from exc
        user_id = int(data["id"])
        avatar = (f"https://cdn.discordapp.com/avatars/{user_id}/{data['avatar']}.png?size=64"
                  if data.get("avatar") else default_avatar(user_id))
        identity = Identity(user_id, data.get("global_name") or data.get("username") or str(user_id), avatar)
        self._cache[access_token] = (time.monotonic(), identity)
        self._cache.move_to_end(access_token)
        while len(self._cache) > CACHE_MAX:
            self._cache.popitem(last=False)
        return identity
