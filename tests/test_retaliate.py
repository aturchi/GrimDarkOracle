"""Retaliate in the melee exchange, exact and against the
dice oracle."""
import random
from fractions import Fraction as F

import testpaths                                    # noqa: F401 (sys.path)
import dice_resolve as DR
from grimdarkoracle.engine import melee
from grimdarkoracle.engine import pmf as P
from grimdarkoracle.engine.melee import MeleeSetup
from unitkit import REG, R, W, cm, unit

H = ()
CLAW = (W("Claw", 0, 1),)


def charger(n_armed=1, rules=(), size=10):
    """size D4 models, the first n_armed with one A1 claw."""
    armed = tuple(cm(CLAW, rules=list(rules)) for _ in range(n_armed))
    return unit(size - n_armed, H, extra=armed)


def law(setup, side):
    res = melee.resolve(setup, exact=True)
    ch = res.attacker() if side == "att" else res.defender()
    return P.trim(ch.killed())


big = unit(1, H, rules=[R("Tough", 9), R("Retaliate", 2)])
# The claw wounds the Tough(9) model on 1/4; each wound: 2 hits at the D4
# charger, each a kill on 1/2.
st = MeleeSetup(REG, charger(), big)
assert law(st, "att") == [F(13, 16), F(2, 16), F(1, 16)]
assert law(st, "def") == [1]                          # Tough(9): not killed
# Impact wounds count too: 5/6 * 1/2 = 5/12
imp = unit(9, H, extra=(cm(H, rules=[R("Impact", 1)]),))   # one die
assert law(MeleeSetup(REG, imp, big), "att")[1:] == [F(5, 12) * F(1, 2),
                                                      F(5, 12) * F(1, 4)]
# Retaliate on the charger: the strike back wounds it, the charged unit
# takes the hits (1 hit per wound)
tank = unit(1, H, rules=[R("Tough", 9), R("Retaliate", 1)])
assert law(MeleeSetup(REG, tank, charger()), "def") == [F(7, 8), F(1, 8)]
assert law(MeleeSetup(REG, tank, charger(), strike_back=False), "def") == [1]
# no Retaliate: the charger takes nothing
assert law(MeleeSetup(REG, charger(), unit(1, H, rules=[R("Tough", 9)])),
           "att") == [1]

# dice oracle (tests/dice_resolve): frequencies against the exact law
n, rng = 4000, random.Random(11)
counts = [0, 0, 0]
for _ in range(n):
    a1, _d1, log = DR.resolve_melee(st, None, rng)
    counts[st.a_alloc.killed(a1)] += 1
for k, p in enumerate([F(13, 16), F(2, 16), F(1, 16)]):
    sd = (n * p * (1 - p)) ** 0.5
    assert abs(counts[k] - n * p) < 4 * sd, (k, counts)
_a, _d, log = DR.resolve_melee(st, None, random.Random(0))
assert {p for p, _r in log} <= {"strike", "retaliate"}


print("test_retaliate OK")
