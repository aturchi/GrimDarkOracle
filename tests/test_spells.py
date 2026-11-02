"""Spells: rules.spells (keys, validation, status, lookup, mark
entries), app.spells (casting law, damage plan, grants, buff menu),
analyzer_core spell analyses (closed forms in Fractions, morale without
Banner), side_spec.run with spells and buffs. Synthetic book + fixture;
real DAO / BB spells with --real_data."""
from dataclasses import replace
from fractions import Fraction as F

from unitkit import IDS, R, REG, W, CORE, unit, ctx, resolved
import testpaths
from grimdarkoracle.app import spells as SP
from grimdarkoracle.app import result_rows as RR
from grimdarkoracle.app.analyzer_core import Options, Side, analyse
from grimdarkoracle.app.setup_model import Setup, SideSetup
from grimdarkoracle.app import side_spec as SS
from grimdarkoracle.data import af_book as ab
from grimdarkoracle.engine import pmf as P
from grimdarkoracle.rules import registry, spells as S

book = ab.load_book(testpaths.book_path("synthetic00book01",
                                        testpaths.SYNTHETIC_DIR))
bolt, ward = book.spells
mark_spell = ab.Spell("sp3", "Hex", 1, "Synthetic: enemy marked, AP(1).")
book = replace(book, spells=book.spells + (mark_spell,))
K = {s.name: S.spell_key(s) for s in book.spells}
assert K["Bolt"].startswith("sp1:") and len(K["Bolt"]) == 14
DOC = {"format": S.FORMAT, "spells": {
    K["Bolt"]: {"name": "Bolt", "kind": "damage", "hits": 2, "range": 12,
                "rules": [["AP", 1]]},
    K["Ward"]: {"name": "Ward", "kind": "grant",
                "grants": [{"rule": "Fearless"},
                           {"rule": "Shred", "to": "weapons",
                            "attack": "shooting"}]},
    K["Hex"]: {"name": "Hex", "kind": "mark", "conditions": {"attack":
                                                            "shooting"},
               "effects": [{"primitive": "ap_mod", "value": 1}]}}}
assert S.validate(DOC) == []
bad = {"format": S.FORMAT, "spells": {
    "a": {"kind": "boom"}, "b": {"kind": "damage", "hits": 0},
    "c": {"kind": "grant", "grants": [{"rule": "X", "to": "feet"}]},
    "d": {"kind": "mark"}}}
errs = " | ".join(S.validate(bad))
for needle in ("unknown kind", "positive integer", "'range' must",
               "models or weapons", "needs effects"):
    assert needle in errs, needle
assert S.validate({"format": "x"})
assert S.validate(S.load()) == []                     # shipped file

reg = registry.RuleRegistry(registry.load_semantics(), CORE, [book])
sreg = S.SpellRegistry(DOC, reg, [book])
assert [s.name for s in sreg.spells(book)] == ["Bolt", "Ward", "Hex"]
b = sreg.lookup(book, bolt)
assert (b.kind, b.hits, b.range, b.threshold) == ("damage", 2, 12, 1)
assert b.rules[0].id == IDS["AP"] and b.rules[0].label == "AP(1)"
w = sreg.lookup(book, ward)
assert [(r.name, to, a) for r, to, a in w.grants] == [
    ("Fearless", "models", None), ("Shred", "weapons", "shooting")]
assert reg.lookup("spell:" + K["Hex"]).handler == "mark"
changed = replace(bolt, effect="Synthetic: target takes 3 hits.")
other = ab.Spell("zz9", "New", 1, "Unknown.")
assert [sreg.status(book, s) for s in (bolt, changed, other)] == \
    ["ok", "unmapped", "unmapped"]      # mapped text still there: a variant
book2 = replace(book, spells=tuple(changed if s is bolt else s
                                   for s in book.spells))
sreg2 = S.SpellRegistry(DOC, reg, [book2])
assert sreg2.status(book2, changed) == "changed"        # the text changed
sub = replace(book, uid="sub", name="Sub", spells=(changed,))
assert sreg.status(sub, changed) == "unmapped"          # sub-faction variant
assert sreg2.status(sub, changed) == "changed"
assert sreg2.status(book, changed) == "unmapped"        # this book has both
broken = S.SpellRegistry({"format": S.FORMAT, "spells": {K["Bolt"]: dict(
    DOC["spells"][K["Bolt"]], rules=[["Nope", None]])}}, reg, [book])
