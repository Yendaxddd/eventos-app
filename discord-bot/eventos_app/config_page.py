"""The "Configuración" page: token, event (server / channel / roles), helper bots, startup, AI."""

from __future__ import annotations

import asyncio
import logging
import tkinter as tk
import webbrowser
from tkinter import messagebox

import aiohttp
import customtkinter as ctk
import discord

from . import multibot, ollama
from .runner import State
from .settings import Settings
from .theme import (ACCENT, AMBER, BUTTON_NEUTRAL, CARD_BORDER, GREEN, MUTED, RED, TEXT, card)
from .widgets import PickerField

log = logging.getLogger("eventos_app")

DEVELOPER_PORTAL = "https://discord.com/developers/applications"
NO_ADMIN = "— Ninguno —"


def _short(token: str) -> str:
    return f"…{token[-6:]}" if len(token) > 6 else token


class ConfigPage(ctk.CTkFrame):
    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._snapshot: dict | None = None
        self._loaded_session = False
        self._helper_rows: list[dict] = []
        self._helper_notes: dict[str, str] = {}  # token -> last message from "Probar"
        self._busy_event = False

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 0))
        self.scroll.grid_columnconfigure(0, weight=1)

        s = app.settings
        self.vars: dict[str, tk.Variable] = {
            "discord_token": tk.StringVar(value=s.discord_token),
            "ai_enabled": tk.BooleanVar(value=s.ai_enabled),
            "ollama_endpoint": tk.StringVar(value=s.ollama_endpoint),
            "ollama_model": tk.StringVar(value=s.ollama_model),
            "reset_on_start": tk.BooleanVar(value=s.reset_on_start),
            "hotkeys_enabled": tk.BooleanVar(value=s.hotkeys_enabled),
            "use_webhooks": tk.BooleanVar(value=s.use_webhooks),
            "activity_enabled": tk.BooleanVar(value=s.activity_enabled),
            "activity_client_secret": tk.StringVar(value=s.activity_client_secret),
            "auto_start": tk.BooleanVar(value=s.auto_start),
        }
        self._build_token(0)
        self._build_event(1)
        self._build_helpers(2)
        self._build_webhooks(3)
        self._build_activity(4)
        self._build_performance(5)
        self._build_startup(6)
        self._build_ai(7)

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=1, column=0, sticky="ew", padx=20, pady=14)
        ctk.CTkButton(bar, text="Guardar cambios", width=160, height=38, fg_color=ACCENT,
                      command=app.save_from_page).pack(side="left")
        self.save_msg = ctk.CTkLabel(bar, text="", text_color=MUTED)
        self.save_msg.pack(side="left", padx=14)
        self._show_offline_event()

    # ---- small helpers ----------------------------------------------------------
    def _section(self, title: str, row: int) -> ctk.CTkFrame:
        box = card(self.scroll)
        box.grid(row=row, column=0, sticky="ew", padx=10, pady=8)
        box.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(box, text=title, font=ctk.CTkFont(size=15, weight="bold"), text_color=TEXT).grid(
            row=0, column=0, columnspan=4, padx=18, pady=(14, 6), sticky="w")
        return box

    @staticmethod
    def _note(box, row: int, text: str, columnspan: int = 4, pady=(0, 10)) -> ctk.CTkLabel:
        label = ctk.CTkLabel(box, text=text, text_color=MUTED, anchor="w", justify="left", wraplength=640)
        label.grid(row=row, column=0, columnspan=columnspan, padx=18, pady=pady, sticky="w")
        return label

    def _field(self, box, row: int, label: str, key: str, show: str | None = None) -> ctk.CTkEntry:
        ctk.CTkLabel(box, text=label, text_color=MUTED, anchor="w").grid(row=row, column=0, padx=(18, 12), pady=6, sticky="w")
        entry = ctk.CTkEntry(box, textvariable=self.vars[key], show=show, height=34)
        entry.grid(row=row, column=1, columnspan=3, padx=(0, 18), pady=6, sticky="ew")
        return entry

    # ---- token ----------------------------------------------------------------------
    def _build_token(self, row: int) -> None:
        box = self._section("Bot de Discord", row)
        self.token_entry = self._field(box, 1, "Token del bot", "discord_token", show="•")
        actions = ctk.CTkFrame(box, fg_color="transparent")
        actions.grid(row=2, column=1, columnspan=3, padx=(0, 18), pady=(0, 6), sticky="w")
        self.show_token = ctk.CTkSwitch(actions, text="Mostrar token", progress_color=ACCENT, command=self._toggle_token)
        self.show_token.pack(side="left")
        ctk.CTkButton(actions, text="¿Dónde lo consigo?", width=150, height=26, fg_color="transparent", border_width=1,
                      border_color=CARD_BORDER, text_color=MUTED, hover_color=CARD_BORDER,
                      command=lambda: webbrowser.open(DEVELOPER_PORTAL)).pack(side="left", padx=14)
        self._note(box, 3, "Developer Portal → tu aplicación → Bot → «Reset Token». Se guarda solo en este equipo.")

    def _toggle_token(self) -> None:
        self.token_entry.configure(show="" if self.show_token.get() else "•")

    def focus_token(self) -> None:
        self.token_entry.focus_set()

    # ---- event: server / channel / roles ------------------------------------------------
    def _build_event(self, row: int) -> None:
        box = self._section("Evento: servidor, canal y roles", row)
        self.guild_picker = PickerField(box, placeholder="Servidor", on_change=self._guild_changed)
        self.channel_picker = PickerField(box, placeholder="Canal donde ocurren los QTE")
        self.player_picker = PickerField(box, placeholder="Rol de los jugadores")
        self.admin_picker = PickerField(box, placeholder="Rol de administrador (opcional)", none_label=NO_ADMIN)
        labels = ("Servidor", "Canal de QTE", "Rol de jugadores", "Rol de admin")
        for i, (text, picker) in enumerate(zip(labels, (self.guild_picker, self.channel_picker, self.player_picker,
                                                        self.admin_picker)), start=1):
            ctk.CTkLabel(box, text=text, text_color=MUTED, anchor="w").grid(row=i, column=0, padx=(18, 12), pady=6, sticky="w")
            picker.grid(row=i, column=1, columnspan=3, padx=(0, 18), pady=6, sticky="ew")
        actions = ctk.CTkFrame(box, fg_color="transparent")
        actions.grid(row=5, column=0, columnspan=4, padx=18, pady=(4, 4), sticky="w")
        self.apply_btn = ctk.CTkButton(actions, text="Aplicar al evento", width=150, height=34, fg_color=ACCENT,
                                       command=self._apply_event)
        self.apply_btn.pack(side="left")
        self.reload_btn = ctk.CTkButton(actions, text="Actualizar listas", width=130, height=34, fg_color=BUTTON_NEUTRAL,
                                        command=self.reload_servers)
        self.reload_btn.pack(side="left", padx=10)
        self.event_msg = ctk.CTkLabel(box, text="", text_color=MUTED, anchor="w", justify="left", wraplength=640)
        self.event_msg.grid(row=6, column=0, columnspan=4, padx=18, pady=(2, 4), sticky="w")
        self._note(box, 7, "Se aplica al instante, sin reiniciar. El bot crea (o reutiliza) el hilo «📊 HP Bars» en el canal. "
                           "Es lo mismo que el comando /setchannel de Discord.")

    def _set_event_message(self, text: str, color: str = MUTED) -> None:
        self.event_msg.configure(text=text, text_color=color)

    def _show_offline_event(self) -> None:
        """While the bot is off the pickers are locked and show the last known event."""
        summary = self.app.settings.event_summary or {}
        for picker in (self.guild_picker, self.channel_picker, self.player_picker, self.admin_picker):
            picker.set_enabled(False)
            picker.set_items([])
        self.guild_picker.set_value(summary.get("guild_id"), summary.get("guild_name", ""))
        self.channel_picker.set_value(summary.get("channel_id"), f"#{summary['channel_name']}" if summary.get("channel_name") else "")
        self.player_picker.set_value(summary.get("player_role_id"), f"@{summary['player_role_name']}" if summary.get("player_role_name") else "")
        self.admin_picker.set_value(summary.get("admin_role_id") or 0, f"@{summary['admin_role_name']}" if summary.get("admin_role_name") else "")
        self.apply_btn.configure(state="disabled")
        self.reload_btn.configure(state="disabled")
        self._set_event_message("Inicia el bot para elegir el servidor, el canal y los roles." if not summary else
                                "Inicia el bot para cambiar el evento. Esto es lo último que se usó.")

    def reload_servers(self) -> None:
        try:
            future = self.app.runner.load_servers()
        except RuntimeError as exc:
            self._set_event_message(str(exc), AMBER)
            return
        self._set_event_message("Cargando servidores…")
        self.app.watch(future, self._apply_snapshot, lambda exc: self._set_event_message(f"No se pudo leer: {exc}", RED))

    def _apply_snapshot(self, snapshot: dict) -> None:
        self._snapshot = snapshot
        guilds = snapshot["guilds"]
        current = snapshot["current"]
        for picker in (self.guild_picker, self.channel_picker, self.player_picker, self.admin_picker):
            picker.set_enabled(True)
        self.apply_btn.configure(state="normal")
        self.reload_btn.configure(state="normal")
        self.guild_picker.set_items([(g["id"], g["name"], "") for g in guilds])
        guild_id = current["guild_id"] or (guilds[0]["id"] if len(guilds) == 1 else None)
        self.guild_picker.set_value(guild_id)
        self._fill_for_guild(guild_id, current)
        self._remember_event(snapshot)
        if not guilds:
            self._set_event_message("El bot no está en ningún servidor todavía. Invítalo desde el Developer Portal.", AMBER)
        elif not current["channel_id"]:
            self._set_event_message("Elige el canal de los QTE y pulsa «Aplicar al evento».", AMBER)
        else:
            self._set_event_message("")

    def _guild(self, guild_id: int | None) -> dict | None:
        for g in (self._snapshot or {}).get("guilds", []):
            if g["id"] == guild_id:
                return g
        return None

    def _fill_for_guild(self, guild_id: int | None, current: dict | None) -> None:
        guild = self._guild(guild_id)
        channels = [(c["id"], f"#{c['name']}", c["group"]) for c in (guild["channels"] if guild else [])]
        roles = [(r["id"], f"@{r['name']}", "") for r in (guild["roles"] if guild else [])]
        self.channel_picker.set_items(channels)
        self.player_picker.set_items(roles)
        self.admin_picker.set_items(roles)
        cur = current or {}
        in_guild = {c[0] for c in channels}, {r[0] for r in roles}
        channel = cur.get("channel_id")
        self.channel_picker.set_value(channel if channel in in_guild[0] else None)
        player, admin = cur.get("player_role_id"), cur.get("admin_role_id")
        self.player_picker.set_value(player if player in in_guild[1] else (player or None),
                                     "" if player in in_guild[1] or not player else "(rol de otro servidor)")
        self.admin_picker.set_value(admin if admin in in_guild[1] else (admin or 0),
                                    "" if admin in in_guild[1] or not admin else "(rol de otro servidor)")

    def _guild_changed(self, guild_id: int | None) -> None:
        self._fill_for_guild(guild_id, None)
        self._set_event_message("Servidor cambiado: elige el canal y el rol de jugadores de ese servidor.", AMBER)

    def _apply_event(self) -> None:
        channel, player = self.channel_picker.get(), self.player_picker.get()
        if not channel:
            self._set_event_message("Elige el canal de los QTE.", AMBER)
            return
        if not player:
            self._set_event_message("Elige el rol de los jugadores (los QTE se reparten entre quienes lo tienen).", AMBER)
            return
        admin = self.admin_picker.get() or 0
        try:
            future = self.app.runner.apply_event(channel, player, admin)
        except RuntimeError as exc:
            self._set_event_message(str(exc), RED)
            return
        self.apply_btn.configure(state="disabled")
        self._set_event_message("Aplicando…")

        def done(result: dict) -> None:
            self.apply_btn.configure(state="normal")
            if result["ok"]:
                kind = "creado" if result["created"] else "ya existía"
                self._set_event_message(f"✓ Evento configurado. Hilo de barras de HP: «{result['thread']}» ({kind}).", GREEN)
                self.reload_servers()
            else:
                self._set_event_message(f"✗ {result['error']}", RED)

        def failed(exc: BaseException) -> None:
            self.apply_btn.configure(state="normal")
            self._set_event_message(f"✗ {exc}", RED)

        self.app.watch(future, done, failed)

    def _remember_event(self, snapshot: dict) -> None:
        """Keep the names of the current event so they can be shown while the bot is off."""
        cur = snapshot["current"]
        guild = next((g for g in snapshot["guilds"] if g["id"] == cur["guild_id"]), None)
        if guild is None:
            return
        name = lambda items, ident: next((i["name"] for i in items if i["id"] == ident), "")  # noqa: E731
        summary = {
            "guild_id": guild["id"], "guild_name": guild["name"],
            "channel_id": cur["channel_id"], "channel_name": name(guild["channels"], cur["channel_id"]),
            "player_role_id": cur["player_role_id"], "player_role_name": name(guild["roles"], cur["player_role_id"]),
            "admin_role_id": cur["admin_role_id"], "admin_role_name": name(guild["roles"], cur["admin_role_id"]),
        }
        if summary != self.app.settings.event_summary:
            self.app.settings.event_summary = summary
            self.app.persist_quietly()

    # ---- helper bots ------------------------------------------------------------------
    def _build_helpers(self, row: int) -> None:
        box = self._section("Bots auxiliares (evitan el rate limit)", row)
        self._note(box, 1, "Discord limita cuántos mensajes puede mandar cada bot por canal. Con bots auxiliares, el bot "
                           "reparte los mensajes (QTE, respuestas, imágenes) entre todos y una ráfaga sale sin esperas. "
                           "Cada auxiliar es otra aplicación de Discord (créala en el Developer Portal) que debe estar "
                           "invitada a tu servidor con permiso para escribir en el canal. No necesitan estar «en línea».")
        self.helper_list = ctk.CTkFrame(box, fg_color="transparent")
        self.helper_list.grid(row=2, column=0, columnspan=4, padx=14, sticky="ew")
        self.helper_list.grid_columnconfigure(0, weight=1)
        add = ctk.CTkFrame(box, fg_color="transparent")
        add.grid(row=3, column=0, columnspan=4, padx=18, pady=(8, 4), sticky="ew")
        add.grid_columnconfigure(0, weight=1)
        self.helper_token_var = tk.StringVar()
        self.helper_entry = ctk.CTkEntry(add, textvariable=self.helper_token_var, show="•", height=34)
        self.helper_entry.grid(row=0, column=0, sticky="ew")
        self.helper_add_btn = ctk.CTkButton(add, text="Agregar bot auxiliar", width=170, height=34, fg_color=ACCENT,
                                            command=self._add_helper)
        self.helper_add_btn.grid(row=0, column=1, padx=(10, 0))
        self.helper_msg = ctk.CTkLabel(box, text="Pega el token del bot auxiliar y pulsa «Agregar».", text_color=MUTED,
                                       anchor="w", justify="left", wraplength=640)
        self.helper_msg.grid(row=4, column=0, columnspan=4, padx=18, pady=(2, 12), sticky="w")
        self._render_helpers()

    def _set_helper_message(self, text: str, color: str = MUTED) -> None:
        self.helper_msg.configure(text=text, text_color=color)

    def _render_helpers(self) -> None:
        for child in self.helper_list.winfo_children():
            child.destroy()
        self._helper_rows = []
        for i, helper in enumerate(self.app.settings.helper_bots):
            token = helper.get("token", "")
            row = ctk.CTkFrame(self.helper_list, fg_color=CARD_BORDER, corner_radius=8)
            row.grid(row=i, column=0, sticky="ew", padx=4, pady=3)
            row.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(row, text=helper.get("name") or f"Bot {_short(token)}", text_color=TEXT, anchor="w",
                         font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, columnspan=2, padx=(12, 8), pady=(8, 0), sticky="w")
            status = ctk.CTkLabel(row, text="", text_color=MUTED, anchor="w", justify="left", wraplength=430)
            status.grid(row=1, column=0, columnspan=2, padx=(12, 8), pady=(0, 8), sticky="w")
            for col, (text, command) in enumerate((("Probar", lambda t=token: self._test_helper(t)),
                                                   ("Invitar", lambda h=helper: self._copy_invite(h)),
                                                   ("Quitar", lambda t=token: self._remove_helper(t))), start=2):
                ctk.CTkButton(row, text=text, width=70, height=28, fg_color=BUTTON_NEUTRAL if text != "Quitar" else "#5a2f37",
                              hover_color=CARD_BORDER, command=command).grid(row=0, column=col, rowspan=2, padx=(0, 6 if col < 4 else 10), pady=6)
            self._helper_rows.append({"token": token, "status": status})
        if not self.app.settings.helper_bots:
            ctk.CTkLabel(self.helper_list, text="Todavía no hay bots auxiliares. Funciona igual solo con el principal.",
                         text_color=MUTED).grid(row=0, column=0, padx=8, pady=6, sticky="w")

    def _refresh_helper_status(self) -> None:
        runner = self.app.runner
        for row in self._helper_rows:
            token = row["token"]
            note = self._helper_notes.get(token)
            if note:
                row["status"].configure(text=note, text_color=TEXT)
                continue
            info = runner.helper_info(token)
            if info["state"] == "ok":
                sender = info["sender"]
                access = {"ok": "ve el canal", "no": "NO ve el canal del evento", "?": ""}.get(sender["access"], "")
                speed = f" · {sender['p50_ms']} ms" if sender["p50_ms"] else ""
                text = f"● Conectado · {sender['sent']} mensajes{speed}" + (f" · {access}" if access else "")
                row["status"].configure(text=text, text_color=RED if sender["access"] == "no" else GREEN)
            elif info["state"] == "error":
                row["status"].configure(text=f"✗ {info['error']}", text_color=RED)
            else:
                waiting = "Se conectará al iniciar el bot" if not runner.is_active() else "Conectando…"
                row["status"].configure(text=waiting, text_color=MUTED)

    def _add_helper(self) -> None:
        token = self.helper_token_var.get().strip()
        if not token:
            return
        taken = [h.get("token") for h in self.app.settings.helper_bots] + [self.vars["discord_token"].get().strip()]
        if token in taken:
            self._set_helper_message("Ese token ya está en uso (es el bot principal o ya lo agregaste).", AMBER)
            return
        self.helper_add_btn.configure(state="disabled")
        self._set_helper_message("Comprobando el token con Discord…")

        def done(info: multibot.TokenInfo) -> None:
            self.helper_add_btn.configure(state="normal")
            main_id = self.app.runner.main_bot_id()
            known = {h.get("user_id") for h in self.app.settings.helper_bots} | {main_id}
            if info.user_id in known:
                self._set_helper_message(f"{info.name} ya está en uso: el principal y los auxiliares deben ser bots distintos.", AMBER)
                return
            self.app.settings.helper_bots.append({"token": token, "name": info.name, "user_id": info.user_id})
            self.app.persist_quietly()
            self.helper_token_var.set("")
            self._render_helpers()
            if self.app.runner.state is State.CONNECTED:
                self.app.runner.add_helper(token)
                tail = "Se está conectando."
            else:
                tail = "Se conectará al iniciar el bot."
            self._set_helper_message(f"✓ «{info.name}» agregado. {tail} Pulsa «Invitar» para copiar el enlace y "
                                     f"añadirlo a tu servidor.", GREEN)

        def failed(exc: BaseException) -> None:
            self.helper_add_btn.configure(state="normal")
            if isinstance(exc, discord.LoginFailure):
                text = "Discord rechazó ese token. Revisa que lo copiaste completo."
            elif isinstance(exc, (aiohttp.ClientError, OSError, asyncio.TimeoutError)):
                text = "No se pudo conectar con Discord. ¿Hay internet?"
            else:
                text = f"{type(exc).__name__}: {exc}"
            self._set_helper_message(f"✗ {text}", RED)

        self.app.bg(lambda: asyncio.run(multibot.inspect_token(token)), done, failed)

    def _remove_helper(self, token: str) -> None:
        self.app.settings.helper_bots = [h for h in self.app.settings.helper_bots if h.get("token") != token]
        self.app.persist_quietly()
        self._helper_notes.pop(token, None)
        if self.app.runner.state is State.CONNECTED:
            self.app.runner.remove_helper(token)
        self._render_helpers()
        self._set_helper_message("Bot auxiliar quitado.")

    def _copy_invite(self, helper: dict) -> None:
        user_id = helper.get("user_id")
        if not user_id:
            self._set_helper_message("No conozco el ID de ese bot; quítalo y agrégalo de nuevo.", AMBER)
            return
        self.clipboard_clear()
        self.clipboard_append(multibot.invite_url(user_id))
        self._set_helper_message(f"Enlace de invitación de «{helper.get('name')}» copiado. Ábrelo en el navegador y elige "
                                 f"tu servidor.", GREEN)

    def _test_helper(self, token: str) -> None:
        try:
            future = self.app.runner.test_helper(token)
        except RuntimeError as exc:
            self._set_helper_message(str(exc), AMBER)
            return
        self._helper_notes[token] = "Enviando mensaje de prueba…"

        def finish(text: str, ok: bool) -> None:
            self._helper_notes[token] = text
            self.after(6000, lambda: self._helper_notes.pop(token, None))
            self._set_helper_message(text, GREEN if ok else RED)

        self.app.watch(future, lambda result: finish("✓ Escribió y borró un mensaje de prueba en el canal." if not result
                                                     else f"✗ {result}", not result),
                       lambda exc: finish(f"✗ {exc}", False))

    # ---- performance test ------------------------------------------------------------------
    def _build_performance(self, row: int) -> None:
        box = self._section("Rendimiento (límites de Discord)", row)
        self._note(box, 1, "Mide con tus bots reales cuánto tarda cada mensaje y reacción, cuántos mensajes por minuto aguanta el "
                           "canal del evento y cuántos jugadores pueden responder a la vez sin esperas. Manda mensajes de prueba al "
                           "canal del evento (se borran solos). Hazla con el evento parado.")
        actions = ctk.CTkFrame(box, fg_color="transparent")
        actions.grid(row=2, column=0, columnspan=4, padx=18, pady=(0, 4), sticky="w")
        self.bench_quick = ctk.CTkButton(actions, text="Prueba rápida (~30 s)", width=170, height=34, fg_color=ACCENT,
                                         command=lambda: self._run_benchmark("rapida"))
        self.bench_quick.pack(side="left")
        self.bench_full = ctk.CTkButton(actions, text="Prueba completa (~1 min)", width=180, height=34, fg_color=BUTTON_NEUTRAL,
                                        command=lambda: self._run_benchmark("completa"))
        self.bench_full.pack(side="left", padx=10)
        self.bench_stop = ctk.CTkButton(actions, text="Cancelar", width=90, height=34, fg_color="#5a2f37", state="disabled",
                                        command=self.app.runner.cancel_benchmark)
        self.bench_stop.pack(side="left")
        self.bench_msg = ctk.CTkLabel(box, text="", text_color=MUTED, anchor="w", justify="left", wraplength=640)
        self.bench_msg.grid(row=3, column=0, columnspan=4, padx=18, pady=(2, 12), sticky="w")

    def _run_benchmark(self, profile: str) -> None:
        if self.app.runner.state is not State.CONNECTED:
            self.bench_msg.configure(text="Inicia el bot primero.", text_color=AMBER)
            return
        if not messagebox.askyesno(
                "Prueba de rendimiento",
                "Se enviarán decenas de mensajes de prueba (y reacciones) al canal del evento y se borrarán al terminar.\n\n"
                "Hazla cuando no haya un evento en marcha.\n\n¿Empezar?"):
            return
        try:
            future = self.app.runner.run_benchmark(profile)
        except RuntimeError as exc:
            self.bench_msg.configure(text=str(exc), text_color=RED)
            return
        for button in (self.bench_quick, self.bench_full):
            button.configure(state="disabled")
        self.bench_stop.configure(state="normal")
        self.bench_msg.configure(text="Midiendo… el avance sale en el registro del Panel.", text_color=MUTED)

        def finish() -> None:
            for button in (self.bench_quick, self.bench_full):
                button.configure(state="normal")
            self.bench_stop.configure(state="disabled")

        def done(result: dict) -> None:
            finish()
            if not result["ok"]:
                self.bench_msg.configure(text=f"⚠ {result['error']}", text_color=AMBER)
                return
            c = result["report"]["capacity"]["3"]
            self.bench_msg.configure(
                text=f"✓ Listo. ≈ {c['players']} jugadores a la vez (límite: {c['limiting']}) · ≈ {round(c['messages_per_minute'])} "
                     f"mensajes/min. Informe completo en el registro y en {result['path']}", text_color=GREEN)

        def failed(exc: BaseException) -> None:
            finish()
            self.bench_msg.configure(text=f"✗ {exc}", text_color=RED)

        self.app.watch(future, done, failed)

    # ---- webhooks -----------------------------------------------------------------------
    def _build_webhooks(self, row: int) -> None:
        box = self._section("Webhooks de envío (más mensajes sin más bots)", row)
        self._note(box, 1, "Cada bot registra UN webhook en el canal del evento (se hace solo, y de nuevo al cambiar de "
                           "canal). Los webhooks tienen su propio límite de Discord, así que sacan mensajes extra cuando los "
                           "bots ya no tienen cupo. No mandan reacciones, respuestas ni botones: eso sigue siendo de los bots. "
                           "Necesitan el permiso «Gestionar webhooks» del bot en ese canal (un canal admite 15 webhooks).")
        ctk.CTkCheckBox(box, text="Usar un webhook por bot como carril de envío extra", variable=self.vars["use_webhooks"],
                        fg_color=ACCENT, hover_color=ACCENT).grid(row=2, column=0, columnspan=3, padx=18, pady=(2, 6), sticky="w")
        self.lanes_btn = ctk.CTkButton(box, text="Aplicar ahora", width=130, height=32, fg_color=ACCENT,
                                       command=self._apply_lanes)
        self.lanes_btn.grid(row=2, column=3, padx=(0, 18), pady=(2, 6), sticky="e")
        self.lanes_status = ctk.CTkLabel(box, text="", text_color=MUTED, anchor="w", justify="left", wraplength=640)
        self.lanes_status.grid(row=3, column=0, columnspan=4, padx=18, pady=(0, 12), sticky="w")

    def _apply_lanes(self) -> None:
        try:
            future = self.app.runner.refresh_lanes(bool(self.vars["use_webhooks"].get()))
        except RuntimeError as exc:
            self.lanes_status.configure(text=str(exc), text_color=AMBER)
            return
        self.lanes_btn.configure(state="disabled")
        self.lanes_status.configure(text="Registrando webhooks…", text_color=MUTED)

        def done(result: dict) -> None:
            self.lanes_btn.configure(state="normal")
            if not result.get("ok"):
                self.lanes_status.configure(text=result.get("error", ""), text_color=AMBER)

        def failed(exc: BaseException) -> None:
            self.lanes_btn.configure(state="normal")
            self.lanes_status.configure(text=f"✗ {exc}", text_color=RED)

        self.app.watch(future, done, failed)

    def _refresh_webhooks(self) -> None:
        """Which bots have their webhook (from the pool), updated while the bot runs."""
        runner = self.app.runner
        if not runner.is_active():
            self.lanes_status.configure(text="Se registrarán al iniciar el bot y elegir el canal del evento.", text_color=MUTED)
            return
        bots = [s for s in runner.pool_snapshot() if not s["lane"]]
        if not bots:
            return
        good = [b for b in bots if b["lane_note"].startswith("ok")]
        bad = [b for b in bots if b["lane_note"] and not b["lane_note"].startswith("ok")]
        if not self.vars["use_webhooks"].get() and not good:
            self.lanes_status.configure(text="Desactivados.", text_color=MUTED)
            return
        lines = [f"● {len(good)} de {len(bots)} bots tienen su webhook en el canal del evento"]
        lines += [f"✗ {b['name'].rsplit('#', 1)[0]}: {b['lane_note']}" for b in bad[:6]]
        self.lanes_status.configure(text="\n".join(lines), text_color=GREEN if good and not bad else AMBER if good else MUTED)

    # ---- Discord Activity ---------------------------------------------------------------
    def _build_activity(self, row: int) -> None:
        box = self._section("Actividad de Discord (beta)", row)
        self._note(box, 1, "Una Actividad es una pantalla del juego dentro de Discord (PC y móvil) que muestra el canal del "
                           "evento y mide los tiempos sin depender de los mensajes. Esta versión es un prototipo: espeja el "
                           "canal en solo lectura y mide la conexión de cada jugador. Funciona desde este PC con un túnel "
                           "gratuito de Cloudflare cuya dirección cambia cada vez. Pasos en docs/ACTIVIDAD.md.")
        ctk.CTkCheckBox(box, text="Activar la Actividad al iniciar el bot", variable=self.vars["activity_enabled"],
                        fg_color=ACCENT, hover_color=ACCENT).grid(row=2, column=0, columnspan=4, padx=18, pady=(2, 6), sticky="w")
        self.activity_secret_entry = self._field(box, 3, "Client Secret", "activity_client_secret", show="•")
        self._note(box, 4, "Developer Portal → tu aplicación → OAuth2 → «Client Secret». Se guarda solo en este equipo.", pady=(0, 6))
        self.activity_status = ctk.CTkLabel(box, text="", text_color=MUTED, anchor="w", justify="left", wraplength=640)
        self.activity_status.grid(row=5, column=0, columnspan=4, padx=18, pady=(2, 6), sticky="w")
        buttons = ctk.CTkFrame(box, fg_color="transparent")
        buttons.grid(row=6, column=0, columnspan=4, padx=14, pady=(0, 14), sticky="w")
        self.activity_buttons = {}
        for text, command in (("Copiar dirección", self._copy_activity_url), ("Nueva dirección", self._reopen_tunnel),
                              ("Probar en este PC", self._test_activity), ("Abrir Developer Portal", self._open_portal)):
            button = ctk.CTkButton(buttons, text=text, width=150, height=30, fg_color=BUTTON_NEUTRAL, hover_color=CARD_BORDER,
                                   command=command)
            button.pack(side="left", padx=4)
            self.activity_buttons[text] = button

    def _activity_url(self) -> str:
        return self.app.runner.activity_info().get("url", "")

    def _copy_activity_url(self) -> None:
        url = self._activity_url()
        if not url:
            self.activity_status.configure(text="Todavía no hay dirección: el túnel se abre al iniciar el bot.", text_color=AMBER)
            return
        self.clipboard_clear()
        self.clipboard_append(url.removeprefix("https://"))
        self.activity_status.configure(text=f"Copiada: {url.removeprefix('https://')} (pégala en URL Mappings, raíz «/»).",
                                       text_color=GREEN)

    def _reopen_tunnel(self) -> None:
        try:
            future = self.app.runner.reopen_tunnel()
        except RuntimeError as exc:
            self.activity_status.configure(text=str(exc), text_color=AMBER)
            return
        self.activity_status.configure(text="Abriendo un túnel nuevo…", text_color=MUTED)
        self.app.watch(future, lambda result: None, lambda exc: self.activity_status.configure(text=f"✗ {exc}", text_color=RED))

    def _test_activity(self) -> None:
        info = self.app.runner.activity_info()
        if not info.get("running"):
            self.activity_status.configure(text="La Actividad no está en marcha: actívala, guarda y inicia el bot.", text_color=AMBER)
            return
        webbrowser.open(f"http://127.0.0.1:{info['port']}/?dev=Admin")

    def _open_portal(self) -> None:
        webbrowser.open(DEVELOPER_PORTAL)

    def _refresh_activity(self) -> None:
        info = self.app.runner.activity_info()
        if not info.get("running"):
            enabled = bool(self.vars["activity_enabled"].get())
            self.activity_status.configure(
                text="Se activará al iniciar el bot." if enabled else "Desactivada.", text_color=MUTED)
            return
        lines = []
        if info["tunnel"] == "up":
            lines.append(f"● Túnel listo: {info['url'].removeprefix('https://')}")
            lines.append("En el Developer Portal → Activities → URL Mappings pon esa dirección en la raíz «/» (cambia en cada inicio).")
        elif info["tunnel"] == "error":
            lines.append(f"✗ Túnel: {info['detail']}")
        else:
            lines.append(f"… {info['detail'] or 'Preparando el túnel'}")
        if not info["secret_set"]:
            lines.append("⚠ Falta el Client Secret: nadie podrá entrar desde Discord.")
        users = info["users"]
        if users:
            lines.append(f"{len(users)} conexión(es): " + " · ".join(
                f"{u['name']} {round(u['rtt_ms'])} ms" if u["rtt_ms"] is not None else u["name"] for u in users[:8]))
        else:
            lines.append("Nadie conectado todavía.")
        color = RED if info["tunnel"] == "error" else GREEN if info["tunnel"] == "up" and info["secret_set"] else AMBER
        self.activity_status.configure(text="\n".join(lines), text_color=color)

    # ---- startup ---------------------------------------------------------------------
    def _build_startup(self, row: int) -> None:
        box = self._section("Inicio", row)
        checks = (("auto_start", "Iniciar el bot automáticamente al abrir la app"),
                  ("reset_on_start", "Reiniciar HP, cargas y buffs cada vez que se inicia el bot"),
                  ("hotkeys_enabled", "Atajos de teclado globales (F9–F12, F8…) — funcionan aunque la app esté en segundo plano"))
        for i, (key, text) in enumerate(checks, start=1):
            ctk.CTkCheckBox(box, text=text, variable=self.vars[key], fg_color=ACCENT, hover_color=ACCENT).grid(
                row=i, column=0, columnspan=4, padx=18, pady=(6, 14 if i == len(checks) else 6), sticky="w")

    # ---- AI ----------------------------------------------------------------------------
    def _build_ai(self, row: int) -> None:
        box = self._section("IA (Ollama, opcional)", row)
        ctk.CTkSwitch(box, text="Activar la IA del bot", variable=self.vars["ai_enabled"], progress_color=ACCENT).grid(
            row=1, column=0, columnspan=4, padx=18, pady=(2, 6), sticky="w")
        self._field(box, 2, "Dirección", "ollama_endpoint")
        ctk.CTkLabel(box, text="Modelo", text_color=MUTED, anchor="w").grid(row=3, column=0, padx=(18, 12), pady=6, sticky="w")
        self.model_box = ctk.CTkComboBox(box, variable=self.vars["ollama_model"], values=[""], height=34)
        self.model_box.grid(row=3, column=1, padx=(0, 8), pady=6, sticky="ew")
        self.detect_btn = ctk.CTkButton(box, text="Detectar modelos", width=140, height=34, fg_color=BUTTON_NEUTRAL,
                                        command=self._detect_models)
        self.detect_btn.grid(row=3, column=2, columnspan=2, padx=(0, 18), pady=6)
        self.ai_msg = self._note(box, 4, "Pulsa «Detectar modelos» para elegir uno de los que tienes instalados en Ollama.",
                                 pady=(0, 12))

    def _detect_models(self) -> None:
        endpoint = self.vars["ollama_endpoint"].get()
        self.detect_btn.configure(state="disabled")
        self.ai_msg.configure(text="Buscando modelos…", text_color=MUTED)

        def done(models: list[str]) -> None:
            self.detect_btn.configure(state="normal")
            if not models:
                self.ai_msg.configure(text="Ollama responde, pero no tiene modelos instalados (ollama pull <modelo>).", text_color=AMBER)
                return
            self.model_box.configure(values=models)
            if self.vars["ollama_model"].get() not in models:
                self.vars["ollama_model"].set(models[0])
            self.ai_msg.configure(text=f"✓ {len(models)} modelos instalados. Elige uno de la lista.", text_color=GREEN)

        def failed(exc: BaseException) -> None:
            self.detect_btn.configure(state="normal")
            self.ai_msg.configure(text=f"✗ {exc}", text_color=RED)

        self.app.bg(lambda: ollama.list_models(endpoint), done, failed)

    # ---- called by the app --------------------------------------------------------------
    def tick(self, state: State) -> None:
        """Every ~400 ms: load the server lists when the bot connects, update helper status."""
        if state is State.CONNECTED and not self._loaded_session:
            self._loaded_session = True
            self.reload_servers()
        elif state in (State.STOPPED, State.ERROR) and self._loaded_session:
            self._loaded_session = False
            self._snapshot = None
            self._show_offline_event()
        self._refresh_helper_status()
        self._refresh_webhooks()
        self._refresh_activity()

    def collect(self) -> Settings:
        """Settings as currently shown (helper bots and event names are kept up to date by the app)."""
        current = self.app.settings
        values = {key: var.get() for key, var in self.vars.items()}
        return Settings(
            **values,
            qte_player_role_id=current.qte_player_role_id, admin_role_id=current.admin_role_id,
            helper_bots=current.helper_bots, event_summary=current.event_summary,
        )

    def flash(self, text: str, color: str) -> None:
        self.save_msg.configure(text=text, text_color=color)
        self.after(6000, lambda: self.save_msg.configure(text=""))
