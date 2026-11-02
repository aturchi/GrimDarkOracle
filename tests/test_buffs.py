"""buff rules (Regeneration Buff, Stealth Buff), Precision Target
(a Mark never used up), and the fix of a Mark's grant leaking to its own
holder."""
import testpaths                                    # noqa: F401 (sys.path)
from grimdarkoracle.app import setup_model as S
from grimdarkoracle.app import spells as SP
from grimdarkoracle.engine.context import AttackContext as Ctx
from grimdarkoracle.engine.modifiers import build_plan
from unitkit import IDS, REG, R, resolved, unit

PT, UM = IDS["Precision Target"], IDS["Unstoppable Mark"]
RB, SB = IDS["Regeneration Buff"], IDS["Stealth Buff"]


def first(att, tgt, **ctx):
    return build_plan(REG, att, tgt, Ctx(**ctx)).groups[0]


# --- a Mark's grant goes on the marked unit only (a fixed bug) ---------------
regen = unit(rules=[R("Regeneration")])
assert not first(unit(rules=[R("Unstoppable Mark")]), regen).spec.ignores_regen
assert first(unit(), regen, marks=(UM,)).spec.ignores_regen
assert not first(unit(rules=[R("Regeneration Buff")]), unit()).target \
    .regeneration                                     # nor a buff's

# --- Precision Target: +1 to hit for every friendly attack -------------------
assert (PT, "Precision Target") in S.marks(REG)
assert first(unit(), unit(), marks=(PT,)).spec.hit_mod == 1
m = build_plan(REG, unit(), unit(), Ctx("melee", action="charge",
                                        marks=(PT,))).groups[0]
assert m.spec.hit_mod == 1

# --- buff rules: the grants, the Analyzer toggle ---------------------------------
gr = SP.rule_buff_grants(REG, RB)
assert [(r.name, to, a) for r, to, a in gr] == [("Regeneration", "models",
                                                 None)]
assert SP.rule_buff_grants(REG, PT) == []             # not a buff
buffed = SP.grant(resolved(unit()), gr, "shooting")
assert all(any(r.name == "Regeneration" for r in m.rules)
           for m in buffed.models)

print("test_buffs OK")
