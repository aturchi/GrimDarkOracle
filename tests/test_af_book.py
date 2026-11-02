"""af_book: typed views of Army Forge books, on synthetic and real data."""
import glob
import os

import testpaths
import make_synthetic
from grimdarkoracle.data import af_book as ab

SYN = os.path.join(testpaths.SYNTHETIC_DIR, "books",
                   f"{make_synthetic.BOOK_UID}.json")

# --- the committed synthetic book is what the generator writes ------------
assert testpaths.load_json(SYN) == make_synthetic.build_book(), \
    "tests/synthetic is stale: run tests/make_synthetic.py"

# --- synthetic book ---------------------------------------------------------
book = ab.load_book(SYN)
assert (book.uid, book.version, book.game_system) == (
    make_synthetic.BOOK_UID, "3.6.0", 2)
assert set(book.units) == {"uTroop1", "uCapt01", "uWalk01", "uJets01"}
assert set(book.packages) == {"PA", "PB", "PC", "PD"}

troop, jets = book.units["uTroop1"], book.units["uJets01"]
walker, capt = book.units["uWalk01"], book.units["uCapt01"]
assert (troop.size, troop.quality, troop.defense, troop.cost) == (10, 4, 4, 100)
assert [w.name for w in troop.weapons] == ["Rifle", "Hand Weapon"]
assert troop.weapons[0].count == 10 and not troop.weapons[0].melee
assert troop.weapons[1].melee

# attacksMultiplier is ignored; null range -> melee, with a warning
rotary = walker.weapons[0]
assert rotary.attacks == 6 and rotary.range == 24
stomp = walker.weapons[2]
assert stomp.range == 0 and stomp.melee
assert any("Stomp" in w for w in book.warnings)
assert any("PMISSING" in w for w in book.warnings)

# rule refs: int rating, string rating, no rating
tough = next(r for r in walker.rules if r.name == "Tough")
assert tough.rating == 9 and tough.label == "Tough(9)"
split = capt.items[0].rules[0]
assert split.rating == "Drones [2]" and split.name == "Split"
assert next(r for r in capt.rules if r.name == "Hero").rating is None

# disabled sections and unknown packages
assert jets.disabled_sections == frozenset({"sMUpTo3", "staleUid"})
assert [p.uid for p in book.unit_packages(jets)] == ["PB"]

# sections: quantifiers, targets, flags; section 'id' never used
pa = {s.uid: s for s in book.packages["PA"].sections}
assert pa["sRepAll"].affects == ab.Quant("all")
assert pa["sUpTo2"].affects == ab.Quant("up to", 2)
assert pa["sUpTo2"].targets == ("Rifles", "Hand Weapons")
assert pa["sRep1"].affects is None and pa["sRep1"].select is None
assert pa["sAttM1"].model and pa["sAttM1"].select == ab.Quant("any")
assert pa["sAttMAny"].low_prio
assert next(s for s in book.packages["PC"].sections
            if s.uid == "sOne").hero_only

# costs: always from costs[] per unit, whatever option.cost says
opt = pa["sRepAny"].options[0]
assert opt.cost_for("uTroop1") == 5            # option.cost says 99
assert pa["sRepAll"].options[0].cost_for("uTroop1") == 10   # cost absent
pb = {s.uid: s for s in book.packages["PB"].sections}
shields = pb["sMAll"].options[0]
assert (shields.cost_for("uTroop1"), shields.cost_for("uJets01")) == (20, 9)
assert shields.cost_for("uWalk01") is None

# gains: weapon, item with rules, item with weapons, bare rule
g = pa["sRepOne"].options[1].gains[0]
assert isinstance(g, ab.Weapon) and g.rules[0].rating == 4
drone = pb["sMOneOne"].options[1].gains[0]
assert isinstance(drone, ab.Item) and drone.weapons[0].name == "Drone Gun"
music = pb["sMUpTo3"].options[0].gains[0]
assert isinstance(music, ab.Item) and music.is_rule
assert music.rules[0].name == "Musician"

# book rules, alias, spells
sharp = book.rules["synSharpshot1"]
assert sharp.aliased_rule_id == "synMarksman01"
assert sharp.original_name == "Marksman"
assert [s.threshold for s in book.spells] == [1, 2]

core = ab.load_core_rules(testpaths.rules_path())
assert core["17crjK7P6_w6"].name == "AP" and len(core) == 39

# strict on missing structure
try:
    ab.parse_book({"uid": "x"})
except ab.BookFormatError as exc:
    assert "units" in str(exc)
else:
    raise AssertionError("missing 'units' accepted")

# --- only af_book may read Army Forge field names ---------------------------
# (local_books WRITES the subset af_book reads: the other half of the adapter)
AF_KEYS = ("upgradePackages", "versionString", "specialRules",
           "attacksMultiplier", "disabledSections", "parentSectionId",
           "isHeroUpgrade", "aliasedRuleId")
pkg_dir = os.path.join(testpaths.REPO_ROOT, "grimdarkoracle")
for path in glob.glob(os.path.join(pkg_dir, "**", "*.py"), recursive=True):
    if os.path.basename(path) in ("af_book.py", "local_books.py"):
        continue
    text = open(path, encoding="utf-8").read()
    leaked = [k for k in AF_KEYS if f'"{k}"' in text or f"'{k}'" in text]
    assert not leaked, f"{path} reads Army Forge fields {leaked}"

# --- real data (only with --real_data) --------------------------------------
if not testpaths.USING_SYNTHETIC:
    paths = [p for p in glob.glob(os.path.join(testpaths.DATA_DIR, "books",
                                               "*.json"))
             if not p.endswith(".prev.json")]
    unexpected = []
    for p in paths:
        b = ab.load_book(p)
        unexpected += [w for w in b.warnings if "taken as melee" not in w]
        for u in b.units.values():
            for pkg in b.unit_packages(u):
                for s in pkg.sections:
                    for o in s.options:
                        assert o.cost_for(u.id) is not None, (b.name, u.name,
                                                              o.label)
    assert not unexpected, unexpected
    dao = ab.load_book(testpaths.book_path("z8205ez2boggzs22"))
    titan = next(u for u in dao.units.values() if u.name == "Tide Titan")
    sword = next(w for w in titan.weapons if w.name == "Titan Plasma Sword")
    assert sword.attacks == 12, sword
    print(f"af_book: {len(paths)} real books parsed")
print("af_book: OK")
