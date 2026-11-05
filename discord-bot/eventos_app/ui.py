"""Main window of the desktop app (CustomTkinter): the sidebar, the pages and the services they share (the bot, the log, background work)."""

from __future__ import annotations

import collections
import datetime
import logging
import os
import sys
import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox

import customtkinter as ctk
from PIL import Image

from . import APP_NAME, __version__, browser, paths, settings as settings_store, theme, updates
from .config_page import ConfigPage
from .console_bridge import Segment
from .logview import Line, LogHub
from .pages import Page
from .pages.activity import ActivityPage
from .pages.data import DataPage
from .pages.help import HelpPage
from .pages.home import STATUS, HomePage
from .pages.log import LogPage
from .runner import STOP_TIMEOUT_SECONDS, BotRunner, State
from .theme import ACCENT, ACCENT_SOFT, BG, BAD_TEXT, FAINT, MUTED, OK_TEXT, SIDEBAR, TEXT, WARN_TEXT, button, font
from .widgets import Pill, Toast

log = logging.getLogger("eventos_app")

LINES_PER_TICK = 300
UPDATE_CHECK_DELAY_MS = 4000                      # after the window is up and the bot (if it starts by itself) is already connecting
NAV = (("home", "🏠", "Inicio"), ("activity", "🌐", "Actividad"), ("data", "💾", "Datos"), ("log", "📜", "Registro"),
       ("config", "⚙", "Configuración"), ("help", "❓", "Ayuda"))


