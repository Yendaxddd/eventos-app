"""The information a person pastes when asking for help: the app's version, the system, what the bot and the Activity say, and the last
lines of the log, with every secret blanked out first."""

from __future__ import annotations

import platform
import re
import sys
from typing import Iterable

from . import APP_NAME, __version__

_TOKEN_SHAPE = re.compile(r"[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{5,}\.[A-Za-z0-9_\-]{20,}")     # what a Discord bot token looks like
HIDDEN = "«oculto»"


def redact(text: str, secrets: Iterable[str]) -> str:
    """The text with the given secrets (and anything shaped like a bot token) replaced."""
    for secret in sorted({s.strip() for s in secrets if s and len(s.strip()) >= 6}, key=len, reverse=True):
        text = text.replace(secret, HIDDEN)
    return _TOKEN_SHAPE.sub(HIDDEN, text)


def settings_lines(settings) -> list[str]:
    """What is switched on, never any secret: only whether a value is set."""
    return [
        f"Token del bot: {'puesto' if settings.discord_token.strip() else 'FALTA'}",
        f"Rol de jugadores: {'sí' if settings.qte_player_role_id.strip() else 'no'} · Rol de administrador: {'sí' if settings.admin_role_id.strip() else 'no'}",
        f"Bots auxiliares: {len(settings.helper_tokens())} · Webhooks: {'sí' if settings.use_webhooks else 'no'}",
        f"Actividad: {'activada' if settings.activity_enabled else 'apagada'} · Client Secret: {'puesto' if settings.activity_client_secret.strip() else 'FALTA'}"
        f" · Dirección: {settings.activity_tunnel}",
        f"IA: {'sí' if settings.ai_enabled else 'no'} · Atajos de teclado: {'sí' if settings.hotkeys_enabled else 'no'} · "
        f"Reiniciar al iniciar: {'sí' if settings.reset_on_start else 'no'}",
    ]


def support_report(settings, *, state: str, connection: str = "", error: str = "", event: str = "", activity: dict | None = None,
                   log_lines: Iterable[str] = (), frozen: bool = False) -> str:
    secrets = [settings.discord_token, settings.activity_client_secret, *settings.helper_tokens()]
    lines = [f"{APP_NAME} {__version__} ({'instalado' if frozen else 'desde el código'})",
             f"Sistema: {platform.system()} {platform.release()} · Python {sys.version.split()[0]}", "",
             f"Estado: {state}" + (f" · {connection}" if connection else ""), *([f"Error: {error}"] if error else []),
             *([f"Evento: {event}"] if event else []), "", *settings_lines(settings)]
    info = activity or {}
    if info.get("running"):
        lines += ["", f"Actividad: puerto {info.get('port')} · túnel {info.get('tunnel')} · {info.get('detail') or 'sin detalle'}",
                  f"Conectados: {len([u for u in info.get('users', []) if not u.get('hidden')])}"]
    tail = [str(line).rstrip() for line in log_lines][-40:]
    if tail:
        lines += ["", "Últimas líneas del registro:", *tail]
    return redact("\n".join(lines), secrets)
