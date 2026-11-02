"""the rules of the Brothers / Prime Brothers families, the four
Disciples and Havoc Brothers: Predator (one new attack
per Predator result), the "Enhanced ..." rules (lift_distance, a ward
replacing another, deltas), Warding, Versatile Warrior and their auras.
Closed forms on hand-built units; the alias names (Bloodborn, ...) on the
real books when present."""
import random
from fractions import Fraction as F

import testpaths
import dice_resolve as DR
import mc_support as MC
from grimdarkoracle.engine import gf_math as G
from grimdarkoracle.engine.context import AttackContext as Ctx
from grimdarkoracle.engine.modifiers import build_plan
from grimdarkoracle.engine.specs import AttackSpec
from grimdarkoracle.rules import effects as E
from unitkit import IDS, REG, R, W, cm, unit

CHARGE = {"attack": "melee", "action": "charge"}
FAR_CHARGE = dict(CHARGE, charge_distance=8)
MAPPED = (
    "Predator", "Enhanced Predator", "Shrouded", "Enhanced Shrouded",
    "Warding", "Enhanced Warding", "Versatile Warrior",
    "Enhanced Versatile Warrior", "Piercing Warrior",
    "Enhanced Piercing Warrior", "Screened", "Enhanced Screened", "Violent",
    "Enhanced Violent", "Enhanced Protected", "Nimble", "Enhanced Nimble",
    "Enhanced Agile", "Rapid Ambush", "Enhanced Bloodborn Aura",
    "Enhanced Darkborn Aura", "Enhanced Knightborn Aura",
    "Enhanced Watchborn Aura", "Enhanced Wolfborn Aura",
    "Enhanced Havocbound Aura", "Enhanced Changebound Aura",
    "Enhanced Lustbound Aura", "Enhanced Plaguebound Aura",
    "Enhanced Warbound Aura")


def groups(att, tgt, weapon, reg=REG, **ctx):
    return [g for g in build_plan(reg, att, tgt, Ctx(**ctx)).groups
            if g.weapon.name == weapon]


def one(att, tgt, weapon="Rifle", reg=REG, **ctx):
    gs = groups(att, tgt, weapon, reg, **ctx)
    assert len(gs) == 1, gs
    return gs[0]


def melee(att, tgt, reg=REG, **ctx):
    return one(att, tgt, "Hand Weapon", reg, **dict(CHARGE, **ctx))


def wards(tgt, weapon="Rifle", reg=REG, **ctx):
    return one(unit(), tgt, weapon, reg, **ctx).targets[0].wards


for name in MAPPED:
    sem = REG.lookup(IDS[name], name)
    assert sem is not None and sem.impl != "todo", name

# --- Predator: closed forms of one attack ------------------------------
def law(**kw):
    return G.weapon_hits(AttackSpec(attacks=1, quality=4, **kw), 1, True)


assert law(extra_attack_on=6) == [F(1, 2), F(5, 12), F(1, 12)]
assert law(extra_attack_on=5) == [F(1, 2), F(1, 3), F(1, 6)]
# a 5 that misses (Quality 6+) never triggers; a 6 always hits
assert G.weapon_hits(AttackSpec(attacks=1, quality=6, extra_attack_on=5),
                     1, True) == [F(5, 6), F(5, 36), F(1, 36)]
assert law(extra_attack_on=6, fatigued=True) == law(fatigued=True)
assert law(extra_attack_on=6, auto_hit=True) == law(auto_hit=True)
# the new attack is an ordinary attack: its 6s are six-hits (Rending)
pairs = G.weapon_hit_pairs(AttackSpec(attacks=1, quality=4,
                                      extra_attack_on=6), 1, True)
assert pairs[(0, 2)] == F(1, 36) and pairs[(1, 1)] == F(1, 18)
# Monte Carlo oracle (tests/dice_resolve): Blast, Surge, Enhanced, AP
spec = AttackSpec(attacks=3, quality=4, hit_mod=-1, extra_attack_on=5,
                  extra_hits_on_6=1, blast=3)
rng = random.Random(37)
samples = [sum(DR.roll_hits(spec, 5, rng)) for _ in range(20000)]
ok, msg = MC.parity("Predator hits", G.weapon_hits(spec, 5), samples)
assert ok, msg

# --- Predator in the plan ----------------------------------------------------
pred = unit(rules=[R("Predator")])
epred = unit(rules=[R("Predator"), R("Enhanced Predator")])
assert one(pred, unit()).spec.extra_attack_on == 6
assert melee(pred, unit()).spec.extra_attack_on == 6
assert one(epred, unit()).spec.extra_attack_on == 5
assert one(unit(rules=[R("Enhanced Predator")]), unit()
           ).spec.extra_attack_on == 0                  # needs Predator

# --- Shrouded: -4" (Enhanced: -8") to shooting, min 6" ------------
shr = unit(rules=[R("Shrouded")])
eshr = unit(rules=[R("Shrouded"), R("Enhanced Shrouded")])
assert groups(unit(), shr, "Rifle", distance=20)
assert not groups(unit(), shr, "Rifle", distance=21)
assert groups(unit(), eshr, "Rifle", distance=16)
assert not groups(unit(), eshr, "Rifle", distance=17)
assert groups(unit(rules=[]), unit(rules=[R("Enhanced Shrouded")]), "Rifle",
              distance=24)                              # needs Shrouded
