#!/usr/bin/env python3
"""Reference configurations checked against Army Forge.

Each reference is written with LABELS (as shown in Army Forge) so a human
can rebuild it: section label (+ occurrence, when a unit has two sections
with the same label), option label prefix, count. 'computed' is what
resolve() gives; 'af_points' is what the Army Forge UI shows, filled in by
the user. test_reference_configs.py checks both on real data.

    python3 tests/reference_configs.py > references.md
"""
import sys

import testpaths
from grimdarkoracle.data import af_book as ab
from grimdarkoracle.data.resolve import Choice, resolve

DAO, BB = "z8205ez2boggzs22", "78qp9l5alslt6yj8"

# (id, book, unit, [(section label, occurrence, option prefix, count)],
#  computed, af_points, what it checks)
REFS = [
    ("R1", DAO, "Security Grunts", [
        ("Replace all Pistols and Particle Walls", 1, "Shotgun", 1),
        ("Replace one Shotgun", 1, "Plasma Rifle", 1),
        ("Upgrade one model with one", 1, "Shield Drone", 1)],
     150, 150, "replace all with two targets (one is an item), chain on "
                "its result, one model with one"),
    ("R2", DAO, "Security Grunts", [
        ("Replace one Pistol", 1, "Sgt. Pistol", 1),
        ("Replace Sgt. Pistol", 1, "Plasma Pistol", 1),
        ("Replace Sgt. Hand Weapon", 1, "Plasma Sword", 1)],
     85, 85, "three-step sergeant chain"),
    ("R3", DAO, "Spotters", [
        ("Replace one Carbine", 1, "Gauss Tandem-Rifle", 1),
        ("Upgrade any model with", 1, "Spotting Laser", 2),
        ("Upgrade one model with one", 1, "Accelerator Drone", 1)],
     195, 195, "'Upgrade any model with' priced per model (x2)"),
    ("R4", DAO, "Battle Suits", [
        ("Replace any Dual Suit-Flamers", 1, "Dual Suit-Plasmas", 2),
        ("Replace any Dual Suit-Flamers", 1, "Dual Suit-Missiles", 1),
        ("Replace any Strike", 1, "Assault Suit-Fuser", 1),
        ("Upgrade all models with one", 1, "Thrusters", 1)],
     250, 250, "replace any with two options sharing the pool; "
                "all models priced once"),
    ("R5", DAO, "Battle Suit Elite", [
        ("Replace Dual Suit-Flamers", 1, "Plasma Sword", 1),
        ("Upgrade with one", 1, "Airdrop Thrusters", 1),
        ("Upgrade with", 1, "Gun Drone", 1),
        ("Upgrade with one", 2, "Master Armorer", 1)],
     210, 210, "two sections with the same label"),
    ("R6", DAO, "Gun Drones", [
        ("Replace all Drone Missile-Guns", 1, "Drone Guns", 1),
        ("Upgrade all models with", 1, "Self-Repair", 1)],
     120, 120, "replace all and upgrade all priced once"),
    ("R7", DAO, "Grunt Leader", [
        ("Replace Pistol and Hand Weapon", 1, "Burst Pistol", 1),
        ("Replace Burst Pistol", 1, "Burst Fusion Pistol", 1),
        ("Upgrade with any", 1, "Gun Drone", 1),
        ("Upgrade with any", 1, "Master Spotter", 1),
        ("Upgrade with one", 1, "Elder Sage", 1)],
     110, 110, "chain on a hero, 'with any' with two options"),
    ("R8", BB, "Veteran Battle Brothers", [
        ("Replace any Flamer", 1, "Burst Battle Rifle", 2),
        ("Any model may take any Burst Battle Rifle attachment", 1,
         "Plasma-Mod", 2),
        ("Upgrade one model with one", 1, "Medical Training", 1)],
     175, 175, "attachments capped by the rifles present (a third mod on "
               "two rifles is refused, see test_reference_configs)"),
    ("R9", BB, "Veteran Master Brother", [
        ("Replace Flamer Pistol and Hand Weapon", 1, "Burst Heavy Rifle", 1),
        ("Take one Burst Heavy Rifle attachment", 1, "Fusion-Mod", 1),
        ("Upgrade with one", 1, "Jetpack", 1),
        ("Upgrade with one", 2, "Archivist", 1)],
     170, 170, "attachment on a chained weapon"),
    ("R10", BB, "Pathfinders", [
        ("Replace one Heavy Rifle", 1, "Sniper Rifle", 1),
        ("Replace one Heavy Rifle and Hand Weapon", 1, "Sgt. Heavy Pistol", 1),
        ("Replace Sgt. Heavy Pistol", 1, "Plasma Pistol", 1),
        ("Upgrade all models with any", 1, "Camo Cloaks", 1),
        ("Upgrade all models with any", 1, "Forward Sentries", 1)],
     165, 165, "all models with any (two options), sergeant chain"),
    ("R11", BB, "Destroyers", [
        ("Replace all Assault Cyclic Rifles and Hand Weapons", 1,
         "Burst Cyclic Rifle", 1),
        ("Replace one Burst Cyclic Rifle", 1, "Gatling Cannon", 1),
        ("Upgrade all models with", 1, "Orbital Drop", 1),
        ("Upgrade one model with one", 1, "The Founder's Banner", 1)],
     340, 340, "replace one on the result of replace all"),
    ("R12", BB, "Assault Brothers", [
        ("Replace any Heavy Pistol", 1, "Plasma Pistol", 3),
        ("Replace one Heavy Pistol and Hand Weapon", 1, "Dual Energy Claws", 1),
        ("Upgrade all models with one", 1, "Jetpack", 1),
        ("Upgrade one model with one", 1, "Detachment Banner", 1)],
     215, 215, "replace any x3 then replace one on a remaining model"),
]


