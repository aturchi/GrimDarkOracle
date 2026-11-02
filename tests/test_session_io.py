"""app.session_io: save / load round trip of both sides (book and
list sources, choices, Combined, overrides, joined Hero, start state,
weapons off) and the setup; book snapshots used when the library's book
differs; notes; bad files. Synthetic library in temporary folders."""
import json
import os
import shutil
import tempfile

import testpaths
from grimdarkoracle.app import session_io as SIO
from grimdarkoracle.app import side_spec as SS
from grimdarkoracle.app.library import Library, digest
from grimdarkoracle.app.setup_model import Setup, SideSetup
from grimdarkoracle.app.unit_config import UnitConfig
from grimdarkoracle.data.resolve import Choice

tmp = tempfile.mkdtemp()
try:
    root = os.path.join(tmp, "af")
    shutil.copytree(testpaths.SYNTHETIC_DIR, root)
    lib = Library.load(root)
    B = "synthetic00book01"
    book = lib.books[B]
    cfg = UnitConfig(book, "uTroop1", [Choice("PA", "sRepOne", "oRepOneB")])
    left = SS.SideSpec(SS.UnitSpec(cfg, combined=True,
                                   cfg_b=UnitConfig(book, "uTroop1"),
                                   overrides=({"op": "set", "path": "quality",
                                               "value": 3},), label="Squad"),
                       SS.UnitSpec(UnitConfig(book, "uCapt01")))
    right = SS.book_side(book, "uJets01")
    ru, hero = left.resolved()
    rifle = next(w for w, _n in ru.weapons() if w.name == "Rifle")
    ss_left = SideSetup(wounds_taken=3, fatigued=True, hero_quality=3,
                        off=frozenset({rifle}))
    setup = Setup(attack="melee", strike_back=False, tie="attacker",
                  marks=("m1",), versatile=(("v1", 1),), buffs=(("att", "k"),),
                  spotter_tokens=2, distance=18)
    session = SIO.Session(setup, {
        "left": SIO.SideState(left, ss_left, "list", "/no/such/list.json"),
        "right": SIO.SideState(right, SideSetup(not_moved=False))},
        flipped=True)
    path = os.path.join(tmp, "s.json")
    SIO.save(session, lib, path)
    doc = json.load(open(path, encoding="utf-8"))
    assert doc["format"] == SIO.FORMAT and set(doc["books"]) == {B}
    assert doc["core_rules"] is not None and doc["sides"]["left"]["units"][1][
        "joined_to"] == "u1"
    assert doc["sides"]["left"]["state"]["off"][0]["name"] == "Rifle"

    # Same library: identical book, no notes, everything back.
    got, notes = SIO.load(path, Library.load(root))
    assert notes == [] and got.flipped and got.setup == setup
    gl, gr = got.sides["left"], got.sides["right"]
    r2, h2 = gl.spec.resolved()
    assert (r2.points, r2.size, r2.quality, r2.name) == \
        (ru.points, ru.size, 3, "Squad")
    assert h2.name == hero.name and gl.spec.unit.combined
    assert gl.spec.unit.cfg_b.choices == () and gl.spec.unit.cfg.choices
    assert gl.side_setup == ss_left and gl.source == "list" and \
        gl.list_path == "/no/such/list.json"
    assert gr.spec.resolved()[0].unit_id == "uJets01" and \
        not gr.side_setup.not_moved and gr.spec.hero is None

    # The library's book changed: the session's copy is used, with a note.
    bpath = os.path.join(root, "books", f"{B}.json")
    raw = json.load(open(bpath, encoding="utf-8"))
    raw["units"][0]["cost"] += 50
    json.dump(raw, open(bpath, "w", encoding="utf-8"))
    lib2 = Library.load(root)
    got, notes = SIO.load(path, lib2)
    assert len(notes) == 1 and "session's copy is used" in notes[0] and \
        "different content" in notes[0]
    r3 = got.sides["left"].spec.resolved()[0]
    assert r3.points == ru.points                       # old prices kept
    assert got.sides["left"].spec.unit.cfg.book is not lib2.books[B]
    again, notes2 = SIO.load(path, lib2)                # snapshot reused
    assert again.sides["left"].spec.unit.cfg.book is \
        got.sides["left"].spec.unit.cfg.book
    # Saving again writes the session's copy, not the library's file.
    p2 = os.path.join(tmp, "s2.json")
    SIO.save(got, lib2, p2)
    assert digest(json.load(open(p2))["books"][B]) == digest(doc["books"][B])

    # Core rules changed: noted.
    cpath = os.path.join(root, "rules", "common_2.json")
    core = json.load(open(cpath, encoding="utf-8"))
    core["rules"][0]["description"] += " (errata)"
    json.dump(core, open(cpath, "w", encoding="utf-8"))
    _s, notes = SIO.load(path, Library.load(root))
    assert any(n.startswith("core rules changed") for n in notes)

    # A side whose unit vanished is reported, the other side still loads.
    bad = json.load(open(path, encoding="utf-8"))
    bad["sides"]["right"]["units"][0].update(unit_id="gone", unit_name="Gone")
    bad["books"] = {}
    got, notes = SIO.from_dict(bad, Library.load(root))
    assert got.sides["right"] is None and got.sides["left"] is not None
    assert any(n.startswith("right side not restored") for n in notes)
    for wrong in ({"format": "x"}, [], None):
        try:
            SIO.from_dict(wrong, lib)
            raise AssertionError(f"{wrong!r} accepted")
        except SIO.SessionFormatError:
            pass
    empty = SIO.Session(Setup(), {"left": None, "right": None})
    SIO.save(empty, lib, path)
    got, notes = SIO.load(path, lib)
    assert got.sides == {"left": None, "right": None} and not notes
finally:
    shutil.rmtree(tmp)
if not testpaths.USING_SYNTHETIC:
    real = Library.load(testpaths.DATA_DIR)
    dao, bb = real.books["z8205ez2boggzs22"], real.books["78qp9l5alslt6yj8"]
    tmp = tempfile.mkdtemp()
    try:
        path = os.path.join(tmp, "real.json")
        for a_id in list(dao.units)[::4]:
            for b_id in list(bb.units)[::5]:
                sess = SIO.Session(Setup(), {
                    "left": SIO.SideState(SS.book_side(dao, a_id), SideSetup()),
                    "right": SIO.SideState(SS.book_side(bb, b_id),
                                           SideSetup())})
                SIO.save(sess, real, path)
                got, notes = SIO.load(path, real)
                assert not notes and got.sides["left"].spec.resolved()[0] == \
                    sess.sides["left"].spec.resolved()[0]
        print(f"session_io: real round trips ok, file "
              f"{os.path.getsize(path) // 1024} kB")
    finally:
        shutil.rmtree(tmp)
print("session_io: OK")
