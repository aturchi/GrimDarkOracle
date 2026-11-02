"""Soul-Snatcher
Cults (Grounded Defense / Precision on the Near terrain input, Reap), the
Titan Lords books and Prime Brothers (spells identical to mapped ones),
Jackals, Ratmen Clans, Rebel Guerrillas, Saurian Starhosts, Voidspace
Stalkers (Enhanced auras / buffs, Predator Shooter, Precision Tag,
Reinforcement) and their spells. With --real_data: every book complete."""
import json
import os
import subprocess
import sys
from collections import defaultdict
from dataclasses import replace as _r
from fractions import Fraction as F

import testpaths
from grimdarkoracle.app import analyzer_core as AC
from grimdarkoracle.app import spells as SP
from grimdarkoracle.app.defense_choice import mean
from grimdarkoracle.app.spells import SpellPlan
from grimdarkoracle.engine.context import AttackContext as Ctx
from grimdarkoracle.engine.context import combatant
from grimdarkoracle.engine.modifiers import build_plan
from grimdarkoracle.rules import spells as RS
from unitkit import IDS, REG, R, W, cm, resolved, unit

MELEE = {"attack": "melee", "action": "charge"}

for name in ("Grounded Defense", "Grounded Precision", "Grounded Defense Aura",
             "Grounded Precision Aura", "Reap", "Predator Shooter",
             "Predator Shooter Aura", "Precision Tag", "Reinforcement",
             "Enhanced Guerrilla Aura", "Enhanced Scrapper Aura",
             "Enhanced Scurry Aura", "Enhanced Shadowborn Aura",
             "Enhanced Shadowborn Buff", "Enhanced Primal Buff"):
    sem = REG.lookup(IDS[name], name)
    assert sem is not None and sem.impl != "todo", name


def one(att, tgt, weapon="Rifle", **ctx):
    gs = [g for g in build_plan(REG, att, tgt, Ctx(**ctx)).groups
          if g.weapon.name == weapon]
    assert len(gs) == 1, gs
    return gs[0]


def killed(att, tgt, ctx=Ctx(), reg=REG, a_side=None, t_side=None, **kw):
    a = AC.analyse(reg, AC.Side(resolved(att), **(a_side or {})),
                   AC.Side(resolved(tgt), **(t_side or {})),
                   AC.Options(ctx=ctx, exact=True, **kw))
    return mean(a.def_losses.killed)


NEAR = {"near_terrain": True}

# --- Grounded Defense: +1 Defense near terrain, most models ----------
gd = [R("Grounded Defense")]
assert killed(unit(1), unit(1, rules=gd), t_side=NEAR) == F(1, 6)
assert killed(unit(1), unit(1, rules=gd)) == F(1, 4)
assert killed(unit(1), unit(1, rules=gd), a_side=NEAR) == F(1, 4)
few = _r(unit(2, rules=gd, extra=unit(3).models), near_terrain=True)
assert one(unit(), few).targets[0].defense_mod == 0
aura = _r(unit(4, extra=(cm(rules=[R("Grounded Defense Aura")]),)),
          near_terrain=True)
assert one(unit(), aura).targets[0].defense_mod == 1
assert one(unit(), aura, "Hand Weapon", **MELEE).targets[0].defense_mod == 1

# --- Grounded Precision: +1 to hit for its holder near terrain -------
gp = _r(unit(1, rules=[R("Grounded Precision")], extra=unit(1).models),
        near_terrain=True)
assert sorted(g.spec.hit_mod for g in build_plan(REG, gp, unit(), Ctx())
              .groups) == [0, 1]
assert killed(unit(1, rules=[R("Grounded Precision")]), unit(1),
              a_side=NEAR) == F(1, 3)
assert killed(unit(1, rules=[R("Grounded Precision")]), unit(1)) == F(1, 4)
gpa = _r(unit(3, extra=(cm(rules=[R("Grounded Precision Aura")]),)),
         near_terrain=True)
assert {g.spec.hit_mod for g in build_plan(REG, gpa, unit(), Ctx()).groups
        } == {1}

