"""Unwieldy (a melee phase after the strike back)
and Regenerative Strength (wound dice, one per token of an Analyzer menu).
Closed forms on duels whose order matters, Monte Carlo
parity with tests/dice_resolve, the Analyzer's rows and menus."""
import random
from fractions import Fraction as F

import testpaths  # noqa: F401  (sys.path)
import dice_resolve as DR
from grimdarkoracle.app import analyzer_core as AC
from grimdarkoracle.app import setup_model as SM
from grimdarkoracle.data import rule_weapons as RW
from grimdarkoracle.engine import gf_math as G
from grimdarkoracle.engine import melee as ML
from grimdarkoracle.engine.context import AttackContext as Ctx
from grimdarkoracle.engine.context import combatant
from grimdarkoracle.engine.modifiers import build_plan
from grimdarkoracle.engine.specs import TargetSpec
from unitkit import IDS, REG, R, W, resolved, unit

CHARGE = Ctx("melee", action="charge")
BACK = Ctx("melee", action=None)
for name in ("Unwieldy", "Regenerative Strength"):
    assert REG.lookup(IDS[name], name).impl != "todo", name


def blade(*rules):
    return W("Blade", 0, 1, *rules)


def duel(att_rules=(), w_rules=()):
    """Both 1 model, Quality 4+, Defense 4+, one attack AP 0: each strike
    kills on 1/4."""
    a = unit(1, weapons=(blade(*w_rules),), rules=list(att_rules))
    d = unit(1, weapons=(blade(),))
    return ML.MeleeSetup(REG, combatant(resolved(a)), combatant(resolved(d)))


# --- Unwieldy: the plan flag, the steps, the phase order ---------------
uw = unit(1, weapons=(blade(),), rules=[R("Unwieldy")])
assert all(g.last for g in build_plan(REG, uw, unit(), CHARGE).groups)
assert not any(g.last for g in build_plan(REG, uw, unit(), BACK).groups)
two = unit(1, weapons=(blade(R("Unwieldy")), W("Knife", 0, 1)))
assert {g.weapon.name: g.last for g in build_plan(REG, two, unit(),
                                                   CHARGE).groups} == {
    "Blade": True, "Knife": False}
st = duel(att_rules=[R("Unwieldy")])
seq = st.seq("att", (0,))
assert not st.steps("strike", seq) and len(st.steps("last", seq)) == 1
for setup, def_killed, att_killed in (
        (duel(), F(1, 4), F(3, 16)),                    # charger first
        (duel(att_rules=[R("Unwieldy")]), F(3, 16), F(1, 4)),
        (duel(w_rules=[R("Unwieldy")]), F(3, 16), F(1, 4))):
    res = ML.resolve(setup, exact=True)
    assert res.defender().killed()[1] == def_killed
    assert res.attacker().killed()[1] == att_killed
# no strike back: the Unwieldy strikes still happen (last)
nb = ML.MeleeSetup(REG, combatant(resolved(uw)),
                   combatant(resolved(unit(1, weapons=(blade(),)))), False)
assert ML.resolve(nb, exact=True).defender().killed()[1] == F(1, 4)
# Monte Carlo oracle follows the same phases
rng = random.Random(42)
n, setup = 20000, duel(att_rules=[R("Unwieldy")])
kd = sum(DR.resolve_melee(setup, rng=rng)[1] != setup.d_alloc.fresh()
         for _ in range(n))
assert abs(kd / n - 3 / 16) < 4 * (3 / 16 * 13 / 16 / n) ** 0.5, kd / n
# the Analyzer shows the phase
an = AC.analyse(REG, AC.Side(resolved(uw)), AC.Side(resolved(unit(1))),
                AC.Options(ctx=CHARGE, exact=True))
assert [r.phase for r in an.rows if r.side == "att"] == ["last"]

# --- Regenerative Strength: one wound die per token, 4+, first ---------------
RS = IDS["Regenerative Strength"]
rs = RW.add_all(resolved(unit(1, rules=[R("Regenerative Strength")])))
assert rs.models[0].weapons[0][0].name == "Regenerative Strength"
rsu = combatant(rs)


def rs_groups(ctx):
    return [g for g in build_plan(REG, rsu, unit(), ctx).groups
            if g.weapon.name == "Regenerative Strength"]


assert not rs_groups(CHARGE)                            # no token, no die
assert ("Regenerative Strength", "Regenerative Strength: no token", (0,)) \
    in build_plan(REG, rsu, unit(), CHARGE).excluded
g, = rs_groups(Ctx("melee", action="charge", versatile=((RS, 2),)))
assert (g.spec.attacks, g.spec.quality, g.spec.no_block) == (3, 4, True)
assert G.weapon_wounds(g.spec, TargetSpec(defense=4), 10, True) == [
    F(1, 8), F(3, 8), F(3, 8), F(1, 8)]
assert rs_groups(Ctx("melee", action=None, versatile=((RS, 0),)))  # back
assert not rs_groups(Ctx(versatile=((RS, 0),)))         # shooting
tired = combatant(rs, fatigued=True)
assert not [x for x in build_plan(REG, tired, unit(), Ctx(
    "melee", action="charge", versatile=((RS, 0),))).groups
    if x.weapon.name == "Regenerative Strength"]
assert SM.versatile(REG, rs) == [(RS, "Regenerative Strength", [
    "1 token", "2 tokens", "3 tokens", "4 tokens", "5 tokens", "6 tokens"])]

# --- No Retreat: a failed test counts as passed, then its wounds ------
from grimdarkoracle.app import result_rows as RR
from grimdarkoracle.engine import kill_chain as K
from grimdarkoracle.engine import morale as MO
from grimdarkoracle.engine.target_state import Allocation


