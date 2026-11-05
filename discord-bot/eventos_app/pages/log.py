"""«Registro»: everything the bot says, with a search box and a «only problems» switch."""

from __future__ import annotations

import customtkinter as ctk

from .. import browser, paths
from ..logview import LogView
from ..theme import INPUT_BG, button, card
from . import Page


class LogPage(Page):
    title = "Registro"
    subtitle = "Todo lo que dice el bot, en vivo. Busca una palabra o mira solo los avisos y errores."

    def __init__(self, master, app) -> None:
        super().__init__(master, app)
        self.grid_rowconfigure(2, weight=1)
        actions = self.header()
        button(actions, "Abrir carpeta de logs", lambda: browser.open_folder(paths.logs_dir()), kind="ghost", width=170, height=32).pack(side="right")

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=1, column=0, sticky="ew", padx=26, pady=(2, 8))
        bar.grid_columnconfigure(0, weight=1)
        self.search = ctk.CTkEntry(bar, placeholder_text="Buscar en el registro…", height=36, fg_color=INPUT_BG, border_width=0)      # no textvariable: it hides the placeholder
        self.search.grid(row=0, column=0, sticky="ew")
        self.search.bind("<KeyRelease>", lambda _e: self._filter())
        self.problems = ctk.CTkSwitch(bar, text="Solo avisos y errores", progress_color="#8b5cf6", command=self._filter)
        self.problems.grid(row=0, column=1, padx=16)
        button(bar, "Copiar", self.copy, kind="neutral", width=76, height=34).grid(row=0, column=2, padx=3)
        button(bar, "Limpiar", self.clear, kind="neutral", width=76, height=34).grid(row=0, column=3, padx=3)

        box = card(self)
        box.grid(row=2, column=0, sticky="nsew", padx=26, pady=(0, 22))
        box.grid_columnconfigure(0, weight=1)
        box.grid_rowconfigure(0, weight=1)
        self.view = LogView(box, app.hub, max_lines=3500, font_size=12)
        self.view.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

    def _filter(self) -> None:
        self.view.set_filter(self.search.get(), bool(self.problems.get()))

    def copy(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self.app.hub.text())
        self.app.toast("Registro copiado.", "ok")

    def clear(self) -> None:
        self.app.hub.clear()

    def on_show(self, **_options) -> None:
        self.view.box.see("end")
