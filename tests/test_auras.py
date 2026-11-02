"""auras whose base rule is mapped, the "X on its weapons in melee /
when shooting" family and Ravage Aura. Checked on the
AttackSpec / TargetSpec each entry produces, on hand-built units carrying
the real rule ids, and on the real Daemons of Plague book when present."""
import testpaths
from grimdarkoracle.data import rule_weapons as RW
from grimdarkoracle.data.resolve import combine
from grimdarkoracle.engine.context import AttackContext as Ctx
from grimdarkoracle.engine.context import combatant
from grimdarkoracle.engine.modifiers import build_plan
from grimdarkoracle.rules import effects as E
from unitkit import IDS, REG, R, cm, model, resolved, unit

CHARGE = {"action": "charge"}
MAPPED = (
    "Anti-Cover Aura", "Evasive Aura", "Fast Aura", "Fearless Aura",
    "Infiltrate Aura", "Melee Slayer Aura", "Protected Aura",
    "Rapid Advance Aura", "Ravage Aura", "Strider Aura", "Swift Aura",
    "Thrust in Melee Aura", "Anti-Cover when Shooting Aura",
    "Indirect when Shooting Aura", "Rending in Melee Aura",
    "Rending when Shooting Aura", "Shred when Shooting Aura",
    "Unstoppable in Melee Aura", "Unstoppable when Shooting Aura",
    "Piercing Fighter Aura", "Piercing Shooter Aura",
    "Precision Shooter Aura", "Precision Charge Aura", "Precision Charge",
    "Anti-Cover when Shooting", "Rending in Melee", "Shred in Melee",
    "Shred when Shooting", "Unstoppable in Melee",
    "Unstoppable when Shooting")


def groups(att, tgt, weapon, **ctx):
    return [g for g in build_plan(REG, att, tgt, Ctx(**ctx)).groups
            if g.weapon.name == weapon]


def one(att, tgt, weapon="Rifle", **ctx):
    gs = groups(att, tgt, weapon, **ctx)
    assert len(gs) == 1, gs
    return gs[0]


def melee(att, tgt, **ctx):
    return one(att, tgt, "Hand Weapon", attack="melee", **ctx)


def aura_unit(aura, n=4):
    """n plain models and one holder: the aura reaches all five."""
    return unit(n, extra=(cm(rules=[R(aura)]),))


def held_by_all(u, name):
    v = E.View(REG, Ctx(), "defender", u, (), u,
               tuple(m.defense for m in u.models))
    holds, missing = E.holdings(REG, v)
    return not missing and all(any(h.sem.name == name for h in hs)
                               for hs in holds)


ALL = (0, 1, 2, 3, 4)

# --- every entry is mapped ---------------------------------------------------
for name in MAPPED:
    sem = REG.lookup(IDS[name], name)
    assert sem is not None and sem.impl != "todo", name

# --- (a) auras granting a mapped rule --------------------------------
for aura, rule in (("Evasive Aura", "Evasive"), ("Fearless Aura", "Fearless"),
                   ("Protected Aura", "Protected"),
                   ("Melee Slayer Aura", "Melee Slayer")):
    assert held_by_all(aura_unit(aura), rule), aura
# one holder in five: a majority only through the aura
lone = unit(4, extra=(cm(rules=[R("Evasive")]),))
assert one(unit(), lone).spec.hit_mod == 0
assert one(unit(), aura_unit("Evasive Aura")).spec.hit_mod == -1
assert one(unit(), aura_unit("Protected Aura")).target.wards == (6,)
assert one(unit(), lone).target.wards == ()
big = unit(rules=[R("Tough", 3)])
msa = aura_unit("Melee Slayer Aura")
assert melee(msa, big, **CHARGE).spec.ap == 2
assert melee(msa, big, **CHARGE).models == ALL
assert melee(msa, big).spec.ap == 0                   # strike back
tma = aura_unit("Thrust in Melee Aura")
g = melee(tma, unit(), **CHARGE)
assert (g.spec.hit_mod, g.spec.ap, g.models) == (1, 1, ALL)
assert melee(tma, unit()).spec.hit_mod == 0           # not charging
assert one(tma, unit()).spec.hit_mod == 0            # shooting

