"""Unstoppable drops the negative modifiers of the debuffs an ENEMY
gave; the "+1 to
Morale Test rolls once" spells are a source of their own, added to Bravery
Aura."""
from fractions import Fraction as F

import testpaths
from grimdarkoracle.app import analyzer_core as AC
from grimdarkoracle.app import side_spec as SS
from grimdarkoracle.app import spells as SP
from grimdarkoracle.app.defense_choice import mean
from grimdarkoracle.app.setup_model import Setup
from grimdarkoracle.engine import morale as MO
from grimdarkoracle.engine.context import AttackContext as Ctx
from grimdarkoracle.engine.context import combatant
from grimdarkoracle.engine.modifiers import build_plan
from grimdarkoracle.rules import effects as E
from unitkit import IDS, REG, R, W, cm, resolved, unit

UNS = W("Lance", 24, 1, R("AP", 1), R("Unstoppable"))
GUN = W("Gun", 24, 1, R("AP", 1))


class _Sreg:                        # what _buffs reads for buff RULES
    reg = REG


def debuffed(rule, *weapons):
    """A unit of 'weapons' with the enemy's debuff rule on it, through the
    Analyzer's toggle (the target's book puts it on the attacker)."""
    notes = []
    _m, g_att, _g = SS._buffs(_Sreg(), Setup(buffs=(
        ("def", SP.RULE_BUFF + IDS[rule]),)), {"att": None, "def": None},
        notes)
    assert not notes and g_att and all(r.foreign for r, _to, _a in g_att)
    return combatant(SP.grant(resolved(unit(1, weapons=weapons)), g_att,
                              "shooting"))


def spec(att, weapon):
    gs = [g for g in build_plan(REG, att, unit(), Ctx()).groups
          if g.weapon.name == weapon]
    assert len(gs) == 1, gs
    return gs[0].spec


# --- Unstoppable and the enemy's debuffs ---- --------------------------
pd = debuffed("Precision Debuff", UNS, GUN)
assert spec(pd, "Gun").hit_mod == -1 and spec(pd, "Lance").hit_mod == 0
pi = debuffed("Piercing Debuff", UNS, GUN)
assert spec(pi, "Gun").ap == 0 and spec(pi, "Lance").ap == 1
# the model's OWN negative rule stays (not foreign)
own = unit(1, weapons=(UNS,), rules=[R("Imprecise")])
assert spec(own, "Lance").hit_mod == -1
# a buff of its own side is not foreign
ok = SS._buffs(_Sreg(), Setup(buffs=(("att", SP.RULE_BUFF + IDS[
    "Precision Attacks Buff"]),)), {"att": None, "def": None}, [])[1]
assert ok and not any(r.foreign for r, _to, _a in ok)
# closed form: Q4+ vs Defense 4+, AP(1): 1/2 x 2/3; debuffed -1: 1/3 x 2/3
uns_side = AC.Side(resolved(unit(1, weapons=(UNS,))))
assert mean(AC.analyse(REG, AC.Side(resolved(pd), None), AC.Side(resolved(
    unit(1))), AC.Options(exact=True)).def_losses.killed) == \
    1 - F(2, 3) * F(7, 9)           # one model: Lance 1/3, Gun 1/3 x 2/3
assert mean(AC.analyse(REG, uns_side, AC.Side(resolved(unit(1))),
                       AC.Options(exact=True)).def_losses.killed) == F(1, 3)
# a rule granted by a foreign rule is foreign too (holdings)
fr = unit(2, rules=[E.RuleRef(IDS["Enhanced Infected Aura"],
                             "Enhanced Infected Aura", foreign=True)])
v = E.View(REG, Ctx(), "attacker", fr, (), unit(), ())
holds, _ = E.holdings(REG, v)
assert all(h.ref.foreign for hs in holds for h in hs)

# --- the real books ----------------------------------------------------------
if not testpaths.USING_SYNTHETIC:
    from grimdarkoracle.app.library import Library
    from grimdarkoracle.rules import spells as RS
    lib = Library.load(testpaths.DATA_DIR)
    reg = lib.reg
    bk = {b.name: b for b in lib.books.values()}
    sreg = RS.SpellRegistry(RS.load(), reg, list(lib.books.values()))

    def spell(book, name):
        b = bk[book]
        return sreg.lookup(b, next(s for s in b.spells
                                   if s.name.strip() == name))

    # the same through a debuff SPELL (Brain Infestation gives Imprecise)
    bi = spell("Infected Colonies", "Brain Infestation")
    _m, g_att, _g = SS._buffs(sreg, Setup(buffs=(("def", bi.key),)), {
        "att": bk["Infected Colonies"], "def": bk["Infected Colonies"]}, [])
    weak = combatant(SP.grant(resolved(unit(1, weapons=(UNS, GUN))), g_att,
                              "shooting"))
    hm = {g.weapon.name: g.spec.hit_mod for g in build_plan(
        reg, weak, unit(), Ctx()).groups}
    assert hm == {"Gun": -1, "Lance": 0}, hm

    # the spell's +1 adds to Bravery Aura's +1
    def morale(cb):
        m = MO.Morale(reg, cb, None, Ctx(attack="spell"))
        return m.numbers(m.alloc.fresh(), "spell")[1]

    aura = unit(4, extra=(cm(rules=[R("Bravery Aura")]),))
    for book, name in (("Human Inquisition", "Psy-Injected Courage"),
                       ("Titan Lords", "Psy-Injected Courage"),
                       ("Rebel Guerrillas", "Aura of Peace")):
        s = spell(book, name)
        assert [x[0].id for x in s.grants] == [IDS["Bravery Buff"]
                                               + "#effect"], name
        both = combatant(SP.grant(resolved(aura), s.grants, "spell"))
        assert morale(both) == 2, name
        alone = combatant(SP.grant(resolved(unit(4)), s.grants, "spell"))
        assert morale(alone) == 1, name
    assert morale(aura) == 1

print("test_review OK")
