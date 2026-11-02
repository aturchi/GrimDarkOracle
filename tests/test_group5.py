"""Human Defense Force, Human Inquisition, Infected Colonies:
Quick Throw, Piercing Tag, Defensive / Precision Growth,
the No Retreat buff and aura, the Enhanced auras, and the spells."""
from fractions import Fraction as F

import testpaths
from grimdarkoracle.app import defense_choice as DC
from grimdarkoracle.app import spells as SP
from grimdarkoracle.engine import kill_chain as K
from grimdarkoracle.engine import morale as MO
from grimdarkoracle.engine.context import AttackContext as Ctx
from grimdarkoracle.engine.context import combatant
from grimdarkoracle.engine.modifiers import build_plan
from grimdarkoracle.engine.target_state import Allocation
from grimdarkoracle.rules import effects as E
from unitkit import IDS, REG, R, W, cm, resolved, unit

GROUP = ("Human Defense Force", "Human Inquisition", "Infected Colonies")
MELEE = {"attack": "melee", "action": "charge"}

for name in ("Coordinate", "Enhanced Hold the Line Aura", "No Retreat Buff",
             "Defensive Growth", "Defensive Growth Aura", "Quick Throw",
             "Piercing Tag", "Enhanced Infected Aura", "No Retreat Aura",
             "Precision Growth"):
    sem = REG.lookup(IDS[name], name)
    assert sem is not None and sem.impl != "todo", name


def names(att, tgt, **ctx):
    return sorted(g.weapon.name for g in build_plan(REG, att, tgt,
                                                    Ctx(**ctx)).groups)


def one(att, tgt, weapon="Rifle", **ctx):
    gs = [g for g in build_plan(REG, att, tgt, Ctx(**ctx)).groups
          if g.weapon.name == weapon]
    assert len(gs) == 1, gs
    return gs[0]


# --- Quick Throw: Indirect without line of sight after any action -----
MORTAR = W("Mortar", 24, 1, R("Indirect"))
WEAPONS = (MORTAR, W("Rifle", 24, 1))
qt = unit(weapons=WEAPONS, rules=[R("Quick Throw")])
plain = unit(weapons=WEAPONS)
blind = {"line_of_sight": False, "distance": 12}
assert names(plain, unit(), action="hold", **blind) == ["Mortar"]
assert names(plain, unit(), action="advance", **blind) == []
assert names(qt, unit(), action="advance", **blind) == ["Mortar"]
assert names(qt, unit(), action="hold", **blind) == ["Mortar"]
assert names(qt, unit(), action="rush", **blind) == []       # no shooting
# the cover part of Indirect stays Hold-only
sb = dict(cover="sight_blocker", distance=12)
assert one(qt, unit(), "Mortar", action="hold", **sb).targets[0] \
    .defense_mod == 0
assert one(qt, unit(), "Mortar", action="advance", **sb).targets[0] \
    .defense_mod == one(qt, unit(), "Rifle", action="advance", **sb) \
    .targets[0].defense_mod == 1
# held by one model only: its Indirect weapon, not the others'
part = unit(1, weapons=WEAPONS, rules=[R("Quick Throw")],
            extra=unit(1, weapons=WEAPONS).models)
gs = build_plan(REG, part, unit(), Ctx(action="advance", **blind)).groups
assert [g.models for g in gs] == [(0,)], gs

# --- Piercing Tag: the AP spotter tokens (one per attack) -------------------
assert REG.lookup(IDS["Piercing Tag"]).handler == "spotter"
assert one(unit(), unit(), ap_spotter_tokens=1).spec.ap == 1

# --- Defensive Growth: the target's token state, +1 / +2 Defense ------------
DG, PG = IDS["Defensive Growth"], IDS["Precision Growth"]
dg = unit(rules=[R("Defensive Growth")])
assert [one(unit(), dg, versatile=v).targets[0].defense_mod
        for v in ((), ((DG, 0),), ((DG, 1),))] == [0, 1, 2]
assert DC.is_state(REG, DG)
few = unit(2, rules=[R("Defensive Growth")], extra=unit(3).models)
assert one(unit(), few, versatile=((DG, 1),)).targets[0].defense_mod == 0
# the aura: one holder gives it to the unit; listed as the target's menu
aura = unit(4, extra=(cm(rules=[R("Defensive Growth Aura")]),))
assert [m[0] for m in DC.menus(REG, aura, unit(), Ctx())] == [DG]
assert one(unit(), aura, versatile=((DG, 1),)).targets[0].defense_mod == 2
# state: never picked for the target, so the default is no token
ctx, notes = DC.pick(REG, aura, unit(), Ctx(), lambda c: (0, 0))
assert ctx.versatile == () and notes == []