# --- Reap: the target re-rolls successful Defense 5-6 when Shaken / Fatigued
rp = unit(1, weapons=(W("Scythe", 24, 1, R("Reap")),))
# Q4+ vs Defense 4+: fail 1/2, plus the 5-6 (1/3) re-rolled and failed 1/2
assert killed(rp, unit(1), t_side={"shaken": True}) == F(1, 3)
assert killed(rp, unit(1), t_side={"fatigued": True}) == F(1, 3)
assert killed(rp, unit(1)) == F(1, 4)
assert one(rp, unit(), "Scythe").spec.reroll_defense_on == 0
assert one(rp, unit(shaken=True), "Scythe").spec.reroll_defense_on == 5

# --- Predator Shooter: Predator when shooting only --------------------
ps = unit(rules=[R("Predator Shooter")])
assert one(ps, unit()).spec.extra_attack_on == 6
assert one(ps, unit(), "Hand Weapon", **MELEE).spec.extra_attack_on == 0
psa = unit(4, extra=(cm(rules=[R("Predator Shooter Aura")]),))
assert {g.spec.extra_attack_on for g in build_plan(REG, psa, unit(), Ctx())
        .groups} == {6}
assert {g.spec.extra_attack_on for g in build_plan(REG, psa, unit(), Ctx(
    **MELEE)).groups} == {0}                            # not Predator

# --- Precision Tag: the Spotter tokens; Reinforcement: nothing ---------------
assert REG.lookup(IDS["Precision Tag"]).handler == "spotter"
assert one(unit(), unit(), spotter_tokens=1).spec.hit_mod == 1
for name in ("Reinforcement", "Precision Tag"):
    u = unit(rules=[R(name)])
    p, q = build_plan(REG, u, u, Ctx()), build_plan(REG, unit(), unit(), Ctx())
    assert [x.spec for x in p.groups] == [x.spec for x in q.groups], name
    assert not p.warnings, (name, p.warnings)

# --- spells: one text, one meaning (the copied spells rely on it) --------
groups = defaultdict(set)
for k, v in RS.load()["spells"].items():
    groups[v["text_sha1"]].add(json.dumps({x: y for x, y in v.items() if x
                                           not in ("name", "text_sha1",
                                                   "note")}, sort_keys=True))
assert all(len(b) == 1 for b in groups.values()), \
    [h for h, b in groups.items() if len(b) > 1]

