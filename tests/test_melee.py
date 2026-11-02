"""engine.melee: phase order, Counter, Impact / Brace, strike back of
the survivors, Fatigue; closed forms in Fractions; Monte Carlo parity of
the whole exchange; real data."""
import time
from fractions import Fraction as F

import testpaths
import mc_support as M
from unitkit import R, W, CCW, REG, cm, unit
from grimdarkoracle.engine import melee
from grimdarkoracle.engine import pmf as P
from grimdarkoracle.engine.context import Combatant
from grimdarkoracle.engine.melee import MeleeSetup

H = (CCW,)
CTR = W("Spear", 0, 1, R("Counter"))


def joint_killed(res):
    """{(charger killed, target killed): p}."""
    out = {}
    for (a, d), p in res.dist.items():
        k = (res.setup.a_alloc.killed(a), res.setup.d_alloc.killed(d))
        out[k] = out.get(k, 0) + p
    return out


def nested(first, second_of):
    """Law of (X, Y) with X ~ first, Y | X ~ second_of(X)."""
    out = {}
    for x, px in enumerate(first):
        for y, py in enumerate(second_of(x)):
            if px * py:
                out[(x, y)] = out.get((x, y), 0) + px * py
    return out


# --- plain exchange: strikes, then strike back of the survivors ---------------
res = melee.resolve(MeleeSetup(REG, unit(5, H), unit(5, H)), exact=True)
q = F(1, 4)                                  # hit 1/2, block fails 1/2
assert joint_killed(res) == {(j, k): p for (k, j), p in nested(
    P.binomial(5, q), lambda k: P.binomial(5 - k, q)).items()}
# No strike back (flag) / Fatigued strike back: hits on 6 only.
res = melee.resolve(MeleeSetup(REG, unit(5, H), unit(5, H), strike_back=False),
                    exact=True)
assert res.attacker().killed() == [1]
res = melee.resolve(MeleeSetup(REG, unit(5, H), unit(5, H, fatigued=True)),
                    exact=True)
assert joint_killed(res) == {(j, k): p for (k, j), p in nested(
    P.binomial(5, q), lambda k: P.binomial(5 - k, F(1, 12))).items()}

# --- Counter strikes first, then only the other weapons strike back -------------
dfn = unit(5, (CTR, CCW))
st = MeleeSetup(REG, unit(5, H), dfn)
seq = st.seq("def", (0, 1, 2, 3, 4))
assert [s.weapon.name for s in st.steps("counter", seq)] == ["Spear"]
assert [s.weapon.name for s in st.steps("back", seq)] == ["Hand Weapon"]
st_f = MeleeSetup(REG, unit(5, H), unit(5, (CTR, CCW), fatigued=True))
seq_f = st_f.seq("def", (0, 1, 2, 3, 4))
assert st_f.steps("counter", seq_f) == [] and len(st_f.steps("back", seq_f)) == 2
st_n = MeleeSetup(REG, unit(5, H), dfn, strike_back=False)
assert st_n.steps("counter", seq) == [] == st_n.steps("back", seq)
# Spear only: Counter kills chargers before they strike, nothing after.
res = melee.resolve(MeleeSetup(REG, unit(5, H), unit(5, (CTR,))), exact=True)
assert joint_killed(res) == nested(P.binomial(5, q),
                                   lambda j: P.binomial(5 - j, q))
# Counter in Melee Aura (DAO) reaches the unit's weapons.
aura = Combatant("c", (cm(H, rules=[R("Counter in Melee Aura")]),) +
                 tuple(cm(H) for _ in range(4)))
st = MeleeSetup(REG, unit(5, H), aura)
assert all(s.counter for s in st.seq("def", range(5)).steps)

