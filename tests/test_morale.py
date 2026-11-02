"""engine.morale: half or less, Morale Test probability (Banner,
Bravery, Fearless, Hero Quality, Shaken), tests after shooting, melee
result with Fear and the tie options; exact closed forms in Fractions."""
from fractions import Fraction as F

from unitkit import R, W, CCW, RIFLE, REG, cm, unit, ctx
from grimdarkoracle.engine import kill_chain as K
from grimdarkoracle.engine import melee
from grimdarkoracle.engine.context import Combatant
from grimdarkoracle.engine.melee import MeleeSetup
from grimdarkoracle.engine.morale import (Morale, MoraleOutcome, after_melee,
                                          after_shooting, half_or_less)
from grimdarkoracle.engine.sequence import AttackSequence
from grimdarkoracle.engine.target_state import Allocation, ModelInfo

H = (CCW,)
T3, T6 = [R("Tough", 3)], [R("Tough", 6)]

# --- half or less ------------------------------------------------------------
ten = Allocation([ModelInfo(1, False, False)] * 10)
assert half_or_less(ten, (1,) * 5 + (0,) * 5)
assert not half_or_less(ten, (1,) * 4 + (0,) * 6)
one6 = Allocation([ModelInfo(6, True, False)])
assert half_or_less(one6, (3,)) and not half_or_less(one6, (2,))
assert not half_or_less(Allocation([ModelInfo(1, False, False)]), (0,))
hero = Combatant("h", (cm(H), cm(H), cm(H), cm(H, rules=T3, hero=True)))
ha = Allocation.of(hero)
assert half_or_less(ha, (1, 1, 0, 0)) and not half_or_less(ha, (1, 0, 0, 0))

# --- Morale Test probability ---------------------------------------------------------
def pp(u, state=None, attack="shooting", **kw):
    m = Morale(REG, u, **kw)
    return m.pass_prob(state or m.alloc.fresh(), attack, exact=True)


assert pp(unit(5, H)) == F(1, 2)
ban = Combatant("b", (cm(H, rules=[R("Banner")]),) + (cm(H),) * 4)
assert pp(ban) == F(2, 3)
assert pp(ban, (1, 0, 0, 0, 0)) == F(1, 2)        # Banner holder dead
both = Combatant("b", (cm(H, rules=[R("Banner"), R("Bravery Aura")]),
                       cm(H, rules=[R("Banner")])) + (cm(H),) * 3)
assert pp(both) == F(5, 6)                        # +1 +1, once per rule
assert pp(unit(5, H, q=2, rules=[R("Banner")])) == F(5, 6)   # 1 always fails
two_ban = Combatant("b", (cm(H, q=5, rules=[R("Banner")]),) * 2 + (cm(H, q=5),))
assert pp(two_ban) == F(1, 2)                     # two Banners: +1 once
# The condition of Banner-like rules: what triggered the test.
from grimdarkoracle.rules import effects as E  # noqa: E402
v = E.View(REG, ctx(attack="melee", action=None), "defender", two_ban, (),
           two_ban, ())
assert E._cond("morale_from", "melee", v, "") and \
    not E._cond("morale_from", "shooting", v, "")
assert pp(unit(5, H, rules=[R("Fearless")])) == F(3, 4)
few = Combatant("f", (cm(H, rules=[R("Fearless")]),) + (cm(H),) * 2)
assert pp(few) == F(1, 2)                         # not most models
hq = Combatant("h", (cm(H, q=5),) * 3 + (cm(H, rules=T3, q=3, hero=True),))
assert pp(hq) == F(2, 3)                          # the Hero's Quality
assert pp(hq, (0, 0, 0, 3)) == F(1, 3)            # Hero dead
assert pp(unit(5, H, q=5), hero_quality=3) == F(2, 3)   # Tough(9)+ nearby
assert pp(unit(5, H, rules=[R("Fearless")], shaken=True)) == 0

# --- after shooting -------------------------------------------------------------
two = unit(2, H)
res = K.resolve(AttackSequence(REG, unit(2, (RIFLE,)), two, ctx()), exact=True)
o = after_shooting(Morale(REG, two), res, exact=True)
assert o == MoraleOutcome(destroyed=F(1, 16), test=F(3, 8), shaken=F(3, 16))
# Already below half: any wound tests again; a Shaken unit stays Shaken.
four = unit(4, H)
res = K.resolve(AttackSequence(REG, unit(1, (RIFLE,)), four, ctx()),
                start=(1, 1, 1, 0), exact=True)
