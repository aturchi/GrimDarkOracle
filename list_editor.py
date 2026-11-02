#!/usr/bin/env python3
"""GrimDarkOracle List Editor: build and edit army lists for Grimdark Future
3.6 from the Army Forge books (and the local books of home-made units).

Left: the list (entries, a joined Hero under its host), its settings and
the Force Org checks. Right: the selected entry (upgrades, Combined copies,
Hero join, placement, overrides). Every change is one undo step.
"Print roster..." saves the whole list as a printable sheet (HTML or
text); "Inspect..." shows the selected entry as the programs play it.

Run from the repository root:  python list_editor.py [list.json]
"""
import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from grimdarkoracle import app_paths
from grimdarkoracle.app import roster_sheet as RS
from grimdarkoracle.app import update_check
from grimdarkoracle.app.library import Library
from grimdarkoracle.app.list_editor import ListEditor
from grimdarkoracle.ui import search_widget
from grimdarkoracle.ui import ui_utils as ui
from grimdarkoracle.ui.entry_panel import EntryPanel
from grimdarkoracle.ui.inspect_dialog import InspectDialog
from grimdarkoracle.ui.list_dialogs import AddUnitDialog
from grimdarkoracle.ui.local_unit_editor import LocalUnitEditor

LISTS_DIR = os.path.join(app_paths.app_dir(), "lists")
FILETYPES = [("Army list", "*.json"), ("All files", "*.*")]