# Rare shapes absent from DAO / BB, answered in the Army Forge UI.
QUESTIONS = [
    ("Q1", "Robot Legions: Great Monolith, 'Upgrade with up to two'",
     "Can 'Technoward' be taken twice?", "yes", "yes"),
    ("Q2", "Human Defense Force: Tactical Titan, "
           "'Upgrade with up to two of any'",
     "Can the same option (e.g. 'Cluster Missiles') be taken twice?", "yes",
     "yes"),
    ("Q3", "War Disciples: War Chosen Havoc Brothers (after replacing their "
           "Flamers with Burst Heavy Rifles), 'Any model may take one Burst "
           "Heavy Rifle attachment'",
     "Can ONE model take two different mods?", "no (one per model)",
     "no: at most one mod per Burst Heavy Rifle present"),
]


def find_unit(book, name):
    units = [u for u in book.units.values() if u.name == name]
    if len(units) != 1:
        raise LookupError(f"{book.name}: {len(units)} units named {name!r}")
    return units[0]


def build_choices(book, unit, spec):
    """Label spec -> [Choice]. Raises LookupError if a label is not found
    or not unique (the reference must then be rewritten)."""
    sections = [(p.uid, s) for p in book.unit_packages(unit)
                for s in p.sections if s.uid not in unit.disabled_sections]
    out = []
    for label, nth, prefix, count in spec:
        same = [(pu, s) for pu, s in sections if s.label == label]
        if len(same) < nth:
            raise LookupError(f"{unit.name}: section {label!r} #{nth}")
        pu, sec = same[nth - 1]
        opts = [o for o in sec.options if o.label.startswith(prefix)]
        if len(opts) != 1:
            raise LookupError(f"{unit.name}: {len(opts)} options {prefix!r}")
        out.append(Choice(pu, sec.uid, opts[0].uid, count))
    return out


def run(ref):
    """(book, unit, ResolvedUnit) of a reference."""
    rid, book_uid, unit_name, spec = ref[:4]
    book = ab.load_book(testpaths.book_path(book_uid))
    unit = find_unit(book, unit_name)
    return book, unit, resolve(book, unit.id, build_choices(book, unit, spec))


def sheet():
    """Markdown checklist for the user."""
    lines = ["# Reference configurations — check in Army Forge", "",
             "For each one: create the unit in Army Forge (GF 3.6.0), take "
             "exactly these options and write the points Army Forge shows "
             "in the last column.", ""]
    for ref in REFS:
        rid, _, unit_name, spec, computed, af, note = ref
        book, unit, ru = run(ref)
        lines.append(f"## {rid} — {book.name}: {unit_name} "
                     f"(base {unit.cost} pts, {unit.size} models)")
        lines.append(f"*Checks: {note}*\n")
        lines.append("| Section | Option | Count |\n|---|---|---|")
        for label, nth, prefix, count in spec:
            tag = f" (#{nth})" if nth > 1 else ""
            lines.append(f"| {label}{tag} | {prefix} | {count} |")
        loadout = "; ".join(f"{n}x {w.name}" for w, n in ru.weapons())
        lines.append(f"\nResolved weapons: {loadout}  ")
        lines.append(f"**GrimDarkOracle: {ru.points} pts** — Army Forge: "
                     f"{af if af is not None else '____'}")
        if ru.issues:
            lines.append(f"\nISSUES: {list(ru.issues)}")
        lines.append("")
    lines += ["## Rare section shapes (not in DAO / BB)", "",
              "| # | Unit and section | Question | GrimDarkOracle assumes | "
              "Army Forge |", "|---|---|---|---|---|"]
    lines += [f"| {q} | {where} | {ask} | {assumed} | {answer} |"
              for q, where, ask, assumed, answer in QUESTIONS]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    if testpaths.USING_SYNTHETIC:
        testpaths.set_source(True)
    if testpaths.USING_SYNTHETIC:
        sys.exit("real Army Forge data needed (data/army_forge)")
    print(sheet())
