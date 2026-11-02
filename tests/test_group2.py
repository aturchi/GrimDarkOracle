"""Rules and spells of Alien Hives, Blessed Sisters and Custodian
Brothers: Brutal / Enhanced Brutal, Valiant (the Morale
Test reads the attack it follows), Enhanced Fortified, Disintegrate,
Fragment, Piercing Target, Piercing Growth, their auras (the rules once
`todo` are in tests/test_melee_mechanics.py).
Hand-built units; the books' names and spells on the real data."""

import testpaths
from grimdarkoracle.engine.context import AttackContext as Ctx
from grimdarkoracle.engine.modifiers import build_plan
from grimdarkoracle.engine.morale import Morale
from grimdarkoracle.rules import effects as E
from unitkit import IDS, REG, R, W, cm, unit

GROUP = ("Alien Hives", "Blessed Sisters", "Custodian Brothers")
TODO = ()                       # once todo: test_melee_mechanics.py
CHARGE = {"attack": "melee", "action": "charge"}


def groups(att, tgt, weapon="Rifle", reg=REG, **ctx):
    return [g for g in build_plan(reg, att, tgt, Ctx(**ctx)).groups
            if g.weapon.name == weapon]


def one(att, tgt, weapon="Rifle", reg=REG, **ctx):
    gs = groups(att, tgt, weapon, reg, **ctx)
    assert len(gs) == 1, gs
    return gs[0]


def melee(att, tgt, reg=REG, **ctx):
    return one(att, tgt, "Hand Weapon", reg, **dict(CHARGE, **ctx))


for name in ("Brutal", "Enhanced Brutal", "Valiant", "Enhanced Valiant",
             "Enhanced Fortified", "Disintegrate", "Fragment",
             "Piercing Target", "Piercing Growth", "Predator Aura",
             "Enhanced Devout Aura", "Enhanced Guardian Aura",
             "Enhanced Hive Bond Aura", "Dash", "Dash Aura", "Rapid Charge",
             "Hit & Run Fighter"):
    sem = REG.lookup(IDS[name], name)
    assert sem is not None and sem.impl != "todo", name
for name in TODO:                       # known, reported, no effect
    assert REG.lookup(IDS[name], name).impl == "todo", name
    p = build_plan(REG, unit(rules=[R(name)]), unit(), Ctx())
    assert name in p.warnings, (name, p.warnings)

# --- Brutal: a 6 to hit deals 1 extra hit when far; Enhanced: always --------
br = unit(rules=[R("Brutal")])
ebr = unit(rules=[R("Brutal"), R("Enhanced Brutal")])
assert [one(br, unit(), distance=d).spec.extra_hits_on_6
        for d in (12, 9)] == [1, 0]
assert one(ebr, unit(), distance=9).spec.extra_hits_on_6 == 1
assert (melee(br, unit(), charge_distance=8).spec.extra_hits_on_6,
        melee(br, unit()).spec.extra_hits_on_6,
        melee(ebr, unit()).spec.extra_hits_on_6,
        melee(ebr, unit(), action=None).spec.extra_hits_on_6) == (1, 0, 1, 0)

# --- Disintegrate, Fragment --------------------------------------------------
dis = unit(weapons=(W("Ray", 24, 1, R("Disintegrate")),))
g = one(dis, unit(rules=[R("Tough", 3)]), "Ray")
assert (g.spec.ap, g.spec.ignores_regen) == (2, True)
g = one(dis, unit(), "Ray")
assert (g.spec.ap, g.spec.ignores_regen) == (0, True)
frg = unit(weapons=(W("Spike", 24, 1, R("Fragment")),))
assert one(frg, unit(d=5), "Spike").spec.reroll_defense_on == 5
assert one(frg, unit(d=6), "Spike").spec.reroll_defense_on == 5
assert one(frg, unit(d=4), "Spike").spec.reroll_defense_on == 0

