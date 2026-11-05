"""Spanish for the bot: the catalogue of its English text (extract.py, catalog_es.json), the translator (translator.py) and the
layer that applies it to what is sent to Discord and written in the app's log (discord_hooks.py).

`activate("es")` is all the app calls; `"en"` leaves the bot as it was written."""
from __future__ import annotations

import logging

log = logging.getLogger("eventos_app.lang")
LANGUAGES = ("es", "en")


def activate(language: str = "es"):
    """Translate the bot's messages and log to `language`. Returns the translator (None for English). Never raises."""
    from .. import console_bridge
    from . import discord_hooks
    if language != "es":
        discord_hooks.uninstall()
        console_bridge.console.translate = None
        return None
    try:
        from .translator import load
        tr = load()
    except Exception:  # noqa: BLE001 - a broken catalogue leaves the bot in English, it never stops it
        log.exception("could not load the Spanish catalogue")
        return None
    discord_hooks.install(tr)
    console_bridge.console.translate = lambda text: tr.text(text, "console")
    return tr