# --- the real books ----------------------------------------------------------
if not testpaths.USING_SYNTHETIC:
    from grimdarkoracle.app.library import Library
    from grimdarkoracle.data.af_book import RuleRef
    tool = os.path.join(testpaths.REPO_ROOT, "tools", "rules_report.py")
    r = subprocess.run([sys.executable, tool, "--data", testpaths.DATA_DIR],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-1500:]        # all 49 books
    lib = Library.load(testpaths.DATA_DIR)
    reg = lib.reg
    bk = {b.name: b for b in lib.books.values()}
    sreg = RS.SpellRegistry(RS.load(), reg, list(lib.books.values()))

    def rid(name):
        return next(r for r, d in reg.defs.items() if d.name == name)

    def rules(*names, n=5):
        return unit(n, rules=[RuleRef(rid(x), x, None, x) for x in names])

    def spell(book, name):
        b = bk[book]
        return sreg.lookup(b, next(s for s in b.spells
                                   if s.name.strip() == name))

    def plan(att, tgt, **ctx):
        return build_plan(reg, att, tgt, Ctx(**ctx))

    def buffed(base, buff, attack="shooting"):
        return combatant(SP.grant(resolved(rules(base)), SP.rule_buff_grants(
            reg, rid(buff)), attack))

    # the Enhanced auras and buffs on the books' own rule names
    sc = rules("Scrapper", "Enhanced Scrapper Aura")
    assert {g.spec.reroll_defense_on for g in plan(sc, unit()).groups} == {5}
    assert {g.spec.reroll_defense_on for g in plan(rules("Scrapper"), unit())
            .groups} == {0}
    far = dict(distance=17)                 # Shadowborn: -4", Enhanced -8"
    assert plan(unit(), rules("Shadowborn"), **far).groups
    assert not plan(unit(), rules("Shadowborn", "Enhanced Shadowborn Aura"),
                    **far).groups
    assert not plan(unit(), buffed("Shadowborn", "Enhanced Shadowborn Buff"),
                    **far).groups
    pr = buffed("Primal", "Enhanced Primal Buff")
    assert {g.spec.extra_attack_on for g in plan(pr, unit()).groups} == {5}
    for name in ("Enhanced Guerrilla Aura", "Enhanced Scurry Aura"):
        assert not plan(rules(name), unit()).warnings, name
    # Grounded Defense through a spell (Insidious Protection) and the input
    ip = spell("Soul-Snatcher Cults", "Insidious Protection")
    gdu = combatant(SP.grant(resolved(unit()), ip.grants, "shooting"))
    assert plan(unit(), _r(gdu, near_terrain=True)).groups[0] \
        .targets[0].defense_mod == 1
    assert plan(unit(), gdu).groups[0].targets[0].defense_mod == 0
    # damage spells: Reap vs a Shaken target, Puncture, Power Surge
    po = spell("Soul-Snatcher Cults", "Psychic Onslaught")
    assert (po.hits, po.roll_sixes, [x.label for x in po.rules]) == \
        (3, True, ["AP(1)", "Reap"])
    pw = SP.plan(po, reg, resolved(unit(1)), exact=True)
    pplan = SpellPlan(pw.name, pw.weapon, F(1), pw.roll_sixes)
    # AP(1) vs Defense 4+: fail 4/6; the blocks (5-6, 2/6) re-rolled and
    # failed 4/6 vs a Shaken target: 4/6 + 2/6 * 4/6 = 8/9 per hit
    assert killed(unit(1), unit(5), Ctx(attack="spell"), reg=reg,
                  spell=pplan, t_side={"shaken": True}) == 3 * F(8, 9)
    assert killed(unit(1), unit(5), Ctx(attack="spell"), reg=reg,
                  spell=pplan) == 3 * F(2, 3)
    serp = spell("Saurian Starhosts", "Serpent Comet")
    assert [x.label for x in serp.rules] == ["Puncture"]
    ps_ = spell("Ratmen Clans", "Power Surge")
    assert (ps_.roll_sixes, [x.label for x in ps_.rules]) == \
        (True, ["Hazardous", "Takedown"])
    # grants of a token rule's own effects
    dm = spell("Rebel Guerrillas", "Deep Meditation")
    sharp = combatant(SP.grant(resolved(unit()), dm.grants, "shooting"))
    assert [g.spec.hit_mod for g in plan(sharp, unit()).groups] == [1]
    ts = spell("Ratmen Clans", "Tech-Sickness")
    soft = combatant(SP.grant(resolved(unit()), ts.grants, "shooting"))
    assert ts.kind == "debuff" and \
        plan(unit(), soft).groups[0].targets[0].defense_mod == -1
    ms = spell("Jackals", "Mind Shaper")
    assert ms.kind == "debuff" and [x[0].id for x in ms.grants] == \
        [rid("Morale Debuff") + "#effect"]
    # marks: Bane (Toxin Mist), Furious when charging (Bad Omen)
    tm = spell("Saurian Starhosts", "Toxin Mist")
    assert all(g.spec.reroll_defense_6 for g in plan(
        unit(), unit(), marks=(tm.mark_id,)).groups)
    bo = spell("Rebel Guerrillas", "Bad Omen")
    assert [g.spec.extra_hits_on_6 for g in plan(
        unit(), unit(), marks=(bo.mark_id,), **MELEE).groups] == [1]
    assert [g.spec.extra_hits_on_6 for g in plan(
        unit(), unit(), marks=(bo.mark_id,)).groups] == [0]
    # the Titan Lords books and Prime Brothers: every spell mapped, and the
    # copy of a mapped text (checked above for every text)
    for name in ("Titan Lords", "Titan Lords Lust Disciples",
                 "Titan Lords Plague Disciples", "Titan Lords War Disciples",
                 "Titan Lords Change Disciples", "Prime Brothers"):
        b = bk[name]
        assert all(sreg.status(b, s) == "ok" for s in b.spells), name
    gb = spell("Titan Lords Change Disciples", "Breath of Change")
    assert [x[0].name for x in gb.grants] == ["Bane when Shooting"]

print("test_group7 OK")
