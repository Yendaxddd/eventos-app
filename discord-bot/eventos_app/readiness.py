"""«Antes de empezar»: what is still missing for the event to work, as a short checklist for the Home page. Pure: the window gives it the
facts (settings and what the bot says) and shows the steps."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Step:
    key: str
    title: str
    detail: str
    state: str           # "done" | "todo" | "wait" (needs the step before) | "off" (optional and switched off)
    action: str = ""     # the page or place that fixes it: "config", "event", "activity", "start" or ""


def checklist(*, token_set: bool, connected: bool, starting: bool, event_ready: bool, activity_enabled: bool,
              secret_set: bool, tunnel: str = "", tunnel_detail: str = "", activity_running: bool = False) -> list[Step]:
    """`tunnel` is the Activity tunnel's state («up», «error», something else while it is opening); `event_ready` is a channel chosen."""
    steps = [Step("token", "Token del bot", "Pegado." if token_set else "Pégalo en Configuración (Developer Portal → Bot → Reset Token).",
                  "done" if token_set else "todo", "" if token_set else "config")]
    if not token_set:
        steps.append(Step("start", "Iniciar el bot", "Primero falta el token.", "wait"))
    elif connected:
        steps.append(Step("start", "Iniciar el bot", "Conectado a Discord.", "done"))
    else:
        steps.append(Step("start", "Iniciar el bot", "Conectando…" if starting else "Pulsa «Iniciar bot».", "wait" if starting else "todo",
                          "" if starting else "start"))
    if connected:
        steps.append(Step("event", "Servidor y canal del evento", "Elegidos." if event_ready else "Elige el servidor y el canal donde ocurren los QTE.",
                          "done" if event_ready else "todo", "" if event_ready else "event"))
    else:
        steps.append(Step("event", "Servidor y canal del evento", "Se elige con el bot conectado.", "wait"))
    if not activity_enabled:
        steps.append(Step("activity", "Actividad de Discord", "Apagada: los QTE van por el chat de siempre. Actívala para tener botones, paneles y el panel del GM.",
                          "off", "activity"))
    elif not secret_set:
        steps.append(Step("activity", "Actividad de Discord", "Falta el Client Secret (Developer Portal → OAuth2): sin él nadie puede entrar.", "todo", "activity"))
    elif not connected:
        steps.append(Step("activity", "Actividad de Discord", "Se abrirá al iniciar el bot.", "wait"))
    elif tunnel == "up":
        steps.append(Step("activity", "Actividad de Discord", "Lista: pega su dirección en el Developer Portal si cambió.", "done", "activity"))
    elif tunnel == "error":
        steps.append(Step("activity", "Actividad de Discord", tunnel_detail or "El túnel no se pudo abrir.", "todo", "activity"))
    else:
        steps.append(Step("activity", "Actividad de Discord", tunnel_detail or "Abriendo el túnel…", "wait" if activity_running else "todo", "activity"))
    return steps


def all_done(steps: list[Step]) -> bool:
    return all(step.state in ("done", "off") for step in steps)
