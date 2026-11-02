"""Unpredictable, Unpredictable Fighter / Shooter and their
auras: one die per unit and attack; the Analyzer mixes the outcomes
exactly."""
from fractions import Fraction as F

import testpaths                                    # noqa: F401 (sys.path)
from grimdarkoracle.app import analyzer_core as AC
from grimdarkoracle.app import unpredictable as UP
from grimdarkoracle.engine import pmf as P
from grimdarkoracle.engine.context import AttackContext as Ctx
from grimdarkoracle.engine.melee import CHARGE, STRIKE_BACK
from grimdarkoracle.engine.modifiers import build_plan
from unitkit import IDS, REG, R, cm, resolved, unit

UF, US, UN = (IDS[n] for n in ("Unpredictable Fighter",
                               "Unpredictable Shooter", "Unpredictable"))


def first(att, tgt, weapon="Rifle", **ctx):
    return next(g for g in build_plan(REG, att, tgt, Ctx(**ctx)).groups
                if g.weapon.name == weapon)


# --- which rules roll, and what each face gives ------------------------------
fighter, shooter = unit(rules=[R("Unpredictable Fighter")]), \
    unit(rules=[R("Unpredictable Shooter")])
assert UP.menus(REG, fighter, unit(), Ctx()) == []
assert UP.menus(REG, fighter, unit(), CHARGE) == \
    [(UF, "Unpredictable Fighter", (3, 3))]
assert UP.menus(REG, fighter, unit(), STRIKE_BACK)          # its strike back
assert UP.menus(REG, shooter, unit(), CHARGE) == []
assert UP.menus(REG, unit(rules=[R("Unpredictable")]), unit(), Ctx())
aura = unit(4, extra=(cm(rules=[R("Unpredictable Shooter Aura")]),))
assert UP.menus(REG, aura, unit(), Ctx())[0][0] == US
assert first(shooter, unit(), versatile=((US, 0),)).spec.ap == 1
assert first(shooter, unit(), versatile=((US, 1),)).spec.hit_mod == 1
g = first(shooter, unit())                            # no die: nothing
assert (g.spec.ap, g.spec.hit_mod) == (0, 0)
assert first(aura, unit(), versatile=((US, 0),)).models == (0, 1, 2, 3, 4)
two = UP.outcomes(UP.menus(REG, fighter, unit(), CHARGE) * 2)
assert [p for p, _c in two] == [F(1, 4)] * 4

# --- Analyzer: the exact mixture ---------------------------------------------------
# One rifle shot at D5: AP(+1) -> 1/2 * 5/6 = 5/12; +1 to hit -> 2/3 * 4/6 =
# 4/9; each with probability 1/2: 31/72.
att = AC.Side(resolved(unit(1, rules=[R("Unpredictable Shooter")])))
tgt = AC.Side(resolved(unit(5, d=5)))
an = AC.analyse(REG, att, tgt, AC.Options(Ctx(distance=12), exact=True))
assert P.trim(an.def_losses.killed) == [F(41, 72), F(31, 72)]
assert P.trim(an.rows[0].hits) == [F(5, 12), F(7, 12)]
assert len(an.rows[0].audit) == 2                     # both outcomes shown
assert any("mixes every die outcome" in w for w in an.warnings)
assert an.opts.ctx.versatile == ()                    # the user's options
fixed = AC.analyse(REG, att, tgt, AC.Options(
    Ctx(distance=12, versatile=((US, 1),)), exact=True))
assert P.trim(fixed.def_losses.killed) == [F(5, 9), F(4, 9)]
assert not any("mixes" in w for w in fixed.warnings)
# Melee: both units roll (4 outcomes); the charged unit's losses come from
# the charger's die only.
f1 = AC.Side(resolved(unit(1, rules=[R("Unpredictable Fighter")])))
f2 = AC.Side(resolved(unit(2, d=5, rules=[R("Unpredictable Fighter")])))
mel = AC.analyse(REG, f1, f2, AC.Options(CHARGE, exact=True))
assert P.trim(mel.def_losses.killed) == [F(41, 72), F(31, 72)]
assert sum(mel.att_losses.killed) == 1 and sum(mel.def_losses.killed) == 1
w = mel.winner
assert w.charger + w.charged + w.none == 1
# the charged unit's own die, in its strike back (a charger with no melee
# weapon: the target strikes back whole, one attack at the D5 charger)
bare = AC.Side(resolved(unit(3, (), d=5)))
one = AC.Side(resolved(unit(1, rules=[R("Unpredictable Fighter")])))
sb = AC.analyse(REG, bare, one, AC.Options(CHARGE, exact=True))
assert P.trim(sb.att_losses.killed) == [F(41, 72), F(31, 72)]
# numbers mix too: a lone D5 target is destroyed on 31/72
lone = AC.analyse(REG, att, AC.Side(resolved(unit(1, d=5))),
                  AC.Options(Ctx(distance=12), exact=True))
assert lone.def_losses.destroyed == F(31, 72)
assert lone.rows[0].destroyed == F(31, 72)
nb = AC.analyse(REG, f1, f2, AC.Options(CHARGE, strike_back=False,
                                        exact=True))
assert P.trim(nb.def_losses.killed) == P.trim(mel.def_losses.killed)


print("test_unpredictable OK")
