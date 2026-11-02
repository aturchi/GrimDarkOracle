"""resolve.placement_candidates: the models offered
for an instance are EXACTLY those resolve() honours. For every placeable
section, option, count and instance: earlier instances on random allowed
models, then every model tried for the instance: offered <=> resolve()
places it there without an issue. Synthetic book; with --real_data every
unit of DAO / BB too. Plus ListEditor.candidates (copy B, lost choices) and
the dialog."""
import random

from tkhost import REAL                             # noqa: F401
import testpaths
from grimdarkoracle.app.library import Library
from grimdarkoracle.app.list_editor import ListEditor
from grimdarkoracle.data import army_list as AL
from grimdarkoracle.data.resolve import Choice, placement_candidates, resolve
from grimdarkoracle.ui.list_dialogs import AUTO, PlacementDialog

rng = random.Random(20261101)


def _extra(book, unit_id, base, st, opt):
    """Context choices: another option of the same section on a random
    model (explicit, may be refused), and one option of another section."""
    sec = next(s for p in book.unit_packages(book.units[unit_id])
               for s in p.sections if s.uid == st.uid)
    out = []
    others = [o for o in sec.options if o.label != opt.label]
    if others and st.caps.total >= 2:
        out.append(Choice(st.package, st.uid, rng.choice(others).uid, 1,
                          (rng.randrange(base.size),)))
    secs = [x for x in base.sections if x.uid != st.uid and x.enabled]
    if secs:
        x = rng.choice(secs)
        s2 = next(s for p in book.unit_packages(book.units[unit_id])
                  for s in p.sections if s.uid == x.uid)
        if s2.options:
            out.append(Choice(x.package, x.uid, s2.options[0].uid, 1))
    return out


def check_unit(book, unit_id, context=False) -> int:
    """Property check on one unit; returns the number of checks. With
    'context', other choices are added around the target (see _extra)."""
    base = resolve(book, unit_id)
    n = 0
    for st in base.sections:
        if not (st.placeable and st.enabled):
            continue
        sec = next(s for p in book.unit_packages(book.units[unit_id])
                   for s in p.sections if s.uid == st.uid)
        for opt in sec.options:
            count = min(st.caps.per_option, st.caps.total, 3)
            if count < 1:
                continue
            extra = _extra(book, unit_id, base, st, opt) if context else []
            for k in range(count):
                picks = [None] * count
                ch = [Choice(st.package, st.uid, opt.uid, count, ())] + extra
                for j in range(k):              # earlier: allowed, random
                    c = placement_candidates(book, unit_id, ch, 0, picks)
                    picks[j] = rng.choice(c[j]) if c and c[j] else None
                cands = placement_candidates(book, unit_id, ch, 0, picks)
                if cands is None:               # context removed the targets
                    assert context and any("absent" in x for x in resolve(
                        book, unit_id, ch).issues)
                    break
                for i in range(base.size):
                    trial = list(picks)
                    trial[k] = i
                    ru = resolve(book, unit_id, [Choice(
                        st.package, st.uid, opt.uid, count, tuple(trial))]
                        + extra)
                    bad = f"model {i + 1} cannot take {opt.label!r}"
                    moved = any(bad in x for x in ru.issues)
                    over = any("exceeds the limit" in x for x in ru.issues)
                    if over:
                        break
                    assert (i in cands[k]) != moved, \
                        (book.name, unit_id, sec.label, opt.label, k, i,
                         cands, ru.issues)
                    if not moved:
                        placed = dict(next(s for s in ru.sections
                                           if s.uid == st.uid).placed)
                        pos = sum(1 for p in trial[:k] if p is not None)
                        assert placed[opt.uid][pos] == i
                    n += 1
    return n


lib = Library.load(testpaths.SYNTHETIC_DIR)
book = lib.books["synthetic00book01"]
n = sum(check_unit(book, u) for u in book.units)
n += sum(check_unit(book, u, True) for u in book.units for _ in range(3))
assert n > 50, n

# Not placeable (a single model, or all models): None.
troop = resolve(book, "uTroop1")
allm = next(s for s in troop.sections if s.caps.expand_all)
opt = next(o for p in book.unit_packages(book.units["uTroop1"])
           for s in p.sections if s.uid == allm.uid for o in s.options)
assert placement_candidates(book, "uTroop1", [Choice(
    allm.package, allm.uid, opt.uid)], 0, ()) is None

# ListEditor.candidates: copy B, and a lost choice before the target.
ed = ListEditor(lib)
key = ed.add_unit(book.uid, "uTroop1")
cfg = ed.config(key)
cfg.set_count("PA", "sRepOne", "oRepOneB", 1)
ed.commit(key, cfg)
ed.set_combined(key, True)
ed.set_copy_b(key, True)
want = placement_candidates(book, "uTroop1", cfg.choices, 0, [None])
assert ed.candidates(key, 0, [None]) == want
assert ed.candidates(key, 0, [None], "b") == want
bogus = AL.ChoiceRef("PX", "sGone", "oGone", 1, "Gone", 1, "Gone")
ed.entry(key).choices.insert(0, bogus)
assert ed.candidates(key, 0, [None]) is None            # the lost one
assert ed.candidates(key, 1, [None]) == want            # shifted index

# The dialog offers only the candidates and flags a bad saved pick.
got = []
c0 = want[0]
bad_pick = next(i for i in range(10) if i not in c0) if len(c0) < 10 \
    else None
d = PlacementDialog(None, "x", 1, 10, [bad_pick], got.append,
                    lambda p: placement_candidates(book, "uTroop1",
                                                   cfg.choices, 0, p))
assert list(d.boxes[0].cget("values")) == [AUTO] + [f"model {i + 1}"
                                                     for i in c0]
if bad_pick is not None:
    assert "cannot take" in d.notes[0].cget("text")
d.vars[0].set(f"model {c0[0] + 1}")
d.refresh()
assert d.notes[0].cget("text") == ""
d.cmd_ok()
assert got == [[c0[0]]]

# Two instances of "Replace any Rifle": the model of the first is no longer
# offered to the second, and a saved pick on it is flagged.
any2 = [Choice("PA", "sRepAny", "oRepAny", 2)]
d = PlacementDialog(None, "y", 2, 10, [0, 0], got.append,
                    lambda p: placement_candidates(book, "uTroop1", any2, 0,
                                                   p))
assert list(d.boxes[1].cget("values")) == [AUTO] + [f"model {i + 1}"
                                                     for i in range(1, 10)]
assert d.notes[0].cget("text") == "" and "cannot take" in \
    d.notes[1].cget("text")
d.vars[0].set("model 2")
d.refresh()                                 # model 1 free again, 2 taken
assert "model 1" in d.boxes[1].cget("values") and d.notes[1].cget("text") == ""
assert "model 2" not in d.boxes[1].cget("values")
d.destroy()

if not testpaths.USING_SYNTHETIC:
    real = Library.load(testpaths.DATA_DIR)
    total = 0
    for uid in ("z8205ez2boggzs22", "78qp9l5alslt6yj8"):
        b = real.books[uid]
        for u in b.units:
            total += check_unit(b, u) + check_unit(b, u, True)
    print(f"placement candidates: {total} real checks (DAO, BB)")
print(f"placement candidates: OK ({n} synthetic checks)")
