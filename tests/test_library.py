"""app.library: loading books, core rules and the registry from an
af_fetch folder; missing / broken files become warnings; army lists
resolved on the loaded books."""
import os
import shutil
import tempfile

import testpaths
from grimdarkoracle.app.library import Library
from grimdarkoracle.data import army_list
from grimdarkoracle.data.army_list import ArmyList, ListUnit

lib = Library.load(testpaths.SYNTHETIC_DIR)
assert not lib.warnings, lib.warnings
assert [b.uid for b in lib.catalogue()] == ["synthetic00book01"]
info = lib.catalogue()[0]
assert info.units == len(lib.units(info.uid)) > 0
assert lib.units("nope") == []
assert lib.reg is not None and lib.core and set(lib.core) <= set(lib.reg.defs)

tmp = tempfile.mkdtemp()
try:
    # Empty folder: an empty library that says why.
    empty = Library.load(tmp)
    assert not empty.books and len(empty.warnings) == 2 and empty.reg
    # A broken book is skipped, a .prev.json is never read, the rest loads.
    shutil.copytree(os.path.join(testpaths.SYNTHETIC_DIR, "rules"),
                    os.path.join(tmp, "rules"))
    os.makedirs(os.path.join(tmp, "books"))
    src = testpaths.book_path("synthetic00book01", testpaths.SYNTHETIC_DIR)
    shutil.copy(src, os.path.join(tmp, "books", "synthetic00book01.json"))
    with open(os.path.join(tmp, "books", "old.prev.json"), "w") as fh:
        fh.write("{never read")
    with open(os.path.join(tmp, "books", "bad.json"), "w") as fh:
        fh.write("{not json")
    part = Library.load(tmp)
    assert list(part.books) == ["synthetic00book01"]
    assert len(part.warnings) == 1 and part.warnings[0].startswith("bad.json")
    # Army lists resolve on the library's books.
    army = ArmyList("t", books={"synthetic00book01": info.version},
                    units=[ListUnit("u1", "synthetic00book01", "uTroop1")])
    path = os.path.join(tmp, "t.json")
    army_list.save(army, path)
    got, res = part.load_list(path)
    assert got.name == "t" and res.entries["u1"].unit.name == "Line Troopers"
finally:
    shutil.rmtree(tmp)
if not testpaths.USING_SYNTHETIC:
    real = Library.load(testpaths.DATA_DIR)
    assert len(real.books) >= 49 and not [w for w in real.warnings
                                          if "not loaded" in w]
    print(f"library: {len(real.books)} real books")
print("library: OK")
