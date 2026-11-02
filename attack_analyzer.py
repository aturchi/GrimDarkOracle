#!/usr/bin/env python3
"""GrimDarkOracle Attack Analyzer: exact laws of one unit's attack on another
in Grimdark Future 3.6 (shooting, or a charge with the full melee
exchange), with Morale and points metrics.

Left / right: the two sides (army book unit or army list entry, upgrades,
joined Hero, state at the start). Middle: the attack setup. "Analyse"
opens a result window (several may stay open); "Pin" keeps a result for
the comparison window; "Variants" compares the options of one section.
Under the setup: the attacker's weapon order and the Takedown target
preferences.

Run from the repository root:  python attack_analyzer.py
Army Forge data: python tools/af_fetch.py (downloads into data/army_forge).
"""
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from grimdarkoracle import app_paths
from grimdarkoracle.app import analyzer_orders as AO
from grimdarkoracle.app import comparison as C
from grimdarkoracle.app import defense_choice as DC
from grimdarkoracle.app import order_advice as OA
from grimdarkoracle.app import session_io as SIO
from grimdarkoracle.app import setup_model as S
from grimdarkoracle.app import side_spec as SS
from grimdarkoracle.app import spells as SP
from grimdarkoracle.app import update_check
from grimdarkoracle.app.library import Library
from grimdarkoracle.engine.context import AttackContext, combatant
from grimdarkoracle.ui import search_widget
from grimdarkoracle.ui import ui_utils as ui
from grimdarkoracle.ui.orders_bar import OrdersBar
from grimdarkoracle.ui.result_window import CompareWindow, ResultWindow
from grimdarkoracle.ui.setup_panel import SetupPanel
from grimdarkoracle.ui.side_picker import SidePicker
from grimdarkoracle.ui.variants_dialog import VariantsDialog

ROLES = ("Attacker", "Target")
SESSIONS_DIR = os.path.join(app_paths.app_dir(), "sessions")


def _book(spec):
    return spec.unit.cfg.book if spec is not None else None


