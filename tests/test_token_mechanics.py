"""Hazardous (AP(4) and the
attacker's self-inflicted wounds as an Analyzer line), Piercing Spotter
(AP spotter tokens), Vengeance (a Mark with a token count)."""
from fractions import Fraction as F

import testpaths
from grimdarkoracle.app import analyzer_core as AC
from grimdarkoracle.app import result_rows as RR
from grimdarkoracle.app import setup_model as SM
from grimdarkoracle.app.spells import SpellPlan
from grimdarkoracle.engine.context import AttackContext as Ctx
from grimdarkoracle.engine.modifiers import build_plan
from grimdarkoracle.rules import effects as E
from unitkit import IDS, REG, R, W, resolved, unit

for name in ("Hazardous", "Piercing Spotter", "Vengeance"):
    assert REG.lookup(IDS[name], name).impl != "todo", name


def one(att, tgt, weapon, **ctx):
    gs = [g for g in build_plan(REG, att, tgt, Ctx(**ctx)).groups
          if g.weapon.name == weapon]
    assert len(gs) == 1, gs
    return gs[0]


# --- Hazardous: AP(4); 1 wound per unmodified 1, X with Blast / Deadly -------
hz = unit(1, weapons=(W("Zapper", 24, 3, R("Hazardous")),))
g = one(hz, unit(), "Zapper")
assert (g.spec.ap, g.spec.self_wounds_on_1) == (4, 1)
bz = unit(1, weapons=(W("Boomer", 24, 1, R("Hazardous"), R("Blast", 3)),))
assert one(bz, unit(), "Boomer").spec.self_wounds_on_1 == 3
dz = unit(1, weapons=(W("Ripper", 0, 2, R("Hazardous"), R("Deadly", 2)),))
assert one(dz, unit(), "Ripper", attack="melee",
           action="charge").spec.self_wounds_on_1 == 2
assert one(unit(), unit(), "Rifle").spec.self_wounds_on_1 == 0


def analysis(att, ctx=Ctx(), **kw):
    return AC.analyse(REG, AC.Side(resolved(att)), AC.Side(resolved(unit(5))),
                      AC.Options(ctx=ctx, exact=True, **kw))


a = analysis(hz)                        # 3 attacks: Binomial(3, 1/6)
assert a.hazard == [F(125, 216), F(75, 216), F(15, 216), F(1, 216)]
lines = dict(RR.outcome_lines(a))
assert lines["Hazardous: wounds the attacker takes (mean)"] == "0.50"
b = analysis(bz)                        # 1 attack, 3 wounds on a 1
assert b.hazard == [F(5, 6), 0, 0, F(1, 6)]
assert analysis(unit(1)).hazard == []
assert "Hazardous: P(at least one)" not in dict(RR.outcome_lines(
    analysis(unit(1))))
m = analysis(dz, Ctx("melee", action="charge"))
assert m.hazard == [F(25, 36), 0, F(10, 36), 0, F(1, 36)]
# fixed hits: only a spell rolling its dice (Pow!)
def pow_hazard(sixes):
    plan = SpellPlan("Pow", W("Pow", 18, 6, R("Hazardous")), F(1), sixes)
    return analysis(unit(1), Ctx(attack="spell"), spell=plan).hazard


assert pow_hazard(False) == []
law = pow_hazard(True)                  # Binomial(6, 1/6)
assert len(law) == 7 and law[0] == F(5, 6) ** 6 and law[6] == F(1, 6) ** 6

# --- Piercing Spotter: +AP(1) per AP spotter token ---------------------------
assert one(unit(), unit(), "Rifle", ap_spotter_tokens=2).spec.ap == 2
assert one(unit(), unit(), "Rifle", spotter_tokens=2).spec.ap == 0
assert SM.Setup(ap_spotter_tokens=3).context().ap_spotter_tokens == 3
assert SM.Setup(attack="melee", ap_spotter_tokens=1).context() \
    .ap_spotter_tokens == 1

# --- Vengeance: one Mark toggle per token count, +X to hit -------------------
V = IDS["Vengeance"]
assert E.mark_parts(f"{V}*2") == (V, 2) and E.mark_parts(V) == (V, None)
menu = [m for m in SM.marks(REG) if m[0].startswith(V)]
assert menu == [(f"{V}*1", "Vengeance (1 token)"),
                (f"{V}*2", "Vengeance (2 tokens)")]
assert [one(unit(), unit(), "Rifle", marks=(f"{V}*{k}",)).spec.hit_mod
        for k in (1, 2)] == [1, 2]
assert one(unit(), unit(), "Hand Weapon", attack="melee", action="charge",
           marks=(f"{V}*1",)).spec.hit_mod == 1

# --- the real books ----------------------------------------------------------
if not testpaths.USING_SYNTHETIC:
    import os
    import subprocess
    import sys
    tool = os.path.join(testpaths.REPO_ROOT, "tools", "rules_report.py")
    for book in ("Eternal Dynasty", "Goblin Reclaimers", "High Elf Fleets"):
        r = subprocess.run([sys.executable, tool, "--data",
                            testpaths.DATA_DIR, "--only", book],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stdout[-800:]

print("test_token_mechanics OK")
