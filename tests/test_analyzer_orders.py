"""app.analyzer_orders + app.unit_labels: the
attacker's weapon order and the Takedown preferences on the target as
the Analyzer sets them: Info of two sides (book, Hero, Takedown by an
override or by a damage spell), the default, reset when the target's
configuration changes, cleaning, text; the values reaching the analysis
through side_spec.run (shooting, melee charger, spell), the pin context
and the session round trip (old sessions without them). Synthetic data.
"""
import json
import os
import shutil
import tempfile
from dataclasses import replace

import testpaths
from grimdarkoracle.app import analyzer_orders as AO
from grimdarkoracle.app import comparison as C
from grimdarkoracle.app import session_io as SIO
from grimdarkoracle.app import side_spec as SS
from grimdarkoracle.app import unit_labels as UL
from grimdarkoracle.app.library import Library
from grimdarkoracle.app.setup_model import Setup, SideSetup
from grimdarkoracle.app.unit_config import UnitConfig
from grimdarkoracle.engine import pmf as P
from grimdarkoracle.engine.context import combatant
from grimdarkoracle.engine.sequence import AttackSequence
from grimdarkoracle.rules import spells as S

lib = Library.load(testpaths.SYNTHETIC_DIR)
reg = lib.reg
B = "synthetic00book01"
book = lib.books[B]
TD = {"op": "weapon_add_rule", "weapon": "Rifle",
      "rule": {"id": "8Hjy54TYtwb7", "name": "Takedown"}}
CTD = {"op": "weapon_add_rule", "weapon": "Hand Weapon",
       "rule": {"id": "8Hjy54TYtwb7", "name": "Takedown"}}

troops = SS.book_side(book, "uTroop1")
snipers = SS.SideSpec(SS.UnitSpec(UnitConfig(book, "uTroop1"),
                                  overrides=(TD,)))
captain = SS.UnitSpec(UnitConfig(book, "uCapt01"))
target = SS.SideSpec(SS.UnitSpec(UnitConfig(book, "uTroop1")), captain)
SHOOT, MELEE = Setup(distance=12), Setup(attack="melee")

# --- unit_labels ---------------------------------------------------------------------
ru, hero = target.resolved()
labels = UL.model_labels(ru, hero)
assert len(labels) == 11 and labels[-1].startswith("Field Captain: ")
assert "Tough(" in labels[-1] and not labels[0].startswith("Field")
assert UL.weapon_names(ru, hero) == ["Rifle", "Hand Weapon", "Pistol",
                                     "Blade"]
assert not UL.has_takedown(reg, ru, hero)
assert UL.has_takedown(reg, *snipers.resolved())

# --- Info and the default -------------------------------------------------------------
i = AO.info(reg, lib.sreg, snipers, target, SHOOT)
assert i.takedown and i.weapons and i.names == ("Rifle", "Hand Weapon")
assert i.labels == tuple(labels) and i.target == AO.signature(target)
seq = AttackSequence(reg, combatant(*snipers.resolved()[:1]),
                     combatant(ru, hero=hero), SHOOT.context())
assert i.default == seq.takedown_targets and i.default[0] == 10   # Hero
assert not AO.info(reg, lib.sreg, troops, target, SHOOT).takedown
assert not AO.info(reg, lib.sreg, snipers, None, SHOOT).takedown
assert AO.info(reg, lib.sreg, None, None, SHOOT) == AO.Info()
# A spell attack: no weapon order; Takedown only from the chosen spell.
assert not AO.info(reg, lib.sreg, snipers, target,
                   Setup(attack="spell")).weapons
assert not AO.info(reg, lib.sreg, snipers, target,
                   Setup(attack="spell")).takedown

# --- signature, follow, clean ------------------------------------------------------------
assert AO.signature(None) == ""
same = SS.SideSpec(SS.UnitSpec(UnitConfig(book, "uTroop1")),
                   SS.UnitSpec(UnitConfig(book, "uCapt01")))
assert AO.signature(same) == AO.signature(target)           # equal configs
for other in (SS.SideSpec(target.unit), troops,
              SS.SideSpec(replace(target.unit, combined=True), captain),
              SS.SideSpec(replace(target.unit, label="Squad"), captain),
              SS.SideSpec(replace(target.unit, overrides=(TD,)), captain)):
    assert AO.signature(other) != AO.signature(target)
o = AO.Orders(("Hand Weapon", "Gone"), (3, 10))
kept = AO.follow(o, i, i)                                   # same sides
assert kept == AO.Orders(("Hand Weapon",), (3, 10))
assert AO.follow(o, None, i).takedown_targets == ()         # first time
i2 = AO.info(reg, lib.sreg, snipers, SS.SideSpec(target.unit), SHOOT)
assert AO.follow(o, i, i2) == AO.Orders(("Hand Weapon",), ())   # target changed
assert AO.clean(AO.Orders((), (3, 10, 11)), i).takedown_targets == (3, 10)
i3 = AO.info(reg, lib.sreg, troops, target, SHOOT)
assert AO.follow(kept, i, i3) == kept                       # other attacker
assert AO.describe(kept, i) == ("Weapon order: Hand Weapon; "
                                "Takedown: m4 > m11")
