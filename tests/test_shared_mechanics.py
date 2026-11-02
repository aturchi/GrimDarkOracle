"""new mechanics for the shared rules, against closed forms.

Unique Hero, wards (Spell Resistance, Protected, Plaguebound),
Pierce, Heavy Impact and Ranged Shrouding."""
import random
from fractions import Fraction as F
from types import SimpleNamespace as NS

import testpaths                                    # noqa: F401 (sys.path)
from grimdarkoracle.data import force_org
from grimdarkoracle.data.list_resolve import is_hero, is_unique
import dice_resolve as DR
from grimdarkoracle.engine import gf_math as G
from grimdarkoracle.engine import melee
from grimdarkoracle.engine import pmf as P
from grimdarkoracle.engine.context import AttackContext as Ctx
from grimdarkoracle.engine.melee import MeleeSetup
from grimdarkoracle.engine.modifiers import build_plan
from grimdarkoracle.engine.specs import AttackSpec, TargetSpec
from unitkit import REG, R, W, cm, resolved, unit


def plan(att, tgt, **ctx):
    return build_plan(REG, att, tgt, Ctx(**ctx))


def one(att, tgt, weapon="Rifle", **ctx):
    gs = [g for g in plan(att, tgt, **ctx).groups if g.weapon.name == weapon]
    assert len(gs) == 1, gs
    return gs[0]


def minority(rule, n=2, others=3):
    return unit(n, rules=[R(rule)], extra=unit(others).models)


# --- Unique Hero -------------------------------------------------------
uh = resolved(unit(1, rules=[R("Unique Hero"), R("Tough", 3)]), name="UH")
hero = resolved(unit(1, rules=[R("Hero"), R("Tough", 3)]), name="H")
assert is_hero(uh) and is_unique(uh) and is_hero(hero) and not is_unique(hero)
assert not is_hero(resolved(unit(5)))


def fo_check(units, force=False):
    army = NS(points_limit=2000, force_org=force,
              units=[NS(key=str(k), book="bk") for k in range(len(units))])
    result = NS(points=0, entries={str(k): NS(unit=u)
                                   for k, u in enumerate(units)})
    return force_org.check(army, result)


v = fo_check([uh, uh])
assert [x.kind for x in v] == ["unique"] and not v[0].force_org
assert v[0].keys == ("0", "1")
assert fo_check([uh]) == [] and fo_check([hero, hero]) == []
assert [x.kind for x in fo_check([uh, uh], force=True)] == ["unique"]

# --- wards -------------------------------------------------------------
# One wound event: a 6+ ward lets 5/6 through, Regeneration (5+) 4/6, both
# 4/6 * 5/6; "ignores Regeneration" keeps the ward; Deadly(3) rolls for each.
spec = AttackSpec(1)
assert G.event_wounds(spec, TargetSpec(wards=(6,)), True) == [F(1, 6), F(5, 6)]
both = TargetSpec(regeneration=True, wards=(6,))
assert G.event_wounds(spec, both, True)[1] == F(4, 6) * F(5, 6)
bane = AttackSpec(1, ignores_regen=True)
assert G.event_wounds(bane, both, True)[1] == F(5, 6)
deadly = AttackSpec(1, deadly=3)
assert G.event_wounds(deadly, TargetSpec(wards=(2,)), True) == \
    P.binomial(3, F(1, 6))
assert G.event_wounds(spec, TargetSpec(wards=(6, 6)), True)[1] == F(25, 36)

# Plan: who holds a ward, shooting vs spell, majority, aura
assert one(unit(), unit(rules=[R("Protected")])).target.wards == (6,)
assert one(unit(), unit(rules=[R("Plaguebound")])).target.wards == (6,)
sr = unit(rules=[R("Spell Resistance")])
assert one(unit(), sr).target.wards == (6,)
assert one(unit(), sr, "Hand Weapon", attack="melee").target.wards == (6,)
assert one(unit(), sr, attack="spell").target.wards == (2,)
assert one(unit(), minority("Protected")).target.wards == ()
sra = unit(4, extra=(cm(rules=[R("Spell Resistance Aura")]),))
assert one(unit(), sra).target.wards == (6,)
rp = one(unit(weapons=[W("Gun", 24, 1, R("Anti-Regen"))]),
         unit(rules=[R("Regeneration"), R("Protected")]), "Gun")
assert rp.spec.ignores_regen and rp.target.regeneration and \
    rp.target.wards == (6,)