assert broken.status(book, bolt) == "broken" and broken.spells(book) == []
assert sreg.coverage([book])[0] == ("Synthetic Legion", "Bolt", "ok")

# --- casting law -----------------------------------------------------------------
plain = resolved(unit(1))
amp = resolved(unit(1, rules=[R("Caster", 2), R("Spell Amplifier")]))
assert SP.caster_rating(REG, plain) == 0 and SP.caster_rating(REG, amp) == 2
assert SP.cast_mod(REG, amp) == 1
assert SP.cast_prob(REG, plain, exact=True) == F(1, 2)
assert SP.cast_prob(REG, amp, exact=True) == F(2, 3)
assert SP.cast_prob(REG, amp, None, 4, 0, exact=True) == F(5, 6)    # 1 fails
assert SP.cast_prob(REG, plain, None, 0, 9, exact=True) == F(1, 6)  # 6 wins
hero = resolved(unit(1, rules=[R("Caster", 3)]))
assert SP.caster_rating(REG, plain, hero) == 3
assert SP.caster_rating(REG, amp, hero) == 3                # highest
two_amp = resolved(unit(2, rules=[R("Caster", 1), R("Spell Amplifier")]))
assert SP.cast_mod(REG, two_amp, amp) == 1                  # once per rule
plan = SP.plan(b, REG, amp, exact=True)
assert plan.p_cast == F(2, 3) and plan.weapon.attacks == 2 and \
    plan.weapon.range == 12
try:
    SP.plan(w, REG, amp)
    raise AssertionError("grant spell planned as damage")
except ValueError:
    pass

# --- spell analysis: fixed hits, mixture with the cast ----------------------
SPELL = ctx(attack="spell")
tgt = Side(resolved(unit(5), 100, "T"))
a = analyse(REG, Side(amp), tgt,
            Options(ctx=SPELL, spell=plan, exact=True))
row = a.rows[0]
assert (row.phase, row.attacks, row.hits) == ("spell", 2, P.delta(2))
hit = P.binomial(2, F(2, 3))                   # AP(1) vs D4: blocks on 5+
assert row.wounds == hit and a.cast == F(2, 3)
assert a.def_losses.wounds == [F(1, 3) + F(2, 3) * hit[0]] + \
    [F(2, 3) * p for p in hit[1:]]
assert RR.outcome_lines(a)[0] == ("Spell cast (weapon row: if cast)", "66.7 %")
assert RR.table(a)[0].name == "Spell: Bolt"
# No cover against spells, no range limit, the caster's rules ignored.
cov = analyse(REG, Side(resolved(unit(1, rules=[R("Good Shot")]))), tgt,
              Options(ctx=ctx(attack="spell", cover="terrain", distance=40),
                      spell=SP.SpellPlan("Bolt", plan.weapon, 1),
                      exact=True))
assert cov.rows[0].wounds == hit
# Morale after a spell: Banner does not help (shooting / melee only).
ban = Side(resolved(unit(2, (W("Gun", 24, 1),), rules=[R("Banner")])))
big = SP.SpellPlan("Big", W("Big", 12, 6, R("AP", 4)), 1)
ms = analyse(REG, Side(amp), ban, Options(ctx=SPELL, spell=big, exact=True))
p_one = ms.def_losses.killed[1]                  # one of two dead: test
assert ms.def_losses.morale.test == p_one and \
    ms.def_losses.morale.shaken == p_one / 2     # Q4, no +1
for bad_opts in ({"ctx": SPELL}, {"spell": plan}):
    try:
        Options(**bad_opts)
        raise AssertionError(f"{bad_opts} accepted")
    except ValueError:
        pass

# --- grants and buffs --------------------------------------------------------------
gun = W("Gun", 24, 1)
u = resolved(unit(2, (gun,)))
g = SP.grant(u, w.grants, "shooting")
assert [r.name for r in g.models[0].rules] == ["Fearless"]
assert [r.name for r in g.models[0].weapons[0][0].rules] == ["Shred"]
g2 = SP.grant(u, w.grants, "melee")
assert g2.models[0].weapons[0][0] == gun                 # shooting only
assert SP.grant(g, w.grants, "shooting") == g            # no duplicates
assert SP.grant(None, w.grants, "shooting") is None
fm = ((R("Fearless"), "models", "melee"),)
assert SP.grant(u, fm, "shooting") == u and \
    SP.grant(u, fm, "melee").models[0].rules[-1].name == "Fearless"
