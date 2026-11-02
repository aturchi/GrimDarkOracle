"""engine.target_state, engine.sequence, engine.kill_chain: allocation
order, carry / no carry, step order, per-state plans, closed forms with
exact Fractions."""
from dataclasses import replace
from fractions import Fraction as F

from unitkit import R, W, RIFLE, REG, cm, unit, ctx
from grimdarkoracle.engine import gf_math as G
from grimdarkoracle.engine import kill_chain as K
from grimdarkoracle.engine import pmf as P
from grimdarkoracle.engine.context import Combatant
from grimdarkoracle.engine.sequence import AttackSequence
from grimdarkoracle.engine.specs import AttackSpec, TargetSpec
from grimdarkoracle.engine.target_state import Allocation, ModelInfo

# --- allocation order (Tough, Heroes last) ----------------------------------------
T3 = (R("Tough", 3),)
tgt = Combatant("t", (cm(), cm(upgrades=1, points=10), cm(upgrades=1, points=5),
                      cm(rules=T3), cm(), cm(rules=T3, hero=True)))
a = Allocation.of(tgt)
assert a.order(a.fresh()) == (4, 0, 2, 1, 3, 5)
assert [m.cap for m in a.infos] == [1, 1, 1, 3, 1, 3]
s = a.carry(a.fresh(), 6)                  # 4 one-wound models, then Tough
assert s == (1, 1, 1, 2, 1, 0) and a.order(s) == (3, 5)
s = a.carry(s, 3)                          # Hero last, excess carried / lost
assert s == (1, 1, 1, 3, 1, 2) and a.killed(s) == 5 and a.taken(s) == 9
two = Allocation([ModelInfo(3, True, False)] * 2)
assert two.order((0, 0)) == (1, 0)
assert two.order((1, 0)) == (0, 1)         # most-wounded Tough model first
assert two.carry((0, 0), 4) == (1, 3)
assert two.wound((0, 0), 1, 7) == (0, 3)   # no carry: excess lost
hero_w = Allocation([ModelInfo(1, False, False), ModelInfo(3, True, True)])
assert hero_w.order((0, 2)) == (0, 1)      # Heroes last even if wounded
for bad in ((0,), (0, 4), (-1, 0)):
    try:
        hero_w.check(bad)
        raise AssertionError(bad)
    except ValueError:
        pass

# --- closed forms on apply_weapon (Fractions) ----------------------------------------
laws = K._Laws(True)
spec, tspec = AttackSpec(6, quality=4, ap=1), TargetSpec(defense=4)
five = Allocation([ModelInfo(1, False, False)] * 5)
out = K.apply_weapon({five.fresh(): 1}, five, spec, tspec, laws)
res = K.ChainResult(five, five.fresh(), out)
gross = G.weapon_law(spec, tspec, 5, True).gross
want = [sum(gross[i] for i in range(len(gross)) if min(5, i) == k)
        for k in range(6)]
assert P.trim(res.killed()) == P.trim(want) and sum(out.values()) == 1

# Deadly(4) on one Tough(6) model: 4 wounds, then the second event kills
# (2 left, excess lost).
dspec = AttackSpec(3, quality=3, deadly=4)
one6 = Allocation([ModelInfo(6, True, False)])
ev = G.weapon_law(dspec, tspec, 1, True).events
res = K.ChainResult(one6, (0,), K.apply_weapon({(0,): 1}, one6, dspec, tspec,
                                               laws))
assert res.wounds() == [ev[0], 0, 0, 0, ev[1], 0, 1 - ev[0] - ev[1]]
# Deadly(3) on three Tough(2) models: each event kills one model.
three2 = Allocation([ModelInfo(2, True, False)] * 3)
ev = G.weapon_law(dspec, tspec, 3, True).events
res = K.ChainResult(three2, three2.fresh(), K.apply_weapon(
    {three2.fresh(): 1}, three2, replace(dspec, deadly=3), tspec, laws))
assert res.killed() == [ev[0], ev[1], ev[2], 1 - ev[0] - ev[1] - ev[2]]
# Blast counts the models alive at the start of the weapon.
blast = AttackSpec(2, quality=4, blast=3)
s = (1, 1, 1, 0, 0)                        # two left
out = K.apply_weapon({s: 1}, five, blast, tspec, laws)
g = G.weapon_law(blast, tspec, 2, True).gross
assert out[(1, 1, 1, 1, 1)] == 1 - g[0] - g[1]

