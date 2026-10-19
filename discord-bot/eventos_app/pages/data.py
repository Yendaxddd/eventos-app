"""«Datos»: where the event's data lives and its copies: make one now, one every time the bot stops, restore one."""

from __future__ import annotations

import time
from tkinter import messagebox

import customtkinter as ctk

from .. import backups, browser, paths
from ..theme import FAINT, MUTED, TEXT, button, card, font, raised
from . import Page


def human_size(size: int) -> str:
    """1536 -> «1,5 KB»."""
    units = ("B", "KB", "MB", "GB")
    value, unit = float(size), 0
    while value >= 1024 and unit < len(units) - 1:
        value /= 1024
        unit += 1
    text = f"{value:.0f}" if unit == 0 or value >= 100 else f"{value:.1f}".replace(".", ",")
    return f"{text} {units[unit]}"


def since(timestamp: float | None, now: float | None = None) -> str:
    """«hace 3 min»: how long ago something happened."""
    if not timestamp:
        return "nunca"
    seconds = max(0, int((now if now is not None else time.time()) - timestamp))
    if seconds < 60:
        return "hace un momento"
    if seconds < 3600:
        return f"hace {seconds // 60} min"
    if seconds < 86400:
        return f"hace {seconds // 3600} h"
    return f"hace {seconds // 86400} d"


