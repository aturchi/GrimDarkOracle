"""list_editor.py + ui.entry_panel / list_dialogs, driven end to
end on the synthetic library: add units, upgrades through the option
panel, join, Combined and copy B, placement, overrides, settings and
Force Org, undo / redo, save / open, unsaved-changes guard. Real Tk when a
display answers, else tkstub."""
import os
import tempfile

from tkhost import REAL                             # noqa: F401
import testpaths
from tkinter import messagebox
from list_editor import ListEditorApp
from grimdarkoracle.app.library import Library
from grimdarkoracle.data import army_list as AL

shown, answers = [], []
messagebox.showinfo = messagebox.showerror = \
    lambda title, msg, **kw: shown.append((title, msg))
messagebox.askyesnocancel = lambda *a, **kw: answers.pop(0)

lib = Library.load(testpaths.SYNTHETIC_DIR)
B = "synthetic00book01"
app = ListEditorApp(lib)
assert app.panel.key is None and "0 / 2000 pts" in app.total.cget("text")

# Add through the dialog, then directly.
dlg = app.cmd_add()
dlg.choose(B, "Line Troopers")
dlg.cmd_ok()
dlg.destroy()
troop = app.selected()
assert troop == "u1" and app.panel.key == troop
cap = app.cmd_add(B, "uCapt01")
walk = app.cmd_add(B, "uWalk01")
assert app.tree.get_children() == (troop, cap, walk)

# Upgrades through the option panel commit into the list.
app.select(troop)
panel = app.panel.panels["a"]
panel.cfg.set_count("PA", "sRepOne", "oRepOneB", 1)
panel._changed()
assert app.ed.entry(troop).choices[0].option == "oRepOneB"
pts = app.ed.result().entries[troop].points
assert app.tree.item(troop, "values")[1] in (pts, str(pts))

# Join: the Hero goes under its host; a refused join shows the reason.
app.select(cap)
hosts = app.panel.join_box.cget("values")
app.panel.join_var.set(next(h for h in hosts if f"({troop})" in h))
app.panel.cmd_join()
assert app.ed.entry(cap).joined_to == troop
assert app.tree.parent(cap) == troop
assert all(f"({walk})" not in h for h in hosts)     # single model: no host
app.panel.join_var.set("(not joined)")
app.panel.cmd_join()
assert app.ed.entry(cap).joined_to is None and app.tree.parent(cap) == ""
app.select(cap)
app.panel.join_var.set(next(h for h in hosts if f"({troop})" in h))
app.panel.cmd_join()
assert app.ed.entry(cap).joined_to == troop
app.select(walk)
assert all(f"({walk})" not in h for h in app.panel.join_box.cget("values"))

# Combined and copy B.
app.select(troop)
app.panel.combined.set(True)
app.panel.cmd_combined()
app.panel.copy_b.set(True)
app.panel.cmd_copy_b()
lu = app.ed.entry(troop)
assert lu.combined and lu.choices_b == lu.choices
assert app.panel.panels["b"].cfg is not None
app.select(walk)
app.panel.combined.set(True)
app.panel.cmd_combined()                            # single model: refused
assert shown[-1][0] == "List Editor" and not app.ed.entry(walk).combined

# Placement of the upgrade (copy A), then back to automatic.
app.select(troop)
app.panel.place_var.set(app.panel.place_box.cget("values")[0])
pd = app.panel.cmd_placement()
pd.vars[0].set("model 4")
pd.cmd_ok()
assert app.ed.entry(troop).choices[0].models == [3]
# Copy B choices are placed too, with the candidates of copy B.
cfg_b = app.ed.config(troop, "b")
cfg_b.set_count("PA", "sRepAny", "oRepAny", 1)     # B only: model 1's
cfg_b.set_count("PA", "sRepOne", "oRepOneB", 1)     # Rifle is taken first
app.ed.commit(troop, cfg_b, "b")
app.ed.set_models(troop, 0, [0], "b")
app.changed()
b_items = [v for v in app.panel.place_box.cget("values") if v.startswith("B")]
assert len(b_items) == 2
app.panel.place_var.set(b_items[1])
pd = app.panel.cmd_placement()
assert pd.allowed() == [tuple(app.ed.candidates(troop, 1, [None], "b")[0])]
assert 0 not in pd.allowed()[0]                     # copy B's state, not A's
pick = pd.boxes[0].cget("values")[2]
pd.vars[0].set(pick)
pd.cmd_ok()
assert app.ed.entry(troop).choices_b[1].models == [int(pick.split()[1]) - 1]
assert app.ed.entry(troop).choices[0].models == [3]          # A untouched