refs = SP.weapon_grants(w.grants, "shooting")
assert SP.grant_weapon(gun, refs) == g.models[0].weapons[0][0]
menu = SP.buff_menu(sreg, book, book)
assert [(m.side, m.label) for m in menu] == [
    ("att", "Ward (grant)"), ("att", "Hex (mark)"), ("def", "Ward (grant)")]
# Spell marks are offered with the spells, not with the Mark rules.
from grimdarkoracle.app import setup_model as SM  # noqa: E402
assert ("spell:" + K["Hex"], "Hex") not in SM.marks(reg) and SM.marks(reg)
# A grant that only adds shooting weapon rules is not offered to the target.
ammo = dict(DOC["spells"][K["Ward"]], grants=[
    {"rule": "Shred", "to": "weapons", "attack": "shooting"}])
sreg2 = S.SpellRegistry({"format": S.FORMAT, "spells": {K["Ward"]: ammo}},
                        reg, [book])
assert [(m.side, m.key) for m in SP.buff_menu(sreg2, book, book)] == \
    [("att", K["Ward"])]

# side_spec.run: spell analysis, buffs, a switched-off weapon stays off.
from grimdarkoracle.app.unit_config import UnitConfig  # noqa: E402
side = SS.SideSpec(SS.UnitSpec(UnitConfig(book, "uTroop1")))
foe = SS.SideSpec(SS.UnitSpec(UnitConfig(book, "uTroop1")))
base = SS.run(reg, side, SideSetup(), foe, SideSetup(), Setup(), sreg,
              exact=True)
hexed = SS.run(reg, side, SideSetup(), foe, SideSetup(),
               Setup(buffs=(("att", K["Hex"]),)), sreg, exact=True)
assert P.mean(hexed.def_losses.wounds) > P.mean(base.def_losses.wounds)
rifle = next(x for x, _n in side.resolved()[0].weapons() if x.name == "Rifle")
off = SideSetup(off=frozenset({rifle}))
warded = SS.run(reg, side, off, foe, SideSetup(),
                Setup(buffs=(("att", K["Ward"]),)), sreg)
assert "Rifle" not in [r.name for r in warded.rows]       # still off
assert all(any(x.name == "Shred" for x in r.weapon.rules)
           for r in warded.rows if r.weapon.range)
sp = SS.run(reg, side, SideSetup(), foe, SideSetup(),
            Setup(attack="spell", spell=K["Bolt"], friendly_tokens=1), sreg,
            exact=True)
assert sp.kind == "spell" and sp.cast == F(2, 3)          # 4+ with +1
def_mark = SS.run(reg, side, SideSetup(), foe, SideSetup(),
                  Setup(buffs=(("def", K["Hex"]),)), sreg, exact=True)
assert def_mark.def_losses.wounds == base.def_losses.wounds  # not a target mark
nope = SS.run(reg, side, SideSetup(), foe, SideSetup(),
              Setup(buffs=(("def", "zz:0"),)), sreg)
assert any("zz:0" in x for x in nope.warnings)
for setup in (Setup(attack="spell", spell=K["Ward"]),
              Setup(attack="spell", spell=None)):
    try:
        SS.run(reg, side, SideSetup(), foe, SideSetup(), setup, sreg)
        raise AssertionError("bad spell accepted")
    except ValueError:
        pass
try:
    SS.run(reg, side, SideSetup(), foe, SideSetup(),
           Setup(attack="spell", spell=K["Bolt"]))           # no sreg
    raise AssertionError("spell without semantics accepted")
except ValueError:
    pass

# --- real data: every DAO / BB spell maps and resolves --------------------------------
if not testpaths.USING_SYNTHETIC:
    from grimdarkoracle.app.library import Library
    lib = Library.load(testpaths.DATA_DIR)
    for uid in ("z8205ez2boggzs22", "78qp9l5alslt6yj8"):
        rb = lib.books[uid]
        assert [st for _b, _s, st in lib.sreg.coverage([rb])] == ["ok"] * 6
        kinds = [s.kind for s in lib.sreg.spells(rb)]
        assert kinds.count("damage") == 3, kinds
    kb = next(s for s in lib.sreg.spells(lib.books["z8205ez2boggzs22"])
              if s.name == "Killing Blow")
    assert kb.rules[0].id == "17crjK7P6_w6"         # core AP, as weapons
    print("spells: DAO / BB coverage ok")
print("spells: OK")
