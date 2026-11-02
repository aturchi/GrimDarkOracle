"""app.roster_sheet and the unit_sheet parts it reuses: the
header (points / limit, Force Org, books), problems (Force Org, list
issues, missing units), entries in list order with the list labels, a
joined Hero printed with its host (points added), a second Hero joined
to the same host printed alone with its issue, Combined Units, a guest
whose host is missing, choices that no longer link, the rule glossary
printed once, the spells of a Caster's book; text and HTML; entry_sheet
for Inspect. Synthetic data; every DAO / BB unit in one roster with
--real_data."""
from dataclasses import replace

import testpaths
from grimdarkoracle.app import roster_sheet as RS
from grimdarkoracle.app import unit_sheet as US
from grimdarkoracle.app.library import Library
from grimdarkoracle.data import army_list as AL
from grimdarkoracle.data.list_resolve import resolve_list
from grimdarkoracle.data.resolve import Choice

lib = Library.load(testpaths.SYNTHETIC_DIR)
B = "synthetic00book01"
book = lib.books[B]


def lu(key, unit_id, label="", choices=(), **kw):
    u = book.units[unit_id]
    refs = [AL.make_ref(book, u, Choice(*c)) for c in choices]
    return AL.ListUnit(key, B, unit_id, u.name, label, choices=refs, **kw)


psychic = ("PC", "sOne", "oOneA")
lost = AL.ChoiceRef("PX", "sX", "oX", 1, "Gone section", 1, "Gone option")
army = AL.ArmyList("Test Army", points_limit=200, books={B: book.version},
                   units=[
    lu("u1", "uTroop1", "Squad"),
    lu("u2", "uCapt01", "Captain", (psychic,), joined_to="u1"),
    lu("u3", "uCapt01", "Second", joined_to="u1"),
    lu("u4", "uJets01", combined=True),
    AL.ListUnit("u5", B, "uNope", "Ghost Unit"),
    lu("u6", "uCapt01", "Orphan", joined_to="u5"),
    lu("u7", "uWalk01")])
army.units[6].choices.append(lost)
res = resolve_list(army, lib.books)
ro = RS.build(lib, army, res)

# --- header and problems ------------------------------------------------------------------
head = dict(ro.header)
assert head["Points"] == f"{res.points} / 200" and res.points > 200
assert head["Force Org"] == "on" and head["Entries"] == "7"   # as the editor
assert head["Books"] == f"{book.name} {book.version}"
assert any("exceed the limit of 200" in p for p in ro.problems)
assert any("Heroes" in p for p in ro.problems)            # Force Org on
assert "Ghost Unit: unit not found, not printed" in ro.problems
off = RS.build(lib, replace(army, force_org=False), res)
assert dict(off.header)["Force Org"] == "off"
assert not any("Heroes" in p for p in off.problems)

# --- entries --------------------------------------------------------------------------------
keys = [e.key for e in ro.entries]
assert keys == ["u1", "u3", "u4", "u6", "u7"], keys       # list order
squad = ro.entries[0]
assert squad.points == res.entries["u1"].points + res.entries["u2"].points
assert squad.sheet.title.startswith("Squad + Captain  [11]")
assert any(r[0] == "Caster(1)" for r in squad.sheet.rules)
second = ro.entries[1].sheet
assert second.title.startswith("Second  [1]")
assert any("already has another Hero joined" in n for n in second.notes)
assert "[combined]" not in ro.entries[2].sheet.title and any(
    "Combined Unit" in v for _k, v in ro.entries[2].sheet.stats)
assert ro.entries[3].sheet.title.startswith("Orphan")      # host missing
assert any("joined to missing unit" in n for n in ro.entries[3].sheet.notes)
assert any("Gone option" in n for n in ro.entries[4].sheet.notes)

# --- glossary and spells --------------------------------------------------------------------
labels = [r[0] for r in ro.rules]
assert len(labels) == len(set(labels)) and "Caster(1)" in labels
assert labels == sorted(labels, key=str.lower)
assert [b for b, _rows in ro.spells] == [book.name]
assert [s[0] for s in ro.spells[0][1]] == [s.name for s in book.spells]

# --- text and HTML --------------------------------------------------------------------------
txt = RS.to_text(ro)
assert txt.startswith("Test Army\n=========\nPoints: ")
assert "\n1. Squad + Captain" in txt and "\n5. Siege Walker" in txt
assert txt.count("\nRules: ") == 5 and "\nRules\n=====\n" in txt
caster_text = next(r[2] for r in ro.rules if r[0] == "Caster(1)")
assert txt.count(caster_text) == 1                         # printed once
assert f"Spells ({book.name})" in txt and "\nNotes\n" in txt
html = RS.to_html(ro)
assert html.count('<div class="entry">') == 5
assert "<h2>1. Squad + Captain" in html and "<h3>Weapons</h3>" in html
assert html.count(US.esc(caster_text)) == 1
assert "GrimDarkOracle army roster" in html and 'class="warn"' in html
assert RS.render(ro, "a.HTM") == html and RS.render(ro, "a.txt") == txt
clean = AL.ArmyList("Ok", points_limit=2000, books={B: book.version},
                    units=[lu("u1", "uTroop1")])
cro = RS.build(lib, clean, resolve_list(clean, lib.books))
assert cro.problems == [] and "No problems" in RS.to_text(cro)
assert "No problems" in RS.to_html(cro) and cro.spells == []

# --- unit_sheet parts -----------------------------------------------------------------------
s = squad.sheet
assert US.to_text(s) == "\n".join(US.text_lines(s)) + "\n"
assert "Rules: " not in US.to_text(s) and "\nSpells\n" in US.to_text(s)
assert "\nSpells\n" not in "\n".join(US.text_lines(s, texts=False))
assert US.rule_names(s).count("Caster(1)") == 1

# --- Inspect of one entry -------------------------------------------------------------------
assert RS.entry_sheet(lib, army, res, "u1").title == squad.sheet.title
assert RS.entry_sheet(lib, army, res, "u2").title.startswith("Captain  [1]")
assert RS.entry_sheet(lib, army, res, "u5") is None
assert RS.entry_sheet(lib, army, res, "nope") is None

# --- real data: every DAO / BB unit in one roster ------------------------------------------
if not testpaths.USING_SYNTHETIC:
    rl = Library.load(testpaths.DATA_DIR)
    for uid in ("z8205ez2boggzs22", "78qp9l5alslt6yj8"):
        b = rl.books[uid]
        big = AL.ArmyList(b.name, books={uid: b.version}, units=[
            AL.ListUnit(f"u{i}", uid, u.id, u.name)
            for i, u in enumerate(b.units.values())])
        r = RS.build(rl, big, resolve_list(big, rl.books))
        assert len(r.entries) == len(b.units) and r.rules
        assert RS.to_html(r).count('<div class="entry">') == len(b.units)
        assert all(st == "ok" for _l, st, _t in r.rules), b.name
    print("roster_sheet: DAO / BB rosters OK")
print("roster_sheet: OK")
