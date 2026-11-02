"""app.local_editor: text forms in Army Forge label syntax, saved
into a local book with stable uids; removed uids retired."""
import copy

import testpaths
from grimdarkoracle.app import local_editor as LE
from grimdarkoracle.app.library import Library
from grimdarkoracle.data import af_book as ab
from grimdarkoracle.data import local_books as LB
from grimdarkoracle.data.resolve import Choice, resolve

lib = Library.load(testpaths.SYNTHETIC_DIR)
raw = LB.new_book("Drill Hall")
lucky = LB.custom_rule(raw, "Lucky Charm", "As Fearless.")
res = LE.RuleResolver(lib.reg, raw)

# Text forms.
assert LE.split_top("AP(1), Tough(3) , Rending") == ["AP(1)", "Tough(3)",
                                                     "Rending"]
assert res.find("lucky charm") == (lucky["id"], "Lucky Charm")
assert res.find("AP")[0] == "17crjK7P6_w6" and res.find("nope") is None
shadow = LB.new_book("Shadow")
mine = LB.custom_rule(shadow, "Stealth", "Our own Stealth.")
assert LE.RuleResolver(lib.reg, shadow).find("Stealth")[0] == mine["id"]
rules, errs = LE.parse_rules("Fearless, Tough(3), Lucky Charm, Ghost", res)
assert [r["label"] for r in rules] == ["Fearless", "Tough(3)", "Lucky Charm"]
assert errs == ["unknown rule 'Ghost' (create it as a custom rule first)"]
w, errs = LE.parse_weapon('2x Las Rifle (24", A1, AP(1))', res, 5)
assert errs == [] and (w["count"], w["range"], w["attacks"]) == (2, 24, 1)
assert w["label"] == '2x Las Rifle (24", A1, AP(1))'
w, _ = LE.parse_weapon("Knife (A1)", res, 5)
assert (w["count"], w["range"]) == (5, 0)                  # every model
assert LE.parse_weapon('Gun (24")', res)[1] == ["Gun: attacks missing "
                                               "(A1, A2...)"]
assert LE.parse_weapon("just text", res)[0] is None
g, errs = LE.parse_gains('Plasma Gun (24", A1, AP(4)); Tough(3)', res)
assert errs == [] and g[0]["type"] == "ArmyBookWeapon" and \
    g[1] == LB.rule_ref(res.find("Tough")[0], "Tough", 3)
assert LE.parse_quant("up to 2") == (("up to", 2), None)
assert LE.parse_quant("1") == (("exactly", 1), None)
assert LE.parse_quant("All") == (("all",), None)
assert LE.parse_quant("lots")[1]

# A new unit with two sections.
d = LE.UnitDraft("Guard Squad", 5, 5, 5, 60, "Lucky Charm",
                 'Las Rifle (24", A1)\nKnife (A1)', [
                     LE.SectionDraft("Replace one Las Rifle", "replace",
                                     "Las Rifle", affects="1", options=[
                                         LE.OptionDraft(
                                             'Plasma Gun (24", A1, AP(4))',
                                             15)]),
                     LE.SectionDraft("Upgrade with one", "upgrade",
                                     select="1", options=[
                                         LE.OptionDraft("Fearless", 5)])])
before = copy.deepcopy(raw)
bad = copy.deepcopy(d)
bad.sections[0].targets = ""
bad.rules = "Ghost"
uid, errs = LE.save_unit(raw, bad, res)
assert uid is None and len(errs) == 2 and raw == before   # nothing changed
uid, errs = LE.save_unit(raw, d, res)
assert errs == [] and uid == "local-u1"
book = ab.parse_book(raw)
r = resolve(book, uid, [Choice("local-p1", "local-s1", "local-o1"),
                        Choice("local-p1", "local-s2", "local-o2")])
assert r.points == 80 and not r.issues and r.size == 5
assert sorted((w.name, n) for w, n in r.weapons()) == \
    [("Knife", 5), ("Las Rifle", 4), ("Plasma Gun", 1)]
assert LB.check(raw, set(lib.reg.defs)) == []

# Round trip, edit with stable uids, removed uids retired.
d2 = LE.UnitDraft.from_raw(raw, uid)
assert d2.weapons == '5x Las Rifle (24", A1)\n5x Knife (A1)'
assert d2.rules == "Lucky Charm" and d2.sections[0].affects == "1"
assert d2.sections[0].options[0].cost == 15 and d2.uid == uid
d2.sections[0].options[0].cost = 20
del d2.sections[1]
d2.sections.append(LE.SectionDraft("Upgrade with any", "upgrade", options=[
    LE.OptionDraft("Tough(3)", 10)]))
assert LE.save_unit(raw, d2, res) == (uid, [])
p = raw["upgradePackages"][0]
assert [s["uid"] for s in p["sections"]] == ["local-s1", "local-s3"]
assert p["sections"][0]["options"][0]["uid"] == "local-o1"
assert p["sections"][1]["options"][0]["uid"] == "local-o3"
assert set(raw[LB.RETIRED_KEY]) == {"local-s2", "local-o2"}
assert resolve(ab.parse_book(raw), uid, [Choice("local-p1", "local-s2",
                                                "local-o2")]).issues
d3 = LE.UnitDraft.from_raw(raw, uid)
d3.sections = []
LE.save_unit(raw, d3, res)
assert raw["upgradePackages"] == [] and "local-p1" in raw[LB.RETIRED_KEY]
second, _ = LE.save_unit(raw, LE.UnitDraft("Other", weapons="Fist (A2)"), res)
assert second == "local-u2"
LB.remove_unit(raw, second)
third, _ = LE.save_unit(raw, LE.UnitDraft("Third", weapons="Fist (A2)"), res)
assert third == "local-u3"                          # u2 is retired
# Renaming a rule rebuilds the labels that show it (weapons, options).
w, _ = LE.parse_weapon('Gun (24", A1, Lucky Charm)', res)
raw["units"][0]["weapons"].append(w)
LB.rename_rule(raw, lucky["id"], "Charm")
assert raw["units"][0]["weapons"][-1]["label"] == 'Gun (24", A1, Charm)'
assert raw["units"][0]["rules"][0]["label"] == "Charm"
assert LB.rule_used(raw, lucky["id"]) and not LB.rule_used(raw, "zz")
print("local editor: OK")
