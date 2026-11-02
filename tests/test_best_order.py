"""engine.best_order: scores against the kill
chain and the melee exchange, the canonical candidates (plain weapons
commute: same best as a brute force over every permutation), classes
kept, Takedown preferences, melee charger /
strike back / Parry, the fallback beyond the budget, refusals; the time
on the largest real case (--real_data)."""
import itertools
import time

import testpaths
from unitkit import R, W, REG, CCW, cm, unit, ctx
from grimdarkoracle.engine import best_order as BO
from grimdarkoracle.engine import kill_chain as K
from grimdarkoracle.engine import melee as ML
from grimdarkoracle.engine import pmf as P
from grimdarkoracle.engine.context import Combatant
from grimdarkoracle.engine.sequence import AttackSequence

SHOOT = ctx(attack="shooting", distance=12, action="hold")


def brute(problem):
    """Best score over EVERY permutation within the classes."""
    best = None
    classes = BO._units(problem)
    for perms in itertools.product(*[itertools.permutations(c[1])
                                     for c in classes]):
        sc = BO.evaluate(problem, [n for p in perms for n in p])
        if best is None or sc.beats(best):
            best = sc
    return best


def mean_killed(seq, order):
    s = AttackSequence(REG, seq.attacker, seq.target, seq.ctx,
                       seq.takedown_targets, order)
    ch = K.resolve(s)
    return float(P.mean(ch.killed()))


# --- Score -----------------------------------------------------------------------------
a, b = BO.Score(2.0, 0.1, 3.0), BO.Score(2.0 + 1e-12, 0.0, 9.0)
assert a.beats(b) and not b.beats(a)               # killed tie: destroyed
assert not a.beats(a)
assert BO.Score(2.1).beats(BO.Score(2.0, 1.0, 9.0))

# --- a Blast weapon and plain ones against alike models ----------------------------------
flamer = W("Flamer", 12, 1, R("Blast", 3))
guns = (W("Gun A", 24, 2), W("Gun B", 24, 1, R("AP", 1)), flamer)
shooter = unit(2, guns)
target = unit(5)
seq = AttackSequence(REG, shooter, target, SHOOT)
pr = BO.shooting(seq)
classes = BO._units(pr)
assert [(c[0], c[1], c[2]) for c in classes] == [
    ("other", ["Gun A", "Gun B", "Flamer"], {"Gun A", "Gun B"})]
assert BO._count(classes) == 1 * 2 ** 2            # m! (m + 1)^p
sg = BO.search(pr)
assert sg.exact and sg.total == 4 and sg.examined == 4
assert sg.best.key() == brute(pr).key()            # exact, canonical
assert sg.improves and sg.order[-1] != "Flamer" and sg.gain > 0.05
assert abs(sg.best.killed - mean_killed(seq, sg.order)) < 1e-9
assert abs(sg.book.killed - mean_killed(seq, ())) < 1e-9
assert sg.current == sg.book
cur = BO.search(pr, ("Gun B", "Flamer"))
assert abs(cur.current.killed - mean_killed(seq, ("Gun B", "Flamer"))) < 1e-9
assert "searched all 4 order(s)" in sg.note()
# Plain weapons commute: swapping the two guns next to each other
# changes nothing, so the canonical walk loses nothing.
for o1, o2 in ((("Gun A", "Gun B", "Flamer"), ("Gun B", "Gun A", "Flamer")),
               (("Flamer", "Gun A", "Gun B"), ("Flamer", "Gun B", "Gun A"))):
    assert abs(BO.evaluate(pr, o1).killed - BO.evaluate(pr, o2).killed) \
        < 1e-12

# --- mixed target (a model with Tough): nothing is plain ------------------------------
mixed = unit(4, extra=(cm(rules=[R("Tough", 3)]),))
pm = BO.shooting(AttackSequence(REG, shooter, mixed, SHOOT))
assert BO._units(pm)[0][2] == set() and BO._count(BO._units(pm)) == 6
sm = BO.search(pm)
assert sm.exact and sm.examined == 6 and sm.best.key() == brute(pm).key()

# --- the book order already best: no suggestion ---------------------------------------
plain = BO.search(BO.shooting(AttackSequence(REG, unit(2, guns[:2]), target,
                                             SHOOT)))