# Dice oracle (tests/dice_resolve): one wound event through a 2+ ward survives on 1/6
rng = random.Random(7)
n = 12000
through = sum(DR.roll_event(spec, TargetSpec(wards=(2,)), rng)
              for _ in range(n))
sd = (n * F(1, 6) * F(5, 6)) ** 0.5
assert abs(through - n / 6) < 4 * sd, through

# --- Pierce ------------------------------------------------------------
pierce = unit(weapons=[W("Gun", 24, 1, R("Pierce"))])
shielded = unit(rules=[R("Shielded")])
g = one(pierce, shielded, "Gun", cover="terrain", distance=12)
assert (g.target.defense_mod, g.spec.ap) == (0, 0)  # cover and Shielded gone
g = one(pierce, shielded, "Gun", distance=13)        # over half of 24"
assert (g.target.defense_mod, g.spec.ap) == (0, 1)
assert one(unit(), shielded, cover="terrain").target.defense_mod == 2
armor = unit(rules=[R("Armor", 3)])
assert one(pierce, armor, "Gun").target.defense == 3     # Armor is not a mod
fort = one(pierce, unit(rules=[R("Fortified")]), "Gun", distance=13)
assert fort.spec.ap == 0                                 # AP(+1) - Fortified

# --- Ranged Shrouding --------------------------------------------------
rs = unit(rules=[R("Ranged Shrouding")])
for wr, eff in ((24, 20), (8, 6), (10, 6), (6, 6), (4, 4)):
    assert one(unit(weapons=[W("Gun", wr, 1)]), rs, "Gun",
               distance=eff).spec is not None, (wr, eff)
    assert not plan(unit(weapons=[W("Gun", wr, 1)]), rs,
                    distance=eff + 1).groups, (wr, eff)
assert plan(unit(weapons=[W("Gun", 24, 1)]), minority("Ranged Shrouding"),
            distance=24).groups
rsa = unit(4, extra=(cm(rules=[R("Ranged Shrouding Aura")]),))
assert not plan(unit(weapons=[W("Gun", 24, 1)]), rsa, distance=21).groups
assert plan(unit(weapons=[W("Gun", 24, 1, R("Unstoppable"))]), rs,
            distance=24).groups
assert plan(unit(), rs, attack="melee", action="charge").groups  # melee

# --- Heavy Impact ------------------------------------------------------
H = ()                                              # no melee weapons
heavy = unit(1, H, rules=[R("Heavy Impact", 3)])
st = MeleeSetup(REG, heavy, unit(10, H))
(sp, tg), = st.impacts((0,), (0,) * 10)
assert (sp.attacks, sp.quality, sp.ap) == (3, 2, 1)
# D4 at AP(1): blocks on 5+, each die wounds on 5/6 * 4/6 = 5/9
res = melee.resolve(MeleeSetup(REG, heavy, unit(10, H), strike_back=False),
                    exact=True)
assert P.trim(res.defender().killed()) == P.binomial(3, F(5, 9))
# Fortified takes the AP back: 5/6 * 1/2
res = melee.resolve(MeleeSetup(REG, heavy, unit(10, H, rules=[R("Fortified")]),
                               strike_back=False), exact=True)
assert P.trim(res.defender().killed()) == P.binomial(3, F(5, 12))
# Mixed pools: Heavy Impact(3) and Impact(2) models; Brace(2) removes the
# AP(1) dice first -> 1 die at AP(1), 2 at AP(0)
mixed = unit(1, H, rules=[R("Heavy Impact", 3)],
             extra=(cm(H, rules=[R("Impact", 2)]),))
st = MeleeSetup(REG, mixed, unit(10, H))
assert st.impact_pools((0, 0)) == ((1, 3), (0, 2))
braced = unit(10, H, rules=[R("Brace", 2)])
st = MeleeSetup(REG, mixed, braced, strike_back=False)
assert st.impact_pools((0, 0)) == ((1, 1), (0, 2))
assert st.impact_dice((0, 0)) == 3
res = melee.resolve(st, exact=True)
assert P.trim(res.defender().killed()) == P.trim(P.convolve(
    P.binomial(1, F(5, 9)), P.binomial(2, F(5, 12))))
# a model with both sources uses the one with the highest X
both = unit(1, H, rules=[R("Impact", 4), R("Heavy Impact", 2)])
assert MeleeSetup(REG, both, unit(10, H)).impact_pools((0,)) == ((0, 4),)

print("test_shared_mechanics OK")
