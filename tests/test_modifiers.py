"""engine.modifiers + rules.effects: rules and context -> AttackSpec /
TargetSpec, on hand-built units carrying real rule ids (shipped semantics)."""
from fractions import Fraction as F
from types import SimpleNamespace

import testpaths
from grimdarkoracle.data import af_book as ab
from grimdarkoracle.data.af_book import RuleDef, RuleRef, Weapon
from grimdarkoracle.data.resolve import ResolvedModel
from grimdarkoracle.engine import gf_math as G
from grimdarkoracle.engine import pmf as P
from grimdarkoracle.engine.context import (AttackContext as Ctx, CombatModel,
                                           Combatant)
from grimdarkoracle.engine.modifiers import build_plan
from grimdarkoracle.rules import registry

SEM = registry.load_semantics()
IDS = {e["name"]: rid for rid, e in SEM["rules"].items()}
core = ab.load_core_rules(testpaths.rules_path(root=testpaths.SYNTHETIC_DIR))
visor = SimpleNamespace(rules={"tvisor": RuleDef(
    "tvisor", "Targeting Visor", "t", aliased_rule_id=IDS["Precision Marksman"])})
IDS["Targeting Visor"] = "tvisor"
reg = registry.RuleRegistry(SEM, core, [visor])


def R(name, rating=None):
    return RuleRef(IDS[name], name, rating,
                   name if rating is None else f"{name}({rating})")


def W(name, rng, att, *rules):
    return Weapon(name, 1, rng, att, tuple(rules))


RIFLE = W("Rifle", 24, 1, R("AP", 1))
CCW = W("Hand Weapon", 0, 1)


def model(weapons=(RIFLE, CCW), rules=()):
    return ResolvedModel(tuple((w, 1) for w in weapons), (), tuple(rules))


def unit(n=5, weapons=(RIFLE, CCW), rules=(), q=4, d=4, extra=(), **kw):
    """n identical models, then the models in 'extra' (CombatModels)."""
    ms = tuple(CombatModel(model(weapons, rules), q, d) for _ in range(n))
    return Combatant("u", ms + tuple(extra), **kw)


def plan(att, tgt, **ctx):
    return build_plan(reg, att, tgt, Ctx(**ctx))


def one(att, tgt, weapon="Rifle", **ctx):
    p = plan(att, tgt, **ctx)
    gs = [g for g in p.groups if g.weapon.name == weapon]
    assert len(gs) == 1, (gs, p.excluded)
    return gs[0]


# --- basics, eligibility --------------------------------------------------------------
p = plan(unit(), unit())
assert not p.warnings and len(p.groups) == 1
g = p.groups[0]
assert (g.models, g.spec.attacks, g.spec.quality, g.spec.ap) == \
    ((0, 1, 2, 3, 4), 5, 4, 1)
assert g.target == G.TargetSpec(4, 0, False, 5) and len(g.targets) == 5
assert p.excluded == (("Hand Weapon", "melee weapon", (0, 1, 2, 3, 4)),)
assert plan(unit(), unit(), distance=30).excluded[0][1] == 'out of range (24")'
assert plan(unit(), unit(), action="rush").groups == ()
m = plan(unit(), unit(), attack="melee", action="charge")
assert [g.weapon.name for g in m.groups] == ["Hand Weapon"]
assert m.excluded[0][:2] == ("Rifle", "ranged weapon")

# --- attacker rules: scope, alias, grants, conditions ----------------------------------
gs = unit(rules=[R("Good Shot")])
assert one(gs, unit()).spec.hit_mod == 1
assert one(gs, unit(), "Hand Weapon", attack="melee").spec.hit_mod == 0
tv = unit(rules=[R("Targeting Visor")])
assert one(tv, unit(), distance=12).spec.hit_mod == 1     # alias -> PM
assert one(tv, unit(), distance=6).spec.hit_mod == 0
# Enhanced Targeting Visor Aura on one model: every model with the visor
# gets +1 within 9" too; a model without it gets nothing.
aura = CombatModel(model(rules=[R("Targeting Visor"),
                                R("Enhanced Targeting Visor Aura")]), 4, 4)
plain = CombatModel(model(), 4, 4)
p = plan(unit(2, rules=[R("Targeting Visor")], extra=(aura, plain)), unit(),
         distance=6)