assert AO.describe(AO.Orders(), i3) == "Weapon order: book order"
assert AO.describe(AO.Orders(), i).endswith(
    "Takedown: default (removed last first)")

# --- dict round trip, lenient -------------------------------------------------------------
assert AO.Orders.from_dict(kept.to_dict()) == kept
assert AO.Orders.from_dict(None) == AO.Orders.from_dict("x") == AO.Orders()
assert AO.Orders.from_dict({"weapon_order": ["A", 3, "A"],
                            "takedown_targets": [2, -1, True, "4", 2, 0]}) \
    == AO.Orders(("A",), (2, 0))
assert AO.Orders.from_dict({"weapon_order": "A"}) == AO.Orders()

# --- the values reach the analysis (side_spec.run) -----------------------------------------
def killed(spec, setup, orders=AO.Orders(), tgt=target):
    a = SS.run(reg, spec, SideSetup(), tgt, SideSetup(), setup, lib.sreg,
               exact=True, **orders.kw())
    return a, a.def_losses.killed


a0, k0 = killed(snipers, SHOOT)
a1, k1 = killed(snipers, SHOOT, AO.Orders((), (0,)))
assert a1.opts.takedown_targets == (0,) and a0.opts.takedown_targets == ()
assert k1 != k0 and P.mean(k1) > P.mean(k0)   # m1 dies, the Hero did not
w = killed(target, SHOOT, AO.Orders(("Pistol",)), troops)[0]
assert w.opts.weapon_order == ("Pistol",)
assert [r.name for r in w.rows][:1] == ["Pistol"]
# Melee: the charger's preferences and weapon order.
melee_snipers = SS.SideSpec(SS.UnitSpec(UnitConfig(book, "uTroop1"),
                                        overrides=(CTD,)))
m0 = killed(melee_snipers, replace(MELEE, strike_back=False))[1]
m1 = killed(melee_snipers, replace(MELEE, strike_back=False),
            AO.Orders((), (0,)))[1]
assert P.mean(m1) > P.mean(m0)
# Pin context shows the values (two orders compare as different).
sig = C.context_signature(a1)
assert sig.endswith("Takedown m1") and "weapon order" not in sig
assert C.context_signature(w).endswith("weapon order Pistol")

# --- a damage spell with Takedown -----------------------------------------------------
bolt = book.spells[0]
key = S.spell_key(bolt)
sreg = S.SpellRegistry({"format": S.FORMAT, "spells": {key: {
    "name": "Bolt", "kind": "damage", "hits": 1, "range": 12,
    "rules": [["Takedown", None]]}}}, reg, [book])
caster = SS.SideSpec(SS.UnitSpec(UnitConfig(book, "uCapt01")))
sp = Setup(attack="spell", spell=key)
assert AO.spell_takedown(reg, sreg, book, key)
assert not AO.spell_takedown(reg, sreg, book, None)
assert not AO.spell_takedown(reg, None, book, key)
si = AO.info(reg, sreg, caster, target, sp)
assert si.takedown and not si.weapons
s0 = SS.run(reg, caster, SideSetup(), target, SideSetup(), sp, sreg,
            exact=True)
s1 = SS.run(reg, caster, SideSetup(), target, SideSetup(), sp, sreg,
            exact=True, **AO.Orders((), (0,)).kw())
assert P.mean(s1.def_losses.killed) > P.mean(s0.def_losses.killed)

# --- sessions: orders stored, old files load ------------------------------------------------
tmp = tempfile.mkdtemp()
try:
    root = os.path.join(tmp, "af")
    shutil.copytree(testpaths.SYNTHETIC_DIR, root)
    lib2 = Library.load(root)
    b2 = lib2.books[B]
    ses = SIO.Session(SHOOT, {"left": SIO.SideState(
        SS.book_side(b2, "uTroop1"), SideSetup()), "right": None}, False,
        AO.Orders(("Rifle",), (4, 2)))
    path = os.path.join(tmp, "s.json")
    SIO.save(ses, lib2, path)
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    assert doc["orders"] == {"weapon_order": ["Rifle"],
                             "takedown_targets": [4, 2]}
    back, notes = SIO.load(path, lib2)
    assert back.orders == ses.orders and notes == []
    del doc["orders"]                               # an old session
    back, _n = SIO.from_dict(doc, lib2)
    assert back.orders == AO.Orders()
finally:
    shutil.rmtree(tmp)
print("analyzer_orders: OK")
