"""ui.local_unit_editor + ui.rules_mapper_dialog, from the List
Editor: a local book, a custom rule with effects built in the Mapper, a
unit with an upgrade section, rename, refusals, deletion. Real Tk when a
display answers, else tkstub."""
import tempfile

from tkhost import REAL                             # noqa: F401
import testpaths
from tkinter import messagebox
from list_editor import ListEditorApp
from grimdarkoracle.app.library import Library
from grimdarkoracle.data import local_books as LB

shown = []
messagebox.showinfo = messagebox.showerror = \
    lambda title, msg, **kw: shown.append((title, msg))
messagebox.askyesno = lambda *a, **kw: True

tmp = tempfile.TemporaryDirectory()
lib = Library.load(testpaths.SYNTHETIC_DIR, local_dir=tmp.name)
app = ListEditorApp(lib)
le = app.cmd_local()
assert le.raw is None and not le.cmd_save_unit()
le.new_book_var.set("Drill Hall")
assert le.cmd_new_book() and lib.local == {"local-drill-hall"}
assert le.raw["uid"] == "local-drill-hall"

# A custom rule, then its effects in the Rules Mapper.
le.cmd_new_rule()
le.rv["name"].set("Firing Drill")
le.rv["text"].set("+1 to hit when holding.")
assert le.cmd_save_rule()
assert le.rules.get(0) == "Firing Drill  [unmapped]"
le.rules.selection_set(0)
le._rule()
md = le.cmd_map()
md.v["primitive"].set("hit_mod")
md.v["value"].set("1")
md.v["scope"].set("model")
assert md.cmd_add()
md.v["value"].set("lots")
assert not md.cmd_add() and "whole number" in md.errors.cget("text")
md.conds.set("attack=shooting, action=hold")
md.refresh()
assert md.preview.cget("text").splitlines() == [
    "when attack Shooting and using Hold actions",
    "- +1 to hit rolls on its own attacks (this model only)"]
md.conds.set("moon=full")
assert not md.cmd_save() and shown[-1][0] == "Rules Mapper"
md.conds.set("attack=shooting, action=hold")
assert md.cmd_save()
rid = le.raw["specialRules"][0]["id"]
assert lib.reg.status(rid) == "ok" and le.rules.get(0).endswith("[ok]")

# A second custom rule that behaves as a native rule.
le.cmd_new_rule()
le.rv["name"].set("Spotlight")
le.rv["text"].set("A Mark: friendly shooting gets AP(+1) against it.")
assert le.cmd_save_rule()
le.rules.selection_set(1)
le._rule()
md = le.cmd_map()
assert str(md.as_box.cget("state")) == "disabled"
md.impl.set("behaves as")
md.refresh()
assert str(md.as_box.cget("state")) == "readonly"
assert "pick the rule it behaves as" in md.errors.cget("text")
assert not md.cmd_save()
md.as_name.set("Piercing Shooting Mark")
md.refresh()
assert md.preview.cget("text").startswith(
    "behaves as Piercing Shooting Mark (engine rule 'mark')")
assert len(md.preview.cget("text").splitlines()) > 2   # its effects
assert md.errors.cget("text") == ""
assert md.cmd_save()
terror = le.raw["specialRules"][1]
assert terror[LB.SEM_KEY]["impl"] == "native:mark"
assert terror[LB.SEM_KEY]["effects"]
assert lib.reg.status(terror["id"]) == "ok"
md = le.cmd_map()                                  # reopened as saved
assert (md.impl.get(), md.as_name.get()) == ("behaves as",
                                             "Piercing Shooting Mark")
assert md.effects == [] and md.conds.get() == ""   # not editable effects
md.impl.set("composed")
md.refresh()
assert str(md.as_box.cget("state")) == "disabled"
md.destroy()
le.rules.selection_set(0)
le._rule()

# A unit with the rule and an upgrade section.
le.cmd_new_unit()
for k, v in (("name", "Drillers"), ("size", "5"), ("quality", "4"),
             ("defense", "4"), ("cost", "50"), ("rules", "Firing Drill")):
    le.uv[k].set(v)
le.weapons.insert("1.0", 'Gun (24", A1)')
sd = le.cmd_add_section()
sd.options.insert("1.0", "5 | Fearless")
assert sd.cmd_ok() and le.sections.size() == 1
assert le.cmd_save_unit()
assert le.units.size() == 1 and "As saved: Drillers [5]" in \
    le.preview.cget("text")
le.weapons.delete("1.0", "end")
le.weapons.insert("1.0", "nonsense")
assert not le.cmd_save_unit() and "cannot read weapon" in \
    le.errors.cget("text")
le.show_unit("local-u1")
assert le.uv["rules"].get() == "Firing Drill"

# The List Editor sees the unit at once.
key = app.cmd_add("local-drill-hall", "local-u1")
assert app.ed.result().entries[key].points == 50

# Rename the rule: the unit follows; a used rule cannot be deleted.
le.rules.selection_set(0)
le._rule()
le.rv["name"].set("Drill")
assert le.cmd_save_rule()
assert le.raw["units"][0]["rules"][0]["name"] == "Drill"
le.cmd_delete_rule()
assert "used by a unit" in shown[-1][1]
assert lib.reg.status(rid) == "ok"

# Delete the unit: the list keeps the entry, flagged.
le.units.selection_set(0)
le.cmd_delete_unit()
assert le.units.size() == 0
assert not app.ed.rows()[0].valid
le.cmd_delete_book()
assert lib.local == set() and le.raw is None
le.destroy()
app.destroy()
tmp.cleanup()
print("local unit gui: OK")
