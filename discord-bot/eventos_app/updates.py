"""«¿Hay una versión nueva?»: asks GitHub for the latest release and says so when it is newer than the one running. Quiet about everything
that can go wrong (no internet, rate limits, odd answers): an update notice is a convenience, never a reason to bother the person."""

from __future__ import annotations

import json
import logging
import re
import urllib.request
from dataclasses import dataclass
from typing import Callable

from . import __version__

log = logging.getLogger("eventos_app")

REPOSITORY = "Yendaxddd/eventos-app"
RELEASES_API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPOSITORY}/releases/latest"


class UpdateCheckError(Exception):
    """The latest release could not be looked up (only raised when asked not to stay quiet)."""


@dataclass(frozen=True)
class Update:
    version: str                 # «1.0.1»
    url: str                     # the release's page
    notes: str                   # its first lines, for a tooltip or a line of text
    installer: str = ""          # the installer's direct download, if the release has one


def parse_version(text: str) -> tuple[int, int, int] | None:
    """«v1.2.3» or «1.2.3-beta» -> (1, 2, 3); None if it does not look like a version."""
    match = re.match(r"^\s*v?(\d+)\.(\d+)(?:\.(\d+))?", str(text or ""))
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)


def is_newer(latest: str, current: str = __version__) -> bool:
    a, b = parse_version(latest), parse_version(current)
    return a is not None and b is not None and a > b


def fetch_json(url: str, timeout: float = 6.0) -> dict:
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": f"EventosApp/{__version__}"})
    with urllib.request.urlopen(request, timeout=timeout) as reply:  # noqa: S310 - a fixed https address
        return json.loads(reply.read().decode("utf-8"))


def check(current: str = __version__, fetch: Callable[[str], dict] | None = None, *, quiet: bool = True) -> Update | None:
    """The latest release if it is newer than `current`; None when up to date. When it could not be found out the answer is also None, unless
    `quiet` is False (somebody pressed «buscar actualizaciones» and wants to know): then UpdateCheckError says so."""
    try:
        release = (fetch or fetch_json)(RELEASES_API)
    except Exception as exc:  # noqa: BLE001 - no internet, no answer, rate limit...
        log.info("update check skipped: %s", exc)
        if not quiet:
            raise UpdateCheckError("No se pudo consultar GitHub: revisa tu conexión a internet e inténtalo de nuevo.") from exc
        return None
    if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
        return None
    tag = str(release.get("tag_name") or "")
    if not is_newer(tag, current):
        return None
    installer = ""
    for asset in release.get("assets") or []:
        name = str(asset.get("name", "")) if isinstance(asset, dict) else ""
        if name.startswith("EventosApp-Setup") and name.endswith(".exe"):
            installer = str(asset.get("browser_download_url", ""))
    lines = [line.strip("# ").strip() for line in str(release.get("body") or "").splitlines() if line.strip()]
    return Update(version=tag.lstrip("vV"), url=str(release.get("html_url") or RELEASES_PAGE), notes=lines[0][:160] if lines else "", installer=installer)