# --- (b) core rule granted under "attack" ----------------------------
for aura in ("Rending in Melee Aura", "Rending when Shooting Aura"):
    a = aura_unit(aura)
    m, s = melee(a, unit()).spec, one(a, unit()).spec
    on, off = (m, s) if "Melee" in aura else (s, m)
    assert (on.ap_on_6, on.ignores_regen) == (4, True), aura
    assert (off.ap_on_6, off.ignores_regen) == (0, False), aura
    assert (melee(a, unit()) if "Melee" in aura else one(a, unit())
            ).models == ALL
sws = aura_unit("Shred when Shooting Aura")
assert one(sws, unit()).spec.shred == 1 and melee(sws, unit()).spec.shred == 0
evasive = unit(rules=[R("Evasive")])                  # -1 to hit
uim = aura_unit("Unstoppable in Melee Aura")
assert melee(uim, evasive).spec.hit_mod == 0
assert one(uim, evasive).spec.hit_mod == -1
uws = aura_unit("Unstoppable when Shooting Aura")
assert one(uws, evasive).spec.hit_mod == 0
assert melee(uws, evasive).spec.hit_mod == -1
for aura in ("Anti-Cover Aura", "Anti-Cover when Shooting Aura"):
    assert one(aura_unit(aura), unit(), cover="terrain").target.defense_mod \
        == 0, aura
assert one(unit(), unit(), cover="terrain").target.defense_mod == 1
iws = aura_unit("Indirect when Shooting Aura")
assert one(iws, unit(), line_of_sight=False).models == ALL
assert not groups(iws, unit(), "Rifle", line_of_sight=False,
                  action="advance")                   # Hold only
assert not groups(unit(), unit(), "Rifle", line_of_sight=False)

# --- (c) auras with effects of their own -----------------------------
pfa = aura_unit("Piercing Fighter Aura")
psa = aura_unit("Piercing Shooter Aura")
assert (melee(pfa, unit()).spec.ap, one(pfa, unit()).spec.ap) == (1, 0)
assert (melee(psa, unit()).spec.ap, one(psa, unit()).spec.ap) == (0, 1)
assert one(psa, unit()).models == ALL
pso = aura_unit("Precision Shooter Aura")
assert (one(pso, unit()).spec.hit_mod, melee(pso, unit()).spec.hit_mod) == \
    (1, 0)
pca = aura_unit("Precision Charge Aura")
assert melee(pca, unit(), **CHARGE).spec.hit_mod == 1
assert melee(pca, unit(), **CHARGE).models == ALL
assert melee(pca, unit()).spec.hit_mod == 0           # strike back
assert one(pca, unit()).spec.hit_mod == 0
# the model rule reaches its holder only
pc = unit(4, extra=(cm(rules=[R("Precision Charge")]),))
mods = {g.models: g.spec.hit_mod
        for g in groups(pc, unit(), "Hand Weapon", attack="melee", **CHARGE)}
assert mods == {(0, 1, 2, 3): 0, (4,): 1}, mods

# --- model rules of the family: holder only, one attack type -----------------
for name, field, val, kind in (
        ("Rending in Melee", "ap_on_6", 4, "melee"),
        ("Shred in Melee", "shred", 1, "melee"),
        ("Shred when Shooting", "shred", 1, "shooting")):
    u = unit(rules=[R(name)])
    on = melee(u, unit()) if kind == "melee" else one(u, unit())
    off = one(u, unit()) if kind == "melee" else melee(u, unit())
    assert getattr(on.spec, field) == val and getattr(off.spec, field) == 0
uim1 = unit(rules=[R("Unstoppable in Melee")])
assert melee(uim1, evasive).spec.hit_mod == 0
assert one(uim1, evasive).spec.hit_mod == -1
uws1 = unit(rules=[R("Unstoppable when Shooting")])
assert (one(uws1, evasive).spec.hit_mod, melee(uws1, evasive).spec.hit_mod) \
    == (0, -1)
acs = unit(rules=[R("Anti-Cover when Shooting")])
assert one(acs, unit(), cover="terrain").target.defense_mod == 0

# --- (d) no combat effect: the plan is the plain one -------------------------
for name in ("Fast Aura", "Infiltrate Aura", "Rapid Advance Aura",
             "Strider Aura", "Swift Aura"):
    u = aura_unit(name)
    for a, t in ((u, unit(5)), (unit(5), u)):
        p = build_plan(REG, a, t, Ctx())
        q = build_plan(REG, unit(5), unit(5), Ctx())
        assert [x.spec for x in p.groups] == [x.spec for x in q.groups], name
        assert [x.target for x in p.groups] == [x.target for x in q.groups]
        assert not p.warnings, (name, p.warnings)

