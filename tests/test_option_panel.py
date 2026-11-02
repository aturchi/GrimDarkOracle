"""ui.option_panel: widgets generated from a UnitConfig, gestures
routed to the config, rebuild after each change, invalid choices shown
and removed on request. Real Tk when a display answers, else tkstub."""
from tkhost import ROOT, packed
import testpaths
from grimdarkoracle.app.unit_config import UnitConfig
from grimdarkoracle.data import af_book as ab
from grimdarkoracle.ui import option_panel as OP

book = ab.load_book(testpaths.book_path(
    "synthetic00book01", testpaths.SYNTHETIC_DIR))
seen = []
panel = OP.OptionPanel(ROOT, on_change=lambda c: seen.append(c.points))
panel.pack()
panel.refresh()                                     # no unit: no error
assert panel.cfg is None and not panel.widgets
cfg = UnitConfig(book, "uTroop1")
panel.set_config(cfg)
base = cfg.points
assert panel.header.cget("text").startswith(f"Line Troopers  [10]  {base}")
keys = set(panel.widgets)
radio = ("PA", "sRepOne", None)
assert radio in keys and ("PA", "sRepAny", "oRepAny") in keys
assert ("PA", "sChain", None) in keys                # shown, disabled
assert str(panel.widgets[("PA", "sChain", None)].cget("state")) == "disabled"
# Radio by its text.
sv = cfg.section("PA", "sRepOne")
panel._radio(sv, OP.option_text(sv.options[0]))
assert cfg.section("PA", "sRepOne").selected == sv.options[0].uid
assert seen and seen[-1] == cfg.points
assert str(panel.widgets[("PA", "sChain", None)].cget("state")) == "readonly"
panel._radio(cfg.section("PA", "sChain"), OP.option_text(
    cfg.section("PA", "sChain").options[0]))
# Undo the chain source: invalid choice listed, prune button removes it.
panel._radio(cfg.section("PA", "sRepOne"), OP.option_text(
    cfg.section("PA", "sRepOne").options[1]))
assert cfg.invalid() and panel.issues.cget("text") and packed(panel.prune_btn)
n = len(seen)
panel.cmd_prune()
assert not cfg.invalid() and not panel.issues.cget("text") and len(seen) == n + 1
assert not packed(panel.prune_btn)
sv = cfg.section("PA", "sRepOne")
panel._radio(sv, OP.option_text(sv.options[1]))      # same option again
assert len(seen) == n + 1                            # nothing to notify
panel._radio(cfg.section("PA", "sRepOne"), OP.NONE)
assert cfg.choices == () and cfg.points == base
# Spinbox: typed text clamped by the config; bad text and FocusOut with
# an unchanged count do not rebuild nor notify.
key = ("PA", "sRepAny", "oRepAny")
panel.vars[key].set("99")
panel._spin(key, panel.vars[key])
lim = cfg.section("PA", "sRepAny").options[0].wanted
assert lim == cfg.section("PA", "sRepAny").total and \
    panel.vars[key].get() == str(lim)
n = len(seen)
panel.vars[key].set("abc")
panel._spin(key, panel.vars[key])                   # -> 0: a real change
assert cfg.choices == () and len(seen) == n + 1
panel._spin(key, panel.vars[key])                   # unchanged: no notify
assert len(seen) == n + 1 and panel.vars[key].get() == "0"
panel.vars[key].set("x")                            # bad text, count 0
panel._spin(key, panel.vars[key])
assert len(seen) == n + 1 and panel.vars[key].get() == "0"
# Check sections.
cap = UnitConfig(book, "uCapt01")
panel.set_config(cap)
ck = ("PC", "sAny", cap.section("PC", "sAny").options[0].uid)
panel.vars[ck].set(True)
panel._set(ck, 1)
assert cap.section("PC", "sAny").options[0].wanted == 1
o = cap.section("PC", "sAny").options[0]
assert OP.option_text(o) == (f"{o.label}  (+{o.cost} pts)" if o.cost
                             else f"{o.label}  (free)")
panel.set_config(None)
assert panel.header.cget("text") == "No unit selected"
print("option_panel: OK")
