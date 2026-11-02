"""resolve(): section semantics, chains, caps, points, issues (synthetic)."""
import testpaths
import make_synthetic
from grimdarkoracle.data import af_book as ab
from grimdarkoracle.data import options_core as oc
from grimdarkoracle.data.resolve import Choice, resolve

# Always the synthetic book, whatever source is selected.
book = ab.load_book(testpaths.book_path(make_synthetic.BOOK_UID,
                                        testpaths.SYNTHETIC_DIR))


def ch(pkg, sec, opt, n=1):
    return Choice(pkg, sec, opt, n)


def counts(ru):
    """Weapon name -> total count."""
    return {w.name: n for w, n in ru.weapons()}


def state(ru, uid):
    return next(s for s in ru.sections if s.uid == uid)


# --- names -------------------------------------------------------------------
assert oc.parse_target("2x Heavy Claw") == (2, "heavy claw")
assert oc.same_name("Rifles", "Rifle") and oc.same_name("Power Axes", "Power Axe")
assert oc.same_name("Hand Weapons", "hand weapon")
assert not oc.same_name("Rifle", "Heavy Rifle")
# a base weapon (count 5, "5x" label) and a gained copy are one profile
w5 = ab.Weapon("Hand Weapon", 5, 0, 1, (), "5x Hand Weapon (A1)")
w1 = ab.Weapon("Hand Weapon", 1, 0, 1, (), "Hand Weapon (A1)")
assert oc.profile(w5) == oc.profile(w1) == w1

# --- base unit ----------------------------------------------------------------
T = "uTroop1"
r = resolve(book, T)
assert (r.points, r.size, r.issues) == (100, 10, ())
assert counts(r) == {"Rifle": 10, "Hand Weapon": 10}
assert all(dict((w.name, n) for w, n in m.weapons) == {"Rifle": 1,
                                                        "Hand Weapon": 1}
           for m in r.models)
assert not state(r, "sChain").enabled          # no Sgt. Pistol yet
assert state(r, "sRepAny").caps == oc.Caps("count", 10, 10)
assert state(r, "sRepAll").caps.expand_all

# --- replace all (plural target), price from costs[] --------------------------
r = resolve(book, T, [ch("PA", "sRepAll", "oRepAll")])
assert counts(r) == {"Carbine": 10, "Hand Weapon": 10} and r.points == 110
assert not state(r, "sRepAny").enabled         # nothing left to replace

# --- replace any: count, spread over models, cap ------------------------------
r = resolve(book, T, [ch("PA", "sRepAny", "oRepAny", 3)])
assert counts(r)["Flamer"] == 3 and counts(r)["Rifle"] == 7
assert r.points == 115                         # 5 x 3 (option.cost says 99)
assert [i for i, m in enumerate(r.models)
        if any(w.name == "Flamer" for w, _ in m.weapons)] == [0, 1, 2]
r = resolve(book, T, [ch("PA", "sRepAny", "oRepAny", 11)])
assert r.points == 100 and "exceeds" in r.issues[0]

# --- chain in book order, placed on the least upgraded model -------------------
r = resolve(book, T, [ch("PA", "sRepAny", "oRepAny", 2),
                      ch("PA", "sRepOne", "oRepOneA"),
                      ch("PA", "sChain", "oChain")])
assert r.issues == () and r.points == 100 + 10 + 0 + 5
sgt = r.models[2]
assert {w.name for w, _ in sgt.weapons} == {"Sgt. Plasma Pistol",
                                            "Hand Weapon"}
assert state(r, "sChain").enabled

# --- radio: one option only ------------------------------------------------------
r = resolve(book, T, [ch("PA", "sRepOne", "oRepOneA"),
                      ch("PA", "sRepOne", "oRepOneB")])
assert r.points == 100 and len(r.issues) == 1 and "exceeds" in r.issues[0]

# --- weapon team: Tough on one model only (numeric-string rating) --------------
r = resolve(book, T, [ch("PA", "sRepOne", "oRepOneC")])
assert [m.tough for m in r.models] == [3] + [0] * 9
assert counts(r)["Heavy Gun"] == 1 and r.points == 120

# --- up to two, several targets taken from the same model ----------------------
r = resolve(book, T, [ch("PA", "sUpTo2", "oUpTo2", 2)])
assert counts(r) == {"Rifle": 8, "Hand Weapon": 8, "Heavy Rifle": 2}
assert r.points == 120
assert "exceeds" in resolve(book, T, [ch("PA", "sUpTo2", "oUpTo2", 3)]).issues[0]

# --- attachments keep the target ---------------------------------------------------
r = resolve(book, T, [ch("PA", "sAtt1", "oAtt1"),
                      ch("PA", "sAttM1", "oAttM1", 10)])
