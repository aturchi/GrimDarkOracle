# GrimDarkOracle

Exact attack, melee and morale mathematics for **Grimdark Future 3.6**
(One Page Rules), with two programs:

- **Attack Analyzer**: the exact laws (no simulation) of one unit
  attacking another: shooting, a charge with the full melee exchange
  (Impact, Counter, strikes, strike back, Fatigue, strikes last, melee
  result with Fear, Morale and Rout), damage spells with their casting
  roll; every special rule and spell of the 49 Army Forge books, with the
  table states as inputs; the attacker's weapon order (with a suggested
  best order) and Takedown target preferences, points metrics,
  comparison of upgrade variants, audit of the modifiers applied,
  printable cheat sheet, saved sessions.
- **List Editor**: army lists from the Army Forge books (upgrades, Hero
  joins, Combined Units, per-model placement, overrides, Force Org) and
  home-made units in local books, with a Rules Mapper for their custom
  rules (effects of their own, or behaving as an existing engine rule);
  printable army roster (HTML / text) and Inspect of an entry.

Independent fork of W40kDiviner. Python **>= 3.14**, standard library +
Tkinter only. License: GPL v3 (see `LICENSE`). Grimdark Future and the
Army Forge data are © OPR Games: the data is downloaded by the user for
personal use and is never part of this repository or of a build.

## The windows

**Attack Analyzer**: attacker on the left, target on the right, the attack in
the middle. Each side is a unit of an army book or an entry of a saved army
list, with its upgrades (one tab for the unit, one for a joined Hero), a
Combined option, its state at the start (wounds taken, Moved / Fatigued /
Shaken, Near terrain, Feat used, a Tough(9)+ Hero nearby) and the weapons
used. The middle column sets the attack: Shooting (distance, action, cover,
line of sight, Crossing Strike), Melee (charge distance; strike back, tie) or
Spell (tokens, Spell Conduit), deployed via Ambush this round, Spotter and AP
spotter tokens, Marks on the target, Versatile and token choices, spell
effects assumed cast (buffs, Marks, debuffs), buff and debuff rules, and the
attacker's weapon order and Takedown targets. *Analyse* opens a result
window: one row per weapon and the TOTAL, mean / median / quartiles,
distributions, Morale and points metrics (and the attacker's self-inflicted
wounds of Hazardous or No Retreat when they apply), audit of the modifiers,
CSV; results can be pinned and compared. Toolbar: Swap sides, Variants,
Compare pins, Save / Load session.

**List Editor**: the list on the left (name, points limit, Force Org, the
entries with their points, Add unit / Duplicate / Remove / Up / Down /
Inspect, the problems found); the selected entry on the right (label, notes,
Hero join, Combined copies, upgrades, per-model placement, overrides for house
rules). Toolbar: New, Open, Save, Undo / Redo, Local units (home-made units and
the Rules Mapper), Print roster.

In every window **Ctrl+F** finds a row in the lists shown (Enter: next match,
Esc: close), and every button explains itself when hovered. A step-by-step
description is in **`docs/USER_GUIDE.md`**.

## Getting started (from source)

```bash
python3 tools/af_fetch.py                 # download books + core rules (once)
python3 attack_analyzer.py                # Attack Analyzer
python3 list_editor.py [list.json]        # List Editor
```

Run the programs from the repository root. The first download takes a
couple of minutes (a polite delay between requests); later runs fetch
only the books whose version changed (`--force` fetches everything,
`--only "DAO Union"` some books).

## Updating the Army Forge data

Army Forge changes its books from time to time (points, units, rule texts). The
program's rule semantics (`grimdarkoracle/rules/semantics.json`, `spells.json`) were
written for a given text of every rule and spell, and store a fingerprint of that
text (`text_sha1`, the SHA-1 of the text with its spaces normalised; for an Army
Forge alias such as Enhanced Devout, mapped as Enhanced Brutal, the fingerprint of
its own text in `alias_sha1`; spells are keyed by id plus the first 10 hex digits),
never the text itself. Two different comparisons follow from that:

| Comparison | Against | Tool | Tells you |
|---|---|---|---|
| book diff | the **previous download** (`*.prev.json`, kept by `af_fetch`) | `af_fetch` (printed after a download that changed something), `tools/update_report.py` | what Army Forge changed: units, points, options, rule and spell texts (old and new) |
| text check (**`changed`**) | the text **the semantics were written for** (`text_sha1`) | `tools/rules_report.py`, and the "review" part of the update report | which mapped rules and spells may now compute something the new text no longer says |

So `changed` does NOT mean "changed since the last download": it means "the text the
books have now is not the text the mapping was made for". A text changed in an
earlier download and never reviewed stays `changed`; a text changed back to the
mapped one is `ok` again. Each book's own text is checked, and the report names the
books where it differs.

### The procedure

