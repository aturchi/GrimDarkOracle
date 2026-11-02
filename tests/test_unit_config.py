"""app.unit_config: the option panel model on the synthetic book
(every panel mode, caps, chains, invalid choices kept and pruned,
placement kept while the count is unchanged); with real data every
option of every DAO / BB unit set to its limit and back."""
import testpaths
from grimdarkoracle.app.unit_config import UnitConfig
from grimdarkoracle.data import af_book as ab
from grimdarkoracle.data.resolve import Choice, resolve

if testpaths.USING_SYNTHETIC:
    book = ab.load_book(testpaths.book_path("synthetic00book01"))
    cfg = UnitConfig(book, "uTroop1")
    base = cfg.points
    sv = {s.uid: s for s in cfg.sections()}
    assert sv["sRepOne"].mode == "radio" and sv["sRepAny"].mode == "count"
    assert not sv["sChain"].enabled                     # no Sgt. Pistol yet
    try:
        cfg.set_count("PA", "sChain", "oChain", 1)
        raise AssertionError("disabled section accepted")
    except ValueError:
        pass
    # Radio: picking an option drops the other one of the section.
    cfg.select("PA", "sRepOne", "oRepOneB")
    cfg.select("PA", "sRepOne", "oRepOneA")
    assert cfg.section("PA", "sRepOne").selected == "oRepOneA"
    assert [c.option for c in cfg.choices] == ["oRepOneA"]
    assert cfg.section("PA", "sChain").enabled           # chain unlocked
    cfg.select("PA", "sChain", "oChain")
    assert cfg.points == resolve(book, "uTroop1", cfg.choices).points
    # Undo the chain's source: the chained choice is kept and reported.
    cfg.select("PA", "sRepOne", "oRepOneB")
    assert [c.option for c in cfg.invalid()] == ["oChain"] and cfg.issues
    assert [c.option for c in cfg.prune()] == ["oChain"]
    assert not cfg.invalid() and [c.option for c in cfg.choices] == \
        ["oRepOneB"]
    cfg.select("PA", "sRepOne", None)
    assert cfg.choices == () and cfg.points == base
    # Count: bounded per option and per section; the limit is live.
    st = cfg.section("PA", "sRepAny")
    lim = st.options[0].limit
    assert lim == st.total and cfg.set_count("PA", "sRepAny", "oRepAny",
                                             lim + 5) == lim
    assert cfg.section("PA", "sRepAny").options[0].applied == lim
    # All Rifles replaced: "up to two Rifles and Hand Weapons" has no
    # complete target left.
    assert not cfg.section("PA", "sUpTo2").enabled
    cfg.set_count("PA", "sRepAny", "oRepAny", 0)
    assert cfg.set_count("PA", "sUpTo2", "oUpTo2", 2) == 2
    # Section total shared by its options (Upgrade with up to two).
    capt = UnitConfig(book, "uCapt01")
    two = capt.section("PC", "sUpTo2")
    assert two.mode == "count" and two.total == 2 and len(two.options) > 1
    a, b = two.options[0].uid, two.options[-1].uid
    capt.set_count("PC", "sUpTo2", a, 1)
    assert capt.section("PC", "sUpTo2").options[-1].limit == 1
    assert capt.set_count("PC", "sUpTo2", b, 2) == 1
    try:
        cfg.set_count("PA", "sRepAny", "nope", 1)
        raise AssertionError("unknown option accepted")
    except KeyError:
        pass
    # Choices stay in book order whatever the order of the clicks.
    cfg.set_count("PA", "sRepAny", "oRepAny", 1)
    assert [c.section for c in cfg.choices] == ["sRepAny", "sUpTo2"]
    # Placement survives while the count is unchanged.
    placed = Choice("PB", "sMOne", book.packages["PB"].sections[1]
                    .options[0].uid, 1, (2,))
    jets = UnitConfig(book, "uJets01", [placed])
    other = jets.section("PB", "sMAll").options[0].uid
    jets.set_count("PB", "sMAll", other, 1)
    assert placed in jets.choices
    jets.set_count("PB", "sMOne", placed.option, 1)      # same count
    assert placed in jets.choices
    # Check sections: each option 0 / 1.
    cap = UnitConfig(book, "uCapt01")
    any_ = cap.section("PC", "sAny")
    assert any_.mode == "check" and all(o.limit == 1 for o in any_.options)
    for o in any_.options:
        cap.set_count("PC", "sAny", o.uid, 3)
    assert all(o.wanted == 1 for o in cap.section("PC", "sAny").options)
    try:
        UnitConfig(book, "nope")
        raise AssertionError("unknown unit accepted")
    except KeyError:
        pass
else:
    import time
    t0, n = time.time(), 0
    for uid in ("z8205ez2boggzs22", "78qp9l5alslt6yj8"):
        book = ab.load_book(testpaths.book_path(uid))
        for unit_id, unit in book.units.items():
            cfg = UnitConfig(book, unit_id)
            assert not any(s.uid in unit.disabled_sections
                           for s in cfg.sections())
            for sv in cfg.sections():
                if not sv.enabled:
                    continue
                for o in sv.options:
                    got = cfg.set_count(sv.package, sv.uid, o.uid, o.limit)
                    ref = resolve(book, unit_id, cfg.choices)
                    assert cfg.points == ref.points, (unit.name, sv.label)
                    assert not cfg.issues, (unit.name, sv.label, cfg.issues)
                    assert cfg.section(sv.package, sv.uid).options[
                        [x.uid for x in sv.options].index(o.uid)].applied == got
                    cfg.set_count(sv.package, sv.uid, o.uid, 0)
                    n += 1
            assert cfg.choices == () and cfg.points == unit.cost
    print(f"unit_config: {n} real options set and cleared in "
          f"{time.time() - t0:.1f}s")
print("unit_config: OK")
