# GrimDarkOracle — User guide

GrimDarkOracle computes, for **Grimdark Future 3.6**, what an attack can do: the exact
probabilities of hits, wounds, models killed, Morale Tests, Shaken and Rout, with no
simulation. It has two programs that share the same army data and the same files:

| Program | Use it to |
|---|---|
| **Attack Analyzer** | study one unit attacking another before or after a game |
| **List Editor** | build and save army lists (and home-made units) |

Every special rule and spell of the core rules and of the 49 Army Forge books
(November 2026) is in the computations; what the program cannot see on the table
(distances, cover, terrain, tokens) is an input (see "Limits" at the end).

## 1. First start

1. Download the Army Forge data once: `python3 tools/af_fetch.py` from the program
   folder (with the executables: run `af_fetch`). It takes a couple of minutes; later
   runs fetch only what changed and print a report of the changes.
2. Start a program: `python3 attack_analyzer.py` or `python3 list_editor.py` (or
   the executables of the same names).

The status line at the bottom of each window says how many army books were loaded, or
what is missing (no data: run `af_fetch`; rules changed in Army Forge: run
`tools/update_report.py`).

Everywhere: hover a button or a field for a short explanation; **Ctrl+F** finds a row
in the lists of the window (Enter: next match, Esc: close); Undo / Redo cover every
change in the List Editor.

## 2. Attack Analyzer

The window has three columns: the **Attacker** on the left, the **Attack** setup in the
middle, the **Target** on the right. The line at the top reads, for example,
"Battle Suits (150 pts) shoots Battle Brothers (135 pts)".

**Choosing the two units** (left and right columns, the same for both):

- *Army book*: pick the book, then the unit in the list. *Army list*: open one or more
  saved lists and pick an entry (its joined Hero and Combined copies come with it).
- *Joined Hero* adds a Hero to the unit; *Combined* doubles a multi-model unit.
- The *Unit* / *Hero* tabs show the upgrade sections, as in Army Forge: drop-down
  menus for "choose one" sections, counters for "any" sections. The points follow.
- *Inspect...* shows the unit as the program plays it, with *Save cheat sheet...*
  (HTML or text, printable).
