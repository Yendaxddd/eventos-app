"""«Actividad»: the state and address of the Activity, who is inside it and how good their connection is, opening the GM panel in a window of
its own, and the Activity's settings."""

from __future__ import annotations

import webbrowser

import customtkinter as ctk

from ..runner import State
from ..theme import BAD_TEXT, FAINT, MUTED, OK_TEXT, TEXT, WARN_TEXT, button, card, font, raised
from ..widgets import Pill
from . import Page

DEVELOPER_PORTAL = "https://discord.com/developers/applications"
MAX_ROWS = 40


def quality_of(rtt_ms: float | None) -> tuple[str, str]:
    """(word, colour) for a player's round trip: what the host reads in the list of connections."""
    if rtt_ms is None:
        return "sin medir", FAINT
    if rtt_ms < 90:
        return "excelente", OK_TEXT
    if rtt_ms < 160:
        return "buena", OK_TEXT
    if rtt_ms < 300:
        return "regular", WARN_TEXT
    return "mala", BAD_TEXT


def connected_for(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds} s"
    if seconds < 3600:
        return f"{seconds // 60} min"
    return f"{seconds // 3600} h {seconds % 3600 // 60} min"


class ActivityPage(Page):
    title = "Actividad"
    subtitle = "La pantalla del evento dentro de Discord: botones de QTE, los paneles de cada jugador y el panel del GM."

    def __init__(self, master, app) -> None:
        super().__init__(master, app)
        self.grid_rowconfigure(1, weight=1)
        self._rows: list[tuple[ctk.CTkFrame, ctk.CTkLabel, ctk.CTkLabel, ctk.CTkLabel]] = []
        self._address = ""
        actions = self.header()
        self.state_pill = Pill(actions, "Apagada", "idle")
        self.state_pill.pack(side="left")

        self.body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.body.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 14))
        self.body.grid_columnconfigure((0, 1), weight=1, uniform="cols")
        self._build_status()
        self._build_open()
        self._build_connected()
        self._build_settings()
        self._build_steps()

    # ---- construction --------------------------------------------------------------------------------------------------------------
    def _build_status(self) -> None:
        box = card(self.body)
        box.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(4, 8))
        box.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(box, text="Dirección", font=font(15, "bold"), text_color=TEXT).grid(row=0, column=0, padx=20, pady=(14, 4), sticky="w")
        line = raised(box)
        line.grid(row=1, column=0, sticky="ew", padx=20, pady=4)
        line.grid_columnconfigure(0, weight=1)
        self.address = ctk.CTkLabel(line, text="Todavía no hay dirección", font=("Consolas" if self._win() else "DejaVu Sans Mono", 14),
                                    text_color=MUTED, anchor="w")
        self.address.grid(row=0, column=0, padx=16, pady=12, sticky="ew")
        buttons = ctk.CTkFrame(line, fg_color="transparent")
        buttons.grid(row=0, column=1, padx=8)
        self.copy_btn = button(buttons, "Copiar", self.copy_address, kind="primary", width=84, height=30)
        self.copy_btn.pack(side="left", padx=3)
        self.new_btn = button(buttons, "Nueva dirección", self.new_address, kind="neutral", width=130, height=30)
        self.new_btn.pack(side="left", padx=3)
        self.detail = ctk.CTkLabel(box, text="", text_color=MUTED, anchor="w", justify="left", wraplength=700)
        self.detail.grid(row=2, column=0, padx=20, pady=(6, 14), sticky="w")

    def _build_open(self) -> None:
        box = card(self.body)
        box.grid(row=1, column=0, sticky="nsew", padx=12, pady=8)
        ctk.CTkLabel(box, text="Abrir", font=font(15, "bold"), text_color=TEXT).pack(anchor="w", padx=20, pady=(14, 8))
        button(box, "🧭  Panel del GM (ventana propia)", self.app.open_gm_panel, kind="primary", height=40).pack(fill="x", padx=20, pady=4)
        ctk.CTkLabel(box, text="Lanza QTE, controla al jefe, a los jugadores, los valores y el contenido. Solo se abre desde este PC.",
                     text_color=FAINT, font=font(12), anchor="w", justify="left", wraplength=330).pack(anchor="w", padx=20, pady=(0, 8))
        button(box, "🌐  Ver la Actividad como jugador", self.app.open_player_window, kind="neutral", height=36).pack(fill="x", padx=20, pady=4)
        button(box, "Developer Portal", lambda: webbrowser.open(DEVELOPER_PORTAL), kind="ghost", height=32).pack(fill="x", padx=20, pady=(4, 6))
        button(box, "Comprobar la dirección desde fuera", self.check_outside, kind="ghost", height=32).pack(fill="x", padx=20, pady=(0, 16))

    def _build_connected(self) -> None:
        box = card(self.body)
        box.grid(row=1, column=1, sticky="nsew", padx=12, pady=8)
        box.grid_columnconfigure(0, weight=1)
        head = ctk.CTkFrame(box, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=20, pady=(14, 6))
        ctk.CTkLabel(head, text="Conectados ahora", font=font(15, "bold"), text_color=TEXT).pack(side="left")
        self.count = ctk.CTkLabel(head, text="", text_color=MUTED)
        self.count.pack(side="left", padx=10)
        self.list = ctk.CTkScrollableFrame(box, fg_color="transparent", height=190)
        self.list.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 6))
        self.list.grid_columnconfigure(0, weight=1)
        self.empty = ctk.CTkLabel(box, text="Nadie conectado todavía.", text_color=FAINT)
        self.empty.grid(row=2, column=0, pady=(0, 16))

    def _build_settings(self) -> None:
        box = card(self.body)
        box.grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=8)
        box.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(box, text="Ajustes de la Actividad", font=font(15, "bold"), text_color=TEXT).grid(
            row=0, column=0, columnspan=4, padx=20, pady=(14, 6), sticky="w")
        self.app.config_page.build_activity_settings(box, first_row=1)

    def _build_steps(self) -> None:
        box = card(self.body)
        box.grid(row=3, column=0, columnspan=2, sticky="ew", padx=12, pady=(8, 16))
        ctk.CTkLabel(box, text="Puesta en marcha (una sola vez)", font=font(15, "bold"), text_color=TEXT).pack(anchor="w", padx=20, pady=(14, 6))
        steps = (
            "En el Developer Portal → tu aplicación → Activities: pulsa «Enable Activities».",
            "OAuth2 → Redirects: añade https://127.0.0.1 y copia el «Client Secret» (pégalo arriba, en los ajustes).",
            "Activities → URL Mappings: en la raíz «/» pega la dirección de arriba. Con Tailscale es fija: solo la primera vez.",
            "Aquí: activa la Actividad, guarda e inicia el bot. Los jugadores la abren desde Discord (cohete en un canal de voz, o «+» → Apps).",
        )
        for number, text in enumerate(steps, start=1):
            row = ctk.CTkFrame(box, fg_color="transparent")
            row.pack(fill="x", padx=20, pady=2)
            ctk.CTkLabel(row, text=str(number), width=24, text_color=FAINT, font=font(13, "bold")).pack(side="left", anchor="n")
            ctk.CTkLabel(row, text=text, text_color=MUTED, anchor="w", justify="left", wraplength=760).pack(side="left", anchor="w")
        ctk.CTkLabel(box, text="", height=8).pack()

    @staticmethod
    def _win() -> bool:
        import sys
        return sys.platform == "win32"

    # ---- actions -------------------------------------------------------------------------------------------------------------------------
    def copy_address(self) -> None:
        if not self._address:
            self.app.toast("Todavía no hay dirección: el túnel se abre al iniciar el bot.", "warn")
            return
        self.clipboard_clear()
        self.clipboard_append(self._address)
        self.app.toast(f"Copiada: {self._address}. Pégala en URL Mappings, raíz «/».", "ok")

    def new_address(self) -> None:
        try:
            future = self.app.runner.reopen_tunnel()
        except RuntimeError as exc:
            self.app.toast(str(exc), "warn")
            return
        self.app.toast("Abriendo un túnel nuevo…", "info")
        self.app.watch(future, lambda result: None, lambda exc: self.app.toast(f"✗ {exc}", "bad", 6000))

    def check_outside(self) -> None:
        client_id = self.app.runner.activity_info().get("client_id")
        if not client_id:
            self.app.toast("La Actividad no está en marcha.", "warn")
            return
        webbrowser.open(f"https://{client_id}.discordsays.com/healthz")

    # ---- every ~400 ms ---------------------------------------------------------------------------------------------------------------------
    def tick(self, state: State) -> None:
        info = self.app.runner.activity_info()
        enabled = bool(self.app.settings.activity_enabled)
        if not info.get("running"):
            self._address = ""
            self.state_pill.set("Desactivada" if not enabled else "Se activa al iniciar el bot", "idle")
            self.address.configure(text="Todavía no hay dirección", text_color=FAINT)
            self.detail.configure(text="Activa la Actividad en los ajustes de abajo, guarda e inicia el bot." if not enabled
                                  else "Inicia el bot y la dirección aparecerá aquí.", text_color=MUTED)
            self.copy_btn.configure(state="disabled")
            self.new_btn.configure(state="disabled")
            self._render_connections([])
            return
        tunnel = info["tunnel"]
        self.copy_btn.configure(state="normal" if tunnel == "up" else "disabled")
        self.new_btn.configure(state="normal")
        lines = []
        if tunnel == "up":
            self._address = info["url"].removeprefix("https://")
            self.address.configure(text=self._address, text_color=TEXT)
            self.state_pill.set("Lista", "ok" if info["secret_set"] else "warn")
            lines.append("Pégala en el Developer Portal → Activities → URL Mappings (raíz «/»). " +
                         ("Es fija: solo la primera vez." if info.get("fixed") else "Cambia en cada inicio."))
        elif tunnel == "error":
            self._address = ""
            self.address.configure(text="No se pudo abrir el túnel", text_color=BAD_TEXT)
            self.state_pill.set("Error", "bad")
            lines.append(info["detail"] or "El túnel no se pudo abrir.")
        else:
            self._address = ""
            self.address.configure(text="Abriendo el túnel…", text_color=MUTED)
            self.state_pill.set("Abriendo…", "warn")
            lines.append(info["detail"] or "Preparando el túnel.")
        if not info["secret_set"]:
            lines.append("⚠ Falta el Client Secret: nadie podrá entrar desde Discord. Pégalo en los ajustes de abajo.")
        self.detail.configure(text="\n".join(lines), text_color=BAD_TEXT if tunnel == "error" else (WARN_TEXT if not info["secret_set"] else MUTED))
        self._render_connections(info.get("users", []))

    def _render_connections(self, users: list[dict]) -> None:
        visible = users[:MAX_ROWS]
        while len(self._rows) < len(visible):
            row = raised(self.list)
            row.grid_columnconfigure(0, weight=1)
            name = ctk.CTkLabel(row, text="", text_color=TEXT, anchor="w")
            name.grid(row=0, column=0, padx=(12, 6), pady=7, sticky="ew")
            ping = ctk.CTkLabel(row, text="", width=120, anchor="e", font=font(12))
            ping.grid(row=0, column=1, padx=6)
            since = ctk.CTkLabel(row, text="", width=64, anchor="e", text_color=FAINT, font=font(12))
            since.grid(row=0, column=2, padx=(0, 12))
            self._rows.append((row, name, ping, since))
        for index, (row, name, ping, since) in enumerate(self._rows):
            if index >= len(visible):
                row.grid_remove()
                continue
            user = visible[index]
            row.grid(row=index, column=0, sticky="ew", pady=3)
            word, color = quality_of(user.get("rtt_ms"))
            label = user["name"].replace(" (prueba local)", "") + ("  · esta app" if user.get("hidden") else "")
            name.configure(text=label)
            ping.configure(text=f"{round(user['rtt_ms'])} ms · {word}" if user.get("rtt_ms") is not None else word, text_color=color)
            since.configure(text=connected_for(user.get("seconds", 0)))
        self.count.configure(text=f"{len([u for u in users if not u.get('hidden')])} jugadores" if users else "")
        if visible:
            self.empty.grid_remove()
        else:
            self.empty.grid()
