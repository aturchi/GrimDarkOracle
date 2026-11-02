"""Variants dialog: one variant per option of a section of one side's
unit, analysed with the current setup and shown in a CompareWindow
(app.variants). The other side and the setup are fixed.
"""
import tkinter as tk
from tkinter import messagebox, ttk

from grimdarkoracle.app import variants as V
from grimdarkoracle.app.side_spec import SideSpec
from grimdarkoracle.ui import ui_utils as ui
from grimdarkoracle.ui.result_window import CompareWindow


class VariantsDialog(tk.Toplevel):
    """sides: {role: SidePicker}; run_with(role, SideSpec) -> Analysis."""

    def __init__(self, parent, sides: dict, run_with):
        super().__init__(parent)
        self.title("Compare upgrade variants")
        self.sides, self.run_with = sides, run_with
        self.role = tk.StringVar()
        self.section = tk.StringVar()
        self.include_none = tk.BooleanVar(value=True)
        self.choices: list = []         # (package, uid) per section label
        roles = [r for r, p in sides.items() if p.spec is not None]
        ttk.Label(self, text="Side").grid(row=0, column=0, sticky=tk.W,
                                          padx=6, pady=3)
        rb = ttk.Combobox(self, textvariable=self.role, values=roles,
                          state="readonly", width=12)
        rb.grid(row=0, column=1, sticky=tk.W, padx=6)
        rb.bind("<<ComboboxSelected>>", lambda _e: self._fill())
        ttk.Label(self, text="Section").grid(row=1, column=0, sticky=tk.W,
                                             padx=6, pady=3)
        self.sec_box = ttk.Combobox(self, textvariable=self.section,
                                    state="readonly", width=56)
        self.sec_box.grid(row=1, column=1, sticky=tk.W, padx=6)
        ui.tip(ttk.Checkbutton(self, text="Include the unit without this "
                               "section", variable=self.include_none),
               "Adds a '(none)' variant: the unit with no option of the "
               "section").grid(row=2, column=1, sticky=tk.W, padx=6)
        row = ttk.Frame(self)
        row.grid(row=3, column=0, columnspan=2, pady=6)
        ttk.Button(row, text="Compare", command=self.cmd_run).pack(
            side=tk.LEFT, padx=4)
        ttk.Button(row, text="Close", command=self.destroy).pack(
            side=tk.LEFT, padx=4)
        if roles:
            self.role.set(roles[0])
            self._fill()

    def _spec(self) -> SideSpec | None:
        p = self.sides.get(self.role.get())
        return p.spec if p else None

    def _fill(self):
        spec = self._spec()
        secs = [] if spec is None else [s for s in spec.unit.cfg.sections()
                                        if s.enabled]
        self.choices = [(s.package, s.uid) for s in secs]
        labels = [f"{s.label} ({len(s.options)} options)" for s in secs]
        self.sec_box.configure(values=labels)
        self.section.set(labels[0] if labels else "")

    def compute(self) -> list[dict]:
        """Pins of the variants of the chosen section (tests call this)."""
        spec = self._spec()
        labels = list(self.sec_box.cget("values"))
        if spec is None or self.section.get() not in labels:
            return []
        package, uid = self.choices[labels.index(self.section.get())]
        cfg = spec.unit.cfg
        vs = V.section_variants(cfg.book, cfg.unit.id, cfg.choices, package,
                                uid, self.include_none.get())
        role = self.role.get()
        return V.compare(vs, lambda v: self.run_with(
            role, SideSpec(spec.unit.with_choices(v.choices), spec.hero)))

    def cmd_run(self):
        try:
            pins = self.compute()
        except ValueError as exc:
            messagebox.showerror("Variants", str(exc), parent=self)
            return None
        if not pins:
            return None
        return CompareWindow(self.master, pins,
                             title=f"Variants of {self.section.get()}")
