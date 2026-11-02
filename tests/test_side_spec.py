"""app.side_spec: sides from a book or an army list entry (joined
Hero, Combined copies, overrides, label), join checks, hero candidates,
list labels, run() with join warnings. Synthetic book."""
import testpaths
from grimdarkoracle.app import side_spec as SS
from grimdarkoracle.app.library import Library
from grimdarkoracle.app.setup_model import Setup, SideSetup
from grimdarkoracle.app.unit_config import UnitConfig
from grimdarkoracle.data.army_list import ArmyList, ChoiceRef, ListUnit
from grimdarkoracle.data.list_resolve import resolve_list
from grimdarkoracle.data.resolve import Choice, combine, resolve

lib = Library.load(testpaths.SYNTHETIC_DIR)
book = lib.books["synthetic00book01"]
B = book.uid

troop = SS.book_side(book, "uTroop1")
ru, hero = troop.resolved()
assert hero is None and ru == resolve(book, "uTroop1")
assert troop.issues() == [] and troop.name == "Line Troopers"
assert [u.id for u in SS.hero_candidates(book)] == ["uCapt01"]

# Combined copies (B = A unless given), overrides, list label as name.
cs = (Choice("PA", "sRepOne", "oRepOneB"),)
spec = SS.UnitSpec(UnitConfig(book, "uTroop1", cs), combined=True,
                   overrides=({"op": "set", "path": "quality", "value": 3},),
                   label="Troopers A")
r = spec.resolved()
both = combine(resolve(book, "uTroop1", cs), resolve(book, "uTroop1", cs))
assert r.size == 20 and r.points == both.points and r.quality == 3
assert r.name == "Troopers A"
v = spec.with_choices(())
assert v.cfg.choices == () and v.combined and spec.cfg.choices == cs

# Hero joins: a valid join, then an invalid one (host is a single model).
cap = SS.UnitSpec(UnitConfig(book, "uCapt01"))
joined = SS.SideSpec(SS.UnitSpec(UnitConfig(book, "uTroop1")), cap)
assert joined.issues() == [] and joined.name == "Line Troopers + Field Captain"
bad = SS.SideSpec(SS.UnitSpec(UnitConfig(book, "uWalk01")), cap)
assert bad.issues() == ["Field Captain: Heroes may only join multi-model "
                        "units"]

# run(): the analysis carries the join problems first.
a = SS.run(lib.reg, joined, SideSetup(), bad, SideSetup(), Setup())
assert a.warnings[0].startswith("Field Captain: ")
assert a.attacker.hero is not None and a.attacker.points == \
    resolve(book, "uTroop1").points + resolve(book, "uCapt01").points
m = SS.run(lib.reg, troop, SideSetup(), troop,
           SideSetup(wounds_taken=3), Setup(attack="melee"), exact=True)
assert m.kind == "melee" and m.target.wounds == (0,) * 7 + (1, 1, 1)   # Heroes last

# Army list entries.
army = ArmyList("t", books={B: book.version}, units=[
    ListUnit("u1", B, "uTroop1", "Line Troopers", "Squad", combined=True,
             choices=[ChoiceRef("PA", "sRepOne", "oRepOneB")],
             choices_b=[]),
    ListUnit("u2", B, "uCapt01", "Field Captain", "Cap", joined_to="u1"),
    ListUnit("u3", B, "uWalk01", "Siege Walker",
             choices=[ChoiceRef("PX", "sNope", "oNope",
                                section_label="Nope", option_label="Nope")]),
])
res = resolve_list(army, lib.books)
labels = SS.entry_labels(army, res)
assert [k for k, _t in labels] == ["u1", "u3"]          # the guest is merged
pts = res.entries["u1"].points + res.entries["u2"].points
assert labels[0][1] == f"Squad + Cap [combined]  ({pts} pts)"
assert labels[1][1].endswith("[invalid]")
side, notes = SS.entry_side(lib.books, army, "u1")
ru, hero = side.resolved()
assert ru.name == "Squad" and ru.size == 20 and hero.name == "Cap"
assert side.unit.cfg_b is not None and side.unit.cfg_b.choices == ()
assert ru.points == res.entries["u1"].points and notes == []
walker, notes = SS.entry_side(lib.books, army, "u3")
assert walker.hero is None and len(notes) == 1 and notes[0].startswith(
    "Siege Walker: ")
for key in ("nope",):
    try:
        SS.entry_side(lib.books, army, key)
        raise AssertionError("missing entry accepted")
    except ValueError:
        pass
if not testpaths.USING_SYNTHETIC:
    # All 49 books: the candidates are exactly the single-model Heroes up
    # to Tough(6); 12 official Heroes are bigger (e.g. vehicle leaders).
    from grimdarkoracle.data.list_resolve import is_hero
    real = Library.load(testpaths.DATA_DIR)
    big = n = 0
    for rb in real.books.values():
        cand = {u.id for u in SS.hero_candidates(rb)}
        for u in rb.units.values():
            r0 = resolve(rb, u.id)
            tough = max(m.tough for m in r0.models)
            ok = is_hero(r0) and r0.size == 1 and tough <= 6
            assert (u.id in cand) == ok, (rb.name, u.name)
            big += is_hero(r0) and r0.size == 1 and tough > 6
            n += ok
    assert n and big, (n, big)
    print(f"side_spec: {n} Hero candidates, {big} Heroes above Tough(6)")
print("side_spec: OK")
