"""Army lists: format, re-linking, combined units, joins, overrides, Force Org."""
import copy
import os
import tempfile

import testpaths
import make_synthetic
from grimdarkoracle.data import af_book as ab
from grimdarkoracle.data import army_list as al
from grimdarkoracle.data import force_org, links
from grimdarkoracle.data.list_resolve import resolve_list
from grimdarkoracle.data.resolve import Choice

BOOK = ab.load_book(testpaths.book_path(make_synthetic.BOOK_UID,
                                        testpaths.SYNTHETIC_DIR))
BOOKS = {BOOK.uid: BOOK}
CAPT = BOOK.units["uCapt01"]


def ref(unit_id, pkg, sec, opt, n=1):
    return al.make_ref(BOOK, BOOK.units[unit_id], Choice(pkg, sec, opt, n))


def entry(key, unit_id, choices=(), **kw):
    u = BOOK.units[unit_id]
    return al.ListUnit(key, BOOK.uid, unit_id, u.name,
                       choices=list(choices), **kw)


# --- fingerprints: occurrence of same-label sections ------------------------
r1 = ref("uCapt01", "PC", "sOne", "oOneA")
r2 = ref("uCapt01", "PC", "sOne2", "oOne2A")
assert (r1.section_label, r1.section_nth, r1.option_label) == (
    "Upgrade with one", 1, "Psychic")
assert (r2.section_label, r2.section_nth, r2.option_label) == (
    "Upgrade with one", 2, "Psychic")

# --- links: uid, label fallback (respecting occurrence), invalid -------------
lu = entry("u1", "uCapt01", [r1, r2])
lr = links.link_unit(BOOK, lu)
assert lr.unit_id == "uCapt01" and not lr.relinked and not lr.invalid
broken = copy.deepcopy(lu)
for r in broken.choices:
    r.section, r.option = "gone-" + r.section, "gone-" + r.option
lr = links.link_unit(BOOK, broken)
assert [(c.section, c.option) for c in lr.choices] == [("sOne", "oOneA"),
                                                       ("sOne2", "oOne2A")]
assert len(lr.relinked) == 2 and not lr.invalid
broken.choices[0].option_label = "No Such Option"
lr = links.link_unit(BOOK, broken)
assert len(lr.choices) == 1 and len(lr.invalid) == 1
moved = entry("u1", "uCapt01", [r1])
moved.unit_id = "renamedId"                     # unit uid changed upstream
lr = links.link_unit(BOOK, moved)
assert lr.unit_id == "uCapt01" and lr.relinked == ["unit 'Field Captain'"]
assert links.link_unit(None, moved).invalid == ["book "
                                                f"{BOOK.uid!r} not available"]

# --- format: round trip, atomic save, errors ---------------------------------
army = al.ArmyList("Test", points_limit=1000, books={BOOK.uid: "3.6.0"},
                   units=[entry("u1", "uTroop1",
                                [ref("uTroop1", "PA", "sRepAny", "oRepAny", 2)]),
                          entry("u2", "uCapt01", [r1], joined_to="u1"),
                          entry("u3", "uJets01", combined=True,
                                overrides=[{"op": "set", "path": "quality",
                                            "value": 3}])])
assert al.from_dict(al.to_dict(army)) == army
tmp = tempfile.mkdtemp(prefix="grimdarkoracle_list_")
path = os.path.join(tmp, "test.json")
al.save(army, path)
assert al.load(path) == army and not os.path.exists(path + ".tmp")
assert army.new_key() == "u4"
for bad in ({"format": "other"}, {"format": al.FORMAT, "units": [
        {"key": "a"}, {"key": "a"}]}, []):
    try:
        al.from_dict(bad)
    except al.ListFormatError:
        pass
    else:
        raise AssertionError(f"accepted {bad!r}")

# --- whole list: points, join, combined, overrides ----------------------------
res = resolve_list(army, BOOKS)
e1, e2, e3 = (res.entries[k] for k in ("u1", "u2", "u3"))
assert e1.points == 110 and e2.points == 75 and not e2.issues
assert e3.unit.combined and e3.unit.size == 6 and e3.points == 240
assert e3.unit.quality == 3 and e3.unit.modified
assert res.points == 425 and res.issues == []
assert force_org.check(army, res) == []

# combined copies must share all-model upgrades
shields = ref("uJets01", "PB", "sMAll", "oMAll")
army.units[2].choices = [shields]
army.units[2].choices_b = []
e3 = resolve_list(army, BOOKS).entries["u3"]
assert e3.points == 240 + 9
assert any("all models" in i for i in e3.unit.issues)
army.units[2].choices_b = None                  # B = same as A
e3 = resolve_list(army, BOOKS).entries["u3"]
assert e3.points == 240 + 18 and not e3.unit.issues

# joins: not a hero, too tough, host single-model, two heroes, missing host
bad = al.ArmyList("Joins", books={BOOK.uid: "3.5.0"}, units=[
    entry("t", "uTroop1"), entry("w", "uWalk01", joined_to="t"),
    entry("c1", "uCapt01", joined_to="t"), entry("c2", "uCapt01",
                                                 joined_to="w2"),
    entry("w2", "uWalk01")])
res = resolve_list(bad, BOOKS)
w_issues = " | ".join(res.entries["w"].issues)
assert "only Heroes" in w_issues and "Tough(6)" in w_issues
assert "already has another Hero" in w_issues
assert any("multi-model" in i for i in res.entries["c2"].issues)
assert "list saved with 3.5.0" in res.issues[0]

# overrides: weapon and rule patches, bad ops reported
army2 = al.ArmyList(units=[entry("x", "uTroop1", overrides=[
    {"op": "weapon_set", "weapon": "Rifles", "field": "attacks", "value": 2},
    {"op": "weapon_add_rule", "weapon": "Rifle",
     "rule": {"id": "17crjK7P6_w6", "name": "AP", "rating": 1}},
    {"op": "add_rule", "rule": {"id": "2atvlmICQSCV", "name": "Fearless"}},
    {"op": "weapon_set", "weapon": "Laser", "field": "attacks", "value": 9},
    {"op": "explode"}])])
ru = resolve_list(army2, BOOKS).entries["x"].unit
rifle = next(w for w, _ in ru.weapons() if w.name == "Rifle")
assert rifle.attacks == 2 and rifle.rules[-1].label == "AP(1)"
assert ru.rule_models() == {"Fearless": 10} and ru.modified
assert len(ru.issues) == 2

# --- Force Org ----------------------------------------------------------------
assert force_org.limits(1000) == {"heroes": 2, "copies": 2, "unit_points": 350,
                                  "units": 5, "models": 50}
fo = al.ArmyList("FO", points_limit=500, units=[
    entry("a", "uTroop1"), entry("b", "uTroop1"), entry("c", "uCapt01"),
    entry("d", "uCapt01"), entry("e", "uWalk01")])
res = resolve_list(fo, BOOKS)
kinds = {v.kind for v in force_org.check(fo, res)}
# 560 pts > 500; 2 heroes > 1; 2 copies > 1; walker 200 > 175; 5 units > 2;
# models 10+10+3+3+9 = 35 > 25
assert kinds == {"points", "heroes", "copies", "unit_share", "units",
                 "models"}, kinds
fo.force_org = False
assert [v.kind for v in force_org.check(fo, res)] == ["points"]
print("army list: OK")
