"""The game-master panel's server side: every operation re-implements what a bot command or hotkey does, with the same limits.

`GmPanel` is built once by the bridge; the bridge decides who may call it (see `gm_rpc.py`)."""
from __future__ import annotations

from pathlib import Path

from .boss import BossOps
from .common import GmLog
from .data import DataOps
from .event import EventOps
from .players import PlayerOps
from .values import ValueOps

__all__ = ["GmLog", "GmPanel"]


class GmPanel(EventOps, BossOps, PlayerOps, ValueOps, DataOps):
    def __init__(self, app, log: GmLog | None = None, data_dir: Path | None = None, values_file: Path | None = None) -> None:
        self.app = app
        self.log = log or GmLog()
        self.data_dir = Path(data_dir) if data_dir else None
        self.values_file = Path(values_file) if values_file else None

    def _emit(self, event: str, /, **data) -> None:
        """Tell the Activity (sound cues, cinematics) about what the panel just did, as the bot itself does for the same thing."""
        emit = getattr(self.app, "emit_event", None)
        if emit is not None:
            emit(event, **data)
