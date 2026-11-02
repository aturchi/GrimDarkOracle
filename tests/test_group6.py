"""Machine Cults, Orc Marauders, Robot Legions: Bad Shot, Shatter, the
Enhanced / Feat / Reanimation auras, the Enhanced Self-Repair buff, a spell
granting a buff rule's own effects, the spells; the table inputs: Demolish
and Grounded Evasion (near terrain), Protection Feat (a once-per-game ward,
"Feat used")."""
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import replace as _r
from fractions import Fraction as F

import testpaths
from grimdarkoracle.app import analyzer_core as AC
from grimdarkoracle.app import comparison as CO
from grimdarkoracle.app import setup_model as SM
from grimdarkoracle.app import spells as SP
from grimdarkoracle.app.defense_choice import mean
from grimdarkoracle.app.spells import SpellPlan
from grimdarkoracle.engine.context import AttackContext as Ctx
from grimdarkoracle.engine.context import combatant
from grimdarkoracle.engine.modifiers import build_plan
from grimdarkoracle.rules import effects as E
from unitkit import IDS, REG, R, W, cm, resolved, unit

GROUP = ("Machine Cults", "Orc Marauders", "Robot Legions")
MELEE = {"attack": "melee", "action": "charge"}

for name in ("Bad Shot", "Shatter", "Enhanced Ferocious Aura", "Speed Feat",
             "Speed Feat Aura", "Enhanced Machine-Fog Aura",
             "Enhanced Self-Repair Buff", "Reanimation", "Reanimation Aura",
             "Protection Feat Aura", "Demolish", "Grounded Evasion",
             "Protection Feat"):
    sem = REG.lookup(IDS[name], name)
    assert sem is not None and sem.impl != "todo", name


def one(att, tgt, weapon="Rifle", **ctx):
    gs = [g for g in build_plan(REG, att, tgt, Ctx(**ctx)).groups
          if g.weapon.name == weapon]
    assert len(gs) == 1, gs
    return gs[0]


def analysis(att, tgt, ctx=Ctx(), reg=REG, a_side=None, t_side=None, **kw):
    a_side, t_side = a_side or {}, t_side or {}
    return AC.analyse(reg, AC.Side(resolved(att), **a_side),
                      AC.Side(resolved(tgt), **t_side),
                      AC.Options(ctx=ctx, exact=True, **kw))


def killed(att, tgt, ctx=Ctx(), reg=REG, **kw):
    return mean(analysis(att, tgt, ctx, reg, **kw).def_losses.killed)


def holds_rule(cb, rule, reg=REG):
    v = E.View(reg, Ctx(), "defender", cb, (), cb, ())
    holds, missing = E.holdings(reg, v)
    return not missing and all(any(h.sem.name == rule for h in hs)
                               for hs in holds)


# --- Bad Shot: -1 to hit when shooting only ----------------------------------
bs = unit(1, rules=[R("Bad Shot")])
assert one(bs, unit()).spec.hit_mod == -1
assert one(bs, unit(), "Hand Weapon", **MELEE).spec.hit_mod == 0
assert killed(bs, unit(1)) == F(1, 6)                   # Q5+ x blocks 1/2
assert killed(unit(1), unit(1)) == F(1, 4)
assert killed(bs, unit(1), Ctx(**MELEE), strike_back=False) == F(1, 4)

# --- Shatter: unmodified 6s to hit get AP(+3) --------------------------------
SHATTER = W("Gauss", 24, 1, R("Shatter"))
sh = unit(1, weapons=(SHATTER,))
assert one(sh, unit(), "Gauss").spec.ap_on_6 == 3
# Q4+ vs Defense 4+: 4-5 hit and 1/2 to fail the block; a 6 needs 7+ to
# block, so only a natural 6 saves: 2/6 * 1/2 + 1/6 * 5/6 = 11/36
assert killed(sh, unit(1)) == F(11, 36)
# rolled fixed hits (Gauss Bots): 3 hits AP(1), each a 6 on 1/6:
# 5/6 * 4/6 + 1/6 * 5/6 = 25/36 per hit
gauss = W("Gauss Bots", 6, 3, R("AP", 1), R("Shatter"))


def bots(sixes):
    return killed(unit(1), unit(5), Ctx(attack="spell"),
                  spell=SpellPlan("Gauss Bots", gauss, F(1), sixes))


assert bots(True) == F(75, 36) and bots(False) == 2

# --- the auras grant their rule to the unit ----------------------------
for aura, rule in (("Enhanced Ferocious Aura", "Enhanced Brutal"),
                   ("Enhanced Machine-Fog Aura", "Enhanced Screened"),
                   ("Speed Feat Aura", "Speed Feat"),
                   ("Reanimation Aura", "Reanimation"),
                   ("Protection Feat Aura", "Protection Feat")):
    assert holds_rule(unit(4, extra=(cm(rules=[R(aura)]),)), rule), aura
