"""app.analyzer_core + app.points_metrics: shooting and melee
analyses on hand-built units, exact closed forms in Fractions, points
metrics, start states, switched-off weapons; real DAO / BB pairs."""
from fractions import Fraction as F

from unitkit import R, W, CCW, RIFLE, REG, cm, unit, ctx, resolved
from grimdarkoracle.app import points_metrics as PM
from grimdarkoracle.app.analyzer_core import Options, Side, analyse
from grimdarkoracle.data.resolve import ResolvedUnit
from grimdarkoracle.engine import pmf as P
from grimdarkoracle.engine.morale import MeleeWinner, MoraleOutcome


ru = resolved


def binom(n, p):
    return P.binomial(n, p)


EX = Options(exact=True)
MELEE = Options(ctx=ctx(attack="melee", action="charge"), exact=True)
A5, T5 = Side(ru(unit(5))), Side(ru(unit(5), name="t"))

# --- shooting closed forms -------------------------------------------------------
a = analyse(REG, A5, T5, EX)
assert a.kind == "shooting" and len(a.rows) == 1
row = a.rows[0]
assert (row.name, row.count, row.attacks, row.phase) == ("Rifle", 5, 5, "shoot")
assert row.hits == binom(5, F(1, 2))
assert row.wounds == row.killed == binom(5, F(1, 4))
assert a.def_losses.wounds == row.wounds and row.destroyed == F(1, 1024)
# Morale: 3+ killed and not destroyed -> test, Q4 -> half Shaken.
assert a.def_losses.morale == MoraleOutcome(F(1, 1024), F(105, 1024),
                                            F(105, 2048))
assert [(s.name, s.count) for s in a.skipped] == [("Hand Weapon", 5)]
assert a.att_losses is None and a.winner is None

# Two weapons on a big target: no saturation, the chained total has the
# sum of the rows' means (rows = each weapon alone).
gun = W("Gun", 24, 2, R("AP", 1))
two = Side(ru(unit(4, (RIFLE, gun))))
big = Side(ru(unit(30), name="big"))
b = analyse(REG, two, big, EX)
assert [r.name for r in b.rows] == ["Rifle", "Gun"]
assert (b.rows[1].count, b.rows[1].attacks) == (4, 8)          # 4 x A2
assert P.mean(b.def_losses.wounds) == sum(P.mean(r.wounds) for r in b.rows)

# Weapons switched off: no row, a "switched off" skipped row.
c = analyse(REG, Side(A5.unit, off=frozenset({RIFLE})), T5, EX)
assert not c.rows and c.def_losses.wounds == [1]
assert ("Rifle", 5, "switched off") in [(s.name, s.count, s.reason)
                                         for s in c.skipped]

# Start states: dead attackers do not shoot; a target already below half
# tests on any wound, its dead models count in the total size.
d = analyse(REG, Side(A5.unit, wounds=(1, 1, 1, 0, 0)),
            Side(T5.unit, wounds=(1, 1, 0, 0, 0)), EX)
assert d.rows[0].hits == binom(2, F(1, 2)) and d.rows[0].count == 2
w2 = binom(2, F(1, 4))
assert d.def_losses.killed == w2
assert d.def_losses.morale.test == 1 - w2[0]
assert d.def_losses.points_removed == 20 * float(P.mean(w2))   # dead at start: 0
for bad in ((1,) * 5, (2, 0, 0, 0, 0)):
    try:
        analyse(REG, A5, Side(T5.unit, wounds=bad), EX)
        raise AssertionError(f"start {bad} accepted")
    except ValueError:
        pass

# --- points metrics ------------------------------------------------------
tgt_cb = unit(4, extra=(cm(points=10, upgrades=1),))
tgt = Side(ru(tgt_cb, 100, "t"))
assert tgt.values() == (18.0,) * 4 + (28.0,)
e = analyse(REG, A5, tgt, EX)
k = e.def_losses.killed
assert abs(e.def_losses.points_removed
           - float(18 * P.mean(k) + 10 * k[5])) < 1e-12    # upgraded last
hero_u = ResolvedUnit("bk", "h", "h", 4, 4, 45, 45,
                      (cm(rules=[R("Hero"), R("Tough", 3)]).model,), (), ())
hs = Side(ru(unit(5), 100), hero=hero_u)
assert hs.points == 145 and hs.values() == (20.0,) * 5 + (45.0,)
v = PM.metrics(a)
assert abs(v["wounds_per100"] - 1.25) < 1e-12        # 5/4 wounds per 100 pts
assert abs(v["killed_per100"] - 1.25) < 1e-12
assert abs(v["points_removed"] - 25.0) < 1e-12        # 20 pts a model
assert v["destroyed"] == 100 / 1024 and "win" not in v and "hits" not in v
assert PM.per100(3.0, 0) is None

# --- flags and warnings -----------------------------------------------------------
td = W("Sniper", 24, 1, R("Takedown"), R("Limited"))
f = analyse(REG, Side(ru(unit(1, (td,)))), Side(ru(unit(5)), hero=hero_u), EX)
assert f.rows[0].flags == ("takedown", "limited")
assert f.rows[0].wounds == f.def_losses.wounds          # one weapon only
issues = analyse(REG, Side(ru(unit(5), issues=["bad choice"])), T5, EX)
assert "u: bad choice" in issues.warnings

# --- melee closed form: 1 v 1, Q4 D4, one Hand Weapon each ---------------
one_a, one_d = Side(ru(unit(1, (CCW,)), 50, "a")), \
    Side(ru(unit(1, (CCW,)), 50, "d"))