# --- Precision Growth: the attacker's token menu, its holders only ----------
pg = unit(rules=[R("Precision Growth")])
assert [one(pg, unit(), "Hand Weapon", versatile=v, **MELEE).spec.hit_mod
        for v in ((), ((PG, 0),), ((PG, 1),))] == [0, 1, 2]
part = unit(1, rules=[R("Precision Growth")], extra=unit(1).models)
hm = sorted(g.spec.hit_mod for g in build_plan(REG, part, unit(), Ctx(
    versatile=((PG, 0),))).groups if g.weapon.name == "Rifle")
assert hm == [0, 1], hm


# --- No Retreat Aura / Buff: a failed test counts as passed -----------
def after(cb):
    al = Allocation.of(cb)
    half = al.wound(al.fresh(), 0, 1)
    for _ in range(len(cb.models) // 2 - 1):
        half = al.wound(half, al.alive(half)[0], 1)
    chain = K.ChainResult(al, al.fresh(), {half: F(1)})
    return MO.after_shooting(MO.Morale(REG, cb, None, Ctx()), chain, True)


base = after(combatant(resolved(unit(4))))
assert (base.shaken, base.held) == (F(1, 2), 0)
nra = after(combatant(resolved(unit(3, extra=(
    cm(rules=[R("No Retreat Aura")]),)))))
assert (nra.shaken, nra.held) == (0, F(1, 2))
grants = SP.rule_buff_grants(REG, IDS["No Retreat Buff"])
assert [g[0].id for g in grants] == [IDS["No Retreat"]]
buffed = SP.grant(resolved(unit(4)), grants, "shooting")
nrb = after(combatant(buffed))
assert (nrb.shaken, nrb.held) == (0, F(1, 2))
assert nrb.self_wounds == [F(5, 8), F(1, 4), F(1, 8)]   # 2 dice, 1-3
# the buff never gives No Retreat to its own holder
own = after(combatant(resolved(unit(4, rules=[R("No Retreat Buff")]))))
assert own.held == 0

# --- the Enhanced auras grant their Enhanced rule to the unit ---------------
for aura_name, rule in (("Enhanced Hold the Line Aura", "Enhanced Valiant"),
                        ("Enhanced Infected Aura", "Enhanced Violent")):
    u = unit(4, extra=(cm(rules=[R(aura_name)]),))
    v = E.View(REG, Ctx(), "defender", u, (), u, ())
    holds, missing = E.holdings(REG, v)
    assert not missing and all(any(h.sem.name == rule for h in hs)
                               for hs in holds), aura_name
ehl = unit(4, rules=[R("Valiant")], extra=(
    cm(rules=[R("Valiant"), R("Enhanced Hold the Line Aura")]),))
m = MO.Morale(REG, ehl, None, Ctx(distance=6))
assert m.numbers(m.alloc.fresh(), "shooting")[1] == 1           # lifted

# --- Coordinate: nothing in an attack ---------------------------------------
co = unit(rules=[R("Coordinate")])
p, q = build_plan(REG, co, co, Ctx()), build_plan(REG, unit(), unit(), Ctx())
assert [x.spec for x in p.groups] == [x.spec for x in q.groups]
assert not p.warnings, p.warnings

# --- the real books ----------------------------------------------------------
if not testpaths.USING_SYNTHETIC:
    import os
    import subprocess
    import sys
    from grimdarkoracle.app.library import Library
    from grimdarkoracle.data.af_book import RuleRef
    from grimdarkoracle.data.resolve import resolve
    from grimdarkoracle.rules import spells as RS
    tool = os.path.join(testpaths.REPO_ROOT, "tools", "rules_report.py")
    r = subprocess.run([sys.executable, tool, "--data", testpaths.DATA_DIR,
                        "--only", *GROUP], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-1500:]
    lib = Library.load(testpaths.DATA_DIR)
    reg = lib.reg
    sreg = RS.SpellRegistry(RS.load(), reg, list(lib.books.values()))
    bk = {b.name: b for b in lib.books.values()}

    def rules(*names, n=5):
        refs = [RuleRef(next(r for r, d in reg.defs.items() if d.name == x),
                        x, None, x) for x in names]
        return unit(n, rules=refs)

    def spell(book, name):
        b = bk[book]
        return sreg.lookup(b, next(s for s in b.spells
                                   if s.name.strip() == name))

    # the book names: Hold the Line (Valiant), Infected (Violent)
    hl = rules("Hold the Line", "Enhanced Hold the Line Aura")
    m = MO.Morale(reg, hl, None, Ctx(distance=6))
    assert m.numbers(m.alloc.fresh(), "shooting")[1] == 1
    m = MO.Morale(reg, rules("Hold the Line"), None, Ctx(distance=6))
    assert m.numbers(m.alloc.fresh(), "shooting")[1] == 0
    inf = rules("Infected", "Enhanced Infected Aura")
    g = [x for x in build_plan(reg, inf, unit(), Ctx(distance=6)).groups
         if x.weapon.name == "Rifle"]
    assert g and g[0].spec.shred == 1
    g = [x for x in build_plan(reg, rules("Infected"), unit(),
                               Ctx(distance=6)).groups
         if x.weapon.name == "Rifle"]
    assert g and g[0].spec.shred == 0
    # a real Quick Throw unit shoots its Indirect weapon unseen after Advance
    hi = bk["Human Inquisition"]
    qid = IDS["Quick Throw"]
    ru = next(x for x in (resolve(hi, k, ()) for k in hi.units)
              if any(r.id == qid for m in x.models for r in m.rules))
    plan = build_plan(reg, combatant(ru), unit(), Ctx(
        action="advance", line_of_sight=False, distance=6))
    assert plan.groups and all(any(
        reg.lookup(r.id, r.name) and reg.lookup(r.id, r.name).handler
        == "indirect" for r in g.weapon.rules) for g in plan.groups)

    # spells: grants, debuff, mark and the copies of mapped damage spells
    co = spell("Human Inquisition", "Psy-Injected Courage")
    brave = SP.grant(resolved(unit(4)), co.grants, "spell")
    m = MO.Morale(reg, combatant(brave), None, Ctx(attack="spell"))
    assert m.numbers(m.alloc.fresh(), "spell")[1] == 1
    co = spell("Human Defense Force", "Psy-Injected Courage")
    assert [x[0].name for x in co.grants] == ["Enhanced Hold the Line"]
    bi = spell("Infected Colonies", "Brain Infestation")
    assert bi.kind == "debuff"
    weak = combatant(SP.grant(resolved(unit()), bi.grants, "shooting"))
    assert [x.spec.hit_mod for x in build_plan(reg, weak, unit(), Ctx(
        distance=12)).groups] == [-1]
    cf = spell("Human Defense Force", "Calculated Foresight")
    g = [x for x in build_plan(reg, unit(), unit(), Ctx(
        distance=12, marks=(cf.mark_id,))).groups]
    assert [x.spec.extra_hits_on_6 for x in g] == [1]
    g = [x for x in build_plan(reg, unit(), unit(), Ctx(
        distance=6, marks=(cf.mark_id,))).groups]
    assert [x.spec.extra_hits_on_6 for x in g] == [0]
    doc = RS.load()["spells"]

    def body(key):
        return {k: v for k, v in doc[key].items()
                if k not in ("name", "text_sha1", "note")}

    def key(book, name):
        return RS.spell_key(next(s for s in bk[book].spells
                                 if s.name.strip() == name))

    pairs = ((("Human Defense Force", "Searing Burst"),
              ("Dark Elf Raiders", "Holistic Suffering")),
             (("Human Inquisition", "Searing Burst"),
              ("Dark Elf Raiders", "Holistic Suffering")),
             (("Human Defense Force", "Electric Tempest"),
              ("High Elf Fleets", "Shattering Curse")),
             (("Human Inquisition", "Electric Tempest"),
              ("Wolf Brothers", "Storm of Power")))
    for new, old in pairs:
        assert body(key(*new)) == body(key(*old)), (new, old)
    vi = spell("Infected Colonies", "Volatile Infection")
    assert (vi.hits, [x.label for x in vi.rules]) == (2, ["AP(2)",
                                                          "Deadly(3)"])
    bh = spell("Infected Colonies", "Bio-Horror")
    assert (bh.hits, bh.roll_sixes) == (6, True)

print("test_group5 OK")
