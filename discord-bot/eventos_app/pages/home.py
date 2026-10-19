"""«Inicio»: the bot's state with the start/stop button, what is still missing (the checklist), the live event, the quick actions and the
latest lines of the log."""

from __future__ import annotations

import time

import customtkinter as ctk

from .. import readiness
from ..logview import LogView
from ..runner import State
from ..theme import BUTTON_NEUTRAL, FAINT, INACTIVE, MUTED, OK_TEXT, TEXT, WARN_TEXT, button, card, font
from ..widgets import HpBar, Pill, StatTile
from . import Page

DIFFICULTIES = [
    ("easy", "Fácil", "#1f9d6c"),
    ("medium", "Media", "#b8901f"),
    ("hard", "Difícil", "#d6455d"),
    ("impossible", "Imposible", "#8f5bd6"),
]
DEFAULT_KEYS = {
    "single_easy": "F9", "single_medium": "F10", "single_hard": "F11", "single_impossible": "F12",
    "group_easy": "Shift+F9", "group_medium": "Shift+F10", "group_hard": "Shift+F11",
    "group_impossible": "Shift+F12", "checkpoint": "F8", "sync_commands": "F7", "batch_toggle": "Alt+F9",
}
STATUS = {                                    # state -> (pill tone, text)
    State.STOPPED: ("idle", "Detenido"), State.STARTING: ("warn", "Conectando…"), State.CONNECTED: ("ok", "Conectado"),
    State.STOPPING: ("warn", "Deteniendo…"), State.ERROR: ("bad", "Error"),
}
MARKS = {"done": ("✓", OK_TEXT), "todo": ("●", WARN_TEXT), "wait": ("○", FAINT), "off": ("–", FAINT)}
EVENT_REFRESH_SECONDS = 1.0


