"""attack_analyzer + ui.side_picker / result_window / variants_dialog,
driven end to end on the synthetic library: book and list
sources, joined Hero, analyse (shooting and melee), statistic cycling,
distribution, pins and comparison, variants, swap. Real Tk when a
display answers, else tkstub."""
import os
import shutil
import tempfile

from tkhost import REAL
import testpaths
from tkinter import messagebox
from attack_analyzer import AnalyzerApp
from grimdarkoracle.app.library import Library
from grimdarkoracle.data import army_list
from grimdarkoracle.data.army_list import ArmyList, ListUnit

# Modal message boxes would block a real Tk run: record them instead.
shown = []
messagebox.showinfo = messagebox.showerror = \
    lambda title, msg, **kw: shown.append((title, msg))
lib = Library.load(testpaths.SYNTHETIC_DIR)
app = AnalyzerApp(lib)
left, right = app.left, app.right
assert app.attacker is left and app.target is right
assert app.cmd_analyse() is None and shown[-1][0] == "Analyse"   # no units
names = [u.name for u in left.units]
left.select(names.index("Line Troopers"))
right.select(names.index("Jet Riders"))
assert left.spec.unit.cfg.unit.id == "uTroop1"
assert "Line Troopers" in app.summary.cget("text") and "shoots" in \
    app.summary.cget("text")

# Shooting result window.
rw = app.cmd_analyse()
rows = rw.rows()
assert rows[-1][0].startswith("TOTAL") and any(r[0] == "Rifle" for r in rows)
before = rw.tree.heading("wounds")["text"]
rw.cycle("wounds")
assert rw.tree.heading("wounds")["text"] != before
assert rw.stats["wounds"] == "median"
rw.cycle("count")                                   # not a statistic
assert "count" not in rw.stats
aw = rw.cmd_audit()                                 # no selection: all
assert aw.body().startswith("Rifle  (") and "Hit     Quality" in aw.body()
first = rw.tree.get_children()[0]
rw.tree.selection_set(first)
assert rw.cmd_audit().body().startswith(rw.tree.item(first, "text"))
ins = left.cmd_inspect()
assert ins.body().startswith("Line Troopers") and "Weapons" in ins.body()
assert right.sheet().title.startswith("Jet Riders")
dist = rw.cmd_dist()                                # TOTAL by default
assert dist is not None
rw.cmd_pin()
assert len(app.pins) == 1 and str(rw.pin_btn.cget("state")) == "disabled"

# Joined Hero in book mode, then melee with a wounded target.
left.hero_var.set(left.hero_box.cget("values")[1])
left._picked()
assert left.spec.hero is not None and "Field Captain" in left.summary()
if REAL:
    assert str(left.tabs.tab(left.hero_panel, "state")) == "normal"
assert left.state_panel._max == 10 + 3 - 1          # 10 + Hero Tough(3)
right.state_panel.wounds.set("2")
app.setup.v["attack"].set("melee")
app.setup._edited()
mw = app.cmd_analyse()
assert mw.a.kind == "melee" and mw.a.target.wounds is not None
assert any(r[0].startswith("Strike back: ") or r[0].startswith("TOTAL")
           for r in mw.rows())
items = [i for i in mw.tree.get_children() if hasattr(mw.sources[i], "audit")
         and mw.sources[i] is not mw.a.rows[0]]
mw.tree.selection_set(items[0])                     # not the first weapon
assert mw.cmd_audit().body().startswith(mw.sources[items[0]].name + "  (")
mw.cmd_pin()
cw = app.cmd_compare()
assert len(cw.pins) == 2 and str(app.compare_btn.cget("state")) == "normal"
cw._clear()
assert app.pins == [] and str(app.compare_btn.cget("state")) == "disabled"

# Variants of the attacker's sections.
vd = app.cmd_variants()
assert vd.role.get() == "Attacker" and vd.section.get()
pins = vd.compute()
assert pins and pins[0]["name"] == "(none)"
assert vd.cmd_run() is not None

# Swap: the right side attacks.
app.cmd_swap()
assert app.attacker is right and str(right.cget("text")) == "Attacker"
assert app.cmd_analyse().a.attacker.unit.name == "Jet Riders"

# Army list source with a joined Hero.
tmp = tempfile.mkdtemp()
try:
    path = os.path.join(tmp, "l.json")
    b = "synthetic00book01"
    army_list.save(ArmyList("L", books={b: lib.books[b].version}, units=[
        ListUnit("u1", b, "uTroop1", "Line Troopers", "Squad"),
        ListUnit("u2", b, "uCapt01", "Field Captain", joined_to="u1")]), path)
    left.cmd_load(path)
    assert left.source.get() == "list" and left.listbox.size() == 1
    left.select(0)
    assert left.spec.hero is not None and left.spec.unit.label == "Squad"
    assert "L (l.json)" == left.list_label.cget("text")
finally:
    os.remove(path)
    os.rmdir(tmp)
left.source.set("book")
left._source_changed()
assert left.spec is None and left.listbox.size() == len(left.units)
assert left.cmd_inspect() is None                   # nothing picked
# Attacker's orders: weapon order and Takedown preferences.
from grimdarkoracle.app import side_spec as SS                 # noqa: E402
from grimdarkoracle.app.unit_config import UnitConfig          # noqa: E402
book = lib.books["synthetic00book01"]
TD = {"op": "weapon_add_rule", "weapon": "Rifle",
      "rule": {"id": "8Hjy54TYtwb7", "name": "Takedown"}}