def after(rules, shaken=False):
    cb = combatant(resolved(unit(2, rules=rules)), shaken=shaken)
    al = Allocation.of(cb)
    half = al.wound(al.fresh(), 0, 1)               # 1 of 2 dead: a test
    chain = K.ChainResult(al, al.fresh(), {half: F(1)})
    return MO.after_shooting(MO.Morale(REG, cb, None, Ctx()), chain, True)


plain = after([])
assert (plain.test, plain.shaken, plain.held) == (1, F(1, 2), 0)
assert plain.self_wounds == []
nr = after([R("No Retreat")])
assert (nr.test, nr.shaken, nr.held) == (1, 0, F(1, 2))
assert nr.self_wounds == [F(3, 4), F(1, 4)]     # 1 wound left, a 1-3
assert after([R("No Retreat")], shaken=True).shaken == 1
cb = combatant(resolved(unit(1, rules=[R("No Retreat")],
                             extra=unit(2).models)))
m3 = MO.Morale(REG, cb, None, Ctx())
assert not m3.no_retreat(m3.alloc.fresh(), "shooting")     # 1 of 3
fl = after([R("No Retreat"), R("Fearless")])
assert (fl.shaken, fl.held) == (0, F(1, 4))     # Fearless first
an = AC.analyse(REG, AC.Side(resolved(unit(10))), AC.Side(resolved(unit(
    2, d=6, rules=[R("No Retreat")]))), AC.Options(exact=True))
assert an.def_losses.morale.shaken == 0 and an.def_losses.morale.held > 0
law = an.def_losses.morale.self_wounds
held = an.def_losses.morale.held
assert sum(law) == 1 and law[1:] == [held / 2]  # tests at half: 1 wound left
assert any("No Retreat" in k for k, _v in RR.outcome_lines(an))

# --- Self-Destruct(X): X hits after the exchange, the holder removed --
def sd_setup(back=True, x=2):
    a = unit(1, weapons=(), rules=[R("Self-Destruct", x)])
    d = unit(3, weapons=(blade(),))
    return ML.MeleeSetup(REG, combatant(resolved(a)),
                         combatant(resolved(d)), back)


res = ML.resolve(sd_setup(back=False), exact=True)
assert res.defender().killed() == [F(1, 4), F(1, 2), F(1, 4)]  # 2 hits, D4
assert res.attacker().killed() == [0, 1]                       # removed
# the removal is no wound taken for the melee result: a win unless 0 kills
m_a = MO.Morale(REG, res.setup.att)
m_d = MO.Morale(REG, res.setup.dfn)
w = MO.melee_winner(m_a, m_d, res, "none")
assert (w.charger, w.charged, w.none) == (F(3, 4), 0, F(1, 4))
# killed by the strike back first: its hits still come
res = ML.resolve(sd_setup(), exact=True)
assert res.defender().killed() == [F(1, 4), F(1, 2), F(1, 4)]
assert res.attacker().killed() == [0, 1]
# no Self-Destruct in the unit: the exchange as before
plain_melee = ML.resolve(duel(), exact=True)
assert not plain_melee.setup.self_destruct and plain_melee.extra is None
# Monte Carlo oracle
rng = random.Random(43)
setup = sd_setup()
counts = [0, 0, 0]
for _ in range(20000):
    _a, d, _log = DR.resolve_melee(setup, rng=rng)
    counts[setup.d_alloc.killed(d)] += 1
for k, exact_p in enumerate((1 / 4, 1 / 2, 1 / 4)):
    assert abs(counts[k] / 20000 - exact_p) < 4 * (exact_p * (1 - exact_p)
                                                   / 20000) ** 0.5, counts

# --- Surprise Attack(X): X dice within 6", each 2+ a hit AP(1) --------
sa = RW.add_all(resolved(unit(1, rules=[R("Surprise Attack", 3)])))
w0 = next(w for w, _n in sa.models[0].weapons if w.name == "Surprise Attack")
assert (w0.range, w0.attacks) == (6, 3)
sac = combatant(sa)


def sa_groups(tgt=None, **ctx):
    return [g for g in build_plan(REG, sac, tgt or unit(), Ctx(**ctx)).groups
            if g.weapon.name == "Surprise Attack"]


g, = sa_groups(distance=6)
assert (g.spec.attacks, g.spec.quality, g.spec.ap, g.limited) == \
    (3, 2, 1, True)
assert G.weapon_hits(g.spec, 1, True) == [
    F(1, 216), F(15, 216), F(75, 216), F(125, 216)]
assert not sa_groups(distance=7)                        # out of range
assert not sa_groups(attack="melee", action="charge")
assert not sa_groups(distance=6, line_of_sight=False)
assert sa_groups(distance=6, action="rush")             # at its activation
g, = sa_groups(unit(rules=[R("Stealth")]), distance=6)
assert g.spec.hit_mod == 0                              # not a to-hit roll

# --- the book's Unwieldy (a weapon rule of Hive Warriors' Toxin Whips)
if not testpaths.USING_SYNTHETIC:
    from grimdarkoracle.app.library import Library
    from grimdarkoracle.data.af_book import RuleRef
    lib = Library.load(testpaths.DATA_DIR)
    ah = next(b for b in lib.books.values() if b.name == "Alien Hives")
    rid = next(k for k, d in ah.rules.items() if d.name == "Unwieldy")
    whip = W("Toxin Whip", 0, 1, RuleRef(rid, "Unwieldy", None, "Unwieldy"))
    a = AC.analyse(lib.reg, AC.Side(resolved(unit(3, weapons=(whip,)))),
                   AC.Side(resolved(unit(5))),
                   AC.Options(ctx=CHARGE, exact=True))
    assert {r.phase for r in a.rows if r.side == "att"} == {"last"}

print("test_melee_mechanics OK")