# --- Enhanced Fortified: AP(-2) instead of AP(-1) ----------------------------
gun = unit(weapons=(W("Gun", 24, 1, R("AP", 3)),))
fo = unit(rules=[R("Fortified")])
efo = unit(rules=[R("Fortified"), R("Enhanced Fortified")])
assert [one(gun, t, "Gun").spec.ap for t in (
    unit(), fo, efo, unit(rules=[R("Enhanced Fortified")]))] == [3, 2, 1, 3]
ugun = unit(weapons=(W("Gun", 24, 1, R("AP", 3), R("Unstoppable")),))
assert one(ugun, efo, "Gun").spec.ap == 3
mixed = unit(2, rules=[R("Fortified"), R("Enhanced Fortified")],
             extra=unit(3, rules=[R("Fortified")]).models)
assert one(gun, mixed, "Gun").spec.ap == 2                      # 2 of 5

# --- Valiant: the Morale Test reads the attack it follows --------------
def mod(u, ctx=None, attack="shooting"):
    m = Morale(REG, u, None, ctx)
    return m.numbers(m.alloc.fresh(), attack)[1]


val = unit(rules=[R("Valiant")])
evl = unit(rules=[R("Valiant"), R("Enhanced Valiant")])
assert [mod(val, Ctx(distance=d)) for d in (12, 9)] == [1, 0]
assert mod(evl, Ctx(distance=9)) == 1
assert mod(val, Ctx(**CHARGE, charge_distance=8), "melee") == 1
assert mod(val, Ctx(**CHARGE), "melee") == 0
assert mod(evl, Ctx(**CHARGE), "melee") == 1
assert mod(evl, Ctx(attack="melee", action=None), "melee") == 0  # charger
assert mod(val, Ctx(attack="spell", distance=12), "spell") == 0
assert mod(unit(), Ctx(distance=12)) == 0
# through the Analyzer: P(Shaken) changes with the distance only with Valiant
from grimdarkoracle.app import analyzer_core as AC
from unitkit import resolved


def shaken(tgt, d):
    a = AC.analyse(REG, AC.Side(resolved(unit(10))), AC.Side(resolved(tgt)),
                   AC.Options(ctx=Ctx(distance=d), exact=True))
    return a.def_losses.morale.shaken


plain = unit(4, d=6)
assert shaken(plain, 12) == shaken(plain, 9)
brave = unit(4, d=6, rules=[R("Valiant")])
assert shaken(brave, 12) < shaken(brave, 9)              # +1 when far
assert shaken(brave, 9) == shaken(plain, 9)

# a charger with Valiant was not charged: its Morale after melee is plain


def charger_morale(rules):
    a = AC.analyse(REG, AC.Side(resolved(unit(3, d=6, rules=rules))),
                   AC.Side(resolved(unit(10))),
                   AC.Options(ctx=Ctx(**CHARGE, charge_distance=8),
                              exact=True))
    return a.att_losses.morale


assert charger_morale([R("Valiant")]) == charger_morale([])
assert charger_morale([]).test > 0

# --- Piercing Target (a Mark), Piercing Growth (a Versatile choice) ----------
pt = (IDS["Piercing Target"],)
assert one(unit(), unit(), marks=pt).spec.ap == 1
assert melee(unit(), unit(), marks=pt).spec.ap == 1
PG = IDS["Piercing Growth"]
pg = unit(rules=[R("Piercing Growth")])
assert [one(pg, unit(), versatile=v).spec.ap
        for v in ((), ((PG, 0),), ((PG, 1),))] == [0, 1, 2]

# --- auras and no combat effect ----------------------------------------------
for aura, rule in (("Predator Aura", "Predator"),
                   ("Enhanced Devout Aura", "Enhanced Brutal"),
                   ("Enhanced Guardian Aura", "Enhanced Fortified"),
                   ("Enhanced Hive Bond Aura", "Enhanced Valiant"),
                   ("Dash Aura", "Dash")):
    u = unit(4, extra=(cm(rules=[R(aura)]),))
    v = E.View(REG, Ctx(), "defender", u, (), u, ())
    holds, missing = E.holdings(REG, v)
    assert not missing and all(any(h.sem.name == rule for h in hs)
                               for hs in holds), aura