m = analyse(REG, one_a, one_d, MELEE)
assert [(r.side, r.phase) for r in m.rows] == [("att", "strike"),
                                               ("def", "back")]
assert m.rows[1].wounds == [F(3, 4), F(1, 4)]          # alone, at the start
assert m.winner == MeleeWinner(F(1, 4), F(3, 16), F(9, 16))
assert m.def_losses.morale == MoraleOutcome(destroyed=F(1, 4))
assert m.att_losses.morale == MoraleOutcome(destroyed=F(3, 16))
assert m.att_losses.points_removed == 50 * 3 / 16
v = PM.metrics(m)
assert abs(v["points_net"] - (50 / 4 - 50 * 3 / 16)) < 1e-12
assert abs(v["win"] + v["lose"] + v["tie"] - 100) < 1e-9
# Same exchange, tie won by the charged unit: the charger tests on a tie.
m2 = analyse(REG, one_a, one_d, Options(ctx=MELEE.ctx, tie="defender",
                                        exact=True))
assert m2.winner == MeleeWinner(F(1, 4), F(3, 4), 0)
assert m2.att_losses.morale.test == F(9, 16)
# No strike back: no defender rows, the charger loses nothing.
m3 = analyse(REG, one_a, one_d, Options(ctx=MELEE.ctx, strike_back=False,
                                        exact=True))
assert [r.side for r in m3.rows] == ["att"] and m3.att_losses.wounds == [1]

# Impact and Counter rows.
imp = Side(ru(unit(2, (CCW,), rules=[R("Impact", 2)])))
spear = W("Spear", 0, 1, R("Counter"))
n = analyse(REG, imp, Side(ru(unit(5, (spear, CCW)))), MELEE)
assert [(r.side, r.phase, r.name) for r in n.rows] == [
    ("att", "impact", "Impact"), ("att", "strike", "Hand Weapon"),
    ("def", "counter", "Spear"), ("def", "back", "Hand Weapon")]
assert n.rows[0].count == 4 and n.rows[0].hits == binom(4, F(5, 6))
assert n.rows[2].flags == ("counter",)

# --- options validation --------------------------------------------------------------
for kw in ({"ctx": ctx(attack="melee", action="hold")}, {"tie": "draw"}):
    try:
        Options(**kw)
        raise AssertionError(f"{kw} accepted")
    except ValueError:
        pass

# --- real data: DAO / BB units, shooting and melee ---------------------------------
import testpaths                                                    # noqa: E402
if not testpaths.USING_SYNTHETIC:
    import time
    from grimdarkoracle.data import af_book as ab
    from grimdarkoracle.data.resolve import resolve
    from grimdarkoracle.rules import registry
    from unitkit import SEM
    books = [ab.load_book(testpaths.book_path(u))
             for u in ("z8205ez2boggzs22", "78qp9l5alslt6yj8")]
    real = registry.RuleRegistry(SEM, ab.load_core_rules(testpaths.rules_path()),
                                 books)
    units = [resolve(b, u) for b in books for u in b.units]
    sh = Options(ctx=ctx(distance=12))
    me = Options(ctx=ctx(attack="melee", action="charge"))
    t0, n = time.time(), 0
    for ua in units:
        for ut in units[::6]:
            for o in (sh, me):
                r = analyse(real, Side(ua), Side(ut), o)
                for loss in (r.def_losses, r.att_losses):
                    if loss is None:
                        continue
                    assert abs(sum(loss.wounds) - 1) < 1e-9, (ua.name, ut.name)
                    assert 0 <= loss.points_removed <= loss.points + 1e-9
                    assert loss.morale.destroyed == loss.destroyed
                if r.winner is not None:
                    w = r.winner
                    assert abs(w.charger + w.charged + w.none - 1) < 1e-9
                PM.metrics(r)
                n += 1
    print(f"analyzer: {n} real analyses in {time.time() - t0:.1f}s")
# --- melee weapon order: the charger's ------------------------------------------
AXE, CLAW = W("Axe", 0, 1), W("Claw", 0, 2)
duo = Side(ru(unit(2, weapons=(AXE, CLAW))))
first = [r.name for r in analyse(REG, duo, T5, MELEE).rows
         if r.side == "att" and r.phase == "strike"]
assert first[0] == "Axe"
opts = Options(ctx=MELEE.ctx, exact=True, weapon_order=("Claw",))
first = [r.name for r in analyse(REG, duo, T5, opts).rows
         if r.side == "att" and r.phase == "strike"]
assert first[0] == "Claw", first
# Melee Takedown preferences of the charger: Options reach the
# charger's strikes; default = the joined Hero (Tough 3, one attack can't
# kill it), m1 picked = 1/2 to hit x 1/2 not blocked.
blade = W("Blade", 0, 1, R("Takedown"))
lone = Side(ru(unit(1, (blade,)), 50, "a"))
host = Side(ru(unit(5), name="t"), hero=hero_u)
nb = Options(ctx=MELEE.ctx, strike_back=False, exact=True)
assert analyse(REG, lone, host, nb).def_losses.killed == [1]
aimed = analyse(REG, lone, host, Options(ctx=MELEE.ctx, strike_back=False,
                                         exact=True, takedown_targets=(0,)))
assert aimed.def_losses.killed == [F(3, 4), F(1, 4)]
print("analyzer_core: OK")
