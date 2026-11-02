"""the Mark and Buff families mapped with the existing vocabulary
and the base rules they grant: their effects on the
AttackSpec / TargetSpec and the grants of the Analyzer buff toggles."""
import testpaths                                    # noqa: F401 (sys.path)
from grimdarkoracle.app import spells as SP
from grimdarkoracle.engine.context import AttackContext as Ctx
from grimdarkoracle.engine.modifiers import build_plan
from unitkit import IDS, REG, R, unit

TOUGH3 = R("Tough", 3)


def plan(att, tgt, **ctx):
    return build_plan(REG, att, tgt, Ctx(**ctx))


def one(att, tgt, weapon="Rifle", **ctx):
    gs = [g for g in plan(att, tgt, **ctx).groups if g.weapon.name == weapon]
    assert len(gs) == 1, gs
    return gs[0]


def melee(att, tgt, **ctx):
    return one(att, tgt, "Hand Weapon", attack="melee", **ctx)


def mk(name):
    return (IDS[name],)


CHARGE = {"action": "charge"}
BACK = {"action": None}                             # strike back

# --- every entry below is mapped ---------------------------------------------
NAMES = ("Bane Mark", "Furious Mark", "Increased Shooting Range Mark",
         "Indirect Mark", "Precision Fighting Mark", "Precision Shooting Mark",
         "Relentless Mark", "Rending Mark", "Shred Mark", "Slayer Mark",
         "Bane in Melee Buff", "Furious Buff", "Guarded Buff",
         "Entrenched Buff", "Counter in Melee Buff", "Thrust in Melee Buff",
         "Rapid Advance Buff", "Rapid Rush Buff", "Swift Buff", "Speed Buff",
         "Precision Fighter Buff", "Increased Shooting Range Buff",
         "Speed Debuff", "Difficult Terrain Debuff", "Slayer", "Guarded",
         "Entrenched", "Counter in Melee", "Thrust in Melee",
         "Precision Fighter", "Increased Shooting Range", "Rapid Advance",
         "Swift")
for name in NAMES:
    sem = REG.lookup(IDS[name], name)
    assert sem is not None and sem.impl != "todo", name

# --- base rules --------------------------------------------------------
big, small = unit(rules=[TOUGH3]), unit()
sl = unit(rules=[R("Slayer")])
assert one(sl, big).spec.ap == 2                     # Hold + shooting
assert one(sl, big, action="advance").spec.ap == 0
assert melee(sl, big, **CHARGE).spec.ap == 2
assert melee(sl, big, **BACK).spec.ap == 0
assert one(sl, small).spec.ap == 0 and melee(sl, small, **CHARGE).spec.ap == 0

gd = unit(rules=[R("Guarded")])
assert one(unit(), gd, distance=10).target.defense_mod == 1
assert one(unit(), gd, distance=9).target.defense_mod == 0
assert melee(unit(), gd, charge_distance=7, **CHARGE).target.defense_mod == 1
assert melee(unit(), gd, charge_distance=6, **CHARGE).target.defense_mod == 0
mixed = unit(2, rules=[R("Guarded")], extra=unit(3).models)
assert one(unit(), mixed, distance=10).target.defense_mod == 0

en = unit(rules=[R("Entrenched")])
assert one(unit(), en, distance=13).spec.hit_mod == -1
assert one(unit(), en, distance=12).spec.hit_mod == 0
assert one(unit(), unit(rules=[R("Entrenched")], not_moved=False),
           distance=13).spec.hit_mod == 0

ci = unit(rules=[R("Counter in Melee")])
assert melee(ci, unit(), **BACK).counter            # it strikes first
assert not melee(unit(), unit(), **BACK).counter
tm = unit(rules=[R("Thrust in Melee")])
s = melee(tm, unit(), **CHARGE).spec
assert (s.hit_mod, s.ap) == (1, 1)
assert (melee(tm, unit(), **BACK).spec.hit_mod, one(tm, unit()).spec.ap) \
    == (0, 0)
pf = unit(rules=[R("Precision Fighter")])
assert melee(pf, unit(), **BACK).spec.hit_mod == 1
assert one(pf, unit()).spec.hit_mod == 0
isr = unit(rules=[R("Increased Shooting Range")])
assert one(isr, unit(), distance=30).spec.attacks == 5
assert not [g for g in plan(unit(), unit(), distance=30).groups
            if g.weapon.name == "Rifle"]

# --- Marks in the engine (Analyzer toggles) ----------------------------
regen = unit(rules=[R("Regeneration")])
s = one(unit(), regen, marks=mk("Bane Mark")).spec
assert s.ignores_regen and s.reroll_defense_6
assert melee(unit(), regen, marks=mk("Bane Mark"), **CHARGE).spec \
    .reroll_defense_6
assert one(unit(), unit(), marks=mk("Rending Mark")).spec.ap_on_6 == 4
assert one(unit(), unit(), marks=mk("Shred Mark")).spec.shred == 1
fm = mk("Furious Mark")
assert melee(unit(), unit(), marks=fm, **CHARGE).spec.extra_hits_on_6 == 1
assert melee(unit(), unit(), marks=fm, **BACK).spec.extra_hits_on_6 == 0
assert one(unit(), unit(), marks=fm).spec.extra_hits_on_6 == 0
rm = mk("Relentless Mark")
assert one(unit(), unit(), marks=rm, distance=10).spec.extra_hits_on_6 == 1
assert one(unit(), unit(), marks=rm, distance=9).spec.extra_hits_on_6 == 0
im = mk("Indirect Mark")
assert one(unit(), unit(), marks=im, line_of_sight=False).spec.attacks == 5
assert not [g for g in plan(unit(), unit(), marks=im, line_of_sight=False,
                            action="advance").groups]
assert not [g for g in plan(unit(), unit(), line_of_sight=False).groups]
ir = mk("Increased Shooting Range Mark")
assert one(unit(), unit(), marks=ir, distance=30).spec.attacks == 5
pfm, psm = mk("Precision Fighting Mark"), mk("Precision Shooting Mark")
assert melee(unit(), unit(), marks=pfm, **CHARGE).spec.hit_mod == 1
assert one(unit(), unit(), marks=pfm).spec.hit_mod == 0
assert one(unit(), unit(), marks=psm).spec.hit_mod == 1
assert melee(unit(), unit(), marks=psm, **CHARGE).spec.hit_mod == 0
sm = mk("Slayer Mark")
assert one(unit(), big, marks=sm).spec.ap == 2
assert melee(unit(), big, marks=sm, **CHARGE).spec.ap == 2
assert one(unit(), small, marks=sm).spec.ap == 0
# a Mark never acts for its own holder
assert one(unit(rules=[R("Precision Shooting Mark")]), unit()).spec.hit_mod \
    == 0

# --- the grants of the buff toggles ---------------------------------
assert [r.id for r, _to, _a in SP.rule_buff_grants(
    REG, IDS["Furious Buff"])] == [IDS["Furious"]]
assert [a for _r, _to, a in SP.rule_buff_grants(
    REG, IDS["Increased Shooting Range Buff"])] == ["shooting"]
assert all(SP.rule_buff_grants(REG, IDS[n]) == [] for n in (
    "Rapid Advance Buff", "Speed Buff"))           # no combat effect

print("test_marks_buffs OK")
