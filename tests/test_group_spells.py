"""The spells of the Brothers / Prime Brothers
families, four Disciples, Havoc Brothers) and the rules only spells use:
Lacerate, Melee Evasion, Bane when Shooting, Quick Shot; Obliterate,
Purge, Decimate and Storm of Power's rolled sixes.
Hand-built units for the rules; the spells on the real books when
present (they are keyed by the books' spell ids and texts)."""
from fractions import Fraction as F

import testpaths
from grimdarkoracle.engine import gf_math as G
from grimdarkoracle.engine.context import AttackContext as Ctx
from grimdarkoracle.engine.modifiers import build_plan
from grimdarkoracle.rules import spells as RS
from unitkit import IDS, REG, R, W, unit

GROUP = ("Blood Brothers", "Blood Prime Brothers", "Dark Brothers",
         "Dark Prime Brothers", "Knight Brothers", "Knight Prime Brothers",
         "Watch Brothers", "Watch Prime Brothers", "Wolf Brothers",
         "Wolf Prime Brothers", "Change Disciples", "Lust Disciples",
         "Plague Disciples", "War Disciples", "Havoc Brothers")
LATER = {"Beautiful Pain", "Brutal Massacre", "Rapid Putrefaction",
         "Storm of Power"}


def one(att, tgt, weapon="Rifle", **ctx):
    gs = [g for g in build_plan(REG, att, tgt, Ctx(**ctx)).groups
          if g.weapon.name == weapon]
    assert len(gs) == 1, gs
    return gs[0]


# --- the rules only spells use -----------------------------------------
for name in ("Lacerate", "Melee Evasion", "Bane when Shooting", "Quick Shot"):
    sem = REG.lookup(IDS[name], name)
    assert sem is not None and sem.impl != "todo", name
assert not one(unit(), unit()).spec.reroll_defense_6
lw = unit(weapons=(W("Lash", 12, 1, R("Lacerate")),))
g = one(lw, unit(rules=[R("Regeneration")]), "Lash")
assert g.spec.reroll_defense_6 and not g.spec.ignores_regen  # not Bane
me = unit(rules=[R("Melee Evasion")])
melee = {"attack": "melee", "action": "charge"}
assert one(unit(), me, "Hand Weapon", **melee).spec.hit_mod == -1
assert one(unit(), me).spec.hit_mod == 0                      # shooting
mixed = unit(2, rules=[R("Melee Evasion")], extra=unit(3).models)
assert one(unit(), mixed, "Hand Weapon", **melee).spec.hit_mod == 0
bws = unit(rules=[R("Bane when Shooting")])
assert one(bws, unit()).spec.reroll_defense_6
assert not one(bws, unit(), "Hand Weapon", **melee).spec.reroll_defense_6
qs = unit(rules=[R("Quick Shot")])
assert one(qs, unit()).spec == one(unit(), unit()).spec

# --- every spell of these books is mapped, LATER included ---------
doc = RS.load()
names = {e["name"] for e in doc["spells"].values()}
assert names >= LATER, LATER - names

# --- LATER: the block re-roll, the target conditions, rolled sixes -------
from dataclasses import replace
import random
import dice_resolve as DR
import mc_support as MC
from grimdarkoracle.engine.specs import AttackSpec, TargetSpec
t4 = TargetSpec(defense=4)
assert G.block_probs(t4, 0, 5, True) == (F(12, 36), F(16, 36), F(8, 36))
assert G.block_probs(t4, 0, True, True) == G.block_probs(t4, 0, 6, True) \
    == (F(15, 36), F(14, 36), F(7, 36))
# AP 2 vs Defense 4+: a 5 fails, so only the 6 is re-rolled
assert G.block_probs(t4, 2, 5, True) == G.block_probs(t4, 2, 6, True)
assert G.reroll_face(AttackSpec(1, reroll_defense_6=True,
                                reroll_defense_on=5)) == 5
assert G.reroll_face(AttackSpec(1, reroll_defense_6=True)) == 6
assert G.reroll_face(AttackSpec(1)) == 0
obl = unit(weapons=(W("Lash", 12, 1, R("Obliterate")),))
big = unit(rules=[R("Tough", 3)])
g = one(obl, big, "Lash")
assert (g.spec.reroll_defense_on, g.spec.ignores_regen) == (5, True)
g = one(obl, unit(), "Lash")
assert (g.spec.reroll_defense_on, g.spec.ignores_regen) == (0, True)
pur = unit(weapons=(W("Axe", 12, 1, R("Purge")),))
assert [one(pur, unit(**f), "Axe").spec.ap for f in (
    {}, {"shaken": True}, {"fatigued": True})] == [0, 2, 2]
