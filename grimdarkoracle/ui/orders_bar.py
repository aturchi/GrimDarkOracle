"""The attacker's weapon order and Takedown target preferences in the
Analyzer window: two buttons opening the shared order dialogs
and a line saying what is set. Thin view over app.analyzer_orders.

The window calls refresh(info) whenever the sides or the setup change;
the bar keeps the orders valid for them (the Takedown preferences
are reset when the target's configuration changes).
"""
import tkinter as tk
from tkinter import ttk

from grimdarkoracle.app import analyzer_orders as AO
from grimdarkoracle.ui import ui_utils as ui
from grimdarkoracle.ui.order_dialog import takedown_order, weapon_order


class OrdersBar(ttk.LabelFrame):
    """on_change(orders) after a dialog changed them."""

    def __init__(self, parent, on_change=None, suggest=None):
        """suggest: callable -> (names first, line) for the weapon order
        dialog's Suggest button, or None."""
        super().__init__(parent, text="Attacker's orders")
        self.on_change, self.suggest = on_change, suggest
        self.orders = AO.Orders()
        self.info: AO.Info | None = None
        row = ttk.Frame(self)
        row.pack(fill=tk.X, padx=4, pady=2)
        self.weapon_btn = ui.tip(
            ttk.Button(row, text="Weapon order...", command=self.cmd_weapons),
            "The attacker's weapons that attack first, within the rules: "
            "Takedown, then Deadly, then the others; in melee the "
            "charger's weapons")
        self.weapon_btn.pack(side=tk.LEFT)
        self.takedown_btn = ui.tip(
            ttk.Button(row, text="Takedown targets...",
                       command=self.cmd_takedown),
            "Models of the target every Takedown weapon picks, first "
            "choice first (a dead pick passes to the next)")
        self.takedown_btn.pack(side=tk.LEFT, padx=4)
        self.text = ttk.Label(self, text="", foreground=ui.HINT_COLOR,
                              wraplength=360, justify=tk.LEFT)
        self.text.pack(anchor=tk.W, padx=4)
        self._show()

    def refresh(self, info: AO.Info) -> None:
        """New sides or setup: keep what still applies."""
        self.orders = AO.follow(self.orders, self.info, info)
        self.info = info
        self._show()

    def get(self) -> AO.Orders:
        return self.orders

    def set(self, orders: AO.Orders) -> None:
        """Orders from a session, restricted to the current sides."""
        self.orders = orders if self.info is None else \
            AO.clean(orders, self.info)
        self._show()

    def _show(self) -> None:
        info = self.info or AO.Info()
        self.weapon_btn.configure(state=tk.NORMAL if info.weapons
                                  else tk.DISABLED)
        self.takedown_btn.configure(state=tk.NORMAL if info.takedown
                                    else tk.DISABLED)
        self.text.configure(text=AO.describe(self.orders, info))

    def _done(self, orders: AO.Orders) -> None:
        self.orders = orders
        self._show()
        if self.on_change:
            self.on_change(orders)

    def cmd_weapons(self):
        if self.info is None or not self.info.weapons:
            return None
        return weapon_order(self, self.info.names, self.orders.weapon_order,
                            lambda o: self._done(AO.Orders(
                                o, self.orders.takedown_targets)),
                            suggest=self.suggest)

    def cmd_takedown(self):
        if self.info is None or not self.info.takedown:
            return None
        return takedown_order(self, self.info.labels,
                              self.orders.takedown_targets, self.info.default,
                              lambda o: self._done(AO.Orders(
                                  self.orders.weapon_order, o)))
