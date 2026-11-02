"""Eternal Dynasty, Goblin Reclaimers, High Elf Fleets: Fracture, Vicious /
Enhanced, Extra Reach / Enhanced, Instinctive, Deathstrike, Unwieldy Debuff,
Defense(X), the auras; the spell kind "debuff" and rated grants (the rules
once todo: tests/test_token_mechanics.py)."""
import random
from fractions import Fraction as F

import testpaths
import dice_resolve as DR
from grimdarkoracle.app import spells as SP
from grimdarkoracle.engine import melee as ML
from grimdarkoracle.engine.context import AttackContext as Ctx
from grimdarkoracle.engine.context import combatant
from grimdarkoracle.engine.modifiers import build_plan
from grimdarkoracle.rules import effects as E
from unitkit import IDS, REG, R, W, cm, resolved, unit

CHARGE = {"attack": "melee", "action": "charge"}
TODO = ()                       # once todo: test_token_mechanics.py


def groups(att, tgt, weapon="Rifle", reg=REG, **ctx):
    return [g for g in build_plan(reg, att, tgt, Ctx(**ctx)).groups
            if g.weapon.name == weapon]


def one(att, tgt, weapon="Rifle", reg=REG, **ctx):
    gs = groups(att, tgt, weapon, reg, **ctx)
    assert len(gs) == 1, gs
    return gs[0]


for name in ("Fracture", "Vicious", "Enhanced Vicious", "Extra Reach",
             "Enhanced Extra Reach", "Instinctive", "Deathstrike",
             "Unwieldy Debuff", "Defense", "Melee Evasion Aura",
             "Quick Shot Aura", "Enhanced Clan Warrior Aura",
             "Enhanced Highborn Aura", "Enhanced Mischievous Aura"):
    sem = REG.lookup(IDS[name], name)
    assert sem is not None and sem.impl != "todo", name
for name in TODO:
    assert REG.lookup(IDS[name], name).impl == "todo", name

# --- weapon and model rules --------------------------------------------------
fr = unit(weapons=(W("Lance", 24, 1, R("Fracture")),))
assert one(fr, unit(), "Lance").spec.ap_on_6 == 2
vic = unit(rules=[R("Vicious")])
evic = unit(rules=[R("Vicious"), R("Enhanced Vicious")])
assert one(vic, unit()).spec.reroll_defense_6
assert one(evic, unit()).spec.reroll_defense_on == 5
assert one(unit(rules=[R("Enhanced Vicious")]), unit()
           ).spec.reroll_defense_on == 0                # needs Vicious
er = unit(rules=[R("Extra Reach")])
eer = unit(rules=[R("Extra Reach"), R("Enhanced Extra Reach")])
assert groups(er, unit(), distance=28) and not groups(er, unit(), distance=29)
assert groups(eer, unit(), distance=32) and not groups(eer, unit(),
                                                        distance=33)
assert not groups(unit(rules=[R("Enhanced Extra Reach")]), unit(),
                  distance=25)
ins = unit(rules=[R("Instinctive")])
assert one(ins, unit()).spec.hit_mod == 1
assert one(ins, unit(), "Hand Weapon", **CHARGE).spec.hit_mod == 1
assert one(ins, unit(), "Hand Weapon", attack="melee",
           action=None).spec.hit_mod == 0                # strike back
dfx = unit(rules=[R("Defense", 2)])
assert one(unit(), dfx).targets[0].defense_mod == 2

# --- Deathstrike: X hits when killed in melee, no removal -------------
def ds_setup(back):
    a = unit(1, weapons=(W("Blade", 0, 1),), rules=[R("Deathstrike", 2)])
    d = unit(3, weapons=(W("Blade", 0, 1),))
    return ML.MeleeSetup(REG, combatant(resolved(a)),
                         combatant(resolved(d)), back)