# Enhanced Ferocious (= Enhanced Brutal) lifts Brutal's over 9"
br = [R("Brutal")]
efa = unit(4, rules=br, extra=(cm(rules=br + [R("Enhanced Ferocious Aura")]),))
assert one(efa, unit(), distance=6).spec.extra_hits_on_6 == 1
assert one(unit(rules=br), unit(), distance=6).spec.extra_hits_on_6 == 0
# Enhanced Machine-Fog (= Enhanced Screened) on the target: -1 at any range
sc = [R("Screened")]
ema = unit(4, rules=sc,
           extra=(cm(rules=sc + [R("Enhanced Machine-Fog Aura")]),))
assert one(unit(), ema, distance=6).spec.hit_mod == -1
assert one(unit(), unit(rules=sc), distance=6).spec.hit_mod == 0
# movement / activation rules: nothing in an attack, no warning
for name in ("Speed Feat", "Speed Feat Aura", "Reanimation",
             "Reanimation Aura"):
    u = unit(rules=[R(name)])
    p, q = build_plan(REG, u, u, Ctx()), build_plan(REG, unit(), unit(), Ctx())
    assert [x.spec for x in p.groups] == [x.spec for x in q.groups], name
    assert not p.warnings, (name, p.warnings)

# --- Enhanced Self-Repair Buff: a friendly unit gets the 5-6 ward -----------
grants = SP.rule_buff_grants(REG, IDS["Enhanced Self-Repair Buff"])
assert [g[0].id for g in grants] == [IDS["Enhanced Protected"]]
prot = [R("Protected")]
buffed = SP.grant(resolved(unit(4, rules=prot)), grants, "shooting")
assert one(unit(), combatant(buffed)).targets[0].wards == (5,)
assert one(unit(), unit(rules=prot)).targets[0].wards == (6,)
own = unit(4, rules=prot + [R("Enhanced Self-Repair Buff")])  # not its holder
assert one(unit(), own).targets[0].wards == (6,)

# --- near terrain (table input of each side) -------------------------
NEAR = {"near_terrain": True}
dm = unit(1, weapons=(W("Breacher", 24, 1, R("Demolish")),))
assert killed(dm, unit(1)) == F(1, 4)
assert killed(dm, unit(1), t_side=NEAR) == F(1, 3)            # AP(1): 2/3
assert killed(dm, unit(1), a_side=NEAR) == F(1, 4)            # the target's
assert killed(unit(1), unit(1), Ctx(cover="terrain")) == F(1, 6)
assert killed(dm, unit(1), Ctx(cover="terrain")) == F(1, 4)   # Ignores Cover
assert killed(dm, unit(1), Ctx(cover="terrain"), t_side=NEAR) == F(1, 3)
ge = [R("Grounded Evasion")]
assert killed(unit(1), unit(1, rules=ge), t_side=NEAR) == F(1, 6)
assert killed(unit(1), unit(1, rules=ge)) == F(1, 4)
assert killed(unit(1), unit(1, rules=ge), a_side=NEAR) == F(1, 4)
few = unit(2, rules=ge, extra=unit(3).models)                 # not most
assert one(unit(), _r(few, near_terrain=True)).spec.hit_mod == 0
assert one(unit(), _r(unit(rules=ge), near_terrain=True)).spec.hit_mod == -1
assert one(unit(), _r(unit(rules=ge), near_terrain=True), "Hand Weapon",
           **MELEE).spec.hit_mod == -1                        # any attack
# strike back: the struck charger's own flag is read
assert one(unit(), _r(unit(rules=ge), near_terrain=True), "Hand Weapon",
           attack="melee", action=None).spec.hit_mod == -1

# --- Protection Feat, a once-per-game ward 5+ ("Feat used") -----
pf = [R("Protection Feat")]
USED = {"feat_used": True}
assert killed(unit(1), unit(1, rules=pf)) == F(1, 4)
assert killed(unit(1), unit(1, rules=pf), t_side=USED) == F(1, 6)
assert killed(unit(1), unit(1), t_side=USED) == F(1, 4)       # no such rule
assert one(unit(), _r(unit(2, rules=pf, extra=unit(3).models),
                      feat_used=True)).targets[0].wards == ()  # not most
# (a): every wound of the activation, spells and both melee roles
used = _r(unit(rules=pf), feat_used=True)
assert one(unit(), used).targets[0].wards == (5,)
assert one(unit(), used, "Hand Weapon", **MELEE).targets[0].wards == (5,)
assert one(unit(), used, "Hand Weapon", attack="melee",
           action=None).targets[0].wards == (5,)
