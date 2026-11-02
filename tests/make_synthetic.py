#!/usr/bin/env python3
"""Write the synthetic Army Forge data used by the test suite.

OPR data must never be committed, so the tests run on an invented army
book with the SAME schema as Army Forge. It is built to exercise every
section shape found in the 49 official GF 3.6.0 books (22 shapes, see
tools/af_survey.py) and every pitfall af_book handles:

- option.cost null or disagreeing with costs[] (shared package, two units);
- plural and "2x" replace targets; several targets in one section;
- implicit chains (a replace whose target only another option grants),
  in book order and in reverse book order;
- a numeric-string Tough rating gained by one model (weapon team);
- disabledSections (one real uid, one stale uid);
- two sections of one unit with the same label and a shared option label;
- string rating, null weapon range, attacksMultiplier != attacks;
- gains of type weapon, item (rules / weapons) and bare rule;
- a faction rule aliased to a generic rule of the same book;
- stale parentSectionUid and a regenerated section 'id'.

Core rules keep the real Army Forge ids and names (rule ids are global, so
the semantics registry applies to synthetic units too) with placeholder
descriptions instead of OPR's text.

    python3 tests/make_synthetic.py      # rewrites tests/synthetic/
"""
import json
import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "synthetic")
BOOK_UID = "synthetic00book01"

CORE = {  # name -> real Army Forge rule id
    "Aircraft": "3FeiOe3krHMa", "Ambush": "6mJw5IdqSqNC",
    "AP": "17crjK7P6_w6", "Artillery": "GRuFoZiyjY5f",
    "Assault": "FF5ddXgx75lI", "Bane": "Naqc5mga9Uha",
    "Banner": "ywXKQKPOLjTF", "Blast": "w_vX0mi58KKt",
    "Brace": "0bcGY4Xr4NE0", "Caster": "47CAqf7ySlfc",
    "Counter": "c45Fw0D2oGOk", "Deadly": "_mrPya5SXSqW",
    "Fast": "KdgwlPb8LuD2", "Fear": "dIQ3SGl2J2Ew",
    "Fearless": "2atvlmICQSCV", "Flying": "-QJdqJEKjIpE",
    "Furious": "JoOCVPx1xT1G", "Hero": "T08VkBuVmNZ_",
    "Immobile": "HWtnPV9LQF1D", "Impact": "62-mYKVM9MLd",
    "Indirect": "8Ck9GAwUK824", "Limited": "9042COVrLCsI",
    "Musician": "qrG_DXJez5Dg", "Parry": "_T07iXWo4VwJ",
    "Regeneration": "8KujvrTG8k9p", "Relentless": "H9E9PIWpGRdw",
    "Reliable": "Zx4mWN0SbmK8", "Rending": "cavWDboL4ubs",
    "Scout": "FAMbscK5vhSu", "Shred": "IEJp3a4vE0CB",
    "Slow": "Ldhtmr4H8b6G", "Spell Amplifier": "4Q1owB6yNFz1",
    "Stealth": "9jyvRoBODD-O", "Strider": "JSKVyurtWIyW",
    "Surge": "5v6oaGfrdf29", "Takedown": "8Hjy54TYtwb7",
    "Thrust": "umbiz4tnEyF8", "Tough": "a0YtInGiUDd6",
    "Transport": "aogQZcOOQrDI"}

# Book rules: Marksman is generic, Sharpshot its faction alias, Split rated
# by a string.
BOOK_RULES = [
    {"id": "synMarksman01", "name": "Marksman", "aliasedRuleId": None,
     "description": "Synthetic: +1 to hit when shooting over 9\".",
     "hasRating": False, "coreType": None, "targetType": 1},
    {"id": "synSharpshot1", "name": "Sharpshot",
     "aliasedRuleId": "synMarksman01", "originalName": "Marksman",
     "description": "Synthetic: +1 to hit when shooting over 9\".",
     "hasRating": False, "coreType": None, "targetType": 1},
    {"id": "synSplit00001", "name": "Split", "aliasedRuleId": None,
     "description": "Synthetic: splits into another unit.",
     "hasRating": True, "coreType": None, "targetType": 1},
]

