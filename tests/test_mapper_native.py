"""Rules Mapper native behaviours: the natives offered (no Tough / Hero,
spells or custom rules), the copy (handler, parameters, effects), its checks
(no other numbers, no name-bound handler, a known native), the preview, the
refresh on load and the stored copy when the native is missing; then, for
every kind of native rule, a unit with a custom copy does EXACTLY what the
same unit with the official rule does: analyses (shooting, charge, as
attacker and target), activation bars, Caster rating, Versatile menu, Marks.
Synthetic data."""
import tempfile
from dataclasses import replace

import testpaths
from grimdarkoracle.app import side_spec as SS
from grimdarkoracle.app import spells as SP
from grimdarkoracle.app.library import Library
from grimdarkoracle.app.setup_model import Setup, SideSetup, versatile
from grimdarkoracle.data import local_books as LB
from grimdarkoracle.data.resolve import resolve
from grimdarkoracle.rules import mapper as MP

tmp = tempfile.TemporaryDirectory()
lib = Library.load(testpaths.SYNTHETIC_DIR, local_dir=tmp.name)
reg = lib.reg
core = {d.name: d.id for d in lib.core.values()}
nat = MP.natives(reg)

# --- what may be copied --------------------------------------------------------------------
assert "Tough" not in nat and "Hero" not in nat
assert {"Fear", "Fearless", "Caster", "Impact", "Immobile",
        "Piercing Shooting Mark", "Versatile Expert"} <= set(nat)
assert all(not k.startswith("spell:") and not LB.is_local(v)
           for k, v in nat.items())
fear = MP.native_entry(reg, nat["Fear"])
assert fear == {"impl": "native:fear", "behaves_as": nat["Fear"]}
assert MP.check(fear, reg) == []
fl = MP.native_entry(reg, nat["Fearless"])
assert fl["params"] == {"pass_on": 4} and MP.check(fl, reg) == []
im = MP.native_entry(reg, nat["Immobile"])
assert im["params"] == {"actions": ["hold"]}
psm = MP.native_entry(reg, nat["Piercing Shooting Mark"])
assert psm["effects"] and MP.check(psm, reg) == []
assert MP.describe(fl, reg)[:2] == [
    "behaves as Fearless (engine rule 'fearless'), with this rule's own "
    "name and rating", "- pass_on: 4"]
assert len(MP.describe(psm, reg)) > 1                # its effects too
# Refused: other numbers, effects or conditions; name-bound; unknown.
for bad, why in (
        (dict(fl, params={"pass_on": 3}), "keep its handler and numbers"),
        (dict(fear, conditions={"charging": True}), "keep its handler"),
        (dict(fear, effects=[MP.effect("hit_mod", 1)]), "keep its handler"),
        ({"impl": "native:tough", "behaves_as": core["Tough"]},
         "recognised by its name"),
        ({"impl": "native:hero", "behaves_as": core["Hero"]}, "alias"),
        ({"impl": "native:fear", "behaves_as": "nope"}, "no such native"),
        ({"impl": "native:fear"}, "no such native"),
        (dict(fl, impl="native:fear"), "keep its handler")):
    errs = MP.check(bad, reg)
    assert errs and why in errs[0], (bad, errs)
try:
    MP.native_entry(reg, core["AP"])                 # composed, not native
    raise AssertionError("accepted")
except ValueError:
    pass

# --- a local book: the official rule and its custom copy, side by side -----------------
raw = LB.new_book("Copies")
gun = LB.weapon("Gun", 24, 2, count=5)
blade = LB.weapon("Blade", 0, 2, count=5)
units: dict = {}


def pair(name, rating=None, on="unit", extra_weapons=()):
    """Units 'off:<name>' (official rule) and 'cus:<name>' (copy)."""
    rule = LB.custom_rule(raw, f"My {name}", f"Works as {name}.",
                          has_rating=rating is not None)
    LB.set_semantics(raw, rule["id"], MP.native_entry(reg, nat[name]))
    for tag, ref in (("off", LB.rule_ref(nat[name], name, rating)),
                     ("cus", LB.rule_ref(rule["id"], f"My {name}", rating))):
        weapons = [dict(gun), dict(blade)] + [dict(w) for w in extra_weapons]
        if on == "weapon":
            for w in weapons:
                w["specialRules"] = [ref]
        rules = [ref] if on == "unit" else []
        units[f"{tag}:{name}"] = LB.put_unit(raw, LB.unit(
            raw, f"{tag} {name}", 5, 4, 4, 100, weapons=weapons,
            rules=rules))
    return rule["id"]


CASES = [("Fear", 2, "unit"), ("Fearless", None, "unit"),
         ("Impact", 3, "unit"), ("Regeneration", None, "unit"),
         ("Brace", 2, "unit"), ("Parry", 1, "unit"),
         ("Immobile", None, "unit"), ("Cumbersome", None, "unit"),
         ("Aircraft", None, "unit"),
         ("Caster", 2, "unit"), ("Counter", None, "weapon"),
         ("Deadly", 3, "weapon"), ("Blast", 3, "weapon"),
         ("Takedown", None, "weapon"), ("Limited", None, "weapon"),
         ("Indirect", None, "weapon"), ("Assault", None, "weapon"),
         ("Versatile Expert", None, "unit"),
         ("Piercing Shooting Mark", None, "unit"),
         ("Precision Spotter", None, "unit")]
