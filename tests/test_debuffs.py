"""buffs with effects of their own (Bravery,
Casting, Precision Attacks, Precision Shooter Buff), debuffs (Defense,
Morale, Piercing, Precision Debuff) held by the debuffed unit as the
pseudo-rule '<id>#effect', never by their holder; the Analyzer toggles
(a debuff of a side's book goes on the OTHER side); Unpredictable Fighter /
Shooter Marks (the die of a rule a Mark gives the weapons)."""
from fractions import Fraction as F
from types import SimpleNamespace as NS

import testpaths                                    # noqa: F401 (sys.path)
from grimdarkoracle.app import analyzer_core as AC
from grimdarkoracle.app import side_spec as SS
from grimdarkoracle.app import spells as SP
from grimdarkoracle.app import unpredictable as UP
from grimdarkoracle.app.setup_model import Setup
from grimdarkoracle.data.af_book import RuleRef
from grimdarkoracle.engine import gf_math as G
from grimdarkoracle.engine import pmf as P
from grimdarkoracle.engine.context import AttackContext as Ctx
from grimdarkoracle.engine.modifiers import build_plan
from grimdarkoracle.engine.morale import Morale
from unitkit import IDS, REG, R, W, resolved, unit

SUFFIX = "#effect"


def eff(name):
    """The pseudo-rule a buffed / debuffed unit holds."""
    return RuleRef(IDS[name] + SUFFIX, name, None, name)


def one(att, tgt, weapon="Rifle", **ctx):
    gs = [g for g in build_plan(REG, att, tgt, Ctx(**ctx)).groups
          if g.weapon.name == weapon]
    assert len(gs) == 1, gs
    return gs[0]


def melee(att, tgt, **ctx):
    return one(att, tgt, "Hand Weapon", attack="melee", **ctx)


def morale(u):
    m = Morale(REG, u)
    return m.pass_prob(m.alloc.fresh(), "shooting", exact=True)


CHARGE = {"action": "charge"}

# --- every entry below is mapped ---------------------------------------------
for name in ("Bravery Buff", "Casting Buff", "Precision Attacks Buff",
             "Precision Shooter Buff", "Defense Debuff", "Morale Debuff",
             "Piercing Debuff", "Precision Debuff", "Fatigue Debuff",
             "Unpredictable Fighter Mark", "Unpredictable Shooter Mark",
             "Extended Buff Range"):
    sem = REG.lookup(IDS[name], name)
    assert sem is not None and sem.impl != "todo", name

# --- the pseudo-rule ---------------------------------------------------------
ps = REG.lookup(IDS["Precision Shooter Buff"] + SUFFIX)
assert ps.impl == "composed" and ps.handler is None
assert [e.primitive for e in ps.effects] == ["hit_mod"]
assert REG.lookup(IDS["Furious Buff"] + SUFFIX) is None     # grants only
assert REG.lookup(IDS["Furious"] + SUFFIX) is None          # not a token
g = SP.rule_buff_grants(REG, IDS["Precision Shooter Buff"])
assert [(r.id, a) for r, _to, a in g] == \
    [(IDS["Precision Shooter Buff"] + SUFFIX, "shooting")]

# --- buffs: on the buffed unit, never on the holder ------------------------
pa = unit(rules=[eff("Precision Attacks Buff")])
assert one(pa, unit()).spec.hit_mod == 1
assert melee(pa, unit(), **CHARGE).spec.hit_mod == 1
assert one(unit(rules=[R("Precision Attacks Buff")]), unit()).spec.hit_mod \
    == 0
psb = unit(rules=[eff("Precision Shooter Buff")])
assert one(psb, unit()).spec.hit_mod == 1
assert melee(psb, unit(), **CHARGE).spec.hit_mod == 0
assert morale(unit(5)) == F(1, 2)
assert morale(unit(5, rules=[eff("Bravery Buff")])) == F(2, 3)
assert morale(unit(5, rules=[R("Bravery Buff")])) == F(1, 2)
assert SP.cast_mod(REG, resolved(unit(1, rules=[eff("Casting Buff")]))) == 1
assert SP.cast_mod(REG, resolved(unit(1, rules=[R("Casting Buff")]))) == 0

