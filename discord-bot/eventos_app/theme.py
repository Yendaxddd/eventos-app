"""Colours and small building blocks shared by the windows."""

import sys

import customtkinter as ctk

BG = "#16171a"
CARD = "#1f2125"
CARD_BORDER = "#2b2e34"
INPUT_BG = "#2a2d33"
TEXT = "#e4e4e7"
MUTED = "#9a9ea8"
ACCENT = "#7c5cff"
GREEN, GREEN_HOVER = "#2e9e5b", "#268a4e"
RED, RED_HOVER = "#d1495b", "#b53c4d"
AMBER = "#e0a030"
GRAY = "#6b7280"
INACTIVE = "#2a2d33"
BUTTON_NEUTRAL = "#3b3f47"
LOG_MONO = "Consolas" if sys.platform == "win32" else "DejaVu Sans Mono"


def card(parent, **kwargs) -> ctk.CTkFrame:
    return ctk.CTkFrame(parent, fg_color=CARD, border_color=CARD_BORDER, border_width=1, corner_radius=12, **kwargs)
