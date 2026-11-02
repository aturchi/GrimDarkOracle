"""app.order_advice: the suggestion of an Analyzer attack
(shooting, charge with the charger's Takedown preferences, spell and
barred attacks: none) equals the analysis run with the suggested order;
the lines; analyzer_orders.moved (the Up / Down of the order dialogs).
Synthetic data."""
from spellkit import ru
from unitkit import R, W, REG, CCW, unit, ctx
from grimdarkoracle.app import analyzer_orders as AO
from grimdarkoracle.app import order_advice as OA
from grimdarkoracle.app.analyzer_core import Options, Side, analyse
from grimdarkoracle.engine import pmf as P

flamer = W("Flamer", 12, 1, R("Blast", 3))
GUNS = (W("Gun A", 24, 2), W("Gun B", 24, 1, R("AP", 1)), flamer)
att = Side(ru(unit(2, GUNS), "Shooters"))
tgt = Side(ru(unit(5), "Targets"))
SH = Options(ctx=ctx(attack="shooting", distance=12, action="hold"))


def killed(a, t, opts):
    return float(P.mean(analyse(REG, a, t, opts).def_losses.killed))


# --- Analyzer ----------------------------------------------------------------------------
sg = OA.analyzer(REG, att, tgt, SH)
assert sg.improves and sg.exact
from dataclasses import replace                             # noqa: E402
best = replace(SH, weapon_order=sg.order)
assert abs(sg.best.killed - killed(att, tgt, best)) < 1e-9
assert abs(sg.book.killed - killed(att, tgt, SH)) < 1e-9
line = OA.line(sg)
assert line.startswith("Best weapon order: ") and "every order checked" in \
    line and "your order" not in line
assert "your order" in OA.line(OA.analyzer(REG, att, tgt, best), best.
                               weapon_order)
# A wounded target: the start state counts.
hurt = replace(tgt, wounds=(1, 1, 0, 0, 0))
sw = OA.analyzer(REG, att, hurt, SH)
assert abs(sw.book.killed - killed(att, hurt, SH)) < 1e-9
# Charge: the charger's strikes, its Takedown preferences used.
axe, claw = W("Axe", 0, 2, R("AP", 1)), W("Claw", 0, 1, R("Blast", 3))
chg = Side(ru(unit(3, (axe, claw, CCW)), "Chargers"))
ME = Options(ctx=ctx(attack="melee", action="charge"))
sm = OA.analyzer(REG, chg, tgt, ME)
assert abs(sm.book.killed - killed(chg, tgt, ME)) < 1e-9
assert abs(sm.best.killed - killed(chg, tgt, replace(
    ME, weapon_order=sm.order))) < 1e-9
blade = W("Blade", 0, 1, R("Takedown"))
hero = ru(unit(1, rules=(R("Hero"), R("Tough", 3))), "Hero")
host = Side(ru(unit(4), "Host"), hero)
td = Side(ru(unit(2, (blade, CCW)), "Duelists"))
pref = replace(ME, takedown_targets=(0,), strike_back=False)
st = OA.analyzer(REG, td, host, pref)
assert abs(st.book.killed - killed(td, host, pref)) < 1e-9
assert abs(st.book.killed - killed(td, host, replace(
    pref, takedown_targets=()))) > 0.1               # preferences matter
snipers = Side(ru(unit(2, (W("Snipe", 24, 1, R("Takedown")), flamer)), "S"))
spref = replace(SH, takedown_targets=(0,))
ss = OA.analyzer(REG, snipers, host, spref)
assert abs(ss.book.killed - killed(snipers, host, spref)) < 1e-9
assert abs(ss.book.killed - killed(snipers, host, SH)) > 0.1
# No order: a spell, an attack the rules forbid, a book order already best.
assert OA.analyzer(REG, replace(att, shaken=True), tgt, SH) is None
plain = OA.analyzer(REG, Side(ru(unit(2, GUNS[:2]), "P")), tgt, SH)
assert not plain.improves and "already the best" in OA.line(plain)
assert OA.line(None) == ""
assert OA.for_dialog(None, ("Gun A",)) == (["Gun A"],
                                           "No weapon order to suggest "
                                           "for this attack.")
assert OA.for_dialog(plain)[0] is None
assert OA.for_dialog(sg)[0] == list(sg.order)

# --- moved (the order dialogs' Up / Down) ------------
assert AO.moved([0, 1, 2], 2, -1) == [0, 2, 1]
assert AO.moved([0, 1, 2], 0, -1) == [0, 1, 2]          # clamped
assert AO.moved([0, 1, 2], 0, 5) == [1, 2, 0]
print("order_advice: OK")
