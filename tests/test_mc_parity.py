"""Exact kill chain vs dice resolver: models killed and wounds
allocated must agree within mc_support.SIGMA on every configuration.
Each configuration targets a mechanism where an exact-law bug would show:
carry over, Deadly without carry, Regeneration, Blast after earlier
casualties, six-hit riders, Shred, Takedown, joined Hero, Fatigue, a
wounded start state."""
import time

import testpaths                                    # noqa: F401 (sys.path)
import mc_support as M
from unitkit import R, W, REG, cm, unit, ctx
from grimdarkoracle.engine.context import Combatant
from grimdarkoracle.engine.sequence import AttackSequence

T3, T6 = (R("Tough", 3),), (R("Tough", 6),)
CASES = []


def case(name, att, tgt, start=None, **c):
    CASES.append((name, AttackSequence(REG, att, tgt, ctx(**c)), start))


case("rifles AP1 vs 10 x D5", unit(10, weapons=(W("Rifle", 24, 2,
     R("AP", 1)),)), unit(10, d=5))
case("Deadly3 + Regen vs Tough3",
     unit(3, weapons=(W("Fusion", 12, 2, R("Deadly", 3), R("AP", 2)),)),
     unit(4, rules=T3 + (R("Regeneration"),), d=4))
case("Rifles then Blast3",
     Combatant("a", (cm(weapons=(W("Rifle", 24, 1, count=1),) * 1),) * 8
               + (cm(weapons=(W("Mortar", 30, 2, R("Blast", 3)),)),)),
     unit(5, d=5))
case("Rending Bane Shred vs Fortified",
     unit(4, weapons=(W("Claw", 24, 3, R("Rending"), R("Bane"),
                        R("Shred")),)),
     unit(3, rules=T3 + (R("Fortified"),), d=3))
case("Surge + Relentless, cover", unit(6, weapons=(W("Gun", 30, 2,
     R("Surge"), R("Relentless"), R("AP", 1)),)), unit(8, d=4),
     distance=18, cover="terrain")
case("Takedown + Hero join",
     Combatant("a", (cm(weapons=(W("Sniper", 30, 3, R("Takedown"),
                                  R("AP", 2)),)),) * 2 + (cm(),) * 4),
     Combatant("h", (cm(),) * 4 + (cm(rules=list(T3), d=3, hero=True),)))
case("Furious charge vs Tough6", unit(5, weapons=(W("Blade", 0, 3,
     R("Furious"), R("AP", 1)),)), unit(2, rules=T6, d=4),
     attack="melee", action="charge")
case("Fatigued strike back", unit(5, fatigued=True), unit(5, d=4),
     attack="melee", action=None)
case("Fatigued Rending + Surge", unit(5, weapons=(W("Claw", 0, 4,
     R("Rending"), R("Surge")),), fatigued=True), unit(6, d=2),
     attack="melee", action=None)
case("Deadly2 on wounded Tough3", unit(2, weapons=(W("Lance", 18, 2,
     R("Deadly", 2)),)), unit(3, rules=T3, d=3), start=(2, 0, 1))

t0 = time.time()
bad = []
for name, seq, start in CASES:
    assert seq.steps, name
    ok, msgs = M.check(name, seq, start=start)
    for m in msgs:
        print(m)
    if not ok:
        bad.append(name)
print(f"mc parity: {len(CASES)} configurations, {M.TRIALS} trials each, "
      f"{time.time() - t0:.1f}s")
assert not bad, bad
print("mc_parity: OK")