class App(ctk.CTk):
    def __init__(self) -> None:
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        theme.apply()
        super().__init__(fg_color=BG)

        self.title(APP_NAME)
        self.geometry("1120x780")
        self.minsize(1000, 700)
        self._set_icon()

        self.settings = settings_store.load()
        self.hub = LogHub()
        self._log_queue: collections.deque[list[Segment]] = collections.deque(maxlen=20000)
        self._bg_results: collections.deque = collections.deque()
        self._futures: list = []
        self.runner = BotRunner(sink=self._log_queue.append)
        self.current = ""
        self.update_info: updates.Update | None = None                 # the newer release the sidebar is announcing, if any
        self._checking_updates = False

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()
        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)
        self.toast_bar = Toast(self.content)

        self.home = HomePage(self.content, self)
        self.config_page = ConfigPage(self.content, self)
        self.pages: dict[str, Page | ConfigPage] = {
            "home": self.home, "activity": ActivityPage(self.content, self), "data": DataPage(self.content, self),
            "log": LogPage(self.content, self), "config": self.config_page, "help": HelpPage(self.content, self)}
        self.home.refresh_captions()
        self.show_page("home")

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        for index, (key, _icon, _label) in enumerate(NAV, start=1):
            self.bind_all(f"<Control-Key-{index}>", lambda _e, k=key: self.show_page(k))
        self.after(100, self._drain_log)
        self.after(300, self._refresh)
        if self.settings.auto_start and self.settings.discord_token.strip():
            self.after(800, self._start)
        if self.settings.check_updates and os.environ.get("EVENTOS_NO_UPDATE_CHECK") != "1":
            self.after(UPDATE_CHECK_DELAY_MS, self.check_for_updates)

    # ---- construction -------------------------------------------------------------------------------------------------------
    def _set_icon(self) -> None:
        ico = paths.resource_path("eventos_app", "resources", "icon.ico")
        png = paths.resource_path("eventos_app", "resources", "icon.png")
        try:
            if sys.platform == "win32" and ico.exists():
                # CustomTkinter installs its own icon ~200 ms after start; override it after that.
                self.after(250, lambda: self.iconbitmap(str(ico)))
            elif png.exists():
                self.iconphoto(True, tk.PhotoImage(file=str(png)))
        except Exception:
            log.warning("could not set window icon", exc_info=True)

    def _build_sidebar(self) -> None:
        side = ctk.CTkFrame(self, width=236, corner_radius=0, fg_color=SIDEBAR)
        side.grid(row=0, column=0, sticky="nsw")
        side.grid_propagate(False)
        side.grid_columnconfigure(0, weight=1)
        side.grid_rowconfigure(20, weight=1)

        head = ctk.CTkFrame(side, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=20, pady=(24, 22))
        png = paths.resource_path("eventos_app", "resources", "icon.png")
        if png.exists():
            try:
                ctk.CTkLabel(head, image=ctk.CTkImage(Image.open(png), size=(44, 44)), text="").pack(side="left")
            except Exception:
                log.warning("could not load logo", exc_info=True)
        title = ctk.CTkFrame(head, fg_color="transparent")
        title.pack(side="left", padx=12)
        ctk.CTkLabel(title, text=APP_NAME, font=font(18, "bold"), text_color=TEXT, anchor="w").pack(anchor="w")
        ctk.CTkLabel(title, text=f"v{__version__}", text_color=FAINT, font=font(12), anchor="w").pack(anchor="w")

        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        for row, (key, icon, label) in enumerate(NAV, start=1):
            btn = ctk.CTkButton(side, text=f"{icon}   {label}", anchor="w", height=42, corner_radius=10, fg_color="transparent", hover_color="#1a1a2e",
                                text_color=MUTED, font=font(14), command=lambda k=key: self.show_page(k))
            btn.grid(row=row, column=0, padx=14, pady=2, sticky="ew")
            self.nav_buttons[key] = btn

        self.update_card = ctk.CTkFrame(side, fg_color="#1d1840", border_color=ACCENT, border_width=1, corner_radius=14)
        self.update_card.grid(row=21, column=0, sticky="ew", padx=14, pady=(8, 0))
        self.update_card.grid_columnconfigure(0, weight=1)
        self.update_title = ctk.CTkLabel(self.update_card, text="", font=font(13, "bold"), text_color="#c9b8ff", anchor="w")
        self.update_title.grid(row=0, column=0, padx=14, pady=(12, 0), sticky="w")
        self.update_notes = ctk.CTkLabel(self.update_card, text="", font=font(12), text_color=MUTED, anchor="w", justify="left", wraplength=176)
        self.update_notes.grid(row=1, column=0, padx=14, pady=(2, 6), sticky="w")
        self.update_download = button(self.update_card, "⬇  Descargar e instalar", self.open_update, kind="primary", height=32, font=font(12, "bold"))
        self.update_download.grid(row=2, column=0, padx=12, pady=(0, 4), sticky="ew")
        self.update_news = button(self.update_card, "Ver novedades", lambda: self.open_update(notes=True), kind="ghost", height=28, font=font(12))
        self.update_news.grid(row=3, column=0, padx=12, pady=(0, 12), sticky="ew")
        self.update_card.grid_remove()

        foot = ctk.CTkFrame(side, fg_color="#141426", corner_radius=14)
        foot.grid(row=22, column=0, sticky="ew", padx=14, pady=(8, 8))
        foot.grid_columnconfigure(0, weight=1)
        self.side_pill = Pill(foot, "Detenido", "idle")
        self.side_pill.grid(row=0, column=0, padx=14, pady=(14, 8), sticky="w")
        self.side_toggle = button(foot, "▶  Iniciar bot", self.toggle_bot, kind="good", height=36, font=font(13, "bold"))
        self.side_toggle.grid(row=1, column=0, padx=14, pady=(0, 14), sticky="ew")
        for row, (text, target) in enumerate((("📁  Carpeta de datos", paths.app_home), ("📄  Carpeta de logs", paths.logs_dir)), start=23):
            ctk.CTkButton(side, text=text, anchor="w", height=30, fg_color="transparent", hover_color="#1a1a2e", text_color=FAINT, font=font(12),
                          command=lambda t=target: browser.open_folder(t())).grid(row=row, column=0, padx=14, pady=1, sticky="ew")
        ctk.CTkLabel(side, text="", height=8).grid(row=25, column=0)

    # ---- navigation ---------------------------------------------------------------------------------------------------------
    def show_page(self, key: str, **options) -> None:
        for name, frame in self.pages.items():
            if name == key:
                frame.grid(row=0, column=0, sticky="nsew")
            else:
                frame.grid_remove()
        for name, btn in self.nav_buttons.items():
            btn.configure(fg_color=ACCENT_SOFT if name == key else "transparent", text_color=TEXT if name == key else MUTED)
        self.current = key
        page = self.pages[key]
        if hasattr(page, "on_show"):
            page.on_show(**options)
        self.toast_bar.lift()

    def toast(self, text: str, kind: str = "info", ms: int = 4200) -> None:
        self.toast_bar.show(text, kind, ms)

    # ---- settings -----------------------------------------------------------------------------------------------------------
    def save_from_page(self) -> None:
        new = self.config_page.collect()
        problems = new.validate()
        if problems:
            self.toast("⚠ " + " ".join(problems), "bad", 6500)
            return
        try:
            settings_store.save(new)
        except OSError as exc:
            self.toast(f"⚠ No se pudo guardar: {exc}", "bad", 6500)
            return
        self.settings = new
        note = "✓ Guardado." + (" Reinicia el bot para aplicar los cambios de token, IA y atajos." if self.runner.is_active() else "")
        self.toast(note, "ok", 5200)
        self.config_page.flash(note, OK_TEXT)
        self.home.refresh_captions()

    def persist_quietly(self) -> None:
        """Save self.settings as they are (used after adding a helper bot etc.)."""
        try:
            settings_store.save(self.settings)
        except OSError:
            log.exception("could not save settings")

    # ---- background work --------------------------------------------------------------------------------------------------------
    def bg(self, work, done, failed=None) -> None:
        """Run `work()` on a thread; call done(result) / failed(exc) back on the UI thread."""
        def run() -> None:
            try:
                outcome = (True, work())
            except BaseException as exc:  # noqa: BLE001
                outcome = (False, exc)
            self._bg_results.append((outcome, done, failed))

        threading.Thread(target=run, name="ui-background", daemon=True).start()

    def watch(self, future, done, failed=None) -> None:
        """Call done(result) / failed(exc) on the UI thread when a concurrent Future finishes."""
        self._futures.append((future, done, failed))

    def _drain_background(self) -> None:
        finished = [(item[0], item[1], item[2]) for item in self._futures if item[0].done()]
        self._futures = [item for item in self._futures if not item[0].done()]
        results = []
        for future, done, failed in finished:
            try:
                results.append(((True, future.result()), done, failed))
            except BaseException as exc:  # noqa: BLE001
                results.append(((False, exc), done, failed))
        while self._bg_results:
            results.append(self._bg_results.popleft())
        for (ok, value), done, failed in results:
            callback = done if ok else failed
            if callback is None:
                if not ok:
                    log.error("background task failed: %s", value)
                continue
            try:
                callback(value)
            except Exception:  # noqa: BLE001
                log.exception("background callback failed")

    def report_callback_exception(self, exc, val, tb) -> None:
        """Tk calls this when a UI callback raises. Without a console the traceback would vanish."""
        log.error("UI error", exc_info=(exc, val, tb))
        self._log_queue.append([Segment(f"✗ Error de la interfaz: {val}", BAD_TEXT)])

    # ---- bot control ---------------------------------------------------------------------------------------------------------
    def toggle_bot(self) -> None:
        if self.runner.is_active():
            self.runner.stop()
        else:
            self._start()

    def _start(self) -> None:
        if not self.settings.discord_token.strip():
            self.show_page("config", tab="bot")
            self.config_page.focus_token()
            self.toast("Pega primero el token de tu bot de Discord.", "warn")
            return
        self.runner.start(self.settings)

    def run_action(self, name: str) -> None:
        if not self.runner.run_action(name):
            self._log_queue.append([Segment("El bot todavía no está listo para esa acción.", WARN_TEXT)])

    # ---- the Activity in a window of its own -----------------------------------------------------------------------------------------
    def open_gm_panel(self) -> None:
        url = self.runner.host_url(gm=True)
        if not url:
            self.toast("La Actividad no está en marcha: actívala en la página Actividad y inicia el bot.", "warn", 6000)
            self.show_page("activity")
            return
        if browser.open_app_window(url) == "browser":
            self.toast("Se abrió en tu navegador (no se encontró Edge ni Chrome para una ventana propia).", "info", 5000)

    def open_player_window(self) -> None:
        url = self.runner.host_url(gm=False)
        if not url:
            self.toast("La Actividad no está en marcha: actívala en la página Actividad y inicia el bot.", "warn", 6000)
            self.show_page("activity")
            return
        webbrowser.open(url)

    # ---- new versions ----------------------------------------------------------------------------------------------------------------
    def check_for_updates(self, manual: bool = False) -> None:
        """Ask GitHub for the latest release. On its own it only speaks up if there is a newer one; when asked for (the Help page) it also says
        «estás al día» or why it could not find out."""
        if self._checking_updates:
            return
        self._checking_updates = True

        def done(update: updates.Update | None) -> None:
            self._checking_updates = False
            self.show_update(update)
            if manual:
                self.toast(f"Hay una versión nueva: {update.version}." if update else f"Estás al día: la {__version__} es la última.", "info" if update else "ok")

        def failed(exc: BaseException) -> None:
            self._checking_updates = False
            if manual:
                self.toast(str(exc) if isinstance(exc, updates.UpdateCheckError) else f"No se pudo buscar actualizaciones: {exc}", "warn", 6000)

        self.bg(lambda: updates.check(quiet=not manual), done, failed)

    def show_update(self, update: updates.Update | None) -> None:
        self.update_info = update
        if update is None:
            self.update_card.grid_remove()
            return
        self.update_title.configure(text=f"⬆  Versión {update.version}")
        self.update_notes.configure(text=update.notes or "Hay una versión nueva de la app.")
        self.update_card.grid()

    def open_update(self, notes: bool = False) -> None:
        """«Descargar» takes the installer (running it over the installed app updates it, keeping the data); «Novedades» the release page."""
        update = self.update_info
        if update is not None:
            webbrowser.open(update.url if notes or not update.installer else update.installer)

    # ---- every ~400 ms ---------------------------------------------------------------------------------------------------------------
    def _refresh(self) -> None:
        state = self.runner.state
        tone, text = STATUS[state]
        self.side_pill.set(text, tone)
        if state is State.STOPPING:
            self.side_toggle.configure(text="Deteniendo…", state="disabled")
        elif self.runner.is_active():
            self.side_toggle.configure(text="■  Detener bot", state="normal", fg_color="#d6455d", hover_color="#b8374d")
        else:
            self.side_toggle.configure(text="▶  Iniciar bot", state="normal", fg_color="#1f9d6c", hover_color="#188358")
        for page in self.pages.values():
            page.tick(state)
        self.after(400, self._refresh)

    # ---- the log ------------------------------------------------------------------------------------------------------------------------
    def _drain_log(self) -> None:
        self._drain_background()
        if self._log_queue:
            stamp = datetime.datetime.now().strftime("%H:%M:%S  ")
            lines = []
            for _ in range(min(LINES_PER_TICK, len(self._log_queue))):
                segments = self._log_queue.popleft()
                lines.append(Line(stamp, tuple((seg.text, "dim" if seg.dim and not seg.color else seg.color) for seg in segments)))
            self.hub.add(lines)
        self.after(100, self._drain_log)

    # ---- closing ---------------------------------------------------------------------------------------------------------------------------
    def _on_close(self) -> None:
        if self.runner.is_active():
            if not messagebox.askyesno(
                APP_NAME, "El bot sigue en ejecución.\n\n¿Cerrar la app y detenerlo? Los datos se guardan antes de salir."):
                return
            self.withdraw()
            self.runner.stop(wait=STOP_TIMEOUT_SECONDS)
        self.destroy()
