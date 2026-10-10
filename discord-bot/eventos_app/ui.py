"""Main window of the desktop app (CustomTkinter)."""

from __future__ import annotations

import collections
import datetime
import logging
import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk
from PIL import Image

from . import APP_NAME, __version__, paths, settings as settings_store
from .console_bridge import Segment
from .config_page import ConfigPage
from .runner import STOP_TIMEOUT_SECONDS, BotRunner, State
from .theme import (ACCENT, AMBER, BG, BUTTON_NEUTRAL, CARD, CARD_BORDER, GRAY, GREEN, GREEN_HOVER, INACTIVE,
                    LOG_MONO, MUTED, RED, RED_HOVER, TEXT, card)

log = logging.getLogger("eventos_app")

MAX_LOG_LINES = 4000
LINES_PER_TICK = 300

# (action id, caption, colour). Action ids match bot.quick_actions.
DIFFICULTIES = [
    ("easy", "Fácil", "#2e9e5b"),
    ("medium", "Media", "#c9a227"),
    ("hard", "Difícil", "#d1495b"),
    ("impossible", "Imposible", "#8f5bd6"),
]
DEFAULT_KEYS = {
    "single_easy": "F9", "single_medium": "F10", "single_hard": "F11", "single_impossible": "F12",
    "group_easy": "Shift+F9", "group_medium": "Shift+F10", "group_hard": "Shift+F11",
    "group_impossible": "Shift+F12", "checkpoint": "F8", "sync_commands": "F7", "batch_toggle": "Alt+F9",
}

STATUS_STYLE = {
    State.STOPPED: (GRAY, "Detenido"),
    State.STARTING: (AMBER, "Conectando…"),
    State.CONNECTED: (GREEN, "Conectado"),
    State.STOPPING: (AMBER, "Deteniendo…"),
    State.ERROR: (RED, "Error"),
}


def _readable(color: str | None) -> str:
    """Lift dark console colours so they stay legible on the dark background."""
    if not color:
        return TEXT
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    if luminance >= 135:
        return color
    t = (160 - luminance) / (255 - luminance)
    return "#%02x%02x%02x" % tuple(round(c + (255 - c) * t) for c in (r, g, b))


def open_folder(path) -> None:
    try:
        if sys.platform == "win32":
            os.startfile(str(path))  # noqa: S606 - opening a folder we own
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        log.exception("could not open %s", path)


