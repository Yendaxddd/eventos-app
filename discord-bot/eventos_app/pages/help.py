"""«Ayuda»: the first steps, the keys, the usual problems and the information to paste when asking for help."""

from __future__ import annotations

import webbrowser

import customtkinter as ctk

from .. import browser, paths, support
from ..theme import FAINT, MUTED, TEXT, button, card, font
from . import Page

REPOSITORY = "https://github.com/Yendaxddd/eventos-app"

FIRST_STEPS = (
    "Configuración → pega el token de tu bot (Developer Portal → tu aplicación → Bot → Reset Token) y guarda.",
    "Inicio → «Iniciar bot». Cuando conecte, en Configuración → Bot y evento elige el servidor, el canal de los QTE y los roles.",
    "Actividad → activa la Actividad, pega el Client Secret y sigue los 4 pasos del Developer Portal (solo la primera vez).",
    "Inicio → «Abrir el panel del GM» para llevar el evento desde su ventana: lanza QTE, controla al jefe y a los jugadores.",
)
KEYS = (
    ("F9 · F10 · F11 · F12", "QTE individual fácil · media · difícil · imposible"),
    ("Mayús + F9 … F12", "El mismo QTE para todo el grupo"),
    ("F8", "Checkpoint: cura a todos los jugadores"),
    ("F7", "Sincronizar los comandos de barra"),
    ("Alt + F9", "Modo lote: prepara varios QTE y envíalos juntos"),
    ("Ctrl + 1 … 6", "Cambiar de página en esta ventana"),
)
PROBLEMS = (
    ("La Actividad sale en blanco en Discord",
     "Revisa que la dirección esté en URL Mappings (raíz «/»), que el túnel diga «Lista» y que /healthz abra desde fuera (botón en Actividad). "
     "Tras cambiar el mapping, cierra la Actividad y vuelve a lanzarla."),
    ("«Falta el Client Secret»", "Developer Portal → OAuth2 → Client Secret. Pégalo en Actividad → Ajustes y guarda."),
    ("Discord va lento o dice 429", "Añade bots auxiliares y deja activados los webhooks (Configuración → Envío). La prueba de rendimiento te dice cuántos hacen falta."),
    ("Perdí datos del evento", "Datos → Copias de seguridad: restaura la última. Con el bot detenido; antes se guarda lo que hay ahora."),
    ("El panel del GM no abre", "La Actividad debe estar en marcha (Actividad → Lista). Se abre con Edge o Chrome; si no hay, en tu navegador."),
)


class HelpPage(Page):
    title = "Ayuda"
    subtitle = "Primeros pasos, atajos y qué hacer si algo no va."

    def __init__(self, master, app) -> None:
        super().__init__(master, app)
        self.grid_rowconfigure(1, weight=1)
        actions = self.header()
        button(actions, "Novedades y descargas", lambda: webbrowser.open(f"{REPOSITORY}/releases"), kind="ghost", width=170, height=32).pack(side="right")
        button(actions, "Buscar actualizaciones", lambda: app.check_for_updates(manual=True), kind="ghost", width=180, height=32).pack(side="right", padx=(0, 8))
        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 14))
        body.grid_columnconfigure(0, weight=1)
        self._steps(body)
        self._keys(body)
        self._problems(body)
        self._support(body)

    def _box(self, body, title: str, row: int) -> ctk.CTkFrame:
        box = card(body)
        box.grid(row=row, column=0, sticky="ew", padx=12, pady=(4 if row == 0 else 8, 8))
        box.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(box, text=title, font=font(15, "bold"), text_color=TEXT).grid(row=0, column=0, columnspan=2, padx=20, pady=(14, 8), sticky="w")
        return box

    def _steps(self, body) -> None:
        box = self._box(body, "Primeros pasos", 0)
        for row, text in enumerate(FIRST_STEPS, start=1):
            ctk.CTkLabel(box, text=str(row), width=28, text_color="#b9a2ff", font=font(15, "bold")).grid(row=row, column=0, padx=(16, 0), pady=3, sticky="n")
            ctk.CTkLabel(box, text=text, text_color=MUTED, anchor="w", justify="left", wraplength=740).grid(row=row, column=1, padx=(4, 20), pady=3, sticky="w")
        ctk.CTkLabel(box, text="", height=6).grid(row=len(FIRST_STEPS) + 1, column=0)

    def _keys(self, body) -> None:
        box = self._box(body, "Atajos de teclado", 1)
        for row, (keys, what) in enumerate(KEYS, start=1):
            ctk.CTkLabel(box, text=keys, text_color=TEXT, font=font(13, "bold"), anchor="w", width=190).grid(row=row, column=0, padx=(20, 8), pady=3, sticky="w")
            ctk.CTkLabel(box, text=what, text_color=MUTED, anchor="w").grid(row=row, column=1, padx=(0, 20), pady=3, sticky="w")
        ctk.CTkLabel(box, text="Los atajos de F7 a F12 funcionan aunque la app esté en segundo plano (se pueden apagar en Configuración → Inicio e IA).",
                     text_color=FAINT, font=font(12), anchor="w", justify="left", wraplength=760).grid(row=len(KEYS) + 1, column=0, columnspan=2, padx=20, pady=(6, 14), sticky="w")

    def _problems(self, body) -> None:
        box = self._box(body, "Si algo no va", 2)
        for row, (title, text) in enumerate(PROBLEMS, start=1):
            ctk.CTkLabel(box, text=title, text_color=TEXT, font=font(13, "bold"), anchor="w").grid(row=row * 2 - 1, column=0, columnspan=2, padx=20, pady=(6, 0), sticky="w")
            ctk.CTkLabel(box, text=text, text_color=MUTED, anchor="w", justify="left", wraplength=760).grid(row=row * 2, column=0, columnspan=2, padx=20, pady=(0, 4), sticky="w")
        ctk.CTkLabel(box, text="", height=6).grid(row=len(PROBLEMS) * 2 + 1, column=0)

    def _support(self, body) -> None:
        box = self._box(body, "Pedir ayuda", 3)
        ctk.CTkLabel(box, text="Copia la información de esta app (versión, estado, ajustes sin secretos y las últimas líneas del registro) y pégala donde pidas ayuda. "
                               "El token y el Client Secret nunca van incluidos.", text_color=MUTED, anchor="w", justify="left", wraplength=760).grid(
            row=1, column=0, columnspan=2, padx=20, pady=(0, 8), sticky="w")
        row = ctk.CTkFrame(box, fg_color="transparent")
        row.grid(row=2, column=0, columnspan=2, padx=16, pady=(0, 16), sticky="w")
        button(row, "📋  Copiar información para soporte", self.copy_report, kind="primary", width=270, height=36).pack(side="left", padx=4)
        button(row, "Abrir la carpeta de logs", lambda: browser.open_folder(paths.logs_dir()), kind="neutral", width=190, height=36).pack(side="left", padx=4)

    def report(self) -> str:
        runner, app = self.app.runner, self.app
        return support.support_report(
            app.settings, state=runner.state.value, connection=runner.describe_connection(), error=runner.error, event=runner.event_line(),
            activity=runner.activity_info(), log_lines=[line.plain for line in list(app.hub.lines)[-40:]], frozen=paths.is_frozen())

    def copy_report(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self.report())
        self.app.toast("Información copiada: pégala donde pidas ayuda.", "ok")
