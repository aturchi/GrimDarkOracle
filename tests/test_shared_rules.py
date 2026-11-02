"""rules shared by 3+ books mapped with the existing vocabulary.
Each entry is checked on the AttackSpec / TargetSpec
it produces, on hand-built units carrying the real rule ids."""
import testpaths                                    # noqa: F401 (sys.path)
from grimdarkoracle.engine.context import AttackContext as Ctx
from grimdarkoracle.engine.modifiers import build_plan
from grimdarkoracle.rules import effects as E
from unitkit import IDS, REG, R, W, cm, unit


def plan(att, tgt, **ctx):
    return build_plan(REG, att, tgt, Ctx(**ctx))


def one(att, tgt, weapon="Rifle", **ctx):
    gs = [g for g in plan(att, tgt, **ctx).groups if g.weapon.name == weapon]
    assert len(gs) == 1, gs
    return gs[0]


def melee(att, tgt, **ctx):
    return one(att, tgt, "Hand Weapon", attack="melee", **ctx)


CHARGE = {"action": "charge"}
TOUGH3 = R("Tough", 3)

# --- every entry below is mapped (not unmapped / todo) -----------------------
for name in ("Anti-Regen", "Melee Slayer", "Repel Ambushers", "Bounding",
             "Furious Aura", "Scout Aura", "Relentless Aura", "Steadfast Aura",
             "Ambush Aura", "Delayed Action", "Teleport", "Agile",
             "Infiltrate", "Spawn", "Dodge", "Imprecise",
             "Precision Fighter Aura", "Rapid Charge Aura", "Sergeant",
             "Bounding Aura", "Lustbound", "Piercing Charge",
             "Piercing Charge Aura", "Piercing Marksman",
             "Piercing Marksman Aura", "Shielded", "Shielded Aura",
             "Shred in Melee Aura", "Teleport Aura"):
    sem = REG.lookup(IDS[name], name)
    assert sem is not None and sem.impl != "todo", name

# --- weapon and model rules --------------------------------------------------
gun = unit(weapons=[W("Gun", 24, 1, R("Anti-Regen"))])
regen = unit(rules=[R("Regeneration")])
assert one(gun, regen, "Gun").spec.ignores_regen
assert not one(unit(), regen).spec.ignores_regen

sgt = unit(rules=[R("Sergeant")])
assert one(sgt, unit()).spec.ap == 1 and melee(sgt, unit()).spec.ap == 1
imp = unit(rules=[R("Imprecise")])
assert one(imp, unit()).spec.hit_mod == -1
assert melee(imp, unit()).spec.hit_mod == -1
# Imprecise is the model's own rule: Unstoppable keeps it
ugun = unit(weapons=[W("Gun", 24, 1, R("Unstoppable"))],
            rules=[R("Imprecise")])
assert one(ugun, unit(), "Gun").spec.hit_mod == -1

# "When charging": the charger's strikes only
slay = unit(rules=[R("Melee Slayer")])
big = unit(rules=[TOUGH3])
assert melee(slay, big, **CHARGE).spec.ap == 2
assert melee(slay, big).spec.ap == 0                  # strike back
assert melee(slay, unit(), **CHARGE).spec.ap == 0     # target not Tough(3)+
assert one(slay, big).spec.ap == 0                    # shooting
pc = unit(rules=[R("Piercing Charge")])
assert melee(pc, unit(), **CHARGE).spec.ap == 1
assert melee(pc, unit()).spec.ap == 0

pm = unit(rules=[R("Piercing Marksman")])
assert one(pm, unit(), distance=10).spec.ap == 1
assert one(pm, unit(), distance=9).spec.ap == 0

# --- auras: one holder gives the rule to every model of its unit --------
def aura_unit(aura, n=4):
    return unit(n, extra=(cm(rules=[R(aura)]),))


pca = aura_unit("Piercing Charge Aura")
assert melee(pca, unit(), **CHARGE).models == (0, 1, 2, 3, 4)
assert melee(pca, unit(), **CHARGE).spec.ap == 1
pma = aura_unit("Piercing Marksman Aura")
assert one(pma, unit(), distance=12).spec.ap == 1
pfa = aura_unit("Precision Fighter Aura")
assert melee(pfa, unit()).spec.hit_mod == 1
assert one(pfa, unit()).spec.hit_mod == 0
sma = aura_unit("Shred in Melee Aura")
assert melee(sma, unit()).spec.shred == 1 and one(sma, unit()).spec.shred == 0
fa = aura_unit("Furious Aura")
assert melee(fa, unit(), **CHARGE).spec.extra_hits_on_6 == 1
ra = aura_unit("Relentless Aura")
assert one(ra, unit(), distance=12).spec.extra_hits_on_6 == 1

# Steadfast Aura: every model of the unit holds Steadfast
sa = aura_unit("Steadfast Aura")
v = E.View(REG, Ctx(), "defender", sa, (), sa,
           tuple(m.defense for m in sa.models))
holds, missing = E.holdings(REG, v)
assert not missing
assert all(any(h.sem.name == "Steadfast" for h in hs) for hs in holds)

# --- defender rules ----------------------------------------------------------
dodge = unit(rules=[R("Dodge")])
assert melee(unit(), dodge, **CHARGE).spec.hit_mod == -1
assert melee(unit(), dodge).spec.hit_mod == -1
assert one(unit(), dodge).spec.hit_mod == 0           # shooting
assert melee(unit(), unit(rules=[R("Dodge")], fatigued=True),
             **CHARGE).spec.hit_mod == 0
mixed = unit(2, rules=[R("Dodge")], extra=unit(3).models)
assert melee(unit(), mixed, **CHARGE).spec.hit_mod == 0   # not most

sh = unit(rules=[R("Shielded")])
assert one(unit(), sh).target.defense_mod == 1
assert melee(unit(), sh, **CHARGE).target.defense_mod == 1
assert one(unit(), sh, cover="terrain").target.defense_mod == 2
shm = unit(2, rules=[R("Shielded")], extra=unit(3).models)
assert one(unit(), shm).target.defense_mod == 0
assert one(unit(), aura_unit("Shielded Aura")).target.defense_mod == 1

# --- no combat effect: the plan is the plain one -----------------------------
for name in ("Repel Ambushers", "Bounding", "Delayed Action", "Teleport",
             "Agile", "Infiltrate", "Spawn", "Rapid Charge Aura", "Lustbound",
             "Scout Aura", "Ambush Aura", "Bounding Aura", "Teleport Aura"):
    u = unit(rules=[R(name)])
    for a, t in ((u, unit()), (unit(), u)):
        p, q = plan(a, t), plan(unit(), unit())
        assert [g.spec for g in p.groups] == [g.spec for g in q.groups], name
        assert [g.target for g in p.groups] == [g.target for g in q.groups]
        assert not p.warnings, (name, p.warnings)

print("test_shared_rules OK")
