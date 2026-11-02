"""Option panel: the upgrade sections of one unit, generated from a
UnitConfig (app.unit_config) and shared by the Analyzer and the List
Editor. A thin view: every gesture calls the config and
the whole panel is rebuilt from it, so what is shown is always what
resolve() made of the choices.

Widgets per section mode: radio -> read-only
combobox with "(none)"; check -> one checkbutton per option; count ->
one spinbox per option, bounded by the live limit. Sections whose
targets are absent are greyed. Invalid choices are listed in red with a
"Remove invalid" button (they are never pruned silently).
"""
import tkinter as tk
from tkinter import ttk

from grimdarkoracle.ui import ui_utils as ui

NONE = "(none)"


def option_text(o) -> str:
    """Option label with its price for this unit."""
    if o.cost is None:
        return o.label
    return f"{o.label}  (+{o.cost} pts)" if o.cost else f"{o.label}  (free)"


class OptionPanel(ttk.Frame):
    """on_change(cfg) is called after every change of the choices."""

    def __init__(self, parent, on_change=None, height=260):
        super().__init__(parent)
        self.cfg = None
        self.on_change = on_change
        self.header = ttk.Label(self, text="No unit selected",
                                font=ui.bold_font())
        self.header.pack(anchor=tk.W, padx=4, pady=(2, 0))
        self.issues = ttk.Label(self, text="", foreground=ui.WARN_COLOR,
                                wraplength=420, justify=tk.LEFT)
        self.issues.pack(anchor=tk.W, padx=4)
        self.prune_btn = ui.tip(
            ttk.Button(self, text="Remove invalid choices",
                       command=self.cmd_prune),
            "Drop the choices that no longer apply (e.g. a replacement of a "
            "weapon another choice no longer grants)")
        self.scroll = ui.ScrollableFrame(self, height=height)
        self.scroll.pack(fill=tk.BOTH, expand=True)
        self.widgets: dict = {}         # (package, section, option) -> widget
        self.vars: dict = {}

    # --- public --------------------------------------------------------------

    def set_config(self, cfg) -> None:
        self.cfg = cfg
        self.refresh()

    def refresh(self) -> None:
        body = self.scroll.body
        for w in body.winfo_children():
            w.destroy()
        self.widgets.clear()
        self.vars.clear()
        if self.cfg is None:
            self.header.configure(text="No unit selected")
            self.issues.configure(text="")
            self.prune_btn.pack_forget()
            return
        u = self.cfg.resolved
        self.header.configure(text=f"{u.name}  [{u.size}]  {u.points} pts")
        self.issues.configure(text="\n".join(self.cfg.issues))
        if self.cfg.invalid():
            self.prune_btn.pack(anchor=tk.W, padx=4, pady=2,
                                before=self.scroll)
        else:
            self.prune_btn.pack_forget()
        for sv in self.cfg.sections():
            self._section(body, sv)
        self.scroll.bind_wheel()

    # --- building ------------------------------------------------------------

    def _section(self, body, sv) -> None:
        text = sv.label if sv.enabled else f"{sv.label}  (not available)"
        box = ttk.LabelFrame(body, text=text)
        box.pack(fill=tk.X, padx=4, pady=2)
        state = tk.NORMAL if sv.enabled else tk.DISABLED
        if sv.mode == "radio":
            labels = [NONE] + [option_text(o) for o in sv.options]
            var = tk.StringVar(value=next((option_text(o) for o in sv.options
                                           if o.wanted), NONE))
            cb = ttk.Combobox(box, textvariable=var, values=labels,
                              state="readonly" if sv.enabled else tk.DISABLED,
                              width=48)
            cb.pack(fill=tk.X, padx=4, pady=2)
            cb.bind("<<ComboboxSelected>>",
                    lambda _e, s=sv, v=var: self._radio(s, v.get()))
            self.widgets[(sv.package, sv.uid, None)] = cb
            self.vars[(sv.package, sv.uid, None)] = var
            return
        for o in sv.options:
            key = (sv.package, sv.uid, o.uid)
            if sv.mode == "check":
                var = tk.BooleanVar(value=bool(o.wanted))
                w = ttk.Checkbutton(box, text=option_text(o), variable=var,
                                    state=state, command=lambda k=key, v=var:
                                    self._set(k, int(v.get())))
                w.pack(anchor=tk.W, padx=4)
            else:
                row = ttk.Frame(box)
                row.pack(fill=tk.X, padx=4)
                var = tk.StringVar(value=str(o.wanted))
                w = ttk.Spinbox(row, from_=0, to=max(o.limit, o.wanted),
                                width=4, textvariable=var, state=state,
                                command=lambda k=key, v=var: self._spin(k, v))
                w.pack(side=tk.LEFT)
                w.bind("<Return>", lambda _e, k=key, v=var: self._spin(k, v))
                w.bind("<FocusOut>", lambda _e, k=key, v=var: self._spin(k, v))
                ttk.Label(row, text=option_text(o)).pack(side=tk.LEFT, padx=4)
            if o.applied < o.wanted:
                ttk.Label(box, text=f"  applied {o.applied} of {o.wanted}",
                          foreground=ui.WARN_COLOR).pack(anchor=tk.W, padx=4)
            self.widgets[key] = w
            self.vars[key] = var

    # --- gestures ------------------------------------------------------------

    def _changed(self) -> None:
        self.refresh()
        if self.on_change:
            self.on_change(self.cfg)

    def _radio(self, sv, text: str) -> None:
        opt = next((o.uid for o in sv.options if option_text(o) == text), None)
        if opt == sv.selected:
            return
        self.cfg.select(sv.package, sv.uid, opt)
        self._changed()

    def _set(self, key, n: int) -> None:
        package, section, option = key
        current = next(o.wanted for o in self.cfg.section(package,
                                                          section).options
                       if o.uid == option)
        if n == current:                # FocusOut, unchanged or bad text
            var = self.vars.get(key)
            if isinstance(var, tk.StringVar):
                var.set(str(current))   # show the count actually set
            return
        self.cfg.set_count(package, section, option, n)
        self._changed()

    def _spin(self, key, var) -> None:
        try:
            n = int(var.get())
        except (TypeError, ValueError):
            n = 0
        self._set(key, n)

    def cmd_prune(self) -> None:
        if self.cfg is not None and self.cfg.invalid():
            self.cfg.prune()
            self._changed()