U_TROOP, U_CAPT, U_WALK, U_JET = "uTroop1", "uCapt01", "uWalk01", "uJets01"


def rule(name, rating=None):
    """A rule reference by core / book name."""
    rid = CORE.get(name) or next(r["id"] for r in BOOK_RULES
                                 if r["name"] == name)
    d = {"type": "ArmyBookRule", "id": rid, "name": name,
         "label": name if rating is None else f"{name}({rating})"}
    if rating is not None:
        d["rating"] = rating
    return d


def weapon(name, rng, attacks, rules=(), count=1, mult=1):
    """Weapon dict; 'rng' None reproduces the null range of the real data."""
    parts = ([f'{rng}"'] if rng else []) + [f"A{attacks}"] + \
        [r["label"] for r in rules]
    prefix = f"{count}x " if count > 1 else ""
    return {"id": "w-" + name.replace(" ", "_"), "name": name,
            "type": "ArmyBookWeapon", "count": count, "range": rng,
            "attacks": attacks, "weaponId": f"wid-{name}",
            "specialRules": list(rules), "attacksMultiplier": mult,
            "label": f"{prefix}{name} ({', '.join(parts)})",
            "originalCount": count}


def item(name, content, count=1):
    """Item dict; content mixes rule and weapon dicts."""
    return {"id": f"i-{name}", "name": name, "type": "ArmyBookItem",
            "bases": None, "content": list(content), "count": count,
            "label": name}


def option(uid, gains, costs, cost="from_costs"):
    """Option priced per unit; 'cost' reproduces the unreliable top field."""
    label = ", ".join(g.get("label", g["name"]) for g in gains)
    d = {"uid": uid, "id": f"regen-{uid}", "type": "ArmyBookUpgradeOption",
         "label": label, "gains": list(gains),
         "costs": [{"unitId": u, "cost": c, "exactCost": c - 0.4,
                    "questCost": 2 * c} for u, c in costs.items()],
         "parentSectionId": None, "parentSectionUid": "staleSection"}
    if cost == "from_costs":
        d["cost"] = next(iter(costs.values()))
    elif cost is not None:
        d["cost"] = cost
    return d


def section(uid, label, variant, options, targets=None, affects=None,
            select=None, model=None, hero=False, low=False):
    """Section dict; affects / select as ('exactly', 1) / ('all',) tuples."""
    d = {"id": f"regen-{uid}", "uid": uid, "label": label,
         "parentPackageUid": None, "type": "ArmyBookUpgradeSection",
         "variant": variant, "options": options}
    for key, val in (("affects", affects), ("select", select)):
        if val:
            d[key] = {"type": val[0]} if len(val) == 1 else \
                {"type": val[0], "value": val[1]}
    if targets:
        d["targets"] = list(targets)
    if model:
        d["model"] = True
    if hero:
        d["isHeroUpgrade"] = True
    if low:
        d["isLowPrio"] = True
    for o in options:
        o["parentSectionId"] = uid
    return d


def unit(uid, name, size, q, d, cost, rules, weapons, items, upgrades,
         disabled=None):
    return {"id": uid, "name": name, "size": size, "quality": q,
            "defense": d, "cost": cost, "rules": rules, "weapons": weapons,
            "items": items, "upgrades": upgrades, "bases": None,
            "valid": True, "hasCustomRule": False,
            "hasBalanceInvalid": False, "disabledSections": disabled}


