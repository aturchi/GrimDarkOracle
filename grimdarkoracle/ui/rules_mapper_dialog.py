"""Rules Mapper dialog: the semantics of one custom rule of a local book,
built from the primitives and conditions of rules/vocab. A thin view over
rules.mapper: the effects are kept as plain dicts, the preview is
mapper.describe, the checks mapper.check; Save stores them in the book
(local_books.set_semantics) and makes them live (Library.put_local).

Conditions are typed as text: 'attack=shooting, range_over=12, charging'
(a bare key means yes; has_rule takes a rule name).

Kind "behaves as": the rule copies an existing native rule
(handler, parameters, effects) with its own name and rating; the effects
and conditions are then the native rule's and cannot be edited.
"""
import tkinter as tk
from tkinter import messagebox, ttk

from grimdarkoracle.data import local_books as LB
from grimdarkoracle.rules import mapper as MP
from grimdarkoracle.rules import vocab as V
from grimdarkoracle.ui import ui_utils as ui

DEFAULT_SCOPE = "(default)"


class RulesMapperDialog(tk.Toplevel):
    def __init__(self, parent, lib, raw: dict, rule_id: str, on_saved=None):
        super().__init__(parent)
        self.lib, self.raw, self.rule_id = lib, raw, rule_id
        self.on_saved = on_saved
        rule = LB.find_rule(raw, rule_id)
        self.title(f"Rules Mapper - {rule['name']}")
        old = rule.get(LB.SEM_KEY) or {}
        native = str(old.get("impl", "")).startswith(V.NATIVE_PREFIX)
        self.natives = MP.natives(lib.reg)
        self.effects = [] if native else \
            [dict(e) for e in old.get("effects", [])]
        ttk.Label(self, text=rule["name"], font=ui.bold_font()).pack(
            anchor=tk.W, padx=6)
        ttk.Label(self, text=rule["description"], wraplength=520,
                  foreground=ui.HINT_COLOR).pack(anchor=tk.W, padx=6)
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=6, pady=4)
        self.impl = tk.StringVar(value=MP.NATIVE if native else
                                 old.get("impl", "composed"))
        self.conds = tk.StringVar(value="" if native else MP.conditions_text(
            old.get("conditions", {}), lib.reg))
        as_sem = lib.reg.entries.get(old.get(MP.AS_KEY)) if native else None
        self.as_name = tk.StringVar(value=as_sem.name if as_sem else "")
        ttk.Label(top, text="Kind").grid(row=0, column=0, sticky=tk.W)
        cb = ttk.Combobox(top, textvariable=self.impl,
                          values=MP.IMPLS + (MP.NATIVE,), state="readonly",
                          width=20)
        cb.grid(row=0, column=1, sticky=tk.W)
        cb.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
        self.as_box = ui.tip(ttk.Combobox(
            top, textvariable=self.as_name, values=list(self.natives),
            state="readonly", width=28), "The engine rule this one copies "
            "(handler and numbers); its own name and rating stay")
        self.as_box.grid(row=0, column=2, sticky=tk.W, padx=4)
        self.as_box.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
        ttk.Label(top, text="When (all effects)").grid(row=1, column=0,
                                                       sticky=tk.W)
        e = ttk.Entry(top, textvariable=self.conds, width=56)
        e.grid(row=1, column=1, sticky="ew")
        e.bind("<KeyRelease>", lambda _e: self.refresh())
        top.columnconfigure(1, weight=1)
        box = ttk.LabelFrame(self, text="Effects")
        box.pack(fill=tk.BOTH, expand=True, padx=6)
        self.listbox = tk.Listbox(box, height=6, exportselection=False)
        self.listbox.pack(fill=tk.BOTH, expand=True, padx=4, pady=2)
        form = ttk.Frame(box)
        form.pack(fill=tk.X, padx=4)
        self.v = {"primitive": tk.StringVar(value="hit_mod"),
                  "value": tk.StringVar(value="1"),
                  "side": tk.StringVar(value="attacker"),
                  "scope": tk.StringVar(value=DEFAULT_SCOPE),
                  "conds": tk.StringVar()}
        for c, (key, values, w) in enumerate((
                ("primitive", sorted(V.PRIMITIVES), 20), ("value", None, 10),
                ("side", V.SIDES, 9), ("scope", (DEFAULT_SCOPE,) + V.SCOPES,
                                       10), ("conds", None, 26))):
            ttk.Label(form, text=key if key != "conds" else "only if").grid(
                row=0, column=c, sticky=tk.W)
            wdg = ttk.Entry(form, textvariable=self.v[key], width=w) \
                if values is None else ttk.Combobox(
                    form, textvariable=self.v[key], values=list(values),
                    state="readonly", width=w)
            wdg.grid(row=1, column=c, padx=1)
        ttk.Label(box, text="Value: a number or X (the rating); yes / no; a "
                  "rule name for grant_rule.", foreground=ui.HINT_COLOR).pack(
            anchor=tk.W, padx=4)
        row = ttk.Frame(box)
        row.pack(fill=tk.X, padx=4, pady=2)
        ttk.Button(row, text="Add effect", command=self.cmd_add).pack(
            side=tk.LEFT)
        ttk.Button(row, text="Remove effect", command=self.cmd_remove).pack(
            side=tk.LEFT, padx=4)
        self.preview = ttk.Label(self, text="", justify=tk.LEFT,
                                 wraplength=520)
        self.preview.pack(anchor=tk.W, padx=6, pady=2)
        self.errors = ttk.Label(self, text="", foreground=ui.WARN_COLOR,
                                justify=tk.LEFT, wraplength=520)
        self.errors.pack(anchor=tk.W, padx=6)
        row = ttk.Frame(self)
        row.pack(fill=tk.X, padx=6, pady=4)
        ttk.Button(row, text="Save", command=self.cmd_save).pack(side=tk.RIGHT)
        ttk.Button(row, text="No semantics", command=self.cmd_clear).pack(
            side=tk.RIGHT, padx=4)
        ttk.Button(row, text="Close", command=self.destroy).pack(
            side=tk.RIGHT)
        self.refresh()

    # --- model ---------------------------------------------------------------------

    def entry(self) -> tuple[dict, list[str]]:
        """(semantics entry, errors) of the dialog as it stands."""
        if self.impl.get() == MP.NATIVE:
            as_id = self.natives.get(self.as_name.get())
            if as_id is None:
                return {"impl": "native:"}, ["pick the rule it behaves as"]
            e = MP.native_entry(self.lib.reg, as_id)
            return e, MP.check(e, self.lib.reg, self.rule_id)
        conds, errors = MP.parse_conditions(self.conds.get(), self.lib.reg)
        effects = [] if self.impl.get() == "no_combat_effect" else self.effects
        e = MP.entry(self.impl.get(), effects, conds)
        return e, errors + MP.check(e, self.lib.reg, self.rule_id)

    def refresh(self) -> None:
        reg = self.lib.reg
        self.listbox.delete(0, tk.END)
        for x in self.effects:
            text = f"{x['primitive']} {MP.value_text(x['primitive'], x['value'], reg)}" \
                f"  [{x.get('side', 'attacker')}, {x.get('scope') or 'default'}]"
            if x.get("conditions"):
                text += "  if " + MP.conditions_text(x["conditions"], reg)
            self.listbox.insert(tk.END, text)
        native = self.impl.get() == MP.NATIVE
        self.as_box.configure(state="readonly" if native else tk.DISABLED)
        e, errors = self.entry()
        self.preview.configure(text="\n".join(
            MP.describe(e, reg) if e.get("impl") != "native:" else []))
        self.errors.configure(text="\n".join(errors))

    # --- gestures ------------------------------------------------------------------

    def cmd_add(self) -> bool:
        reg, prim = self.lib.reg, self.v["primitive"].get()
        value, err = MP.parse_value(prim, self.v["value"].get(), reg)
        conds, errs = MP.parse_conditions(self.v["conds"].get(), reg)
        errs = ([err] if err else []) + errs
        if errs:
            self.errors.configure(text="\n".join(errs))
            return False
        scope = self.v["scope"].get()
        self.effects.append(MP.effect(prim, value, self.v["side"].get(),
                                      None if scope == DEFAULT_SCOPE
                                      else scope, conds))
        self.refresh()
        return True

    def cmd_remove(self) -> None:
        sel = self.listbox.curselection()
        if sel:
            del self.effects[sel[0]]
            self.refresh()

    def _store(self) -> None:
        self.lib.put_local(self.raw)
        if self.on_saved:
            self.on_saved()

    def cmd_save(self) -> bool:
        e, errors = self.entry()
        if errors:
            messagebox.showerror("Rules Mapper", "\n".join(errors),
                                 parent=self)
            return False
        LB.set_semantics(self.raw, self.rule_id, e)
        self._store()
        self.destroy()
        return True

    def cmd_clear(self) -> None:
        LB.clear_semantics(self.raw, self.rule_id)
        self._store()
        self.destroy()
