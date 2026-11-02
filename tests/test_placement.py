"""Per-model placement of upgrade instances:
explicit models, validation, explicit-first, list format, re-link."""
import copy
from dataclasses import replace
import random

import testpaths
import make_synthetic
from grimdarkoracle.data import af_book as ab
from grimdarkoracle.data import army_list as al
from grimdarkoracle.data import links
from grimdarkoracle.data import options_core as oc
from grimdarkoracle.data.resolve import Choice, resolve

book = ab.load_book(testpaths.book_path(make_synthetic.BOOK_UID,
                                        testpaths.SYNTHETIC_DIR))
T, CAPT = "uTroop1", "uCapt01"


def ch(sec, opt, n=1, models=(), pkg="PA"):
    return Choice(pkg, sec, opt, n, tuple(models))


def held(ru, i):
    m = ru.models[i]
    return {w.name for w, _ in m.weapons} | {it.name for it, _ in m.items}


def state(ru, uid):
    return next(s for s in ru.sections if s.uid == uid)


def loadout(ru):
    return [sorted(held(ru, i)) for i in range(ru.size)]


# --- placeable sections --------------------------------------------------------------
r = resolve(book, T)
flags = {s.uid: s.placeable for s in r.sections}
assert flags["sRepOne"] and flags["sRepAny"] and flags["sAttM1"] \
    and flags["sMUpTo3"] and flags["sMOne"] and flags["sAtt1"]
assert not flags["sRepAll"] and not flags["sMAll"] and not flags["sMAllAny"]
assert not any(s.placeable for s in resolve(book, CAPT).sections)

# --- explicit placement, chains, weapon team ------------------------------------------
r = resolve(book, T, [ch("sRepOne", "oRepOneA", models=[7]),
                      ch("sChain", "oChain")])           # chain follows model 7
assert "Sgt. Plasma Pistol" in held(r, 7) and "Rifle" not in held(r, 7)
assert state(r, "sRepOne").placed == (("oRepOneA", (7,)),)
assert state(r, "sChain").placed == (("oChain", (7,)),) and not r.issues
r = resolve(book, T, [ch("sRepOne", "oRepOneC", models=[3])])
assert [m.tough for m in r.models] == [0, 0, 0, 3] + [0] * 6
r = resolve(book, T, [ch("sUpTo2", "oUpTo2", 2, models=[5, 9])])
assert "Heavy Rifle" in held(r, 5) and "Heavy Rifle" in held(r, 9)
assert r.points == resolve(book, T, [ch("sUpTo2", "oUpTo2", 2)]).points

# --- validation: impossible placement -> automatic + issue -----------------------
r = resolve(book, T, [ch("sRepOne", "oRepOneA", models=[7]),
                      ch("sChain", "oChain", models=[2])])
assert "Sgt. Plasma Pistol" in held(r, 7)
assert any("model 3 cannot take" in i for i in r.issues)
r = resolve(book, T, [ch("sRepAny", "oRepAny", 2, models=[4, 4])])
assert state(r, "sRepAny").placed == (("oRepAny", (4, 0)),)   # one Rifle each
assert len(r.issues) == 1
r = resolve(book, T, [ch("sRepOne", "oRepOneA", models=[10])])  # out of range
assert len(r.issues) == 1 and "Sgt. Pistol" in held(r, 0)
r = resolve(book, T, [ch("sUpTo2", "oUpTo2", 2, models=[1, 2, 3])])
assert any("3 models given for 2 instances" in i for i in r.issues)
r = resolve(book, T, [ch("sMAll", "oMAll", models=[3], pkg="PB")])
assert any("placement ignored" in i for i in r.issues)
assert not resolve(book, CAPT, [ch("sWith", "oWith", models=[0],
                                   pkg="PC")]).issues          # single model

# --- capacity per model ----------------------------------------------------------
# One attachment per target weapon: a model with one Rifle takes one.
r = resolve(book, T, [ch("sAttMAny", "oAttMAny", 2, models=[6, 6])])
assert state(r, "sAttMAny").placed[0][1][0] == 6 and len(r.issues) == 1
# "with one": a model takes one option of the section; "any": each once.
r = resolve(book, T, [ch("sMUpTo3", "oMUpTo3", 2, models=[1, 1], pkg="PB")])
assert state(r, "sMUpTo3").placed == (("oMUpTo3", (1, 0)),)
r = resolve(book, T, [ch("sMOneAny", "oMOneAnyA", models=[2], pkg="PB"),
                         ch("sMOneAny", "oMOneAnyB", models=[2], pkg="PB")])
assert {"Auspex", "Comms"} <= held(r, 2) and not r.issues
# "one model with any": every option of the section on the SAME model,
# automatically and when a second model is asked for.
r = resolve(book, T, [ch("sMOneAny", "oMOneAnyA", pkg="PB"),
                      ch("sMOneAny", "oMOneAnyB", pkg="PB")])
