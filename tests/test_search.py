"""Ctrl+F search (app.text_search, ui.search_widget): matching with
wrap-around, the lists a window shows (hidden ones and other windows left
out), revealing a tree row, the dialog's Next / not found, and the one
dialog re-aimed at the window where Ctrl+F is pressed."""
from tkhost import ROOT, REAL
import tkinter as tk
from tkinter import ttk

from grimdarkoracle.app.text_search import next_match
from grimdarkoracle.ui import search_widget as SW

# --- pure matching ----------------------------------------------------------
R = [("a", "Battle Brothers"), ("b", "Assault Brothers"), ("c", "Drop Pod")]
assert next_match(R, "brothers") == "a"
assert next_match(R, "BROTHERS", "a") == "b"
assert next_match(R, "brothers", "b") == "a"            # wrap-around
assert next_match(R, "pod", "zz") == "c"                # unknown: start
assert next_match(R, "  ", None) is None and next_match([], "x") is None
assert next_match(R, "titan") is None

# --- the lists of a window --------------------------------------------------
win = tk.Toplevel(ROOT)
lb = tk.Listbox(win)
lb.insert(tk.END, "Grunt Leader", "Hover Tank", "Tide Titan")
lb.pack()
tree = ttk.Treeview(win, columns=("pts",))
top = tree.insert("", tk.END, text="DAO Union", values=("",))
leaf = tree.insert(top, tk.END, text="Surge Titan", values=("395",))
tree.pack()
hidden = ttk.Frame(win)                     # never packed: not searched
tk.Listbox(hidden).pack()
other = tk.Toplevel(win)                    # another window: not searched
tk.Listbox(other).pack()
if REAL:
    win.update()
found = SW.searchables(win)
assert found == [lb, tree], found
rows = SW.rows(found)
assert rows[0] == ((0, 0), "Grunt Leader") and rows[-1] == (
    (1, leaf), "Surge Titan 395"), rows

picked = []
tree.bind("<<TreeviewSelect>>", lambda _e: picked.append(tree.selection()))
dlg = SW.SearchDialog(ROOT, win)
dlg.entry.insert(0, "titan")
assert dlg.cmd_next() == (lb, 2) and lb.curselection() == (2,)
assert dlg.cmd_next() == (tree, leaf)
assert tree.selection() == (leaf,) and tree.item(top, "open") in (1, True)
if REAL:
    win.update()
    assert picked and picked[-1] == (leaf,)     # panels follow the pick
assert dlg.cmd_next() == (lb, 2)                # wrap-around
assert dlg.cmd_next() == (tree, leaf)
assert SW.searchables(win)[1] is tree
dlg.entry.delete(0, tk.END)
dlg.entry.insert(0, "nothing like this")
assert dlg.cmd_next() is None and "not found" in dlg.info.cget("text")
dlg.target = hidden
assert dlg.cmd_next() is None and "Nothing to search" in dlg.info.cget(
    "text")
dlg.destroy()


# --- Ctrl+F: one dialog, aimed at the window where it was pressed -----------
class Event:
    def __init__(self, widget):
        self.widget = widget


app = tk.Toplevel(ROOT)
SW.attach_search(app)
holder = app.search_holder
if REAL:
    script = app.bind_all("<Control-f>")
    assert script, "Ctrl+F not bound"
    win.focus_force()
    lb.focus_set()
    win.update()
    lb.event_generate("<Control-f>")
    win.update()
    assert holder["dlg"] is not None and holder["dlg"].target is win
    tree.event_generate("<Control-F>")
    assert holder["dlg"].target is win
    other_lb = other.winfo_children()[0]
    other.update()
    other_lb.focus_force()                  # key events go to the focus
    other.update()
    other_lb.event_generate("<Control-f>")
    assert holder["dlg"].target is other         # re-aimed, same dialog
    holder["dlg"].destroy()
print(f"search: matching, lists of a window, dialog and Ctrl+F OK "
      f"({'real Tk' if REAL else 'stub'})")