pistol = unit(weapons=(W("Pistol", 12, 1),))
assert groups(pistol, eshr, "Pistol", distance=6)       # floor 6"
assert not groups(pistol, eshr, "Pistol", distance=7)
assert melee(unit(), eshr).spec.attacks == 5            # charge: positional

# --- Warding: spells 2+, others 6+ only when far; Enhanced: always ----------
wd = unit(rules=[R("Warding")])
ewd = unit(rules=[R("Warding"), R("Enhanced Warding")])
assert wards(wd, distance=12) == (6,) and wards(wd, distance=9) == ()
assert wards(wd, "Hand Weapon", **FAR_CHARGE) == (6,)
assert wards(wd, "Hand Weapon", **CHARGE) == ()
assert wards(wd, "Hand Weapon", attack="melee", action=None) == ()
assert wards(ewd, distance=9) == (6,)
assert wards(ewd, "Hand Weapon", **CHARGE) == (6,)
assert wards(ewd, "Hand Weapon", attack="melee", action=None) == ()
v = E.View(REG, Ctx(attack="spell", distance=3), "defender", wd, (), wd, ())
holds, _ = E.holdings(REG, v)
from grimdarkoracle.engine.modifiers import wards as ward_rolls
from dataclasses import replace
assert ward_rolls(replace(v, holds=holds), spell=True) == (2,)
mixed = unit(2, rules=[R("Warding"), R("Enhanced Warding")],
             extra=unit(3, rules=[R("Warding")]).models)
assert wards(mixed, distance=9) == ()                   # Enhanced not most

# --- Enhanced Protected replaces Protected (6+ -> 5+) ------------------------
prot = unit(rules=[R("Protected")])
eprot = unit(rules=[R("Protected"), R("Enhanced Protected")])
assert wards(prot) == (6,) and wards(eprot) == (5,)
assert wards(unit(rules=[R("Enhanced Protected")])) == ()   # needs Protected

# --- Versatile Warrior and the lift of Enhanced ... ---------------
VW = IDS["Versatile Warrior"]
vw = unit(rules=[R("Versatile Warrior")])
evw = unit(rules=[R("Versatile Warrior"), R("Enhanced Versatile Warrior")])
ap, hit = ((VW, 0),), ((VW, 1),)
assert one(vw, unit(), versatile=ap, distance=12).spec.ap == 1
assert one(vw, unit(), versatile=ap, distance=9).spec.ap == 0
assert one(vw, unit(), distance=12).spec.ap == 0        # no pick: no effect
assert one(evw, unit(), versatile=ap, distance=9).spec.ap == 1
assert melee(vw, unit(), versatile=hit, charge_distance=8).spec.hit_mod == 1
assert melee(vw, unit(), versatile=hit).spec.hit_mod == 0
assert melee(evw, unit(), versatile=hit).spec.hit_mod == 1
assert melee(evw, unit(), versatile=hit, action=None).spec.hit_mod == 0
# the lift is per model: "If this model has ..."
half = unit(1, rules=[R("Versatile Warrior"), R("Enhanced Versatile Warrior")],
            extra=unit(1, rules=[R("Versatile Warrior")]).models)
aps = sorted(g.spec.ap for g in groups(half, unit(), "Rifle", versatile=ap,
                                       distance=9))
assert aps == [0, 1], aps
part = unit(1, rules=[R("Versatile Warrior")], extra=unit(1).models)
aps = sorted(g.spec.ap for g in groups(part, unit(), "Rifle", versatile=ap,
                                       distance=12))
assert aps == [0, 1], aps                               # holders only

# --- Piercing Warrior, Violent (Warbound), Screened (Changebound) -----------
pw = unit(rules=[R("Piercing Warrior")])
epw = unit(rules=[R("Piercing Warrior"), R("Enhanced Piercing Warrior")])
assert (one(pw, unit(), distance=12).spec.ap,
        one(pw, unit(), distance=9).spec.ap) == (1, 0)
assert one(epw, unit(), distance=9).spec.ap == 1
assert melee(epw, unit()).spec.ap == 1 and melee(pw, unit()).spec.ap == 0
assert melee(epw, unit(), action=None).spec.ap == 0      # strike back
assert one(unit(rules=[R("Enhanced Piercing Warrior")]), unit(),
           distance=12).spec.ap == 0                     # needs the base
vio = unit(rules=[R("Violent")])
evio = unit(rules=[R("Violent"), R("Enhanced Violent")])
assert (one(vio, unit(), distance=12).spec.shred,
        one(vio, unit(), distance=9).spec.shred) == (1, 0)
assert one(evio, unit(), distance=9).spec.shred == 1
assert (melee(vio, unit(), charge_distance=8).spec.shred,
        melee(vio, unit()).spec.shred, melee(evio, unit()).spec.shred) == \
    (1, 0, 1)