assert after_shooting(Morale(REG, four), res, exact=True).test == 0
res = K.resolve(AttackSequence(REG, unit(1, (W("G", 24, 2),)), four, ctx()),
                start=(1, 1, 0, 0), exact=True)
o = after_shooting(Morale(REG, four), res, exact=True)
assert o.test == 2 * F(1, 4) * F(3, 4) and o.destroyed == F(1, 16)
sh = unit(2, H, shaken=True)
res = K.resolve(AttackSequence(REG, unit(1, (RIFLE,)), sh, ctx()), exact=True)
o = after_shooting(Morale(REG, sh), res, exact=True)
assert o.shaken == 1 and o.test == F(1, 4)

# --- melee result ----------------------------------------------------------
def exchange(att, dfn, tie="none", **kw):
    st = MeleeSetup(REG, att, dfn, **kw)
    r = melee.resolve(st, exact=True)
    return after_melee(Morale(REG, att), Morale(REG, dfn), r, tie, exact=True)


# 1 v 1: a decisive result destroys the loser; tie (9/16) as chosen.
a, d = exchange(unit(1, H), unit(1, H))
assert (a.test, d.test, a.destroyed, d.destroyed) == (0, 0, F(3, 16), F(1, 4))
a, d = exchange(unit(1, H), unit(1, H), tie="defender")
assert a.test == F(9, 16) and a.shaken == F(9, 32) and d.test == 0
a, d = exchange(unit(1, H), unit(1, H), tie="attacker")
assert d.test == F(9, 16) and a.test == 0
# Fear(1) on the charger: the 0-0 tie is lost by the charged unit.
a, d = exchange(unit(1, H, rules=[R("Fear", 1)]), unit(1, H))
assert d.test == F(9, 16) and d.shaken == F(9, 32) and a.test == 0
# Rout: at half or less after losing (2 models, one killed).
a, d = exchange(unit(2, H), unit(2, ()), strike_back=False)
assert d == MoraleOutcome(destroyed=F(1, 16), test=F(3, 8), rout=F(3, 16))
assert a == MoraleOutcome()
# Fear adds up over the living models at the start.
m = Morale(REG, unit(3, H, rules=[R("Fear", 2)]))
assert m.fear(m.alloc.fresh()) == 6 and m.fear((1, 1, 0)) == 2
try:
    after_melee(m, m, None, tie="draw")
    raise AssertionError("tie option not checked")
except ValueError:
    pass

# --- Shaken defender: Counter not first, strike back Fatigued -------------
ctr = unit(5, (W("Spear", 0, 1, R("Counter")),), shaken=True)
st = MeleeSetup(REG, unit(5, H), ctr)
sq = st.seq("def", range(5))
assert st.steps("counter", sq) == [] and len(st.steps("back", sq)) == 1
assert sq.parts(sq.steps[0], st.a_alloc.fresh())[0][0].fatigued
# --- real data: shooting and melee morale of DAO / BB units -----------------------
import testpaths                                                    # noqa: E402
if not testpaths.USING_SYNTHETIC:
    import time
    from grimdarkoracle.data import af_book as ab
    from grimdarkoracle.data.resolve import resolve
    from grimdarkoracle.engine.context import combatant
    from grimdarkoracle.rules import registry
    from unitkit import SEM
    books = [ab.load_book(testpaths.book_path(u))
             for u in ("z8205ez2boggzs22", "78qp9l5alslt6yj8")]
    real = registry.RuleRegistry(SEM, ab.load_core_rules(testpaths.rules_path()),
                                 books)
    units = [combatant(resolve(b, u)) for b in books for u in b.units]
    t0, n, fear = time.time(), 0, 0
    for a in units:
        ma = Morale(real, a)
        fear += ma.fear(ma.alloc.fresh()) > 0
        for t in units[::7]:
            mt = Morale(real, t)
            ch = K.resolve(AttackSequence(real, a, t, ctx()))
            o = after_shooting(mt, ch)
            assert 0 <= o.shaken <= o.test + 1e-12 <= 1 + 1e-9, (a.name, t.name)
            r = melee.resolve(MeleeSetup(real, a, t))
            for o in after_melee(ma, mt, r):
                assert o.test >= o.shaken + o.rout - 1e-12, (a.name, t.name)
                assert o.destroyed + o.test <= 1 + 1e-9
            n += 1
    assert fear, "no real unit with Fear found"
    print(f"morale: {n} real shooting + melee pairs in {time.time() - t0:.1f}s")
print("morale: OK")
