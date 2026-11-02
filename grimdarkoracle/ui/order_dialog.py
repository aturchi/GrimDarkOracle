"""An ordered list the user rearranges (Up / Down / Default), shared by
the firing order of the weapons and the Takedown preferences
on a target. on_ok(order) gets the list of item ids, or None
when the default was kept or restored.

weapon_order() and takedown_order() build the two dialogs from plain
names and labels.
"""
import tkinter as tk
from tkinter import ttk

from grimdarkoracle.app.analyzer_orders import moved
from grimdarkoracle.ui import ui_utils as ui


class OrderDialog(tk.Toplevel):
    def __init__(self, parent, title: str, hint: str, labels: dict, order,
                 default, on_ok, is_default: bool = True,
                 default_name: str = "default order", suggest=None):
        """labels: {id: text}; order: ids as shown first; default: the ids
        in the default order (Default button); suggest: optional callable
        -> (ids first in the suggested order, or None for the default;
        a line of text), behind a "Suggest" button."""
        super().__init__(parent)
        self.suggest = suggest
        self.title(title)
        self.labels, self.on_ok = labels, on_ok
        self.order, self._default = list(order), list(default)
        self.default, self.default_name = is_default, default_name
        ttk.Label(self, text=hint, foreground=ui.HINT_COLOR,
                  wraplength=460, justify=tk.LEFT).pack(anchor=tk.W, padx=6,
                                                        pady=4)
        self.box = tk.Listbox(self, width=64, height=max(3, min(
            16, len(self.order))), exportselection=False)
        self.box.pack(fill=tk.BOTH, expand=True, padx=6)
        row = ttk.Frame(self)
        row.pack(fill=tk.X, padx=6, pady=4)
        for text, fn in (("Up", lambda: self.cmd_move(-1)),
                         ("Down", lambda: self.cmd_move(1)),
                         ("Default", self.cmd_default)):
            ttk.Button(row, text=text, command=fn).pack(side=tk.LEFT, padx=1)
        if suggest is not None:
            ui.tip(ttk.Button(row, text="Suggest", command=self.cmd_suggest),
                   "The order with the most models killed on average "
                   "(exact search, within the rules)").pack(side=tk.LEFT,
                                                            padx=1)
        self.mode = ttk.Label(row, foreground=ui.HINT_COLOR)
        self.mode.pack(side=tk.LEFT, padx=8)
        ttk.Button(row, text="Cancel", command=self.destroy).pack(
            side=tk.RIGHT, padx=1)
        ttk.Button(row, text="OK", command=self.cmd_ok).pack(side=tk.RIGHT)
        self.note = ttk.Label(self, text="", foreground=ui.HINT_COLOR,
                              wraplength=460, justify=tk.LEFT)
        self.note.pack(anchor=tk.W, padx=6, pady=(0, 4))
        self.bind("<Escape>", lambda _e: self.destroy())
        self._fill()

    def _fill(self, select=None) -> None:
        self.box.delete(0, tk.END)
        for i in self.order:
            self.box.insert(tk.END, self.labels[i])
        if select is not None:
            self.box.selection_set(self.order.index(select))
        self.mode.configure(text=self.default_name if self.default
                            else "your order")

    def selected(self):
        sel = self.box.curselection()
        return self.order[sel[0]] if sel else None

    def cmd_move(self, delta: int) -> None:
        i = self.selected()
        if i is None:
            return
        self.order = moved(self.order, i, delta)
        self.default = False
        self._fill(i)

    def cmd_default(self) -> None:
        self.order, self.default = list(self._default), True
        self._fill()

    def cmd_suggest(self) -> None:
        """Show the suggested order (busy cursor while searching)."""
        self.configure(cursor="watch")
        self.update_idletasks()
        try:
            first, text = self.suggest()
        finally:
            self.configure(cursor="")
        if first is None:
            self.cmd_default()
        else:
            first = [i for i in first if i in self.labels]
            self.order = first + [i for i in self.order if i not in first]
            self.default = False
            self._fill()
        self.note.configure(text=text)

    def cmd_ok(self) -> None:
        order = None if self.default else list(self.order)
        self.destroy()
        self.on_ok(order)


def weapon_order(parent, names, current, done, who: str = "",
                 suggest=None):
    """OrderDialog of the weapon 'names'; done(names tuple), () for the
    book order. Names no longer in 'names' are dropped. Listed weapons
    attack first within their class: Takedown, Deadly, others.
    suggest: see OrderDialog."""
    names = list(names)
    current = tuple(n for n in current if n in names)
    order = list(current) + [n for n in names if n not in current]
    return OrderDialog(parent, f"Weapon order{who}", "Listed first attack "
                       "first, within the rules: Takedown, then Deadly, then "
                       "the others.", {n: n for n in names}, order,
                       names, lambda o: done(tuple(o or ())),
                       is_default=not current, default_name="book order",
                       suggest=suggest)


def takedown_order(parent, labels, current, default, done,
                   who: str = ""):
    """OrderDialog of the target's model places (labels by place), first
    choice first; done(places tuple), () for the default (the model
    the allocation order would remove last first). A dead pick passes to
    the next."""
    places = range(len(labels))
    current = tuple(p for p in current if p in places)
    order = list(current) + [p for p in default if p not in current]
    order += [p for p in places if p not in order]
    return OrderDialog(parent, f"Takedown targets{who}", "Every Takedown "
                       "weapon picks the first model of the list still "
                       "alive.",
                       {p: f"m{p + 1}  {lab}" for p, lab in enumerate(labels)},
                       order, default, lambda o: done(tuple(o or ())),
                       is_default=not current,
                       default_name="default (removed last first)")