class HomePage(Page):
    title = "Inicio"
    subtitle = "El estado del evento y lo que puedes hacer ahora."

    def __init__(self, master, app) -> None:
        super().__init__(master, app)
        self.grid_rowconfigure(1, weight=1)
        self._steps_signature = None
        self._last_event_read = 0.0
        self._players: list[HpBar] = []
        self.action_buttons: dict[str, ctk.CTkButton] = {}

        actions = self.header()
        self.status_pill = Pill(actions, "Detenido", "idle")
        self.status_pill.pack(side="left", padx=(0, 14))
        self.toggle_btn = button(actions, "▶  Iniciar bot", app.toggle_bot, kind="good", width=170, height=42, font=font(14, "bold"))
        self.toggle_btn.pack(side="left")

        self.body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.body.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 10))
        self.body.grid_columnconfigure(0, weight=1)
        self._build_checklist()
        self._build_event()
        self._build_actions()
        self._build_log()

    # ---- construction ------------------------------------------------------------------------------------------------------
    def _build_checklist(self) -> None:
        self.check_card = card(self.body)
        self.check_card.grid(row=0, column=0, sticky="ew", padx=12, pady=(4, 8))
        self.check_card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self.check_card, text="Antes de empezar", font=font(15, "bold"), text_color=TEXT, anchor="w").grid(
            row=0, column=0, padx=20, pady=(14, 4), sticky="w")
        self.steps_frame = ctk.CTkFrame(self.check_card, fg_color="transparent")
        self.steps_frame.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 10))
        self.steps_frame.grid_columnconfigure(1, weight=1)
        self.ready_strip = card(self.body)
        ctk.CTkLabel(self.ready_strip, text="✓  Todo listo", font=font(14, "bold"), text_color=OK_TEXT).pack(side="left", padx=(20, 10), pady=12)
        ctk.CTkLabel(self.ready_strip, text="El bot está conectado, el evento elegido y la Actividad lista para tus jugadores.",
                     text_color=MUTED).pack(side="left", pady=12)

    def _build_event(self) -> None:
        self.event_card = card(self.body)
        self.event_card.grid_columnconfigure(0, weight=5, uniform="event")
        self.event_card.grid_columnconfigure(1, weight=6, uniform="event")
        head = ctk.CTkFrame(self.event_card, fg_color="transparent")
        head.grid(row=0, column=0, columnspan=2, sticky="ew", padx=20, pady=(14, 6))
        ctk.CTkLabel(head, text="Evento en vivo", font=font(15, "bold"), text_color=TEXT).pack(side="left")
        self.event_note = ctk.CTkLabel(head, text="", text_color=MUTED, font=font(12))
        self.event_note.pack(side="left", padx=14)
        left = ctk.CTkFrame(self.event_card, fg_color="transparent")
        left.grid(row=1, column=0, sticky="nsew", padx=(14, 6), pady=(0, 14))
        left.grid_columnconfigure((0, 1), weight=1, uniform="tile")
        self.tiles = {key: StatTile(left, caption) for key, caption in
                      (("fight", "Combate"), ("qtes", "QTE en curso"), ("online", "En la Actividad"), ("session", "Sesión"))}
        for index, tile in enumerate(self.tiles.values()):
            tile.grid(row=index // 2, column=index % 2, sticky="nsew", padx=3, pady=3)
        right = ctk.CTkFrame(self.event_card, fg_color="transparent")
        right.grid(row=1, column=1, sticky="nsew", padx=(6, 14), pady=(0, 14))
        right.grid_columnconfigure(0, weight=1)
        self.boss_bar = HpBar(right, name_width=150, color="#fb7185")
        self.boss_bar.grid(row=0, column=0, sticky="ew", padx=6, pady=(4, 6))
        self.boss_none = ctk.CTkLabel(right, text="No hay un jefe en combate.", text_color=FAINT, anchor="w")
        self.boss_none.grid(row=0, column=0, sticky="w", padx=6, pady=(4, 6))
        self.players_frame = ctk.CTkScrollableFrame(right, fg_color="#10101c", corner_radius=10, height=96)
        self.players_frame.grid(row=1, column=0, sticky="nsew", pady=(2, 0))
        self.players_frame.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)
        self.no_players = ctk.CTkLabel(right, text="", text_color=FAINT, wraplength=330, justify="left")

    def _build_actions(self) -> None:
        self.actions_card = card(self.body)
        self.actions_card.grid(row=2, column=0, sticky="ew", padx=12, pady=8)
        box = self.actions_card
        head = ctk.CTkFrame(box, fg_color="transparent")
        head.grid(row=0, column=0, columnspan=6, sticky="ew", padx=20, pady=(14, 4))
        ctk.CTkLabel(head, text="Acciones rápidas", font=font(15, "bold"), text_color=TEXT).pack(side="left")
        self.keys_note = ctk.CTkLabel(head, text="", text_color=FAINT, font=font(12))
        self.keys_note.pack(side="left", padx=12)
        for row, (prefix, title) in enumerate((("single", "Individual"), ("group", "Grupal")), start=1):
            ctk.CTkLabel(box, text=title, text_color=MUTED, width=82, anchor="w").grid(row=row, column=0, padx=(20, 4), pady=4, sticky="w")
            for column, (diff, label, color) in enumerate(DIFFICULTIES, start=1):
                self._action_button(box, f"{prefix}_{diff}", label, color).grid(
                    row=row, column=column, padx=(4, 20 if column == len(DIFFICULTIES) else 4), pady=4, sticky="ew")
        extras = ctk.CTkFrame(box, fg_color="transparent")
        extras.grid(row=3, column=0, columnspan=6, padx=16, pady=(2, 14), sticky="ew")
        for name, label, width in (("checkpoint", "💚 Checkpoint", 150), ("batch_toggle", "📦 Modo lote", 150), ("sync_commands", "🔄 Sincronizar", 150)):
            self._action_button(extras, name, label, BUTTON_NEUTRAL, width=width).pack(side="left", padx=4)
        button(extras, "🧭  Abrir el panel del GM", self.app.open_gm_panel, kind="primary", width=210, height=44).pack(side="right", padx=4)
        for column in range(1, 5):
            box.grid_columnconfigure(column, weight=1)

    def _action_button(self, parent, name: str, label: str, color: str, width: int | None = None) -> ctk.CTkButton:
        kwargs = {"width": width} if width else {}
        btn = ctk.CTkButton(parent, text=self.caption(name, label), height=42, corner_radius=8, fg_color=INACTIVE, hover_color=color,
                            text_color_disabled="#5f5e80", state="disabled", command=lambda n=name: self.app.run_action(n), **kwargs)
        btn._base_label = label  # type: ignore[attr-defined]
        btn._color = color  # type: ignore[attr-defined]
        self.action_buttons[name] = btn
        return btn

    def _build_log(self) -> None:
        box = card(self.body)
        box.grid(row=3, column=0, sticky="ew", padx=12, pady=(8, 14))
        box.grid_columnconfigure(0, weight=1)
        head = ctk.CTkFrame(box, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=20, pady=(12, 0))
        ctk.CTkLabel(head, text="Registro reciente", font=font(15, "bold"), text_color=TEXT).pack(side="left")
        button(head, "Ver todo →", lambda: self.app.show_page("log"), kind="ghost", width=90, height=26).pack(side="right")
        self.log = LogView(box, self.app.hub, max_lines=250, height=190)
        self.log.grid(row=1, column=0, sticky="ew", padx=10, pady=10)

    # ---- the quick actions ------------------------------------------------------------------------------------------------------
    def caption(self, name: str, label: str) -> str:
        key = self.app.runner.action_label(name).upper() or DEFAULT_KEYS.get(name, "")
        if not (self.app.settings.hotkeys_enabled and key):
            return label
        return f"{label}\n{key}" if name.startswith(("single_", "group_")) else f"{label}  ({key})"

    def refresh_captions(self) -> None:
        for name, btn in self.action_buttons.items():
            btn.configure(text=self.caption(name, btn._base_label))  # type: ignore[attr-defined]
        self.keys_note.configure(text="Con los atajos de teclado, también desde cualquier ventana." if self.app.settings.hotkeys_enabled else "")

    # ---- every ~400 ms -----------------------------------------------------------------------------------------------------------------
    def tick(self, state: State) -> None:
        runner = self.app.runner
        tone, text = STATUS[state]
        self.status_pill.set(text, tone)
        active = runner.is_active()
        if state is State.STOPPING:
            self.toggle_btn.configure(text="Deteniendo…", state="disabled")
        elif active:
            self.toggle_btn.configure(text="■  Detener bot", state="normal", fg_color="#d6455d", hover_color="#b8374d")
        else:
            self.toggle_btn.configure(text="▶  Iniciar bot", state="normal", fg_color="#1f9d6c", hover_color="#188358")

        connected = state is State.CONNECTED
        for btn in self.action_buttons.values():
            btn.configure(state="normal" if connected else "disabled", fg_color=btn._color if connected else INACTIVE)  # type: ignore[attr-defined]
        if connected:
            self.set_subtitle(runner.event_line() or self.subtitle)
        elif state is State.ERROR:
            self.set_subtitle(runner.error or self.subtitle)
        else:
            self.set_subtitle(self.subtitle)

        info = runner.activity_info()
        self._render_checklist(readiness.checklist(
            token_set=bool(self.app.settings.discord_token.strip()), connected=connected, starting=state is State.STARTING,
            event_ready=runner.event_ready(), activity_enabled=bool(self.app.settings.activity_enabled),
            secret_set=bool(info.get("secret_set")), tunnel=info.get("tunnel", ""), tunnel_detail=info.get("detail", ""),
            activity_running=bool(info.get("running"))))
        self._render_event(connected, info)

    # ---- the checklist --------------------------------------------------------------------------------------------------------------------
    def _render_checklist(self, steps: list[readiness.Step]) -> None:
        if readiness.all_done(steps):
            self.check_card.grid_remove()
            self.ready_strip.grid(row=0, column=0, sticky="ew", padx=12, pady=(4, 8))
            self._steps_signature = None
            return
        self.ready_strip.grid_remove()
        self.check_card.grid(row=0, column=0, sticky="ew", padx=12, pady=(4, 8))
        signature = tuple((s.key, s.detail, s.state, s.action) for s in steps)
        if signature == self._steps_signature:
            return
        self._steps_signature = signature
        for child in self.steps_frame.winfo_children():
            child.destroy()
        where = {"config": ("Ir a Configuración", lambda: self.app.show_page("config", tab="bot")),
                 "event": ("Elegir el evento", lambda: self.app.show_page("config", tab="bot")),
                 "activity": ("Ver la Actividad", lambda: self.app.show_page("activity")), "start": ("Iniciar el bot", self.app.toggle_bot)}
        for row, step in enumerate(steps):
            mark, color = MARKS[step.state]
            ctk.CTkLabel(self.steps_frame, text=mark, width=30, text_color=color, font=font(16, "bold")).grid(row=row, column=0, pady=3)
            text = ctk.CTkFrame(self.steps_frame, fg_color="transparent")
            text.grid(row=row, column=1, sticky="ew", pady=3)
            ctk.CTkLabel(text, text=step.title, font=font(13, "bold"), text_color=TEXT if step.state != "wait" else MUTED, anchor="w").pack(anchor="w")
            ctk.CTkLabel(text, text=step.detail, text_color=MUTED, font=font(12), anchor="w", justify="left", wraplength=520).pack(anchor="w")
            if step.action in where and step.state in ("todo", "off"):
                label, command = where[step.action]
                button(self.steps_frame, label, command, kind="primary" if step.state == "todo" else "ghost", width=150, height=28).grid(
                    row=row, column=2, padx=(10, 6), pady=3)

    # ---- the live event -------------------------------------------------------------------------------------------------------------------
    def _render_event(self, connected: bool, info: dict) -> None:
        if not connected:
            self.event_card.grid_remove()
            return
        self.event_card.grid(row=1, column=0, sticky="ew", padx=12, pady=8)
        now = time.monotonic()
        if now - self._last_event_read < EVENT_REFRESH_SECONDS:
            return
        self._last_event_read = now
        snap = self.app.runner.event_snapshot()
        if not snap:
            return
        stun = snap.get("stunLeft", 0)
        self.tiles["fight"].set("En curso" if snap["fight"] else "En pausa", f"Jefe aturdido {int(stun) + 1} s" if stun else
                                ("Los poderes se recargan." if snap["fight"] else "Recargas pausadas."), "ok" if snap["fight"] else None)
        self.tiles["qtes"].set(str(len(snap["qtes"])), "esperando respuesta" if snap["qtes"] else "ninguno ahora")
        users = [u for u in info.get("users", []) if not u.get("hidden")]
        self.tiles["online"].set(str(len(users)), f"puerto {info['port']}" if info.get("running") else "Actividad apagada")
        self.tiles["session"].set(str(snap["session"]["qtes"]), f"{snap['session']['blackFlashes']} Black Flash hoy")
        boss = snap.get("boss")
        if boss:
            self.boss_none.grid_remove()
            self.boss_bar.grid()
            self.boss_bar.set(boss["name"], boss["hp"], boss["max"], tone="bad")
        else:
            self.boss_bar.grid_remove()
            self.boss_none.grid()
        self.event_note.configure(text=f"{snap['playerCount']} jugadores con vida registrada" if snap["playerCount"] else "")
        self._render_players(snap["players"])

    def _render_players(self, players: list[dict]) -> None:
        while len(self._players) < len(players):
            bar = HpBar(self.players_frame, name_width=150)
            bar.pack(fill="x", pady=3, padx=6)
            self._players.append(bar)
        for index, bar in enumerate(self._players):
            if index >= len(players):
                bar.pack_forget()
                continue
            p = players[index]
            if not bar.winfo_ismapped():
                bar.pack(fill="x", pady=3, padx=6)
            note = "caído" if not p["alive"] else ""
            label = p["name"] + ("  ·  modo venganza" if p["revenge"] and p["alive"] else "") + ("  ·  fuera de los QTE" if p["afk"] else "")
            bar.set(label[:34], p["hp"], p["max"], tone="bad" if not p["alive"] else None, note=note)
        if not players:
            self.no_players.configure(text="Todavía nadie tiene vida registrada: aparece cuando lanzas el primer QTE.")
            self.no_players.grid(row=1, column=0, sticky="nw", padx=6, pady=(8, 0))
            self.players_frame.grid_remove()
        else:
            self.no_players.grid_remove()
            self.players_frame.grid()
