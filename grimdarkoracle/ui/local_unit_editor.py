"""Local unit editor: home-made units in local books (books_local/),
their custom rules (with an alias, or semantics from the Rules Mapper) and
their upgrade sections. A thin view over app.local_editor (text forms in
Army Forge label syntax) and data.local_books; every save goes through
Library.put_local, so the List Editor and the Analyzer see it at once.
"""
import copy
import tkinter as tk
from tkinter import messagebox, ttk

from grimdarkoracle.app import local_editor as LE
from grimdarkoracle.data import local_books as LB
from grimdarkoracle.data.resolve import resolve
from grimdarkoracle.ui import ui_utils as ui
from grimdarkoracle.ui.rules_mapper_dialog import RulesMapperDialog

NO_ALIAS = "(no alias)"
FIELDS = (("name", "Name", 28), ("size", "Models", 5), ("quality", "Quality",
          4), ("defense", "Defense", 4), ("cost", "Points", 6))


class LocalUnitEditor(tk.Toplevel):
    def __init__(self, parent, lib, on_saved=None):
        super().__init__(parent)
        self.title("Local units")
        self.lib, self.on_saved = lib, on_saved
        self.raw: dict | None = None
        self.draft: LE.UnitDraft | None = None
        self._build()
        self._fill_books()

    # --- building --------------------------------------------------------------------

    def _build(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=6, pady=4)
        self.book_var, self.new_book_var = tk.StringVar(), tk.StringVar()
        ttk.Label(top, text="Local book").pack(side=tk.LEFT)
        self.book_box = ttk.Combobox(top, textvariable=self.book_var,
                                     state="readonly", width=28)
        self.book_box.pack(side=tk.LEFT, padx=4)
        self.book_box.bind("<<ComboboxSelected>>", lambda _e: self._book())
        ttk.Entry(top, textvariable=self.new_book_var, width=20).pack(
            side=tk.LEFT, padx=(12, 2))
        ttk.Button(top, text="New book", command=self.cmd_new_book).pack(
            side=tk.LEFT)
        ttk.Button(top, text="Delete book", command=self.cmd_delete_book).pack(
            side=tk.LEFT, padx=4)
        body = ttk.Frame(self)
        body.pack(fill=tk.BOTH, expand=True, padx=6)
        left = ttk.Frame(body)
        left.pack(side=tk.LEFT, fill=tk.Y)
        ttk.Label(left, text="Units").pack(anchor=tk.W)
        self.units = tk.Listbox(left, height=10, exportselection=False)
        self.units.pack(fill=tk.X)
        self.units.bind("<<ListboxSelect>>", lambda _e: self._unit())
        row = ttk.Frame(left)
        row.pack(fill=tk.X)
        ttk.Button(row, text="New unit", command=self.cmd_new_unit).pack(
            side=tk.LEFT)
        ttk.Button(row, text="Delete unit", command=self.cmd_delete_unit).pack(
            side=tk.LEFT, padx=4)
        self._rules_box(left)
        self._unit_form(body)

    def _rules_box(self, parent) -> None:
        box = ttk.LabelFrame(parent, text="Custom rules")
        box.pack(fill=tk.X, pady=6)
        self.rules = tk.Listbox(box, height=6, exportselection=False)
        self.rules.pack(fill=tk.X, padx=2)
        self.rules.bind("<<ListboxSelect>>", lambda _e: self._rule())
        self.rv = {k: tk.StringVar() for k in ("name", "text", "alias")}
        for r, (k, t) in enumerate((("name", "Name"), ("text", "Text"),
                                    ("alias", "Same as"))):
            ttk.Label(box, text=t).pack(anchor=tk.W, padx=2)
            w = ttk.Entry(box, textvariable=self.rv[k], width=34) \
                if k != "alias" else ttk.Combobox(
                    box, textvariable=self.rv[k], width=32, values=[NO_ALIAS]
                    + sorted({d.name for d in self.lib.reg.defs.values()}))
            w.pack(fill=tk.X, padx=2)
        row = ttk.Frame(box)
        row.pack(fill=tk.X, padx=2, pady=2)
        for text, fn in (("New", self.cmd_new_rule), ("Save", self.cmd_save_rule),
                         ("Effects...", self.cmd_map), ("Delete",
                                                       self.cmd_delete_rule)):
            ttk.Button(row, text=text, command=fn).pack(side=tk.LEFT, padx=1)

    def _unit_form(self, parent) -> None:
        right = ttk.Frame(parent)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0))
        row = ttk.Frame(right)
        row.pack(fill=tk.X)
        self.uv = {k: tk.StringVar() for k, _t, _w in FIELDS}
        self.uv["rules"] = tk.StringVar()
        for k, text, w in FIELDS:
            ttk.Label(row, text=text).pack(side=tk.LEFT)
            ttk.Entry(row, textvariable=self.uv[k], width=w).pack(
                side=tk.LEFT, padx=(1, 6))
        ttk.Label(right, text="Rules (comma separated, e.g. Fearless, "
                  "Tough(3))").pack(anchor=tk.W)
        ttk.Entry(right, textvariable=self.uv["rules"]).pack(fill=tk.X)
        ttk.Label(right, text='Weapons, one per line as on Army Forge: '
                  '5x Rifle (24", A1, AP(1)) - without "Nx" every model has '
                  'one').pack(anchor=tk.W)
        self.weapons = tk.Text(right, height=6, width=70)
        self.weapons.pack(fill=tk.X)
        ttk.Label(right, text="Upgrade sections").pack(anchor=tk.W, pady=(4, 0))
        self.sections = tk.Listbox(right, height=5, exportselection=False)
        self.sections.pack(fill=tk.X)
        row = ttk.Frame(right)
        row.pack(fill=tk.X)
        for text, fn in (("Add section...", self.cmd_add_section),
                         ("Edit section...", self.cmd_edit_section),
                         ("Remove section", self.cmd_remove_section)):
            ttk.Button(row, text=text, command=fn).pack(side=tk.LEFT, padx=1)
        ttk.Button(right, text="Save unit", command=self.cmd_save_unit).pack(
            anchor=tk.E, pady=4)
        self.errors = ttk.Label(right, text="", foreground=ui.WARN_COLOR,
                                justify=tk.LEFT, wraplength=560)
        self.errors.pack(anchor=tk.W)
        self.preview = ttk.Label(right, text="", justify=tk.LEFT,
                                 wraplength=560)
        self.preview.pack(anchor=tk.W)

    # --- showing ---------------------------------------------------------------------

    def _fill_books(self, uid: str | None = None) -> None:
        books = sorted((self.lib.books[u] for u in self.lib.local),
                       key=lambda b: b.name.lower())
        self._uids = [b.uid for b in books]
        self.book_box.configure(values=[b.name for b in books])
        if uid is None and self._uids:
            uid = self._uids[0]
        self.book_var.set(self.lib.books[uid].name if uid else "")
        self._book()

    def _book(self) -> None:
        names = list(self.book_box.cget("values"))
        name = self.book_var.get()
        uid = self._uids[names.index(name)] if name in names else None
        self.raw = copy.deepcopy(self.lib.raw_book(self.lib.books[uid])) \
            if uid else None
        self._fill_units()
        self._fill_rules()
        self.show_unit(None)

    def _fill_units(self, select: str | None = None) -> None:
        self.units.delete(0, tk.END)
        for u in (self.raw or {}).get("units", []):
            self.units.insert(tk.END, f"{u['name']} [{u['size']}]  "
                                      f"{u['cost']} pts")
        ids = [u["id"] for u in (self.raw or {}).get("units", [])]
        if select in ids:
            self.units.selection_set(ids.index(select))

    def _fill_rules(self) -> None:
        keep = self._rule_id() if self.raw else None
        self.rules.delete(0, tk.END)
        rules = LB.rules_of(self.raw) if self.raw else []
        ids = [r["id"] for r in rules]
        for r in rules:
            st = self.lib.reg.status(r["id"], r["name"])
            self.rules.insert(tk.END, f"{r['name']}  [{st}]")
        if keep in ids:                     # the selection survives a save
            self.rules.selection_set(ids.index(keep))

    def show_unit(self, unit_id: str | None) -> None:
        self.draft = LE.UnitDraft.from_raw(self.raw, unit_id) if unit_id \
            else LE.UnitDraft()
        d = self.draft
        for k, _t, _w in FIELDS:
            self.uv[k].set(str(getattr(d, k)))
        self.uv["rules"].set(d.rules)
        self.weapons.delete("1.0", tk.END)
        self.weapons.insert("1.0", d.weapons)
        self._fill_sections()
        self.errors.configure(text="")
        self._preview()

    def _fill_sections(self) -> None:
        self.sections.delete(0, tk.END)
        for s in self.draft.sections:
            n = len(s.options)
            self.sections.insert(tk.END, f"{s.label}  ({s.variant}, {n} "
                                         f"option{'' if n == 1 else 's'})")

    def _preview(self) -> None:
        d = self.draft
        if not (self.raw and d.uid):
            self.preview.configure(text="")
            return
        ru = resolve(self.lib.books[self.raw["uid"]], d.uid)
        ws = ", ".join(f"{n}x {w.name}" for w, n in ru.weapons())
        self.preview.configure(text=f"As saved: {ru.name} [{ru.size}] "
                                    f"Q{ru.quality}+ D{ru.defense}+ "
                                    f"{ru.points} pts - {ws}")

    # --- units -----------------------------------------------------------------------

    def _form(self) -> LE.UnitDraft | None:
        d = self.draft
        try:
            for k in ("size", "quality", "defense", "cost"):
                setattr(d, k, int(self.uv[k].get()))
        except ValueError:
            self.errors.configure(text="models, quality, defense and points "
                                       "must be whole numbers")
            return None
        d.name, d.rules = self.uv["name"].get(), self.uv["rules"].get()
        d.weapons = self.weapons.get("1.0", tk.END).strip()
        return d

    def _unit(self) -> None:
        sel = self.units.curselection()
        if sel and self.raw:
            self.show_unit(self.raw["units"][sel[0]]["id"])

    def cmd_new_unit(self) -> None:
        self.units.selection_clear(0, tk.END)
        self.show_unit(None)

    def cmd_save_unit(self) -> bool:
        if self.raw is None:
            self.errors.configure(text="create a local book first")
            return False
        d = self._form()
        if d is None:
            return False
        raw = copy.deepcopy(self.raw)
        uid, errors = LE.save_unit(raw, d, LE.RuleResolver(self.lib.reg, raw))
        if errors:
            self.errors.configure(text="\n".join(errors))
            return False
        self._commit(raw)
        self._fill_units(uid)
        self.show_unit(uid)
        return True

    def cmd_delete_unit(self) -> None:
        sel = self.units.curselection()
        if not (sel and self.raw) or not messagebox.askyesno(
                "Local units", "Delete this unit? Lists using it will show "
                "it as missing.", parent=self):
            return
        raw = copy.deepcopy(self.raw)
        LB.remove_unit(raw, raw["units"][sel[0]]["id"])
        self._commit(raw)
        self._fill_units()
        self.show_unit(None)

    def _commit(self, raw) -> None:
        self.lib.put_local(raw)
        self.raw = copy.deepcopy(raw)
        self._fill_rules()
        if self.on_saved:
            self.on_saved()

    # --- sections --------------------------------------------------------------------

    def cmd_add_section(self):
        return SectionDialog(self, LE.SectionDraft("Upgrade with one",
                                                   select="1"),
                             lambda s: self._section(None, s))

    def cmd_edit_section(self):
        sel = self.sections.curselection()
        if not sel:
            return None
        i = sel[0]
        return SectionDialog(self, copy.deepcopy(self.draft.sections[i]),
                             lambda s, i=i: self._section(i, s))

    def _section(self, i, s) -> None:
        if i is None:
            self.draft.sections.append(s)
        else:
            self.draft.sections[i] = s
        self._fill_sections()

    def cmd_remove_section(self) -> None:
        sel = self.sections.curselection()
        if sel:
            del self.draft.sections[sel[0]]
            self._fill_sections()

    # --- books and rules -------------------------------------------------------------

    def cmd_new_book(self) -> bool:
        name = self.new_book_var.get().strip()
        if not name:
            self.errors.configure(text="type the name of the new book")
            return False
        raw = LB.new_book(name)
        if raw["uid"] in self.lib.books:
            self.errors.configure(text=f"{raw['uid']} exists already")
            return False
        self.lib.put_local(raw)
        self.new_book_var.set("")
        self._fill_books(raw["uid"])
        if self.on_saved:
            self.on_saved()
        return True

    def cmd_delete_book(self) -> None:
        if self.raw and messagebox.askyesno(
                "Local units", f"Delete the book {self.raw['name']} and all "
                "its units?", parent=self):
            self.lib.drop_local(self.raw["uid"])
            self._fill_books()
            if self.on_saved:
                self.on_saved()

    def _rule_id(self) -> str | None:
        sel = self.rules.curselection()
        return LB.rules_of(self.raw)[sel[0]]["id"] if sel and self.raw \
            else None

    def _rule(self) -> None:
        rid = self._rule_id()
        if rid is None:
            return
        r = LB.find_rule(self.raw, rid)
        alias = self.lib.reg.defs.get(LB.alias_of(r) or "")
        self.rv["name"].set(r["name"])
        self.rv["text"].set(r["description"])
        self.rv["alias"].set(alias.name if alias else NO_ALIAS)

    def _alias_id(self) -> str | None:
        name = self.rv["alias"].get()
        if name in ("", NO_ALIAS):
            return None
        hit = LE.RuleResolver(self.lib.reg, {}).find(name)
        return hit[0] if hit else None

    def cmd_new_rule(self) -> None:
        self.rules.selection_clear(0, tk.END)
        for v in self.rv.values():
            v.set("")
        self.rv["alias"].set(NO_ALIAS)

    def cmd_save_rule(self) -> bool:
        name, text = self.rv["name"].get().strip(), self.rv["text"].get()
        if self.raw is None or not name:
            self.errors.configure(text="a local book and a rule name are "
                                       "needed")
            return False
        raw, rid = copy.deepcopy(self.raw), self._rule_id()
        if rid is None:
            LB.custom_rule(raw, name, text, self._alias_id())
        else:
            LB.edit_rule(raw, rid, text, self._alias_id())
            if LB.find_rule(raw, rid)["name"] != name:
                LB.rename_rule(raw, rid, name)
        self._commit(raw)
        return True

    def cmd_delete_rule(self) -> None:
        rid = self._rule_id()
        if rid is None:
            return
        raw = copy.deepcopy(self.raw)
        try:
            LB.delete_rule(raw, rid)
        except LB.LocalBookError as exc:
            messagebox.showerror("Local units", f"{exc}.", parent=self)
            return
        self._commit(raw)

    def cmd_map(self):
        rid = self._rule_id()
        if rid is None:
            return None
        if LB.alias_of(LB.find_rule(self.raw, rid)):
            messagebox.showinfo("Rules Mapper", "This rule behaves as its "
                                "alias; remove the alias to give it effects "
                                "of its own.", parent=self)
            return None
        raw = copy.deepcopy(self.raw)

        def saved():
            self.raw = copy.deepcopy(raw)
            self._fill_rules()
            if self.on_saved:
                self.on_saved()
        return RulesMapperDialog(self, self.lib, raw, rid, saved)