class App(ctk.CTk):
    def __init__(self) -> None:
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        super().__init__(fg_color=BG)

        self.title(APP_NAME)
        self.geometry("1040x720")
        self.minsize(900, 620)
        self._set_icon()

        self.settings = settings_store.load()
        self._log_queue: collections.deque[list[Segment]] = collections.deque(maxlen=20000)
        self._tags: set[str] = set()
        self._last_state: State | None = None
        self._bg_results: collections.deque = collections.deque()
        self._futures: list = []
        self.runner = BotRunner(sink=self._log_queue.append)

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()
        self.config_page = ConfigPage(self, self)
        self.pages = {"panel": self._build_panel(), "config": self.config_page}
        self._show("panel" if self.settings.discord_token.strip() else "config")

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._drain_log)
        self.after(300, self._refresh)
        if self.settings.auto_start and self.settings.discord_token.strip():
            self.after(800, self._start)

    # ---- construction -------------------------------------------------------
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
        side = ctk.CTkFrame(self, width=210, corner_radius=0, fg_color=CARD)
        side.grid(row=0, column=0, sticky="nsw")
        side.grid_propagate(False)
        side.grid_rowconfigure(10, weight=1)

        png = paths.resource_path("eventos_app", "resources", "icon.png")
        if png.exists():
            try:
                img = ctk.CTkImage(Image.open(png), size=(56, 56))
                ctk.CTkLabel(side, image=img, text="").grid(row=0, column=0, padx=20, pady=(24, 6), sticky="w")
            except Exception:
                log.warning("could not load logo", exc_info=True)
        ctk.CTkLabel(side, text=APP_NAME, font=ctk.CTkFont(size=20, weight="bold"), text_color=TEXT).grid(
            row=1, column=0, padx=20, sticky="w")
        ctk.CTkLabel(side, text=f"v{__version__}", text_color=MUTED).grid(row=2, column=0, padx=20, pady=(0, 18), sticky="w")

        self.nav_buttons = {}
        for row, (key, text) in enumerate((("panel", "🎮  Panel"), ("config", "⚙  Configuración")), start=3):
            btn = ctk.CTkButton(
                side, text=text, anchor="w", height=38, corner_radius=8, fg_color="transparent",
                hover_color=CARD_BORDER, text_color=TEXT, command=lambda k=key: self._show(k))
            btn.grid(row=row, column=0, padx=12, pady=2, sticky="ew")
            self.nav_buttons[key] = btn

        for row, (text, target) in enumerate((("📁  Carpeta de datos", paths.app_home),
                                              ("📄  Carpeta de logs", paths.logs_dir)), start=11):
            ctk.CTkButton(side, text=text, anchor="w", height=32, fg_color="transparent", hover_color=CARD_BORDER,
                          text_color=MUTED, command=lambda t=target: open_folder(t())).grid(
                row=row, column=0, padx=12, pady=2, sticky="ew")
        ctk.CTkLabel(side, text="", height=10).grid(row=13, column=0)

    def _build_panel(self) -> ctk.CTkFrame:
        page = ctk.CTkFrame(self, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(3, weight=1)

        # status + start/stop
        status = card(page)
        status.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))
        status.grid_columnconfigure(1, weight=1)
        self.status_dot = ctk.CTkLabel(status, text="●", font=ctk.CTkFont(size=26), text_color=GRAY)
        self.status_dot.grid(row=0, column=0, rowspan=3, padx=(18, 10), pady=14)
        self.status_title = ctk.CTkLabel(status, text="Detenido", font=ctk.CTkFont(size=18, weight="bold"),
                                         text_color=TEXT, anchor="w")
        self.status_title.grid(row=0, column=1, sticky="ew", pady=(14, 0))
        self.status_detail = ctk.CTkLabel(status, text="", text_color=MUTED, anchor="w", justify="left", wraplength=520)
        self.status_detail.grid(row=1, column=1, sticky="ew")
        self.status_event = ctk.CTkLabel(status, text="", text_color=MUTED, anchor="w", justify="left", wraplength=520)
        self.status_event.grid(row=2, column=1, sticky="ew", pady=(0, 12))
        self.toggle_btn = ctk.CTkButton(status, text="▶  Iniciar bot", width=170, height=42, font=ctk.CTkFont(size=14, weight="bold"),
                                        fg_color=GREEN, hover_color=GREEN_HOVER, command=self._toggle)
        self.toggle_btn.grid(row=0, column=2, rowspan=3, padx=18)

        # first-run hint
        self.hint = card(page)
        self.hint.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self.hint, text="👋  Para empezar, pega el token de tu bot de Discord en Configuración.",
                     text_color=TEXT, anchor="w").grid(row=0, column=0, padx=16, pady=12, sticky="w")
        ctk.CTkButton(self.hint, text="Ir a Configuración", width=150, fg_color=ACCENT,
                      command=lambda: self._show("config")).grid(row=0, column=1, padx=16)

        # quick actions
        actions = card(page)
        actions.grid(row=2, column=0, sticky="ew", padx=20, pady=10)
        ctk.CTkLabel(actions, text="Acciones rápidas", font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=TEXT).grid(row=0, column=0, columnspan=6, padx=18, pady=(12, 4), sticky="w")
        self.action_buttons: dict[str, ctk.CTkButton] = {}
        for row, (prefix, title) in enumerate((("single", "Individual"), ("group", "Grupal")), start=1):
            ctk.CTkLabel(actions, text=title, text_color=MUTED, width=80, anchor="w").grid(
                row=row, column=0, padx=(18, 4), pady=4, sticky="w")
            for col, (diff, label, color) in enumerate(DIFFICULTIES, start=1):
                self._action_button(actions, f"{prefix}_{diff}", label, color).grid(
                    row=row, column=col, padx=(4, 18 if col == len(DIFFICULTIES) else 4), pady=4, sticky="ew")
        extras = ctk.CTkFrame(actions, fg_color="transparent")
        extras.grid(row=3, column=0, columnspan=6, padx=14, pady=(2, 12), sticky="w")
        for name, label in (("checkpoint", "💚 Checkpoint (curar)"), ("batch_toggle", "📦 Modo lote"),
                            ("sync_commands", "🔄 Sincronizar comandos")):
            self._action_button(extras, name, label, BUTTON_NEUTRAL, width=190).pack(side="left", padx=4)
        for col in range(1, 5):
            actions.grid_columnconfigure(col, weight=1)

        # live log
        logcard = card(page)
        logcard.grid(row=3, column=0, sticky="nsew", padx=20, pady=(10, 20))
        logcard.grid_columnconfigure(0, weight=1)
        logcard.grid_rowconfigure(1, weight=1)
        head = ctk.CTkFrame(logcard, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 0))
        ctk.CTkLabel(head, text="Registro en vivo", font=ctk.CTkFont(size=14, weight="bold"), text_color=TEXT).pack(side="left")
        ctk.CTkButton(head, text="Limpiar", width=70, height=26, fg_color=BUTTON_NEUTRAL, command=self._clear_log).pack(side="right")
        ctk.CTkButton(head, text="Copiar", width=70, height=26, fg_color=BUTTON_NEUTRAL, command=self._copy_log).pack(side="right", padx=6)
        self.log_box = ctk.CTkTextbox(logcard, fg_color="#121316", text_color=TEXT, font=(LOG_MONO, 12), wrap="word",
                                      border_width=0, corner_radius=8)
        self.log_box.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        self.log_box.configure(state="disabled")
        return page

    def _action_button(self, parent, name: str, label: str, color: str, width: int | None = None) -> ctk.CTkButton:
        kwargs = {"width": width} if width else {}
        btn = ctk.CTkButton(parent, text=self._action_caption(name, label), height=44, fg_color=INACTIVE,
                            hover_color=color, text_color_disabled="#7d818b", state="disabled",
                            command=lambda n=name: self._run_action(n), **kwargs)
        btn._base_label = label  # type: ignore[attr-defined]
        btn._color = color  # type: ignore[attr-defined]
        self.action_buttons[name] = btn
        return btn

    def _action_caption(self, name: str, label: str) -> str:
        key = self.runner.action_label(name).upper() or DEFAULT_KEYS.get(name, "")
        if not (self.settings.hotkeys_enabled and key):
            return label
        return f"{label}\n{key}" if name.startswith(("single_", "group_")) else f"{label}  ({key})"

    # ---- navigation ---------------------------------------------------------
    def _show(self, key: str) -> None:
        for name, frame in self.pages.items():
            if name == key:
                frame.grid(row=0, column=1, sticky="nsew")
            else:
                frame.grid_remove()
        for name, btn in self.nav_buttons.items():
            btn.configure(fg_color=CARD_BORDER if name == key else "transparent")

    # ---- settings -----------------------------------------------------------
    def save_from_page(self) -> None:
        new = self.config_page.collect()
        problems = new.validate()
        if problems:
            self.config_page.flash("⚠ " + " ".join(problems), RED)
            return
        try:
            settings_store.save(new)
        except OSError as exc:
            self.config_page.flash(f"⚠ No se pudo guardar: {exc}", RED)
            return
        self.settings = new
        note = "✓ Guardado." + (" Reinicia el bot para aplicar los cambios de token, IA y atajos." if self.runner.is_active() else "")
        self.config_page.flash(note, GREEN)
        self._refresh_actions_captions()

    def persist_quietly(self) -> None:
        """Save self.settings as they are (used after adding a helper bot etc.)."""
        try:
            settings_store.save(self.settings)
        except OSError:
            log.exception("could not save settings")

    # ---- background work ---------------------------------------------------------
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
        self._log_queue.append([Segment(f"✗ Error de la interfaz: {val}", RED)])

    # ---- bot control --------------------------------------------------------
    def _toggle(self) -> None:
        if self.runner.is_active():
            self.runner.stop()
        else:
            self._start()

    def _start(self) -> None:
        if not self.settings.discord_token.strip():
            self._show("config")
            self.config_page.focus_token()
            return
        self.runner.start(self.settings)

    def _run_action(self, name: str) -> None:
        if not self.runner.run_action(name):
            self._log_queue.append([Segment("El bot todavía no está listo para esa acción.", AMBER)])

    def _refresh_actions_captions(self) -> None:
        for name, btn in self.action_buttons.items():
            btn.configure(text=self._action_caption(name, btn._base_label))  # type: ignore[attr-defined]

    def _refresh(self) -> None:
        state = self.runner.state
        color, title = STATUS_STYLE[state]
        detail = ""
        if state is State.CONNECTED:
            detail = self.runner.describe_connection()
        elif state is State.ERROR:
            detail = self.runner.error
        elif state is State.STOPPED and not self.settings.discord_token.strip():
            detail = "Falta el token del bot."
        elif state is State.STARTING:
            detail = "Iniciando sesión en Discord…"

        self.status_dot.configure(text_color=color)
        self.status_title.configure(text=title)
        self.status_detail.configure(text=detail)
        event = self.runner.event_line()
        self.status_event.configure(text=event, text_color=AMBER if event.startswith("⚠") else MUTED)

        active = self.runner.is_active()
        if state is State.STOPPING:
            self.toggle_btn.configure(text="Deteniendo…", state="disabled")
        elif active:
            self.toggle_btn.configure(text="■  Detener bot", state="normal", fg_color=RED, hover_color=RED_HOVER)
        else:
            self.toggle_btn.configure(text="▶  Iniciar bot", state="normal", fg_color=GREEN, hover_color=GREEN_HOVER)

        ready = state is State.CONNECTED
        for btn in self.action_buttons.values():
            btn.configure(state="normal" if ready else "disabled", fg_color=btn._color if ready else INACTIVE)  # type: ignore[attr-defined]
        if state is not self._last_state and ready:
            self._refresh_actions_captions()
        self._last_state = state
        self.config_page.tick(state)

        if self.settings.discord_token.strip():
            self.hint.grid_remove()
        else:
            self.hint.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 10))
        self.after(400, self._refresh)

    # ---- log panel ----------------------------------------------------------
    def _tag_for(self, color: str | None) -> str:
        color = _readable(color)
        tag = "c" + color[1:]
        if tag not in self._tags:
            self.log_box.tag_config(tag, foreground=color)
            self._tags.add(tag)
        return tag

    def _insert(self, text: str, tag: str) -> None:
        try:
            self.log_box.insert("end", text, tag)
        except tk.TclError:  # some Tk builds can't draw characters outside the BMP
            safe = "".join(ch if ord(ch) <= 0xFFFF else "?" for ch in text)
            self.log_box.insert("end", safe, tag)

    def _drain_log(self) -> None:
        self._drain_background()
        if self._log_queue:
            at_bottom = self.log_box.yview()[1] >= 0.99
            self.log_box.configure(state="normal")
            for _ in range(min(LINES_PER_TICK, len(self._log_queue))):
                segments = self._log_queue.popleft()
                self._insert(datetime.datetime.now().strftime("%H:%M:%S  "), self._tag_for("#6b7280"))
                for seg in segments:
                    self._insert(seg.text, self._tag_for("#8b8f98" if seg.dim and not seg.color else seg.color))
                self._insert("\n", self._tag_for(None))
            lines = int(self.log_box.index("end-1c").split(".")[0])
            if lines > MAX_LOG_LINES:
                self.log_box.delete("1.0", f"{lines - MAX_LOG_LINES + 500}.0")
            self.log_box.configure(state="disabled")
            if at_bottom:
                self.log_box.see("end")
        self.after(100, self._drain_log)

    def _clear_log(self) -> None:
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def _copy_log(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self.log_box.get("1.0", "end-1c"))

    # ---- closing ------------------------------------------------------------
    def _on_close(self) -> None:
        if self.runner.is_active():
            if not messagebox.askyesno(
                APP_NAME, "El bot sigue en ejecución.\n\n¿Cerrar la app y detenerlo? Los datos se guardan antes de salir."):
                return
            self.withdraw()
            self.runner.stop(wait=STOP_TIMEOUT_SECONDS)
        self.destroy()
