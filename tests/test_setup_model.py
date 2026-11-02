"""app.setup_model: Setup -> AttackContext / Options, relevance of
the controls, start wounds placed by the allocation order, token-rule
menus (Marks, Versatile)."""
from unitkit import IDS, R, REG, cm, unit, resolved
from grimdarkoracle.app import setup_model as S
from grimdarkoracle.app.analyzer_core import analyse
from grimdarkoracle.data.resolve import ResolvedUnit

s = S.Setup(distance=18, action="advance", cover="terrain")
c = s.context()
assert (c.attack, c.distance, c.action, c.cover) == ("shooting", 18,
                                                      "advance", "terrain")
m = S.Setup(attack="melee", distance=30, cover="terrain", strike_back=False,
            tie="attacker", marks=("x",), spotter_tokens=2)
mc = m.context()
assert (mc.attack, mc.action, mc.cover) == ("melee", "charge", None)
assert mc.marks == ("x",) and mc.spotter_tokens == 2
o = m.options(exact=True)
assert (o.strike_back, o.tie, o.exact) == (False, "attacker", True)
assert s.relevant("cover") and not s.relevant("tie")
assert m.relevant("tie") and not m.relevant("distance") and m.relevant("marks")
for bad in ({"attack": "psychic"}, {"action": "fly"}, {"tie": "draw"},
            {"cover": "smoke"}):
    try:
        S.Setup(**bad)
        raise AssertionError(f"{bad} accepted")
    except ValueError:
        pass

# Start wounds: allocation order (non-Tough first, Heroes last).
u = resolved(unit(3, extra=(cm(rules=[R("Tough", 3)]),)), 100)
hero = ResolvedUnit("bk", "h", "h", 4, 4, 40, 40,
                    (cm(rules=[R("Hero"), R("Tough", 3)]).model,), (), ())
assert S.max_wounds(u) == 5 and S.max_wounds(u, hero) == 8
side = S.make_side(u, hero, S.SideSetup(wounds_taken=4, fatigued=True))
assert side.wounds == (1, 1, 1, 1, 0) and side.fatigued
assert S.make_side(u, hero, S.SideSetup(wounds_taken=99)).wounds == \
    (1, 1, 1, 3, 2)                                     # one wound left
assert S.make_side(u).wounds is None
a = analyse(REG, S.make_side(u), side, s.options(exact=True))
assert a.def_losses.size == 5

# Token-rule menus.
names = [n for _rid, n in S.marks(REG)]
assert names == sorted(names) and "Piercing Shooting Mark" in names
vu = resolved(unit(2, rules=[R("Versatile Expert")]))
menu = S.versatile(REG, vu)
assert menu == [(IDS["Versatile Expert"], "Versatile Expert",
                 ["AP +1", "+1 to hit"])]
assert S.versatile(REG, resolved(unit(2))) == []
reach = S.versatile(REG, resolved(unit(1, rules=[R("Versatile Reach")])))
assert reach[0][2] == ['+4" range']
um = next(e for e in REG.entries.values() if e.name == "Unstoppable Mark")
assert S.effect_label(um.effects[0], REG).startswith("gains ")
print("setup_model: OK")
