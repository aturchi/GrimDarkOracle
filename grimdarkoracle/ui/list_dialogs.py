"""Small dialogs of the List Editor: add a unit from a book, add an
override, place the instances of a choice on models. Thin views: each one
returns plain values (book / unit ids, an override dict, model indices)
through on_ok and never edits the list itself. Not modal, so the tests can
drive them (choose / set fields, then cmd_ok).
"""
import tkinter as tk
from tkinter import ttk

from grimdarkoracle.data import overrides as OV
from grimdarkoracle.ui import ui_utils as ui

AUTO = "automatic"


class AddUnitDialog(tk.Toplevel):
    """Book + filtered unit list; on_ok(book_uid, unit_id)."""

    def __init__(self, parent, lib, on_ok, book_uid: str | None = None):
        super().__init__(parent)
        self.title("Add unit")
        self.lib, self.on_ok = lib, on_ok
        self.books = lib.catalogue()
        self.book_var, self.filter_var = tk.StringVar(), tk.StringVar()
        ttk.Label(self, text="Army book").pack(anchor=tk.W, padx=6)
        self.book_box = ttk.Combobox(self, textvariable=self.book_var,
                                     state="readonly", width=40,
                                     values=[self._book_text(b)
                                             for b in self.books])
        self.book_box.pack(fill=tk.X, padx=6)
        self.book_box.bind("<<ComboboxSelected>>", lambda _e: self._fill())
        ttk.Label(self, text="Filter").pack(anchor=tk.W, padx=6)
        f = ttk.Entry(self, textvariable=self.filter_var)
        f.pack(fill=tk.X, padx=6)
        f.bind("<KeyRelease>", lambda _e: self._fill())
        frame, self.listbox = ui.scrollable_listbox(self, height=14, width=50)
        frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)
        self.listbox.bind("<Double-Button-1>", lambda _e: self.cmd_ok())
        row = ttk.Frame(self)
        row.pack(fill=tk.X, padx=6, pady=4)
        ttk.Button(row, text="Add", command=self.cmd_ok).pack(side=tk.RIGHT)
        ttk.Button(row, text="Close", command=self.destroy).pack(
            side=tk.RIGHT, padx=4)
        self.units: list = []
        first = next((b for b in self.books if b.uid == book_uid),
                     self.books[0] if self.books else None)
        if first is not None:
            self.book_var.set(self._book_text(first))
        self._fill()

    def _book_text(self, b) -> str:
        local = "  [local]" if b.uid in self.lib.local else ""
        return f"{b.name} {b.version}{local}"

    def book_uid(self) -> str | None:
        text = self.book_var.get()
        return next((b.uid for b in self.books
                     if self._book_text(b) == text), None)

    def _fill(self) -> None:
        uid, needle = self.book_uid(), self.filter_var.get().lower().strip()
        self.units = [u for u in self.lib.units(uid)
                      if needle in u.name.lower()] if uid else []
        self.listbox.delete(0, tk.END)
        for u in self.units:
            self.listbox.insert(tk.END, f"{u.name} [{u.size}]  {u.cost} pts")

    def choose(self, book_uid: str, unit_name: str) -> None:
        """Select a book and a unit by name (tests, keyboard users)."""
        b = next(b for b in self.books if b.uid == book_uid)
        self.book_var.set(self._book_text(b))
        self.filter_var.set("")
        self._fill()
        i = [u.name for u in self.units].index(unit_name)
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(i)

    def cmd_ok(self) -> None:
        sel = self.listbox.curselection()
        if sel:
            self.on_ok(self.book_uid(), self.units[sel[0]].id)


