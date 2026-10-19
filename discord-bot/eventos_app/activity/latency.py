"""Latency adjustment of each player.

A QTE answer is timed on the player's screen from the moment they see it, and the bot judges it against windows that start
when the bot started the QTE. Two things sit in between and are not the player's fault:

* **network** -- the QTE took a while to reach them (about half the round trip). It is *added* to what they measured.
* **device** -- their screen shows it late and their touch registers late (a slow phone). It is *taken off*.

The network part is measured by the server itself all the time (it pings every player); the device part comes from the tap
test in the Activity ("Prueba de latencia") and is kept here. Their difference is the adjustment, and it never moves an
answer by more than `cap_ms` (so nobody can buy time by inflating a number)."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

log = logging.getLogger("eventos_app.activity")

NET_MAX_MS = 400.0          # one-way delay credited at most
DEVICE_MAX_MS = 150.0       # device lag taken off at most
CAP_MS = 300.0              # the whole adjustment of one answer, either way


def _num(value, low: float, high: float) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value:
        return None
    return float(min(high, max(low, value)))


def sanitize(raw) -> dict | None:
    """The result of the latency test as the client reports it, with every number forced into a believable range."""
    if not isinstance(raw, dict):
        return None
    out = {
        "median": _num(raw.get("median"), 0, 5000), "min": _num(raw.get("min"), 0, 5000), "p90": _num(raw.get("p90"), 0, 10000),
        "jitter": _num(raw.get("jitter"), 0, 5000), "loss": _num(raw.get("loss"), 0, 1),
        "device": _num(raw.get("device"), 0, DEVICE_MAX_MS), "spread": _num(raw.get("spread"), 0, 2000),
        "taps": int(_num(raw.get("taps"), 0, 100) or 0),
    }
    if out["median"] is None and out["device"] is None:
        return None
    out["at"] = int(time.time())
    return out


def compensation(net_ms: float, device_ms: float, cap_ms: float = CAP_MS) -> dict:
    """What is added (network) and taken off (device) from this player's answers, in ms."""
    return {"net": round(min(NET_MAX_MS, max(0.0, net_ms)), 1), "device": round(min(DEVICE_MAX_MS, max(0.0, device_ms)), 1), "cap": cap_ms}


class LatencyBook:
    """The tap-test result of each player (and the game master's manual device override), by Discord user id."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self._data: dict[str, dict] = {}
        if path is not None and path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                for key, value in (raw.items() if isinstance(raw, dict) else []):
                    clean = sanitize(value)
                    if clean:
                        clean["at"] = int(value.get("at", clean["at"])) if isinstance(value, dict) else clean["at"]
                        self._data[str(key)] = clean
            except (OSError, ValueError):
                log.warning("could not read %s", path)

    def get(self, user_id: int) -> dict | None:
        return self._data.get(str(user_id))

    def device_ms(self, user_id: int) -> float:
        entry = self._data.get(str(user_id)) or {}
        return float(entry.get("device") or 0.0)

    def set(self, user_id: int, raw) -> dict | None:
        clean = sanitize(raw)
        if clean is None:
            return None
        self._data[str(user_id)] = clean
        if user_id > 0:
            self._save()
        return clean

    def clear(self, user_id: int) -> None:
        if self._data.pop(str(user_id), None) is not None and user_id > 0:
            self._save()

    def _save(self) -> None:
        if self.path is None:
            return
        try:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({k: v for k, v in self._data.items() if not k.startswith("-")}, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            log.warning("could not save %s", self.path)