app.setup.v["attack"].set("shooting")
app.setup._edited()
att, tgt = app.attacker, app.target       # the right side attacks now
att.source.set("book")
att._source_changed()
att.select(names.index("Line Troopers"))
tgt.select(names.index("Line Troopers"))
bar = app.orders
assert str(bar.weapon_btn.cget("state")) == "normal"
assert str(bar.takedown_btn.cget("state")) == "disabled"
assert bar.cmd_takedown() is None
d = bar.cmd_weapons()
assert d.order == ["Rifle", "Hand Weapon"] and d.default
d.box.selection_set(1)
d.cmd_move(-1)
d.cmd_ok()
assert bar.get().weapon_order == ("Hand Weapon", "Rifle")
assert "Hand Weapon > Rifle" in bar.text.cget("text")
att._set_spec(SS.SideSpec(SS.UnitSpec(UnitConfig(book, "uTroop1"),
                                       overrides=(TD,))))
assert str(bar.takedown_btn.cget("state")) == "normal"
assert bar.get().weapon_order == ("Hand Weapon", "Rifle")  # same names
d = bar.cmd_takedown()
assert d.default and d.order == [10] + list(range(10))   # joined Hero
d.box.selection_set(3)
d.cmd_move(-3)
d.cmd_ok()
assert bar.get().takedown_targets[0] == 2 and "Takedown: m3 >" in \
    bar.text.cget("text")
rw = app.cmd_analyse()
assert rw.advice.startswith("Weapon order: the book order")
assert rw.a.opts.takedown_targets == bar.get().takedown_targets
assert rw.a.opts.weapon_order == ("Hand Weapon", "Rifle")
d = bar.cmd_weapons()
d.cmd_suggest()
assert "already the best" in d.note.cget("text")
d.destroy()
app.setup.v["attack"].set("melee")
app.setup._edited()                       # same target: preferences kept
assert app.cmd_analyse().a.opts.takedown_targets[0] == 2
app.setup.v["attack"].set("shooting")
app.setup._edited()
saved_orders = bar.get()
tmp3 = tempfile.mkdtemp()
try:
    opath = os.path.join(tmp3, "o.json")
    assert app.cmd_save(opath) == opath
    tgt.unit_panel.on_change(None)        # same configuration: kept
    assert bar.get() == saved_orders
    tgt.combined.set(True)                # target configuration changes
    tgt._picked()
    assert bar.get().takedown_targets == () and \
        bar.get().weapon_order == saved_orders.weapon_order   # target changed
    assert app.cmd_open(opath) == [] and bar.get() == saved_orders
    from grimdarkoracle.app.analyzer_orders import Orders     # noqa: E402
    bar.set(Orders(("Nope", "Rifle"), (2, 99)))            # stale values
    assert bar.get() == Orders(("Rifle",), (2,))
    bar.set(saved_orders)
    app.setup.v["attack"].set("spell")
    app.setup._edited()
    assert str(bar.weapon_btn.cget("state")) == "disabled"
    assert bar.cmd_weapons() is None
    app.setup.v["attack"].set("shooting")
    app.setup._edited()
    app.cmd_swap()                         # the other unit attacks
    assert bar.get().takedown_targets == ()
    assert str(bar.takedown_btn.cget("state")) == "disabled"
    app.cmd_swap()
finally:
    shutil.rmtree(tmp3)

# Sessions: save, change everything, load back (a second window too).
tmp2 = tempfile.mkdtemp()
try:
    spath = os.path.join(tmp2, "s.json")
    left.select(names.index("Line Troopers"))
    left.state_panel.wounds.set("2")
    left.state_panel.flags["fatigued"].set(True)
    next(iter(left.state_panel.weapon_vars.values())).set(False)
    app.setup.v["attack"].set("melee")
    app.setup.v["tie"].set("charger wins")
    app.setup._edited()
    before = (app.summary.cget("text"), app.setup.get_setup(),
              left.state_panel.get_side(), app.flipped)
    assert before[2].fatigued and before[2].off
    assert app.cmd_save(spath) == spath
    left.select(names.index("Siege Walker"))
    left.state_panel.flags["fatigued"].set(False)
    app.setup.set_setup(app.setup.get_setup().__class__())
    app.cmd_swap()
    assert app.cmd_open(spath) == []
    assert (app.summary.cget("text"), app.setup.get_setup(),
            left.state_panel.get_side(), app.flipped) == before
    other = AnalyzerApp(lib)
    other.cmd_open(spath)
    assert other.summary.cget("text") == before[0] and \
        other.left.spec.unit.cfg.choices == left.spec.unit.cfg.choices
    other.destroy()
    with open(spath, "w") as fh:
        fh.write("{}")
    n = len(shown)
    assert app.cmd_open(spath) is None and shown[n][0] == "Load session"
finally:
    shutil.rmtree(tmp2)

# Spells: the shipped spells.json maps no synthetic spell, so no damage
# spell is offered and a spell attack reports the problem.
assert app.setup.caster_info.cget("text").startswith("no Caster") or \
    app.setup.get_setup().spell is None
app.setup.v["attack"].set("spell")
app.setup._edited()
assert "casts at" in app.summary.cget("text")
left.select(0)
n = len(shown)
assert app.cmd_analyse() is None and len(shown) == n + 1
app.destroy()
print(f"analyzer_gui: OK ({'real Tk' if REAL else 'tkstub'})")
