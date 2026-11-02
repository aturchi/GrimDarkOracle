"""Scourge, every unmodified block 1 counts 2 extra wounds in the
melee result (exact joint law) and, reading (b), triggers the shooting
Morale Test of a unit at half or less."""
from fractions import Fraction as F

import testpaths                                    # noqa: F401 (sys.path)
from grimdarkoracle.app import analyzer_core as AC
import dice_resolve as DR
from grimdarkoracle.engine import melee
from grimdarkoracle.engine import scourge as SC
from grimdarkoracle.engine.context import AttackContext as Ctx
from grimdarkoracle.engine.melee import MeleeSetup
from grimdarkoracle.engine.morale import Morale, melee_winner
from grimdarkoracle.engine.specs import AttackSpec, TargetSpec
from unitkit import REG, R, W, resolved, unit

H, CLAW = (), (W("Claw", 0, 1),)

# --- one hit -------------------------------------------------------------------
spec = AttackSpec(1, scourge=2)
assert SC.hit_pairs(spec, TargetSpec(), False, True) == \
    {(0, 0): F(1, 2), (1, 0): F(1, 3), (1, 1): F(1, 6)}
shred = AttackSpec(1, scourge=2, shred=1)
assert SC.hit_pairs(shred, TargetSpec(), False, True)[(2, 1)] == F(1, 6)


# --- the melee result ------------------------------------------------------------
def winner(att, dfn):
    st = MeleeSetup(REG, att, dfn)
    res = melee.resolve(st, exact=True)
    return st, melee_winner(Morale(REG, att), Morale(REG, dfn), res)


# The charger's one claw (hit 1/2); the charged unit's Fear(2) makes the
# charger "take" 2: it loses unless the target took 3 = 1 wound + 2 for a
# block 1 (1/2 * 1/6 = 1/12).
sc = unit(1, CLAW, rules=[R("Scourge")])
big = unit(1, H, rules=[R("Tough", 9), R("Fear", 2)])
st, w = winner(sc, big)
assert st.scourge and (w.charger, w.charged, w.none) == (F(1, 12),
                                                         F(11, 12), 0)
_st, w = winner(unit(1, CLAW), big)                   # no Scourge
assert (w.charger, w.charged) == (0, 1)
# the charged unit's Scourge in its strike back counts for the charger
tank = unit(1, H, rules=[R("Tough", 9), R("Fear", 2)])
_st, w = winner(tank, unit(1, CLAW, rules=[R("Scourge")]))
assert (w.charged, w.charger) == (F(1, 12), F(11, 12))
# the states' law is the plain one (the counts only change the result)
plain = melee.resolve(MeleeSetup(REG, unit(1, CLAW), big), exact=True)
assert melee.resolve(st, exact=True).dist == plain.dist

# --- shooting, reading (b) ----------------------------------------------------------
# A D4 target with Regeneration, one of its two models dead: a block 1 whose
# wound is regenerated (1/2 * 1/6 * 1/3) still triggers the test.
gun = resolved(unit(1, (W("Gun", 24, 1),), rules=[R("Scourge")]))
tgt = AC.Side(resolved(unit(2, H, rules=[R("Regeneration")])), None,
              (1, 0))
an = AC.analyse(REG, AC.Side(gun), tgt, AC.Options(Ctx(distance=12),
                                                   exact=True))
assert an.def_losses.morale.test == F(1, 36)
no = AC.analyse(REG, AC.Side(resolved(unit(1, (W("Gun", 24, 1),)))), tgt,
                AC.Options(Ctx(distance=12), exact=True))
assert no.def_losses.morale.test == 0


# --- dice oracle (tests/dice_resolve) -----------------------------------------------------------
class Dice:
    def __init__(self, *v):
        self.v = list(v)

    def randint(self, lo, hi):
        return self.v.pop(0) if self.v else 6


roll = DR.roll_weapon(AttackSpec(1, scourge=2), TargetSpec(), 1, Dice(4, 1))
assert roll.events == (1,) and roll.extra == 2
assert DR.roll_weapon(AttackSpec(1, scourge=2), TargetSpec(), 1,
                      Dice(4, 2)).extra == 0
print("test_scourge OK")
