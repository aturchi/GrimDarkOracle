"""Dark Elf Raiders, Dwarf Guilds, Elven Jesters:
Destructive, the token menus of Piercing / Precision Frenzy, Infiltrating
Precision Strike, Enhanced Guarded (Enhanced Sturdy), the auras, and the
spells (a rule a spell names may come from another book)."""
import testpaths
from grimdarkoracle.engine.context import AttackContext as Ctx
from grimdarkoracle.engine.modifiers import build_plan
from grimdarkoracle.rules import effects as E
from unitkit import IDS, REG, R, W, cm, unit

GROUP = ("Dark Elf Raiders", "Dwarf Guilds", "Elven Jesters")
MELEE = {"attack": "melee", "action": "charge"}


def one(att, tgt, weapon="Rifle", reg=REG, **ctx):
    gs = [g for g in build_plan(reg, att, tgt, Ctx(**ctx)).groups
          if g.weapon.name == weapon]
    assert len(gs) == 1, gs
    return gs[0]


for name in ("Destructive", "Piercing Frenzy", "Precision Frenzy",
             "Infiltrating Precision Strike", "Enhanced Guarded", "Hit & Run",
             "Enhanced Hit & Run", "Ambush Re-Deployment", "Martial Prowess",
             "Enhanced Harassing Aura", "Enhanced Rapid Blink Aura",
             "Enhanced Sturdy Aura"):
    sem = REG.lookup(IDS[name], name)
    assert sem is not None and sem.impl != "todo", name

# --- Destructive: AP(+1) against a target above half -------------------------
from dataclasses import replace
dst = unit(weapons=(W("Shard", 24, 1, R("Destructive")),))
assert one(dst, unit(), "Shard").spec.ap == 1
assert one(dst, replace(unit(), over_half=False), "Shard").spec.ap == 0

# --- Piercing / Precision Frenzy: token menus, holders only ------------------
PF, QF = IDS["Piercing Frenzy"], IDS["Precision Frenzy"]
pf = unit(rules=[R("Piercing Frenzy")])
assert [one(pf, unit(), versatile=v).spec.ap
        for v in ((), ((PF, 0),), ((PF, 1),))] == [0, 1, 2]
qf = unit(rules=[R("Precision Frenzy")])
assert [one(qf, unit(), "Hand Weapon", versatile=v, **MELEE).spec.hit_mod
        for v in ((), ((QF, 0),), ((QF, 1),))] == [0, 1, 2]
part = unit(1, rules=[R("Piercing Frenzy")], extra=unit(1).models)
aps = sorted(g.spec.ap for g in build_plan(REG, part, unit(), Ctx(
    versatile=((PF, 1),))).groups if g.weapon.name == "Rifle")
assert aps == [0, 2], aps

# --- Infiltrating Precision Strike: +1 in melee on its deployment round ------
ips = unit(rules=[R("Infiltrating Precision Strike")])
assert one(ips, unit(), "Hand Weapon", ambushed=True,
           **MELEE).spec.hit_mod == 1
assert one(ips, unit(), "Hand Weapon", **MELEE).spec.hit_mod == 0
assert one(ips, unit(), ambushed=True).spec.hit_mod == 0        # shooting

# --- Enhanced Guarded lifts Guarded's distance -------------------------------
gd = unit(rules=[R("Guarded")])
egd = unit(rules=[R("Guarded"), R("Enhanced Guarded")])
assert [one(unit(), gd, distance=d).targets[0].defense_mod
        for d in (12, 9)] == [1, 0]
assert one(unit(), egd, distance=9).targets[0].defense_mod == 1
assert one(unit(), egd, "Hand Weapon", **MELEE).targets[0].defense_mod == 1

# --- auras -------------------------------------------------------------------
for aura, rule in (("Enhanced Harassing Aura", "Enhanced Hit & Run"),
                   ("Enhanced Rapid Blink Aura", "Enhanced Nimble"),
                   ("Enhanced Sturdy Aura", "Enhanced Guarded")):
    u = unit(4, extra=(cm(rules=[R(aura)]),))
    v = E.View(REG, Ctx(), "defender", u, (), u, ())
    holds, missing = E.holdings(REG, v)
    assert not missing and all(any(h.sem.name == rule for h in hs)
                               for hs in holds), aura

# --- the real books ----------------------------------------------------------
if not testpaths.USING_SYNTHETIC:
    import os
    import subprocess
    import sys
    from grimdarkoracle.app import spells as SP
    from grimdarkoracle.app.library import Library
    from grimdarkoracle.data.resolve import resolve
    from grimdarkoracle.engine.context import combatant
    from grimdarkoracle.rules import spells as RS
    tool = os.path.join(testpaths.REPO_ROOT, "tools", "rules_report.py")
    r = subprocess.run([sys.executable, tool, "--data", testpaths.DATA_DIR,
                        "--only", *GROUP], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-1500:]
    lib = Library.load(testpaths.DATA_DIR)
    sreg = RS.SpellRegistry(RS.load(), lib.reg, list(lib.books.values()))
    dw = next(b for b in lib.books.values() if b.name == "Dwarf Guilds")
    assert not any(d.name == "Increased Shooting Range"
                   for d in dw.rules.values())      # defined elsewhere only
    rune = sreg.lookup(dw, next(s for s in dw.spells
                                if s.name.strip() == "Battle Rune"))
    assert [g[0].name for g in rune.grants] == ["Increased Shooting Range"]
    ru = next(r for r in (resolve(dw, k, ()) for k in dw.units)
              if any(w.range for m in r.models for w, _n in m.weapons))
    buffed = SP.grant(ru, rune.grants, "shooting")
    base = build_plan(lib.reg, combatant(ru), unit(), Ctx(distance=30))
    more = build_plan(lib.reg, combatant(buffed), unit(), Ctx(distance=30))
    assert len(more.groups) >= len(base.groups)
    long_w = max((w.range for m in ru.models for w, _n in m.weapons),
                 default=0)
    d = long_w + 3                      # out of range without the rune
    assert long_w and not [g for g in build_plan(
        lib.reg, combatant(ru), unit(), Ctx(distance=d)).groups
        if g.weapon.range == long_w]
    assert [g for g in build_plan(lib.reg, combatant(buffed), unit(),
                                  Ctx(distance=d)).groups
            if g.weapon.range == long_w]

print("test_group3 OK")