class DataPage(Page):
    title = "Datos"
    subtitle = "Lo que el evento va guardando (jugadores, logros, objetos, valores) y sus copias de seguridad."

    def __init__(self, master, app) -> None:
        super().__init__(master, app)
        self.grid_rowconfigure(1, weight=1)
        self._rows: list[ctk.CTkFrame] = []
        self.header()
        self.body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.body.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 14))
        self.body.grid_columnconfigure(0, weight=1)
        self._build_summary()
        self._build_backups()

    # ---- construction --------------------------------------------------------------------------------------------------------------
    def _build_summary(self) -> None:
        box = card(self.body)
        box.grid(row=0, column=0, sticky="ew", padx=12, pady=(4, 8))
        box.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(box, text="Datos del evento", font=font(15, "bold"), text_color=TEXT).grid(row=0, column=0, padx=20, pady=(14, 2), sticky="w")
        self.summary = ctk.CTkLabel(box, text="", text_color=MUTED, anchor="w", justify="left")
        self.summary.grid(row=1, column=0, padx=20, sticky="w")
        self.where = ctk.CTkLabel(box, text=str(paths.app_home()), text_color=FAINT, font=font(12), anchor="w", justify="left", wraplength=760)
        self.where.grid(row=2, column=0, padx=20, pady=(2, 8), sticky="w")
        row = ctk.CTkFrame(box, fg_color="transparent")
        row.grid(row=3, column=0, padx=16, pady=(0, 14), sticky="w")
        for text, target in (("📁  Carpeta de datos", paths.data_dir), ("💾  Carpeta de copias", lambda: backups.backups_dir(paths.app_home())),
                             ("📄  Carpeta de logs", paths.logs_dir)):
            button(row, text, lambda t=target: self._open(t()), kind="neutral", width=170, height=32).pack(side="left", padx=4)

    def _build_backups(self) -> None:
        box = card(self.body)
        box.grid(row=1, column=0, sticky="ew", padx=12, pady=8)
        box.grid_columnconfigure(0, weight=1)
        head = ctk.CTkFrame(box, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=20, pady=(14, 4))
        ctk.CTkLabel(head, text="Copias de seguridad", font=font(15, "bold"), text_color=TEXT).pack(side="left")
        self.make_btn = button(head, "💾  Crear copia ahora", self.create_now, kind="primary", width=180, height=34)
        self.make_btn.pack(side="right")
        self.auto = ctk.CTkSwitch(box, text="Hacer una copia cada vez que se detiene el bot (solo si hubo cambios)", progress_color="#8b5cf6",
                                  command=self._auto_changed)
        self.auto.grid(row=1, column=0, padx=20, pady=(6, 4), sticky="w")
        ctk.CTkLabel(box, text="Una copia guarda los datos del evento, no el token ni el Client Secret. Para volver atrás, restaura la que quieras con el bot detenido: "
                               "antes se guarda una copia de lo que hay ahora, así nada se pierde.",
                     text_color=FAINT, font=font(12), anchor="w", justify="left", wraplength=760).grid(row=2, column=0, padx=20, pady=(0, 8), sticky="w")
        self.list = ctk.CTkFrame(box, fg_color="transparent", height=1)               # empty, a CTkFrame would ask for 200 px
        self.list.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 10))
        self.list.grid_columnconfigure(0, weight=1)
        self.empty = ctk.CTkLabel(box, text="Todavía no hay copias.", text_color=FAINT)
        self.empty.grid(row=4, column=0, pady=(0, 16))

    # ---- showing ---------------------------------------------------------------------------------------------------------------------------
    def on_show(self, **_options) -> None:
        self.refresh()

    def refresh(self) -> None:
        home = paths.app_home()
        summary = backups.data_summary(home)
        self.summary.configure(text=f"{summary['files']} archivos · {human_size(summary['bytes'])} · último cambio {since(summary['newest'])}")
        self.auto.select() if self.app.settings.backup_on_stop else self.auto.deselect()
        listed = backups.list_backups(home)
        for row in self._rows:
            row.destroy()
        self._rows = []
        for index, copy in enumerate(listed[:30]):
            row = raised(self.list)
            row.grid(row=index, column=0, sticky="ew", pady=3)
            row.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(row, text=copy.title, text_color=TEXT, anchor="w").grid(row=0, column=0, padx=14, pady=9, sticky="w")
            ctk.CTkLabel(row, text=human_size(copy.size), text_color=FAINT, font=font(12), width=70, anchor="e").grid(row=0, column=1, padx=6)
            button(row, "Restaurar", lambda c=copy: self.restore(c), kind="neutral", width=94, height=28).grid(row=0, column=2, padx=4)
            button(row, "Borrar", lambda c=copy: self.delete(c), kind="ghost", width=70, height=28).grid(row=0, column=3, padx=(4, 10))
            self._rows.append(row)
        if listed:
            self.empty.grid_remove()
        else:
            self.empty.grid()

    def tick(self, state) -> None:
        pass

    # ---- actions ---------------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _open(path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        browser.open_folder(path)

    def _auto_changed(self) -> None:
        self.app.settings.backup_on_stop = bool(self.auto.get())
        self.app.config_page.vars["backup_on_stop"].set(self.app.settings.backup_on_stop)
        self.app.persist_quietly()

    def create_now(self) -> None:
        self.make_btn.configure(state="disabled", text="Guardando…")

        def work():
            if self.app.runner.is_active():
                self.app.runner.flush_data()               # what the bot knows goes to disk first
            return backups.make_backup(paths.app_home(), keep=backups.KEEP_AUTOMATIC)

        def done(path) -> None:
            self.make_btn.configure(state="normal", text="💾  Crear copia ahora")
            self.app.toast(f"Copia creada: {path.name}", "ok")
            self.refresh()

        def failed(exc: BaseException) -> None:
            self.make_btn.configure(state="normal", text="💾  Crear copia ahora")
            self.app.toast(str(exc) if isinstance(exc, backups.BackupError) else f"No se pudo crear la copia: {exc}", "bad", 6500)

        self.app.bg(work, done, failed)

    def restore(self, copy: backups.Backup) -> None:
        if self.app.runner.is_active():
            self.app.toast("Detén el bot antes de restaurar una copia.", "warn", 5500)
            return
        if not messagebox.askyesno("Restaurar copia", f"¿Restaurar los datos de la copia del {copy.title}?\n\nAntes se guarda una copia de lo que hay ahora."):
            return

        def done(safety) -> None:
            self.app.toast("Datos restaurados." + (f" Lo anterior quedó en {safety.name}." if safety else ""), "ok", 7000)
            self.refresh()

        self.app.bg(lambda: backups.restore_backup(paths.app_home(), copy.path), done,
                    lambda exc: self.app.toast(str(exc) if isinstance(exc, backups.BackupError) else f"No se pudo restaurar: {exc}", "bad", 8000))

    def delete(self, copy: backups.Backup) -> None:
        if not messagebox.askyesno("Borrar copia", f"¿Borrar la copia del {copy.title}?"):
            return
        try:
            backups.delete_backup(paths.app_home(), copy.path)
        except backups.BackupError as exc:
            self.app.toast(str(exc), "bad", 6000)
            return
        self.app.toast("Copia borrada.", "ok")
        self.refresh()
