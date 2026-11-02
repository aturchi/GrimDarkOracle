"""ui.setup_panel: SetupPanel <-> Setup round trip, relevance of
the controls, token menus; SidePanel -> SideSetup with weapons off and
wounds capped. Real Tk when a display answers, else tkstub."""
from tkhost import ROOT
from unitkit import IDS, R, REG, W, cm, unit, resolved
from grimdarkoracle.app import setup_model as S
from grimdarkoracle.ui import setup_panel as SP

got = []
p = SP.SetupPanel(ROOT, on_change=got.append)
p.pack()
assert p.get_setup() == S.Setup()
p.set_marks(S.marks(REG))
vu = resolved(unit(2, rules=[R("Versatile Expert")]))
p.set_versatile(S.versatile(REG, vu))
want = S.Setup(distance=20, action="advance", cover="sight_blocker",
               line_of_sight=False, crossing=True,
               marks=(IDS["Piercing Shooting Mark"],), spotter_tokens=2,
               versatile=((IDS["Versatile Expert"], 1),))
p.set_setup(want)
assert p.get_setup() == want
st = lambda n: str(p.w[n].cget("state"))           # noqa: E731
assert st("distance") == "normal" and st("tie") == "disabled"
p.v["attack"].set("melee")
p.v["tie"].set(SP.TIE_LABELS["attacker"])
p._edited()
s = got[-1]
assert s.attack == "melee" and s.tie == "attacker" and s.marks == want.marks
assert st("distance") == "disabled" and st("tie") == "readonly"
assert s.context().action == "charge"
p.v["distance"].set("abc")                          # bad text: default
p.v["spotter_tokens"].set("40")                     # clamped
assert p.get_setup().distance == 12 and p.get_setup().spotter_tokens == 12
p.set_versatile([])                                 # attacker changed
assert p.get_setup().versatile == ()
# the target's Versatile Defense: 'best' first (no choice)
VD = IDS["Versatile Defense"]
p.set_versatile([], [(VD, "Versatile Defense", ["+1 Defense", "-1 to hit"])])
assert p.get_setup().versatile == ()
assert p.versatile_vars[VD][0].get() == "best"
p.set_setup(S.Setup(attack="melee", versatile=((VD, 1),), charge_distance=9,
                    ambushed=True))
s = p.get_setup()
assert s.versatile == ((VD, 1),) and s.charge_distance == 9 and s.ambushed
assert st("charge_distance") == "normal"
p.set_setup(S.Setup())
assert p.versatile_vars[VD][0].get() == "best"
assert st("charge_distance") == "disabled"

side_got = []
sp = SP.SidePanel(ROOT, on_change=side_got.append)
gun = W("Gun", 24, 2)
u = resolved(unit(3, (gun,), extra=(cm((gun,), rules=[R("Tough", 3)]),)))
sp.set_unit(u)
assert sp.get_side() == S.SideSetup()
sp.wounds.set("50")
sp.flags["fatigued"].set(True)
sp.hero_q.set("3+")
sp.weapon_vars[gun].set(False)
sp._edited()
ss = side_got[-1]
assert ss.wounds_taken == S.max_wounds(u) == 5 and ss.fatigued
assert ss.hero_quality == 3 and ss.off == frozenset({gun}) and ss.not_moved
sp.set_unit(resolved(unit(2, (gun,))))              # smaller unit
assert sp.get_side().wounds_taken == 1 and sp.get_side().off == {gun}
# table inputs: near terrain, Feat used (both ways)
sp.flags["terrain"].set(True)
sp.flags["feat"].set(True)
sp._edited()
assert side_got[-1].near_terrain and side_got[-1].feat_used
sp.set_side(S.SideSetup(near_terrain=True))
assert sp.flags["terrain"].get() and not sp.flags["feat"].get()
assert SP.weapon_text(W("Gun", 24, 2, R("AP", 1))) == 'Gun (24", A2, AP(1))'
assert SP.weapon_text(W("Claw", 0, 3)) == "Claw (A3)"
# Spells: damage spell list, tokens, buff toggles kept across refreshes.
from grimdarkoracle.app.spells import Buff                     # noqa: E402
p.set_spells([("k1", "Bolt (1 tok., 2 hits)"), ("k2", "Zap (2 tok., 4 hits)")],
             "Caster(2)")
p.set_buffs([Buff("att", "b1", "Hex (mark)", "mark"),
             Buff("def", "b2", "Ward (grant)", "grant")])
p.v["attack"].set("spell")
p.v["spell"].set("Zap (2 tok., 4 hits)")
p.v["friendly_tokens"].set("2")
p.buff_vars[("def", "b2")].set(True)
p._edited()
sp = got[-1]
assert (sp.attack, sp.spell, sp.friendly_tokens) == ("spell", "k2", 2)
assert sp.buffs == (("def", "b2"),) and sp.context().attack == "spell"
assert st("spell") == "readonly" and st("distance") == "normal"
assert st("tie") == "disabled" and st("cover") == "disabled"
assert p.caster_info.cget("text") == "Caster(2)"
p.set_spells([("k1", "Bolt (1 tok., 2 hits)"),
              ("k2", "Zap (2 tok., 4 hits)")])             # choice kept
p.set_buffs([Buff("def", "b2", "Ward (grant)", "grant")])  # tick kept
assert p.get_setup().spell == "k2" and p.get_setup().buffs == (("def", "b2"),)
p.set_setup(S.Setup())
assert p.get_setup().buffs == () and p.get_setup().attack == "shooting"
p.set_spells([])
assert p.get_setup().spell is None
p.set_setup(S.Setup(ap_spotter_tokens=3, spotter_tokens=1))
assert (p.get_setup().ap_spotter_tokens, p.get_setup().spotter_tokens) == \
    (3, 1)
print("setup_panel: OK")