scr = unit(rules=[R("Screened")])
escr = unit(rules=[R("Screened"), R("Enhanced Screened")])
assert (one(unit(), scr, distance=12).spec.hit_mod,
        one(unit(), scr, distance=9).spec.hit_mod) == (-1, 0)
assert one(unit(), escr, distance=9).spec.hit_mod == -1
assert melee(unit(), escr).spec.hit_mod == -1
assert melee(unit(), escr, action=None).spec.hit_mod == 0   # strike back
mscr = unit(2, rules=[R("Screened"), R("Enhanced Screened")],
            extra=unit(3, rules=[R("Screened")]).models)
assert one(unit(), mscr, distance=9).spec.hit_mod == 0      # Enhanced: 2/5

# --- the Enhanced auras give the Enhanced rule to the whole unit -------------
for aura, rule in (("Enhanced Bloodborn Aura", "Enhanced Predator"),
                   ("Enhanced Darkborn Aura", "Enhanced Shrouded"),
                   ("Enhanced Knightborn Aura", "Enhanced Warding"),
                   ("Enhanced Watchborn Aura", "Enhanced Versatile Warrior"),
                   ("Enhanced Wolfborn Aura", "Enhanced Nimble"),
                   ("Enhanced Havocbound Aura", "Enhanced Piercing Warrior"),
                   ("Enhanced Changebound Aura", "Enhanced Screened"),
                   ("Enhanced Lustbound Aura", "Enhanced Agile"),
                   ("Enhanced Plaguebound Aura", "Enhanced Protected"),
                   ("Enhanced Warbound Aura", "Enhanced Violent")):
    u = unit(4, extra=(cm(rules=[R(aura)]),))
    hv = E.View(REG, Ctx(), "defender", u, (), u, ())
    holds, missing = E.holdings(REG, hv)
    assert not missing and all(any(h.sem.name == rule for h in hs)
                               for hs in holds), aura
ewa = unit(4, rules=[R("Warding")],
           extra=(cm(rules=[R("Warding"), R("Enhanced Knightborn Aura")]),))
assert wards(ewa, distance=9) == (6,)

# --- no combat effect --------------------------------------------------------
for name in ("Nimble", "Enhanced Nimble", "Enhanced Agile", "Rapid Ambush"):
    u = unit(rules=[R(name)])
    for a, t in ((u, unit()), (unit(), u)):
        p, q = build_plan(REG, a, t, Ctx()), build_plan(REG, unit(), unit(),
                                                        Ctx())
        assert [x.spec for x in p.groups] == [x.spec for x in q.groups], name
        assert not p.warnings, (name, p.warnings)

# --- the books' names (aliases) on the real data -----------------------------
if not testpaths.USING_SYNTHETIC:
    from grimdarkoracle.app.library import Library
    from grimdarkoracle.data.af_book import RuleRef
    lib = Library.load(testpaths.DATA_DIR)
    reg = lib.reg

    def book_rule(name):
        rid = next(r for r, d in reg.defs.items() if d.name == name)
        return RuleRef(rid, name, None, name)

    def rules(*names):
        return unit(rules=[book_rule(n) for n in names])

    blood = rules("Bloodborn", "Enhanced Bloodborn")
    assert one(blood, unit(), reg=reg).spec.extra_attack_on == 5
    assert one(rules("Bloodborn"), unit(), reg=reg).spec.extra_attack_on == 6
    assert not groups(unit(), rules("Darkborn", "Enhanced Darkborn"),
                      "Rifle", reg, distance=17)
    assert wards(rules("Knightborn", "Enhanced Knightborn"), reg=reg,
                 distance=9) == (6,)
    assert wards(rules("Plaguebound", "Enhanced Plaguebound"), reg=reg) == (5,)
    assert wards(rules("Plaguebound"), reg=reg) == (6,)
    assert one(rules("Havocbound", "Enhanced Havocbound"), unit(), reg=reg,
               distance=9).spec.ap == 1
    assert one(rules("Warbound", "Enhanced Warbound"), unit(), reg=reg,
               distance=9).spec.shred == 1
    assert one(unit(), rules("Changebound", "Enhanced Changebound"), reg=reg,
               distance=9).spec.hit_mod == -1
    assert one(unit(), rules("Changebound"), reg=reg,
               distance=9).spec.hit_mod == 0
    wid = IDS["Versatile Warrior"]
    from grimdarkoracle.app import setup_model as SM
    from grimdarkoracle.data.resolve import resolve
    wb = next(b for b in lib.books.values() if b.name == "Watch Brothers")
    wuid = next(k for k, u in wb.units.items()
                if u.name == "Watch Battle Brothers")
    assert SM.versatile(reg, resolve(wb, wuid, ())) == [
        (wid, "Watchborn", ["AP(+1)", "+1 to hit"])]
    assert one(rules("Watchborn", "Enhanced Watchborn"), unit(), reg=reg,
               versatile=((wid, 0),), distance=9).spec.ap == 1

print("test_enhanced OK")
