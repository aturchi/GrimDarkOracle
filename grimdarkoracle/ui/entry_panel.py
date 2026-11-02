"""Right-hand panel of the List Editor: one list entry (label, notes,
Combined copies, Hero join, upgrades of copy A / B, choices that no
longer link, placement, overrides). A thin view over app.list_editor:
every gesture calls the editor and then app.changed(), which redraws
everything from the list, so undo / redo need nothing special here.
"""
import tkinter as tk
from tkinter import messagebox, ttk

from grimdarkoracle.ui import ui_utils as ui
from grimdarkoracle.ui.list_dialogs import OverrideDialog, PlacementDialog
from grimdarkoracle.ui.option_panel import OptionPanel

NOT_JOINED = "(not joined)"


class EntryPanel(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app                  # needs .ed, .lib, .changed()
        self.key: str | None = None
        self.header = ttk.Label(self, text="No entry selected",
                                font=ui.bold_font())
        self.header.pack(anchor=tk.W, padx=4, pady=2)
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=4)
        self.label_var, self.notes_var = tk.StringVar(), tk.StringVar()
        self.combined, self.copy_b = tk.BooleanVar(), tk.BooleanVar()
        self.join_var = tk.StringVar(value=NOT_JOINED)
        ttk.Label(top, text="Label").grid(row=0, column=0, sticky=tk.W)
        e = ttk.Entry(top, textvariable=self.label_var, width=30)
        e.grid(row=0, column=1, sticky="ew")
        for ev in ("<Return>", "<FocusOut>"):
            e.bind(ev, lambda _e: self.cmd_label())
        ttk.Label(top, text="Notes").grid(row=1, column=0, sticky=tk.W)
        n = ttk.Entry(top, textvariable=self.notes_var, width=30)
        n.grid(row=1, column=1, sticky="ew")
        for ev in ("<Return>", "<FocusOut>"):
            n.bind(ev, lambda _e: self.cmd_notes())
        ttk.Label(top, text="Joined to").grid(row=2, column=0, sticky=tk.W)
        self.join_box = ttk.Combobox(top, textvariable=self.join_var,
                                     state="readonly", width=28)
        self.join_box.grid(row=2, column=1, sticky="ew")
        self.join_box.bind("<<ComboboxSelected>>", lambda _e: self.cmd_join())
        row = ttk.Frame(top)
        row.grid(row=3, column=0, columnspan=2, sticky=tk.W)
        self.combined_box = ui.tip(ttk.Checkbutton(
            row, text="Combined (two copies)", variable=self.combined,
            command=self.cmd_combined), "Two copies of a multi-model unit "
            "as one unit; it counts as one for Force Org")
        self.combined_box.pack(side=tk.LEFT)
        self.copy_b_box = ui.tip(ttk.Checkbutton(
            row, text="Copy B has its own upgrades", variable=self.copy_b,
            command=self.cmd_copy_b), "Off: copy B takes copy A's upgrades")
        self.copy_b_box.pack(side=tk.LEFT, padx=6)
        top.columnconfigure(1, weight=1)
        self.tabs = ttk.Notebook(self)
        self.panels = {c: OptionPanel(self.tabs, lambda cfg, c=c:
                                      self._on_options(c, cfg), height=260)
                       for c in ("a", "b")}
        self.tabs.add(self.panels["a"], text="Upgrades")
        self.tabs.add(self.panels["b"], text="Copy B")
        self.tabs.pack(fill=tk.BOTH, expand=True, padx=4, pady=2)
        self.lost = ttk.Label(self, text="", foreground=ui.WARN_COLOR,
                              wraplength=460, justify=tk.LEFT)
        self.lost.pack(anchor=tk.W, padx=4)
        row = ttk.Frame(self)
        row.pack(fill=tk.X, padx=4)
        self.drop_btn = ui.tip(ttk.Button(row, text="Drop invalid choices",
                                          command=self.cmd_drop),
                               "Remove the choices that no longer exist in "
                               "the book (kept until you do)")
        self.drop_btn.pack(side=tk.LEFT)
        ttk.Button(row, text="Placement...",
                   command=self.cmd_placement).pack(side=tk.LEFT, padx=4)
        self.place_var = tk.StringVar()
        self.place_box = ttk.Combobox(row, textvariable=self.place_var,
                                      state="readonly", width=34)
        self.place_box.pack(side=tk.LEFT)
        box = ttk.LabelFrame(self, text="Overrides (house rules, errata)")
        box.pack(fill=tk.X, padx=4, pady=2)
        self.ov_list = tk.Listbox(box, height=3, exportselection=False)
        self.ov_list.pack(fill=tk.X, padx=4)
        row = ttk.Frame(box)
        row.pack(fill=tk.X, padx=4, pady=2)
        ttk.Button(row, text="Add...", command=self.cmd_add_override).pack(
            side=tk.LEFT)
        ttk.Button(row, text="Remove", command=self.cmd_remove_override).pack(
            side=tk.LEFT, padx=4)
        self.issues = ttk.Label(self, text="", foreground=ui.WARN_COLOR,
                                wraplength=460, justify=tk.LEFT)
        self.issues.pack(anchor=tk.W, padx=4)

    # --- showing -----------------------------------------------------------------

    @property
    def ed(self):
        return self.app.ed

    def show(self, key: str | None) -> None:
        """Redraw the panel for entry 'key' (None: empty)."""
        self.key = key if key and self.ed.army.unit(key) else None
        if self.key is None:
            self.header.configure(text="No entry selected")
            for p in self.panels.values():
                p.set_config(None)
            self.ov_list.delete(0, tk.END)
            self.lost.configure(text="")
            self.issues.configure(text="")
            return
        lu, row = self.ed.entry(self.key), self._row()
        self.header.configure(text=f"{row.unit_name}  ({row.book})  "
                                   f"{row.points} pts")
        self.label_var.set(lu.label)
        self.notes_var.set(lu.notes)
        self.combined.set(lu.combined)
        self.copy_b.set(lu.choices_b is not None)
        self.copy_b_box.configure(state=tk.NORMAL if lu.combined
                                  else tk.DISABLED)
        hosts = self._hosts()
        self.join_box.configure(values=[NOT_JOINED] + [t for _k, t in hosts])
        self.join_var.set(next((t for k, t in hosts if k == lu.joined_to),
                               NOT_JOINED))
        for c in ("a", "b"):
            try:
                cfg = self.ed.config(self.key, c)
            except ValueError:
                cfg = None
            self.panels[c].set_config(cfg)
        self.tabs.tab(self.panels["b"], state=tk.NORMAL if lu.combined and
                      lu.choices_b is not None else tk.DISABLED)
        lost = self.ed.invalid(self.key) + (
            self.ed.invalid(self.key, "b") if lu.choices_b is not None else [])
        self.lost.configure(text="\n".join(
            f"No longer in the book: {r.section_label} / {r.option_label}"
            for r in lost))
        self.drop_btn.configure(state=tk.NORMAL if lost else tk.DISABLED)
        places = [self._choice_text("A", i, r)
                  for i, r in enumerate(lu.choices)]
        if lu.combined and lu.choices_b is not None:
            places += [self._choice_text("B", i, r)
                       for i, r in enumerate(lu.choices_b)]
        self.place_box.configure(values=places)
        self.place_var.set("")
        self.ov_list.delete(0, tk.END)
        for ov in lu.overrides:
            self.ov_list.insert(tk.END, " ".join(f"{k}={v}" for k, v in
                                                 ov.items()))
        self.issues.configure(text="\n".join(row.issues))

    def _row(self):
        return next(r for r in self.ed.rows() if r.key == self.key)

    def _hosts(self) -> list[tuple[str, str]]:
        return [(r.key, f"{r.label} ({r.key})") for r in self.ed.rows()
                if r.key != self.key and r.joined_to is None and r.size > 1]

    @staticmethod
    def _choice_text(copy_, i, r) -> str:
        return f"{copy_}{i + 1}. {r.option_label} x{r.count}"

    # --- gestures ----------------------------------------------------------------

    def _do(self, fn, *a) -> bool:
        """Run an editor edit; a refusal is shown, the panel redrawn."""
        try:
            fn(*a)
        except (ValueError, KeyError, IndexError) as exc:
            messagebox.showerror("List Editor", str(exc), parent=self)
            self.app.changed()
            return False
        self.app.changed()
        return True

    def _on_options(self, copy_, cfg) -> None:
        if self.key is not None and cfg is not None:
            self._do(self.ed.commit, self.key, cfg, copy_)

    def cmd_label(self) -> None:
        if self.key and self.label_var.get().strip() != \
                self.ed.entry(self.key).label:
            self._do(self.ed.set_label, self.key, self.label_var.get())

    def cmd_notes(self) -> None:
        if self.key and self.notes_var.get() != self.ed.entry(self.key).notes:
            self._do(self.ed.set_notes, self.key, self.notes_var.get())

    def cmd_combined(self) -> None:
        if self.key:
            self._do(self.ed.set_combined, self.key, bool(self.combined.get()))

    def cmd_copy_b(self) -> None:
        if self.key:
            self._do(self.ed.set_copy_b, self.key, bool(self.copy_b.get()))

    def cmd_join(self) -> None:
        if not self.key:
            return
        text = self.join_var.get()
        host = next((k for k, t in self._hosts() if t == text), None)
        if host is None:
            self._do(self.ed.unjoin, self.key)
        elif host != self.ed.entry(self.key).joined_to:
            self._do(self.ed.join, self.key, host)

    def cmd_drop(self) -> None:
        if self.key:
            lu = self.ed.entry(self.key)
            self._do(lambda: (self.ed.drop_invalid(self.key),
                              lu.choices_b is not None and
                              self.ed.drop_invalid(self.key, "b")))

    def cmd_placement(self):
        """Placement dialog of the choice picked in the combobox (copy A
        or B), offering only the models able to take each instance."""
        if not self.key or not self.place_var.get():
            return None
        lu, text = self.ed.entry(self.key), self.place_var.get()
        copy_, i = text[0].lower(), int(text[1:].split(".")[0]) - 1
        ref = (lu.choices if copy_ == "a" else lu.choices_b)[i]
        size = self._row().size // (2 if lu.combined else 1)
        if size < 2:
            messagebox.showinfo("Placement", "A single model takes every "
                                "upgrade.", parent=self)
            return None
        key = self.key
        if self.ed.candidates(key, i, ref.models or (), copy_) is None:
            messagebox.showinfo("Placement", "This upgrade goes to every "
                                "model, or to the unit: it has no placement.",
                                parent=self)
            return None
        return PlacementDialog(
            self, ref.option_label, ref.count, size, ref.models,
            lambda ms: self._do(self.ed.set_models, key, i, ms, copy_),
            lambda picks: self.ed.candidates(key, i, picks, copy_))

    def cmd_add_override(self):
        if not self.key:
            return None
        ru = self.ed.result().entries[self.key].unit
        if ru is None:
            return None
        dlg = OverrideDialog(self, ru, self.app.lib.reg, None)

        def ok(ov):
            if self._do(self.ed.add_override, self.key, ov):
                dlg.destroy()
        dlg.on_ok = lambda ov: ok(ov)
        dlg.cmd_ok = lambda: self._build_and(dlg, ok)
        return dlg

    def _build_and(self, dlg, ok) -> None:
        try:
            ov = dlg.build()
        except ValueError as exc:
            messagebox.showerror("Override", str(exc), parent=dlg)
            return
        ok(ov)

    def cmd_remove_override(self) -> None:
        sel = self.ov_list.curselection()
        if self.key and sel:
            self._do(self.ed.remove_override, self.key, sel[0])
