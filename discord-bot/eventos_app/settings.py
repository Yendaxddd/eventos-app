"""User settings, stored in <home>/settings.json.

The bot itself still reads its configuration from environment variables, so the
app translates these settings into env vars right before starting it
(`Settings.to_env`). That keeps the headless/Docker setup working unchanged.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from . import paths

log = logging.getLogger("eventos_app")

_ID_FIELDS = {
    "qte_player_role_id": "QTE_PLAYER_ROLE_ID",
    "admin_role_id": "ADMIN_ROLE_ID",
    "gm_role_id": "GM_ROLE_ID",
}


@dataclass
class Settings:
    discord_token: str = ""
    qte_player_role_id: str = ""
    admin_role_id: str = ""
    gm_role_id: str = ""
    ollama_endpoint: str = "http://localhost:11434/api/generate"
    ollama_model: str = "dolphin-phi:2.7b"
    reset_on_start: bool = False
    hotkeys_enabled: bool = True
    auto_start: bool = False

    def validate(self) -> list[str]:
        """Human-readable problems (Spanish, shown in the UI). Empty list = OK."""
        problems = []
        labels = {
            "qte_player_role_id": "Rol de jugadores",
            "admin_role_id": "Rol de administrador",
            "gm_role_id": "Rol de GM",
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
            "EVENTOS_RESET_ON_START": "1" if self.reset_on_start else "0",
            "EVENTOS_HOTKEYS": "1" if self.hotkeys_enabled else "0",
        }
        for name, var in _ID_FIELDS.items():
            value = getattr(self, name).strip()
            if value.isdigit():
                env[var] = value
        return {k: v for k, v in env.items() if v != "" or k.startswith("EVENTOS_")}


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
        field = known.get(key)
        if field is None:
            continue
        default = getattr(Settings(), key)
        if isinstance(default, bool):
            values[key] = bool(value)
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
