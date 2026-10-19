"""User settings, stored in <home>/settings.json.

The bot itself still reads its configuration from environment variables, so the
app translates these settings into env vars right before starting it
(`Settings.to_env`). That keeps the headless/Docker setup working unchanged.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from . import paths

log = logging.getLogger("eventos_app")

_ID_FIELDS = {
    "qte_player_role_id": "QTE_PLAYER_ROLE_ID",
    "admin_role_id": "ADMIN_ROLE_ID",
}


@dataclass
class Settings:
    discord_token: str = ""
    qte_player_role_id: str = ""
    admin_role_id: str = ""
    ai_enabled: bool = False
    ollama_endpoint: str = "http://localhost:11434/api/generate"
    ollama_model: str = ""
    # extra bot accounts that share the sending load: [{"token": ..., "name": ..., "user_id": ...}]
    helper_bots: list = field(default_factory=list)
    # every bot registers one webhook in the event channel and sends through it too (needs "Manage Webhooks")
    use_webhooks: bool = True
    # Discord Activity (beta): a local web server + free tunnel; needs the application's OAuth2 Client Secret
    activity_enabled: bool = False
    activity_client_secret: str = ""
    # how Discord reaches the Activity: "cloudflare" (free quick tunnel, new address each start) or "tailscale"
    # (Tailscale Funnel: a fixed address, pasted once in the Developer Portal)
    activity_tunnel: str = "cloudflare"
    # names of the last event (ids + server/channel/role names), shown while the bot is off
    event_summary: dict = field(default_factory=dict)
    reset_on_start: bool = False
    hotkeys_enabled: bool = True
    auto_start: bool = False

    def validate(self) -> list[str]:
        """Human-readable problems (Spanish, shown in the UI). Empty list = OK."""
        problems = []
        labels = {
            "qte_player_role_id": "Rol de jugadores",
            "admin_role_id": "Rol de administrador",
        }
        for name, label in labels.items():
            value = getattr(self, name).strip()
            if value and not value.isdigit():
                problems.append(f"{label}: debe ser un ID numérico de Discord.")
        return problems

    def to_env(self) -> dict[str, str]:
        env = {
            "DISCORD_TOKEN": self.discord_token.strip(),
            "OLLAMA_ENDPOINT": self.ollama_endpoint.strip(),
            "OLLAMA_MODEL": self.ollama_model.strip(),
            "AI_ENABLED": "1" if self.ai_enabled else "0",
            "EVENTOS_RESET_ON_START": "1" if self.reset_on_start else "0",
            "EVENTOS_HOTKEYS": "1" if self.hotkeys_enabled else "0",
        }
        for name, var in _ID_FIELDS.items():
            value = getattr(self, name).strip()
            if value.isdigit():
                env[var] = value
        return {k: v for k, v in env.items() if v != "" or k.startswith("EVENTOS_")}

    def helper_tokens(self) -> list[str]:
        return [h["token"].strip() for h in self.helper_bots if isinstance(h, dict) and h.get("token", "").strip()]


def load(path: Path | None = None) -> Settings:
    path = path or paths.settings_file()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("settings.json is not an object")
    except FileNotFoundError:
        return _from_environment(Settings())
    except (OSError, ValueError) as exc:
        log.warning("settings.json unreadable (%s); keeping a backup and starting fresh", exc)
        try:
            path.replace(path.with_suffix(".json.bad"))
        except OSError:
            pass
        return _from_environment(Settings())

    known = {f.name: f for f in fields(Settings)}
    values = {}
    for key, value in raw.items():
        if key not in known:
            continue
        default = getattr(Settings(), key)
        if isinstance(default, bool):
            values[key] = bool(value)
        elif isinstance(default, list):
            values[key] = [h for h in value if isinstance(h, dict)] if isinstance(value, list) else []
        elif isinstance(default, dict):
            values[key] = value if isinstance(value, dict) else {}
        else:
            values[key] = "" if value is None else str(value)
    return Settings(**values)


def _from_environment(settings: Settings) -> Settings:
    """First run: pick up a DISCORD_TOKEN from the environment / .env if there is one."""
    token = os.environ.get("DISCORD_TOKEN", "")
    if token:
        settings.discord_token = token
    for name, var in _ID_FIELDS.items():
        if os.environ.get(var, "").isdigit():
            setattr(settings, name, os.environ[var])
    return settings


def save(settings: Settings, path: Path | None = None) -> None:
    path = path or paths.settings_file()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(asdict(settings), indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
