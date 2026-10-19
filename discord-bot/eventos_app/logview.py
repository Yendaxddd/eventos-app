"""The live log: one stream of lines, shown in as many places as needed (the last lines on the Home page, the whole history on the Log page)."""

from __future__ import annotations

import collections
import tkinter as tk
from dataclasses import dataclass

import customtkinter as ctk

from .theme import LOG_MONO, TEXT

MAX_STORED = 4000
PROBLEM_MARKS = ("⚠", "✗", "error", "fallo", "falló", "no se pudo", "traceback")


@dataclass(frozen=True)
class Line:
    stamp: str                                   # «12:03:41  »
    segments: tuple[tuple[str, str | None], ...]  # (text, colour or None for the normal one)

    @property
    def plain(self) -> str:
        return self.stamp + "".join(text for text, _ in self.segments)

    @property
    def is_problem(self) -> bool:
        lowered = self.plain.lower()
        return any(mark in lowered for mark in PROBLEM_MARKS)


def readable(color: str | None) -> str:
    """Lift dark console colours so they stay legible on the dark background."""
    if not color:
        return TEXT
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    if luminance >= 135:
        return color
    t = (160 - luminance) / (255 - luminance)
    return "#%02x%02x%02x" % tuple(round(c + (255 - c) * t) for c in (r, g, b))


class LogHub:
    """Keeps the last lines and tells every view about the new ones."""

    def __init__(self, maxlen: int = MAX_STORED) -> None:
        self.lines: collections.deque[Line] = collections.deque(maxlen=maxlen)
        self.views: list[LogView] = []

    def add(self, new: list[Line]) -> None:
        self.lines.extend(new)
        for view in self.views:
            view.append(new)

    def clear(self) -> None:
        self.lines.clear()
        for view in self.views:
            view.rebuild()

    def text(self) -> str:
        return "\n".join(line.plain for line in self.lines)


class LogView(ctk.CTkFrame):
    """A coloured, read-only box of log lines that follows the bottom while you are there. Can show only what matches a text, or only problems."""

    def __init__(self, master, hub: LogHub, *, max_lines: int = 1200, font_size: int = 12, fg_color: str = "#0a0a12", height: int | None = None) -> None:
        super().__init__(master, fg_color="transparent")
        self.hub, self.max_lines = hub, max_lines
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        options = {"height": height} if height else {}
        self.box = ctk.CTkTextbox(self, fg_color=fg_color, text_color=TEXT, font=(LOG_MONO, font_size), wrap="word", border_width=0, corner_radius=10, **options)
        self.box.grid(row=0, column=0, sticky="nsew")
        self.box.configure(state="disabled")
        self._tags: set[str] = set()
        self._query = ""
        self._problems = False
        self._shown = 0
        hub.views.append(self)
        self.rebuild()

    # ---- what is shown ----------------------------------------------------------------------------------------
    def set_filter(self, query: str = "", problems: bool = False) -> None:
        query = query.strip().lower()
        if (query, problems) != (self._query, self._problems):
            self._query, self._problems = query, problems
            self.rebuild()

    def _wanted(self, line: Line) -> bool:
        if self._problems and not line.is_problem:
            return False
        return not self._query or self._query in line.plain.lower()

    def _tag(self, color: str | None) -> str:
        color = readable(color)
        tag = "c" + color[1:]
        if tag not in self._tags:
            self.box.tag_config(tag, foreground=color)
            self._tags.add(tag)
        return tag

    def _insert(self, text: str, tag: str) -> None:
        try:
            self.box.insert("end", text, tag)
        except tk.TclError:                       # some Tk builds can't draw characters outside the BMP
            self.box.insert("end", "".join(ch if ord(ch) <= 0xFFFF else "?" for ch in text), tag)

    def _write(self, lines) -> int:
        count = 0
        for line in lines:
            if not self._wanted(line):
                continue
            self._insert(line.stamp, self._tag("#6b7280"))
            for text, color in line.segments:
                self._insert(text, self._tag("#8b8f98" if color == "dim" else color))
            self._insert("\n", self._tag(None))
            count += 1
        return count

    def rebuild(self) -> None:
        self.box.configure(state="normal")
        self.box.delete("1.0", "end")
        self._shown = self._write(list(self.hub.lines)[-self.max_lines * 3:])
        self._trim()
        self.box.configure(state="disabled")
        self.box.see("end")

    def append(self, lines: list[Line]) -> None:
        at_bottom = self.box.yview()[1] >= 0.99
        self.box.configure(state="normal")
        self._shown += self._write(lines)
        self._trim()
        self.box.configure(state="disabled")
        if at_bottom:
            self.box.see("end")

    def _trim(self) -> None:
        if self._shown > self.max_lines:
            drop = self._shown - self.max_lines + max(20, self.max_lines // 10)
            self.box.delete("1.0", f"{drop + 1}.0")
            self._shown -= drop

    def destroy(self) -> None:
        if self in self.hub.views:
            self.hub.views.remove(self)
        super().destroy()