spell_w = W("Bolt", 18, 1)
assert killed(unit(1), unit(1, rules=pf), Ctx(attack="spell"), t_side=USED,
              spell=SpellPlan("Bolt", spell_w, F(1), False)) == F(1, 3)
# not cancelled by "ignores Regeneration"
bane = unit(1, weapons=(W("Bane Gun", 24, 1, R("Bane")),))
assert one(bane, used, "Bane Gun").targets[0].wards == (5,)
# the charger's Feat in the strike back: its losses fall
duel = unit(1, rules=pf)
plain_back = analysis(duel, unit(1), Ctx(**MELEE)).att_losses
feat_back = analysis(duel, unit(1), Ctx(**MELEE), a_side=USED).att_losses
assert mean(feat_back.killed) == mean(plain_back.killed) * F(2, 3)

# --- the inputs through the setup model and the comparison labels ----------
side = SM.make_side(resolved(unit(2)), None, SM.SideSetup(
    near_terrain=True, feat_used=True))
cb = side.combatant()
assert cb.near_terrain and cb.feat_used
assert "A near terrain" in CO._side_bits("A", side) and \
    "A Feat used" in CO._side_bits("A", side)
assert not SM.make_side(resolved(unit(2))).combatant().near_terrain

# --- the real books ----------------------------------------------------------
if not testpaths.USING_SYNTHETIC:
    from grimdarkoracle.app.library import Library
    from grimdarkoracle.data.af_book import RuleRef
    from grimdarkoracle.rules import spells as RS
    tool = os.path.join(testpaths.REPO_ROOT, "tools", "rules_report.py")

    def report(*books, spells=None):
        extra = ["--spells", spells] if spells else []
        r = subprocess.run([sys.executable, tool, "--data", testpaths.DATA_DIR,
                            *extra, "--only", *books], capture_output=True,
                           text=True)
        return r.returncode, r.stdout

    # every rule and spell mapped
    for book in GROUP:
        code, out = report(book)
        assert code == 0, (book, out[-1500:])
    # tool fix: with --only, a spell sharing its id with a mapped spell of a
    # book not chosen is 'unmapped', not 'changed'
    lib = Library.load(testpaths.DATA_DIR)
    reg = lib.reg
    bk = {b.name: b for b in lib.books.values()}
    doc = RS.load()
    orc = {RS.spell_key(s) for s in bk["Orc Marauders"].spells}
    old = dict(doc, spells={k: v for k, v in doc["spells"].items()
                            if k not in orc or v["name"] == "Boom!"})
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "spells.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(old, fh)
        code, out = report("Orc Marauders", spells=path)
    assert code == 1 and "[changed]" not in out, out
    assert out.count("[unmapped]") == 5, out

    sreg = RS.SpellRegistry(doc, reg, list(lib.books.values()))

    def rules(*names, n=5):
        refs = [RuleRef(next(r for r, d in reg.defs.items() if d.name == x),
                        x, None, x) for x in names]
        return unit(n, rules=refs)

    def spell(book, name):
        b = bk[book]
        return sreg.lookup(b, next(s for s in b.spells
                                   if s.name.strip() == name))

    def plan(att, tgt, **ctx):
        return build_plan(reg, att, tgt, Ctx(**ctx))

    # the book names: Ferocious, Machine-Fog, Self-Repair
    fe = rules("Ferocious", "Enhanced Ferocious Aura")
    assert [g.spec.extra_hits_on_6 for g in plan(fe, unit(), distance=6)
            .groups if g.weapon.name == "Rifle"] == [1]
    mf = rules("Machine-Fog", "Enhanced Machine-Fog Aura")
    assert [g.spec.hit_mod for g in plan(unit(), mf, distance=6).groups] \
        == [-1]
    sr = SP.grant(resolved(rules("Self-Repair")), SP.rule_buff_grants(
        reg, next(r for r, d in reg.defs.items()
                  if d.name == "Enhanced Self-Repair Buff")), "shooting")
    assert plan(unit(), combatant(sr)).groups[0].targets[0].wards == (5,)
    # Shatter on a real Robot Legions weapon
    rl = bk["Robot Legions"]
    from grimdarkoracle.data.resolve import resolve
    sid = IDS["Shatter"]
    ru = next(x for x in (resolve(rl, k, ()) for k in sorted(rl.units))
              if any(r.id == sid for m in x.models for w, _n in m.weapons
                     for r in w.rules))
    assert any(g.spec.ap_on_6 >= 3 for g in plan(
        combatant(ru), unit(), distance=6).groups)

    # spells: a grant of a buff rule's own effects (Corrode Weapons)
    cw = spell("Machine Cults", "Corrode Weapons")
    assert cw.kind == "debuff" and [(r.id, a) for r, _to, a in cw.grants] \
        == [(IDS["Piercing Debuff"] + "#effect", "shooting")]
    ap1 = W("Gun", 24, 1, R("AP", 1))
    weak = combatant(SP.grant(resolved(unit(weapons=(ap1,))), cw.grants,
                              "shooting"))
    assert [g.spec.ap for g in plan(weak, unit()).groups] == [0]
    weak_m = combatant(SP.grant(resolved(unit(weapons=(W(
        "Axe", 0, 1, R("AP", 1)),))), cw.grants, "melee"))
    assert [g.spec.ap for g in plan(weak_m, unit(), **MELEE).groups] == [1]
    mc = bk["Machine Cults"]
    assert sreg._rule(mc, "Nope#effect") is None
    assert sreg._rule(mc, "Machine-Fog#effect") is None     # not a token rule
    # marks: Head Bang (Rending in melee), Triangulation Bots (Indirect)
    hb = spell("Orc Marauders", "Head Bang")
    assert [g.spec.ap_on_6 for g in plan(unit(), unit(), marks=(
        hb.mark_id,), **MELEE).groups] == [4]
    assert [g.spec.ap_on_6 for g in plan(unit(), unit(), marks=(
        hb.mark_id,)).groups] == [0]
    tb = spell("Robot Legions", "Triangulation Bots")
    blind = dict(line_of_sight=False, action="hold")
    assert not plan(unit(), unit(), **blind).groups
    assert len(plan(unit(), unit(), marks=(tb.mark_id,), **blind).groups) == 1
    # grants: the Enhanced rules by the book's name, Spell Resistance
    for book, name, rule in (("Machine Cults", "Shrouding Incense",
                              "Enhanced Machine-Fog"),
                             ("Orc Marauders", "Path of War",
                              "Enhanced Ferocious"),
                             ("Orc Marauders", "Elder Protection",
                              "Spell Resistance"),
                             ("Robot Legions", "Mending Bots",
                              "Enhanced Self-Repair")):
        s = spell(book, name)
        assert s.kind == "grant" and [x[0].name for x in s.grants] == [rule]
    md = spell("Robot Legions", "Mending Bots")
    healed = combatant(SP.grant(resolved(rules("Self-Repair")), md.grants,
                                "shooting"))
    assert plan(unit(), healed).groups[0].targets[0].wards == (5,)
    # damage spells
    gb = spell("Robot Legions", "Gauss Bots")
    assert (gb.hits, gb.range, gb.roll_sixes, [x.label for x in gb.rules]) \
        == (3, 6, True, ["AP(1)", "Shatter"])
    gp = SP.plan(gb, reg, resolved(unit(1)), exact=True)
    assert killed(unit(1), unit(5), Ctx(attack="spell"), reg=reg,
                  spell=SpellPlan(gp.name, gp.weapon, F(1), gp.roll_sixes)) \
        == F(75, 36)
    for book, name, hits, labels in (
            ("Machine Cults", "Power Beam", 2, ["AP(1)", "Takedown"]),
            ("Machine Cults", "Crushing Force", 6, ["AP(2)"]),
            ("Orc Marauders", "Death Bolt", 4, ["AP(1)", "Pierce"]),
            ("Orc Marauders", "Psychic Vomit", 9, ["Bane"]),
            ("Orc Marauders", "Crackling Bolt", 1, ["Blast(3)"]),
            ("Robot Legions", "Flame Bots", 4, []),
            ("Robot Legions", "Piercing Bots", 6, ["AP(2)"])):
        s = spell(book, name)
        assert (s.kind, s.hits, [x.label for x in s.rules]) == \
            ("damage", hits, labels), name
    ss = spell("Machine Cults", "Searing Shrapnel")
    assert (ss.hits, [x.label for x in ss.rules]) == (4, ["Demolish"])
    sp = SP.plan(ss, reg, resolved(unit(1)), exact=True)
    shr = SpellPlan(sp.name, sp.weapon, F(1), False)
    assert killed(unit(1), unit(5), Ctx(attack="spell"), reg=reg, spell=shr,
                  t_side=NEAR) == F(8, 3)
    assert killed(unit(1), unit(5), Ctx(attack="spell"), reg=reg,
                  spell=shr) == 2
    for book, name in (("Machine Cults", "Cyborg Assault"),
                       ("Robot Legions", "Inspiring Bots")):
        assert spell(book, name).kind == "no_combat_effect", name

print("test_group6 OK")
