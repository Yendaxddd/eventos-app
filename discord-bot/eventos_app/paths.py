"""Where the app keeps its files.

Layout (all next to each other, so a user can back up / move one folder):

    <home>/data/        player data and game config (JSON)
    <home>/assets/      GIFs and images
    <home>/logs/        log files
    <home>/settings.json
    <home>/.env         optional, power users only

<home> is, in order of preference:
    1. $EVENTOS_HOME, if set
    2. the folder with the .exe (frozen) or discord-bot/ (running from source),
       as long as it is writable
    3. %APPDATA%\\EventosApp (or ~/.eventos-app), seeded from the install folder,
       for when the app lives somewhere read-only such as Program Files
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

DIR_NAME = "EventosApp"
_home_cache: Path | None = None


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def install_dir() -> Path:
    """Folder that holds the .exe, or discord-bot/ when running from source."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def bundle_dir() -> Path:
    """Folder holding code and resources that PyInstaller packed into the build."""
    return Path(getattr(sys, "_MEIPASS", install_dir()))


def _is_writable(folder: Path) -> bool:
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def _fallback_home() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / DIR_NAME
    return Path.home() / ".eventos-app"


def app_home() -> Path:
    global _home_cache
    if _home_cache is not None:
        return _home_cache

    override = os.environ.get("EVENTOS_HOME")
    if override:
        home = Path(override).expanduser().resolve()
        home.mkdir(parents=True, exist_ok=True)
    elif _is_writable(install_dir()):
        home = install_dir()
    else:
        home = _fallback_home()
        home.mkdir(parents=True, exist_ok=True)

    _home_cache = home
    return home


def data_dir() -> Path:
    return app_home() / "data"


def assets_dir() -> Path:
    return app_home() / "assets"


def logs_dir() -> Path:
    path = app_home() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings_file() -> Path:
    return app_home() / "settings.json"


def resource_path(*parts: str) -> Path:
    """A file shipped inside the build (icons etc). Works frozen and from source."""
    return bundle_dir().joinpath(*parts)


def seed_defaults() -> None:
    """If <home> is not the install folder, copy over data/ and assets/ once.

    Existing files are never overwritten, so user changes survive app updates.
    """
    home, source = app_home(), install_dir()
    if home == source:
        return
    for name in ("data", "assets"):
        src = source / name
        if not src.is_dir():
            continue
        for item in src.rglob("*"):
            if not item.is_file():
                continue
            dest = home / name / item.relative_to(src)
            if dest.exists():
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dest)