# Thrust / Furious only for the charger: the strike back is not a charge.
TH = (W("Pike", 0, 1, R("Thrust")),)
st = MeleeSetup(REG, unit(5, TH), unit(5, TH))
for side, want in (("att", (1, 1)), ("def", (0, 0))):
    sq = st.seq(side, range(5))
    other = (st.d_alloc if side == "att" else st.a_alloc).fresh()
    spec = sq.parts(sq.steps[0], other)[0][0]
    assert (spec.hit_mod, spec.ap) == want, (side, spec)

# --- Impact / Brace ------------------------------------------------------------
imp = unit(3, H, rules=[R("Impact", 2)])
assert MeleeSetup(REG, imp, unit(10, H)).impact_dice((0,) * 3) == 6
braced = unit(10, H, rules=[R("Brace", 2)])
assert MeleeSetup(REG, imp, braced).impact_dice((0,) * 3) == 4
assert MeleeSetup(REG, imp, unit(10, H, rules=[R("Brace", 2)], fatigued=True)
                  ).impact_dice((0,) * 3) == 6
assert MeleeSetup(REG, unit(3, H, rules=[R("Impact", 2)], fatigued=True),
                  unit(10, H)).impact_dice((0,) * 3) == 0
st = MeleeSetup(REG, imp, unit(10, H, rules=[R("Evasive")]))
(spec, tgt), = st.impacts((0,) * 3, (0,) * 10)
assert (spec.attacks, spec.quality, spec.hit_mod, spec.ap) == (6, 2, 0, 0)
# Impact only (no melee weapons, no strike back): Binomial(6, 5/6 * 1/2).
res = melee.resolve(MeleeSetup(REG, unit(3, (), rules=[R("Impact", 2)]),
                               unit(10, H), strike_back=False), exact=True)
assert P.trim(res.defender().killed()) == P.binomial(6, F(5, 12))
# --- Parry: one roll per phase on the pooled hits ----------------------------
from grimdarkoracle.engine import parry as PR  # noqa: E402
PAR = [R("Parry", 1)]
par = Combatant("p", tuple(cm(H, rules=PAR) for _ in range(2)) +
                tuple(cm(H) for _ in range(18)))
st = MeleeSetup(REG, unit(6, (W("Blade", 0, 2),)), par, strike_back=False)
assert st.parry_dice("def", st.d_alloc.fresh()) == 2
assert st.parry_dice("att", st.a_alloc.fresh()) == 0


def parried(hits, dice, keep):
    """Killed law: hits ~ 'hits', Parry min(dice, h) at 1/6, each
    remaining hit kills with probability 'keep' (one-wound models)."""
    out = [0]
    for h, ph in enumerate(hits):
        for k, pk in enumerate(P.binomial(min(dice, h), F(1, 6))):
            out = P.add(out, [ph * pk * x for x in P.binomial(h - k, keep)])
    return out


res = melee.resolve(st, exact=True)
assert P.trim(res.defender().killed()) == P.trim(
    parried(P.binomial(12, F(1, 2)), 2, F(1, 2)))
# Impact is a phase of its own, with its own Parry roll.
st = MeleeSetup(REG, unit(3, (), rules=[R("Impact", 2)]), par,
                strike_back=False)
assert P.trim(melee.resolve(st, exact=True).defender().killed()) == P.trim(
    parried(P.binomial(6, F(5, 6)), 2, F(1, 2)))
# The defender ignores the most damaging hits first (expected wounds per
# hit vs D4): Rending six-hit (AP 4) > AP(2) > AP(0); ties: later entry.
att = Combatant("a", (cm((W("Axe", 0, 1, R("AP", 2)), CCW,
                          W("Claw", 0, 1, R("Rending")))),))
st = MeleeSetup(REG, att, par)
sq = st.seq("att", (0,))
ents = PR.entries_for(sq, sq.steps, st.d_alloc.fresh())
names = [ents[n].spec.name + ("/6" if slot else "")
         for n, slot in PR.ranking(ents, st.d_alloc.fresh())]