# Overrides: built in the dialog; a bad one is refused with the reason.
app.select(walk)
od = app.panel.cmd_add_override()
od.v["op"].set("Set a value")
od._op()
od.v["what"].set("quality")
od.v["value"].set("3")
od.cmd_ok()
assert app.ed.entry(walk).overrides == [{"op": "set", "path": "quality",
                                         "value": 3}]
od = app.panel.cmd_add_override()
od.v["op"].set("Add a rule")
od._op()
od.v["rule"].set("Not a rule")
od.cmd_ok()
assert shown[-1][0] == "Override" and len(app.ed.entry(walk).overrides) == 1
od.destroy()
app.panel.ov_list.selection_set(0)
app.panel.cmd_remove_override()
assert app.ed.entry(walk).overrides == []

# Settings and Force Org.
app.limit_var.set("250")
app.cmd_settings()
assert app.ed.army.points_limit == 250 and "exceed" in app.checks.cget("text")

# Inspect and Print roster.
from tkinter import filedialog                      # noqa: E402
app.select(troop)
ins = app.cmd_inspect()
assert ins.body().startswith("Line Troopers + Field Captain")   # as played
ins.destroy()
app.select(cap)
assert app.cmd_inspect().body().startswith("Field Captain  [1]")
app.tree.selection_set(())
assert app.cmd_inspect() is None                    # nothing selected
with tempfile.TemporaryDirectory() as tmp:
    for ext in ("html", "txt"):
        rpath = os.path.join(tmp, f"r.{ext}")
        filedialog.asksaveasfilename = lambda *a, p=rpath, **kw: p
        assert app.cmd_roster() == rpath
        with open(rpath, encoding="utf-8") as fh:
            body = fh.read()
        assert ("<!DOCTYPE html>" in body) == (ext == "html")
        assert "Line Troopers + Field Captain" in body and "exceed" in body
    filedialog.asksaveasfilename = lambda *a, **kw: ""
    assert app.cmd_roster() is None                 # cancelled

# Undo / redo redraw everything.
app.select(walk)
app.panel.label_var.set("Big one")
app.panel.cmd_label()
assert app.tree.item(walk, "text") == "Big one"
app.cmd_undo()
assert app.tree.item(walk, "text") == "Siege Walker"
app.cmd_redo()
assert app.tree.item(walk, "text") == "Big one"

# Remove the host: its Hero is back at the top level.
app.select(troop)
app.cmd_remove()
assert app.tree.parent(cap) == "" and app.ed.entry(cap).joined_to is None

# Files and the unsaved-changes guard.
with tempfile.TemporaryDirectory() as tmp:
    path = os.path.join(tmp, "l.json")
    assert app.cmd_save_as(path) == path and not app.ed.dirty
    assert app.title().endswith("l.json") if REAL else True
    app.select(walk)
    assert app.cmd_duplicate() == "u1"          # first free key
    answers.append(None)                            # cancel: stays
    app.cmd_new()
    assert len(app.ed.army.units) == 3
    answers.append(False)                           # discard
    app.cmd_open(path)
    assert len(app.ed.army.units) == 2 and not app.ed.dirty
    assert AL.load(path).units[1].label == "Big one"
    app.select(walk)
    app.cmd_duplicate()
    answers.append(True)                            # save, then new
    app.cmd_new()
    assert app.ed.army.units == [] and len(AL.load(path).units) == 3
app.destroy()
print("list editor gui: OK")
