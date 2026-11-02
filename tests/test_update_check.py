"""data.book_diff + app.update_check: a synthetic book
and core rules changed against their previous copies, the implemented
rules / spells to review (a sub-faction spell variant is not a change),
the saved lists affected, the af_fetch report and tools/update_report."""
import copy
import io
import json
import os
import shutil
import sys
import tempfile
from contextlib import redirect_stdout
from dataclasses import replace

import testpaths
from spellkit import book as sbook, DOC, K
from unitkit import SEM, CORE
from grimdarkoracle.app import update_check as UC
from grimdarkoracle.app.library import Library
from grimdarkoracle.data import af_book as ab
from grimdarkoracle.data import army_list as AL
from grimdarkoracle.data import book_diff as BD
from grimdarkoracle.data.army_list import ArmyList, ChoiceRef, ListUnit
from grimdarkoracle.rules import registry, spells as S

sys.path.insert(0, os.path.join(testpaths.REPO_ROOT, "tools"))
import af_fetch                                      # noqa: E402
import update_report                                 # noqa: E402

B = "synthetic00book01"
tmp = tempfile.mkdtemp()
root = os.path.join(tmp, "army_forge")
shutil.copytree(testpaths.SYNTHETIC_DIR, root,
                ignore=shutil.ignore_patterns("*.prev.json"))
bpath = os.path.join(root, "books", f"{B}.json")
cpath = os.path.join(root, "rules", "common_2.json")
lists = os.path.join(tmp, "lists")
os.makedirs(lists)


