"""Custom widgets."""

from __future__ import annotations

import tkinter as tk
from typing import Callable

import customtkinter as ctk

from .theme import ACCENT, CARD, CARD_BORDER, INPUT_BG, MUTED, TEXT

POPUP_HEIGHT = 330
NONE_ID = 0


class PickerField(ctk.CTkFrame):
    """A dropdown with a search box.

    Built for lists that are too long for a plain menu (a roleplay server easily has hundreds of
    channels and roles): click, type to filter, arrow keys + Enter (or click) to choose, Esc to close.
    Items are (id, label, group) tuples; `none_label` adds a first "no selection" entry whose id is 0.
    """

    def __init__(self, master, *, placeholder: str = "Elegir…", none_label: str | None = None,
                 on_change: Callable[[int | None], None] | None = None) -> None:
        super().__init__(master, fg_color="transparent")
        self.placeholder = placeholder
        self.none_label = none_label
        self.on_change = on_change
        self._items: list[tuple[int, str, str]] = []
        self._value: int | None = None
        self._fallback = ""
        self._enabled = True
        self._popup: tk.Toplevel | None = None
        self._visible: list[tuple[int, str, str]] = []
        self._button = ctk.CTkButton(
            self, text="", anchor="w", height=34, fg_color=INPUT_BG, hover_color=CARD_BORDER, border_width=1,
            border_color=CARD_BORDER, text_color=TEXT, text_color_disabled=MUTED, command=self.toggle)
        self._button.pack(fill="x")
        self._render()

    # ---- data ---------------------------------------------------------------------
    def set_items(self, items: list[tuple[int, str, str]]) -> None:
        self._items = list(items)
        self._render()

    def set_value(self, value: int | None, fallback: str = "") -> None:
        """Select `value`. `fallback` is the text to show if it isn't in the list (e.g. while offline)."""
        self._value = value
        self._fallback = fallback
        self._render()

    def get(self) -> int | None:
        return self._value

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self._button.configure(state="normal" if enabled else "disabled")
        if not enabled:
            self.close()

    def _label_for(self, value: int | None) -> str:
        if value in (None, NONE_ID):
            return self.none_label or ""
        for ident, label, _group in self._items:
            if ident == value:
                return label
        return self._fallback or f"(ID {value})"

    def _render(self) -> None:
        label = self._label_for(self._value)
        self._button.configure(text=f"{label or self.placeholder}   ▾", text_color=TEXT if label else MUTED)

    # ---- popup ----------------------------------------------------------------------
    def toggle(self) -> None:
        if self._popup is not None:
            self.close()
        else:
            self.open()

    def open(self) -> None:
        if self._popup is not None or not self._enabled:
            return
        root = self.winfo_toplevel()
        top = tk.Toplevel(root)
        top.overrideredirect(True)
        top.configure(bg=CARD_BORDER)
        self._popup = top

        self.update_idletasks()
        width = max(self._button.winfo_width(), 300)
        x, y = self._button.winfo_rootx(), self._button.winfo_rooty() + self._button.winfo_height() + 2
        if y + POPUP_HEIGHT > self.winfo_screenheight():  # not enough room below: open upwards
            y = max(0, self._button.winfo_rooty() - POPUP_HEIGHT - 2)
        top.geometry(f"{width}x{POPUP_HEIGHT}+{x}+{y}")

        inner = tk.Frame(top, bg=CARD)
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        self._query = tk.StringVar()
        search = tk.Entry(inner, textvariable=self._query, bg=INPUT_BG, fg=TEXT, insertbackground=TEXT, relief="flat",
                          highlightthickness=1, highlightbackground=CARD_BORDER, highlightcolor=ACCENT)
        search.pack(fill="x", padx=8, pady=(8, 4), ipady=5)
        body = tk.Frame(inner, bg=CARD)
        body.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._list = tk.Listbox(body, activestyle="none", bg=CARD, fg=TEXT, selectbackground=ACCENT, selectforeground="white",
                                highlightthickness=0, relief="flat", borderwidth=0, exportselection=False)
        scrollbar = ctk.CTkScrollbar(body, command=self._list.yview)
        self._list.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self._list.pack(side="left", fill="both", expand=True)

        self._query.trace_add("write", lambda *_: self._fill())
        search.bind("<Down>", lambda e: self._move(1))
        search.bind("<Up>", lambda e: self._move(-1))
        search.bind("<Return>", lambda e: self._choose_selected())
        self._list.bind("<ButtonRelease-1>", lambda e: self._choose_at(e.y))
        top.bind("<Escape>", lambda e: self.close())
        search.bind("<Escape>", lambda e: self.close())
        top.bind("<ButtonPress-1>", self._click_outside, add="+")

        self._fill(select=self._value)
        try:
            top.wait_visibility()
            top.grab_set()  # clicks elsewhere are reported to the popup, which closes it
        except tk.TclError:
            pass
        search.focus_set()

    def close(self) -> None:
        top, self._popup = self._popup, None
        if top is None:
            return
        try:
            top.grab_release()
        except tk.TclError:
            pass
        top.destroy()

    def _click_outside(self, event) -> None:
        top = self._popup
        if top is None:
            return
        inside = (top.winfo_rootx() <= event.x_root < top.winfo_rootx() + top.winfo_width()
                  and top.winfo_rooty() <= event.y_root < top.winfo_rooty() + top.winfo_height())
        if not inside:
            self.close()

    def _fill(self, select: int | None = None) -> None:
        query = self._query.get().strip().lower()
        rows = ([(NONE_ID, self.none_label, "")] if self.none_label else []) + self._items
        self._visible = [r for r in rows if not query or query in f"{r[1]} {r[2]}".lower()]
        self._list.delete(0, "end")
        for _ident, label, group in self._visible:
            self._list.insert("end", f"{label}   ·  {group}" if group else label)
        target = 0
        if select is not None:
            for i, row in enumerate(self._visible):
                if row[0] == select:
                    target = i
                    break
        if self._visible:
            self._list.selection_set(target)
            self._list.see(target)

    def _move(self, step: int) -> str:
        if not self._visible:
            return "break"
        current = self._list.curselection()
        index = (current[0] if current else -1) + step
        index = max(0, min(len(self._visible) - 1, index))
        self._list.selection_clear(0, "end")
        self._list.selection_set(index)
        self._list.see(index)
        return "break"

    def _choose_selected(self) -> None:
        current = self._list.curselection()
        if current:
            self._pick(self._visible[current[0]][0])

    def _choose_at(self, y: int) -> None:
        if not self._visible:
            return
        index = self._list.nearest(y)
        if 0 <= index < len(self._visible):
            self._pick(self._visible[index][0])

    def _pick(self, ident: int) -> None:
        self._value = ident
        self._fallback = ""
        self.close()
        self._render()
        if self.on_change is not None:
            self.on_change(ident)