# --- sequence: step order, per-state plans, unit-level Defense ------------------------
SN = W("Sniper", 30, 1, R("Takedown"))
DG = W("Fusion", 12, 1, R("Deadly", 3))
att = Combatant("a", (cm(weapons=(RIFLE, DG, SN)), cm(weapons=(RIFLE, SN))))
seq = AttackSequence(REG, att, unit(3), ctx())
assert [(st.weapon.name, st.kind, st.models) for st in seq.steps] == [
    ("Sniper", "takedown", (0,)), ("Sniper", "takedown", (1,)),
    ("Fusion", "deadly", (0,)), ("Rifle", "other", (0, 1))]
seq2 = AttackSequence(REG, att, unit(3), ctx(), weapon_order=("Rifle",))
assert seq2.steps[-1].weapon.name == "Rifle"           # only within a class
# "Most models" re-checked at each weapon: Stealth on 2 of 3.
st = Combatant("s", (cm(rules=[R("Stealth")]), cm(rules=[R("Stealth")]),
                     cm(upgrades=1)))
seq = AttackSequence(REG, unit(1), st, ctx(distance=12))
rifle = next(x for x in seq.steps if x.weapon == RIFLE)
assert seq.alloc.order(seq.alloc.fresh()) == (1, 0, 2)
assert seq.parts(rifle, (0, 0, 0))[0][0].hit_mod == -1
assert seq.parts(rifle, (0, 1, 0))[0][0].hit_mod == 0
# Unit-level Defense: most living models; tie -> next in the order.
arm = Combatant("m", tuple(cm() for _ in range(3)) + tuple(
    cm(rules=[R("Armor", 3)], upgrades=1) for _ in range(2)))
seq = AttackSequence(REG, unit(1), arm, ctx())
rifle = next(x for x in seq.steps if x.weapon == RIFLE)
assert seq.parts(rifle, (0, 0, 0, 0, 0))[0][1].defense == 4
assert seq.parts(rifle, (0, 0, 1, 0, 0))[0][1].defense == 4   # 2-2: front
assert seq.parts(rifle, (1, 0, 1, 0, 0))[0][1].defense == 3
# Joined Hero: host Defense while a host lives, then its own.
hero = cm(rules=list(T3), d=2, hero=True)
hu = Combatant("h", (cm(), cm(), hero))
seq = AttackSequence(REG, unit(1), hu, ctx())
rifle = next(x for x in seq.steps if x.weapon == RIFLE)
assert seq.parts(rifle, (0, 0, 0))[0][1].defense == 4
assert seq.parts(rifle, (1, 1, 0))[0][1].defense == 2

# --- Takedown: default target = the model lost last, as a unit of one ----------------
sn = Combatant("a", (cm(weapons=(W("Sniper", 30, 2, R("Takedown"),
                                    R("AP", 1)),)),))
seq = AttackSequence(REG, sn, hu, ctx())
assert seq.takedown_targets[0] == 2 and len(seq.steps) == 1
res = K.resolve(seq, exact=True)
spec, t = seq.takedown_part(seq.steps[0], 2)
assert t.defense == 2 and spec.attacks == 2          # the Hero's own Defense
g = G.weapon_law(spec, t, 1, True).gross
assert P.trim(res.wounds()) == P.trim(g[:3] + [sum(g[3:])])   # cap 3
assert all(s[0] == s[1] == 0 for s in res.dist)      # hosts untouched
seq = AttackSequence(REG, sn, hu, ctx(), takedown_targets=(0,))
assert all(s[1] == s[2] == 0 for s in K.resolve(seq, exact=True).dist)

# --- whole sequence, exact: rifles on a plain unit ------------------------------------
seq = AttackSequence(REG, unit(5), unit(5), ctx())
res = K.resolve(seq, exact=True)
assert sum(res.dist.values()) == 1
assert res.killed() == P.binomial(5, F(1, 4))         # hit 1/2, block 1/2
assert res.destroyed() == F(1, 4) ** 5
melee = K.resolve(AttackSequence(REG, unit(5), unit(5),
                                 ctx(attack="melee", action="charge")),
                  exact=True)
assert melee.killed() == P.binomial(5, F(1, 4))       # Hand Weapons
# --- real data: every DAO / BB unit against every 7th unit, float laws ------------------
import testpaths                                                 # noqa: E402
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
    units = [resolve(b, u) for b in books for u in b.units]
    t0, count = time.time(), 0
    for att in units:
        for tgt in units[::7]:
            for c in (ctx(), ctx(attack="melee", action="charge")):
                r = K.resolve(AttackSequence(real, combatant(att),
                                             combatant(tgt), c))
                assert abs(sum(r.dist.values()) - 1) < 1e-9, (att.name, tgt.name)
                count += 1
    print(f"kill_chain: {count} real sequences in {time.time() - t0:.1f}s")
print("kill_chain: OK")