assert {"Auspex", "Comms"} <= held(r, 0) and not r.issues
r = resolve(book, T, [ch("sMOneAny", "oMOneAnyA", models=[2], pkg="PB"),
                      ch("sMOneAny", "oMOneAnyB", models=[3], pkg="PB")])
assert {"Auspex", "Comms"} <= held(r, 2) and len(r.issues) == 1
# The automatic choice respects capacity too, whatever the loads.
models = oc.base_models(book.units[T])
for m in models[1:]:
    m.load = 5
sec = next(s for s in book.packages["PA"].sections if s.uid == "sAttMAny")
assert oc.apply_option(sec, sec.options[0], 2, models) == ((0, 1), [])

# "with one" holds across options: a second option cannot go on that model.
up3 = next(s for s in book.packages["PB"].sections if s.uid == "sMUpTo3")
two = replace(up3, options=(up3.options[0],
                            replace(up3.options[0], uid="oOther", label="X")))
models, used = oc.base_models(book.units[T]), {}
assert oc.apply_option(two, two.options[0], 1, models, [4], used)[0] == (4,)
assert oc.apply_option(two, two.options[1], 1, models, [4], used)[0] == (0,)

# --- explicit instances first -----------------------------------------------------
r = resolve(book, T, [ch("sAttMAny", "oAttMAny", 2, models=[None, 0])])
assert state(r, "sAttMAny").placed == (("oAttMAny", (0, 1)),) and not r.issues

# --- default placement is reproducible from 'placed' -------------------------------------
def roundtrip(b, unit_id, picks):
    """Re-resolving with the models the default chose gives the same unit."""
    r1 = resolve(b, unit_id, picks)
    placed = {(s.package, s.uid, o): ms for s in r1.sections if s.placeable
              for o, ms in s.placed}
    again = [Choice(c.package, c.section, c.option, c.count,
                    placed.get((c.package, c.section, c.option), ()))
             for c in picks]
    r2 = resolve(b, unit_id, again)
    assert loadout(r1) == loadout(r2) and r1.points == r2.points, unit_id
    assert len(r2.issues) == len(r1.issues), (r1.issues, r2.issues)


roundtrip(book, T, [ch("sRepOne", "oRepOneB"), ch("sRepAny", "oRepAny", 3),
                    ch("sAttMAny", "oAttMAny", 2), ch("sAttM1", "oAttM1", 2),
                    ch("sMUpTo3", "oMUpTo3", 3, pkg="PB")])

# --- army list: format and re-link keep the models ---------------------------------------
ref = al.make_ref(book, book.units[T], ch("sRepOne", "oRepOneA", models=[7]))
assert ref.models == [7] and ref.choice().models == (7,)
assert al.make_ref(book, book.units[T], ch("sRepOne", "oRepOneA")).models is None
army = al.ArmyList("P", units=[al.ListUnit("u1", book.uid, T, choices=[ref])])
d = al.to_dict(army)
assert d["units"][0]["choices"][0]["models"] == [7]
assert al.from_dict(d).units[0].choices[0].models == [7]
del d["units"][0]["choices"][0]["models"]                 # old lists load
assert al.from_dict(d).units[0].choices[0].models is None
d["units"][0]["choices"][0]["models"] = [1, None, 2]
assert al.from_dict(d).units[0].choices[0].models == [1, None, 2]
for bad in ([-1], "3", [1.5], [True]):
    d["units"][0]["choices"][0]["models"] = bad
    try:
        al.from_dict(d)
        raise AssertionError(f"ListFormatError expected for {bad!r}")
    except al.ListFormatError:
        pass
broken = copy.deepcopy(army.units[0])
broken.choices[0].section = "gone"
lr = links.link_unit(book, broken)
assert lr.relinked and lr.choices[0].models == [7]

# --- real data: random explicit placements never raise, defaults reproducible -----------
if not testpaths.USING_SYNTHETIC:
    import glob
    import os
    rnd = random.Random(7)
    n = 0
    for path in sorted(glob.glob(os.path.join(testpaths.DATA_DIR, "books",
                                              "*.json"))):
        b = ab.load_book(path)
        for u in b.units.values():
            base = resolve(b, u.id)
            picks = []
            for s in base.sections:
                if s.enabled and rnd.random() < 0.4:
                    sec = next(x for x in b.packages[s.package].sections
                               if x.uid == s.uid)
                    k = rnd.randint(1, max(1, min(2, s.caps.per_option)))
                    ms = tuple(rnd.choice([None, rnd.randrange(base.size + 1)])
                               for _ in range(k))
                    picks.append(Choice(s.package, s.uid,
                                        rnd.choice(sec.options).uid, k, ms))
            r = resolve(b, u.id, picks)
            for s in r.sections:
                for _, ms in s.placed:
                    assert all(0 <= i < r.size for i in ms), (u.name, s.label)
            roundtrip(b, u.id, [Choice(c.package, c.section, c.option,
                                       c.count) for c in picks])
            n += 1
    print(f"placement: {n} real units, random placements and round trips")
print("placement: OK")
