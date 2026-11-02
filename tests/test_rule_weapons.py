"""Takedown Strike / Shot as Limited weapons of the model
(data.rule_weapons); Caster Group and Spell Conduit
(app.spells)."""
from fractions import Fraction as F

import testpaths
from grimdarkoracle.app import spells as SP
from grimdarkoracle.data import rule_weapons as RW
from grimdarkoracle.engine.context import AttackContext as Ctx
from grimdarkoracle.engine.modifiers import build_plan
from unitkit import CCW, REG, RIFLE, R, W, model, resolved, unit


def groups(att, tgt, **ctx):
    return {g.weapon.name: g for g in
            build_plan(REG, att, tgt, Ctx(**ctx)).groups}


# --- the weapons -------------------------------------------------------------
strike = RW.add(model(rules=[R("Takedown Strike", 2)]))
w = strike.weapons[-1][0]
assert (w.name, w.range, w.attacks, w.count) == ("Takedown Strike", 0, 2, 1)
assert [r.label for r in w.rules] == ["Reliable", "AP(2)", "Deadly(3)",
                                      "Takedown", "Limited"]
assert RW.add(strike) == strike                       # idempotent
pistol = W("Pistol", 12, 1)
shot = RW.add(model(weapons=(RIFLE, pistol, CCW),
                    rules=[R("Takedown Shot", 1)]))
assert shot.weapons[-1][0].range == 24                # the longest range
assert RW.add(model(weapons=(CCW,), rules=[R("Takedown Shot", 1)])) == \
    model(weapons=(CCW,), rules=[R("Takedown Shot", 1)])   # no ranged
u = resolved(unit(2, rules=[R("Takedown Strike", 1)]))
assert all(m.weapons[-1][0].name == "Takedown Strike"
           for m in RW.add_all(u).models)

# --- in the plan: Quality 2+, AP(2), Deadly(3), Takedown, Limited ---------------
def fielded(cm_model, n=1):
    from grimdarkoracle.engine.context import CombatModel, Combatant
    return Combatant("u", tuple(CombatModel(cm_model, 4, 4)
                                for _ in range(n)))


g = groups(fielded(strike), unit(), attack="melee", action="charge")[
    "Takedown Strike"]
assert (g.spec.quality, g.spec.ap, g.spec.deadly, g.spec.attacks) == \
    (2, 2, 3, 2)
assert g.takedown and g.limited
assert "Takedown Shot" in groups(fielded(shot), unit(), distance=20)
assert "Takedown Shot" not in groups(fielded(shot), unit(), distance=30)
assert "Takedown Strike" not in groups(fielded(strike), unit(), distance=1)

# --- through resolve(), on the real book when present ---------------------------
if not testpaths.USING_SYNTHETIC:
    from grimdarkoracle.app.library import Library
    lib = Library.load(testpaths.DATA_DIR)
    book = next(b for b in lib.books.values()
                if b.name == "Human Inquisition")
    from grimdarkoracle.data.resolve import resolve
    uid = next(k for k, x in book.units.items()
               if x.name == "Surveillance Ministry Assassin")
    names = [w.name for w, _n in resolve(book, uid, ()).models[0].weapons]
    assert "Takedown Shot" in names, names

# --- Caster Group -------------------------------------------------------------
grp = resolved(unit(3, rules=[R("Caster Group")]))
assert SP.caster_group(REG, grp) == 3 and SP.caster_rating(REG, grp) == 3
assert SP.caster_rating(REG, resolved(unit(3))) == 0
# --- Spell Conduit ------------------------------------------------------------
mage = resolved(unit(1, rules=[R("Caster", 2)]))
assert SP.cast_prob(REG, mage, exact=True) == F(1, 2)
assert SP.cast_prob(REG, mage, exact=True, conduit=True) == F(2, 3)

print("test_rule_weapons OK")