class OverrideDialog(tk.Toplevel):
    """Build one override (data.overrides) for a resolved unit; on_ok(dict).
    Rules to add are picked by name from the registry definitions."""

    OPS = {"Set a value": "set", "Add a rule": "add_rule",
           "Remove a rule": "remove_rule", "Set a weapon value": "weapon_set",
           "Add a rule to a weapon": "weapon_add_rule",
           "Remove a rule from a weapon": "weapon_remove_rule"}

    def __init__(self, parent, unit, reg, on_ok):
        super().__init__(parent)
        self.title(f"Override - {unit.name}")
        self.unit, self.reg, self.on_ok = unit, reg, on_ok
        self.rule_ids = {}
        for d in reg.defs.values():
            self.rule_ids.setdefault(d.name, d.id)
        self.v = {k: tk.StringVar() for k in ("op", "what", "weapon", "rule",
                                               "value")}
        grid = ttk.Frame(self)
        grid.pack(fill=tk.X, padx=6, pady=6)
        self.boxes = {}
        for r, (key, text) in enumerate((("op", "Change"), ("what", "Field"),
                                         ("weapon", "Weapon"),
                                         ("rule", "Rule"),
                                         ("value", "Value / rating"))):
            ttk.Label(grid, text=text).grid(row=r, column=0, sticky=tk.W)
            w = ttk.Entry(grid, textvariable=self.v[key], width=34) \
                if key == "value" else ttk.Combobox(
                    grid, textvariable=self.v[key], width=32)
            w.grid(row=r, column=1, sticky="ew", pady=1)
            self.boxes[key] = w
        self.boxes["op"].configure(values=list(self.OPS), state="readonly")
        self.boxes["op"].bind("<<ComboboxSelected>>", lambda _e: self._op())
        self.boxes["weapon"].configure(
            values=sorted({w.name for w, _n in unit.weapons()}))
        row = ttk.Frame(self)
        row.pack(fill=tk.X, padx=6, pady=4)
        ttk.Button(row, text="Add", command=self.cmd_ok).pack(side=tk.RIGHT)
        ttk.Button(row, text="Close", command=self.destroy).pack(
            side=tk.RIGHT, padx=4)
        self.v["op"].set(next(iter(self.OPS)))
        self._op()

    def _op(self) -> None:
        op = self.OPS.get(self.v["op"].get(), "set")
        what = OV.SET_PATHS if op == "set" else \
            OV.WEAPON_FIELDS if op == "weapon_set" else ()
        self.boxes["what"].configure(values=list(what))
        if what and self.v["what"].get() not in what:
            self.v["what"].set(what[0])
        unit_rules = sorted({r.name for m in self.unit.models for r in m.rules})
        self.boxes["rule"].configure(
            values=unit_rules if op == "remove_rule" else
            sorted(self.rule_ids))

    def build(self) -> dict:
        """The override as data.overrides reads it (ValueError if a field
        is missing)."""
        op = self.OPS[self.v["op"].get()]
        val, rule = self.v["value"].get().strip(), self.v["rule"].get().strip()
        weapon = self.v["weapon"].get().strip()

        def num(s):
            return int(s) if s.lstrip("-").isdigit() else s

        def ref():
            if rule not in self.rule_ids:
                raise ValueError(f"unknown rule {rule!r}")
            d = {"id": self.rule_ids[rule], "name": rule}
            if val:
                d["rating"] = num(val)
            return d
        need = {"set": (val,), "add_rule": (rule,), "remove_rule": (rule,),
                "weapon_set": (weapon, val), "weapon_add_rule": (weapon, rule),
                "weapon_remove_rule": (weapon, rule)}[op]
        if not all(need):
            raise ValueError("fill in the fields of this change")
        if op == "set":
            path = self.v["what"].get()
            return {"op": op, "path": path,
                    "value": val if path == "name" else num(val)}
        if op == "add_rule":
            return {"op": op, "rule": ref()}
        if op == "remove_rule":
            return {"op": op, "name": rule}
        if op == "weapon_set":
            return {"op": op, "weapon": weapon, "field": self.v["what"].get(),
                    "value": num(val)}
        if op == "weapon_add_rule":
            return {"op": op, "weapon": weapon, "rule": ref()}
        return {"op": op, "weapon": weapon, "name": rule}

    def cmd_ok(self) -> None:
        self.on_ok(self.build())


class PlacementDialog(tk.Toplevel):
    """Model of each instance of one choice; on_ok(models) with None for
    automatic. 'candidates(picks)' gives, per instance, the models able to
    take it (resolve.placement_candidates): only those are
    offered, and the lists are recomputed after every pick. A saved pick
    that is not allowed any more is shown with a warning (resolve places
    that instance automatically)."""

    def __init__(self, parent, title: str, count: int, size: int, models,
                 on_ok, candidates=None):
        super().__init__(parent)
        self.title(f"Placement - {title}")
        self.on_ok, self.size = on_ok, size
        self.candidates = candidates or (lambda _p: [tuple(range(size))]
                                         * count)
        models = list(models or []) + [None] * count
        self.vars, self.boxes, self.notes = [], [], []
        for n in range(count):
            row = ttk.Frame(self)
            row.pack(fill=tk.X, padx=6, pady=1)
            ttk.Label(row, text=f"Instance {n + 1}").pack(side=tk.LEFT)
            m = models[n]
            v = tk.StringVar(value=AUTO if m is None or m >= size
                             else f"model {m + 1}")
            cb = ttk.Combobox(row, textvariable=v, state="readonly", width=14)
            cb.pack(side=tk.LEFT, padx=4)
            cb.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
            note = ttk.Label(row, text="", foreground=ui.WARN_COLOR)
            note.pack(side=tk.LEFT)
            self.vars.append(v)
            self.boxes.append(cb)
            self.notes.append(note)
        ttk.Label(self, text="Only the models able to take the upgrade at "
                  "that point are offered (weapons held, upgrades already "
                  "placed).", foreground=ui.HINT_COLOR, wraplength=320).pack(
            padx=6)
        row = ttk.Frame(self)
        row.pack(fill=tk.X, padx=6, pady=4)
        ttk.Button(row, text="Apply", command=self.cmd_ok).pack(side=tk.RIGHT)
        ttk.Button(row, text="Close", command=self.destroy).pack(
            side=tk.RIGHT, padx=4)
        self.refresh()

    def models(self) -> list:
        return [None if v.get() == AUTO else int(v.get().split()[1]) - 1
                for v in self.vars]

    def allowed(self) -> list:
        """Per instance, the model indices offered now."""
        cands = self.candidates(self.models())
        return [tuple(c) for c in cands] if cands is not None else \
            [()] * len(self.vars)

    def refresh(self) -> None:
        picks = self.models()
        for n, (cb, note, ok) in enumerate(zip(self.boxes, self.notes,
                                               self.allowed())):
            cb.configure(values=[AUTO] + [f"model {i + 1}" for i in ok])
            bad = picks[n] is not None and picks[n] not in ok
            note.configure(text="cannot take it: placed automatically"
                           if bad else "")

    def cmd_ok(self) -> None:
        self.on_ok(self.models())
        self.destroy()