dec = unit(weapons=(W("Bile", 12, 1, R("Decimate")),))
assert one(dec, unit(), "Bile").spec.reroll_defense_6
assert not one(dec, replace(unit(), over_half=False),
               "Bile").spec.reroll_defense_6
# over_half from the Analyzer's starting wounds (morale.half_or_less)
from grimdarkoracle.app.analyzer_core import Side
from grimdarkoracle.engine.target_state import Allocation
from unitkit import resolved
four = resolved(unit(4))
al = Allocation.of(Side(four).combatant())
one_dead = al.wound(al.fresh(), 0, 1)
assert Side(four).combatant().over_half
assert Side(four, wounds=one_dead).combatant().over_half
assert not Side(four, wounds=al.wound(one_dead, 1, 1)).combatant().over_half
# Storm of Power: 4 fixed hits, each a six-hit on 1/6, Surge adds a hit
sp = AttackSpec(4, auto_hit=True, auto_sixes=True, extra_hits_on_6=1)
assert G.hit_probs(sp, True) == (0, F(5, 6), F(1, 6))
law = G.weapon_hits(sp, 1, True)
assert law[4:] == [F(625, 1296), F(500, 1296), F(150, 1296), F(20, 1296),
                   F(1, 1296)] and not any(law[:4])
assert G.hit_probs(replace(sp, auto_sixes=False), True) == (0, 1, 0)
# the flag reaches the spec only for a spell, and through the Analyzer
bolt = unit(weapons=(W("Storm", 12, 4, R("Surge")),))
assert one(bolt, unit(), "Storm", attack="spell",
           spell_sixes=True).spec.auto_sixes
assert not one(bolt, unit(), "Storm", attack="spell").spec.auto_sixes
assert not one(bolt, unit(), "Storm", spell_sixes=True).spec.auto_sixes
from grimdarkoracle.app import analyzer_core as AC
from grimdarkoracle.app.spells import SpellPlan
from grimdarkoracle.engine.context import AttackContext
ten = resolved(unit(10))
for sixes, mean in ((False, F(2)), (True, F(7, 3))):
    plan = SpellPlan("Storm", W("Storm", 12, 4, R("Surge")), F(1), sixes)
    an = AC.analyse(REG, Side(resolved(unit(1))), Side(ten), AC.Options(
        ctx=AttackContext(attack="spell"), exact=True, spell=plan))
    got = sum(k * p for k, p in enumerate(an.def_losses.wounds))
    assert got == mean, (sixes, got)          # (4 + 4/6) hits x 1/2
# Monte Carlo oracle of both (tests/dice_resolve)
rng = random.Random(39)
for spec in (AttackSpec(3, quality=3, reroll_defense_on=5, shred=1),
             replace(sp, ap_on_6=2)):
    tgt = TargetSpec(defense=4)
    samples = [len(DR._blocks(spec, tgt, *DR.roll_hits(spec, 1, rng),
                              rng)[0]) for _ in range(20000)]
    ok, msg = MC.parity("re-rolled block wound events",
                        G.weapon_wounds(spec, tgt, 1), samples)
    assert ok, msg

