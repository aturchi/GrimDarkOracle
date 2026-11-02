"""app.list_editor: editing an army list in memory, synthetic book.
Joins, Combined copies, choices through UnitConfig, invalid choices kept,
re-link on open, overrides, placement, undo / redo, files."""
import os
import tempfile

import testpaths
from grimdarkoracle.app.library import Library
from grimdarkoracle.app.list_editor import ListEditor
from grimdarkoracle.data import army_list as AL
from grimdarkoracle.data.resolve import Choice, combine, resolve

lib = Library.load(testpaths.SYNTHETIC_DIR)
book = lib.books["synthetic00book01"]
B = book.uid


def raises(exc, fn, *a, **kw):
    try:
        fn(*a, **kw)
    except exc as e:
        return str(e)
    raise AssertionError(f"{exc.__name__} expected")


ed = ListEditor(lib)
assert ed.points == 0 and not ed.dirty and ed.violations() == []
troop = ed.add_unit(B, "uTroop1", "Squad")
cap = ed.add_unit(B, "uCapt01")
walk = ed.add_unit(B, "uWalk01")
assert (troop, cap, walk) == ("u1", "u2", "u3") and ed.dirty
assert ed.army.books == {B: book.version}
assert ed.points == sum(resolve(book, u).points
                        for u in ("uTroop1", "uCapt01", "uWalk01"))
raises(KeyError, ed.add_unit, B, "nope")

# Hero joins: allowed on the multi-model unit, refused elsewhere.
msg = raises(ValueError, ed.join, cap, walk)
assert "multi-model" in msg
ed.join(cap, troop)
assert [r.key for r in ed.rows()] == [troop, cap, walk]
assert ed.rows()[1].joined_to == troop
assert "already has a Hero" in raises(ValueError, ed.join, walk, troop)

# Combined and copy B.
assert "multi-model" in raises(ValueError, ed.set_combined, walk, True)
ed.set_combined(troop, True)
assert ed.rows()[0].size == 20
raises(ValueError, ed.config, troop, "b")          # B = A for now
ed.set_copy_b(troop, True)
assert ed.entry(troop).choices_b == []

# Choices through the option panel model.
cfg = ed.config(troop)
cfg.set_count("PA", "sRepOne", "oRepOneB", 1)
ed.commit(troop, cfg)
ref = ed.entry(troop).choices[0]
assert (ref.section_label, ref.option_label) == ("Replace one Rifle",
                                                ref.option_label)
want = combine(resolve(book, "uTroop1", [Choice("PA", "sRepOne", "oRepOneB")]),
               resolve(book, "uTroop1"))
assert ed.result().entries[troop].points == want.points
raises(ValueError, ed.commit, walk, cfg)            # another unit's config

# A choice that no longer links is kept by commit() and flagged.
bogus = AL.ChoiceRef("PX", "sGone", "oGone", 1, "Gone section", 1, "Gone")
ed.entry(troop).choices.append(bogus)
ed._result = None
assert ed.invalid(troop) == [bogus] and not ed.rows()[0].valid
cfg = ed.config(troop)
assert len(cfg.choices) == 1                        # only the linked one
ed.commit(troop, cfg)
assert ed.entry(troop).choices[-1] == bogus
assert ed.drop_invalid(troop) == 1 and ed.invalid(troop) == []
assert ed.rows()[0].valid

# Placement: validated shape, automatic when all None.
ed.set_models(troop, 0, [3])
assert ed.entry(troop).choices[0].models == [3]
ed.set_models(troop, 0, [None])
assert ed.entry(troop).choices[0].models is None
raises(ValueError, ed.set_models, troop, 0, [1, 2])

# Overrides: a working one is stored, one that matches nothing refused.
ed.add_override(walk, {"op": "set", "path": "quality", "value": 3})
assert ed.result().entries[walk].unit.quality == 3
assert "no weapon" in raises(ValueError, ed.add_override, walk,
                             {"op": "weapon_set", "weapon": "Nope",
                              "field": "attacks", "value": 2})
ed.remove_override(walk, 0)
assert ed.entry(walk).overrides == []

# Settings and Force Org checks.
ed.set_meta(name="Test", points_limit=200, force_org_on=True)
kinds = {v.kind for v in ed.violations()}
assert "points" in kinds and "unit_share" in kinds, kinds
raises(ValueError, ed.set_meta, points_limit=0)
assert ed.army.points_limit == 200

# Undo / redo: every edit is one step, and a failed edit leaves no trace.
n = len(ed.history)
ed.set_label(walk, "Big one")
assert ed.undo() and ed.entry(walk).label == ""
assert ed.redo() and ed.entry(walk).label == "Big one"
assert len(ed.history) == n + 1

def boom():
    ed.army.name = "changed"
    raise RuntimeError("boom")
raises(RuntimeError, ed._edit, "bad", boom)
assert ed.army.name == "Test" and len(ed.history) == n + 1

# Duplicate, move, remove (the host frees its Hero).
cap2 = ed.duplicate(cap)
assert ed.entry(cap2).joined_to is None             # one Hero per host
ed.remove(cap2)
dup = ed.duplicate(troop)
assert ed.entry(dup).label == "Squad (copy)" and ed.entry(dup).combined
ed.move(dup, -10)
assert ed.army.units[0].key == dup
ed.remove(troop)
assert ed.entry(cap).joined_to is None
assert [r.key for r in ed.rows()] == [dup, cap, walk]

# Files: save, open; the uids of a renamed option are re-linked.
with tempfile.TemporaryDirectory() as tmp:
    path = ed.save(os.path.join(tmp, "list.json"))
    assert not ed.dirty and ed.title.endswith("list.json")
    raw = AL.to_dict(ed.army)
    raw["units"][0]["choices"][0]["option"] = "oldUid"
    raw["units"][0]["choices"].append(AL._ref_to_dict(bogus))
    stale = os.path.join(tmp, "stale.json")
    AL.save(AL.from_dict(raw), stale)
    op = ListEditor.open(lib, stale)
    assert op.editor.dirty and any("re-linked" in n for n in op.notes)
    assert op.editor.entry(dup).choices[0].option == "oRepOneB"
    assert op.editor.entry(dup).choices[-1] == bogus    # kept, flagged
    assert any("no longer exists" in n for n in op.notes)
    assert not op.editor.history.can_undo()
    same = ListEditor.open(lib, path)
    assert not same.editor.dirty and same.notes == []
    assert AL.to_dict(same.editor.army) == AL.to_dict(ed.army)

# Combined off: copy B goes back to "same as A".
ed.set_combined(dup, False)
assert ed.entry(dup).choices_b is None and not ed.entry(dup).combined
print("list editor: OK")
