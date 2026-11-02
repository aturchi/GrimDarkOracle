"""Files written before the program was renamed GrimOracle -> GrimDarkOracle
 still load: army lists, sessions, user copies of the rule and
spell semantics (their old format tags) and local books (their old keys,
renamed on read). New files are written with the new names only."""
import copy
import json
import os
import tempfile

import testpaths                                    # noqa: F401 (sys.path)
from grimdarkoracle.app import session_io as SIO
from grimdarkoracle.app.library import Library
from grimdarkoracle.data import army_list as AL
from grimdarkoracle.data import local_books as LB
from grimdarkoracle.rules import registry
from grimdarkoracle.rules import spells as S
from grimdarkoracle.rules import vocab as V

# --- army lists ---------------------------------------------------------------
old = {"format": "grimoracle-list/1", "name": "Old", "units": []}
assert AL.from_dict(old).name == "Old"
assert AL.to_dict(AL.from_dict(old))["format"] == "grimdarkoracle-list/1"
try:
    AL.from_dict({"format": "other/1", "units": []})
except AL.ListFormatError as e:
    assert "'other/1'" in str(e)
else:
    raise AssertionError("an unknown format was accepted")

# --- sessions: the old tag passes the format check ----------------------------
assert "grimoracle-session/1" in SIO.LEGACY_FORMATS
assert SIO.FORMAT == "grimdarkoracle-session/1"
try:
    SIO.from_dict({"format": "other/1"}, None)
except SIO.SessionFormatError:
    pass
else:
    raise AssertionError("an unknown session format was accepted")

# --- semantics and spells documents --------------------------------------------
sem = registry.load_semantics()
assert sem["format"] == V.FORMAT == "grimdarkoracle-semantics/1"
legacy = dict(sem, format="grimoracle-semantics/1")
assert registry.validate(legacy) == []
assert registry.validate(dict(sem, format="other/1"))
assert S.validate({"format": "grimoracle-spells/1", "spells": {}}) == []
assert S.validate({"format": "other/1", "spells": {}})

# --- local books: old keys renamed on read ------------------------------------
raw = {"uid": "local-x", "grimoracle_retired": ["u1"],
       "specialRules": [{"id": "local-x-r1", "name": "R",
                         "grimoracle_semantics": {"impl": "todo"}},
                        {"id": "local-x-r2", "name": "Q"}]}
mig = LB.migrate(copy.deepcopy(raw))
assert mig[LB.RETIRED_KEY] == ["u1"] and "grimoracle_retired" not in mig
assert LB.semantics_of(mig) == {"local-x-r1": {"impl": "todo"}}
assert "grimoracle_semantics" not in mig["specialRules"][0]
assert LB.migrate(copy.deepcopy(mig)) == mig        # idempotent

# --- a local book saved before the rename, through the Library --------------
with tempfile.TemporaryDirectory() as tmp:
    book = LB.new_book("Old Book")
    rid = LB.custom_rule(book, "Old Rule", "Synthetic: +1 to hit.")["id"]
    LB.set_semantics(book, rid, {"impl": "composed", "effects": [
        {"primitive": "hit_mod", "value": 1}]})
    path = LB.save(book, tmp)
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    rule = LB.find_rule(doc, rid)
    rule["grimoracle_semantics"] = rule.pop(LB.SEM_KEY)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)
    lib = Library.load(testpaths.SYNTHETIC_DIR, local_dir=tmp)
    assert rid in lib.reg.entries, lib.warnings
    assert lib.reg.entries[rid].effects[0].primitive == "hit_mod"
    assert os.path.basename(path).endswith(".json")
    # the same book as a session snapshot (Library.adopt)
    lib2 = Library.load(testpaths.SYNTHETIC_DIR, local_dir=os.path.join(
        tmp, "none"))
    _book, _note = lib2.adopt(copy.deepcopy(doc))
    assert rid in lib2.reg.entries

print("test_rename_compat OK")
