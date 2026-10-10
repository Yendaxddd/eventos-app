"""Main window of the desktop app (CustomTkinter)."""

from __future__ import annotations

import collections
import datetime
import logging
import os
import subprocess
import sys
import tkinter as tk
import webbrowser
from tkinter import messagebox

import customtkinter as ctk
from PIL import Image

from . import APP_NAME, __version__, paths, settings as settings_store
from .console_bridge import Segment
from .runner import STOP_TIMEOUT_SECONDS, BotRunner, State

log = logging.getLogger("eventos_app")

# ---- look -------------------------------------------------------------------
BG = "#16171a"
CARD = "#1f2125"
CARD_BORDER = "#2b2e34"
TEXT = "#e4e4e7"
MUTED = "#9a9ea8"
ACCENT = "#7c5cff"
GREEN, GREEN_HOVER = "#2e9e5b", "#268a4e"
RED, RED_HOVER = "#d1495b", "#b53c4d"
AMBER = "#e0a030"
GRAY = "#6b7280"
INACTIVE = "#2a2d33"
LOG_MONO = "Consolas" if sys.platform == "win32" else "DejaVu Sans Mono"

DEVELOPER_PORTAL = "https://discord.com/developers/applications"
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


def card(parent, **kwargs) -> ctk.CTkFrame:
    return ctk.CTkFrame(parent, fg_color=CARD, border_color=CARD_BORDER, border_width=1, corner_radius=12, **kwargs)


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
        self._saved_flash = None
        self.runner = BotRunner(sink=self._log_queue.append)

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()
        self.pages = {"panel": self._build_panel(), "config": self._build_config()}
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
        self.status_dot.grid(row=0, column=0, rowspan=2, padx=(18, 10), pady=14)
        self.status_title = ctk.CTkLabel(status, text="Detenido", font=ctk.CTkFont(size=18, weight="bold"),
                                         text_color=TEXT, anchor="w")
        self.status_title.grid(row=0, column=1, sticky="ew", pady=(14, 0))
        self.status_detail = ctk.CTkLabel(status, text="", text_color=MUTED, anchor="w", justify="left", wraplength=520)
        self.status_detail.grid(row=1, column=1, sticky="ew", pady=(0, 14))
        self.toggle_btn = ctk.CTkButton(status, text="▶  Iniciar bot", width=170, height=42, font=ctk.CTkFont(size=14, weight="bold"),
                                        fg_color=GREEN, hover_color=GREEN_HOVER, command=self._toggle)
        self.toggle_btn.grid(row=0, column=2, rowspan=2, padx=18)

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
            self._action_button(extras, name, label, "#3b3f47", width=190).pack(side="left", padx=4)
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
        ctk.CTkButton(head, text="Limpiar", width=70, height=26, fg_color="#3b3f47", command=self._clear_log).pack(side="right")
        ctk.CTkButton(head, text="Copiar", width=70, height=26, fg_color="#3b3f47", command=self._copy_log).pack(side="right", padx=6)
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

    def _build_config(self) -> ctk.CTkFrame:
        page = ctk.CTkFrame(self, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)
        scroll = ctk.CTkScrollableFrame(page, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 0))
        scroll.grid_columnconfigure(0, weight=1)

        s = self.settings
        self.vars: dict[str, tk.Variable] = {
            "discord_token": tk.StringVar(value=s.discord_token),
            "qte_player_role_id": tk.StringVar(value=s.qte_player_role_id),
            "admin_role_id": tk.StringVar(value=s.admin_role_id),
            "gm_role_id": tk.StringVar(value=s.gm_role_id),
            "ollama_endpoint": tk.StringVar(value=s.ollama_endpoint),
            "ollama_model": tk.StringVar(value=s.ollama_model),
            "reset_on_start": tk.BooleanVar(value=s.reset_on_start),
            "hotkeys_enabled": tk.BooleanVar(value=s.hotkeys_enabled),
            "auto_start": tk.BooleanVar(value=s.auto_start),
        }

        def section(title: str, row: int) -> ctk.CTkFrame:
            box = card(scroll)
            box.grid(row=row, column=0, sticky="ew", padx=10, pady=8)
            box.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(box, text=title, font=ctk.CTkFont(size=15, weight="bold"), text_color=TEXT).grid(
                row=0, column=0, columnspan=3, padx=18, pady=(14, 6), sticky="w")
            return box

        def field(box, row, label, key, show=None):
            ctk.CTkLabel(box, text=label, text_color=MUTED, anchor="w").grid(row=row, column=0, padx=(18, 12), pady=6, sticky="w")
            entry = ctk.CTkEntry(box, textvariable=self.vars[key], show=show, height=34)
            entry.grid(row=row, column=1, padx=(0, 18), pady=6, sticky="ew")
            return entry

        # Discord
        box = section("Bot de Discord", 0)
        self.token_entry = field(box, 1, "Token del bot", "discord_token", show="•")
        row = ctk.CTkFrame(box, fg_color="transparent")
        row.grid(row=2, column=1, padx=(0, 18), pady=(0, 12), sticky="w")
        self.show_token = ctk.CTkSwitch(row, text="Mostrar token", progress_color=ACCENT, command=self._toggle_token)
        self.show_token.pack(side="left")
        ctk.CTkButton(row, text="¿Dónde lo consigo?", width=150, height=26, fg_color="transparent", border_width=1,
                      border_color=CARD_BORDER, text_color=MUTED, hover_color=CARD_BORDER,
                      command=lambda: webbrowser.open(DEVELOPER_PORTAL)).pack(side="left", padx=14)
        ctk.CTkLabel(box, text="Developer Portal → tu aplicación → Bot → «Reset Token». Se guarda solo en este equipo.",
                     text_color=MUTED, anchor="w").grid(row=3, column=0, columnspan=2, padx=18, pady=(0, 12), sticky="w")

        # Roles
        box = section("Roles (opcional)", 1)
        field(box, 1, "Rol de jugadores (ID)", "qte_player_role_id")
        field(box, 2, "Rol de GM (ID)", "gm_role_id")
        field(box, 3, "Rol de admin (ID)", "admin_role_id")
        ctk.CTkLabel(box, text="El canal de los QTE se elige desde Discord con el comando /setchannel.",
                     text_color=MUTED, anchor="w").grid(row=4, column=0, columnspan=2, padx=18, pady=(2, 12), sticky="w")

        # Startup
        box = section("Inicio", 2)
        ctk.CTkCheckBox(box, text="Iniciar el bot automáticamente al abrir la app", fg_color=ACCENT, hover_color=ACCENT, variable=self.vars["auto_start"]).grid(
            row=1, column=0, columnspan=2, padx=18, pady=6, sticky="w")
        ctk.CTkCheckBox(box, text="Reiniciar HP, cargas y buffs cada vez que se inicia el bot",
                        fg_color=ACCENT, hover_color=ACCENT, variable=self.vars["reset_on_start"]).grid(row=2, column=0, columnspan=2, padx=18, pady=6, sticky="w")
        ctk.CTkCheckBox(box, text="Atajos de teclado globales (F9–F12, F8…) — funcionan aunque la app esté en segundo plano",
                        fg_color=ACCENT, hover_color=ACCENT, variable=self.vars["hotkeys_enabled"]).grid(row=3, column=0, columnspan=2, padx=18, pady=(6, 14), sticky="w")

        # AI
        box = section("IA (Ollama, opcional)", 3)
        field(box, 1, "Dirección", "ollama_endpoint")
        field(box, 2, "Modelo", "ollama_model")
        ctk.CTkLabel(box, text="", height=6).grid(row=3, column=0)

        # save bar
        bar = ctk.CTkFrame(page, fg_color="transparent")
        bar.grid(row=1, column=0, sticky="ew", padx=20, pady=14)
        ctk.CTkButton(bar, text="Guardar cambios", width=160, height=38, fg_color=ACCENT, command=self._save_settings).pack(side="left")
        self.save_msg = ctk.CTkLabel(bar, text="", text_color=MUTED)
        self.save_msg.pack(side="left", padx=14)
        return page

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
    def _toggle_token(self) -> None:
        self.token_entry.configure(show="" if self.show_token.get() else "•")

    def _collect_settings(self) -> settings_store.Settings:
        return settings_store.Settings(**{k: v.get() for k, v in self.vars.items()})

    def _save_settings(self) -> None:
        new = self._collect_settings()
        problems = new.validate()
        if problems:
            self._flash_save("⚠ " + " ".join(problems), RED)
            return
        try:
            settings_store.save(new)
        except OSError as exc:
            self._flash_save(f"⚠ No se pudo guardar: {exc}", RED)
            return
        self.settings = new
        note = "✓ Guardado." + (" Reinicia el bot para aplicar los cambios." if self.runner.is_active() else "")
        self._flash_save(note, GREEN)
        self._refresh_actions_captions()

    def _flash_save(self, text: str, color: str) -> None:
        self.save_msg.configure(text=text, text_color=color)
        if self._saved_flash:
            self.after_cancel(self._saved_flash)
        self._saved_flash = self.after(6000, lambda: self.save_msg.configure(text=""))

    # ---- bot control --------------------------------------------------------
    def _toggle(self) -> None:
        if self.runner.is_active():
            self.runner.stop()
        else:
            self._start()

    def _start(self) -> None:
        if not self.settings.discord_token.strip():
            self._show("config")
            self.token_entry.focus_set()
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