def troopers_package():
    """PA: weapon swaps of Line Troopers (replace / attachment shapes)."""
    def c(p):
        return {U_TROOP: p}
    return {"uid": "PA", "hint": "Line Troopers", "sections": [
        section("sRep1", "Replace Hand Weapon", "replace",
                [option("oRep1a", [weapon("Chain Blade", 0, 2)], c(5))],
                targets=["Hand Weapon"]),
        section("sRepAll", "Replace all Rifles", "replace",
                [option("oRepAll", [weapon("Carbine", 18, 2)], c(10),
                        cost=None)],
                targets=["Rifles"], affects=("all",)),
        section("sRepAny", "Replace any Rifle", "replace",
                [option("oRepAny", [weapon("Flamer", 12, 1, [rule("Blast", 3)])],
                        c(5), cost=99)],
                targets=["Rifle"], affects=("any",)),
        section("sRepOne", "Replace one Rifle", "replace",
                [option("oRepOneA", [weapon("Sgt. Pistol", 12, 1)], c(0)),
                 option("oRepOneB", [weapon("Plasma Gun", 24, 1,
                                            [rule("AP", 4)])], c(15)),
                 # Weapon team: one model gains Tough "3" (string rating).
                 option("oRepOneC", [item("Weapon Team", [
                     weapon("Heavy Gun", 30, 3, [rule("AP", 1)]),
                     dict(rule("Tough", 3), rating="3")])], c(20))],
                targets=["Rifle"], affects=("exactly", 1)),
        # Implicit chain: exists only after oRepOneA granted a Sgt. Pistol.
        section("sChain", "Replace Sgt. Pistol", "replace",
                [option("oChain", [weapon("Sgt. Plasma Pistol", 12, 1,
                                          [rule("AP", 4)])], c(5))],
                targets=["Sgt. Pistol"]),
        section("sUpTo2", "Replace up to two Rifles and Hand Weapons",
                "replace",
                [option("oUpTo2", [weapon("Heavy Rifle", 30, 1,
                                          [rule("AP", 1)])], c(10))],
                targets=["Rifles", "Hand Weapons"], affects=("up to", 2)),
        section("sAtt1", "Take one Rifle attachment", "attachment",
                [option("oAtt1", [weapon("Grenade Launcher", 24, 1,
                                         [rule("Blast", 3)])], c(10))],
                targets=["Rifle"], select=("exactly", 1)),
        section("sAttM1", "Any model may take one Rifle attachment",
                "attachment",
                [option("oAttM1", [weapon("Bayonet", 0, 1)], c(1))],
                targets=["Rifle"], affects=("exactly", 1), select=("any",),
                model=True),
        section("sAttMAny", "Any model may take any Rifle attachment",
                "attachment",
                [option("oAttMAny", [weapon("Underslung Flamer", 6, 1)],
                        c(2))],
                targets=["Rifle"], affects=("any",), select=("any",),
                model=True, low=True),
    ]}