# --- debuffs: on the debuffed unit -------------------------------------------
dd = unit(rules=[eff("Defense Debuff")])
assert one(unit(), dd).target.defense_mod == -1
assert one(unit(), dd, cover="terrain").target.defense_mod == 0
assert one(unit(), unit(rules=[R("Defense Debuff")])).target.defense_mod \
    == 0
assert morale(unit(5, rules=[eff("Morale Debuff")])) == F(1, 3)
pierced = unit(weapons=[W("Gun", 24, 1, R("AP", 2))],
               rules=[eff("Piercing Debuff")])
assert one(pierced, unit(), "Gun").spec.ap == 1
s = one(unit(rules=[eff("Piercing Debuff")]), unit()).spec
assert s.ap == -1 and G.effective_ap(s, False) == 0     # floored at 0
assert one(unit(rules=[eff("Precision Debuff")]), unit()).spec.hit_mod == -1
assert melee(unit(rules=[eff("Precision Debuff")]), unit(),
             action=None).spec.hit_mod == -1            # its strike back

# --- Analyzer toggles: a debuff goes on the OTHER side -----------------
sreg = NS(reg=REG, spells=lambda book: [])
books = {"att": None, "def": None}
for side, other in (("att", "def"), ("def", "att")):
    setup = Setup(buffs=((side, SP.RULE_BUFF + IDS["Defense Debuff"]),))
    _m, g_att, g_def = SS._buffs(sreg, setup, books, [])
    got = {"att": g_att, "def": g_def}
    assert got[other] and not got[side], (side, got)
setup = Setup(buffs=(("att", SP.RULE_BUFF + IDS["Bravery Buff"]),))
_m, g_att, g_def = SS._buffs(sreg, setup, books, [])
assert g_att and not g_def                          # a buff stays

# --- Unpredictable Fighter / Shooter Mark ------------------------------
usm, ufm = IDS["Unpredictable Shooter Mark"], IDS["Unpredictable Fighter Mark"]
shoot = Ctx(marks=(usm,))
assert [(r, o) for r, _n, o in UP.menus(REG, unit(), unit(), shoot)] == \
    [(IDS["Unpredictable Shooter"], (3, 3))]
assert UP.menus(REG, unit(), unit(), Ctx("melee", action="charge",
                                         marks=(usm,))) == []
assert [r for r, _n, _o in UP.menus(REG, unit(), unit(), Ctx(
    "melee", action="charge", marks=(ufm,)))] == [IDS["Unpredictable Fighter"]]
us = IDS["Unpredictable Shooter"]
s0 = one(unit(), unit(), marks=(usm,), versatile=((us, 0),)).spec
s1 = one(unit(), unit(), marks=(usm,), versatile=((us, 1),)).spec
assert (s0.ap, s0.hit_mod, s1.ap, s1.hit_mod) == (1, 0, 0, 1)
s = one(unit(), unit(), marks=(usm,)).spec           # no die: no effect
assert (s.ap, s.hit_mod) == (0, 0)
# a unit that has the rule AND the Mark: one die, the effect once
both = unit(rules=[R("Unpredictable Shooter")])
assert len(UP.menus(REG, both, unit(), shoot)) == 1
assert one(both, unit(), marks=(usm,), versatile=((us, 1),)).spec.hit_mod \
    == 1

# the Analyzer mixes the Mark's die exactly, as for a rule of the unit:
# one rifle shot at D5 -> 31/72 (test_unpredictable)
att = AC.Side(resolved(unit(1)))
tgt = AC.Side(resolved(unit(5, d=5)))
an = AC.analyse(REG, att, tgt, AC.Options(Ctx(distance=12, marks=(usm,)),
                                          exact=True))
assert P.trim(an.def_losses.killed) == [F(41, 72), F(31, 72)]
assert any("mixes every die outcome" in w for w in an.warnings)

print("test_debuffs OK")
