"""Printable army roster of a list. Pure.

build() turns an army list and its ListResult into a Roster: a header
(name, points / limit, Force Org on or off and its violations, list
issues), then one app.unit_sheet.Sheet per entry in list order, a joined
Hero printed with its host (as it plays), Combined Units as resolved.
The rule texts and the spells are printed ONCE at the end (glossary),
each entry only names its rules, so a 2000 pts list stays readable.

Entries whose unit is missing cannot be printed: they are listed among
the problems. An entry with choices that no longer link is printed with
what did link, and the problem is in its notes.

entry_sheet() is the full sheet of one entry (List Editor "Inspect"):
a host with its joined Hero, or a Hero alone when the Hero is asked.
"""
from dataclasses import dataclass, field, replace

from grimdarkoracle.app import unit_sheet as US
from grimdarkoracle.data import force_org


@dataclass
class Entry:
    key: str
    points: int                     # host + joined Hero
    sheet: US.Sheet


@dataclass
class Roster:
    title: str
    header: list = field(default_factory=list)     # (label, value)
    problems: list = field(default_factory=list)   # violations, issues
    entries: list = field(default_factory=list)    # Entry
    rules: list = field(default_factory=list)      # (label, status, text)
    spells: list = field(default_factory=list)     # (book, sheet rows)


def _named(ru, lu):
    """The resolved unit under the list's label (as side_spec does)."""
    return replace(ru, name=lu.label) if lu.label and \
        lu.label != ru.name else ru


def _guests(army) -> dict:
    """Host key -> the first Hero joined to it (list order)."""
    out = {}
    for lu in army.units:
        if lu.joined_to and army.unit(lu.joined_to) is not None:
            out.setdefault(lu.joined_to, lu)
    return out


def _sheet(lib, army, result, lu, guest=None) -> US.Sheet:
    e = result.entries[lu.key]
    hero = None
    notes = [f"{lu.label or lu.unit_name}: {x}" for x in e.issues]
    if guest is not None:
        g = result.entries[guest.key]
        if g.unit is not None:
            hero = _named(g.unit, guest)
            notes += [f"{guest.label or guest.unit_name}: {x}"
                      for x in g.issues]
    sheet = US.build(lib.reg, _named(e.unit, lu), hero,
                     lib.books.get(lu.book), lib.sreg)
    sheet.notes = notes + sheet.notes
    return sheet


def entry_sheet(lib, army, result, key: str) -> US.Sheet | None:
    """Full sheet of entry 'key': a host with its joined Hero, a Hero (or
    any other unit) alone; None when its unit is missing."""
    lu = army.unit(key)
    if lu is None or result.entries[key].unit is None:
        return None
    guest = _guests(army).get(key)
    return _sheet(lib, army, result, lu, guest)


def _header(lib, army, result) -> list:
    books = []
    for uid in army.books:
        b = lib.books.get(uid)
        books.append(f"{b.name} {b.version}" if b else f"{uid} (missing)")
    fo = "on" if army.force_org else "off"
    return [("Points", f"{result.points} / {army.points_limit}"),
            ("Entries", str(len(army.units))), ("Force Org", fo),
            ("Books", ", ".join(books) or "-")]


def build(lib, army, result) -> Roster:
    """Roster of 'army' (data.army_list.ArmyList) resolved as 'result'
    (ListResult), with the library 'lib' (reg, sreg, books)."""
    ro = Roster(army.name, _header(lib, army, result))
    ro.problems = [v.message for v in force_org.check(army, result)] + \
        list(result.issues)
    guests = {h: g for h, g in _guests(army).items()
              if result.entries[h].unit is not None}
    with_host = {g.key for g in guests.values()}
    rules: dict = {}
    spells: dict = {}
    for lu in army.units:
        e = result.entries[lu.key]
        if e.unit is None:
            ro.problems.append(f"{lu.label or lu.unit_name or lu.unit_id}: "
                               "unit not found, not printed")
            continue
        if lu.key in with_host:
            continue                    # printed with its host
        guest = guests.get(lu.key)
        sheet = _sheet(lib, army, result, lu, guest)
        pts = e.points + (result.entries[guest.key].points if guest else 0)
        ro.entries.append(Entry(lu.key, pts, sheet))
        for row in sheet.rules:
            rules.setdefault((row[0], row[2]), row)
        b = lib.books.get(lu.book)
        if sheet.spells and b is not None:
            spells.setdefault(b.name, sheet.spells)
    ro.rules = sorted(rules.values(), key=lambda r: r[0].lower())
    ro.spells = list(spells.items())
    return ro


# --- renderers ------------------------------------------------------------------------


def to_text(ro: Roster) -> str:
    out = [ro.title, "=" * len(ro.title)]
    out += [f"{k}: {v}" for k, v in ro.header]
    out += ["", "Problems"] + [f"  {x}" for x in ro.problems] \
        if ro.problems else ["No problems"]
    for n, e in enumerate(ro.entries, 1):
        lines = US.text_lines(e.sheet, texts=False)
        lines[0] = f"{n}. {lines[0]}"
        lines[1] = "-" * len(lines[0])
        out += ["", ""] + lines
    out += ["", "", "Rules", "====="]
    out += [f"{lb}{'' if st == 'ok' else f' [{st}]'}: {tx}"
            for lb, st, tx in ro.rules]
    for book, rows in ro.spells:
        out += ["", f"Spells ({book})"]
        out += [f"  {name} ({tok}){'' if st == 'ok' else f' [{st}]'}: {eff}"
                for name, tok, eff, st in rows]
    return "\n".join(out) + "\n"


def to_html(ro: Roster) -> str:
    e_ = US.esc
    parts = [f"<h1>{e_(ro.title)}</h1>",
             US.table(("", ""), [(e_(k), e_(v)) for k, v in ro.header])]
    if ro.problems:
        parts.append("<ul>" + "".join(f'<li class="warn">{e_(x)}</li>'
                                      for x in ro.problems) + "</ul>")
    else:
        parts.append('<p class="dim">No problems</p>')
    for n, e in enumerate(ro.entries, 1):
        sheet = replace(e.sheet, title=f"{n}. {e.sheet.title}")
        parts.append('<div class="entry">' +
                     "\n".join(US.html_parts(sheet, False, 2)) + "</div>")
    parts += ["<h2>Rules</h2>", US.rules_table(ro.rules)]
    for book, rows in ro.spells:
        parts += [f"<h2>Spells ({e_(book)})</h2>", US.spells_table(rows)]
    return US.page(ro.title, parts, "GrimDarkOracle army roster")


def render(ro: Roster, path: str) -> str:
    """HTML for a .htm / .html path, text otherwise (ui.save_text)."""
    return to_html(ro) if path.lower().endswith((".html", ".htm")) \
        else to_text(ro)