def model_package():
    """PB: per-model upgrades, shared by Line Troopers and Jet Riders with
    DIFFERENT prices (the case that breaks option.cost)."""
    def c(a, b):
        return {U_TROOP: a, U_JET: b}
    medic = item("Medic Kit", [rule("Regeneration")])
    banner = item("Banner Kit", [rule("Banner")])
    drone = item("Gun Drone", [weapon("Drone Gun", 18, 2, [rule("Limited")])])
    return {"uid": "PB", "hint": "Line Troopers, Jet Riders", "sections": [
        section("sMAll", "Upgrade all models with", "upgrade",
                [option("oMAll", [item("Shields", [rule("Parry", 1)])],
                        c(20, 9))], affects=("all",), model=True),
        section("sMOne", "Upgrade one model with", "upgrade",
                [option("oMOne", [banner], c(5, 6))],
                affects=("exactly", 1), model=True),
        section("sMAllOne", "Upgrade all models with one", "upgrade",
                [option("oMAllOneA", [item("Jump Packs", [rule("Fast")])],
                        c(20, 10)),
                 option("oMAllOneB", [item("Camo Cloaks",
                                           [rule("Stealth")])], c(15, 8))],
                affects=("all",), select=("exactly", 1), model=True),
        section("sMOneOne", "Upgrade one model with one", "upgrade",
                [option("oMOneOneA", [medic], c(10, 10)),
                 option("oMOneOneB", [drone], c(10, 12))],
                affects=("exactly", 1), select=("exactly", 1), model=True),
        section("sMAllAny", "Upgrade all models with any", "upgrade",
                [option("oMAllAnyA", [item("Frag Grenades", [rule("Impact", 1)])],
                        c(10, 5)),
                 option("oMAllAnyB", [item("Krak Grenades", [rule("Bane")])],
                        c(10, 5))],
                affects=("all",), select=("any",), model=True),
        section("sMUpTo3", "Upgrade up to three models with one", "upgrade",
                [option("oMUpTo3", [{"id": "gRule1", "name": "Musician",
                                     "type": "ArmyBookRule",
                                     "label": "Musician", "count": 1}],
                        c(5, 5))],
                affects=("up to", 3), select=("exactly", 1), model=True),
        section("sMUpTo2", "Upgrade up to two models with one", "upgrade",
                [option("oMUpTo2", [weapon("Sniper Rifle", 30, 1,
                                           [rule("Sharpshot")])], c(10, 10))],
                affects=("up to", 2), select=("exactly", 1), model=True),
        section("sMAny", "Upgrade any model with", "upgrade",
                [option("oMAny", [item("Combat Stims", [rule("Furious")])],
                        c(2, 3))], affects=("any",), model=True),
        section("sMOneAny", "Upgrade one model with any", "upgrade",
                [option("oMOneAnyA", [item("Auspex", [rule("Relentless")])],
                        c(5, 5)),
                 option("oMOneAnyB", [item("Comms", [rule("Reliable")])],
                        c(5, 5))],
                affects=("exactly", 1), select=("any",), model=True),
    ]}


def captain_package():
    """PC: unit-level upgrades of the hero, incl. a hero-only section."""
    def c(p):
        return {U_CAPT: p}
    return {"uid": "PC", "hint": "Field Captain", "sections": [
        section("sOne", "Upgrade with one", "upgrade",
                [option("oOneA", [item("Psychic", [rule("Caster", 1)])], c(15)),
                 option("oOneB", [item("Veteran", [rule("Fearless")])], c(10))],
                select=("exactly", 1), hero=True),
        # Same section label AND same option label as sOne: only the
        # occurrence tells them apart (as in BB Assault Brothers).
        section("sOne2", "Upgrade with one", "upgrade",
                [option("oOne2A", [item("Psychic", [rule("Caster", 1)])],
                        c(20)),
                 option("oOne2B", [item("Scanner", [rule("Relentless")])],
                        c(5))],
                select=("exactly", 1)),
        section("sAny", "Upgrade with any", "upgrade",
                [option("oAnyA", [item("Bodyguard", [rule("Tough", 1)])],
                        c(10)),
                 option("oAnyB", [weapon("Grav Pistol", 12, 1,
                                         [rule("Rending")])], c(5))],
                select=("any",)),
        section("sWith", "Upgrade with", "upgrade",
                [option("oWith", [item("Command Banner",
                                       [rule("Banner")])], c(10))]),
        section("sUpTo2", "Upgrade with up to two", "upgrade",
                [option("oUT2A", [item("Iron Halo", [rule("Fear", 1)])], c(5)),
                 option("oUT2B", [item("Jet Pack", [rule("Flying")])], c(10)),
                 option("oUT2C", [item("Auspex", [rule("Relentless")])],
                        c(5))],
                select=("up to", 2)),
        section("sAnyUpTo2", "Upgrade with up to two of any", "upgrade",
                [option("oAUT2", [item("Frag Charges",
                                       [rule("Impact", 2)])], c(5))],
                affects=("any",), select=("up to", 2)),
        section("sRepPistol", "Replace Pistol", "replace",
                [option("oRepPistol", [weapon("Plasma Pistol", 12, 1,
                                              [rule("AP", 4)])], c(5))],
                targets=["Pistol"]),
    ]}