assert counts(r)["Rifle"] == 10 and counts(r)["Grenade Launcher"] == 1
assert counts(r)["Bayonet"] == 10 and r.points == 100 + 10 + 10
assert resolve(book, T, [ch("PA", "sAttM1", "oAttM1", 11)]).issues
# "any ... attachment": still one attachment per target weapon (Army Forge)
assert state(resolve(book, T), "sAttMAny").caps == oc.Caps("count", 10, 10)

# --- per-model upgrades ---------------------------------------------------------------
r = resolve(book, T, [ch("PB", "sMAll", "oMAll")])
assert r.rule_models() == {"Parry(1)": 10} and r.points == 120
r = resolve(book, T, [ch("PB", "sMAllOne", "oMAllOneA"),
                      ch("PB", "sMAllOne", "oMAllOneB")])
assert r.rule_models() == {"Fast": 10} and len(r.issues) == 1
r = resolve(book, T, [ch("PB", "sMUpTo3", "oMUpTo3", 3),
                      ch("PB", "sMOneOne", "oMOneOneB")])
assert r.rule_models() == {"Musician": 3}      # weapon rules are not here
assert r.points == 100 + 15 + 10 and counts(r)["Drone Gun"] == 1
holders = [i for i, m in enumerate(r.models) if m.items]
assert holders == [0, 1, 2, 3], holders        # drone on a 4th model
assert "exceeds" in resolve(book, T,
                            [ch("PB", "sMUpTo3", "oMUpTo3", 4)]).issues[0]
r = resolve(book, T, [ch("PB", "sMAny", "oMAny", 10)])
assert r.rule_models() == {"Furious": 10} and r.points == 120

# --- shared package priced per unit; disabled section; unknown package ---------
J = "uJets01"
r = resolve(book, J, [ch("PB", "sMAll", "oMAll"),
                      ch("PB", "sMUpTo3", "oMUpTo3"),
                      ch("PMISSING", "x", "y")])
assert r.points == 120 + 9
assert any("disabled" in i for i in r.issues)
assert any("not available" in i for i in r.issues)
assert not state(r, "sMUpTo3").enabled
assert [m.tough for m in r.models] == [3, 3, 3]

# --- hero: radio, up to two (same option twice), tough stacking ----------------
C = "uCapt01"
r = resolve(book, C, [ch("PC", "sOne", "oOneA"), ch("PC", "sOne", "oOneB"),
                      ch("PC", "sAny", "oAnyA"), ch("PC", "sUpTo2", "oUT2A", 2),
                      ch("PC", "sRepPistol", "oRepPistol")])
assert r.points == 60 + 15 + 10 + 10 + 5 and len(r.issues) == 1
assert r.models[0].tough == 4                  # Tough(3) + Bodyguard Tough(1)
assert counts(r) == {"Plasma Pistol": 1, "Blade": 1}

# --- chain in reverse book order is deferred, then applied ---------------------
W = "uWalk01"
r = resolve(book, W, [ch("PD", "sHammer", "oHammer"), ch("PD", "s2x", "o2x")])
assert r.issues == () and r.points == 230
assert counts(r) == {"Rotary Gun": 1, "Stomp": 1, "Thunder Hammer": 1}
r = resolve(book, W, [ch("PD", "sHammer", "oHammer")])
assert r.points == 200 and "absent" in r.issues[0]
r = resolve(book, W, [ch("PD", "sWOne", "oWOne")])
assert counts(r)["Sponson Flamer"] == 1 and r.points == 215

# --- invalid references never crash ----------------------------------------------
r = resolve(book, T, [ch("PA", "nope", "x"), ch("PA", "sRepAll", "nope"),
                      ch("PA", "sRepAll", "oRepAll", 0)])
assert r.points == 100 and len(r.issues) == 3
try:
    resolve(book, "nope")
except KeyError:
    pass
else:
    raise AssertionError("unknown unit accepted")
# --- real data: every unit by default, plus seeded random configurations -----
if not testpaths.USING_SYNTHETIC:
    import glob
    import os
    import random
    rnd, n = random.Random(36), 0
    for path in sorted(glob.glob(os.path.join(testpaths.DATA_DIR, "books",
                                              "*.json"))):
        if path.endswith(".prev.json"):
            continue
        b = ab.load_book(path)
        for u in b.units.values():
            r = resolve(b, u.id)
            assert r.points == u.cost and not r.issues, (b.name, u.name)
            assert r.size == max(1, u.size)
            for _ in range(3):           # must never raise
                picks = []
                for s in r.sections:
                    if s.enabled and rnd.random() < 0.5:
                        sec = next(x for x in b.packages[s.package].sections
                                   if x.uid == s.uid)
                        picks.append(Choice(s.package, s.uid,
                                            rnd.choice(sec.options).uid))
                resolve(b, u.id, picks)
                n += 1
    print(f"resolve: {n} random real configurations resolved")
print("resolve: OK")
