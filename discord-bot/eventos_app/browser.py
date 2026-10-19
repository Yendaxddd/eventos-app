"""Opening the Activity from the desktop app: in a window of its own (the host's GM panel looks like a program, not a browser tab)
or in the normal browser. Edge ships with Windows 10 and 11, so there is nearly always a browser that can open «app windows»."""

from __future__ import annotations

import logging
import ntpath
import os
import shutil
import subprocess
import sys
import webbrowser
from typing import Callable
from urllib.parse import quote

log = logging.getLogger("eventos_app")

HOST_NAME = "Anfitrión"                  # the name the host's window uses; it is not listed among the players (see the Activity server)
WINDOW_SIZE = (1280, 860)

_WINDOWS_BROWSERS = (
    ("ProgramFiles(x86)", r"Microsoft\Edge\Application\msedge.exe"), ("ProgramFiles", r"Microsoft\Edge\Application\msedge.exe"),
    ("LOCALAPPDATA", r"Microsoft\Edge\Application\msedge.exe"),
    ("ProgramFiles", r"Google\Chrome\Application\chrome.exe"), ("ProgramFiles(x86)", r"Google\Chrome\Application\chrome.exe"),
    ("LOCALAPPDATA", r"Google\Chrome\Application\chrome.exe"),
)
_COMMANDS = ("microsoft-edge", "microsoft-edge-stable", "google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome")


def find_app_browser(platform: str = sys.platform, environ: dict | None = None, which: Callable[[str], str | None] = shutil.which,
                     exists: Callable[[str], bool] = os.path.exists) -> str | None:
    """A browser that can open a page as an «app window» (no tabs, no address bar), or None. Edge first, then Chrome."""
    environ = os.environ if environ is None else environ
    if platform == "win32":
        for variable, relative in _WINDOWS_BROWSERS:
            base = environ.get(variable)
            if base:
                candidate = ntpath.join(base, relative)
                if exists(candidate):
                    return candidate
    for name in _COMMANDS:
        found = which(name)
        if found:
            return found
    return None


def app_window_command(url: str, browser: str, size: tuple[int, int] = WINDOW_SIZE) -> list[str]:
    return [browser, f"--app={url}", f"--window-size={size[0]},{size[1]}", "--no-first-run", "--no-default-browser-check"]


def host_url(port: int, *, gm: bool = True, name: str = HOST_NAME) -> str:
    """The address of the Activity as the host sees it from this very PC: a test window (no Discord), with the GM panel if asked."""
    return f"http://127.0.0.1:{int(port)}/?dev={quote(name)}" + ("&gm=1&host=1" if gm else "")


def open_app_window(url: str, *, find: Callable[[], str | None] = find_app_browser, spawn: Callable = subprocess.Popen,
                    fallback: Callable[[str], object] = webbrowser.open) -> str:
    """Open `url` in an app window; if there is no browser for that, in the normal one. Returns what was used: «window» or «browser»."""
    browser = find()
    if browser:
        try:
            spawn(app_window_command(url, browser), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
            return "window"
        except OSError:
            log.warning("could not start %s as an app window", browser, exc_info=True)
    fallback(url)
    return "browser"


def open_folder(path) -> bool:
    """Show a folder in the system's file explorer."""
    try:
        if sys.platform == "win32":
            os.startfile(str(path))  # noqa: S606 - opening a folder we own
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
        return True
    except Exception:  # noqa: BLE001
        log.exception("could not open %s", path)
        return False