assert plain.total == 1 and not plain.improves and plain.order == ()

# --- classes kept: Takedown, then Deadly, then the others -------------------------
snipe = W("Snipe", 24, 1, R("Takedown"))
dead = W("Melta", 12, 1, R("Deadly", 3))
dead2 = W("Lance", 12, 1, R("Deadly", 2), R("AP", 2))
hero = cm(rules=[R("Hero"), R("Tough", 3)], hero=True)
tgt_h = unit(4, extra=(hero,))
mix = Combatant("m", (cm((snipe, dead, dead2, flamer)),) * 2)
sq = AttackSequence(REG, mix, tgt_h, SHOOT)
pc = BO.shooting(sq)
assert [c[0] for c in BO._units(pc)] == ["takedown", "deadly", "other"]
sc = BO.search(pc)
assert sc.exact and sc.total == 1 * 2 * 1
assert sc.best.key() == brute(pc).key()
order = sc.order or ("Snipe", "Melta", "Lance", "Flamer")
assert order.index("Snipe") < 1 and abs(
    sc.best.killed - mean_killed(sq, sc.order)) < 1e-9
for o in (("Flamer",), ("Lance", "Flamer", "Snipe")):  # classes kept
    assert abs(BO.evaluate(pc, o).killed - mean_killed(sq, o)) < 1e-9
ch = K.resolve(sq)
bk = BO.evaluate(pc, ())
assert abs(bk.destroyed - float(ch.destroyed())) < 1e-9
assert abs(bk.wounds - float(P.mean(ch.wounds()))) < 1e-9
snipe2 = W("Snipe B", 24, 1, R("Takedown"), R("AP", 2))
sq2 = AttackSequence(REG, Combatant("m", (cm((snipe, snipe2, flamer,
                                               dead)),) * 2), tgt_h, SHOOT)
assert BO.search(BO.shooting(sq2)).examined == 2   # preferences: ordered

# --- the fallback beyond the budget --------------------------------------------------------
many = tuple(W(f"G{i}", 24, 1, R("Blast", 2)) for i in range(5))
pf = BO.shooting(AttackSequence(REG, unit(2, many[:4] + (flamer,)), mixed,
                                SHOOT))
full = BO.search(pf)
small = BO.search(pf, budget=10)
assert full.exact and full.total == full.examined == 120
assert not small.exact and small.total == 120
assert full.improves and small.improves            # the fallback's order
cls_f = BO._units(pf)                              # swaps improve a start
wk = BO._Walk(pf, cls_f, 10 ** 6, time.perf_counter() + 5)
start = BO._book(cls_f)
got, order_f = BO._improve(cls_f, start, wk)
assert got.beats(BO.evaluate(pf, start)) and list(order_f) != start
assert not small.best.beats(full.best)
big = BO.search(BO.shooting(AttackSequence(REG, unit(2, many + (flamer,)),
                                           mixed, SHOOT)))
assert not big.exact and big.total == 720       # 1956 nodes > BUDGET
pbig = BO.shooting(AttackSequence(REG, unit(2, many + (flamer,)), mixed,
                                  SHOOT))
assert BO._tree(BO._units(pbig), 10 ** 6) == 1956
assert BO._tree(BO._units(pr), 10 ** 6) == 11       # no dead ends
assert BO.search(pbig, budget=1956, time_limit=30).exact   # just fits
over = BO.search(pbig, budget=1955)
assert not over.exact and over.examined < 200      # no walk: the fallback
assert not small.book.beats(small.best) and small.examined > 0
assert "greedy + swaps" in small.note()
t = time.perf_counter()
assert not BO.search(pf, time_limit=0.0).exact     # the safety net cuts
assert time.perf_counter() - t < 0.5

# --- melee: the charger's strikes, the strike back, Parry ---------------------------------
axe, claw = W("Axe", 0, 2, R("AP", 1)), W("Claw", 0, 1, R("Blast", 3))
charger = unit(3, (axe, claw, CCW))
setup = ML.MeleeSetup(REG, charger, unit(5))


def melee_killed(order, side="att", base=(), dfn=None):
    s = ML.MeleeSetup(REG, charger, dfn or unit(5),
                      order_att=order if side == "att" else base,
                      order_def=order if side == "def" else ())
    res = ML.resolve(s)
    ch = res.defender() if side == "att" else res.attacker()
    return float(P.mean(ch.killed()))


