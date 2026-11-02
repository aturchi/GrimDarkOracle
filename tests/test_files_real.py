"""Files on real data: army lists and Analyzer sessions
built from whole books (DAO Union / Battle Brothers with --real_data,
else the synthetic book), saved, loaded and compared; then the same files
after a simulated Army Forge update (a .prev.json copy and a changed
book): re-linked and lost choices, the update report, sessions resumed on
their own snapshots.
"""
import json
import os
import shutil
import tempfile

import testpaths
import realkit
from grimdarkoracle.app import session_io as SIO
from grimdarkoracle.app import side_spec as SS
from grimdarkoracle.app import update_check as UC
from grimdarkoracle.app.library import Library
from grimdarkoracle.app.setup_model import Setup, SideSetup
from grimdarkoracle.data import army_list as AL
from grimdarkoracle.data import list_resolve as LR

SALTS = 3


def resolved(army, books) -> dict:
    res = LR.resolve_list(army, books)
    return {k: (e.unit, tuple(e.issues)) for k, e in res.entries.items()}


def round_trips(lib, uids, tmp):
    """Lists and sessions: save, load, compare. Returns the files
    of salt 0 for the update step."""
    files = {}
    for salt in range(SALTS):
        armies = [realkit.army(lib, uid, salt + i, f"L{i}{salt}")
                  for i, uid in enumerate(uids)]
        for i, army in enumerate(armies):
            p = os.path.join(tmp, f"list{i}{salt}.json")
            AL.save(army, p)
            back = AL.load(p)
            assert AL.to_dict(back) == AL.to_dict(army)
            assert resolved(back, lib.books) == resolved(army, lib.books)
            if salt == 0:
                files[f"list{i}"] = p
        # Sessions: entry k of one list against entry k of the other.
        a, b = armies
        for n, (la, lb) in enumerate(zip(a.units, b.units)):
            if la.joined_to or lb.joined_to:
                continue                    # inside their host's side
            left, _ = SS.entry_side(lib.books, a, la.key)
            right, _ = SS.entry_side(lib.books, b, lb.key)
            setup = Setup(attack=("shooting", "melee")[n % 2],
                          distance=6 + n % 20, strike_back=bool(n % 3))
            ss = SideSetup(wounds_taken=n % 2, fatigued=bool(n % 2))
            session = SIO.Session(setup, {
                "left": SIO.SideState(left, ss, "list", "x.json"),
                "right": SIO.SideState(right, SideSetup())})
            p = os.path.join(tmp, f"s{salt}_{n}.json")
            SIO.save(session, lib, p)
            got, notes = SIO.load(p, lib)
            assert notes == [] and got.setup == setup, notes
            for k in ("left", "right"):
                assert got.sides[k].spec.resolved() == \
                    session.sides[k].spec.resolved(), (salt, n, k)
            assert got.sides["left"].side_setup == ss
            if salt == 0 and "session" not in files:
                files["session"] = (p, session)
    return files


def simulate_update(root, uid, army_path):
    """Keep the old book as .prev.json and change the current one: the
    option of a saved choice gets a new uid (same label: re-linked), the
    price of another goes up by 5, and one unit of the list is removed.
    Returns (removed unit name, re-linked option label)."""
    path = os.path.join(root, "books", f"{uid}.json")
    shutil.copy(path, UC.prev_path(path))
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    army = AL.load(army_path)
    with_choices = [lu for lu in army.units if lu.choices and
                    not lu.joined_to and not lu.combined and
                    not any(x.joined_to == lu.key for x in army.units)]
    keep, gone = with_choices[0], with_choices[-1]
    assert keep is not gone
    ref = keep.choices[0]
    for pkg in raw["upgradePackages"]:
        for sec in pkg["sections"]:
            for opt in sec["options"]:
                if (pkg["uid"], sec["uid"], opt["uid"]) == \
                        (ref.package, ref.section, ref.option):
                    opt["uid"] = "t25-new-uid"
    raw["units"] = [u for u in raw["units"] if u["id"] != gone.unit_id]
    raw["versionString"] = raw.get("versionString", "") + "-t25"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(raw, fh)
    return gone, keep, ref


def after_update(root, uids, files, tmp):
    lists = os.path.join(tmp, "lists")
    os.makedirs(lists)
    for k in ("list0", "list1"):
        shutil.copy(files[k], lists)
    gone, keep, ref = simulate_update(root, uids[0], files["list0"])
    lib = Library.load(root)
    # The list: one choice re-linked by its labels, one unit missing.
    army = AL.load(files["list0"])
    res = LR.resolve_list(army, lib.books)
    e = res.entries[keep.key]
    assert e.unit is not None and e.link.relinked and not e.link.invalid
    assert res.entries[gone.key].unit is None
    # The update report names the book and the list to look at.
    rep = UC.build(lib, lists_dir=lists)
    assert [b.uid for b in rep.books] == [uids[0]], rep.books
    assert any(gone.unit_name in u for u in rep.books[0].units_removed)
    notes = dict(rep.lists)
    name = next(n for n in notes if n.startswith(army.name + " "))
    assert any("re-linked" in x for x in notes[name]), notes[name]
    assert any(gone.unit_name in x and "no longer exists" in x
               for x in notes[name]), notes[name]
    # Sessions resume on the books they were saved with.
    spath, session = files["session"]
    got, snotes = SIO.load(spath, lib)
    if session.sides["left"].spec.unit.cfg.book.uid == uids[0]:
        assert any("session's copy is used" in x for x in snotes), snotes
    for k in ("left", "right"):
        assert got.sides[k].spec.resolved() == \
            session.sides[k].spec.resolved()
    return len(rep.lists)


def main():
    lib, uids = realkit.library()
    tmp = tempfile.mkdtemp()
    try:
        files = round_trips(lib, uids, tmp)
        if uids[0] == uids[1]:
            print("files: round trips on the synthetic book; the update "
                  "step needs two books (--real_data)")
            return
        root = realkit.tmpdir_copy(testpaths.DATA_DIR, tmp, uids)
        after_update(root, uids, files, tmp)
        print(f"files: lists and sessions round-trip on "
              f"{', '.join(lib.books[u].name for u in uids)} "
              f"({SALTS} configurations each); after a simulated update "
              "the list re-links, reports the lost unit, and sessions "
              "resume on their snapshots")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