class AnalyzerApp(tk.Tk):
    def __init__(self, lib: Library | None = None):
        super().__init__()
        search_widget.attach_search(self)          # Ctrl+F
        self.title("GrimDarkOracle - Attack Analyzer")
        self.geometry("1440x880")
        self.lib = lib if lib is not None else Library.load()
        self.pins: list[dict] = []
        self.flipped = False            # True: right side attacks
        self._build()

    def _build(self):
        bar = ttk.Frame(self)
        bar.pack(fill=tk.X, padx=6, pady=4)
        ui.tip(ttk.Button(bar, text="Analyse", command=self.cmd_analyse),
               "Run the attack with the current setup").pack(side=tk.LEFT)
        ui.tip(ttk.Button(bar, text="Swap sides", command=self.cmd_swap),
               "The target attacks the attacker").pack(side=tk.LEFT, padx=4)
        ui.tip(ttk.Button(bar, text="Variants...", command=self.cmd_variants),
               "Compare every option of one upgrade section").pack(
            side=tk.LEFT, padx=4)
        self.compare_btn = ui.tip(
            ttk.Button(bar, text="Compare pins (0)", command=self.cmd_compare,
                       state=tk.DISABLED),
            "Pinned analyses side by side")
        self.compare_btn.pack(side=tk.LEFT, padx=4)
        ui.tip(ttk.Button(bar, text="Save session...", command=self.cmd_save),
               "Both sides, their state and the setup, with a copy of the "
               "books used (pins are not saved)").pack(side=tk.LEFT, padx=4)
        ui.tip(ttk.Button(bar, text="Load session...", command=self.cmd_open),
               "Restore a saved session").pack(side=tk.LEFT, padx=4)
        self.summary = ttk.Label(bar, text="", font=ui.bold_font())
        self.summary.pack(side=tk.LEFT, padx=12)
        status, warn = update_check.status_text(
            self.lib, f"{len(self.lib.books)} army books loaded")
        ttk.Label(self, text=status, foreground=ui.WARN_COLOR
                  if warn else ui.HINT_COLOR,
                  wraplength=1400).pack(side=tk.BOTTOM, anchor=tk.W, padx=6)
        panes = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        panes.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)
        self.left = SidePicker(panes, self.lib, ROLES[0], self._side_changed)
        middle = ttk.Frame(panes)
        self.setup = SetupPanel(middle, lambda _s: self._setup_changed())
        self.setup.pack(fill=tk.X)
        self.orders = OrdersBar(middle, suggest=self.suggest_order)
        self.orders.pack(fill=tk.X, pady=4)
        if self.lib.reg is not None:
            self.setup.set_marks(S.marks(self.lib.reg))
        self.right = SidePicker(panes, self.lib, ROLES[1], self._side_changed)
        panes.add(self.left, weight=3)
        panes.add(middle, weight=2)
        panes.add(self.right, weight=3)
        self._side_changed(self.attacker)

    # --- sides ---------------------------------------------------------------

    @property
    def attacker(self) -> SidePicker:
        return self.right if self.flipped else self.left

    @property
    def target(self) -> SidePicker:
        return self.left if self.flipped else self.right

    def sides(self) -> dict:
        return {ROLES[0]: self.attacker, ROLES[1]: self.target}

    def _side_changed(self, picker) -> None:
        if not hasattr(self, "right"):
            return                      # still building
        self._refresh_versatile()
        self._refresh_spells()
        self._refresh_orders()
        self._refresh_summary()

    def _refresh_versatile(self) -> None:
        """The attacker's Versatile choices and the target's Versatile
        Defense ('best' = the program picks)."""
        menu, defense = [], []
        reg, a, t = self.lib.reg, self.attacker.spec, self.target.spec
        if reg is not None and a is not None:
            menu = S.versatile(reg, a.resolved()[0])
        if reg is not None and a is not None and t is not None:
            (tu, th), (au, ah) = t.resolved(), a.resolved()
            defense = DC.menus(reg, combatant(tu, hero=th),
                               combatant(au, hero=ah), AttackContext(),
                               check=False)
        self.setup.set_versatile(menu, defense)

    def _setup_changed(self) -> None:
        self._refresh_orders()          # attack kind, spell (Takedown)
        self._refresh_summary()

    def _refresh_orders(self) -> None:
        if not hasattr(self, "right"):
            return                      # still building
        self.orders.refresh(AO.info(self.lib.reg, self.lib.sreg,
                                    self.attacker.spec, self.target.spec,
                                    self.setup.get_setup()))

    def _refresh_spells(self) -> None:
        """Damage spells of a Caster attacker, buff toggles of both books."""
        reg, sreg = self.lib.reg, self.lib.sreg
        a, t = self.attacker.spec, self.target.spec
        if reg is None or sreg is None:
            return
        spells, info = [], "no Caster in the attacker's unit"
        if a is not None:
            ru, hero = a.resolved()
            rating = SP.caster_rating(reg, ru, hero)
            if rating:
                mod = SP.cast_mod(reg, ru, hero)
                info = f"Caster({rating})" + (f", {mod:+d} to cast"
                                              if mod else "")
                spells = [(s.key, f"{s.name} ({s.threshold} tok., "
                                  f"{s.hits} hits)")
                          for s in sreg.spells(_book(a)) if s.kind == "damage"]
        self.setup.set_spells(spells, info)
        self.setup.set_buffs(SP.buff_menu(sreg, _book(a), _book(t)))

    def _refresh_summary(self) -> None:
        if not hasattr(self, "right"):
            return                      # still building
        s = self.setup.get_setup()
        verb = {"shooting": "shoots", "melee": "charges",
                "spell": "casts at"}[s.attack]
        self.summary.configure(text=f"{self.attacker.summary()}  {verb}  "
                               f"{self.target.summary()}")

    def cmd_swap(self) -> None:
        self.flipped = not self.flipped
        self.attacker.configure(text=ROLES[0])
        self.target.configure(text=ROLES[1])
        self._side_changed(self.attacker)

    # --- analysis ------------------------------------------------------------

    def suggest_order(self) -> tuple:
        """(names first, line) of the best weapon order for the current
        sides and setup, for the weapon order dialog."""
        att, tgt = self.attacker, self.target
        cur = self.orders.get().weapon_order
        if att.spec is None or tgt.spec is None:
            return list(cur) or None, "Pick a unit on both sides."
        try:
            a, t, opts, _n = SS.prepare(
                self.lib.reg, att.spec, att.state_panel.get_side(), tgt.spec,
                tgt.state_panel.get_side(), self.setup.get_setup(),
                self.lib.sreg, **self.orders.get().kw())
            sg = OA.analyzer(self.lib.reg, a, t, opts)
        except ValueError as exc:
            return list(cur) or None, str(exc)
        return OA.for_dialog(sg, cur)

    def run_with(self, role: str, spec):
        """Analysis with 'spec' in place of the side 'role' (variants)."""
        att, tgt = self.attacker, self.target
        a_spec = spec if role == ROLES[0] else att.spec
        t_spec = spec if role == ROLES[1] else tgt.spec
        return SS.run(self.lib.reg, a_spec, att.state_panel.get_side(),
                      t_spec, tgt.state_panel.get_side(),
                      self.setup.get_setup(), self.lib.sreg,
                      **self.orders.get().kw())

    def cmd_analyse(self):
        att, tgt = self.attacker, self.target
        if att.spec is None or tgt.spec is None:
            messagebox.showinfo("Analyse", "Pick a unit on both sides.",
                                parent=self)
            return None
        try:
            a = self.run_with(ROLES[0], att.spec)
        except ValueError as exc:
            messagebox.showerror("Analyse", str(exc), parent=self)
            return None
        sg = OA.analyzer(self.lib.reg, a.attacker, a.target, a.opts)
        return ResultWindow(self, a, self.summary.cget("text"),
                            on_pin=self._pin,
                            advice=OA.line(sg, a.opts.weapon_order))

    def cmd_variants(self):
        return VariantsDialog(self, self.sides(), self.run_with)

    # --- sessions ------------------------------------------------------------

    def session(self):
        return SIO.Session(self.setup.get_setup(),
                           {"left": self.left.state(),
                            "right": self.right.state()}, self.flipped,
                           self.orders.get())

    def apply_session(self, session) -> None:
        if session.flipped != self.flipped:
            self.cmd_swap()
        self.left.restore(session.sides.get("left"))
        self.right.restore(session.sides.get("right"))
        self._side_changed(self.attacker)
        self.setup.set_setup(session.setup)
        self._refresh_orders()
        self.orders.set(session.orders)
        self._refresh_summary()

    def cmd_save(self, path: str | None = None):
        if path is None:
            os.makedirs(SESSIONS_DIR, exist_ok=True)
            path = filedialog.asksaveasfilename(
                parent=self, title="Save session", initialdir=SESSIONS_DIR,
                defaultextension=".json", initialfile="session.json",
                filetypes=[("Session", "*.json"), ("All files", "*.*")])
            if not path:
                return None
        try:
            SIO.save(self.session(), self.lib, path)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Save session", str(exc), parent=self)
            return None
        return path

    def cmd_open(self, path: str | None = None):
        if path is None:
            path = filedialog.askopenfilename(
                parent=self, title="Load session", initialdir=SESSIONS_DIR
                if os.path.isdir(SESSIONS_DIR) else None,
                filetypes=[("Session", "*.json"), ("All files", "*.*")])
            if not path:
                return None
        try:
            session, notes = SIO.load(path, self.lib)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Load session", str(exc), parent=self)
            return None
        self.apply_session(session)
        if notes:
            messagebox.showinfo("Load session", "\n".join(notes), parent=self)
        return notes

    # --- pins ----------------------------------------------------------------

    def _pin(self, name, analysis) -> None:
        self.pins.append(C.make_pin(name, analysis))
        self._refresh_pins()

    def _refresh_pins(self) -> None:
        n = len(self.pins)
        self.compare_btn.configure(text=f"Compare pins ({n})",
                                   state=tk.NORMAL if n else tk.DISABLED)

    def _clear_pins(self) -> None:
        self.pins.clear()
        self._refresh_pins()

    def cmd_compare(self):
        if not self.pins:
            return None
        return CompareWindow(self, self.pins, on_clear=self._clear_pins)


if __name__ == "__main__":
    AnalyzerApp().mainloop()