pmel = BO.melee(setup)
sgm = BO.search(pmel)
assert sgm.exact and sgm.best.key() == brute(pmel).key()
assert abs(sgm.best.killed - melee_killed(sgm.order)) < 1e-9
assert abs(sgm.book.killed - melee_killed(())) < 1e-9
# Impact, then a Counter that may kill the lone charger: the states where
# no striker is left still count (their Impact kills).
lone = unit(1, (axe, claw), rules=[R("Impact", 3)])
spear = unit(5, (W("Spear", 0, 2, R("Counter"), R("AP", 2)),))
pl = BO.melee(ML.MeleeSetup(REG, lone, spear))
assert pl.rest and pl.branches
rl = ML.resolve(ML.MeleeSetup(REG, lone, spear))
bl = BO.search(pl).book
assert abs(bl.killed - float(P.mean(rl.defender().killed()))) < 1e-9
assert abs(bl.destroyed - float(rl.defender().destroyed())) < 1e-9
fighters = unit(5, (axe, claw, CCW))
back = ML.MeleeSetup(REG, charger, fighters)
pb = BO.melee(back, side="def")
sgb = BO.search(pb)
assert abs(sgb.book.killed - melee_killed((), "def", dfn=fighters)) < 1e-9
assert abs(sgb.best.killed - melee_killed(sgb.order, "def", dfn=fighters)) \
    < 1e-9
assert sgb.best.key() == brute(pb).key()
par = ML.MeleeSetup(REG, charger, unit(5, rules=[R("Parry", 1)]))
pp = BO.melee(par)
assert pp.branches and all(br.leaf is not None for br in pp.branches)
sgp = BO.search(pp)
assert sgp.best.key() == brute(pp).key()
rp = ML.resolve(ML.MeleeSetup(REG, charger, unit(5, rules=[R("Parry", 1)]),
                              order_att=sgp.order))
assert abs(sgp.best.killed - float(P.mean(rp.defender().killed()))) < 1e-9
assert BO._units(pp)[-1][2] == set()               # Parry: nothing plain

# --- refusals ------------------------------------------------------------------------------
for bad in (lambda: BO.melee(ML.MeleeSetup(REG, charger, unit(5),
                                           order_att=("Axe",))),
            lambda: BO.shooting(AttackSequence(
                REG, unit(2, guns, shaken=True), target, SHOOT))):
    try:
        bad()
        raise AssertionError("accepted")
    except ValueError:
        pass

# --- the largest real case (well under 1 s) ---------------------------------------
if not testpaths.USING_SYNTHETIC:
    from grimdarkoracle.app.library import Library
    from grimdarkoracle.app.unit_config import UnitConfig
    from grimdarkoracle.data.resolve import Choice, combine
    from grimdarkoracle.engine.context import combatant
    lib = Library.load(testpaths.DATA_DIR)
    bb = lib.books["78qp9l5alslt6yj8"]
    ab = next(u for u in bb.units.values() if u.name == "Assault Brothers")
    picks = [("E1", "RQd82ba", "9_vV60ClMQ", 2), ("E1", "zH7MpIKu0o",
             "N2HURmGQwa", 1), ("E1", "lIOr2V5Y", "ZEy3nKBj", 1)]
    cfg = UnitConfig(bb, ab.id, [Choice(*p) for p in picks])
    names = {w.name for w, _n in cfg.resolved.weapons()}
    assert len(names) == 7, names                   # the worst seen

    def unit_of(name):
        u = next(x for x in bb.units.values() if x.name == name)
        return UnitConfig(bb, u.id).resolved
    bik = unit_of("Brother Bikers")
    big = combatant(combine(bik, bik), hero=unit_of("Master Brother"))
    for tgt in (big, combatant(unit_of("Battle Brothers"))):
        s = ML.MeleeSetup(lib.reg, combatant(cfg.resolved), tgt)
        t = time.perf_counter()
        r = BO.search(BO.melee(s))
        dt = time.perf_counter() - t
        assert dt < 0.5, dt
        print(f"best_order: {r.total} orders, exact {r.exact}, {dt:.3f} s")
print("best_order: OK")
