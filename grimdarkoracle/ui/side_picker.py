"""Side picker of the Analyzer: where one side's unit comes from (a book
unit, or an army list entry with its joined Hero and Combined copies),
its upgrade choices (OptionPanel, one tab for the unit and one for a
joined Hero) and its state at the start (SidePanel). A thin view over
app.side_spec; on_change(picker) after every change of the unit.

Edits made here change the analysis only: a list loaded from disk is
never written back (that is the List Editor's job).
"""
import os
import tkinter as tk
from tkinter import messagebox, ttk

from grimdarkoracle.app import session_io as SIO
from grimdarkoracle.app import side_spec as SS
from grimdarkoracle.app import unit_sheet as US
from grimdarkoracle.app.unit_config import UnitConfig
from grimdarkoracle.ui import ui_utils as ui
from grimdarkoracle.ui.inspect_dialog import InspectDialog
from grimdarkoracle.ui.option_panel import OptionPanel
from grimdarkoracle.ui.roster_picker import ask_roster_files
from grimdarkoracle.ui.setup_panel import SidePanel

NO_HERO = "(no Hero)"


class SidePicker(ttk.LabelFrame):
    def __init__(self, parent, lib, title: str, on_change=None):
        super().__init__(parent, text=title)
        self.lib, self.on_change = lib, on_change
        self.spec: SS.SideSpec | None = None
        self.notes: list[str] = []
        self.books = lib.catalogue()
        self.units: list = []           # units shown in book mode
        self.heroes: list = []          # Hero candidates of the book
        self.army = self.result = None
        self.entries: list = []         # (key, text) in list mode
        self.source = tk.StringVar(value="book")
        self.book_var = tk.StringVar()
        self.hero_var = tk.StringVar(value=NO_HERO)
        self.combined = tk.BooleanVar(value=False)
        self._build()
        if self.books:
            self.book_var.set(self.books[0].name)
            self._book_changed()

    # --- building ---------------------------------------------------------------

    def _build(self):
        row = ttk.Frame(self)
        row.pack(fill=tk.X, padx=4, pady=2)
        for value, text in (("book", "Army book"), ("list", "Army list")):
            ttk.Radiobutton(row, text=text, value=value, variable=self.source,
                            command=self._source_changed).pack(side=tk.LEFT)
        self.book_frame = ttk.Frame(self)
        self.book_box = ttk.Combobox(
            self.book_frame, textvariable=self.book_var, state="readonly",
            values=[f"{b.name}" for b in self.books])
        self.book_box.pack(fill=tk.X)
        self.book_box.bind("<<ComboboxSelected>>",
                           lambda _e: self._book_changed())
        self.list_frame = ttk.Frame(self)
        lrow = ttk.Frame(self.list_frame)
        lrow.pack(fill=tk.X)
        ttk.Button(lrow, text="Load list...", command=self.cmd_load).pack(
            side=tk.LEFT)
        self.list_label = ttk.Label(lrow, text="no list loaded",
                                    foreground=ui.HINT_COLOR)
        self.list_label.pack(side=tk.LEFT, padx=4)
        frame, self.listbox = ui.scrollable_listbox(self, height=8,
                                                    exportselection=False)
        self.list_holder = frame
        self.listbox.bind("<<ListboxSelect>>", lambda _e: self._picked())
        jrow = ttk.Frame(self)
        self.join_row = jrow
        ttk.Label(jrow, text="Joined Hero").pack(side=tk.LEFT)
        self.hero_box = ttk.Combobox(jrow, textvariable=self.hero_var,
                                     state="readonly", width=26)
        self.hero_box.pack(side=tk.LEFT, padx=4)
        self.hero_box.bind("<<ComboboxSelected>>", lambda _e: self._picked())
        self.combined_box = ui.tip(ttk.Checkbutton(
            jrow, text="Combined", variable=self.combined,
            command=self._picked),
            "Two copies of this multi-model unit as one (same choices)")
        self.combined_box.pack(side=tk.LEFT)
        self.inspect_row = ttk.Frame(self)
        ui.tip(ttk.Button(self.inspect_row, text="Inspect...",
                          command=self.cmd_inspect),
               "The unit as the program will play it, with the rule texts; "
               "Save cheat sheet from there").pack(side=tk.LEFT)
        self.tabs = ttk.Notebook(self)
        self.unit_panel = OptionPanel(self.tabs, self._options_changed,
                                      height=220)
        self.hero_panel = OptionPanel(self.tabs, self._options_changed,
                                      height=220)
        self.tabs.add(self.unit_panel, text="Unit")
        self.tabs.add(self.hero_panel, text="Hero")
        self.state_panel = SidePanel(self, "State at the start")
        self._layout()

    def _layout(self):
        for w in (self.book_frame, self.list_frame, self.list_holder,
                  self.join_row, self.inspect_row, self.tabs,
                  self.state_panel):
            w.pack_forget()
        top = self.book_frame if self.source.get() == "book" \
            else self.list_frame
        top.pack(fill=tk.X, padx=4, pady=2)
        self.list_holder.pack(fill=tk.X, padx=4)
        if self.source.get() == "book":
            self.join_row.pack(fill=tk.X, padx=4, pady=2)
        self.inspect_row.pack(fill=tk.X, padx=4, pady=2)
        self.tabs.pack(fill=tk.BOTH, expand=True, padx=4, pady=2)
        self.state_panel.pack(fill=tk.X, padx=4, pady=2)

    # --- sources ------------------------------------------------------------------

    def _source_changed(self):
        self._layout()
        self._fill_list()
        self._set_spec(None)

    def _book(self):
        name = self.book_var.get()
        info = next((b for b in self.books if b.name == name), None)
        return self.lib.books.get(info.uid) if info else None

    def _book_changed(self):
        book = self._book()
        self.units = self.lib.units(book.uid) if book else []
        self.heroes = SS.hero_candidates(book) if book else []
        self.hero_box.configure(values=[NO_HERO] + [
            f"{u.name} ({u.cost} pts)" for u in self.heroes])
        self.hero_var.set(NO_HERO)
        self._fill_list()
        self._set_spec(None)

    def _fill_list(self):
        self.listbox.delete(0, tk.END)
        if self.source.get() == "book":
            for u in self.units:
                self.listbox.insert(tk.END, f"{u.name} [{u.size}]  "
                                            f"{u.cost} pts")
        else:
            for _key, text in self.entries:
                self.listbox.insert(tk.END, text)

    def cmd_load(self, path: str | None = None):
        if path is None:
            paths = ask_roster_files(self, title="Load army list")
            if not paths:
                return
            path = paths[0]
        try:
            self.army, self.result = self.lib.load_list(path)
        except (OSError, ValueError, KeyError) as exc:
            messagebox.showerror("Load army list", str(exc), parent=self)
            return
        self.entries = SS.entry_labels(self.army, self.result)
        self.list_path = path
        self.list_label.configure(
            text=f"{self.army.name} ({os.path.basename(path)})")
        self.source.set("list")
        self._layout()
        self._fill_list()
        self._set_spec(None)

    def select(self, index: int) -> None:
        """Pick the index-th unit / entry of the list (also for tests)."""
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(index)
        self._picked()

    def _picked(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        i = sel[0]
        if self.source.get() == "list":
            try:
                spec, self.notes = SS.entry_side(self.lib.books, self.army,
                                                 self.entries[i][0])
            except ValueError as exc:
                messagebox.showerror("Army list", str(exc), parent=self)
                return
            self._set_spec(spec)
            return
        book, unit = self._book(), self.units[i]
        multi = unit.size > 1
        self.combined_box.configure(state=tk.NORMAL if multi else
                                    tk.DISABLED)
        self.hero_box.configure(state="readonly" if multi else tk.DISABLED)
        if not multi:
            self.combined.set(False)
            self.hero_var.set(NO_HERO)
        old = self.spec
        same = old is not None and old.unit.cfg.unit.id == unit.id and \
            old.unit.cfg.book is book
        cfg = old.unit.cfg if same else UnitConfig(book, unit.id)
        hero = None
        h = self.hero_var.get()
        if h != NO_HERO:
            names = [f"{u.name} ({u.cost} pts)" for u in self.heroes]
            hu = self.heroes[names.index(h)]
            keep = same and old.hero is not None and \
                old.hero.cfg.unit.id == hu.id
            hero = old.hero if keep else SS.UnitSpec(UnitConfig(book, hu.id))
        self.notes = []
        self._set_spec(SS.SideSpec(SS.UnitSpec(cfg, self.combined.get()),
                                   hero))

    def _set_spec(self, spec) -> None:
        self.spec = spec
        self.unit_panel.set_config(spec.unit.cfg if spec else None)
        self.hero_panel.set_config(spec.hero.cfg if spec and spec.hero
                                   else None)
        self.tabs.tab(self.hero_panel, state=tk.NORMAL if spec and spec.hero
                      else tk.DISABLED)
        self._options_changed(None)

    def _options_changed(self, _cfg) -> None:
        if self.spec is None:
            self.state_panel.set_unit(None)
        else:
            ru, hero = self.spec.resolved()
            self.state_panel.set_unit(ru, hero)
        if self.on_change:
            self.on_change(self)

    def sheet(self):
        """app.unit_sheet.Sheet of the side, or None."""
        if self.spec is None:
            return None
        ru, hero = self.spec.resolved()
        return US.build(self.lib.reg, ru, hero, self.spec.unit.cfg.book,
                        self.lib.sreg)

    def cmd_inspect(self):
        sheet = self.sheet()
        return InspectDialog(self, sheet) if sheet is not None else None

    # --- sessions -------------------------------------------------------------------

    def state(self):
        """app.session_io.SideState of this side, or None."""
        if self.spec is None:
            return None
        path = getattr(self, "list_path", None) \
            if self.source.get() == "list" else None
        return SIO.SideState(self.spec, self.state_panel.get_side(),
                             self.source.get(), path)

    def restore(self, st) -> None:
        """Show a SideState (None: no unit). The list file is reloaded when
        it still exists, so its other entries can be picked again."""
        if st is None:
            self._set_spec(None)
            return
        book = st.spec.unit.cfg.book
        if st.source == "list" and st.list_path and \
                os.path.isfile(st.list_path):
            self.cmd_load(st.list_path)
        else:
            self.source.set("book")
            info = next((b for b in self.books if b.uid == book.uid), None)
            self.book_var.set(info.name if info else book.name)
            self._layout()
            self._book_changed()
            ids = [u.id for u in self.units]
            if st.spec.unit.cfg.unit.id in ids:
                i = ids.index(st.spec.unit.cfg.unit.id)
                self.listbox.selection_clear(0, tk.END)
                self.listbox.selection_set(i)
            multi = st.spec.unit.cfg.unit.size > 1
            self.combined_box.configure(state=tk.NORMAL if multi
                                        else tk.DISABLED)
            self.hero_box.configure(state="readonly" if multi
                                    else tk.DISABLED)
            self.combined.set(st.spec.unit.combined)
            h = st.spec.hero
            names = [f"{u.name} ({u.cost} pts)" for u in self.heroes]
            hit = [n for u, n in zip(self.heroes, names)
                   if h is not None and u.id == h.cfg.unit.id]
            self.hero_var.set(hit[0] if hit else NO_HERO)
        self._set_spec(st.spec)
        self.state_panel.set_side(st.side_setup)

    # --- reading ------------------------------------------------------------------

    def summary(self) -> str:
        if self.spec is None:
            return "no unit"
        ru, hero = self.spec.resolved()
        pts = ru.points + (hero.points if hero else 0)
        return f"{self.spec.name}  ({pts} pts)"