if not testpaths.USING_SYNTHETIC:
    from grimdarkoracle.app import side_spec as S
    from grimdarkoracle.app import spells as SP
    from grimdarkoracle.app.library import Library
    from grimdarkoracle.data.resolve import resolve
    from grimdarkoracle.engine.context import combatant
    lib = Library.load(testpaths.DATA_DIR)
    reg = lib.reg
    sreg = RS.SpellRegistry(doc, reg, list(lib.books.values()))
    books = {b.name: b for b in lib.books.values()}
    # rules_report --only exits
    # 0; a rule a book only receives is defined elsewhere (Precision
    # Fighter in Eternal Dynasty): --only must still know it
    import os
    import subprocess
    import sys
    tool = os.path.join(testpaths.REPO_ROOT, "tools",
                        "rules_report.py")
    r = subprocess.run([sys.executable, tool, "--data", testpaths.DATA_DIR,
                        "--only", *GROUP], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-2000:]
    r = subprocess.run([sys.executable, tool, "--data", testpaths.DATA_DIR,
                        "--only", "Blessed Sisters"], capture_output=True,
                       text=True)
    assert "changed 0" in r.stdout, r.stdout[:300]
    rows = sreg.coverage([books[n] for n in GROUP])
    left = {s for _b, s, st in rows if st != "ok"}
    assert not left, left

    def sem(book, name):
        b = books[book]
        return sreg.lookup(b, next(s for s in b.spells if s.name == name))

    def plan(att, tgt, **ctx):
        return build_plan(reg, combatant(att), combatant(tgt), Ctx(**ctx))

    def first_unit(book, name):
        b = books[book]
        uid = next(k for k, u in b.units.items() if u.name == name)
        return resolve(b, uid, ())

    # grant spells reach the friendly unit's models (buff toggles)
    blood = first_unit("Blood Brothers", "Blood Battle Brothers")
    pth = first_unit("Battle Brothers", "Pathfinders")
    sp = sem("Blood Brothers", "Burst of Rage")
    assert sp.kind == "grant"
    rage = SP.grant(blood, sp.grants, "shooting")
    assert {g.spec.extra_attack_on for g in plan(rage, pth).groups} == {5}
    assert {g.spec.extra_attack_on for g in plan(blood, pth).groups} == {6}
    da = sem("Havoc Brothers", "Dark Assault")
    havoc = first_unit("Havoc Brothers", "Havoc Brothers")
    armed = SP.grant(havoc, da.grants, "melee")
    assert all(g.spec.shred == 1 for g in plan(armed, pth, attack="melee",
                                                action="charge").groups)
    assert SP.grant(havoc, da.grants, "shooting") == havoc
    # a damage spell: closed form of its fixed hits on 1-wound models
    rot = sem("Plague Disciples", "Rot Wave")
    assert (rot.kind, rot.hits, rot.range, rot.rules) == ("damage", 4, 18, ())
    lash = sem("Lust Disciples", "Overpowering Lash")
    assert [r.name for r in lash.rules] == ["Shred"]
    sky = sem("Change Disciples", "Sky Blaze")
    assert [r.name for r in sky.rules] == ["Lacerate"]
    for book, name, rules in (
            ("Blood Prime Brothers", "Blood Wound", ["AP", "Pierce"]),
            ("Wolf Brothers", "Godly Thunder", ["AP", "Takedown"]),
            ("War Disciples", "Flame of Destruction", ["Blast"]),
            ("Havoc Brothers", "Havoc Fog", ["Scourge"])):
        assert [r.name for r in sem(book, name).rules] == rules, name
    # 4 fixed hits, no AP, against Defense 4+: wound events Binomial(4, 1/2)
    from grimdarkoracle.engine.specs import AttackSpec, TargetSpec
    spec = AttackSpec(attacks=4, auto_hit=True)
    assert G.weapon_wounds(spec, TargetSpec(defense=4), 5, True) == \
        [F(1, 16), F(4, 16), F(6, 16), F(4, 16), F(1, 16)]
    # the Analyzer resolves a group damage spell end to end
    from grimdarkoracle.app.setup_model import Setup, SideSetup
    from grimdarkoracle.app.unit_config import UnitConfig
    from grimdarkoracle.data.resolve import Choice
    cd = books["Change Disciples"]
    uid, pick = next((k, Choice(pu, sec.uid, o.uid, 1))
                     for k, u in cd.units.items() for pu in u.packages
                     for sec in cd.packages[pu].sections
                     for o in sec.options if "Caster(" in o.label)
    side = S.SideSpec(S.UnitSpec(UnitConfig(cd, uid, (pick,))))
    assert SP.caster_rating(reg, side.unit.resolved()) > 0
    key = sem("Change Disciples", "Power Bolt").key
    a = S.run(reg, side, SideSetup(), S.book_side(
        books["Battle Brothers"], next(k for k, u in books[
            "Battle Brothers"].units.items() if u.name == "Pathfinders")),
        SideSetup(), Setup(attack="spell", spell=key), sreg)
    assert abs(sum(a.def_losses.wounds) - 1) < 1e-9 and a.cast
    assert a.def_losses.wounds[0] < 1
    assert not [w for w in a.warnings if "unmapped" in w.lower()], a.warnings
    storm = sem("Wolf Brothers", "Storm of Power")
    assert storm.roll_sixes and [r.name for r in storm.rules] == ["Surge"]
    assert not sem("Wolf Brothers", "Godly Thunder").roll_sixes
    assert SP.plan(storm, reg, side.unit.resolved()).roll_sixes
    for book, name, rules in (
            ("Lust Disciples", "Beautiful Pain", ["Obliterate"]),
            ("War Disciples", "Brutal Massacre", ["AP", "Purge"]),
            ("Plague Disciples", "Rapid Putrefaction", ["AP", "Decimate"])):
        assert [r.name for r in sem(book, name).rules] == rules, name

print("test_group_spells OK")
