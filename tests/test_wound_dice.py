"""Ravage and Crossing Attack as wound-dice weapons
(data.rule_weapons, handler wound_dice)."""
import random
from dataclasses import replace
from fractions import Fraction as F

import testpaths                                    # noqa: F401 (sys.path)
from grimdarkoracle.data import rule_weapons as RW
import dice_resolve as DR
from grimdarkoracle.engine import gf_math as G
from grimdarkoracle.engine import melee
from grimdarkoracle.engine import pmf as P
from grimdarkoracle.engine.context import AttackContext as Ctx
from grimdarkoracle.engine.melee import MeleeSetup
from grimdarkoracle.engine.modifiers import build_plan
from grimdarkoracle.engine.specs import AttackSpec, TargetSpec
from unitkit import REG, R, W, unit


def armed(cb):
    """The Combatant with the weapons its rules give (resolve() does it)."""
    return replace(cb, models=tuple(replace(c, model=RW.add(c.model))
                                    for c in cb.models))


def plan(att, tgt, **ctx):
    return build_plan(REG, att, tgt, Ctx(**ctx))


def group(p, name):
    return next((g for g in p.groups if g.weapon.name == name), None)


# --- the weapons ---------------------------------------------------------------
rav = armed(unit(1, rules=[R("Ravage", 3), R("Furious"), R("Precise")]))
w0 = rav.models[0].model.weapons[0][0]
assert (w0.name, w0.range, w0.attacks) == ("Ravage", 0, 3)
cross = armed(unit(1, rules=[R("Crossing Attack", 2)]))
assert cross.models[0].model.weapons[-1][0].name == "Crossing Attack"

# --- the plan: 6+ with no modifier, no Defense roll ---------------------------------
g = group(plan(rav, unit(), attack="melee", action="charge"), "Ravage")
assert (g.spec.attacks, g.spec.quality, g.spec.hit_mod, g.spec.no_block,
        g.spec.extra_hits_on_6) == (3, 6, 0, True, 0)
p = plan(replace(rav, fatigued=True), unit(), attack="melee", action="charge")
assert group(p, "Ravage") is None and any("Fatigued" in why for _n, why, _m
                                          in p.excluded)
assert group(plan(replace(rav, shaken=True), unit(), attack="melee",
                  action=None), "Ravage") is None     # strikes as Fatigued
assert group(plan(rav, unit()), "Ravage") is None     # shooting
assert group(plan(cross, unit()), "Crossing Attack") is None
c = group(plan(cross, unit(), crossing=True, distance=1), "Crossing Attack")
assert c.spec.no_block and c.spec.attacks == 2

# --- the maths -------------------------------------------------------------------------
spec = AttackSpec(3, quality=6, no_block=True)
assert G.hit_wounds(spec, TargetSpec(defense=2), False, True) == [0, 1]
assert P.trim(G.weapon_law(spec, TargetSpec(defense=2), 10, True).gross) == \
    P.binomial(3, F(1, 6))
regen = G.weapon_law(spec, TargetSpec(regeneration=True), 10, True).gross
assert P.trim(regen) == P.binomial(3, F(1, 6) * F(2, 3))
H = ()
bare = armed(unit(1, H, rules=[R("Ravage", 3)]))
for tgt in (unit(10, H, d=2), unit(10, H, d=2, rules=[R("Parry", 1)])):
    res = melee.resolve(MeleeSetup(REG, bare, tgt, strike_back=False),
                        exact=True)
    assert P.trim(res.defender().killed()) == P.binomial(3, F(1, 6))
# with real hits in the phase, Parry ignores hits, never the Ravage wounds:
# the losses are Ravage's law convolved with the claws' (Parry applied)
claws = (W("Claws", 0, 2),)
par = unit(10, H, d=2, rules=[R("Parry", 2)])
both = melee.resolve(MeleeSetup(REG, armed(unit(1, claws, rules=[
    R("Ravage", 3)])), par, strike_back=False), exact=True)
alone = melee.resolve(MeleeSetup(REG, unit(1, claws), par,
                                 strike_back=False), exact=True)
assert P.trim(both.defender().killed()) == P.trim(P.convolve(
    P.binomial(3, F(1, 6)), alone.defender().killed()))
rng = random.Random(4)
assert DR.roll_blocks(spec, TargetSpec(defense=2), 2, 1, rng) == (1, 1, 1)

print("test_wound_dice OK")
