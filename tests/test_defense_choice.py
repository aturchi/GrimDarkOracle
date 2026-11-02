"""charge distance and Ambush inputs, Changebound, Warbound,
Ambushing Piercing Shot, Versatile Defense with the target's best pick
(app.defense_choice) in both programs."""
from fractions import Fraction as F

import testpaths                                    # noqa: F401 (sys.path)
from grimdarkoracle.app import analyzer_core as AC
from grimdarkoracle.app import defense_choice as DC
from grimdarkoracle.app import session_io as SIO
from grimdarkoracle.app.setup_model import Setup
from grimdarkoracle.engine import kill_chain as K
from grimdarkoracle.engine.context import AttackContext as Ctx
from grimdarkoracle.engine.modifiers import build_plan
from grimdarkoracle.engine.sequence import AttackSequence
from unitkit import IDS, REG, R, cm, resolved, unit

VD = IDS["Versatile Defense"]


def plan(att, tgt, **ctx):
    return build_plan(REG, att, tgt, Ctx(**ctx))


def one(att, tgt, weapon="Rifle", **ctx):
    gs = [g for g in plan(att, tgt, **ctx).groups if g.weapon.name == weapon]
    assert len(gs) == 1, gs
    return gs[0]


def charge(att, tgt, **ctx):
    return one(att, tgt, "Hand Weapon", attack="melee", action="charge",
               **ctx)


def back(att, tgt):
    """Strike back after a long charge: never 'a charge from over 6"'."""
    return one(att, tgt, "Hand Weapon", attack="melee", action=None,
               charge_distance=12)


# --- Changebound: -1 to hit when shot from over 9" / charged from over 6" ----
cb = unit(rules=[R("Changebound")])
assert one(unit(), cb, distance=10).spec.hit_mod == -1
assert one(unit(), cb, distance=9).spec.hit_mod == 0
assert charge(unit(), cb, charge_distance=7).spec.hit_mod == -1
assert charge(unit(), cb).spec.hit_mod == 0           # default 6": no effect
assert back(unit(), cb).spec.hit_mod == 0             # strike back
assert one(unit(), cb, distance=5, charge_distance=12).spec.hit_mod == 0
mixed = unit(2, rules=[R("Changebound")], extra=unit(3).models)
assert one(unit(), mixed, distance=10).spec.hit_mod == 0

# --- Warbound: the holder's attacks, Shred-like ------------------------------
wb = unit(rules=[R("Warbound")])
assert one(wb, unit(), distance=10).spec.shred == 1
assert one(wb, unit(), distance=9).spec.shred == 0
assert charge(wb, unit(), charge_distance=7).spec.shred == 1
assert charge(wb, unit(), charge_distance=6).spec.shred == 0

# --- Ambushing Piercing Shot -------------------------------------------------
aps = unit(rules=[R("Ambushing Piercing Shot")])
assert one(aps, unit(), ambushed=True).spec.ap == 1
assert one(aps, unit()).spec.ap == 0
assert charge(aps, unit(), ambushed=True).spec.ap == 0   # shooting only

# --- Versatile Defense: the target's menu -----------------------------------
vd = unit(rules=[R("Versatile Defense")])
assert DC.menus(REG, vd, unit(), Ctx(distance=9)) == []
assert DC.menus(REG, vd, unit(), Ctx(distance=10)) == \
    [(VD, "Versatile Defense", ["+1 Defense", "-1 to hit"])]
assert DC.menus(REG, vd, unit(), Ctx(distance=9), check=False)
assert DC.menus(REG, unit(4, extra=(cm(rules=[R("Versatile Defense Aura")]),)),
                unit(), Ctx(distance=10))
g0 = one(unit(), vd, distance=10, versatile=((VD, 0),))
g1 = one(unit(), vd, distance=10, versatile=((VD, 1),))
assert (g0.target.defense_mod, g0.spec.hit_mod) == (1, 0)
assert (g1.target.defense_mod, g1.spec.hit_mod) == (0, -1)
gn = one(unit(), vd, distance=10)                     # no pick: nothing
assert (gn.target.defense_mod, gn.spec.hit_mod) == (0, 0)
assert one(unit(), vd, distance=9, versatile=((VD, 0),)).target.defense_mod \
    == 0
assert charge(unit(), vd, charge_distance=8,
              versatile=((VD, 1),)).spec.hit_mod == -1


# --- the best pick, closed forms -----------------------------------------------
def evaluate(att, tgt):
    def run(c):
        ch = K.resolve(AttackSequence(REG, att, tgt, c), None, exact=True)
        return DC.mean(ch.killed()), ch.destroyed()
    return run


# Defense 2+: +1 Defense changes nothing (a 1 always fails), so -1 to hit
d2 = unit(rules=[R("Versatile Defense")], d=2)
ctx, notes = DC.pick(REG, d2, unit(), Ctx(distance=10), evaluate(unit(), d2))
assert dict(ctx.versatile)[VD] == 1 and "-1 to hit" in notes[0]
assert evaluate(unit(), d2)(ctx)[0] == 5 * F(1, 3) * F(1, 6)
# Quality 6+: -1 to hit changes nothing (a 6 always hits), so +1 Defense
q6 = unit(q=6)
ctx, notes = DC.pick(REG, vd, q6, Ctx(distance=10), evaluate(q6, vd))
assert dict(ctx.versatile)[VD] == 0 and "+1 Defense" in notes[0]
assert evaluate(q6, vd)(ctx)[0] == 5 * F(1, 6) * F(1, 3)
# a choice already made is kept; within 9" nothing to pick
c = Ctx(distance=10, versatile=((VD, 0),))
assert DC.pick(REG, d2, unit(), c, evaluate(unit(), d2)) == (c, [])
c = Ctx(distance=9)
assert DC.pick(REG, d2, unit(), c, evaluate(unit(), d2)) == (c, [])

# --- Analyzer: the pick is in the warnings and in the options --------------
att, tgt = AC.Side(resolved(unit())), AC.Side(resolved(d2))
an = AC.analyse(REG, att, tgt, AC.Options(Ctx(distance=10), exact=True))
assert any("best for the target" in w for w in an.warnings)
assert dict(an.opts.ctx.versatile)[VD] == 1
fixed = AC.analyse(REG, att, tgt, AC.Options(
    Ctx(distance=10, versatile=((VD, 0),)), exact=True))
assert not any("best for the target" in w for w in fixed.warnings)
assert DC.mean(fixed.def_losses.killed) > DC.mean(an.def_losses.killed)
mel = AC.analyse(REG, att, tgt, AC.Options(
    Ctx("melee", action="charge", charge_distance=8), exact=True))
assert any("-1 to hit" in w for w in mel.warnings)

# --- Setup and sessions -----------------------------------------------------
s = Setup(attack="melee", charge_distance=9, ambushed=True)
assert s.context().charge_distance == 9 and s.context().ambushed
assert Setup(ambushed=True).context().ambushed
assert s.relevant("charge_distance") and not Setup().relevant(
    "charge_distance")
assert SIO._setup_from(SIO._setup_dict(s)) == s
assert SIO._setup_from({}) == Setup()                 # older sessions

print("test_defense_choice OK")