# --- (e) Ravage Aura: Ravage(X+1) on every model of the unit ---------
def ravage(m):
    return [w.attacks for w, _n in m.weapons if w.name == "Ravage"]


banner = resolved(unit(3, extra=(cm(rules=[R("Ravage Aura")]),
                                 cm(rules=[R("Ravage", 2)]))))
armed = RW.add_all(banner)
assert [ravage(m) for m in armed.models] == [[1], [1], [1], [1], [3]]
assert all(m.weapons[0][0].name == "Ravage" for m in armed.models)  # first
assert RW.add_all(armed) == armed                     # idempotent
assert RW.add_all(resolved(unit(3))) == resolved(unit(3))
# the dice in the plan: one die per model, 6+ with no Defense roll
gs = groups(combatant(armed), unit(), "Ravage", attack="melee", **CHARGE)
assert all((g.spec.no_block, g.spec.quality) == (True, 6) for g in gs)
assert sum(g.spec.attacks for g in gs) == 1 + 1 + 1 + 1 + 3
# a Combined Unit: the aura of copy A reaches copy B
plain = RW.add_all(resolved(unit(5)))
both = combine(armed, plain)
assert [ravage(m) for m in both.models[5:]] == [[1]] * 5
# copy B already armed with its own Ravage(2): the aura makes it Ravage(3)
own2 = RW.add_all(resolved(unit(2, rules=[R("Ravage", 2)])))
assert [ravage(m) for m in own2.models] == [[2], [2]]
assert [ravage(m) for m in combine(armed, own2).models[5:]] == [[3], [3]]
# two Ravage rules on one model: one weapon, the first rule's rating
twice = RW.add(model(rules=[R("Ravage", 2), R("Ravage", 1)]))
assert ravage(twice) == [2]
# a joined Hero gets it from its host, and gives it to its host
hero = RW.add_all(resolved(unit(1)))
cb = combatant(armed, hero=hero)
assert ravage(cb.models[-1].model) == [1] and cb.models[-1].hero
assert all(not ravage(c.model) for c in combatant(plain, hero=hero).models)
lord = RW.add_all(resolved(unit(1, rules=[R("Ravage Aura")])))
assert all(ravage(c.model) == [1]
           for c in combatant(plain, hero=lord).models)

# --- the real book: Plague Warriors with the Banner of Plague ----------------
if not testpaths.USING_SYNTHETIC:
    from grimdarkoracle.app.library import Library
    from grimdarkoracle.data.resolve import Choice, resolve
    lib = Library.load(testpaths.DATA_DIR)
    book = next(b for b in lib.books.values()
                if b.name == "Daemons of Plague")
    uid = next(k for k, x in book.units.items()
               if x.name == "Plague Warriors")
    pick = next(Choice(pu, s.uid, o.uid, 1)
                for pu in book.units[uid].packages
                for s in book.packages[pu].sections for o in s.options
                if "(Ravage Aura)" in o.label)
    ru = resolve(book, uid, [pick])
    assert [ravage(m) for m in ru.models] == [[1]] * ru.size
    assert all(not ravage(m) for m in resolve(book, uid, ()).models)
    # whole charge in the Analyzer: P(no wound) = P(no wound without the
    # banner) x P(no 6 on its five Ravage dice) (a target with no
    # Regeneration or ward; no wound leaves the state unchanged)
    from grimdarkoracle.app import side_spec as S
    from grimdarkoracle.app.setup_model import Setup, SideSetup
    from grimdarkoracle.app.unit_config import UnitConfig
    bb = next(b for b in lib.books.values() if b.name == "Battle Brothers")
    tid = next(k for k, x in bb.units.items() if x.name == "Pathfinders")
    p0 = [S.run(lib.reg, S.SideSpec(S.UnitSpec(UnitConfig(book, uid, ch))),
                SideSetup(), S.book_side(bb, tid), SideSetup(),
                Setup(attack="melee", action="charge")).def_losses.wounds[0]
          for ch in ((), (pick,))]
    assert abs(p0[1] - p0[0] * (5 / 6) ** 5) < 1e-12, p0

print("test_auras OK")