1. **Download**, from the folder of the programs you use (the data goes into that
   folder's `data/army_forge/`; `--out` to choose another):

   ```bash
   python3 tools/af_fetch.py            # books whose version changed
   python3 tools/af_fetch.py --force    # every book (Army Forge may fix a text
                                        # without changing the version)
   ```

   `+` marks a book whose content changed (its previous copy is kept as
   `books/<uid>.prev.json`), `=` one unchanged. Keep the `*.prev.json` files until
   the review below is done: the next download that changes the book replaces them.
2. **Read the update report** that `af_fetch` prints (again at any time:
   `python3 tools/update_report.py`, exit code 1 when something needs a look):
   what changed in each book, the rules and spells to review, the saved lists
   affected.
3. **Check the coverage**: `python3 tools/rules_report.py` (exit code 0 when every
   rule and spell is `ok`). For one rule: `python3 tools/rules_report.py --text
   "Mind Control"` prints its text in every book with its fingerprint and whether it
   matches the semantics.
4. **Act on the result**:

| Result | Meaning | What to do |
|---|---|---|
| exit code 0, all `ok` | every rule and spell has the text its semantics were written for | nothing |
| `changed` | the text differs from the mapped one (`mapped text …, text now: <book> …` names the books; `<rule> (its target)`: the text of the rule it is an alias of changed; `mapped text (none)`: an alias never fingerprinted, e.g. a user copy of `semantics.json` older than the alias fingerprints: `python3 tools/fingerprint.py --aliases` once the aliases are reviewed) | compare the old and the new text (update report, or `--text` and the `*.prev.json`). **Same meaning** (wording, typo): accept it with `python3 tools/fingerprint.py "<rule>"`, which stores the new fingerprint (`text_sha1`, or `alias_sha1` for an alias); for a spell, its key and `text_sha1` in `spells.json` by hand. **Different meaning**: the semantics must be rewritten (a development task). Until then the programs keep using the OLD semantics and say so in their status line |
| `unmapped` | a rule or spell with no semantics (new in Army Forge) | it has no effect in the results until it is mapped (development task); the analyses list it in their warnings |
| `todo` | known, not implemented yet | as `unmapped` |
| `undefined` | a unit uses a rule no book or core file defines | an Army Forge data problem; usually fixed by a later download |
| lists affected | saved lists whose choices were re-linked or no longer exist | open them in the List Editor: re-linked choices are kept; drop or replace the invalid ones |

A user copy `rules/semantics.json` / `rules/spells.json` next to the program (see
below) is used instead of the shipped one; `tools/fingerprint.py` writes to the file
the programs read (that copy when present, else the shipped one; `--semantics` to
choose).

## Folders next to the program

| Folder / file | Content |
|---|---|
| `data/army_forge/` | Army Forge download (`af_fetch`), personal use only |
| `lists/` | army lists (List Editor) |
| `books_local/` | home-made units (local books, uid prefix `local-`) |
| `sessions/` | Attack Analyzer sessions |
| `rules/semantics.json`, `rules/spells.json` | optional user copies of the shipped rule and spell semantics (in a `rules/` folder next to the program); when present they are used instead |

Sessions store a copy of the books they were made with, so they reopen
on the same data after an update.

## Building the executables

```bash
pip install pyinstaller
pyinstaller GrimDarkOracle.spec           # -> dist/
```

Four one-file executables: `AttackAnalyzer`, `ListEditor` (windows) and
`af_fetch`, `update_report` (console).
Build with Python >= 3.14 on the system the executables are for. Copy
them into a folder of their own and run `af_fetch` there first: the
folders above are created next to the executables. On Linux, a Python
whose Tcl/Tk libraries PyInstaller cannot find (e.g. a uv-managed
interpreter) builds executables that need those libraries at run time.

## Tests

```bash
python3 tests/run_all.py                  # synthetic data, no download needed
python3 tests/run_all.py --real_data      # on the download in data/army_forge
```

The window tests use the real Tk when a display is available, otherwise
a stub toolkit.

## Status and limitations

- The mathematics cover the core rules and every rule and spell of the
  49 Army Forge books downloaded in November 2026. Rules and spells that
  Army Forge adds or changes later have no effect until they are mapped
  (`tools/rules_report.py` lists them). Rules that act outside one attack
  (movement, deployment, activation order) are recorded as having no
  combat effect; table states (distances, cover, terrain, tokens, a Feat
  used) are inputs of the Analyzer.
- The programs cannot see the table: distances, line of sight, cover,
  terrain, aura ranges and tokens are set by the player.
- Advanced (paid) rules are not implemented.
- The executables were built and tested on Linux only.

## Documentation

| File | Content |
|---|---|
| `docs/USER_GUIDE.md` | how to use the two programs (start here) |

## Layout

```
attack_analyzer.py  list_editor.py  GrimDarkOracle.spec
grimdarkoracle/  data/ (Army Forge adapter, options, lists)  rules/ (semantics)
             engine/ (exact maths)  app/ (pure program logic)  ui/ (Tk views)
tools/       af_fetch, update_report, rules_report, fingerprint, af_survey
tests/       run_all + test files per module or feature, synthetic Army Forge data
docs/        USER_GUIDE
```