assert sorted((g.models, g.spec.hit_mod) for g in p.groups) == \
    [((0, 1, 2), 1), ((3,), 0)]
# A joined Hero's own rules stay on the Hero.
hero = CombatModel(model(rules=[R("Good Shot"), R("Hero")]), 3, 4, hero=True)
p = plan(unit(3, extra=(hero,)), unit())
assert sorted((g.models, g.spec.quality, g.spec.hit_mod) for g in p.groups) \
    == [((0, 1, 2), 4, 0), ((3,), 3, 1)]
# Weapon rules
spec = one(unit(weapons=[W("Gun", 24, 2, R("Reliable"), R("Surge"),
                           R("Relentless"), R("Rending"), R("Shred"),
                           R("Blast", 3), R("Deadly", 2))]),
           unit(), "Gun").spec
assert (spec.quality, spec.extra_hits_on_6, spec.ap_on_6, spec.shred,
        spec.blast, spec.deadly, spec.ignores_regen) == (2, 2, 4, 1, 3, 2, True)
assert one(unit(weapons=[W("Gun", 24, 1, R("Relentless"))]), unit(), "Gun",
           distance=9).spec.extra_hits_on_6 == 0

# --- defender rules: most models, auras, no stacking -----------------------
st = CombatModel(model(rules=[R("Stealth")]), 4, 4)
assert one(unit(), unit(2, extra=(st,) * 3)).spec.hit_mod == -1    # 3 of 5
assert one(unit(), unit(2, extra=(st,) * 2)).spec.hit_mod == 0     # 2 of 4
assert one(unit(), unit(rules=[R("Stealth")]), distance=9).spec.hit_mod == 0
st_aura = CombatModel(model(rules=[R("Stealth"), R("Stealth Aura")]), 4, 4)
assert one(unit(), unit(4, rules=[R("Stealth")], extra=(st_aura,))
           ).spec.hit_mod == -1                                    # once
assert one(unit(), unit(4, extra=(st_aura,))).spec.hit_mod == -1   # aura
# Same entry twice at different ratings: highest only.
assert one(unit(weapons=[W("Gun", 24, 1, R("AP", 2), R("AP", 1))]), unit(),
           "Gun").spec.ap == 2
# Defender side too, whatever the model order: a test-only rated rule
# "+X to Defense rolls" (unit scope) on models rated 2 and 1 gives +2.
sem2 = {**SEM, "rules": {**SEM["rules"], "tshield": {
    "name": "Test Shield", "impl": "composed", "text_sha1": "0" * 40,
    "effects": [{"primitive": "defense_mod", "value": "X",
                 "side": "defender"}]}}}
reg2 = registry.RuleRegistry(sem2, core, [visor])
shield = Combatant("s", tuple(CombatModel(model(rules=[RuleRef(
    "tshield", "Test Shield", x)]), 4, 4) for x in (2, 1)))
t = build_plan(reg2, unit(), shield, Ctx()).groups[0].target
assert t.defense_mod == 2, t
ev = unit(rules=[R("Evasive")])
assert one(unit(), ev, "Hand Weapon", attack="melee").spec.hit_mod == -1
fort = unit(rules=[R("Fortified")])
assert one(unit(), fort).spec.ap == 0
assert one(unit(weapons=[W("Gun", 24, 1, R("Rending"))]), fort,
           "Gun").spec.ap == -1                    # gf_math floors per kind

# --- Unstoppable ----------------------------------------------------------------
un = unit(weapons=[W("Gun", 24, 1, R("AP", 1), R("Unstoppable"))])
tough_target = unit(rules=[R("Stealth"), R("Fortified")])
g = one(un, tough_target, "Gun", cover="terrain")
assert (g.spec.hit_mod, g.spec.ap, g.target.defense_mod) == (0, 1, 1)
g = one(unit(), tough_target, cover="terrain")
assert (g.spec.hit_mod, g.spec.ap, g.target.defense_mod) == (-1, 0, 1)
air = unit(rules=[R("Aircraft")])
assert plan(unit(), air, distance=18).groups == ()             # 24-12 < 18
g = one(un, air, "Gun", distance=18)
assert g.spec.hit_mod == 0

# --- cover, Blast, Anti-Cover, Indirect -------------------------------------------
assert one(unit(), unit(), cover="terrain").target.defense_mod == 1
assert one(unit(), unit(), "Hand Weapon", attack="melee",
           cover="terrain").target.defense_mod == 0
