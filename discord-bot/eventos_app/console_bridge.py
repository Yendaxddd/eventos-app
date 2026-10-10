"""Lets the bot keep calling `console.print("[green]...[/green]")` while the app
decides where that text goes.

Headless (Docker, `python advanced_qte_hp_system_debug.py`): no sink is set, so
everything goes to a normal rich Console, exactly as before.

Desktop app: the GUI installs a sink and receives each print as a list of
`Segment`s (text + colour), which it draws in the log panel. This is why a
windowed .exe never touches stdout (which is None in that mode).
"""

from __future__ import annotations

import io
import re
import sys
from typing import Callable, NamedTuple

from rich.cells import cell_len
from rich.console import Console
from rich.style import Style
from rich.text import Text


class Segment(NamedTuple):
    text: str
    color: str | None = None  # "#rrggbb"
    bold: bool = False
    dim: bool = False


Sink = Callable[[list[Segment]], None]


def _style_at(text: Text, index: int) -> Style:
    style = Style()
    for span in text.spans:
        if not span.start <= index < span.end:
            continue
        try:
            span_style = Style.parse(span.style) if isinstance(span.style, str) else span.style
        except Exception:  # unknown colour name etc: skip styling, keep the text
            continue
        style = style + span_style
    return style


def _text_to_segments(text: Text) -> list[Segment]:
    plain = text.plain
    if not plain:
        return []
    cuts = {0, len(plain)}
    for span in text.spans:
        cuts.add(max(0, min(span.start, len(plain))))
        cuts.add(max(0, min(span.end, len(plain))))
    bounds = sorted(cuts)
    segments: list[Segment] = []
    for start, end in zip(bounds, bounds[1:]):
        if start == end:
            continue
        style = _style_at(text, start)
        color = None
        if style.color is not None:
            try:
                rgb = style.color.get_truecolor()
                color = f"#{rgb.red:02x}{rgb.green:02x}{rgb.blue:02x}"
            except Exception:
                color = None
        segments.append(Segment(plain[start:end], color, bool(style.bold), bool(style.dim)))
    return segments


# Inside tables and panels, emoji break the right-hand border: rich counts them as 1 or 2 columns, a
# monospace font draws them however it likes. Swap them for plain symbols of the width rich expects.
_EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D]+")
_SYMBOLS = {"✅": "OK", "❌": "NO", "⚠": "!", "✓": "+", "✗": "x", "⭐": "*", "🔴": "o", "🟢": "o", "🟡": "o"}


def _flatten_emoji(text: str) -> str:
    def replace(match: re.Match) -> str:
        chunk = match.group(0)
        width = cell_len(chunk)
        symbol = "".join(_SYMBOLS.get(ch, "") for ch in chunk)
        return symbol[:width].ljust(width)

    return _EMOJI.sub(replace, text)


def _render_block(renderable, width: int = 96) -> str:
    """Panels, tables etc. become plain monospace text."""
    buffer = io.StringIO()
    Console(file=buffer, width=width, force_terminal=False, color_system=None, legacy_windows=False).print(renderable)
    return _flatten_emoji(buffer.getvalue().rstrip("\n"))


def to_segments(objects: tuple, sep: str = " ") -> list[Segment]:
    segments: list[Segment] = []
    for i, obj in enumerate(objects):
        if i:
            segments.append(Segment(sep))
        if isinstance(obj, str):
            try:
                segments.extend(_text_to_segments(Text.from_markup(obj)))
            except Exception:  # stray "[...]" in a message that rich can't parse
                segments.append(Segment(obj))
        elif isinstance(obj, Text):
            segments.extend(_text_to_segments(obj))
        else:
            segments.append(Segment(_render_block(obj)))
    return segments


class ConsoleProxy:
    """Drop-in for `rich.console.Console` for the calls the bot makes."""

    def __init__(self) -> None:
        self._sink: Sink | None = None
        self._real: Console | None = None

    def set_sink(self, sink: Sink | None) -> None:
        self._sink = sink

    def print(self, *objects, sep: str = " ", end: str = "\n", **kwargs) -> None:
        sink = self._sink
        if sink is not None:
            try:
                sink(to_segments(objects, sep))
            except Exception:
                pass  # logging must never break the bot
            return
        if sys.stdout is None:  # windowed build with no sink yet
            return
        if self._real is None:
            self._real = Console()
        self._real.print(*objects, sep=sep, end=end, **kwargs)


console = ConsoleProxy()