assert names == ["Claw/6", "Axe", "Claw", "Hand Weapon"], names
assert PR.remove([[2], [1], [3, 1]], [(0, 0), (2, 1), (1, 0), (2, 0)], 4) == \
    ((0,), (0,), (3, 0))

# --- Monte Carlo parity of whole exchanges ------------------------------------------
T3 = (R("Tough", 3),)
cases = [
    ("Tough + Hero, Furious", MeleeSetup(
        REG, unit(5, (W("Claw", 0, 2, R("Furious"), R("AP", 1)),)),
        Combatant("h", tuple(cm(H, rules=T3) for _ in range(3)) +
                  (cm((W("Axe", 0, 3, R("AP", 2)),), rules=list(T3), d=3,
                      hero=True),)))),
    ("Impact Brace Counter Thrust", MeleeSetup(
        REG, unit(4, (W("Lance", 0, 2, R("Thrust")),),
                  rules=[R("Impact", 3)]),
        unit(6, (CTR, CCW), rules=[R("Brace", 2)]))),
    ("Parry both sides, Rending, Takedown", MeleeSetup(
        REG, Combatant("a", (cm((W("Sword", 0, 2, R("Rending")),),
                                rules=[R("Parry", 2)]),) * 4 +
                       (cm((W("Duel", 0, 3, R("Takedown"), R("AP", 1)),
                            CCW), rules=list(T3)),)),
        Combatant("d", tuple(cm((W("Spear", 0, 2, R("Counter")), CCW),
                                rules=[R("Parry", 1)]) for _ in range(5))
                  + (cm(H, rules=list(T3), d=3, hero=True),)))),
    ("Impact into Parry, Deadly", MeleeSetup(
        REG, unit(3, (W("Maul", 0, 2, R("Deadly", 2)),),
                  rules=list(T3) + [R("Impact", 3)]),
        unit(6, (W("Knife", 0, 2),), rules=[R("Parry", 1)]))),
    ("Deadly vs Regen, Rending back", MeleeSetup(
        REG, unit(3, (W("Fist", 0, 2, R("Deadly", 3)),), rules=T3),
        unit(4, (W("Talon", 0, 3, R("Rending")),),
             rules=T3 + (R("Regeneration"),)))),
]
t0, bad = time.time(), []
for name, setup in cases:
    ok, msgs = M.check_melee(name, setup)
    print(*msgs, sep="\n")
    if not ok:
        bad.append(name)
print(f"melee parity: {len(cases)} exchanges in {time.time() - t0:.1f}s")
assert not bad, bad

# --- real data: every DAO / BB unit charging every 7th unit -------------------------
if not testpaths.USING_SYNTHETIC:
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
    t0, n = time.time(), 0
    for a in units:
        for t in units[::7]:
            r = melee.resolve(MeleeSetup(real, combatant(a), combatant(t)))
            assert abs(sum(r.dist.values()) - 1) < 1e-9, (a.name, t.name)
            n += 1
    print(f"melee: {n} real exchanges in {time.time() - t0:.1f}s")
# --- weapon order of each side ---------------------------------------------------
AXE, CLAW = W("Axe", 0, 1), W("Claw", 0, 2)
two = unit(2, weapons=(AXE, CLAW))
ms = MeleeSetup(REG, two, two)
names = [st.weapon.name for st in ms.seq("att", (0, 1)).steps]
assert names[0] == "Axe" and set(names) == {"Axe", "Claw"}
ms = MeleeSetup(REG, two, two, order_att=("Claw",), order_def=("Claw",))
for side in ("att", "def"):
    names = [st.weapon.name for st in ms.seq(side, (0, 1)).steps]
    assert names[0] == "Claw" and names[-1] == "Axe", (side, names)
ms = MeleeSetup(REG, two, two, order_def=("Claw",))
assert ms.seq("att", (0, 1)).steps[0].weapon.name == "Axe"
print("melee: OK")
