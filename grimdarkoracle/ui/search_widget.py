"""Ctrl+F search in the lists of a window (all three programs).

attach_search(root) binds Ctrl+F on the whole application. The search
dialog looks through the lists (tk.Listbox and ttk.Treeview) shown in
the window where Ctrl+F was pressed (the main window or a dialog):
case-insensitive, Enter / "Next" for the next match (wrap-around), Esc
to close. A Treeview match is revealed (its parents opened) and
selected, as a click would, so the panels follow the selection.
Ported from W40kDiviner; the matching is app.text_search.
"""
import tkinter as tk
from tkinter import ttk

from grimdarkoracle.app.text_search import next_match
from grimdarkoracle.ui import ui_utils as ui


def searchables(window) -> list:
    """The Listbox / Treeview widgets shown in 'window', in widget order
    (lists in hidden tabs or unpacked frames are left out)."""
    out = []

    def walk(w):
        for c in w.winfo_children():
            if isinstance(c, tk.Toplevel) or not c.winfo_ismapped():
                continue                    # other windows, hidden parts
            if isinstance(c, (tk.Listbox, ttk.Treeview)):
                out.append(c)
            walk(c)
    walk(window)
    return out


def _tree_items(tree) -> list:
    out = []

    def walk(parent):
        for iid in tree.get_children(parent):
            out.append(iid)
            walk(iid)
    walk("")
    return out


def rows(widgets) -> list:
    """((widget index, item key), text) of every row of 'widgets'."""
    out = []
    for wi, w in enumerate(widgets):
        if isinstance(w, tk.Listbox):
            out += [((wi, i), str(w.get(i))) for i in range(w.size())]
        else:
            out += [((wi, iid), " ".join([str(w.item(iid, "text"))] + [
                str(v) for v in w.item(iid, "values")]))
                for iid in _tree_items(w)]
    return out


def reveal(widget, key) -> None:
    """Select and show one row, firing the selection event."""
    if isinstance(widget, tk.Listbox):
        widget.selection_clear(0, tk.END)
        widget.selection_set(key)
        widget.see(key)
        widget.event_generate("<<ListboxSelect>>")
        return
    parent = widget.parent(key)
    while parent:
        widget.item(parent, open=True)
        parent = widget.parent(parent)
    widget.selection_set(key)
    widget.focus(key)
    widget.see(key)
    widget.event_generate("<<TreeviewSelect>>")


class SearchDialog(tk.Toplevel):
    """Find a row in the lists of the target window."""

    def __init__(self, parent, target):
        super().__init__(parent)
        self.title("Find")
        self.transient(parent)
        self.resizable(False, False)
        self.target = target
        self._last = None               # (widget, key) of the last hit
        ttk.Label(self, text="Find:").grid(row=0, column=0, padx=4, pady=6)
        self.entry = ttk.Entry(self, width=28)
        self.entry.grid(row=0, column=1, padx=2)
        self.entry.focus_set()
        ui.tip(ttk.Button(self, text="Next", command=self.cmd_next),
               "Next row of the lists of this window that contains the "
               "text (Enter does the same)").grid(row=0, column=2, padx=4)
        self.info = ttk.Label(self, text="", foreground=ui.HINT_COLOR)
        self.info.grid(row=1, column=0, columnspan=3, sticky=tk.W, padx=4)
        self.entry.bind("<Return>", lambda _e: self.cmd_next())
        self.bind("<Escape>", lambda _e: self.destroy())

    def cmd_next(self):
        """Jump to the next match; returns (widget, key) or None."""
        widgets = searchables(self.target) if self.target.winfo_exists() \
            else []
        found = rows(widgets)
        last = None
        if self._last is not None and self._last[0] in widgets:
            last = (widgets.index(self._last[0]), self._last[1])
        key = next_match(found, self.entry.get(), last)
        if key is None:
            self._last = None
            self.info.config(text="Nothing to search in this window"
                             if not found else
                             f"'{self.entry.get().strip()}' not found")
            return None
        w = widgets[key[0]]
        reveal(w, key[1])
        self._last = (w, key[1])
        self.info.config(text="")
        return self._last


def attach_search(root) -> None:
    """Ctrl+F anywhere in the application opens (or brings back) the one
    search dialog, aimed at the window where it was pressed."""
    holder = {"dlg": None}

    def open_search(event=None):
        w = getattr(event, "widget", None)
        win = w.winfo_toplevel() if isinstance(w, tk.Misc) else root
        dlg = holder["dlg"]
        if dlg is not None and dlg.winfo_exists():
            if win is not dlg:
                dlg.target, dlg._last = win, None
            dlg.lift()
            dlg.entry.focus_set()
        else:
            holder["dlg"] = SearchDialog(root, win)
        return "break"

    root.bind_all("<Control-f>", open_search)
    root.bind_all("<Control-F>", open_search)
    root.search_holder = holder         # the dialog, for tests