ids = {name: pair(name, rating, on) for name, rating, on in CASES}
units["plain"] = LB.put_unit(raw, LB.unit(raw, "plain", 5, 4, 4, 100,
                                          weapons=[dict(gun), dict(blade)]))
units["brute"] = LB.put_unit(raw, LB.unit(                 # Tough, Impact
    raw, "Brutes", 3, 4, 4, 120, weapons=[dict(blade, count=3)],
    rules=[LB.rule_ref(core["Tough"], "Tough", 3),
           LB.rule_ref(nat["Impact"], "Impact", 2)]))
book = lib.put_local(raw)
assert not lib.warnings
for rid in ids.values():
    assert reg.status(rid) == "ok"
assert not set(ids.values()) & set(MP.natives(reg).values())   # no copies
copy_of_copy = {"impl": "native:fear", "behaves_as": ids["Fear"]}
assert "cannot be copied" in MP.check(copy_of_copy, reg)[0]
FOES = (SS.book_side(lib.books["synthetic00book01"], "uTroop1"),
        SS.book_side(book, units["brute"]))
SETUPS = (Setup(distance=12), Setup(distance=12, action="advance"),
          Setup(attack="melee"), Setup(attack="melee", strike_back=False),
          Setup(distance=12, action="hold", cover="terrain"),
          Setup(distance=12, line_of_sight=False))


def outcome(spec, setup, as_target, foe):
    a, t = (foe, spec) if as_target else (spec, foe)
    try:
        r = SS.run(reg, a, SideSetup(), t, SideSetup(), setup, lib.sreg,
                   exact=True)
    except ValueError as exc:
        return ("refused", str(exc).replace("My ", ""))
    def bare(x):                                    # the unit's name aside
        return x if x is None else replace(x, name="")
    return (bare(r.def_losses), bare(r.att_losses), r.winner,
            tuple(s.reason.replace("My ", "") for s in r.skipped))


# Rules the Analyzer shows an effect of (against a plain unit) must
# show it with the copy too, in every case; the others are checked below.
ACTIVE = {"Fear", "Fearless", "Impact", "Regeneration", "Brace", "Parry",
          "Immobile", "Cumbersome", "Aircraft", "Counter", "Deadly", "Blast",
          "Takedown", "Indirect", "Assault"}
plain = SS.book_side(book, units["plain"])
for name, _r, _on in CASES:
    off = SS.book_side(book, units[f"off:{name}"])
    cus = SS.book_side(book, units[f"cus:{name}"])
    differs = False
    for foe in FOES:
        for setup in SETUPS:
            for as_target in (False, True):
                o = outcome(off, setup, as_target, foe)
                assert o == outcome(cus, setup, as_target, foe), \
                    (name, setup, as_target)
                differs |= o != outcome(plain, setup, as_target, foe)
    assert differs == (name in ACTIVE), name


def ru(name, tag):
    return resolve(book, units[f"{tag}:{name}"])


# Caster: same rating, so the same tokens and spells.
assert SP.caster_rating(reg, ru("Caster", "cus"), None) == \
    SP.caster_rating(reg, ru("Caster", "off"), None) == 2
# Versatile: the same menu, under the copy's own name.
vo, vc = versatile(reg, ru("Versatile Expert", "off")), \
    versatile(reg, ru("Versatile Expert", "cus"))
assert vc[0][1] == "My Versatile Expert" and vc[0][2] == vo[0][2]
# Analyzer Marks menu: the copy is offered under its own name.
from grimdarkoracle.app.setup_model import marks             # noqa: E402
assert (ids["Piercing Shooting Mark"], "My Piercing Shooting Mark") in \
    marks(reg)

# --- stored copy: refreshed on load, kept when the native is missing ----------------------
rid = ids["Fearless"]
stored = LB.find_rule(raw, rid)[LB.SEM_KEY]
stored["params"] = {"pass_on": 2}                  # a stale, other number
assert MP.refresh_native(stored, reg)["params"] == {"pass_on": 4}
assert MP.refresh_native(stored, reg)["name"] == "My Fearless"
LB.save(raw, tmp.name)
lib2 = Library.load(testpaths.SYNTHETIC_DIR, local_dir=tmp.name)
assert dict(lib2.reg.entries[rid].params) == {"pass_on": 4}
moved = dict(stored, impl="native:fear")            # the native changed kind
assert MP.refresh_native(moved, reg) is moved
orphan = dict(stored, behaves_as="gone-id")
assert MP.refresh_native(orphan, reg) is orphan     # stored copy used
assert MP.refresh_native({"impl": "composed"}, reg) == {"impl": "composed"}
tmp.cleanup()
print("mapper native: OK")