res = ML.resolve(ds_setup(False), exact=True)       # never killed: no hits
assert res.attacker().killed() == [1]
assert res.defender().killed() == [F(3, 4), F(1, 4)]
res = ML.resolve(ds_setup(True), exact=True)
# by cases: the charger kills k (k=0: 3/4, k=1: 1/4), then 3-k models
# strike back and kill it with q_k = 1 - (3/4)^(3-k); if so, its 2 hits
# (each a kill on 1/2, D4) fall on the 3-k left
base = [F(3, 4), F(1, 4)]
two = [F(1, 4), F(1, 2), F(1, 4)]
want, p_dead = [0] * 4, 0
for k, p in enumerate(base):
    q = 1 - F(3, 4) ** (3 - k)
    p_dead += p * q
    want[k] += p * (1 - q)
    for j, r in enumerate(two):
        want[k + j] += p * q * r
assert res.attacker().killed()[1] == p_dead == F(139, 256)
got = res.defender().killed()
assert got == want[:len(got)] and sum(want[len(got):]) == 0, got
rng = random.Random(45)
setup = ds_setup(True)
n = 20000
k1 = sum(setup.d_alloc.killed(DR.resolve_melee(setup, rng=rng)[1]) >= 1
         for _ in range(n))
p1 = float(1 - want[0])
assert abs(k1 / n - p1) < 4 * (p1 * (1 - p1) / n) ** 0.5, (k1 / n, p1)

# --- Unwieldy Debuff and the auras -------------------------------------------
g = SP.rule_buff_grants(REG, IDS["Unwieldy Debuff"])
assert [(r.id, a) for r, _to, a in g] == [(IDS["Unwieldy"], "melee")]
for aura, rule in (("Melee Evasion Aura", "Melee Evasion"),
                   ("Enhanced Clan Warrior Aura", "Enhanced Predator"),
                   ("Enhanced Highborn Aura", "Enhanced Extra Reach"),
                   ("Enhanced Mischievous Aura", "Enhanced Vicious")):
    u = unit(4, extra=(cm(rules=[R(aura)]),))
    v = E.View(REG, Ctx(), "defender", u, (), u, ())
    holds, missing = E.holdings(REG, v)
    assert not missing and all(any(h.sem.name == rule for h in hs)
                               for hs in holds), aura

# --- the real books ----------------------------------------------------------
if not testpaths.USING_SYNTHETIC:
    from grimdarkoracle.app import side_spec as S
    from grimdarkoracle.app.library import Library
    from grimdarkoracle.app.setup_model import Setup, SideSetup
    from grimdarkoracle.rules import spells as RS
    lib = Library.load(testpaths.DATA_DIR)
    sreg = RS.SpellRegistry(RS.load(), lib.reg, list(lib.books.values()))
    books = {b.name: b for b in lib.books.values()}
    he, gob = books["High Elf Fleets"], books["Goblin Reclaimers"]

    def spell(book, name):
        return sreg.lookup(book, next(s for s in book.spells
                                      if s.name.strip() == name))

    coi = spell(he, "Creator of Illusions")
    assert coi.kind == "debuff"
    assert [(r.name, a) for r, _t, a in coi.grants] == [("Unwieldy", "melee")]
    menu = SP.buff_menu(sreg, he, gob)
    assert any(b.key == coi.key and b.label.endswith("on the target)")
               for b in menu if b.side == "att")
    shroud = spell(gob, "Shroud Field")
    assert [(r.name, r.rating) for r, _t, _a in shroud.grants] == [
        ("Defense", 1)]
    # the debuff spell reaches the target: its charge strikes come last
    tid = next(k for k, u in gob.units.items()
               if S.book_side(gob, k) is not None and any(
                   not w.range for w in u.weapons))
    att = next(iter(he.units))
    runs = [S.run(lib.reg, S.book_side(gob, tid), SideSetup(),
                  S.book_side(he, att), SideSetup(),
                  Setup(attack="melee", action="charge",
                        buffs=b), sreg, exact=True)
            for b in ((), (("def", coi.key),))]
    assert "last" not in {r.phase for r in runs[0].rows}
    assert "last" in {r.phase for r in runs[1].rows if r.side == "att"}
    left = {s for _b, s, st in sreg.coverage([gob]) if st != "ok"}
    assert not left                            # Pow!: test_token_mechanics.py

print("test_group4 OK")
