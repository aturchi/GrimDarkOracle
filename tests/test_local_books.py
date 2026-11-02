"""data.local_books + Library local books: home-made units in the
Army Forge schema subset, resolved, listed and analysed like official
ones; custom rules aliased to official ones."""
import json
import os
import tempfile

import testpaths
from grimdarkoracle.app import side_spec as SS
from grimdarkoracle.app.library import Library
from grimdarkoracle.app.list_editor import ListEditor
from grimdarkoracle.app.setup_model import Setup, SideSetup
from grimdarkoracle.data import local_books as LB
from grimdarkoracle.data.resolve import Choice, resolve


def raises(exc, fn, *a, **kw):
    try:
        fn(*a, **kw)
    except exc as e:
        return str(e)
    raise AssertionError(f"{exc.__name__} expected")


tmp = tempfile.TemporaryDirectory()
lib = Library.load(testpaths.SYNTHETIC_DIR, local_dir=tmp.name)
assert lib.local == set() and lib.local_dir == tmp.name
assert Library.load(testpaths.SYNTHETIC_DIR).local_dir is None
core = {d.name: d.id for d in lib.core.values()}

raw = LB.new_book("My Guard")
assert raw["uid"] == "local-my-guard" and LB.is_local(raw["uid"])
raises(LB.LocalBookError, LB.new_book, "x", uid="abc")

lucky = LB.custom_rule(raw, "Lucky Charm", "As Fearless.",
                       alias_of=core["Fearless"])
odd = LB.custom_rule(raw, "Odd Habit", "Nothing in combat.")
assert (lucky["id"], odd["id"]) == ("local-my-guard-r1", "local-my-guard-r2")
# Rule ids are global: two local books never share one.
other = LB.new_book("Other")
assert LB.custom_rule(other, "X", "x")["id"] == "local-other-r1"
ap1 = LB.rule_ref(core["AP"], "AP", 1)
rifle = LB.weapon("Las Rifle", 24, 1, [ap1], count=5)
assert rifle["label"] == '5x Las Rifle (24", A1, AP(1))'
knife = LB.weapon("Knife", 0, 1, count=5)
assert knife["label"] == "5x Knife (A1)"
raises(LB.LocalBookError, LB.weapon, "x", -1, 1)
squad = LB.unit(raw, "Guard Squad", 5, 5, 5, 60,
                rules=[LB.rule_ref(lucky["id"], "Lucky Charm")],
                weapons=[rifle, knife])
uid = LB.put_unit(raw, squad)
assert uid == "local-u1"
raises(LB.LocalBookError, LB.unit, raw, "bad", 0, 4, 4, 10)

# Upgrades: replace one rifle, and a unit-wide banner (bare rule).
plasma = LB.weapon("Plasma Gun", 24, 1, [LB.rule_ref(core["AP"], "AP", 4)])
opts = [LB.option("Plasma Gun (24\", A1, AP(4))", [plasma], {uid: 15})]
banner = LB.item("Banner", rules=[LB.rule_ref(core["Banner"], "Banner")])
secs = [LB.section("Replace one Las Rifle", "replace", opts,
                   targets=["Las Rifle"], affects=("exactly", 1)),
        LB.section("Upgrade with one", "upgrade",
                   [LB.option("Banner", [banner], {uid: 5})],
                   select=("exactly", 1))]
raises(LB.LocalBookError, LB.add_package, raw, [uid, "local-u9"], secs)
assert raw["upgradePackages"] == []                 # nothing half-added
pu = LB.add_package(raw, [uid], secs, hint="Guard")
assert pu == "local-p1" and squad["upgrades"] == [pu]
assert [s["uid"] for s in raw["upgradePackages"][0]["sections"]] == \
    ["local-s1", "local-s2"]

known = set(lib.reg.defs)
assert LB.check(raw, known) == []
bad = json.loads(json.dumps(raw))
bad["units"][0]["rules"].append(LB.rule_ref("zzz", "Ghost"))
bad["units"].append(dict(bad["units"][0], id="u-official"))
bad["specialRules"].append(dict(bad["specialRules"][0], id="local-r9"))
probs = LB.check(bad, known)
assert any("'local-r9' must start with" in p for p in probs), probs
assert any("Ghost" in p for p in probs)
assert any("'u-official'" in p for p in probs), probs
raises(LB.LocalBookError, LB.check, {"uid": "local-x"}, known)

# Saved and made live: resolve, points, semantics through the alias.
b = lib.put_local(raw)
assert lib.local == {raw["uid"]} and os.path.isfile(lib.paths[b.uid])
r0 = resolve(b, uid)
assert r0.points == 60 and r0.size == 5
r1 = resolve(b, uid, [Choice(pu, "local-s1", "local-o1"),
                      Choice(pu, "local-s2", "local-o2")])
assert r1.points == 80 and not r1.issues
assert sorted(w.name for w, _ in r1.weapons()) == \
    ["Knife", "Las Rifle", "Plasma Gun"]
assert lib.reg.lookup(lucky["id"], "Lucky Charm").name == "Fearless"
# a custom alias is the user's: no text fingerprint of its own; only
# its target's text is checked (here the synthetic Fearless, whose text is
# not the one the shipped semantics hashed)
from grimdarkoracle.rules import coverage as CV                # noqa: E402
assert CV._changed_texts(lib.reg, lucky["id"], "Lucky Charm",
                         [lib.books[raw["uid"]]]) == {}
cov = CV.coverage(lib.reg, [lib.books[raw["uid"]]])
assert list(cov.changed[lucky["id"]][1]) == ["Fearless (its target)"]
assert lib.reg.status(odd["id"]) == "unmapped"

# An edited custom rule text replaces the registry's definition.
raw["specialRules"][1]["description"] = "Still nothing."
lib.put_local(raw)
assert lib.reg.defs[odd["id"]].description == "Still nothing."

# A list and an analysis with the home-made unit.
ed = ListEditor(lib)
k = ed.add_unit(raw["uid"], uid, "Guard A")
assert ed.points == 60 and ed.rows()[0].book == "My Guard"
a = SS.run(lib.reg, SS.book_side(b, uid), SideSetup(),
           SS.book_side(lib.books["synthetic00book01"], "uTroop1"),
           SideSetup(), Setup(), lib.sreg)
assert a.kind == "shooting" and [r.name for r in a.rows] == ["Las Rifle"]

# Reloaded from disk; a file without the prefix is refused.
with open(os.path.join(tmp.name, "intruder.json"), "w") as fh:
    json.dump(dict(LB.new_book("x"), uid="notlocal"), fh)
lib2 = Library.load(testpaths.SYNTHETIC_DIR, local_dir=tmp.name)
assert lib2.local == {raw["uid"]}
assert any("notlocal" in w for w in lib2.warnings)
assert resolve(lib2.books[raw["uid"]], uid).points == 60

# Removing a unit drops its now unused packages; deleting the book.
LB.remove_unit(raw, uid)
assert raw["units"] == [] and raw["upgradePackages"] == []
lib.drop_local(raw["uid"])
assert raw["uid"] not in lib.books and not os.path.exists(
    LB.path_for(tmp.name, raw["uid"]))
raises(ValueError, lib.drop_local, "synthetic00book01")
raises(LB.LocalBookError, LB.save, dict(raw, uid="official"), tmp.name)
tmp.cleanup()
print("local books: OK")