for name in ("Dash", "Rapid Charge", "Hit & Run Fighter"):
    u = unit(rules=[R(name)])
    for a, t in ((u, unit()), (unit(), u)):
        p, q = build_plan(REG, a, t, Ctx()), build_plan(REG, unit(), unit(),
                                                        Ctx())
        assert [x.spec for x in p.groups] == [x.spec for x in q.groups], name
        assert not p.warnings, (name, p.warnings)

# --- the real books ----------------------------------------------------------
if not testpaths.USING_SYNTHETIC:
    import os
    import subprocess
    import sys
    from grimdarkoracle.app.library import Library
    from grimdarkoracle.data.af_book import RuleRef
    from grimdarkoracle.rules import spells as RS
    lib = Library.load(testpaths.DATA_DIR)
    reg = lib.reg

    def rules(*names):
        refs = [RuleRef(next(r for r, d in reg.defs.items() if d.name == n),
                        n, None, n) for n in names]
        return unit(rules=refs)

    assert one(rules("Devout", "Enhanced Devout"), unit(), reg=reg,
               distance=9).spec.extra_hits_on_6 == 1
    assert one(gun, rules("Fortified", "Enhanced Guardian"), "Gun", reg,
               ).spec.ap == 1
    m = Morale(reg, rules("Hive Bond"), None, Ctx(distance=12))
    assert m.numbers(m.alloc.fresh(), "shooting")[1] == 1
    m = Morale(reg, rules("Hive Bond", "Enhanced Hive Bond"), None,
               Ctx(distance=6))
    assert m.numbers(m.alloc.fresh(), "shooting")[1] == 1
    # acceptance: no unmapped rule, the todo within 10% of each book
    tool = os.path.join(testpaths.REPO_ROOT, "tools", "rules_report.py")
    for book in GROUP:
        out = subprocess.run([sys.executable, tool, "--data",
                              testpaths.DATA_DIR, "--only", book],
                             capture_output=True, text=True).stdout
        line = out.splitlines()[1]
        n = dict(x.split() for x in line.split(": ")[1].split(", "))
        ok, todo = int(n["ok"]), int(n["todo"])
        assert int(n["unmapped"]) == int(n["changed"]) == 0, out[:400]
        assert 10 * todo <= ok + todo, (book, line)
        assert "unmapped" not in out.split("spells:")[1], out[-400:]
    # a spell Mark granting Unpredictable Fighter changes a melee analysis
    from grimdarkoracle.app import side_spec as S
    from grimdarkoracle.app.setup_model import Setup, SideSetup
    sreg = RS.SpellRegistry(RS.load(), reg, list(lib.books.values()))
    ah = next(b for b in lib.books.values() if b.name == "Alien Hives")
    key = next(RS.spell_key(s) for s in ah.spells
               if s.name == "Infuse Bloodthirst")
    assert sreg.lookup(ah, next(s for s in ah.spells
                                if s.name == "Infuse Bloodthirst")).kind == \
        "mark"
    bb = next(b for b in lib.books.values() if b.name == "Battle Brothers")
    tid = next(k for k, u in bb.units.items() if u.name == "Pathfinders")
    att = next(k for k, u in ah.units.items() if u.name == "Hive Warriors") \
        if any(u.name == "Hive Warriors" for u in ah.units.values()) else \
        next(iter(ah.units))
    res = [S.run(reg, S.book_side(ah, att), SideSetup(), S.book_side(bb, tid),
                 SideSetup(), Setup(attack="melee", action="charge",
                                    buffs=b), sreg, exact=True)
           for b in ((), (("att", key),))]
    assert res[0].def_losses.wounds != res[1].def_losses.wounds
    assert not [w for w in res[1].warnings if "unknown" in w.lower()]

print("test_group2 OK")