class ListEditorApp(tk.Tk):
    def __init__(self, lib: Library | None = None, path: str | None = None):
        super().__init__()
        search_widget.attach_search(self)          # Ctrl+F
        self.geometry("1280x820")
        self.lib = lib if lib is not None else Library.load()
        self.ed = ListEditor(self.lib)
        self._build()
        self.protocol("WM_DELETE_WINDOW", self.cmd_quit)
        for seq, fn in (("<Control-z>", self.cmd_undo),
                        ("<Control-y>", self.cmd_redo),
                        ("<Control-s>", self.cmd_save)):
            self.bind(seq, lambda _e, f=fn: f())
        if path:
            self.cmd_open(path)
        self.changed()

    # --- building ------------------------------------------------------------

    def _build(self) -> None:
        bar = ttk.Frame(self)
        bar.pack(fill=tk.X, padx=6, pady=4)
        for text, fn, hint in (
                ("New", self.cmd_new, "Start an empty list"),
                ("Open...", self.cmd_open, "Open a saved list"),
                ("Save", self.cmd_save, "Save (Ctrl+S)"),
                ("Save as...", self.cmd_save_as, "Save under another name"),
                ("Undo", self.cmd_undo, "Ctrl+Z"),
                ("Redo", self.cmd_redo, "Ctrl+Y"),
                ("Local units...", self.cmd_local,
                 "Home-made units, their custom rules and upgrades"),
                ("Print roster...", self.cmd_roster,
                 "The whole list on printable pages: .html opens in a "
                 "browser (Ctrl-P), .txt is plain text")):
            ui.tip(ttk.Button(bar, text=text, command=fn), hint).pack(
                side=tk.LEFT, padx=2)
        status, warn = update_check.status_text(
            self.lib, f"{len(self.lib.books)} army books loaded "
            f"({len(self.lib.local)} local)")
        ttk.Label(self, text=status, foreground=ui.WARN_COLOR if
                  warn else ui.HINT_COLOR, wraplength=1250).pack(
            side=tk.BOTTOM, anchor=tk.W, padx=6)
        panes = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        panes.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)
        left = ttk.Frame(panes)
        self._settings(left)
        self.tree = ttk.Treeview(left, columns=("unit", "pts", "status"),
                                 height=18, selectmode="browse")
        for col, text, w in (("#0", "Entry", 220), ("unit", "Unit", 200),
                             ("pts", "Pts", 60), ("status", "", 80)):
            self.tree.heading(col, text=text)
            self.tree.column(col, width=w, stretch=col in ("#0", "unit"))
        self.tree.pack(fill=tk.BOTH, expand=True, pady=2)
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._selected())
        row = ttk.Frame(left)
        row.pack(fill=tk.X)
        for text, fn in (("Add unit...", self.cmd_add),
                         ("Duplicate", self.cmd_duplicate),
                         ("Remove", self.cmd_remove),
                         ("Up", lambda: self.cmd_move(-1)),
                         ("Down", lambda: self.cmd_move(1)),
                         ("Inspect...", self.cmd_inspect)):
            ttk.Button(row, text=text, command=fn).pack(side=tk.LEFT, padx=1)
        self.total = ttk.Label(left, text="", font=ui.bold_font())
        self.total.pack(anchor=tk.W, pady=(6, 0))
        self.checks = ttk.Label(left, text="", foreground=ui.WARN_COLOR,
                                wraplength=560, justify=tk.LEFT)
        self.checks.pack(anchor=tk.W)
        self.panel = EntryPanel(panes, self)
        panes.add(left, weight=2)
        panes.add(self.panel, weight=3)

    def _settings(self, parent) -> None:
        box = ttk.LabelFrame(parent, text="List")
        box.pack(fill=tk.X)
        self.name_var, self.limit_var = tk.StringVar(), tk.StringVar()
        self.force_var = tk.BooleanVar(value=True)
        ttk.Label(box, text="Name").grid(row=0, column=0, sticky=tk.W)
        e = ttk.Entry(box, textvariable=self.name_var, width=30)
        e.grid(row=0, column=1, sticky="ew")
        ttk.Label(box, text="Points limit").grid(row=0, column=2, padx=4)
        s = ttk.Spinbox(box, from_=100, to=20000, increment=250, width=7,
                        textvariable=self.limit_var,
                        command=self.cmd_settings)
        s.grid(row=0, column=3)
        for w in (e, s):
            for ev in ("<Return>", "<FocusOut>"):
                w.bind(ev, lambda _e: self.cmd_settings())
        ui.tip(ttk.Checkbutton(box, text="Force Org", variable=self.force_var,
                               command=self.cmd_settings),
               "Check the optional Force Org limits of the core rules").grid(
            row=0, column=4, padx=4)
        box.columnconfigure(1, weight=1)

    # --- refresh -------------------------------------------------------------

    def changed(self) -> None:
        """Redraw everything from the list (after any edit, undo, open)."""
        ed, keep = self.ed, self.selected()
        self.title(f"GrimDarkOracle - List Editor - {ed.title}")
        self.name_var.set(ed.army.name)
        self.limit_var.set(str(ed.army.points_limit))
        self.force_var.set(ed.army.force_org)
        self.tree.delete(*self.tree.get_children())
        for r in ed.rows():
            parent = r.joined_to if r.joined_to and \
                self.tree.exists(r.joined_to) else ""
            status = "" if r.valid and not r.issues else \
                ("invalid" if not r.valid else "issues")
            unit = r.unit_name + (" [combined]" if r.combined else "")
            self.tree.insert(parent, tk.END, iid=r.key, text=r.label,
                             values=(unit, r.points, status), open=True)
        n = sum(1 for u in ed.army.units)
        self.total.configure(text=f"{ed.points} / {ed.army.points_limit} pts"
                                  f"  -  {n} entries")
        lines = [v.message for v in ed.violations()] + \
            list(ed.result().issues)
        self.checks.configure(text="\n".join(lines) or "No problems",
                              foreground=ui.WARN_COLOR if lines
                              else ui.HINT_COLOR)
        if keep and self.tree.exists(keep):
            self.tree.selection_set(keep)
        self.panel.show(keep if keep and ed.army.unit(keep) else None)

    def selected(self) -> str | None:
        sel = self.tree.selection()
        return sel[0] if sel else None

    def select(self, key: str) -> None:
        self.tree.selection_set(key)
        self._selected()

    def _selected(self) -> None:
        key = self.selected()
        if key != self.panel.key:
            self.panel.show(key)

    # --- commands ------------------------------------------------------------

    def _guard(self, fn, *a):
        try:
            return fn(*a)
        except (ValueError, KeyError, OSError) as exc:
            messagebox.showerror("List Editor", str(exc), parent=self)
            return None
        finally:
            self.changed()

    def cmd_settings(self) -> None:
        a = self.ed.army
        try:
            limit = int(self.limit_var.get())
        except ValueError:
            limit = a.points_limit
        name, force = self.name_var.get().strip() or a.name, \
            bool(self.force_var.get())
        if (name, limit, force) != (a.name, a.points_limit, a.force_org):
            self._guard(self.ed.set_meta, name, limit, force)

    def cmd_add(self, book_uid: str | None = None, unit_id: str | None = None):
        if unit_id is not None:
            key = self._guard(self.ed.add_unit, book_uid, unit_id)
            if key:
                self.select(key)
            return key
        return AddUnitDialog(self, self.lib, self.cmd_add)

    def cmd_duplicate(self):
        key = self.selected()
        if key:
            new = self._guard(self.ed.duplicate, key)
            if new:
                self.select(new)
            return new
        return None

    def cmd_remove(self) -> None:
        key = self.selected()
        if key:
            self._guard(self.ed.remove, key)

    def cmd_move(self, delta: int) -> None:
        key = self.selected()
        if key:
            self._guard(self.ed.move, key, delta)

    def cmd_inspect(self):
        """The selected entry as played: a host with its joined Hero, a
        Hero selected alone."""
        key = self.selected()
        sheet = RS.entry_sheet(self.lib, self.ed.army, self.ed.result(),
                               key) if key else None
        return InspectDialog(self, sheet) if sheet is not None else None

    def roster(self):
        return RS.build(self.lib, self.ed.army, self.ed.result())

    def cmd_roster(self):
        ro = self.roster()
        return ui.save_text(self, lambda path: RS.render(ro, path),
                            title="Print roster", defaultextension=".html",
                            filetypes=[("HTML", "*.html"), ("Text", "*.txt"),
                                       ("All files", "*.*")],
                            initialfile=f"{self.ed.army.name}.html")

    def cmd_local(self):
        return LocalUnitEditor(self, self.lib, self._books_changed)

    def _books_changed(self) -> None:
        """A local book was saved: re-resolve the list on the new data."""
        self.ed.books_changed()
        self.changed()

    def cmd_undo(self) -> None:
        if self.ed.undo():
            self.changed()

    def cmd_redo(self) -> None:
        if self.ed.redo():
            self.changed()

    def _discard_ok(self) -> bool:
        """Unsaved changes: save them (yes), drop them (no) or stay."""
        if not self.ed.dirty:
            return True
        ans = messagebox.askyesnocancel(
            "List Editor", "Save the changes to the list?", parent=self)
        if ans is None:
            return False
        return self.cmd_save() is not None if ans else True

    def cmd_new(self) -> None:
        if self._discard_ok():
            self.ed = ListEditor(self.lib)
            self.changed()

    def cmd_open(self, path: str | None = None):
        if not self._discard_ok():
            return None
        if path is None:
            path = filedialog.askopenfilename(
                parent=self, title="Open army list", filetypes=FILETYPES,
                initialdir=LISTS_DIR if os.path.isdir(LISTS_DIR) else None)
            if not path:
                return None
        try:
            res = ListEditor.open(self.lib, path)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Open army list", str(exc), parent=self)
            return None
        self.ed = res.editor
        self.changed()
        if res.notes:
            messagebox.showinfo("Open army list", "\n".join(res.notes),
                                parent=self)
        return res.notes

    def cmd_save(self):
        if not self.ed.path:
            return self.cmd_save_as()
        return self._guard(self.ed.save)

    def cmd_save_as(self, path: str | None = None):
        if path is None:
            os.makedirs(LISTS_DIR, exist_ok=True)
            path = filedialog.asksaveasfilename(
                parent=self, title="Save army list", initialdir=LISTS_DIR,
                defaultextension=".json", filetypes=FILETYPES,
                initialfile=f"{self.ed.army.name}.json")
            if not path:
                return None
        return self._guard(self.ed.save, path)

    def cmd_quit(self) -> None:
        if self._discard_ok():
            self.destroy()


if __name__ == "__main__":
    ListEditorApp(path=sys.argv[1] if len(sys.argv) > 1 else None).mainloop()