class SectionDialog(tk.Toplevel):
    """One upgrade section; options one per line: 'points | gains'."""

    def __init__(self, parent, sd: LE.SectionDraft, on_ok):
        super().__init__(parent)
        self.title("Upgrade section")
        self.sd, self.on_ok = sd, on_ok
        self.v = {"label": tk.StringVar(value=sd.label),
                  "variant": tk.StringVar(value=sd.variant),
                  "targets": tk.StringVar(value=sd.targets),
                  "affects": tk.StringVar(value=sd.affects),
                  "select": tk.StringVar(value=sd.select)}
        self.model = tk.BooleanVar(value=sd.model)
        grid = ttk.Frame(self)
        grid.pack(fill=tk.X, padx=6, pady=4)
        for r, (k, text) in enumerate((
                ("label", "Label (as Army Forge: Replace one Rifle)"),
                ("variant", "Kind"), ("targets", "Targets (weapons replaced "
                                      "or extended)"),
                ("affects", "Models / instances (1, up to 2, any, all)"),
                ("select", "Options to pick (1, up to 2, any)"))):
            ttk.Label(grid, text=text).grid(row=r, column=0, sticky=tk.W)
            w = ttk.Combobox(grid, textvariable=self.v[k], state="readonly",
                             values=["upgrade", "replace", "attachment"]) \
                if k == "variant" else ttk.Entry(grid, textvariable=self.v[k],
                                                 width=40)
            w.grid(row=r, column=1, sticky="ew")
        ttk.Checkbutton(grid, text="Per model (one model / any model / all "
                        "models)", variable=self.model).grid(
            row=5, column=0, columnspan=2, sticky=tk.W)
        ttk.Label(self, text='Options, one per line:  points | gains   e.g.  '
                  '10 | Plasma Gun (24", A1, AP(4)); Tough(3)').pack(
            anchor=tk.W, padx=6)
        self.options = tk.Text(self, height=6, width=70)
        self.options.pack(fill=tk.BOTH, padx=6)
        self.options.insert("1.0", "\n".join(f"{o.cost} | {o.gains}"
                                             for o in sd.options))
        self.errors = ttk.Label(self, text="", foreground=ui.WARN_COLOR)
        self.errors.pack(anchor=tk.W, padx=6)
        row = ttk.Frame(self)
        row.pack(fill=tk.X, padx=6, pady=4)
        ttk.Button(row, text="OK", command=self.cmd_ok).pack(side=tk.RIGHT)
        ttk.Button(row, text="Cancel", command=self.destroy).pack(
            side=tk.RIGHT, padx=4)

    def draft(self) -> LE.SectionDraft:
        """The section; options keep the uids of the lines they replace."""
        opts = []
        lines = [x for x in self.options.get("1.0", tk.END).splitlines()
                 if x.strip()]
        for n, line in enumerate(lines):
            cost, _, gains = line.partition("|")
            uid = self.sd.options[n].uid if n < len(self.sd.options) else ""
            opts.append(LE.OptionDraft(gains.strip(), int(cost.strip()), uid))
        return LE.SectionDraft(self.v["label"].get().strip(),
                               self.v["variant"].get(), self.v["targets"].get(),
                               bool(self.model.get()), self.v["affects"].get(),
                               self.v["select"].get(), opts, self.sd.uid)

    def cmd_ok(self) -> bool:
        try:
            sd = self.draft()
        except ValueError:
            self.errors.configure(text="each option line starts with its "
                                       "points: 10 | gains")
            return False
        self.on_ok(sd)
        self.destroy()
        return True
