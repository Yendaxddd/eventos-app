"""Display settings of each player (theme, text size, spacing, size and place of the QTE buttons...), kept by the app so they
follow the person from their phone to their PC. The rules here are the same as `sanitizePrefs` in the web client."""

from __future__ import annotations

import json
import logging
from collections import OrderedDict
from pathlib import Path

from .later import SavesLater

log = logging.getLogger("eventos_app.activity")

DEFAULTS: dict = {
    "theme": "dark", "accent": "violet", "corners": "round", "bg": "plain", "palette": "default", "textScale": 100, "density": "comfortable", "motion": "full", "vfx": "full",
    "buttonScale": 100, "buttonPlacement": "random", "keepEvade": False, "queueMode": False,
    "sound": True, "volume": 60, "haptics": True, "audio": True, "musicVolume": 70, "sfxVolume": 85,
    "cinema": True,
    "showAvatars": True, "showMedia": True, "showTimestamps": True, "showPlayers": True, "compactHud": False,
    "messageLimit": 150, "tutorialDone": False,
}
CHOICES = {
    "theme": ("dark", "oled", "contrast", "midnight", "ember", "forest", "rose", "sepia"),
    "accent": ("violet", "blue", "cyan", "green", "amber", "pink", "red"), "corners": ("round", "sharp", "soft"), "bg": ("plain", "grid", "aurora"), "palette": ("default", "cb"), "density": ("compact", "comfortable", "spacious"),
    "motion": ("full", "reduced"), "vfx": ("full", "soft", "off"), "buttonPlacement": ("random", "bottom", "left", "right"),
}
RANGES = {"textScale": (85, 140), "buttonScale": (70, 160), "volume": (0, 100), "musicVolume": (0, 100), "sfxVolume": (0, 100), "messageLimit": (50, 400)}
MAX_PEOPLE = 2000


def sanitize(raw) -> dict:
    """Every setting that is valid is kept; anything else falls back to the default. Unknown keys are dropped."""
    out = dict(DEFAULTS)
    if not isinstance(raw, dict):
        return out
    for key, default in DEFAULTS.items():
        if key not in raw:
            continue
        value = raw[key]
        if key in CHOICES:
            if value in CHOICES[key]:
                out[key] = value
        elif key in RANGES:
            if isinstance(value, (int, float)) and not isinstance(value, bool) and value == value:
                low, high = RANGES[key]
                out[key] = int(round(min(high, max(low, value))))
        elif isinstance(default, bool):
            out[key] = bool(value)
    return out


class PrefsStore(SavesLater):
    """Settings by Discord user id, in a JSON file (people testing from this PC, with negative ids, are kept in memory only)."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self._data: OrderedDict[str, dict] = OrderedDict()
        if path is not None and path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                for key, value in (raw.items() if isinstance(raw, dict) else []):
                    self._data[str(key)] = sanitize(value)
            except (OSError, ValueError):
                log.warning("could not read %s", path)

    def get(self, user_id: int) -> dict:
        return dict(self._data.get(str(user_id)) or DEFAULTS)

    def has(self, user_id: int) -> bool:
        return str(user_id) in self._data

    def set(self, user_id: int, raw) -> dict:
        clean = sanitize(raw)
        key = str(user_id)
        self._data[key] = clean
        self._data.move_to_end(key)
        while len(self._data) > MAX_PEOPLE:
            self._data.popitem(last=False)
        if user_id > 0:
            self._save_soon()
        return dict(clean)

    def _save(self) -> None:
        if self.path is None:
            return
        try:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({k: v for k, v in self._data.items() if not k.startswith("-")}, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            log.warning("could not save %s", self.path)
