"""Eventos App - desktop shell around the QTE Discord bot.

This package is intentionally light to import: the headless (Docker/Railway)
deployment imports `eventos_app.paths` and `eventos_app.console_bridge` from the
bot, so nothing GUI-related may be imported here.
"""

__version__ = "0.10.0"
APP_NAME = "Eventos App"