for w in (W("Gun", 24, 1, R("Blast", 3)), W("Gun", 24, 1, R("Anti-Cover"))):
    assert one(unit(weapons=[w]), unit(), "Gun",
               cover="terrain").target.defense_mod == 0
ind = unit(weapons=[W("Gun", 24, 1, R("Indirect"))])
assert one(ind, unit(), "Gun", cover="sight_blocker",
           line_of_sight=False).target.defense_mod == 0
assert one(ind, unit(), "Gun", cover="terrain").target.defense_mod == 1
assert plan(ind, unit(), line_of_sight=False, action="advance").groups == ()
assert plan(unit(), unit(), line_of_sight=False).groups == ()

# --- target Defense: Armor per model, joined Hero, Regeneration ------------------
armored = CombatModel(model(rules=[R("Armor", 3)]), 4, 4)
g = one(unit(), unit(2, extra=(armored,)))
assert g.target is None and [t.defense for t in g.targets] == [4, 4, 3]
hero_d = CombatModel(model(rules=[R("Hero"), R("Armor", 2)]), 3, 3, hero=True)
assert [t.defense for t in one(unit(), unit(2, extra=(hero_d,))).targets] \
    == [4, 4, 4]
assert [t.defense for t in one(unit(), Combatant("h", (hero_d,))).targets] \
    == [2]
rg = CombatModel(model(rules=[R("Regeneration")]), 4, 4)
assert one(unit(), unit(1, extra=(rg,) * 2)).target.regeneration
assert not one(unit(), unit(2, extra=(rg,) * 2)).target.regeneration
assert one(unit(weapons=[W("Gun", 24, 1, R("Bane"))]),
           unit(rules=[R("Regeneration")]), "Gun").spec.ignores_regen

# --- target-dependent attacker rules ----------------------------------------------------
pun = unit(weapons=[W("Gun", 24, 1, R("Puncture"))])
assert one(pun, unit(d=3), "Gun").spec.ap == 2
assert one(pun, unit(d=4), "Gun").spec.ap == 0
assert one(pun, unit(2, d=4, extra=(armored,) * 3), "Gun").spec.ap == 2
sm = unit(weapons=[W("Gun", 24, 1, R("Smash"))])
assert one(sm, unit(), "Gun", distance=13).spec.reroll_defense_6
assert not one(sm, unit(), "Gun", distance=12).spec.reroll_defense_6
far = unit(weapons=[W("Gun", 24, 1, R("Smash"))],
           rules=[R("Increased Shooting Range Aura")])
assert not one(far, unit(), "Gun", distance=13).spec.reroll_defense_6
assert one(far, unit(), "Gun", distance=30).spec.reroll_defense_6
art = unit(rules=[R("Artillery")])
assert one(art, unit(), distance=13).spec.hit_mod == 1
assert one(art, unit(), distance=13, action="advance").spec.hit_mod == 0
assert one(unit(), unit(rules=[R("Artillery")]), distance=13).spec.hit_mod == -1
assert one(unit(), unit(rules=[R("Artillery")], not_moved=False),
           distance=13).spec.hit_mod == 0
slay = unit(rules=[R("Ranged Slayer")])
big = unit(rules=[RuleRef(IDS["Tough"], "Tough", 3, "Tough(3)")])
assert one(slay, big).spec.ap == 3 and one(slay, unit()).spec.ap == 1
assert one(slay, big, action="advance").spec.ap == 1

# --- melee ------------------------------------------------------------------------------
lance = W("Lance", 0, 2, R("Thrust"), R("Counter"))
pistol = W("Pistol", 12, 1, R("Assault"))
mel = unit(weapons=[lance, pistol], rules=[R("Furious")], fatigued=True)
p = plan(mel, unit(), attack="melee", action="charge")
lg = next(g for g in p.groups if g.weapon.name == "Lance")
assert (lg.spec.hit_mod, lg.spec.ap, lg.spec.extra_hits_on_6, lg.spec.fatigued,
        lg.counter) == (1, 1, 1, True, True)