- *State at the start*: wounds already taken, Moved / Fatigued / Shaken, *Near
  terrain* (most models within 1" of terrain: Demolish, Grounded rules), *Feat used*
  (the unit uses its once-per-game ward Feat, Protection Feat, for every wound of the
  activation), a Tough(9)+ Hero within 6" (its Quality for Morale Tests), and the
  weapons to use (untick the ones that are not firing).

**The attack** (middle column):

- *Shooting*: distance, the attacker's action (Hold, Advance...), the target's cover,
  line of sight, Crossing Strike.
- *Melee (charge)*: the whole exchange (Impact, Counter, strikes, strike back with
  Fatigue, the strikes that come last (Unwieldy), Self-Destruct, melee result with
  Fear, Morale and Rout); *Charge from* is the distance the charger moved (rules that
  act "when charging from over 6\""), *Strike back* can be switched off and *Melee tie*
  says who loses a tie.
- *Spell*: a damage spell of the attacker's Caster, with the friendly and enemy spell
  tokens that help or hinder the casting roll, and *Cast via Spell Conduit*.
- *Deployed via Ambush this round*: for the rules that act on that round.
- Tokens and effects in play: *Spotter tokens* (+1 to hit each) and *AP spotter
  tokens* (+AP(1) each) the attacker removes, Marks on the target, the *Versatile*
  choices (rules with a choice per activation, and token counts such as Defensive
  Frenzy or Growth rules: none picked = no token; the target's are marked [target]), the *Spell effects (assumed cast)*
  of either side (buffs, Marks, debuffs) and the buff and debuff rules (a debuff of
  one side's book acts on the other side). Rules with a die roll (Unpredictable) are
  averaged exactly over the die.
- *Attacker's orders*: *Weapon order...* (with *Suggest*, the order that kills most
  models) and *Takedown targets...* (which models the Takedown weapons pick first).

**Results.** *Analyse* opens a result window (several may stay open):

- one row per weapon (that weapon alone against the full target) and a TOTAL row
  (all weapons in order, the real result);
- click a column heading to switch between mean, median and quartiles;
  double-click a row, or *Distribution*, for its full histogram;
- below the table: P(destroyed), P(Morale Test), P(Shaken), P(Rout), the melee result,
  points removed and the per-100-points metrics; when they apply, the wounds the
  attacker inflicts on itself (Hazardous) and No Retreat's failed tests counted as
  passed with the wounds they cost;
- *Audit* lists every modifier applied to each weapon and why; *Export CSV...* saves
  the table; *Pin* keeps the result for *Compare pins*, which shows pinned analyses
  side by side with their differences and survival curves.

Other tools: *Swap sides*; *Variants...* compares every option of one upgrade section
(the same analysis repeated for each option, with the points-efficiency metrics);
*Save session...* / *Load session...* store both sides and the setup, with a copy of
the books used, so a session reopens on the same data after an Army Forge update.

## 3. List Editor

**Left**: the list. *Name*, *Points limit* and *Force Org* (the optional limits of
the core rules: Heroes per 500 pts, copies per 1000 pts, 35% per unit, units per
200 pts, models per 20 pts; untick to ignore them). The table shows the entries with
their points; a joined Hero appears under its host. Below: *Add unit...* (pick a book
and a unit), *Duplicate*, *Remove*, *Up* / *Down*, *Inspect...*, then the total, the
problems found (Force Org, invalid choices) and the status line.

**Right**: the selected entry.

- *Label* (your name for it) and *Notes*.
- *Joined to*: join a Hero (up to Tough(6)) to a multi-model unit.
- *Combined (two copies)*; *Copy B has its own upgrades* when the copies differ.
- *Upgrades* (and *Copy B*): the upgrade sections, as in the Analyzer.
- *Placement...*: which model takes each upgrade (Army Forge does not say; by default
  the model with the fewest upgrades so far).
- *Drop invalid choices*: choices that no longer exist after a book update are kept
  and reported until you drop them.
- *Overrides (house rules, errata)*: change a stat, the points or a weapon of this
  entry without touching the book.

Toolbar: *New*, *Open...*, *Save*, *Save as...*, *Undo*, *Redo*, *Print roster...* (the
whole list as a printable HTML or text sheet) and *Local units...*.

**Local units** are home-made units kept in your own "local books": stats, weapons,
rules and upgrade sections typed in Army Forge style. A rule of your own can be given
a meaning in the **Rules Mapper**: effects of its own (e.g. +1 to hit when shooting),
or "behaves as" an existing rule under a new name. Local units can be used in lists,
in the Analyzer like any other unit.

## 4. Files

| Folder | Content |
|---|---|
| `data/army_forge/` | the Army Forge download (`af_fetch`), for personal use |
| `lists/` | army lists |
| `books_local/` | local books of home-made units |
| `sessions/` | Analyzer sessions |

After an Army Forge update, `af_fetch` prints what changed and which saved lists are
affected (choices re-linked by their label, choices or units that no longer exist).
`tools/update_report.py` prints that report again at any time, and
`tools/rules_report.py` checks that every rule and spell still has the text its
semantics were written for (`changed` = it has not). The whole procedure, with what to
do for each result, is in the README ("Updating the Army Forge data").

## 5. Limits

- Rules and spells are mapped for the core rules and all 49 Army Forge books
  (November 2026); `tools/rules_report.py` lists what is mapped in every book. Rules
  added or changed by a later Army Forge update have no effect in the results until
  they are mapped (they are never guessed).
- The programs cannot see the table: distances, line of sight, cover, terrain, aura
  ranges and tokens are yours to set. One analysis is one activation: rules that act
  outside it (movement, deployment, activation order, Morale Tests forced by a spell)
  have no effect in the results.
- Advanced (paid) rules are not implemented.
