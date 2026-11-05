"""Colours, type and small building blocks shared by the windows. The palette is the Activity's own (a deep blue-violet «ink» with a violet
accent), so the app and what the players see feel like one product."""

import sys

import customtkinter as ctk

# surfaces, from the window's background up to a raised card
BG = "#0b0b14"
SIDEBAR = "#0f0f1b"
CARD = "#141422"
CARD_2 = "#1a1a2c"
CARD_BORDER = "#26263d"
INPUT_BG = "#1b1b2e"

TEXT = "#ecebf8"
MUTED = "#a09fc0"
FAINT = "#6f6e92"

ACCENT = "#8b5cf6"
ACCENT_HOVER = "#7a49ea"
ACCENT_SOFT = "#272050"                    # the chosen page in the sidebar, soft highlights
GREEN, GREEN_HOVER = "#1f9d6c", "#188358"
RED, RED_HOVER = "#d6455d", "#b8374d"
AMBER = "#e0a030"
GRAY = "#6b6a8a"
INACTIVE = "#1d1d30"
BUTTON_NEUTRAL = "#2b2b45"
BUTTON_NEUTRAL_HOVER = "#37375a"

# text colours for good / bad news (the buttons above are a shade deeper so white text reads on them)
OK_TEXT = "#4ade9c"
BAD_TEXT = "#fb7185"
WARN_TEXT = "#fbbf24"

LOG_MONO = "Consolas" if sys.platform == "win32" else "DejaVu Sans Mono"

TONES = {            # (text, background) of a small status pill
    "ok": (OK_TEXT, "#12382b"), "warn": (WARN_TEXT, "#3a2d10"), "bad": (BAD_TEXT, "#3d1620"),
    "info": ("#7cb7ff", "#142640"), "accent": ("#b9a2ff", ACCENT_SOFT), "idle": (MUTED, "#23233a"),
}


def font(size: int = 13, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(size=size, weight=weight)


def card(parent, **kwargs) -> ctk.CTkFrame:
    return ctk.CTkFrame(parent, fg_color=CARD, border_color=CARD_BORDER, border_width=1, corner_radius=14, **kwargs)


def raised(parent, **kwargs) -> ctk.CTkFrame:
    """A box inside a card (a row of a list, a tile)."""
    return ctk.CTkFrame(parent, fg_color=CARD_2, corner_radius=10, **kwargs)


def button(parent, text: str, command=None, *, kind: str = "neutral", width: int = 0, height: int = 34, **kwargs) -> ctk.CTkButton:
    """Buttons of the app: «primary» (violet), «good» (green), «bad» (red), «neutral» or «ghost» (no background)."""
    styles = {
        "primary": dict(fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="white"),
        "good": dict(fg_color=GREEN, hover_color=GREEN_HOVER, text_color="white"),
        "bad": dict(fg_color=RED, hover_color=RED_HOVER, text_color="white"),
        "neutral": dict(fg_color=BUTTON_NEUTRAL, hover_color=BUTTON_NEUTRAL_HOVER, text_color=TEXT),
        "ghost": dict(fg_color="transparent", hover_color=CARD_BORDER, text_color=MUTED, border_width=1, border_color=CARD_BORDER),
    }[kind]
    options = {**styles, "corner_radius": 8, "height": height, "text_color_disabled": FAINT, **kwargs}
    if width:
        options["width"] = width
    return ctk.CTkButton(parent, text=text, command=command, **options)


def apply() -> None:
    """Give every standard widget of CustomTkinter the colours of the app (entries, menus, switches...), so each page does not have to."""
    manager = ctk.ThemeManager.theme

    def pair(color):
        return [color, color]

    changes = {
        "CTkEntry": dict(fg_color=pair(INPUT_BG), border_color=pair(CARD_BORDER), text_color=pair(TEXT), placeholder_text_color=pair(FAINT)),
        "CTkComboBox": dict(fg_color=pair(INPUT_BG), border_color=pair(CARD_BORDER), button_color=pair(BUTTON_NEUTRAL), button_hover_color=pair(BUTTON_NEUTRAL_HOVER),
                            dropdown_fg_color=pair(CARD), dropdown_hover_color=pair(ACCENT_SOFT), dropdown_text_color=pair(TEXT), text_color=pair(TEXT)),
        "CTkOptionMenu": dict(fg_color=pair(BUTTON_NEUTRAL), button_color=pair(CARD_BORDER), button_hover_color=pair(BUTTON_NEUTRAL_HOVER),
                              dropdown_fg_color=pair(CARD), dropdown_hover_color=pair(ACCENT_SOFT), dropdown_text_color=pair(TEXT), text_color=pair(TEXT)),
        "CTkSwitch": dict(progress_color=pair(ACCENT), button_color=pair("#ffffff"), button_hover_color=pair("#e6e6f2"), fg_color=pair("#2e2e4a"), text_color=pair(TEXT)),
        "CTkCheckBox": dict(fg_color=pair(ACCENT), hover_color=pair(ACCENT_HOVER), border_color=pair("#3b3b5c"), checkmark_color=pair("#ffffff"), text_color=pair(TEXT)),
        "CTkScrollbar": dict(button_color=pair("#34344f"), button_hover_color=pair("#4a4a6e")),
        "CTkSegmentedButton": dict(selected_color=pair(ACCENT), selected_hover_color=pair(ACCENT_HOVER), unselected_color=pair(INPUT_BG),
                                   unselected_hover_color=pair(CARD_BORDER), fg_color=pair(INPUT_BG), text_color=pair(TEXT)),
        "CTkProgressBar": dict(fg_color=pair("#0a0a12"), progress_color=pair(ACCENT)),
        "CTkTextbox": dict(fg_color=pair(INPUT_BG), text_color=pair(TEXT), border_color=pair(CARD_BORDER)),
        "CTkLabel": dict(text_color=pair(TEXT)),
    }
    for widget, values in changes.items():
        try:
            manager[widget].update(values)
        except (KeyError, TypeError, AttributeError):
            pass                                            # a CustomTkinter version without that widget in its theme: keep its own colours