def walker_package():
    """PD: '2x' replace target and an item granting a weapon."""
    def c(p):
        return {U_WALK: p}
    return {"uid": "PD", "hint": "Siege Walker", "sections": [
        # Chain in REVERSE book order: its target is granted by s2x below.
        section("sHammer", "Replace Siege Hammer", "replace",
                [option("oHammer", [weapon("Thunder Hammer", 0, 4,
                                           [rule("AP", 4)])], c(10))],
                targets=["Siege Hammer"]),
        section("s2x", "Replace 2x Claw", "replace",
                [option("o2x", [weapon("Siege Hammer", 0, 3,
                                       [rule("AP", 3), rule("Deadly", 3)])],
                        c(20))],
                targets=["2x Claw"]),
        section("sWOne", "Upgrade with one", "upgrade",
                [option("oWOne", [item("Sponson", [weapon(
                    "Sponson Flamer", 12, 1, [rule("Blast", 3)])])], c(15))],
                select=("exactly", 1)),
    ]}


def build_book():
    units = [
        unit(U_TROOP, "Line Troopers", 10, 4, 4, 100, [],
             [weapon("Rifle", 24, 1, count=10),
              weapon("Hand Weapon", 0, 1, count=10)],
             [], ["PA", "PB"], disabled=None),
        unit(U_CAPT, "Field Captain", 1, 3, 4, 60,
             [rule("Hero"), rule("Tough", 3)],
             [weapon("Pistol", 12, 1), weapon("Blade", 0, 3, [rule("AP", 1)])],
             [item("Command Kit", [rule("Split", "Drones [2]")])], ["PC"]),
        unit(U_WALK, "Siege Walker", 1, 4, 2, 200,
             [rule("Tough", 9), rule("Fear", 2)],
             [weapon("Rotary Gun", 24, 6, [rule("Surge")], mult=2),
              weapon("Claw", 0, 2, [rule("AP", 1)], count=2),
              weapon("Stomp", None, 3)],
             [], ["PD"]),
        unit(U_JET, "Jet Riders", 3, 4, 3, 120,
             [rule("Tough", 3), rule("Fast")],
             [weapon("Jet Carbine", 18, 2, count=3),
              weapon("Spike", 0, 1, count=3)],
             [], ["PB", "PMISSING"], disabled=["sMUpTo3", "staleUid"]),
    ]
    packages = [troopers_package(), model_package(), captain_package(), walker_package()]
    return {"uid": BOOK_UID, "name": "Synthetic Legion",
            "versionString": "3.6.0", "gameSystemId": 2,
            "gameSystemSlug": "grimdark-future", "factionName": None,
            "factionRelation": None, "units": units,
            "upgradePackages": packages, "specialRules": BOOK_RULES,
            "spells": [
                {"id": "sp1", "name": "Bolt", "threshold": 1,
                 "effect": "Synthetic: target takes 2 hits with AP(1).",
                 "generation": {}},
                {"id": "sp2", "name": "Ward", "threshold": 2,
                 "effect": "Synthetic: friendly unit gets +1 to defense "
                           "rolls once.", "generation": {}}],
            "transforms": [{"id": "t1", "type": "unit/namePrefix",
                            "filter": [], "target": "Ignored"}]}


def build_core():
    return {"rules": [{"id": rid, "name": name,
                       "description": f"Synthetic placeholder for {name}.",
                       "enabledGameSystems": [2], "coreType": 1}
                      for name, rid in sorted(CORE.items())],
            "traits": []}


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
        fh.write("\n")


def main():
    write(os.path.join(OUT, "books", f"{BOOK_UID}.json"), build_book())
    write(os.path.join(OUT, "rules", "common_2.json"), build_core())
    print(f"synthetic data written to {OUT}")


if __name__ == "__main__":
    main()