def raw(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write(path, d):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(d, fh)


# Semantics re-hashed on the synthetic texts: nothing to review at start.
sem = copy.deepcopy(SEM)
core0 = ab.load_core_rules(cpath)
for rid, e in sem["rules"].items():
    if rid in core0:
        e["text_sha1"] = registry.text_sha1(core0[rid].description)
lib = Library.load(root, semantics=sem)
assert UC.review(lib) == [] and UC.startup_note(lib) == ""
assert UC.status_text(lib, "ok") == ("ok", False)
assert UC.build(lib).books == []                     # no previous copy

# A list saved on the old revision.
old = raw(bpath)
pa = next(p for p in old["upgradePackages"] if p["uid"] == "PA")
s_rep1 = next(s for s in pa["sections"] if s["uid"] == "sRep1")
army = ArmyList("Alpha", units=[
    ListUnit("u1", B, "uTroop1", unit_name="Line Troopers", choices=[
        ChoiceRef("PA", "sRep1", "oRep1a", 1, s_rep1["label"], 1,
                  s_rep1["options"][0]["label"])]),
    ListUnit("u2", B, "uWalk01", unit_name="Siege Walker")])
AL.save(army, os.path.join(lists, "alpha.json"))
with open(os.path.join(lists, "broken.json"), "w") as fh:
    fh.write("{")
assert [n for n, _x in UC.list_notes(lib, lists)] == ["broken.json"]

# --- a new revision --------------------------------------------------------------------------
shutil.copy(bpath, UC.prev_path(bpath))
shutil.copy(cpath, UC.prev_path(cpath))
new = copy.deepcopy(old)
new["versionString"] = "3.6.1"
units = {u["id"]: u for u in new["units"]}
units["uTroop1"]["quality"] = 3
units["uTroop1"]["cost"] = 110
new["units"] = [u for u in new["units"] if u["id"] != "uWalk01"]
extra = copy.deepcopy(units["uJets01"])
extra["id"], extra["name"] = "uNew0001", "Sky Lancers"
new["units"].append(extra)
pkg = next(p for p in new["upgradePackages"] if p["uid"] == "PA")
sec = next(s for s in pkg["sections"] if s["uid"] == "sRep1")
sec["options"][0]["uid"] = "oRep1z"                  # same label: re-link
for c in sec["options"][0]["costs"]:
    if c["unitId"] == "uTroop1":
        c["cost"] += 5
rule = new["specialRules"][0]
rule["description"] = rule.get("description", "") + " Changed."
new["spells"][0]["effect"] += " Now 3 hits."
write(bpath, new)
core = raw(cpath)
core["rules"][0]["description"] = core["rules"][0].get("description",
                                                        "") + " New."
write(cpath, core)
lib = Library.load(root, semantics=sem)

d = BD.diff_books(ab.load_book(UC.prev_path(bpath)), lib.books[B])
lines = d.lines()
assert lines[0] == f"{old['name']}: {old['versionString']} -> 3.6.1"
assert d.units_added == ["Sky Lancers"] and d.units_removed == ["Siege Walker"]
troop = dict(d.units)["Line Troopers"]
assert "Quality 4+ -> 3+" in troop and "points 100 -> 110" in troop
assert any(x.startswith("option price: Replace Hand Weapon / ") and
           x.endswith("5 -> 10 pts") for x in troop), troop
assert d.rules == [f"rule changed: {rule['name']}"]
assert d.spells == ["spell changed: Bolt"]
assert not d.empty
# Units matched by id, then by name; a renamed unit keeps its id.
cur = lib.books[B]
lt = cur.units["uTroop1"]
moved = replace(cur, units={("uMoved01" if k == "uTroop1" else k):
                            (replace(u, id="uMoved01") if k == "uTroop1"
                             else u) for k, u in cur.units.items()})
dm = BD.diff_books(cur, moved)
assert not dm.units_added and not dm.units_removed  # same name: matched
renamed = replace(cur, units={k: (replace(u, name="Line Guards")
                                  if k == "uTroop1" else u)
                              for k, u in cur.units.items()})
assert BD.diff_books(cur, renamed).units == [("Line Guards",
                                              ["renamed from Line Troopers"])]
# Sections the unit does not get are not its options.
offered = BD._options(cur, lt)
gone = replace(lt, disabled_sections=frozenset({"sRep1"}))
assert {k for k in offered if k[0] == s_rep1["label"]} and not \
    {k for k in BD._options(cur, gone) if k[0] == s_rep1["label"]}
same = BD.diff_books(lib.books[B], lib.books[B])
assert same.empty and same.lines()[-1].startswith("  no difference")
first_core = core["rules"][0]
rep = UC.build(lib, lists_dir=lists)
assert [x.uid for x in rep.books] == [B]
assert rep.core == [f"core rule changed: {first_core['name']}"]
assert any(first_core["name"] in x for x in rep.review), rep.review
assert not rep.clean and "may be outdated" in UC.startup_note(lib)
text, warn = UC.status_text(lib, "ok")
assert warn and text == UC.startup_note(lib)
notes = dict(rep.lists)["Alpha (alpha.json)"]
assert any("re-linked" in n for n in notes), notes
assert notes[0].startswith("Line Troopers: re-linked "), notes
assert len(notes) == 2 and notes[1].startswith("Siege Walker: lost "), notes
assert rep.unmapped == [] and rep.unmapped_total >= 0
text = UC.to_text(rep)
for part in ("== Changes since the previous download", "unit added: Sky "
             "Lancers", "== Implemented rules and spells to review",
             "== Saved army lists", "broken.json", "not readable"):
    assert part in text, part
assert not UC.Report(lists=[("x", ["y"])]).clean
assert not UC.Report(unreadable=["z"]).clean and UC.Report().clean
only = UC.build(lib, uids={"nope"}, lists_dir=None)
assert only.books == [] and only.lists == []

# A previous copy that cannot be read.
shutil.move(UC.prev_path(bpath), bpath + ".keep")
with open(UC.prev_path(bpath), "w") as fh:
    fh.write("{")
r2 = UC.build(lib)
assert r2.books == [] and any("not readable" in x for x in r2.unreadable)
shutil.move(bpath + ".keep", UC.prev_path(bpath))

# --- spells: a text change vs a sub-faction variant -------------------------------------------
doc = copy.deepcopy(DOC)


class SLib:
    reg = registry.RuleRegistry(SEM, CORE, [sbook])
    sreg = S.SpellRegistry(doc, reg, [sbook])


assert UC.spell_review(SLib, [sbook]) == []
ward = next(s for s in sbook.spells if s.name == "Ward")
variant = replace(ward, effect="Sub-faction: other text.")
b2 = replace(sbook, uid="sub", name="Sub", spells=(variant,))
assert UC.spell_review(SLib, [sbook, b2]) == []      # a variant: no change
bolt = next(s for s in sbook.spells if s.name == "Bolt")
b3 = replace(sbook, spells=tuple(replace(s, effect="New text.") if s is bolt
                                 else s for s in sbook.spells))
assert UC.spell_review(SLib, [b3]) == \
    [f"spell Bolt ({sbook.name}): text changed, review its semantics"]
assert K["Bolt"] in doc["spells"]
assert UC.unmapped(SLib, [b2])[-1] == "spell Ward (Sub)"   # the variant
doc2 = copy.deepcopy(DOC)
doc2["spells"][K["Bolt"]]["rules"] = [["No Such Rule", None]]


class BLib:
    reg = registry.RuleRegistry(SEM, CORE, [sbook])
    sreg = S.SpellRegistry(doc2, reg, [sbook])


assert UC.spell_review(BLib, [sbook]) == \
    [f"spell Bolt ({sbook.name}): a rule it names no longer resolves"]

# --- af_fetch report and tools/update_report --------------------------------------------------
out = af_fetch.report(root, [B], lists)
assert "== Changes since the previous download" in out
assert "unit added: Sky Lancers" in out
empty = af_fetch.report(os.path.join(tmp, "nothing"), [], None)
assert empty.startswith("core rules not loaded") and "nothing to check" in \
    empty
buf = io.StringIO()
with redirect_stdout(buf):
    code = update_report.main(["--data", root, "--lists", lists])
assert code == 1 and "unit added: Sky Lancers" in buf.getvalue()
with redirect_stdout(io.StringIO()):
    assert update_report.main(["--data", root, "--only", "zzz"]) == 2
    assert update_report.main(["--data", root, "--only", B,
                               "--lists", os.path.join(tmp, "none")]) == 1
print("update check: OK")
