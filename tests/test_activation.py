"""Activation bars: the Shaken flag set by the user and the
permanent action limits of Immobile, Cumbersome and Aircraft, in the
modifier layer, the melee exchange and the Analyzer. Hand-built units
with real rule ids (no book needed)."""
from fractions import Fraction

import testpaths                                    # noqa: F401 (sys.path)
from unitkit import R, W, RIFLE, CCW, REG, unit, ctx, resolved
from grimdarkoracle.app import analyzer_core as AC
from grimdarkoracle.app.spells import SpellPlan
from grimdarkoracle.engine import melee as ML
from grimdarkoracle.engine.modifiers import activation_bar, build_plan

IMM, CUM, AIR = R("Immobile"), R("Cumbersome"), R("Aircraft")
IMPACT = (R("Impact", 3),)
SHOOT, ADV = ctx(), ctx(action="advance")
CHARGE, BACK = ctx(attack="melee", action="charge"), \
    ctx(attack="melee", action=None)


def bar(att, tgt, c):
    """Reason of the plan, checking that every weapon is then excluded."""
    p = build_plan(REG, att, tgt, c)
    assert p.barred == activation_bar(REG, att, tgt, c)
    if p.barred:
        assert not p.groups and p.excluded and \
            all(why == p.barred for _n, why, _m in p.excluded), p
    return p.barred


# The registry keeps list params as tuples (entries stay hashable).
sem = REG.lookup(IMM.id)
assert sem.handler == "action_limit" and dict(sem.params)["actions"] == \
    ("hold",)
hash(sem)

plain, tgt = unit(3), unit(5)
assert bar(plain, tgt, SHOOT) is None and bar(plain, tgt, ADV) is None
assert bar(plain, tgt, CHARGE) is None

# Shaken: no shooting and no charge; strike back (action None) is allowed.
sh = unit(3, shaken=True)
assert bar(sh, tgt, SHOOT) == "Shaken: must stay idle"
assert bar(sh, tgt, CHARGE) == "Shaken: must stay idle"
assert bar(sh, tgt, BACK) is None
assert build_plan(REG, sh, tgt, BACK).groups

# Immobile: Hold only.
imm = unit(1, rules=(IMM,))
assert bar(imm, tgt, SHOOT) is None
assert bar(imm, tgt, ADV) == "Immobile: may only use Hold actions"
assert bar(imm, tgt, CHARGE) == "Immobile: may only use Hold actions"

# Cumbersome: Hold / Advance, no shooting when moving, no charge.
cum = unit(1, rules=(CUM,))
assert bar(cum, tgt, SHOOT) is None
assert bar(cum, tgt, ADV) == "Cumbersome: can't shoot when moving"
assert bar(cum, tgt, CHARGE) == \
    "Cumbersome: may only use Hold / Advance actions"

# Aircraft: Advance only; it cannot charge nor be charged; it can be shot.
air = unit(1, rules=(AIR,))
assert bar(air, tgt, SHOOT) == "Aircraft: may only use Advance actions"
assert bar(air, tgt, ADV) is None
assert bar(air, tgt, CHARGE) == "Aircraft: may only use Advance actions"
assert bar(plain, air, CHARGE) == "the target (Aircraft) can't be charged"
assert bar(plain, air, SHOOT) is None
# Its composed effects still apply: -1 to hit, -12" range.
g = build_plan(REG, plain, air, ctx(distance=12)).groups
assert g and g[0].spec.hit_mod == -1
assert build_plan(REG, plain, air, ctx(distance=13)).excluded
# One model with the limit is enough (the unit moves as one).
assert bar(unit(4, extra=unit(1, rules=(IMM,)).models), tgt, ADV)

# Melee: a barred charge is no exchange (no Impact, no strike back).
charger = unit(3, weapons=(CCW,), rules=IMPACT)
ok = ML.MeleeSetup(REG, charger, unit(4))
assert not ok.barred and ok.impact_dice(ok.a_alloc.fresh()) == 9
no = ML.MeleeSetup(REG, charger, unit(1, rules=(AIR,)))
assert no.barred and no.impact_dice(no.a_alloc.fresh()) == 0
res = ML.resolve(no, exact=True)
assert res.dist == {(no.a_alloc.fresh(), no.d_alloc.fresh()): 1}
for phase in ("counter", "strike", "back"):
    assert no.steps(phase, no.seq("def", (0,))) == []

# Analyzer: no rows, no Morale test (even with a tie option), reason first.
s_air = AC.Side(resolved(unit(1, weapons=(RIFLE, CCW), rules=(AIR,))))
s_ch = AC.Side(resolved(charger))
a = AC.analyse(REG, s_ch, s_air, AC.Options(CHARGE, tie="defender",
                                             exact=True))
assert a.rows == () and a.warnings[0] == \
    "no attack: the target (Aircraft) can't be charged"
assert a.att_losses.morale.test == 0 and a.def_losses.morale.test == 0
assert a.winner.none == 1
s_sh = AC.Side(resolved(unit(5)), shaken=True)
a = AC.analyse(REG, s_sh, AC.Side(resolved(unit(5))), AC.Options(exact=True))
assert a.rows == () and a.def_losses.destroyed == 0
assert a.warnings[0] == "no attack: Shaken: must stay idle"
assert {s.reason for s in a.skipped} == {"Shaken: must stay idle"}

# A Shaken caster casts nothing.
plan = SpellPlan("Bolt", W("Bolt", 18, 3), Fraction(1, 2))
spell = AC.Options(ctx(attack="spell"), spell=plan, exact=True)
target = AC.Side(resolved(unit(5)))
cast = AC.analyse(REG, AC.Side(resolved(unit(1))), target, spell)
idle = AC.analyse(REG, AC.Side(resolved(unit(1)), shaken=True), target,
                  spell)
assert cast.cast == Fraction(1, 2) and cast.def_losses.wounds[0] < 1
assert idle.cast == 0 and idle.def_losses.wounds[0] == 1
assert idle.warnings[0] == "no attack: Shaken: must stay idle"
print("activation: OK")
