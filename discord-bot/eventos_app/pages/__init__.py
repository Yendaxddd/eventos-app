"""The pages of the desktop window. Each one is a frame the shell (ui.App) shows one at a time."""

from __future__ import annotations

import customtkinter as ctk

from ..theme import MUTED, TEXT, font


class Page(ctk.CTkFrame):
    """A page: a header (title, a line under it, buttons on the right) and whatever the page puts under row 0."""

    title = ""
    subtitle = ""

    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.grid_columnconfigure(0, weight=1)

    def header(self, subtitle: str | None = None, pad=(26, 8)) -> ctk.CTkFrame:
        """Build row 0. Returns the frame on its right where the page puts its main buttons."""
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", padx=26, pady=pad)
        bar.grid_columnconfigure(0, weight=1)
        text = ctk.CTkFrame(bar, fg_color="transparent")
        text.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(text, text=self.title, font=font(24, "bold"), text_color=TEXT, anchor="w").pack(anchor="w")
        self.subtitle_label = ctk.CTkLabel(text, text=self.subtitle if subtitle is None else subtitle, text_color=MUTED, font=font(13),
                                           anchor="w", justify="left", wraplength=560)
        self.subtitle_label.pack(anchor="w")
        actions = ctk.CTkFrame(bar, fg_color="transparent", width=1, height=1)       # an empty CTkFrame asks for 200x200: it must not
        actions.grid(row=0, column=1, sticky="e")
        return actions

    def set_subtitle(self, text: str) -> None:
        if self.subtitle_label.cget("text") != text:
            self.subtitle_label.configure(text=text)

    def on_show(self) -> None:
        """The page has just been opened."""

    def tick(self, state) -> None:
        """Every ~400 ms, whether or not the page is the one on screen (keep it cheap)."""
