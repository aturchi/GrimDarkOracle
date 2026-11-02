"""Game numbers of semantics.json 'game': the engine reads
them through the registry, so editing the file changes the maths. Checks
with numbers different from GF 3.6, against independent face counts."""
import copy
from fractions import Fraction as F
from itertools import product

import testpaths                                    # noqa: F401 (sys.path)
from unitkit import SEM, CORE, R, W, unit, ctx
from grimdarkoracle.app import spells as SP
from grimdarkoracle.engine import gf_math as G
from grimdarkoracle.engine import morale as MO
from grimdarkoracle.engine.modifiers import build_plan
from grimdarkoracle.engine.specs import AttackSpec, TargetSpec
from grimdarkoracle.engine.target_state import Allocation
from grimdarkoracle.rules import registry

# The shipped numbers are those of GF 3.6 (and the engine defaults).
GF36 = {"quality_auto_success": 6, "quality_auto_fail": 1,
        "cover_defense_bonus": 1, "fatigue_hit_on": 6, "morale_half": 0.5}
assert SEM["game"] == GF36, SEM["game"]

# Validation of the numbers.
for bad in ({"quality_auto_fail": 6}, {"morale_half": 2},
            {"fatigue_hit_on": 0}, {"cover_defense_bonus": True},
            {"quality_auto_success": 3, "quality_auto_fail": 3}):
    doc = copy.deepcopy(SEM)
    doc["game"].update(bad)
    assert any(e.startswith("game") for e in registry.validate(doc)), bad
assert registry.validate(SEM) == []

# A registry with other numbers.
HOUSE = {"quality_auto_success": 5, "quality_auto_fail": 2,
         "cover_defense_bonus": 2, "fatigue_hit_on": 5, "morale_half": 0.25}
doc = copy.deepcopy(SEM)
doc["game"] = dict(HOUSE)
REG2 = registry.RuleRegistry(doc, CORE)

att, tgt = unit(2, weapons=(W("Gun", 24, 1),)), unit(4, d=5)
g = build_plan(REG2, att, tgt, ctx(cover="terrain")).groups[0]
assert (g.spec.auto_success, g.spec.auto_fail, g.spec.fatigue_on) == (5, 2, 5)
t = g.targets[0]
assert (t.auto_success, t.auto_fail, t.defense_mod) == (5, 2, 2)  # cover +2
melee = build_plan(REG2, unit(2, fatigued=True), tgt,
                   ctx(attack="melee", action=None)).groups[0].spec
assert melee.fatigued and melee.fatigue_on == 5
assert G.hit_probs(melee, exact=True) == (F(4, 6), F(2, 6), 0)


def faces_block(target, ap, reroll):
    """Independent count over the 36 pairs of dice."""
    ok = lambda f: f >= target.auto_success or (
        f > target.auto_fail and f + target.defense_mod - ap >= target.defense)
    block = fail = one = F(0)
    for a, b in product(range(1, 7), repeat=2):
        r = b if (reroll and a == 6) else a
        if ok(r):
            block += F(1, 36)
        elif r == 1:
            one += F(1, 36)
        else:
            fail += F(1, 36)
    return block, fail, one


for d, mod, ap, auto, rr in product((2, 4, 6), (-2, 0, 1), (0, 2), ((6, 1),
                                    (5, 2), (4, 3)), (False, True)):
    tt = TargetSpec(d, mod, auto_success=auto[0], auto_fail=auto[1])
    assert G.block_probs(tt, ap, rr, exact=True) == faces_block(tt, ap, rr), \
        (d, mod, ap, auto, rr)
for q, mod, auto in product((2, 4, 6), (-3, 0, 2), ((6, 1), (5, 2))):
    s = AttackSpec(1, q, mod, auto_success=auto[0], auto_fail=auto[1])
    n = sum(1 for f in range(1, 7) if f >= auto[0] or
            (f > auto[1] and f + mod >= q))
    assert G.hit_probs(s, exact=True) == (F(6 - n, 6), F(n - 1, 6), F(1, 6))

# The dice resolver reads the same numbers (Fatigue 5+, auto 5 / 2).
import mc_support as M                              # noqa: E402
from grimdarkoracle.engine.sequence import AttackSequence   # noqa: E402
seq = AttackSequence(REG2, unit(6, weapons=(W("Claw", 0, 2),), fatigued=True),
                     unit(6, d=3), ctx(attack="melee", action=None))
ok, msgs = M.check("house numbers, Fatigued", seq)
print("\n".join(msgs))
assert ok

# Morale: "half or less" and the automatic faces.
assert MO.half_or_less(Allocation.of(unit(4)), (1, 1, 0, 0)) is True
assert MO.half_or_less(Allocation.of(unit(4)), (1, 1, 0, 0), F(1, 4)) is False
m2 = MO.Morale(REG2, unit(4, q=6))
assert m2.half == F(1, 4)
assert m2.pass_prob((0, 0, 0, 0), "shooting", exact=True) == F(2, 6)  # 5, 6
assert MO.Morale(registry.RuleRegistry(SEM, CORE), unit(4, q=6)).pass_prob(
    (0, 0, 0, 0), "shooting", exact=True) == F(1, 6)

# Casting roll.
caster = unit(1, rules=(R("Caster", 2),))
from unitkit import resolved                        # noqa: E402
assert SP.cast_prob(REG2, resolved(caster), enemy=4, exact=True) == F(2, 6)
print("game numbers: OK")
