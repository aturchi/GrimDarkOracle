"""the four Daemons books: Defensive Frenzy and
Fortified Growth as the target's token menus (Versatile param `state`:
never picked for the target, none = no token), two auras, three rules with
no combat effect, and the books' acceptance on the real data."""
import testpaths
from grimdarkoracle.app import analyzer_core as AC
from grimdarkoracle.app import defense_choice as DC
from grimdarkoracle.engine import gf_math as G
from grimdarkoracle.engine.context import AttackContext as Ctx
from grimdarkoracle.engine.context import combatant
from grimdarkoracle.engine.modifiers import build_plan
from grimdarkoracle.rules import effects as E
from unitkit import IDS, REG, R, W, cm, resolved, unit

DAEMONS = ("Daemons of Change", "Daemons of Lust", "Daemons of Plague",
           "Daemons of War")
DF, FG = IDS["Defensive Frenzy"], IDS["Fortified Growth"]


def one(att, tgt, weapon="Rifle", **ctx):
    gs = [g for g in build_plan(REG, att, tgt, Ctx(**ctx)).groups
          if g.weapon.name == weapon]
    assert len(gs) == 1, gs
    return gs[0]


for name in ("Defensive Frenzy", "Fortified Growth", "Hit & Run Fighter Aura",
             "Screened Aura", "Quick Shot Mark", "Spell Accumulator", "Split"):
    sem = REG.lookup(IDS[name], name)
    assert sem is not None and sem.impl != "todo", name

# --- Defensive Frenzy: +1 Defense per token (the target's state) ------------
dfu = unit(rules=[R("Defensive Frenzy")])
assert [one(unit(), dfu, versatile=v).targets[0].defense_mod
        for v in ((), ((DF, 0),), ((DF, 1),))] == [0, 1, 2]
few = unit(2, rules=[R("Defensive Frenzy")], extra=unit(3).models)
assert one(unit(), few, versatile=((DF, 1),)).targets[0].defense_mod == 0

# --- Fortified Growth: AP(-1) per two tokens, never below AP(0) --------------
gun = unit(weapons=(W("Gun", 24, 1, R("AP", 3)),))
fgu = unit(rules=[R("Fortified Growth")])
assert [one(gun, fgu, "Gun", versatile=v).spec.ap
        for v in ((), ((FG, 0),), ((FG, 1),))] == [3, 2, 1]
g = one(unit(), fgu, versatile=((FG, 1),))
assert G.effective_ap(g.spec, False) == 0
ugun = unit(weapons=(W("Gun", 24, 1, R("AP", 3), R("Unstoppable")),))
assert one(ugun, fgu, "Gun", versatile=((FG, 1),)).spec.ap == 3

# --- state menus are listed for the user, never picked for the target --------
vd = unit(rules=[R("Defensive Frenzy"), R("Versatile Defense")])
cb, att, ctx = combatant(resolved(vd)), combatant(resolved(unit())), Ctx()
assert {m[0] for m in DC.menus(REG, cb, att, ctx)} == {
    DF, IDS["Versatile Defense"]}
assert DC.is_state(REG, DF) and DC.is_state(REG, FG)
assert not DC.is_state(REG, IDS["Versatile Defense"])
picked, notes = DC.pick(REG, cb, att, ctx, lambda c: (0, 0))
assert [r for r, _k in picked.versatile] == [IDS["Versatile Defense"]]
alone = combatant(resolved(dfu))
assert DC.pick(REG, alone, att, ctx, lambda c: (0, 0)) == (ctx, [])


# through the Analyzer: no tokens = the plain target; tokens = fewer losses
def losses(tgt, versatile=()):
    a = AC.analyse(REG, AC.Side(resolved(unit(10))), AC.Side(resolved(tgt)),
                   AC.Options(ctx=Ctx(versatile=versatile), exact=True))
    return sum(k * p for k, p in enumerate(a.def_losses.wounds))


plain = unit(5)
assert losses(dfu) == losses(plain)
assert losses(dfu, ((DF, 1),)) < losses(dfu, ((DF, 0),)) < losses(plain)

# --- auras and no combat effect ----------------------------------------------
for aura, rule in (("Hit & Run Fighter Aura", "Hit & Run Fighter"),
                   ("Screened Aura", "Screened")):
    u = unit(4, extra=(cm(rules=[R(aura)]),))
    v = E.View(REG, Ctx(), "defender", u, (), u, ())
    holds, missing = E.holdings(REG, v)
    assert not missing and all(any(h.sem.name == rule for h in hs)
                               for hs in holds), aura
sa = unit(4, extra=(cm(rules=[R("Screened Aura")]),))
assert one(unit(), sa, distance=12).spec.hit_mod == -1
for name in ("Quick Shot Mark", "Spell Accumulator", "Split"):
    u = unit(rules=[R(name)])
    for a, t in ((u, unit()), (unit(), u)):
        p, q = build_plan(REG, a, t, Ctx()), build_plan(REG, unit(), unit(),
                                                        Ctx())
        assert [x.spec for x in p.groups] == [x.spec for x in q.groups], name
        assert not p.warnings, (name, p.warnings)

# --- the real books ----------------------------------------------------------
if not testpaths.USING_SYNTHETIC:
    import os
    import subprocess
    import sys
    from grimdarkoracle.app.library import Library
    from grimdarkoracle.rules import spells as RS
    tool = os.path.join(testpaths.REPO_ROOT, "tools", "rules_report.py")
    r = subprocess.run([sys.executable, tool, "--data", testpaths.DATA_DIR,
                        "--only", *DAEMONS], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-1500:]
    from grimdarkoracle.data.af_book import RuleRef
    lib = Library.load(testpaths.DATA_DIR)
    sreg = RS.SpellRegistry(RS.load(), lib.reg, list(lib.books.values()))
    doc = RS.load()["spells"]

    def body(e):
        return {k: v for k, v in e.items() if k != "text_sha1"}

    for b in (x for x in lib.books.values() if x.name in DAEMONS):
        for sp in b.spells:
            key = RS.spell_key(sp)
            assert sreg.status(b, sp) == "ok", (b.name, sp.name)
            same = [body(x) for k, x in doc.items()
                    if x["name"] == sp.name and k != key]
            assert body(doc[key]) in same, sp.name      # copied entry
    war = next(x for x in lib.books.values() if x.name == "Daemons of War")
    ref = RuleRef(DF, "Defensive Frenzy", None, "Defensive Frenzy")
    assert war.rules[DF].name == "Defensive Frenzy"     # the book's own id
    tgt = AC.Side(resolved(unit(5, rules=[ref])))
    a0, a2 = (AC.analyse(lib.reg, AC.Side(resolved(unit(10))), tgt,
                         AC.Options(ctx=Ctx(versatile=v), exact=True))
              for v in ((), ((DF, 1),)))
    assert a2.def_losses.wounds[0] > a0.def_losses.wounds[0]

print("test_daemons OK")
