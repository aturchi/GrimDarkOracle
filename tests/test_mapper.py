"""rules.mapper + custom rule semantics in local books: a rule with NEW
effects, checked, described, stored in its book, installed live, applied by
the engine, reported changed when its text changes, kept by sessions."""
import tempfile

import testpaths
from grimdarkoracle.app import side_spec as SS
from grimdarkoracle.app.library import Library
from grimdarkoracle.app.setup_model import Setup, SideSetup
from grimdarkoracle.data import local_books as LB
from grimdarkoracle.rules import mapper as MP


def raises(exc, fn, *a, **kw):
    try:
        fn(*a, **kw)
    except exc as e:
        return str(e)
    raise AssertionError(f"{exc.__name__} expected")


tmp = tempfile.TemporaryDirectory()
lib = Library.load(testpaths.SYNTHETIC_DIR, local_dir=tmp.name)
reg = lib.reg
core = {d.name: d.id for d in lib.core.values()}

# Entries: valid, and the custom-rule limits.
drill = MP.entry(effects=[MP.effect("hit_mod", 1, scope="model"),
                          MP.effect("ap_mod", 1, scope="model",
                                    conditions={"range_within": 12})],
                 conditions={"attack": "shooting", "action": "hold"})
assert MP.check(drill, reg) == []
assert MP.describe(drill, reg) == [
    "when attack Shooting and using Hold actions",
    "- +1 to hit rolls on its own attacks (this model only)",
    '- AP +1 on its own attacks (this model only) if target within 12"']
aura = MP.entry(effects=[MP.effect("grant_rule", {"rule": core["Stealth"]},
                                   scope="unit")])
assert MP.check(aura, reg) == []
assert MP.describe(aura, reg) == ["- gives Stealth (this model and its unit)"]
assert MP.describe(MP.entry(effects=[MP.effect("defense_mod", 1,
                                               side="defender")]), reg) == \
    ["- +1 to Defense rolls on attacks against its unit"]
assert MP.describe(MP.entry("no_combat_effect"), reg) == ["no combat effect"]
assert MP.check(MP.entry("native:fearless"), reg) == \
    ["behaves as: no such native rule"]           # needs behaves_as
assert MP.check(MP.entry("magic"), reg)[0].startswith("impl must be one of")
assert any("unknown primitive" in x for x in MP.check(
    MP.entry(effects=[MP.effect("fly", 1)]), reg))
assert any("no entry" in x for x in MP.check(MP.entry(effects=[MP.effect(
    "grant_rule", {"rule": "nope"})]), reg))
assert any("unknown condition" in x for x in MP.check(MP.entry(effects=[
    MP.effect("hit_mod", 1)], conditions={"moon": True}), reg))
assert MP.check(MP.entry("no_combat_effect", effects=[MP.effect(
    "hit_mod", 1)]), reg) == ["no_combat_effect takes no effects"]
# registry.install refuses what validate refuses.
raises(ValueError, reg.install, "local-x-r1",
       dict(MP.entry(effects=[MP.effect("fly", 1)]), name="x",
            text_sha1="0" * 40))

# A local unit with the custom rule.
raw = LB.new_book("Drill Hall")
rule = LB.custom_rule(raw, "Firing Drill", "+1 to hit when holding.")
twin = LB.custom_rule(raw, "Twin", "As Fearless.", alias_of=core["Fearless"])
raises(LB.LocalBookError, LB.set_semantics, raw, twin["id"], drill)
e = LB.set_semantics(raw, rule["id"], drill)
assert e["name"] == "Firing Drill" and len(e["text_sha1"]) == 40
gun = LB.weapon("Gun", 24, 1, count=5)
uid = LB.put_unit(raw, LB.unit(raw, "Drillers", 5, 4, 4, 50, weapons=[gun],
                               rules=[LB.rule_ref(rule["id"],
                                                  "Firing Drill")]))
book = lib.put_local(raw)
assert reg.status(rule["id"]) == "ok"


def spec(setup, lib_=lib, b=None):
    a = SS.run(lib_.reg, SS.book_side(b or book, uid), SideSetup(),
               SS.book_side(lib_.books["synthetic00book01"], "uTroop1"),
               SideSetup(), setup, lib_.sreg)
    return a.rows[0].audit[0].spec


s = spec(Setup(distance=10))
assert (s.hit_mod, s.ap) == (1, 1)
s = spec(Setup(distance=18))
assert (s.hit_mod, s.ap) == (1, 0)
s = spec(Setup(distance=10, action="advance"))
assert (s.hit_mod, s.ap) == (0, 0)

# Text edited after mapping: 'changed'; semantics cleared: 'unmapped'.
LB.find_rule(raw, rule["id"])["description"] = "Now something else."
lib.put_local(raw)
assert reg.status(rule["id"]) == "changed"
LB.clear_semantics(raw, rule["id"])
lib.put_local(raw)
assert reg.status(rule["id"]) == "unmapped" and rule["id"] not in reg.entries
assert spec(Setup(distance=10)).hit_mod == 0

# Stored in the book file: a new library installs it again.
LB.set_semantics(raw, rule["id"], drill)
lib.put_local(raw)
lib2 = Library.load(testpaths.SYNTHETIC_DIR, local_dir=tmp.name)
assert lib2.reg.status(rule["id"]) == "ok" and not lib2.warnings
assert spec(Setup(distance=10), lib2, lib2.books[raw["uid"]]).hit_mod == 1

# A session copy of the book: installed when the rule is unknown, never
# over the live semantics.
lib3 = Library.load(testpaths.SYNTHETIC_DIR)
b3, note = lib3.adopt(raw)
assert "session's copy" in note and lib3.reg.status(rule["id"]) == "ok"
other = dict(raw, specialRules=[dict(r) for r in raw["specialRules"]])
LB.set_semantics(other, rule["id"], MP.entry(effects=[MP.effect(
    "hit_mod", -1)]))
other["name"] = "Drill Hall v2"
lib2.adopt(other)
assert lib2.reg.entries[rule["id"]].effects[0].value == 1

# A broken stored entry is reported, not installed.
LB.find_rule(raw, rule["id"])[LB.SEM_KEY]["effects"][0]["primitive"] = "fly"
LB.save(raw, tmp.name)
lib4 = Library.load(testpaths.SYNTHETIC_DIR, local_dir=tmp.name)
assert rule["id"] not in lib4.reg.entries
assert any("unknown primitive" in w for w in lib4.warnings)
tmp.cleanup()
print("mapper: OK")