assert {g.weapon.name for g in p.groups} == {"Lance", "Pistol"}   # Assault
lg = one(mel, unit(), "Lance", attack="melee", action=None)       # strike back
assert (lg.spec.hit_mod, lg.spec.extra_hits_on_6) == (0, 0)
bma = unit(rules=[R("Bane in Melee Aura"), R("Counter in Melee Aura")])
assert one(bma, unit(), "Hand Weapon", attack="melee").spec.reroll_defense_6
assert one(bma, unit(), "Hand Weapon", attack="melee").counter
assert not one(bma, unit()).spec.reroll_defense_6

# --- token rules: Marks, Spotter, Versatile ----------------------------------------------
g = one(unit(), unit(rules=[R("Stealth")]), spotter_tokens=2,
        marks=(IDS["Piercing Shooting Mark"], IDS["Unstoppable Mark"]))
assert (g.spec.hit_mod, g.spec.ap) == (2, 2)          # Stealth ignored
assert one(unit(), unit(), "Hand Weapon", attack="melee",
           marks=(IDS["Piercing Shooting Mark"],)).spec.ap == 0
vx = unit(rules=[R("Versatile Expert")])
assert one(vx, unit()).spec.ap == 1                   # nothing chosen
assert one(vx, unit(), versatile=((IDS["Versatile Expert"], 0),)).spec.ap == 2
assert one(vx, unit(), versatile=((IDS["Versatile Expert"], 1),)
           ).spec.hit_mod == 1
assert one(unit(), unit(), versatile=((IDS["Versatile Expert"], 1),)
           ).spec.hit_mod == 0

# --- flags, Crossing Strike, warnings ----------------------------------------------------
g = one(unit(weapons=[W("Gun", 24, 1, R("Takedown"), R("Limited"))]), unit(),
        "Gun")
assert g.takedown and g.limited and "Takedown" in g.sources
# Real Crossing Strike weapons are range-0 bombs: in a crossing attack they
# ignore range, action and line of sight.
cs = unit(weapons=[RIFLE, W("Bombs", 0, 2, R("Crossing Strike"))])
assert [g.weapon.name for g in plan(cs, unit()).groups] == ["Rifle"]
for act in ("advance", "rush"):
    p = plan(cs, unit(), crossing=True, distance=1, action=act,
             line_of_sight=False)
    assert [g.weapon.name for g in p.groups] == ["Bombs"], (act, p.excluded)
    assert [x[0] for x in p.excluded] == ["Rifle"]
    assert p.groups[0].target.defense_mod == 0                  # no cover
p = plan(cs, unit(), crossing=True, distance=1, cover="terrain")
assert p.groups[0].target.defense_mod == 0
p = plan(unit(weapons=[W("Gun", 24, 1, R("AP", "two"),
                         RuleRef("zzz", "Mystery"))]), unit())
assert any("Mystery" in w for w in p.warnings)
assert any("'two'" in w for w in p.warnings) and p.groups[0].spec.ap == 0

# --- end to end: plan -> gf_math ----------------------------------------------------------
g = one(unit(10, rules=[R("Good Shot")]), unit(rules=[R("Fortified")]),
        cover="terrain")
law = G.weapon_law(g.spec, g.target, 5, exact=True)
# Hit 3+ (Good Shot) = 4/6; block: D4, cover +1, AP(1) - Fortified = 0
# -> blocks on 3+, fails 2/6.
assert (g.spec.hit_mod, g.spec.ap, g.target.defense_mod) == (1, 0, 1)
assert P.mean(law.gross) == 10 * F(4, 6) * F(2, 6)

# --- real data: every DAO / BB unit against each other, no warnings ----------------------
if not testpaths.USING_SYNTHETIC:
    from grimdarkoracle.data.resolve import resolve
    from grimdarkoracle.engine.context import combatant
    books = [ab.load_book(testpaths.book_path(u))
             for u in ("z8205ez2boggzs22", "78qp9l5alslt6yj8")]
    real = registry.RuleRegistry(SEM, ab.load_core_rules(testpaths.rules_path()),
                                 books)
    units = [resolve(b, u) for b in books for u in b.units]
    count = 0
    for a in units:
        for t in units[::5]:
            for ctx in (Ctx(), Ctx(distance=24, cover="terrain"),
                        Ctx("melee", action="charge")):
                p = build_plan(real, combatant(a), combatant(t), ctx)
                assert not p.warnings, (a.name, p.warnings)
                count += 1
    print(f"modifiers: {count} real plans, no warnings")
print("modifiers: OK")
